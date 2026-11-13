"""The figures the store shows about itself. Live figures (projects, fields, hold minutes) are counted from the
catalogue and config; project figures (tests, coverage) live in app/facts.json, which is the one place the home page
and the README both agree with and which these tests keep equal to what pytest actually collects."""
import json
import re
import subprocess
import sys
from pathlib import Path

from app.extensions import db
from app.models import Category, Product

ROOT = Path(__file__).resolve().parent.parent
FACTS = json.loads((ROOT / "app" / "facts.json").read_text(encoding="utf-8"))
README = (ROOT / "README.md").read_text(encoding="utf-8")


def figures(html):
    out = {}
    for card in re.findall(r'<article class="fx-card fx-stat".*?</article>', html, re.S):
        n = int(re.search(r'data-to="(\d+)"', card).group(1))
        out[re.sub(r"<[^>]+>", "", re.search(r'<p class="fx-l">(.*?)</p>', card, re.S).group(1))] = n
    return out


def collected(*args):
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *args],
                         cwd=ROOT, capture_output=True, text=True).stdout
    return int(re.search(r"(\d+) tests? collected", out).group(1))


# ---- live figures ---------------------------------------------------------------------------------------------------

def test_the_live_figures_are_counted_from_the_catalogue(client, app):
    stats = figures(client.get("/").get_data(as_text=True))
    active = db.session.scalar(db.select(db.func.count(Product.id)).where(Product.is_active.is_(True)))
    fields = db.session.scalar(db.select(db.func.count(db.distinct(Product.category_id))).where(Product.is_active.is_(True)))
    labels = list(stats)
    assert stats[labels[0]] == active and labels[0].startswith("project")
    assert stats[labels[1]] == fields
    assert stats[labels[2]] == app.config["RESERVATION_MINUTES"]
    names = labels[1].split(": ", 1)[1].split(", ")
    assert set(names) == {c.name for c in db.session.scalars(db.select(Category)) if any(p.is_active for p in c.products)}


def test_the_live_figures_follow_the_data_when_it_changes(client, app, rag):
    before = figures(client.get("/").get_data(as_text=True))
    rag.is_active = False
    db.session.commit()
    after = figures(client.get("/").get_data(as_text=True))
    assert list(after.values())[0] == list(before.values())[0] - 1
    app.config["RESERVATION_MINUTES"] = 7
    assert list(figures(client.get("/").get_data(as_text=True)).values())[2] == 7


# ---- project figures: one file, three readers --------------------------------------------------------------------------

def test_the_home_page_shows_exactly_what_the_facts_file_says(client):
    html = client.get("/").get_data(as_text=True)
    stats = figures(html)
    assert list(stats.values())[3] == FACTS["tests"]
    assert "covering %d%% of the app's lines" % FACTS["coverage"] in html


def test_the_readme_states_exactly_what_the_facts_file_says():
    assert "| {:,} tests pass on SQLite, {} skip without MySQL".format(FACTS["tests"], FACTS["skipped"]) in README
    assert "Line coverage of `app/` is {}% ({:,} statements, {} missed)".format(FACTS["coverage"], FACTS["statements"], FACTS["missed"]) in README
    assert "{} of those tests are the security suite".format(FACTS["security_tests"]) in README


def test_the_facts_file_has_exactly_these_keys_and_sane_values():
    assert set(FACTS) == {"tests", "skipped", "security_tests", "coverage", "statements", "missed"}
    assert all(isinstance(v, int) and v >= 0 for v in FACTS.values())
    assert 0 < FACTS["coverage"] <= 100 and FACTS["missed"] < FACTS["statements"]
    assert round(100 * (FACTS["statements"] - FACTS["missed"]) / FACTS["statements"]) == FACTS["coverage"]


def test_no_template_or_readme_hard_codes_a_test_count():
    for f in (ROOT / "app" / "templates").rglob("*.html"):
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"\b\d{3,4}\s+(automated\s+)?tests?\b", text), f.name
        assert '"tests":' not in text, f.name


def test_the_test_counts_are_what_pytest_collects():
    total = collected()
    assert total == FACTS["tests"] + FACTS["skipped"], (total, FACTS)
    assert collected("tests/security") == FACTS["security_tests"]


def test_the_update_script_reads_and_writes_the_same_three_places():
    script = (ROOT / "scripts" / "update_facts.py").read_text(encoding="utf-8")
    assert "app" in script and "facts.json" in script and "README" in script and "--check" in script
