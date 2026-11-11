"""Database-backed rate limits for the actions an attacker would repeat: registering, starting a checkout,
confirming a payment and failing to sign in.

Same idea as login_throttle.py: the counters live in the `rate_limits` table, not in process memory, so the
limit holds across gunicorn workers and restarts. One row per (scope, client). It is a fixed window: the first
hit starts a window of the configured length, hits add to it, and once the window holds the allowed number
further hits are refused until it ends. The row is locked (SELECT ... FOR UPDATE) while it is read and
changed, so two workers cannot both slip under the limit.

Limits come from Config.RATE_LIMITS. A refusal is HTTP 429 with a Retry-After header (see errors.py).
"""
import math
from datetime import timedelta

from flask import current_app, request
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import TooManyRequests

from ..extensions import db
from ..models import RateLimit, utcnow

STALE_AFTER = timedelta(days=1)       # rows older than any window are deleted when a new row is made


def client_key():
    """Who is acting: the signed-in user, otherwise the connection's address (X-Forwarded-For is not trusted,
    because a client can forge it)."""
    if current_user.is_authenticated:
        return f"user:{current_user.id}"
    return f"ip:{request.remote_addr or 'unknown'}"


def ip_key():
    return f"ip:{request.remote_addr or 'unknown'}"


def _limit(scope):
    limit, seconds = current_app.config["RATE_LIMITS"][scope]
    return limit, timedelta(seconds=seconds)


def _wait(row, window, now):
    return max(1, math.ceil((row.window_start + window - now).total_seconds()))


def _locked_row(scope, key, now):
    query = db.select(RateLimit).where(RateLimit.scope == scope, RateLimit.key == key).with_for_update()
    row = db.session.scalar(query)
    if row is not None:
        return row, False
    row = RateLimit(scope=scope, key=key, hits=0, window_start=now)
    db.session.add(row)
    try:
        db.session.flush()
        return row, True
    except IntegrityError:                # another worker created it first: use theirs
        db.session.rollback()
        return db.session.scalar(query), False


def hit(scope, key):
    """Count one hit. Returns 0 if it is allowed, or the seconds to wait if the limit is already used up."""
    limit, window = _limit(scope)
    now = utcnow()
    row, created = _locked_row(scope, key, now)
    if created:
        db.session.execute(db.delete(RateLimit).where(RateLimit.window_start < now - STALE_AFTER,
                                                      RateLimit.id != row.id))
    if now - row.window_start >= window:        # the previous window is over: start a new one
        row.hits, row.window_start = 0, now
    if row.hits >= limit:
        wait = _wait(row, window, now)
        db.session.rollback()                   # releases the row lock; nothing was changed
        return wait
    row.hits += 1
    db.session.commit()
    return 0


def seconds_blocked(scope, key):
    """Seconds left if this client has used up the window, else 0. Counts nothing."""
    limit, window = _limit(scope)
    now = utcnow()
    row = db.session.scalar(db.select(RateLimit).where(RateLimit.scope == scope, RateLimit.key == key))
    if row is not None and now - row.window_start < window and row.hits >= limit:
        return _wait(row, window, now)
    return 0


def enforce(scope, key=None):
    """Count a hit for this client and refuse the request with HTTP 429 if the limit is used up."""
    wait = hit(scope, key or client_key())
    if wait:
        raise TooManyRequests(retry_after=wait)
