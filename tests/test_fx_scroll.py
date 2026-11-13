"""The scroll system's script, fx-scroll.js, run under node against a small fake DOM, a fake requestAnimationFrame and a
fake IntersectionObserver. The pages and stylesheet that go with it are tested in test_fx_system.py."""
import gzip
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "app" / "static" / "js" / "fx-scroll.js"
NODE = shutil.which("node")

HARNESS = r"""
const vm = require("vm"), fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
function world(opts = {}) {
  let now = 0, rafId = 0, queue = [], maxQueued = 0;
  const listeners = {}, removed = [], observers = [], writes = [];
  const rootClasses = new Set();
  const make = (name, o = {}) => {
    const e = Object.assign({
      name, dataset: {}, children: [], parentElement: null, textContent: "", top: 2000, height: 100,
      style: { props: {}, setProperty(k, v) { this.props[k] = v; writes.push([name, k, v]); } },
      classList: { s: new Set(), add(...c) { c.forEach((x) => this.s.add(x)); }, remove(...c) { c.forEach((x) => this.s.delete(x)); },
        toggle(c, on) { if (on) this.s.add(c); else this.s.delete(c); }, contains(c) { return this.s.has(c); } },
      getBoundingClientRect() { return { top: this.top, bottom: this.top + this.height, height: this.height }; },
      querySelector() { return null; }, querySelectorAll() { return []; },
      closest(sel) { for (let n = this; n; n = n.parentElement) if (n.dataset.fx !== undefined) return n; return null; },
      offsetHeight: 100, offsetWidth: 100,
    }, o);
    return e;
  };
  const adopt = (parent, kids) => { parent.children = kids; kids.forEach((k) => { k.parentElement = parent; }); };
  const w = { make, adopt, listeners, removed, observers, writes, rootClasses };
  w.run = (dom = {}) => {
    const IO = opts.noIO ? undefined : class {
      constructor(cb, o) { this.cb = cb; this.opts = o; this.targets = new Set(); this.disconnected = false; observers.push(this); }
      observe(e) { this.targets.add(e); } unobserve(e) { this.targets.delete(e); } disconnect() { this.disconnected = true; this.targets.clear(); }
    };
    const body = make("body", { dataset: { page: opts.page === undefined ? "browse" : opts.page } });
    const html = make("html", { scrollHeight: 4000 });
    html.classList = { s: rootClasses, add(c) { rootClasses.add(c); }, remove(c) { rootClasses.delete(c); } };
    const win = {
      matchMedia: () => ({ matches: !!opts.calm }), innerHeight: 800, pageYOffset: 0, location: { search: opts.search || "" },
      addEventListener: (t, f, o) => { (listeners[t] = listeners[t] || []).push({ f, o }); },
      removeEventListener: (t, f) => { removed.push(t); const l = listeners[t] || []; const i = l.findIndex((x) => x.f === f); if (i >= 0) l.splice(i, 1); },
    };
    if (IO) win.IntersectionObserver = IO;
    const doc = {
      hidden: false, body, documentElement: html,
      querySelector: (s) => (dom[s] || [])[0] || null,
      querySelectorAll: (s) => dom[s] || [],
      addEventListener: (t, f) => { (listeners["doc:" + t] = listeners["doc:" + t] || []).push({ f }); },
      removeEventListener: (t, f) => { removed.push("doc:" + t); const l = listeners["doc:" + t] || []; const i = l.findIndex((x) => x.f === f); if (i >= 0) l.splice(i, 1); },
    };
    const sandbox = {
      window: win, document: doc, IntersectionObserver: IO, navigator: opts.nav || { hardwareConcurrency: 8, deviceMemory: 8 },
      requestAnimationFrame: (f) => { queue.push(f); maxQueued = Math.max(maxQueued, queue.length); return ++rafId; },
      cancelAnimationFrame: () => { queue = []; },
      performance: { now: () => now },
      getComputedStyle: (e) => ({ position: e.__position || "static" }),
      parseFloat, Math, Number, String, Set, Map, Array, Object,
    };
    w.win = win; w.doc = doc; w.html = html;
    vm.runInNewContext(src, sandbox);
  };
  w.advance = (ms) => { const end = now + ms; for (let g = 0; g < 4000; g++) { now = Math.min(end, now + (opts.frameMs || 16)); const q = queue; queue = []; q.forEach((f) => f(now)); if (now >= end) break; } };
  w.pending = () => queue.length;
  w.maxQueued = () => maxQueued;
  w.io = () => observers[0];
  w.fire = (entries) => { observers[0].cb(entries); };
  w.dispatch = (type, ev) => (listeners[type] || []).forEach((l) => l.f(ev));
  return w;
}
"""


def run_node(body):
    if not NODE:
        pytest.skip("node is not installed")
    out = subprocess.run([NODE, "-e", HARNESS + "\n" + body + "\nconsole.log(JSON.stringify(result));", str(JS)],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


PAGE = """
  const w = world(OPTS);
  const rise_in = w.make("rise_in", { dataset: { fx: "rise" }, top: 100 });
  const rise_below = w.make("rise_below", { dataset: { fx: "rise" }, top: 1500 });
  const kids = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => w.make("kid" + i, { top: i < 2 ? 300 : 1200 + i * 50 }));
  const grid = w.make("grid", { dataset: { fx: "cascade" } }); w.adopt(grid, kids);
  const live = w.make("live", {});
  const count = w.make("count", { dataset: { fx: "count", to: "641" }, top: 1800, querySelector: (s) => (s === ".cnt-live" ? live : null) });
  const live2 = w.make("live2", {});
  const count_in = w.make("count_in", { dataset: { fx: "count", to: "15" }, top: 200, querySelector: (s) => (s === ".cnt-live" ? live2 : null) });
  const header = w.make("header", {}); const bar = w.make("bar", {});
  const dom = { '[data-fx="rise"], [data-fx="count"]': [rise_in, rise_below, count, count_in], '[data-fx="cascade"]': [grid], '[data-fx="pin"]': [], '[data-fx="parallax"]': [], ".site-header": [header], ".fx-progress": [bar] };
  w.run(dom);
"""


def page(extra, opts="{}"):
    return PAGE.replace("OPTS", opts) + extra


# ---- when it does not run ----------------------------------------------------------------------------------------------

def test_it_does_nothing_for_admin_and_error_pages_for_reduced_motion_and_without_an_observer():
    for opts in ('{ page: "none" }', '{ calm: true }', '{ noIO: true }', '{ page: "none", calm: true, noIO: true }'):
        r = run_node(page("const result = { on: [...w.rootClasses], observers: w.observers.length, listeners: Object.keys(w.listeners), writes: w.writes.length, queued: w.pending(), below: rise_below.classList.s.size };", opts))
        assert r == {"on": [], "observers": 0, "listeners": [], "writes": 0, "queued": 0, "below": 0}, (opts, r)


def test_a_page_with_no_data_page_at_all_does_nothing():
    r = run_node("""
      const w = world({ page: "" }); w.run({});
      const result = { on: [...w.rootClasses], observers: w.observers.length };""")
    assert r == {"on": [], "observers": 0}


# ---- start up ------------------------------------------------------------------------------------------------------------

def test_what_is_already_on_screen_is_shown_before_fx_on_is_set_and_the_rest_waits_for_the_one_observer():
    r = run_node(page("""
      const result = { on: [...w.rootClasses], observers: w.observers.length,
        inView: [rise_in, kids[0], kids[1]].map((e) => e.classList.s.has("is-in")),
        below: [rise_below, kids[2], kids[9]].map((e) => e.classList.s.has("is-in")),
        watched: [...w.io().targets].map((e) => e.name).sort() };"""))
    assert r["on"] == ["fx-on"] and r["observers"] == 1
    assert r["inView"] == [True, True, True] and r["below"] == [False, False, False]
    assert "rise_below" in r["watched"] and "kid2" in r["watched"] and "rise_in" not in r["watched"] and "grid" not in r["watched"]


def test_exactly_one_observer_and_never_more_than_one_frame_queued():
    r = run_node(page("""
      w.fire([{ target: rise_below, isIntersecting: true }]); w.fire([{ target: kids[3], isIntersecting: true }]);
      w.dispatch("scroll"); w.dispatch("scroll"); w.dispatch("resize"); w.advance(200);
      const result = { observers: w.observers.length, maxQueued: w.maxQueued() };"""))
    assert r == {"observers": 1, "maxQueued": 1}


# ---- rise and cascade ----------------------------------------------------------------------------------------------------

def test_rise_comes_in_once_and_stops_being_watched():
    r = run_node(page("""
      w.fire([{ target: rise_below, isIntersecting: false }]); const before = rise_below.classList.s.has("is-in");
      w.fire([{ target: rise_below, isIntersecting: true }]);
      const result = { before, after: rise_below.classList.s.has("is-in"), watched: w.io().targets.has(rise_below) };"""))
    assert r == {"before": False, "after": True, "watched": False}


def test_children_that_arrive_together_are_staggered_in_order_and_capped_at_eight_steps():
    r = run_node(page("""
      w.fire(kids.slice(2).map((k) => ({ target: k, isIntersecting: true })));
      const first = kids.slice(2).map((k) => k.style.props["--i"]);
      const result = { first, initial: [kids[0].style.props["--i"], kids[1].style.props["--i"]] };"""))
    assert r["initial"] == ["0", "1"]
    assert r["first"] == ["0", "1", "2", "3", "4", "5", "6", "7"], r


def test_more_than_eight_children_in_one_batch_share_the_last_step():
    r = run_node("""
      const w = world({});
      const kids = Array.from({ length: 12 }, (_, i) => w.make("k" + i, { top: 1500 + i * 10 }));
      const grid = w.make("grid", { dataset: { fx: "cascade" } }); w.adopt(grid, kids);
      w.run({ '[data-fx="cascade"]': [grid], '[data-fx="rise"], [data-fx="count"]': [] });
      w.fire(kids.map((k) => ({ target: k, isIntersecting: true })));
      const result = { i: kids.map((k) => k.style.props["--i"]) };""")
    assert r["i"] == ["0", "1", "2", "3", "4", "5", "6", "7", "7", "7", "7", "7"]


def test_a_later_batch_starts_again_from_zero_and_other_children_are_not_touched():
    r = run_node(page("""
      w.fire([{ target: kids[2], isIntersecting: true }, { target: kids[3], isIntersecting: true }]);
      w.fire([{ target: kids[4], isIntersecting: true }]);
      const result = { a: kids[2].style.props["--i"], b: kids[3].style.props["--i"], c: kids[4].style.props["--i"], untouched: kids[5].classList.s.has("is-in") };"""))
    assert r == {"a": "0", "b": "1", "c": "0", "untouched": False}


# ---- count --------------------------------------------------------------------------------------------------------------

def test_a_counter_waits_at_zero_then_counts_up_once_to_the_real_number_and_the_loop_stops():
    r = run_node(page("""
      const waiting = live.textContent;
      w.fire([{ target: count, isIntersecting: true }]); w.advance(32); const early = live.textContent;
      w.advance(300); const mid = live.textContent; w.advance(700); const end = live.textContent;
      w.fire([{ target: count, isIntersecting: true }]); w.advance(500);
      const result = { waiting, early, mid, end, again: live.textContent, queued: w.pending() };"""))
    assert r["waiting"] == "0" and int(r["early"]) < 100 and 0 < int(r["mid"]) < 641 and r["end"] == "641" and r["again"] == "641"
    assert r["queued"] == 0


def test_a_counter_already_on_screen_counts_straight_away():
    r = run_node(page("""
      w.advance(1000);
      const result = { text: live2.textContent };"""))
    assert r == {"text": "15"}


# ---- pin and parallax --------------------------------------------------------------------------------------------------

PIN = """
  const w = world(OPTS);
  const stage = w.make("stage", { offsetHeight: 725 }); stage.__position = STAGEPOS;
  const mover = w.make("mover", {}); const mover2 = w.make("mover2", {});
  const header = w.make("header", {}); header.__position = "sticky"; header.offsetHeight = 75;
  const sec = w.make("sec", { dataset: { fx: "pin" }, top: 75, offsetHeight: 1920, querySelector: (s) => (s === ".fx-stage" ? stage : null), querySelectorAll: (s) => (s === ".fx-move" ? [mover, mover2] : []) });
  const art = w.make("art", { dataset: { fx: "parallax" }, top: 400, height: 200 });
  w.run({ '[data-fx="pin"]': [sec], '[data-fx="parallax"]': [art], ".site-header": [header] });
  const at = (top) => { sec.top = top; w.fire([{ target: sec, isIntersecting: true }]); w.advance(32); return parseFloat(sec.style.props["--p"]); };
"""


def pin(extra, pos="sticky", opts="{}"):
    return PIN.replace("OPTS", opts).replace("STAGEPOS", '"%s"' % pos) + extra


def test_a_pinned_scene_reports_how_far_through_it_the_reader_is_and_sets_its_top_under_the_sticky_header():
    r = run_node(pin("""
      const ps = [75, 75 - 1195 * .5, 75 - 1195, -3000, 900].map(at);
      const result = { ps, top: sec.style.props["--fx-top"], animating: mover.classList.s.has("is-animating") };"""))
    assert r["ps"][0] == 0 and abs(r["ps"][1] - 0.5) < 0.01 and r["ps"][2] == 1 and r["ps"][3] == 1 and r["ps"][4] == 0, r
    assert r["top"] == "75px" and r["animating"] is True


def test_a_scene_that_is_not_pinned_stays_finished_and_will_change_comes_off_when_it_leaves():
    r = run_node(pin("""
      const p = at(-200);
      w.fire([{ target: sec, isIntersecting: false }]); w.advance(32);
      const result = { p, animating: mover.classList.s.has("is-animating") };""", "static"))
    assert r == {"p": 1, "animating": False}


def test_a_scene_that_is_not_pinned_follows_its_position_on_the_screen_instead():
    r = run_node(pin("""
      const ps = [900, 600, 400, 100, -300].map(at);
      const result = { ps };""", "static"))
    assert r["ps"][0] == 0 and 0 < r["ps"][1] < r["ps"][2] < 1 and r["ps"][3] == 1 and r["ps"][4] == 1, r


def test_a_scene_that_scrolled_out_fast_gets_one_last_measurement_so_it_ends_at_zero_or_one():
    r = run_node(pin("""
      at(75 - 600);                               // half way through
      sec.top = -5000; w.fire([{ target: sec, isIntersecting: false }]); w.advance(32);
      const result = { p: parseFloat(sec.style.props["--p"]) };"""))
    assert r == {"p": 1}


def test_parallax_drifts_with_position_and_is_clamped():
    r = run_node(pin("""
      const py = [];
      for (const top of [-5000, 300, 700, 9000]) { art.top = top; w.fire([{ target: art, isIntersecting: true }]); w.advance(32); py.push(parseFloat(art.style.props["--py"])); }
      const result = { py };"""))
    assert r["py"][0] == -1 and r["py"][3] == 1 and r["py"][1] < r["py"][2]


# ---- page furniture ------------------------------------------------------------------------------------------------------

def test_the_header_condenses_past_40px_and_the_progress_line_follows_the_scroll_on_browse_pages():
    r = run_node(page("""
      w.win.pageYOffset = 0; w.dispatch("scroll"); w.advance(32);
      const top = [header.classList.s.has("is-condensed"), bar.style.props["--sp"]];
      w.win.pageYOffset = 41; w.dispatch("scroll"); w.advance(32);
      const below = header.classList.s.has("is-condensed");
      w.win.pageYOffset = 0; w.dispatch("scroll"); w.advance(32);
      const back = header.classList.s.has("is-condensed");
      const result = { top, below, back };"""))
    assert r["top"][0] is False and r["top"][1] == "0.000" and r["below"] is True and r["back"] is False


def test_the_progress_number_is_written_on_its_own_node_and_never_on_the_root_element():
    r = run_node(page("""
      w.win.pageYOffset = 1000; w.dispatch("scroll"); w.advance(32);
      const rootWrites = w.writes.filter((x) => x[0] === "html").length;
      const result = { bar: parseFloat(bar.style.props["--sp"]) > 0, rootWrites };"""))
    assert r == {"bar": True, "rootWrites": 0}


def test_other_page_classes_condense_the_header_but_draw_no_progress_line():
    r = run_node(page("""
      w.win.pageYOffset = 100; w.dispatch("scroll"); w.advance(32);
      const result = { condensed: header.classList.s.has("is-condensed"), sp: bar.style.props["--sp"] === undefined, root: w.html.style.props["--sp"] === undefined };""", '{ page: "transactional" }'))
    assert r == {"condensed": True, "sp": True, "root": True}


# ---- focus, visibility, clean up -------------------------------------------------------------------------------------------

def test_a_focused_element_is_never_left_hidden():
    r = run_node(page("""
      const inner = w.make("inner", {}); w.adopt(kids[5], [inner]);
      w.dispatch("doc:focusin", { target: inner });
      const deep = w.make("deep", {}); deep.parentElement = rise_below;
      w.dispatch("doc:focusin", { target: deep });
      const result = { kid: kids[5].classList.s.has("is-in"), rise: rise_below.classList.s.has("is-in"), other: kids[6].classList.s.has("is-in"),
        instant: [kids[5].classList.s.has("is-instant"), rise_below.classList.s.has("is-instant")] };"""))
    assert r == {"kid": True, "rise": True, "other": False, "instant": [True, True]}      # no fade: it must be visible when focus lands


def test_focusing_into_a_pinned_scene_shows_it_whole():
    r = run_node(pin("""
      const inner = w.make("inner", {}); inner.parentElement = sec;
      w.dispatch("doc:focusin", { target: inner });
      const result = { focus: sec.classList.s.has("is-focus") };"""))
    assert r == {"focus": True}


def test_the_loop_stops_in_a_hidden_tab_and_starts_again_when_it_is_shown():
    r = run_node(page("""
      w.dispatch("scroll"); const running = w.pending();
      w.doc.hidden = true; w.dispatch("doc:visibilitychange"); const hidden = w.pending();
      w.dispatch("scroll"); const still = w.pending();
      w.doc.hidden = false; w.dispatch("doc:visibilitychange");
      const result = { running, hidden, still, shown: w.pending() };"""))
    assert r == {"running": 1, "hidden": 0, "still": 0, "shown": 1}


def test_scroll_and_resize_listeners_are_passive():
    r = run_node(page("""
      const result = { scroll: w.listeners.scroll.every((l) => l.o && l.o.passive === true), resize: w.listeners.resize.every((l) => l.o && l.o.passive === true) };"""))
    assert r == {"scroll": True, "resize": True}


def test_everything_is_undone_on_pagehide():
    r = run_node(page("""
      w.dispatch("scroll");
      const tally = () => ({ scroll: w.listeners.scroll.length, resize: w.listeners.resize.length, vis: w.listeners["doc:visibilitychange"].length, focus: w.listeners["doc:focusin"].length });
      const before = tally();
      w.dispatch("pagehide");
      const result = { before, after: tally(), disconnected: w.io().disconnected, queued: w.pending() };"""))
    assert r["before"] == {"scroll": 1, "resize": 1, "vis": 1, "focus": 1}
    assert r["after"] == {"scroll": 0, "resize": 0, "vis": 0, "focus": 0} and r["disconnected"] is True and r["queued"] == 0


def test_script_budget():
    assert len(gzip.compress(JS.read_bytes(), 9)) < 6 * 1024


# ---- adaptive quality: fx-lite ---------------------------------------------------------------------------------------------

def test_a_capable_device_gets_the_full_system_and_no_lite_class():
    r = run_node(page("""
      w.advance(700);
      const result = { classes: [...w.rootClasses].sort() };"""))
    assert r == {"classes": ["fx-on"]}


def test_few_cores_or_little_memory_switch_on_fx_lite_straight_away():
    for nav in ("{ hardwareConcurrency: 4, deviceMemory: 8 }", "{ hardwareConcurrency: 8, deviceMemory: 4 }", "{ hardwareConcurrency: 2 }"):
        r = run_node(page("const result = { classes: [...w.rootClasses].sort() };", "{ nav: %s }" % nav))
        assert r == {"classes": ["fx-lite", "fx-on"]}, nav


def test_the_address_can_force_lite_or_full_either_way():
    assert run_node(page("const result = { c: [...w.rootClasses].sort() };", '{ search: "?fx=lite" }')) == {"c": ["fx-lite", "fx-on"]}
    assert run_node(page("const result = { c: [...w.rootClasses].sort() };", '{ search: "?a=1&fx=full", nav: { hardwareConcurrency: 2 } }')) == {"c": ["fx-on"]}


def test_a_slow_first_half_second_switches_lite_on_and_a_fast_one_does_not():
    slow = run_node(page("""
      w.advance(1200);                     // frames arrive every 40 ms: 25 fps
      const result = { c: [...w.rootClasses].sort() };""", "{ frameMs: 40 }"))
    assert slow == {"c": ["fx-lite", "fx-on"]}
    fast = run_node(page("""
      w.advance(1200);
      const result = { c: [...w.rootClasses].sort() };"""))
    assert fast == {"c": ["fx-on"]}
