from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Order
from ..services import cart as cart_svc
from ..services import orders as order_svc
from ..services import payments

bp = Blueprint("checkout", __name__, url_prefix="/checkout")


def own_order_or_404(public_id):
    order_svc.release_expired()
    order = db.session.scalar(db.select(Order).where(Order.public_id == public_id))
    if order is None or (order.user_id != current_user.id and not current_user.is_admin):
        abort(404)
    return order


def confirm_payment(order, gateway_order_id, payment_id, signature):
    """Shared by the Razorpay redirect and the test gateway.

    Returns the order's new status ("paid", "refund_due"), or None if the payment didn't verify.
    """
    if gateway_order_id != order.gateway_order_id or not payments.verify_payment(
            gateway_order_id, payment_id, signature):
        return None
    return order_svc.mark_paid(order.id, payment_id)


def _announce(status):
    if status == "paid":
        flash("Payment received. Your download link is below.", "success")
    elif status == "refund_due":
        flash("Your payment arrived after the hold expired and the project sold out meanwhile. "
              "It will be refunded in full.", "error")


@bp.route("", methods=["GET", "POST"])
@login_required
def start():
    cart = cart_svc.contents(current_user)
    if request.method == "GET":
        if not cart["lines"]:
            flash("Your cart is empty.", "info")
            return redirect(url_for("cart.view"))
        return render_template("checkout.html", cart=cart, name=current_user.name, phone="")

    name = request.form.get("billing_name", "").strip()
    phone = request.form.get("phone", "").strip()
    if not name:
        flash("Enter the name for this order.", "error")
        return render_template("checkout.html", cart=cart, name=name, phone=phone), 400

    try:
        order = order_svc.create_order_from_cart(current_user, name, phone)
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
