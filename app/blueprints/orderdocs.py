"""The invoice and setup-guide pages, and the "stop messages" link.

/i/<token> and /g/<token> are signed, order-scoped links that expire after MESSAGE_LINK_DAYS; they are what the
messages carry, so they open without signing in. They are read-only, never cached and never indexed. A signed-in
buyer (or an admin) also reaches the invoice at /orders/<public_id>/invoice.
"""
from flask import Blueprint, abort, flash, make_response, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Message, Order
from ..services import notify

bp = Blueprint("orderdocs", __name__)


def _private(html):
    resp = make_response(html)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@bp.get("/i/<token>")
def invoice_by_token(token):
    order = notify.order_from_token("invoice", token)
    if order is None:
        abort(404)
    return _private(render_template("invoice.html", **notify.invoice_context(order), via_link=True))


@bp.get("/g/<token>")
def guide_by_token(token):
    order = notify.order_from_token("guide", token)
    if order is None:
        abort(404)
    return _private(render_template("guide.html", **notify.invoice_context(order), via_link=True))


@bp.get("/orders/<public_id>/invoice")
@login_required
def invoice(public_id):
    order = db.session.scalar(db.select(Order).where(Order.public_id == public_id))
    if order is None or (order.user_id != current_user.id and not current_user.is_admin) \
            or order.status not in ("paid", "refunded"):
        abort(404)
    return _private(render_template("invoice.html", **notify.invoice_context(order), via_link=False))


def _message_from_stop(token):
    data = notify.read_token("stop", token, max_days=365)
    msg = db.session.get(Message, data["i"]) if data else None
    if msg is None:
        abort(404)
    return msg


@bp.get("/stop/<token>")
def stop(token):
    msg = _message_from_stop(token)
    return _private(render_template("stop.html", token=token, done=notify.opted_out(msg.to_hash)))


@bp.post("/stop/<token>")
def stop_confirm(token):
    msg = _message_from_stop(token)
    notify.opt_out(msg.to_hash)
    flash("Done. We will not send any more messages to that contact.", "success")
    return redirect(url_for("orderdocs.stop", token=token))
