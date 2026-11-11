import pytest
from flask import g

from app import create_app, inr
from app.config import TestConfig
from app.extensions import db
from app.seed import seed_catalogue

from .conftest import make_user


@pytest.mark.parametrize("paise,expected", [(0, "₹0"), (49900, "₹499"), (199900, "₹1,999"), (12349900, "₹1,23,499"),
                                            (49950, "₹499.50"), (10000000, "₹1,00,000")])
def test_indian_rupee_formatting(paise, expected):
    assert inr(paise) == expected


def test_csrf_blocks_api_writes_without_token():
    class Csrf(TestConfig):
        WTF_CSRF_ENABLED = True
    app = create_app(Csrf)

    @app.before_request
    def _fresh_request_state():      # this test keeps one app context open; a real request gets its own g
        g.pop("_login_user", None)
        g.pop("csrf_token", None)

    with app.app_context():
        db.create_all(); seed_catalogue(); make_user()
        c = app.test_client()
        r = c.post("/login", data={"email": "buyer@example.com", "password": "correct-horse"})
        assert r.status_code == 400                       # login form also needs the token
        page = c.get("/login").data.decode()
        token = page.split('name="csrf_token" value="')[1].split('"')[0]
        assert c.post("/login", data={"email": "buyer@example.com", "password": "correct-horse",
                                       "csrf_token": token}).status_code == 302
        assert c.post("/api/v1/cart/items", json={"product_id": 1, "qty": 1}).status_code == 400
        meta = c.get("/").data.decode().split('name="csrf-token" content="')[1].split('"')[0]
        ok = c.post("/api/v1/cart/items", json={"product_id": 1, "qty": 1}, headers={"X-CSRFToken": meta})
        assert ok.status_code == 201
        db.session.remove(); db.drop_all()
