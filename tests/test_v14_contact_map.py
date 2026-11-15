"""v1.4: the owner's contact details from the environment, the click-to-load Google map, the one CSP change it needs, the
Cross-Origin-Resource-Policy header, and no placeholder contact values anywhere in the repository."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db

ROOT = Path(__file__).resolve().parent.parent
OWNER = dict(CONTACT_NAME="Owner Name", CONTACT_PHONE="+91 98450 12345", CONTACT_EMAIL="owner@example.test",
             CONTACT_CITY="Bengaluru", SELLER_NAME="Owner Name", SELLER_ADDRESS="Bengaluru, Karnataka, India")
EMBED = "https://maps.google.com/maps?q=Bengaluru&amp;t=h&amp;z=12&amp;output=embed"


@pytest.fixture()
def owner(app):
    app.config.update(OWNER)
    return app


def test_the_contact_block_shows_name_email_city_and_the_phone_as_tel_and_whatsapp_links(owner, client):
    for path in ("/contact", "/"):
        page = client.get(path).get_data(as_text=True)
        assert ">Owner Name<" in page and "mailto:owner@example.test" in page and ">Bengaluru<" in page
        assert '<a href="tel:+919845012345">+91 98450 12345</a>' in page
        assert re.search(r'<a class="wa-link" href="https://wa.me/919845012345" rel="noopener noreferrer" target="_blank">Chat on WhatsApp', page)


def test_with_nothing_configured_no_contact_detail_or_map_is_shown(client):
    page = client.get("/contact").get_data(as_text=True)
    assert "tel:" not in page and "wa.me" not in page and "mailto:" not in page and "data-map" not in page


def test_the_map_is_a_poster_until_asked_for_and_has_a_plain_link_that_works_without_script(owner, client):
    page = client.get("/contact").get_data(as_text=True)
    box = page[page.index('<div class="map"'):page.index("</aside>")]
    assert f'data-src="{EMBED}"' in box                                    # hybrid view (t=h), city level, no API key
    assert "<iframe" not in page                                          # nothing from Google until the visitor presses the button
    assert '<p class="map-city">Bengaluru, Karnataka</p>' in box
    assert re.search(r'<button class="btn map-load" type="button" data-map-load hidden>Load map</button>', box)
    assert '<a class="map-open" href="https://www.google.com/maps/search/?api=1&amp;query=Bengaluru%2C%20Karnataka" rel="noopener noreferrer" target="_blank">Open in Google Maps' in box
    assert 'js/contact-map.js' in page and "pin-art" not in page


def test_the_map_is_never_centred_on_more_than_the_city(owner, client):
    owner.config["SELLER_ADDRESS"] = "12 Some Street, Bengaluru, Karnataka"         # a street address is never used for the map
    page = client.get("/contact").get_data(as_text=True)
    assert "Street" not in page[page.index('<div class="map"'):page.index("</aside>")]
    assert f'data-src="{EMBED}"' in page


NODE = shutil.which("node")
MAP_HARNESS = r"""
const vm = require("vm"), fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
const made = [];
const mk = (tag) => ({ tag, attrs: {}, className: "", setAttribute(k, v) { this.attrs[k] = v; }, focus() { this.focused = true; } });
const btn = { hidden: true, L: {}, addEventListener(t, f, o) { this.L[t] = { f, o }; } };
const box = { dataset: { src: SRC, title: "Map of Bengaluru, Karnataka (Google Maps)" }, kids: [], classList: { s: new Set(), add(c) { this.s.add(c); } },
  querySelector: (s) => (s === "[data-map-load]" ? btn : null), appendChild(k) { this.kids.push(k); } };
const document = { querySelectorAll: (s) => (s === "[data-map]" ? [box] : []), createElement: (t) => { const e = mk(t); made.push(e); return e; } };
vm.runInNewContext(src, { document });
const before = { hidden: btn.hidden, made: made.length };
if (btn.L.click) btn.L.click.f();
const f = box.kids[0] || {};
console.log(JSON.stringify({ before, once: btn.L.click && btn.L.click.o, tag: f.tag, src: f.src, title: f.title, loading: f.loading,
  ref: f.referrerPolicy, sandbox: f.attrs && f.attrs.sandbox, cls: f.className, focused: !!f.focused, loaded: box.classList.s.has("is-loaded") }));
"""


def run_map(src):
    if not NODE:
        pytest.skip("node is not installed")
    code = MAP_HARNESS.replace("SRC", repr(src))
    out = subprocess.run([NODE, "-e", code, str(ROOT / "app" / "static" / "js" / "contact-map.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    import json
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_map_script_creates_the_iframe_only_on_click_with_the_required_attributes():
    r = run_map("https://maps.google.com/maps?q=Bengaluru&t=h&z=12&output=embed")
    assert r["before"] == {"hidden": False, "made": 0} and r["once"] == {"once": True}
    assert r["tag"] == "iframe" and r["src"] == "https://maps.google.com/maps?q=Bengaluru&t=h&z=12&output=embed"
    assert r["title"] == "Map of Bengaluru, Karnataka (Google Maps)" and r["loading"] == "lazy"
    assert r["ref"] == "strict-origin-when-cross-origin" and r["sandbox"] == "allow-scripts allow-same-origin allow-popups"
    assert r["cls"] == "map-frame" and r["focused"] and r["loaded"]


def test_the_map_script_refuses_any_source_that_is_not_google_maps():
    r = run_map("https://evil.example/maps")
    assert r["before"] == {"hidden": True, "made": 0} and r.get("tag") is None


EXPECTED_CSP = {
    "default-src": ["'self'"], "script-src": ["'self'", "https://checkout.razorpay.com"], "style-src": ["'self'"],
    "font-src": ["'self'"], "img-src": ["'self'", "data:"],
    "frame-src": ["https://api.razorpay.com", "https://checkout.razorpay.com", "https://maps.google.com", "https://www.google.com"],
    "connect-src": ["'self'", "https://lumberjack.razorpay.com", "https://api.razorpay.com"],
    "object-src": ["'none'"], "form-action": ["'self'"], "base-uri": ["'self'"], "frame-ancestors": ["'self'"],
}


@pytest.mark.parametrize("path", ["/", "/contact", "/no-such-page", "/static/js/app.js", "/api/v1/products"])
def test_the_csp_is_exactly_the_v13_policy_plus_the_two_google_maps_frame_origins(client, path):
    policy = client.get(path).headers["Content-Security-Policy"]
    d = {p.split()[0]: p.split()[1:] for p in policy.split(";") if p.strip()}
    assert d == EXPECTED_CSP
    assert "'unsafe-inline'" not in policy and "'unsafe-eval'" not in policy and "*" not in policy


def test_the_only_relaxation_since_v13_is_the_maps_frame_origins():
    """The v1.3 frame-src held the two Razorpay origins. v1.4 adds exactly maps.google.com and www.google.com; every other
    directive is the same or stricter (object-src 'none' is new and only tightens)."""
    v13_frames = {"https://api.razorpay.com", "https://checkout.razorpay.com"}
    assert set(EXPECTED_CSP["frame-src"]) - v13_frames == {"https://maps.google.com", "https://www.google.com"}


def test_every_response_says_its_resources_are_for_this_site_only(client):
    for path in ("/", "/static/css/main.css", "/api/v1/products", "/no-such-page"):
        assert client.get(path).headers["Cross-Origin-Resource-Policy"] == "same-origin", path


def test_no_placeholder_contact_value_is_left_anywhere_in_the_repository():
    hits = []
    for folder in ("app", "tests", "docs", "scripts"):
        for f in (ROOT / folder).rglob("*"):
            if f.is_file() and f.suffix in (".py", ".html", ".md", ".txt", ".js", ".css", ".json", ".sh") and f.name != Path(__file__).name:
                text = f.read_text(encoding="utf-8", errors="ignore")
                for needle in ("90000 00000", "hello@example.com", "Your city", "github.com/example"):
                    if needle in text:
                        hits.append((str(f.relative_to(ROOT)), needle))
    for f in ("README.md", "CHANGELOG.md", ".env.example"):
        text = (ROOT / f).read_text(encoding="utf-8")
        hits += [(f, n) for n in ("90000 00000", "hello@example.com", "Your city") if n in text]
    assert not hits, hits


def test_the_owners_real_details_live_only_in_the_environment():
    """No Indian mobile number and no Gmail address is written in the app or the docs (the tests use invented ones to check
    masking): the owner's real details come from .env only."""
    for folder in ("app", "docs"):
        for f in (ROOT / folder).rglob("*"):
            if f.is_file() and f.suffix in (".py", ".html", ".md", ".js", ".json", ".txt"):
                text = f.read_text(encoding="utf-8", errors="ignore")
                assert not re.search(r"\+91[\s-]?[6-9]\d{4}[\s-]?\d{5}", text), f
                assert set(re.findall(r"[\w.]+@gmail\.com", text)) <= {"you@gmail.com"}, f     # the setup example in NOTIFICATIONS.md


def test_env_example_lists_the_new_settings_with_empty_values():
    values = dict(l.split("=", 1) for l in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
    for key in ("CONTACT_NAME", "CONTACT_PHONE", "CONTACT_EMAIL", "CONTACT_CITY", "SELLER_NAME", "SELLER_ADDRESS"):
        assert key in values and values[key] in ("", "Project Store"), key
    assert values["TRUSTED_PROXIES"] == "0"


# ---- the client address behind a proxy (security item 14) ---------------------------------------------------------------

def _ip_app(proxies):
    application = create_app(type("C", (TestConfig,), {"TRUSTED_PROXIES": proxies}))

    @application.get("/_ip")
    def _ip():
        from flask import request
        return request.remote_addr or ""
    return application


def test_by_default_a_forged_x_forwarded_for_is_ignored():
    c = _ip_app(0).test_client()
    assert c.get("/_ip", headers={"X-Forwarded-For": "1.2.3.4"}, environ_base={"REMOTE_ADDR": "10.0.0.9"}).text == "10.0.0.9"


def test_with_one_trusted_proxy_only_the_hop_it_added_is_believed():
    c = _ip_app(1).test_client()
    # the client forged "1.2.3.4"; our proxy appended the real address it saw, 203.0.113.7
    r = c.get("/_ip", headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.7"}, environ_base={"REMOTE_ADDR": "10.0.0.2"})
    assert r.text == "203.0.113.7"


def test_rate_limits_cannot_be_dodged_by_rotating_a_forged_header(app):
    app.config["RATE_LIMITS"] = dict(app.config["RATE_LIMITS"], contact_ip=(2, 3600))
    c = app.test_client()
    codes = [c.post("/contact", data={"website": "x"}, headers={"X-Forwarded-For": f"9.9.9.{i}"}).status_code for i in range(4)]
    assert codes[:2] == [302, 302] and codes[2:] == [429, 429]
