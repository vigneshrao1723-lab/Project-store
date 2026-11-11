"""Security audit A10: input validation."""

import json

import pytest

from app.extensions import db
from app.models import Order, Product, User


LONG = "x" * 10_000


BAD_QTY = [-1, 0, "abc", "", None, [], {}, [1], True, 1e999, -1e999, 2.5, "9" * 400, 10 ** 400]


BAD_IDS = ["abc", [], {}, None, 1.5, -1, 0, 10 ** 30, "1; DROP TABLE products"]


ADMIN_PRODUCT_OK = {"title": "Valid", "category_id": 1, "price_rupees": "100", "stock": "1", "tagline": "t",
                    "description": "d", "tech": "x", "includes": "i", "delivery_url": "https://example.com/k"}


BAD_PRODUCT_FIELDS = [
    ("title", "T" * 1000), ("tagline", "t" * 5000), ("tech", "t" * 5000),
    ("delivery_url", "https://example.com/" + "a" * 5000), ("delivery_url", "javascript:alert(1)"),
    ("price_rupees", "-5"), ("price_rupees", "1e999"), ("price_rupees", "inf"), ("price_rupees", "nan"),
    ("price_rupees", "99999999999999999999999"), ("stock", "-1"), ("stock", "99999999999999999999999"),
    ("category_id", "abc"), ("category_id", "99999999999999999999999"),
]


API_ONLY_BAD_FIELDS = [("title", ["x"]), ("title", {"a": 1}), ("tagline", 12345), ("stock", [1]), ("price_rupees", [1])]


API_BAD = BAD_PRODUCT_FIELDS + API_ONLY_BAD_FIELDS


@pytest.mark.parametrize("field,value", [("name", LONG), ("email", LONG + "@example.com"), ("password", "p" * 5000)])
def test_a10_registration_rejects_oversized_input(client, field, value):
    form = {"name": "Okay Name", "email": "okay@example.com", "password": "long-enough-1", field: value}
    client.post("/register", data=form)
    n = db.session.scalar(db.select(db.func.count(User.id)).where(User.role == "customer"))
    assert n == 0, f"an account was created with an oversized {field} ({len(value)} characters)"


@pytest.mark.parametrize("body", [{"billing_name": LONG}, {"billing_name": "Okay", "phone": LONG},
                                  {"billing_name": ["list"]}, {"billing_name": {"a": 1}}, {"billing_name": "Okay", "phone": ["1"]}])
def test_a10_api_checkout_rejects_oversized_or_wrongly_typed_fields(live_buyer, live_rag, body):
    live_buyer.post("/api/v1/cart/items", json={"product_id": live_rag.id, "qty": 1})
    r = live_buyer.post("/api/v1/checkout", json=body)
    assert 400 <= r.status_code < 500, f"HTTP {r.status_code}: checkout accepted {str(body)[:60]}"
    assert db.session.scalar(db.select(db.func.count(Order.id))) == 0


@pytest.mark.parametrize("form", [{"billing_name": LONG}, {"billing_name": "Okay", "phone": LONG}])
def test_a10_page_checkout_rejects_oversized_fields(buyer, rag, form):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    r = buyer.post("/checkout", data=form)
    assert r.status_code == 400 and db.session.scalar(db.select(db.func.count(Order.id))) == 0


@pytest.mark.parametrize("qty", BAD_QTY, ids=[repr(q)[:18] for q in BAD_QTY])
def test_a10_cart_quantity_never_causes_a_server_error_or_an_oversized_line(live_app, live_buyer, live_rag, qty):
    if isinstance(qty, float) and qty in (float("inf"), float("-inf")):
        literal = "1e999" if qty > 0 else "-1e999"             # json.dumps would write Infinity, which is not JSON
    else:
        literal = json.dumps(qty)
    payload = '{"product_id": %d, "qty": %s}' % (live_rag.id, literal)
    r = live_buyer.post("/api/v1/cart/items", data=payload, content_type="application/json")
    assert r.status_code < 500, f"qty={literal[:30]} -> HTTP {r.status_code}"
    assert live_buyer.get("/api/v1/cart").get_json()["count"] <= live_app.config["MAX_QTY_PER_LINE"]


@pytest.mark.parametrize("pid", BAD_IDS, ids=[repr(p)[:18] for p in BAD_IDS])
def test_a10_cart_product_id_never_causes_a_server_error(live_buyer, pid):
    r = live_buyer.post("/api/v1/cart/items", json={"product_id": pid, "qty": 1})
    assert 400 <= r.status_code < 500, f"product_id={pid!r:.30} -> HTTP {r.status_code}"


def test_a10_huge_page_number_does_not_cause_a_server_error(live_client):
    for path in ("/api/v1/products?page=99999999999999999999999", "/catalogue?page=99999999999999999999999"):
        assert live_client.get(path).status_code < 500, path


def test_a10_search_text_is_bounded(live_client):
    r = live_client.get("/api/v1/products", query_string={"q": "a" * 100_000})
    assert r.status_code in (200, 400, 414), f"a 100 000 character search term gave HTTP {r.status_code}"
    r = live_client.get("/catalogue", query_string={"q": "%" * 5000, "sort": "x" * 5000, "category": "y" * 5000})
    assert r.status_code < 500


@pytest.mark.parametrize("field,value", BAD_PRODUCT_FIELDS, ids=[f"{f}={str(v)[:14]}" for f, v in BAD_PRODUCT_FIELDS])
def test_a10_admin_product_form_rejects_bad_values(live_admin, field, value):
    before = db.session.scalar(db.select(db.func.count(Product.id)))
    r = live_admin.post("/admin/products/new", data={**ADMIN_PRODUCT_OK, "slug": "new-one", field: value})
    db.session.rollback()
    after = db.session.scalar(db.select(db.func.count(Product.id)))
    assert r.status_code == 200 and after == before, f"HTTP {r.status_code}; product created={after != before}"


@pytest.mark.parametrize("field,value", API_BAD, ids=[f"{f}={str(v)[:14]}" for f, v in API_BAD])
def test_a10_admin_product_api_rejects_bad_values(live_admin, field, value):
    r = live_admin.post("/api/v1/admin/products", json={**ADMIN_PRODUCT_OK, "slug": "new-api-one", field: value})
    assert r.status_code == 422, f"HTTP {r.status_code} for {field}={str(value)[:30]}"


@pytest.mark.parametrize("delta", [10 ** 30, "x", [], {}, None, -10 ** 30], ids=lambda d: repr(d)[:12])
def test_a10_admin_stock_adjustment_rejects_bad_deltas(live_admin, live_rag, delta):
    r = live_admin.post(f"/api/v1/admin/products/{live_rag.id}/stock", json={"delta": delta})
    assert 400 <= r.status_code < 500, f"delta={delta!r:.30} -> HTTP {r.status_code}"


def test_a10_request_bodies_are_size_limited(client):
    assert client.application.config.get("MAX_CONTENT_LENGTH"), "MAX_CONTENT_LENGTH is not set"
    r = client.post("/api/v1/cart/items", data=b"x" * 5_000_000, content_type="application/json")
    assert r.status_code == 413, f"a 5 MB body was read and processed (HTTP {r.status_code})"
