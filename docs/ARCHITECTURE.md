# Architecture

Project Store is a server-rendered Flask application with a JSON REST API, backed by MySQL. This note records the decisions that matter and why they were made.

## Shape of the system

```
Browser ──► Flask app (gunicorn, 3 workers)
             ├─ blueprints: shop, auth, cart, checkout, account, admin, api (/api/v1), webhooks
             ├─ services:   orders (state machine + stock), cart, catalog, payments, products, login_throttle, rate_limit
             └─ SQLAlchemy ──► MySQL 8
Razorpay ◄──► checkout.js in the browser, plus a signed webhook back to /webhooks/razorpay
sweeper container: `flask release-expired` every 60s
```

Pages are rendered with Jinja and hand-written CSS. The cart and the quantity controls call the same `/api/v1` endpoints that third parties could use, so the API is exercised by the UI and not a side feature.

## Data model

| Table | Purpose |
|---|---|
| `users` | Customers and admins. Passwords are salted scrypt hashes (Werkzeug). `session_token` is the per-user value every sign-in cookie must carry. |
| `categories`, `products` | Catalogue. Money is stored as integer paise, never floats. `CHECK (stock >= 0)` is a last line of defence in the database itself. |
| `cart_items` | One row per user and product, unique together. |
| `orders`, `order_items` | An order snapshots title and unit price at purchase, so later price edits never rewrite history. |
| `inventory_log` | Append-only ledger of every stock change (`seed`, `reserve`, `release`, `adjust`). Current stock must always equal the sum of the ledger; a test asserts this. |
| `login_throttle` | One row per (email, IP) with its recent failed sign-ins and, once blocked, `locked_until`. See "Security notes" below. |
| `rate_limits` | One row per (limit name, client) with the hits in the current window. Backs the registration, checkout, payment-confirmation and per-address sign-in limits. |

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

## Motion

A small, optional motion layer on the home page, the catalogue and the product page. Every page works and reads the same without it, so a failed script, a blocked `sessionStorage` or `prefers-reduced-motion` only means nothing moves.

| Piece | Where | What it does |
|---|---|---|
| `static/js/motion-boot.js` | plain script in `<head>` | Adds `.intro-run` to `<html>` on the first page of a browser session (storage works, reduced motion off). Sets its flag at once, so a broken `motion.js` can show the loader at most once. |
| Loader | `base.html`, CSS "intro loader" | Hidden by default. A pure-CSS timeline plays a six-object line-art scene (inbox, cart, TV, PC, CPU, RAM) and fades out by 1.2 s; a second animation hides it at 2 s whatever else fails. `pointer-events: none`, nothing focusable, only the loader is `aria-hidden`. |
| `static/js/motion.js` (deferred, about 6 KB) | end of `<body>` | Counts the loader percentage and removes `.intro-run` when the loader's own exit animation ends. Runs the card interactions below. No timers; everything is cleaned up on `pagehide`. |
| `_macros.html` `fx_back()` / `fx_panel(kind)` | tiles, hero plate, product plate | Two `aria-hidden` layers inside the cover's box: a flat ink/yellow backdrop behind the cover and a small corner panel with the category's motif. Chosen by `p.category.cover_kind` (`data-motion-kind`), never by title or id. |

**One active card at a time.** `motion.js` puts `.is-active` on the card the user is pointing at (fine pointers only), has keyboard focus on (`:focus-visible`; focus in the product's purchase box plays the plate's motif), or is pressing (any pointer; touch rests on `pointerup` or `pointercancel`). The CSS does the rest and returns to rest when the class goes. The cover zooms 1.02-1.035 and tilts 1-2 degrees over the backdrop. Sold-out tiles get no panel.

| Category (`cover_kind`) | Motif |
|---|---|
| `crypto` | a packet crosses a tiny lattice and drops into an envelope; the flap closes |
| `ai` | two document panes and three source cards arrive; a data node pulses once |
| `web` | three storefront panes stack; two project tiles drop into a cart |
| `hardware` | the display wakes; CPU pins pulse twice; two RAM sticks drop into their slots |

Rules every change here must keep (tests in `tests/test_motion_*.py` enforce them): only `transform` and `opacity` are animated; `will-change` appears only on the `.is-animating` class the script sets while the cover transitions; hover effects live only under `(hover: hover) and (pointer: fine)`; no gradients, shadows, external assets or inline styles and scripts; content is visible by default; and **pressing never changes the pressed element's own box** (a scale shrinks the hit area, so a press near an edge ends outside the element and the click is lost; tiles dim their text block and buttons dim themselves instead). Navigation is never delayed or cancelled.

## Scroll system

One vocabulary, one script, one observer, one animation-frame loop. Pages do not write their own scroll code: they put attributes on elements through two macros in `_macros.html`, and `static/js/fx-scroll.js` does the rest. Styles live in `static/css/motion3.css` and nowhere else.

**The vocabulary.** Five words, spelled only by the macros (a test fails if a template writes `data-fx` by hand):

| Word | What it does | Example |
|---|---|---|
| `rise` | One block comes in once, as it nears the screen: it fades up by `--fx-dist` (14 px). | `<div class="section-head" {{ fx('rise') }}>` |
| `cascade` | On a parent. Each direct child rises once, as it nears the screen. Children that arrive together are staggered by `--fx-stagger` (60 ms) in document order, the first 8 of a batch; later ones share the last step. | `<div class="grid" {{ fx('cascade') }}>{% for p in items %}{{ tile(p) }}{% endfor %}</div>` |
| `count` | A figure counts up once, in about 0.9 s. The macro writes the number three times (target, a sizing copy and the live text), so the box is as wide as the final figure and counting moves nothing. | `{{ fx_count(n_projects) }}` |
| `pin` | A tall section holds a scene on screen. The script writes `--p` (0 to 1) on the section while it is near the screen; children marked `.fx-move` turn that into sideways slides and growth. The section's height comes from `--pin-h`; add `.pin-lg` to pin on screens 900 px wide and up only, never on phones, or `.pin-soft` to never pin (the progress then follows how far the section has come up the screen). The home showcase is `.pin-lg`: pinned on large screens with three scenes (the covers slide in from both sides, the headline changes, a counter reads 01 / 02 / 03), and scroll-linked but not pinned on phones and under `fx-lite`. | `<section class="scene pin-lg" {{ fx('pin') }}><div class="fx-stage">...<figure class="fx-move">` |
| `parallax` | A few pixels of drift against the scroll. The script writes `--py` (-1 to 1) while the element is near the screen. Transform only. | `<div class="sc-art" {{ fx('parallax') }}>{{ cover(p) }}</div>` |

**Variants.** More words in the same vocabulary, each a named effect that can be switched off by listing its word in `OFF` at the top of `fx-scroll.js` (the script then treats it as already in place and adds `fx-off-<word>` to `<html>` for CSS-only effects):

| Word | What it does | Example |
|---|---|---|
| `from-left`, `from-right`, `zoom`, `flip` | A single block enters from a side, grows, or flips down. For a cascade's children, put `.fx-alt` (alternate sides), `.fx-zoomc` or `.fx-flipc` on the parent. | `<div class="hs-head" {{ fx('from-left') }}>` |
| `clip` | A cover is wiped in from the top by `clip-path` while its drawing settles from 1.08x. | `<div class="plate-cover" {{ fx('clip') }}>` |
| `lines` | A headline comes up line by line out of a mask. Lines are explicit, so a responsive wrap never splits one. | `<h1 {{ fx('lines') }}>{{ fx_lines('Real engineering projects,', 'ready to run.') }}</h1>` |
| `words` | Copy fades up word by word (the macro numbers at most 30 words). | `<p {{ fx('words') }}>{{ fx_words(p.tagline) }}</p>` |
| `draw` | An SVG line draws as the block crosses the screen (`--d`, 0 to 1) and the steps along it light up. | `<div class="tl-wrap" {{ fx('draw') }}>...<path pathLength="100" class="tl-draw"/>` |
| `hscroll` | A sideways shelf. A plain swipe row on phones, in `fx-lite` and without the script; on large screens it is pinned and the track slides with the vertical scroll. | `<section class="shelf" {{ fx('hscroll') }}><div class="hs-stage fx-stage"><ul class="hs-track">` |
| `marquee` | A slow CSS-only ticker; pauses on hover, stops for reduced motion, a plain wrapped list without the script. | `<div class="marquee" {{ fx('marquee') }}>` |
| `tilt`, `magnetic` | Pointer feedback on fine pointers only: tiles lean up to 6 degrees with a flat yellow disc following the pointer; a primary button leans up to 6 px toward the pointer. Written straight onto the one element under the pointer. | `<a class="tile" {{ fx('tilt') }}>`, `<a class="btn" {{ fx('magnetic') }}>` |

Other pieces that are not words: the section rail (`<nav class="rail">`, desktop only, fills as the home page's sections go by), three parallax layers of line-art in the home hero (`.px-1`, `.px-2`, `.px-3` set their speed with `--pm`), and cross-document view transitions (`@view-transition { navigation: auto }` with a named cover that travels from the card you point at to the product page; ignored by browsers without support).

**Adaptive quality.** `html.fx-lite` turns off only the heaviest items: pinned sticky stages become scroll-linked (and the sideways shelf becomes a swipe row), and big parallax stops. The script sets it when `navigator.hardwareConcurrency <= 4`, `navigator.deviceMemory <= 4`, or the first 500 ms of frames average under 45 fps. `?fx=lite` or `?fx=full` in the address forces it either way. Everyone else gets every effect; the budget is measured at normal speed (p95 at most 16.7 ms), and the 4x CPU throttle is only a stress diagnostic.

**Measured limit.** At normal speed every page class holds about 7 ms per frame on desktop and phone (p95 at most 21 ms, worst 42 ms, on the home page). Under a 4x CPU throttle the home page averages about 28 ms per frame: style recalculation dominates (about 16 ms of it per frame), it is spread over the page rather than one effect, and `fx-lite` does not reduce it. That is a known limitation, not a fixed one.

**Defaults are visible.** The page as the server renders it has no hidden state, no taller sections and no sticky stages. Every hiding rule in `motion3.css` starts with `html.fx-on`, a class the script adds only after it has checked that reduced motion is off and `IntersectionObserver` exists. Anything already on screen at that moment gets `.is-in` first, so nothing flashes. With no script, a blocked script, reduced motion or no observer, the page is simply finished. A focused element is never left hidden: `focusin` brings in its `data-fx` ancestors, and shows a pinned scene whole.

**Page classes.** `base.html` puts `data-page` on `<body>` from `{% block page_class %}`:

| Class | Pages | Treatment |
|---|---|---|
| `browse` (the default) | home, catalogue, product | Full: rise, cascade, count, pins, a product scene using that product's own generated cover, a scroll-progress hairline, a footer rise. |
| `transactional` | cart, checkout, pay, sign in, register | Scroll words on headings and read-only summaries only (a test fails if any element that starts hidden contains a form control, button or link, the footer aside). Fields, labels, buttons and error messages are never hidden. The interface layer below gives them motion that hides nothing. |
| `account` | orders, order detail | Table rows cascade. The payment-result sequence (`fx-pay.js`) is separate and unchanged. |
| `admin` | admin dashboard, orders, products | One-shot words only (figures count up, rows fade in, the heading flips in) plus the interface layer; no scenes, pointer effects, hairline or rail. A test checks the templates and the rendered pages. |
| `none` | error pages | No `data-fx`, no scripts. |

**One loop.** The script creates a single `IntersectionObserver` (it watches every `rise`, every cascade child, every `count`, and every `pin` and `parallax` element) and a single `requestAnimationFrame` loop that runs only while something needs it: a pin or parallax element is near the screen, a counter is counting, or a scroll just happened. Reads are batched before writes, the scroll and resize listeners are passive, the loop stops while the tab is hidden, `will-change` is set only on `.fx-move` elements of a pin that is near the screen, and everything is undone on `pagehide`. The loop also keeps the header's condensed state (past 40 px) and the progress hairline's `--sp`, which is written on the hairline's own node and never on `<html>` (a custom property on the root makes the browser restyle every element on every scroll frame; that cost 90 ms per frame at 4x throttle before it was moved).

**Tokens.** `--fx-dist`, `--fx-ease`, `--fx-stagger` and `--fx-dur` are defined once in `motion3.css` and used only there.

**The interface layer.** `static/css/motion3-ui.css` and `static/js/fx-ui.js` hold the motion that belongs to controls and to the pages people pay and sign in on. Nothing in it hides a control, and it has no observer and no animation-frame loop.

| Piece | What it does |
|---|---|
| Checkout stepper (`stepper(n)` macro) | Cart, Details, Pay, Done; decorative (`aria-hidden`); the line into the current step draws. |
| Fields (`field()` macro) | A focus underline that draws from the left, an error shake (420 ms, once), a success tick that draws (`:user-valid`). |
| Posting button | While a form posts the button shows a spinning arc and a second submit of the same form is ignored (released after 15 s, or on a back-forward-cache return). The add-to-cart form handles its own guard and is left alone. |
| Toasts | Flash messages leave the page flow (only while `fx-ui.js` runs), slide in, and success and info ones drain a timer line and slide out after six seconds. Errors stay. |
| Cart | A removed row comes back as a harmless ghost that slides out; changed totals, counts and line totals tick; the empty cart bobs. |
| Order timeline (`order_timeline(order)` macro) | Placed, Paid, Ready to download, drawn to match the status. Downloads show a "preparing" state when pressed. |
| Sign in and register | Slow line-art drifts behind the form. |
| Everywhere | An animated focus ring, press feedback, an underline wipe on navigation links, a hover lift on cards; table rows light on hover in admin. |

**Switches.** One list turns any effect off: `OFF` at the top of `fx-scroll.js`. Names: the `data-fx` words above (`rise from-left from-right zoom flip clip lines words count cascade pin hscroll parallax draw tilt magnetic marquee`) and `rail stepper inputs shake toasts cart downloads forms drift bob timeline focus-ring press wipe lift`. Each becomes an `fx-off-<name>` class on `<html>`; a data-fx word is also treated as already in place. View transitions are one `@view-transition` rule in `motion3.css`; delete it to switch them off.

**Image fade-in.** The covers are generated inline SVG and arrive with the page, so there is no raster image load to smooth; they get the `clip` wipe instead.

**Inventory.** `docs/MOTION_INVENTORY.md` lists every effect with a literal hook; `tests/test_fx_inventory.py` fails if a listed hook disappears. Motion work is additive.

**Rules a change here must keep** (enforced in `tests/test_fx_*.py`): only `transform` and `opacity` change with scroll (plus `clip-path`, and `stroke-dashoffset` on drawn lines, which are paint-only; the focus ring animates `outline-offset`); no hiding without `html.fx-on`; no `:hover` dependence outside the fine-pointer query; nothing but one-shot words in admin and nothing at all on error pages; no control is ever hidden at first paint; at most one observer and one queued frame in `fx-scroll.js`; `fx-ui.js` has neither; no routes, services, models or headers involved.

## Tuning the motion

Every number someone is likely to want to change is a CSS custom property in `static/css/fx-tuning.css`, loaded before `motion3.css`: overall speed, travel distance, stagger, easing, tilt and magnet strength, parallax strength, how far the showcase covers start from the side, loader length, the Add to cart and payment-mark lengths and the marquee speed. Change a value and reload; nothing else needs editing. `fx-cart.js`, `fx-pay.js` and `motion.js` read the same properties, so the scripted effects follow.

Any single effect can be switched off by listing its name in `app/fx.json` (`{"off": ["tilt"]}`). The context processor writes the list to `<html data-fx-off="...">` before first paint, so CSS-only effects switch off with no script, and `fx-scroll.js` and `fx-ui.js` skip the effects they own. `docs/MOTION_TUNING.md` lists every knob and every switch name with a good range; `docs/MOTION_INVENTORY.md` lists every effect with the switch that turns it off, and a test fails if a listed effect disappears from its file.

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
| Security suite (`tests/security`) | One file per audit item: headers and CSP, secret and gateway start-up checks, error pages, admin and access control, authentication, XSS, password hashing, rate limits, input validation, CORS, exposed files, dependency locks |
| Rate limit, session, validation and one-unpaid-order tests | Window and 429 behaviour, per-user and per-address keys, cookies dying on sign-out, bounds on every input, the second checkout redirected to the unpaid order |
| Motion, layout and phone tests | The stylesheet rules that keep motion safe (only `transform` and `opacity`, hover only for fine pointers, nothing hidden by default), the markup hooks, the scripts run under Node, and no horizontal overflow at phone widths |

The concurrency tests need real row locks, so they skip on SQLite and run in CI against a MySQL service. Removing the `FOR UPDATE` makes them fail, which is how we know they test the right thing.

## Known limits and next steps

* Migrations run when the web container starts. Two web containers starting at once would race; run `flask db upgrade` as a separate step if you scale out.
* No email. Download links are shown on the order page only.
* Refunds are tracked, not issued: an admin refunds in the Razorpay dashboard and then marks the order refunded.
* The sign-in limit is per email and IP, plus a per-address cap across emails. Behind a reverse proxy all visitors share the proxy's address until `ProxyFix` is configured for it.
* No password reset (there is no email to send it to), and registering an existing email reveals that it is registered (see "Accepted risk" above).
* The Razorpay client code and webhook are tested against a mocked API only; they have not run against a live Razorpay account.
* Cart is for signed-in users only.
