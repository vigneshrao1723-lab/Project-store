"""Error pages for the site and JSON errors for /api, so API clients never get an HTML page."""
from flask import jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

from .extensions import db
from .validation import InputError

API_MESSAGES = {
    400: "That request could not be understood.",
    401: "Sign in to continue.",
    403: "You can't do that.",
    404: "Not found.",
    405: "That method is not allowed here.",
    413: "The request is too large.",
    415: "Send the request as JSON.",
    429: "Too many requests. Wait a moment and try again.",
    500: "Something went wrong on our side.",
}


def _wants_json():
    return request.path.startswith("/api/")


def _json_error(message, status, fields=None):
    body = {"error": message}
    if fields:
        body["fields"] = fields
    return jsonify(body), status


def register_error_handlers(app):
    # Registered after csrf.init_app, so this replaces Flask-WTF's own CSRFError handler.
    @app.errorhandler(CSRFError)
    def csrf_failed(exc):
        if _wants_json():
            return _json_error("The security token is missing or has expired. Reload the page and try again.", 400)
        return exc.get_response()

    @app.errorhandler(InputError)
    def bad_input(exc):
        return _json_error(exc.message, exc.status, exc.fields)

    @app.errorhandler(HTTPException)
    def http_error(exc):
        if _wants_json():
            return _json_error(API_MESSAGES.get(exc.code, exc.name), exc.code)
        return exc

    @app.errorhandler(429)
    def too_many(exc):
        wait = getattr(exc, "retry_after", None) or 60
        minutes = max(1, -(-wait // 60))
        if _wants_json():
            resp = _json_error(API_MESSAGES[429] + f" Try again in {wait} seconds.", 429)
        else:
            resp = (render_template("error.html", code=429, title="Too many requests",
                                    message=f"Slow down. Try again in {minutes} minute{'s' if minutes != 1 else ''}."),
                    429)
        response = app.make_response(resp)
        response.headers["Retry-After"] = str(wait)
        return response

    @app.errorhandler(404)
    def not_found(exc):
        if _wants_json():
            return _json_error(API_MESSAGES[404], 404)
        return render_template("error.html", code=404, title="Page not found",
                               message="That page doesn't exist, or the project has been retired."), 404

    @app.errorhandler(500)
    def server_error(exc):
        db.session.rollback()
        if _wants_json():
            return _json_error(API_MESSAGES[500], 500)
        return render_template("error.html", code=500, title="Something broke on our side",
                               message="The error has been logged. Try again in a moment."), 500
