"""Fine-tuning: every knob is documented and used, every effect in the inventory has a switch, the switch list lives in one
file, and setting the off attribute is what turns an effect off."""
import json
import re
from pathlib import Path

import pytest

from tests.test_fx_inventory import ALL_ROWS

ROOT = Path(__file__).resolve().parent.parent
TUNING = (ROOT / "app" / "static" / "css" / "fx-tuning.css").read_text(encoding="utf-8").replace("\r\n", "\n")
DOC = (ROOT / "docs" / "MOTION_TUNING.md").read_text(encoding="utf-8")
STYLES = "".join((ROOT / "app" / "static" / "css" / f).read_text(encoding="utf-8") for f in ("main.css", "motion3.css", "motion3-ui.css"))
SCRIPTS = "".join(f.read_text(encoding="utf-8") for f in (ROOT / "app" / "static" / "js").glob("*.js"))
KNOBS = re.findall(r"^  (--[\w-]+):\s*([^;]+);\s*/\*\s*([\w-]+(?:, [\w-]+)*|ALL)", TUNING.split("/* derived")[0], re.M)
SWITCHES = sorted(set(re.findall(r'html\[data-fx-off~="([\w-]+)"\]', TUNING)))
NEUTRALISING = re.compile(r"animation: none|transition: none|transform: none|display: none|opacity: 1|clip-path: none|stroke-dashoffset: 0|height: auto|position: static|position: relative|view-transition-name: none")


# ---- knobs -----------------------------------------------------------------------------------------------------------------

def test_the_twelve_knobs_exist_with_their_defaults_and_are_all_named_after_an_effect():
    names = [k[0] for k in KNOBS]
    assert names == ["--fx-speed", "--fx-dist", "--fx-stagger", "--fx-ease", "--tilt-max", "--magnet-max", "--parallax-strength",
                     "--cover-slide-distance", "--loader-ms", "--cart-anim-ms", "--pay-anim-ms", "--marquee-speed"]
    defaults = {k: v.strip() for k, v, _ in KNOBS}
    assert defaults["--fx-speed"] == "1" and defaults["--tilt-max"] == "6" and defaults["--magnet-max"] == "6"
    assert defaults["--fx-dist"] == "14px" and defaults["--fx-stagger"] == "60ms" and defaults["--cover-slide-distance"] == "60vw"
    assert defaults["--loader-ms"] == "1000ms" and defaults["--cart-anim-ms"] == "1000" and defaults["--pay-anim-ms"] == "1400"


@pytest.mark.parametrize("knob", [k[0] for k in KNOBS])
def test_every_knob_is_documented_with_a_range_and_actually_used(knob):
    row = next(l for l in DOC.splitlines() if l.startswith(f"| `{knob}`"))
    assert len([c for c in row.split("|") if c.strip()]) == 4 and re.search(r"\d", row.split("|")[-2])          # name, default, what, range
    users = STYLES.count(f"var({knob}") + SCRIPTS.count(f'"{knob}"') + TUNING.count(f"var({knob}")
    assert users >= 1, f"{knob} is defined but nothing reads it"


def test_the_derived_numbers_follow_the_knobs_and_the_defaults_leave_every_duration_unchanged():
    assert "--cart-k: calc(var(--cart-anim-ms) / 1000 / var(--fx-speed))" in TUNING
    assert "--pay-k: calc(var(--pay-anim-ms) / 1400 / var(--fx-speed))" in TUNING
    css = (ROOT / "app" / "static" / "css" / "motion3.css").read_text(encoding="utf-8")
    assert "calc(240ms * var(--cart-k))" in css and "calc(440ms * var(--pay-k))" in css
    assert "--fx-dur: calc(460ms / var(--fx-speed, 1))" in css
    assert "html.intro-run .loader { animation-delay: var(--loader-ms), 2s; }" in TUNING


def test_the_tuning_sheet_is_loaded_before_the_stylesheet_that_uses_it(client):
    html = client.get("/").get_data(as_text=True)
    links = re.findall(r'<link rel="stylesheet" href="([^"]+)"', html)
    names = [l.rsplit("/", 1)[1] for l in links]
    assert names.index("fx-tuning.css") == names.index("main.css") + 1 and names.index("fx-tuning.css") < names.index("motion3.css")


# ---- switches -----------------------------------------------------------------------------------------------------------------

def test_every_switch_has_a_rule_that_stops_its_animation_and_is_listed_in_the_docs():
    assert len(SWITCHES) >= 40
    for name in SWITCHES:
        rules = [b for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", TUNING) if f'data-fx-off~="{name}"' in s]
        assert rules and any(NEUTRALISING.search(b) for b in rules), name
        assert f"`{name}`" in DOC, f"{name} is not in docs/MOTION_TUNING.md"


def test_the_twenty_named_effects_are_all_switchable():
    wanted = "lines words from-left from-right zoom flip clip draw hscroll marquee tilt magnetic rail parallax view-transitions spotlight toasts stepper status-timeline admin-motion".split()
    assert set(wanted) <= set(SWITCHES), set(wanted) - set(SWITCHES)


def test_every_effect_in_the_inventory_names_a_switch_that_exists():
    assert len(ALL_ROWS) >= 100
    for effect, page, hook, file, switch in ALL_ROWS:
        assert switch == "-" or switch in SWITCHES, (effect, switch)
    covered = {r[4] for r in ALL_ROWS} - {"-"}
    missing = set(SWITCHES) - covered
    assert not missing - {"zoom", "flip", "from-right"}, missing        # single-block words share the from-left row


def test_plumbing_rows_marked_with_a_dash_are_only_plumbing():
    plumbing = [r[0] for r in ALL_ROWS if r[4] == "-"]
    assert 5 <= len(plumbing) <= 20
    for name in plumbing:
        assert re.search(r"macro|guard|machinery|cleanup|adaptive|tokens|settled|progress|script|markup", name, re.I), name


def test_the_off_list_is_one_json_file_that_is_empty_by_default_and_names_only_real_switches():
    cfg = json.loads((ROOT / "app" / "fx.json").read_text(encoding="utf-8"))
    assert cfg == {"off": []}
    assert set(cfg["off"]) <= set(SWITCHES)


def test_the_server_writes_the_list_into_the_html_element(client, app, monkeypatch):
    assert '<html lang="en" data-fx-off="">' in client.get("/").get_data(as_text=True)
    import app.context as ctx
    monkeypatch.setattr(ctx, "FX_OFF", ["tilt", "marquee"])
    page = client.get("/").get_data(as_text=True)
    assert '<html lang="en" data-fx-off="tilt marquee">' in page


def test_an_error_page_and_the_admin_carry_the_attribute_too_so_admin_motion_can_be_switched_off(client, admin_client):
    assert 'data-fx-off=""' in client.get("/no-such-page").get_data(as_text=True)
    assert 'data-fx-off=""' in admin_client.get("/admin").get_data(as_text=True)


def test_the_off_selectors_beat_the_rules_they_override():
    # an OFF rule that loses to a more specific rule would silently do nothing, so each carries !important
    for name in SWITCHES:
        for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", TUNING):
            if f'data-fx-off~="{name}"' in s:
                assert "!important" in b, (name, s)
