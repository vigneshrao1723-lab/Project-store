# Resume coverage

Each claim on the resume entry for Project Store, checked against the code on branch `v1.4-final`. "Where" names the
file and feature that backs it. Where a claim is only partly true, the last column says so and suggests wording; nothing
was added just to make a line true.

Resume entry: **Production E-Commerce Platform | REST APIs, Database Transactions, Docker, CI/CD**

## Headline keywords

| Keyword | Used? | Where | Notes |
|---|---|---|---|
| REST APIs | Yes | `app/blueprints/api.py`: 16 JSON routes under `/api/v1` (catalogue, cart, checkout and payment verification, orders, admin stats, orders, products and stock). Session-cookie auth, CSRF header on writes, one error shape `{"error", "fields"}`, rate limits on writes. | Tests: `tests/test_checkout_flow.py`, `tests/security/test_a16_api.py`. |
| Database Transactions | Yes | `app/services/orders.py`: `create_order_from_cart`, `cancel_order`, `mark_paid`, `adjust_stock` each run in one transaction, lock rows with `SELECT ... FOR UPDATE` in ascending id order, and write an `inventory_log` row. | Real MySQL row-lock tests: `tests/test_concurrency.py` (run against MySQL 8.4, see the MORNING_REPORT). |
| Docker | Yes | `Dockerfile` (pinned base image by digest, hashed lock install, non-root user, healthcheck, gunicorn), `docker-compose.yml` (MySQL 8.4, one-shot migrate service, web, sweeper; rows-only database account for the app). | Built and smoke-tested this session. |
| CI/CD | Partly | `.github/workflows/ci.yml`: on every push and pull request, tests on SQLite and MySQL, coverage gate, pip-audit, bandit, lock-file check, gitleaks over the whole history, Docker build and container smoke test. On a push to `main` the `deploy` job **publishes** the image to GitHub Container Registry. | Nothing deploys the image to a server automatically: there is no hosting target configured. Whether the publish step has run on GitHub was **not verified** from here (no GitHub CLI on this machine). Suggested wording below. |

## Bullet 1

> Built a full-stack e-commerce platform with user authentication/authorization, a product catalog with category-based
> search and inventory tracking, and a shopping cart and checkout flow with sandboxed payment integration

| Claim | Used? | Where |
|---|---|---|
| Full-stack | Yes | Flask server-rendered pages (`app/templates/`), JavaScript for the cart, motion and payments (`app/static/js/`), MySQL through SQLAlchemy (`app/models.py`), Alembic migrations 0001 to 0009. |
| User authentication | Yes | `app/blueprints/auth.py` (`register`, `login`, `logout`): scrypt password hashes at the OWASP cost, session fixation protection, sign-in throttling per email and address, a server-side session token that signing out or a password change rotates. |
| Authorization | Yes | Roles `customer` and `admin` (`User.role`); `admin_required` in `app/blueprints/admin.py`; `admin_required_json` in `api.py`; per-user ownership checks on orders, invoices and payments (`own_order_or_404`). A route-walk test (`tests/security/test_v14_audit.py`) fails if any route outside the public list works without signing in. |
| Product catalog | Yes | `app/blueprints/shop.py` (`/catalogue`, `/p/<slug>`), `app/services/catalog.py`. |
| Category-based search | Yes | `search_products(q, category, sort, page)` in `app/services/catalog.py`: text search over title, tagline, technologies and field name, filtered by category (`/catalogue?category=...`), sorted and paginated; category counts in the sidebar. |
| Inventory tracking | Yes | `Product.stock`, the `inventory_log` table (`InventoryLog` in `app/models.py`), stock held at checkout and released when a hold expires (`release_expired`), admin stock adjustments (`adjust_stock`). |
| Shopping cart | Yes | `app/services/cart.py` (`set_qty`, `contents`), `CartItem`, `/cart` and `/api/v1/cart`. |
| Checkout flow | Yes | `app/blueprints/checkout.py`: reservation hold, server-side total, terms agreement (v1.4), one pending order per user, order messages after payment. |
| Sandboxed payment integration | Yes, with a limit | `app/services/payments.py`: Razorpay Orders API and Checkout in **test mode** with `rzp_test_` keys, HMAC-SHA256 signature checks with `hmac.compare_digest`, a signed webhook, and a built-in practice gateway for demos. | The tests use a fake Razorpay HTTP layer; no call against a real Razorpay test account was made in this session. The resume line is accurate as long as you have used your own test keys; otherwise say "Razorpay integration (test mode)". |

## Bullet 2

> Implemented order management and an admin dashboard backed by transactional database operations, exposed through REST
> APIs and validated with automated testing

| Claim | Used? | Where |
|---|---|---|
| Order management | Yes | Statuses pending, paid, cancelled, expired, failed, refund_due, refunded (`ORDER_STATUSES` in `app/models.py`), idempotent `mark_paid` (payment redirect and webhook can both fire), buyer order pages, admin cancel and "refunded" actions (`app/blueprints/admin.py`). |
| Admin dashboard | Yes | `/admin` (`dashboard()` in `app/blueprints/admin.py`): revenue and paid orders, orders by status, units in stock, a 14-day revenue chart, low-stock projects (5 or fewer) and the latest orders; product, order and message management pages. |
| Backed by transactional database operations | Yes | The four functions in `app/services/orders.py` above; nothing else changes stock or order status. |
| Exposed through REST APIs | Yes | `/api/v1/orders`, `/api/v1/admin/stats`, `/api/v1/admin/orders`, `/api/v1/admin/products`, `/api/v1/admin/products/<id>/stock`. |
| Validated with automated testing | Yes | FACTS_LINE |

## Bullet 3

> Containerized the application with Docker and configured a CI/CD pipeline for automated build, test, and deployment

| Claim | Used? | Where |
|---|---|---|
| Containerized with Docker | Yes | See Docker above. |
| Automated build | Yes | CI `build` job: Docker Buildx build and a container smoke test (`/healthz`). |
| Automated test | Yes | CI `test` job (SQLite suite with a coverage gate, then the MySQL concurrency, migration and rate-limit tests) and `security` and `secrets` jobs. |
| Automated deployment | **Partly** | The `deploy` job pushes the image to GHCR on a push to `main` (delivery of a ready image). There is no step that runs it on a server, because no server is configured; the live store is started by hand with `docker compose` (`docs/RELEASE_STEPS_v1.4.md`). |

## Suggested wording

Everything except "deployment" is accurate as written. Two honest options for bullet 3:

* "Containerized the application with Docker and built a CI/CD pipeline (GitHub Actions) that tests on SQLite and
  MySQL, runs security scans and publishes the Docker image to GitHub Container Registry on every merge to main."
* Or keep "deployment" only after adding a real deploy step to a host you control (for example SSH to a VPS and
  `docker compose pull && up -d`), which needs a server and its credentials that this project does not have today.

Also consider "Razorpay payment integration (test mode)" instead of "sandboxed payment integration" if you have not
run it with your own Razorpay test keys.
