"""The interface layer (motion3-ui.css and fx-ui.js): checkout progress, field feedback, the posting button, toasts, cart row
motion, the order timeline, drifting art, and the global polish. The rule for all of it: a control is never hidden, never
delayed, and never made unusable by its animation."""
import gzip
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "motion3-ui.css").read_text(encoding="utf-8").replace("\r\n", "\n")
BARE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
JS = ROOT / "app" / "static" / "js" / "fx-ui.js"
NODE = shutil.which("node")


@pytest.fixture()
def order_id(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    return buyer.post("/api/v1/checkout", json={"billing_name": "Buyer"}).get_json()["id"]


# ---- markup ---------------------------------------------------------------------------------------------------------------

def steps(html):
    block = re.search(r'<ol class="stp" aria-hidden="true">(.*?)</ol>', html, re.S).group(1)
    return [(re.search(r'class="([^"]*)"', li).group(1), re.sub(r"<[^>]+>", "", li).strip()) for li in re.findall(r"<li .*?</li>", block, re.S)]


def test_the_checkout_stepper_is_decorative_and_marks_the_step_each_page_is_on(buyer, rag, order_id):
    cart = buyer.get("/cart").get_data(as_text=True)
    assert [t for _, t in steps(cart)] == ["Cart", "Details", "Pay", "Done"]
    assert steps(cart)[0][0].startswith("is-current") and not any("is-done" in c for c, _ in steps(cart))
    pay = buyer.get(f"/checkout/pay/{order_id}").get_data(as_text=True)
    classes = [c for c, _ in steps(pay)]
    assert "is-done" in classes[0] and "is-done" in classes[1] and "is-current" in classes[2] and "is-arriving" in classes[1]
    buyer.post(f"/checkout/test-pay/{order_id}", data={"outcome": "pay"})
    done = buyer.get(f"/orders/{order_id}").get_data(as_text=True)
    assert "is-current" in steps(done)[3][0] and "is-done" in steps(done)[2][0]


def test_the_checkout_page_says_details_and_its_heading_and_form_are_unchanged(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    page = buyer.get("/checkout").get_data(as_text=True)
    assert "is-current" in steps(page)[1][0]
    assert '<h1 class="h2">Checkout</h1>' in page and 'name="billing_name"' in page and "Continue to payment" in page


def test_the_stepper_has_no_words_a_screen_reader_would_hear_twice(buyer, rag, order_id):
    html = buyer.get(f"/checkout/pay/{order_id}").get_data(as_text=True)
    assert html.count('<ol class="stp" aria-hidden="true">') == 1


def test_every_field_has_its_underline_and_tick_and_keeps_its_label_input_and_error(client):
    html = client.get("/register").get_data(as_text=True)
    assert html.count('<span class="inp">') == 3 == html.count('<i class="ul" aria-hidden="true">') == html.count('<svg class="ok"')
    assert '<label for="email">Email</label>' in html and 'name="email"' in html and 'placeholder=" "' in html
    resp = client.post("/register", data={"name": "", "email": "nope", "password": "x"})
    page = resp.get_data(as_text=True)
    assert 'class="field has-error"' in page and 'aria-invalid="true"' in page and 'class="msg"' in page


def test_the_error_shake_belongs_to_a_field_that_already_shows_its_message(client):
    assert ".field.has-error .inp { animation: fx-shake" in BARE


def test_login_and_register_get_drifting_art_that_is_decorative(client):
    for page in ("/login", "/register"):
        html = client.get(page).get_data(as_text=True)
        art = html[html.index('<div class="drift"'):html.index('<div class="auth">')]
        assert 'aria-hidden="true"' in art and art.count("<span") == 3 and not re.search(r"<(a|button|input)\b", art)
        assert 'class="wrap page-pad auth-wrap"' in html


def test_the_empty_cart_has_its_line_art_cart_and_the_same_words(buyer):
    html = buyer.get("/cart").get_data(as_text=True)
    assert 'class="empty-cart"' in html and "Nothing in your cart yet." in html and "Browse the catalogue" in html


def test_order_detail_draws_a_three_step_status_line_that_matches_the_status(buyer, rag, order_id):
    pending = buyer.get(f"/orders/{order_id}").get_data(as_text=True)
    items = re.findall(r'<li class="([^"]*)"><i class="otl-line"></i>(.*?)</li>', pending)
    assert [t for _, t in items] == ["Placed", "Paid", "Ready to download"]
    assert "is-done" in items[0][0] and "is-done" not in items[1][0] and "is-done" not in items[2][0]
    buyer.post(f"/checkout/test-pay/{order_id}", data={"outcome": "pay"})
    paid = buyer.get(f"/orders/{order_id}").get_data(as_text=True)
    items = re.findall(r'<li class="([^"]*)"><i class="otl-line"></i>(.*?)</li>', paid)
    assert all("is-done" in c for c, _ in items) and "is-linked" in items[0][0] and "is-linked" in items[1][0]
    assert '<ol class="otl" aria-hidden="true">' in paid and "Your downloads" in paid


def test_the_pay_amount_zooms_in_and_is_plain_text(buyer, rag, order_id):
    html = buyer.get(f"/checkout/pay/{order_id}").get_data(as_text=True)
    assert re.search(r'<div class="amount" data-fx="zoom">₹[\d,]+</div>', html)


def test_the_new_stylesheet_is_linked_for_every_page(client, admin_client):
    for c, path in ((client, "/"), (client, "/login"), (admin_client, "/admin")):
        assert "motion3-ui.css" in c.get(path).get_data(as_text=True)


# ---- stylesheet ------------------------------------------------------------------------------------------------------------

def test_nothing_in_the_interface_layer_hides_a_control_or_depends_on_the_script_to_be_visible():
    for selector, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", re.sub(r"@keyframes [\w-]+ \{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", BARE)):
        assert not re.search(r"opacity:\s*0\b|visibility:\s*hidden|display:\s*none", body) or "drift" in selector or ".stp-line" in selector or ".otl-line" in selector, (selector, body)
    assert "pointer-events: none" in BARE and "!important" not in BARE and "will-change" not in BARE
    # toasts leave the page's flow only when the script that dismisses them is running
    for selector, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", BARE):
        if "position: fixed" in body:
            assert "html.fx-ui" in selector, selector


def test_every_animation_moves_transform_or_opacity_or_is_paint_only():
    for name, body in re.findall(r"@keyframes ([\w-]+) \{((?:[^{}]*\{[^{}]*\})*[^{}]*)\}", BARE):
        props = set(re.findall(r"([\w-]+)\s*:", body)) - {"from", "to"}
        assert props <= {"transform", "opacity", "outline-offset", "outline-color"}, (name, props)
    assert re.search(r"@keyframes fx-ring \{ from \{ outline-offset: 9px; outline-color: transparent; \} \}", BARE)
    assert re.search(r"@keyframes fx-shake .*transform", BARE) and "translate3d" in BARE


def test_hover_rules_exist_only_under_the_fine_pointer_query_and_touch_loses_nothing():
    from tests.test_fx_system import without_hover_media
    assert ":hover" not in without_hover_media(BARE)


def test_the_shake_is_short_and_runs_once_and_reduced_motion_switches_everything_off():
    assert re.search(r"fx-shake 4\d\dms var\(--fx-ease\) 1;", BARE)
    tail = BARE[BARE.rindex("@media (prefers-reduced-motion: reduce)"):]
    for needle in (".btn.is-loading::after", ".empty-cart", ".drift .d1", ".line.is-ghost", ":focus-visible", ".field.has-error .inp", "transition: none"):
        assert needle in tail, needle


def test_the_posting_button_shows_a_spinning_arc_and_the_toast_drains_a_timer_line():
    assert re.search(r"\.btn\.is-loading::after \{[^}]*border-top-color: transparent;[^}]*animation: fx-spin", BARE)
    assert re.search(r"\.flash:not\(\.flash-error\)::after \{[^}]*animation: fx-drain 6s linear", BARE)
    assert "fx-toast-in" in BARE and "fx-toast-out" in BARE


def test_script_budget_and_files_stay_under_the_total():
    assert len(gzip.compress(JS.read_bytes(), 9)) < 3 * 1024


# ---- the script, under node ---------------------------------------------------------------------------------------------------

HARNESS = r"""
const vm = require("vm"), fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
function world(opts = {}) {
  const listeners = {}, observers = [], timers = [];
  const classes = () => ({ s: new Set(), add(c) { this.s.add(c); }, remove(c) { this.s.delete(c); }, contains(c) { return this.s.has(c); } });
  const el = (o = {}) => Object.assign({ classList: classes(), attrs: {}, children: [], nodeType: 1,
    setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; },
    matches(sel) { return sel === ".line:not(.is-ghost)" ? this.classList.contains("line") && !this.classList.contains("is-ghost") : false; },
    querySelector: () => null, querySelectorAll: () => [], closest() { return null; }, addEventListener(t, f) { (this.ls = this.ls || {})[t] = f; },
    remove() { this.removed = true; }, offsetWidth: 1 }, o);
  const html = el();
  const sandbox = {
    window: { matchMedia: () => ({ matches: !!opts.calm }), addEventListener: (t, f) => { (listeners["w:" + t] = listeners["w:" + t] || []).push(f); } },
    document: { documentElement: html,
      querySelector: (s) => (opts.dom || {})[s] || null, querySelectorAll: (s) => (opts.dom || {})[s] || [],
      addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); } },
    setTimeout: (f, ms) => { timers.push({ f, ms, done: false }); return timers.length; }, clearTimeout: () => {},
    MutationObserver: class { constructor(cb) { this.cb = cb; this.disconnected = false; observers.push(this); } observe(t, o) { this.target = t; } disconnect() { this.disconnected = true; } },
    Set, Array, Object,
  };
  return { el, html, listeners, observers, timers, sandbox, run() { vm.runInNewContext(src, sandbox); },
    fire: (t, e) => (listeners[t] || []).forEach((f) => f(e)),
    runTimers(ms) { timers.filter((t) => !t.done && t.ms <= ms).forEach((t) => { t.done = true; t.f(); }); } };
}
"""


def run_node(body):
    if not NODE:
        pytest.skip("node is not installed")
    out = subprocess.run([NODE, "-e", HARNESS + "\n" + body + "\nconsole.log(JSON.stringify(result));", str(JS)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_a_posting_button_spins_and_a_second_submit_of_the_same_form_is_ignored():
    r = run_node("""
      const w = world(); const btn = w.el({ classList: (() => { const c = { s: new Set(["btn"]), add(x) { this.s.add(x); }, remove(x) { this.s.delete(x); }, contains(x) { return this.s.has(x); } }; return c; })() });
      const form = { tagName: "FORM", querySelector: () => btn };
      w.run();
      const first = { prevented: false }; w.fire("submit", { target: form, defaultPrevented: false, preventDefault() { first.prevented = true; } });
      const spinning = btn.classList.s.has("is-loading"), busy = btn.attrs["aria-busy"];
      const second = { prevented: false }; w.fire("submit", { target: form, defaultPrevented: false, preventDefault() { second.prevented = true; } });
      const result = { spinning, busy, firstPrevented: first.prevented, secondPrevented: second.prevented };""")
    assert r == {"spinning": True, "busy": "true", "firstPrevented": False, "secondPrevented": True}


def test_a_submit_that_something_else_already_handled_is_left_alone_so_add_to_cart_keeps_its_own_guard():
    r = run_node("""
      const w = world(); const btn = w.el(); btn.classList.add("btn");
      const form = { tagName: "FORM", querySelector: () => btn };
      w.run();
      w.fire("submit", { target: form, defaultPrevented: true, preventDefault() {} });
      const result = { spinning: btn.classList.s.has("is-loading") };""")
    assert r == {"spinning": False}


def test_a_form_never_stays_locked_when_the_request_never_answers_or_the_page_comes_back_from_the_cache():
    r = run_node("""
      const w = world(); const btn = w.el(); btn.classList.add("btn");
      const form = { tagName: "FORM", querySelector: () => btn };
      w.run(); w.fire("submit", { target: form, defaultPrevented: false, preventDefault() {} });
      w.runTimers(15000);
      const released = !btn.classList.s.has("is-loading");
      const again = { p: false }; w.fire("submit", { target: form, defaultPrevented: false, preventDefault() { again.p = true; } });
      const result = { released, secondAllowed: !again.p };""")
    assert r == {"released": True, "secondAllowed": True}


def test_success_toasts_leave_after_six_seconds_and_errors_stay():
    r = run_node("""
      const ok = (() => { const e = { classList: { s: new Set(["flash", "flash-success"]), add(x) { this.s.add(x); }, contains(x) { return this.s.has(x); } }, hidden: false }; return e; })();
      const bad = { classList: { s: new Set(["flash", "flash-error"]), add(x) { this.s.add(x); }, contains(x) { return this.s.has(x); } }, hidden: false };
      const w = world({ dom: { ".flashes .flash": [ok, bad] } }); w.run();
      const before = [ok.classList.s.has("is-leaving"), w.html.classList.s.has("fx-ui")];
      w.runTimers(5999); const early = ok.classList.s.has("is-leaving");
      w.runTimers(6000); const leaving = ok.classList.s.has("is-leaving");
      w.runTimers(6400);
      const result = { before, early, leaving, okHidden: ok.hidden, errorLeaves: bad.classList.s.has("is-leaving"), errorHidden: bad.hidden };""")
    assert r == {"before": [False, True], "early": False, "leaving": True, "okHidden": True, "errorLeaves": False, "errorHidden": False}


def test_under_reduced_motion_only_the_form_guard_runs():
    r = run_node("""
      const w = world({ calm: true, dom: { ".flashes .flash": [{ classList: { contains: () => false, add() { throw new Error("toast moved"); } } }] } });
      w.run();
      const result = { ui: w.html.classList.s.has("fx-ui"), submit: !!w.listeners.submit, click: !!w.listeners.click, observers: w.observers.length };""")
    assert r == {"ui": False, "submit": True, "click": False, "observers": 0}


def test_a_removed_cart_row_comes_back_as_a_harmless_ghost_that_slides_out_and_is_then_removed():
    r = run_node("""
      const inserted = [];
      const row = (() => { const r = { classList: { s: new Set(["line"]), add(x) { this.s.add(x); }, contains(x) { return this.s.has(x); }, remove(x) { this.s.delete(x); } }, attrs: {}, nodeType: 1,
        matches(sel) { return sel === ".line:not(.is-ghost)" && this.classList.s.has("line") && !this.classList.s.has("is-ghost"); },
        removeAttribute(k) { delete this.attrs[k]; }, setAttribute(k, v) { this.attrs[k] = v; },
        querySelectorAll: () => [{ setAttribute(k, v) { (row.kids = row.kids || []).push(k + v); } }], addEventListener(t, f) { this.end = f; }, remove() { this.removed = true; } }; return r; })();
      row.attrs["data-line"] = "7";
      const lines = { insertBefore(n, ref) { inserted.push(n === row); }, querySelector: () => null };
      const cart = { querySelector: (s) => (s === ".lines" ? lines : null) };
      const w = world({ dom: { "[data-cart]": cart } }); w.run();
      w.observers[0].cb([{ removedNodes: [row], nextSibling: null }]);
      const slid = row.classList.s.has("is-ghost"), stripped = !("data-line" in row.attrs), hidden = row.attrs["aria-hidden"];
      row.end();
      const result = { slid, stripped, hidden, inserted, removed: row.removed === true, kids: row.kids };""")
    assert r == {"slid": True, "stripped": True, "hidden": "true", "inserted": [True], "removed": True, "kids": ["tabindex-1"]}


def test_a_changed_cart_figure_and_its_quantity_box_tick():
    r = run_node("""
      const input = { classList: { s: new Set(), add(x) { this.s.add(x); }, remove(x) { this.s.delete(x); } }, offsetWidth: 1 };
      const row = { querySelector: (s) => (s === "input" ? input : null) };
      const fig = { classList: { s: new Set(), add(x) { this.s.add(x); }, remove(x) { this.s.delete(x); } }, offsetWidth: 1, nodeType: 1,
        closest: (s) => (s.indexOf("data-line-total") >= 0 ? fig : s === "[data-line]" ? row : null) };
      const lines = { insertBefore() {}, querySelector: () => null };
      const cart = { querySelector: (s) => (s === ".lines" ? lines : null) };
      const w = world({ dom: { "[data-cart]": cart } }); w.run();
      w.observers[1].cb([{ target: fig }]);
      const result = { fig: fig.classList.s.has("is-tick"), input: input.classList.s.has("is-tick") };""")
    assert r == {"fig": True, "input": True}


def test_a_download_press_says_preparing_for_a_moment():
    r = run_node("""
      const a = { classList: { s: new Set(), add(x) { this.s.add(x); }, remove(x) { this.s.delete(x); } }, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; } };
      const target = { closest: (s) => (s === ".delivery a" ? a : null) };
      const w = world(); w.run(); w.fire("click", { target });
      const during = [a.classList.s.has("is-preparing"), a.attrs["aria-busy"]];
      w.runTimers(1400);
      const result = { during, after: [a.classList.s.has("is-preparing"), "aria-busy" in a.attrs] };""")
    assert r == {"during": [True, "true"], "after": [False, False]}


def test_everything_is_disconnected_on_pagehide():
    r = run_node("""
      const lines = { insertBefore() {}, querySelector: () => null };
      const w = world({ dom: { "[data-cart]": { querySelector: (s) => (s === ".lines" ? lines : null) } } }); w.run();
      w.fire("w:pagehide", {});
      const result = { all: w.observers.every((o) => o.disconnected), n: w.observers.length };""")
    assert r == {"all": True, "n": 2}
