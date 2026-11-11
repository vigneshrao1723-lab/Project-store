"""No inline styles anywhere, so the Content-Security-Policy can leave 'unsafe-inline' out of style-src."""
import re
from pathlib import Path

from app.models import Order
from app.extensions import db
from app.services import orders as order_svc

ROOT = Path(__file__).resolve().parent.parent
CSS_RULES_FROM_THE_OLD_STYLE_ATTRIBUTES = [
    ".fs-sm {", ".fs-md {", ".mt-08 {", ".mt-1 {", "h2.mt-24 {", ".mw-640 {", "p.stat-value {", ".actions-row {",
    ".title-row {", ".wrap.narrow.cart-body {", ".count-line {", ".table-wrap.end-gap {", ".empty.end-gap {",
    ".wrap.w-820 {", ".crumbs.flush {", ".placed-note {", ".pay-items {", ".pay-items li {", ".byline {",
    ".section.flush-top {",
]


def test_style_src_is_self_only(client):
    policy = client.get("/").headers["Content-Security-Policy"]
    assert "style-src 'self';" in policy and "unsafe-inline" not in policy


def test_no_template_or_script_sets_a_style_attribute_or_style_element():
    for f in list((ROOT / "app" / "templates").rglob("*.html")):
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"\sstyle\s*=", text) and "<style" not in text, f
    for f in (ROOT / "app" / "static" / "js").glob("*.js"):
        text = f.read_text(encoding="utf-8")
        assert "setAttribute(\"style\"" not in text and "setAttribute('style'" not in text and "cssText" not in text, f


def test_each_rule_that_replaced_a_style_attribute_is_in_the_stylesheet():
    css = (ROOT / "app" / "static" / "css" / "main.css").read_text(encoding="utf-8")
    css = css.replace("\r\n", "\n")
    missing = [rule for rule in CSS_RULES_FROM_THE_OLD_STYLE_ATTRIBUTES if "\n" + rule not in css]
    assert not missing, missing


def test_the_class_names_do_not_collide_with_older_rules():
    css = (ROOT / "app" / "static" / "css" / "main.css").read_text(encoding="utf-8")
    assert len(re.findall(r"^\.page-head\b", css, re.M)) == 1          # the original header rule is untouched
    assert len(re.findall(r"^\.title-row\b", css, re.M)) == 1


def test_dashboard_bars_carry_their_height_in_an_svg_attribute(admin_client, buyer, rag, app):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 2})
    order = buyer.post("/api/v1/checkout").get_json()
    row = db.session.scalar(db.select(Order).where(Order.public_id == order["id"]))
    order_svc.mark_paid(row.id, "pay_bar")
    page = admin_client.get("/admin").get_data(as_text=True)
    heights = re.findall(r'<svg width="100%" height="([\d.]+)%" aria-hidden="true"></svg>', page)
    assert len(heights) == 14 and "100.0%" in [h + "%" for h in heights]       # the busiest day is a full-height bar
    assert heights.count("0.0") == 13 and "style=" not in page


def test_the_busiest_day_is_the_highlighted_bar(admin_client, buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    order = buyer.post("/api/v1/checkout").get_json()
    order_svc.mark_paid(db.session.scalar(db.select(Order.id).where(Order.public_id == order["id"])), "pay_top")
    page = admin_client.get("/admin").get_data(as_text=True)
    assert page.count('class="bar-col top"') == 1
