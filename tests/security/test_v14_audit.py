"""Security audit, v1.4 re-check: the gaps the earlier audit files did not pin down, including v1.3's new surface
(contact form, /i/<token>, /g/<token>, /orders/<id>/invoice, /stop, the outbox) and v1.4's pages and map.
Each test names the docs/SECURITY_AUDIT.md item it proves."""
import re
from pathlib import Path

import pytest

from app.extensions import db
from app.models import ContactMessage, Message, Order
from app.services import notify
from ..conftest import force_login, login, make_user
from .helpers import start_order

ROOT = Path(__file__).resolve().parents[2]

# Every route a signed-out visitor may use. Anything not listed here must send them to sign in (302 to /login),
# answer 401 (API) or 404 (a signed link or token that does not verify).
PUBLIC = {
    "/", "/catalogue", "/p/<slug>", "/healthz", "/login", "/register", "/contact", "/static/<path:filename>",
    "/about", "/faq", "/privacy", "/terms", "/refunds", "/delivery", "/cookies", "/accessibility",
    "/robots.txt", "/sitemap.xml", "/.well-known/security.txt", "/favicon.svg", "/favicon.ico", "/manifest.webmanifest",
    "/api/v1/products", "/api/v1/products/<slug>", "/webhooks/razorpay",
    "/i/<token>", "/g/<token>", "/stop/<token>",        # signed, expiring tokens: open without signing in by design
    "/cart",                                              # redirects a signed-out visitor to sign in (checked below)
}
FILL = {"<slug>": "advanced-rag-knowledge-assistant", "<int:product_id>": "1", "<int:message_id>": "1",
        "<public_id>": "PS-AAAAAAA", "<token>": "not-a-token", "<path:filename>": "css/main.css"}


def _path(rule):
    for k, v in FILL.items():
        rule = rule.replace(k, v)
    return rule


def _rules(app):
    return [(r.rule, _path(r.rule), sorted(r.methods - {"HEAD", "OPTIONS"})) for r in app.url_map.iter_rules()]


def test_e4_route_walk_every_route_outside_the_public_list_needs_sign_in(app):
    """Item 4: walk the whole url_map. A signed-out visitor gets nothing from any non-public route, for any method."""
    rules = _rules(app)
    assert len(rules) >= 60, len(rules)
    unknown = [r for r, _, _ in rules if r not in PUBLIC and not r.startswith(("/admin", "/api/v1", "/checkout", "/orders", "/logout"))]
    assert not unknown, f"routes that are neither public nor under a protected prefix: {unknown}"
    c, leaks = app.test_client(), []
    for rule, path, methods in rules:
        if rule in PUBLIC:
            continue
        for m in methods:
            r = getattr(c, m.lower())(path, **({} if m == "GET" else {"json": {}}))
            ok = r.status_code in (401, 404, 405) or (r.status_code == 302 and "/login" in r.headers.get("Location", ""))
            if not ok:
                leaks.append((m, rule, r.status_code))
    assert not leaks, leaks


def test_e4_route_walk_every_admin_route_refuses_a_customer(app, buyer):
    bad = []
    for rule, path, methods in _rules(app):
        if not rule.startswith(("/admin", "/api/v1/admin")):
            continue
        for m in methods:
            r = getattr(buyer, m.lower())(path, **({} if m == "GET" else {"json": {}}))
            if r.status_code not in (403, 404):
                bad.append((m, rule, r.status_code))
    assert not bad, bad


def test_e4_state_changing_admin_actions_are_post_only_and_need_csrf(csrf_app):
    admin = make_user("boss@example.com", role="admin", name="Boss")
    c = csrf_app.test_client()
    force_login(c, admin)
    posts = [r.rule for r in csrf_app.url_map.iter_rules() if r.rule.startswith("/admin") and "POST" in r.methods]
    assert len(posts) >= 7
    for rule in posts:
        r = c.post(_path(rule), data={})
        assert r.status_code == 400, (rule, r.status_code)                  # CSRF token missing
    for r in csrf_app.url_map.iter_rules():
        if r.rule.startswith("/admin") and r.methods & {"PUT", "PATCH", "DELETE"}:
            pytest.fail(f"{r.rule} changes state without a form POST")


def test_e4_the_public_list_matches_what_signed_out_visitors_really_get(app, rag):
    c = app.test_client()
    for rule in PUBLIC - {"/webhooks/razorpay", "/i/<token>", "/g/<token>", "/stop/<token>", "/cart", "/favicon.ico"}:
        assert c.get(_path(rule)).status_code == 200, rule
    assert c.get("/cart").status_code == 302 and "/login" in c.get("/cart").headers["Location"]
    for rule in ("/i/<token>", "/g/<token>", "/stop/<token>"):
        assert c.get(_path(rule)).status_code == 404, rule                   # a token that does not verify


# ---- item 8: user A cannot see user B's things --------------------------------------------------------------------------

@pytest.fixture()
def paid_victim(app, rag):
    make_user("victim@example.com", name="Victim Person")
    v = app.test_client()
    login(v, "victim@example.com")
    order = start_order(v, rag)
    v.post(f"/checkout/test-pay/{order['id']}", data={"outcome": "pay"})
    o = db.session.scalar(db.select(Order).where(Order.public_id == order["id"]))
    return {"client": v, "order": o}


def test_e8_another_user_cannot_open_an_invoice_or_order_or_its_download(buyer, paid_victim):
    pid = paid_victim["order"].public_id
    assert buyer.get(f"/orders/{pid}/invoice").status_code == 404
    assert buyer.get(f"/orders/{pid}").status_code == 404
    assert buyer.get(f"/api/v1/orders/{pid}").status_code == 404
    assert pid not in buyer.get("/orders").get_data(as_text=True)
    assert paid_victim["client"].get(f"/orders/{pid}/invoice").status_code == 200     # the owner can


def test_e8_signed_links_are_scoped_to_one_order_and_one_document(app, paid_victim):
    o = paid_victim["order"]
    with app.test_request_context():
        inv, guide = notify.make_token("invoice", o.id, o.public_id), notify.make_token("guide", o.id, o.public_id)
    c = app.test_client()
    assert c.get(f"/i/{inv}").status_code == 200 and c.get(f"/g/{guide}").status_code == 200
    assert c.get(f"/i/{guide}").status_code == 404 and c.get(f"/g/{inv}").status_code == 404      # a guide token is not an invoice token
    tampered = inv[:-3] + ("AAA" if not inv.endswith("AAA") else "BBB")
    assert c.get(f"/i/{tampered}").status_code == 404
    with app.test_request_context():
        other = notify.make_token("invoice", o.id + 999, o.public_id)
        wrong_pid = notify.make_token("invoice", o.id, "PS-ZZZZZZZ")
    assert c.get(f"/i/{other}").status_code == 404                                            # no such order
    assert c.get(f"/i/{wrong_pid}").status_code == 404                                        # the order number must match too


def test_e8_expired_links_are_refused(app, paid_victim, monkeypatch):
    o = paid_victim["order"]
    with app.test_request_context():
        inv = notify.make_token("invoice", o.id, o.public_id)
    assert app.test_client().get(f"/i/{inv}").status_code == 200
    monkeypatch.setitem(app.config, "MESSAGE_LINK_DAYS", -1)                                    # every token is now too old
    assert app.test_client().get(f"/i/{inv}").status_code == 404


def test_e8_messages_and_the_outbox_are_admin_only(app, buyer, paid_victim):
    db.session.add(ContactMessage(first_name="Eve", email="eve@example.com", subject="s", body="b", consent=True))
    db.session.add(Message(order_id=paid_victim["order"].id, kind="order_paid", channel="email", to_value="v@example.com",
                           to_hash="x" * 64, subject="s", body_text="t", body_html="h"))
    db.session.commit()
    msg = db.session.scalar(db.select(Message))
    for path in ("/admin/messages", f"/admin/outbox/{msg.id}"):
        assert buyer.get(path).status_code in (403, 404), path
        assert app.test_client().get(path).status_code == 302, path


# ---- item 12: XSS payloads through every input that is echoed back -------------------------------------------------------

PAYLOADS = ['<script>alert(1)</script>', '"><img src=x onerror=alert(1)>', "' onmouseover='alert(1)",
            '<svg onload=alert(1)>', 'javascript:alert(1)']


def _clean(html):
    return all(p not in html for p in PAYLOADS[:4]) and "<script>alert" not in html and "onerror=alert" not in html.replace("onerror=alert(1)&gt;", "")


@pytest.mark.parametrize("p", PAYLOADS)
def test_e12_search_and_the_404_page_escape_the_query(client, p):
    for path in (f"/catalogue?q={p}", f"/nope?q={p}"):
        html = client.get(path).get_data(as_text=True)
        assert p not in html or p == "javascript:alert(1)", path
        assert "<script>alert(1)" not in html and "<svg onload" not in html


@pytest.mark.parametrize("p", PAYLOADS)
def test_e12_the_contact_form_escapes_what_it_shows_back_and_what_the_admin_sees(app, client, admin_client, p):
    r = client.post("/contact", data={"first_name": p[:60], "last_name": "x", "email": "bad", "subject": p, "message": p, "consent": "on"})
    html = r.get_data(as_text=True)
    assert r.status_code == 400 and "<script>alert(1)" not in html and "<svg onload" not in html and "<img src=x" not in html
    client.post("/contact", data={"first_name": p[:60], "last_name": "x", "email": "ok@example.com", "subject": p, "message": p, "consent": "on"})
    admin = admin_client.get("/admin/messages").get_data(as_text=True)
    assert "<script>alert(1)" not in admin and "<svg onload" not in admin and "<img src=x" not in admin


@pytest.mark.parametrize("p", PAYLOADS)
def test_e12_names_on_orders_are_escaped_on_the_order_page_invoice_and_admin(app, buyer, admin_client, rag, p):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    oid = buyer.post("/api/v1/checkout", json={"accept_terms": True, "billing_name": p}).get_json()["id"]
    buyer.post(f"/checkout/test-pay/{oid}", data={"outcome": "pay"})
    for c, path in ((buyer, f"/orders/{oid}"), (buyer, f"/orders/{oid}/invoice"), (admin_client, f"/admin/orders/{oid}"), (admin_client, "/admin/orders")):
        html = c.get(path).get_data(as_text=True)
        assert "<script>alert(1)" not in html and "<svg onload" not in html and "<img src=x" not in html, path


def test_e12_a_javascript_url_never_becomes_a_link(app, client):
    app.config.update(CONTACT_GITHUB="javascript:alert(1)", CONTACT_LINKEDIN="data:text/html,x", CONTACT_CITY="Bengaluru")
    html = client.get("/contact").get_data(as_text=True)
    assert 'href="javascript:' not in html and 'href="data:text' not in html


def test_e12_e10_no_template_marks_user_data_safe():
    """Item 10 and 12: autoescape is on and no template uses |safe; the only Markup() calls are the cover helper (it
    escapes everything it is given) and the setup-guide renderer in app/services/guide.py (escapes first, then adds a
    whitelisted markdown subset)."""
    safe = []
    for f in (ROOT / "app" / "templates").rglob("*.html"):
        for m in re.finditer(r"\|\s*safe\b|autoescape\s+false", f.read_text(encoding="utf-8")):
            safe.append(f.name)
    assert safe == [], safe
    py = {f.relative_to(ROOT).as_posix() for f in (ROOT / "app").rglob("*.py") if re.search(r"\bMarkup\(", f.read_text(encoding="utf-8"))}
    assert py == {"app/__init__.py", "app/services/guide.py"}, py


# ---- item 14: rate limits on the v1.3 token routes and the API ------------------------------------------------------------

def test_e14_signed_links_and_the_stop_page_are_rate_limited(app):
    app.config["RATE_LIMITS"] = dict(app.config["RATE_LIMITS"], links=(3, 600))
    c = app.test_client()
    codes = [c.get(p).status_code for p in ("/i/x", "/g/x", "/stop/x", "/i/y")]
    assert codes[:3] == [404, 404, 404] and codes[3] == 429
    assert c.post("/stop/x").status_code == 429


def test_e14_api_writes_are_rate_limited_per_account(app, buyer, rag):
    app.config["RATE_LIMITS"] = dict(app.config["RATE_LIMITS"], api_write=(3, 600))
    codes = [buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1}).status_code for _ in range(4)]
    assert codes[:3] == [201, 201, 201] and codes[3] == 429
    assert buyer.get("/api/v1/cart").status_code == 200                       # reads are not counted


# ---- item 13: no weak hashes; secrets compared in constant time -----------------------------------------------------------

def test_e13_no_md5_or_sha1_and_secrets_are_compared_in_constant_time():
    src = {f: f.read_text(encoding="utf-8") for f in (ROOT / "app").rglob("*.py")}
    for f, text in src.items():
        assert not re.search(r"hashlib\.(md5|sha1)\b|\bmd5\(|\bsha1\(", text), f
    joined = "".join(src.values())
    assert joined.count("hmac.compare_digest") >= 2                           # payment signature and webhook
    assert not re.search(r"signature\s*==|== *signature|digest\(\)\s*==", joined)


def test_e13_the_do_not_contact_list_and_message_limits_hold_only_keyed_hashes(app):
    h = notify.contact_hash("someone@example.com")
    assert re.fullmatch(r"[0-9a-f]{64}", h) and "someone" not in h
    assert h != notify.contact_hash("someone@example.org")


# ---- item 6: authentication details not covered elsewhere ------------------------------------------------------------------

def test_e6_changing_the_password_ends_other_sessions(app, user):
    other = app.test_client()
    login(other, user.email)
    assert other.get("/orders").status_code == 200
    user.set_password("a-brand-new-password")                                 # end_sessions=True by default
    db.session.commit()
    assert other.get("/orders").status_code == 302


def test_e6_the_contact_form_reveals_nothing_about_accounts(client, user):
    a = client.post("/contact", data={"first_name": "A", "email": user.email, "subject": "s", "message": "m", "consent": "on"})
    b = client.post("/contact", data={"first_name": "A", "email": "nobody@example.com", "subject": "s", "message": "m", "consent": "on"})
    assert a.status_code == b.status_code == 302 and a.headers["Location"] == b.headers["Location"]


# ---- item 2: the app refuses to start for real with unsafe settings ----------------------------------------------------------

from app import config_problems, create_app  # noqa: E402
from app.config import TestConfig  # noqa: E402

GOOD = {"SECRET_KEY": "9f2c" * 16, "SQLALCHEMY_DATABASE_URI": "mysql+pymysql://store_app:Xk29-qPz-long@db:3306/project_store",
        "RAZORPAY_KEY_ID": "", "RAZORPAY_KEY_SECRET": "", "RAZORPAY_WEBHOOK_SECRET": ""}


def test_e2_a_good_production_configuration_has_no_problems():
    assert config_problems(GOOD) == []
    assert config_problems({**GOOD, "RAZORPAY_KEY_ID": "rzp_live_AbC123", "RAZORPAY_KEY_SECRET": "s3cr3t-value-from-razorpay"}) == []


@pytest.mark.parametrize("change,needle", [
    ({"SQLALCHEMY_DATABASE_URI": "mysql+pymysql://store:@db:3306/project_store"}, "database password"),
    ({"SQLALCHEMY_DATABASE_URI": "mysql+pymysql://store:store@db:3306/project_store"}, "database password"),
    ({"SQLALCHEMY_DATABASE_URI": "mysql+pymysql://store:your-db-password@localhost/project_store"}, "database password"),
    ({"RAZORPAY_KEY_ID": "rzp_test_abc"}, "both RAZORPAY_KEY_ID"),
    ({"RAZORPAY_KEY_SECRET": "only-the-secret"}, "both RAZORPAY_KEY_ID"),
    ({"RAZORPAY_KEY_ID": "rzp_test_abc", "RAZORPAY_KEY_SECRET": "change-me"}, "RAZORPAY_KEY_SECRET is a placeholder"),
    ({"RAZORPAY_WEBHOOK_SECRET": "your-secret-here"}, "RAZORPAY_WEBHOOK_SECRET is a placeholder"),
    ({"RAZORPAY_KEY_ID": "not-a-key", "RAZORPAY_KEY_SECRET": "real-looking-secret"}, "does not look like a Razorpay key"),
    ({"SECRET_KEY": "dev-only-change-me"}, "SECRET_KEY"),
])
def test_e2_unsafe_settings_are_named_without_printing_their_values(change, needle):
    problems = config_problems({**GOOD, **change})
    assert any(needle in p for p in problems), problems
    secret_values = [v for k, v in change.items() if k != "SQLALCHEMY_DATABASE_URI" and v]
    assert not [v for v in secret_values if any(v in p for p in problems)], problems


def test_e2_create_app_refuses_to_start_in_production_with_a_placeholder_db_password(monkeypatch):
    cfg = type("C", (TestConfig,), {"TESTING": False, "SECRET_KEY": "9f2c" * 16,
                                    "SQLALCHEMY_DATABASE_URI": "mysql+pymysql://store:store@db:3306/project_store"})
    with pytest.raises(RuntimeError, match="database password"):
        create_app(cfg)


def test_e2_every_setting_the_app_reads_is_listed_in_env_example():
    names = set(re.findall(r'os\.getenv\("([A-Z_]+)"', (ROOT / "app" / "config.py").read_text(encoding="utf-8")))
    names |= set(re.findall(r'os\.getenv\("([A-Z_]+)"', (ROOT / "app" / "seed.py").read_text(encoding="utf-8")))
    example = {l.split("=", 1)[0] for l in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#")}
    missing = names - example - {"TEST_DATABASE_URL"}                    # test-only, documented in the README
    assert not missing, missing
