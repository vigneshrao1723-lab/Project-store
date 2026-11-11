"""Security audit A4: admin routes."""

import re


ADMIN_PREFIXES = ("/admin", "/api/v1/admin")


VERBS = ("get", "head", "post", "put", "patch", "delete")


def _admin_rules(application):
    out = []
    for rule in application.url_map.iter_rules():
        if rule.rule.startswith(ADMIN_PREFIXES):
            path = re.sub(r"<int:\w+>", "1", rule.rule)
            path = re.sub(r"<\w+>", "PS-AAAAAAA", path)
            out.append((rule.rule, path, rule.methods - {"HEAD", "OPTIONS"}))
    return out


def _allowed(resp, who):
    if resp.status_code in (401, 403, 405):
        return True
    return who == "anonymous" and resp.status_code == 302 and "/login" in resp.headers.get("Location", "")


def test_a4_every_admin_route_rejects_anonymous_and_customers_for_every_method(app, client, buyer):
    rules = _admin_rules(app)
    assert len(rules) >= 12, f"only found {len(rules)} admin routes; the url_map walk is broken"
    anonymous = app.test_client()
    bad = []
    declared_but_405 = []
    for rule, path, declared in rules:
        for who, c in (("anonymous", anonymous), ("customer", buyer)):
            for verb in VERBS:
                r = getattr(c, verb)(path, **({} if verb in ("get", "head") else {"json": {}}))
                if not _allowed(r, who):
                    bad.append((who, verb.upper(), rule, r.status_code))
                if verb.upper() in declared and r.status_code == 405:
                    declared_but_405.append((rule, verb))
    assert not bad, f"admin routes reachable without admin rights: {bad}"
    assert not declared_but_405, f"declared methods answered 405, so auth was never exercised: {declared_but_405}"


def test_a4_admin_can_still_reach_admin_routes(admin_client):
    assert admin_client.get("/admin").status_code == 200
    assert admin_client.get("/api/v1/admin/stats").status_code == 200
