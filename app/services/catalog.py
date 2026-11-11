from flask import current_app
from sqlalchemy import or_

from ..extensions import db
from ..models import Category, Product
from ..validation import MAX_CATEGORY_SLUG, clean_query, page_number

SORTS = {
    "new": Product.created_at.desc(),
    "price_asc": Product.price_paise.asc(),
    "price_desc": Product.price_paise.desc(),
    "title": Product.title.asc(),
}


def search_products(q="", category=None, sort="new", page=1, include_inactive=False):
    stmt = db.select(Product).join(Category)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    if category:
        stmt = stmt.where(Category.slug == category[:MAX_CATEGORY_SLUG])
    q = clean_query(q).strip()
    if q:
        like = f"%{q.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(or_(Product.title.ilike(like), Product.tagline.ilike(like),
                              Product.tech.ilike(like), Category.name.ilike(like)))
    # In-stock items first, then the chosen order; id keeps pagination stable.
    stmt = stmt.order_by((Product.stock == 0).asc(), SORTS.get(sort, SORTS["new"]), Product.id)
    return db.paginate(stmt, page=page_number(page), per_page=current_app.config["PAGE_SIZE"], error_out=False)


def category_counts():
    rows = db.session.execute(
        db.select(Category, db.func.count(Product.id))
        .outerjoin(Product, db.and_(Product.category_id == Category.id, Product.is_active.is_(True)))
        .group_by(Category.id).order_by(Category.name)
    ).all()
    return rows
