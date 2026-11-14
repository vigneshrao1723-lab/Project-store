"""The palette and the 3D background (v1.2): colours are written once (tokens.css), every pair in use passes contrast, and the
background obeys the loop, placement and fallback rules."""
import gzip
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
CSS = APP / "static" / "css"
JS = APP / "static" / "js"
spec = importlib.util.spec_from_file_location("check_contrast", ROOT / "scripts" / "check_contrast.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

PALETTE = {"amber": "#FFAB00", "harley": "#DD2E18", "white": "#FFFFFF", "sunset": "#FF5841", "violet": "#C53678",
           "night": "#14070F", "panel": "#1F0C18", "panel-2": "#2A1221", "line": "#4A2438", "muted": "#D9C3CE", "ink": "#1A0B14"}
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b|%23[0-9a-fA-F]{6}\b")


# ---- tokens ---------------------------------------------------------------------------------------------------------
def test_the_palette_is_exactly_the_agreed_one_and_lives_in_one_file_on_bare_root():
    tok = cc.tokens()
    assert {k: v for k, v in tok.items()} == PALETTE
    css = (CSS / "tokens.css").read_text(encoding="utf-8")
    assert css.count(":root {") == 1 and "color-scheme: dark" in css and "@media" not in css and "data-theme" not in css


def test_the_rgb_triples_match_the_hex_palette_and_are_space_separated():
    css = (CSS / "tokens.css").read_text(encoding="utf-8")
    for name in ("night", "panel", "amber", "sunset", "violet"):
        m = re.search(rf"--{name}-rgb:\s*(\d+) (\d+) (\d+);", css)               # space-separated, so rgb(var(--x-rgb) / .9) is valid
        assert m, name
        h = PALETTE[name]
        assert tuple(int(x) for x in m.groups()) == (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)), name


def test_every_translucent_rgb_in_the_styles_is_valid_modern_syntax():
    for f in CSS.glob("*.css"):
        for m in re.finditer(r"rgb\(var\(--[a-z-]+-rgb\)([^)]*)\)", f.read_text(encoding="utf-8")):
            assert m.group(1).strip() == "" or re.fullmatch(r"/ (\.\d+|1|0)", m.group(1).strip()), (f.name, m.group(0))


def test_tokens_css_is_the_first_stylesheet_on_every_kind_of_page(client, rag):
    for path in ("/", "/catalogue", "/login", f"/p/{rag.slug}"):
        links = re.findall(r'<link rel="stylesheet" href="([^"]+)"', client.get(path).get_data(as_text=True))
        assert links[0].endswith("css/tokens.css"), path


def _text_files():
    for base, suffixes in ((CSS, {".css"}), (JS, {".js"}), (APP / "templates", {".html"}), (APP, {".py"})):
        for f in base.rglob("*"):
            if f.is_file() and f.suffix in suffixes and "__pycache__" not in f.parts:
                if base is APP and f.parent != APP:
                    continue                                                  # app/*.py only; subfolders have their own checks below
                if f.name == "tokens.css":
                    continue
                yield f
    for f in (APP / "blueprints").glob("*.py"):
        yield f
    for f in (APP / "services").glob("*.py"):
        yield f


def test_no_hex_colour_is_written_anywhere_but_tokens_css():
    offenders = []
    for f in _text_files():
        text = f.read_text(encoding="utf-8")
        if f.suffix == ".css":
            text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        for m in HEX.finditer(text):
            offenders.append(f"{f.relative_to(ROOT)}: {m.group(0)}")
        if re.search(r"rgba?\(\s*\d", text):
            offenders.append(f"{f.relative_to(ROOT)}: a literal rgb()/rgba()")
    assert not offenders, offenders[:12]


def test_the_old_ink_blue_and_yellow_tokens_are_gone_from_styles_templates_and_scripts():
    old = re.compile(r"var\(--(paper|paper-2|ink-2|rule|mark|green|red)\)|--(paper|paper-2|ink-2|rule|mark|green|red):")
    offenders = [f.name for f in _text_files() if old.search(f.read_text(encoding="utf-8"))]
    assert not offenders, offenders


def test_every_colour_token_a_rule_uses_exists():
    defined = set(cc.tokens()) | {"night-rgb", "panel-rgb", "amber-rgb", "sunset-rgb", "violet-rgb"}
    used = set()
    for f in CSS.glob("*.css"):
        used |= set(re.findall(r"var\(--([a-z0-9-]+)(?:\)|,)", f.read_text(encoding="utf-8")))
    colourish = {u for u in used if u in PALETTE or u.endswith("-rgb")}
    assert colourish <= defined
    for u in used - defined:                                                  # anything else must be a non-colour custom property
        assert not re.search(r"paper|mark|rule|green|red", u), u


def test_the_favicon_is_painted_from_the_palette_and_the_page_links_it(client):
    page = client.get("/").get_data(as_text=True)
    href = re.search(r'<link rel="icon" href="([^"]+)"', page).group(1)
    assert "%23C53678" in href.upper().replace("%2523", "%23") or "%23C53678" in href
    from app.context import FAVICON
    assert "%23C53678" in FAVICON and "%23FFAB00" in FAVICON


# ---- contrast ---------------------------------------------------------------------------------------------------------
def test_the_measured_ratios_in_the_brief_are_what_the_tokens_give():
    t = cc.tokens()
    r = lambda a, b: round(cc.ratio(t[a], t[b]), 2)
    assert r("white", "harley") == 4.69 and r("white", "violet") == 5.03 and r("ink", "sunset") == 6.10 and r("ink", "amber") == 10.05
    assert r("white", "sunset") < 4.5 and r("white", "amber") < 4.5                        # which is why the text on them is --ink
    assert r("amber", "night") == 10.38 and r("sunset", "night") == 6.30
    assert r("violet", "night") == 3.91 and r("harley", "night") == 4.20


def test_every_text_and_graphic_pair_the_design_relies_on_passes():
    rows, bad = cc.check()
    assert len(rows) > 100
    assert not bad, [(n, round(x, 2)) for n, x, _ in bad]


def test_violet_and_harley_are_never_a_text_colour():
    for sel, fg, bg, f in cc.rule_pairs():
        assert fg not in cc.NEVER_TEXT, (f, sel)


def test_a_rule_that_breaks_contrast_is_caught(tmp_path, monkeypatch):
    bad = tmp_path / "bad.css"
    bad.write_text(".x { color: var(--white); background: var(--sunset); } .y { color: var(--violet); }", encoding="utf-8")
    monkeypatch.setattr(cc, "CSS_DIR", tmp_path)
    (tmp_path / "tokens.css").write_text((CSS / "tokens.css").read_text(encoding="utf-8"), encoding="utf-8")
    rows, found = cc.check()
    assert any("white on sunset" in n for n, _, _ in found) and any("violet used as a text colour" in n for n, _, _ in found)


# ---- the background ------------------------------------------------------------------------------------------------------
def test_the_canvas_is_on_home_sign_in_register_and_the_paid_order_page_only(app, buyer, rag):
    has = lambda c, p: "data-bg3d" in c.get(p).get_data(as_text=True)
    anon = app.test_client()                                  # the `buyer` fixture signs the shared client in
    assert has(anon, "/") and has(anon, "/login") and has(anon, "/register")
    for p in ("/catalogue", f"/p/{rag.slug}", "/no-such-page"):
        assert not has(anon, p), p
    pid = _order(buyer, rag)
    for p in ("/cart", "/checkout", f"/checkout/pay/{pid}", "/orders", f"/orders/{pid}"):          # unpaid order: still no canvas
        assert not has(buyer, p), p
    assert 'data-bg="css"' in buyer.get("/catalogue").get_data(as_text=True)
    buyer.post(f"/checkout/test-pay/{pid}", data={"outcome": "pay"})
    paid = buyer.get(f"/orders/{pid}").get_data(as_text=True)
    assert "data-bg3d" in paid and 'data-bg="gl"' in paid and "js/fx-bg.js" in paid


def test_admin_has_neither_canvas_nor_gradient(admin_client):
    page = admin_client.get("/admin").get_data(as_text=True)
    assert 'data-bg="none"' in page and "data-bg3d" not in page and "fx-bg.js" not in page
    assert 'body[data-bg="none"]::before { content: none; }' in (CSS / "main.css").read_text(encoding="utf-8")


def _order(client, product):
    client.post("/api/v1/cart/items", json={"product_id": product.id, "qty": 1})
    return client.post("/api/v1/checkout", json={"billing_name": "Buyer"}).get_json()["id"]


def test_the_background_module_has_no_loop_no_observer_and_no_colour_of_its_own():
    src = (JS / "fx-bg.js").read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", src, flags=re.S)
    assert "requestAnimationFrame" not in code and "IntersectionObserver" not in code and "setInterval" not in code
    assert not HEX.search(src) and "getPropertyValue" in code
    assert "https://" not in code and "<script" not in code                    # no external library, no inline script


def test_the_scroll_loop_drives_the_background_and_there_is_still_exactly_one_loop():
    scroll = (JS / "fx-scroll.js").read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", scroll, flags=re.S)
    assert "window.fxBg.tick(now)" in code
    assert code.count("requestAnimationFrame(") == 1 and code.count("new IntersectionObserver(") == 1
    for f in JS.glob("*.js"):
        if f.name not in ("fx-scroll.js", "motion.js", "fx-cart.js"):
            assert "requestAnimationFrame(" not in re.sub(r"/\*.*?\*/|//[^\n]*", "", f.read_text(encoding="utf-8"), flags=re.S), f.name


def test_quality_rules_are_in_the_module():
    src = (JS / "fx-bg.js").read_text(encoding="utf-8")
    assert "Math.min(window.devicePixelRatio || 1, 1.5) * 0.5" in src and "phone ? 0.35" in src
    assert "frames < 40" in src and "sum / 40 > 42" in src                     # 24 fps is 41.7 ms a frame
    assert "prefers-reduced-motion" in src and 'indexOf("bg3d")' in src and 'contains("fx-lite")' in src
    assert "getContext(\"webgl\"" in src and "COMPILE_STATUS" in src and "LINK_STATUS" in src and "webglcontextlost" in src


def test_the_css_fallback_gradient_is_always_underneath_and_text_over_the_shader_has_a_scrim():
    css = (CSS / "main.css").read_text(encoding="utf-8")
    assert re.search(r"body::before \{[^}]*content: \"\"[^}]*position: fixed[^}]*z-index: -2", css, re.S)
    assert re.search(r"\.bg3d \{[^}]*z-index: -1[^}]*pointer-events: none", css, re.S)
    assert re.search(r"\.bg-scrim \{[^}]*linear-gradient\(90deg", css, re.S)
    assert 'html[data-fx-off~="bg3d"] .bg3d' in (CSS / "fx-tuning.css").read_text(encoding="utf-8")


def test_cards_over_the_background_are_at_least_ninety_percent_panel():
    css = "".join(f.read_text(encoding="utf-8") for f in CSS.glob("*.css"))
    for alpha in re.findall(r"rgb\(var\(--panel-rgb\) / (\.\d+|1)\)", css):
        assert float(alpha) >= 0.9, alpha


def test_the_canvas_is_aria_hidden_and_the_scrim_too(client):
    page = client.get("/").get_data(as_text=True)
    assert '<canvas class="bg3d" data-bg3d aria-hidden="true"></canvas><div class="bg-scrim" aria-hidden="true"></div>' in page


def test_fx_bg_fits_the_script_budget():
    assert len(gzip.compress((JS / "fx-bg.js").read_bytes(), 9)) < 4096


def test_covers_carry_classes_not_colours_and_still_escape_titles():
    from app.covers import cover_svg
    for kind in ("crypto", "ai", "web", "hardware"):
        svg = cover_svg("slug", kind, "A & <b>")
        assert "fill=\"#" not in svg and "stroke=\"#" not in svg and "cv-" in svg
        assert "&lt;b&gt;" in svg and "<b>" not in svg


def test_the_payment_mark_uses_an_amber_ring_a_violet_disc_and_a_white_tick():
    css = (CSS / "motion3.css").read_text(encoding="utf-8")
    assert ".result-success .rs-ring { stroke: var(--amber); }" in css and ".result-success .rs-disc { fill: var(--violet); }" in css
    assert ".rs-draw { stroke: var(--white);" in css and ".result-failure .rs-disc { fill: var(--harley); }" in css


@pytest.mark.parametrize("f", ["README.md", "CLAUDE.md", "docs/ARCHITECTURE.md"])
def test_the_old_design_rules_no_longer_say_no_gradients_or_ink_blue(f):
    text = (ROOT / f).read_text(encoding="utf-8")
    assert "#1B2A41" not in text and "#F5D90A" not in text
    assert not re.search(r"[Dd]o not add gradients", text)


def test_nothing_that_slides_in_from_the_side_can_widen_the_page():
    css = (CSS / "main.css").read_text(encoding="utf-8")
    assert re.search(r"main \{ flex: 1; overflow-x: clip; \}", css)                       # clip, not hidden: no scroll container, sticky still works
    assert re.search(r"\.hero \{[^}]*overflow-x: clip", css)
