"""v1.4 site pages and compliance: the policy and information pages, the footer links, the cookie notice, the checkout
agreement (Consumer Protection (E-Commerce) Rules, 2020), seller details, robots.txt, sitemap.xml, security.txt, the
favicon and manifest, meta tags on every page, the custom 404 and 500 pages, and erasing an account."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import pytest

from app.extensions import db
from app.models import CartItem, ContactMessage, Order, User

ROOT = Path(__file__).resolve().parent.parent
POLICIES = {"/privacy": "Privacy Policy", "/terms": "Terms of Sale", "/refunds": "Refund and Cancellation Policy",
            "/delivery": "Delivery Policy", "/cookies": "Cookie Policy", "/accessibility": "Accessibility Statement"}
INFO = {"/about": "About", "/faq": "Frequently asked questions"}
OWNER = dict(CONTACT_NAME="Owner Name", CONTACT_EMAIL="owner@example.test", CONTACT_PHONE="+91 98450 12345",
             CONTACT_CITY="Bengaluru", SELLER_NAME="Owner Name", SELLER_ADDRESS="Bengaluru, Karnataka, India")


@pytest.fixture()
def owner(app):
    app.config.update(OWNER)
    return app


@pytest.mark.parametrize("path,title", list(POLICIES.items()) + list(INFO.items()))
def test_every_new_page_renders_in_the_site_design_with_its_own_title_and_description(client, path, title):
    r = client.get(path)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and r.mimetype == "text/html"
    assert f"<title>{title} | Project Store</title>" in html and f'<h1 class="h2" id="page-h">{title}</h1>' in html
    assert re.search(r'<meta name="description" content="[^"]{30,}">', html)
    assert 'class="site-header"' in html and 'class="site-footer"' in html and "css/tokens.css" in html


@pytest.mark.parametrize("path", list(POLICIES))
def test_every_policy_says_when_it_was_updated_and_that_no_lawyer_has_reviewed_it(client, path):
    html = client.get(path).get_data(as_text=True)
    assert 'Last updated: <time datetime="2026-11-15">15 November 2026</time>' in html
    assert "This is a template that has not been reviewed by a lawyer." in html


def test_information_pages_are_not_labelled_as_policies(client):
    for path in INFO:
        assert "Last updated" not in client.get(path).get_data(as_text=True)


PUBLIC = ["/", "/catalogue", "/contact", "/login", "/register", "/cart"] + list(POLICIES) + list(INFO)


@pytest.mark.parametrize("path", PUBLIC + ["/no-such-page"])
def test_every_page_has_lang_canonical_open_graph_and_the_manifest(client, path):
    html = client.get(path, follow_redirects=True).get_data(as_text=True)
    assert html.startswith("<!doctype html>\n<html lang=\"en\"")
    canonical = re.search(r'<link rel="canonical" href="([^"]+)">', html).group(1)
    assert canonical.startswith("http://localhost/")
    for tag in ('property="og:title"', 'property="og:description"', 'property="og:url"', 'property="og:type" content="website"',
                'property="og:site_name" content="Project Store"', 'name="twitter:card" content="summary"'):
        assert tag in html, (path, tag)
    assert f'<meta property="og:url" content="{canonical}">' in html
    assert '<link rel="manifest" href="/manifest.webmanifest">' in html and 'href="/favicon.svg" type="image/svg+xml"' in html


def test_the_canonical_url_drops_tracking_and_sort_parameters_but_keeps_the_field(client, rag):
    html = client.get("/catalogue?sort=price&utm_source=x").get_data(as_text=True)
    assert '<link rel="canonical" href="http://localhost/catalogue">' in html
    html = client.get(f"/catalogue?category={rag.category.slug}&page=1").get_data(as_text=True)
    assert f'<link rel="canonical" href="http://localhost/catalogue?category={rag.category.slug}">' in html


FOOTER = ["/about", "/faq", "/delivery", "/refunds", "/terms", "/privacy", "/cookies", "/accessibility", "/contact", "/catalogue"]


@pytest.mark.parametrize("path", PUBLIC + ["/no-such-page"])
def test_the_footer_links_every_policy_and_information_page_on_every_page(client, path):
    html = client.get(path, follow_redirects=True).get_data(as_text=True)
    footer = html[html.index('<footer class="site-footer"'):html.index("</footer>")]
    for href in FOOTER:
        assert f'href="{href}"' in footer, (path, href)


def test_the_footer_and_about_page_show_the_seller_and_grievance_officer(owner, client):
    footer = client.get("/").get_data(as_text=True)
    footer = footer[footer.index('<footer class="site-footer"'):]
    assert "Sold by Owner Name, Bengaluru, Karnataka, India." in footer
    assert 'Grievance officer: Owner Name, <a href="mailto:owner@example.test">owner@example.test</a>.' in footer
    about = client.get("/about").get_data(as_text=True)
    assert "<dt>Seller</dt><dd>Owner Name</dd>" in about and "<dt>Grievance officer</dt>" in about and "+91 98450 12345" in about


def test_policies_name_the_grievance_contact_from_the_environment(owner, client):
    for path in ("/privacy", "/terms", "/refunds"):
        html = client.get(path).get_data(as_text=True)
        assert "Owner Name" in html and "mailto:owner@example.test" in html, path


def test_the_privacy_policy_matches_what_the_app_does(client):
    html = client.get("/privacy").get_data(as_text=True)
    for must in ("Digital Personal Data Protection Act, 2023", "Razorpay", "email provider", "WhatsApp", "Google Maps",
                 "/stop/", "flask anonymise-order", "flask anonymise-account", "Data Protection Board of India",
                 "scrypt", "Deleted after one day", "after 10 minutes", "10 MB", "no analytics"):
        assert must.lower() in html.lower(), must
    assert "Load map" in html                                  # Google is contacted only after the visitor asks


def test_the_cookie_policy_lists_every_cookie_the_app_really_sets(app, client, user):
    """Sign in with "Keep me signed in", visit pages, and check that every Set-Cookie name appears in the policy table."""
    names = set()
    r = client.post("/login", data={"email": user.email, "password": "correct-horse-battery", "remember": "on"})
    names |= {c.split("=", 1)[0] for c in r.headers.getlist("Set-Cookie")}
    for path in ("/", "/cart", "/orders", "/contact"):
        names |= {c.split("=", 1)[0] for c in client.get(path).headers.getlist("Set-Cookie")}
    names |= {c.split("=", 1)[0] for c in client.post("/logout").headers.getlist("Set-Cookie")}
    policy = client.get("/cookies").get_data(as_text=True)
    assert names and names <= {"session", "remember_token"}, names
    for n in names:
        assert f"<tr><td><code>{n}</code></td>" in policy, n
    js = "".join(f.read_text(encoding="utf-8") for f in (ROOT / "app" / "static" / "js").glob("*.js"))
    assert "document.cookie" not in js                          # no script sets a cookie
    for key in re.findall(r'(?:local|session)Storage\.setItem\("([\w-]+)', js):
        assert f"<code>{key}" in policy, key
    assert "ps-paid-" in js and "<code>ps-paid-&lt;order&gt;</code>" in policy


def test_the_cookie_notice_is_honest_dismissible_and_needs_no_cookie(client):
    html = client.get("/").get_data(as_text=True)
    note = html[html.index("<aside class=\"cookie-note"):html.index("</aside>", html.index("<aside class=\"cookie-note"))]
    assert "essential cookies only" in note and "No analytics, no advertising, no tracking." in note
    assert '<a href="/cookies">Cookie Policy</a>' in note
    assert re.search(r'<button class="btn cookie-btn" type="button" data-cookie-ok hidden>OK<span class="sr">, hide this notice</span></button>', note)
    boot = (ROOT / "app" / "static" / "js" / "motion-boot.js").read_text(encoding="utf-8")
    app_js = (ROOT / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'localStorage.getItem("ps-cookie-note") === "ok"' in boot and 'classList.add("cookie-ok")' in boot
    assert 'localStorage.setItem("ps-cookie-note", "ok")' in app_js and "ok.hidden = false" in app_js
    css = (ROOT / "app" / "static" / "css" / "main.css").read_text(encoding="utf-8")
    assert "html.cookie-ok .cookie-note { display: none; }" in css
    assert "analytics" not in "".join(f.read_text(encoding="utf-8") for f in (ROOT / "app" / "static" / "js").glob("*.js")).lower()


# ---- the checkout agreement -------------------------------------------------------------------------------------------

def test_the_checkout_form_has_the_terms_box_with_links_and_the_seller_line(owner, buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    html = buyer.get("/checkout").get_data(as_text=True)
    box = html[html.index('class="field terms-field'):html.index("</div>", html.index('class="field terms-field'))]
    assert 'name="accept_terms" required' in box and "checked" not in box
    for href in ("/terms", "/privacy", "/refunds"):
        assert f'href="{href}" target="_blank" rel="noopener"' in box
    assert "Sold by Owner Name, Bengaluru, Karnataka, India." in box


def test_checkout_without_the_agreement_is_refused_and_creates_no_order(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    r = buyer.post("/checkout", data={"billing_name": "Asha"})
    html = r.get_data(as_text=True)
    assert r.status_code == 400 and 'id="accept_terms-msg"' in html and "Tick the box to agree to the Terms of Sale" in html
    assert db.session.scalar(db.select(db.func.count(Order.id))) == 0
    for bad in ("", "off", "no", "0"):
        assert buyer.post("/checkout", data={"billing_name": "Asha", "accept_terms": bad}).status_code == 400


def test_checkout_with_the_agreement_records_when_it_was_given(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    before = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5)
    r = buyer.post("/checkout", data={"billing_name": "Asha", "accept_terms": "on"})
    assert r.status_code == 302 and "/checkout/pay/" in r.headers["Location"]
    order = db.session.scalar(db.select(Order))
    assert order.terms_accepted_at is not None and order.terms_accepted_at >= before


def test_the_api_needs_accept_terms_true_exactly(buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    for bad in ({}, {"accept_terms": False}, {"accept_terms": "true"}, {"accept_terms": 1}, {"accept_terms": None}):
        r = buyer.post("/api/v1/checkout", json=bad)
        assert r.status_code == 400 and "accept_terms" in r.get_json()["fields"], bad
    assert db.session.scalar(db.select(db.func.count(Order.id))) == 0
    r = buyer.post("/api/v1/checkout", json={"accept_terms": True})
    assert r.status_code == 201 and db.session.scalar(db.select(Order)).terms_accepted_at is not None


def test_the_invoice_shows_the_seller_contact_and_grievance_officer(owner, buyer, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    order = buyer.post("/api/v1/checkout", json={"accept_terms": True}).get_json()["id"]
    buyer.post(f"/checkout/test-pay/{order}", data={"outcome": "pay"})
    owner.config["PUBLIC_BASE_URL"] = "https://shop.example.test"        # the link uses the configured address, not the request host
    html = buyer.get(f"/orders/{order}/invoice").get_data(as_text=True)
    assert "Bengaluru, Karnataka, India" in html and "owner@example.test" in html and "+91 98450 12345" in html
    assert "Grievance officer: Owner Name, owner@example.test." in html and "https://shop.example.test/refunds" in html


# ---- files for crawlers and browsers ----------------------------------------------------------------------------------

def test_robots_txt_keeps_private_pages_out_and_points_at_the_sitemap(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200 and r.mimetype == "text/plain"
    for path in ("/admin", "/api/", "/cart", "/checkout", "/orders", "/i/", "/g/", "/stop/"):
        assert f"Disallow: {path}\n" in r.text
    assert "Sitemap: http://localhost/sitemap.xml" in r.text


def test_the_sitemap_lists_every_public_page_and_live_project_and_nothing_private(client, rag, soc):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200 and r.mimetype == "application/xml"
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [e.text for e in ElementTree.fromstring(r.data).findall("s:url/s:loc", ns)]
    for path in ["/", "/catalogue", "/contact"] + list(POLICIES) + list(INFO) + [f"/p/{rag.slug}"]:
        assert "http://localhost" + path in locs, path
    assert not [u for u in locs if re.search(r"/(admin|api|cart|checkout|orders|i|g|stop)(/|$)", u)]
    assert len(locs) == len(set(locs))


def test_security_txt_follows_rfc_9116(owner, client):
    r = client.get("/.well-known/security.txt")
    assert r.status_code == 200 and r.mimetype == "text/plain"
    fields = dict(l.split(": ", 1) for l in r.text.strip().splitlines())
    assert fields["Contact"] == "mailto:owner@example.test" and fields["Preferred-Languages"] == "en"
    assert fields["Canonical"] == "http://localhost/.well-known/security.txt"
    expires = datetime.strptime(fields["Expires"], "%Y-%m-%dT%H:%M:%SZ")
    assert timedelta(days=300) < expires - datetime.now(timezone.utc).replace(tzinfo=None) < timedelta(days=366)


def test_security_txt_falls_back_to_the_contact_page(client):
    assert "Contact: http://localhost/contact" in client.get("/.well-known/security.txt").text


def test_the_favicon_and_manifest_use_the_palette_tokens(client):
    from app.context import TOKENS
    r = client.get("/favicon.svg")
    assert r.status_code == 200 and r.mimetype == "image/svg+xml" and TOKENS["violet"] in r.text and TOKENS["amber"] in r.text
    assert client.get("/favicon.ico").status_code == 301 and client.get("/favicon.ico").headers["Location"].endswith("/favicon.svg")
    m = client.get("/manifest.webmanifest")
    data = json.loads(m.data)
    assert m.mimetype == "application/manifest+json" and data["name"] == "Project Store" and data["start_url"] == "/"
    assert data["icons"][0] == {"src": "/favicon.svg", "type": "image/svg+xml", "sizes": "any", "purpose": "any"}
    assert data["theme_color"] == TOKENS["night"]


def test_healthz_still_answers(client):
    assert client.get("/healthz").get_json() == {"status": "ok"}


# ---- error pages ---------------------------------------------------------------------------------------------------------

def test_the_404_page_helps_and_leaks_nothing(client):
    r = client.get("/definitely/not/here")
    html = r.get_data(as_text=True)
    assert r.status_code == 404 and "<title>Page not found | Project Store</title>" in html
    assert 'role="search"' in html and 'action="/catalogue"' in html and 'href="/contact"' in html
    assert '<meta name="robots" content="noindex">' in html and "Traceback" not in html and "werkzeug" not in html.lower()
    assert "fx-scroll.js" not in html                                  # error pages run no motion scripts


def test_the_500_page_is_plain_and_leaks_nothing(app):
    @app.get("/_explode")
    def _explode():
        raise RuntimeError("secret detail that must not leak")
    app.config["PROPAGATE_EXCEPTIONS"] = False
    r = app.test_client().get("/_explode")
    html = r.get_data(as_text=True)
    assert r.status_code == 500 and "Something broke on our side" in html and "secret detail" not in html and "Traceback" not in html


# ---- erasing an account ---------------------------------------------------------------------------------------------------

def test_anonymise_account_erases_the_person_and_keeps_the_sales_record(app, buyer, user, rag):
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    order = buyer.post("/api/v1/checkout", json={"accept_terms": True, "billing_name": "Asha Rao", "phone": "9845012345"}).get_json()
    buyer.post("/api/v1/cart/items", json={"product_id": rag.id, "qty": 1})
    db.session.add(ContactMessage(first_name="Asha", email=user.email, subject="Hi", body="Hello", consent=True))
    db.session.commit()
    email = user.email
    result = app.test_cli_runner().invoke(args=["anonymise-account", email.upper()])
    assert result.exit_code == 0 and "Account anonymised." in result.output
    u = db.session.get(User, user.id)
    o = db.session.scalar(db.select(Order).where(Order.public_id == order["id"]))
    assert u.name == "Removed" and u.email == f"removed-{u.id}@deleted.invalid" and not u.check_password("correct-horse-battery")
    assert o.billing_name == "Removed" and o.phone == "" and o.total_paise == order["total_paise"]
    assert db.session.scalar(db.select(db.func.count(CartItem.id)).where(CartItem.user_id == u.id)) == 0
    assert db.session.scalar(db.select(db.func.count(ContactMessage.id)).where(ContactMessage.email == email)) == 0
    assert buyer.get("/orders").status_code == 302                      # the old session is signed out
    assert app.test_cli_runner().invoke(args=["anonymise-account", "nobody@example.test"]).exit_code != 0


def test_container_logs_are_rotated_as_the_privacy_policy_says():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'max-size: "10m"' in compose and 'max-file: "3"' in compose and compose.count("logging: *logging") == 4          # db, migrate, web, sweeper
