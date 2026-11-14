"""Input checks shared by the web forms and the JSON API.

Every number that arrives from a client is parsed here, with explicit bounds, so a wrong type, an absurd size or a
non-finite float becomes a 4xx answer and never an unhandled exception. Every text field has a length cap that
matches its column.
"""
import math
import re
from decimal import Decimal, InvalidOperation

from flask import request

INT32_MAX = 2**31 - 1

# Column sizes (see models.py).
MAX_NAME = 120
MAX_EMAIL = 190
MAX_PHONE = 24
MAX_TITLE = 160
MAX_SLUG = 120
MAX_TAGLINE = 255
MAX_TECH = 255
MAX_URL = 500
MAX_NOTE = 190
MAX_LONG_TEXT = 20_000      # description and includes are TEXT columns; this keeps one product page sane
MAX_SEARCH = 100
MAX_CATEGORY_SLUG = 80

MAX_PASSWORD = 128          # scrypt runs on whatever is sent, so the length has to be bounded
MIN_PASSWORD = 8

MAX_PAGE = 1000
MAX_REQUEST_QTY = 1000      # anything above the per-line cap is clamped to it; this only rejects nonsense
MAX_STOCK = 100_000
MAX_STOCK_DELTA = 100_000
MAX_PRICE_PAISE = 10_000_000    # Rs 1,00,000 a project: five lines of it still fit a 32-bit order total


class InputError(ValueError):
    """A client sent something unusable. ``status`` is the HTTP status to answer with."""

    def __init__(self, message, status=400, fields=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.fields = fields


def whole_number(value, lo, hi, label="This value"):
    """Parse an int from JSON (int, integral float or digit string). Booleans, NaN, infinities, fractions,
    lists, objects and out-of-range values raise InputError."""
    problem = InputError(f"{label} must be a whole number from {lo} to {hi}.")
    if isinstance(value, bool):
        raise problem
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        if not math.isfinite(value) or value != int(value):
            raise problem
        number = int(value)
    elif isinstance(value, str) and re.fullmatch(r"\s*[+-]?\d{1,30}\s*", value):
        number = int(value)
    else:
        raise problem
    if not lo <= number <= hi:
        raise problem
    return number


def rupees_to_paise(value, label="The price"):
    """Rupees (a string or a JSON number) to integer paise, without floats. At most two decimal places."""
    problem = InputError(f"{label} must be between 0 and {MAX_PRICE_PAISE // 100:,} rupees, with at most two decimals.")
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise problem
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation:
        raise problem from None
    if not amount.is_finite() or amount < 0 or amount > Decimal(MAX_PRICE_PAISE) / 100:
        raise problem
    if amount.normalize().as_tuple().exponent < -2:
        raise problem
    return int(amount.scaleb(2))


def text(value, max_len, label="This field", required=False, default=""):
    """A stripped string no longer than ``max_len``. Non-strings are rejected rather than converted."""
    if value is None:
        value = default
    if not isinstance(value, str):
        raise InputError(f"{label} must be text.")
    value = value.strip()
    if required and not value:
        raise InputError(f"{label} is required.")
    if len(value) > max_len:
        raise InputError(f"{label} must be at most {max_len} characters.")
    return value


def clean_query(value, max_len=MAX_SEARCH):
    """Search text from a URL: cut to the cap instead of failing, so a long paste still searches."""
    return (value or "")[:max_len]


def page_number(value):
    """A page from the query string, kept inside 1..MAX_PAGE."""
    try:
        return max(1, min(int(value), MAX_PAGE))
    except (TypeError, ValueError):
        return 1


def json_body():
    """The request's JSON object, or an empty dict when there is no body. Anything else (an array, a string, a
    number, ``null`` or malformed JSON) is a 400, so the routes only ever see a dict."""
    if not request.get_data(cache=True).strip():
        return {}
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise InputError("Send a JSON object.", 400)
    return body


# ---- contact form and order contact choice (v1.3) -------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_FIRST_NAME = 60
MAX_SUBJECT = 160
MAX_MESSAGE = 5000
_LINE_BREAKS = re.compile(r"[\r\n\u2028\u2029\x00]")


def has_line_break(value):
    """True if a one-line field carries a line break (or a NUL): the start of an email header injection."""
    return bool(_LINE_BREAKS.search(value or ""))


def valid_email(value):
    return bool(value) and len(value) <= MAX_EMAIL and EMAIL_RE.match(value) is not None and not has_line_break(value)


def normalise_whatsapp(raw):
    """An Indian 10-digit mobile number (6 to 9 first) or an international number in +country form, as E.164.

    Spaces, dashes, dots and brackets are ignored. Raises InputError for anything else."""
    problem = InputError("Enter a 10-digit mobile number, or the full number starting with + and the country code.")
    value = re.sub(r"[\s\-().]", "", raw or "")
    if not value or len(value) > 20 or has_line_break(raw or ""):
        raise problem
    if value.startswith("00"):
        value = "+" + value[2:]
    if value.startswith("+"):
        digits = value[1:]
        if not re.fullmatch(r"[1-9]\d{7,14}", digits):
            raise problem
        if digits.startswith("91") and not re.fullmatch(r"91[6-9]\d{9}", digits):
            raise problem
        return "+" + digits
    if re.fullmatch(r"0?[6-9]\d{9}", value):
        return "+91" + value[-10:]
    if re.fullmatch(r"91[6-9]\d{9}", value):
        return "+" + value
    raise problem


def contact_form(form):
    """Check the contact form. Returns (data, errors); errors maps a field to its message."""
    data = {k: (form.get(k) or "").strip() for k in ("first_name", "last_name", "email", "subject", "message")}
    data["email"] = data["email"].lower()
    data["consent"] = form.get("consent") in ("on", "yes", "1", "true")
    errors = {}
    for key, label, cap, required in (("first_name", "your first name", MAX_FIRST_NAME, True),
                                      ("last_name", "your last name", MAX_FIRST_NAME, False),
                                      ("subject", "a subject", MAX_SUBJECT, True)):
        if required and not data[key]:
            errors[key] = f"Enter {label}."
        elif len(data[key]) > cap:
            errors[key] = f"Use at most {cap} characters."
        elif has_line_break(data[key]):
            errors[key] = "Keep this to one line."
    if not valid_email(data["email"]):
        errors["email"] = "Enter a valid email address."
    if not data["message"]:
        errors["message"] = "Write your message."
    elif len(data["message"]) > MAX_MESSAGE:
        errors["message"] = f"Use at most {MAX_MESSAGE:,} characters."
    if not data["consent"]:
        errors["consent"] = "Tick the box so we may reply to you."
    for key in ("first_name", "last_name", "email", "subject"):
        data[key] = data[key][:MAX_SUBJECT]
    data["message"] = data["message"][:MAX_MESSAGE]
    return data, errors
