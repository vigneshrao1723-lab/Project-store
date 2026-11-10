# Project Store

A full-stack store for selling finished engineering projects: sign-in, a searchable catalogue, per-user carts, a checkout that reserves stock inside one database transaction, Razorpay payments, order management and an admin dashboard. REST API, automated tests, Docker and CI included.

Built with Flask, SQLAlchemy, MySQL, Jinja and hand-written CSS. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.

## Run it with Docker (MySQL)

```bash
cp .env.example .env          # set SECRET_KEY; Razorpay keys are optional
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

**Demo admin:** `admin@projectstore.local` / `admin12345`. Change it before putting the app anywhere public: set `ADMIN_EMAIL` and `ADMIN_PASSWORD` before the first `flask seed`, or run `flask create-admin you@example.com`.

## Payments

* **No keys set:** a practice gateway runs the same signing and confirmation code as Razorpay. Good for demos and tests. A yellow banner says so.
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

## Tests

```bash
pytest                                   # 75 tests (2 skip without MySQL), about 20 seconds
pytest --cov=app --cov-report=term-missing

# Concurrency tests need MySQL or MariaDB row locks. The migration tests also run there:
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
* **Download links:** the seeded links point at GitHub repositories. If a repository is public, anyone can read it without buying. Replace each link with a private one (a private repo invite page, or a file link) before selling for real.
* Run `flask release-expired` from cron if you don't use the Docker sweeper.

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
