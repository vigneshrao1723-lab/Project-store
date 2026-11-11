"""Security audit A2: secret and gateway."""

import re

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import Product
from app.seed import seed_catalogue
from ..conftest import login, make_user
from .helpers import build_app, order_status, read, start_order


def _create_with(secret, monkeypatch):
    monkeypatch.delenv("FLASK_ENV", raising=False)        # the check must not depend on FLASK_ENV
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    return create_app(type("C", (TestConfig,), {"TESTING": False, "SECRET_KEY": secret}))


def test_a2_default_secret_key_is_refused_outside_testing(monkeypatch):
    with pytest.raises((RuntimeError, ValueError)):
        _create_with("dev-only-change-me", monkeypatch)


@pytest.mark.parametrize("secret", ["short", "x" * 31, "", "change-me-to-a-long-random-string"])
def test_a2_weak_or_placeholder_secret_key_is_refused(secret, monkeypatch):
    with pytest.raises((RuntimeError, ValueError)):
        _create_with(secret, monkeypatch)


def test_a2_a_long_random_secret_key_is_accepted(monkeypatch):
    assert _create_with("9f2c" * 16, monkeypatch) is not None


def test_a2_env_example_contains_no_real_values():
    values = dict(l.split("=", 1) for l in read(".env.example").splitlines() if "=" in l and not l.startswith("#"))
    assert values["SECRET_KEY"].startswith("change-me")
    for k in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET", "ADMIN_PASSWORD"):
        assert values.get(k, "") == "", f"{k} has a value in .env.example"
    assert not re.search(r"rzp_(test|live)_[A-Za-z0-9]{8,}", read(".env.example"))


def test_a2_practice_gateway_must_be_switched_on_explicitly():
    """Without Razorpay keys the app silently enables /checkout/test-pay, which marks any order paid for free.
    A production deployment that forgets the keys must not give the store away. Required: the practice
    gateway runs only when ALLOW_PRACTICE_GATEWAY is true (tests and docker-compose can set it)."""
    application = build_app(TESTING=False, PROPAGATE_EXCEPTIONS=False, ALLOW_PRACTICE_GATEWAY=False,
                            RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    with application.app_context():
        db.create_all()
        seed_catalogue()
        make_user("shopper@example.com")
        c = application.test_client()
        login(c, "shopper@example.com")
        pid = start_order(c, db.session.scalar(db.select(Product).limit(1)))["id"]
        resp = c.post(f"/checkout/test-pay/{pid}", data={"outcome": "pay"})
        status = order_status(pid)
        db.session.remove()
        db.drop_all()
    assert status != "paid", f"order was marked paid with no payment (HTTP {resp.status_code}) on a keyless deployment"
