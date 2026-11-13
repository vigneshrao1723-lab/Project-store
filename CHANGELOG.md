# Changelog

Dates are commit dates. The newest release is first.

## Unreleased (branch `motion-3`)

Motion, additive only (`docs/MOTION_INVENTORY.md` lists every effect; a test fails if one disappears).

* **Add to cart** rolls the label out, carries an item off in the cart and draws a tick; the header count pulses. **Payment result** draws a tick or a cross from a growing disc. Both play from plain CSS or the page's own DOM changes; no route, service or model changed.
* **Scroll system** (`fx-scroll.js`, one observer, one loop): a `data-fx` vocabulary written through macros: rise, cascade, count, pin, parallax, plus lines, words, from-left, from-right, zoom, flip, clip, draw, hscroll, marquee, tilt and magnetic. Hidden states exist only after the script sets `html.fx-on`. Page classes: browse, transactional, account, admin, none.
* **Home**: headline line by line, copy word by word, three parallax layers, a stack marquee, story cards and counters, a pinned cover showcase whose headline crossfades through three lines with a Scroll cue, a sideways shelf, a drawn "How buying works" timeline, a section rail. **Catalogue and product**: alternating card entrances, clip-path cover wipes, tile tilt with a pointer spotlight, a pinned product scene (large screens only), cross-document view transitions with a shared cover.
* **Checkout and account**: a stepper that draws into the current step, field underline, shake and tick, a spinner and double-submit guard on posting buttons, toasts with a draining timer, cart rows that slide away, ticking totals, a bobbing empty cart, an order status timeline, a download "preparing" state, drifting art behind sign in and register. **Admin**: figures count up and rows fade in.
* **Everywhere**: a scroll-progress hairline, a condensed header, a footer rise, an animated focus ring, press feedback, underline wipes, hover lift.
* **Adaptive quality**: `html.fx-lite` (few cores, little memory, or under 45 fps for half a second; `?fx=lite` and `?fx=full` force it) turns the pinned stages scroll-linked, the shelf into a swipe row and stops big parallax. Every other effect stays.
* The home page's test count and coverage now come from `app/facts.json`; tests keep it, the README and the collected test count equal, and `scripts/update_facts.py` re-measures.

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
