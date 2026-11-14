"""Security audit A12: xss."""

import re

import pytest

from app.extensions import db
from app.models import Product
from ..conftest import login, make_user
from .helpers import APP_DIR, ROOT, start_order


HOSTILE = ['<script>alert(1)</script>', '"><img src=x onerror=alert(1)>', "</title><script>alert(2)</script>",
           "x' onmouseover='alert(3)", '"></svg><script>alert(4)</script>']


BREAKOUTS = ["<script>alert", "<img src=x", "</title><script", "</svg><script", "' onmouseover='"]


@pytest.mark.parametrize("title", HOSTILE)
def test_a12_product_titles_are_escaped_in_the_cover_art_and_everywhere_else(app, client, buyer, rag, title):
    rag.title = title
    db.session.commit()
    start_order(buyer, rag)
    pages = ["/", "/catalogue", f"/p/{rag.slug}", "/cart", "/orders"]
    for path in pages:
        body = buyer.get(path).get_data(as_text=True)
        found = [b for b in BREAKOUTS if b in body]
        assert not found, f"{path} contains unescaped markup from a product title: {found}"


@pytest.mark.parametrize("name", HOSTILE)
def test_a12_customer_names_are_escaped(app, name):
    make_user("xss@example.com", name=name)
    c = app.test_client()
    login(c, "xss@example.com")
    p = db.session.scalar(db.select(Product).limit(1))
    order = start_order(c, p, name=name)
    boss = make_user("boss@example.com", role="admin")
    a = app.test_client()
    login(a, "boss@example.com")
    for client_, path in ((c, "/"), (c, f"/orders/{order['id']}"), (c, f"/checkout/pay/{order['id']}"),
                          (a, "/admin"), (a, "/admin/orders"), (a, f"/admin/orders/{order['id']}")):
        body = client_.get(path).get_data(as_text=True)
        found = [b for b in BREAKOUTS if b in body]
        assert not found, f"{path} contains unescaped markup from a customer name: {found}"


def test_a12_cover_svg_is_not_marked_safe_without_escaping():
    from app.covers import cover_svg
    svg = cover_svg("slug", "web", '"><script>alert(1)</script>')
    assert "<script>" not in svg and '"><script' not in svg and "<img" not in svg


def test_a12_the_only_unescaped_html_in_the_codebase_is_the_cover_helper():
    files = set()
    for f in list(APP_DIR.rglob("*.py")) + list((APP_DIR / "templates").rglob("*.html")):
        text = f.read_text(encoding="utf-8")
        if re.search(r"\|\s*safe|Markup\(|autoescape\s+false|render_template_string", text):
            files.add(f.relative_to(ROOT).as_posix())
    # the cover helper, and the setup-guide renderer, which escapes every piece first (tests/test_order_messages.py)
    assert files == {"app/__init__.py", "app/services/guide.py"}, files
