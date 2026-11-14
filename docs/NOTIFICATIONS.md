# Order messages: email and WhatsApp

When a buyer pays, the store sends one message to the contact they chose at checkout (email or WhatsApp), if they ticked "Send my invoice and setup guide to this contact". The message holds a short thank-you note, the invoice, the setup guide for each project and where to download. The order page always shows the invoice and the setup guides too, so nothing depends on the message arriving.

Out of the box nothing is sent: with no email or WhatsApp settings the rendered message waits in **Admin → Messages** with the status "Not configured". You can open it, copy it to the buyer yourself, and press "I sent it by hand".

## How it works

* Nothing is sent at checkout. The message is created only after the payment is confirmed (`mark_paid` returned "paid").
* One message per order and channel (a unique key in the `messages` table), so the payment redirect, the Razorpay webhook and the API confirming the same payment never send twice.
* Delivery runs after the payment has been saved, and every error is caught: a failed send can never fail or undo a payment.
* A failed send is retried by the sweeper (`flask send-messages`, every minute in Docker Compose) after 2, 4, 8 and 16 minutes; after 5 attempts it stops and the order page says "We could not send this, it is on your order page below".
* A contact gets at most 3 messages a day. Checkouts that ask for messages are limited to 10 a day per address and 5 a day per account.
* Every message ends with a "stop" link. Pressing the button on that page puts the contact on a do-not-contact list (only a keyed hash is stored) and no further message is sent to it.
* Invoice and guide links in messages are signed, tied to one order and expire after 7 days (`/i/<token>`, `/g/<token>`); they are never cached or indexed.
* Raw contact values are never written to the logs. `flask anonymise-order PS-XXXXXXX` removes the name and contact from an order and its messages.

Statuses you will see in Admin → Messages: **Queued**, **Sent**, **Failed** (with a short reason, never a password or token), **Not configured**.

## Turn on email (Gmail)

1. Turn on 2-Step Verification on the Google account you want to send from.
2. Create an app password: Google Account → Security → App passwords → choose "Mail", copy the 16-character password.
3. Put these in `.env` (never commit it):

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=the-16-character-app-password
SMTP_FROM=you@gmail.com
SMTP_STARTTLS=true
PUBLIC_BASE_URL=https://your-store-address
```

4. Rebuild: `docker compose up -d --build --no-deps web sweeper`.
5. Buy something with the practice gateway using your own email and check that it arrives; the order page should say "Sent to y***@gmail.com".
6. If it does not arrive, open **Admin → Messages**: the outbox row says why, for example "the mail server refused the login" (the app password or `SMTP_USER` is wrong, or 2-Step Verification is off) or "mail server error (TimeoutError)" (the host or port is wrong, or the network blocks port 587). The sweeper retries after 2, 4, 8 and 16 minutes.

Any SMTP server with STARTTLS works the same way (port 587). The store also emails `CONTACT_EMAIL` when someone uses the contact form, once SMTP is set.

## Turn on WhatsApp (Meta WhatsApp Cloud API)

WhatsApp only lets a business start a conversation with an **approved message template**, so the store sends one template whose variables carry the buyer's name, the order number and the links.

1. Create a Meta developer account and an app of type "Business" at developers.facebook.com, and add the **WhatsApp** product.
2. In WhatsApp → API Setup, note the **Phone number ID** of your business number (the test number works for trying it with up to five verified recipients).
3. Create a **permanent access token**: Business Settings → Users → System users → add a system user, give it the WhatsApp app with `whatsapp_business_messaging` permission, generate a token. (The temporary token on the API Setup page expires in 24 hours.)
4. In WhatsApp Manager → Message templates, create a template:
   * Name: `order_paid` (or any name; put the same in `WHATSAPP_TEMPLATE_NAME`)
   * Category: **Utility**
   * Language: English (`en`; put the same code in `WHATSAPP_LANG`)
   * Body, with exactly these six variables in this order:

```
Hi {{1}}, thank you for your order {{2}}! Your project kit is paid for.
Invoice: {{3}}
Setup guide: {{4}}
Download from your order page: {{5}}
The invoice and guide links work for 7 days.
Stop these messages: {{6}}
```

   Variable meaning: {{1}} first name, {{2}} order number, {{3}} invoice link, {{4}} setup guide link, {{5}} order page link, {{6}} stop link. Submit it and wait for approval (usually minutes to a day).
5. Put these in `.env`:

```
WHATSAPP_TOKEN=the-permanent-token
WHATSAPP_PHONE_NUMBER_ID=the-phone-number-id
WHATSAPP_TEMPLATE_NAME=order_paid
WHATSAPP_LANG=en
PUBLIC_BASE_URL=https://your-store-address
```

6. Rebuild: `docker compose up -d --build --no-deps web sweeper`, then buy something with your own WhatsApp number.

If Meta refuses the message the order page says so and Admin → Messages shows the HTTP status and Meta's error code (for example 132001: the template name or language does not match; 131030: with the test number, the recipient is not on your list of up to five verified numbers). A number that is not `+` and 8 to 15 digits is refused before any call to Meta ("the WhatsApp number is not valid").

## Before you switch either on

* Set `PUBLIC_BASE_URL` to the address buyers use (with `https://` once you have it). Every link in a message is built from it; with the default `http://localhost:8000` the links only work on your own computer.
* Set `CONTACT_EMAIL` so the contact form can notify you, and `SELLER_NAME` / `SELLER_ADDRESS` for the invoice.
* Keep the sweeper running (`docker compose ps` shows `sweeper`): it retries failed sends and delivers anything still queued.
* The variables live in `.env` only. Never commit it, and never paste the app password or the WhatsApp token into an issue or a chat.

## Known limitations

* **Real WhatsApp delivery has not been verified**: it was tested only against a local fake of the Cloud API, because no Meta credentials were available. Real email delivery was tested only against a local fake SMTP server. Until you set the variables above, messages stay "Not configured" (or "Queued") and the buyer is told so truthfully.
* Replies to a WhatsApp message are not read by the store, so "reply STOP" does nothing; the stop link in every message is the way to opt out.
* The invoice is a receipt for a digital kit; no tax is itemised. If you are GST-registered set `SELLER_GSTIN` and check the invoice with your accountant.
