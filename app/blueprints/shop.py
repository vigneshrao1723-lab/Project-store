from flask import Blueprint, abort, render_template, request

from ..extensions import db
from ..models import Product
from ..services.catalog import SORTS, category_counts, search_products

bp = Blueprint("shop", __name__)


@bp.get("/")
def home():
    featured = db.session.scalars(
        db.select(Product).where(Product.is_active.is_(True), Product.featured.is_(True)).order_by(Product.id)
    ).all()
    latest = db.session.scalars(
        db.select(Product).where(Product.is_active.is_(True)).order_by((Product.stock == 0).asc(), Product.id.desc()).limit(4)
    ).all()
    return render_template("home.html", featured=featured, hero=featured[0] if featured else None,
                           latest=latest, categories=category_counts())


@bp.get("/catalogue")
def catalogue():
    q = request.args.get("q", "")
    category = request.args.get("category", "")
    sort = request.args.get("sort", "new")
    if sort not in SORTS:
        sort = "new"
    page = request.args.get("page", 1, type=int)
    result = search_products(q, category or None, sort, page)
    return render_template("catalogue.html", result=result, q=q, category=category, sort=sort,
                           categories=category_counts())


@bp.get("/p/<slug>")
def product(slug):
    p = db.session.scalar(db.select(Product).where(Product.slug == slug, Product.is_active.is_(True)))
    if p is None:
        abort(404)
    related = db.session.scalars(
        db.select(Product).where(Product.category_id == p.category_id, Product.id != p.id,
                                 Product.is_active.is_(True)).limit(3)
    ).all()
    return render_template("product.html", p=p, related=related)


@bp.get("/healthz")
def healthz():
    """Liveness and database check for Docker and load balancers."""
    db.session.execute(db.text("SELECT 1"))
    return {"status": "ok"}
