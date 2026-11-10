"""The seed has no built-in admin password: it comes from ADMIN_PASSWORD or is generated and shown once."""
import re
from pathlib import Path

from app.extensions import db
from app.models import User
from app.seed import seed_admin

from .conftest import login

ROOT = Path(__file__).resolve().parent.parent
OLD_DEFAULT = "admin" + "12345"          # joined so this file does not contain the old password itself


def admins():
    return db.session.scalars(db.select(User).where(User.role == "admin")).all()


def test_without_admin_password_a_random_one_is_generated(app, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    email, generated = seed_admin()
    assert email == "admin@projectstore.local"
    assert generated and len(generated) >= 12 and generated != OLD_DEFAULT
    (admin,) = admins()
    assert admin.check_password(generated)
    assert not admin.check_password(OLD_DEFAULT)
    assert generated not in admin.password_hash           # only a hash is stored


def test_generated_passwords_differ_between_runs(app, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    first = seed_admin()[1]
    db.session.delete(admins()[0])
    db.session.commit()
    assert seed_admin()[1] != first


def test_admin_password_from_the_environment_is_used_and_not_echoed(app, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "chosen-by-the-owner")
    monkeypatch.setenv("ADMIN_EMAIL", "Owner@Example.com")
    email, generated = seed_admin()
    assert email == "owner@example.com" and generated is None
    assert admins()[0].check_password("chosen-by-the-owner")


def test_an_empty_admin_password_counts_as_not_set(app, monkeypatch):
    """docker-compose passes ADMIN_PASSWORD as an empty string when .env leaves it blank."""
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    assert seed_admin()[1]


def test_nothing_happens_if_an_admin_already_exists(app, admin, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert seed_admin() is None
    assert [a.email for a in admins()] == ["boss@example.com"]


def test_seed_command_prints_the_generated_password_once_and_it_works(app, client, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    runner = app.test_cli_runner()
    first = runner.invoke(args=["seed"])
    assert first.exit_code == 0 and "Admin account created: admin@projectstore.local" in first.output
    shown = re.findall(r"Generated admin password[^:]*: (\S+)", first.output)
    assert len(shown) == 1
    assert login(client, "admin@projectstore.local", shown[0]).status_code == 302
    assert client.get("/admin", follow_redirects=False).status_code == 200

    again = runner.invoke(args=["seed"])
    assert again.exit_code == 0
    assert "Generated admin password" not in again.output and shown[0] not in again.output


def test_seed_command_says_when_the_password_came_from_the_environment(app, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "chosen-by-the-owner")
    out = app.test_cli_runner().invoke(args=["seed"]).output
    assert "ADMIN_PASSWORD you set" in out and "chosen-by-the-owner" not in out


def test_the_old_built_in_password_appears_nowhere_in_the_project():
    places = [ROOT / "app", ROOT / "docs", ROOT / "tests", ROOT / "README.md", ROOT / "CLAUDE.md",
              ROOT / "docker-compose.yml", ROOT / ".env.example", ROOT / "docker-entrypoint.sh", ROOT / ".github"]
    hits = []
    for place in places:
        for f in ([place] if place.is_file() else place.rglob("*")):
            if f.is_file() and f.suffix not in {".pyc", ".woff2"} and OLD_DEFAULT in f.read_text("utf-8", "ignore"):
                hits.append(str(f.relative_to(ROOT)))
    assert hits == []
