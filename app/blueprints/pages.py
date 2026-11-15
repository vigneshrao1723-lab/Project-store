"""Site pages that are not the shop (v1.4): About, FAQ, the policies (privacy, terms of sale, refunds and cancellation,
delivery, cookies, accessibility), and the files crawlers and browsers ask for (robots.txt, sitemap.xml,
/.well-known/security.txt, the favicon and the web app manifest).

Every policy is written from what the app really does (see docs/SECURITY_AUDIT.md and the "Data the store keeps"
section of docs/ARCHITECTURE.md). Each says when it was last updated and that it is a template no lawyer has reviewed.
Names, addresses and contact details come from the environment (CONTACT_*, SELLER_*), never from the code.
"""
import json
import re
from datetime import timedelta
from pathlib import Path

from flask import Blueprint, Response, current_app, redirect, render_template, url_for

from ..context import FAVICON_SVG, TOKENS
from ..extensions import db
from ..models import Product, utcnow

bp = Blueprint("pages", __name__)

# Bump this when a policy's wording changes; it is printed on every policy page.
POLICIES_UPDATED = "15 November 2026"
REFUND_DAYS = 7

POLICY_PAGES = {               # endpoint: (template, title, description)
    "privacy": ("pages/privacy.html", "Privacy Policy", "What personal data Project Store keeps, why, for how long, who processes it and your rights under India's DPDP Act, 2023."),
    "terms": ("pages/terms.html", "Terms of Sale", "The terms for buying a digital project kit from Project Store."),
    "refunds": ("pages/refunds.html", "Refund and Cancellation Policy", "When you can cancel an order or get a refund for a digital project kit, and how to ask."),
    "delivery": ("pages/delivery.html", "Delivery Policy", "How and when a digital project kit is delivered: a download link on your order page."),
    "cookies": ("pages/cookies.html", "Cookie Policy", "Every cookie and browser storage item Project Store uses, what it is for and how long it lasts."),
    "accessibility": ("pages/accessibility.html", "Accessibility Statement", "How Project Store is built to be usable with a keyboard, a screen reader and reduced motion, and what is not verified."),
}
INFO_PAGES = {
    "about": ("pages/about.html", "About", "Who sells on Project Store and what a project kit contains."),
    "faq": ("pages/faq.html", "Frequently asked questions", "Answers about buying, delivery, payment, refunds and order messages."),
}


def _render(table, name):
    template, title, description = table[name]
    return render_template(template, page_title=title, page_description=description, updated=POLICIES_UPDATED,
                           refund_days=REFUND_DAYS, is_policy=table is POLICY_PAGES)


def _view(table, name):
    def view():
        return _render(table, name)
    view.__name__ = name
    return view


for _name in POLICY_PAGES:
    bp.add_url_rule(f"/{_name}", endpoint=_name, view_func=_view(POLICY_PAGES, _name), methods=["GET"])
for _name in INFO_PAGES:
    bp.add_url_rule(f"/{_name}", endpoint=_name, view_func=_view(INFO_PAGES, _name), methods=["GET"])


def _base():
    return current_app.config["PUBLIC_BASE_URL"]


PRIVATE_PATHS = ("/admin", "/api/", "/cart", "/checkout", "/orders", "/i/", "/g/", "/stop/", "/login", "/register")


@bp.get("/robots.txt")
def robots():
    lines = ["User-agent: *"] + [f"Disallow: {p}" for p in PRIVATE_PATHS] + ["", f"Sitemap: {_base()}{url_for('pages.sitemap')}", ""]
    return Response("\n".join(lines), mimetype="text/plain")


def public_urls():
    """Every page a search engine may list: the shop, each live project, each field, the information and policy pages."""
    urls = [url_for("shop.home"), url_for("shop.catalogue"), url_for("contact.page")]
    urls += [url_for(f"pages.{n}") for n in list(INFO_PAGES) + list(POLICY_PAGES)]
    products = db.session.scalars(db.select(Product).where(Product.is_active.is_(True)).order_by(Product.id)).all()
    urls += [url_for("shop.product", slug=p.slug) for p in products]
    urls += sorted({url_for("shop.catalogue", category=p.category.slug) for p in products})
    return urls


@bp.get("/sitemap.xml")
def sitemap():
    from xml.sax.saxutils import escape
    body = "".join(f"<url><loc>{escape(_base() + u)}</loc></url>" for u in public_urls())
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>\n'
    return Response(xml, mimetype="application/xml")


@bp.get("/.well-known/security.txt")
def security_txt():
    """RFC 9116. Expires is always one year ahead, so the file never goes stale."""
    email = current_app.config.get("CONTACT_EMAIL", "")
    contact = f"mailto:{email}" if email else _base() + url_for("contact.page")
    expires = (utcnow() + timedelta(days=365)).strftime("%Y-%m-%dT00:00:00Z")
    text = (f"Contact: {contact}\nExpires: {expires}\nPreferred-Languages: en\n"
            f"Canonical: {_base()}{url_for('pages.security_txt')}\nPolicy: {_base()}{url_for('pages.privacy')}\n")
    return Response(text, mimetype="text/plain")


@bp.get("/favicon.svg")
def favicon():
    resp = Response(FAVICON_SVG, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@bp.get("/favicon.ico")
def favicon_ico():
    return redirect(url_for("pages.favicon"), 301)


@bp.get("/manifest.webmanifest")
def manifest():
    data = {"name": "Project Store", "short_name": "Project Store", "start_url": "/", "scope": "/", "display": "browser",
            "description": "Finished engineering projects with working source, a setup guide and architecture notes.",
            "background_color": TOKENS["night"], "theme_color": TOKENS["night"],
            "icons": [{"src": url_for("pages.favicon"), "type": "image/svg+xml", "sizes": "any", "purpose": "any"}]}
    return Response(json.dumps(data, indent=1), mimetype="application/manifest+json")
