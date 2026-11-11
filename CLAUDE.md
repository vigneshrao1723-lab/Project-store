# Project Store: guide for Claude Code

Flask + SQLAlchemy + MySQL store selling the owner's engineering projects. Razorpay payments, REST API at /api/v1, admin dashboard, Docker, GitHub Actions. Read docs/ARCHITECTURE.md before changing anything in services/.

## Commands
- Tests (SQLite, ~15s): `pytest`
- Tests with coverage: `pytest --cov=app --cov-report=term-missing`
- Concurrency tests need MySQL/MariaDB: set TEST_DATABASE_URL (see README)
- Run locally: `set FLASK_APP=wsgi.py` then `flask db upgrade` then `flask seed` then `flask run` (Windows)
- Schema changes go through Alembic: edit the model, `flask db migrate -m "..."` (against MySQL), read the generated file in migrations/versions, commit both. Never use `create_all` outside tests. `tests/test_migrations.py` fails if models and migrations disagree.
- Docker: `docker compose up --build` (needs .env with SECRET_KEY, DB_PASSWORD and DB_ROOT_PASSWORD)

## Rules that must not be broken
1. Money is integer paise. Never use floats for prices or totals.
2. Stock changes only through app/services/orders.py (create_order_from_cart, cancel_order, mark_paid, adjust_stock). Each locks product rows with FOR UPDATE in ascending id order and writes an inventory_log row. Never edit Product.stock anywhere else.
3. Order status changes only through services/orders.py, and stay idempotent (payment redirect and webhook can both fire).
4. The amount charged is always computed server-side from the order. Never trust a price from the browser.
5. Payment confirmation must verify the HMAC signature and that the gateway order id belongs to that order.
6. Every state-changing route needs CSRF protection (the webhook is exempt and uses its own signature).
7. Never commit .env, real keys or passwords. Razorpay keys come from environment variables.
8. Any behaviour change needs a test. Run `pytest` before saying a task is done, and show the result.

## Conventions
- Business logic goes in app/services/, routes stay thin.
- No inline <script>; the Content-Security-Policy forbids it. Put JS in app/static/js/.
- Design: graph-paper green-grey, ink blue (#1B2A41), one highlighter yellow (#F5D90A). Archivo + Source Serif 4, self-hosted. Do not add gradients, emoji icons, purple, or card shadows. Keep copy plain and specific.
- Commit small, one task per commit, message in imperative mood.
