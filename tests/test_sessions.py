"""Session tokens, fresh sessions at sign-in, password cost and the stable CSRF token."""
import re

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import DUMMY_PASSWORD_HASH, User, load_user
from .conftest import login, make_user


def _cookie_names(resp):
    return [c.split("=", 1)[0] for c in resp.headers.getlist("Set-Cookie")]


def _signed_in_client(app, remember=False):
    c = app.test_client()
    data = {"email": "buyer@example.com", "password": "correct-horse"}
    if remember:
        data["remember"] = "on"
    assert c.post("/login", data=data).status_code == 302
    return c


def test_the_session_id_carries_the_users_token(app, user):
    assert user.get_id() == f"{user.id}:{user.session_token}"
    assert len(user.session_token) == 32


def test_cookies_without_a_matching_token_do_not_sign_anyone_in(app, user):
    assert load_user(f"{user.id}:{user.session_token}") is user
    for bad in (str(user.id), f"{user.id}:", f"{user.id}:wrong", f"{user.id}:{user.session_token}x", "x:y", ":",
                f"99999:{user.session_token}", f"{10 ** 30}:{user.session_token}", "é:é"):
        assert load_user(bad) is None, bad


def test_an_old_cookie_that_only_holds_the_user_id_is_refused(app, user):
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = str(user.id)             # what cookies looked like before session tokens
        s["_fresh"] = True
    assert c.get("/orders").status_code == 302


def test_signing_out_ends_every_session_of_the_account(app, user):
    laptop, phone = _signed_in_client(app), _signed_in_client(app)
    assert laptop.get("/orders").status_code == phone.get("/orders").status_code == 200
    laptop.post("/logout")
    assert laptop.get("/orders").status_code == 302
    assert phone.get("/orders").status_code == 302


def test_signing_out_also_defeats_a_copied_remember_me_cookie(app, user):
    c = _signed_in_client(app, remember=True)
    remember = c.get_cookie("remember_token").value
    c.post("/logout")
    thief = app.test_client()
    thief.set_cookie("remember_token", remember)
    assert thief.get("/orders").status_code == 302


def test_changing_the_password_ends_the_old_sessions(app, user):
    c = _signed_in_client(app)
    before = user.session_token
    user.set_password("a-new-password-1")
    db.session.commit()
    assert user.session_token != before
    assert c.get("/orders").status_code == 302


def test_a_new_password_can_skip_ending_sessions_for_a_rehash(app, user):
    before = user.session_token
    user.set_password("correct-horse", end_sessions=False)
    assert user.session_token == before


def test_sign_in_starts_a_new_session_and_drops_what_was_in_the_old_one(app, user):
    c = app.test_client()
    with c.session_transaction() as s:
        s["planted"] = "by an attacker"
        s["csrf_token"] = "old-secret"
    assert login(c).status_code == 302
    with c.session_transaction() as s:
        assert "planted" not in s and s.get("csrf_token") != "old-secret"
        assert s["_user_id"].startswith(f"{user.id}:")


def test_registering_also_starts_a_new_session(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s["planted"] = 1
    c.post("/register", data={"name": "New", "email": "new@example.com", "password": "long-enough-1"})
    with c.session_transaction() as s:
        assert "planted" not in s and "_user_id" in s


def test_remember_me_lasts_14_days_and_has_the_cookie_flags(app, user):
    app.config["REMEMBER_COOKIE_SECURE"] = True
    resp = app.test_client().post("/login", data={"email": "buyer@example.com", "password": "correct-horse",
                                                  "remember": "on"})
    cookie = next(c for c in resp.headers.getlist("Set-Cookie") if c.startswith("remember_token="))
    assert "Max-Age=1209600" in cookie or "Expires=" in cookie
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=Lax" in cookie


def test_remember_cookie_security_follows_the_session_cookie_setting():
    from app import create_app
    from app.config import TestConfig
    secure = create_app(type("C", (TestConfig,), {"SESSION_COOKIE_SECURE": True}))
    plain = create_app(TestConfig)
    assert secure.config["REMEMBER_COOKIE_SECURE"] is True and plain.config["REMEMBER_COOKIE_SECURE"] is False
    explicit = create_app(type("C", (TestConfig,), {"SESSION_COOKIE_SECURE": True, "REMEMBER_COOKIE_SECURE": False}))
    assert explicit.config["REMEMBER_COOKIE_SECURE"] is False


def test_the_production_hash_cost_is_the_owasp_minimum(app):
    method, n, r, p = app.config["PASSWORD_HASH_METHOD"].split(":")
    assert method == "scrypt" and int(r) >= 8 and int(n) * int(p) >= 2 ** 17


def test_the_dummy_hash_costs_the_same_as_a_real_one(app, user):
    """Otherwise an unknown email would still answer faster (or slower) than a wrong password."""
    assert DUMMY_PASSWORD_HASH.split("$", 1)[0] == app.config["PASSWORD_HASH_METHOD"]
    assert user.password_hash.split("$", 1)[0] == app.config["PASSWORD_HASH_METHOD"]
    assert not User(password_hash=DUMMY_PASSWORD_HASH).password_needs_rehash()


def test_old_cheaper_hashes_are_upgraded_at_the_next_sign_in_without_ending_sessions(app, user):
    user.password_hash = generate_password_hash("correct-horse", method="scrypt:32768:8:1")
    db.session.commit()
    assert user.password_needs_rehash()
    other_device = _signed_in_client(app)            # signs in (and is upgraded) once
    db.session.refresh(user)
    assert user.password_hash.startswith(app.config["PASSWORD_HASH_METHOD"] + "$")
    token = user.session_token
    _signed_in_client(app)
    db.session.refresh(user)
    assert user.session_token == token and other_device.get("/orders").status_code == 200


def test_legacy_hashes_of_other_kinds_are_marked_for_upgrade(app, user):
    for old in ("pbkdf2:sha256:600000$salt$abc", "garbage", "scrypt:x:y:z$s$h"):
        assert User(password_hash=old).password_needs_rehash(), old


def test_an_account_from_before_tokens_gets_one_when_it_signs_in(app):
    u = make_user("old@example.com")
    u.session_token = ""
    db.session.commit()
    assert load_user(f"{u.id}:") is None
    c = app.test_client()
    assert login(c, "old@example.com").status_code == 302
    assert c.get("/orders").status_code == 200 and u.session_token


def test_csrf_token_is_the_same_on_every_page_of_one_session_and_new_after_sign_in(app, user):
    c = app.test_client()
    meta = lambda path: re.search(r'name="csrf-token" content="([^"]+)"', c.get(path).get_data(as_text=True)).group(1)
    first = meta("/login")
    assert meta("/catalogue") == first
    login(c)
    assert meta("/orders") != first
