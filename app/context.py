import json
import re
from pathlib import Path
from urllib.parse import quote

from flask import current_app, request
from flask_login import current_user
from sqlalchemy import func

from .extensions import db, stable_csrf_token
from .models import CartItem, Category, utcnow
from .services import payments


# Figures about the project itself (test counts, coverage). One file, written only by scripts/update_facts.py and
# checked by tests/test_fx_facts.py, so the home page and the README cannot drift from each other or from the suite.
FACTS = json.loads((Path(__file__).parent / "facts.json").read_text(encoding="utf-8"))
# Effects switched off, by name (see docs/MOTION_TUNING.md). One list for the whole site; written into <html data-fx-off>.
FX_OFF = json.loads((Path(__file__).parent / "fx.json").read_text(encoding="utf-8"))["off"]


# The palette, read once from tokens.css (the only place a colour is written), for the favicon and the manifest.
TOKENS = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})",
                         (Path(__file__).parent / "static" / "css" / "tokens.css").read_text(encoding="utf-8")))


def _favicon_svg():
    """The tab icon, painted with the palette from tokens.css, so no colour is written twice."""
    return ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' fill='%s'/>"
            "<path d='M6 6h13l7 7v13H6z' fill='%s'/></svg>") % (TOKENS["violet"], TOKENS["amber"])


FAVICON_SVG = _favicon_svg()
FAVICON = "data:image/svg+xml," + quote(FAVICON_SVG, safe="/:=' ")


MAP_EMBED = "https://maps.google.com/maps?q={q}&t=h&z=12&output=embed"      # hybrid view, city level, no API key
MAP_OPEN = "https://www.google.com/maps/search/?api=1&query={q}"


def contact_info(cfg):
    """The owner's contact details, only those set in the environment. Nothing personal is written in the code.

    The phone number is shown as typed in CONTACT_PHONE, and its tel: and wa.me links are built from its digits here,
    at render time. The map is city level only: it is centred on CONTACT_CITY, never on a street address."""
    phone = cfg.get("CONTACT_PHONE", "")
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits and len(digits) == 10:                  # a bare Indian mobile number
        digits = "91" + digits
    safe_url = lambda u: u if u.startswith(("https://", "http://")) else ""
    city = cfg.get("CONTACT_CITY", "")
    # "Bengaluru, Karnataka" from SELLER_ADDRESS when it starts with the city, otherwise the city alone
    parts = [p.strip() for p in cfg.get("SELLER_ADDRESS", "").split(",") if p.strip()]
    region = ", ".join(parts[:2]) if city and parts and parts[0].lower() == city.lower() else city
    info = {"name": cfg.get("CONTACT_NAME", ""), "email": cfg.get("CONTACT_EMAIL", ""), "phone": phone, "city": city,
            "tel": ("+" + digits) if 8 <= len(digits) <= 15 else "",
            "whatsapp": f"https://wa.me/{digits}" if 8 <= len(digits) <= 15 else "",
            "github": safe_url(cfg.get("CONTACT_GITHUB", "")), "linkedin": safe_url(cfg.get("CONTACT_LINKEDIN", "")),
            "map_label": region,
            "map_embed": MAP_EMBED.format(q=quote(city)) if city else "",
            "map_open": MAP_OPEN.format(q=quote(region or city)) if city else ""}
    info["any"] = any(info[k] for k in ("name", "email", "phone", "city", "github", "linkedin"))
    return info


def seller_info(cfg):
    """Who sells, as the Consumer Protection (E-Commerce) Rules, 2020 ask a seller to show: name, address, contact
    and the grievance officer. Everything comes from the environment."""
    return {"name": cfg.get("SELLER_NAME", "") or "Project Store", "address": cfg.get("SELLER_ADDRESS", ""),
            "gstin": cfg.get("SELLER_GSTIN", ""), "grievance_name": cfg.get("CONTACT_NAME", "") or cfg.get("SELLER_NAME", ""),
            "email": cfg.get("CONTACT_EMAIL", ""), "phone": cfg.get("CONTACT_PHONE", "")}


def canonical_url():
    """The one address a page should be listed under: PUBLIC_BASE_URL plus the path, without tracking or sort
    parameters. The catalogue keeps its field (?category=...), which is a page of its own."""
    url = current_app.config["PUBLIC_BASE_URL"] + request.path
    if request.endpoint == "shop.catalogue" and request.args.get("category"):
        url += "?category=" + quote(request.args.get("category", "")[:80], safe="")
    return url


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
                "facts": FACTS, "fx_off": FX_OFF, "favicon_href": FAVICON,
                "contact_info": contact_info(current_app.config), "seller": seller_info(current_app.config),
                "current_year": utcnow().year, "canonical_url": canonical_url(), "theme_color": TOKENS["night"]}
