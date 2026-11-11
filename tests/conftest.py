import os

import pytest
from flask import current_app, g

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import Category, Product, User
from app.seed import seed_catalogue


def pytest_runtest_logreport(report):
    """On GitHub Actions, turn each failing test into an error annotation, so the reason is visible on the run
    page and through the API without opening the raw log."""
    if os.getenv("GITHUB_ACTIONS") and report.failed:
        lines = [l for l in report.longreprtext.strip().splitlines() if l.strip()][-4:] or ["failed"]
        detail = "%0A".join(l.replace("%", "%25").replace("\r", "") for l in lines)
        name = report.nodeid.replace("::", " > ").replace(",", ";")      # "::" and "," would end the title early
        print(f"\n::error title=pytest {report.when} failed: {name}::{detail}")


@pytest.fixture()
def app():
    app = create_app(TestConfig)

    @app.before_request
    def _fresh_login_cache():
        # The fixture keeps one app context open so tests can query the DB directly, which means
        # `g` would otherwise outlive a request and leak the logged-in user between test clients.
        # A real request always gets its own context.
        g.pop("_login_user", None)
        g.pop("csrf_token", None)     # the CSRF token is cached on g too; a real request starts with a fresh one

    with app.app_context():
        db.create_all()
        seed_catalogue()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


_DEFAULT_PASSWORD = "correct-horse"
_default_hashes = {}        # hashing method -> hash; production-cost scrypt takes ~0.4 s, so make it once per run


def make_user(email="buyer@example.com", password=_DEFAULT_PASSWORD, role="customer", name="Buyer"):
    u = User(name=name, email=email, role=role)
    if password == _DEFAULT_PASSWORD:
        method = current_app.config["PASSWORD_HASH_METHOD"]
        if method not in _default_hashes:
            u.set_password(password)
            _default_hashes[method] = u.password_hash
        else:
            u.password_hash = _default_hashes[method]
    else:
        u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture()
def user(app):
    return make_user()


@pytest.fixture()
def admin(app):
    return make_user("boss@example.com", role="admin", name="Boss")


def login(client, email="buyer@example.com", password="correct-horse"):
    return client.post("/login", data={"email": email, "password": password})


def force_login(client, user):
    """Start a signed-in session without the password check, as Django's force_login does. Fixtures use it so a
    test that is not about signing in does not pay for a full-cost password hash; tests of the sign-in flow
    itself still go through login()."""
    with client.session_transaction() as s:
        s["_user_id"] = user.get_id()
        s["_fresh"] = True


@pytest.fixture()
def buyer(client, user):
    force_login(client, user)
    return client


@pytest.fixture()
def admin_client(app, admin):
    c = app.test_client()
    force_login(c, admin)
    return c


@pytest.fixture()
def rag(app):
    return db.session.scalar(db.select(Product).where(Product.slug == "advanced-rag-knowledge-assistant"))


@pytest.fixture()
def soc(app):
    return db.session.scalar(db.select(Product).where(Product.slug == "smart-home-soc-fpga"))
