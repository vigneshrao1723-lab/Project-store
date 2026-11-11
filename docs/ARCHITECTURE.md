# Architecture

Project Store is a server-rendered Flask application with a JSON REST API, backed by MySQL. This note records the decisions that matter and why they were made.

## Shape of the system

```
Browser ──► Flask app (gunicorn, 3 workers)
             ├─ blueprints: shop, auth, cart, checkout, account, admin, api (/api/v1), webhooks
             ├─ services:   orders (state machine + stock), cart, catalog, payments, products
             └─ SQLAlchemy ──► MySQL 8
Razorpay ◄──► checkout.js in the browser, plus a signed webhook back to /webhooks/razorpay
sweeper container: `flask release-expired` every 60s
```

Pages are rendered with Jinja and hand-written CSS. The cart and the quantity controls call the same `/api/v1` endpoints that third parties could use, so the API is exercised by the UI and not a side feature.

## Data model

| Table | Purpose |
|---|---|
| `users` | Customers and admins. Passwords are salted hashes (Werkzeug). |
| `categories`, `products` | Catalogue. Money is stored as integer paise, never floats. `CHECK (stock >= 0)` is a last line of defence in the database itself. |
| `cart_items` | One row per user and product, unique together. |
| `orders`, `order_items` | An order snapshots title and unit price at purchase, so later price edits never rewrite history. |
| `inventory_log` | Append-only ledger of every stock change (`seed`, `reserve`, `release`, `adjust`). Current stock must always equal the sum of the ledger; a test asserts this. |
| `login_throttle` | One row per (email, IP) with its recent failed sign-ins and, once blocked, `locked_until`. See "Sign-in limit" below. |

The schema is created and changed only by the Alembic migrations in `migrations/`. `docker-entrypoint.sh` runs `flask db upgrade` before the app starts; `create_all` is used only by the tests. A test fails if the models and the migrations ever disagree. Databases built by the old `create_all` start-up are adopted at revision `0001` by `flask adopt-legacy-db` and then upgraded, so they keep their data.

## The checkout transaction

This is the part that has to be right. Reserving stock happens in one transaction in `services/orders.create_order_from_cart`:

1. Read the user's cart lines.
2. `SELECT ... FOR UPDATE` on every product involved, **in ascending id order**. Locking in a fixed order means two buyers with overlapping baskets cannot deadlock.
3. Check every line against stock. If any line fails, roll back and report every problem. Nothing is partially reserved.
4. Decrement stock, write `order` + `order_items` + ledger rows, delete the cart lines, commit.

A second submit of the same checkout finds an empty cart and is refused, so a double click cannot create two orders.

## Order lifecycle

```
pending ──pay──► paid
   │
   ├─cancel──► cancelled      (stock released)
   ├─timeout─► expired        (stock released by the sweeper or the next request)
   └─gateway down─► failed    (stock released)

expired/cancelled ──late payment──► paid        if stock can be re-taken
                                └─► refund_due  if it sold out meanwhile ──admin──► refunded
```

A user has **at most one unpaid order**: `create_order_from_cart` takes a lock on the user's row, then refuses with `PendingOrderExists` (which carries the existing order) if one is still pending. The web checkout redirects to that order's pay page, and `POST /api/v1/checkout` answers 409 with the order and how to pay it. Cancelling it, paying it or letting its hold run out lets the user check out again. Stock is held for `RESERVATION_MINUTES` (default 15). Every transition lives in `services/orders.py` and is idempotent, because the browser redirect and the Razorpay webhook can both report the same payment.

## Payments

* The amount is always computed on the server from the order. The browser never sends a price.
* Razorpay mode: the server creates a Razorpay order, the browser opens Checkout, and on success the handler posts `order_id|payment_id|signature` back. The server verifies the HMAC-SHA256 with the key secret (constant-time compare) and checks that the gateway order id belongs to *this* order.
* A valid signature is not enough on its own. Before an order is marked paid, the payment's **amount (integer paise), currency (`INR`), status (`captured`) and Razorpay order id are compared with the order**. The webhook gets them in the event; the browser routes fetch the payment from Razorpay's API (`GET /v1/payments/<id>`) with the key pair, because the browser's word is not evidence. If that lookup fails or the payment is not captured yet, the order stays pending and the webhook marks it paid when Razorpay reports the capture. **Set payment capture to automatic in the Razorpay dashboard**, or orders will wait for a manual capture.
* The webhook (`/webhooks/razorpay`) is the backup for closed tabs. It is CSRF-exempt and authenticated by its own signature header instead. A correctly signed event that does not match its order is logged and answered `{"ok": false}` with HTTP 200 (so Razorpay stops retrying) and changes nothing.
* With no Razorpay keys and `ALLOW_PRACTICE_GATEWAY` on, a practice gateway runs the same signing and confirmation code, so tests, CI and local demos exercise the real path. The flag defaults to off: with neither keys nor the flag, `payments.mode()` is `"off"`, orders get no gateway id, the pay page says payment is unavailable, and no signature verifies, so a deployment that forgot its keys cannot mark anything paid.
* `SECRET_KEY` must be at least 32 characters and not a placeholder, or `create_app` raises (unless `TESTING` or debug is on). The check does not depend on `FLASK_ENV`.

## Security notes

* CSRF tokens on every form and on every API write (`X-CSRFToken`).
* Rate limits (`services/rate_limit.py`, table `rate_limits`, limits in `Config.RATE_LIMITS`): registration 10 an hour per address, starting a checkout 10 per 10 minutes per user, confirming a payment 20 per 10 minutes per user, and 20 failed sign-ins per 10 minutes per address across all emails. Past a limit the answer is HTTP 429 with `Retry-After` (JSON under `/api`). Like the sign-in limit it lives in the database, so the 3 gunicorn workers share it, and it takes a row lock so two requests cannot both slip under it.
* Sign-in limit: 5 failures for one email and IP block that pair for 10 minutes (HTTP 429). The state is a database table, not process memory, because gunicorn runs 3 workers and an in-memory counter would let through 5 attempts per worker. While blocked the password is not even checked, and unknown emails are counted like real ones so the block does not reveal which accounts exist. The IP is the connection's address; `X-Forwarded-For` is not trusted because clients can forge it.
* **Sessions.** The session and remember-me cookies hold `<user id>:<session token>`. The token is a per-user random value in `users.session_token`; signing out and changing a password replace it, so every cookie issued before that moment stops working, even a copy someone kept. The cost: signing out on one device signs the account out everywhere. Both cookies expire after 14 days, are `HttpOnly` and `SameSite=Lax`, and are `Secure` when `COOKIE_SECURE=true`. Signing in (or registering) clears the old session first, which also replaces the CSRF secret.
* **Passwords** are scrypt at the OWASP minimum (`PASSWORD_HASH_METHOD`, N=2**17, r=8, p=1: 128 MiB and about 0.4 s a hash). Hashes made with a lower cost are upgraded at the user's next sign-in. An unknown email is checked against a dummy hash of the same cost, so the response time does not reveal which emails have accounts. Each concurrent sign-in holds 128 MiB, which is why the sign-in throttle and the 128-character password cap matter.
* **Accepted risk:** registering an email that already has an account says so ("An account with this email already exists"), which reveals that the address is registered. Fixing it properly needs email (send "you already have an account" to the address instead of answering in the page), so it is left as is until the store sends email.
* Post-login redirects accept same-site relative paths only; control characters in the `next` value make it fall back to the home page.
* Input is parsed in `app/validation.py`: every number has explicit bounds (quantity, product id, price, stock, page), prices go from rupees to integer paise through `Decimal` (never a float), every text field has a length cap that matches its column, and passwords are limited to 8-128 characters so a huge value is never fed to scrypt. A bad value is a 400 or 422, never a 500. JSON bodies must be objects (`json_body()`).
* Request bodies over 1 MB get HTTP 413 before any route reads them. Anything under `/api/` answers errors as `{"error": ...}` JSON, including 404, 405, 413, CSRF failures and 500.
* The payment routes under `/checkout` serve only the order's owner. An admin reads and cancels customer orders from `/admin`, never pays for them.
* Users can read only their own orders; admin routes return 403 to everyone else.
* On every response: Content-Security-Policy (with `frame-ancestors 'self'`, `form-action 'self'`, `base-uri 'self'`), `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` (camera, microphone, geolocation and USB off; `payment` only for this site and Razorpay) and `Cross-Origin-Opener-Policy: same-origin-allow-popups` (not `same-origin`, which would sever the windows Razorpay opens). `Strict-Transport-Security` (one year, no `includeSubDomains`) is sent only when `COOKIE_SECURE=true`, i.e. when the site is served over HTTPS. Pages for a signed-in visitor carry `Cache-Control: no-store`. No inline scripts and **no inline styles**: `style-src` is `'self'` only, so templates carry no `style=` attribute (the old ones are classes in `main.css`) and the dashboard's bar heights are the `height` attribute of an empty `<svg>`, which CSP does not treat as a style. Keep it that way: a test fails if a `style=` or `<style>` appears in a template.
* **Razorpay and `style-src`:** Razorpay's `checkout.js` is third-party script running in our page. If it injects a `<style>` element into the page, `style-src 'self'` blocks it and the payment window can look broken. This has not been tried against a live Razorpay account. If the window is unstyled, check the browser console for "Refused to apply inline style", and the narrowest fix is to allow only style *elements*, keeping attributes blocked: add `style-src-elem 'self' 'unsafe-inline'` next to `style-src 'self'` in `security_headers()` (`app/__init__.py`).
* Cover art is built from the product title in `covers.py`, which escapes it with `markupsafe.escape`; `Markup` is applied once, in `app/__init__.py`, to the finished drawing (and carries the bandit `# nosec` with that reason). A test fails if `|safe`, `Markup(` or `render_template_string` appears anywhere else.
* Docker: MySQL's passwords have no defaults (`${DB_PASSWORD:?}`), the database port is not published, the app connects as the `store` user (never root), the MySQL health check carries no password, and `.dockerignore` keeps `.env*`, bytecode, `.venv`, `.vscode`, `*.db` and source maps out of the image.
* Fonts are self-hosted, so the page makes no third-party requests apart from Razorpay on the payment page.
* Secrets come from the environment. `.env` is git-ignored.

## Testing strategy

| Layer | What it proves |
|---|---|
| Service and API tests | Reserve, pay, expire, cancel, late payment, refund; idempotency; tampered and cross-order signatures; ledger equals stock; price snapshots |
| Page tests | Every public and admin page renders; auth, redirects, validation messages |
| Razorpay-mode tests | Real client code path with the HTTP call mocked, outage handling |
| CSRF tests | Writes are refused without a token |
| Concurrency tests (MySQL) | 10 buyers racing for 3 copies produce exactly 3 winners; mixed baskets neither deadlock nor oversell |
| Migration tests (SQLite, and MySQL in CI) | Migrations build exactly the schema the models describe; every one can be undone; an old `create_all` database is adopted with its data intact |
| Sign-in limit tests | Block on the 5th failure for 10 minutes, per email and per IP, even for the right password; counts reset on success and after quiet periods; unknown emails block identically |

The concurrency tests need real row locks, so they skip on SQLite and run in CI against a MySQL service. Removing the `FOR UPDATE` makes them fail, which is how we know they test the right thing.

## Known limits and next steps

* Migrations run when the web container starts. Two web containers starting at once would race; run `flask db upgrade` as a separate step if you scale out.
* No email. Download links are shown on the order page only.
* Refunds are tracked, not issued: an admin refunds in the Razorpay dashboard and then marks the order refunded.
* The sign-in limit is per email and IP. Behind a reverse proxy all visitors share the proxy's address until `ProxyFix` is configured for it, and one address trying many emails is not slowed. Registration has no limit.
* Cart is for signed-in users only.
