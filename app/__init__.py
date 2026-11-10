import os
from pathlib import Path

import click
from flask import Flask, render_template
from markupsafe import Markup

from .config import Config
from .covers import cover_svg
from .extensions import csrf, db, login_manager


def inr(paise):
    """12349900 -> '₹1,23,499' (Indian digit grouping)."""
    rupees, p = divmod(int(paise), 100)
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return f"₹{s}" + (f".{p:02d}" if p else "")


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(config or Config)

    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///") and not app.testing:
        Path(app.instance_path).mkdir(parents=True, exist_ok=True)
        Path(app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)

    if not app.testing and not app.debug and app.config["SECRET_KEY"] == "dev-only-change-me" \
            and os.getenv("FLASK_ENV") == "production":
        raise RuntimeError("Set SECRET_KEY before running in production.")

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    app.jinja_env.filters["inr"] = inr
    app.jinja_env.globals["cover"] = lambda p: Markup(cover_svg(p.slug, p.category.cover_kind, p.title))

    from .blueprints import account, admin, api, auth, cart, checkout, shop, webhooks

    for bp in (shop.bp, auth.bp, cart.bp, checkout.bp, account.bp, admin.bp, api.bp, webhooks.bp):
        app.register_blueprint(bp)
    csrf.exempt(webhooks.bp)

    from .context import register_context
    register_context(app)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' https://checkout.razorpay.com; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; img-src 'self' data:; "
            "frame-src https://api.razorpay.com https://checkout.razorpay.com; "
            "connect-src 'self' https://lumberjack.razorpay.com https://api.razorpay.com; "
            "form-action 'self'; base-uri 'self'",
        )
        return resp

    @app.errorhandler(404)
    def not_found(_):
        return render_template("error.html", code=404, title="Page not found",
                               message="That page doesn't exist, or the project has been retired."), 404

    @app.errorhandler(500)
    def server_error(_):
        db.session.rollback()
        return render_template("error.html", code=500, title="Something broke on our side",
                               message="The error has been logged. Try again in a moment."), 500

    register_cli(app)
    return app


def register_cli(app):
    from .seed import seed_catalogue
    from .models import User
    from .services.orders import release_expired

    @app.cli.command("init-db")
    def init_db():
        """Create all tables."""
        db.create_all()
        click.echo("Tables created.")

    @app.cli.command("seed")
    @click.option("--if-empty", is_flag=True, help="Only seed when there are no products.")
    def seed(if_empty):
        """Load the catalogue and a demo admin account."""
        db.create_all()
        created = seed_catalogue(only_if_empty=if_empty)
        click.echo("Seeded." if created else "Catalogue already present, skipped.")

    @app.cli.command("create-admin")
    @click.argument("email")
    @click.password_option()
    @click.option("--name", default="Admin")
    def create_admin(email, password, name):
        """Create or promote an admin account."""
        user = db.session.scalar(db.select(User).where(User.email == email.lower()))
        if user is None:
            user = User(name=name, email=email.lower())
            db.session.add(user)
        user.role = "admin"
        user.set_password(password)
        db.session.commit()
        click.echo(f"Admin ready: {user.email}")

    @app.cli.command("release-expired")
    def release_expired_cmd():
        """Free stock held by unpaid orders (run from cron)."""
        click.echo(f"Released {release_expired()} expired order(s).")
