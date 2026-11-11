"""Security audit A17: webhook amount."""

import pytest

from .helpers import _captured, _signed_webhook, order_status, start_order


@pytest.mark.parametrize("override", [{"amount": 100}, {"amount": 0}, {"currency": "USD"}, {"currency": "usd"}, {"amount": "abc"}],
                         ids=lambda o: str(o))
def test_a17_signed_webhook_with_the_wrong_amount_or_currency_does_not_mark_the_order_paid(buyer, rag, override):
    order = start_order(buyer, rag)
    _signed_webhook(buyer.application.test_client(), _captured(order, **override))
    assert order_status(order["id"]) == "pending", \
        f"the webhook marked an order for {order['total_paise']} paise INR paid using {override}"
