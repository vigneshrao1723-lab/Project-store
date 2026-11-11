# Project Store

A full-stack store for selling finished engineering projects: sign-in, a searchable catalogue, per-user carts, a checkout that reserves stock inside one database transaction, Razorpay payments, order management and an admin dashboard. REST API, automated tests, Docker and CI included.

Built with Flask, SQLAlchemy, MySQL, Jinja and hand-written CSS. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.

**This is an open-source demo store.** The source is public (MIT), so there is no paywall. The download links in the seeded catalogue are blank placeholders that show where a link would go; they protect nothing. If you run a store like this for your own work, set private links as described in [How to set up the private delivery links](#how-to-set-up-the-private-delivery-links).

## Required settings

* **`SECRET_KEY`** signs sessions and CSRF tokens. The app **refuses to start** (outside tests and debug mode) if it is missing, shorter than 32 characters, or a placeholder such as the one in `.env.example`. Generate one:

  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```

  Paste the output after `SECRET_KEY=` in `.env`. Changing it signs everyone out.
* **Payments:** set both Razorpay keys, or set `ALLOW_PRACTICE_GATEWAY=true` for demos and local development. With neither, the store takes no orders (see [Payments](#payments)).

## Run it with Docker (MySQL)

```bash
cp .env.example .env          # then set SECRET_KEY (see "Required settings"); Razorpay keys are optional
docker compose up --build
```

Open http://localhost:8000. Every start applies any pending [database migrations](#database-migrations), and the first start also loads the catalogue. If port 8000 is taken, set `WEB_PORT` in `.env`.

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

With no `DATABASE_URL` it uses a SQLite file in `instance/`. `flask seed` no longer creates tables; it stops and tells you to run `flask db upgrade` if there are none.

**Already have an `instance/store.db` from before migrations existed?** Run `flask adopt-legacy-db` once, then `flask db upgrade`. Your data is kept.

**Admin account:** `flask seed` creates one admin when there is none, with email `ADMIN_EMAIL` (default `admin@projectstore.local`). There is no built-in password. Set `ADMIN_PASSWORD` before the first seed to choose one, or leave it empty and a random password is generated and printed **once** in the seed output ("Generated admin password ..."). Under Docker the seed runs when the web container first starts, so read it with `docker compose logs web`. It is stored only as a hash and cannot be recovered; to set a new one run `flask create-admin you@example.com` (`docker compose exec web flask create-admin you@example.com` under Docker). Container logs keep the generated password, so change it before the app is reachable by anyone else.

**Seeded earlier?** A database seeded by an older version has an admin whose password was published in this repository. Set a new one with `flask create-admin` before exposing that database.

## Payments

* **No keys, `ALLOW_PRACTICE_GATEWAY=true`:** a practice gateway runs the same signing and confirmation code as Razorpay. Good for demos and local development. A yellow banner on every page and a notice on the pay page say that no real money moves. **Anyone who is signed in can mark their own order paid for free in this mode, so never switch it on for a store that sells for real.**
* **No keys, `ALLOW_PRACTICE_GATEWAY` off (the default):** the store takes no payments. The pay page says "Payment is not available", the practice route returns 404, no signature verifies and nothing can be marked paid. A deployment that forgets its Razorpay keys therefore cannot give the downloads away.
* **Razorpay test mode:** put your test `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in `.env`. Use Razorpay's test card numbers from their docs. For the webhook, add `https://<your-host>/webhooks/razorpay` in the Razorpay dashboard for `payment.captured` and set `RAZORPAY_WEBHOOK_SECRET`. Locally, expose the port with a tunnel.

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
3. **Read the new file in `migrations/versions/`.** Alembic cannot see renames (it writes a drop and an add, which loses the data) and its `downgrade` can be wrong. The first migration needed its `downgrade` rewritten, because MySQL refuses to drop an index that a foreign key still uses.
4. Run `flask db upgrade`, then `pytest`. `tests/test_migrations.py` fails if the models and the migrations disagree, if a migration cannot be undone, or if an old database cannot be adopted.
5. Commit the model change and its migration together. Never edit a migration that has already been applied anywhere; add a new one.

Things to know when running it for real:

* **Back up before upgrading production.** MySQL cannot roll back schema changes, so a migration that fails halfway leaves the database partly changed.
* Run one web container at a time during an upgrade. Two starting together would both try to migrate. With several containers, run `flask db upgrade` once as its own step first.
* `migrations/versions/0001_initial_schema.py` is the schema as it was when migrations began. Databases created by the old `create_all` start-up are adopted at that revision, so it must keep describing that schema.

## Sign-in limit

After **5 failed sign-ins** for the same email from the same IP address, that pair is blocked for **10 minutes**. The page answers with status 429, a `Retry-After` header, and "Too many failed sign-in attempts. Try again in 10 minutes."

* While blocked, even the correct password is refused, and further tries do not extend the block.
* Failures that are more than 10 minutes apart do not add up. A successful sign-in resets the count.
* Emails with no account are blocked in the same way, so the block does not reveal which emails have accounts.
* The counts live in the `login_throttle` table, so the limit is shared by all web workers and survives restarts. (Flask-Limiter's built-in storage is per process; with 3 gunicorn workers a limit of 5 would really be 15.)
* Change it with `LOGIN_MAX_ATTEMPTS` and `LOGIN_LOCKOUT_MINUTES` in `.env`. To unblock someone early, delete their row: `DELETE FROM login_throttle WHERE email = 'them@example.com';`

What it does not do:

* **The IP is the address of the connection.** Behind a reverse proxy, every visitor arrives from the proxy's address, and on Docker Desktop for Windows we saw every request arrive from the Docker gateway (`172.x.0.1`). The limit then works per email only, and someone failing five times against an email locks out everyone who shares that address. The app deliberately does not trust `X-Forwarded-For`, because any client can forge it and walk around the limit. If you run behind a proxy you control, configure Werkzeug's `ProxyFix` for exactly that one proxy.
* One address trying many different emails is not slowed, and registration is not limited. Put a rate limit on `/login` and `/register` at the proxy if you expect that.

## Tests

```bash
pytest                                   # 106 tests (2 skip without MySQL), about 40 seconds
pytest --cov=app --cov-report=term-missing

# Concurrency tests need MySQL or MariaDB row locks. The migration and sign-in limit tests also run there:
TEST_DATABASE_URL="mysql+pymysql://store:store@127.0.0.1:3306/project_store_test?charset=utf8mb4" pytest
```

## REST API

Base path `/api/v1`. It uses the signed-in session cookie, and writes need an `X-CSRFToken` header (the page's `<meta name="csrf-token">`).

| Method and path | Purpose |
|---|---|
| `GET /products?q=&category=&sort=&page=` | Search and list |
| `GET /products/<slug>` | One product |
| `GET /cart` · `POST /cart/items` · `PATCH`/`DELETE /cart/items/<product_id>` | Cart |
| `POST /checkout` | Reserve stock, create a pending order and gateway order |
| `POST /checkout/verify` | Confirm a payment by signature |
| `GET /orders` · `GET /orders/<id>` | Your orders (download links only once paid) |
| `GET /admin/stats` · `GET /admin/orders` | Admin |
| `POST /admin/products` · `PUT /admin/products/<id>` · `POST /admin/products/<id>/stock` | Admin catalogue and stock |

Errors are `{"error": "...", "fields": {...}}` with a matching status code.

## Make it yours

* Seed projects live in `app/seed.py`. Edit products in the admin screen afterwards.
* **Download links:** the seeded products have no link, so a paid order's page says "Link coming soon. Contact the store." until you set one in the admin screen. Never use a public repository as a link. See [How to set up the private delivery links](#how-to-set-up-the-private-delivery-links).
* Run `flask release-expired` from cron if you don't use the Docker sweeper.

## How to set up the private delivery links

Each product has one **Download link**. When an order is paid, the order page shows that link to the person who paid, and to nobody before that (`tests/test_delivery_links.py` checks the order page, the pay page, the order and product APIs, and other users). The app sends no email and does not ask buyers for a GitHub username, so the link must either work for any buyer as it is, or you give access yourself after each sale.

**The link must never be the public repository.** A public repo can be read by anyone without paying. For each link, open it in a private or incognito window while signed out. It must not show the code.

### Pick one method per product

**A. A file link (no manual step per sale).** Zip the kit. Upload the zip to Google Drive, Dropbox, OneDrive, S3 or similar. Set sharing to "anyone with the link can download", not "public on the web". Use that link.
* Every buyer gets the same link. If it leaks, replace the file, make a new link and update the product. Orders already placed show the new link, because the page reads the product's current link.
* Check it: in an incognito window the link downloads the zip without asking you to sign in.

**B. A private GitHub repository.** Keep the repository private and use its URL as the link.
* A signed-out visitor sees a 404. A buyer sees a 404 too until you add them: repository, Settings, Collaborators, add their username with read access.
* The admin order page shows each buyer's name, email and phone (Admin, Orders, open an order), so you can ask for their GitHub username. This is manual work for every sale, so use it only when orders are few.

### Set the link

1. Sign in as an admin and open Admin, Products.
2. Open the product and paste the link into **Download link**. Save.
3. Place a test order for it and pay with the practice gateway. Confirm that **Open download** works from the order page, in an incognito window after signing in as that buyer.

Do this for every product:

- [ ] Quantum-Resistant Secure Communication System
- [ ] Advanced RAG Knowledge Assistant
- [ ] Production E-Commerce Platform. This is the source of the store itself. Do not use the repository that hosts it unless that repository is private.
- [ ] Smart Home SoC on FPGA. Leave the link empty until it ships. While it is empty the order page says "Link coming soon. Contact the store." The app sends no email, so set the link before you put it on sale.

### Seed data and existing databases

`flask seed` only adds a product whose slug is not in the database yet. Changing links in `app/seed.py` does not change a database that already has the products, so edit those in the admin screen. A new database (for example a fresh Docker volume) gets products with no links, so set them in the admin screen before you sell anything. A database that was seeded before the links were blanked still has the old ones, which point at public GitHub repositories, until you edit them.

## Layout

```
app/
  blueprints/   shop, auth, cart, checkout, account, admin, api, webhooks
  services/     orders (state machine + stock), cart, catalog, payments, products
  templates/    Jinja pages, admin/ for the dashboard
  static/       css, js, self-hosted fonts
tests/          pytest suite
docs/           ARCHITECTURE.md
```

## License

MIT. See [LICENSE](LICENSE). The self-hosted fonts keep their own licences, in `app/static/fonts/LICENSE-*.txt`.
