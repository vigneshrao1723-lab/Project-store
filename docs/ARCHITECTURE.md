# Architecture

Project Store is a server-rendered Flask application with a JSON REST API, backed by MySQL. This note records the decisions that matter and why they were made.

## Shape of the system

```
Browser ──► Flask app (gunicorn, 3 workers)
             ├─ blueprints: shop, auth, cart, checkout, account, admin, api (/api/v1), webhooks, contact, orderdocs
             ├─ services:   orders (state machine + stock), cart, catalog, payments, products, login_throttle, rate_limit,
             │              notify (order messages: email / WhatsApp / outbox), guide (setup guide renderer), privacy
             └─ SQLAlchemy ──► MySQL 8
Razorpay ◄──► checkout.js in the browser, plus a signed webhook back to /webhooks/razorpay
SMTP server / Meta WhatsApp Cloud API ◄── order messages, only when configured (otherwise they wait in the outbox)
sweeper container: `flask release-expired` and `flask send-messages` every 60s
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
| `rate_limits` | One row per (limit name, client) with the hits in the current window. Backs the registration, checkout, payment-confirmation and per-address sign-in limits, and the contact-form and order-message limits. |
| `contact_messages` | Messages from the contact form (v1.3): names, email, subject, message, the consent box and when an admin marked it handled. The IP is not stored. |
| `orders.contact_channel`, `contact_value`, `contact_consent_at` | Where the buyer asked for the invoice and setup guide (email, or a WhatsApp number in E.164) and when they consented. Empty when they did not ask. |
| `messages` | The order-message outbox (v1.3): one row per (order, kind, channel), unique together, with the status (`queued`, `sent`, `failed`, `not_configured`), attempts, next attempt time, a short last error and the rendered text. |
| `contact_optouts` | The do-not-contact list: only a keyed hash of each contact that pressed "stop". |
| `products.setup_guide`, `guide_edited` | The setup guide shown on the order page, the guide page and in the message; `guide_edited` is set when an admin changes it, and `flask seed` never overwrites an edited guide. |

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
| `_macros.html` `fx_back()` / `fx_panel(kind)` | tiles, hero plate, product plate | Two `aria-hidden` layers inside the cover's box: a flat violet/amber backdrop behind the cover and a small corner panel with the category's motif. Chosen by `p.category.cover_kind` (`data-motion-kind`), never by title or id. |

**One active card at a time.** `motion.js` puts `.is-active` on the card the user is pointing at (fine pointers only), has keyboard focus on (`:focus-visible`; focus in the product's purchase box plays the plate's motif), or is pressing (any pointer; touch rests on `pointerup` or `pointercancel`). The CSS does the rest and returns to rest when the class goes. The cover zooms 1.02-1.035 and tilts 1-2 degrees over the backdrop. Sold-out tiles get no panel.

| Category (`cover_kind`) | Motif |
|---|---|
| `crypto` | a packet crosses a tiny lattice and drops into an envelope; the flap closes |
| `ai` | two document panes and three source cards arrive; a data node pulses once |
| `web` | three storefront panes stack; two project tiles drop into a cart |
| `hardware` | the display wakes; CPU pins pulse twice; two RAM sticks drop into their slots |

Rules every change here must keep (tests in `tests/test_motion_*.py` enforce them): only `transform` and `opacity` are animated; `will-change` appears only on the `.is-animating` class the script sets while the cover transitions; hover effects live only under `(hover: hover) and (pointer: fine)`; no gradients or shadows inside the motion layers (the palette's background and the card hover glow live in the Background block of `main.css`, outside them), no external assets or inline styles and scripts; content is visible by default; and **pressing never changes the pressed element's own box** (a scale shrinks the hit area, so a press near an edge ends outside the element and the click is lost; tiles dim their text block and buttons dim themselves instead). Navigation is never delayed or cancelled.

## Palette and tokens

One theme, dark first (`color-scheme: dark`), every colour written once in `app/static/css/tokens.css`, which is the first stylesheet on every page. Nothing else may contain a hex literal or a literal `rgb()`: stylesheets, templates, scripts and Python all refer to tokens by name, and `tests/test_palette.py` fails on a violation. Where a colour has to reach something that cannot read a stylesheet, the value is read from the tokens at run time: the WebGL shader reads `--amber`, `--harley`, `--white`, `--sunset`, `--violet` and `--night` with `getComputedStyle`; the Razorpay checkout theme reads `--violet`; the tab icon is built in `app/context.py` from the values in `tokens.css`; the cover drawings carry classes (`cv-ln`, `cv-hl` ...) that `main.css` paints.

| Token | Value | Use |
|---|---|---|
| `--amber` | #FFAB00 | primary action, key numbers, the focus ring; text on it is `--ink` |
| `--harley` | #DD2E18 | critical fills (errors, failed pills, the failed mark); text on it is `--white` |
| `--white` | #FFFFFF | body text on dark |
| `--sunset` | #FF5841 | links, hover accents, section labels, secondary button outline; text on it is `--ink` |
| `--violet` | #C53678 | status pills, chips, bars, big shapes, the headline card; text on it is `--white` |
| `--night` | #14070F | page background |
| `--panel`, `--panel-2` | #1F0C18, #2A1221 | cards, raised and hover surfaces |
| `--line` | #4A2438 | hairlines (decoration only, never the sole edge of a control) |
| `--muted` | #D9C3CE | secondary text, control borders |
| `--ink` | #1A0B14 | text on amber and sunset |
| `--*-rgb` | the same colours as `20 7 15` style triples | translucent surfaces: `rgb(var(--night-rgb) / .9)` (space separated; a comma list is invalid there) |

**Contrast** is measured, not assumed: `scripts/check_contrast.py` computes WCAG ratios from `tokens.css` and checks the required pairs (white on harley 4.69, white on violet 5.03, ink on sunset 6.10, ink on amber 10.05, amber on night 10.38, sunset on night 6.30, and every text colour on all three surfaces), then every `color` and `background` that appear together in one rule of the stylesheets, and a rule that sets only a text colour on all three surfaces. White on sunset (3.12) and white on amber (1.90) fail for small text, which is why the text on them is `--ink`. Violet on night (3.91) and harley on night (4.20) are for graphics and large text only: the script fails if either is ever a `color`. The tests run the same functions.

**Old tokens to new** (v1.1.0 ink-blue and yellow to v1.2.0):

| Old | Was used for | Now |
|---|---|---|
| `--paper` | page background | `--night` |
| `--paper-2` | cards, inputs, summary boxes | `--panel` (`--panel-2` on hover) |
| `--panel` | cover backdrop, admin row hover | `--panel-2` |
| `--ink` | text | `--white` |
| | strong borders | `--line` for decoration, `--muted` for inputs, steppers, tabs |
| | dark fills (buttons, badges, bars) | `--amber` with `--ink` text; bars `--violet` |
| `--ink-2` | secondary text | `--muted` |
| `--rule` | hairlines | `--line` |
| `--mark` | highlighter, hover fill, banners | `--amber` (action, key numbers, banners), `--sunset` (hover), `--violet` (big shapes, the big error code) |
| `--green` | success | `--amber` (ring, ticks, borders), `--violet` (paid pill, tick disc) |
| `--red` | errors | `--harley` fill with white text; `--sunset` for text on dark |
| `#fff` literals | text on fills, the tick stroke | `--white` |

The design rule "no gradients, shadows or photos" of v1.0.0 and v1.1.0 is overridden for this release (decided by the owner): the warm glossy background and a soft glow on card hover are allowed; the line-art identity of the covers and icons is kept and recoloured.

## Background

A warm 3D background sits behind some pages. Four parts, from the bottom up:

1. **The CSS gradient** on `body::before` (fixed, `z-index: -2`): three radial gradients in violet, sunset and amber over `--night`. It is always there, it is the fallback for everything below, and it drifts slowly (a `transform`-only animation) only on pages that carry the canvas and only until the canvas is running. Admin has no gradient (`body[data-bg="none"]`).
2. **The canvas** (`<canvas class="bg3d" data-bg3d aria-hidden="true">`, fixed, `z-index: -1`, `pointer-events: none`) drawn by `app/static/js/fx-bg.js`: domain-warped noise lit like a glossy iridescent solid, ported from the owner's approved prototype with the colours read from the tokens. No library; the shader is a string in the module, so the Content-Security-Policy is unchanged.
3. **The scrim** (`.bg-scrim`): a left-to-right dark gradient over the canvas (an even 82% at 900 px and under, where the text runs the full width) so a headline over it stays above 4.5:1.
4. **Veils and cards**: text that is not on a card sits on the page colour at 92% (home sections) or on a panel card at 90% or more (sign in, register, the paid order page, every tile and plate). Cards are never more transparent than that.

**Where.** `<body data-bg>` is set by `{% block bg %}`: `gl` (canvas) on home, sign in, register and a *paid* order page; `css` (gradient only) everywhere else, including catalogue, product, cart, checkout, pay, orders and errors; `none` on admin.

**The loop rule.** The background has no animation loop of its own. `fx-bg.js` exposes `window.fxBg.tick(now)`; the single `requestAnimationFrame` loop in `fx-scroll.js` calls it on every frame and keeps the loop alive while it answers true. There is still exactly one observer and one loop on every page (`tests/test_palette.py` counts them). `fx-bg.js` starts after the page has loaded and the browser is idle, compiles the shader in parallel where the browser supports it, and then dispatches `fxbg-ready` so the loop wakes up; the frame-rate probe that can set `fx-lite` waits for that, so the one-off cost of creating a WebGL context is not mistaken for a slow device.

**Quality.** Render scale is `min(devicePixelRatio, 1.5) * 0.5` on desktop and `0.35` on phones, dropped once (x0.6) if the first 40 frames average slower than 24 fps. The loop stops while the tab is hidden, so nothing is drawn. With `prefers-reduced-motion`, `html.fx-lite` or the `bg3d` switch the module draws one still frame and never animates. If WebGL is missing, the context is lost, or the shader fails to compile or link, the canvas stays hidden and the gradient shows. Knobs: `--bg-speed` and `--bg-brightness` (`fx-tuning.css`); switch: `{"off": ["bg3d"]}` in `app/fx.json`.

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
| `hscroll` | A sideways shelf. A plain swipe row on phones, in `fx-lite` and without the script; on large screens it is pinned. Since v1.4 the track inside the pin is an endless loop (`fx-shelf.js`, below) instead of sliding with the vertical scroll. | `<section class="shelf" {{ fx('hscroll') }}><div class="hs-stage fx-stage"><ul class="hs-track">` |
| `marquee` | A slow CSS-only ticker; pauses on hover, stops for reduced motion, a plain wrapped list without the script. | `<div class="marquee" {{ fx('marquee') }}>` |
| `tilt`, `magnetic` | Pointer feedback on fine pointers only: tiles lean up to 6 degrees with a flat amber disc following the pointer; a primary button leans up to 6 px toward the pointer. Written straight onto the one element under the pointer. | `<a class="tile" {{ fx('tilt') }}>`, `<a class="btn" {{ fx('magnetic') }}>` |

Other pieces that are not words: two parallax layers of line-art in the home hero (`.px-1`, `.px-2` set their speed with `--pm`), the home shelf's endless loop (`fx-shelf.js`, v1.4), and cross-document view transitions (`@view-transition { navigation: auto }` with a named cover that travels from the card you point at to the product page; ignored by browsers without support).

**Adaptive quality.** `html.fx-lite` turns off only the heaviest items: pinned sticky stages become scroll-linked (and the sideways shelf becomes a swipe row), and big parallax stops. The script sets it when `navigator.hardwareConcurrency <= 4`, `navigator.deviceMemory <= 4`, or the first 500 ms of frames average under 45 fps. `?fx=lite` or `?fx=full` in the address forces it either way. Everyone else gets every effect; the budget is measured at normal speed (p95 at most 16.7 ms), and the 4x CPU throttle is only a stress diagnostic.

**Measured limit.** At normal speed every page class holds about 7 ms per frame on desktop and phone (p95 at most 21 ms, worst 42 ms, on the home page). Under a 4x CPU throttle the home page averages about 28 ms per frame: style recalculation dominates (about 16 ms of it per frame), it is spread over the page rather than one effect, and `fx-lite` does not reduce it. That is a known limitation, not a fixed one.

**Defaults are visible.** The page as the server renders it has no hidden state, no taller sections and no sticky stages. Every hiding rule in `motion3.css` starts with `html.fx-on`, a class the script adds only after it has checked that reduced motion is off and `IntersectionObserver` exists. Anything already on screen at that moment gets `.is-in` first, so nothing flashes. With no script, a blocked script, reduced motion or no observer, the page is simply finished. A focused element is never left hidden: `focusin` brings in its `data-fx` ancestors, and shows a pinned scene whole.

**Page classes.** `base.html` puts `data-page` on `<body>` from `{% block page_class %}`:

| Class | Pages | Treatment |
|---|---|---|
| `browse` (the default) | home, catalogue, product | Full: rise, cascade, count, pins, a product scene using that product's own generated cover, a scroll-progress hairline, a footer rise. |
| `transactional` | cart, checkout, pay, sign in, register | Scroll words on headings and read-only summaries only (a test fails if any element that starts hidden contains a form control, button or link, the footer aside). Fields, labels, buttons and error messages are never hidden. The interface layer below gives them motion that hides nothing. |
| `account` | orders, order detail | Table rows cascade. The payment-result sequence (`fx-pay.js`) is separate and unchanged. |
| `admin` | admin dashboard, orders, products | One-shot words only (figures count up, rows fade in, the heading flips in) plus the interface layer; no scenes, pointer effects or hairline. A test checks the templates and the rendered pages. |
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

**Switches.** One list turns any effect off: `OFF` at the top of `fx-scroll.js`. Names: the `data-fx` words above (`rise from-left from-right zoom flip clip lines words count cascade pin hscroll parallax draw tilt magnetic marquee`) and `stepper inputs shake toasts cart downloads forms drift bob timeline focus-ring press wipe lift`, plus the two modules `shelf-loop` (`fx-shelf.js`) and `bg3d` (`fx-bg.js`). Each becomes an `fx-off-<name>` class on `<html>`; a data-fx word is also treated as already in place. View transitions are one `@view-transition` rule in `motion3.css`; delete it to switch them off.

**Image fade-in.** The covers are generated inline SVG and arrive with the page, so there is no raster image load to smooth; they get the `clip` wipe instead.

**Inventory.** `docs/MOTION_INVENTORY.md` lists every effect with a literal hook; `tests/test_fx_inventory.py` fails if a listed hook disappears. Motion work is additive.

**Rules a change here must keep** (enforced in `tests/test_fx_*.py`): only `transform` and `opacity` change with scroll (plus `clip-path`, and `stroke-dashoffset` on drawn lines, which are paint-only; the focus ring animates `outline-offset`); no hiding without `html.fx-on`; no `:hover` dependence outside the fine-pointer query; nothing but one-shot words in admin and nothing at all on error pages; no control is ever hidden at first paint; at most one observer and one queued frame in `fx-scroll.js`; `fx-ui.js` has neither; no routes, services, models or headers involved.

**Removed in v1.4.** The section rail (a column of nine squares on the right edge of the home page) and the crosshair-and-dashed-line art (the third hero layer, and the third drifting shape on sign in and register) were taken out at the owner's request. `docs/MOTION_INVENTORY.md` records the deleted rows and a test keeps both from coming back.

### The home shelf loop (v1.4)

`static/js/fx-shelf.js` turns the shelf ("The whole shelf, side by side") into an endless row. It drifts at `--shelf-speed` px per second; scrolling the page, a sideways wheel or trackpad swipe over the shelf and a drag (finger, pen or mouse) push it, with `--shelf-wheel-gain` setting how hard, and the push eases back (time constant 0.6 s) into the drift, which then runs in the direction of the last push. Scrolling down sends the cards right to left, scrolling up left to right; dragging follows the finger.

* **Seamless.** One set of copies goes before the real cards and enough sets after them to cover the screen; the position wraps by one set's width. The copies are `aria-hidden="true"` and `inert`, and their links get `tabindex="-1"`, so a screen reader and the Tab key meet each project once. The server never sends copies.
* **Stopping it (WCAG 2.2.2).** A Pause / Play button (in the DOM and the tab order once the loop runs, clipped to nothing until it has `:focus-visible`, then shown over the top right of the head without moving anything), mouse hover over the row, and keyboard focus inside the row (not on the button) stop the drift; the drift starts on its own at load. A focused card is moved fully into view at the page gutter and the wrap is held until focus leaves.
* **When it does not run.** Without the script, with fewer than two cards, or with `shelf-loop` in `app/fx.json`, the shelf is the plain sideways-scrolling row it always was. With reduced motion fx-scroll.js still never sets `fx-on` and runs nothing but a frame loop for the shelf; fx-shelf.js adds `fx-shelf-rm` to `<html>` (the loop styles accept `fx-on` or `fx-shelf-rm`), builds the loop, starts it paused with the button on "Play", and ignores the page scroll. A drag or sideways wheel still moves it, and Play starts the drift. If reduced motion is switched on while the page is open, it pauses.
* **One loop.** The module has no `requestAnimationFrame` and no observer. `fx-scroll.js` calls `window.fxShelf.tick(now, scrollY)` every frame and keeps going while it answers true; the module asks for frames with an `fxshelf-wake` event. It writes one custom property, `--sx`, on the track; the pinned height is computed for one set of cards (`track.__span`), so the page is no longer than before.

### Script notes

The long comments that used to open each script live here, so the scripts stay inside their size budget (all `fx-*.js` together under 14 KB gzipped, `tests/test_fx_system.py`).

* **fx-scroll.js.** One script, one `IntersectionObserver`, one `requestAnimationFrame` loop for every page. For the one-shot words (rise, from-left, from-right, zoom, flip, clip, cascade, words, lines, count) it only adds `.is-in`; for scenes (pin, hscroll, parallax, draw) it writes custom properties (`--p`, `--py`, `--d`); tilt and magnetic are pointer feedback on fine pointers only. The stylesheet does the moving with transform, opacity, clip-path and stroke-dashoffset. It starts only if reduced motion is off and the observer exists, and only then puts `fx-on` on `<html>`; whatever is already on screen is revealed in the same step. A focused element is never left hidden. Listeners are passive, the loop stops while the tab is hidden or there is nothing to do, everything is undone on `pagehide`. Error pages do not run it; admin pages run only the one-shot words. Adaptive quality (`fx-lite`): a device with 4 cores or fewer, 4 GB or less, or under 45 fps for half a second (measured 300 ms after load, or after the 3D background has started) loses the pinned stages, the pinned shelf and big parallax; `?fx=lite` / `?fx=full` forces either way. The 3D background and the shelf loop ride this loop through `window.fxBg.tick(now)` and `window.fxShelf.tick(now, y)`.
* **fx-bg.js.** Domain-warped noise lit like a glossy, iridescent solid, in the palette read from `tokens.css`. One module for every page that carries it (home, sign in, register, the paid order page); no loop of its own. Render scale `min(devicePixelRatio, 1.5) * 0.5` on desktop and `0.35` on phones, one drop of the scale if the first 40 frames average slower than 24 fps, nothing drawn while the tab is hidden. With reduced motion, `fx-lite` or the `bg3d` switch it draws one still frame. If WebGL or the shader fails, the canvas stays hidden and the CSS gradient underneath shows. The shader compiles without blocking (`KHR_parallel_shader_compile`, polled with a timer), and the module starts only after load, when the browser is idle.
* **fx-cart.js.** Add to cart on the product page and a pulse on the header count. It follows what the page already does: the form's submit event starts the animation, and the DOM updates `app.js` makes say how the request ended. Without it the button works as before.
* **fx-ui.js.** Motion for controls and the pages people pay and sign in on. It never hides anything; it adds states (a spinner on a posting button, a toast that leaves, a cart row that slides away, a figure that ticks, a download that says it is preparing). No viewport observer and no frame loop. Under reduced motion only the form guard runs, with a still ring.
* **fx-pay.js.** The payment success sequence is plain CSS and plays as the page paints; this file switches it off when the same order already played it in this browser session (sessionStorage key `ps-paid-<order>`). With storage blocked it just plays again.
* **contact-map.js (v1.4).** Creates the Google Maps iframe only when "Load map" is pressed, and only for a `https://maps.google.com/` source; see "Contact form" below.

## Tuning the motion

Every number someone is likely to want to change is a CSS custom property in `static/css/fx-tuning.css`, loaded before `motion3.css`: overall speed, travel distance, stagger, easing, tilt and magnet strength, parallax strength, how far the showcase covers start from the side, loader length, the Add to cart and payment-mark lengths, the marquee speed, and the shelf loop's drift speed and push strength. Change a value and reload; nothing else needs editing. `fx-cart.js`, `fx-pay.js` and `motion.js` read the same properties, so the scripted effects follow.

Any single effect can be switched off by listing its name in `app/fx.json` (`{"off": ["tilt"]}`). The context processor writes the list to `<html data-fx-off="...">` before first paint, so CSS-only effects switch off with no script, and `fx-scroll.js` and `fx-ui.js` skip the effects they own. `docs/MOTION_TUNING.md` lists every knob and every switch name with a good range; `docs/MOTION_INVENTORY.md` lists every effect with the switch that turns it off, and a test fails if a listed effect disappears from its file.

## Contact form (v1.3)

`GET /contact` and the "Get in touch" block on the home page render the same component (`_contact.html`): a form on the left and a violet panel on the right with the name, phone, email, city and Connect buttons. Every detail comes from `CONTACT_NAME`, `CONTACT_EMAIL`, `CONTACT_PHONE`, `CONTACT_CITY`, `CONTACT_GITHUB` and `CONTACT_LINKEDIN` (`contact_info` in `app/context.py`); an empty one is not shown, and the repository holds no phone number or email (tests scan for them). The phone is shown as typed; its `tel:` and `wa.me` links are built from its digits at render time.

**Map (v1.4).** Below the details the panel shows a poster: the region label ("Bengaluru, Karnataka", the first two parts of `SELLER_ADDRESS` when it starts with the city), a note that the map comes from Google, a "Load map" button (hidden until `contact-map.js` runs) and an "Open in Google Maps" link that works without scripts. Pressing the button creates `<iframe class="map-frame" src="https://maps.google.com/maps?q=<city>&t=h&z=12&output=embed">` (hybrid view, city level, no API key) with a title, `loading="lazy"`, `referrerpolicy="strict-origin-when-cross-origin"` and `sandbox="allow-scripts allow-same-origin allow-popups"`, and moves focus to it. The script refuses any source that is not `https://maps.google.com/`. The map is centred on `CONTACT_CITY` only, never on a street address. CSP `frame-src` lists `https://maps.google.com` (the embed) and `https://www.google.com` (where it redirects); nothing else was relaxed.

`POST /contact` (`app/blueprints/contact.py`) is CSRF-protected and parsed by `validation.contact_form`: required fields, length caps that match the columns, no line breaks in one-line fields (no header injection), a valid email, and a consent box. A hidden `website` field is a honeypot: a bot that fills it is thanked and nothing is stored. Limits: 10 an hour per address and 3 an hour per sender email (keyed by a hash). A good message is stored in `contact_messages`, the owner is emailed if SMTP is set, and the visitor sees "Thanks, we will reply soon". Admin → Messages lists them newest first with "mark handled". Logs never carry the name, email or message.

## Policies and compliance (v1.4)

`app/blueprints/pages.py` serves About, FAQ and the six policies (`/privacy`, `/terms`, `/refunds`, `/delivery`, `/cookies`, `/accessibility`) from `templates/pages/`, plus `robots.txt`, `sitemap.xml`, `/.well-known/security.txt` (RFC 9116, Expires always a year ahead), `/favicon.svg` (painted from `tokens.css`) and `/manifest.webmanifest`. Every page gets a canonical URL (`PUBLIC_BASE_URL` + path; the catalogue keeps `?category=`) and Open Graph tags from its title and description. The footer links every page; its seller line names the seller, the address and the grievance officer (`seller_info` in `app/context.py`, from `SELLER_*` and `CONTACT_*`). The 404 and 500 pages are their own templates with no scripts.

**Data the store keeps.** The policies were written from this audit of the code (v1.4):

| Data | Table or place | Kept until |
|---|---|---|
| Account: name, email, scrypt hash, role, session token | `users` | erasure (`flask anonymise-account`) |
| Orders: name, phone (old orders), items, amounts, status, gateway ids, chosen contact and its consent time, terms agreement time | `orders`, `order_items` | sales record; name and contact removable (`flask anonymise-order`) |
| Cart | `cart_items` | checkout or removal |
| Order messages: recipient, text, status, keyed hash of the recipient | `messages` | with the order; recipient and text removable |
| Do-not-contact list: keyed hash only | `contact_optouts` | kept |
| Contact form messages | `contact_messages` | deleted on request (no automatic deletion) |
| Failed sign-ins: email, IP, count | `login_throttle` | successful sign-in, or 10 quiet minutes |
| Rate-limit counters: `ip:<address>`, `user:<id>`, `email:<hash>` | `rate_limits` | one day |
| Access log: address, time, request, status, user agent | gunicorn stdout, Docker json-file log | rotated, 3 x 10 MB per container |
| Cookies `session` (browser session) and `remember_token` (14 days, opt-in) | browser | as stated |
| `ps-cookie-note` (localStorage), `ps-intro` and `ps-paid-<order>` (sessionStorage) | browser | never sent to the server |

Processors: Razorpay (when real keys are set; it also receives the name, email and phone used to prefill its checkout), the SMTP provider and Meta's WhatsApp platform (only when switched on), Google (only after "Load map"), and the server's host.

**Cookie notice.** `base.html` renders a short notice above the footer: essential cookies only, no analytics, a link to the Cookie Policy, and an OK button that `app.js` shows and that records the dismissal in `localStorage` (`motion-boot.js` hides the notice before first paint on later visits). Without scripts it stays as a plain line. A test fails if a cookie the app sets is missing from the Cookie Policy's table.

**Checkout agreement.** The checkout form has a required "I agree to the Terms of Sale, the Privacy Policy and the Refund and Cancellation Policy" box, checked on the server; the API needs `"accept_terms": true`. `create_order_from_cart(..., terms_accepted=True)` stores `orders.terms_accepted_at` (migration 0009).

## Order messages (v1.3)

At checkout the buyer chooses Email or WhatsApp, gives one address (the email is prefilled; a WhatsApp number is normalised to E.164 with +91 as the default) and must tick "Send my invoice and setup guide to this contact". The order stores the channel, the value and the consent time. A checkout that asks for messages is limited to 10 a day per address and 5 a day per account.

```
mark_paid() == "paid" ──► notify.after_payment(order)        (after the payment is committed; every error is swallowed)
                             ├─ queue_order_paid: one `messages` row per (order, kind, channel), unique together
                             └─ deliver: opted out? daily cap (3 a contact)? ──► render ──► EmailChannel | WhatsAppChannel
                                          not configured ──► status not_configured (the admin can read it and send it by hand)
                                          send error     ──► failed, retried by `flask send-messages` after 2, 4, 8, 16 minutes, 5 tries
```

* **Idempotent.** The redirect, the webhook and the API can all confirm the same payment; the unique key means one message, not three.
* **Never in the payment's way.** Delivery runs after `mark_paid` has committed, and `after_payment` catches everything, so a slow or failing mail server cannot fail or roll back a payment.
* **Channels** (`app/services/notify/channels.py`): `EmailChannel` is `smtplib` with STARTTLS; `WhatsAppChannel` posts one approved template (six variables) to the Meta Cloud API and checks that the number is `+` and 8 to 15 digits before any call. Header values have CR and LF removed. With neither configured, the outbox is the channel.
* **One message** holds a short thank-you note, the invoice, the setup guide for each project and where to download (it says honestly when a link is not ready yet). The order page always shows the invoice and the guides as well, and says exactly what happened to the message ("Sent to j***@gmail.com", "Not sent: this store has not switched on email or WhatsApp messages yet", "We could not send this, it is on your order page below").
* **Signed links.** `/i/<token>` (invoice) and `/g/<token>` (guide) carry an `itsdangerous` token with a per-purpose salt, the order id and its public id, valid for 7 days and only for a paid or refunded order; they answer `Cache-Control: no-store`, `X-Robots-Tag: noindex` and `Referrer-Policy: no-referrer`. `/orders/<id>/invoice` serves the owner and admins. The invoice has print styles.
* **Stop.** Every message ends with `/stop/<token>`; the page asks for a button press (a POST, so link scanners cannot opt people out) and stores only a keyed hash in `contact_optouts`. Nothing more is sent to that contact.
* **Privacy.** Raw contact values never reach a log line; the order page and the admin show them masked. `flask anonymise-order PS-XXXXXXX` (`services/privacy.py`) removes the name and contact from an order and its messages.

## Setup guides and catalogue copy (v1.3)

`products.setup_guide` holds a small markdown subset rendered by `services/guide.py`: headings, lists (numbered lists keep their start), code blocks and inline code. The text is escaped first and only those tags are produced, so a guide cannot inject HTML. The seeded guides (`app/guides.py`) were written from each project's own README and code; an admin edits a guide in the product form, which sets `guide_edited`.

The seeded catalogue copy was checked against the projects' code in v1.3 (the messenger uses ML-KEM-768 over TLS; the RAG assistant is FastAPI, PostgreSQL with pgvector and Next.js). `seed.seed_copy_fixes()`, run by `flask seed --if-empty` at every container start, replaces an old seeded field only while it still holds the exact old text, so anything an admin has rewritten stays.

## Security notes

* CSRF tokens on every form and on every API write (`X-CSRFToken`).
* Rate limits (`services/rate_limit.py`, table `rate_limits`, limits in `Config.RATE_LIMITS`): registration 10 an hour per address, starting a checkout 10 per 10 minutes per user, confirming a payment 20 per 10 minutes per user, and 20 failed sign-ins per 10 minutes per address across all emails. Past a limit the answer is HTTP 429 with `Retry-After` (JSON under `/api`). Like the sign-in limit it lives in the database, so the 3 gunicorn workers share it, and it takes a row lock so two requests cannot both slip under it.
* Sign-in limit: 5 failures for one email and IP block that pair for 10 minutes (HTTP 429). The state is a database table, not process memory, because gunicorn runs 3 workers and an in-memory counter would let through 5 attempts per worker. While blocked the password is not even checked, and unknown emails are counted like real ones so the block does not reveal which accounts exist.
* **Client address (v1.4).** By default the address is the TCP peer and `X-Forwarded-For` is ignored, because clients can forge it. `TRUSTED_PROXIES=n` wraps the app in Werkzeug's `ProxyFix(x_for=n, x_proto=n)`, which believes only the last `n` hops (the ones the owner's proxies appended). Set it to exactly the number of reverse proxies in front of the app.
* **More limits (v1.4):** the signed `/i/`, `/g/` and `/stop/` links, 60 per 10 minutes per address; every API write, 120 per 10 minutes per account or address (`limit_writes` in `api.py`). A `RATE_LIMITS` setting that leaves a scope out keeps that scope's default.
* **Startup refusals (v1.4).** Outside tests and debug runs, `config_problems()` (`app/__init__.py`) refuses a weak `SECRET_KEY`, a MySQL URL with an empty or placeholder password, only one of the two Razorpay keys, a placeholder Razorpay secret, and a key id that is not `rzp_test_`/`rzp_live_`. It names the setting and never prints the value.
* **CORS.** No response carries `Access-Control-*` headers and no endpoint needs them. If one ever does, give it an explicit origin allowlist; never `*` together with credentials (`tests/security/test_a18_cors.py`).
* **Sessions.** The session and remember-me cookies hold `<user id>:<session token>`. The token is a per-user random value in `users.session_token`; signing out and changing a password replace it, so every cookie issued before that moment stops working, even a copy someone kept. The cost: signing out on one device signs the account out everywhere. Both cookies expire after 14 days, are `HttpOnly` and `SameSite=Lax`, and are `Secure` when `COOKIE_SECURE=true`. Signing in (or registering) clears the old session first, which also replaces the CSRF secret.
* **Passwords** are scrypt at the OWASP minimum (`PASSWORD_HASH_METHOD`, N=2**17, r=8, p=1: 128 MiB and about 0.4 s a hash). Hashes made with a lower cost are upgraded at the user's next sign-in. An unknown email is checked against a dummy hash of the same cost, so the response time does not reveal which emails have accounts. Each concurrent sign-in holds 128 MiB, which is why the sign-in throttle and the 128-character password cap matter.
* **Open finding (owner's decision):** registering an email that already has an account says so ("An account with this email already exists"), which reveals that the address is registered. The fix is email verification at sign-up, which needs SMTP switched on; mitigated meanwhile by the registration limit (10 an hour per address).
* Post-login redirects accept same-site relative paths only; control characters in the `next` value make it fall back to the home page.
* Input is parsed in `app/validation.py`: every number has explicit bounds (quantity, product id, price, stock, page), prices go from rupees to integer paise through `Decimal` (never a float), every text field has a length cap that matches its column, and passwords are limited to 8-128 characters so a huge value is never fed to scrypt. A bad value is a 400 or 422, never a 500. JSON bodies must be objects (`json_body()`).
* Request bodies over 1 MB get HTTP 413 before any route reads them. Anything under `/api/` answers errors as `{"error": ...}` JSON, including 404, 405, 413, CSRF failures and 500.
* The payment routes under `/checkout` serve only the order's owner. An admin reads and cancels customer orders from `/admin`, never pays for them.
* Users can read only their own orders; admin routes return 403 to everyone else.
* On every response: Content-Security-Policy (with `frame-ancestors 'self'`, `form-action 'self'`, `base-uri 'self'`), `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` (camera, microphone, geolocation and USB off; `payment` only for this site and Razorpay) and `Cross-Origin-Opener-Policy: same-origin-allow-popups` (not `same-origin`, which would sever the windows Razorpay opens). `Strict-Transport-Security` (one year, no `includeSubDomains`) is sent only when `COOKIE_SECURE=true`, i.e. when the site is served over HTTPS. Pages for a signed-in visitor carry `Cache-Control: no-store`. No inline scripts and **no inline styles**: `style-src` is `'self'` only, so templates carry no `style=` attribute (the old ones are classes in `main.css`) and the dashboard's bar heights are the `height` attribute of an empty `<svg>`, which CSP does not treat as a style. Keep it that way: a test fails if a `style=` or `<style>` appears in a template.
* **Razorpay and `style-src`:** Razorpay's `checkout.js` is third-party script running in our page. If it injects a `<style>` element into the page, `style-src 'self'` blocks it and the payment window can look broken. This has not been tried against a live Razorpay account. If the window is unstyled, check the browser console for "Refused to apply inline style", and the narrowest fix is to allow only style *elements*, keeping attributes blocked: add `style-src-elem 'self' 'unsafe-inline'` next to `style-src 'self'` in `security_headers()` (`app/__init__.py`).
* Cover art is built from the product title in `covers.py`, which escapes it with `markupsafe.escape`; `Markup` is applied once, in `app/__init__.py`, to the finished drawing (and carries the bandit `# nosec` with that reason). A test fails if `|safe`, `Markup(` or `render_template_string` appears anywhere else.
* Docker: MySQL's passwords have no defaults (`${DB_PASSWORD:?}`), the database port is not published, and the MySQL health check carries no password. **Database accounts (v1.4):** `store` owns the schema and is used only by the one-shot `migrate` service (migrations and the seed, `RUN_MIGRATIONS=1`); the web app and the sweeper connect as `store_app`, which `docker/mysql-init/10-app-user.sh` creates on a new volume with `SELECT, INSERT, UPDATE, DELETE` on `project_store` only (no DROP, ALTER, GRANT, FILE or SUPER); `docker-entrypoint.sh` skips migrations when `RUN_MIGRATIONS=0`. On an existing volume the account is created by hand (`docs/RELEASE_STEPS_v1.4.md`). `.dockerignore` keeps `.env*`, bytecode, `.venv`, `.vscode`, `*.db`, source maps, local tooling, the compose file and the init folder out of the image, and the base image is pinned by digest.
* Fonts are self-hosted, so the page makes no third-party requests apart from Razorpay on the payment page and Google Maps after a visitor presses "Load map". Every response also carries `Cross-Origin-Resource-Policy: same-origin` (v1.4), and the CSP has `object-src 'none'`.
* Secret scanning (v1.4): a CI job runs gitleaks over every commit on every branch; `scripts/hooks/pre-commit` runs it on what is staged. `docs/SECURITY_AUDIT.md` has the full re-check.
* Contact form and order messages: see their sections above (CSRF, honeypot, per-address and per-email limits, consent, CR/LF stripped from headers, the number checked before any WhatsApp call, signed and expiring links, a stop link, no raw contact in logs).
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
| Contact and order-message tests (v1.3) | Contact form: success, CSRF, validation, honeypot, both rate limits, XSS and header injection, admin access. Order messages: consent, E.164 numbers, one message per order and channel, sent only after payment and outside its transaction, retries and back-off, the daily cap, the stop link, signed links (tampered, expired, wrong purpose, unpaid order), anonymising, practice mode end to end; email and WhatsApp against local fake servers (`tests/fakes.py`), never a real service |
| Rate limit, session, validation and one-unpaid-order tests | Window and 429 behaviour, per-user and per-address keys, cookies dying on sign-out, bounds on every input, the second checkout redirected to the unpaid order |
| Motion, layout and phone tests | The stylesheet rules that keep motion safe (only `transform` and `opacity`, hover only for fine pointers, nothing hidden by default), the markup hooks, the scripts run under Node, and no horizontal overflow at phone widths |

The concurrency tests need real row locks, so they skip on SQLite and run in CI against a MySQL service. Removing the `FOR UPDATE` makes them fail, which is how we know they test the right thing.

## Known limits and next steps

* Migrations run when the web container starts. Two web containers starting at once would race; run `flask db upgrade` as a separate step if you scale out.
* Order messages are built and tested, but **real delivery has not been verified**: email was tested against a local fake SMTP server and WhatsApp against a local fake of the Meta Cloud API. Until the owner sets the SMTP or WhatsApp variables, messages wait in the outbox as "Not configured" and the order page says so (see `docs/NOTIFICATIONS.md`).
* Replies to a WhatsApp message are not read, so "reply STOP" does nothing; the stop link is the way out.
* Refunds are tracked, not issued: an admin refunds in the Razorpay dashboard and then marks the order refunded.
* The sign-in limit is per email and IP, plus a per-address cap across emails. Behind a reverse proxy all visitors share the proxy's address until `ProxyFix` is configured for it.
* No password reset (email is used only for order messages and the owner's contact notice so far), and registering an existing email reveals that it is registered (see "Accepted risk" above).
* The Razorpay client code and webhook are tested against a mocked API only; they have not run against a live Razorpay account.
* Cart is for signed-in users only.
