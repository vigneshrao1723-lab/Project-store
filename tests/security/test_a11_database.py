"""Security audit A11: database."""

import ast
import re

import pytest

from .helpers import APP_DIR, ROOT, read


def _compose_service(name):
    text = read("docker-compose.yml")
    m = re.search(rf"^  {name}:\n((?:    .*\n|\n)+)", text, re.M)
    assert m, f"service {name} not found"
    return m.group(1)


def test_a11_the_app_does_not_connect_as_mysql_root():
    web = _compose_service("web")
    url = re.search(r"DATABASE_URL: (\S+)", web).group(1)
    assert "root" not in url.split("@")[0]
    assert "root" not in re.search(r"DATABASE_URL: (\S+)", _compose_service("sweeper")).group(1).split("@")[0]


def test_a11_mysql_port_is_not_published_to_the_host():
    assert not re.search(r"^\s+ports:", _compose_service("db"), re.M), "the db service publishes a port"


def test_a11_database_passwords_come_from_env_with_no_weak_defaults():
    compose = read("docker-compose.yml")
    weak = re.findall(r"\$\{(DB_PASSWORD|DB_ROOT_PASSWORD):-([^}]*)\}", compose)
    assert not weak, f"compose falls back to guessable database passwords: {weak}"


def test_a11_healthcheck_does_not_put_the_root_password_on_a_command_line():
    hc = re.search(r"healthcheck:\n\s+test: (\[.*\])", _compose_service("db")).group(1)
    assert not re.search(r"-p\S", hc), f"root password is part of the healthcheck command: {hc}"


def test_a11_no_sql_is_built_from_strings():
    offenders = []
    for f in APP_DIR.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                if name in {"text", "execute", "exec_driver_sql"} and node.args:
                    a = node.args[0]
                    dynamic = isinstance(a, (ast.JoinedStr, ast.BinOp)) or (
                        isinstance(a, ast.Call) and getattr(a.func, "attr", "") == "format")
                    if dynamic:
                        offenders.append(f"{f.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, offenders


@pytest.mark.parametrize("payload", ["' OR 1=1 --", "%' OR '1'='1", "'; DROP TABLE products; --", "\\", "%_%", "\x00"])
def test_a11_a17_search_sort_and_category_resist_sql_injection(client, payload):
    total = client.get("/api/v1/products").get_json()["total"]
    for params in ({"q": payload}, {"sort": payload}, {"category": payload}):
        r = client.get("/api/v1/products", query_string=params)
        assert r.status_code == 200
        if "q" not in params and "category" not in params:
            assert r.get_json()["total"] == total
        if "category" in params:
            assert r.get_json()["total"] == 0, "category filter matched rows for a hostile value"
    assert client.get("/api/v1/products").get_json()["total"] == total
