from flask import current_app

from ..extensions import db
from ..models import CartItem, Product
from ..validation import INT32_MAX, MAX_REQUEST_QTY, InputError, whole_number


class CartError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def _clamp(qty):
    return max(1, min(int(qty), current_app.config["MAX_QTY_PER_LINE"]))


def set_qty(user, product_id, qty, add=False):
    try:
        product_id = whole_number(product_id, 1, INT32_MAX, "The project")
        qty = whole_number(qty, 1, MAX_REQUEST_QTY, "Quantity")
    except InputError as exc:
        raise CartError(exc.message)
    product = db.session.get(Product, product_id)
    if product is None or not product.is_active:
        raise CartError("That project isn't available.", 404)
    if product.stock == 0:
        raise CartError(f"{product.title} is sold out.", 409)

    item = db.session.scalar(db.select(CartItem).where(CartItem.user_id == user.id,
                                                       CartItem.product_id == product_id))
    new_qty = _clamp((item.qty if (item and add) else 0) + qty)
    if new_qty > product.stock:
        new_qty = product.stock
    if item is None:
        item = CartItem(user_id=user.id, product_id=product_id, qty=new_qty)
        db.session.add(item)
    else:
        item.qty = new_qty
    db.session.commit()
    return item


def remove(user, product_id):
    if not 1 <= product_id <= INT32_MAX:        # nothing that large can be in a cart
        return
    item = db.session.scalar(db.select(CartItem).where(CartItem.user_id == user.id,
                                                       CartItem.product_id == product_id))
    if item:
        db.session.delete(item)
        db.session.commit()


def contents(user):
    items = db.session.scalars(
        db.select(CartItem).where(CartItem.user_id == user.id).order_by(CartItem.id)
    ).all()
    lines = [{
        "product_id": i.product_id, "slug": i.product.slug, "title": i.product.title,
        "unit_paise": i.product.price_paise, "qty": i.qty, "line_paise": i.product.price_paise * i.qty,
        "stock": i.product.stock, "available": i.product.available,
    } for i in items]
    return {"lines": lines, "count": sum(l["qty"] for l in lines),
            "total_paise": sum(l["line_paise"] for l in lines)}
