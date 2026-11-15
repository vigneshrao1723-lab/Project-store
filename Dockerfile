# Python 3.12.16 on Debian 13 (trixie), pinned by digest so every build starts from the same bytes; Dependabot
# proposes the next digest. Checked 15 Nov 2026 (docs/SECURITY_AUDIT.md, item 5).
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/app

# Dependencies first so this layer is cached until requirements change.
# The lock pins every package with a hash, so the build is reproducible and a tampered download is refused.
COPY requirements.lock .
RUN pip install --require-hashes -r requirements.lock

COPY . .

# Run as an unprivileged user.
RUN chmod +x docker-entrypoint.sh && useradd --system --uid 10001 store && chown -R store /srv/app
USER store

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"

ENTRYPOINT ["./docker-entrypoint.sh"]
# --no-control-socket: gunicorn 27 otherwise opens a control socket under the home directory, which the system user
# does not have (it logged "Control server error: Permission denied"); the store does not use that interface.
CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--no-control-socket"]
