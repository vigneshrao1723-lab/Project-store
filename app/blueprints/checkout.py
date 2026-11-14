from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Order
from ..services import cart as cart_svc
from ..services import orders as order_svc
from ..services import notify, payments, rate_limit
from ..validation import MAX_EMAIL, MAX_NAME, MAX_PHONE, InputError, normalise_whatsapp, valid_email

bp = Blueprint("checkout", __name__, url_prefix="/checkout")


def own_order_or_404(public_id):
    """The signed-in user's own order. These routes pay, verify and cancel, so an admin gets no exception here:
    admins read any order from the admin pages and cancel from there, but never pay for a customer."""
    order_svc.release_expired()
    order = db.session.scalar(db.select(Order).where(Order.public_id == public_id, Order.user_id == current_user.id))
    if order is None:
        abort(404)
    return order


def confirm_payment(order, gateway_order_id, payment_id, signature):
    """Shared by the Razorpay redirect and the test gateway.

    Returns the order's new status ("paid", "refund_due"), or None if the payment didn't verify.
    """
    if (not order.gateway_order_id or gateway_order_id != order.gateway_order_id
            or not payments.verify_payment(gateway_order_id, payment_id, signature)
            or not payments.payment_matches_order(order, payment_id)):
        return None
    status = order_svc.mark_paid(order.id, payment_id)
    if status == "paid":
        notify.after_payment(order.id)          # outside the payment transaction; it never raises
    return status


def _announce(status):
    if status == "paid":
        flash("Payment received. Your download link is below.", "success")
    elif status == "refund_due":
        flash("Your payment arrived after the hold expired and the project sold out meanwhile. "
              "It will be refunded in full.", "error")


def _to_unpaid_order(order):
    flash("You already have an unpaid order. Finish paying for it, or cancel it, before checking out again.", "info")
    return redirect(url_for("checkout.pay", public_id=order.public_id))


@bp.route("", methods=["GET", "POST"])
@login_required
def start():
    cart = cart_svc.contents(current_user)
    if request.method == "GET":
        unpaid = order_svc.open_order_for(current_user)
        if unpaid is not None:
            return _to_unpaid_order(unpaid)
        if not cart["lines"]:
            flash("Your cart is empty.", "info")
            return redirect(url_for("cart.view"))
        return render_template("checkout.html", cart=cart, name=current_user.name, phone="",
                               contact=_contact_defaults(), errors={})

    rate_limit.enforce("checkout")
    name = request.form.get("billing_name", "").strip()
    phone = request.form.get("phone", "").strip()
    contact, errors = _read_contact(request.form)
    problem = None
    if not name:
        problem = "Enter the name for this order."
    elif len(name) > MAX_NAME:
        problem = f"Use at most {MAX_NAME} characters for the name."
    elif len(phone) > MAX_PHONE:
        problem = f"Use at most {MAX_PHONE} characters for the phone number."
    elif errors:
        problem = next(iter(errors.values()))
    if problem:
        flash(problem, "error")
        return render_template("checkout.html", cart=cart, name=name[:MAX_NAME], phone=phone[:MAX_PHONE],
                               contact=contact["form"], errors=errors), 400
    if contact["channel"] == "whatsapp" and not phone:
        phone = contact["value"]                 # the payment form can prefill it; the free phone field is gone
    if contact["channel"]:                       # messages were asked for: limit how often, per address and account
        rate_limit.enforce("notify_ip", rate_limit.ip_key())
        rate_limit.enforce("notify_user", f"user:{current_user.id}")

    try:
        order = order_svc.create_order_from_cart(current_user, name, phone,
                                                 contact=(contact["channel"], contact["value"]) if contact["channel"] else None)
    except order_svc.PendingOrderExists as exc:
        return _to_unpaid_order(exc.order)
    except order_svc.CheckoutError as exc:
        for m in exc.messages:
            flash(m, "error")
        return redirect(url_for("cart.view"))

    try:
        order.gateway_order_id = payments.create_gateway_order(order)
        db.session.commit()
    except payments.GatewayError as exc:
        order_svc.cancel_order(order.id, "failed")
        _refill_cart(order)
        flash(str(exc), "error")
        return redirect(url_for("cart.view"))
    return redirect(url_for("checkout.pay", public_id=order.public_id))


def _contact_defaults():
    return {"channel": "email", "email": current_user.email, "whatsapp": "", "consent": False}


def _read_contact(form):
    """The checkout's "send my invoice and setup guide" choice. A form without the choice at all (an older client)
    asks for no messages. With the choice, the contact must be valid and the consent box ticked."""
    if "contact_channel" not in form:
        return {"channel": "", "value": "", "form": _contact_defaults()}, {}
    channel = form.get("contact_channel", "")
    shown = {"channel": channel if channel in ("email", "whatsapp") else "email",
             "email": form.get("contact_email", "").strip()[:MAX_EMAIL],
             "whatsapp": form.get("contact_whatsapp", "").strip()[:24], "consent": bool(form.get("contact_consent"))}
    errors, value = {}, ""
    if channel == "email":
        value = shown["email"].lower()
        if not valid_email(value):
            errors["contact_email"] = "Enter a valid email address for your invoice."
    elif channel == "whatsapp":
        try:
            value = normalise_whatsapp(shown["whatsapp"])
        except InputError as exc:
            errors["contact_whatsapp"] = exc.message
    else:
        errors["contact_channel"] = "Choose email or WhatsApp."
    if not shown["consent"]:
        errors["contact_consent"] = "Tick the box so we can send your invoice and setup guide."
    return {"channel": channel if not errors else "", "value": value, "form": shown}, errors


def _refill_cart(order):
    for item in order.items:
        try:
            cart_svc.set_qty(order.user, item.product_id, item.qty, add=True)
        except cart_svc.CartError:
            pass


@bp.get("/pay/<public_id>")
@login_required
def pay(public_id):
    order = own_order_or_404(public_id)
    if not order.is_open:
        return redirect(url_for("account.order_detail", public_id=order.public_id))
    return render_template("pay.html", order=order, mode=payments.mode(),
                           key_id=current_app.config["RAZORPAY_KEY_ID"])


@bp.post("/verify")
@login_required
def verify():
    rate_limit.enforce("verify")
    order = own_order_or_404(request.form.get("public_id", ""))
    status = confirm_payment(order, request.form.get("razorpay_order_id"),
                             request.form.get("razorpay_payment_id"), request.form.get("razorpay_signature"))
    if status:
        _announce(status)
        return redirect(url_for("account.order_detail", public_id=order.public_id))
    flash("We couldn't verify that payment. If money left your account it will be matched "
          "automatically; otherwise try again.", "error")
    return redirect(url_for("checkout.pay", public_id=order.public_id))


@bp.post("/test-pay/<public_id>")
@login_required
def test_pay(public_id):
    if payments.mode() != "test":
        abort(404)
    order = own_order_or_404(public_id)
    if not order.is_open:
        return redirect(url_for("account.order_detail", public_id=order.public_id))
    if request.form.get("outcome") == "fail":
        flash("The test payment was declined. Your items are still held. Try again or cancel.", "error")
        return redirect(url_for("checkout.pay", public_id=order.public_id))
    payment_id = "pay_test_" + order.public_id.lower()
    sig = payments.sign(order.gateway_order_id, payment_id)
    _announce(confirm_payment(order, order.gateway_order_id, payment_id, sig))
    return redirect(url_for("account.order_detail", public_id=order.public_id))


@bp.post("/cancel/<public_id>")
@login_required
def cancel(public_id):
    order = own_order_or_404(public_id)
    if order.user_id == current_user.id and order_svc.cancel_order(order.id):
        _refill_cart(order)
        flash("Order cancelled. Your items are back in the cart.", "info")
        return redirect(url_for("cart.view"))
    return redirect(url_for("account.order_detail", public_id=order.public_id))
