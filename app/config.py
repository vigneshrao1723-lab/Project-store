import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name, default=False):
    raw = os.getenv(name, "").strip().lower()
    if not raw:                      # unset or empty (docker compose passes empty values through): the default
        return default
    return raw in {"1", "true", "yes", "on"}


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

    # Per client and window: (allowed hits, window in seconds). Past the limit the answer is HTTP 429 with a
    # Retry-After header until the window ends. "login_ip" counts failed sign-ins from one address across all
    # emails (the per-email limit below is separate). See services/rate_limit.py.
    RATE_LIMITS = {
        "register": (10, 3600),
        "checkout": (10, 600),
        "verify": (20, 600),
        "login_ip": (20, 600),
        "contact_ip": (10, 3600),          # the contact form, per address
        "contact_email": (3, 3600),        # the contact form, per sender email
        "notify_ip": (10, 86400),          # checkouts that ask for an invoice by email or WhatsApp, per address per day
        "notify_user": (5, 86400),         # the same, per account per day
    }

    # Sign-in is blocked for LOGIN_LOCKOUT_MINUTES after LOGIN_MAX_ATTEMPTS failures from one email + IP.
    LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "10"))

    # Contact details shown on the contact block and /contact. Each comes only from the environment; an empty one is
    # simply not shown. Nothing personal is written in the repository.
    CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "").strip()
    CONTACT_PHONE = os.getenv("CONTACT_PHONE", "").strip()
    CONTACT_CITY = os.getenv("CONTACT_CITY", "").strip()
    CONTACT_GITHUB = os.getenv("CONTACT_GITHUB", "").strip()
    CONTACT_LINKEDIN = os.getenv("CONTACT_LINKEDIN", "").strip()

    # Seller details printed on invoices. No tax line is shown unless SELLER_GSTIN is set.
    SELLER_NAME = os.getenv("SELLER_NAME", "").strip() or "Project Store"
    SELLER_ADDRESS = os.getenv("SELLER_ADDRESS", "").strip()
    SELLER_GSTIN = os.getenv("SELLER_GSTIN", "").strip()

    # Order messages (docs/NOTIFICATIONS.md). Email goes over SMTP with STARTTLS; WhatsApp over the Meta Cloud API with
    # an approved template. With neither configured, messages are kept in the outbox for the admin to read.
    SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
    SMTP_PORT = int(os.getenv("SMTP_PORT") or "587")
    SMTP_USER = os.getenv("SMTP_USER", "").strip()
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "").strip()
    SMTP_STARTTLS = _bool("SMTP_STARTTLS", True)
    WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    WHATSAPP_TEMPLATE_NAME = os.getenv("WHATSAPP_TEMPLATE_NAME", "").strip()
    WHATSAPP_LANG = os.getenv("WHATSAPP_LANG", "").strip() or "en"
    WHATSAPP_API_BASE = os.getenv("WHATSAPP_API_BASE", "").strip() or "https://graph.facebook.com/v19.0"
    # Absolute links inside messages (invoice, guide, order page, stop) start with this, e.g. https://store.example.com
    PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL", "").strip() or "http://localhost:8000").rstrip("/")
    MESSAGE_LINK_DAYS = 7
    MESSAGE_MAX_ATTEMPTS = 5
    MESSAGES_PER_CONTACT_PER_DAY = 3

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
    SMTP_HOST = ""
    WHATSAPP_TOKEN = ""
    CONTACT_EMAIL = ""
    CONTACT_PHONE = ""
    CONTACT_CITY = ""
    CONTACT_GITHUB = ""
    CONTACT_LINKEDIN = ""
    PUBLIC_BASE_URL = "http://localhost"
