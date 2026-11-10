"""Order lifecycle: reserve stock, confirm payment, release stock.

Every function here owns its transaction. Stock rows are always locked in
ascending id order (SELECT ... FOR UPDATE on MySQL), so two checkouts that
touch the same products can never deadlock, and stock can never go negative.
"""
from flask import current_app
from sqlalchemy import select

from ..extensions import db
from ..models import (
    CartItem,
    InventoryLog,
    Order,
    OrderItem,
    Product,
    utcnow,
)


class CheckoutError(Exception):
    def __init__(self, messages):
        if isinstance(messages, str):
            messages = [messages]
        self.messages = messages
        super().__init__("; ".join(messages))


def _lock_products(product_ids):
    stmt = (
        select(Product)
        .where(Product.id.in_(sorted(set(product_ids))))
        .order_by(Product.id)
        .with_for_update()
    )
    return {p.id: p for p in db.session.scalars(stmt)}


def _log(product, delta, reason, order=None, note=""):
    db.session.add(
        InventoryLog(product_id=product.id, order_id=order.id if order else None,
                     delta=delta, reason=reason, note=note)
    )


def create_order_from_cart(user, billing_name, phone=""):
    """Turn the user's cart into a pending order and hold the stock. All or nothing."""
    release_expired()
    try:
        items = db.session.scalars(
            select(CartItem).where(CartItem.user_id == user.id).order_by(CartItem.product_id)
        ).all()
        if not items:
            raise CheckoutError("Your cart is empty.")

        products = _lock_products([i.product_id for i in items])
        problems = []
        for item in items:
            p = products.get(item.product_id)
            if p is None or not p.is_active:
                problems.append(f"{p.title if p else 'An item'} is no longer available.")
            elif p.stock < item.qty:
                left = "is sold out" if p.stock == 0 else f"has only {p.stock} left"
                problems.append(f"{p.title} {left}. Lower the quantity or remove it.")
        if problems:
            raise CheckoutError(problems)

        order = Order(
            user_id=user.id,
            billing_name=billing_name.strip(),
            phone=phone.strip(),
            total_paise=sum(products[i.product_id].price_paise * i.qty for i in items),
            expires_at=Order.new_expiry(current_app.config["RESERVATION_MINUTES"]),
        )
        db.session.add(order)
        db.session.flush()

        for item in items:
            p = products[item.product_id]
            p.stock -= item.qty
            db.session.add(OrderItem(order_id=order.id, product_id=p.id, title=p.title,
                                     unit_price_paise=p.price_paise, qty=item.qty))
            _log(p, -item.qty, "reserve", order)
            db.session.delete(item)

        db.session.commit()
        return order
    except Exception:
        db.session.rollback()
        raise


def _restock(order, reason):
    products = _lock_products([i.product_id for i in order.items])
    for item in order.items:
        p = products[item.product_id]
        p.stock += item.qty
        _log(p, item.qty, reason, order)


def cancel_order(order_id, new_status="cancelled"):
    """Release the stock held by a pending order. Safe to call twice."""
    try:
        order = db.session.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if order is None or order.status != "pending":
            db.session.rollback()
            return False
        _restock(order, "release")
        order.status = new_status
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        raise


def release_expired():
    """Free stock held by unpaid orders past their window. Returns how many."""
    ids = db.session.scalars(
        select(Order.id).where(Order.status == "pending", Order.expires_at < utcnow())
    ).all()
    return sum(1 for oid in ids if cancel_order(oid, "expired"))


def mark_paid(order_id, payment_id):
    """Confirm a payment. Idempotent: the redirect and the webhook may both call it.

    Returns the order's resulting status.
    """
    try:
        order = db.session.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if order is None:
            db.session.rollback()
            return None
        if order.status in ("paid", "refund_due", "refunded"):
            db.session.rollback()
            return order.status

        if order.status == "pending":
            order.status = "paid"
        else:
            # Payment landed after the hold expired or the order was cancelled.
            # Re-take the stock if it is still there, otherwise flag for refund.
            products = _lock_products([i.product_id for i in order.items])
            if all(products[i.product_id].stock >= i.qty and products[i.product_id].is_active
                   for i in order.items):
                for item in order.items:
                    p = products[item.product_id]
                    p.stock -= item.qty
                    _log(p, -item.qty, "reserve", order, "late payment")
                order.status = "paid"
            else:
                order.status = "refund_due"

        order.gateway_payment_id = payment_id
        order.paid_at = utcnow()
        db.session.commit()
        return order.status
    except Exception:
        db.session.rollback()
        raise


def mark_refunded(order_id):
    order = db.session.get(Order, order_id)
    if order and order.status == "refund_due":
        order.status = "refunded"
        db.session.commit()
        return True
    return False


def adjust_stock(product_id, delta, note=""):
    try:
        product = _lock_products([product_id]).get(product_id)
        if product is None:
            raise CheckoutError("Product not found.")
        if product.stock + delta < 0:
            raise CheckoutError("Stock cannot go below zero.")
        product.stock += delta
        _log(product, delta, "adjust", note=note[:190])
        db.session.commit()
        return product
    except Exception:
        db.session.rollback()
        raise
