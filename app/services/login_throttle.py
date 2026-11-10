"""Sign-in throttling: too many failed attempts for one email from one IP address blocks sign-in for a while.

State lives in the `login_throttle` table, not in memory, so the limit holds across gunicorn workers and
survives restarts. One row per (email, ip):

* Each failed attempt adds one. If the previous failure was more than LOGIN_LOCKOUT_MINUTES ago the count
  starts again from zero, so slow, scattered typos never add up to a lock.
* The LOGIN_MAX_ATTEMPTS-th failure sets `locked_until`. While it is in the future the password is not
  checked at all (a correct password gets the same refusal), and further attempts do not extend the lock.
* A successful sign-in deletes the row.
* Unknown emails are counted exactly like real ones, so the lock does not reveal which emails have accounts.

The limit is per email AND IP: one address trying many different emails is not slowed by this.
"""
import math
from datetime import timedelta

from flask import current_app
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import LoginThrottle, utcnow


def _key(email, ip):
    return (email or "").strip().lower()[:190], (ip or "unknown")[:45]


def _same(email, ip):
    return LoginThrottle.email == email, LoginThrottle.ip == ip


def _remaining(row, now):
    """Whole seconds left on a lock, at least 1 while locked, 0 if not locked."""
    if row is not None and row.locked_until is not None and row.locked_until > now:
        return max(1, math.ceil((row.locked_until - now).total_seconds()))
    return 0


def seconds_locked(email, ip):
    """How long until this email + IP may try again; 0 means sign-in is allowed."""
    email, ip = _key(email, ip)
    row = db.session.scalar(db.select(LoginThrottle).where(*_same(email, ip)))
    return _remaining(row, utcnow())


def _row_for_update(email, ip, now):
    """The (email, ip) row, locked for this transaction; created if missing. Returns (row, created)."""
    query = db.select(LoginThrottle).where(*_same(email, ip)).with_for_update()
    row = db.session.scalar(query)
    if row is not None:
        return row, False
    row = LoginThrottle(email=email, ip=ip, failures=0, last_failure_at=now)
    db.session.add(row)
    try:
        db.session.flush()
        return row, True
    except IntegrityError:
        # Another worker inserted the same pair between our read and our insert. Use theirs.
        db.session.rollback()
        return db.session.scalar(query), False


def record_failure(email, ip):
    """Count one failed attempt. Returns the seconds of lock now in force, 0 if sign-in is still allowed."""
    cfg = current_app.config
    window = timedelta(minutes=cfg["LOGIN_LOCKOUT_MINUTES"])
    now = utcnow()
    email, ip = _key(email, ip)

    row, created = _row_for_update(email, ip, now)
    if created:
        # Forget pairs that have been quiet for longer than the window, so the table cannot grow forever.
        db.session.execute(db.delete(LoginThrottle).where(
            LoginThrottle.last_failure_at < now - window, LoginThrottle.id != row.id))

    wait = _remaining(row, now)
    if wait:                                  # already locked: do not count it and do not extend the lock
        db.session.rollback()
        return wait

    if now - row.last_failure_at >= window:   # quiet for a full window (or a finished lock): start again
        row.failures = 0
        row.locked_until = None
    row.failures += 1
    row.last_failure_at = now
    if row.failures >= cfg["LOGIN_MAX_ATTEMPTS"]:
        row.locked_until = now + window
    wait = _remaining(row, now)
    db.session.commit()
    return wait


def clear(email, ip):
    """A successful sign-in wipes the failure count for this email + IP."""
    email, ip = _key(email, ip)
    db.session.execute(db.delete(LoginThrottle).where(*_same(email, ip)))
    db.session.commit()


def lock_message(seconds):
    minutes = max(1, math.ceil(seconds / 60))
    unit = "minute" if minutes == 1 else "minutes"
    return f"Too many failed sign-in attempts. Try again in {minutes} {unit}."
