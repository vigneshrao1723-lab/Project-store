"""Security audit A1: inline styles."""

import re

from .helpers import APP_DIR, ROOT


def test_a1_templates_have_no_inline_styles_so_unsafe_inline_can_be_removed():
    offenders = {}
    for f in (APP_DIR / "templates").rglob("*.html"):
        text = f.read_text(encoding="utf-8")
        n = len(re.findall(r'\sstyle\s*=\s*"', text)) + len(re.findall(r"<style[\s>]", text))
        if n:
            offenders[str(f.relative_to(ROOT))] = n
    assert not offenders, f"{sum(offenders.values())} inline styles in {len(offenders)} templates: {offenders}"
