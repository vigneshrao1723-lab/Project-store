"""Back after sign-out must not show a stale, signed-in looking page (browsers keep a frozen copy in the
back/forward cache and Safari keeps it even for no-store pages), so app.js reloads a restored page."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = (ROOT / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")


def test_app_js_reloads_a_page_restored_from_the_back_forward_cache():
    assert re.search(r'addEventListener\(\s*"pageshow"', APP_JS), "no pageshow handler"
    handler = APP_JS[APP_JS.index('"pageshow"'):]
    handler = handler[:handler.index("});") + 3]
    assert "event.persisted" in handler or "e.persisted" in handler
    assert "location.reload()" in handler


def test_the_handler_reloads_only_for_restored_pages_not_for_normal_loads():
    handler = APP_JS[APP_JS.index('"pageshow"'):]
    handler = handler[:handler.index("});") + 3]
    assert re.search(r"if\s*\(\s*\w+\.persisted\s*\)", handler)


def test_every_kind_of_page_loads_app_js_without_inline_script(app, buyer, rag, admin_client):
    anonymous = app.test_client()
    pages = [(buyer, "/"), (buyer, "/catalogue"), (buyer, f"/p/{rag.slug}"), (buyer, "/cart"), (buyer, "/orders"),
             (anonymous, "/login"), (anonymous, "/register"), (buyer, "/no-such-page"), (anonymous, "/no-such-page")]
    for client, path in pages:
        html = client.get(path).get_data(as_text=True)
        assert 'src="/static/js/app.js"' in html, path
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), f"inline script on {path}"
    for path in ("/admin", "/admin/orders", "/admin/products"):
        html = admin_client.get(path).get_data(as_text=True)
        assert 'src="/static/js/app.js"' in html and not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), path


def test_signed_in_responses_vary_on_the_cookie_explicitly(buyer):
    resp = buyer.get("/catalogue")
    assert "Cookie" in resp.headers["Vary"] and resp.headers["Cache-Control"] == "no-store"
