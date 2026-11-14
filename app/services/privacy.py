"""Removing a buyer's personal details from an order once it no longer needs them."""
from ..extensions import db
from ..models import Message, Order


def anonymise_order(order_id):
    """Blank the name, phone and contact on an order and the recipient and rendered text of its messages. The
    keyed hash of the contact stays on each message so a "stop messages" request and the daily limit still hold.
    Amounts, items and dates stay: they are the sales record."""
    order = db.session.get(Order, order_id)
    if order is None:
        return False
    order.billing_name = "Removed"
    order.phone = ""
    order.contact_value = ""
    for msg in db.session.scalars(db.select(Message).where(Message.order_id == order.id)):
        msg.to_value = ""
        msg.body_text = ""
        msg.body_html = ""
    db.session.commit()
    return True
