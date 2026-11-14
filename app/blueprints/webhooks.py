import json

from flask import Blueprint, abort, current_app, request

from ..extensions import db
from ..models import Order
from ..services import orders as order_svc
from ..services import notify, payments

bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


@bp.post("/razorpay")
def razorpay():
    """Backup path for payments the browser never reported (closed tab, lost connection)."""
    raw = request.get_data()
    if not payments.verify_webhook(raw, request.headers.get("X-Razorpay-Signature", "")):
        abort(400)
    try:
        event = json.loads(raw)
        if event.get("event") in ("payment.captured", "order.paid"):
            payload = event["payload"]
            entity = payload["payment"]["entity"]
            gateway_order_id, payment_id = entity["order_id"], entity["id"]
            if not (isinstance(gateway_order_id, str) and isinstance(payment_id, str)):
                abort(400)
            order = db.session.scalar(db.select(Order).where(Order.gateway_order_id == gateway_order_id))
            if order is not None:
                # A correctly signed event is still checked against the order: same order, captured, the exact
                # amount in paise, INR. Anything else is logged and left for a person to look at; the reply is
                # 200 so Razorpay does not keep retrying an event that will never match.
                if not payments.entity_matches_order(order, entity):
                    current_app.logger.warning("Webhook for order %s does not match the order (amount, currency "
                                               "or status); not marking it paid.", order.public_id)
                    return {"ok": False, "reason": "does not match the order"}
                if order_svc.mark_paid(order.id, payment_id) == "paid":
                    notify.after_payment(order.id)          # after the commit; never raises
    except (ValueError, KeyError, TypeError):
        abort(400)
    return {"ok": True}
