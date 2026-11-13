"""Measure the project's own figures and write them to the one place that holds them.

    python scripts/update_facts.py            run the suite with coverage, write app/facts.json, patch the README table
    python scripts/update_facts.py --check    run it and fail if app/facts.json or the README disagrees with the run

The home page reads app/facts.json. tests/test_fx_facts.py keeps the file, the README and the home page equal, and
keeps the test counts equal to what pytest collects. Coverage cannot be checked inside a normal test run (it needs
the coverage plugin and the whole suite), so this script is where that figure is measured."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACTS = ROOT / "app" / "facts.json"
README = ROOT / "README.md"


def run(*args):
    return subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args], cwd=ROOT, capture_output=True, text=True).stdout


def measure():
    full = run("--cov=app", "--cov-report=term", "-q")
    summary = re.search(r"(\d+) passed(?:, (\d+) skipped)?", full)
    total = re.search(r"^TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%", full, re.M)
    if not summary or not total:
        sys.exit("could not read the pytest summary:\n" + full[-1500:])
    security = re.search(r"(\d+) tests? collected", run("tests/security", "--collect-only", "-q"))
    return {"tests": int(summary.group(1)), "skipped": int(summary.group(2) or 0), "security_tests": int(security.group(1)),
            "coverage": int(total.group(3)), "statements": int(total.group(1)), "missed": int(total.group(2))}


def patch_readme(f):
    text = README.read_text(encoding="utf-8")
    text = re.sub(r"\| [\d,]+ tests pass on SQLite, \d+ skip", "| {:,} tests pass on SQLite, {} skip".format(f["tests"], f["skipped"]), text, count=1)
    text = re.sub(r"Line coverage of `app/` is \d+% \([\d,]+ statements, \d+ missed\)", "Line coverage of `app/` is {}% ({:,} statements, {} missed)".format(f["coverage"], f["statements"], f["missed"]), text, count=1)
    text = re.sub(r"\| \d+ of those tests are the security suite", "| {} of those tests are the security suite".format(f["security_tests"]), text, count=1)
    README.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    facts = measure()
    if "--check" in sys.argv:
        current = json.loads(FACTS.read_text(encoding="utf-8"))
        if current != facts:
            sys.exit("app/facts.json is stale.\n  recorded: %s\n  measured: %s\nRun: python scripts/update_facts.py" % (current, facts))
        print("facts are current:", facts)
    else:
        FACTS.write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8", newline="\n")
        patch_readme(facts)
        print("wrote", facts)
