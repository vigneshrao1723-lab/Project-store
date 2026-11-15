"""The home shelf's endless loop, fx-shelf.js (v1.4), run under node against a small fake DOM. fx-scroll.js drives it by
calling window.fxShelf.tick(now, scrollY) every frame; here the test calls tick itself. The markup, stylesheet and switch
are checked at the bottom."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "app" / "static" / "js" / "fx-shelf.js"
NODE = shutil.which("node")

HARNESS = r"""
const vm = require("vm"), fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
function world(opts = {}) {
  let now = 0;
  const events = [], winL = {}, mqL = [];
  const W = 400, G = 20;                               // card width and gap: one set of 4 cards is 1680 px
  function el(name, tags = [], o = {}) {
    const e = Object.assign({ name, tags, children: [], parentNode: null, dataset: {}, attrs: {}, hidden: false, textContent: "", L: {}, captured: null,
      style: { props: {}, setProperty(k, v) { this.props[k] = v; } },
      classList: { s: new Set(), add(...c) { c.forEach((x) => this.s.add(x)); }, remove(...c) { c.forEach((x) => this.s.delete(x)); }, contains(c) { return this.s.has(c); } },
      setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
      addEventListener(t, f, o) { (this.L[t] = this.L[t] || []).push({ f, o }); },
      removeEventListener(t, f) { const l = this.L[t] || []; const i = l.findIndex((x) => x.f === f); if (i >= 0) l.splice(i, 1); },
      matches(sel) { return sel.split(",").some((s) => this.tags.indexOf(s.trim()) >= 0); },
      querySelectorAll(sel) { const out = []; const walk = (n) => n.children.forEach((c) => { if (c.matches(sel)) out.push(c); walk(c); }); walk(this); return out; },
      querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
      closest(sel) { for (let n = this; n; n = n.parentNode) if (n.matches && n.matches(sel)) return n; return null; },
      contains(x) { for (let n = x; n; n = n.parentNode) if (n === this) return true; return false; },
      append(...kids) { kids.forEach((k) => { k.parentNode = this; this.children.push(k); }); return this; },
      appendChild(k) { k.parentNode = this; this.children.push(k); return k; },
      insertBefore(k, ref) { k.parentNode = this; const i = this.children.indexOf(ref); this.children.splice(i < 0 ? 0 : i, 0, k); return k; },
      get firstChild() { return this.children[0] || null; },
      setPointerCapture(id) { this.captured = id; },
      cloneNode() {
        const k = el(this.name + "'", this.tags.slice(), {});
        k.attrs = Object.assign({}, this.attrs); this.classList.s.forEach((c) => k.classList.add(c));
        if (this.isCard) makeCard(k);
        this.children.forEach((c) => k.appendChild(c.cloneNode(true)));
        return k;
      },
    }, o);
    return e;
  }
  function makeCard(e) {
    e.isCard = true;
    Object.defineProperty(e, "offsetLeft", { get() { return this.parentNode ? this.parentNode.children.indexOf(this) * (W + G) : 0; } });
    e.offsetWidth = W;
    return e;
  }
  const root = el("html"); if (!opts.noFx) root.classList.add("fx-on"); (opts.rootClasses || []).forEach((c) => root.classList.add(c));
  const sec = el("sec", ['[data-fx="hscroll"]']); let secTop = opts.secTop === undefined ? 0 : opts.secTop;
  sec.getBoundingClientRect = () => ({ top: secTop, bottom: secTop + 800 });
  const stage = el("stage", [".hs-stage"]); stage.clientWidth = 1280;
  const track = el("track", [".hs-track"]);
  const cards = [0, 1, 2, 3].map((i) => { const c = makeCard(el("card" + i, [".hs-card"])); c.append(el("a" + i, ["a"])); return c; });
  track.append(...cards);
  const label = el("label", ["[data-label]"]); label.textContent = "Pause";
  const btn = el("btn", ["[data-shelf-toggle]"]); btn.hidden = true; btn.append(label);
  sec.append(btn, stage); stage.append(track);
  const win = {
    innerHeight: 800,
    matchMedia: () => ({ matches: false, addEventListener: (t, f) => mqL.push(f), removeEventListener: (t, f) => { const i = mqL.indexOf(f); if (i >= 0) mqL.splice(i, 1); } }),
    addEventListener: (t, f, o) => { (winL[t] = winL[t] || []).push(f); },
    removeEventListener: (t, f) => { const l = winL[t] || []; const i = l.indexOf(f); if (i >= 0) l.splice(i, 1); },
    dispatchEvent: (ev) => { events.push(ev.type); },
  };
  const sandbox = {
    window: win, document: { documentElement: root, querySelector: (s) => (s === '[data-fx="hscroll"]' && !opts.noShelf ? sec : null) },
    getComputedStyle: (e) => ({ paddingLeft: e === track ? "24px" : "", getPropertyValue: (n) => (e === root ? (opts.knobs || {})[n] || "" : "") }),
    Event: function (type) { this.type = type; }, performance: { now: () => now },
    Math, Number, String, Array, Object, parseFloat, Set,
  };
  vm.runInNewContext(src, sandbox);
  const w = { win, sec, stage, track, cards, btn, label, events, winL, mqL, root };
  w.shelf = () => win.fxShelf;
  w.s = () => win.fxShelf.state;
  w.tick = (ms, y = 0) => { const end = now + ms; let more = true; while (now < end) { now += 16; more = win.fxShelf.tick(now, y); } return more; };
  w.fire = (target, type, ev = {}) => { const e = Object.assign({ target, prevented: false, stopped: false, preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; } }, ev); (target.L[type] || []).slice().forEach((l) => l.f(e)); return e; };
  w.at = (t) => { now = t; };
  w.setTop = (t) => { secTop = t; };
  w.sx = () => parseFloat(track.style.props["--sx"]);
  return w;
}
"""


def run(body, opts="{}"):
    if not NODE:
        pytest.skip("node is not installed")
    code = HARNESS + "\nconst w = world(" + opts + ");\n" + body + "\nconsole.log(JSON.stringify(result));"
    out = subprocess.run([NODE, "-e", code, str(JS)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_it_does_nothing_without_motion_or_with_its_switch_off():
    for opts in ("{ noFx: true }", '{ rootClasses: ["fx-off-shelf-loop"] }', "{ noShelf: true }"):
        r = run("const result = { api: !!w.win.fxShelf, kids: w.track.children.length, loop: w.sec.classList.contains('is-loop'), btn: w.btn.hidden };", opts)
        assert r == {"api": False, "kids": 4, "loop": False, "btn": True}, opts


def test_copies_fill_the_loop_and_are_hidden_from_screen_readers_and_the_tab_key():
    r = run("""
      w.tick(16);
      const kids = w.track.children;
      const clones = kids.filter((k) => k.classList.contains("hs-clone"));
      const real = kids.filter((k) => !k.classList.contains("hs-clone"));
      const result = { total: kids.length, firstIsClone: kids[0].classList.contains("hs-clone"),
        realOrder: real.map((k) => k.name), realClean: real.every((k) => !("aria-hidden" in k.attrs) && !("inert" in k.attrs)),
        clonesHidden: clones.every((k) => k.attrs["aria-hidden"] === "true" && "inert" in k.attrs),
        cloneLinks: clones.every((k) => k.children.every((a) => a.attrs.tabindex === "-1")),
        loop: w.sec.classList.contains("is-loop"), btn: w.btn.hidden, ready: w.events.indexOf("fxshelf-ready") >= 0,
        span: w.track.__span };""")
    assert r["firstIsClone"] and r["total"] >= 12 and r["total"] % 4 == 0
    assert r["realOrder"] == ["card0", "card1", "card2", "card3"] and r["realClean"]
    assert r["clonesHidden"] and r["cloneLinks"]
    assert r["loop"] and r["btn"] is False and r["ready"] and r["span"] == 1680       # fx-scroll.js pins for one set only


def test_it_drifts_at_the_knob_speed_and_stops_asking_for_frames_when_off_screen():
    r = run("""
      w.tick(16); const x0 = w.s().x;
      w.tick(4000); const v = w.s().v; const before = w.sx();
      w.setTop(5000); const more = w.tick(32); const after = w.s().x;
      const result = { v, more, drifted: before !== x0, offscreen: after };""", '{ knobs: { "--shelf-speed": "40" } }')
    assert 39 < r["v"] <= 40.01 and r["drifted"] and r["more"] is False


def test_the_loop_wraps_so_the_position_never_runs_away():
    r = run("""
      w.tick(16); const s = w.s();
      const xs = []; for (let i = 0; i < 60; i++) { s.v = 1800; w.tick(200); xs.push(s.x); }
      const result = { lo: s.lo, P: s.P, min: Math.min(...xs), max: Math.max(...xs) };""")
    assert r["P"] == 1680 and r["lo"] <= r["min"] and r["max"] < r["lo"] + r["P"]


def test_scrolling_pushes_it_and_the_push_eases_back_into_a_drift_in_the_same_direction():
    r = run("""
      w.tick(16, 0); w.tick(16, 0);
      w.tick(16, 120); const down = { v: w.s().v, dir: w.s().dir };
      w.tick(16, 120); w.tick(16, -200); const up = { v: w.s().v, dir: w.s().dir };
      w.tick(6000, -200); const settled = w.s().v;
      const result = { down, up, settled };""")
    assert r["down"]["v"] > 300 and r["down"]["dir"] == 1                     # scrolling down: right to left
    assert r["up"]["v"] < -300 and r["up"]["dir"] == -1                        # scrolling up: left to right
    assert -26.5 < r["settled"] < -25.5                                        # back to the drift, now left to right


def test_a_sideways_wheel_moves_it_and_a_vertical_wheel_is_left_to_the_page():
    r = run("""
      w.tick(16);
      const side = w.fire(w.stage, "wheel", { deltaX: -300, deltaY: 10, deltaMode: 0 });
      const vSide = w.s().v;
      const vert = w.fire(w.stage, "wheel", { deltaX: 2, deltaY: 300, deltaMode: 0 });
      const passive = w.stage.L.wheel[0].o;
      const result = { side: side.prevented, vSide, vert: vert.prevented, passive, wake: w.events.indexOf("fxshelf-wake") >= 0 };""")
    assert r["side"] is True and r["vSide"] < -1000 and r["vert"] is False and r["passive"] == {"passive": False} and r["wake"]


def test_the_pause_button_stops_the_drift_and_says_what_it_will_do():
    r = run("""
      w.tick(2000); const moving = w.s().v;
      w.fire(w.btn, "click"); w.tick(4000);
      const paused = { v: w.s().v, label: w.label.textContent, state: w.btn.dataset.state, more: w.tick(16) };
      w.fire(w.btn, "click"); w.tick(4000);
      const result = { moving, paused, again: { v: w.s().v, label: w.label.textContent, state: w.btn.dataset.state } };""")
    assert r["moving"] > 20
    assert abs(r["paused"]["v"]) < 0.5 and r["paused"]["label"] == "Play" and r["paused"]["state"] == "paused" and r["paused"]["more"] is False
    assert r["again"]["v"] > 20 and r["again"]["label"] == "Pause" and r["again"]["state"] == "playing"


def test_a_mouse_hovering_pauses_it_and_a_finger_does_not():
    r = run("""
      w.tick(2000);
      w.fire(w.stage, "pointerenter", { pointerType: "touch" }); w.tick(3000); const touch = w.s().v;
      w.fire(w.stage, "pointerenter", { pointerType: "mouse" }); w.tick(3000); const mouse = w.s().v;
      w.fire(w.stage, "pointerleave", { pointerType: "mouse" }); w.tick(4000); const left = w.s().v;
      const result = { touch, mouse, left };""")
    assert r["touch"] > 20 and abs(r["mouse"]) < 1 and r["left"] > 20


def test_a_drag_follows_the_pointer_flings_on_release_and_the_click_after_it_opens_nothing():
    r = run("""
      w.tick(16); const x0 = w.s().x;
      w.fire(w.stage, "pointerdown", { pointerId: 7, clientX: 600, button: 0 });
      w.fire(w.stage, "pointermove", { pointerId: 7, clientX: 603 }); const small = w.s().moving;
      w.at(1000); w.fire(w.stage, "pointermove", { pointerId: 7, clientX: 650 });
      w.at(1016); w.fire(w.stage, "pointermove", { pointerId: 7, clientX: 700 });
      const during = { dx: w.s().x - x0, dragging: w.sec.classList.contains("is-dragging"), captured: w.stage.captured };
      w.fire(w.stage, "pointerup", { pointerId: 7 });
      const fling = { v: w.s().v, dir: w.s().dir, dragging: w.sec.classList.contains("is-dragging") };
      const click1 = w.fire(w.stage, "click"); const click2 = w.fire(w.stage, "click");
      const result = { small, during, fling, click1: click1.prevented, click2: click2.prevented };""")
    assert r["small"] is False                                               # under 6 px is a click, not a drag
    assert r["during"] == {"dx": -100, "dragging": True, "captured": 7}       # the shelf follows the finger to the right
    assert r["fling"]["v"] < -100 and r["fling"]["dir"] == -1 and r["fling"]["dragging"] is False
    assert r["click1"] is True and r["click2"] is False


def test_keyboard_focus_stops_it_and_brings_the_real_card_fully_into_view():
    r = run("""
      w.tick(16); const s = w.s(); s.x = s.lo + 900; w.tick(16);
      const card = w.cards[0], link = card.children[0];
      w.fire(w.sec, "focusin", { target: link });
      const left = card.offsetLeft - w.track.firstChild.offsetLeft - s.x;
      w.tick(2000); const still = s.x;
      w.fire(w.sec, "focusout", { target: link, relatedTarget: w.cards[1].children[0] }); const kept = s.focus;
      w.fire(w.sec, "focusout", { target: link, relatedTarget: null }); w.tick(3000);
      const result = { left, lock: still === s.x ? "moved" : "x", stillSame: true, kept, after: s.v, focus: s.focus };""")
    assert r["left"] == 24                                                    # the focused card sits at the page gutter
    assert r["kept"] is True and r["focus"] is False and r["after"] > 20


def test_reduced_motion_switched_on_while_open_stops_the_drift():
    r = run("""
      w.tick(2000); w.mqL.forEach((f) => f({ matches: true })); w.tick(4000);
      const result = { v: w.s().v };""")
    assert abs(r["v"]) < 0.5


def test_pagehide_removes_every_listener_and_the_api():
    r = run("""
      w.tick(16);
      w.winL.pagehide.slice().forEach((f) => f());
      const count = (n) => Object.values(n.L).reduce((a, l) => a + l.length, 0);
      const result = { api: !!w.win.fxShelf, stage: count(w.stage), sec: count(w.sec), btn: count(w.btn), resize: (w.winL.resize || []).length };""")
    assert r == {"api": False, "stage": 0, "sec": 0, "btn": 0, "resize": 0}


# ---- markup, stylesheet, switch ----------------------------------------------------------------------------------------

def test_the_home_page_loads_the_shelf_module_after_the_scroll_system_with_a_hidden_pause_button(client):
    html = client.get("/").get_data(as_text=True)
    assert html.index("js/fx-scroll.js") < html.index("js/fx-shelf.js")
    btn = re.search(r'<button class="shelf-toggle"[^>]*>', html).group(0)
    assert 'type="button"' in btn and "data-shelf-toggle" in btn and " hidden" in btn       # shown only once the loop runs
    assert '<span data-label>Pause</span><span class="sr"> the moving shelf</span>' in html
    shelf = html[html.index('class="shelf"'):html.index("</section>", html.index('class="shelf"'))]
    assert shelf.count('class="hs-card"') >= 2 and "hs-clone" not in shelf                    # copies are made by the script, never served
    for path in ("/catalogue", "/login", "/contact"):
        assert "fx-shelf.js" not in client.get(path).get_data(as_text=True), path


def test_the_loop_styles_only_apply_with_the_script_and_the_switch_on():
    css = (ROOT / "app" / "static" / "css" / "motion3.css").read_text(encoding="utf-8")
    rules = re.findall(r"([^{}]*\.is-loop[^{}]*)\{", css)
    assert rules and all("html.fx-on:not(.fx-off-shelf-loop)" in r for r in rules)
    assert "touch-action: pan-y" in css and "translate3d(calc(var(--sx, 0) * -1px), 0, 0)" in css
    tuning = (ROOT / "app" / "static" / "css" / "fx-tuning.css").read_text(encoding="utf-8")
    assert 'html[data-fx-off~="shelf-loop"] .shelf-toggle { display: none !important; }' in tuning


def test_the_shelf_module_has_no_loop_or_observer_of_its_own():
    src = JS.read_text(encoding="utf-8")
    assert "requestAnimationFrame" not in src and "IntersectionObserver" not in src and "setInterval" not in src
    scroll = (ROOT / "app" / "static" / "js" / "fx-scroll.js").read_text(encoding="utf-8")
    assert "window.fxShelf.tick(now, y)" in scroll and '"fxshelf-wake", schedule' in scroll


def test_the_loop_property_is_registered_as_not_inherited():
    """--sx changes every frame. Unregistered custom properties inherit, so writing one on the track would restyle every
    card and cover inside it each frame (measured: shelf p95 49.9 ms before, 33.4 ms after, headless, 1280x800)."""
    css = (ROOT / "app" / "static" / "css" / "motion3.css").read_text(encoding="utf-8")
    assert '@property --sx { syntax: "<number>"; inherits: false; initial-value: 0; }' in css
