import json
from pathlib import Path

from flask import current_app, request
from flask_login import current_user
from sqlalchemy import func

from .extensions import db, stable_csrf_token
from .models import CartItem, Category
from .services import payments


# Figures about the project itself (test counts, coverage). One file, written only by scripts/update_facts.py and
# checked by tests/test_fx_facts.py, so the home page and the README cannot drift from each other or from the suite.
FACTS = json.loads((Path(__file__).parent / "facts.json").read_text(encoding="utf-8"))
# Effects switched off, by name (see docs/MOTION_TUNING.md). One list for the whole site; written into <html data-fx-off>.
FX_OFF = json.loads((Path(__file__).parent / "fx.json").read_text(encoding="utf-8"))["off"]


def register_context(app):
    @app.context_processor
    def inject():
        count = 0
        if current_user.is_authenticated:
            count = db.session.scalar(
                db.select(func.coalesce(func.sum(CartItem.qty), 0)).where(CartItem.user_id == current_user.id)
            )
        cats = db.session.scalars(db.select(Category).order_by(Category.name)).all()
        return {"csrf_token": stable_csrf_token, "cart_count": int(count or 0), "nav_categories": cats,
                "gateway_mode": payments.mode(),
                "reservation_minutes": current_app.config["RESERVATION_MINUTES"], "current_path": request.path,
                "facts": FACTS, "fx_off": FX_OFF}
