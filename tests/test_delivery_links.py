"""The download link is what the buyer pays for, so it must appear only once an order is paid."""
from app.extensions import db

from .conftest import login, make_user

SECRET_LINK = "https://files.example.com/private/kit-7f3a9c"


def _start_order(client, product, qty=1):
    client.post("/api/v1/cart/items", json={"product_id": product.id, "qty": qty})
    pay_url = client.post("/checkout", data={"billing_name": "Asha"}).headers["Location"]
    return pay_url.rsplit("/", 1)[1]


def _everywhere_a_buyer_can_look(client, public_id, product):
    """Every page and API response that a buyer, or the public, can reach for this order and product.

    Each one must actually load (200), otherwise "the link is not in the body" would pass on an error page.
    """
    paths = {
        "order page": f"/orders/{public_id}",
        "pay page": f"/checkout/pay/{public_id}",
        "orders list": "/orders",
        "order API": f"/api/v1/orders/{public_id}",
        "orders API": "/api/v1/orders",
        "product page": f"/p/{product.slug}",
        "product API": f"/api/v1/products/{product.slug}",
        "catalogue API": "/api/v1/products",
        "catalogue page": "/catalogue",
    }
    bodies = {}
    for where, path in paths.items():
        r = client.get(path, follow_redirects=True)
        assert r.status_code == 200, f"{where} ({path}) returned {r.status_code}"
        bodies[where] = r.get_data(as_text=True)
    return bodies


def test_link_is_hidden_until_the_order_is_paid(app, buyer, rag):
    rag.delivery_url = SECRET_LINK
    db.session.commit()
    public_id = _start_order(buyer, rag)

    # Pending: the buyer has an order but has not paid.
    for where, body in _everywhere_a_buyer_can_look(buyer, public_id, rag).items():
        assert SECRET_LINK not in body, f"link leaked on the {where} while the order was pending"
    assert "Your downloads" not in buyer.get(f"/orders/{public_id}").get_data(as_text=True)
    assert buyer.get(f"/api/v1/orders/{public_id}").get_json()["items"][0]["download_url"] is None

    # A declined payment changes nothing: still pending, still no link.
    buyer.post(f"/checkout/test-pay/{public_id}", data={"outcome": "fail"})
    assert buyer.get(f"/api/v1/orders/{public_id}").get_json()["status"] == "pending"
    for where, body in _everywhere_a_buyer_can_look(buyer, public_id, rag).items():
        assert SECRET_LINK not in body, f"link leaked on the {where} after a declined payment"

    # Paid: now, and only now, the link is there.
    buyer.post(f"/checkout/test-pay/{public_id}", data={"outcome": "pay"})
    page = buyer.get(f"/orders/{public_id}").get_data(as_text=True)
    assert "Your downloads" in page and f'href="{SECRET_LINK}"' in page
    assert buyer.get(f"/api/v1/orders/{public_id}").get_json()["items"][0]["download_url"] == SECRET_LINK

    # Paying still does not put the link on public pages.
    public = app.test_client()
    assert public.get(f"/p/{rag.slug}").status_code == 200
    assert SECRET_LINK not in public.get(f"/p/{rag.slug}").get_data(as_text=True)
    assert SECRET_LINK not in public.get(f"/api/v1/products/{rag.slug}").get_data(as_text=True)
    assert SECRET_LINK not in public.get("/api/v1/products").get_data(as_text=True)


def test_cancelled_order_never_shows_the_link(buyer, rag):
    rag.delivery_url = SECRET_LINK
    db.session.commit()
    public_id = _start_order(buyer, rag)
    buyer.post(f"/checkout/cancel/{public_id}")
    assert buyer.get(f"/api/v1/orders/{public_id}").get_json()["status"] == "cancelled"
    for where, body in _everywhere_a_buyer_can_look(buyer, public_id, rag).items():
        assert SECRET_LINK not in body, f"link leaked on the {where} for a cancelled order"


def test_someone_elses_paid_order_does_not_reveal_the_link(app, buyer, rag):
    rag.delivery_url = SECRET_LINK
    db.session.commit()
    public_id = _start_order(buyer, rag)
    buyer.post(f"/checkout/test-pay/{public_id}", data={"outcome": "pay"})
    assert SECRET_LINK in buyer.get(f"/orders/{public_id}").get_data(as_text=True)

    make_user("stranger@example.com", name="Stranger")
    stranger = app.test_client()
    login(stranger, "stranger@example.com")
    page = stranger.get(f"/orders/{public_id}")
    assert page.status_code == 404 and SECRET_LINK not in page.get_data(as_text=True)
    api = stranger.get(f"/api/v1/orders/{public_id}")
    assert api.status_code in (403, 404) and SECRET_LINK not in api.get_data(as_text=True)

    anonymous = app.test_client()
    assert SECRET_LINK not in anonymous.get(f"/orders/{public_id}", follow_redirects=True).get_data(as_text=True)
    assert SECRET_LINK not in anonymous.get(f"/api/v1/orders/{public_id}").get_data(as_text=True)
