"""Security audit A18: cors."""

from importlib import util

import pytest

from ..conftest import make_user
from .helpers import csrf_login, read


def test_a18_flask_cors_is_not_installed_or_required():
    assert util.find_spec("flask_cors") is None
    assert "cors" not in read("requirements.txt").lower() + read("requirements-dev.txt").lower()


@pytest.mark.parametrize("path", ["/", "/api/v1/products", "/static/css/main.css", "/no-such-page"])
def test_a18_cross_origin_requests_get_no_cors_headers(client, path):
    r = client.get(path, headers={"Origin": "https://evil.example"})
    assert not [h for h in r.headers.keys() if h.lower().startswith("access-control-")], dict(r.headers)


def test_a18_preflight_requests_are_not_approved(client):
    r = client.options("/api/v1/cart/items", headers={"Origin": "https://evil.example",
                                                      "Access-Control-Request-Method": "POST",
                                                      "Access-Control-Request-Headers": "x-csrftoken,content-type"})
    assert not [h for h in r.headers.keys() if h.lower().startswith("access-control-")]


def test_a18_credentialed_cross_site_post_is_rejected_by_csrf(csrf_app):
    make_user()
    c = csrf_app.test_client()
    assert csrf_login(c).status_code == 302
    for path, body in (("/api/v1/cart/items", {"product_id": 1, "qty": 1}), ("/api/v1/checkout", {})):
        r = c.post(path, json=body, headers={"Origin": "https://evil.example", "Referer": "https://evil.example/attack"})
        assert r.status_code == 400, f"{path} accepted a cookie-authenticated cross-site POST"
    assert c.post("/logout", headers={"Origin": "https://evil.example"}).status_code == 400
