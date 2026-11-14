"""JSON REST API, v1. Authenticates with the same session cookie as the site.

Writes need the X-CSRFToken header (the storefront JS sends it). Errors are
always {"error": "...", "fields": {...}} with a matching HTTP status.
"""
from functools import wraps

from flask import Blueprint, jsonify, request
from flask_login import current_user
from sqlalchemy import func

from ..extensions import db
from ..models import Order, ORDER_STATUSES, Product, utcnow
from ..services import cart as cart_svc
from ..services import orders as order_svc
from ..services import notify, payments, rate_limit
from ..services.catalog import search_products
from ..services.products import validate_product
from ..validation import MAX_NAME, MAX_NOTE, MAX_PHONE, MAX_STOCK_DELTA, InputError, json_body, text, whole_number

bp = Blueprint("api", __name__, url_prefix="/api/v1")


def error(message, status=400, fields=None):
    body = {"error": message}
    if fields:
        body["fields"] = fields
    return jsonify(body), status


def login_required_json(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user.is_authenticated:
            return error("Sign in to continue.", 401)
        return fn(*a, **kw)
    return wrapper


def admin_required_json(fn):
    @wraps(fn)
    @login_required_json
    def wrapper(*a, **kw):
        if not current_user.is_admin:
            return error("Admins only.", 403)
        return fn(*a, **kw)
    return wrapper


def product_json(p, admin=False):
    data = {
        "id": p.id, "code": p.code, "slug": p.slug, "title": p.title, "tagline": p.tagline,
        "category": {"id": p.category.id, "name": p.category.name, "slug": p.category.slug},
        "tech": p.tech_list, "price_paise": p.price_paise, "in_stock": p.stock > 0,
        "stock": p.stock, "featured": p.featured,
    }
    if admin:
        data.update(is_active=p.is_active, delivery_url=p.delivery_url)
    return data


def payment_json(order):
    """What a client needs to pay an order: the provider and the gateway order, the amount and the currency."""
    return {"provider": payments.mode(), "gateway_order_id": order.gateway_order_id,
            "amount_paise": order.total_paise, "currency": "INR"}


def order_json(o, with_delivery=True):
    return {
        "id": o.public_id, "status": o.status, "total_paise": o.total_paise,
        "billing_name": o.billing_name, "created_at": o.created_at.isoformat() + "Z",
        "expires_at": o.expires_at.isoformat() + "Z" if o.is_open else None,
        "paid_at": o.paid_at.isoformat() + "Z" if o.paid_at else None,
        "items": [{"product_id": i.product_id, "title": i.title, "qty": i.qty,
                   "unit_price_paise": i.unit_price_paise,
                   "download_url": i.product.delivery_url if (with_delivery and o.is_paid) else None}
                  for i in o.items],
    }


# ---- catalogue -------------------------------------------------------------

@bp.get("/products")
def products():
    res = search_products(request.args.get("q", ""), request.args.get("category") or None,
                          request.args.get("sort", "new"), request.args.get("page", 1))
    return jsonify({"items": [product_json(p) for p in res.items], "page": res.page,
                    "pages": res.pages, "total": res.total})


@bp.get("/products/<slug>")
def product(slug):
    p = db.session.scalar(db.select(Product).where(Product.slug == slug, Product.is_active.is_(True)))
    if p is None:
        return error("Project not found.", 404)
    data = product_json(p)
    data.update(description=p.description, includes=p.includes_list)
    return jsonify(data)


# ---- cart ------------------------------------------------------------------

@bp.get("/cart")
@login_required_json
def cart():
    return jsonify(cart_svc.contents(current_user))


@bp.post("/cart/items")
@login_required_json
def cart_add():
    body = json_body()
    try:
        cart_svc.set_qty(current_user, body.get("product_id"), body.get("qty", 1), add=True)
    except cart_svc.CartError as exc:
        return error(exc.message, exc.status)
    return jsonify(cart_svc.contents(current_user)), 201


@bp.patch("/cart/items/<int:product_id>")
@login_required_json
def cart_update(product_id):
    body = json_body()
    try:
        cart_svc.set_qty(current_user, product_id, body.get("qty"))
    except cart_svc.CartError as exc:
        return error(exc.message, exc.status)
    return jsonify(cart_svc.contents(current_user))


@bp.delete("/cart/items/<int:product_id>")
@login_required_json
def cart_remove(product_id):
    cart_svc.remove(current_user, product_id)
    return jsonify(cart_svc.contents(current_user))


# ---- checkout and orders ---------------------------------------------------

@bp.post("/checkout")
@login_required_json
def checkout():
    """Hold stock and create a pending order. The client then pays and calls /checkout/verify."""
    rate_limit.enforce("checkout")
    body = json_body()
    name = text(body.get("billing_name"), MAX_NAME, "The billing name") or current_user.name
    phone = text(body.get("phone"), MAX_PHONE, "The phone number")
    try:
        order = order_svc.create_order_from_cart(current_user, name, phone)
    except order_svc.PendingOrderExists as exc:
        body = {"error": exc.messages[0], "order": {**order_json(exc.order), "payment": payment_json(exc.order)}}
        return jsonify(body), 409
    except order_svc.CheckoutError as exc:
        return error(exc.messages[0], 409, {"items": exc.messages})
    try:
        order.gateway_order_id = payments.create_gateway_order(order)
        db.session.commit()
    except payments.GatewayError as exc:
        order_svc.cancel_order(order.id, "failed")
        return error(str(exc), 502)
    data = order_json(order)
    data["payment"] = payment_json(order)
    return jsonify(data), 201


@bp.post("/checkout/verify")
@login_required_json
def verify():
    rate_limit.enforce("verify")
    body = json_body()
    public_id = body.get("order_id")
    order = None
    if isinstance(public_id, str):
        order = db.session.scalar(db.select(Order).where(Order.public_id == public_id,
                                                         Order.user_id == current_user.id))
    if order is None:
        return error("Order not found.", 404)
    gateway_order_id, payment_id = body.get("gateway_order_id"), body.get("payment_id")
    if (not order.gateway_order_id or gateway_order_id != order.gateway_order_id
            or not payments.verify_payment(gateway_order_id, payment_id, body.get("signature"))
            or not payments.payment_matches_order(order, payment_id)):
        return error("Payment signature did not verify.", 400)
    if order_svc.mark_paid(order.id, payment_id) == "paid":
        notify.after_payment(order.id)
    db.session.refresh(order)
    return jsonify(order_json(order))


@bp.get("/orders")
@login_required_json
def orders():
    order_svc.release_expired()
    rows = db.session.scalars(db.select(Order).where(Order.user_id == current_user.id)
                              .order_by(Order.id.desc())).all()
    return jsonify({"items": [order_json(o) for o in rows]})


@bp.get("/orders/<public_id>")
@login_required_json
def order(public_id):
    order_svc.release_expired()
    o = db.session.scalar(db.select(Order).where(Order.public_id == public_id,
                                                 Order.user_id == current_user.id))
    return jsonify(order_json(o)) if o else error("Order not found.", 404)


# ---- admin -----------------------------------------------------------------

@bp.get("/admin/stats")
@admin_required_json
def stats():
    paid = db.select(func.coalesce(func.sum(Order.total_paise), 0), func.count(Order.id)).where(Order.status == "paid")
    revenue, paid_count = db.session.execute(paid).one()
    by_status = dict(db.session.execute(db.select(Order.status, func.count(Order.id)).group_by(Order.status)).all())
    return jsonify({"revenue_paise": int(revenue), "paid_orders": paid_count,
                    "orders_by_status": {s: by_status.get(s, 0) for s in ORDER_STATUSES},
                    "units_in_stock": int(db.session.scalar(db.select(func.coalesce(func.sum(Product.stock), 0))))})


@bp.get("/admin/orders")
@admin_required_json
def admin_orders():
    q = db.select(Order).order_by(Order.id.desc())
    if request.args.get("status") in ORDER_STATUSES:
        q = q.where(Order.status == request.args["status"])
    return jsonify({"items": [order_json(o, with_delivery=False) for o in db.session.scalars(q.limit(200))]})


@bp.post("/admin/products")
@admin_required_json
def admin_create_product():
    body = json_body()
    body.setdefault("is_active", True)
    clean, errors = validate_product(body)
    if errors:
        return error("Some fields need attention.", 422, errors)
    p = Product(**clean)
    db.session.add(p)
    db.session.commit()
    return jsonify(product_json(p, admin=True)), 201


@bp.put("/admin/products/<int:product_id>")
@admin_required_json
def admin_update_product(product_id):
    p = db.session.get(Product, product_id)
    if p is None:
        return error("Project not found.", 404)
    body = json_body()
    merged = {"title": p.title, "slug": p.slug, "category_id": p.category_id, "price_paise": p.price_paise,
              "tagline": p.tagline, "description": p.description, "tech": p.tech, "includes": p.includes,
              "delivery_url": p.delivery_url, "is_active": p.is_active, "featured": p.featured, **body}
    merged.pop("stock", None)  # stock changes go through the ledger
    clean, errors = validate_product(merged, existing=p)
    if errors:
        return error("Some fields need attention.", 422, errors)
    for k, v in clean.items():
        setattr(p, k, v)
    db.session.commit()
    return jsonify(product_json(p, admin=True))


@bp.post("/admin/products/<int:product_id>/stock")
@admin_required_json
def admin_stock(product_id):
    body = json_body()
    try:
        delta = whole_number(body.get("delta"), -MAX_STOCK_DELTA, MAX_STOCK_DELTA, "delta")
        p = order_svc.adjust_stock(product_id, delta, text(body.get("note"), MAX_NOTE, "The note"))
    except InputError as exc:
        return error(exc.message, 422)
    except order_svc.CheckoutError as exc:
        return error(exc.messages[0], 409)
    return jsonify(product_json(p, admin=True))
