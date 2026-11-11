"""The database-backed rate limits: windows, keys, the 429 answer and the per-address sign-in limit."""
from datetime import timedelta

import pytest

from app.extensions import db
from app.models import RateLimit, utcnow
from app.services import rate_limit

from .conftest import login, make_user


@pytest.fixture()
def tight(app):
    """Three hits a minute for registration and checkout; five failed sign-ins per address."""
    app.config["RATE_LIMITS"] = {"register": (3, 60), "checkout": (3, 60), "verify": (3, 60), "login_ip": (5, 60)}
    return app


def register(client, i):
    return client.post("/register", data={"name": "Bot", "email": f"bot{i}@example.com", "password": "long-enough-1"})


def test_hits_up_to_the_limit_pass_and_the_next_is_refused_with_the_seconds_left(tight):
    assert [rate_limit.hit("register", "ip:1") for _ in range(3)] == [0, 0, 0]
    wait = rate_limit.hit("register", "ip:1")
    # MySQL rounds a DATETIME to whole seconds, which can put the window start up to half a second ahead of the
    # clock, so the wait can come out as 61 for a 60 second window.
    assert 1 <= wait <= 61
    assert rate_limit.hit("register", "ip:1") > 0


def test_clients_and_scopes_have_separate_counters(tight):
    for _ in range(3):
        rate_limit.hit("register", "ip:1")
    assert rate_limit.hit("register", "ip:1") > 0
    assert rate_limit.hit("register", "ip:2") == 0
    assert rate_limit.hit("checkout", "ip:1") == 0


def test_a_new_window_starts_when_the_old_one_ends(tight, monkeypatch):
    for _ in range(3):
        rate_limit.hit("register", "ip:1")
    assert rate_limit.hit("register", "ip:1") > 0
    later = utcnow() + timedelta(seconds=61)
    monkeypatch.setattr("app.services.rate_limit.utcnow", lambda: later)
    assert rate_limit.hit("register", "ip:1") == 0
    row = db.session.scalar(db.select(RateLimit).where(RateLimit.key == "ip:1"))
    assert row.hits == 1 and abs(row.window_start - later) < timedelta(seconds=1)      # MySQL drops microseconds


def test_refused_hits_do_not_extend_the_window(tight):
    for _ in range(3):
        rate_limit.hit("register", "ip:1")
    start = db.session.scalar(db.select(RateLimit.window_start))
    for _ in range(5):
        rate_limit.hit("register", "ip:1")
    db.session.expire_all()
    row = db.session.scalar(db.select(RateLimit))
    assert row.hits == 3 and row.window_start == start


def test_stale_rows_are_deleted_when_a_new_one_is_made(tight, monkeypatch):
    db.session.add(RateLimit(scope="register", key="ip:old", hits=1, window_start=utcnow() - timedelta(days=3)))
    db.session.commit()
    rate_limit.hit("register", "ip:new")
    assert db.session.scalars(db.select(RateLimit.key)).all() == ["ip:new"]


def test_peek_counts_nothing(tight):
    for _ in range(5):
        assert rate_limit.seconds_blocked("login_ip", "ip:1") == 0
    assert db.session.scalar(db.select(db.func.count(RateLimit.id))) == 0
    for _ in range(5):
        rate_limit.hit("login_ip", "ip:1")
    assert rate_limit.seconds_blocked("login_ip", "ip:1") > 0


def test_registration_answers_429_with_retry_after_after_the_limit(tight):
    results = [register(tight.test_client(), i) for i in range(5)]        # a new visitor each time, one address
    assert [r.status_code for r in results] == [302, 302, 302, 429, 429]
    refused = results[3]
    assert int(refused.headers["Retry-After"]) >= 1
    assert "Too many requests" in refused.get_data(as_text=True)
    assert refused.headers["Content-Type"].startswith("text/html")


def test_the_registration_limit_is_per_address_not_global(tight):
    a, b = tight.test_client(), tight.test_client()
    for i in range(3):
        register(tight.test_client(), i)
    assert register(a, 50).status_code == 429
    b_response = b.post("/register", data={"name": "Bot", "email": "other@example.com", "password": "long-enough-1"},
                        environ_overrides={"REMOTE_ADDR": "203.0.113.9"})
    assert b_response.status_code == 302


def test_api_refusals_are_json_with_retry_after(tight, buyer):
    codes = [buyer.post("/api/v1/checkout", json={}) for _ in range(5)]
    refused = codes[-1]
    assert refused.status_code == 429 and refused.is_json and "Too many requests" in refused.get_json()["error"]
    assert int(refused.headers["Retry-After"]) >= 1


def test_checkout_and_verify_are_limited_per_user_not_per_address(tight, app, buyer):
    other = make_user("other@example.com")
    c2 = app.test_client()
    login(c2, "other@example.com")
    for _ in range(4):
        buyer.post("/api/v1/checkout", json={})
    assert buyer.post("/api/v1/checkout", json={}).status_code == 429
    assert c2.post("/api/v1/checkout", json={}).status_code != 429          # same address, another account
    for _ in range(4):
        buyer.post("/checkout/verify", data={"public_id": "PS-AAAAAAA"})
    assert buyer.post("/checkout/verify", data={"public_id": "PS-AAAAAAA"}).status_code == 429
    assert other.id


def test_sign_in_failures_from_one_address_are_limited_across_emails(tight, client, user):
    codes = [client.post("/login", data={"email": f"nobody{i}@example.com", "password": "guess-guess-1"}).status_code
             for i in range(8)]
    assert codes[:5] == [200] * 5 and set(codes[5:]) == {429}
    # Even the right password is refused while the address is blocked, so a lucky guess gives no signal.
    r = client.post("/login", data={"email": "buyer@example.com", "password": "correct-horse"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert "Too many failed sign-in attempts" in r.get_data(as_text=True)


def test_successful_sign_ins_do_not_count_toward_the_address_limit(tight, app, user):
    for _ in range(10):
        c = app.test_client()
        assert login(c).status_code == 302
    assert app.test_client().post("/login", data={"email": "x@example.com", "password": "nope-nope-1"}).status_code == 200


def test_the_default_limits_leave_room_for_normal_use(app):
    limits = app.config["RATE_LIMITS"]
    assert set(limits) == {"register", "checkout", "verify", "login_ip"}
    assert limits["checkout"][0] >= 5 and limits["verify"][0] >= 10 and limits["login_ip"][0] > app.config["LOGIN_MAX_ATTEMPTS"]
