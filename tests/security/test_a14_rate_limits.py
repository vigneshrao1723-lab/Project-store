"""Security audit A14: rate limits."""

import re


def _hammer(send, attempts=100):
    codes = [send(i).status_code for i in range(attempts)]
    return codes


def test_a14_registration_is_rate_limited(client):
    codes = _hammer(lambda i: client.post("/register", data={"name": "Bot", "email": f"bot{i}@example.com", "password": "x"}))
    assert 429 in codes, "100 registration attempts in a row from one address were all processed"
    assert 429 not in codes[:3]


def test_a14_api_checkout_is_rate_limited(buyer):
    codes = _hammer(lambda i: buyer.post("/api/v1/checkout", json={"billing_name": "Bot"}))
    assert 429 in codes, "100 checkout attempts in a row were all processed"
    assert 429 not in codes[:3]


def test_a14_page_checkout_is_rate_limited(buyer):
    codes = _hammer(lambda i: buyer.post("/checkout", data={"billing_name": "Bot"}))
    assert 429 in codes, "100 checkout form posts in a row were all processed"


def test_a14_payment_verification_is_rate_limited(buyer):
    codes = _hammer(lambda i: buyer.post("/api/v1/checkout/verify", json={"order_id": "PS-AAAAAAA", "gateway_order_id": "x",
                                                                      "payment_id": "p", "signature": "s"}))
    assert 429 in codes, "100 forged payment confirmations in a row were all answered"


def test_a14_page_payment_verification_is_rate_limited(buyer):
    codes = _hammer(lambda i: buyer.post("/checkout/verify", data={"public_id": "PS-AAAAAAA"}))
    assert 429 in codes, "100 forged payment confirmations on the page route were all answered"


def test_a14_login_is_limited_per_address_not_only_per_email(client):
    """The existing limit is per email + IP, so one address can try unlimited different emails."""
    codes = _hammer(lambda i: client.post("/login", data={"email": f"user{i}@example.com", "password": "guess-guess-1"}))
    assert 429 in codes, "100 sign-in attempts against 100 different emails from one address were all processed"


def test_a14_the_per_email_login_limit_still_works(client, user):
    codes = [client.post("/login", data={"email": "buyer@example.com", "password": "wrong-password"}).status_code
             for _ in range(6)]
    assert codes[-1] == 429


def test_a14_there_is_no_password_reset_yet_and_the_contact_form_is_rate_limited(app):
    paths = {r.rule for r in app.url_map.iter_rules()}
    assert not [p for p in paths if re.search(r"reset|forgot", p)], \
        "a reset endpoint now exists; it needs a rate limit and a test"
    # the contact form arrived in v1.3 with its limits (tests/test_contact.py exercises both)
    assert "/contact" in paths
    assert app.config["RATE_LIMITS"]["contact_ip"] == (10, 3600) and app.config["RATE_LIMITS"]["contact_email"] == (3, 3600)
