"""Layout rules that cannot be seen from a response body: read them from the stylesheet."""
import re
from pathlib import Path

import pytest

from app.extensions import db
from app.models import Category, Product

CSS = (Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "main.css").read_text(encoding="utf-8")


def rule(selector, css=CSS):
    """The declarations of the first top-level rule whose selector is exactly ``selector``."""
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, f"no rule for {selector}"
    return m.group(1)


def test_the_product_grid_container_paints_no_background():
    """The old grid drew its hairlines by painting the container navy and showing it through 1px gaps, so every
    empty cell in a partial last row (1 card on a row of 3, say) became a solid navy block."""
    declarations = rule(".grid")
    assert "background" not in declarations, declarations
    assert not re.search(r"gap:\s*1px", declarations), "hairlines must not come from the gap showing the container"


def test_each_tile_draws_its_own_hairline_so_empty_cells_stay_empty():
    declarations = rule(".tile")
    assert re.search(r"border:\s*1px solid var\(--ink\)", declarations)
    assert re.search(r"margin:\s*0 -1px -1px 0", declarations)          # neighbouring borders overlap into one line


def show_exactly(n):
    """Make exactly n products visible in the catalogue, adding some if the demo catalogue has fewer."""
    products = db.session.scalars(db.select(Product).order_by(Product.id)).all()
    cat = db.session.scalar(db.select(Category))
    while len(products) < n:
        extra = Product(category_id=cat.id, slug=f"extra-{len(products)}", title=f"Extra {len(products)}", tagline="t",
                        description="d", tech="x", includes="i", price_paise=10000, stock=3, is_active=True)
        db.session.add(extra)
        db.session.flush()
        products.append(extra)
    for i, p in enumerate(products):
        p.is_active = i < n
    db.session.commit()


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_the_catalogue_renders_every_tile_inside_one_grid(app, client, n):
    show_exactly(n)
    html = client.get("/catalogue").get_data(as_text=True)
    assert html.count('<div class="grid">') == 1
    assert len(re.findall(r'<a class="tile[ "]', html)) == n


def test_search_with_few_hits_renders_only_those_tiles(app, client):
    show_exactly(5)
    html = client.get("/catalogue?q=Extra").get_data(as_text=True)
    assert len(re.findall(r'<a class="tile[ "]', html)) == 1
