"""Payment gateway: Razorpay when keys are set, a built-in practice gateway when ALLOW_PRACTICE_GATEWAY is on.

Both paths use the same signature scheme (HMAC-SHA256 over "order_id|payment_id"),
so the order code that confirms a payment is identical in either mode. With neither, mode() is "off":
no gateway order id is issued and no payment verifies, so a deployment that forgot its keys cannot give the
store away.
"""
import hashlib
import hmac
import secrets
from urllib.parse import quote

import requests
from flask import current_app

RAZORPAY_ORDERS_URL = "https://api.razorpay.com/v1/orders"
RAZORPAY_PAYMENTS_URL = "https://api.razorpay.com/v1/payments"
CURRENCY = "INR"


class GatewayError(Exception):
    pass


def mode():
    """"razorpay", "test" (the practice gateway) or "off"."""
    cfg = current_app.config
    if cfg["RAZORPAY_KEY_ID"] and cfg["RAZORPAY_KEY_SECRET"]:
        return "razorpay"
    return "test" if cfg.get("ALLOW_PRACTICE_GATEWAY") else "off"


def _secret():
    cfg = current_app.config
    return cfg["RAZORPAY_KEY_SECRET"] if mode() == "razorpay" else cfg["SECRET_KEY"]


def sign(gateway_order_id, payment_id):
    msg = f"{gateway_order_id}|{payment_id}".encode()
    return hmac.new(_secret().encode(), msg, hashlib.sha256).hexdigest()


def create_gateway_order(order):
    """Register the order with the gateway; returns the id to store on the order (None when payments are off)."""
    if mode() == "off":
        return None         # no gateway: the order can be seen but never paid; the buyer cancels it or it expires
    if mode() == "test":
        return "test_" + secrets.token_hex(8)
    cfg = current_app.config
    try:
        resp = requests.post(
            RAZORPAY_ORDERS_URL,
            auth=(cfg["RAZORPAY_KEY_ID"], cfg["RAZORPAY_KEY_SECRET"]),
            json={"amount": order.total_paise, "currency": "INR", "receipt": order.public_id},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["id"]
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise GatewayError("The payment provider did not respond. Try again in a moment.") from exc


def entity_matches_order(order, entity):
    """True only if a Razorpay payment entity is a captured payment, for this order, in exactly the amount and
    currency the server asked for. The amount is compared as an integer number of paise; a string, a float or a
    boolean never matches."""
    return (isinstance(entity, dict)
            and order.gateway_order_id is not None
            and entity.get("order_id") == order.gateway_order_id
            and type(entity.get("amount")) is int and entity["amount"] == order.total_paise
            and entity.get("currency") == CURRENCY
            and entity.get("status") == "captured")


def fetch_payment(payment_id):
    """Ask Razorpay for a payment, so the amount, currency and status come from them, not from the browser."""
    cfg = current_app.config
    try:
        resp = requests.get(f"{RAZORPAY_PAYMENTS_URL}/{quote(payment_id, safe='')}",
                            auth=(cfg["RAZORPAY_KEY_ID"], cfg["RAZORPAY_KEY_SECRET"]), timeout=10)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise GatewayError("The payment provider did not respond.") from exc


def payment_matches_order(order, payment_id):
    """Before an order is marked paid after the browser reports success: with Razorpay, fetch the payment and
    check amount, currency, status and order. A failed lookup counts as "not confirmed"; the signed webhook marks
    the order paid when Razorpay reports the capture. The practice gateway has no remote payment to check (its
    signature is made from the order itself), and with payments off nothing is ever confirmed."""
    current_mode = mode()
    if current_mode == "test":
        return True
    if current_mode != "razorpay":
        return False
    try:
        return entity_matches_order(order, fetch_payment(payment_id))
    except GatewayError:
        return False


def verify_payment(gateway_order_id, payment_id, signature):
    if mode() == "off" or not all(isinstance(v, str) and v for v in (gateway_order_id, payment_id, signature)):
        return False
    return hmac.compare_digest(sign(gateway_order_id, payment_id).encode(), signature.encode())


def verify_webhook(raw_body, signature):
    secret = current_app.config["RAZORPAY_WEBHOOK_SECRET"]
    if not (secret and signature):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), signature.encode())
