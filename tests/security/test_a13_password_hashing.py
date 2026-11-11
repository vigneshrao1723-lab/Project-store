"""Security audit A13: password hashing."""

from ..conftest import make_user


def _scrypt_params(h):
    method, _, _ = h.partition("$")
    _, n, r, p = method.split(":")
    return int(n), int(r), int(p)


def test_a13_password_hash_is_salted_scrypt_and_not_reversible(app):
    u = make_user("hash@example.com", password="Sup3r-secret-pw")
    assert u.password_hash.startswith("scrypt:")
    assert "Sup3r-secret-pw" not in u.password_hash
    assert make_user("hash2@example.com", password="Sup3r-secret-pw").password_hash != u.password_hash
    columns = [str(v) for v in (u.name, u.email, u.role)]
    assert not any("Sup3r-secret-pw" in c for c in columns)


def test_a13_scrypt_cost_meets_owasp_minimum(app):
    """OWASP: N=2**17,r=8,p=1 or an equivalent trade (2**16/2, 2**15/3, 2**14/5, 2**13/10)."""
    u = make_user("cost@example.com")
    n, r, p = _scrypt_params(u.password_hash)
    assert r >= 8 and n * p >= 2 ** 17, f"scrypt N={n} r={r} p={p} is below the OWASP minimum (N*p >= 2**17)"


def test_a13_passwords_are_not_written_to_logs(client, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    client.post("/register", data={"name": "Logger", "email": "log@example.com", "password": "never-log-this-1"})
    client.post("/login", data={"email": "log@example.com", "password": "never-log-this-2"})
    assert "never-log-this" not in caplog.text
