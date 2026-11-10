#!/bin/sh
set -e
export FLASK_APP=wsgi.py

# Wait for the database, bring the schema up to date with migrations, load the catalogue on first run.
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
# A database created before migrations existed has the tables but no version record. Mark it as being at
# the first migration so the upgrade below only applies what is new. Does nothing on any other database.
flask adopt-legacy-db
flask db upgrade
flask seed --if-empty
exec "$@"
