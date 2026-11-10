import pytest
from flask import g

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import Category, Product, User
from app.seed import seed_catalogue


@pytest.fixture()
def app():
    app = create_app(TestConfig)

    @app.before_request
    def _fresh_login_cache():
        # The fixture keeps one app context open so tests can query the DB directly, which means
        # `g` would otherwise outlive a request and leak the logged-in user between test clients.
        # A real request always gets its own context.
        g.pop("_login_user", None)

    with app.app_context():
        db.create_all()
        seed_catalogue()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(email="buyer@example.com", password="correct-horse", role="customer", name="Buyer"):
    u = User(name=name, email=email, role=role)
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


@pytest.fixture()
def buyer(client, user):
    login(client)
    return client


@pytest.fixture()
def admin_client(app, admin):
    c = app.test_client()
    login(c, "boss@example.com")
    return c


@pytest.fixture()
def rag(app):
    return db.session.scalar(db.select(Product).where(Product.slug == "advanced-rag-knowledge-assistant"))


@pytest.fixture()
def soc(app):
    return db.session.scalar(db.select(Product).where(Product.slug == "smart-home-soc-fpga"))
