"""Helpers shared by the security audit tests."""

import hashlib
import hmac
import json
from pathlib import Path
import re

from flask import g

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import Order
from app.seed import seed_catalogue


ROOT = Path(__file__).resolve().parents[2]


APP_DIR = ROOT / "app"


def build_app(**overrides):
    attrs = {"SECRET_KEY": "audit-secret-" + "k" * 32, **overrides}      # >= 32 chars, not the default
    cfg = type("AuditConfig", (TestConfig,), attrs)
    application = create_app(cfg)

    @application.before_request
    def _fresh_login_cache():           # same reason as in conftest.py
        g.pop("_login_user", None)
        g.pop("csrf_token", None)     # the CSRF token is cached on g too; a real request starts with a fresh one

    return application


def _with_db(application):
    with application.app_context():
        db.create_all()
        seed_catalogue()
        yield application
        db.session.remove()
        db.drop_all()


def csrf_token(client):
    html = client.get("/login").get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def csrf_login(client, email="buyer@example.com", password="correct-horse"):
    return client.post("/login", data={"csrf_token": csrf_token(client), "email": email, "password": password})


def start_order(client, product, qty=1, name="Victim Person"):
    client.post("/api/v1/cart/items", json={"product_id": product.id, "qty": qty})
    r = client.post("/api/v1/checkout", json={"billing_name": name})
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()


def order_status(public_id):
    db.session.expire_all()
    return db.session.scalar(db.select(Order.status).where(Order.public_id == public_id))


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


LEAK_MARKERS = ["Traceback", "sqlalchemy", "SELECT ", "INSERT ", "FROM users", ".py", "/srv/app", "C:\\", "werkzeug",
                "jinja2", "ZeroDivisionError", "OperationalError", "Werkzeug Debugger"]


def _assert_no_internals(resp, label):
    body = resp.get_data(as_text=True)
    found = [m for m in LEAK_MARKERS if m in body]
    assert not found, f"{label} (HTTP {resp.status_code}) leaks {found}"


def _versions(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)==([^\s;#]+)", line.strip())
        if m:
            out[m.group(1).lower().replace("_", "-")] = m.group(2)
    return out


def _docker_pattern(pat):
    pat = pat.rstrip("/")
    out, i = "", 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pat.startswith("**", i):
            out += ".*"
            i += 2
        elif pat[i] == "*":
            out += "[^/]*"
            i += 1
        elif pat[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pat[i])
            i += 1
    return re.compile(out + r"\Z")


def _docker_ignored(patterns, path):
    """True if Docker leaves this path out of the build context (a matching directory excludes its contents)."""
    parts = path.split("/")
    prefixes = ["/".join(parts[:n]) for n in range(1, len(parts) + 1)]
    return any(_docker_pattern(p).match(prefix) for p in patterns for prefix in prefixes)


def _signed_webhook(client, body, secret="whsec_test"):
    raw = json.dumps(body).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/webhooks/razorpay", data=raw, headers={"X-Razorpay-Signature": sig}, content_type="application/json")


def _captured(order, **entity):
    ent = {"id": "pay_hook1", "order_id": order["payment"]["gateway_order_id"], "amount": order["total_paise"],
           "currency": "INR", "status": "captured"}
    ent.update(entity)
    return {"event": "payment.captured", "payload": {"payment": {"entity": ent}}}
