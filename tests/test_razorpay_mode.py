"""Razorpay code path, with the HTTP call to Razorpay mocked out."""
import hashlib
import hmac

import pytest
import requests

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import Order, Product
from app.seed import seed_catalogue

from .conftest import login, make_user

KEY, SECRET = "rzp_test_abc", "shh-secret"


class RzpConfig(TestConfig):
    RAZORPAY_KEY_ID = KEY
    RAZORPAY_KEY_SECRET = SECRET


class FakeResp:
    def __init__(self, payload, ok=True):
        self.payload, self.ok = payload, ok

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError("500")

    def json(self):
        return self.payload


@pytest.fixture()
def rzp_client():
    app = create_app(RzpConfig)
    with app.app_context():
        db.create_all(); seed_catalogue(); make_user()
        c = app.test_client()
        login(c)
        yield c
        db.session.remove(); db.drop_all()


def rag_id():
    return db.session.scalar(db.select(Product.id).where(Product.slug == "advanced-rag-knowledge-assistant"))


def test_checkout_registers_order_with_razorpay_and_pay_page_uses_it(rzp_client, monkeypatch):
    seen = {}

    def fake_post(url, auth, json, timeout):
        seen.update(url=url, auth=auth, body=json)
        return FakeResp({"id": "order_RZP123"})
    monkeypatch.setattr("app.services.payments.requests.post", fake_post)

    rzp_client.post("/api/v1/cart/items", json={"product_id": rag_id(), "qty": 2})
    r = rzp_client.post("/checkout", data={"billing_name": "Asha", "phone": "9999999999"})
    pay_url = r.headers["Location"]
    assert seen["auth"] == (KEY, SECRET) and seen["body"]["currency"] == "INR"
    assert seen["body"]["amount"] == 2 * 299900          # amount comes from the server, never the browser
    page = rzp_client.get(pay_url).data.decode()
    assert 'data-order="order_RZP123"' in page and KEY in page and SECRET not in page
    assert "checkout.razorpay.com" in page


def test_razorpay_signature_flow(rzp_client, monkeypatch):
    monkeypatch.setattr("app.services.payments.requests.post", lambda *a, **k: FakeResp({"id": "order_RZP9"}))
    rzp_client.post("/api/v1/cart/items", json={"product_id": rag_id(), "qty": 1})
    public_id = rzp_client.post("/checkout", data={"billing_name": "A"}).headers["Location"].rsplit("/", 1)[1]

    bad = rzp_client.post("/checkout/verify", data={"public_id": public_id, "razorpay_order_id": "order_RZP9",
                                                    "razorpay_payment_id": "pay_1", "razorpay_signature": "nope"})
    assert bad.headers["Location"].endswith(f"/checkout/pay/{public_id}")
    assert db.session.scalar(db.select(Order.status).where(Order.public_id == public_id)) == "pending"

    sig = hmac.new(SECRET.encode(), b"order_RZP9|pay_1", hashlib.sha256).hexdigest()
    good = rzp_client.post("/checkout/verify", data={"public_id": public_id, "razorpay_order_id": "order_RZP9",
                                                     "razorpay_payment_id": "pay_1", "razorpay_signature": sig})
    assert good.headers["Location"].endswith(f"/orders/{public_id}")
    assert db.session.scalar(db.select(Order.status).where(Order.public_id == public_id)) == "paid"


def test_test_gateway_is_disabled_when_razorpay_is_configured(rzp_client, monkeypatch):
    monkeypatch.setattr("app.services.payments.requests.post", lambda *a, **k: FakeResp({"id": "order_X"}))
    rzp_client.post("/api/v1/cart/items", json={"product_id": rag_id(), "qty": 1})
    public_id = rzp_client.post("/checkout", data={"billing_name": "A"}).headers["Location"].rsplit("/", 1)[1]
    assert rzp_client.post(f"/checkout/test-pay/{public_id}", data={"outcome": "pay"}).status_code == 404


def test_gateway_outage_releases_stock_and_restores_cart(rzp_client, monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("down")
    monkeypatch.setattr("app.services.payments.requests.post", boom)
    before = db.session.get(Product, rag_id()).stock
    rzp_client.post("/api/v1/cart/items", json={"product_id": rag_id(), "qty": 2})
    r = rzp_client.post("/checkout", data={"billing_name": "A"})
    assert r.headers["Location"].endswith("/cart")
    db.session.expire_all()
    assert db.session.get(Product, rag_id()).stock == before
    assert rzp_client.get("/api/v1/cart").get_json()["count"] == 2
    assert db.session.scalar(db.select(Order.status)) == "failed"


def test_api_checkout_reports_502_on_gateway_outage(rzp_client, monkeypatch):
    monkeypatch.setattr("app.services.payments.requests.post", lambda *a, **k: FakeResp({}, ok=False))
    rzp_client.post("/api/v1/cart/items", json={"product_id": rag_id(), "qty": 1})
    assert rzp_client.post("/api/v1/checkout", json={}).status_code == 502
