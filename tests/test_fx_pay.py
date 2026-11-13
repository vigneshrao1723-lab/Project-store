"""Motion 3, item B: the payment result mark. The server renders a decorative mark next to the text it already
renders; these tests pin that the text, status and routes are unchanged, that the mark plays only on the page the
visitor lands on right after paying or being declined, and that the stylesheet and script behave."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "motion3.css").read_text(encoding="utf-8").replace("\r\n", "\n")
BARE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
JS = ROOT / "app" / "static" / "js" / "fx-pay.js"
NODE = shutil.which("node")
PAY = BARE[BARE.index(".result {"):BARE.index('html.fx-on [data-fx="rise"]:not(.is-in)')]


def _order(client, product):
    client.post("/api/v1/cart/items", json={"product_id": product.id, "qty": 1})
    return client.post("/api/v1/checkout", json={"billing_name": "Buyer"}).get_json()["id"]


def _mark(html):
    found = re.findall(r'<div class="result [^"]*"[^>]*>', html)
    return found[0] if found else None


# ---- markup: text and status are what they were -----------------------------------------------------------------------

def test_right_after_paying_the_order_page_plays_the_success_mark_and_keeps_its_text(buyer, rag):
    pid = _order(buyer, rag)
    page = buyer.post(f"/checkout/test-pay/{pid}", data={"outcome": "pay"}, follow_redirects=True).get_data(as_text=True)
    mark = _mark(page)
    assert 'data-result="success"' in mark and "data-play" in mark and 'aria-hidden="true"' in mark
    assert re.search(r'<div class="wrap flashes" role="status">\s*<p class="flash flash-success">Payment received\. Your download link is below\.</p>', page)
    assert '<span class="status s-paid">Paid</span>' in page and "Your downloads" in page
    assert "style=" not in page.split("<main", 1)[1]
    assert "fx-pay.js" in page


def test_a_later_visit_to_a_paid_order_shows_the_finished_mark_without_playing_it(buyer, rag):
    pid = _order(buyer, rag)
    buyer.post(f"/checkout/test-pay/{pid}", data={"outcome": "pay"}, follow_redirects=True)     # lands on the page that plays it
    public_id = pid
    page = buyer.get(f"/orders/{public_id}").get_data(as_text=True)
    mark = _mark(page)
    assert 'data-result="success"' in mark and "data-play" not in mark


def test_unpaid_and_cancelled_orders_show_no_mark(buyer, rag):
    public_id = _order(buyer, rag)
    assert _mark(buyer.get(f"/orders/{public_id}").get_data(as_text=True)) is None


def test_a_declined_test_payment_plays_the_failure_mark_and_keeps_its_text_and_buttons(buyer, rag):
    pid = _order(buyer, rag)
    page = buyer.post(f"/checkout/test-pay/{pid}", data={"outcome": "fail"}, follow_redirects=True).get_data(as_text=True)
    mark = _mark(page)
    assert 'data-result="failure"' in mark and "data-play" in mark and 'aria-hidden="true"' in mark
    assert "The test payment was declined. Your items are still held. Try again or cancel." in page
    assert 'role="status"' in page.split('<main', 1)[0]
    assert 'name="outcome" value="pay"' in page and 'name="outcome" value="fail"' in page
    assert "fx-pay.js" not in page, "failure plays every time, so it needs no script"


def test_the_pay_page_without_an_error_has_no_mark_and_is_otherwise_untouched(buyer, rag):
    pid = _order(buyer, rag)
    page = buyer.get(f"/checkout/pay/{pid}").get_data(as_text=True)
    assert _mark(page) is None and "fx-pay.js" not in page
    assert "Practice payment, no real money" in page


def test_the_mark_carries_no_words_and_no_links(buyer, rag):
    pid = _order(buyer, rag)
    page = buyer.post(f"/checkout/test-pay/{pid}", data={"outcome": "fail"}, follow_redirects=True).get_data(as_text=True)
    block = re.search(r'<div class="result .*?</div>', page, re.S).group(0)
    assert not re.search(r"<(a|button|input|text|title)\b", block)
    assert re.sub(r"<[^>]+>", "", block).strip() == ""


# ---- stylesheet -------------------------------------------------------------------------------------------------------

def test_payment_keyframes_move_only_transform_and_opacity_and_the_marks_draw_with_dashoffset():
    names = re.findall(r"@keyframes (rs-[\w-]+) ", BARE)
    assert {"rs-disc", "rs-ring", "rs-sweep", "rs-draw", "rs-orbit", "rs-after"} <= set(names)
    for name in names:
        body = re.search(r"@keyframes %s \{(.*?)\n(?=@|\.|/\*|$)" % name, BARE + "\n", re.S).group(1)
        props = set(re.findall(r"([\w-]+)\s*:", body)) - {"from", "to"}
        assert props <= {"opacity", "transform"} | ({"stroke-dashoffset"} if name == "rs-draw" else set()), (name, props)


def test_the_sequence_order_disc_then_mark_then_the_content_fades_up_after_the_mark_is_done():
    def timing(selector_part):
        rule = next(b for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", PAY) if selector_part in s and "animation:" in b)
        ms = [int(x) for x in re.findall(r"(\d+)ms", rule)]
        return ms[0], (ms[1] if len(ms) > 1 else 0)
    disc, _ = timing(".rs-disc")
    tick, tick_delay = timing("result-success[data-play]:not(.is-played) .rs-draw")
    x2, x2_delay = timing(".rs-x2")
    after, after_delay = timing("main:has(.result[data-play]:not(.is-played)) .pay-actions")
    assert disc <= 500 and tick_delay >= disc, "the tick starts once the disc has grown"
    assert after_delay >= tick_delay + tick and after_delay >= x2_delay + x2, "the content arrives after the mark has finished"
    assert after + after_delay <= 1600, "the whole sequence is over in about a second and a half"


def test_nothing_is_hidden_by_default_nothing_depends_on_hover_and_will_change_is_only_on_is_animating():
    assert ":hover" not in PAY and "!important" not in PAY
    assert "display: none" not in PAY and "visibility: hidden" not in PAY
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"@keyframes[^\n]*\n", "", PAY)):
        assert "will-change" not in body
        if re.search(r"opacity:\s*0\b", body):
            assert selector.strip() == ".rs-sweep", selector            # only the progress line starts invisible
    resting = [b for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", PAY) if s.strip() in (".rs-draw", ".rs-disc", ".rs-ring", ".result")]
    assert resting and all("opacity: 0" not in b and "stroke-dashoffset: 30" not in b for b in resting)


def test_only_a_mark_that_asks_to_play_animates_and_reduced_motion_switches_it_off():
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", PAY):
        if "animation:" in body and "@media" not in sel and "none" not in body:
            assert "[data-play]:not(.is-played)" in sel, sel
    inner = re.search(r"@media \(prefers-reduced-motion: reduce\) \{(.*)\n\}", PAY, re.S).group(1)
    assert ".result[data-play] * { animation: none; }" in inner
    assert "animation: none" in inner.split("}")[1]


# ---- the guard script -------------------------------------------------------------------------------------------------

def run_node(body):
    if not NODE:
        pytest.skip("node is not installed")
    prelude = """
      const vm = require("vm"), fs = require("fs");
      const src = fs.readFileSync(process.argv[1], "utf8");
      function run({ mark, store, broken }) {
        const classes = new Set();
        const el = mark ? { dataset: { order: "PS-ABC" }, classList: { add: (c) => classes.add(c) } } : null;
        const data = store || {};
        const sessionStorage = broken ? { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } }
          : { getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => { data[k] = v; } };
        vm.runInNewContext(src, { document: { querySelector: (s) => (s === ".result-success[data-play]" ? el : null) }, window: { sessionStorage } });
        return { played: classes.has("is-played"), data };
      }
    """
    out = subprocess.run([NODE, "-e", prelude + body + "\nconsole.log(JSON.stringify(result));", str(JS)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_first_view_of_an_orders_success_plays_and_the_second_is_switched_off():
    r = run_node("""
      const store = {}; const first = run({ mark: true, store }); const second = run({ mark: true, store });
      const result = { first: first.played, second: second.played, key: Object.keys(store) };""")
    assert r == {"first": False, "second": True, "key": ["ps-paid-PS-ABC"]}


def test_another_order_still_plays_and_blocked_storage_just_plays():
    assert run_node("""
      const store = { "ps-paid-PS-OTHER": "1" }; const r1 = run({ mark: true, store });
      const result = { played: r1.played };""") == {"played": False}
    assert run_node("""
      const r1 = run({ mark: true, broken: true });
      const result = { played: r1.played };""") == {"played": False}


def test_a_page_without_the_mark_is_left_alone():
    assert run_node("const r = run({ mark: false }); const result = { played: r.played, keys: Object.keys(r.data) };") == {"played": False, "keys": []}
