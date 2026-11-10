from flask import Blueprint, render_template
from flask_login import current_user, login_required

from ..services import cart as cart_svc

bp = Blueprint("cart", __name__)


@bp.get("/cart")
@login_required
def view():
    return render_template("cart.html", cart=cart_svc.contents(current_user))
