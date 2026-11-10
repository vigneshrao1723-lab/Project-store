import re
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def safe_next(target):
    """Only allow same-site relative redirects."""
    if not target:
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
        if not EMAIL_RE.match(form["email"]):
            errors["email"] = "Enter a valid email address."
        elif db.session.scalar(db.select(User.id).where(User.email == form["email"])):
            errors["email"] = "An account with this email already exists. Sign in instead."
        if len(password) < 8:
            errors["password"] = "Use at least 8 characters."
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
        email = request.form.get("email", "").strip().lower()
        user = db.session.scalar(db.select(User).where(User.email == email))
        if user and user.check_password(request.form.get("password", "")):
            login_user(user, remember=bool(request.form.get("remember")))
            return redirect(safe_next(request.args.get("next")) or url_for("shop.home"))
        error = "That email and password don't match."
    return render_template("login.html", error=error, email=email)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You're signed out.", "info")
    return redirect(url_for("shop.home"))
