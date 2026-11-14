"""Check the palette's colour contrast from the tokens themselves.

    python scripts/check_contrast.py          print every pair and exit 1 if any is below its limit

Rules (WCAG 2.x relative luminance):
  * text needs 4.5:1 (normal) and the pairs the design relies on are listed in REQUIRED below;
  * graphics and large text need 3:1 (GRAPHICS);
  * every `color` / `background` pair that appears together in one rule of the stylesheets must pass 4.5:1, and a rule that
    sets a text colour with no background of its own must pass on all three surfaces (night, panel, panel-2);
  * violet and harley are fills (white text on them), never text colours.
tests/test_palette.py runs the same functions, so a violation fails the suite."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS_DIR = ROOT / "app" / "static" / "css"
SURFACES = ("night", "panel", "panel-2")
# (text token, background token): normal text, 4.5:1
REQUIRED = [("white", "harley"), ("white", "violet"), ("ink", "sunset"), ("ink", "amber"),
            ("white", "night"), ("white", "panel"), ("white", "panel-2"), ("muted", "night"), ("muted", "panel"), ("muted", "panel-2"),
            ("amber", "night"), ("amber", "panel"), ("amber", "panel-2"), ("sunset", "night"), ("sunset", "panel"), ("sunset", "panel-2")]
# (graphic token, background token): borders, icons, big shapes, 3:1
GRAPHICS = [("muted", "night"), ("muted", "panel"), ("amber", "night"), ("amber", "panel"), ("sunset", "night"), ("sunset", "panel"),
            ("violet", "night"), ("harley", "night"), ("harley", "panel"), ("white", "violet"), ("white", "harley")]
NEVER_TEXT = {"violet", "harley"}      # fills only
FILL_ONLY_TEXT_OK_ON = {"violet": {"white"}, "harley": {"white"}}


def tokens():
    css = (CSS_DIR / "tokens.css").read_text(encoding="utf-8")
    return {k: v.upper() for k, v in re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", css)}


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def ratio(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def rule_pairs():
    """(selector, text token, background token or None) for every rule that sets a plain `color:` from a token"""
    out = []
    for f in sorted(CSS_DIR.glob("*.css")):
        if f.name == "tokens.css":
            continue
        css = re.sub(r"/\*.*?\*/", "", f.read_text(encoding="utf-8"), flags=re.S)
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            m = re.search(r"(?<![\w-])color:\s*var\(--([a-z0-9-]+)\)", body)
            if not m:
                continue
            bg = re.search(r"(?<![\w-])background(?:-color)?:\s*var\(--([a-z0-9-]+)\)", body)
            out.append((" ".join(sel.split())[:90], m.group(1), bg.group(1) if bg else None, f.name))
    return out


def check():
    tok = tokens()
    rows, bad = [], []
    for fg, bg in REQUIRED:
        r = ratio(tok[fg], tok[bg])
        rows.append((f"text {fg} on {bg}", r, 4.5))
    for fg, bg in GRAPHICS:
        rows.append((f"graphic {fg} on {bg}", ratio(tok[fg], tok[bg]), 3.0))
    for sel, fg, bg, fname in rule_pairs():
        if fg not in tok:
            continue                                   # currentColor, inherit and the like
        if fg in NEVER_TEXT:
            bad.append((f"{fname}: {sel}: {fg} used as a text colour (fills only)", 0, 4.5))
            continue
        backs = [bg] if bg in tok else list(SURFACES)
        for b in backs:
            rows.append((f"{fname}: {sel}: {fg} on {b}", ratio(tok[fg], tok[b]), 4.5))
    bad += [r for r in rows if r[1] < r[2]]
    return rows, bad


def main():
    rows, bad = check()
    for name, r, need in sorted(rows, key=lambda x: x[1]):
        print(f"{'FAIL' if r < need else 'ok  '}  {r:5.2f}  (needs {need})  {name}")
    print(f"\n{len(rows)} pairs checked, {len(bad)} below their limit")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
