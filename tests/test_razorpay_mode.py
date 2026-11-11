"""Razorpay code path, with the HTTP call to Razorpay mocked out."""
import hashlib
import hmac
import json

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


def captured(order_id="order_RZP9", **changes):
    """What Razorpay's GET /v1/payments/<id> returns for a captured payment of one advanced-rag kit."""
    entity = {"id": "pay_1", "order_id": order_id, "amount": 299900, "currency": "INR", "status": "captured"}
    return {**entity, **changes}


def test_razorpay_signature_flow(rzp_client, monkeypatch):
    monkeypatch.setattr("app.services.payments.requests.post", lambda *a, **k: FakeResp({"id": "order_RZP9"}))
    monkeypatch.setattr("app.services.payments.requests.get", lambda *a, **k: FakeResp(captured()))
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


# ---- the browser's "success" is checked against Razorpay before the order is marked paid ------------------------

@pytest.fixture()
def pending_order(rzp_client, monkeypatch):
    monkeypatch.setattr("app.services.payments.requests.post", lambda *a, **k: FakeResp({"id": "order_RZP9"}))
    rzp_client.post("/api/v1/cart/items", json={"product_id": rag_id(), "qty": 1})
    public_id = rzp_client.post("/checkout", data={"billing_name": "A"}).headers["Location"].rsplit("/", 1)[1]
    sig = hmac.new(SECRET.encode(), b"order_RZP9|pay_1", hashlib.sha256).hexdigest()
    return public_id, {"public_id": public_id, "razorpay_order_id": "order_RZP9", "razorpay_payment_id": "pay_1",
                       "razorpay_signature": sig}


def status_of(public_id):
    db.session.expire_all()
    return db.session.scalar(db.select(Order.status).where(Order.public_id == public_id))


@pytest.mark.parametrize("changes", [{"amount": 100}, {"amount": 299900.0}, {"amount": "299900"}, {"currency": "USD"},
                                     {"status": "authorized"}, {"status": "failed"}, {"order_id": "order_OTHER"}],
                         ids=lambda c: str(c))
def test_a_validly_signed_payment_that_does_not_match_the_order_is_not_marked_paid(rzp_client, pending_order,
                                                                                    monkeypatch, changes):
    public_id, form = pending_order
    monkeypatch.setattr("app.services.payments.requests.get", lambda *a, **k: FakeResp(captured(**changes)))
    r = rzp_client.post("/checkout/verify", data=form)
    assert r.headers["Location"].endswith(f"/checkout/pay/{public_id}")
    assert status_of(public_id) == "pending"


def test_an_unreachable_razorpay_leaves_the_order_pending_for_the_webhook(rzp_client, pending_order, monkeypatch):
    public_id, form = pending_order

    def down(*a, **k):
        raise requests.ConnectionError("down")
    monkeypatch.setattr("app.services.payments.requests.get", down)
    rzp_client.post("/checkout/verify", data=form)
    assert status_of(public_id) == "pending"
    monkeypatch.setattr("app.services.payments.requests.get", lambda *a, **k: FakeResp({}, ok=False))
    rzp_client.post("/checkout/verify", data=form)
    assert status_of(public_id) == "pending"


def test_the_payment_is_fetched_with_the_key_pair_and_a_quoted_id(rzp_client, pending_order, monkeypatch):
    public_id, form = pending_order
    seen = {}

    def fake_get(url, auth, timeout):
        seen.update(url=url, auth=auth)
        return FakeResp(captured())
    monkeypatch.setattr("app.services.payments.requests.get", fake_get)
    rzp_client.post("/checkout/verify", data=form)
    assert seen == {"url": "https://api.razorpay.com/v1/payments/pay_1", "auth": (KEY, SECRET)}
    assert status_of(public_id) == "paid"


def test_api_verify_makes_the_same_check(rzp_client, pending_order, monkeypatch):
    public_id, form = pending_order
    body = {"order_id": public_id, "gateway_order_id": "order_RZP9", "payment_id": "pay_1",
            "signature": form["razorpay_signature"]}
    monkeypatch.setattr("app.services.payments.requests.get", lambda *a, **k: FakeResp(captured(amount=1)))
    assert rzp_client.post("/api/v1/checkout/verify", json=body).status_code == 400
    assert status_of(public_id) == "pending"
    monkeypatch.setattr("app.services.payments.requests.get", lambda *a, **k: FakeResp(captured()))
    assert rzp_client.post("/api/v1/checkout/verify", json=body).status_code == 200
    assert status_of(public_id) == "paid"


def test_webhook_checks_status_and_order_as_well_as_the_signature(rzp_client, pending_order):
    public_id, _ = pending_order
    app = rzp_client.application

    def send(entity, event="payment.captured"):
        raw = json.dumps({"event": event, "payload": {"payment": {"entity": entity}}}).encode()
        sig = hmac.new(app.config["RAZORPAY_WEBHOOK_SECRET"].encode(), raw, hashlib.sha256).hexdigest()
        return app.test_client().post("/webhooks/razorpay", data=raw, headers={"X-Razorpay-Signature": sig})

    for entity in (captured(status="authorized"), captured(amount=1), captured(currency="usd"),
                   captured(amount=True), captured(amount=None)):
        r = send(entity)
        assert r.status_code == 200 and r.get_json()["ok"] is False
        assert status_of(public_id) == "pending"
    assert send(captured(order_id=["x"])).status_code == 400
    assert send(captured(id=5)).status_code == 400
    assert send(captured(order_id="order_UNKNOWN")).status_code == 200      # no such order: nothing to do
    assert send(captured(), event="order.paid").get_json() == {"ok": True}
    assert status_of(public_id) == "paid"
