"""Phone layout rules that are readable from the stylesheet and the markup. The real rendering is checked in a
browser with mobile emulation (see the commit message), because a unit test cannot measure overflow."""
import re
from pathlib import Path

import pytest

from app.extensions import db
from app.models import Order
from app.services import orders as order_svc

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "main.css").read_text(encoding="utf-8").replace("\r\n", "\n")
BASE = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")


def media_block(query):
    start = CSS.index("@media " + query + " {")
    depth, i = 0, CSS.index("{", start)
    for j in range(i, len(CSS)):
        depth += CSS[j] == "{"
        depth -= CSS[j] == "}"
        if depth == 0:
            return CSS[i + 1:j]
    raise AssertionError("unterminated media block")


PHONE = media_block("(max-width: 620px)")
TABLET = media_block("(max-width: 900px)")


def test_the_viewport_meta_tag_is_device_width_and_does_not_block_zooming():
    tag = re.search(r'<meta name="viewport" content="([^"]*)">', BASE).group(1)
    assert tag == "width=device-width, initial-scale=1"          # no maximum-scale or user-scalable=no


def test_form_controls_are_at_least_16px_on_phones_so_ios_does_not_zoom_into_them():
    assert re.search(r"(?m)^\s*select,\s*input,\s*textarea\s*\{[^}]*font-size:\s*16px", PHONE), PHONE


def test_header_links_and_buttons_are_44px_touch_targets_on_phones():
    assert re.search(r"\.nav a,\s*\.nav \.linkish[^{]*\{[^}]*min-height:\s*44px", PHONE), PHONE
    assert re.search(r"\.wordmark[^{]*\{[^}]*min-height:\s*44px", PHONE), PHONE


def test_the_hero_heading_is_not_oversized_on_a_phone():
    h1 = re.search(r"(?m)^\.h1 \{[^}]*font-size:\s*clamp\(([\d.]+)rem", CSS)
    assert float(h1.group(1)) <= 2.0
    assert re.search(r"\.lede\s*\{[^}]*font-size:\s*1\.1rem", PHONE)


def test_single_column_layouts_cannot_be_stretched_by_wide_content():
    """grid-template-columns: 1fr lets a wide table force the column, and the page, wider than the screen."""
    assert "grid-template-columns: 1fr;" not in re.search(r"\.hero-grid[^{]*\{([^}]*)\}", TABLET).group(1)
    assert re.search(r"\.hero-grid[^{]*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)", TABLET)


@pytest.mark.parametrize("rule", [r"\.table-stack thead", r"\.table-stack td::before", r"\.table-stack tr"])
def test_stacked_tables_have_their_phone_rules(rule):
    assert re.search(rule + r"[^{]*\{", PHONE), rule


def labelled(html):
    """Every <td> in every .table-stack table carries a data-label for the stacked layout."""
    tables = re.findall(r'<table class="table table-stack">(.*?)</table>', html, re.S)
    assert tables, "no stacked table on the page"
    for table in tables:
        body = re.split(r"<tbody[^>]*>", table, maxsplit=1)[1]
        cells = re.findall(r"<td\b([^>]*)>", body)
        assert cells and all("data-label=" in c for c in cells), cells
        head = re.findall(r"<th[^>]*>(.*?)</th>", table.split("</thead>")[0], re.S)
        labels = re.findall(r'data-label="([^"]+)"', body)
        assert set(labels) == {re.sub(r"<[^>]+>", "", h).strip() for h in head}


def test_orders_table_is_stackable_and_labelled(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    buyer.post("/api/v1/checkout", json={})
    labelled(buyer.get("/orders").get_data(as_text=True))


def test_admin_tables_are_stackable_and_labelled(admin_client, buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    buyer.post("/api/v1/checkout", json={})
    labelled(admin_client.get("/admin/orders").get_data(as_text=True))
    labelled(admin_client.get("/admin/products").get_data(as_text=True))
