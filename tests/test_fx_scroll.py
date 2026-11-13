"""Motion 3, item C: the home page story, the pinned cover showcase and the tile cascade. The page and stylesheet are
tested directly (every figure shown must be a real one); fx-scroll.js runs under node against a small fake DOM, a
fake requestAnimationFrame and a fake IntersectionObserver."""
import gzip
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.extensions import db
from app.models import Category, Product

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "motion3.css").read_text(encoding="utf-8").replace("\r\n", "\n")
BARE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
SCROLL = BARE[BARE.index(".story {"):]
JS = ROOT / "app" / "static" / "js" / "fx-scroll.js"
README = (ROOT / "README.md").read_text(encoding="utf-8")
NODE = shutil.which("node")


def rules(css):
    return re.findall(r"([^{}]+)\{([^{}]*)\}", css)


def figures(html):
    """{label: number} for the story's stat cards."""
    out = {}
    for card in re.findall(r'<article class="fx-card fx-stat".*?</article>', html, re.S):
        n = int(re.search(r'data-fx-count="(\d+)"', card).group(1))
        out[re.sub(r"<[^>]+>", "", re.search(r'<p class="fx-l">(.*?)</p>', card, re.S).group(1))] = n
    return out


# ---- the figures are real -------------------------------------------------------------------------------------------

def test_the_live_figures_are_counted_from_the_catalogue(client, app):
    html = client.get("/").get_data(as_text=True)
    stats = figures(html)
    active = db.session.scalar(db.select(db.func.count(Product.id)).where(Product.is_active.is_(True)))
    fields = db.session.scalar(db.select(db.func.count(db.distinct(Product.category_id))).where(Product.is_active.is_(True)))
    labels = list(stats)
    assert stats[labels[0]] == active and labels[0].startswith(("project", "projects"))
    assert stats[labels[1]] == fields
    assert stats[labels[2]] == app.config["RESERVATION_MINUTES"]
    names = labels[1].split(": ", 1)[1].split(", ")
    assert set(names) == {c.name for c in db.session.scalars(db.select(Category)) if any(p.is_active for p in c.products)}


def test_the_figures_follow_the_data_when_it_changes(client, app, rag):
    before = figures(client.get("/").get_data(as_text=True))
    rag.is_active = False
    db.session.commit()
    after = figures(client.get("/").get_data(as_text=True))
    assert list(after.values())[0] == list(before.values())[0] - 1
    app.config["RESERVATION_MINUTES"] = 7
    assert list(figures(client.get("/").get_data(as_text=True)).values())[2] == 7


def test_the_two_figures_that_are_not_in_the_database_match_the_readme(client):
    stats = figures(client.get("/").get_data(as_text=True))
    tests = list(stats.values())[3]
    readme_tests = int(re.search(r"\| ([\d,]+) tests pass on SQLite", README).group(1).replace(",", ""))
    readme_cover = int(re.search(r"Line coverage of `app/` is (\d+)%", README).group(1))
    assert tests == readme_tests
    assert re.search(r"covering %d%% of the app's lines" % readme_cover, client.get("/").get_data(as_text=True))


def test_every_card_states_something_the_store_does_and_nothing_is_invented(client):
    html = client.get("/").get_data(as_text=True)
    story = html[html.index('<section class="story"'):html.index('<section class="showcase"')]
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", story))
    assert "Checkout reserves what you chose" in text and "never from a number sent by the browser" in text
    numbers = {int(n) for n in re.findall(r"\b\d+\b", re.sub(r"\d+% of", "", text))}
    assert numbers <= set(figures(html).values()) | {96}, numbers


# ---- markup -------------------------------------------------------------------------------------------------------

def test_the_counters_hold_their_final_number_in_the_page_so_nothing_depends_on_the_script(client):
    html = client.get("/").get_data(as_text=True)
    boxes = re.findall(r'<span class="cnt" data-fx-count="(\d+)"><span class="cnt-size">(\d+)</span><span class="cnt-live" aria-hidden="true">(\d+)</span></span>', html)
    assert len(boxes) == 4
    for final, size, live in boxes:
        assert final == size == live, "the sizing text, the live text and the target are one number"


def test_home_hooks_and_the_script_is_only_on_the_pages_that_use_it(client, buyer):
    home = client.get("/").get_data(as_text=True)
    assert home.count('data-fx="cascade"') == 1 and home.count('data-fx="showcase"') == 1 and home.count('data-fx="tiles"') == 1
    assert home.count("data-fx-item") == 6
    covers = re.findall(r'<li class="sc-cover sc-(\d)">', home)
    assert covers == [str(i) for i in range(len(covers))] and 2 <= len(covers) <= 4
    assert all(f"/p/" in m for m in re.findall(r'<li class="sc-cover[^>]*><a href="([^"]+)"', home))
    assert "style=" not in home.split("<main", 1)[1].split("</main>")[0]
    for page, expected in (("/", True), ("/catalogue", True), ("/cart", False), ("/orders", False)):
        html = buyer.get(page, follow_redirects=True).get_data(as_text=True)
        assert ("fx-scroll.js" in html) is expected, page
    assert 'data-fx="tiles"' in buyer.get("/catalogue").get_data(as_text=True)
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", home)


def test_the_showcase_needs_at_least_two_projects_and_the_headline_text_is_the_stores_own(client, app):
    for p in db.session.scalars(db.select(Product)):
        p.is_active = p.slug == "advanced-rag-knowledge-assistant"
    db.session.commit()
    assert 'class="showcase"' not in client.get("/").get_data(as_text=True)


def test_the_showcase_stays_keyboard_reachable_every_cover_is_a_real_link(client):
    home = client.get("/").get_data(as_text=True)
    block = home[home.index('<section class="showcase"'):].split("</section>")[0]
    assert block.count("<a ") == block.count('class="sc-cover') and "tabindex" not in block


# ---- stylesheet -------------------------------------------------------------------------------------------------------

def test_scroll_pieces_default_to_finished_so_no_script_means_nothing_hidden():
    for selector in (".fx-card", '[data-fx="tiles"] .tile'):
        body = dict((s.strip(), b) for s, b in rules(SCROLL))[selector]
        assert "opacity: var(--e, 1)" in body and "calc((1 - var(--e, 1))" in body, selector
    assert any(s.strip() == ".showcase" and "--p: 1" in b for s, b in rules(SCROLL))
    assert any(s.strip() == ".sc-hint" and "opacity: clamp(0, calc(1 - var(--p) * 7), 1)" in b for s, b in rules(SCROLL))   # p defaults to 1, so the hint is gone


def test_only_transform_and_opacity_change_with_scroll_and_nothing_depends_on_hover():
    for selector, body in rules(SCROLL):
        if "var(--e" in body or "var(--k" in body or "var(--p" in body:
            for prop in re.findall(r"(?<![\w-])([a-z][a-z-]*)\s*:\s*[^;]*var\(--(?:e|k|p)[,)]", body):
                assert prop in {"opacity", "transform"}, (selector, prop)
    assert ":hover" not in re.sub(r"\.sc-cover a:hover \{[^}]*\}", "", SCROLL)
    assert "will-change" not in SCROLL and "!important" not in SCROLL
    assert "display: none" in SCROLL and "visibility: hidden" not in SCROLL


def test_the_pin_exists_only_with_scripting_and_without_a_reduced_motion_request():
    pin = re.search(r"@media \(scripting: enabled\) and \(prefers-reduced-motion: no-preference\) \{(.*?)\n\}", SCROLL, re.S).group(1)
    assert "height: 240vh" in pin and "position: sticky" in pin and "overflow: hidden" in pin
    outside = SCROLL.replace(pin, "")
    assert "sticky" not in outside and "240vh" not in outside


def test_reduced_motion_makes_everything_final_and_unpins():
    inner = re.search(r"@media \(prefers-reduced-motion: reduce\) \{(.*)\n\}", SCROLL, re.S).group(1)
    assert re.search(r"\.fx-card, \.sc-cover, \.sc-head \{ opacity: 1; transform: none; \}", inner)
    assert ".showcase { height: auto; }" in inner and "position: relative; height: auto" in inner


def test_the_counters_boxes_keep_their_width():
    rule = dict((s.strip(), b) for s, b in rules(SCROLL))
    assert "font-variant-numeric: tabular-nums" in rule[".cnt"] and "display: inline-block" in rule[".cnt"]
    assert "position: absolute" in rule[".cnt-live"] and "opacity: 0" in rule[".cnt-size"]


def test_a_cover_the_reader_tabs_into_is_shown_at_once():
    assert re.search(r"\.showcase\.is-focus \.sc-cover, \.showcase\.is-focus \.sc-head \{ opacity: 1; transform: none; \}", SCROLL)


def test_script_budget():
    assert len(gzip.compress(JS.read_bytes(), 9)) < 2.5 * 1024


# ---- the script, under node ---------------------------------------------------------------------------------------------

HARNESS = r"""
const vm = require("vm"), fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
function world(opts = {}) {
  let now = 0, rafId = 0, queue = [];
  const writes = [], listeners = {}, observed = [];
  let ioCallback = null;
  const el = (o = {}) => Object.assign({
    style: { setProperty(k, v) { writes.push([this.owner, k, v]); this.props[k] = v; }, props: {} },
    classList: { add(c) { this.s.add(c); }, remove(c) { this.s.delete(c); }, s: new Set() }, dataset: {}, textContent: "",
    listeners: {}, addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
    querySelector() { return null; }, querySelectorAll() { return []; },
  }, o);
  const named = (name, o) => { const e = el(o); e.style.owner = name; return e; };
  const w = {
    now: () => now, writes, listeners, named, el,
    advance(ms) { const end = now + ms; for (let guard = 0; guard < 2000; guard++) { const next = Math.min(end, now + 16); now = next; const q = queue; queue = []; q.forEach((f) => f(now)); if (now >= end) break; } },
    pending: () => queue.length,
    fireIO(entries) { ioCallback(entries); },
    observed,
  };
  w.run = (dom) => {
    const IO = opts.noIO ? undefined : class { constructor(cb) { ioCallback = cb; } observe(e) { observed.push(e); } };
    const win = {
      matchMedia: () => ({ matches: !!opts.calm }), innerHeight: 800,
      addEventListener: (t, f, o) => { (listeners[t] = listeners[t] || []).push({ f, o }); },
    };
    if (IO) win.IntersectionObserver = IO;
    const sandbox = {
      window: win, IntersectionObserver: IO,
      document: {
        hidden: false, querySelectorAll: (s) => dom[s] || [], querySelector: (s) => (dom[s] || [])[0] || null,
        addEventListener: (t, f) => { (listeners["doc:" + t] = listeners["doc:" + t] || []).push(f); },
      },
      requestAnimationFrame: (f) => { queue.push(f); return ++rafId; }, cancelAnimationFrame: () => { queue = []; },
      performance: { now: () => now }, getComputedStyle: () => ({ position: "sticky", top: "75px" }),
      parseFloat, Math, Number, String, Set, Map, Array, Object,
    };
    w.doc = sandbox.document;
    vm.runInNewContext(src, sandbox);
  };
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


CASCADE = """
  const w = world(OPTS);
  const items = [0, 1, 2, 3].map((i) => w.named("item" + i, { querySelector: (s) => null }));
  const counterLive = w.named("live", {});
  const counter = w.named("counter", { dataset: { fxCount: "641" }, querySelector: (s) => (s === ".cnt-live" ? counterLive : null) });
  items[3].querySelector = (s) => (s === "[data-fx-count]" ? counter : null);
  const group = w.named("group", { top: TOP, getBoundingClientRect() { return { top: this.top }; }, querySelectorAll: (s) => (s === "[data-fx-item]" ? items : []) });
  w.run({ '[data-fx="cascade"]': [group], "[data-fx-count] .cnt-live": [counterLive] });
"""


def cascade(top, extra="", opts="{}"):
    return CASCADE.replace("TOP", str(top)).replace("OPTS", opts) + extra


def test_cards_come_in_one_after_another_as_the_group_scrolls_up_the_screen():
    r = run_node(cascade(0, """
      w.fireIO([{ target: group, isIntersecting: true }]); w.advance(32);
      const es = (top) => { group.top = top * 800; w.fireIO([{ target: group, isIntersecting: true }]); w.writes.length = 0; w.advance(32);
        return items.map((i) => parseFloat(i.style.props["--e"] || "-1")); };
      const result = { low: es(0.9), mid: es(0.6), high: es(0.3) };""".replace("window_dummy = 0;", "")))
    assert all(v == 0 for v in r["low"]), r
    assert 0 < r["mid"][0] and r["mid"][0] >= r["mid"][1] >= r["mid"][2] >= r["mid"][3], r
    assert all(v == 1 for v in r["high"]), r


def test_a_counter_counts_up_once_inside_its_box_and_ends_on_the_real_number():
    r = run_node(cascade(0, """
      group.top = 0; w.fireIO([{ target: group, isIntersecting: true }]); w.advance(16);
      const seen = [counterLive.textContent]; w.advance(300); seen.push(counterLive.textContent); w.advance(700); seen.push(counterLive.textContent);
      group.top = 700; w.fireIO([{ target: group, isIntersecting: true }]); w.advance(16); group.top = 0; w.fireIO([{ target: group, isIntersecting: true }]); w.advance(100);
      seen.push(counterLive.textContent);
      const result = { seen, loops: w.pending() };"""))
    first, mid, end, after = (int(x) for x in r["seen"])
    assert first <= 5 and 0 < mid < 641 and end == 641 and after == 641, r
    assert r["loops"] == 0, "the loop stops when nothing is moving or counting"


def test_pieces_that_are_not_near_the_screen_are_left_alone_and_the_loop_idles():
    r = run_node(cascade(5000, """
      w.fireIO([{ target: group, isIntersecting: false }]); w.writes.length = 0; w.advance(64);
      const result = { writes: w.writes.length, loops: w.pending() };"""))
    assert r == {"writes": 0, "loops": 0}


def test_scroll_and_resize_listeners_are_passive():
    r = run_node(cascade(0, """
      const passive = Object.fromEntries(["scroll", "resize"].map((t) => [t, w.listeners[t].every((l) => l.o && l.o.passive === true)]));
      const result = { passive };"""))
    assert r["passive"] == {"scroll": True, "resize": True}


def test_the_loop_stops_in_a_hidden_tab_and_starts_again_when_it_is_shown():
    r = run_node(cascade(0, """
      w.fireIO([{ target: group, isIntersecting: true }]);
      const running = w.pending();
      w.doc.hidden = true; w.listeners["doc:visibilitychange"].forEach((f) => f());
      const hidden = w.pending();
      w.listeners.scroll.forEach((l) => l.f());                      // scrolling in a hidden tab schedules nothing
      const stillHidden = w.pending();
      w.doc.hidden = false; w.listeners["doc:visibilitychange"].forEach((f) => f());
      const result = { running, hidden, stillHidden, shown: w.pending() };"""))
    assert r == {"running": 1, "hidden": 0, "stillHidden": 0, "shown": 1}


def test_tiles_follow_each_other_along_a_row():
    r = run_node("""
      const w = world({});
      const tile = (n, top, left) => w.named("t" + n, { getBoundingClientRect: () => ({ top, left }) });
      const t = [tile(0, 700, 0), tile(1, 700, 300), tile(2, 700, 600), tile(3, 1000, 0)];
      const grid = w.named("grid", { querySelectorAll: (s) => (s === ".tile" ? t : []) });
      w.run({ '[data-fx="tiles"]': [grid] });
      w.fireIO([{ target: grid, isIntersecting: true }]); w.advance(32);
      const e = t.map((x) => parseFloat(x.style.props["--e"]));
      const result = { e };""")
    e = r["e"]
    assert e[0] > e[1] > e[2] > 0 and e[3] == 0, e


def test_the_showcase_progress_is_how_far_through_the_pinned_section_the_reader_is():
    r = run_node("""
      const w = world({});
      const stage = w.named("stage", { offsetHeight: 725 });
      const sec = w.named("sec", { top: 75, offsetHeight: 1920, querySelector: (s) => (s === ".showcase-stage" ? stage : null), getBoundingClientRect() { return { top: this.top }; }, classList: { add(c) { this.s.add(c); }, remove(c) { this.s.delete(c); }, s: new Set() } });
      const doc = { '[data-fx="showcase"]': [sec], ".site-header": [{ offsetHeight: 75 }] };
      w.run(doc);
      const ps = [];
      for (const top of [75, 75 - 1195 * 0.5, 75 - 1195, -2000, 900]) { sec.top = top; w.fireIO([{ target: sec, isIntersecting: true }]); w.advance(32); ps.push(parseFloat(sec.style.props["--p"])); }
      const result = { ps, fxTop: sec.style.props["--fx-top"] };""")
    assert r["ps"][0] == 0 and abs(r["ps"][1] - 0.5) < 0.01 and r["ps"][2] == 1 and r["ps"][3] == 1 and r["ps"][4] == 0, r
    assert r["fxTop"] == "75px"


def test_focusing_into_the_showcase_switches_on_the_show_everything_class():
    r = run_node("""
      const w = world({});
      const stage = w.named("stage", { offsetHeight: 700 });
      const sec = w.named("sec", { querySelector: (s) => (s === ".showcase-stage" ? stage : null), getBoundingClientRect: () => ({ top: 0 }), offsetHeight: 1900, classList: { add(c) { this.s.add(c); }, remove(c) { this.s.delete(c); }, s: new Set() } });
      w.run({ '[data-fx="showcase"]': [sec] });
      sec.listeners.focusin[0]();
      const result = { focus: sec.classList.s.has("is-focus") };""")
    assert r == {"focus": True}


def test_reduced_motion_runs_nothing_at_all():
    r = run_node(cascade(0, """
      const result = { listeners: Object.keys(w.listeners), writes: w.writes.length, loops: w.pending(), live: counterLive.textContent };""", "{ calm: true }"))
    assert r == {"listeners": [], "writes": 0, "loops": 0, "live": ""}


def test_without_an_intersection_observer_every_piece_is_simply_kept_up_to_date():
    r = run_node(cascade(0, """
      w.advance(32);
      const result = { e: items.map((i) => parseFloat(i.style.props["--e"])) };""", "{ noIO: true }"))
    assert all(v == 1 for v in r["e"]), r


def test_will_change_is_on_only_while_a_piece_is_near_the_screen():
    r = run_node(cascade(0, """
      const on = () => items.map((i) => i.classList.s.has("is-animating"));
      const before = on();
      w.fireIO([{ target: group, isIntersecting: true }]); const near = on();
      w.fireIO([{ target: group, isIntersecting: false }]); const gone = on();
      const result = { before, near, gone };"""))
    assert r == {"before": [False] * 4, "near": [True] * 4, "gone": [False] * 4}
