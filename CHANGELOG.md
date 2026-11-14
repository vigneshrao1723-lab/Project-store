# Changelog

Dates are commit dates. The newest release is first.

## 1.3.0 (unreleased, branch `v1.3-contact`)

A contact block, and the invoice, setup guide and a thank-you note for every paid order, sent by email or WhatsApp once the owner switches either on. Every animation and hook from 1.2.0 is still there (`docs/MOTION_INVENTORY.md` and its test pass); four rows were added.

* **Home page.** "How buying works" is one horizontal four-step timeline (Choose, Reserve stock, Pay, Download) with a line that draws as you scroll, number badges on one baseline and copy that reads the reservation time from the config; on phones it turns vertical with the line down the left. The duplicated card row is gone. The footer is slim: brand, Shop links, a Contact link and the copyright line.
* **Get in touch.** A two-panel block above the footer on the home page and a new `/contact` page: a form (first and last name, email, subject, message, consent, an amber Send button) and a violet panel with phone, email and city chips, Connect buttons (WhatsApp, email, GitHub, LinkedIn, each only if configured) and a line-art pin instead of a map. Every detail comes from `CONTACT_*` in `.env`; nothing is hard-coded. `POST /contact` has CSRF, validation, length caps, a honeypot and limits of 10 an hour per address and 3 an hour per sender email; messages are stored (migration 0005), listed in the new **Admin → Messages** page with "mark handled", and emailed to the owner once SMTP is set. No contact details reach the logs.
* **Checkout.** Choose Email or WhatsApp and give one address (the email is prefilled; WhatsApp numbers become E.164 with +91 as the default), and tick "Send my invoice and setup guide to this contact" (unticked by default). The order stores the choice and the consent time (migration 0006). The separate phone field is gone.
* **Order messages.** After the payment is confirmed (never at checkout) one message per order and channel goes to an outbox (migration 0007, unique per order, kind and channel), outside the payment's transaction: a short thank-you note, the invoice, the setup guide for each project and the download information (honest when a link is not ready). Channels: `EmailChannel` (smtplib, STARTTLS), `WhatsAppChannel` (Meta Cloud API template) and the outbox by default ("Not configured"). Failed sends are retried by the sweeper (`flask send-messages`) after 2, 4, 8 and 16 minutes, 5 tries at most. Limits: 3 messages a day per contact, 10 checkouts asking for messages a day per address and 5 per account. Every message has a stop link (a do-not-contact list that stores only a hash), and `flask anonymise-order` removes the name and contact from an order.
* **The order page tells the truth** about the message ("Sent to j***@gmail.com", "Not sent: this store has not switched on email or WhatsApp messages yet", "We could not send this, it is on your order page below") and always shows the invoice and the setup guides. Signed 7-day links `/i/<token>` and `/g/<token>` (no-store, noindex) and `/orders/<id>/invoice`; the invoice prints cleanly.
* **Setup guides** (`products.setup_guide`, migration 0008, a safe markdown subset), written from each project's own README and code, editable in the admin product form and never overwritten by `flask seed` once edited.
* **Catalogue copy matches the code.** The messenger kit now says ML-KEM-768 (Kyber768) over TLS with a PySide6 client and PostgreSQL, not Kyber-1024 over raw TCP, and its benchmark is described as what it measures (key generation, exchange and recovery, and sizes). The RAG kit now describes its real stack (FastAPI, PostgreSQL with pgvector, Redis, Next.js; hybrid retrieval with citations, voice, local models) instead of LangChain, FAISS, Flask and Streamlit. Existing databases are corrected at start-up only where the old seeded text was never edited.
* **Accessibility fixes found on the way.** `/contact` has its h1, the cart's item titles no longer skip a heading level (true since 1.0), the outbox table's action column has a name, and the checkout's two-line legend no longer straddles its panel border on phones.
* `scripts/update_facts.py` now counts the facts tests that fail only because the file is stale, and refuses to write if anything else fails.
* **Measured.** 1,075 tests pass on SQLite (3 skip without MySQL), coverage 96% (2,346 statements, 86 missed); on MySQL 8.4 the migration, concurrency, contact, order-message, seed-copy and rate-limit tests pass (104) and migrations 0005 to 0008 go up and down one by one. axe finds no violation on 26 pages (including every new page and the error states) with motion on and with reduced motion. Keyboard only, the contact form and checkout with each channel complete. Frame time at normal speed, 1280 px: the home page p95 14.0 ms (the same as 1.2.0 measured alongside), the new timeline and contact band 14.0 ms, /contact 7.3 ms; one observer and one loop. bandit and pip-audit are clean, the lock files regenerate unchanged, and the Docker image builds and passes its smoke test.
* **Not verified.** Real email and WhatsApp delivery: both were tested only against local fakes (`tests/fakes.py`); see `docs/NOTIFICATIONS.md` for switching them on and checking.

## 1.2.0 (2026-11-14)

A new palette and a 3D background. Every animation from 1.1.0 is still there (`docs/MOTION_INVENTORY.md`, and its test, pass); they are recoloured, not removed.

* **Palette.** Dark first, one theme: amber `#FFAB00` (action, key numbers), harley `#DD2E18` (critical fills), white (text), sunset `#FF5841` (links, accents, the focus ring), violet `#C53678` (pills, chips, bars, big shapes), on a near-black plum with panel, line, muted and ink neutrals. Every colour is written once, in `app/static/css/tokens.css`, loaded first; a test fails on a hex literal anywhere else. The old ink-blue and yellow tokens are gone, mapped one by one in `docs/ARCHITECTURE.md`.
* **Contrast is enforced.** `scripts/check_contrast.py` and `tests/test_palette.py` compute WCAG ratios from the tokens for every text and background pair in use (4.5:1, 3:1 for graphics) and fail on a violation. Text on amber and sunset is `--ink`; white is only on harley, violet and the dark neutrals; violet and harley are never a text colour.
* **3D background.** `app/static/js/fx-bg.js`: a WebGL shader (domain-warped noise lit like a glossy solid) behind the home page, sign in, register and the paid order page, with the CSS gradient always underneath and a dark left-to-right scrim over it. Catalogue, product, cart, checkout, pay, orders and errors have the static gradient only; admin has neither. It has no loop of its own: the one loop in `fx-scroll.js` drives it. One still frame with reduced motion, `fx-lite` or `{"off": ["bg3d"]}`; the gradient shows if WebGL or the shader fails. Knobs `--bg-speed` and `--bg-brightness`; switch `bg3d`.
* **Recoloured everywhere.** Header, footer, buttons (amber primary, sunset outline secondary), links, a 3 px amber focus ring, inputs and their error and success states, status pills, chips, stepper, toasts, cart badge, tables and admin (amber figures); the generated covers and all line art; the payment mark (amber ring, violet disc, white tick; failure stays harley with a white cross). Cards over the background are the panel colour at 90% or more.
* **Fixes found on the way.** The hero art no longer makes the home page 25 px too wide at tablet width; the tab icon, the cover drawings and the Razorpay theme read the palette instead of carrying their own colours.
* **Measured.** 990 tests pass (3 skip without MySQL), coverage 97%. The contrast checker reads every colour pair in use (text 4.5:1, graphics 3:1) and finds none below its limit; a separate pixel check of the text that sits over the canvas (brightest 5% of the background behind each run of text, 320 to 1920 px) found none below 4.5:1 (3:1 for large text). axe finds no violation of any kind on 13 pages in three modes. With the canvas running, frame times at normal speed are 7 ms p50 and at most 13.7 ms p95 on a phone for all four canvas pages; on a desktop the p50 is about 13.7 ms, the register and paid-order pages meet a 16.7 ms p95 and the home and sign-in pages sit at about 21 ms, one extra vsync that comes from the animated WebGL layer itself (see `docs/DECISIONS.md`, 09:20). The 4x CPU slowdown on the home page is still not smooth.

## 1.1.0 (2026-11-14)

Motion, additive only (`docs/MOTION_INVENTORY.md` lists every effect; a test fails if one disappears).

* **Add to cart** rolls the label out, carries an item off in the cart and draws a tick; the header count pulses. **Payment result** draws a tick or a cross from a growing disc. Both play from plain CSS or the page's own DOM changes; no route, service or model changed.
* **Scroll system** (`fx-scroll.js`, one observer, one loop): a `data-fx` vocabulary written through macros: rise, cascade, count, pin, parallax, plus lines, words, from-left, from-right, zoom, flip, clip, draw, hscroll, marquee, tilt and magnetic. Hidden states exist only after the script sets `html.fx-on`. Page classes: browse, transactional, account, admin, none.
* **Home**: headline line by line, copy word by word, three parallax layers, a stack marquee, story cards and counters, a pinned cover showcase whose headline crossfades through three lines with a Scroll cue, a sideways shelf, a drawn "How buying works" timeline, a section rail. **Catalogue and product**: alternating card entrances, clip-path cover wipes, tile tilt with a pointer spotlight, a pinned product scene (large screens only), cross-document view transitions with a shared cover.
* **Checkout and account**: a stepper that draws into the current step, field underline, shake and tick, a spinner and double-submit guard on posting buttons, toasts with a draining timer, cart rows that slide away, ticking totals, a bobbing empty cart, an order status timeline, a download "preparing" state, drifting art behind sign in and register. **Admin**: figures count up and rows fade in.
* **Everywhere**: a scroll-progress hairline, a condensed header, a footer rise, an animated focus ring, press feedback, underline wipes, hover lift.
* **Adaptive quality**: `html.fx-lite` (few cores, little memory, or under 45 fps for half a second; `?fx=lite` and `?fx=full` force it) turns the pinned stages scroll-linked, the shelf into a swipe row and stops big parallax. Every other effect stays.
* The home page's test count and coverage now come from `app/facts.json`; tests keep it, the README and the collected test count equal, and `scripts/update_facts.py` re-measures.
* **Pinned showcase restored with three scenes** ("Scroll to fill the shelf", "Four fields, one platform", "Built to be checked"): four covers slide in from both sides, the headline crossfades, a counter reads 01 / 02 / 03, a Scroll cue fades. Pinned from 900 px up, scroll-linked and unpinned on phones and under `fx-lite`.
* **Home headline** arrives out of a 6 px blur (that one element, once). **Product page**: title row, then a sticky cover and buy box beside the details (CSS sticky, falls back to normal flow on short or narrow windows), cover clip-reveal, sections cascading.
* **Transactional**: the stepper appears on cart, checkout, pay and the order page (also for a pending order); the payment mark shows on the paid order page and on a declined payment, with a ring pulse behind the tick; empty cart, no orders and no search results have line-art with a small idle loop; toasts moved bottom-right so they never cover the stepper.
* **Tuning layer**: `app/static/css/fx-tuning.css` (speed, distance, stagger, easing, tilt, magnet, parallax, cover distance, loader, cart and pay lengths, marquee), `app/fx.json` to switch any single effect off, `docs/MOTION_TUNING.md`, and `docs/MOTION_INVENTORY.md` with a test that fails if an effect is lost.
* **Accessibility**: the test-mode notice is a labelled region, the catalogue lists projects under a heading, and the pay page has a level-one heading (all three were axe findings that also exist in 1.0.0). Axe finds nothing new with the motion on, and nothing at all under reduced motion beyond those.
* **Copy**: admin product visibility reads Visible / Hidden; the home "Pay at checkout" step no longer names Razorpay.
* **Measured**: 957 tests pass (3 skip without MySQL), coverage 97%. At normal speed every page holds about 7 ms a frame; under a 4x CPU throttle the home page does not (known limitation).
* No route, service, model, migration or security header changed; the migration head is still 0004. The only Python change in the app is `app/context.py`, which now also supplies the measured facts and the switched-off list to templates.

## 1.0.0 (2026-11-13)

First tagged release. Everything below is in it.

### Security hardening (2026-11-11)

* The app refuses to start with a missing, short or placeholder `SECRET_KEY`. The practice gateway is opt-in (`ALLOW_PRACTICE_GATEWAY`), so a deployment that forgets its Razorpay keys takes no payments instead of giving downloads away.
* Dependencies updated and every package pinned with hashes (`requirements.lock`, `requirements-dev.lock`). CI runs `pip-audit`, `bandit` and a lock-freshness check; Dependabot is on.
* Every input has bounds and length caps; bad input is a 400 or 422, never a 500. Payments can only be made by the order's owner.
* Sessions carry a per-user token, cookies last 14 days, and passwords use scrypt at the OWASP minimum cost, upgraded at next sign-in.
* Database-backed rate limits for registration, checkout, payment confirmation and sign-ins by address, on top of the existing per-email sign-in block.
* Security headers (CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, COOP, HSTS when `COOKIE_SECURE`), `no-store` on signed-in pages, escaped cover titles, a tighter Docker setup and ignore files.
* No inline styles anywhere, so `style-src` is `'self'` only.
* 302 tests in `tests/security`, one file per audit item.

### Fixes from manual testing (2026-11-11)

* A short last row in the product grid showed a navy block.
* Pages restored from the back/forward cache after sign-out are reloaded instead of showing a stale signed-in view.
* A user can have only one unpaid order; a second checkout goes to the open order's pay page (HTTP 409 on the API).
* Phone layout: no iOS zoom on form fields, bigger tap targets, stacked tables, no sideways scroll.
* Product titles with HTML characters are escaped everywhere, with a test using the title from manual testing.

### Motion (2026-11-12 to 2026-11-13)

* A one-time intro loader (six line-art objects, gone in about 1.3 s) and category interactions on tiles and product plates. Everything is optional: nothing hides without the script, reduced motion turns it off, and only `transform` and `opacity` animate.
* The loader was tightened after it measured 1.49 s on screen against a 1.4 s target.

### Store, checkout and operations (2026-11-10)

* Flask, SQLAlchemy and MySQL store with a searchable catalogue, per-user carts, a checkout that reserves stock in one transaction (row locks in ascending id order, append-only inventory ledger), Razorpay payments with signature checks, a webhook, an admin dashboard and a REST API at `/api/v1`.
* Alembic migrations through Flask-Migrate (`0001` to `0004`); a test fails if models and migrations disagree.
* Sign-in blocked for 10 minutes after 5 failed attempts per email and IP.
* Docker Compose (database, web, sweeper) with a configurable host port and a fixed sweeper health check; GitHub Actions for test, security, build and deploy.
* The seeded catalogue is a plain demo with blank download links, and no default admin password is seeded.
* Relicensed under MIT.

### Known limitations

See the README: no email or password reset, registering an existing email reveals it exists, the Razorpay path is tested with mocks only, and `COOKIE_SECURE` and HSTS are off unless set.
