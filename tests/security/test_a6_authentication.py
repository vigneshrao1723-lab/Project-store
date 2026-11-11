"""Security audit A6: authentication."""

from datetime import timedelta
import hashlib
import re

from app.extensions import db
from app.models import User
from ..conftest import login, make_user
from .helpers import build_app, csrf_login, csrf_token


def _set_cookies(resp):
    return resp.headers.getlist("Set-Cookie")


def _count_scrypt(monkeypatch):
    calls = []
    real = hashlib.scrypt

    def counting(*a, **kw):
        calls.append(1)
        return real(*a, **kw)

    monkeypatch.setattr(hashlib, "scrypt", counting)
    return calls


def test_a6_minimum_password_length_is_enforced(client):
    r = client.post("/register", data={"name": "A", "email": "short@example.com", "password": "1234567"})
    assert db.session.scalar(db.select(User).where(User.email == "short@example.com")) is None


def test_a6_session_cookie_flags(app, user):
    login_resp = login(app.test_client(), "buyer@example.com")
    cookie = next(c for c in _set_cookies(login_resp) if c.startswith("session="))
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_a6_session_cookie_is_secure_when_configured():
    application = build_app(SESSION_COOKIE_SECURE=True, REMEMBER_COOKIE_SECURE=True)
    with application.app_context():
        db.create_all()
        make_user()
        resp = login(application.test_client(), "buyer@example.com")
        db.drop_all()
    assert "Secure" in next(c for c in _set_cookies(resp) if c.startswith("session="))


def test_a6_remember_me_cookie_has_the_same_flags_when_secure_cookies_are_configured():
    application = build_app(SESSION_COOKIE_SECURE=True)          # what COOKIE_SECURE=true sets today
    with application.app_context():
        db.create_all()
        make_user()
        resp = application.test_client().post("/login", data={"email": "buyer@example.com",
                                                             "password": "correct-horse", "remember": "on"})
        db.drop_all()
    remember = next((c for c in _set_cookies(resp) if c.startswith("remember_token=")), "")
    assert remember, "no remember_token cookie was set"
    missing = [f for f in ("HttpOnly", "Secure", "SameSite") if f not in remember]
    assert not missing, f"remember_token cookie lacks {missing}: {remember.split(';', 1)[1].strip()}"


def test_a6_session_and_remember_me_last_14_days(app):
    # Flask-Login falls back to 365 days when REMEMBER_COOKIE_DURATION is not configured.
    got = {"PERMANENT_SESSION_LIFETIME": app.config["PERMANENT_SESSION_LIFETIME"],
           "REMEMBER_COOKIE_DURATION": app.config.get("REMEMBER_COOKIE_DURATION", timedelta(days=365))}
    wrong = {k: str(v) for k, v in got.items() if v != timedelta(days=14)}
    assert not wrong, f"lifetimes should be 14 days but are {wrong}"


def test_a6_logout_invalidates_the_old_session_cookie(app, user):
    c = app.test_client()
    login(c, "buyer@example.com")
    stolen = c.get_cookie("session").value
    assert c.get("/orders").status_code == 200
    c.post("/logout")
    thief = app.test_client()
    thief.set_cookie("session", stolen)
    r = thief.get("/orders")
    assert r.status_code != 200, "a session cookie copied before logout still works after logout (stateless cookie sessions)"


def test_a6_a_cookie_planted_before_login_does_not_become_signed_in(app, user):
    attacker = app.test_client()
    attacker.get("/login")
    planted = attacker.get_cookie("session")
    victim = app.test_client()
    if planted:
        victim.set_cookie("session", planted.value)
    login(victim, "buyer@example.com")
    assert victim.get("/orders").status_code == 200
    assert attacker.get("/orders").status_code != 200


def test_a6_csrf_token_is_rotated_at_login(csrf_app):
    make_user()
    c = csrf_app.test_client()
    csrf_token(c)
    with c.session_transaction() as s:
        before = s.get("csrf_token")
    assert before
    assert csrf_login(c).status_code == 302
    with c.session_transaction() as s:
        after = s.get("csrf_token")
    assert after != before, "the pre-login CSRF token survives login (session is not cleared)"


def test_a6_login_error_is_identical_for_unknown_email_and_wrong_password(client, user):
    a = client.post("/login", data={"email": "nobody@example.com", "password": "whatever-1"})
    b = client.post("/login", data={"email": "buyer@example.com", "password": "whatever-1"})
    assert a.status_code == b.status_code == 200
    strip = lambda r: re.sub(r'value="[^"]*"', "", r.get_data(as_text=True))
    assert strip(a) == strip(b)


def test_a6_a13_unknown_email_login_still_runs_a_password_hash(client, user, monkeypatch):
    """Without it, 'unknown email' returns in microseconds and 'wrong password' takes ~100 ms: a timing oracle."""
    calls = _count_scrypt(monkeypatch)
    client.post("/login", data={"email": "buyer@example.com", "password": "wrong-password"})
    known = len(calls)
    calls.clear()
    client.post("/login", data={"email": "nobody@example.com", "password": "wrong-password"})
    assert known >= 1
    assert len(calls) == known, f"unknown email ran {len(calls)} hashes, known email ran {known}"
