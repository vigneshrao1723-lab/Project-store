# Security audit, v1.4

Re-run on branch `v1.4-final`, 15 November 2026, against a scratch copy only: the test suite, a scratch SQLite server,
a scratch Docker Compose stack (project `psv14scratch`, port 8097, MySQL data in a tmpfs) and a throwaway MySQL 8.4 on
port 3307. The live stack on port 8001 and its database were not touched.

The brief asked for "all 24 items" and then listed 18; all 18 are below. v1.3's new surface (contact form, `/i/<token>`,
`/g/<token>`, `/orders/<id>/invoice`, `/stop`, the outbox) and v1.4's changes (the shelf loop, the map, the new pages)
are included in every check.

Status: **PASS** (checked, nothing to change), **FIXED** (something failed and was changed in v1.4), **NOT VERIFIED**
(not run; never claimed). One finding is left **OPEN** for the owner to decide (item 6).

## Summary

| # | Item | Status |
|---|---|---|
| 1 | Security headers | FIXED (Cross-Origin-Resource-Policy and `object-src 'none'` added; Maps `frame-src` is the only relaxation) |
| 2 | Environment variables | FIXED (production startup now also refuses placeholder DB passwords and half-set or placeholder Razorpay keys; `WHATSAPP_API_BASE` was missing from `.env.example`) |
| 3 | Debug off | PASS |
| 4 | Admin routes | FIXED (route-walk test over the whole url_map added; nothing leaked) |
| 5 | Dependencies | FIXED (7 packages upgraded, base image pinned by digest; SQLAlchemy held, see notes) |
| 6 | Authentication | PASS, with one OPEN finding: registration says an email already has an account |
| 7 | Unused packages | FIXED (python-dotenv moved out of the runtime image) |
| 8 | User access (IDOR) | PASS (new tests for invoices, guide and invoice tokens, outbox and messages) |
| 9 | Exposed files | FIXED (tooling, compose file and MySQL init folder were inside the image) |
| 10 | Sanitize forms | PASS |
| 11 | Secure database | FIXED (the app connected as the schema owner; now a rows-only account) |
| 12 | XSS | PASS (payload tests extended to the contact form, admin views, order pages, invoice) |
| 13 | Password hashing and secrets | PASS |
| 14 | Rate limiting | FIXED (signed links, `/stop` and every API write had no limit; trusted-proxy count added) |
| 15 | Git leaks | FIXED (no secret in history; CI job, pre-commit hook and one checked false positive added) |
| 16 | API endpoints | PASS |
| 17 | CORS | PASS |
| 18 | Full audit | PASS: bandit, pip-audit, semgrep, ZAP baseline, OWASP mapping (0 failures; informational warnings explained) |

## Items

### 1. Security headers: FIXED

Evidence (`curl -sI` against gunicorn in the scratch Docker stack, `http://localhost:8097`):

| Response | Status | CSP | nosniff | frame-ancestors / X-Frame-Options | Referrer-Policy | Permissions-Policy | COOP | CORP | Cache-Control |
|---|---|---|---|---|---|---|---|---|---|
| `/` page | 200 | yes | yes | `'self'` / SAMEORIGIN | strict-origin-when-cross-origin | yes | same-origin-allow-popups | same-origin | (public) |
| `/static/css/main.css` | 200 | yes | yes | yes | yes | yes | yes | same-origin | no-cache |
| `/no-such-page` | 404 | yes | yes | yes | yes | yes | yes | same-origin | (public) |
| `/api/v1/products` (JSON) | 200 | yes | yes | yes | yes | yes | yes | same-origin | (public) |
| `/orders/<id>/invoice` (the download a buyer keeps), signed in | 200 | yes | yes | yes | **no-referrer** | yes | yes | same-origin | **no-store**, plus `X-Robots-Tag: noindex, nofollow` |
| `/orders/<id>`, `/orders`, `/cart`, `/api/v1/orders`, signed in | 200 | yes | yes | yes | yes | yes | yes | same-origin | **no-store**, `Vary: Cookie` |

The policy as served: `default-src 'self'; script-src 'self' https://checkout.razorpay.com; style-src 'self'; font-src 'self';
img-src 'self' data:; frame-src https://api.razorpay.com https://checkout.razorpay.com https://maps.google.com
https://www.google.com; connect-src 'self' https://lumberjack.razorpay.com https://api.razorpay.com; object-src 'none';
form-action 'self'; base-uri 'self'; frame-ancestors 'self'`. No `unsafe-inline`, no `unsafe-eval`, no `*`.

HSTS is sent only when `COOKIE_SECURE=true` (HTTPS): `tests/test_headers.py::test_hsts_only_when_cookies_are_secure`,
`tests/security/test_a1_headers.py::test_a1_hsts_is_sent_when_cookies_are_secure`.

Changed: `app/__init__.py:121` `security_headers` adds `Cross-Origin-Resource-Policy: same-origin` and
`object-src 'none'`, and `frame-src` gains exactly `https://maps.google.com https://www.google.com` for the contact map.
Tests: `tests/test_v14_contact_map.py::test_the_csp_is_exactly_the_v13_policy_plus_the_two_google_maps_frame_origins`
(asserts every directive on five response types), `::test_the_only_relaxation_since_v13_is_the_maps_frame_origins`,
`::test_every_response_says_its_resources_are_for_this_site_only`; CORP added to `REQUIRED_HEADERS` in
`tests/security/test_a1_headers.py`.

Not added on purpose: Cross-Origin-Embedder-Policy (`require-corp` would block the Razorpay Checkout frame and the
Google Maps frame; the site uses nothing that needs cross-origin isolation). COOP stays `same-origin-allow-popups`
because Razorpay opens bank pages in pop-ups. gunicorn sends `Server: gunicorn` (version not shown); informational.

### 2. Environment variables: FIXED

* `.env` and `.env.bak` are untracked: `git check-ignore -v .env .env.bak` -> `.gitignore:1:.env`, `.gitignore:2:.env.*`.
* `.env.example` lists every setting the app reads, with empty or placeholder values:
  `tests/security/test_v14_audit.py::test_e2_every_setting_the_app_reads_is_listed_in_env_example` (it found
  `WHATSAPP_API_BASE` missing; added). New in v1.4: `CONTACT_NAME`, `TRUSTED_PROXIES`, `DB_APP_PASSWORD`.
* Production startup refuses unsafe settings (`app/__init__.py:46` `config_problems`, raised at `:83`), naming the
  setting and never printing its value: a SECRET_KEY under 32 characters or a placeholder (was already there); **new:** a
  MySQL `DATABASE_URL` with an empty or placeholder password, only one of `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`,
  a placeholder Razorpay secret or webhook secret, a key id that is not `rzp_test_...` or `rzp_live_...`. Tests:
  `test_e2_unsafe_settings_are_named_without_printing_their_values` (9 cases),
  `test_e2_create_app_refuses_to_start_in_production_with_a_placeholder_db_password`, and the existing
  `tests/security/test_a2_secret_and_gateway.py`. There is no minimum length for the database password, so an
  existing real password can never block a restart.
* Nothing secret in the image or compose file: `docker image inspect psv14scratch-web --format '{{json .Config.Env}}'`
  shows only `PATH`, `LANG`, `GPG_KEY` (Python's release key), `PYTHON_VERSION`, `PYTHON_SHA256` and three
  `PYTHON*`/`PIP*` switches; `docker history --no-trunc` shows no build arguments; compose takes every password from
  `.env` with `${VAR:?}` (no defaults: `tests/test_headers.py::test_compose_has_no_database_password_defaults_and_requires_them`).
* Logs: secrets are never logged (`tests/security/test_a13_password_hashing.py::test_a13_passwords_are_not_written_to_logs`;
  the contact route logs an id only). `flask seed` prints a **generated** admin password once, on purpose, when
  `ADMIN_PASSWORD` is empty.

### 3. Debug off: PASS

`DEBUG` is never set in `Config` (`tests/security/test_a3_errors.py::test_a3_debug_is_off_by_default`); the image runs
`gunicorn wsgi:app` (`docker image inspect`: `Cmd=["gunicorn","wsgi:app","--bind","0.0.0.0:8000","--workers","3","--access-logfile","-"]`,
`test_a3_docker_runs_gunicorn_without_debug_or_reloader`); `grep -rn "debug=True\|DEBUG = True\|FLASK_DEBUG"` inside
the image finds nothing; `/console` answers 404 on the gunicorn container. Error pages carry no internals:
`test_a3_not_found_page_has_no_internals`, `test_a3_forced_500_page_has_no_internals`,
`test_a3_database_error_500_page_has_no_sql_or_paths`, and the new custom 404 and 500 pages:
`tests/test_v14_pages.py::test_the_404_page_helps_and_leaks_nothing`, `::test_the_500_page_is_plain_and_leaks_nothing`.

### 4. Admin routes: FIXED

New route walk, `tests/security/test_v14_audit.py`:
* `test_e4_route_walk_every_route_outside_the_public_list_needs_sign_in`: enumerates `app.url_map` (over 60 rules), fails
  on any rule that is neither in an explicit public allowlist nor under a protected prefix, and calls every method of
  every non-public rule signed out; each must answer 302 to `/login`, 401, 404 or 405. None leaked.
* `test_e4_route_walk_every_admin_route_refuses_a_customer`: every `/admin` and `/api/v1/admin` rule, every method,
  as a signed-in customer: 403 or 404.
* `test_e4_state_changing_admin_actions_are_post_only_and_need_csrf`: every admin POST without a CSRF token is refused
  (400), and no admin route uses PUT, PATCH or DELETE.
* `test_e4_the_public_list_matches_what_signed_out_visitors_really_get`: every allowlisted page answers 200, `/cart`
  sends a visitor to sign in, an invalid token answers 404.
The earlier `tests/security/test_a4_admin_routes.py` (anonymous and customer, all verbs) still passes.

### 5. Dependencies: FIXED

* `python -m pip_audit -r requirements.lock --disable-pip` and `-r requirements-dev.lock`: **No known vulnerabilities found**
  (before and after the upgrades).
* `pip list --outdated` found 10. Upgraded and tested: Flask-WTF 1.2.2 -> 1.3.0, gunicorn 23.0.0 -> 27.0.1,
  PyMySQL 1.1.1 -> 1.2.4, requests 2.33.0 -> 2.34.2, pytest 9.0.3 -> 9.2.0, python-dotenv 1.2.2 -> 1.2.4, and the
  transitive coverage 7.17.3 and stevedore 5.10.0. **Held:** SQLAlchemy 2.0.36 (2.1.8 exists). Its new compiled
  extension is blocked by this Windows machine's Application Control policy, so the suite could not be run against
  it here; 2.0.36 has no known vulnerability. Upgrade it where the tests can run (CI or a Linux machine).
* Lock files regenerated with hashes under Python 3.12 (`docker run python:3.12-slim sh scripts/relock.sh`); the CI
  check (`relock` then `git diff --exit-code -- requirements.lock requirements-dev.lock`) reports no change.
* Base image: `python:3.12-slim` is Python 3.12.16 on Debian 13 (trixie), built 5 Nov 2026. It is now pinned by digest
  (`FROM python:3.12-slim@sha256:5e2bdb1b...`) so every build starts from the same bytes. Dependabot has open branches
  for newer images and packages (`origin/dependabot/...`); the 3.15 image was not adopted (CI and the lock target 3.12).
* JavaScript: no third-party library is bundled or served (`app/static/js/` is the store's own code). The only
  third-party script is Razorpay Checkout (`https://checkout.razorpay.com/v1/checkout.js`), loaded only on the payment
  page when real Razorpay keys are set, and allowed by name in `script-src`.

### 6. Authentication: PASS, one OPEN finding

* Password policy: 8 to 128 characters (`app/validation.py` `MIN_PASSWORD`, `MAX_PASSWORD`; `test_a6_minimum_password_length_is_enforced`,
  `tests/security/test_a6_password_length.py`). No composition rules, in line with NIST SP 800-63B.
* Lockout: 5 failures per email and address lock sign-in for 10 minutes, and 20 failures per address across all emails
  (`app/services/login_throttle.py`, `login_ip` limit; `test_a14_login_is_limited_per_address_not_only_per_email`).
* Session fixation: `start_session` clears the session before `login_user` (`app/blueprints/auth.py:29`;
  `test_a6_a_cookie_planted_before_login_does_not_become_signed_in`, `test_a6_csrf_token_is_rotated_at_login`).
* Logout and password change revoke every session: logout rotates the account's session token (`auth.py:116`);
  `set_password` does the same (`test_a6_logout_invalidates_the_old_session_cookie`,
  new `test_e6_changing_the_password_ends_other_sessions`).
* Cookies: HttpOnly, SameSite=Lax, Secure with `COOKIE_SECURE`, 14 days for "keep me signed in"
  (`test_a6_session_cookie_flags`, `test_a6_session_cookie_is_secure_when_configured`,
  `test_a6_remember_me_cookie_has_the_same_flags_when_secure_cookies_are_configured`).
* Constant time: payment and webhook signatures use `hmac.compare_digest` (`app/services/payments.py:106`, `:114`);
  password checks use Werkzeug's `check_password_hash`; an unknown email still pays for one scrypt hash
  (`test_a6_a13_unknown_email_login_still_runs_a_password_hash`).
* Generic sign-in error ("That email and password don't match.") for an unknown email and a wrong password
  (`test_a6_login_error_is_identical_for_unknown_email_and_wrong_password`). The contact form reveals nothing about
  accounts (`test_e6_the_contact_form_reveals_nothing_about_accounts`).
* **OPEN: registration reveals an existing account.** `/register` answers "An account with this email already
  exists. Sign in instead." (`app/blueprints/auth.py:54`). Without email verification there is no honest way to hide
  this (a successful sign-up always looks different from a refused one). Mitigated by the registration limit (10 an hour
  per address). The fix is email verification at sign-up (send a link; show the same "check your email" page whether or
  not the address exists), which needs SMTP switched on. Left for the owner to decide; not claimed as fixed.

### 7. Unused packages: FIXED

`deptry` 0.25.1 in a separate tools virtualenv (nothing installed globally or into the project venv):
`deptry . --requirements-files requirements.txt --known-first-party app` reported PyMySQL, cryptography, gunicorn and
python-dotenv as unused imports. Checked by hand: PyMySQL is loaded by name through `mysql+pymysql://`; cryptography is
what PyMySQL needs for MySQL 8.4's default `caching_sha2_password` sign-in (the scratch stack used it); gunicorn is the
image's command; **python-dotenv is unused at run time** (only local `flask` commands read `.env`, and the image never
has one). It moved from `requirements.txt` to `requirements-dev.txt`; both locks were regenerated; the full suite and
the Docker build pass. The dev-only tools deptry lists (pytest, pytest-cov, pip-audit, bandit) are run by CI as
commands. The existing `test_a7_every_third_party_module_the_app_imports_is_declared_in_requirements` still passes.

### 8. User access (IDOR): PASS

Existing `tests/security/test_a8_access_control.py` (order pages, API orders, pay, cancel, verify, cart) plus new tests
in `tests/security/test_v14_audit.py`:
* `test_e8_another_user_cannot_open_an_invoice_or_order_or_its_download`: another buyer gets 404 for
  `/orders/<id>/invoice`, `/orders/<id>` and `/api/v1/orders/<id>`; the order is not in their list; the owner gets 200.
  Download links appear only on the owner's paid order and in the owner's API response
  (`test_a16_public_api_never_exposes_download_links`).
* `test_e8_signed_links_are_scoped_to_one_order_and_one_document`: an invoice token does not open the guide and the
  reverse; a tampered token, a token for another order id and a token whose order number does not match all get 404.
* `test_e8_expired_links_are_refused`: past `MESSAGE_LINK_DAYS` the same token gets 404.
* `test_e8_messages_and_the_outbox_are_admin_only`: `/admin/messages` and `/admin/outbox/<id>` give a customer 403 or
  404 and a visitor a redirect to sign in.

### 9. Exposed files: FIXED

Requested from the gunicorn container (`curl`/`requests`, anonymous): `/.env`, `/.env.example`, `/.git/config`,
`/.git/HEAD`, `/app/config.py`, `/config.py`, `/wsgi.py`, `/requirements.txt`, `/requirements.lock`,
`/docker-compose.yml`, `/Dockerfile`, `/backup.sql`, `/dump.sql`, `/static/../app/config.py`,
`/static/..%2fapp%2fconfig.py`, `/static/%2e%2e/.env`, `/static/js/app.js.map`, `/static/css/main.css.map`,
`/__pycache__/`, `/app/__pycache__/config.cpython-312.pyc`, `/static/`, `/static/js/` (no directory listing),
`/instance/store.db`, `/migrations/env.py`, `/tests/conftest.py`, `/.dockerignore`, `/server-status`, `/console`,
`/admin/../.env`, `/.DS_Store`, `/docs/SECURITY_AUDIT.md`: **all 31 answered 404.**

Image contents (`docker run --rm --entrypoint sh psv14scratch-web -c 'ls -A /srv/app; find / -xdev ...'`): no `.env`,
`.git`, `tests`, `docs`, `*.db`, `*.map` or private keys. **Found and fixed:** `.playwright-mcp` (local browser
scripts), `CLAUDE.md`, `docker-compose.yml`, the `docker/` MySQL init folder and `pytest.ini` were copied in; they are
now in `.dockerignore`, and `tests/security/test_a9_exposed_files.py::test_a9_docker_build_context_excludes_development_files`
checks them. Only `/static/<path>` is served as files (`test_a9_only_the_static_folder_is_exposed_as_static`).

### 10. Sanitize forms: PASS

Every form field is checked on the server for type, length and characters: contact form (`app/validation.py:165`
`contact_form`: lengths, one-line fields, email shape), WhatsApp numbers normalised to E.164 (`:141`
`normalise_whatsapp`), registration and sign-in lengths, checkout name and phone lengths, admin product form
(`app/services/products.py` `validate_product`). Line breaks and NUL are refused in anything that can reach an email
header (`:132` `has_line_break`; `tests/test_contact.py`, `tests/test_order_messages.py`). Templates autoescape; no
template uses `|safe`, and the only `Markup()` calls are the cover helper and the setup-guide renderer, both of which
escape first (`tests/security/test_v14_audit.py::test_e12_e10_no_template_marks_user_data_safe`). Tests:
`tests/security/test_a10_input_validation.py` (11 tests), `tests/test_validation.py`.

### 11. Secure database: FIXED

Before v1.4 the web app and the sweeper connected as `store`, which MySQL's image creates with `ALL PRIVILEGES` on
`project_store` (DROP included).
* Now: `docker/mysql-init/10-app-user.sh` creates `store_app` on a new volume with `SELECT, INSERT, UPDATE, DELETE` on
  `project_store` only. The web app and the sweeper use it; a one-shot `migrate` service runs migrations and the seed
  as `store` and exits; `docker-entrypoint.sh` migrates only when `RUN_MIGRATIONS=1`.
* Evidence (scratch stack): `SHOW GRANTS FOR 'store_app'@'%'` -> `GRANT USAGE ON *.*` and
  `GRANT SELECT, INSERT, UPDATE, DELETE ON project_store.*`. As `store_app`: `SELECT COUNT(*) FROM products` -> 4;
  `DROP TABLE inventory_log`, `ALTER TABLE products ...`, `CREATE TABLE ...` -> ERROR 1142 denied; `SELECT * FROM mysql.user`
  -> denied; `SELECT LOAD_FILE('/etc/passwd')` -> NULL; `GRANT ...` -> ERROR 1044. The running web container reports
  `SELECT CURRENT_USER()` = `store_app@%`.
* Port 3306 is not published (`test_a11_mysql_port_is_not_published_to_the_host`); credentials come from `.env`
  (`test_a11_database_passwords_come_from_env_with_no_weak_defaults`); no SQL is built from strings
  (`test_a11_no_sql_is_built_from_strings`); search, sort and category resist injection
  (`test_a11_a17_search_sort_and_category_resist_sql_injection`). New: `test_e11_*` (3 tests).
* **The live database needs the account created by hand** (an init script never runs on an existing volume): see
  `docs/RELEASE_STEPS_v1.4.md`, step 0.
* Backup and restore: `docs/RELEASE_STEPS_v1.4.md` (dump inside the container with `mysqldump --single-transaction`,
  copy out byte for byte, restore with `mysql < file`), as in earlier releases.

### 12. XSS: PASS

New payload tests (`<script>alert(1)</script>`, `"><img src=x onerror=alert(1)>`, `' onmouseover='alert(1)`,
`<svg onload=alert(1)>`, `javascript:alert(1)`) in `tests/security/test_v14_audit.py`:
`test_e12_search_and_the_404_page_escape_the_query`,
`test_e12_the_contact_form_escapes_what_it_shows_back_and_what_the_admin_sees` (the re-shown form and Admin ->
Messages), `test_e12_names_on_orders_are_escaped_on_the_order_page_invoice_and_admin`,
`test_e12_a_javascript_url_never_becomes_a_link`. Existing: `tests/security/test_a12_xss.py`,
`tests/test_title_escaping.py`, `tests/test_headers.py` cover titles. The CSP has no `unsafe-inline` or `unsafe-eval`,
and the Maps `frame-src` origins are the only relaxation (item 1). The map script refuses any frame source that is not
`https://maps.google.com/` (`tests/test_v14_contact_map.py::test_the_map_script_refuses_any_source_that_is_not_google_maps`).

### 13. Password hashing and secrets: PASS

scrypt `N=2^17, r=8, p=1` (`app/config.py:35`; `test_a13_scrypt_cost_meets_owasp_minimum`), salted and upgraded on next
sign-in when the cost rises. No MD5 or SHA-1 anywhere in `app/`
(`test_e13_no_md5_or_sha1_and_secrets_are_compared_in_constant_time`). The do-not-contact list and the per-contact
message limit store only a keyed HMAC-SHA256 of the contact (`app/services/notify/__init__.py:35`;
`test_e13_the_do_not_contact_list_and_message_limits_hold_only_keyed_hashes`). Signed links are itsdangerous tokens
(never stored). The per-account session token is stored as is: it is a random revocation nonce, useless without
`SECRET_KEY`.

### 14. Rate limiting: FIXED

Already limited: register, sign-in (per email and address, and per address), checkout (page and API), payment
verification, contact form (per address and per sender), checkouts asking for messages (per address and account).
**Not limited before v1.4, now limited:** the signed links `/i/<token>`, `/g/<token>` and `/stop/<token>` (GET and POST),
60 per 10 minutes per address (`app/blueprints/orderdocs.py:27`, `:36`, `:63`, `:70`), and every API write
(POST, PUT, PATCH, DELETE), 120 per 10 minutes per account or address (`app/blueprints/api.py:25` `limit_writes`).
Tests: `test_e14_signed_links_and_the_stop_page_are_rate_limited`, `test_e14_api_writes_are_rate_limited_per_account`,
plus `tests/security/test_a14_rate_limits.py` and `tests/test_rate_limit.py`.

Client address behind a proxy: by default `X-Forwarded-For` is not believed (the TCP peer is the address). New
`TRUSTED_PROXIES` (`app/config.py`, default 0) wraps the app in `ProxyFix(x_for=n, x_proto=n)` with exactly that hop
count (`app/__init__.py:89`), so only the hops the owner's proxies appended are believed. Tests:
`tests/test_v14_contact_map.py::test_by_default_a_forged_x_forwarded_for_is_ignored`,
`::test_with_one_trusted_proxy_only_the_hop_it_added_is_believed`,
`::test_rate_limits_cannot_be_dodged_by_rotating_a_forged_header`. Set `TRUSTED_PROXIES=1` only when one reverse proxy
(nginx, Caddy) sits in front and does not pass client-supplied `X-Forwarded-For` through unchecked.

### 15. Git leaks: FIXED

`gitleaks` v8.30.1 in Docker, read-only mount: `gitleaks git /repo --log-opts="--all" --redact` over **93 commits on
every local and remote branch**: 1 finding, `generic-api-key` in `.env.example` line 9 of the first commit `d13591a`.
Checked by hand: the rule ran across a line break from the empty `RAZORPAY_WEBHOOK_SECRET=` into
`RESERVATION_MINUTES=15`; all three Razorpay values in that commit are empty. **No secret was ever committed; nothing
to rotate.** Its fingerprint is in `.gitleaksignore` with that explanation; the re-run reports "no leaks found".
`gitleaks dir /repo --redact` over the working tree: 2 findings, `SECRET_KEY` in `.env` and in `.env.bak`, both
untracked and gitignored, as expected (values redacted, never printed). History was not rewritten.

Added: a `secrets` CI job (gitleaks over the whole history with `fetch-depth: 0`, then the tree; the build waits for it),
`scripts/hooks/pre-commit` (scans what is staged, in Docker; enable with `git config core.hooksPath scripts/hooks`) and
`.pre-commit-config.yaml` for the pre-commit tool. The hook is not switched on in this clone; that is the owner's choice.

### 16. API endpoints: PASS

Sign-in required except the public catalogue (`test_a16_every_non_public_api_route_requires_sign_in`); CSRF header on
every write, JSON errors for CSRF failures (`test_a16_api_writes_need_a_csrf_token`,
`test_a16_csrf_failures_on_the_api_are_json_too`); undeclared methods answer 405
(`test_a16_api_routes_reject_methods_they_do_not_declare`); only a JSON object is accepted (`json_body`), wrong types
give 4xx not 500 (`test_a16_json_bodies_of_the_wrong_type_give_4xx_never_500`); no mass assignment: checkout reads only
`billing_name`, `phone` and (v1.4) `accept_terms`, never a price (`test_a17_exploits`); admin product writes go through
`validate_product`'s field list; body size capped at 1 MB (`MAX_CONTENT_LENGTH`, 413) and lists capped
(`test_a16_list_endpoints_are_capped`); one error shape with no stack traces
(`test_a16_api_errors_are_json_with_the_documented_shape`, `test_a16_api_error_bodies_leak_no_internals`). v1.4: API
checkout requires `"accept_terms": true` (`tests/test_v14_pages.py::test_the_api_needs_accept_terms_true_exactly`).

### 17. CORS: PASS

No `Access-Control-*` header on any response, including a preflight `OPTIONS`; a credentialed cross-site POST is refused
by CSRF (`tests/security/test_a18_cors.py`, 4 tests). No endpoint needs CORS; if one ever does, it must use an
explicit origin allowlist, never `*` with credentials (stated in `docs/ARCHITECTURE.md`, "Security notes").

### 18. Full audit: PASS

| Tool | Command | Result |
|---|---|---|
| bandit 1.9.4 | `python -m bandit -r app wsgi.py -ll` | no medium or high findings. Low only: test-config placeholders and the scrypt method string flagged as "passwords", `random` for cover art; the one XML-escape import was replaced with `html.escape` |
| pip-audit 2.10.1 | `python -m pip_audit -r requirements.lock --disable-pip` (and the dev lock) | No known vulnerabilities found |
| semgrep (Docker, `semgrep/semgrep:latest`) | `semgrep scan --metrics=off --config p/python --config p/flask --config p/docker-compose --config p/secrets` over 135 files (venv, tests, docs excluded) | 0 findings, 0 errors. Rules confirmed live: the same configs flag 7 issues in a deliberately bad canary file |
| OWASP ZAP baseline (`ghcr.io/zaproxy/zaproxy:stable`) | `zap-baseline.py -t http://host.docker.internal:8097 -m 2` against the scratch Docker stack | 60 URLs, **FAIL 0**, PASS 61, WARN 7, all informational: suspicious comments (words in our JS comments), user-controllable attribute (`category` and `next` values, escaped), non-storable content (signed-in pages are `no-store` on purpose), modern web app, authentication and session requests identified, COEP missing (deliberate, item 1) |
| gitleaks | item 15 | no committed secret |
| deptry | item 7 | one unused runtime package moved to dev |

#### OWASP Top 10 (2021) mapping

| Risk | Where it is handled |
|---|---|
| A01 Broken access control | Items 4 and 8: route walk, admin role checks, per-owner queries, scoped signed links |
| A02 Cryptographic failures | Item 13: scrypt, HMAC signatures with constant-time compare, signed expiring links; HSTS and Secure cookies over HTTPS |
| A03 Injection | Items 10, 11, 12: ORM queries only, header-injection checks, autoescaped templates, strict CSP |
| A04 Insecure design | Server-side prices, one pending order per user, row locks, idempotent payment confirmation, practice gateway off by default |
| A05 Security misconfiguration | Items 1, 2, 3, 9: headers, startup refusals, debug off, nothing extra served or shipped |
| A06 Vulnerable and outdated components | Item 5: pip-audit gate in CI, hashed locks, pinned base image, Dependabot |
| A07 Identification and authentication failures | Item 6: lockout, session rotation, cookie flags, generic errors (one open finding) |
| A08 Software and data integrity failures | Hashed lock files, signed webhook, signed links, image digest pin, gitleaks gate |
| A09 Security logging and monitoring failures | Access log, ids only for contact messages, rotated container logs (3 x 10 MB); no alerting (not in scope) |
| A10 Server-side request forgery | The only server-side requests go to fixed Razorpay and Meta URLs from configuration; no user-supplied URL is fetched |

## Not verified in this audit

* A penetration test by a person; authenticated ZAP scanning (the baseline scan is unauthenticated and passive).
* Razorpay and Meta WhatsApp against real accounts (fakes only), and SMTP delivery.
* The least-privilege account on the **live** database (only on the scratch stack); it needs the release steps.
* SQLAlchemy 2.1.8 (held, see item 5).
* Whether the CI `secrets` job and the rest of the pipeline pass on GitHub (the branch has not been run there from this session).
