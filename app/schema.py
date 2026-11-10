"""Schema management helpers. The schema itself lives in migrations/; see README.md."""
import sqlalchemy as sa
from flask_migrate import stamp

from .extensions import db

# The migration that matches databases built by db.create_all() before migrations existed.
BASELINE_REVISION = "0001"


def adopt_legacy_database():
    """Mark a pre-migrations database as being at the baseline revision.

    A database created by the old `create_all` start-up has the tables but no alembic_version table, so
    `flask db upgrade` would try to create them again and fail. Stamping it at the baseline tells Alembic
    that those tables already exist; the upgrade that follows then applies only the newer migrations.

    Returns True if it stamped, False if there was nothing to do (empty database, or already managed).
    """
    tables = set(sa.inspect(db.engine).get_table_names())
    if "alembic_version" in tables or "users" not in tables:
        return False
    stamp(revision=BASELINE_REVISION)
    return True


def schema_is_present():
    return "products" in sa.inspect(db.engine).get_table_names()
