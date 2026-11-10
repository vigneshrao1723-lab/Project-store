"""Payment gateway: Razorpay when keys are set, a built-in test gateway otherwise.

Both paths use the same signature scheme (HMAC-SHA256 over "order_id|payment_id"),
so the order code that confirms a payment is identical in either mode.
"""
import hashlib
import hmac
import secrets

import requests
from flask import current_app

RAZORPAY_ORDERS_URL = "https://api.razorpay.com/v1/orders"


class GatewayError(Exception):
    pass


def mode():
    cfg = current_app.config
    return "razorpay" if cfg["RAZORPAY_KEY_ID"] and cfg["RAZORPAY_KEY_SECRET"] else "test"


def _secret():
    cfg = current_app.config
    return cfg["RAZORPAY_KEY_SECRET"] if mode() == "razorpay" else cfg["SECRET_KEY"]


def sign(gateway_order_id, payment_id):
    msg = f"{gateway_order_id}|{payment_id}".encode()
    return hmac.new(_secret().encode(), msg, hashlib.sha256).hexdigest()


def create_gateway_order(order):
    """Register the order with the gateway; returns the id to store on the order."""
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


def verify_payment(gateway_order_id, payment_id, signature):
    if not (gateway_order_id and payment_id and signature):
        return False
    return hmac.compare_digest(sign(gateway_order_id, payment_id), signature)


def verify_webhook(raw_body, signature):
    secret = current_app.config["RAZORPAY_WEBHOOK_SECRET"]
    if not (secret and signature):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
