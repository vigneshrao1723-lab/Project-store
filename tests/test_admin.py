from app.extensions import db
from app.models import Category, InventoryLog, Order, Product

from .conftest import make_user


def new_product(**over):
    cat = db.session.scalar(db.select(Category))
    body = {"title": "Test Kit", "category_id": cat.id, "price_rupees": "499.50", "stock": 3,
            "tagline": "t", "tech": "Python", "delivery_url": "https://example.com/kit"}
    body.update(over)
    return body


def test_admin_creates_product_via_api(admin_client):
    r = admin_client.post("/api/v1/admin/products", json=new_product())
    assert r.status_code == 201
    data = r.get_json()
    assert data["price_paise"] == 49950 and data["slug"] == "test-kit" and data["stock"] == 3
    assert admin_client.get("/api/v1/products/test-kit").status_code == 200


def test_product_validation_errors_are_field_level(admin_client):
    r = admin_client.post("/api/v1/admin/products", json=new_product(title="", price_rupees="-5",
                                                                     delivery_url="ftp://x", category_id=999))
    assert r.status_code == 422
    fields = r.get_json()["fields"]
    assert {"title", "price_rupees", "delivery_url", "category_id"} <= set(fields)


def test_slug_must_be_unique(admin_client):
    admin_client.post("/api/v1/admin/products", json=new_product())
    r = admin_client.post("/api/v1/admin/products", json=new_product())
    assert r.status_code == 422 and "slug" in r.get_json()["fields"]


def test_update_keeps_stock_out_of_band(admin_client, rag):
    r = admin_client.put(f"/api/v1/admin/products/{rag.id}", json={"title": "Renamed", "stock": 9999})
    assert r.status_code == 200 and r.get_json()["title"] == "Renamed"
    assert r.get_json()["stock"] == rag.stock


def test_stock_adjust_writes_ledger_and_blocks_negative(admin_client, rag):
    start = rag.stock
    r = admin_client.post(f"/api/v1/admin/products/{rag.id}/stock", json={"delta": 5, "note": "restock"})
    assert r.get_json()["stock"] == start + 5
    assert db.session.scalar(db.select(InventoryLog).where(InventoryLog.reason == "adjust")).note == "restock"
    r = admin_client.post(f"/api/v1/admin/products/{rag.id}/stock", json={"delta": -10_000})
    assert r.status_code == 409
    assert admin_client.post(f"/api/v1/admin/products/{rag.id}/stock", json={"delta": "x"}).status_code == 422


def test_stats_endpoint(admin_client, buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    buyer.post("/api/v1/checkout", json={})
    stats = admin_client.get("/api/v1/admin/stats").get_json()
    assert stats["orders_by_status"]["pending"] == 1 and stats["revenue_paise"] == 0


def test_admin_pages_render(admin_client, buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    order = buyer.post("/api/v1/checkout", json={}).get_json()
    for url in ["/admin", "/admin/products", "/admin/products/new", f"/admin/products/{rag.id}",
                "/admin/orders", "/admin/orders?status=pending", f"/admin/orders/{order['id']}"]:
        assert admin_client.get(url).status_code == 200, url


def test_admin_html_product_form_round_trip(admin_client):
    cat = db.session.scalar(db.select(Category))
    r = admin_client.post("/admin/products/new", data={
        "title": "Form Kit", "slug": "", "category_id": cat.id, "price_rupees": "1999", "stock": "4",
        "tagline": "x", "description": "a\n\nb", "tech": "Go", "includes": "one\ntwo", "delivery_url": "",
        "is_active": "on"})
    assert r.status_code == 302
    p = db.session.scalar(db.select(Product).where(Product.slug == "form-kit"))
    assert p.stock == 4 and p.price_paise == 199900 and p.is_active and p.includes_list == ["one", "two"]
    bad = admin_client.post("/admin/products/new", data={"title": "", "category_id": "", "price_rupees": "x", "stock": "-1"})
    assert bad.status_code == 200 and b"Enter a title." in bad.data


def test_admin_cancels_pending_and_resolves_refund(admin_client, buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 2})
    order = buyer.post("/api/v1/checkout", json={}).get_json()
    before = db.session.get(Product, rag.id).stock
    admin_client.post(f"/admin/orders/{order['id']}/cancel")
    db.session.expire_all()
    assert db.session.get(Product, rag.id).stock == before + 2
    o = db.session.scalar(db.select(Order).where(Order.public_id == order["id"]))
    assert o.status == "cancelled"
    o.status = "refund_due"
    db.session.commit()
    admin_client.post(f"/admin/orders/{order['id']}/refunded")
    db.session.refresh(o)
    assert o.status == "refunded"
