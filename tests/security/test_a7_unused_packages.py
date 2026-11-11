"""Security audit A7: unused packages."""

import ast
from importlib import metadata
import sys

from .helpers import APP_DIR, ROOT, _versions, read


def _third_party_imports():
    stdlib = set(sys.stdlib_module_names)
    mods = set()
    for f in list(APP_DIR.rglob("*.py")) + [ROOT / "wsgi.py"]:
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                mods.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods.add(node.module.split(".")[0])
    return {m for m in mods if m not in stdlib and m != "app"}


def test_a7_every_third_party_module_the_app_imports_is_declared_in_requirements():
    declared = set(_versions(read("requirements.txt")))
    dist_of = metadata.packages_distributions()
    undeclared = {}
    for mod in sorted(_third_party_imports()):
        dists = {d.lower().replace("_", "-") for d in dist_of.get(mod, [mod])}
        if not dists & declared:
            undeclared[mod] = sorted(dists)
    assert not undeclared, f"imported but only present as a transitive dependency: {undeclared}"
