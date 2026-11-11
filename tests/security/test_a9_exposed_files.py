"""Security audit A9: exposed files."""

import pytest

from .helpers import APP_DIR, _docker_ignored, read


NOT_SERVED = [
    "/.env", "/.git/config", "/.git/HEAD", "/app/seed.py", "/app/config.py", "/requirements.txt", "/requirements-dev.txt",
    "/docker-compose.yml", "/Dockerfile", "/docker-entrypoint.sh", "/migrations/env.py", "/migrations/alembic.ini",
    "/migrations/versions/0001_initial_schema.py", "/instance/store.db", "/wsgi.py", "/README.md", "/CLAUDE.md",
    "/tests/conftest.py", "/app/__pycache__/seed.cpython-312.pyc", "/static/js/app.js.map", "/static/css/main.css.map",
    "/static/../app/seed.py", "/static/%2e%2e/app/seed.py", "/static/..%2fapp%2fseed.py", "/static/..\\app\\seed.py",
    "/static/", "/static", "/static/js/",
]


DEV_FILES = [".git/config", ".env", ".env.local", ".venv/pyvenv.cfg", "venv/pyvenv.cfg", "tests/conftest.py",
             "instance/store.db", "local.db", ".vscode/settings.json", "htmlcov/index.html", ".coverage",
             "__pycache__/x.pyc", "app/__pycache__/x.cpython-312.pyc", "migrations/__pycache__/env.cpython-312.pyc",
             "app/services/__pycache__/orders.cpython-312.pyc", "app/static/js/app.js.map",
             ".pytest_cache/README.md", "docs/ARCHITECTURE.md"]


@pytest.mark.parametrize("path", NOT_SERVED)
def test_a9_sensitive_and_source_files_are_not_served(client, path):
    r = client.get(path)
    assert r.status_code in (301, 308, 400, 403, 404), f"{path} -> {r.status_code}"
    body = r.get_data(as_text=True)
    assert "SECRET_KEY" not in body and "create_app" not in body and "[core]" not in body


def test_a9_static_folder_holds_only_public_asset_types():
    allowed = {".css", ".js", ".woff2", ".txt"}
    odd = [str(f.relative_to(APP_DIR)) for f in (APP_DIR / "static").rglob("*") if f.is_file() and f.suffix not in allowed]
    assert not odd, f"unexpected files under static/: {odd}"


def test_a9_only_the_static_folder_is_exposed_as_static(app):
    statics = [r.rule for r in app.url_map.iter_rules() if r.endpoint.endswith("static")]
    assert statics == ["/static/<path:filename>"], statics


def test_a9_docker_build_context_excludes_development_files():
    """Evidence from the built image: 27 .pyc files (compiled by the host's Python 3.14) and a .vscode folder
    were copied in, because '*.pyc' and '__pycache__' in .dockerignore only match at the context root."""
    patterns = [l.strip() for l in read(".dockerignore").splitlines() if l.strip() and not l.startswith("#")]
    leaks = [p for p in DEV_FILES if not _docker_ignored(patterns, p)]
    assert not leaks, f".dockerignore would copy these into the image: {leaks}"
