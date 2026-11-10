import re

from ..extensions import db
from ..models import Category, Product


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:110]


def validate_product(data, existing=None):
    """Return (clean_values, errors) from form or JSON input."""
    errors, clean = {}, {}

    title = str(data.get("title", "")).strip()
    if not title:
        errors["title"] = "Enter a title."
    clean["title"] = title

    slug = slugify(str(data.get("slug") or title))
    clash = db.session.scalar(db.select(Product).where(Product.slug == slug))
    if not slug:
        errors["slug"] = "Enter a URL name."
    elif clash and (existing is None or clash.id != existing.id):
        errors["slug"] = "Another project already uses this URL name."
    clean["slug"] = slug

    cat = db.session.get(Category, int(data["category_id"])) if str(data.get("category_id", "")).isdigit() else None
    if cat is None:
        errors["category_id"] = "Choose a category."
    clean["category_id"] = cat.id if cat else None

    try:
        price = round(float(data.get("price_rupees")) * 100) if "price_rupees" in data else int(data["price_paise"])
        if price < 0:
            raise ValueError
        clean["price_paise"] = price
    except (TypeError, ValueError, KeyError):
        errors["price_rupees"] = "Enter a price of 0 or more."

    if existing is None:
        try:
            stock = int(data.get("stock", 0))
            if stock < 0:
                raise ValueError
            clean["stock"] = stock
        except (TypeError, ValueError):
            errors["stock"] = "Enter a whole number, 0 or more."

    for field in ("tagline", "description", "tech", "includes", "delivery_url"):
        clean[field] = str(data.get(field, "")).strip()
    if clean["delivery_url"] and not re.match(r"^https?://", clean["delivery_url"]):
        errors["delivery_url"] = "Use a full link starting with http:// or https://."
    if len(clean["tagline"]) > 255:
        errors["tagline"] = "Keep the tagline under 255 characters."

    clean["is_active"] = str(data.get("is_active", "")).lower() in {"1", "true", "on", "yes"}
    clean["featured"] = str(data.get("featured", "")).lower() in {"1", "true", "on", "yes"}
    return clean, errors
