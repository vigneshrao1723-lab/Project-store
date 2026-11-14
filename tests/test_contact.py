"""The contact block and form (v1.3): the home page section, /contact, POST /contact with validation, honeypot, rate
limits and storage, and the admin Messages page."""
import re

import pytest
from flask import g

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import ContactMessage
from app.seed import seed_catalogue

from .conftest import make_user
from .fakes import FakeSMTP

GOOD = {"first_name": "Asha", "last_name": "Rao", "email": "asha@example.com", "subject": "A custom build",
        "message": "Can you make a version of the RAG kit for Hindi documents?", "consent": "on"}


def test_home_has_one_timeline_the_contact_block_and_a_slim_footer(client, app):
    home = client.get("/").get_data(as_text=True)
    assert home.count('id="how"') == 1 and home.count("<h3>Choose</h3>") == 1
    assert "Pick a project" not in home and "Pay at checkout" not in home and "Download from your orders" not in home
    tl = home[home.index('class="tl-wrap"'):home.index("</svg>", home.index('class="tl-wrap"'))]
    assert re.findall(r'<span class="tl-n" aria-hidden="true">(\d)</span><h3>', tl) == ["1", "2", "3", "4"]
    assert f"{app.config['RESERVATION_MINUTES']} minutes" in tl
    assert 'id="contact"' in home and "Get in touch" in home and 'name="origin" value="home"' in home
    foot = home[home.index('<footer class="site-footer"'):home.index("</footer>")]
    assert "Bengaluru" not in foot and "The maker" not in foot and "Portfolio" not in foot and "LinkedIn" not in foot
    assert "Catalogue" in foot and "Your orders" in foot and "Cart" in foot and "/contact" in foot and "&copy;" in foot


def test_no_page_carries_the_old_maker_sentence(client):
    for path in ("/", "/catalogue", "/contact", "/login"):
        assert "a computer science student in Bengaluru" not in client.get(path).get_data(as_text=True)


def test_contact_details_come_only_from_the_environment(app, client):
    page = client.get("/contact").get_data(as_text=True)
    assert "Get in touch" in page and "mailto:" not in page and "wa.me" not in page and "tel:" not in page
    assert "Use the form and we will reply" in page
    app.config.update(CONTACT_EMAIL="owner@example.com", CONTACT_PHONE="+91 98765 43210", CONTACT_CITY="Pune",
                      CONTACT_GITHUB="https://github.com/example", CONTACT_LINKEDIN="javascript:alert(1)")
    page = client.get("/contact").get_data(as_text=True)
    assert "mailto:owner@example.com" in page and "https://wa.me/919876543210" in page and "tel:+919876543210" in page
    assert "Pune" in page and "https://github.com/example" in page
    assert "javascript:" not in page                       # a non-http URL in the environment is dropped


def test_no_phone_or_email_is_written_in_the_repository():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "app"
    for f in list(root.rglob("*.html")) + list(root.rglob("*.py")):
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"\+91[\s-]?\d{5}[\s-]?\d{5}", text), f
        assert not re.search(r"wa\.me/\d", text), f


def test_a_good_message_is_stored_and_thanked(client):
    r = client.post("/contact", data=GOOD)
    assert r.status_code == 302 and r.headers["Location"].endswith("/contact")
    m = db.session.scalar(db.select(ContactMessage))
    assert (m.first_name, m.email, m.subject, m.consent) == ("Asha", "asha@example.com", "A custom build", True)
    assert "Thanks, we will reply soon." in client.get("/contact").get_data(as_text=True)


def test_from_the_home_page_it_returns_to_the_home_contact_block(client):
    r = client.post("/contact", data={**GOOD, "origin": "home"})
    assert r.headers["Location"].endswith("/#contact")


@pytest.mark.parametrize("field,value,needle", [
    ("first_name", "", "Enter your first name"), ("email", "not-an-email", "valid email"),
    ("subject", "", "Enter a subject"), ("message", "", "Write your message"),
    ("first_name", "x" * 61, "at most 60"), ("subject", "s" * 161, "at most 160"), ("message", "m" * 5001, "at most 5,000"),
    ("consent", "", "Tick the box"),
])
def test_validation_errors_are_shown_and_nothing_is_stored(client, field, value, needle):
    data = {**GOOD, field: value}
    if field == "consent":
        data.pop("consent")
    r = client.post("/contact", data=data)
    assert r.status_code == 400 and needle in r.get_data(as_text=True)
    assert db.session.scalar(db.select(db.func.count(ContactMessage.id))) == 0


@pytest.mark.parametrize("field", ["first_name", "last_name", "subject", "email"])
def test_line_breaks_in_one_line_fields_are_refused(client, field):
    """CR/LF in a name, subject or email would let a sender add mail headers to the owner's notification."""
    r = client.post("/contact", data={**GOOD, field: "Hello\r\nBcc: victim@example.com"})
    assert r.status_code == 400
    assert db.session.scalar(db.select(db.func.count(ContactMessage.id))) == 0


def test_the_honeypot_pretends_success_and_stores_nothing(client):
    r = client.post("/contact", data={**GOOD, "website": "http://spam.example"})
    assert r.status_code == 302
    assert db.session.scalar(db.select(db.func.count(ContactMessage.id))) == 0


def test_ten_an_hour_per_address(client):
    for i in range(10):
        assert client.post("/contact", data={**GOOD, "email": f"p{i}@example.com"}).status_code == 302
    assert client.post("/contact", data={**GOOD, "email": "p99@example.com"}).status_code == 429


def test_three_an_hour_per_sender_email(client):
    for _ in range(3):
        assert client.post("/contact", data=GOOD).status_code == 302
    assert client.post("/contact", data=GOOD).status_code == 429
    assert db.session.scalar(db.select(db.func.count(ContactMessage.id))) == 3


def test_the_form_needs_a_csrf_token():
    class Csrf(TestConfig):
        WTF_CSRF_ENABLED = True
    app = create_app(Csrf)

    @app.before_request
    def _fresh():
        g.pop("csrf_token", None)

    with app.app_context():
        db.create_all(); seed_catalogue()
        c = app.test_client()
        assert c.post("/contact", data=GOOD).status_code == 400
        token = c.get("/contact").get_data(as_text=True).split('name="csrf_token" value="')[1].split('"')[0]
        assert c.post("/contact", data={**GOOD, "csrf_token": token}).status_code == 302
        db.session.remove(); db.drop_all()


XSS = '<script>alert("x")</script><img src=x onerror=alert(1)>'


@pytest.mark.parametrize("field", ["first_name", "last_name", "subject", "message"])
def test_xss_in_any_field_is_escaped_on_the_admin_page(client, admin_client, field):
    value = XSS if field != "first_name" else "<b>Bad</b>"
    data = {**GOOD, field: value if field == "message" else value[:60]}
    assert client.post("/contact", data=data).status_code == 302
    page = admin_client.get("/admin/messages").get_data(as_text=True)
    assert "<script>alert" not in page and "<img src=x" not in page and "<b>Bad</b>" not in page
    assert "&lt;" in page


def test_admin_messages_need_an_admin(app, buyer):
    assert app.test_client().get("/admin/messages").status_code in (302, 401)       # signed out: to sign in
    assert buyer.get("/admin/messages").status_code == 403
    assert buyer.post("/admin/messages/1/handled").status_code == 403


def test_admin_can_mark_a_message_handled_and_back(client, admin_client):
    client.post("/contact", data=GOOD)
    m = db.session.scalar(db.select(ContactMessage))
    admin_client.post(f"/admin/messages/{m.id}/handled")
    db.session.refresh(m)
    assert m.handled_at is not None
    admin_client.post(f"/admin/messages/{m.id}/handled")
    db.session.refresh(m)
    assert m.handled_at is None


def test_the_owner_gets_an_email_when_smtp_is_configured(app, client):
    smtp = FakeSMTP()
    try:
        app.config.update(SMTP_HOST="127.0.0.1", SMTP_PORT=smtp.port, SMTP_FROM="store@example.com",
                          SMTP_STARTTLS=False, CONTACT_EMAIL="owner@example.com")
        assert client.post("/contact", data=GOOD).status_code == 302
        assert len(smtp.messages) == 1 and smtp.messages[0]["to"] == ["<owner@example.com>"]
        assert "A custom build" in smtp.messages[0]["data"]
    finally:
        smtp.close()


def test_without_smtp_no_email_is_attempted_and_the_message_is_still_stored(app, client, monkeypatch):
    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no SMTP call")))
    assert client.post("/contact", data=GOOD).status_code == 302
    assert db.session.scalar(db.select(db.func.count(ContactMessage.id))) == 1


def test_the_message_content_is_never_logged(app, client, caplog):
    caplog.set_level("DEBUG")
    client.post("/contact", data={**GOOD, "message": "my secret phone 9876543210"})
    assert "9876543210" not in caplog.text and "asha@example.com" not in caplog.text
