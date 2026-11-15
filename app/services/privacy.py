"""Removing a buyer's personal details from an order once it no longer needs them."""
import secrets

from ..extensions import db
from ..models import CartItem, ContactMessage, LoginThrottle, Message, Order, User, new_session_token


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


def anonymise_account(user_id):
    """An erasure request for a whole account (DPDP Act, 2023): every order of the account is anonymised as above, the
    cart is emptied, contact-form messages and failed sign-in records under the account's email are deleted, and the
    account's name, email and password are replaced so it can no longer sign in or be linked to the person. A new
    session token signs it out everywhere. The orders stay as sales records (amounts, projects, dates)."""
    user = db.session.get(User, user_id)
    if user is None:
        return False
    email = user.email
    for order_id in db.session.scalars(db.select(Order.id).where(Order.user_id == user.id)).all():
        anonymise_order(order_id)
    user = db.session.get(User, user_id)
    db.session.execute(db.delete(CartItem).where(CartItem.user_id == user.id))
    db.session.execute(db.delete(ContactMessage).where(ContactMessage.email == email))
    db.session.execute(db.delete(LoginThrottle).where(LoginThrottle.email == email))
    user.name = "Removed"
    user.email = f"removed-{user.id}@deleted.invalid"
    user.role = "customer"
    user.set_password(secrets.token_urlsafe(32))
    user.session_token = new_session_token()
    db.session.commit()
    return True
