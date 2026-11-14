"""Delivery adapters for order messages, in the style of the Razorpay adapter: each one is configured from the
environment, says whether it is usable, and either delivers a message or raises SendError with a short reason that
holds no secret (no token, no password, no message body).

* EmailChannel    stdlib smtplib, STARTTLS on by default (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM)
* WhatsAppChannel Meta WhatsApp Cloud API over HTTPS with an approved template (WHATSAPP_TOKEN,
                  WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_TEMPLATE_NAME, WHATSAPP_LANG); business-initiated messages
                  must use a template, so the thank-you, invoice link and guide link travel as template parameters
* OutboxChannel   the safe default: nothing leaves the server; the rendered message stays in the outbox with status
                  "not_configured" and the admin can read it under Admin -> Messages
"""
import json
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from flask import current_app

from ...validation import has_line_break


class SendError(Exception):
    """Delivery failed. The text is short and safe to store and show to an admin."""


class NotConfigured(Exception):
    """The channel has no credentials; the message stays in the outbox."""


def _clean_header(value, limit=150):
    """A header value with every line break removed (header injection) and a length cap."""
    return "".join(ch for ch in (value or "") if ch not in "\r\n\x00  ")[:limit]


class EmailChannel:
    name = "email"

    def __init__(self, cfg=None):
        c = cfg or current_app.config
        self.host, self.port = c["SMTP_HOST"], int(c["SMTP_PORT"])
        self.user, self.password = c["SMTP_USER"], c["SMTP_PASSWORD"]
        self.sender = c["SMTP_FROM"] or c["SMTP_USER"]
        self.starttls = c["SMTP_STARTTLS"]

    @property
    def configured(self):
        return bool(self.host and self.sender)

    def build(self, to, subject, text, html=""):
        if has_line_break(to) or not to:
            raise SendError("recipient address is not valid")
        msg = EmailMessage()
        msg["Subject"] = _clean_header(subject)
        msg["From"] = _clean_header(self.sender, 190)
        msg["To"] = _clean_header(to, 190)
        msg["Date"] = formatdate(localtime=False)
        msg["Message-ID"] = make_msgid(domain=(self.sender.rsplit("@", 1)[-1] or "localhost"))
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        return msg

    def send(self, to, subject, text, html=""):
        if not self.configured:
            raise NotConfigured()
        msg = self.build(to, subject, text, html)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                smtp.ehlo()
                if self.starttls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                if self.user:
                    smtp.login(self.user, self.password)
                smtp.send_message(msg)
        except smtplib.SMTPAuthenticationError:
            raise SendError("the mail server refused the login") from None
        except smtplib.SMTPRecipientsRefused:
            raise SendError("the mail server refused the recipient") from None
        except (smtplib.SMTPException, OSError) as exc:
            raise SendError(f"mail server error ({type(exc).__name__})") from None
        return "smtp"


class WhatsAppChannel:
    name = "whatsapp"

    def __init__(self, cfg=None):
        c = cfg or current_app.config
        self.token, self.phone_id = c["WHATSAPP_TOKEN"], c["WHATSAPP_PHONE_NUMBER_ID"]
        self.template, self.lang = c["WHATSAPP_TEMPLATE_NAME"], c["WHATSAPP_LANG"]
        self.base = c["WHATSAPP_API_BASE"].rstrip("/")

    @property
    def configured(self):
        return bool(self.token and self.phone_id and self.template)

    def payload(self, to, params):
        if not (isinstance(to, str) and to.startswith("+") and to[1:].isdigit() and 8 <= len(to) - 1 <= 15):
            raise SendError("the WhatsApp number is not valid")           # checked before any API call
        return {
            "messaging_product": "whatsapp", "to": to[1:], "type": "template",
            "template": {"name": self.template, "language": {"code": self.lang},
                         "components": [{"type": "body",
                                         "parameters": [{"type": "text", "text": str(p)[:1000]} for p in params]}]},
        }

    def send(self, to, params):
        if not self.configured:
            raise NotConfigured()
        body = json.dumps(self.payload(to, params)).encode()
        req = urllib.request.Request(f"{self.base}/{self.phone_id}/messages", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310 - fixed https base URL from config
                data = json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            code = ""
            try:
                code = str(json.loads(exc.read() or b"{}").get("error", {}).get("code", ""))[:12]
            except (ValueError, AttributeError):
                pass
            raise SendError(f"WhatsApp API refused the message (HTTP {exc.code}{', code ' + code if code else ''})") from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise SendError(f"WhatsApp API unreachable ({type(exc).__name__})") from None
        ids = [m.get("id") for m in data.get("messages", []) if isinstance(m, dict)]
        if not ids:
            raise SendError("WhatsApp API gave no message id")
        return str(ids[0])[:64]


def channel(name):
    """The real channel for "email" or "whatsapp" (it may not be configured)."""
    return EmailChannel() if name == "email" else WhatsAppChannel()
