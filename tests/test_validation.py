"""Input parsing helpers and the error shapes the API promises."""
import pytest

from app.extensions import db
from app.models import Order, Product
from app.services.products import validate_product
from app.validation import InputError, clean_query, page_number, rupees_to_paise, text, whole_number


@pytest.mark.parametrize("value,expected", [(5, 5), ("7", 7), (" 8 ", 8), (3.0, 3), ("+4", 4), ("-2", -2)])
def test_whole_number_accepts_integers_in_any_json_spelling(value, expected):
    assert whole_number(value, -10, 10) == expected


@pytest.mark.parametrize("value", [True, False, None, [], {}, [1], 2.5, float("inf"), float("nan"), "", "abc", "1.5",
                                   "1e3", "9" * 400, 10 ** 400, 11, -11])
def test_whole_number_rejects_everything_else(value):
    with pytest.raises(InputError):
        whole_number(value, -10, 10)


@pytest.mark.parametrize("value,paise", [("499.50", 49950), ("1999", 199900), (1999, 199900), (499.5, 49950),
                                         ("0", 0), ("0.01", 1), ("100000", 10_000_000)])
def test_rupees_become_exact_integer_paise(value, paise):
    assert rupees_to_paise(value) == paise
    assert isinstance(rupees_to_paise(value), int)


@pytest.mark.parametrize("value", ["99.999", "-1", "nan", "inf", "-inf", "1e999", "100000.01", "", "abc", None, True,
                                   [1], {"a": 1}])
def test_rupees_reject_bad_amounts(value):
    with pytest.raises(InputError):
        rupees_to_paise(value)


def test_text_strips_caps_and_refuses_non_strings():
    assert text("  hi  ", 5) == "hi"
    assert text(None, 5) == ""
    assert text(None, 5, default="x") == "x"
    for bad in (123, ["a"], {"a": 1}):
        with pytest.raises(InputError):
            text(bad, 5)
    with pytest.raises(InputError, match="at most 3"):
        text("abcd", 3)
    with pytest.raises(InputError, match="required"):
        text("  ", 3, required=True)


def test_search_text_is_cut_not_rejected():
    assert clean_query("a" * 500) == "a" * 100
    assert clean_query(None) == ""


@pytest.mark.parametrize("raw,page", [("3", 3), (3, 3), ("0", 1), ("-4", 1), ("abc", 1), (None, 1), ("9" * 40, 1000),
                                      (10 ** 9, 1000), ("1" + "0" * 5000, 1)])
def test_page_numbers_stay_inside_the_cap(raw, page):
    assert page_number(raw) == page


def test_text_fields_are_capped_for_products(app):
    clean, errors = validate_product({"title": "T" * 161, "category_id": 1, "price_rupees": "1", "stock": 0,
                                      "tagline": "t" * 256, "tech": "x" * 256, "description": "d" * 20_001,
                                      "delivery_url": "https://example.com/" + "a" * 500})
    assert set(errors) == {"title", "tagline", "tech", "description", "delivery_url"}


def test_delivery_urls_may_not_contain_spaces_or_other_schemes(app):
    for url in ("https://example.com/a b", "ftp://example.com/x", "javascript:alert(1)", "//example.com"):
        _, errors = validate_product({"title": "T", "category_id": 1, "price_rupees": "1", "delivery_url": url})
        assert "delivery_url" in errors, url


def test_price_is_never_a_float(app):
    clean, errors = validate_product({"title": "T", "category_id": 1, "price_rupees": "0.29", "stock": 1})
    assert not errors and clean["price_paise"] == 29 and type(clean["price_paise"]) is int


# ---- API behaviour ------------------------------------------------------------------------------

def test_json_bodies_must_be_objects(buyer):
    for raw in ("[1]", '"x"', "123", "null", "{not json"):
        r = buyer.post("/api/v1/cart/items", data=raw, content_type="application/json")
        assert r.status_code == 400 and r.get_json()["error"] == "Send a JSON object.", raw


def test_an_empty_body_is_an_empty_object(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id})
    assert buyer.post("/api/v1/checkout").status_code == 201


def test_quantities_above_the_line_cap_still_clamp(buyer, rag, app):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 40})
    assert buyer.get("/api/v1/cart").get_json()["count"] == app.config["MAX_QTY_PER_LINE"]


def test_api_errors_are_json_for_404_405_and_oversized_bodies(client):
    for method, path, status in (("get", "/api/v1/nope", 404), ("delete", "/api/v1/products", 405)):
        r = getattr(client, method)(path)
        assert r.status_code == status and r.is_json and r.get_json()["error"]
    r = client.post("/api/v1/cart/items", data=b"x" * (1024 * 1024 + 1), content_type="application/json")
    assert r.status_code == 413 and r.is_json


def test_site_errors_stay_html(client):
    r = client.get("/no-such-page")
    assert r.status_code == 404 and "text/html" in r.content_type
    assert client.post("/", data=b"x" * (1024 * 1024 + 1)).status_code == 413


def test_non_ascii_signatures_are_rejected_not_crashed(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id})
    pid = buyer.post("/api/v1/checkout").get_json()
    gid = pid["payment"]["gateway_order_id"]
    r = buyer.post("/api/v1/checkout/verify", json={"order_id": pid["id"], "gateway_order_id": gid,
                                                      "payment_id": "pay_x", "signature": "é" * 64})
    assert r.status_code == 400
    r = buyer.post("/checkout/verify", data={"public_id": pid["id"], "razorpay_order_id": gid,
                                              "razorpay_payment_id": "pay_x", "razorpay_signature": "é" * 64})
    assert r.status_code == 302
    r = buyer.post("/api/v1/checkout/verify", json={"order_id": ["x"], "gateway_order_id": [1]})
    assert r.status_code == 404
    assert db.session.scalar(db.select(Order.status).where(Order.public_id == pid["id"])) == "pending"


def test_checkout_form_caps_name_and_phone(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id})
    assert buyer.post("/checkout", data={"billing_name": "n" * 121}).status_code == 400
    assert buyer.post("/checkout", data={"billing_name": "n", "phone": "1" * 25}).status_code == 400
    assert buyer.post("/checkout", data={"billing_name": "n" * 120, "phone": "1" * 24}).status_code == 302


def test_admin_stock_form_rejects_absurd_changes(admin_client, rag):
    before = rag.stock
    for delta in ("1" * 40, "x", "1.5", ""):
        r = admin_client.post(f"/admin/products/{rag.id}/stock", data={"delta": delta}, follow_redirects=True)
        assert r.status_code == 200 and "Enter a whole number" in r.get_data(as_text=True)
    db.session.expire_all()
    assert db.session.get(Product, rag.id).stock == before


def test_registration_and_login_caps(client, user):
    r = client.post("/register", data={"name": "n" * 121, "email": "a@example.com", "password": "long-enough-1"})
    assert "Use at most 120 characters" in r.get_data(as_text=True)
    r = client.post("/register", data={"name": "n", "email": "a@example.com", "password": "p" * 129})
    assert "Use at most 128 characters" in r.get_data(as_text=True)
    # Over-long sign-in values are refused without hashing or touching the throttle row size limits.
    for email, pw in (("e" * 500 + "@example.com", "x"), ("buyer@example.com", "p" * 5000)):
        r = client.post("/login", data={"email": email, "password": pw})
        assert r.status_code == 200 and "email and password" in r.get_data(as_text=True)


def test_admin_cannot_use_customer_payment_routes_but_can_still_read_the_order(admin_client, buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id})
    pid = buyer.post("/api/v1/checkout").get_json()["id"]
    assert admin_client.get(f"/checkout/pay/{pid}").status_code == 404
    assert admin_client.post(f"/checkout/cancel/{pid}").status_code == 404
    assert admin_client.get(f"/orders/{pid}").status_code == 200
