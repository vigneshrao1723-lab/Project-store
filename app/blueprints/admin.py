from collections import defaultdict
from datetime import timedelta
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from ..extensions import db
from ..models import Category, ContactMessage, InventoryLog, Message, Order, ORDER_STATUSES, Product, utcnow
from ..services import notify
from ..services import orders as order_svc
from ..services.products import validate_product
from ..validation import MAX_NOTE, MAX_STOCK_DELTA, InputError, text, whole_number

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*a, **kw):
        if not current_user.is_admin:
            abort(403)
        return fn(*a, **kw)
    return wrapper


@bp.get("")
@admin_required
def dashboard():
    order_svc.release_expired()
    revenue, paid_count = db.session.execute(
        db.select(func.coalesce(func.sum(Order.total_paise), 0), func.count(Order.id))
        .where(Order.status == "paid")).one()
    counts = dict(db.session.execute(db.select(Order.status, func.count(Order.id)).group_by(Order.status)).all())
    units = db.session.scalar(db.select(func.coalesce(func.sum(Product.stock), 0)))

    today = utcnow().date()
    days = [today - timedelta(days=n) for n in range(13, -1, -1)]
    since = utcnow() - timedelta(days=14)
    per_day = defaultdict(int)
    for o in db.session.scalars(db.select(Order).where(Order.status == "paid", Order.paid_at >= since)):
        per_day[o.paid_at.date()] += o.total_paise
    series = [(d, per_day.get(d, 0)) for d in days]
    peak = max((v for _, v in series), default=0) or 1

    low = db.session.scalars(db.select(Product).where(Product.is_active.is_(True), Product.stock <= 5)
                             .order_by(Product.stock, Product.id)).all()
    recent = db.session.scalars(db.select(Order).order_by(Order.id.desc()).limit(8)).all()
    return render_template("admin/dashboard.html", revenue=revenue, paid_count=paid_count, counts=counts,
                           units=units, series=series, peak=peak, low=low, recent=recent)


@bp.get("/products")
@admin_required
def products():
    rows = db.session.scalars(db.select(Product).order_by(Product.id)).all()
    return render_template("admin/products.html", products=rows)


def _form_data():
    f = request.form
    return {k: f.get(k, "") for k in ("title", "slug", "category_id", "price_rupees", "stock", "tagline",
                                      "description", "tech", "includes", "delivery_url", "is_active", "featured",
                                      "setup_guide")}


@bp.route("/products/new", methods=["GET", "POST"])
@admin_required
def product_new():
    categories = db.session.scalars(db.select(Category).order_by(Category.name)).all()
    data, errors = {"is_active": "on", "stock": "0"}, {}
    if request.method == "POST":
        data = _form_data()
        clean, errors = validate_product(data)
        if not errors:
            p = Product(**clean)
            db.session.add(p)
            db.session.flush()
            if p.stock:
                db.session.add(InventoryLog(product_id=p.id, delta=p.stock, reason="initial"))
            db.session.commit()
            flash(f"{p.title} created.", "success")
            return redirect(url_for("admin.products"))
    return render_template("admin/product_form.html", p=None, data=data, errors=errors, categories=categories)


@bp.route("/products/<int:product_id>", methods=["GET", "POST"])
@admin_required
def product_edit(product_id):
    p = db.session.get(Product, product_id) or abort(404)
    categories = db.session.scalars(db.select(Category).order_by(Category.name)).all()
    errors = {}
    data = {"title": p.title, "slug": p.slug, "category_id": str(p.category_id),
            "price_rupees": f"{p.price_paise / 100:g}", "tagline": p.tagline, "description": p.description,
            "tech": p.tech, "includes": p.includes, "delivery_url": p.delivery_url, "setup_guide": p.setup_guide or "",
            "is_active": "on" if p.is_active else "", "featured": "on" if p.featured else ""}
    if request.method == "POST":
        data = _form_data()
        clean, errors = validate_product(data, existing=p)
        if not errors:
            if clean.get("setup_guide", p.setup_guide or "") != (p.setup_guide or ""):
                p.guide_edited = True          # `flask seed` will never overwrite a guide an admin has edited
            for k, v in clean.items():
                setattr(p, k, v)
            db.session.commit()
            flash(f"{p.title} saved.", "success")
            return redirect(url_for("admin.products"))
    log = db.session.scalars(db.select(InventoryLog).where(InventoryLog.product_id == p.id)
                             .order_by(InventoryLog.id.desc()).limit(12)).all()
    return render_template("admin/product_form.html", p=p, data=data, errors=errors,
                           categories=categories, log=log)


@bp.post("/products/<int:product_id>/stock")
@admin_required
def product_stock(product_id):
    try:
        delta = whole_number(request.form.get("delta", ""), -MAX_STOCK_DELTA, MAX_STOCK_DELTA, "The change")
        p = order_svc.adjust_stock(product_id, delta, text(request.form.get("note", ""), MAX_NOTE, "The note"))
        flash(f"{p.title}: stock is now {p.stock}.", "success")
    except InputError:
        flash(f"Enter a whole number from -{MAX_STOCK_DELTA:,} to {MAX_STOCK_DELTA:,} (for example 5 or -2), "
              f"and a note of at most {MAX_NOTE} characters.", "error")
    except order_svc.CheckoutError as exc:
        flash(exc.messages[0], "error")
    return redirect(request.referrer or url_for("admin.products"))


@bp.get("/orders")
@admin_required
def orders():
    order_svc.release_expired()
    status = request.args.get("status", "")
    q = db.select(Order).order_by(Order.id.desc())
    if status in ORDER_STATUSES:
        q = q.where(Order.status == status)
    counts = dict(db.session.execute(db.select(Order.status, func.count(Order.id)).group_by(Order.status)).all())
    return render_template("admin/orders.html", orders=db.session.scalars(q.limit(200)).all(),
                           active_status=status, counts=counts, statuses=ORDER_STATUSES)


@bp.get("/orders/<public_id>")
@admin_required
def order_detail(public_id):
    o = db.session.scalar(db.select(Order).where(Order.public_id == public_id)) or abort(404)
    return render_template("admin/order_detail.html", order=o)


@bp.post("/orders/<public_id>/cancel")
@admin_required
def order_cancel(public_id):
    o = db.session.scalar(db.select(Order).where(Order.public_id == public_id)) or abort(404)
    flash("Order cancelled and stock released." if order_svc.cancel_order(o.id)
          else "Only unpaid orders can be cancelled.", "info")
    return redirect(url_for("admin.order_detail", public_id=public_id))


@bp.post("/orders/<public_id>/refunded")
@admin_required
def order_refunded(public_id):
    o = db.session.scalar(db.select(Order).where(Order.public_id == public_id)) or abort(404)
    flash("Marked as refunded." if order_svc.mark_refunded(o.id) else "That order isn't waiting for a refund.", "info")
    return redirect(url_for("admin.order_detail", public_id=public_id))


@bp.get("/messages")
@admin_required
def messages():
    """Contact-form messages and the order-message outbox, newest first. Rendered as plain, autoescaped text."""
    contacts = db.session.scalars(db.select(ContactMessage).order_by(ContactMessage.id.desc()).limit(200)).all()
    outbox = db.session.scalars(db.select(Message).order_by(Message.id.desc()).limit(200)).all()
    return render_template("admin/messages.html", contacts=contacts, outbox=outbox, mask=notify.mask)


@bp.post("/messages/<int:message_id>/handled")
@admin_required
def message_handled(message_id):
    m = db.session.get(ContactMessage, message_id) or abort(404)
    m.handled_at = None if m.handled_at else utcnow()
    db.session.commit()
    flash("Marked as handled." if m.handled_at else "Marked as not handled.", "info")
    return redirect(url_for("admin.messages"))


@bp.get("/outbox/<int:message_id>")
@admin_required
def outbox_message(message_id):
    m = db.session.get(Message, message_id) or abort(404)
    if not m.body_text and m.status == "queued":
        notify.deliver(m)                       # renders it (and sends it if a channel is configured)
    return render_template("admin/outbox_message.html", m=m, mask=notify.mask)


@bp.post("/outbox/<int:message_id>/sent")
@admin_required
def outbox_sent(message_id):
    """The owner sent this message by hand (copied it into email or WhatsApp)."""
    m = db.session.get(Message, message_id) or abort(404)
    if m.status in ("not_configured", "failed", "queued"):
        m.status, m.sent_at, m.next_attempt_at = "sent", utcnow(), None
        m.last_error = "sent by hand"
        db.session.commit()
        flash("Marked as sent by hand.", "info")
    return redirect(url_for("admin.outbox_message", message_id=m.id))

