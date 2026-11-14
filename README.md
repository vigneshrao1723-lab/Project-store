# Project Store

A store for selling finished engineering projects, built as a full-stack Flask application: sign-in, a searchable catalogue, per-user carts, a checkout that reserves stock inside one database transaction, Razorpay payments, order management, an admin dashboard and a REST API. Docker and GitHub Actions are set up, and the test suite covers the money, stock and security paths.

Built with Flask, SQLAlchemy, MySQL, Jinja and hand-written CSS. The design notes are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and the release history is in [CHANGELOG.md](CHANGELOG.md).

![Home page at 1280 px](docs/screenshots/home.png)

| Home: the story | Home: the pinned showcase |
|---|---|
| ![Home story](docs/screenshots/home-story.png) | ![Pinned showcase, scene two of three](docs/screenshots/home-showcase.png) |
| **Catalogue** | **Product** |
| ![Catalogue](docs/screenshots/catalogue.png) | ![Product page](docs/screenshots/product.png) |
| **Cart** | **Checkout** |
| ![Cart](docs/screenshots/cart.png) | ![Checkout](docs/screenshots/checkout.png) |
| **Pay (practice gateway)** | **Paid order** |
| ![Pay page](docs/screenshots/pay.png) | ![Paid order](docs/screenshots/order.png) |
| **Sign in** | **Your orders** |
| ![Sign in over the 3D background](docs/screenshots/login.png) | ![Orders](docs/screenshots/orders.png) |
| **Admin overview** | |
| ![Admin dashboard](docs/screenshots/admin-dashboard.png) | |

On a 390 px phone: sign in, home, catalogue, product, cart, pay and paid order.

| ![Home at 390 px](docs/screenshots/home-390.png) | ![Catalogue at 390 px](docs/screenshots/catalogue-390.png) | ![Product at 390 px](docs/screenshots/product-390.png) |
|---|---|---|
| ![Cart at 390 px](docs/screenshots/cart-390.png) | ![Pay at 390 px](docs/screenshots/pay-390.png) | ![Paid order at 390 px](docs/screenshots/order-390.png) |
| ![Sign in at 390 px](docs/screenshots/login-390.png) | | |

The screenshots were taken from a fresh database loaded with the demo seed and two practice purchases, so they show no real customer data. Still frames cannot show the motion; run the store locally to see it. The yellow banner is the practice-gateway notice (see [Payments](#payments)).

**This is an open-source demo store.** The source is public (MIT), so there is no paywall. The download links in the seeded catalogue are blank, so a paid order's page says "Link coming soon. Contact the store." If you run a store like this for your own work, set private links as described in [How to set up the private delivery links](#how-to-set-up-the-private-delivery-links).

## What is checked, and where

Every number below comes from a command you can run.

| Claim | How to check it |
|---|---|
| 990 tests pass on SQLite, 3 skip without MySQL (CI runs those against MySQL) | `pytest` |
| Line coverage of `app/` is 97% (1,690 statements, 57 missed), measured on that same run | `pytest --cov=app --cov-report=term-missing` |
| 302 of those tests are the security suite, one file per audit item | `pytest tests/security` |
| CI runs four jobs on every push and pull request: `test` (SQLite, then MySQL for the concurrency and migration tests), `security` (`pip-audit`, `bandit` at medium severity and above, lock files match the pins), `build` (Docker image plus a smoke test) and `deploy` (main only: pushes the image to GitHub Container Registry) | [`.github/workflows/ci.yml`](.github/workflows/ci.yml) |
| The schema is defined only by Alembic migrations, and a test fails if models and migrations disagree | `tests/test_migrations.py` |

## Motion and design

The look is a warm dark palette (amber, harley red, white, sunset, violet over a near-black plum), Archivo and Source Serif 4 self-hosted, with a glossy 3D background behind the home page, sign in, register and the paid order page and a static gradient behind everything except admin. Every colour is a token in `app/static/css/tokens.css`; `scripts/check_contrast.py` measures every text and background pair in use and a test fails if one drops below 4.5:1 (3:1 for graphics). Motion is progressive: the server renders every page complete, and the scripts add movement on top.

* **One scroll system.** `fx-scroll.js` runs one observer and one animation-frame loop. Templates ask for an effect with `data-fx` words written through two macros (rise, cascade, count, pin, parallax, lines, words, from-left, from-right, zoom, flip, clip, draw, hscroll, marquee, tilt, magnetic). The home page has a pinned showcase (covers slide in from both sides over three scenes), a sideways shelf and a drawn timeline; the other pages use the quieter words. `docs/MOTION_INVENTORY.md` lists every effect, and a test fails if one disappears. Details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#scroll-system).
* **Only cheap properties move.** Transform and opacity, plus clip-path, stroke-dashoffset and a 6 px blur on the home headline once. Hidden states exist only after the script has started, so no script, a blocked observer or `prefers-reduced-motion` all show the finished page.
* **The 3D background** (`fx-bg.js`) is a WebGL shader with no library and no loop of its own: the one scroll loop drives it. It draws one still frame (never animates) with reduced motion, under `fx-lite`, or with `{"off": ["bg3d"]}`, and if WebGL or the shader fails the CSS gradient underneath is what shows. Knobs: `--bg-speed`, `--bg-brightness`.
* **Adaptive quality (`fx-lite`).** On a machine with four or fewer cores, four GB of memory or less, or one that renders under 45 frames a second just after load, the pinned stages become scroll-linked and the shelf becomes a swipe row; every other effect stays. `?fx=lite` and `?fx=full` force it. At normal speed pages hold about 7 ms a frame on the test machine; under a 4x CPU throttle the home page does not (about 28 ms), and `fx-lite` does not fix that. See "Measured limit" in the architecture notes.
* **Tuning.** `app/static/css/fx-tuning.css` holds the speed, distance, stagger, easing, tilt, parallax, loader and payment-mark knobs; `app/fx.json` switches single effects off. [docs/MOTION_TUNING.md](docs/MOTION_TUNING.md) lists both.

## Known limitations

Read these before you rely on the store.

* **No email, and no password reset.** The app sends no mail at all. A user who forgets a password cannot recover the account by themselves. The only built-in tool that sets a password is `flask create-admin`, and it also makes that account an admin, so it is not a customer reset.
* **Registering an email that already has an account says so.** That reveals the address is registered. It is an accepted risk, because the proper fix (telling the address's owner by email instead of answering in the page) needs email.
* **The Razorpay path has been tested with mocks only.** The client code, signature checks, amount/currency/status checks and the webhook are tested against a mocked Razorpay API. This code has never run against a live Razorpay account, test or live mode. In particular, `style-src 'self'` might block styling that Razorpay's checkout script injects (see "Razorpay and style-src" in the architecture notes).
* **Add to cart needs JavaScript.** The button calls the REST API from the page script. With scripts blocked it reloads the product page and nothing is added; every page still renders in full without scripts, and checkout and payment are plain form posts.
* **The 3D background needs WebGL and a GPU that keeps up.** Without either you get the still gradient. It was run on one integrated GPU (Intel UHD) in Chromium only; no discrete GPU, no Firefox, no Safari, no phone hardware.
* **Motion is progressive and reduced-motion aware, not guaranteed everywhere.** It was checked in Chromium only (no Firefox or Safari run), at normal speed and under a 4x CPU throttle where the home page is not smooth. With `prefers-reduced-motion` nothing animates.
* **Use the practice gateway for demos.** With `ALLOW_PRACTICE_GATEWAY=true`, anyone who is signed in can mark their own order paid for nothing. It is for demos and local development, and must stay off for a store that sells for real.
* **Download links are blank in the demo seed.** Paid orders show "Link coming soon. Contact the store." until you set a link per product in the admin screen.
* **`COOKIE_SECURE` and HSTS are off unless you set them.** `COOKIE_SECURE=true` marks the session cookies Secure and turns on `Strict-Transport-Security`. Set it when the site is served over HTTPS. Over plain HTTP, leave it off, or sign-in stops working.
* **Sign-in and registration limits count the connection's IP address.** Behind a reverse proxy every visitor arrives from the proxy's address until you configure Werkzeug's `ProxyFix` for that one proxy. The app deliberately does not trust `X-Forwarded-For`.
* Refunds are tracked, not issued: an admin refunds in the Razorpay dashboard and then marks the order refunded.
* The cart is for signed-in users only. Migrations run when the web container starts, so run `flask db upgrade` as its own step if you scale to several web containers.

## Security

What the code does today, each item with a test (see [Security notes](docs/ARCHITECTURE.md#security-notes) for the reasoning):

* The amount charged is computed on the server from the order, never taken from the browser. A payment is accepted only with a valid HMAC signature, a gateway order id that belongs to that order, and (in Razorpay mode) a captured payment of the exact amount in INR.
* Money is integer paise throughout. Stock changes only through `app/services/orders.py`, under `SELECT ... FOR UPDATE` row locks in ascending id order, with an append-only inventory ledger. A user can have one unpaid order at a time.
* CSRF tokens on every form and every API write. The webhook is exempt and authenticated by its own signature.
* Sessions carry a per-user token, so signing out or changing a password invalidates every cookie issued earlier. Passwords are scrypt at N=2**17.
* Database-backed limits shared by all workers: 5 failed sign-ins per email and IP (10-minute block), plus per-address limits on registration, checkout, payment confirmation and failed sign-ins across emails.
* Content-Security-Policy with no inline scripts and no inline styles, plus `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` and `Cross-Origin-Opener-Policy`. Signed-in pages are `no-store`.
* The app refuses to start without a `SECRET_KEY` of at least 32 characters, and with no Razorpay keys and the practice gateway off it takes no payments.
* Input is validated with explicit bounds, request bodies over 1 MB get HTTP 413, and API errors are JSON, never a stack trace.
* Dependencies are pinned by hash in `requirements.lock`; CI runs `pip-audit` and `bandit`, and Dependabot proposes updates weekly.
* In Docker, the database has no default passwords, its port is not published, the app connects as a non-root database user and runs as an unprivileged container user.

## Required settings

* **`SECRET_KEY`** signs sessions and CSRF tokens. The app **refuses to start** (outside tests and debug mode) if it is missing, shorter than 32 characters, or a placeholder such as the one in `.env.example`. Generate one:

  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```

  Paste the output after `SECRET_KEY=` in `.env`. Changing it signs everyone out.
* **`DB_PASSWORD` and `DB_ROOT_PASSWORD`** (Docker): `docker compose` refuses to start without them, because MySQL's accounts are created from them. Use two different long random values (`python -c "import secrets; print(secrets.token_urlsafe(24))"`). They are applied **only when the database volume is first created**. If you already have a volume made with other values, put those same values in `.env`, or change the passwords inside MySQL and then `.env`.
* **Payments:** set both Razorpay keys, or set `ALLOW_PRACTICE_GATEWAY=true` for demos and local development. With neither, the store takes no orders (see [Payments](#payments)).

`.env` is git-ignored. Never commit it or real keys.

## Run it with Docker (MySQL)

```bash
cp .env.example .env          # then set SECRET_KEY, DB_PASSWORD and DB_ROOT_PASSWORD (see "Required settings")
docker compose up --build
```

Open http://localhost:8000. Every start applies any pending [database migrations](#database-migrations), and the first start also loads the catalogue. If port 8000 is taken, set `WEB_PORT` in `.env`. A `sweeper` container runs `flask release-expired` every minute to free stock held by unpaid orders.

## Run it locally without Docker (SQLite)

```bash
python -m venv venv
venv\Scripts\activate          # Windows;  source venv/bin/activate on macOS/Linux
pip install -r requirements-dev.txt
set FLASK_APP=wsgi.py          # Windows;  export FLASK_APP=wsgi.py on macOS/Linux
flask db upgrade               # creates the tables
flask seed
flask run
```

With no `DATABASE_URL` it uses a SQLite file in `instance/`. `flask seed` does not create tables; it stops and tells you to run `flask db upgrade` if there are none.

**Already have an `instance/store.db` from before migrations existed?** Run `flask adopt-legacy-db` once, then `flask db upgrade`. Your data is kept.

**Admin account:** `flask seed` creates one admin when there is none, with email `ADMIN_EMAIL` (default `admin@projectstore.local`). There is no built-in password. Set `ADMIN_PASSWORD` before the first seed to choose one, or leave it empty and a random password is generated and printed **once** in the seed output ("Generated admin password ..."). Under Docker the seed runs when the web container first starts, so read it with `docker compose logs web`. It is stored only as a hash and cannot be recovered; to set a new one run `flask create-admin you@example.com` (`docker compose exec web flask create-admin you@example.com` under Docker). Container logs keep the generated password, so change it before the app is reachable by anyone else.

**Upgrading from an earlier version?** The sign-in cookies carry a per-account token, so everyone is signed out once when this version first runs (`flask db upgrade` adds `users.session_token`). Password hashes made at the old, cheaper scrypt cost are upgraded the next time each user signs in. A database seeded by a very early version has an admin whose password was published in this repository; set a new one with `flask create-admin` before exposing that database.

## Dependencies

* `requirements.txt` lists the direct runtime packages, pinned exactly. `requirements-dev.txt` adds the test and security tools.
* `requirements.lock` and `requirements-dev.lock` pin **every** package, transitive ones included, with hashes. The Docker image and CI install from them with `pip install --require-hashes`, so a build gets the same bytes every time and a tampered download is refused. For local work `pip install -r requirements-dev.txt` is enough.
* **Changing a version:** edit the pin in `requirements.txt` (or `requirements-dev.txt`), then regenerate both locks under Python 3.12 and commit all three files:

  ```bash
  docker run --rm -v "$PWD:/work" -w /work python:3.12-slim sh scripts/relock.sh
  ```

  CI fails if the locks do not match the pins, so a Dependabot pull request needs this step before it can merge.
* CI runs `pip-audit` (known vulnerabilities in the locked packages) and `bandit` (medium severity and above) and fails on any finding. The one intentional `Markup` (the cover art, whose title is escaped inside `cover_svg`) carries a `# nosec` with the reason.

## Payments

* **No keys, `ALLOW_PRACTICE_GATEWAY=true`:** a practice gateway runs the same signing and confirmation code as Razorpay. An amber banner on every page and a notice on the pay page say that no real money moves. **Anyone who is signed in can mark their own order paid for free in this mode, so never switch it on for a store that sells for real.**
* **No keys, `ALLOW_PRACTICE_GATEWAY` off (the default):** the store takes no payments. The pay page says "Payment is not available", the practice route returns 404, no signature verifies and nothing can be marked paid. A deployment that forgets its Razorpay keys therefore cannot give the downloads away.
* **Razorpay test mode** (untested against the live service, see [Known limitations](#known-limitations)): set payment capture to **automatic** in the dashboard (the server marks an order paid only for a *captured* payment of the exact amount, in INR). Put your test `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in `.env`. For the webhook, add `https://<your-host>/webhooks/razorpay` in the Razorpay dashboard for `payment.captured` and set `RAZORPAY_WEBHOOK_SECRET`. Locally, expose the port with a tunnel.

## Database migrations

The schema is defined by the migrations in `migrations/` (Alembic, through Flask-Migrate), not by the models alone.

| Command | What it does |
|---|---|
| `flask db upgrade` | Bring the database up to the latest migration. Docker runs this on every start. |
| `flask db migrate -m "add X"` | Write a new migration by comparing the models with the database. |
| `flask db downgrade` | Undo the latest migration. This drops what it created, so back up first. |
| `flask db current` / `flask db history` | Show where the database is / list the migrations. |
| `flask adopt-legacy-db` | One-off for a database made before migrations existed (see above). Docker runs it automatically and it does nothing on any other database. |

**Changing a model:**

1. Edit the model in `app/models.py`.
2. Point `DATABASE_URL` at an empty MySQL database of the same version as production and run `flask db upgrade`, then `flask db migrate -m "what changed"`. Generate against MySQL, not SQLite, so the file is right for production.
3. **Read the new file in `migrations/versions/`.** Alembic cannot see renames (it writes a drop and an add, which loses the data) and its `downgrade` can be wrong.
4. Run `flask db upgrade`, then `pytest`. `tests/test_migrations.py` fails if the models and the migrations disagree, if a migration cannot be undone, or if an old database cannot be adopted.
5. Commit the model change and its migration together. Never edit a migration that has already been applied anywhere; add a new one.

**Back up before upgrading production.** MySQL cannot roll back schema changes, so a migration that fails halfway leaves the database partly changed. Run one web container at a time during an upgrade, because two starting together would both try to migrate.

## Limits

| Limit | Value | Setting |
|---|---|---|
| Failed sign-ins per email and IP before a block | 5, then blocked for 10 minutes (HTTP 429, `Retry-After`) | `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES` |
| Failed sign-ins from one address across all emails | 20 per 10 minutes | `Config.RATE_LIMITS["login_ip"]` |
| Registrations per address | 10 per hour | `Config.RATE_LIMITS["register"]` |
| Starting a checkout, per user | 10 per 10 minutes | `Config.RATE_LIMITS["checkout"]` |
| Confirming a payment, per user | 20 per 10 minutes | `Config.RATE_LIMITS["verify"]` |
| Stock hold for an unpaid order | 15 minutes | `RESERVATION_MINUTES` |
| Quantity per cart line | 5 | `Config.MAX_QTY_PER_LINE` |
| Request body | 1 MB | `Config.MAX_CONTENT_LENGTH` |

The counters live in database tables (`login_throttle`, `rate_limits`), so the limits are shared by all web workers and survive restarts. While a sign-in is blocked even the correct password is refused, and unknown emails are blocked like real ones so the block does not reveal which accounts exist. To unblock someone early: `DELETE FROM login_throttle WHERE email = 'them@example.com';`

## Tests

```bash
pytest                                   # whole suite on SQLite
pytest tests/security                    # the security suite on its own
pytest --cov=app --cov-report=term-missing

# Concurrency tests need MySQL or MariaDB row locks. The migration and sign-in limit tests also run there:
TEST_DATABASE_URL="mysql+pymysql://store:store@127.0.0.1:3306/project_store_test?charset=utf8mb4" pytest
```

Without MySQL, the 3 concurrency tests skip; CI runs them against a MySQL service. A few motion tests run the page scripts under Node and skip if Node is not installed.

## REST API

Base path `/api/v1`. It uses the signed-in session cookie, and writes need an `X-CSRFToken` header (the page's `<meta name="csrf-token">`).

| Method and path | Purpose |
|---|---|
| `GET /products?q=&category=&sort=&page=` | Search and list |
| `GET /products/<slug>` | One product |
| `GET /cart` · `POST /cart/items` · `PATCH`/`DELETE /cart/items/<product_id>` | Cart |
| `POST /checkout` | Reserve stock, create a pending order and gateway order. With an unpaid order already open it answers 409 with that order |
| `POST /checkout/verify` | Confirm a payment by signature |
| `GET /orders` · `GET /orders/<id>` | Your orders (download links only once paid) |
| `GET /admin/stats` · `GET /admin/orders` | Admin |
| `POST /admin/products` · `PUT /admin/products/<id>` · `POST /admin/products/<id>/stock` | Admin catalogue and stock |

Errors are `{"error": "...", "fields": {...}}` with a matching status code.

## Make it yours

* Seed projects live in `app/seed.py`. Edit products in the admin screen afterwards.
* **Download links:** the seeded products have no link, so a paid order's page says "Link coming soon. Contact the store." until you set one in the admin screen. Never use a public repository as a link.
* Run `flask release-expired` from cron if you don't use the Docker sweeper.

## How to set up the private delivery links

Each product has one **Download link**. When an order is paid, the order page shows that link to the person who paid, and to nobody before that (`tests/test_delivery_links.py` checks the order page, the pay page, the order and product APIs, and other users). The app sends no email and does not ask buyers for a GitHub username, so the link must either work for any buyer as it is, or you give access yourself after each sale.

**The link must never be the public repository.** A public repo can be read by anyone without paying. For each link, open it in a private or incognito window while signed out. It must not show the code.

**A. A file link (no manual step per sale).** Zip the kit. Upload the zip to Google Drive, Dropbox, OneDrive, S3 or similar. Set sharing to "anyone with the link can download", not "public on the web". Every buyer gets the same link. If it leaks, replace the file, make a new link and update the product. Orders already placed show the new link, because the page reads the product's current link.

**B. A private GitHub repository.** Keep the repository private and use its URL as the link. A signed-out visitor sees a 404, and so does a buyer until you add them (repository, Settings, Collaborators, read access). The admin order page shows each buyer's name, email and phone, so you can ask for their GitHub username. This is manual work for every sale, so use it only when orders are few.

To set a link: sign in as an admin, open Admin, Products, open the product, paste the link into **Download link** and save. Then place a test order with the practice gateway and confirm **Open download** works from the order page.

`flask seed` only adds a product whose slug is not in the database yet. Changing links in `app/seed.py` does not change a database that already has the products, so edit those in the admin screen. A database seeded before the links were blanked may still have links that point at public repositories; clear or replace them before you sell anything.

## Layout

```
app/
  blueprints/   shop, auth, cart, checkout, account, admin, api, webhooks
  services/     orders (state machine + stock), cart, catalog, payments, products, login_throttle, rate_limit
  templates/    Jinja pages, admin/ for the dashboard
  static/       css, js, self-hosted fonts
migrations/     Alembic migrations (0001 to 0004)
scripts/        relock.sh (regenerates the hashed lock files)
tests/          pytest suite; tests/security has one file per audit item
docs/           ARCHITECTURE.md, screenshots/
```

## License

MIT. See [LICENSE](LICENSE). The self-hosted fonts keep their own licences, in `app/static/fonts/LICENSE-*.txt`.
