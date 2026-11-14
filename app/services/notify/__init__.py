"""Order messages: a cheerful thank-you note, the invoice, the setup guides and where to download, sent once per paid
order to the contact the buyer chose at checkout (email or WhatsApp), with their consent.

The flow, and the rules it keeps:
* Nothing is sent at checkout. queue_order_paid() runs only after mark_paid() has committed "paid".
* The outbox row is unique on (order, kind, channel), so the redirect, the webhook and the API confirming the same
  payment create one message, not three.
* Delivery runs after the payment transaction and every error is caught: a failed send can never fail or roll back
  a payment. A failure is stored with a short reason and retried by `flask send-messages` (the sweeper) with
  back-off, at most MESSAGE_MAX_ATTEMPTS times.
* A contact that asked to stop (do-not-contact list), a contact without consent, and a contact that has already had
  MESSAGES_PER_CONTACT_PER_DAY messages today get nothing.
* With no channel configured the rendered message stays in the outbox as "not_configured" for the admin to read.
* The order page always shows the invoice and the setup guides itself, so delivery never depends on email or WhatsApp.
* Raw contact values never reach a log line.
"""
import hashlib
import hmac
from datetime import timedelta

import contextlib

from flask import current_app, has_request_context, render_template, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError

from ...extensions import db
from ...models import ContactOptOut, Message, Order, utcnow
from .channels import NotConfigured, SendError, channel

KIND = "order_paid"


# ---- hashing, masking, tokens --------------------------------------------------------------------------------------
def contact_hash(value):
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, ("contact:" + (value or "").strip().lower()).encode(), hashlib.sha256).hexdigest()


def mask(channel_name, value):
    """j***@gmail.com and +91 ******5765: enough for the buyer to recognise, useless to anyone else."""
    value = value or ""
    if channel_name == "email" and "@" in value:
        local, domain = value.split("@", 1)
        return f"{local[:1]}***@{domain}"
    if channel_name == "whatsapp" and len(value) > 5:
        if value.startswith("+91"):
            return "+91 ******" + value[-4:]
        return "+" + "*" * (len(value) - 5) + value[-4:]
    return "***"


def _serializer(purpose):
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=f"order-message-{purpose}")


def make_token(purpose, order_or_message_id, public_id=""):
    return _serializer(purpose).dumps({"i": order_or_message_id, "p": public_id})


def read_token(purpose, token, max_days=None):
    """The payload of a valid, unexpired token for this purpose, or None (tampered, expired or another purpose)."""
    days = max_days if max_days is not None else current_app.config["MESSAGE_LINK_DAYS"]
    try:
        data = _serializer(purpose).loads(token, max_age=int(timedelta(days=days).total_seconds()))
    except (BadSignature, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("i"), int) else None


def order_from_token(purpose, token):
    data = read_token(purpose, token)
    if data is None:
        return None
    order = db.session.get(Order, data["i"])
    if order is None or order.public_id != data.get("p") or order.status not in ("paid", "refunded"):
        return None
    return order


def links(order, external=True):
    base = current_app.config["PUBLIC_BASE_URL"]
    return {
        "invoice": base + url_for("orderdocs.invoice_by_token", token=make_token("invoice", order.id, order.public_id)),
        "guide": base + url_for("orderdocs.guide_by_token", token=make_token("guide", order.id, order.public_id)),
        "order": base + url_for("account.order_detail", public_id=order.public_id),
    }


# ---- do not contact ------------------------------------------------------------------------------------------------
def opted_out(value_hash):
    return db.session.scalar(db.select(ContactOptOut.id).where(ContactOptOut.value_hash == value_hash)) is not None


def opt_out(value_hash):
    if not opted_out(value_hash):
        db.session.add(ContactOptOut(value_hash=value_hash))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()


# ---- rendering -----------------------------------------------------------------------------------------------------
def first_name(order):
    name = "".join(ch for ch in (order.billing_name or "") if ch not in "\r\n\x00").strip()
    return (name.split()[0] if name else "there")[:40]


def invoice_context(order):
    from ..guide import render_guide
    return {
        "order": order, "first_name": first_name(order),
        "seller": {k: current_app.config[f"SELLER_{k.upper()}"] for k in ("name", "address", "gstin")},
        "seller_email": current_app.config["CONTACT_EMAIL"],
        "guides": [(item.title, render_guide(item.product.setup_guide if item.product else ""),
                    (item.product.delivery_url if item.product else "")) for item in order.items],
    }


def _url_context():
    """url_for and render_template need a request; the sweeper (a CLI command) has none, so lend it one."""
    if has_request_context():
        return contextlib.nullcontext()
    return current_app.test_request_context("/", base_url=current_app.config["PUBLIC_BASE_URL"])


def render(order, msg):
    with _url_context():
        return _render(order, msg)


def _render(order, msg):
    ctx = invoice_context(order)
    ctx.update(links=links(order), stop_url=current_app.config["PUBLIC_BASE_URL"]
               + url_for("orderdocs.stop", token=make_token("stop", msg.id)), channel=msg.channel)
    subject = f"Your order {order.public_id}: invoice and setup guide"
    text = render_template("messages/order_paid.txt", **ctx)
    html = render_template("messages/order_paid.html", **ctx) if msg.channel == "email" else ""
    params = [ctx["first_name"], order.public_id, ctx["links"]["invoice"], ctx["links"]["guide"],
              ctx["links"]["order"], ctx["stop_url"]]
    return subject, text, html, params


# ---- queue and deliver ---------------------------------------------------------------------------------------------
def queue_order_paid(order_id):
    """Create the outbox row for a paid order if there is a consented contact. Idempotent. Returns the row or None."""
    order = db.session.get(Order, order_id)
    if (order is None or order.status != "paid" or order.contact_channel not in ("email", "whatsapp")
            or not order.contact_value or order.contact_consent_at is None):
        return None
    existing = db.session.scalar(db.select(Message).where(Message.order_id == order.id, Message.kind == KIND,
                                                          Message.channel == order.contact_channel))
    if existing is not None:
        return existing
    msg = Message(order_id=order.id, kind=KIND, channel=order.contact_channel, to_value=order.contact_value,
                  to_hash=contact_hash(order.contact_value), status="queued", attempts=0)
    db.session.add(msg)
    try:
        db.session.commit()
    except IntegrityError:                      # another worker queued it first
        db.session.rollback()
        return db.session.scalar(db.select(Message).where(Message.order_id == order.id, Message.kind == KIND,
                                                          Message.channel == order.contact_channel))
    return msg


def _sent_today(to_hash, exclude_id):
    since = utcnow() - timedelta(days=1)
    return db.session.scalar(db.select(db.func.count(Message.id)).where(
        Message.to_hash == to_hash, Message.status == "sent", Message.sent_at >= since, Message.id != exclude_id)) or 0


def _fail(msg, reason, final=False):
    msg.attempts += 1
    msg.status = "failed"
    msg.last_error = reason[:200]
    if final or msg.attempts >= current_app.config["MESSAGE_MAX_ATTEMPTS"]:
        msg.next_attempt_at = None
    else:
        msg.next_attempt_at = utcnow() + timedelta(minutes=2 ** msg.attempts)     # 2, 4, 8, 16 minutes


def deliver(msg):
    """Try to deliver one outbox row. Never raises. Returns the new status."""
    try:
        order = msg.order
        if not msg.to_value:
            _fail(msg, "the contact was removed", final=True)
        elif opted_out(msg.to_hash):
            _fail(msg, "the recipient asked not to be contacted", final=True)
        elif _sent_today(msg.to_hash, msg.id) >= current_app.config["MESSAGES_PER_CONTACT_PER_DAY"]:
            _fail(msg, "daily limit for this contact reached")
        else:
            subject, text, html, params = render(order, msg)
            msg.subject, msg.body_text, msg.body_html = subject[:200], text, html
            ch = channel(msg.channel)
            try:
                if msg.channel == "email":
                    ch.send(msg.to_value, subject, text, html)
                else:
                    ch.send(msg.to_value, params)
                msg.status, msg.sent_at, msg.last_error, msg.next_attempt_at = "sent", utcnow(), "", None
                msg.attempts += 1
            except NotConfigured:
                msg.status, msg.next_attempt_at = "not_configured", None
            except SendError as exc:
                _fail(msg, str(exc))
        db.session.commit()
    except Exception as exc:                    # pragma: no cover - last line of defence; payment must never break
        db.session.rollback()
        current_app.logger.warning("Order message %s could not be processed (%s).", msg.id, type(exc).__name__)
        return "failed"
    return msg.status


def after_payment(order_id):
    """Called after a payment is confirmed. Queues and tries to deliver; swallows every error."""
    try:
        msg = queue_order_paid(order_id)
        if msg is not None and msg.status == "queued":
            deliver(msg)
    except Exception as exc:                    # never let a message problem reach the payment response
        db.session.rollback()
        current_app.logger.warning("Order message for order id %s not queued (%s).", order_id, type(exc).__name__)


def sweep(limit=50):
    """Retry failed sends whose back-off has passed and deliver anything still queued. Returns how many were tried."""
    now = utcnow()
    rows = db.session.scalars(db.select(Message).where(
        db.or_(db.and_(Message.status == "failed", Message.next_attempt_at.is_not(None), Message.next_attempt_at <= now,
                       Message.attempts < current_app.config["MESSAGE_MAX_ATTEMPTS"]),
               Message.status == "queued")).order_by(Message.id).limit(limit)).all()
    for msg in rows:
        deliver(msg)
    return len(rows)


def buyer_status(msg):
    """The exact truth for the buyer's order page."""
    where = mask(msg.channel, msg.to_value) if msg.to_value else "your contact"
    if msg.status == "sent":
        return f"Sent to {where}"
    if msg.status == "queued":
        return "Queued"
    if msg.status == "not_configured":
        return ("Not sent: this store has not switched on email or WhatsApp messages yet. "
                "Your invoice and setup guide are on this page below.")
    if msg.next_attempt_at is not None:
        return "We could not send this yet and will try again. Your invoice and setup guide are on this page below."
    return "We could not send this, it is on your order page below"


def notify_owner_contact(contact):
    """Email the site owner about a new contact-form message, if SMTP and CONTACT_EMAIL are set. Never raises."""
    owner = current_app.config["CONTACT_EMAIL"]
    ch = channel("email")
    if not (owner and ch.configured):
        return False
    try:
        body = render_template("messages/contact_owner.txt", m=contact)
        ch.send(owner, f"New contact message: {contact.subject}", body)
        return True
    except (SendError, NotConfigured):
        current_app.logger.warning("Contact message %s: owner notification not sent.", contact.id)
        return False
