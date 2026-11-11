"""The money path: cart -> reserved order -> payment -> delivery, plus every way it can go wrong."""
from datetime import timedelta

from app.extensions import db
from app.models import CartItem, InventoryLog, Order, Product, utcnow
from app.services import orders as svc
from app.services import payments

from .conftest import login, make_user


def add(client, product, qty=1):
    return client.post("/api/v1/cart/items", json={"product_id": product.id, "qty": qty})


def checkout(client, **body):
    return client.post("/api/v1/checkout", json=body)


def pay(client, order_json):
    """Complete a payment through the test gateway the way the browser would."""
    pay_info = order_json["payment"]
    pid = "pay_test_x1"
    sig = payments.sign(pay_info["gateway_order_id"], pid)
    return client.post("/api/v1/checkout/verify", json={
        "order_id": order_json["id"], "gateway_order_id": pay_info["gateway_order_id"],
        "payment_id": pid, "signature": sig})


def stock_of(product):
    db.session.expire_all()
    return db.session.get(Product, product.id).stock


def test_happy_path_reserves_stock_then_delivers_after_payment(buyer, rag):
    rag.delivery_url = "https://files.example.com/kit-abc123"      # seeded products have no link
    db.session.commit()
    before = rag.stock
    add(buyer, rag, 2)
    r = checkout(buyer, billing_name="Vignesh")
    assert r.status_code == 201
    order = r.get_json()
    assert order["status"] == "pending"
    assert order["total_paise"] == 2 * rag.price_paise
    assert stock_of(rag) == before - 2                      # held at checkout
    assert order["items"][0]["download_url"] is None        # not deliverable before payment
    assert buyer.get("/api/v1/cart").get_json()["count"] == 0

    paid = pay(buyer, order).get_json()
    assert paid["status"] == "paid"
    assert paid["items"][0]["download_url"] == "https://files.example.com/kit-abc123"
    assert stock_of(rag) == before - 2                      # no second deduction


def test_payment_confirmation_is_idempotent(buyer, rag):
    add(buyer, rag)
    order = checkout(buyer).get_json()
    before = stock_of(rag)
    assert pay(buyer, order).get_json()["status"] == "paid"
    assert pay(buyer, order).get_json()["status"] == "paid"
    assert stock_of(rag) == before


def test_tampered_signature_is_rejected(buyer, rag):
    add(buyer, rag)
    order = checkout(buyer).get_json()
    r = buyer.post("/api/v1/checkout/verify", json={
        "order_id": order["id"], "gateway_order_id": order["payment"]["gateway_order_id"],
        "payment_id": "pay_x", "signature": "0" * 64})
    assert r.status_code == 400
    assert buyer.get(f"/api/v1/orders/{order['id']}").get_json()["status"] == "pending"


def test_signature_for_another_order_cannot_pay_this_one(buyer, rag, soc):
    add(buyer, rag)
    first = checkout(buyer).get_json()
    buyer.post(f"/checkout/cancel/{first['id']}")      # one unpaid order at a time: cancel it, which refills the cart
    second = checkout(buyer).get_json()
    assert second["id"] != first["id"]
    sig = payments.sign(first["payment"]["gateway_order_id"], "pay_1")
    r = buyer.post("/api/v1/checkout/verify", json={
        "order_id": second["id"], "gateway_order_id": first["payment"]["gateway_order_id"],
        "payment_id": "pay_1", "signature": sig})
    assert r.status_code == 400


def test_last_copy_goes_to_one_buyer_only(app, client, rag):
    svc.adjust_stock(rag.id, -(rag.stock - 1))
    a, b = make_user("a@x.com"), make_user("b@x.com")
    ca, cb = app.test_client(), app.test_client()
    login(ca, "a@x.com"), login(cb, "b@x.com")
    assert add(ca, rag).status_code == 201
    assert add(cb, rag).status_code == 201
    assert checkout(ca).status_code == 201
    loser = checkout(cb)
    assert loser.status_code == 409
    assert "sold out" in loser.get_json()["error"]
    assert stock_of(rag) == 0


def test_double_submit_creates_one_order(buyer, rag):
    add(buyer, rag)
    assert checkout(buyer).status_code == 201
    assert checkout(buyer).status_code == 409                # cart already consumed
    assert db.session.scalar(db.select(db.func.count(Order.id))) == 1


def test_failed_checkout_changes_nothing(buyer, user, rag, soc):
    """If any line can't be filled, no stock moves and the cart is untouched."""
    add(buyer, rag, 2)
    # Sold-out items can't be added through the API, so simulate stock running out after adding.
    db.session.add(CartItem(user_id=user.id, product_id=soc.id, qty=1))
    db.session.commit()
    before = stock_of(rag)
    r = checkout(buyer)
    assert r.status_code == 409
    assert stock_of(rag) == before
    assert buyer.get("/api/v1/cart").get_json()["count"] == 3
    assert db.session.scalar(db.select(db.func.count(Order.id))) == 0


def test_expired_hold_releases_stock(buyer, rag):
    add(buyer, rag, 3)
    order = checkout(buyer).get_json()
    held = stock_of(rag)
    o = db.session.scalar(db.select(Order).where(Order.public_id == order["id"]))
    o.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert svc.release_expired() == 1
    assert stock_of(rag) == held + 3
    assert buyer.get(f"/api/v1/orders/{order['id']}").get_json()["status"] == "expired"
    assert svc.release_expired() == 0                        # second sweep is a no-op


def test_late_payment_after_expiry_retakes_stock(buyer, rag):
    add(buyer, rag, 1)
    order = checkout(buyer).get_json()
    o = db.session.scalar(db.select(Order).where(Order.public_id == order["id"]))
    o.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    svc.release_expired()
    before = stock_of(rag)
    assert pay(buyer, order).get_json()["status"] == "paid"
    assert stock_of(rag) == before - 1


def test_late_payment_when_sold_out_is_flagged_for_refund(app, buyer, rag):
    svc.adjust_stock(rag.id, -(rag.stock - 1))
    add(buyer, rag, 1)
    order = checkout(buyer).get_json()
    o = db.session.scalar(db.select(Order).where(Order.public_id == order["id"]))
    o.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    svc.release_expired()
    other = make_user("late@x.com")
    c2 = app.test_client()
    login(c2, "late@x.com")
    add(c2, rag)
    assert checkout(c2).status_code == 201                   # someone else takes the freed copy
    assert pay(buyer, order).get_json()["status"] == "refund_due"
    assert stock_of(rag) == 0


def test_cancel_releases_stock_once(buyer, rag):
    add(buyer, rag, 2)
    order = checkout(buyer).get_json()
    o = db.session.scalar(db.select(Order).where(Order.public_id == order["id"]))
    start = stock_of(rag)
    assert svc.cancel_order(o.id) is True
    assert svc.cancel_order(o.id) is False
    assert stock_of(rag) == start + 2


def test_paid_order_cannot_be_cancelled(buyer, rag):
    add(buyer, rag)
    order = checkout(buyer).get_json()
    pay(buyer, order)
    o = db.session.scalar(db.select(Order).where(Order.public_id == order["id"]))
    before = stock_of(rag)
    assert svc.cancel_order(o.id) is False
    assert stock_of(rag) == before


def test_inventory_ledger_reconciles_with_stock(buyer, rag):
    add(buyer, rag, 2)
    order = checkout(buyer).get_json()
    o = db.session.scalar(db.select(Order).where(Order.public_id == order["id"]))
    svc.cancel_order(o.id)
    add(buyer, rag, 1)
    checkout(buyer)
    db.session.expire_all()
    ledger = db.session.scalar(db.select(db.func.sum(InventoryLog.delta)).where(InventoryLog.product_id == rag.id))
    assert ledger == db.session.get(Product, rag.id).stock


def test_prices_are_snapshotted_on_the_order(buyer, rag):
    add(buyer, rag)
    order = checkout(buyer).get_json()
    db.session.get(Product, rag.id).price_paise = 1
    db.session.commit()
    again = buyer.get(f"/api/v1/orders/{order['id']}").get_json()
    assert again["items"][0]["unit_price_paise"] != 1
    assert again["total_paise"] == order["total_paise"]


def test_users_cannot_see_each_others_orders(app, buyer, rag):
    add(buyer, rag)
    order = checkout(buyer).get_json()
    make_user("snoop@x.com")
    other = app.test_client()
    login(other, "snoop@x.com")
    assert other.get(f"/api/v1/orders/{order['id']}").status_code == 404
    assert other.get(f"/orders/{order['id']}").status_code == 404


def test_webhook_marks_paid_and_rejects_bad_signature(app, buyer, rag):
    import hashlib, hmac, json
    add(buyer, rag)
    order = checkout(buyer).get_json()
    body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_web1", "order_id": order["payment"]["gateway_order_id"], "amount": order["total_paise"],
        "currency": "INR", "status": "captured"}}}}).encode()
    anon = app.test_client()
    assert anon.post("/webhooks/razorpay", data=body, headers={"X-Razorpay-Signature": "bad"}).status_code == 400
    sig = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
    assert anon.post("/webhooks/razorpay", data=body, headers={"X-Razorpay-Signature": sig}).status_code == 200
    assert buyer.get(f"/api/v1/orders/{order['id']}").get_json()["status"] == "paid"
