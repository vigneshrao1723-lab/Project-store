FROM python:3.12-slim

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
CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
