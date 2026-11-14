"""Checkpoint 1 of the motion pass: the markup hooks and the CSS skeleton. The rules below are the safety rules for
every later checkpoint, so they are tested on the stylesheet itself."""
import re
from pathlib import Path

import pytest

from app.extensions import db
from app.models import Category, Product

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "main.css").read_text(encoding="utf-8").replace("\r\n", "\n")
MOTION_WITH_COMMENTS = CSS[CSS.index("/* ===== Motion (skeleton)"):].split("/* ===== Motion: intro loader")[0]      # later sections have their own tests
MOTION = re.sub(r"/\*.*?\*/", "", MOTION_WITH_COMMENTS, flags=re.S)       # comments hold braces and words that are not rules


def split_top_level(text):
    parts, depth, cur = [], 0, ""
    for ch in text:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    return parts + [cur]


def blocks(css):
    """Yield (selector, body) for each plain rule in a CSS fragment, looking inside @media blocks too."""
    for m in re.finditer(r"([^{}@/][^{}]*)\{([^{}]*)\}", css):
        yield m.group(1).strip(), m.group(2)


def at_rules(css):
    """(prelude, inner css) for each top-level @media block."""
    out = []
    for m in re.finditer(r"@media ([^{]+)\{", css):
        depth, i = 0, m.end() - 1
        for j in range(i, len(css)):
            depth += css[j] == "{"
            depth -= css[j] == "}"
            if depth == 0:
                out.append((m.group(1).strip(), css[i + 1:j]))
                break
    return out


# ---- the stylesheet rules ---------------------------------------------------------------------------------------

def test_will_change_is_only_ever_set_on_the_class_the_script_adds_during_an_animation():
    for selector, body in blocks(MOTION):
        if "will-change" in body:
            assert selector == ".is-animating", selector


def test_only_transform_and_opacity_are_animated():
    for selector, body in blocks(MOTION):
        for prop in re.findall(r"transition:\s*([^;]+);", body):
            names = {part.strip().split()[0] for part in split_top_level(prop) if part.strip()}
            # .btn[data-press] repeats the button's own colour transition so adding the press does not remove it
            allowed = {"opacity", "transform"} | ({"background", "color"} if selector.startswith(".btn[data-press]") else set())
            assert names <= allowed, (selector, names)
    frames = re.search(r"@keyframes motion-failsafe \{(.*)\}\n", MOTION).group(1)
    assert set(re.findall(r"([\w-]+):", frames)) <= {"opacity", "transform"}, frames


def test_every_hover_rule_in_the_motion_section_sits_inside_the_fine_pointer_media_query():
    outside = re.sub(r"@media \(hover: hover\) and \(pointer: fine\) \{.*?\n\}\n", "", MOTION, flags=re.S)
    assert ":hover" not in outside
    guards = [p for p, _ in at_rules(MOTION)]
    assert "(hover: hover) and (pointer: fine)" in guards


def test_hidden_states_exist_only_on_elements_the_script_marked_pending_and_a_css_failsafe_reveals_them():
    hidden = [sel for sel, body in blocks(MOTION) if re.search(r"opacity:\s*0\b", body)]
    assert hidden and all(".is-pending" in s for s in hidden), hidden
    pending = next(body for sel, body in blocks(MOTION) if sel.startswith("[data-reveal].is-pending"))
    delay = re.search(r"animation:\s*motion-failsafe\s+(\d+)ms\s+linear\s+(\d+(?:\.\d+)?)s\s+forwards", pending)
    assert delay and float(delay.group(2)) <= 2.0, pending
    assert re.search(r"@keyframes motion-failsafe\s*\{\s*to\s*\{\s*opacity:\s*1;\s*transform:\s*none;", MOTION)


def test_reduced_motion_shows_everything_and_moves_nothing():
    inner = dict(at_rules(MOTION))["(prefers-reduced-motion: reduce)"]
    pending = next(body for sel, body in blocks(inner) if ".is-pending" in sel)
    assert "opacity: 1" in pending and "transform: none" in pending and "animation: none" in pending
    assert any(".is-pressed" in sel and "opacity: 1" in body for sel, body in blocks(inner))


def test_the_skeleton_defines_its_tokens_and_does_not_hide_anything_by_default():
    for token in ("--motion-ease", "--motion-fast", "--motion-med", "--motion-slow", "--motion-distance", "--motion-stagger"):
        assert re.search(token + r":", MOTION), token
    assert "display: none" not in MOTION and "visibility: hidden" not in MOTION


def test_the_motion_section_uses_custom_properties_and_classes_never_inline_styles():
    assert "style=" not in MOTION and "!important" not in MOTION


# ---- the markup hooks -----------------------------------------------------------------------------------------------

def hooks(html, name):
    return re.findall(rf'data-motion="{name}"', html)


def test_home_page_hooks(client):
    html = client.get("/").get_data(as_text=True)
    for name in ("hero", "hero-copy", "hero-plate", "tile", "tile-cover"):
        assert hooks(html, name), name
    assert html.count("data-reveal") == 4                       # the field index, the shelf, how buying works and get in touch
    assert 'data-motion-group="tiles"' in html
    indices = [int(i) for i in re.findall(r'data-motion="tile" data-motion-kind="\w+" data-motion-index="(\d+)"', html)]
    assert indices == list(range(len(indices))) and indices


def test_catalogue_hooks_and_tile_indices(app, client):
    html = client.get("/catalogue").get_data(as_text=True)
    assert 'class="result-bar" data-reveal' in html and 'data-motion-group="tiles"' in html
    indices = [int(i) for i in re.findall(r'data-motion-index="(\d+)"', html)]
    assert indices == list(range(len(indices))) and len(indices) == 4


def test_product_page_hooks(buyer, client, rag):
    anonymous = client.application.test_client().get(f"/p/{rag.slug}").get_data(as_text=True)
    signed_in = buyer.get(f"/p/{rag.slug}").get_data(as_text=True)
    for html in (anonymous, signed_in):
        for name in ("plate", "product-info", "buybox"):
            assert hooks(html, name) == [f'data-motion="{name}"'], name
    assert 'class="btn atc" data-press type="submit">' in signed_in and '<span class="atc-label">Add to cart</span>' in signed_in
    assert 'class="btn" data-press href=' in anonymous


def test_a_single_tile_still_renders_with_its_index(app, client):
    for p in db.session.scalars(db.select(Product).where(Product.slug != "advanced-rag-knowledge-assistant")):
        p.is_active = False
    db.session.commit()
    html = client.get("/catalogue").get_data(as_text=True)
    assert re.findall(r'data-motion-index="(\d+)"', html) == ["0"]


def test_no_hook_is_a_style_attribute_and_the_pay_page_and_razorpay_script_are_untouched():
    for name in ("home.html", "catalogue.html", "product.html", "_macros.html"):
        assert "style=" not in (ROOT / "app" / "templates" / name).read_text(encoding="utf-8")
    pay = (ROOT / "app" / "templates" / "pay.html").read_text(encoding="utf-8")
    assert "data-motion" not in pay and "data-reveal" not in pay and "data-press" not in pay
    assert "data-motion" not in (ROOT / "app" / "static" / "js" / "razorpay.js").read_text(encoding="utf-8")


def test_related_products_get_the_same_hooks_when_a_category_has_more_than_one_project(client, rag):
    db.session.add(Product(category_id=rag.category_id, slug="sibling", title="Sibling", tagline="t", description="d", tech="x",
                           includes="i", price_paise=10000, stock=3, is_active=True))
    db.session.commit()
    html = client.get(f"/p/{rag.slug}").get_data(as_text=True)
    assert "data-reveal" in html and 'data-motion-group="tiles"' in html
    assert re.findall(r'data-motion-index="(\d+)"', html) == ["0"]
