"""Accessibility landmarks found by an axe-core run on every public page: the test-mode notice is a labelled region,
the catalogue lists its projects under a heading so the tile titles are not an h1 -> h3 jump, and the pay page has a
level-one heading. Each is a visually hidden or attribute-only change."""


def _order(client, product):
    client.post("/api/v1/cart/items", json={"product_id": product.id, "qty": 1})
    return client.post("/api/v1/checkout", json={"billing_name": "Buyer"}).get_json()["id"]


def test_the_test_mode_notice_is_a_labelled_region(client):
    page = client.get("/").get_data(as_text=True)
    assert '<div class="testbar" role="region" aria-label="Test mode">' in page


def test_the_catalogue_names_its_list_of_projects_before_the_tiles(client, rag):
    page = client.get("/catalogue").get_data(as_text=True)
    assert page.index('<h2 class="sr">Projects</h2>') < page.index("<h3>")


def test_the_pay_page_has_exactly_one_level_one_heading_naming_the_order(buyer, rag):
    pid = _order(buyer, rag)
    page = buyer.get(f"/checkout/pay/{pid}").get_data(as_text=True)
    assert page.count("<h1") == 1 and f'<h1 class="sr">Pay for order {pid}</h1>' in page
