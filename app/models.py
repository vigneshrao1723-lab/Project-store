import secrets
from datetime import datetime, timedelta, timezone

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


def utcnow():
    # Naive UTC keeps comparisons identical on SQLite and MySQL.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(190), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="customer")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    cart_items = db.relationship("CartItem", back_populates="user", cascade="all, delete-orphan")
    orders = db.relationship("Order", back_populates="user", order_by="Order.id.desc()")

    @property
    def is_admin(self):
        return self.role == "admin"

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


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
