"""The Alembic migrations in migrations/ are the schema. These tests keep them honest.

They run on a throwaway SQLite file by default, and on the database in TEST_DATABASE_URL (MySQL in CI)
when that is set, because MySQL is where the migrations are really used.
"""
import os

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask_migrate import downgrade, upgrade

from app import create_app
from app.config import BASE_DIR, TestConfig
from app.extensions import db
from app.models import User, load_user
from app.schema import BASELINE_REVISION, adopt_legacy_database


def _wipe():
    db.session.remove()
    db.metadata.drop_all(db.engine)
    with db.engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))


@pytest.fixture()
def fresh(tmp_path):
    """An app on an empty database that is not the one the other tests share."""
    url = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'migrations.db'}"

    class Cfg(TestConfig):
        SQLALCHEMY_DATABASE_URI = url

    app = create_app(Cfg)
    with app.app_context():
        _wipe()
        yield app
        _wipe()
        db.engine.dispose()


def tables():
    return set(sa.inspect(db.engine).get_table_names())


def version():
    return db.session.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()


def drift():
    """What Alembic would still have to change for the database to match the models."""
    with db.engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        return compare_metadata(ctx, db.metadata)


def test_history_is_a_single_line_that_starts_at_the_baseline():
    script = ScriptDirectory(str(BASE_DIR / "migrations"))
    assert len(script.get_heads()) == 1, "two migrations branch from the same parent; merge them"
    assert script.get_bases() == [BASELINE_REVISION]


def test_migrations_build_exactly_the_schema_the_models_describe(fresh):
    upgrade()
    assert tables() == set(db.metadata.tables) | {"alembic_version"}
    assert drift() == [], "a model changed without a migration: run `flask db migrate`"


def test_upgrade_can_be_run_again(fresh):
    upgrade()
    head = version()
    upgrade()
    assert version() == head


def test_every_migration_can_be_undone(fresh):
    upgrade()
    downgrade(revision="base")
    assert tables() == {"alembic_version"}
    upgrade()
    assert drift() == []


def test_a_database_built_the_old_way_is_adopted_with_its_data_intact(fresh):
    """Databases made by create_all() before migrations existed have no alembic_version, no login_throttle or
    rate_limits table and no users.session_token column."""
    db.create_all()
    db.metadata.tables["login_throttle"].drop(db.engine)
    db.metadata.tables["rate_limits"].drop(db.engine)
    user = User(name="Early Buyer", email="early@example.com")
    user.set_password("correct-horse")
    db.session.add(user)
    db.session.commit()
    db.session.execute(db.text("ALTER TABLE users DROP COLUMN session_token"))
    db.session.commit()
    assert "alembic_version" not in tables()

    result = fresh.test_cli_runner().invoke(args=["adopt-legacy-db"])
    assert result.exit_code == 0 and "adopted" in result.output
    assert version() == BASELINE_REVISION

    upgrade()                      # would fail with "table already exists" if it were not adopted first
    assert {"login_throttle", "rate_limits"} <= tables()
    assert drift() == []
    db.session.remove()            # MySQL refuses to read a table whose definition changed under an open transaction
    assert db.session.scalar(db.select(User.email).where(User.email == "early@example.com")) == "early@example.com"
    # The new column arrives empty, which no cookie can match; the first sign-in gives the account a token.
    early = db.session.scalar(db.select(User).where(User.email == "early@example.com"))
    assert early.session_token == "" and load_user(f"{early.id}:") is None
    assert early.get_id().startswith(f"{early.id}:") and early.session_token


def test_adopting_twice_is_harmless(fresh):
    db.create_all()
    assert adopt_legacy_database() is True
    assert adopt_legacy_database() is False
    assert version() == BASELINE_REVISION


def test_an_empty_database_is_not_adopted(fresh):
    assert adopt_legacy_database() is False
    assert "alembic_version" not in tables()


def test_seed_asks_for_the_schema_first_then_works(fresh):
    runner = fresh.test_cli_runner()
    refused = runner.invoke(args=["seed"])
    assert refused.exit_code != 0 and "flask db upgrade" in refused.output
    assert "products" not in tables()          # seed no longer creates tables behind the migrations' back

    upgrade()
    seeded = runner.invoke(args=["seed"])
    assert seeded.exit_code == 0 and "Seeded." in seeded.output
