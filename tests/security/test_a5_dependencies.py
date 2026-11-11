"""Security audit A5: dependencies."""

import re

from .helpers import ROOT, _versions, read


def _vkey(v):
    from packaging.version import Version
    return Version(v)


FIXED_RUNTIME = {"flask": "3.1.3", "cryptography": "49.0.0", "requests": "2.33.0", "python-dotenv": "1.2.2"}


FIXED_DEV = {"pytest": "9.0.3"}


def test_a5_runtime_dependencies_are_at_or_above_their_fixed_versions():
    have = _versions(read("requirements.txt"))
    behind = {k: f"{have.get(k)} < {v}" for k, v in FIXED_RUNTIME.items() if _vkey(have.get(k, "0")) < _vkey(v)}
    assert not behind, f"known-vulnerable pins: {behind}"


def test_a5_dev_dependencies_are_at_or_above_their_fixed_versions():
    have = _versions(read("requirements-dev.txt"))
    behind = {k: f"{have.get(k)} < {v}" for k, v in FIXED_DEV.items() if _vkey(have.get(k, "0")) < _vkey(v)}
    assert not behind, f"known-vulnerable pins: {behind}"


def test_a5_every_direct_requirement_is_pinned_exactly():
    for name in ("requirements.txt", "requirements-dev.txt"):
        for line in read(name).splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-r")):
                assert re.match(r"^[A-Za-z0-9_.\[\]-]+==\d", line), f"{name}: {line!r} is not pinned with =="


def test_a5_transitive_dependencies_are_locked_with_hashes():
    """requirements.txt pins only direct packages; Werkzeug, Jinja2, urllib3, certifi ... float to whatever is
    newest at build time. A lock file with hashes makes builds reproducible and tamper-evident."""
    candidates = [ROOT / "requirements.lock", ROOT / "requirements.txt"]
    assert any("--hash=sha256:" in p.read_text(encoding="utf-8") for p in candidates if p.exists()), \
        "no requirements file contains --hash=sha256 entries"
