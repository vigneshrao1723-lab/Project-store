"""Response headers, cover-art escaping and the Docker/ignore files, beyond what the audit tests pin down."""
import re
from pathlib import Path

import pytest

from app import create_app
from app.config import TestConfig
from app.covers import cover_svg

ROOT = Path(__file__).resolve().parent.parent


def csp(client, path="/"):
    policy = client.get(path).headers["Content-Security-Policy"]
    return {p.split()[0]: p.split()[1:] for p in policy.split(";") if p.strip()}


def test_csp_blocks_framing_forms_and_base_tag_changes(client):
    d = csp(client)
    assert d["frame-ancestors"] == ["'self'"] and d["form-action"] == ["'self'"] and d["base-uri"] == ["'self'"]
    assert d["default-src"] == ["'self'"] and "'unsafe-inline'" not in d["script-src"]


def test_permissions_policy_turns_off_what_the_site_never_uses(client):
    policy = client.get("/").headers["Permissions-Policy"]
    for feature in ("camera", "microphone", "geolocation", "usb"):
        assert f"{feature}=()" in policy
    assert 'payment=(self "https://checkout.razorpay.com"' in policy


def test_cross_origin_opener_policy_keeps_popups_working(client):
    assert client.get("/").headers["Cross-Origin-Opener-Policy"] == "same-origin-allow-popups"


def test_hsts_only_when_cookies_are_secure():
    secure = create_app(type("C", (TestConfig,), {"SESSION_COOKIE_SECURE": True}))
    with secure.app_context():
        from app.extensions import db
        db.create_all()
        assert secure.test_client().get("/healthz").headers["Strict-Transport-Security"] == "max-age=31536000"
        db.drop_all()
    plain = create_app(TestConfig)
    with plain.app_context():
        from app.extensions import db
        db.create_all()
        assert "Strict-Transport-Security" not in plain.test_client().get("/healthz").headers
        db.drop_all()


def test_signed_in_pages_are_no_store_and_public_pages_are_not(buyer, app):
    for path in ("/orders", "/cart", "/", "/catalogue", "/api/v1/cart", "/api/v1/products"):
        assert buyer.get(path).headers["Cache-Control"] == "no-store", path
    assert "no-store" not in buyer.get("/static/css/main.css").headers.get("Cache-Control", "")
    anonymous = app.test_client()
    assert "no-store" not in anonymous.get("/").headers.get("Cache-Control", "")
    assert "no-store" not in anonymous.get("/catalogue").headers.get("Cache-Control", "")


def test_error_responses_for_signed_in_users_are_no_store_too(buyer):
    assert buyer.get("/no-such-page").headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("title", ['"><script>alert(1)</script>', "x' onmouseover='alert(1)", "</title><script>", "A & B"])
def test_cover_titles_are_escaped_in_the_title_element_and_the_attribute(title):
    svg = cover_svg("slug", "web", title)
    for raw in ("<script", "</title><script", "' onmouseover='", "<img"):
        assert raw not in svg
    assert svg.count("<title>") == 1 and svg.count("</title>") == 1
    assert svg.count("<svg") == 1


def test_cover_titles_keep_their_readable_text():
    assert "Smart Home SoC (FPGA)" in cover_svg("s", "hardware", "Smart Home SoC (FPGA)")
    assert "A &amp; B" in cover_svg("s", "web", "A & B")
    assert 'aria-label="Project cover drawing"' in cover_svg("s", "web", "")


def test_the_cover_helper_marks_only_the_finished_drawing_as_html(app, rag):
    rag.title = "<b>bold</b>"
    html = app.jinja_env.globals["cover"](rag)
    assert "<b>" not in html and "&lt;b&gt;" in html and html.startswith("<svg")


def test_compose_has_no_database_password_defaults_and_requires_them():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert ":-store" not in text and ":-root" not in text
    assert len(re.findall(r"\$\{DB_PASSWORD:\?", text)) == 3          # db, web and sweeper
    assert len(re.findall(r"\$\{DB_ROOT_PASSWORD:\?", text)) == 1
    assert "-p${" not in text


def test_env_example_lists_the_database_passwords_empty():
    values = dict(l.split("=", 1) for l in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
                  if "=" in l and not l.startswith("#"))
    assert values["DB_PASSWORD"] == "" and values["DB_ROOT_PASSWORD"] == ""
    assert "store:store@" not in (ROOT / ".env.example").read_text(encoding="utf-8")


def test_ignore_files_cover_the_usual_leaks():
    git = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    docker = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    for pattern in ("**/__pycache__/", "**/*.pyc", ".env.*", "!.env.example", ".venv/", ".vscode/", "*.db", "htmlcov/"):
        assert pattern in git, pattern
    for pattern in ("**/__pycache__", "**/*.pyc", ".env.*", ".venv", ".vscode", "**/*.db", "htmlcov"):
        assert pattern in docker, pattern
