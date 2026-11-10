from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Order
from ..services.orders import release_expired

bp = Blueprint("account", __name__)


@bp.get("/orders")
@login_required
def orders():
    release_expired()
    rows = db.session.scalars(
        db.select(Order).where(Order.user_id == current_user.id).order_by(Order.id.desc())
    ).all()
    return render_template("orders.html", orders=rows)


@bp.get("/orders/<public_id>")
@login_required
def order_detail(public_id):
    release_expired()
    order = db.session.scalar(db.select(Order).where(Order.public_id == public_id))
    if order is None or (order.user_id != current_user.id and not current_user.is_admin):
        abort(404)
    return render_template("order_detail.html", order=order)
