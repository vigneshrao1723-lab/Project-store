import re

from ..extensions import db
from ..models import Category, Product
from ..validation import (INT32_MAX, MAX_LONG_TEXT, MAX_PRICE_PAISE, MAX_SLUG, MAX_STOCK, MAX_TAGLINE, MAX_TECH,
                          MAX_TITLE, MAX_URL, InputError, rupees_to_paise, text, whole_number)

URL_RE = re.compile(r"^https?://\S+$")


def slugify(text_):
    return re.sub(r"[^a-z0-9]+", "-", text_.lower()).strip("-")[:110]


def validate_product(data, existing=None):
    """Return (clean_values, errors) from form or JSON input. Wrong types, over-long text and out-of-range
    numbers are field errors, never exceptions."""
    errors, clean = {}, {}

    def read(name, max_len, label, required=False):
        try:
            return text(data.get(name), max_len, label, required)
        except InputError as exc:
            errors[name] = exc.message
            return ""

    title = read("title", MAX_TITLE, "The title", required=True)
    if errors.get("title") == "The title is required.":
        errors["title"] = "Enter a title."
    clean["title"] = title

    slug = slugify(read("slug", MAX_SLUG, "The URL name") or title)
    clash = db.session.scalar(db.select(Product).where(Product.slug == slug))
    if not slug:
        if "title" not in errors:           # a missing or over-long title already says what to fix
            errors.setdefault("slug", "Enter a URL name.")
    elif clash and (existing is None or clash.id != existing.id):
        errors["slug"] = "Another project already uses this URL name."
    clean["slug"] = slug

    cat = None
    try:
        cat = db.session.get(Category, whole_number(data.get("category_id"), 1, INT32_MAX))
    except InputError:
        pass
    if cat is None:
        errors["category_id"] = "Choose a category."
    clean["category_id"] = cat.id if cat else None

    try:
        if "price_rupees" in data:
            clean["price_paise"] = rupees_to_paise(data["price_rupees"])
        else:
            clean["price_paise"] = whole_number(data["price_paise"], 0, MAX_PRICE_PAISE, "The price")
    except (InputError, KeyError):
        errors["price_rupees"] = f"Enter a price from 0 to {MAX_PRICE_PAISE // 100:,} rupees, with at most two decimals."

    if existing is None:
        try:
            clean["stock"] = whole_number(data.get("stock", 0), 0, MAX_STOCK, "Stock")
        except InputError:
            errors["stock"] = f"Enter a whole number from 0 to {MAX_STOCK:,}."

    clean["tagline"] = read("tagline", MAX_TAGLINE, "The tagline")
    clean["description"] = read("description", MAX_LONG_TEXT, "The description")
    clean["tech"] = read("tech", MAX_TECH, "The tech list")
    clean["includes"] = read("includes", MAX_LONG_TEXT, "The includes list")
    clean["delivery_url"] = read("delivery_url", MAX_URL, "The link")
    if clean["delivery_url"] and not URL_RE.match(clean["delivery_url"]):
        errors.setdefault("delivery_url", "Use a full link starting with http:// or https://, with no spaces.")

    clean["is_active"] = str(data.get("is_active", "")).lower() in {"1", "true", "on", "yes"}
    clean["featured"] = str(data.get("featured", "")).lower() in {"1", "true", "on", "yes"}
    return clean, errors
