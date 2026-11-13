"""MOTION-2: add-to-cart feedback, the cart badge, scroll reveal, the condensed header and the page fade.
The stylesheet and markup are tested directly; motion-flow.js is run under node against a small fake DOM."""
import gzip
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
CSS = (STATIC / "css" / "main.css").read_text(encoding="utf-8").replace("\r\n", "\n")
FLOW_JS = STATIC / "js" / "motion-flow.js"
APP_JS = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
SECTION = CSS[CSS.index("/* ===== Motion 2: flow"):]
CODE = re.sub(r"/\*.*?\*/", "", SECTION, flags=re.S)
NODE = shutil.which("node")


def rules(css):
    return [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"([^{}@/][^{}]*)\{([^{}]*)\}", css)]


# ---- markup hooks and the no-JS fallback ---------------------------------------------------------------------------

def test_the_flow_script_is_deferred_and_loads_after_motion_js_and_app_js(client):
    html = client.get("/").get_data(as_text=True)
    scripts = [s.rsplit("/", 1)[1] for s in re.findall(r'<script src="([^"]+)" defer></script>', html)]
    assert scripts == ["motion.js", "app.js", "motion-flow.js"]
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline script"


def test_the_cart_and_checkout_summaries_are_reveal_targets(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    for path in ("/cart", "/checkout"):
        html = buyer.get(path).get_data(as_text=True)
        assert re.search(r'<aside class="summary" data-reveal ', html), path


def test_server_rendered_pages_show_everything_without_javascript(client, buyer, rag):
    """Nothing is hidden or pending in the HTML itself: only the script ever adds .is-pending, and the CSS failsafe
    reveals those after 2s."""
    for path in ("/", "/catalogue", f"/p/{rag.slug}", "/login"):
        html = client.get(path).get_data(as_text=True)
        assert "is-pending" not in html and "is-in" not in html, path
        assert not re.search(r"\sstyle=", html), path
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    html = buyer.get(f"/p/{rag.slug}").get_data(as_text=True)
    assert re.search(r'<form class="buy-row" data-add-to-cart data-product-id="\d+"', html)     # the hook app.js and the flow script use
    assert 'class="btn" data-press type="submit">Add to cart</button>' in html
    assert 'data-cart-count' in html and re.search(r'data-cart-count[^>]*>1<', html)


def test_the_cart_badge_is_hidden_only_when_the_cart_is_empty(client, buyer, rag):
    assert re.search(r"data-cart-count hidden>", buyer.get("/").get_data(as_text=True))
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 2})
    html = buyer.get("/").get_data(as_text=True)
    assert "hidden" not in re.search(r"<span class=\"count\"[^>]*>", html).group(0)


def test_app_js_only_gained_the_three_events_the_flow_script_listens_for():
    assert APP_JS.count("new CustomEvent(") == 3
    for name in ("cart:count", "cart:added", "cart:rendered"):
        assert f'new CustomEvent("{name}"' in APP_JS
        assert f'"{name}"' in FLOW_JS.read_text(encoding="utf-8")


# ---- the stylesheet --------------------------------------------------------------------------------------------------

def test_only_transform_and_opacity_are_animated_in_this_section():
    names = {n for n, _ in re.findall(r"@keyframes ([\w-]+) \{(.*)", SECTION)}
    assert names == {"flow-page", "flow-check", "flow-bump", "flow-tick", "flow-select"}
    for name, line in re.findall(r"@keyframes ([\w-]+) \{(.*)\}", CODE):
        assert set(re.findall(r"([\w-]+)\s*:", line)) <= {"opacity", "transform"}, name
    for transition in re.findall(r"transition:\s*([^;]+);", CODE):
        if transition.strip() == "none":                    # the reduced-motion block switches them off
            continue
        assert {part.strip().split()[0] for part in transition.split(",")} <= {"opacity", "transform"}, transition


def test_the_section_has_no_layout_properties_no_shadows_no_gradients_and_no_will_change():
    assert not re.search(r"gradient|box-shadow|filter:|drop-shadow|will-change|rgba?\(|#[0-9a-fA-F]{3,8}\b|!important", CODE)
    header = [body for sel, body in rules(CODE) if "site-header" in sel]
    assert header and all(not re.search(r"padding|margin|height|width|top:|left:|position|display", b) for b in header)


def test_the_page_fade_is_150_to_200ms_and_has_no_exit_animation():
    m = re.search(r"(?m)^main \{ animation: flow-page (\d+)ms ", CODE)
    assert m and 150 <= int(m.group(1)) <= 200
    assert "beforeunload" not in FLOW_JS.read_text(encoding="utf-8") and "pagehide" not in FLOW_JS.read_text(encoding="utf-8")


def test_nothing_here_depends_on_hover_and_smooth_scrolling_respects_reduced_motion():
    assert ":hover" not in CODE
    assert re.search(r"@media \(prefers-reduced-motion: no-preference\) \{ html \{ scroll-behavior: smooth; \} \}", CODE)
    assert "scroll-margin-top" in CODE


def test_reduced_motion_turns_every_animation_in_this_section_off():
    tail = CODE[CODE.index("@media (prefers-reduced-motion: reduce)"):]
    for sel in ("main", ".count.is-bump", ".is-tick", '.filters li a[aria-current="true"]', '.btn[data-state="added"]::before'):
        assert sel in tail, sel
    assert "animation: none" in tail and "transition: none" in tail


def test_every_animated_class_in_this_section_is_one_the_script_sets_or_a_state_attribute():
    js = FLOW_JS.read_text(encoding="utf-8")
    for cls in ("is-bump", "is-tick", "is-condensed", "is-pending", "is-in"):
        assert cls in js or cls in CSS, cls
    assert 'dataset.state = "added"' in js


# ---- the script ------------------------------------------------------------------------------------------------------

def test_the_script_stays_inside_its_size_budget_and_uses_no_unsafe_apis():
    text = FLOW_JS.read_text(encoding="utf-8")
    assert len(gzip.compress(text.encode(), 9)) < 3 * 1024             # the whole change must add under 4 KB gzipped
    assert "innerHTML" not in text and 'setAttribute("style"' not in text and ".style.cssText" not in text
    assert "eval(" not in text and "document.write" not in text


needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")

HARNESS = r"""
const src = require('fs').readFileSync(%s, 'utf8');
class El {
  constructor(name, o = {}) {
    this.name = name; this.cls = new Set(); this.dataset = Object.assign({}, o.dataset || {}); this.textContent = o.text || '';
    this.attrs = o.attrs || {}; this.kids = []; this.l = {}; this.props = {}; this.offsetWidth = 1; this.parent = null; this.removed = [];
    this.classList = { add: (...c) => c.forEach((x) => this.cls.add(x)), remove: (...c) => c.forEach((x) => this.cls.delete(x)),
                       contains: (c) => this.cls.has(c), toggle: (c, on) => { on ? this.cls.add(c) : this.cls.delete(c); } };
    this.style = { setProperty: (k, v) => { this.props[k] = v; } };
    this.value = o.value;
    if (o.value === undefined) delete this.value;
  }
  add(k) { k.parent = this; this.kids.push(k); return k; }
  addEventListener(t, f) { (this.l[t] = this.l[t] || []).push(f); }
  removeEventListener(t, f) { this.l[t] = (this.l[t] || []).filter((x) => x !== f); }
  matches(sel) { return !!this.attrs[sel]; }
  querySelector(sel) { return (this.sub && this.sub[sel]) || null; }
  closest(sel) { let n = this; while (n) { if (n.attrs && n.attrs[sel]) return n; n = n.parent; } return null; }
  fireEnd() { (this.l.animationend || []).slice().forEach((f) => f({ target: this })); }
}

function setup(o = {}) {
  const badge = new El('badge', { text: String(o.count === undefined ? 0 : o.count) });
  const store = Object.assign({}, o.store || {});
  const docL = {}, winL = {}, timers = [];
  const els = o.els || {};
  const doc = {
    addEventListener: (t, f) => { (docL[t] = docL[t] || []).push(f); },
    querySelectorAll: (sel) => (sel === '[data-cart-count]' ? [badge] : (els[sel] || [])),
    querySelector: (sel) => (sel === '[data-cart-count]' ? badge : (els[sel] || [])[0] || null),
  };
  const win = {
    matchMedia: () => ({ matches: !!o.calm }), scrollY: 0, requestAnimationFrame: (f) => f(),
    addEventListener: (t, f) => { winL[t] = f; },
    sessionStorage: o.noStorage ? { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } }
                                : { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
  };
  if (o.io) win.IntersectionObserver = o.io;
  const g = { window: win, document: doc, setTimeout: (f, ms) => { timers.push({ f, ms }); return timers.length; }, clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].dead = true; } };
  new Function('window', 'document', 'IntersectionObserver', 'setTimeout', 'clearTimeout', src)(
    win, doc, win.IntersectionObserver, g.setTimeout, g.clearTimeout);
  const fire = (t, target, detail) => (docL[t] || []).forEach((f) => f({ type: t, target, detail }));
  return { badge, store, fire, timers, win, winL, doc };
}
const bumped = (b) => b.cls.has('is-bump');
const out = {};

// 1. badge: bumps once per increase, judged against the count kept in sessionStorage
let t = setup({ count: 2, store: { 'ps-cart-count': '1' } });
out.loadHigher = [bumped(t.badge), t.store['ps-cart-count']];
t.badge.fireEnd(); t.fire('cart:count', null, { count: 2 }); out.sameCountNoBump = bumped(t.badge);
t.fire('cart:count', null, { count: 3 }); out.increaseBumps = [bumped(t.badge), t.store['ps-cart-count']];
t.badge.fireEnd(); out.animationEndClears = [bumped(t.badge), t.badge.cls.has('is-animating')];
t.fire('cart:count', null, { count: 1 }); out.decreaseNoBump = bumped(t.badge);
t = setup({ count: 3 }); out.firstVisitNoBump = bumped(t.badge);
t = setup({ count: 1, store: { 'ps-cart-count': '1' } }); out.reloadSameNoBump = bumped(t.badge);
t = setup({ count: 1, noStorage: true }); t.fire('cart:count', null, { count: 2 }); out.noStorageNoThrowNoBump = bumped(t.badge);
t = setup({ count: 2, calm: true, store: { 'ps-cart-count': '1' } }); t.fire('cart:count', null, { count: 5 }); out.calmNoBump = bumped(t.badge);

// 2. add to cart: check and "Added" for a moment, then the label comes back
const btn = new El('btn', { text: 'Add to cart' });
const form = new El('form'); form.sub = { 'button[type=submit]': btn };
t = setup({ count: 0 });
t.fire('cart:added', form);
out.added = [btn.dataset.state, btn.textContent, t.timers.length, t.timers[0].ms];
t.fire('cart:added', form); out.addedTwiceKeepsLabel = [btn.dataset.label, btn.textContent, t.timers[0].dead === true];
t.timers[1].f(); out.reverted = [btn.dataset.state === undefined, btn.textContent];
t.fire('cart:added', new El('other')); out.noButtonIgnored = true;

// 3. numbers tick when they change, not on first sight
const total = new El('total', { text: '₹100' }), qty = new El('qty', { value: '1' });
t = setup({ count: 0, els: { '.stepper input, [data-line-total], [data-total], [data-count]': [total, qty] } });
out.firstSight = [total.cls.has('is-tick'), qty.cls.has('is-tick')];
total.textContent = '₹200'; t.fire('cart:rendered'); out.totalTicks = [total.cls.has('is-tick'), qty.cls.has('is-tick')];
total.fireEnd(); qty.value = '2'; t.fire('cart:rendered'); out.qtyTicks = [total.cls.has('is-tick'), qty.cls.has('is-tick')];

// 4. header: condensed past 40px
const header = new El('header');
t = setup({ count: 0, els: { '.site-header': [header] } });
out.headerAtTop = header.cls.has('is-condensed');
t.win.scrollY = 41; t.winL.scroll(); out.headerPast40 = header.cls.has('is-condensed');
t.win.scrollY = 40; t.winL.scroll(); out.headerAt40 = header.cls.has('is-condensed');

// 5. reveal on scroll
class IO {
  constructor(cb) { IO.cb = cb; IO.watched = []; IO.gone = []; }
  observe(el) { IO.watched.push(el); } unobserve(el) { IO.gone.push(el); }
}
const sel = '[data-reveal], [data-motion-group=\'tiles\'] [data-motion=\'tile\']';
const sec = new El('section', { attrs: { '[data-reveal]': true } }); const head = new El('head'); sec.sub = { '[data-motion-group=\'tiles\']': {}, '.section-head': head };
const plainSec = new El('plain', { attrs: { '[data-reveal]': true } }); plainSec.sub = {};
const tiles = Array.from({ length: 10 }, (_, i) => new El('tile' + i));
t = setup({ count: 0, io: IO, els: { [sel]: [sec, plainSec].concat(tiles) } });
out.pendingMarked = [IO.watched.length, IO.watched.includes(head), IO.watched.includes(sec), IO.watched.includes(plainSec), IO.watched.every((e) => e.cls.has('is-pending'))];
IO.cb(IO.watched.map((e) => ({ target: e, isIntersecting: true })));
out.revealed = IO.watched.every((e) => e.cls.has('is-in') && !e.cls.has('is-pending'));
out.stagger = tiles.map((e) => e.props['--i']);
out.unobserved = IO.gone.length;
const t2 = new El('late'); t = setup({ count: 0, io: IO, els: { [sel]: [t2] } });
IO.cb([{ target: t2, isIntersecting: false }]); out.notIntersectingStaysPending = [t2.cls.has('is-pending'), t2.cls.has('is-in')];
t = setup({ count: 0, els: { [sel]: [tiles[0]] } }); out.noObserverMarksNothing = !tiles[0].cls.has('is-pending') || tiles[0].cls.has('is-in');
const calmTile = new El('calmTile'); t = setup({ count: 0, calm: true, io: IO, els: { [sel]: [calmTile] } }); out.calmMarksNothing = !calmTile.cls.has('is-pending');
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def behaviour():
    if NODE is None:
        pytest.skip("node is not installed")
    run = subprocess.run([NODE, "-e", HARNESS % json.dumps(str(FLOW_JS))], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


@needs_node
def test_the_badge_bumps_exactly_once_per_increase(behaviour):
    b = behaviour
    assert b["loadHigher"] == [True, "2"]                 # a page that loads with a higher count than last seen bumps once
    assert b["sameCountNoBump"] is False
    assert b["increaseBumps"] == [True, "3"]
    assert b["animationEndClears"] == [False, False]
    assert b["decreaseNoBump"] is False
    assert b["firstVisitNoBump"] is False and b["reloadSameNoBump"] is False
    assert b["noStorageNoThrowNoBump"] is False
    assert b["calmNoBump"] is False


@needs_node
def test_add_to_cart_shows_added_then_restores_the_label_and_never_loses_it(behaviour):
    b = behaviour
    assert b["added"] == ["added", "Added", 1, 1600]
    assert b["addedTwiceKeepsLabel"] == ["Add to cart", "Added", True]      # the second click cancels the first timer
    assert b["reverted"] == [True, "Add to cart"]


@needs_node
def test_changed_numbers_tick_and_unchanged_ones_do_not(behaviour):
    b = behaviour
    assert b["firstSight"] == [False, False]
    assert b["totalTicks"] == [True, False]
    assert b["qtyTicks"] == [False, True]


@needs_node
def test_the_header_condenses_past_40px_only(behaviour):
    b = behaviour
    assert (b["headerAtTop"], b["headerPast40"], b["headerAt40"]) == (False, True, False)


@needs_node
def test_scroll_reveal_marks_pending_reveals_once_in_batches_of_at_most_eight(behaviour):
    b = behaviour
    # 10 tiles + a plain section + the heading row of the section that holds a tile grid; the tile section itself is not marked
    assert b["pendingMarked"] == [12, True, False, True, True]
    assert b["revealed"] is True and b["unobserved"] == 12
    assert b["stagger"] == [2, 3, 4, 5, 6, 7, 7, 7, 7, 7]       # arrival order after the two section targets, capped at 7
    assert b["notIntersectingStaysPending"] == [True, False]


@needs_node
def test_without_an_observer_or_with_reduced_motion_nothing_is_ever_marked_pending(behaviour):
    b = behaviour
    assert b["noObserverMarksNothing"] is True and b["calmMarksNothing"] is True
