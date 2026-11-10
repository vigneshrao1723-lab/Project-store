"""Five failed sign-ins for one email from one IP block that pair for ten minutes."""
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import LoginThrottle
from app.services import login_throttle

from .conftest import make_user

LOCKED = "Too many failed sign-in attempts. Try again in 10 minutes."


class Clock:
    """A clock the test can move, so ten minutes pass instantly."""

    def __init__(self):
        self.now = datetime(2026, 1, 1, 12, 0, 0)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


@pytest.fixture()
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(login_throttle, "utcnow", c)
    return c


def attempt(client, email="buyer@example.com", password="wrong-password", ip="10.0.0.1"):
    return client.post("/login", data={"email": email, "password": password},
                       environ_base={"REMOTE_ADDR": ip})


def fail_times(client, n, **kw):
    return [attempt(client, **kw) for _ in range(n)]


def signed_in(client):
    return client.get("/orders").status_code == 200


def test_first_four_failures_get_the_normal_message(client, user, clock):
    for r in fail_times(client, 4):
        assert r.status_code == 200
        assert b"don&#39;t match" in r.data or b"don't match" in r.data
        assert b"Too many" not in r.data


def test_fifth_failure_blocks_with_a_clear_message(client, user, clock):
    *_, fifth = fail_times(client, 5)
    assert fifth.status_code == 429
    assert LOCKED in fifth.get_data(as_text=True)
    assert fifth.headers["Retry-After"] == "600"
    # And the next try is refused too.
    sixth = attempt(client)
    assert sixth.status_code == 429 and LOCKED in sixth.get_data(as_text=True)


def test_correct_password_is_refused_while_blocked(client, user, clock):
    fail_times(client, 5)
    r = attempt(client, password="correct-horse")
    assert r.status_code == 429 and LOCKED in r.get_data(as_text=True)
    assert not signed_in(client)


def test_block_lifts_after_ten_minutes(client, user, clock):
    fail_times(client, 5)
    clock.advance(minutes=9, seconds=59)
    assert attempt(client, password="correct-horse").status_code == 429
    clock.advance(seconds=1)
    r = attempt(client, password="correct-horse")
    assert r.status_code == 302 and signed_in(client)


def test_message_counts_down(client, user, clock):
    fail_times(client, 5)
    clock.advance(minutes=5)
    assert "Try again in 5 minutes." in attempt(client).get_data(as_text=True)
    clock.advance(minutes=4, seconds=30)
    assert "Try again in 1 minute." in attempt(client).get_data(as_text=True)


def test_after_the_block_the_count_starts_again(client, user, clock):
    fail_times(client, 5)
    clock.advance(minutes=10)
    first_after = attempt(client)
    assert first_after.status_code == 200          # a normal failure, not an instant re-block
    assert [r.status_code for r in fail_times(client, 3)] == [200, 200, 200]
    assert attempt(client).status_code == 429       # five failures since the block ended


def test_attempts_while_blocked_do_not_extend_the_block(client, user, clock):
    fail_times(client, 5)
    clock.advance(minutes=9)
    assert attempt(client).status_code == 429
    clock.advance(minutes=1)
    assert attempt(client, password="correct-horse").status_code == 302


def test_a_failure_that_loses_a_race_with_the_block_neither_counts_nor_extends_it(app, clock):
    """Two workers can both pass the "is it blocked?" check before either records its failure.
    The second one must find the block already in force and leave it alone."""
    for _ in range(5):
        login_throttle.record_failure("race@example.com", "10.0.0.1")
    clock.advance(minutes=9)
    assert login_throttle.record_failure("race@example.com", "10.0.0.1") == 60      # one minute left, not ten
    row = db.session.scalar(db.select(LoginThrottle).where(LoginThrottle.email == "race@example.com"))
    assert row.failures == 5
    assert row.locked_until == clock.now + timedelta(minutes=1)


def test_two_workers_inserting_the_same_pair_at_once_both_count(app, clock, monkeypatch):
    """Worker A reads "no row", worker B inserts it, then A's insert hits the unique constraint.
    A must fall back to B's row and add its failure to it, not crash and not lose the count."""
    login_throttle.record_failure("twin@example.com", "10.0.0.1")           # worker B's row now exists
    real_scalar, calls = db.session.scalar, []

    def stale_first_read(*a, **kw):
        calls.append(1)
        return None if len(calls) == 1 else real_scalar(*a, **kw)          # A's read happened "before" B's insert

    monkeypatch.setattr(db.session, "scalar", stale_first_read)
    login_throttle.record_failure("twin@example.com", "10.0.0.1")           # worker A
    monkeypatch.undo()

    rows = db.session.scalars(db.select(LoginThrottle).where(LoginThrottle.email == "twin@example.com")).all()
    assert len(rows) == 1 and rows[0].failures == 2


def test_block_is_per_email_and_per_ip(client, user, clock):
    make_user("other@example.com", name="Other")
    fail_times(client, 5)                                              # buyer@ from 10.0.0.1 is blocked
    assert attempt(client, ip="10.0.0.2").status_code == 200           # same email, different IP
    assert attempt(client, email="other@example.com").status_code == 200   # same IP, different email
    ok = attempt(client, ip="10.0.0.2", password="correct-horse")
    assert ok.status_code == 302                                       # the real owner on another network


def test_unknown_email_is_blocked_the_same_way(client, user, clock):
    """If only real accounts got blocked, the block itself would tell an attacker which emails exist."""
    ghost = [attempt(client, email="nobody@example.com") for _ in range(5)]
    real = fail_times(client, 5)
    assert [r.status_code for r in ghost] == [r.status_code for r in real] == [200, 200, 200, 200, 429]
    assert ghost[-1].get_data(as_text=True).count(LOCKED) == real[-1].get_data(as_text=True).count(LOCKED) == 1


def test_success_resets_the_count(client, user, clock):
    fail_times(client, 4)
    assert attempt(client, password="correct-horse").status_code == 302
    client.post("/logout")
    assert [r.status_code for r in fail_times(client, 4)] == [200] * 4


def test_old_failures_are_forgotten(client, user, clock):
    fail_times(client, 4)
    clock.advance(minutes=10)
    assert [r.status_code for r in fail_times(client, 4)] == [200] * 4   # would be a block if they added up


def test_email_is_matched_ignoring_case_and_spaces(client, user, clock):
    emails = ["buyer@example.com", "Buyer@Example.com", " buyer@example.com ", "BUYER@EXAMPLE.COM", "buyer@example.com"]
    codes = [attempt(client, email=e).status_code for e in emails]
    assert codes == [200, 200, 200, 200, 429]


def test_limit_follows_configuration(app, client, user, clock):
    app.config["LOGIN_MAX_ATTEMPTS"] = 2
    app.config["LOGIN_LOCKOUT_MINUTES"] = 3
    r1, r2 = fail_times(client, 2)
    assert r1.status_code == 200 and r2.status_code == 429
    assert "Try again in 3 minutes." in r2.get_data(as_text=True)


def test_sign_in_page_still_loads_while_blocked(client, user, clock):
    fail_times(client, 5)
    assert client.get("/login").status_code == 200


def test_stale_rows_are_pruned(app, client, user, clock):
    for i in range(3):
        attempt(client, email=f"someone{i}@example.com")
    assert db.session.scalar(db.select(db.func.count(LoginThrottle.id))) == 3
    clock.advance(minutes=11)
    attempt(client, email="fresh@example.com")
    emails = db.session.scalars(db.select(LoginThrottle.email)).all()
    assert emails == ["fresh@example.com"]


def test_lock_is_stored_in_the_database(app, client, user, clock):
    """A row, not process memory, so every gunicorn worker and a restart see the same block."""
    fail_times(client, 5)
    row = db.session.scalar(db.select(LoginThrottle).where(LoginThrottle.email == "buyer@example.com"))
    assert row.failures == 5 and row.ip == "10.0.0.1"
    assert row.locked_until == clock.now + timedelta(minutes=10)
