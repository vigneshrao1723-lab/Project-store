"""Security audit A8: access control."""

import re

from app.services import payments
from .helpers import order_status


def _assert_untouched(public_id):
    assert order_status(public_id) == "pending"


def test_a8_other_users_cannot_read_an_order_page(buyer, victim_order):
    r = buyer.get(f"/orders/{victim_order['id']}")
    assert r.status_code == 404 and "Victim Person" not in r.get_data(as_text=True)


def test_a8_other_users_cannot_read_an_order_through_the_api(buyer, victim_order):
    r = buyer.get(f"/api/v1/orders/{victim_order['id']}")
    assert r.status_code in (403, 404) and "Victim Person" not in r.get_data(as_text=True)


def test_a8_orders_list_contains_only_own_orders(buyer, victim_order):
    assert victim_order["id"] not in buyer.get("/api/v1/orders").get_data(as_text=True)
    assert victim_order["id"] not in buyer.get("/orders").get_data(as_text=True)


def test_a8_other_users_cannot_open_the_pay_page(buyer, victim_order):
    assert buyer.get(f"/checkout/pay/{victim_order['id']}").status_code == 404


def test_a8_other_users_cannot_pay_someone_elses_order(buyer, victim_order):
    r = buyer.post(f"/checkout/test-pay/{victim_order['id']}", data={"outcome": "pay"})
    assert r.status_code == 404
    _assert_untouched(victim_order["id"])


def test_a8_other_users_cannot_cancel_someone_elses_order(buyer, victim_order):
    r = buyer.post(f"/checkout/cancel/{victim_order['id']}")
    assert r.status_code in (403, 404)
    _assert_untouched(victim_order["id"])


def test_a8_other_users_cannot_confirm_payment_on_the_page_route(buyer, victim_order):
    sig = payments.sign(victim_order["gateway"], "pay_x")
    r = buyer.post("/checkout/verify", data={"public_id": victim_order["id"], "razorpay_order_id": victim_order["gateway"],
                                             "razorpay_payment_id": "pay_x", "razorpay_signature": sig})
    assert r.status_code == 404
    _assert_untouched(victim_order["id"])


def test_a8_other_users_cannot_confirm_payment_on_the_api_route(buyer, victim_order):
    sig = payments.sign(victim_order["gateway"], "pay_x")
    r = buyer.post("/api/v1/checkout/verify", json={"order_id": victim_order["id"],
                                                    "gateway_order_id": victim_order["gateway"],
                                                    "payment_id": "pay_x", "signature": sig})
    assert r.status_code == 404
    _assert_untouched(victim_order["id"])


def test_a8_cart_is_private(buyer, victim_order):
    assert buyer.get("/api/v1/cart").get_json()["count"] == 0
    v = victim_order["client"]
    v.post("/api/v1/cart/items", json={"product_id": victim_order["rag"].id, "qty": 2})
    buyer.delete(f"/api/v1/cart/items/{victim_order['rag'].id}")
    buyer.patch(f"/api/v1/cart/items/{victim_order['rag'].id}", json={"qty": 5})
    assert v.get("/api/v1/cart").get_json()["count"] == 2, "another user's cart line was changed"


def test_a8_the_store_has_no_address_or_account_routes_to_protect(app):
    paths = {r.rule for r in app.url_map.iter_rules()}
    assert not [p for p in paths if re.search(r"address|profile|account|/users?/", p)], \
        "new per-user routes appeared; add an ownership test for them"
