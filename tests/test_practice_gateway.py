"""The practice gateway is opt-in, and SECRET_KEY must be strong outside tests and debug runs."""
import pytest

from app import create_app, secret_key_problem
from app.config import TestConfig
from app.extensions import db
from app.models import Order
from app.services import payments


def _checkout(client, product):
    client.post("/api/v1/cart/items", json={"product_id": product.id, "qty": 1})
    return client.post("/api/v1/checkout", json={"billing_name": "Buyer"})


@pytest.fixture()
def gateway_off(app):
    app.config["ALLOW_PRACTICE_GATEWAY"] = False
    return app


def test_the_test_config_allows_the_practice_gateway(app):
    assert payments.mode() == "test"


def test_gateway_mode_is_off_without_keys_or_the_flag(gateway_off):
    assert payments.mode() == "off"


def test_razorpay_keys_win_over_the_flag(app):
    app.config.update(RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="s", ALLOW_PRACTICE_GATEWAY=False)
    assert payments.mode() == "razorpay"


def test_pay_page_says_practice_payment_no_real_money(buyer, rag):
    pid = _checkout(buyer, rag).get_json()["id"]
    html = buyer.get(f"/checkout/pay/{pid}").get_data(as_text=True)
    assert "Practice payment, no real money" in html
    assert "Nothing is charged to any card" in html


def test_pay_page_offers_no_payment_button_when_the_gateway_is_off(gateway_off, buyer, rag):
    resp = _checkout(buyer, rag)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["payment"]["provider"] == "off" and body["payment"]["gateway_order_id"] is None
    html = buyer.get(f"/checkout/pay/{body['id']}").get_data(as_text=True)
    assert "Payment is not available" in html
    assert "test-pay" not in html and "Practice payment" not in html


def test_nothing_can_be_marked_paid_when_the_gateway_is_off(gateway_off, buyer, rag):
    pid = _checkout(buyer, rag).get_json()["id"]
    assert buyer.post(f"/checkout/test-pay/{pid}", data={"outcome": "pay"}).status_code == 404
    # Empty and made-up identifiers: an order with no gateway id must not "match" a missing one either.
    for fields in ({}, {"razorpay_order_id": "", "razorpay_payment_id": "p", "razorpay_signature": "s"}):
        buyer.post("/checkout/verify", data={"public_id": pid, **fields})
    buyer.post("/api/v1/checkout/verify", json={"order_id": pid, "payment_id": "p", "signature": "s"})
    buyer.post("/api/v1/checkout/verify", json={"order_id": pid, "gateway_order_id": None, "payment_id": "p",
                                                 "signature": "s"})
    db.session.expire_all()
    assert db.session.scalar(db.select(Order.status).where(Order.public_id == pid)) == "pending"


def test_a_signature_cannot_be_verified_when_the_gateway_is_off(gateway_off):
    assert payments.verify_payment("test_1", "pay_1", payments.sign("test_1", "pay_1")) is False


@pytest.mark.parametrize("key,why", [
    ("", "shorter"),
    ("x" * 31, "shorter"),
    ("dev-only-change-me", "shorter"),
    ("change-me-to-a-long-random-string", "placeholder"),
    ("please-CHANGE-ME-" + "a1" * 20, "placeholder"),
    ("a1b2" * 8 + "-your-secret-key-here", "placeholder"),
])
def test_weak_secret_keys_are_described(key, why):
    assert why in secret_key_problem(key)


def test_a_random_secret_key_has_no_problem():
    assert secret_key_problem("9f2c" * 16) is None


def test_the_error_tells_the_operator_how_to_make_a_key():
    cfg = type("C", (TestConfig,), {"TESTING": False, "SECRET_KEY": "short"})
    with pytest.raises(RuntimeError, match=r"secrets\.token_hex\(32\)"):
        create_app(cfg)


def test_debug_runs_may_use_a_short_key():
    cfg = type("C", (TestConfig,), {"TESTING": False, "DEBUG": True, "SECRET_KEY": "short"})
    assert create_app(cfg) is not None


def test_the_check_does_not_depend_on_flask_env(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "development")
    cfg = type("C", (TestConfig,), {"TESTING": False, "SECRET_KEY": "dev-only-change-me"})
    with pytest.raises(RuntimeError):
        create_app(cfg)
