"""Checkpoint 2 of the motion pass: the one-time intro loader. It must fail safe, so most of these tests are about
what happens when things go wrong (no storage, no script, no motion) as much as about the happy path."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
CSS = (STATIC / "css" / "main.css").read_text(encoding="utf-8").replace("\r\n", "\n")
BOOT = STATIC / "js" / "motion-boot.js"
MOTION_JS = STATIC / "js" / "motion.js"
NODE = shutil.which("node")


def loader_markup(html):
    m = re.search(r'<div class="loader" data-loader aria-hidden="true">(.*?)</p>\s*</div>\s*</div>', html, re.S)
    assert m, "no loader block"
    return m.group(0)


# ---- markup -----------------------------------------------------------------------------------------------------------

def test_boot_script_is_a_plain_script_in_head_and_motion_js_is_deferred_before_app_js(client):
    html = client.get("/").get_data(as_text=True)
    head = html[:html.index("</head>")]
    boot = re.search(r"<script ([^>]*motion-boot\.js[^>]*)></script>", head)
    assert boot and "defer" not in boot.group(1) and "async" not in boot.group(1)
    body_scripts = re.findall(r'<script src="([^"]+)" defer></script>', html)
    assert [s.rsplit("/", 1)[1] for s in body_scripts][:2] == ["motion.js", "app.js"]
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline script"


def test_the_loader_is_decorative_has_nothing_focusable_and_the_six_objects_come_in_order(client):
    block = loader_markup(client.get("/").get_data(as_text=True))
    assert not re.search(r"<(a|button|input|select|textarea|iframe)\b|tabindex|contenteditable", block)
    assert re.findall(r'<g class="ls ls-(\w+)">', block) == ["inbox", "cart", "tv", "pc", "cpu", "ram"]
    assert 'data-loader-pct' in block and block.count("<svg") == 1


@pytest.mark.parametrize("path", ["/", "/catalogue", "/login", "/no-such-page"])
def test_page_content_is_never_aria_hidden(client, path):
    html = client.get(path).get_data(as_text=True)
    for tag in ("body", "main", "header", "footer"):
        for opening in re.findall(rf"<{tag}\b[^>]*>", html):
            assert "aria-hidden" not in opening, opening
    outside = html.replace(loader_markup(html), "")
    assert 'id="main"' not in outside or "aria-hidden" not in re.search(r'<[^>]*id="main"[^>]*>', outside).group(0)


def test_the_loader_is_on_every_page_type_through_the_base_template(buyer, admin_client):
    for client, path in ((buyer, "/orders"), (buyer, "/cart"), (admin_client, "/admin"), (buyer, "/no-such-page")):
        assert 'data-loader aria-hidden="true"' in client.get(path).get_data(as_text=True), path


# ---- stylesheet -------------------------------------------------------------------------------------------------------

def rule(selector):
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS, re.S)
    assert m, selector
    return m.group(1)


def test_the_loader_is_hidden_by_default_and_shown_only_under_the_class_motion_boot_adds():
    assert "display: none" in rule(".loader")
    shown = rule(".intro-run .loader")
    assert "display: grid" in shown and "pointer-events: none" in shown and "position: fixed" in shown
    assert not re.search(r"(?m)^\.loader\s*\{[^}]*display:\s*(grid|flex|block)", CSS)      # the base rule only ever hides


def test_the_css_alone_finishes_the_loader_between_900_and_1400_ms_and_a_failsafe_hides_it_by_2s():
    anim = re.search(r"animation:\s*loader-out\s+(\d+)ms\s+[^,]+?\s+(\d+)ms\s+forwards,\s*loader-failsafe\s+1ms\s+linear\s+(\d+)s\s+forwards", rule(".intro-run .loader"))
    assert anim, rule(".intro-run .loader")
    duration, delay, failsafe = int(anim.group(1)), int(anim.group(2)), int(anim.group(3))
    assert 900 <= delay + duration <= 1400
    assert failsafe <= 2
    assert re.search(r"@keyframes loader-failsafe\s*\{\s*to\s*\{\s*opacity:\s*0;", CSS)


def test_every_keyframes_block_in_the_stylesheet_animates_only_opacity_and_transform():
    names = re.findall(r"@keyframes ([\w-]+)", CSS)
    assert {"ls-drop", "ls-from-left", "loader-out", "loader-failsafe", "motion-failsafe"} <= set(names)
    for m in re.finditer(r"@keyframes ([\w-]+)\s*\{((?:[^{}]|\{[^{}]*\})*)\}", CSS):
        props = set(re.findall(r"([\w-]+)\s*:", re.sub(r"\{|\}", ";", m.group(2))))
        assert props <= {"opacity", "transform"}, (m.group(1), props)


def test_the_scene_uses_only_brand_colours_and_no_gradient_or_shadow():
    scene = CSS[CSS.index("/* ===== Motion: intro loader"):]
    assert not re.search(r"gradient|box-shadow|filter:|drop-shadow|rgba?\(|#[0-9a-fA-F]{3,8}\b", scene)
    assert "will-change" not in scene


def test_reduced_motion_removes_the_loader_from_the_stylesheet_too():
    tail = CSS[CSS.index("/* ===== Motion: intro loader"):]
    assert re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{\s*\.intro-run \.loader\s*\{\s*display:\s*none;", tail)


# ---- scripts ------------------------------------------------------------------------------------------------------------

def test_script_budgets_and_no_timers():
    assert BOOT.stat().st_size < 1500
    assert MOTION_JS.stat().st_size < 15 * 1024
    for path in (BOOT, MOTION_JS):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"setTimeout|setInterval", text), path.name
        assert "innerHTML" not in text and 'setAttribute("style"' not in text and ".style.cssText" not in text


needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


def node(script):
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@needs_node
def test_both_scripts_are_valid_javascript():
    for path in (BOOT, MOTION_JS):
        done = subprocess.run([NODE, "--check", str(path)], capture_output=True, text=True, timeout=30)
        assert done.returncode == 0, done.stderr


BOOT_HARNESS = r"""
const src = require('fs').readFileSync(process.argv[1], 'utf8');
function run(o) {
  const classes = new Set(), store = Object.assign({}, o.store || {});
  const win = {
    matchMedia: o.noMatchMedia ? undefined : () => ({ matches: !!o.reduced }),
    sessionStorage: { getItem: (k) => { if (o.throws) throw new Error('blocked'); return k in store ? store[k] : null; },
                      setItem: (k, v) => { if (o.throws) throw new Error('blocked'); store[k] = v; } },
  };
  const doc = { documentElement: { classList: { add: (c) => classes.add(c) } } };
  new Function('window', 'document', src)(win, doc);
  return { classes: [...classes], store };
}
console.log(JSON.stringify({
  first: run({}), second: run({ store: { 'ps-intro': '1' } }), reduced: run({ reduced: true }),
  blocked: run({ throws: true }), noMatchMedia: run({ noMatchMedia: true }),
}));
"""


@needs_node
def test_boot_adds_the_class_once_per_session_and_never_throws():
    out = subprocess.run([NODE, "-e", BOOT_HARNESS.replace("process.argv[1]", json.dumps(str(BOOT)))], capture_output=True,
                         text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout)
    assert r["first"]["classes"] == ["intro-run"] and r["first"]["store"] == {"ps-intro": "1"}     # flag set at the start
    assert r["second"]["classes"] == []                         # same session: no loader
    assert r["reduced"]["classes"] == [] and r["reduced"]["store"] == {}
    assert r["blocked"]["classes"] == []                        # storage blocked: no loader, no exception
    assert r["noMatchMedia"]["classes"] == ["intro-run"]        # an old browser without matchMedia still works


MOTION_HARNESS = r"""
const src = require('fs').readFileSync(%s, 'utf8');
function run(withLoader) {
  const classes = new Set(withLoader ? ['intro-run'] : []);
  const listeners = {}, winListeners = {};
  const pct = { textContent: '0' };
  const loader = { querySelector: (q) => (q === '[data-loader-pct]' ? pct : null), addEventListener: (t, fn) => { listeners[t] = fn; }, removeEventListener: (t) => { delete listeners[t]; } };
  const doc = {
    documentElement: { classList: { contains: (c) => classes.has(c), remove: (c) => classes.delete(c) } },
    querySelector: (q) => (q === '[data-loader]' ? loader : null), querySelectorAll: () => [], addEventListener: () => {},
  };
  const frames = []; let now = 0, cancelled = 0;
  const win = { addEventListener: (t, fn) => { winListeners[t] = fn; }, matchMedia: () => ({ matches: false, addEventListener() {} }) };
  const g = { window: win, document: doc, performance: { now: () => now }, requestAnimationFrame: (fn) => { frames.push(fn); return frames.length; },
              cancelAnimationFrame: () => { cancelled += 1; }, Math };
  new Function('window', 'document', 'performance', 'requestAnimationFrame', 'cancelAnimationFrame', src)(
    g.window, g.document, g.performance, g.requestAnimationFrame, g.cancelAnimationFrame);
  return { frames, setNow: (t) => { now = t; }, pct, loader, classes, listeners, winListeners, cancelled: () => cancelled };
}
const quiet = run(false);
const a = run(true);
const seen = [];
for (let t = 0; t <= 1400; t += 100) { a.setNow(t); const f = a.frames.shift(); if (f) f(t); seen.push(+a.pct.textContent); }
const before = [...a.classes];
const child = { name: 'a scene shape' };
a.listeners.animationend({ animationName: 'ls-drop', target: child });          // bubbled up from the artwork
a.listeners.animationend({ animationName: 'loader-out', target: child });       // same name but not the loader itself
a.listeners.animationend({ animationName: 'loader-failsafe', target: a.loader });
const stillThere = a.classes.has('intro-run');
a.listeners.animationend({ animationName: 'loader-out', target: a.loader });
const b = run(true); b.winListeners.pagehide();
console.log(JSON.stringify({ quietFrames: quiet.frames.length, seen, before, stillThere, after: [...a.classes], pagehideCancelled: b.cancelled(),
                             remainingFrames: a.frames.length }));
"""


@needs_node
def test_motion_js_counts_to_100_removes_the_class_when_the_css_exit_ends_and_cancels_on_pagehide():
    out = subprocess.run([NODE, "-e", MOTION_HARNESS % json.dumps(str(MOTION_JS))], capture_output=True,
                         text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout)
    assert r["quietFrames"] == 0                                # no .intro-run: motion.js does nothing at all
    assert r["seen"][0] < 20 and r["seen"][-1] == 100 and r["seen"] == sorted(r["seen"])
    assert r["stillThere"] is True and r["after"] == []         # only the loader's own exit animation ends it
    assert r["remainingFrames"] == 0 and r["pagehideCancelled"] >= 1
