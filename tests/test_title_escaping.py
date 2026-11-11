"""The product title from manual testing, on every page that shows a title, as plain text everywhere."""
import re

import pytest

from app.extensions import db

TITLE = 'Test <b>bold</b> & "quotes"'


@pytest.fixture()
def odd_titled(app, rag):
    rag.title = TITLE
    db.session.commit()
    return rag


def check(html, where):
    assert "<b>bold</b>" not in html and "<b>" not in html, f"{where}: the title became markup"
    assert "&lt;b&gt;bold&lt;/b&gt;" in html, f"{where}: the escaped title is missing"
    for svg in re.findall(r"<svg class=\"cover\".*?</svg>", html, re.S):
        assert svg.count("<title>") <= 1
        assert 'aria-label="' in svg and svg.index('aria-label="') < svg.index(">")      # the attribute is not cut short


def test_customer_pages_show_the_title_as_text(buyer, odd_titled):
    buyer.post("/api/v1/cart/items", json={"product_id": odd_titled.id, "qty": 1})
    order = buyer.post("/api/v1/checkout", json={}).get_json()["id"]
    buyer.post("/api/v1/cart/items", json={"product_id": odd_titled.id, "qty": 1})
    pages = ["/", "/catalogue", "/catalogue?q=quotes", f"/p/{odd_titled.slug}", "/cart", "/orders", f"/orders/{order}",
             f"/checkout/pay/{order}"]
    for path in pages:
        resp = buyer.get(path)
        assert resp.status_code == 200, path
        check(resp.get_data(as_text=True), path)


def test_admin_pages_show_the_title_as_text(admin_client, buyer, odd_titled):
    buyer.post("/api/v1/cart/items", json={"product_id": odd_titled.id, "qty": 1})
    order = buyer.post("/api/v1/checkout", json={}).get_json()["id"]
    for path in ("/admin/products", f"/admin/orders/{order}"):
        check(admin_client.get(path).get_data(as_text=True), path)
    edit = admin_client.get(f"/admin/products/{odd_titled.id}").get_data(as_text=True)
    assert "<b>bold</b>" not in edit
    assert 'value="Test &lt;b&gt;bold&lt;/b&gt; &amp; &#34;quotes&#34;"' in edit      # the input still holds the exact text


def test_the_api_returns_the_title_unchanged_for_json_clients(client, odd_titled):
    items = client.get("/api/v1/products").get_json()["items"]
    assert TITLE in [p["title"] for p in items]
