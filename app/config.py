import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'store.db'}"
    )
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("COOKIE_SECURE", False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    # REMEMBER_COOKIE_SECURE follows SESSION_COOKIE_SECURE (see create_app), so one setting covers both cookies.

    # Both the session cookie and the remember-me cookie stop working after two weeks.
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)
    REMEMBER_COOKIE_DURATION = timedelta(days=14)

    # scrypt N, r, p at the OWASP minimum (N=2**17, r=8, p=1: 128 MiB and about 0.4 s a hash). Hashes made with
    # a lower cost are upgraded the next time that user signs in.
    PASSWORD_HASH_METHOD = "scrypt:131072:8:1"

    # Razorpay. With no key pair the store takes no payments, unless ALLOW_PRACTICE_GATEWAY is on.
    RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    # The practice gateway lets any signed-in buyer mark an order paid for nothing. It is for demos, local
    # development and tests only, so it must be switched on on purpose and never defaults on.
    ALLOW_PRACTICE_GATEWAY = _bool("ALLOW_PRACTICE_GATEWAY", False)

    # How long stock stays held for an unpaid order.
    RESERVATION_MINUTES = int(os.getenv("RESERVATION_MINUTES", "15"))
    MAX_QTY_PER_LINE = 5
    PAGE_SIZE = 9

    # Sign-in is blocked for LOGIN_LOCKOUT_MINUTES after LOGIN_MAX_ATTEMPTS failures from one email + IP.
    LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "10"))

    WTF_CSRF_TIME_LIMIT = None

    # Every form and JSON body here is a few hundred bytes. Larger requests get HTTP 413 before they are read.
    MAX_CONTENT_LENGTH = 1024 * 1024


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True} if os.getenv("TEST_DATABASE_URL") else {}
    WTF_CSRF_ENABLED = False
    RAZORPAY_KEY_ID = ""
    RAZORPAY_KEY_SECRET = ""
    RAZORPAY_WEBHOOK_SECRET = "whsec_test"
    ALLOW_PRACTICE_GATEWAY = True
