"""Security audit A3: errors."""

import json
import re

import pytest

from app import create_app
from app.config import TestConfig
from .helpers import _assert_no_internals, read


def test_a3_debug_is_off_by_default(monkeypatch):
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    assert create_app(TestConfig).debug is False


def test_a3_docker_runs_gunicorn_without_debug_or_reloader():
    dockerfile, compose, entry = read("Dockerfile"), read("docker-compose.yml"), read("docker-entrypoint.sh")
    cmd = re.search(r"^CMD (\[.*\])", dockerfile, re.M).group(1)
    assert json.loads(cmd)[0] == "gunicorn" and "--reload" not in cmd
    for name, text in (("Dockerfile", dockerfile), ("docker-compose.yml", compose), ("docker-entrypoint.sh", entry)):
        assert "FLASK_DEBUG" not in text and "flask run" not in text and "debug=True" not in text, name
    assert "app.run(" not in read("wsgi.py")


def test_a3_not_found_page_has_no_internals(live_client):
    _assert_no_internals(live_client.get("/no-such-page"), "404 page")


def test_a3_forced_500_page_has_no_internals(live_client):
    resp = live_client.get("/_boom")
    assert resp.status_code == 500
    _assert_no_internals(resp, "500 page")


def test_a3_database_error_500_page_has_no_sql_or_paths(live_app):
    from sqlalchemy.exc import OperationalError

    def explode():
        raise OperationalError("SELECT password_hash FROM users WHERE email='a'", {}, Exception("/srv/app/app/models.py:19"))

    live_app.view_functions["boom"] = explode
    resp = live_app.test_client().get("/_boom")
    assert resp.status_code == 500
    _assert_no_internals(resp, "500 page after a database error")


@pytest.mark.parametrize("method,path", [("delete", "/"), ("get", "/admin"), ("post", "/webhooks/razorpay")])
def test_a3_other_error_responses_have_no_internals(live_client, method, path):
    _assert_no_internals(getattr(live_client, method)(path), f"{method.upper()} {path}")
