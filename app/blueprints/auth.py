import re
from urllib.parse import urlparse

from flask import Blueprint, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User
from ..services import login_throttle
from ..validation import MAX_EMAIL, MAX_NAME, MAX_PASSWORD, MIN_PASSWORD

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_NEXT_LENGTH = 2000


def safe_next(target):
    """Only allow same-site relative redirects. Control characters (a line break would split the Location
    header, a NUL or tab confuses URL parsers) and very long values fall back to the default page."""
    if not target or len(target) > MAX_NEXT_LENGTH or any(ord(c) < 32 or ord(c) == 127 for c in target):
        return None
    u = urlparse(target)
    if u.scheme or u.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("shop.home"))
    errors = {}
    form = {"name": "", "email": ""}
    if request.method == "POST":
        form["name"] = request.form.get("name", "").strip()
        form["email"] = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not form["name"]:
            errors["name"] = "Enter your name."
        elif len(form["name"]) > MAX_NAME:
            errors["name"] = f"Use at most {MAX_NAME} characters."
        if len(form["email"]) > MAX_EMAIL or not EMAIL_RE.match(form["email"]):
            errors["email"] = "Enter a valid email address."
        elif db.session.scalar(db.select(User.id).where(User.email == form["email"])):
            errors["email"] = "An account with this email already exists. Sign in instead."
        if len(password) < MIN_PASSWORD:
            errors["password"] = f"Use at least {MIN_PASSWORD} characters."
        elif len(password) > MAX_PASSWORD:
            errors["password"] = f"Use at most {MAX_PASSWORD} characters."
        if not errors:
            user = User(name=form["name"], email=form["email"])
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Account created. You're signed in.", "success")
            return redirect(safe_next(request.args.get("next")) or url_for("shop.home"))
    return render_template("register.html", errors=errors, form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("shop.home"))
    error = None
    email = ""
    if request.method == "POST":
        typed = request.form.get("email", "").strip().lower()
        email = typed[:MAX_EMAIL]       # the throttle table's column holds no more
        password = request.form.get("password", "")
        ip = request.remote_addr
        wait = login_throttle.seconds_locked(email, ip)
        if not wait:   # while locked the password is not even checked, so a right guess gets no signal
            # No account has an address or a password longer than the limits, so those are never hashed.
            user = None
            if len(typed) <= MAX_EMAIL and len(password) <= MAX_PASSWORD:
                user = db.session.scalar(db.select(User).where(User.email == email))
            if user and user.check_password(password):
                login_throttle.clear(email, ip)
                login_user(user, remember=bool(request.form.get("remember")))
                return redirect(safe_next(request.args.get("next")) or url_for("shop.home"))
            wait = login_throttle.record_failure(email, ip)
        if wait:
            resp = make_response(render_template("login.html", error=login_throttle.lock_message(wait),
                                                 email=email), 429)
            resp.headers["Retry-After"] = str(wait)
            return resp
        error = "That email and password don't match."
    return render_template("login.html", error=error, email=email)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You're signed out.", "info")
    return redirect(url_for("shop.home"))
