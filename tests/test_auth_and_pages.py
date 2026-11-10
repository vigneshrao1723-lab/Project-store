import pytest

from app.extensions import db
from app.models import User

from .conftest import login, make_user


@pytest.mark.parametrize("url", ["/", "/catalogue", "/catalogue?q=kyber", "/catalogue?category=ai-data&sort=price_desc",
                                 "/p/advanced-rag-knowledge-assistant", "/login", "/register"])
def test_public_pages_render(client, url):
    assert client.get(url).status_code == 200


def test_unknown_product_and_page_give_404(client):
    assert client.get("/p/nope").status_code == 404
    assert client.get("/no-such-page").status_code == 404


def test_hidden_products_are_not_public(client, rag):
    rag.is_active = False
    db.session.commit()
    assert client.get(f"/p/{rag.slug}").status_code == 404
    assert b"Advanced RAG" not in client.get("/catalogue").data


def test_search_matches_title_and_technology(client):
    assert b"Quantum-Resistant" in client.get("/catalogue?q=kyber").data
    assert b"FAISS" in client.get("/catalogue?q=faiss").data or b"Advanced RAG" in client.get("/catalogue?q=faiss").data
    assert b"No projects match" in client.get("/catalogue?q=zzzzzz").data


def test_search_treats_wildcards_as_text(client):
    assert client.get("/catalogue?q=%25").status_code == 200


def test_sold_out_sorts_last_and_cannot_be_added(buyer, soc):
    html = buyer.get("/catalogue").data.decode()
    assert html.index("Smart Home SoC") > html.index("Production E-Commerce")
    r = buyer.post("/api/v1/cart/items", json={"product_id": soc.id, "qty": 1})
    assert r.status_code == 409


def test_register_validates_and_logs_in(client):
    r = client.post("/register", data={"name": "", "email": "bad", "password": "short"})
    assert r.status_code == 200
    body = r.data.decode()
    assert "Enter your name." in body and "valid email" in body and "at least 8" in body
    ok = client.post("/register", data={"name": "Asha", "email": "Asha@Example.com", "password": "longenough1"})
    assert ok.status_code == 302
    assert db.session.scalar(db.select(User).where(User.email == "asha@example.com")) is not None
    assert client.get("/orders").status_code == 200


def test_duplicate_email_is_rejected(client, user):
    r = client.post("/register", data={"name": "X", "email": "BUYER@example.com", "password": "longenough1"})
    assert b"already exists" in r.data


def test_passwords_are_hashed(user):
    assert user.password_hash != "correct-horse" and user.check_password("correct-horse")


def test_login_failure_is_generic(client, user):
    r = client.post("/login", data={"email": "buyer@example.com", "password": "wrong"})
    assert b"don&#39;t match" in r.data or b"don't match" in r.data
    r = client.post("/login", data={"email": "ghost@example.com", "password": "wrong"})
    assert b"don&#39;t match" in r.data or b"don't match" in r.data


@pytest.mark.parametrize("target", ["https://evil.example", "//evil.example", "javascript:alert(1)"])
def test_login_does_not_redirect_off_site(client, user, target):
    r = client.post(f"/login?next={target}", data={"email": "buyer@example.com", "password": "correct-horse"})
    assert r.status_code == 302 and r.headers["Location"] == "/"


def test_login_follows_safe_next(client, user):
    r = client.post("/login?next=/cart", data={"email": "buyer@example.com", "password": "correct-horse"})
    assert r.headers["Location"] == "/cart"


def test_cart_and_orders_require_login(client):
    assert client.get("/cart").status_code == 302
    assert client.get("/orders").status_code == 302
    assert client.get("/checkout").status_code == 302
    assert client.get("/api/v1/cart").status_code == 401


def test_admin_is_locked_to_admins(client, buyer, admin_client):
    assert buyer.get("/admin").status_code == 403
    assert buyer.get("/api/v1/admin/stats").status_code == 403
    assert client.application.test_client().get("/admin").status_code == 302
    assert admin_client.get("/admin").status_code == 200


def test_cart_quantity_rules(buyer, rag):
    assert buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 0}).status_code == 400
    assert buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": "x"}).status_code == 400
    assert buyer.post("/api/v1/cart/items", json={"product_id": 9999, "qty": 1}).status_code == 404
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 99})
    assert buyer.get("/api/v1/cart").get_json()["count"] == 5          # capped per line
    patched = buyer.patch(f"/api/v1/cart/items/{rag.id}", json={"qty": 2}).get_json()
    assert patched["count"] == 2 and patched["total_paise"] == 2 * rag.price_paise
    assert buyer.delete(f"/api/v1/cart/items/{rag.id}").get_json()["count"] == 0


def test_cart_is_private_to_each_user(app, buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    make_user("other@example.com")
    other = app.test_client()
    login(other, "other@example.com")
    assert other.get("/api/v1/cart").get_json()["count"] == 0


def test_checkout_pages_walk_through(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    assert buyer.get("/cart").status_code == 200
    r = buyer.post("/checkout", data={"billing_name": "Asha", "phone": ""})
    assert r.status_code == 302 and "/checkout/pay/" in r.headers["Location"]
    pay_url = r.headers["Location"]
    assert b"Pay" in buyer.get(pay_url).data
    done = buyer.post("/checkout/test-pay/" + pay_url.rsplit("/", 1)[1], data={"outcome": "pay"})
    assert done.status_code == 302
    page = buyer.get(done.headers["Location"]).data
    assert b"Your downloads" in page and b"Paid" in page


def test_declined_test_payment_keeps_hold_and_cancel_refills_cart(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 2})
    pay_url = buyer.post("/checkout", data={"billing_name": "Asha"}).headers["Location"]
    public_id = pay_url.rsplit("/", 1)[1]
    buyer.post(f"/checkout/test-pay/{public_id}", data={"outcome": "fail"})
    assert buyer.get("/api/v1/orders/" + public_id).get_json()["status"] == "pending"
    buyer.post(f"/checkout/cancel/{public_id}")
    assert buyer.get("/api/v1/orders/" + public_id).get_json()["status"] == "cancelled"
    assert buyer.get("/api/v1/cart").get_json()["count"] == 2


def test_checkout_requires_a_name(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    r = buyer.post("/checkout", data={"billing_name": "  "})
    assert r.status_code == 400
    assert buyer.get("/api/v1/cart").get_json()["count"] == 1


def test_security_headers_present(client):
    h = client.get("/").headers
    assert h["X-Content-Type-Options"] == "nosniff" and "frame-src" in h["Content-Security-Policy"]
