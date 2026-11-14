"""Order messages (v1.3): the checkout contact choice, the outbox, the channels, signed invoice and guide links,
do-not-contact, limits, anonymising, and the rule that a message problem can never touch a payment."""
import re
from datetime import timedelta

import pytest

from app.extensions import db
from app.models import ContactOptOut, Message, Order, Product, utcnow
from app.services import notify
from app.services.guide import render_guide
from app.services.privacy import anonymise_order

from .conftest import force_login, make_user
from .fakes import FakeSMTP, FakeWhatsApp


def _checkout(client, product, channel="email", value="buyer@example.com", consent=True, name="Asha Rao"):
    client.post("/api/v1/cart/items", json={"product_id": product.id, "qty": 1})
    data = {"billing_name": name, "contact_channel": channel}
    data["contact_email" if channel == "email" else "contact_whatsapp"] = value
    if consent:
        data["contact_consent"] = "on"
    return client.post("/checkout", data=data)


def _latest_order():
    return db.session.scalar(db.select(Order).order_by(Order.id.desc()))


def _pay(client, order):
    return client.post(f"/checkout/test-pay/{order.public_id}", data={"outcome": "pay"})


def _messages(order=None):
    q = db.select(Message)
    if order is not None:
        q = q.where(Message.order_id == order.id)
    return db.session.scalars(q).all()


@pytest.fixture()
def smtp(app):
    server = FakeSMTP()
    app.config.update(SMTP_HOST="127.0.0.1", SMTP_PORT=server.port, SMTP_FROM="store@example.com", SMTP_STARTTLS=False)
    yield server
    server.close()


@pytest.fixture()
def whatsapp(app):
    server = FakeWhatsApp()
    app.config.update(WHATSAPP_TOKEN="tok_secret_value", WHATSAPP_PHONE_NUMBER_ID="12345",
                      WHATSAPP_TEMPLATE_NAME="order_paid", WHATSAPP_LANG="en",
                      WHATSAPP_API_BASE=f"http://127.0.0.1:{server.port}")
    yield server
    server.close()


# ---- checkout contact choice ---------------------------------------------------------------------------------------
def test_checkout_offers_email_prefilled_or_whatsapp_and_consent_unticked(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    page = buyer.get("/checkout").get_data(as_text=True)
    assert 'name="contact_channel" value="email" checked' in page and 'name="contact_channel" value="whatsapp"' in page
    assert 'name="contact_email" type="email" value="buyer@example.com"' in page
    assert re.search(r'<input type="checkbox" name="contact_consent"\s*>', page)                  # unticked
    assert "Send my invoice and setup guide to this contact" in page
    assert 'name="phone"' not in page                                                            # the free phone field is gone


def test_email_choice_is_stored_with_consent(buyer, rag):
    assert _checkout(buyer, rag, value="Asha@Example.com").status_code == 302
    o = _latest_order()
    assert (o.contact_channel, o.contact_value) == ("email", "asha@example.com") and o.contact_consent_at


@pytest.mark.parametrize("raw,e164", [("98765 45765", "+919876545765"), ("+91 98765-45765", "+919876545765"),
                                      ("09876545765", "+919876545765"), ("+44 7911 123456", "+447911123456")])
def test_whatsapp_numbers_are_normalised_to_e164(buyer, rag, raw, e164):
    assert _checkout(buyer, rag, "whatsapp", raw).status_code == 302
    o = _latest_order()
    assert (o.contact_channel, o.contact_value) == ("whatsapp", e164)


@pytest.mark.parametrize("channel,value,needle", [
    ("whatsapp", "12345", "10-digit mobile number"), ("whatsapp", "+91 12345 67890", "10-digit mobile number"),
    ("whatsapp", "98765\r\n45765", "10-digit"), ("email", "not-an-email", "valid email"),
    ("email", "a@b.co\r\nBcc: x@y.z", "valid email"), ("sms", "x", "Choose email or WhatsApp"),
])
def test_bad_contacts_are_refused_and_no_order_is_made(buyer, rag, channel, value, needle):
    r = _checkout(buyer, rag, channel, value)
    assert r.status_code == 400 and needle in r.get_data(as_text=True)
    assert _latest_order() is None


def test_consent_is_required_when_a_contact_is_given(buyer, rag):
    r = _checkout(buyer, rag, consent=False)
    assert r.status_code == 400 and "Tick the box so we can send your invoice" in r.get_data(as_text=True)
    assert _latest_order() is None


def test_the_chosen_contact_is_masked_on_the_order_page_and_never_shown_raw(buyer, rag):
    _checkout(buyer, rag, "whatsapp", "9876545765")
    o = _latest_order()
    _pay(buyer, o)
    page = buyer.get(f"/orders/{o.public_id}").get_data(as_text=True)
    assert "+91 ******5765" in page and "9876545765" not in page


@pytest.mark.parametrize("channel,value,masked", [("email", "jaya@gmail.com", "j***@gmail.com"),
                                                  ("whatsapp", "+919876545765", "+91 ******5765"),
                                                  ("whatsapp", "+447911123456", "+********3456")])
def test_masking(app, channel, value, masked):
    assert notify.mask(channel, value) == masked


# ---- the outbox ----------------------------------------------------------------------------------------------------
def test_nothing_is_queued_at_checkout_only_after_payment(buyer, rag):
    _checkout(buyer, rag)
    o = _latest_order()
    assert _messages() == []
    _pay(buyer, o)
    assert len(_messages(o)) == 1


def test_without_a_channel_the_message_waits_in_the_outbox_and_the_page_tells_the_truth(buyer, rag):
    _checkout(buyer, rag)
    o = _latest_order()
    _pay(buyer, o)
    [m] = _messages(o)
    assert m.status == "not_configured" and "INVOICE" in m.body_text and m.channel == "email"
    page = buyer.get(f"/orders/{o.public_id}").get_data(as_text=True)
    assert "Not sent: this store has not switched on email or WhatsApp messages yet" in page
    assert "Setup guide" in page and "Open the invoice" in page and "What you need" in page


def test_a_repeated_payment_confirmation_never_sends_twice(app, buyer, rag, smtp):
    _checkout(buyer, rag)
    o = _latest_order()
    _pay(buyer, o)
    _pay(buyer, o)                                            # the redirect again
    from app.services import orders as order_svc
    order_svc.mark_paid(o.id, o.gateway_payment_id)           # and the webhook
    notify.after_payment(o.id)
    notify.after_payment(o.id)
    assert len(_messages(o)) == 1 and len(smtp.messages) == 1


def test_email_is_sent_with_the_note_invoice_guide_download_and_stop_link(buyer, rag, smtp):
    _checkout(buyer, rag, value="jaya@example.com", name="Jaya Iyer")
    o = _latest_order()
    _pay(buyer, o)
    [m] = _messages(o)
    assert m.status == "sent" and m.sent_at and m.attempts == 1
    raw = smtp.messages[0]["data"]
    assert smtp.messages[0]["to"] == ["<jaya@example.com>"]
    assert "Subject: Your order " + o.public_id in raw and "Hi Jaya," in raw and "Thank you for your order" in raw
    assert "Advanced RAG Knowledge Assistant" in raw and "Total paid" in raw and "/i/" in raw and "/g/" in raw
    assert "/stop/" in raw and f"/orders/{o.public_id}" in raw
    assert "your download link will appear on your order page as soon as it is ready" in raw.lower()
    page = buyer.get(f"/orders/{o.public_id}").get_data(as_text=True)
    assert "Sent to j***@example.com" in page


def test_a_send_failure_never_breaks_the_payment_and_is_retried_with_backoff(app, buyer, rag, smtp):
    smtp.refuse_rcpt = True
    _checkout(buyer, rag)
    o = _latest_order()
    r = _pay(buyer, o)
    assert r.status_code == 302
    db.session.refresh(o)
    assert o.status == "paid"
    [m] = _messages(o)
    assert m.status == "failed" and m.attempts == 1 and "refused the recipient" in m.last_error
    assert m.next_attempt_at > utcnow()
    assert "We could not send this yet and will try again" in buyer.get(f"/orders/{o.public_id}").get_data(as_text=True)
    for attempt in range(2, 6):                               # the sweeper, once the back-off has passed
        m.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.session.commit()
        assert notify.sweep() == 1
        db.session.refresh(m)
        assert m.attempts == attempt
    assert m.next_attempt_at is None and notify.sweep() == 0          # five attempts, then it stops
    assert "We could not send this, it is on your order page below" in buyer.get(f"/orders/{o.public_id}").get_data(as_text=True)
    smtp.refuse_rcpt = False


def test_an_unexpected_error_in_a_channel_never_reaches_the_payment(app, buyer, rag, monkeypatch):
    from app.services.notify import channels
    def boom(*a, **k):
        raise RuntimeError("exploded")
    monkeypatch.setattr(channels.EmailChannel, "send", boom)
    monkeypatch.setattr(notify, "deliver", lambda m: (_ for _ in ()).throw(RuntimeError("exploded")))
    _checkout(buyer, rag)
    o = _latest_order()
    assert _pay(buyer, o).status_code == 302
    db.session.refresh(o)
    assert o.status == "paid"


def test_whatsapp_uses_the_approved_template_with_the_links_as_parameters(app, buyer, rag, whatsapp):
    _checkout(buyer, rag, "whatsapp", "9876545765", name="Ravi K")
    o = _latest_order()
    _pay(buyer, o)
    [m] = _messages(o)
    assert m.status == "sent"
    [req] = whatsapp.requests
    assert req["path"] == "/12345/messages" and req["auth"] == "Bearer tok_secret_value"
    body = req["json"]
    assert body["to"] == "919876545765" and body["type"] == "template" and body["template"]["name"] == "order_paid"
    params = [p["text"] for p in body["template"]["components"][0]["parameters"]]
    assert params[0] == "Ravi" and params[1] == o.public_id and "/i/" in params[2] and "/g/" in params[3]
    assert params[4].endswith(f"/orders/{o.public_id}") and "/stop/" in params[5]


def test_a_whatsapp_api_error_is_stored_without_the_token(app, buyer, rag, whatsapp):
    whatsapp.status = 400
    _checkout(buyer, rag, "whatsapp", "9876545765")
    o = _latest_order()
    _pay(buyer, o)
    [m] = _messages(o)
    assert m.status == "failed" and "HTTP 400" in m.last_error and "132001" in m.last_error
    assert "tok_secret_value" not in m.last_error


def test_an_invalid_number_is_refused_before_any_api_call(app, whatsapp):
    from app.services.notify.channels import SendError, WhatsAppChannel
    with pytest.raises(SendError):
        WhatsAppChannel().send("98765", ["x"])
    assert whatsapp.requests == []


# ---- limits, consent, do not contact -------------------------------------------------------------------------------
def test_a_contact_gets_at_most_three_messages_a_day(app, rag, smtp):
    for i in range(4):
        u = make_user(f"b{i}@example.com", name=f"B{i}")
        c = app.test_client()
        force_login(c, u)
        _checkout(c, rag, value="same@example.com")
        _pay(c, _latest_order())
    statuses = [m.status for m in _messages()]
    assert statuses.count("sent") == 3 and statuses[-1] == "failed"
    assert "daily limit" in _messages()[-1].last_error and len(smtp.messages) == 3


def test_checkouts_asking_for_messages_are_limited_per_account(app, buyer, rag):
    for _ in range(5):
        assert _checkout(buyer, rag).status_code == 302
        buyer.post(f"/checkout/cancel/{_latest_order().public_id}")
    assert _checkout(buyer, rag).status_code == 429


def test_without_consent_on_the_order_nothing_is_queued(app, buyer, rag):
    _checkout(buyer, rag)
    o = _latest_order()
    o.contact_consent_at = None
    db.session.commit()
    _pay(buyer, o)
    assert _messages(o) == []


def test_the_stop_link_puts_the_contact_on_the_do_not_contact_list_and_it_is_honoured(app, buyer, rag, smtp):
    _checkout(buyer, rag, value="stop@example.com")
    o = _latest_order()
    _pay(buyer, o)
    [m] = _messages(o)
    token = notify.make_token("stop", m.id)
    page = buyer.get(f"/stop/{token}")
    assert page.status_code == 200 and page.headers["Cache-Control"] == "no-store"
    assert buyer.post(f"/stop/{token}").status_code == 302
    assert db.session.scalar(db.select(ContactOptOut.value_hash)) == notify.contact_hash("stop@example.com")
    assert "stop@example.com" not in str(db.session.scalars(db.select(ContactOptOut)).all()[0].__dict__)
    other = make_user("other@example.com", name="Other")
    c = app.test_client()
    force_login(c, other)
    _checkout(c, rag, value="STOP@example.com")
    o2 = _latest_order()
    _pay(c, o2)
    [m2] = _messages(o2)
    assert m2.status == "failed" and "asked not to be contacted" in m2.last_error and len(smtp.messages) == 1
    assert buyer.get("/stop/not-a-token").status_code == 404


def test_names_with_line_breaks_never_reach_a_mail_header(buyer, rag, smtp):
    _checkout(buyer, rag, value="h@example.com", name="Asha\r\nBcc: victim@example.com")
    _pay(buyer, _latest_order())
    raw = smtp.messages[0]["data"]
    headers = raw.split("\r\n\r\n", 1)[0] if "\r\n\r\n" in raw else raw.split("\n\n", 1)[0]
    assert "Bcc:" not in headers and "victim" not in headers


# ---- signed links --------------------------------------------------------------------------------------------------
def _paid_order(buyer, rag):
    _checkout(buyer, rag)
    o = _latest_order()
    _pay(buyer, o)
    db.session.refresh(o)
    return o


def test_signed_invoice_and_guide_links_open_without_signing_in_and_are_private(app, buyer, rag):
    o = _paid_order(buyer, rag)
    anon = app.test_client()
    for purpose, path, needle in (("invoice", "i", "Total paid"), ("guide", "g", "Setup guide")):
        r = anon.get(f"/{path}/{notify.make_token(purpose, o.id, o.public_id)}")
        assert r.status_code == 200 and needle in r.get_data(as_text=True)
        assert r.headers["Cache-Control"] == "no-store" and "noindex" in r.headers["X-Robots-Tag"]
        assert '<meta name="robots" content="noindex, nofollow">' in r.get_data(as_text=True)


def test_tampered_expired_crossed_and_foreign_tokens_fail(app, buyer, rag):
    o = _paid_order(buyer, rag)
    anon = app.test_client()
    good = notify.make_token("invoice", o.id, o.public_id)
    assert anon.get(f"/i/{good[:-2]}xx").status_code == 404                         # tampered
    assert anon.get(f"/g/{good}").status_code == 404                                 # an invoice token on the guide route
    assert anon.get(f"/i/{notify.make_token('invoice', o.id, 'PS-OTHER1')}").status_code == 404   # another order's id
    assert anon.get(f"/i/{notify.make_token('invoice', o.id + 999, o.public_id)}").status_code == 404
    app.config["MESSAGE_LINK_DAYS"] = 0                                              # expired
    import time
    time.sleep(1.1)
    assert anon.get(f"/i/{good}").status_code == 404


def test_a_token_for_an_unpaid_order_fails(app, buyer, rag):
    _checkout(buyer, rag)
    o = _latest_order()
    assert app.test_client().get(f"/i/{notify.make_token('invoice', o.id, o.public_id)}").status_code == 404


def test_the_signed_in_invoice_is_for_the_owner_or_an_admin(app, buyer, admin_client, rag):
    o = _paid_order(buyer, rag)
    assert buyer.get(f"/orders/{o.public_id}/invoice").status_code == 200
    assert admin_client.get(f"/orders/{o.public_id}/invoice").status_code == 200
    stranger = app.test_client()
    force_login(stranger, make_user("s@example.com", name="S"))
    assert stranger.get(f"/orders/{o.public_id}/invoice").status_code == 404
    assert app.test_client().get(f"/orders/{o.public_id}/invoice").status_code == 302


def test_the_invoice_shows_lines_totals_reference_and_no_tax_unless_a_gstin_is_set(app, buyer, rag):
    o = _paid_order(buyer, rag)
    page = buyer.get(f"/orders/{o.public_id}/invoice").get_data(as_text=True)
    assert "Advanced RAG Knowledge Assistant" in page and "₹2,999" in page and o.gateway_payment_id in page
    assert "GSTIN" not in page and "no tax is itemised" in page
    app.config["SELLER_GSTIN"] = "29ABCDE1234F1Z5"
    assert "GSTIN 29ABCDE1234F1Z5" in buyer.get(f"/orders/{o.public_id}/invoice").get_data(as_text=True)


def test_xss_in_titles_and_guides_is_escaped_everywhere(app, buyer, rag, smtp):
    rag.setup_guide = "# <script>alert(1)</script>\n- <img src=x onerror=alert(2)>\n`<b>`"
    db.session.commit()
    _checkout(buyer, rag, value="x@example.com")
    o = _latest_order()
    o.items[0].title = '<script>alert("t")</script>'
    db.session.commit()
    _pay(buyer, o)
    pages = [buyer.get(f"/orders/{o.public_id}").get_data(as_text=True),
             buyer.get(f"/orders/{o.public_id}/invoice").get_data(as_text=True),
             app.test_client().get(f"/g/{notify.make_token('guide', o.id, o.public_id)}").get_data(as_text=True),
             _messages(o)[0].body_html]
    for page in pages:
        assert "<script>alert" not in page and "<img src=x" not in page and "<b>" not in page.replace("<body>", "")


def test_the_guide_renderer_allows_only_its_own_tags():
    html = str(render_guide("# Head\n## Sub\n- a\n- b\n1. one\n2. two\n```\n<x> & y\n```\nplain `code` <i>no</i>"))
    assert "<h3>Head</h3><h4>Sub</h4><ul><li>a</li><li>b</li></ul><ol><li>one</li><li>two</li></ol>" in html
    assert "<pre><code>&lt;x&gt; &amp; y</code></pre>" in html and "<code>code</code>" in html and "<i>" not in html


# ---- guides, admin, anonymising, practice mode ---------------------------------------------------------------------
def test_every_seeded_project_has_a_guide_and_seeding_again_keeps_an_edited_one(app, rag):
    from app.seed import seed_guides
    for p in db.session.scalars(db.select(Product)):
        assert "# What you need" in (p.setup_guide or "")
    rag.setup_guide, rag.guide_edited = "Owner's own guide", True
    db.session.commit()
    seed_guides()
    db.session.refresh(rag)
    assert rag.setup_guide == "Owner's own guide"


def test_editing_the_guide_in_admin_marks_it_edited(admin_client, rag):
    page = admin_client.get(f"/admin/products/{rag.id}").get_data(as_text=True)
    assert 'name="setup_guide"' in page
    data = {"title": rag.title, "slug": rag.slug, "category_id": str(rag.category_id), "price_rupees": "2999",
            "tagline": rag.tagline, "description": rag.description, "tech": rag.tech, "includes": rag.includes,
            "delivery_url": "", "is_active": "on", "setup_guide": "# New guide\n1. step"}
    assert admin_client.post(f"/admin/products/{rag.id}", data=data).status_code == 302
    db.session.refresh(rag)
    assert rag.setup_guide == "# New guide\n1. step" and rag.guide_edited


def test_anonymising_removes_raw_contacts_from_the_order_and_its_messages(buyer, rag):
    o = _paid_order(buyer, rag)
    [m] = _messages(o)
    assert m.to_value == "buyer@example.com"
    anonymise_order(o.id)
    db.session.refresh(o); db.session.refresh(m)
    assert (o.contact_value, o.billing_name, o.phone, m.to_value, m.body_text) == ("", "Removed", "", "", "")
    assert m.to_hash == notify.contact_hash("buyer@example.com")        # stop requests and limits still hold


def test_practice_mode_works_end_to_end_with_the_outbox(app, buyer, admin_client, rag):
    assert app.config["ALLOW_PRACTICE_GATEWAY"]
    o = _paid_order(buyer, rag)
    [m] = _messages(o)
    listing = admin_client.get("/admin/messages").get_data(as_text=True)
    assert o.public_id in listing and "Not configured" in listing and "buyer@example.com" not in listing
    detail = admin_client.get(f"/admin/outbox/{m.id}").get_data(as_text=True)
    assert "Hi Asha," in detail and "I sent it by hand" in detail
    admin_client.post(f"/admin/outbox/{m.id}/sent")
    db.session.refresh(m)
    assert m.status == "sent" and m.last_error == "sent by hand"


def test_admin_outbox_needs_an_admin(app, buyer, rag):
    o = _paid_order(buyer, rag)
    [m] = _messages(o)
    assert buyer.get(f"/admin/outbox/{m.id}").status_code == 403
    assert buyer.post(f"/admin/outbox/{m.id}/sent").status_code == 403


def test_raw_contact_values_are_never_logged(app, buyer, rag, smtp, caplog):
    caplog.set_level("DEBUG")
    smtp.refuse_rcpt = True
    _checkout(buyer, rag, value="private@example.com")
    _pay(buyer, _latest_order())
    assert "private@example.com" not in caplog.text


def test_the_send_messages_command_runs_the_sweep(app):
    result = app.test_cli_runner().invoke(args=["send-messages"])
    assert result.exit_code == 0 and "Tried 0 message(s)." in result.output
