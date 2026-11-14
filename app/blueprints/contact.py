from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import ContactMessage
from ..services import notify, rate_limit
from ..validation import contact_form

bp = Blueprint("contact", __name__)

THANKS = "Thanks, we will reply soon."


@bp.get("/contact")
def page():
    return render_template("contact.html", form={}, errors={})


@bp.post("/contact")
def send():
    origin = request.form.get("origin")
    back = url_for("shop.home", _anchor="contact") if origin == "home" else url_for("contact.page")
    rate_limit.enforce("contact_ip", rate_limit.ip_key())                  # 10 an hour from one address
    if request.form.get("website"):                                        # the honeypot: people never fill it
        flash(THANKS, "success")
        return redirect(back)
    data, errors = contact_form(request.form)
    if errors:
        return render_template("contact.html", form=data, errors=errors), 400
    rate_limit.enforce("contact_email", "email:" + notify.contact_hash(data["email"]))     # 3 an hour per sender
    msg = ContactMessage(first_name=data["first_name"], last_name=data["last_name"], email=data["email"],
                         subject=data["subject"], body=data["message"], consent=True)
    db.session.add(msg)
    db.session.commit()
    current_app.logger.info("Contact message %s received.", msg.id)            # an id only, never the content
    notify.notify_owner_contact(msg)
    flash(THANKS, "success")
    return redirect(back)
