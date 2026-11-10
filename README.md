# Project Store

A full-stack store for selling finished engineering projects: sign-in, a searchable catalogue, per-user carts, a checkout that reserves stock inside one database transaction, Razorpay payments, order management and an admin dashboard. REST API, automated tests, Docker and CI included.

Built with Flask, SQLAlchemy, MySQL, Jinja and hand-written CSS. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.

## Run it with Docker (MySQL)

```bash
cp .env.example .env          # set SECRET_KEY; Razorpay keys are optional
docker compose up --build
```

Open http://localhost:8000. The first start creates the tables and loads the catalogue.

## Run it locally without Docker (SQLite)

```bash
python -m venv venv
venv\Scripts\activate          # Windows;  source venv/bin/activate on macOS/Linux
pip install -r requirements-dev.txt
set FLASK_APP=wsgi.py          # Windows;  export FLASK_APP=wsgi.py on macOS/Linux
flask seed
flask run
```

With no `DATABASE_URL` it uses a SQLite file in `instance/`.

**Demo admin:** `admin@projectstore.local` / `admin12345`. Change it before putting the app anywhere public: set `ADMIN_EMAIL` and `ADMIN_PASSWORD` before the first `flask seed`, or run `flask create-admin you@example.com`.

## Payments

* **No keys set:** a practice gateway runs the same signing and confirmation code as Razorpay. Good for demos and tests. A yellow banner says so.
* **Razorpay test mode:** put your test `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in `.env`. Use Razorpay's test card numbers from their docs. For the webhook, add `https://<your-host>/webhooks/razorpay` in the Razorpay dashboard for `payment.captured` and set `RAZORPAY_WEBHOOK_SECRET`. Locally, expose the port with a tunnel.

## Tests

```bash
pytest                                   # 67 tests, about 15 seconds
pytest --cov=app --cov-report=term-missing

# Concurrency tests need MySQL or MariaDB row locks:
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
