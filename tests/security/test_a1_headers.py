"""Security audit A1: headers."""

import re

import pytest

from app.extensions import db
from .helpers import build_app


REQUIRED_HEADERS = [
    "Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy",
    "Permissions-Policy", "Cross-Origin-Opener-Policy",
]


RESPONSE_KINDS = {
    "page 200": ("get", "/"),
    "catalogue 200": ("get", "/catalogue"),
    "html 404": ("get", "/no-such-page"),
    "redirect 302": ("get", "/cart"),
    "api json 200": ("get", "/api/v1/products"),
    "api json 404": ("get", "/api/v1/nope"),
    "api json 401": ("get", "/api/v1/cart"),
    "405": ("delete", "/"),
    "static css": ("get", "/static/css/main.css"),
    "static js": ("get", "/static/js/app.js"),
    "static 404": ("get", "/static/missing.css"),
    "500 page": ("get", "/_boom"),
}


@pytest.mark.parametrize("kind", RESPONSE_KINDS)
def test_a1_every_response_type_carries_all_security_headers(live_client, kind):
    method, path = RESPONSE_KINDS[kind]
    resp = getattr(live_client, method)(path)
    missing = [h for h in REQUIRED_HEADERS if h not in resp.headers]
    assert not missing, f"{kind} ({method.upper()} {path} -> {resp.status_code}) is missing {missing}"


def test_a1_csrf_error_response_carries_security_headers(csrf_app):
    resp = csrf_app.test_client().post("/login", data={"email": "a@b.co", "password": "x"})
    assert resp.status_code == 400
    missing = [h for h in REQUIRED_HEADERS if h not in resp.headers]
    assert not missing, f"CSRF error response is missing {missing}"


def test_a1_hsts_is_sent_when_cookies_are_secure():
    application = build_app(SESSION_COOKIE_SECURE=True)
    with application.app_context():
        db.create_all()
        hsts = application.test_client().get("/").headers.get("Strict-Transport-Security", "")
        db.drop_all()
    assert "max-age=" in hsts, "COOKIE_SECURE is true but no Strict-Transport-Security header is sent"
    assert int(re.search(r"max-age=(\d+)", hsts).group(1)) >= 15552000, "HSTS max-age under 180 days"


def test_a1_hsts_is_not_sent_when_cookies_are_not_secure(client):
    assert "Strict-Transport-Security" not in client.get("/").headers


def test_a1_signed_in_pages_are_not_cached(buyer):
    for path in ("/orders", "/cart", "/api/v1/cart", "/api/v1/orders"):
        cc = buyer.get(path).headers.get("Cache-Control", "")
        assert "no-store" in cc, f"{path} can be cached by browsers and shared proxies (Cache-Control: {cc!r})"
