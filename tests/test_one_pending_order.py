"""A user has at most one unpaid (pending) order. A second checkout sends them to the one they already have."""
from datetime import timedelta

import pytest

from app.extensions import db
from app.models import CartItem, InventoryLog, Order, Product, User, utcnow
from app.services import orders as svc


def fill_cart(client, *products):
    for p in products:
        assert client.post("/api/v1/cart/items", json={"product_id": p.id, "qty": 1}).status_code == 201


def pending_orders():
    db.session.expire_all()
    return db.session.scalars(db.select(Order).where(Order.status == "pending")).all()


def stock_of(product):
    db.session.expire_all()
    return db.session.get(Product, product.id).stock


# ---- service ------------------------------------------------------------------------------------------------

def test_second_checkout_raises_with_the_existing_order_and_reserves_nothing(app, user, rag, soc):
    soc.stock = 4
    db.session.add_all([CartItem(user_id=user.id, product_id=rag.id, qty=1)])
    db.session.commit()
    first = svc.create_order_from_cart(user, "Buyer")
    db.session.add(CartItem(user_id=user.id, product_id=soc.id, qty=1))
    db.session.commit()
    rag_stock, soc_stock = stock_of(rag), stock_of(soc)

    with pytest.raises(svc.PendingOrderExists) as exc:
        svc.create_order_from_cart(user, "Buyer")
    assert exc.value.order.id == first.id
    assert (stock_of(rag), stock_of(soc)) == (rag_stock, soc_stock)
    assert db.session.scalar(db.select(db.func.count(Order.id))) == 1
    assert db.session.scalar(db.select(db.func.count(CartItem.id)).where(CartItem.user_id == user.id)) == 1
    assert db.session.scalar(db.select(db.func.count(InventoryLog.id)).where(InventoryLog.reason == "reserve")) == 1


def test_the_error_is_still_a_checkout_error_with_a_plain_message(app, user, rag):
    db.session.add(CartItem(user_id=user.id, product_id=rag.id, qty=1))
    db.session.commit()
    svc.create_order_from_cart(user, "Buyer")
    db.session.add(CartItem(user_id=user.id, product_id=rag.id, qty=1))
    db.session.commit()
    with pytest.raises(svc.CheckoutError, match="unpaid order"):
        svc.create_order_from_cart(user, "Buyer")


@pytest.mark.parametrize("how", ["cancelled", "paid", "expired"])
def test_a_new_checkout_is_allowed_once_the_first_order_is_no_longer_pending(app, user, rag, how):
    db.session.add(CartItem(user_id=user.id, product_id=rag.id, qty=1))
    db.session.commit()
    first = svc.create_order_from_cart(user, "Buyer")
    if how == "cancelled":
        svc.cancel_order(first.id)
    elif how == "paid":
        svc.mark_paid(first.id, "pay_1")
    else:
        first.expires_at = utcnow() - timedelta(minutes=1)
        db.session.commit()
    db.session.add(CartItem(user_id=user.id, product_id=rag.id, qty=1))
    db.session.commit()
    second = svc.create_order_from_cart(user, "Buyer")
    assert second.id != first.id and second.status == "pending"


def test_other_users_are_not_blocked(app, user, rag):
    other = User(name="Other", email="other@example.com")
    other.set_password("password123")
    db.session.add(other)
    db.session.commit()
    for u in (user, other):
        db.session.add(CartItem(user_id=u.id, product_id=rag.id, qty=1))
    db.session.commit()
    svc.create_order_from_cart(user, "A")
    svc.create_order_from_cart(other, "B")
    assert len(pending_orders()) == 2


def test_open_order_for_finds_only_a_live_pending_order(app, user, rag):
    assert svc.open_order_for(user) is None
    db.session.add(CartItem(user_id=user.id, product_id=rag.id, qty=1))
    db.session.commit()
    order = svc.create_order_from_cart(user, "Buyer")
    assert svc.open_order_for(user).id == order.id
    order.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert svc.open_order_for(user) is None            # the hold ran out, so it no longer blocks anything


# ---- web ----------------------------------------------------------------------------------------------------

def test_the_checkout_form_redirects_to_the_pay_page_of_the_unpaid_order(buyer, rag, soc):
    soc.stock = 4
    db.session.commit()
    fill_cart(buyer, rag)
    first = buyer.post("/checkout", data={"billing_name": "Asha"})
    first_url = first.headers["Location"]
    assert "/checkout/pay/" in first_url
    fill_cart(buyer, soc)
    for method in ("get", "post"):
        r = getattr(buyer, method)("/checkout", **({"data": {"billing_name": "Asha"}} if method == "post" else {}))
        assert r.status_code == 302 and r.headers["Location"] == first_url, method
    page = buyer.get(first_url).get_data(as_text=True)
    assert "unpaid order" in page                         # the flashed explanation, shown on the pay page
    assert len(pending_orders()) == 1 and buyer.get("/api/v1/cart").get_json()["count"] == 1


def test_an_empty_cart_with_an_unpaid_order_still_goes_to_that_order(buyer, rag):
    fill_cart(buyer, rag)
    url = buyer.post("/checkout", data={"billing_name": "Asha"}).headers["Location"]
    r = buyer.get("/checkout")
    assert r.status_code == 302 and r.headers["Location"] == url


def test_after_cancelling_the_user_can_check_out_again(buyer, rag):
    fill_cart(buyer, rag)
    url = buyer.post("/checkout", data={"billing_name": "Asha"}).headers["Location"]
    public_id = url.rsplit("/", 1)[1]
    buyer.post(f"/checkout/cancel/{public_id}")            # puts the items back in the cart
    again = buyer.post("/checkout", data={"billing_name": "Asha"})
    assert again.status_code == 302 and "/checkout/pay/" in again.headers["Location"]
    assert again.headers["Location"] != url


# ---- API ----------------------------------------------------------------------------------------------------

def test_api_checkout_answers_409_with_the_existing_order_and_how_to_pay_it(buyer, rag, soc):
    soc.stock = 4
    db.session.commit()
    fill_cart(buyer, rag)
    first = buyer.post("/api/v1/checkout", json={}).get_json()
    fill_cart(buyer, soc)
    stock_before = stock_of(soc)
    r = buyer.post("/api/v1/checkout", json={})
    body = r.get_json()
    assert r.status_code == 409 and "unpaid order" in body["error"]
    assert body["order"]["id"] == first["id"] and body["order"]["status"] == "pending"
    assert body["order"]["payment"]["gateway_order_id"] == first["payment"]["gateway_order_id"]
    assert body["order"]["payment"]["amount_paise"] == first["total_paise"]
    assert stock_of(soc) == stock_before and len(pending_orders()) == 1


def test_api_checkout_with_a_pending_order_and_an_empty_cart_reports_the_order_too(buyer, rag):
    fill_cart(buyer, rag)
    first = buyer.post("/api/v1/checkout", json={}).get_json()
    r = buyer.post("/api/v1/checkout", json={})
    assert r.status_code == 409 and r.get_json()["order"]["id"] == first["id"]
