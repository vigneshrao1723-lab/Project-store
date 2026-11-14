import hmac
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app
from flask_login import UserMixin
from sqlalchemy import CheckConstraint, UniqueConstraint, false as sa_false
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


def utcnow():
    # Naive UTC keeps comparisons identical on SQLite and MySQL.
    return datetime.now(timezone.utc).replace(tzinfo=None)


# A real scrypt hash of a random password nobody knows, at the production cost. Sign-in checks an unknown email
# against it so "no such account" takes as long as "wrong password" and the response time reveals nothing.
# It is a literal, not computed, so no extra hash runs at start-up or on first use.
DUMMY_PASSWORD_HASH = ("scrypt:131072:8:1$OUajOQZmaEew8r9T$64285e6a83ab9f8a6cd13d3262e40f08660bc87b272b4ee56750ae34"
                       "ecd0291a743cd97b92dd4bc6758794ac24eac6443312bfd4ea6ece5b09e872e3b15271d1")


def new_session_token():
    return secrets.token_hex(16)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(190), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="customer")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    # Part of the id stored in the session and remember cookies. Changing it (sign-out, new password) makes
    # every cookie issued before the change worthless; see get_id() and load_user().
    session_token = db.Column(db.String(32), nullable=False, default=new_session_token, server_default="")

    cart_items = db.relationship("CartItem", back_populates="user", cascade="all, delete-orphan")
    orders = db.relationship("Order", back_populates="user", order_by="Order.id.desc()")

    @property
    def is_admin(self):
        return self.role == "admin"

    def get_id(self):
        if not self.session_token:          # an account from before session tokens existed
            self.session_token = new_session_token()
            db.session.commit()
        return f"{self.id}:{self.session_token}"

    def end_all_sessions(self):
        """Invalidate every session and remember-me cookie issued so far for this account."""
        self.session_token = new_session_token()

    def set_password(self, raw, end_sessions=True):
        self.password_hash = generate_password_hash(raw, method=current_app.config["PASSWORD_HASH_METHOD"])
        if end_sessions:                    # a new password signs the account out everywhere
            self.end_all_sessions()

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    def password_needs_rehash(self):
        """True if the stored hash is weaker than the configured method (cost raised since it was made)."""
        wanted = current_app.config["PASSWORD_HASH_METHOD"].split(":")
        have = self.password_hash.split("$", 1)[0].split(":")
        try:
            return [int(x) for x in have[1:]] < [int(x) for x in wanted[1:]] or have[0] != wanted[0]
        except ValueError:
            return True

    @staticmethod
    def spend_password_check_time(raw):
        """Do the work of checking a password for an account that does not exist."""
        check_password_hash(DUMMY_PASSWORD_HASH, raw)


@login_manager.user_loader
def load_user(session_id):
    """Resolve the id in a session cookie, which is "<user id>:<session token>". A cookie whose token no longer
    matches (the user signed out or changed password) or that has no token (issued before this existed) is
    not signed in."""
    user_id, _, token = str(session_id).partition(":")
    if not (user_id.isdigit() and token) or int(user_id) > 2**31 - 1:
        return None
    user = db.session.get(User, int(user_id))
    if user is None or not user.session_token or not hmac.compare_digest(user.session_token.encode(), token.encode()):
        return None
    return user


class LoginThrottle(db.Model):
    """Failed sign-in attempts for one email from one IP address; see services/login_throttle.py."""

    __tablename__ = "login_throttle"
    __table_args__ = (UniqueConstraint("email", "ip", name="uq_login_throttle_email_ip"),)

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(190), nullable=False)
    ip = db.Column(db.String(45), nullable=False)          # 45 characters fits any IPv6 address
    failures = db.Column(db.Integer, nullable=False, default=0)
    last_failure_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    locked_until = db.Column(db.DateTime)


class RateLimit(db.Model):
    """Hits on one rate-limited action by one client in the current window; see services/rate_limit.py."""

    __tablename__ = "rate_limits"
    __table_args__ = (UniqueConstraint("scope", "key", name="uq_rate_limits_scope_key"),)

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(32), nullable=False)       # "register", "checkout", "verify", "login_ip"
    key = db.Column(db.String(190), nullable=False)        # "user:7" or "ip:203.0.113.9"
    hits = db.Column(db.Integer, nullable=False, default=0)
    window_start = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    slug = db.Column(db.String(80), nullable=False, unique=True, index=True)
    cover_kind = db.Column(db.String(16), nullable=False, default="web")

    products = db.relationship("Product", back_populates="category")


class Product(db.Model):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("stock >= 0", name="ck_product_stock_nonneg"),
        CheckConstraint("price_paise >= 0", name="ck_product_price_nonneg"),
    )

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True)
    slug = db.Column(db.String(120), nullable=False, unique=True, index=True)
    title = db.Column(db.String(160), nullable=False)
    tagline = db.Column(db.String(255), nullable=False, default="")
    description = db.Column(db.Text, nullable=False, default="")
    tech = db.Column(db.String(255), nullable=False, default="")
    includes = db.Column(db.Text, nullable=False, default="")
    delivery_url = db.Column(db.String(500), nullable=False, default="")
    price_paise = db.Column(db.Integer, nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    featured = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    # How to install, run and test the project: plain text with a small safe markdown subset (services/guide.py).
    setup_guide = db.Column(db.Text, nullable=True, default="")          # nullable: MySQL allows no default on TEXT
    # True once an admin has edited the guide, so `flask seed` never overwrites it.
    guide_edited = db.Column(db.Boolean, nullable=False, default=False, server_default=sa_false())

    category = db.relationship("Category", back_populates="products")

    @property
    def tech_list(self):
        return [t.strip() for t in self.tech.split(",") if t.strip()]

    @property
    def includes_list(self):
        return [t.strip() for t in self.includes.splitlines() if t.strip()]

    @property
    def paragraphs(self):
        return [p.strip() for p in self.description.split("\n\n") if p.strip()]

    @property
    def code(self):
        return f"PS-{self.id:03d}"

    @property
    def available(self):
        return self.is_active and self.stock > 0


class CartItem(db.Model):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_cart_user_product"),
        CheckConstraint("qty > 0", name="ck_cart_qty_pos"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    qty = db.Column(db.Integer, nullable=False, default=1)

    user = db.relationship("User", back_populates="cart_items")
    product = db.relationship("Product")


ORDER_STATUSES = ("pending", "paid", "cancelled", "expired", "failed", "refund_due", "refunded")

_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_public_id():
    return "PS-" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(7))


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(16), nullable=False, unique=True, index=True, default=new_public_id)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, default="pending", index=True)
    billing_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(24), nullable=False, default="")
    total_paise = db.Column(db.Integer, nullable=False)
    gateway_order_id = db.Column(db.String(64), index=True)
    gateway_payment_id = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    paid_at = db.Column(db.DateTime)
    # Where the invoice and setup guide go once the order is paid: "email", "whatsapp" or "" (no messages).
    # contact_value is the raw address or E.164 number; it is never logged and anonymise_order() blanks it.
    contact_channel = db.Column(db.String(16), nullable=False, default="", server_default="")
    contact_value = db.Column(db.String(190), nullable=False, default="", server_default="")
    contact_consent_at = db.Column(db.DateTime)

    user = db.relationship("User", back_populates="orders")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    @property
    def is_paid(self):
        return self.status == "paid"

    @property
    def is_open(self):
        return self.status == "pending"

    @staticmethod
    def new_expiry(minutes):
        return utcnow() + timedelta(minutes=minutes)


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    unit_price_paise = db.Column(db.Integer, nullable=False)
    qty = db.Column(db.Integer, nullable=False)

    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product")

    @property
    def line_paise(self):
        return self.unit_price_paise * self.qty


class InventoryLog(db.Model):
    """Append-only ledger of every stock change, so stock can always be reconciled."""

    __tablename__ = "inventory_log"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"))
    delta = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(40), nullable=False)
    note = db.Column(db.String(190), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    product = db.relationship("Product")


class ContactMessage(db.Model):
    """A message sent with the contact form. Shown to admins as plain text; never logged."""

    __tablename__ = "contact_messages"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(60), nullable=False)
    last_name = db.Column(db.String(60), nullable=False, default="")
    email = db.Column(db.String(190), nullable=False)
    subject = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)
    consent = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    handled_at = db.Column(db.DateTime)


MESSAGE_STATUSES = ("queued", "sent", "failed", "not_configured")


class Message(db.Model):
    """The outbox: one message per order, kind and channel (the unique key makes a repeated payment confirmation
    a no-op). Delivery happens after the payment has committed, so a failed send can never undo a payment."""

    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("order_id", "kind", "channel", name="uq_messages_order_kind_channel"),)

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    kind = db.Column(db.String(24), nullable=False)          # "order_paid"
    channel = db.Column(db.String(16), nullable=False)       # "email" or "whatsapp"
    to_value = db.Column(db.String(190), nullable=False, default="")     # raw recipient; blanked by anonymise_order
    to_hash = db.Column(db.String(64), nullable=False, index=True)       # keyed hash of the recipient, kept for limits
    subject = db.Column(db.String(200), nullable=False, default="")
    body_text = db.Column(db.Text, nullable=False, default="")
    body_html = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(16), nullable=False, default="queued", index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.String(200), nullable=False, default="")
    next_attempt_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    sent_at = db.Column(db.DateTime)

    order = db.relationship("Order", backref=db.backref("messages", order_by="Message.id"))


class ContactOptOut(db.Model):
    """A contact (email or number) that asked to receive no more messages. Only a keyed hash is stored."""

    __tablename__ = "contact_optouts"

    id = db.Column(db.Integer, primary_key=True)
    value_hash = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

