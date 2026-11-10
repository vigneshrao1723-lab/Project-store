from flask import current_app, request
from flask_login import current_user
from sqlalchemy import func

from .extensions import db
from .models import CartItem, Category
from .services import payments


def register_context(app):
    @app.context_processor
    def inject():
        count = 0
        if current_user.is_authenticated:
            count = db.session.scalar(
                db.select(func.coalesce(func.sum(CartItem.qty), 0)).where(CartItem.user_id == current_user.id)
            )
        cats = db.session.scalars(db.select(Category).order_by(Category.name)).all()
        return {"cart_count": int(count or 0), "nav_categories": cats,
                "gateway_mode": payments.mode(),
                "reservation_minutes": current_app.config["RESERVATION_MINUTES"], "current_path": request.path}
