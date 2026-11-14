"""Checkpoint 3 of the motion pass: category interactions on tiles and plates. The markup and stylesheet are tested
directly; motion.js is run under node against a small fake DOM, so hover, focus, pointerdown, touch, reduced motion
and cleanup are all exercised, not just read."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.extensions import db
from app.models import Category, Product

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "main.css").read_text(encoding="utf-8").replace("\r\n", "\n")
MOTION_JS = ROOT / "app" / "static" / "js" / "motion.js"
SECTION = CSS[CSS.index("/* ===== Motion: category interactions"):]
NODE = shutil.which("node")
KINDS = {"crypto": ["mk-packet", "mk-flap", "mk-node"],
         "ai": ["mk-pane", "mk-card", "mk-ring"],
         "web": ["mk-cart", "mk-drop d4", "mk-drop d5"],
         "hardware": ["mk-screen", "mk-pins", "mk-stick"]}


# ---- markup -----------------------------------------------------------------------------------------------------------

def tiles(html):
    return re.findall(r'<a class="tile[^"]*"[^>]*data-motion="tile"[^>]*>.*?</a>', html, re.S)


def test_every_tile_carries_its_categorys_cover_kind_and_a_decorative_motif(client, soc):
    soc.stock = 5                                              # the demo hardware kit is sold out; put it on the shelf
    db.session.commit()
    found = {}
    for tile in tiles(client.get("/catalogue").get_data(as_text=True)):
        kind = re.search(r'data-motion-kind="(\w+)"', tile).group(1)
        found[kind] = tile
        for name in KINDS[kind]:
            assert name in tile, (kind, name)
        assert tile.count('<span class="fx-panel" aria-hidden="true">') == 1 and tile.count('<span class="fx-back" aria-hidden="true">') == 1
        art = tile[tile.index('<span class="fx-panel"'):tile.index("</svg>")]
        assert not re.search(r"<(a|button|input|select|textarea)\b|tabindex", art)
    assert set(found) == set(KINDS)


def test_the_kind_comes_from_the_category_not_from_the_title_or_id(app, client, rag):
    cat = db.session.get(Category, rag.category_id)
    for kind in KINDS:
        cat.cover_kind = kind
        db.session.commit()
        html = client.get("/catalogue?q=Advanced").get_data(as_text=True)
        assert f'data-motion-kind="{kind}"' in tiles(html)[0]
    cat.cover_kind = "hardware"
    rag.title = "Crypto Web AI"                                  # a title that names other kinds changes nothing
    db.session.commit()
    assert 'data-motion-kind="hardware"' in tiles(client.get("/catalogue?q=Crypto").get_data(as_text=True))[0]


def test_the_motif_follows_the_kind_and_an_unknown_kind_falls_back_to_the_web_art(app, client, rag):
    db.session.get(Category, rag.category_id).cover_kind = "mystery"
    db.session.commit()
    tile = tiles(client.get("/catalogue?q=Advanced").get_data(as_text=True))[0]
    assert 'data-motion-kind="mystery"' in tile and "mk-cart" in tile


def test_sold_out_tiles_keep_their_state_and_get_no_panel(app, client, rag):
    rag.stock = 0
    db.session.commit()
    tile = tiles(client.get("/catalogue?q=Advanced").get_data(as_text=True))[0]
    assert "is-out" in tile and "out-flag" in tile and "fx-panel" not in tile
    assert '<span class="fx-back" aria-hidden="true">' in tile            # harmless, never shown without .is-active


def test_tiles_stay_ordinary_links(client):
    html = client.get("/catalogue").get_data(as_text=True)
    for tile in tiles(html):
        assert tile.startswith('<a class="tile') and 'href="/p/' in tile and tile.count("<a ") == 1
        assert "onclick" not in tile and "data-href" not in tile


def test_plates_on_home_and_product_pages_carry_the_kind_and_the_purchase_box_has_no_motion_layers(buyer, rag):
    home = buyer.get("/").get_data(as_text=True)
    hero = re.search(r'<a class="plate-link"[^>]*>', home).group(0)
    assert 'data-motion="hero-plate"' in hero and 'data-motion-kind="' in hero and 'aria-label=' in hero
    assert home.count('<div class="plate-cover">') == 1
    product = buyer.get(f"/p/{rag.slug}").get_data(as_text=True)
    assert re.search(r'<div class="plate" data-motion="plate" data-motion-kind="\w+"(?: data-fx="rise")?><div class="plate-cover"(?: data-fx="clip")?>', product)
    buy = product[product.index('<div class="buy"'):product.index('<dl class="def"')]
    assert "fx-" not in buy and "mk-" not in buy and "data-reveal" not in buy
    assert buy.count("<form") == 1 and 'data-add-to-cart' in buy


# ---- stylesheet ---------------------------------------------------------------------------------------------------------

def test_cover_zoom_and_tilt_stay_in_the_brief_for_every_kind():
    for kind in KINDS:
        decl = re.search(r'\[data-motion-kind="%s"\]\s*\{([^}]*)\}' % kind, SECTION).group(1)
        zoom = float(re.search(r"--zoom:\s*([\d.]+)", decl).group(1))
        tilt = float(re.search(r"--tilt:\s*-?([\d.]+)deg", decl).group(1))
        assert 1.02 <= zoom <= 1.035 and 1 <= tilt <= 2, (kind, zoom, tilt)


def test_no_hover_selector_no_shadow_no_gradient_and_will_change_only_on_the_flag_class():
    # the only :hover this section mentions is inside the reduced-motion block, where it switches an old effect off
    assert ":hover" not in SECTION.split("@media (prefers-reduced-motion: reduce)")[0]
    assert not re.search(r"gradient|box-shadow|text-shadow|filter:|drop-shadow|rgba?\(|#[0-9a-fA-F]{3,8}\b", SECTION)
    assert "will-change" not in SECTION
    assert re.search(r"(?m)^\.is-animating \{ will-change: transform, opacity; \}", CSS)


def test_the_old_always_on_hover_zoom_now_sits_behind_the_fine_pointer_guard():
    assert "@media (hover: hover) and (pointer: fine) { .tile:hover .tile-cover .cover { transform: scale(1.03); } }" in CSS
    assert not re.search(r"(?m)^\.tile:hover \.tile-cover \.cover", CSS)


def test_the_layers_never_take_pointer_input_and_stay_inside_the_cover():
    for selector in (".fx-back", ".fx-panel"):
        decl = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", SECTION, re.S).group(1)
        assert "position: absolute" in decl and "pointer-events: none" in decl, selector
    assert re.search(r"\.tile-cover \{ position: relative; border-bottom: 1px solid var\(--line\); overflow: hidden; \}", CSS)
    assert ".plate-cover { position: relative; overflow: hidden; }" in SECTION


def test_the_active_cover_rule_is_specific_enough_to_beat_the_fine_pointer_hover_zoom():
    active = re.search(r"(\.tile\.is-active \.tile-cover \.cover)[^{]*\{([^}]*)\}", SECTION)
    assert active and "rotate(var(--tilt))" in active.group(2) and "scale(var(--zoom))" in active.group(2)
    classes = lambda sel: len(re.findall(r"\.[\w-]+|:hover", sel))
    assert classes(active.group(1)) >= classes(".tile:hover .tile-cover .cover")


def test_the_sold_out_flag_stays_above_the_cover_and_the_motif_panel():
    z = lambda sel: int(re.search(re.escape(sel) + r"[^{]*\{[^}]*z-index:\s*(\d+)", SECTION).group(1))
    assert z(".tile-cover .out-flag") > z(".tile-cover .cover, .plate-cover .cover") and z(".tile-cover .out-flag") > z(".fx-panel")


def test_pressing_never_changes_the_pressed_elements_own_box():
    """A scale on the pressed link shrinks its hit area: press 2px inside a tile's edge and the pointer is outside it
    by the time the button is released, so the click lands on the grid and navigation is lost. Found in a browser."""
    pressed = [(m.group(1), m.group(2)) for m in re.finditer(r"(?m)^([^{}/@]*\.is-pressed[^{}]*)\{([^}]*)\}", re.sub(r"/\*.*?\*/", "", CSS, flags=re.S))]
    assert pressed
    for selector, body in pressed:
        assert not re.search(r"transform|scale|width|height|padding|margin|border|top:|left:|display", body), (selector, body)
        assert "opacity" in body


def test_every_rest_state_is_hidden_by_default_and_shown_only_under_is_active():
    for sel in (".fx-back", ".fx-panel", ".mk-up, .mk-left, .mk-right, .mk-drop, .mk-screen", ".mk-ring"):
        assert re.search(r"(?m)^" + re.escape(sel) + r"\s*\{[^}]*opacity:\s*0", SECTION), sel
    shown = re.findall(r"(?m)^(\.is-active [^{]+)\{[^}]*opacity:\s*1", SECTION)
    assert shown and all(s.startswith(".is-active") for s in shown)


def test_reduced_motion_removes_the_layers_and_the_tilt():
    tail = SECTION[SECTION.index("@media (prefers-reduced-motion: reduce)"):]
    assert ".fx-back, .fx-panel { display: none; }" in tail
    assert re.search(r"\.tile\.is-active \.tile-cover \.cover, [^{]*\.tile:hover \.tile-cover \.cover \{ transform: none; \}", tail)


# ---- motion.js behaviour under node ---------------------------------------------------------------------------------------

needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")

HARNESS = r"""
const src = require('fs').readFileSync(%s, 'utf8');
function matcher(sel, el) {
  return sel.split(',').map((x) => x.trim()).some((part) => {
    const m = part.match(/^\[([\w-]+)(?:="([^"]*)")?\]$/);
    return m && (m[2] === undefined ? m[1] in el.attrs : el.attrs[m[1]] === m[2]);
  });
}
class El {
  constructor(attrs, o = {}) {
    this.attrs = attrs || {}; this.parent = null; this.kids = []; this.cls = new Set(); this.fv = o.fv !== false;
    this.hasPanel = o.panel !== false; this.cover = new Cover();
    this.classList = { add: (c) => this.cls.add(c), remove: (c) => this.cls.delete(c), contains: (c) => this.cls.has(c),
                       toggle: (c, on) => { if (on) this.cls.add(c); else this.cls.delete(c); } };
  }
  add(k) { k.parent = this; this.kids.push(k); return k; }
  closest(sel) { let n = this; while (n) { if (n.attrs && matcher(sel, n)) return n; n = n.parent; } return null; }
  contains(n) { while (n) { if (n === this) return true; n = n.parent; } return false; }
  querySelector(sel) { if (sel === '.cover') return this.cover; if (sel === '.fx-panel') return this.hasPanel ? {} : null; return null; }
  matches(sel) { return sel === ':focus-visible' ? this.fv : matcher(sel, this); }
}
class Cover { constructor() { this.cls = new Set(); this.l = []; this.classList = { add: (c) => this.cls.add(c), remove: (c) => this.cls.delete(c) }; }
  addEventListener(t, f) { this.l.push(f); } removeEventListener(t, f) { this.l = this.l.filter((x) => x !== f); } }

function build(o = {}) {
  const root = new El({}), body = root.add(new El({}));
  const tileA = body.add(new El({ 'data-motion': 'tile' })), tileB = body.add(new El({ 'data-motion': 'tile' }));
  const sold = body.add(new El({ 'data-motion': 'tile' }, { panel: false }));
  const link = tileA.add(new El({}));
  const plate = body.add(new El({ 'data-motion': 'plate' })), buybox = body.add(new El({ 'data-motion': 'buybox' }));
  const input = buybox.add(new El({}));
  const plain = body.add(new El({}));
  const press = body.add(new El({ 'data-press': '' }));
  const docL = {}, winL = {};
  const doc = {
    activeElement: null,
    addEventListener(t, fn, opts) { (docL[t] = docL[t] || []).push({ fn, opts }); },
    querySelector: (sel) => (sel === '[data-motion="plate"]' ? plate : null),
    documentElement: { classList: { contains: () => false, remove() {} } },
  };
  const win = { addEventListener(t, fn) { winL[t] = fn; },
    matchMedia: (q) => ({ matches: q.indexOf('reduce') >= 0 ? !!o.calm : !o.noHover, addEventListener() {} }) };
  new Function('window', 'document', 'performance', 'requestAnimationFrame', 'cancelAnimationFrame', 'AbortController', src)(
    win, doc, { now: () => 0 }, () => 0, () => {}, AbortController);
  let prevented = 0;
  const fire = (type, target, extra = {}) => {
    const e = Object.assign({ type, target, relatedTarget: null, pointerType: 'mouse', button: 0, preventDefault() { prevented++; } }, extra);
    (docL[type] || []).forEach(({ fn, opts }) => { if (!(opts && opts.signal && opts.signal.aborted)) fn(e); });
  };
  return { tileA, tileB, sold, link, plate, buybox, input, plain, press, doc, fire, winL, get prevented() { return prevented; } };
}
const on = (...els) => els.filter((e) => e.cls.has('is-active')).length;
const out = {};
let t = build();
t.fire('pointerover', t.link); out.hoverA = t.tileA.cls.has('is-active');
t.fire('pointerout', t.link, { relatedTarget: t.tileB }); t.fire('pointerover', t.tileB);
out.onlyB = [t.tileA.cls.has('is-active'), t.tileB.cls.has('is-active'), on(t.tileA, t.tileB, t.sold, t.plate)];
t.fire('pointerout', t.tileB, { relatedTarget: t.plain }); out.leftToRest = on(t.tileA, t.tileB, t.sold, t.plate);
t.fire('pointerover', t.link); t.fire('pointerout', t.link, { relatedTarget: t.tileA }); out.childToParentStays = t.tileA.cls.has('is-active');
t = build(); t.fire('pointerover', t.sold); t.fire('pointerdown', t.sold);
out.sold = { active: on(t.sold), pressed: t.sold.cls.has('is-pressed') };
t = build(); t.fire('pointerover', t.tileA, { pointerType: 'touch' }); out.touchHoverIgnored = on(t.tileA);
t.fire('pointerdown', t.link, { pointerType: 'touch' });
out.touchDown = { active: t.tileA.cls.has('is-active'), pressed: t.tileA.cls.has('is-pressed') };
t.fire('pointerup', t.link, { pointerType: 'touch' }); out.touchUp = { active: on(t.tileA), pressed: t.tileA.cls.has('is-pressed') };
t.fire('pointerdown', t.tileA, { pointerType: 'touch' }); t.fire('pointercancel', t.tileA, { pointerType: 'touch' });
out.touchCancel = { active: on(t.tileA), pressed: t.tileA.cls.has('is-pressed') };
t.fire('pointerdown', t.press); out.dataPress = t.press.cls.has('is-pressed'); t.fire('pointerup', t.press); out.dataPressReleased = !t.press.cls.has('is-pressed');
t.fire('pointerdown', t.tileA, { button: 2 }); out.rightClickIgnored = on(t.tileA);
t = build({ noHover: true }); t.fire('pointerover', t.tileA); out.noHoverMouseIgnored = on(t.tileA);
t.fire('pointerdown', t.tileA); out.noHoverPointerdown = on(t.tileA);
t = build(); t.link.fv = true; t.doc.activeElement = t.link; t.fire('focusin', t.link); out.focusKeyboard = on(t.tileA);
t.fire('pointerover', t.link); t.fire('pointerout', t.link, { relatedTarget: t.plain }); out.keyboardFocusSurvivesPointerLeave = on(t.tileA);
t.doc.activeElement = null; t.fire('focusout', t.link, { relatedTarget: t.plain }); out.blurRests = on(t.tileA);
t = build(); t.link.fv = false; t.fire('focusin', t.link); out.mouseFocusIgnored = on(t.tileA);
t = build(); t.input.fv = true; t.fire('focusin', t.input); out.buyboxFocusPlaysPlate = [on(t.plate), on(t.buybox)];
t.fire('focusout', t.input, { relatedTarget: t.plain }); out.buyboxBlurRests = on(t.plate);
t = build({ calm: true }); t.fire('pointerover', t.tileA); t.fire('pointerdown', t.tileA); t.fire('focusin', t.link);
out.calm = { active: on(t.tileA), pressed: t.tileA.cls.has('is-pressed') };
t = build(); t.fire('pointerover', t.tileA); const cover = t.tileA.cover; out.animatingFlag = cover.cls.has('is-animating');
cover.l.forEach((f) => f({ target: cover, propertyName: 'opacity' })); out.flagKeptForOtherProps = cover.cls.has('is-animating');
cover.l.slice().forEach((f) => f({ target: cover, propertyName: 'transform' })); out.flagClearedAfterTransform = !cover.cls.has('is-animating');
t.fire('pointerover', t.tileA); t.winL.pagehide(); out.pagehideRests = on(t.tileA);
t.fire('pointerover', t.tileB); t.fire('pointerdown', t.tileB); out.afterPagehideDead = on(t.tileB);
out.preventDefaultCalls = t.prevented;
t = build(); t.fire('pointerover', t.tileA); t.fire('pointerdown', t.tileA); t.fire('pointerup', t.tileA); out.neverPrevented = t.prevented;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def behaviour():
    if NODE is None:
        pytest.skip("node is not installed")
    run = subprocess.run([NODE, "-e", HARNESS % json.dumps(str(MOTION_JS))], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


@needs_node
def test_hover_with_a_fine_pointer_activates_one_card_and_leaving_returns_to_rest(behaviour):
    assert behaviour["hoverA"] is True
    assert behaviour["onlyB"] == [False, True, 1]                  # moving to another card hands the state over
    assert behaviour["leftToRest"] == 0
    assert behaviour["childToParentStays"] is True               # moving between a card's own children is not leaving


@needs_node
def test_sold_out_tiles_only_get_the_press(behaviour):
    assert behaviour["sold"] == {"active": 0, "pressed": True}


@needs_node
def test_touch_uses_pointerdown_only_and_rests_when_the_finger_lifts_or_the_gesture_cancels(behaviour):
    assert behaviour["touchHoverIgnored"] == 0
    assert behaviour["touchDown"] == {"active": True, "pressed": True}
    assert behaviour["touchUp"] == {"active": 0, "pressed": False}
    assert behaviour["touchCancel"] == {"active": 0, "pressed": False}
    assert behaviour["dataPress"] is True and behaviour["dataPressReleased"] is True
    assert behaviour["rightClickIgnored"] == 0
    assert behaviour["noHoverMouseIgnored"] == 0 and behaviour["noHoverPointerdown"] == 1


@needs_node
def test_keyboard_focus_activates_and_blur_rests_but_mouse_focus_does_not(behaviour):
    assert behaviour["focusKeyboard"] == 1
    assert behaviour["keyboardFocusSurvivesPointerLeave"] == 1
    assert behaviour["blurRests"] == 0
    assert behaviour["mouseFocusIgnored"] == 0
    assert behaviour["buyboxFocusPlaysPlate"] == [1, 0] and behaviour["buyboxBlurRests"] == 0


@needs_node
def test_reduced_motion_binds_nothing_visible(behaviour):
    assert behaviour["calm"] == {"active": 0, "pressed": False}


@needs_node
def test_will_change_is_flagged_only_while_the_cover_transitions_and_everything_is_cleaned_up_on_pagehide(behaviour):
    assert behaviour["animatingFlag"] is True and behaviour["flagKeptForOtherProps"] is True
    assert behaviour["flagClearedAfterTransform"] is True
    assert behaviour["pagehideRests"] == 0 and behaviour["afterPagehideDead"] == 0


@needs_node
def test_navigation_is_never_gated_or_cancelled(behaviour):
    assert behaviour["neverPrevented"] == 0 and behaviour["preventDefaultCalls"] == 0
    code = re.sub(r"//[^\n]*|/\*.*?\*/", "", MOTION_JS.read_text(encoding="utf-8"), flags=re.S)
    assert "preventDefault" not in code and "stopPropagation" not in code and "href" not in code
    assert "location" not in code.replace("window.location.reload()", "")


def test_the_script_budget_and_no_timers_still_hold():
    text = MOTION_JS.read_text(encoding="utf-8")
    assert MOTION_JS.stat().st_size < 15 * 1024
    assert not re.search(r"setTimeout|setInterval", text)
    assert text.count("addEventListener(") >= 8 and "AbortController" in text and "ctl.abort()" in text
