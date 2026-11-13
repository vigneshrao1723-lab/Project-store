"""Motion 3, item A: the Add to cart button and the header count pulse. The markup and stylesheet are tested
directly; fx-cart.js runs under node against a small fake DOM with a fake clock, so the timings, the error path, the
reduced-motion path and the "no animation if the pieces are missing" path are all exercised."""
import gzip
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "motion3.css").read_text(encoding="utf-8").replace("\r\n", "\n")
JS = ROOT / "app" / "static" / "js" / "fx-cart.js"
NODE = shutil.which("node")
BARE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S).split(".result {")[0]        # this file also holds the payment and scroll sections, which have their own tests


def section(start, end=None):
    text = BARE[BARE.index(start):]
    return text.split(end)[0] if end else text


CART = section(".atc {", ".count.is-bump {")


# ---- markup ---------------------------------------------------------------------------------------------------------

def test_the_button_keeps_its_name_and_hides_the_decorations_from_screen_readers(buyer, rag):
    html = buyer.get(f"/p/{rag.slug}").get_data(as_text=True)
    button = re.search(r'<button class="btn atc".*?</button>', html, re.S).group(0)
    assert '<span class="atc-label">Add to cart</span>' in button
    assert button.count('aria-hidden="true"') == 2                  # the moving icon and the "Added" layer
    assert "style=" not in button
    assert 'data-add-to-cart' in html and 'role="status"' in html    # the live region app.js writes to is unchanged


def test_signed_out_visitors_get_the_plain_sign_in_link_and_no_script(client, rag):
    html = client.get(f"/p/{rag.slug}").get_data(as_text=True)
    assert 'class="btn atc"' not in html
    assert "fx-cart.js" not in html


def test_the_script_is_only_loaded_where_the_button_is(buyer, rag):
    html = buyer.get(f"/p/{rag.slug}").get_data(as_text=True)
    scripts = re.findall(r'<script src="([^"]+)" defer></script>', html)
    assert [s.rsplit("/", 1)[1] for s in scripts] == ["motion.js", "app.js", "fx-scroll.js", "fx-ui.js", "fx-cart.js"]
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html)
    home = buyer.get("/").get_data(as_text=True)
    assert "fx-cart.js" not in home


def test_the_stylesheet_is_linked_once_after_main(client):
    html = client.get("/").get_data(as_text=True)
    links = re.findall(r'<link rel="stylesheet" href="([^"]+)"', html)
    assert [l.rsplit("/", 1)[1] for l in links] == ["main.css", "motion3.css", "motion3-ui.css"]


# ---- stylesheet -----------------------------------------------------------------------------------------------------

def keyframes(name):
    return re.search(r"@keyframes %s \{(.*?)\n(?=@|\.|/\*|$)" % re.escape(name), BARE + "\n", re.S).group(1)


def test_cart_keyframes_move_only_transform_and_opacity_and_the_tick_draws_with_dashoffset():
    names = re.findall(r"@keyframes (atc-[\w-]+|fx-bump) ", BARE)
    assert len(names) >= 10
    for name in names:
        props = set(re.findall(r"([\w-]+)\s*:", keyframes(name)))
        allowed = {"opacity", "transform"} | ({"stroke-dashoffset"} if name == "atc-draw" else set())
        assert props <= allowed, (name, props)


def test_no_hover_no_hidden_default_no_inline_style_and_will_change_only_while_animating():
    assert ":hover" not in BARE and "!important" not in BARE
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", BARE):
        if "will-change" in body:
            assert ".is-animating" in sel, sel
    # the only things that start hidden are the layers the animation reveals, never the button's own label
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", BARE):
        if sel.strip() in (".atc-label", ".atc", ".atc-go"):
            assert "opacity" not in body, sel
    assert "display: none" not in BARE and "visibility: hidden" not in BARE


def test_every_state_the_script_can_set_has_css():
    for state in ("adding", "added", "back", "undo"):
        assert f'.atc[data-state="{state}"]' in CART, state


def test_the_buttons_box_is_never_resized_by_the_animation():
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", CART):
        assert not re.search(r"(^|[;\s])(width|height|padding|margin|top|left|font-size|border-width)\s*:", body) or "atc-go" in sel or "atc-item" in sel or "atc-done" in sel, sel


def test_reduced_motion_removes_every_animation_and_shows_the_added_state_at_once():
    inner = re.search(r"@media \(prefers-reduced-motion: reduce\) \{(.*)\n\}", BARE, re.S).group(1)
    assert re.search(r"\.atc\[data-state\] \* \{ animation: none; \}", inner)
    assert re.search(r'\[data-state="added"\] \.atc-done \{ opacity: 1; \}', inner)
    assert re.search(r'\[data-state="added"\] \.atc-tick \{ stroke-dashoffset: 0; \}', inner)
    assert ".count.is-bump { animation: none; }" in inner


def test_the_button_is_not_dimmed_while_app_js_disables_it_for_the_request():
    assert re.search(r"\.atc\[data-state\] \{ opacity: 1; \}", BARE)


def test_script_is_small():
    assert len(gzip.compress(JS.read_bytes(), 9)) < 2 * 1024


# ---- the script, under node ------------------------------------------------------------------------------------------

HARNESS = r"""
const vm = require("vm"), fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
function run(opts) {
  let now = 0, timers = [], seq = 0;
  const observers = [];
  const el = (extra) => Object.assign({
    dataset: {}, style: { props: {}, setProperty(k, v) { this.props[k] = v; } },
    classList: { s: new Set(), add(...c) { c.forEach((x) => this.s.add(x)); }, remove(...c) { c.forEach((x) => this.s.delete(x)); }, contains(c) { return this.s.has(c); } },
    offsetWidth: 1, listeners: {},
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    getBoundingClientRect() { return { left: 0, right: 100, width: 100, height: 40 }; },
  }, extra);
  const go = el({ getBoundingClientRect() { return { left: 10, right: 32, width: 22, height: 22 }; } });
  const btn = el({ querySelector: (s) => (s === ".atc-go" ? go : null) });
  const note = el({ hasLink: false, querySelector(s) { return s === "a" && this.hasLink ? {} : null; } });
  const buy = { querySelector: (s) => (s === "[data-note]" ? note : null) };
  const form = el({ querySelector: (s) => (s === ".atc" && !opts.noButton ? btn : null), closest: () => buy });
  const count = el({ textContent: String(opts.count ?? 0) });
  const log = [];
  const sandbox = {
    setTimeout: (f, ms) => { const id = ++seq; timers.push({ id, at: now + ms, f }); return id; },
    clearTimeout: (id) => { timers = timers.filter((t) => t.id !== id); },
    performance: { now: () => now },
    window: { matchMedia: () => ({ matches: !!opts.calm }) },
    MutationObserver: class { constructor(cb) { this.cb = cb; } observe(target) { observers.push({ target, cb: this.cb }); } },
    document: { querySelectorAll: (s) => (s === "form[data-add-to-cart]" ? [form] : s === "[data-cart-count]" ? [count] : []) },
  };
  sandbox.window.matchMedia = sandbox.window.matchMedia;
  vm.runInNewContext(src, sandbox);
  const advance = (ms) => { const end = now + ms; for (;;) { timers.sort((a, b) => a.at - b.at); const t = timers[0]; if (!t || t.at > end) break; timers.shift(); now = t.at; t.f(); } now = end; };
  const fire = (target) => observers.filter((o) => o.target === target).forEach((o) => o.cb());
  const state = () => btn.dataset.state || null;
  const submit = () => (form.listeners.submit || []).forEach((f) => f());
  return { advance, fire, state, submit, btn, note, count, go, timers: () => timers.length };
}
"""


def run_node(body):
    if not NODE:
        pytest.skip("node is not installed")
    out = subprocess.run([NODE, "-e", HARNESS + "\n" + body + "\nconsole.log(JSON.stringify(result));", str(JS)],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_success_walks_adding_then_added_then_back_then_idle_on_the_stated_timings():
    r = run_node("""
      const t = run({}); const seen = [];
      t.submit(); seen.push(["submit", t.state()]);
      t.advance(60); t.note.hasLink = true; t.fire(t.note);                 // the request answered after 60 ms
      t.advance(299); seen.push(["359ms", t.state()]);
      t.advance(1); seen.push(["360ms", t.state()]);
      t.advance(1239); seen.push(["1599ms", t.state()]);
      t.advance(1); seen.push(["1600ms", t.state()]);
      t.advance(399); seen.push(["1999ms", t.state()]);
      t.advance(1); seen.push(["2000ms", t.state()]);
      const result = { seen, vars: t.btn.style.props, left: t.timers() };""")
    assert r["seen"] == [["submit", "adding"], ["359ms", "adding"], ["360ms", "added"], ["1599ms", "added"],
                         ["1600ms", "back"], ["1999ms", "back"], ["2000ms", None]]
    assert r["vars"] == {"--atc-x": "29px", "--atc-out": "98px", "--atc-in": "-40px"}
    assert r["left"] == 0, "no timer is left running"


def test_a_slow_answer_still_gets_the_whole_added_state():
    r = run_node("""
      const t = run({}); t.submit(); t.advance(2500);
      t.note.hasLink = true; t.fire(t.note); t.advance(0); const a = t.state();
      t.advance(1239); const b = t.state(); t.advance(1); const c = t.state();
      const result = { a, b, c };""")
    assert r == {"a": "added", "b": "added", "c": "back"}


def test_an_error_rolls_the_cart_back_and_never_shows_added():
    r = run_node("""
      const t = run({}); t.submit(); t.advance(100); t.note.hasLink = false; t.fire(t.note);
      const a = t.state(); t.advance(319); const b = t.state(); t.advance(1); const c = t.state();
      const result = { a, b, c, timers: t.timers() };""")
    assert r == {"a": "undo", "b": "undo", "c": None, "timers": 0}


def test_no_answer_puts_the_button_back_after_eight_seconds():
    r = run_node("""
      const t = run({}); t.submit(); t.advance(7999); const a = t.state(); t.advance(1);
      const result = { a, b: t.state() };""")
    assert r == {"a": "adding", "b": None}


def test_a_second_click_during_added_restarts_added_instead_of_sending_the_cart_back_to_the_left():
    r = run_node("""
      const t = run({}); t.submit(); t.advance(50); t.note.hasLink = true; t.fire(t.note); t.advance(1000);
      const mid = t.state(); t.submit(); const during = t.state();
      t.advance(40); t.fire(t.note); t.advance(0); const again = t.state();
      t.advance(1239); const held = t.state(); t.advance(1); const back = t.state();
      const result = { mid, during, again, held, back };""")
    assert r == {"mid": "added", "during": "added", "again": "added", "held": "added", "back": "back"}


def test_reduced_motion_skips_adding_and_shows_added_at_once_and_skips_the_back_animation():
    r = run_node("""
      const t = run({ calm: true }); t.submit(); const a = t.state();
      t.advance(10); t.note.hasLink = true; t.fire(t.note); t.advance(0); const b = t.state();
      t.advance(1239); const c = t.state(); t.advance(1); const d = t.state();
      const result = { a, b, c, d };""")
    assert r == {"a": None, "b": "added", "c": "added", "d": None}


def test_an_error_with_reduced_motion_changes_nothing():
    r = run_node("""
      const t = run({ calm: true }); t.submit(); t.advance(5); t.fire(t.note);
      const result = { s: t.state() };""")
    assert r == {"s": None}


def test_the_count_pulses_only_when_it_goes_up():
    r = run_node("""
      const t = run({ count: 2 }); const seen = [];
      t.count.textContent = "3"; t.fire(t.count); seen.push(t.count.classList.contains("is-bump"));
      t.count.listeners.animationend[0](); seen.push(t.count.classList.contains("is-bump"));
      t.count.textContent = "1"; t.fire(t.count); seen.push(t.count.classList.contains("is-bump"));
      t.count.textContent = "1"; t.fire(t.count); seen.push(t.count.classList.contains("is-bump"));
      t.count.textContent = "4"; t.fire(t.count); seen.push(t.count.classList.contains("is-bump"));
      const result = { seen };""")
    assert r["seen"] == [True, False, False, False, True]


def test_the_count_does_not_pulse_under_reduced_motion_and_a_page_without_the_button_is_left_alone():
    assert run_node("""
      const t = run({ count: 0, calm: true }); t.count.textContent = "1"; t.fire(t.count);
      const result = { bump: t.count.classList.contains("is-bump") };""") == {"bump": False}
    assert run_node("""
      const t = run({ noButton: true }); t.submit();
      const result = { s: t.state(), timers: t.timers() };""") == {"s": None, "timers": 0}
