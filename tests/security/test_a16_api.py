"""Security audit A16: api."""

import re

import pytest

from app.extensions import db
from ..conftest import make_user
from .helpers import _assert_no_internals, csrf_login


def meta_token(client):
    return re.search(r'name="csrf-token" content="([^"]+)"', client.get("/cart").get_data(as_text=True)).group(1)


def _api_rules(application):
    return [r for r in application.url_map.iter_rules() if r.rule.startswith("/api/v1")]


PUBLIC_API = {("/api/v1/products", "GET"), ("/api/v1/products/<slug>", "GET")}


def _fill(rule):
    return re.sub(r"<\w+>", "PS-AAAAAAA", re.sub(r"<int:\w+>", "1", rule))


API_WRITES = [("post", "/api/v1/cart/items"), ("patch", "/api/v1/cart/items/1"), ("post", "/api/v1/checkout"),
              ("post", "/api/v1/checkout/verify")]


ADMIN_API_WRITES = [("post", "/api/v1/admin/products"), ("put", "/api/v1/admin/products/1"),
                    ("post", "/api/v1/admin/products/1/stock")]


WRONG_BODIES = ['[1]', '"text"', '123', '[{"a": 1}]', '{"qty": {"a": 1}, "product_id": [1], "delta": [1]}', 'null']


def test_a16_every_non_public_api_route_requires_sign_in(app, client):
    rules = _api_rules(app)
    assert len(rules) >= 14
    for rule in rules:
        for m in rule.methods - {"HEAD", "OPTIONS"}:
            if (rule.rule, m) in PUBLIC_API:
                continue
            r = client.open(_fill(rule.rule), method=m, json={})
            assert r.status_code in (401, 403) and r.is_json, f"{m} {rule.rule} -> {r.status_code}"


def test_a16_api_routes_reject_methods_they_do_not_declare(buyer):
    declared = {}
    for rule in _api_rules(buyer.application):
        declared.setdefault(rule.rule, set()).update(rule.methods)
    assert len(declared) >= 10
    for path, methods in declared.items():
        for verb in ("PUT", "PATCH", "DELETE", "POST", "GET"):
            if verb in methods:
                continue
            r = buyer.open(_fill(path), method=verb, json={})
            assert r.status_code == 405, f"{verb} {path} -> {r.status_code}"


@pytest.mark.parametrize("body", WRONG_BODIES)
@pytest.mark.parametrize("method,path", API_WRITES + ADMIN_API_WRITES, ids=lambda v: str(v))
def test_a16_json_bodies_of_the_wrong_type_give_4xx_never_500(live_admin, method, path, body):
    r = getattr(live_admin, method)(path, data=body, content_type="application/json")
    assert r.status_code < 500, f"{method.upper()} {path} with body {body!r} -> HTTP {r.status_code}"


def test_a16_api_writes_need_a_csrf_token(csrf_app):
    make_user("boss@example.com", role="admin")
    c = csrf_app.test_client()
    assert csrf_login(c, "boss@example.com").status_code == 302
    for method, path in API_WRITES + ADMIN_API_WRITES + [("delete", "/api/v1/cart/items/1")]:
        r = getattr(c, method)(path, json={})
        assert r.status_code == 400, f"{method.upper()} {path} accepted a write with no CSRF token (HTTP {r.status_code})"
    ok = c.post("/api/v1/cart/items", json={"product_id": 1, "qty": 1}, headers={"X-CSRFToken": meta_token(c)})
    assert ok.status_code == 201


@pytest.mark.parametrize("method,path", [("get", "/api/v1/nope"), ("delete", "/api/v1/products"), ("get", "/api/v1/products/does-not-exist")])
def test_a16_api_errors_are_json_with_the_documented_shape(live_client, method, path):
    r = getattr(live_client, method)(path)
    assert r.is_json and set(r.get_json()) >= {"error"}, f"{method.upper()} {path} -> {r.status_code} {r.content_type}"


def test_a16_csrf_failures_on_the_api_are_json_too(csrf_app):
    make_user()
    c = csrf_app.test_client()
    csrf_login(c)
    r = c.post("/api/v1/cart/items", json={"product_id": 1})
    assert r.status_code == 400 and r.is_json and "error" in r.get_json(), r.content_type


def test_a16_api_error_bodies_leak_no_internals(live_admin):
    c = live_admin
    for r in (c.post("/api/v1/cart/items", json={"product_id": "x"}), c.get("/api/v1/orders/nope"),
              c.post("/api/v1/admin/products", json={}), c.put("/api/v1/admin/products/999", json={"title": "x"})):
        _assert_no_internals(r, "API error")


def test_a16_list_endpoints_are_capped(client):
    big = client.get("/api/v1/products", query_string={"per_page": 100000, "limit": 100000, "page_size": 100000}).get_json()
    assert len(big["items"]) <= client.application.config["PAGE_SIZE"]


def test_a16_public_api_never_exposes_download_links(client, rag):
    rag.delivery_url = "https://files.example.com/secret-kit"
    db.session.commit()
    assert "secret-kit" not in client.get("/api/v1/products").get_data(as_text=True)
    assert "secret-kit" not in client.get(f"/api/v1/products/{rag.slug}").get_data(as_text=True)
