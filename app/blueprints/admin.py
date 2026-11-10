from collections import defaultdict
from datetime import timedelta
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from ..extensions import db
from ..models import Category, InventoryLog, Order, ORDER_STATUSES, Product, utcnow
from ..services import orders as order_svc
from ..services.products import validate_product

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
                                      "description", "tech", "includes", "delivery_url", "is_active", "featured")}


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
            "tech": p.tech, "includes": p.includes, "delivery_url": p.delivery_url,
            "is_active": "on" if p.is_active else "", "featured": "on" if p.featured else ""}
    if request.method == "POST":
        data = _form_data()
        clean, errors = validate_product(data, existing=p)
        if not errors:
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
        delta = int(request.form.get("delta", ""))
        p = order_svc.adjust_stock(product_id, delta, request.form.get("note", ""))
        flash(f"{p.title}: stock is now {p.stock}.", "success")
    except ValueError:
        flash("Enter a whole number to add or remove (for example 5 or -2).", "error")
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
