"""Fixtures for the security audit tests: an app that behaves like production (live_*) and one with CSRF on."""

import pytest

from app.extensions import db
from app.models import Product
from ..conftest import force_login, login, make_user
from .helpers import _with_db, build_app, start_order


@pytest.fixture()
def live_app():
    application = build_app(TESTING=False, PROPAGATE_EXCEPTIONS=False)
    application.add_url_rule("/_boom", "boom", lambda: 1 / 0)
    yield from _with_db(application)


@pytest.fixture()
def live_client(live_app):
    return live_app.test_client()


@pytest.fixture()
def live_buyer(live_app):
    user = make_user()
    c = live_app.test_client()
    force_login(c, user)
    return c


@pytest.fixture()
def live_admin(live_app):
    admin = make_user("boss@example.com", role="admin", name="Boss")
    c = live_app.test_client()
    force_login(c, admin)
    return c


@pytest.fixture()
def live_rag(live_app):
    return db.session.scalar(db.select(Product).where(Product.slug == "advanced-rag-knowledge-assistant"))


@pytest.fixture()
def csrf_app():
    yield from _with_db(build_app(WTF_CSRF_ENABLED=True))


@pytest.fixture()
def victim_order(app, rag):
    make_user("victim@example.com", name="Victim Person")
    v = app.test_client()
    login(v, "victim@example.com")
    order = start_order(v, rag)
    return {"client": v, "id": order["id"], "gateway": order["payment"]["gateway_order_id"], "rag": rag}
