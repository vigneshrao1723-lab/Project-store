from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask import session
from flask_wtf.csrf import CSRFProtect, generate_csrf

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = "Sign in to continue."
login_manager.login_message_category = "info"


def stable_csrf_token():
    """The CSRF token for templates: one signed value per session token instead of a new timestamp each second.

    Flask-WTF signs the session's secret with the current time, so two pages rendered a second apart carry
    different tokens even though both validate. Reusing the first signed value keeps pages byte-identical for the
    same visitor and is exactly as strong, because validation checks the secret in the session, not the timestamp.
    A new session (sign-in clears it) gets a new secret and so a new token.
    """
    token = generate_csrf()                       # creates session["csrf_token"] when missing
    secret = session["csrf_token"]
    if session.get("csrf_signed_for") == secret and session.get("csrf_signed"):
        return session["csrf_signed"]
    session["csrf_signed_for"], session["csrf_signed"] = secret, token
    return token
