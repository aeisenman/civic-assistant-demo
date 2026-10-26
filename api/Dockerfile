# API image: a uv builder stage installs the locked dependencies into /usr/local,
# and the runtime stage is a clean python:3.12.14-slim that copies that tree in —
# so uv itself (52 MB) never ships. Built by docker-compose.yml `api`; runtime
# config comes from .env (env_file).
#
# Base pinned to the exact patch (checked 2026-09-14: 3.12.14 is the newest
# 3.12.x slim tag on Docker Hub). `python:3.12-slim` moved under us between
# builds, which is fine for a laptop and wrong for an image someone deploys.

FROM python:3.15.0-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

# uv ships as a scratch image holding just the two binaries, so this costs a
# ~30 MB layer in a stage that is thrown away rather than 52 MB of pip install in
# the image that ships. Same 0.11.7 the previous `pip install uv==0.11.7` pinned.
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /bin/

WORKDIR /app

# Dependency layer only: pyproject declares `[tool.uv] package = false`, so there
# is no distribution to build and the app source is never needed here.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev


FROM python:3.15.0-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# The slim image lags Debian's security updates by days to weeks; Trivy gates
# the build on HIGH/CRITICAL with a published fix, so pull the fixes in here
# (gzip, pcre2, sqlite on 2026-09-16) rather than waiting for a new base tag.
RUN apt-get update \
    && apt-get -y --no-install-recommends upgrade \
    && rm -rf /var/lib/apt/lists/*

# UV_PROJECT_ENVIRONMENT=/usr/local above means the builder installed into the
# same prefix this image already uses for python, so one COPY puts uvicorn,
# fastapi and the rest on PATH with no venv to activate.
COPY --from=builder /usr/local /usr/local

# Nothing here needs root: uvicorn binds 8080 (not privileged) and the app only
# ever writes to the database and to S3. A container escape from a root process
# is a much shorter trip than from an unprivileged one.
RUN useradd --create-home --uid 10001 app

WORKDIR /app
COPY --chown=app:app . .

USER app

EXPOSE 8080

# /health is process + db + s3 + kb count and makes no model call. urlopen raises
# HTTPError on the 503 that /health returns when db or s3 is down, so "degraded"
# is an unhealthy container and compose holds `web` back behind it.
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=30 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# --proxy-headers + --forwarded-allow-ips: behind a TLS-terminating proxy the app
# otherwise sees scheme=http and app/api/auth.py issues the session cookie without
# Secure. "*" is right here because the only thing in front of this container is
# whatever the operator put there; COOKIE_SECURE overrides it either way.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
