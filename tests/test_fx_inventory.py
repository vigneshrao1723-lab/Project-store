"""The motion inventory (docs/MOTION_INVENTORY.md) is a promise that no effect is quietly lost. Every row names a literal
hook that must still be in its file. Work on motion is additive: retiring an effect means deleting its row on purpose."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOC = (ROOT / "docs" / "MOTION_INVENTORY.md").read_text(encoding="utf-8")
ALL_ROWS = [m.groups() for m in re.finditer(r"^\| (?!Effect|---)(.+?) \| (.+?) \| `(.+?)` \| (.+?) \| ([\w-]+) \|$", DOC, re.M)]
ROWS = [r[:4] for r in ALL_ROWS]


def test_the_inventory_lists_a_real_number_of_effects_and_never_fewer_than_it_did():
    assert len(ROWS) >= 50, len(ROWS)         # 53 rows when the additive-only rule started; it only grows


@pytest.mark.parametrize("effect,page,hook,file", ROWS, ids=[r[0] for r in ROWS])
def test_every_listed_hook_is_still_in_its_file(effect, page, hook, file):
    path = ROOT / file
    assert path.exists(), f"{effect}: {file} is gone"
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert hook in text, f"{effect}: hook {hook!r} no longer appears in {file}"


def test_every_row_names_an_existing_file_and_no_row_is_listed_twice():
    seen = set()
    for effect, page, hook, file in ROWS:
        assert (ROOT / file).exists(), file
        assert (effect, hook, file) not in seen, effect
        seen.add((effect, hook, file))


def test_the_pinned_showcase_is_restored_and_stays_pinned():
    home = (ROOT / "app" / "templates" / "home.html").read_text(encoding="utf-8")
    css = (ROOT / "app" / "static" / "css" / "motion3.css").read_text(encoding="utf-8")
    assert 'class="showcase" {{ fx(\'pin\') }}' in home and "pin-soft" not in home
    assert re.search(r'html\.fx-on:not\(\.fx-lite\) \[data-fx="pin"\]:not\(\.pin-lg\):not\(\.pin-soft\) \.fx-stage \{[^}]*position: sticky', css)
    assert home.count("sc-line") >= 3 and "sc-cue" in home       # three headline lines and the Scroll cue
