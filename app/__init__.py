from pathlib import Path

import click
from flask import Flask, abort, request
from markupsafe import Markup

from .config import BASE_DIR, Config
from .covers import cover_svg
from .extensions import csrf, db, login_manager, migrate


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


MIN_SECRET_KEY_LENGTH = 32
_PLACEHOLDER_MARKERS = ("dev-only", "change-me", "changeme", "change_me", "your-secret", "your_secret",
                        "replace-me", "placeholder", "test-secret", "example", "secret-key")


def secret_key_problem(key):
    """Why this SECRET_KEY must not be used outside tests and debug runs, or None if it is acceptable."""
    key = key or ""
    if len(key) < MIN_SECRET_KEY_LENGTH:
        return f"is shorter than {MIN_SECRET_KEY_LENGTH} characters"
    if any(m in key.lower() for m in _PLACEHOLDER_MARKERS):
        return "is a placeholder value"
    return None


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(config or Config)
    app.config.setdefault("REMEMBER_COOKIE_SECURE", app.config["SESSION_COOKIE_SECURE"])

    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///") and not app.testing:
        Path(app.instance_path).mkdir(parents=True, exist_ok=True)
        Path(app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)

    if not app.testing and not app.debug:
        problem = secret_key_problem(app.config["SECRET_KEY"])
        if problem:
            raise RuntimeError(f"SECRET_KEY {problem}. Generate one with: "
                               'python -c "import secrets; print(secrets.token_hex(32))"')

    db.init_app(app)
    # Absolute path, so `flask db ...` works from any directory. render_as_batch lets later migrations
    # alter tables on SQLite (local dev, CI smoke test); on MySQL it emits ordinary ALTER statements.
    migrate.init_app(app, db, directory=str(BASE_DIR / "migrations"), compare_type=True, render_as_batch=True)
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

    @app.before_request
    def reject_oversized_body():
        """Refuse a large upload before any route (or the sign-in check) touches it."""
        limit = app.config.get("MAX_CONTENT_LENGTH")
        if limit and request.content_length and request.content_length > limit:
            abort(413)

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

    from .errors import register_error_handlers
    register_error_handlers(app)

    register_cli(app)
    return app


def register_cli(app):
    from .seed import seed_admin, seed_catalogue
    from .models import User
    from .services.orders import release_expired

    @app.cli.command("adopt-legacy-db")
    def adopt_legacy_db():
        """Mark a database built before migrations existed as being at the baseline revision."""
        from .schema import adopt_legacy_database
        if adopt_legacy_database():
            click.echo("Existing database adopted: marked as migration 0001. Run `flask db upgrade` next.")
        else:
            click.echo("Nothing to adopt.")

    @app.cli.command("seed")
    @click.option("--if-empty", is_flag=True, help="Only seed when there are no products.")
    def seed(if_empty):
        """Load the catalogue and, if there is none, an admin account. Run `flask db upgrade` first."""
        from .schema import schema_is_present
        if not schema_is_present():
            raise click.ClickException("The database has no tables yet. Run `flask db upgrade` first.")
        created = seed_catalogue(only_if_empty=if_empty)
        click.echo("Seeded." if created else "Catalogue already present, skipped.")
        admin = seed_admin() if created else None
        if admin:
            email, generated = admin
            click.echo(f"Admin account created: {email}")
            if generated:
                click.echo(f"Generated admin password (shown only this once, so copy it now): {generated}")
            else:
                click.echo("Its password is the ADMIN_PASSWORD you set.")

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
