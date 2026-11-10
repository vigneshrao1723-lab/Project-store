#!/bin/sh
set -e
export FLASK_APP=wsgi.py

# Wait for the database, create tables, load the catalogue on first run.
python - <<'PY'
import time
from app import create_app
from app.extensions import db
app = create_app()
with app.app_context():
    for attempt in range(30):
        try:
            db.session.execute(db.text("SELECT 1"))
            break
        except Exception as exc:
            print(f"database not ready ({attempt + 1}/30): {exc.__class__.__name__}", flush=True)
            time.sleep(2)
    else:
        raise SystemExit("database never became ready")
PY
flask init-db
flask seed --if-empty
exec "$@"
