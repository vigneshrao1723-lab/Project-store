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

Stock is held for `RESERVATION_MINUTES` (default 15). Every transition lives in `services/orders.py` and is idempotent, because the browser redirect and the Razorpay webhook can both report the same payment.

## Payments

* The amount is always computed on the server from the order. The browser never sends a price.
* Razorpay mode: the server creates a Razorpay order, the browser opens Checkout, and on success the handler posts `order_id|payment_id|signature` back. The server verifies the HMAC-SHA256 with the key secret (constant-time compare) and checks that the gateway order id belongs to *this* order.
* The webhook (`/webhooks/razorpay`) is the backup for closed tabs. It is CSRF-exempt and authenticated by its own signature header instead.
* With no Razorpay keys set, a practice gateway runs the same signing and confirmation code, so tests, CI and local demos exercise the real path.

## Security notes

* CSRF tokens on every form and on every API write (`X-CSRFToken`).
* Post-login redirects accept same-site relative paths only.
* Users can read only their own orders; admin routes return 403 to everyone else.
* Content-Security-Policy, `X-Frame-Options`, `nosniff`, `Referrer-Policy` on every response. No inline scripts.
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

The concurrency tests need real row locks, so they skip on SQLite and run in CI against a MySQL service. Removing the `FOR UPDATE` makes them fail, which is how we know they test the right thing.

## Known limits and next steps

* Migrations run when the web container starts. Two web containers starting at once would race; run `flask db upgrade` as a separate step if you scale out.
* No email. Download links are shown on the order page only.
* Refunds are tracked, not issued: an admin refunds in the Razorpay dashboard and then marks the order refunded.
* Login has no rate limiting. Put the app behind a reverse proxy that limits `/login`, or add Flask-Limiter.
* Cart is for signed-in users only.
