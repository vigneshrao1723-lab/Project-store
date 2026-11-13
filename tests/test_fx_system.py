"""The site-wide scroll system: the data-fx vocabulary, which page class each page belongs to, and the rules that keep it
safe (nothing hidden without the script, nothing in admin or on error pages, nothing that has to be used by hand
inside a hidden element). The script itself is tested in test_fx_scroll.py."""
import gzip
import re
from pathlib import Path

import pytest

from app.extensions import db
from app.models import Order

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "motion3.css").read_text(encoding="utf-8").replace("\r\n", "\n")
BARE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
SCROLL = BARE[BARE.index('html.fx-on [data-fx="rise"]:not(.is-in)'):]
SCROLL = re.sub(r"@keyframes [\w-]+ \{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", SCROLL)      # keyframes are not selectors
SCROLL_MAIN = SCROLL.split("@media (prefers-reduced-motion: reduce)")[0]       # without the final reduced-motion block
TEMPLATES = ROOT / "app" / "templates"
VOCABULARY = {"rise", "cascade", "count", "pin", "parallax",                                    # the first five
              "from-left", "from-right", "zoom", "flip", "clip", "lines", "words", "draw", "hscroll",   # scroll variants
              "marquee", "tilt", "magnetic"}                                                       # ticker and pointer feedback


def without_hover_media(css):
    """The stylesheet with every (hover: hover) and (pointer: fine) block removed: hover rules may live only there."""
    out, i = "", 0
    marker = "@media (hover: hover) and (pointer: fine) {"
    while True:
        j = css.find(marker, i)
        if j < 0:
            return out + css[i:]
        out += css[i:j]
        depth, k = 0, j + len(marker) - 1
        for k in range(k, len(css)):
            depth += css[k] == "{"
            depth -= css[k] == "}"
            if depth == 0:
                break
        i = k + 1
CONTROLS = re.compile(r"<(a|button|input|select|textarea|form|label)\b")


def attr(html, name):
    return re.findall(r'<body data-page="(\w+)"', html)


def fx_elements(html):
    """(kind, outer-ish text) for every element carrying data-fx; the text runs to the element's matching close tag."""
    out = []
    for m in re.finditer(r"<(\w+)\b[^>]*\bdata-fx=\"(\w+)\"[^>]*>", html):
        tag, kind = m.group(1), m.group(2)
        depth, pos = 1, m.end()
        for t in re.finditer(r"<(/?)%s\b[^>]*>" % tag, html[pos:]):
            depth += -1 if t.group(1) else 1
            if depth == 0:
                out.append((kind, html[m.start():pos + t.end()], tag))
                break
    return out


@pytest.fixture()
def order_id(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    return buyer.post("/api/v1/checkout", json={"billing_name": "Buyer"}).get_json()["id"]


def pages(app, buyer, admin_client, rag, order_id):
    """{path: (client, expected page class)} for every page a visitor, a buyer or the admin can reach."""
    anon = app.test_client()
    return {
        "/": (anon, "browse"), "/catalogue": (anon, "browse"), "/catalogue?q=zzzz": (anon, "browse"),
        f"/p/{rag.slug}": (anon, "browse"), f"/p/{rag.slug}#buyer": (buyer, "browse"),
        "/login": (anon, "transactional"), "/register": (anon, "transactional"),
        "/cart": (buyer, "transactional"), f"/checkout/pay/{order_id}": (buyer, "transactional"),
        "/orders": (buyer, "account"), f"/orders/{order_id}": (buyer, "account"),
        "/admin": (admin_client, "admin"), "/admin/orders": (admin_client, "admin"), "/admin/products": (admin_client, "admin"),
        "/admin/products/new": (admin_client, "admin"), f"/admin/orders/{order_id}": (admin_client, "admin"),
        "/no-such-page": (anon, "none"),
    }


# ---- page classes -----------------------------------------------------------------------------------------------------

def test_every_page_declares_its_class_and_only_the_classes_that_move_load_the_script(app, buyer, admin_client, rag, order_id):
    for path, (client, expected) in pages(app, buyer, admin_client, rag, order_id).items():
        resp = client.get(path.split("#")[0], follow_redirects=True)
        html = resp.get_data(as_text=True)
        assert attr(html, "data-page") == [expected], (path, resp.status_code)
        assert ("fx-scroll.js" in html) is (expected != "none"), path
        assert ("fx-ui.js" in html) is (expected != "none"), path
        assert ("data-fx=" in html) is (expected != "none"), path
        if expected == "none":
            assert "fx-progress" in html and 'data-fx' not in html and "fx-on" not in html, path


def test_an_error_page_is_a_none_page_and_moves_nothing(client):
    for status in ("/no-such-page",):
        html = client.get(status).get_data(as_text=True)
        assert 'data-page="none"' in html and "data-fx" not in html and "fx-scroll.js" not in html


ADMIN_WORDS = {"rise", "cascade", "count", "flip", "zoom", "from-left", "from-right", "words", "lines"}      # one-shot words only


def test_admin_may_use_one_shot_words_but_never_scroll_linked_pinned_or_pointer_effects():
    for f in sorted((TEMPLATES / "admin").glob("*.html")):
        text = f.read_text(encoding="utf-8")
        assert "data-fx" not in text, f.name                                   # spelled through the macros
        used = set(re.findall(r"fx\('([\w-]+)'\)", text)) | ({"count"} if "fx_count" in text else set())
        assert used <= ADMIN_WORDS, (f.name, used - ADMIN_WORDS)
    assert "{% block page_class %}admin{% endblock %}" in (TEMPLATES / "admin" / "base.html").read_text(encoding="utf-8")
    assert "{% block page_class %}none{% endblock %}" in (TEMPLATES / "error.html").read_text(encoding="utf-8")


def test_the_admin_pages_that_render_only_use_those_words_and_have_the_footer_rise_and_counters(admin_client, app, buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    buyer.post("/api/v1/checkout", json={"billing_name": "Buyer"})
    for path in ("/admin", "/admin/orders", "/admin/products"):
        html = admin_client.get(path).get_data(as_text=True)
        assert set(re.findall(r'data-fx="([\w-]+)"', html)) <= ADMIN_WORDS, path
        assert '<footer class="site-footer" data-fx="rise">' in html and 'class="rail"' not in html and "fx-progress" in html
    dash = admin_client.get("/admin").get_data(as_text=True)
    assert dash.count('data-fx="count"') == 4 and '<h1 data-fx="flip">Overview</h1>' in dash and 'class="figures" data-fx="cascade"' in dash
    assert re.search(r"<tbody data-fx=\"cascade\">", admin_client.get("/admin/orders").get_data(as_text=True))


def test_the_footer_rises_on_every_page_that_moves(client):
    assert '<footer class="site-footer" data-fx="rise">' in client.get("/").get_data(as_text=True)
    assert '<footer class="site-footer" data-fx="rise">' in client.get("/login").get_data(as_text=True)


def test_the_progress_hairline_exists_only_as_a_decorative_element_and_is_drawn_for_browse_pages_only():
    assert re.search(r'html\.fx-on body\[data-page="browse"\] \.fx-progress \{[^}]*transform: scaleX\(var\(--sp, 0\)\)', SCROLL)
    assert re.search(r"\.fx-progress \{ display: none; \}", SCROLL)
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", SCROLL):
        if "fx-progress" in sel and "display: block" in body:
            assert 'body[data-page="browse"]' in sel and "html.fx-on" in sel


# ---- the vocabulary -----------------------------------------------------------------------------------------------------

def test_the_vocabulary_words_in_use_are_all_documented_ones(app, buyer, admin_client, rag, order_id):
    seen = set()
    for path, (client, expected) in pages(app, buyer, admin_client, rag, order_id).items():
        seen |= set(re.findall(r'data-fx="(\w+)"', client.get(path.split("#")[0], follow_redirects=True).get_data(as_text=True)))
    assert seen <= VOCABULARY, seen - VOCABULARY
    assert {"rise", "cascade", "count", "pin", "parallax", "lines", "words", "clip", "draw", "hscroll", "marquee", "tilt", "magnetic"} <= seen, seen


def test_macros_are_the_one_way_templates_spell_it(app):
    macros = (TEMPLATES / "_macros.html").read_text(encoding="utf-8")
    assert '{% macro fx(kind) %}data-fx="{{ kind }}"{% endmacro %}' in macros
    assert "{% macro fx_count(n) %}" in macros and 'data-fx="count" data-to="{{ n }}"' in macros
    for f in TEMPLATES.rglob("*.html"):
        if f.name == "_macros.html":
            continue
        text = f.read_text(encoding="utf-8")
        assert not re.search(r'data-fx="', text), f"{f.name} writes data-fx by hand; use the fx() macro"


def test_every_attribute_has_a_documented_example():
    doc = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    section = doc[doc.index("## Scroll system"):]
    section = section.split("\n## ", 1)[0]
    for word in VOCABULARY:
        assert re.search(r"\{\{ fx\('%s'\) \}\}|fx_count" % word if word != "count" else r"fx_count", section), word
        assert f"`{word}`" in section, word
    assert "html.fx-on" in section and "single `IntersectionObserver`" in section


def test_a_counter_holds_its_number_three_times_so_the_box_never_changes_width(client):
    html = client.get("/").get_data(as_text=True)
    boxes = re.findall(r'<span class="cnt" data-fx="count" data-to="(\d+)"><span class="cnt-size">(\d+)</span><span class="cnt-live" aria-hidden="true">(\d+)</span></span>', html)
    assert len(boxes) == 4
    for to, size, live in boxes:
        assert to == size == live


# ---- hidden only after the script ran ------------------------------------------------------------------------------------

def test_nothing_the_stylesheet_hides_is_hidden_without_the_script():
    hiding = [(s.strip(), b) for s, b in re.findall(r"([^{}@]+)\{([^{}]*)\}", SCROLL) if re.search(r"opacity:\s*0\b", b)]
    assert hiding
    for selector, body in hiding:
        if ".cnt-size" in selector or "::after" in selector or "::before" in selector:
            continue                                  # the sizing text of a counter: invisible by design, still in the page
        parts = [p.strip() for p in selector.split(",")]
        assert all(p.startswith("html.fx-on ") for p in parts), (selector, "hidden by base CSS without the script")
    # taller sections and sticky stages exist only after the script ran, too
    for selector, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", SCROLL):
        if re.search(r"(^|[;\s])(height|position)\s*:\s*(var\(--pin-h|calc\(100vh|sticky)", body):
            assert "html.fx-on" in selector, selector
    assert "visibility: hidden" not in SCROLL and "display: none; }" in SCROLL


def test_the_script_is_what_turns_the_system_on_so_the_server_never_renders_a_hidden_state(app, buyer, admin_client, rag, order_id):
    for path, (client, expected) in pages(app, buyer, admin_client, rag, order_id).items():
        html = client.get(path.split("#")[0], follow_redirects=True).get_data(as_text=True)
        assert "fx-on" not in html.split("<body", 1)[0], path
        assert not re.search(r'\bis-in\b|\bis-focus\b', html.split("</footer>")[0].replace("is-in-", "")) or "result" in html, path
        for kind, text, tag in fx_elements(html):
            opening = text[:text.index(">") + 1]
            assert "style=" not in opening and " hidden" not in opening, (path, opening)


def test_tokens_are_defined_once_and_the_distance_is_12_to_16_pixels():
    root = re.search(r":root \{(.*?)\n\}", BARE, re.S).group(1)
    for token in ("--fx-dist", "--fx-ease", "--fx-stagger", "--fx-dur"):
        assert root.count(token + ":") == 1, token
    assert 12 <= int(re.search(r"--fx-dist:\s*(\d+)px", root).group(1)) <= 16
    assert re.search(r"--fx-stagger:\s*60ms", root)
    # the section transitions use the tokens, not their own numbers
    for selector, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", SCROLL_MAIN):
        if selector.strip().startswith(('html.fx-on [data-fx="rise"]', 'html.fx-on [data-fx="cascade"]')) and "transition" in body and "transition: none" not in body:
            assert "var(--fx-dur) var(--fx-ease)" in body or "var(--fx-stagger)" in body, selector
            assert not re.search(r"\d+ms|cubic-bezier", body), selector


def test_only_transform_and_opacity_change_in_the_scroll_system():
    for selector, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", SCROLL_MAIN):
        for prop in re.findall(r"transition:\s*([^;]+);", body):
            assert {p.strip().split()[0] for p in prop.split(",")} <= {"opacity", "transform", "none"}, selector
    assert "will-change" not in SCROLL and "!important" not in SCROLL and ":hover" not in re.sub(r"\.tile:is\(:hover[^}]*\}", "", re.sub(r"\.(sc-cover|hs-card) a:hover \{[^}]*\}", "", without_hover_media(SCROLL)))


def test_reduced_motion_puts_everything_back_in_its_finished_state_even_if_the_class_is_already_set():
    inner = re.search(r"@media \(prefers-reduced-motion: reduce\) \{(.*)\n\}", SCROLL, re.S).group(1)
    assert 'html.fx-on [data-fx="rise"], html.fx-on [data-fx="cascade"] > * { opacity: 1; transform: none; transition: none; }' in inner
    assert 'html.fx-on [data-fx="pin"] { height: auto; }' in inner and ".fx-move, .sc-head { opacity: 1; transform: none; }" in inner


# ---- pinned scenes ----------------------------------------------------------------------------------------------------------

def test_scenes_marked_pin_lg_are_pinned_on_large_screens_only():
    big = re.search(r"@media \(min-width: 900px\) \{\s*html\.fx-on:not\(\.fx-lite\) \[data-fx=\"pin\"\]\.pin-lg \{.*?\n\}", SCROLL, re.S).group(0)
    assert ".pin-lg .fx-stage { contain: layout paint; position: sticky" in big
    outside = SCROLL.replace(big, "")
    assert not re.search(r"\.pin-lg(?!\))[^{]*\{[^}]*(sticky|height: var)", outside)
    assert 'html.fx-on:not(.fx-lite) [data-fx="pin"]:not(.pin-lg):not(.pin-soft)' in outside     # a plain pin is pinned everywhere; .pin-soft never is


def test_the_product_scene_asks_for_less_than_one_screen_of_extra_scroll():
    pin_h = int(re.search(r"\.scene \{ --pin-h: (\d+)vh", SCROLL).group(1))
    # extra scroll = section height - stage height = pin-h - (100vh - header); the header is about 75px
    for vh_px in (600, 800, 1080):
        assert (pin_h / 100 - 1) * vh_px + 75 < vh_px, vh_px


def test_the_product_page_has_a_scene_with_its_own_cover_and_real_facts(client, rag):
    html = client.get(f"/p/{rag.slug}").get_data(as_text=True)
    scene = html[html.index('<section class="scene pin-lg"'):].split("</section>")[0]
    assert 'data-fx="pin"' in scene and 'data-fx="parallax"' in scene and 'class="scene-stage fx-stage"' in scene
    assert rag.title in scene and "cover" in scene and "<svg" in scene
    assert f"{rag.price_paise // 100:,}".replace(",", "") in scene.replace(",", "")
    for tech in rag.tech_list:
        assert tech in scene
    assert scene.count("fx-move") == 3 and "<a " not in scene and "<button" not in scene


def test_product_page_gets_the_full_treatment(client, rag, soc):
    soc.stock = 5
    db.session.commit()
    html = client.get(f"/p/{rag.slug}").get_data(as_text=True)
    kinds = [(k, t) for k, _, t in fx_elements(html)]
    assert ("rise", "div") in kinds                                  # the cover plate
    assert kinds.count(("cascade", "dl")) == 1 and kinds.count(("cascade", "ul")) >= 1 and ("cascade", "div") in kinds
    assert "pin" in [k for k, _ in kinds] and "parallax" in [k for k, _ in kinds]
    assert 'data-fx="cascade">{% for' not in html


def test_home_and_catalogue_get_the_full_treatment(client):
    home = client.get("/").get_data(as_text=True)
    kinds = [k for k, _, _ in fx_elements(home)]
    assert kinds.count("cascade") >= 4 and kinds.count("count") == 4 and "pin" in kinds and "rise" in kinds
    cat = client.get("/catalogue").get_data(as_text=True)
    assert re.search(r'<div class="grid fx-alt" data-motion-group="tiles" data-fx="cascade">', cat)


# ---- transactional pages -----------------------------------------------------------------------------------------------------

def test_transactional_pages_move_only_text_and_never_anything_the_visitor_has_to_use(app, buyer, admin_client, rag, order_id):
    for path, (client, expected) in pages(app, buyer, admin_client, rag, order_id).items():
        if expected != "transactional":
            continue
        html = client.get(path.split("#")[0], follow_redirects=True).get_data(as_text=True)
        found = fx_elements(html)
        assert found, path
        for kind, text, tag in found:
            if tag == "footer":
                continue
            assert kind in {"rise", "cascade", "zoom"}, (path, kind)
            assert not CONTROLS.search(text), (path, "a control sits inside an element that starts hidden", text[:120])


def test_login_and_register_forms_and_errors_are_never_marked(client):
    for page in ("/login", "/register"):
        html = client.get(page).get_data(as_text=True)
        form = html[html.index("<form"):html.index("</form>")]
        assert "data-fx" not in form
    resp = client.post("/login", data={"email": "nobody@example.com", "password": "wrong-password-123"})
    html = resp.get_data(as_text=True)
    assert 'role="alert"' in html
    alert = re.search(r'<p class="flash flash-error"[^>]*>', html).group(0)
    assert "data-fx" not in alert


def test_the_cart_summary_and_its_checkout_button_are_not_marked(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    html = buyer.get("/cart").get_data(as_text=True)
    summary = html[html.index('<aside class="summary"'):html.index("</aside>")]
    assert "data-fx" not in summary and "Go to checkout" in summary
    assert "data-fx" not in html[html.index('<div class="two-col" data-cart>'):html.index('<aside class="summary"')]


# ---- account pages ---------------------------------------------------------------------------------------------------------

def test_order_rows_cascade_lightly_and_the_payment_sequence_is_left_alone(buyer, rag, order_id):
    html = buyer.get("/orders").get_data(as_text=True)
    assert re.search(r"<tbody data-fx=\"cascade\">", html)
    buyer.post(f"/checkout/test-pay/{order_id}", data={"outcome": "pay"})
    page = buyer.get(f"/orders/{order_id}").get_data(as_text=True)
    assert '<div class="result result-success"' in page and 'class="delivery"' in page
    delivery = page[page.index('<section class="delivery"'):page.index("</section>")]
    assert "data-fx" not in delivery
    assert '<div class="result result-success"' in page and "data-fx" not in re.search(r'<div class="result[^>]*>', page).group(0)


def test_all_the_fx_scripts_together_stay_under_12_kb_gzipped():
    sizes = {f.name: len(gzip.compress(f.read_bytes(), 9)) for f in (ROOT / "app" / "static" / "js").glob("fx-*.js")}
    assert set(sizes) == {"fx-cart.js", "fx-pay.js", "fx-scroll.js", "fx-ui.js"}, sizes
    assert sum(sizes.values()) < 12 * 1024, sizes


def test_there_is_one_scroll_script_not_two():
    scripts = [f.name for f in (ROOT / "app" / "static" / "js").glob("*.js")]
    assert [s for s in scripts if "scroll" in s] == ["fx-scroll.js"]
    for f in (ROOT / "app" / "static" / "js").glob("*.js"):
        text = f.read_text(encoding="utf-8")
        if f.name != "fx-scroll.js":
            assert "new IntersectionObserver" not in text, f.name
