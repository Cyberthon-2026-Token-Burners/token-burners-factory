# Sandbox image for the python-*-core environments: stock slim + the test runner the gate needs.
# SAST is handled generically by the separate Semgrep image, so no bandit here.
FROM python:3.12-slim

# Corporate root CA (see go.Dockerfile): trust it BEFORE the pip install below so the restore works
# behind a TLS-intercepting proxy. Safe no-op when no cert is staged (dir present via certs/.gitkeep).
COPY certs/ /usr/local/share/ca-certificates/
RUN command -v update-ca-certificates >/dev/null && update-ca-certificates || true

RUN pip install --no-cache-dir pytest
# Writable HOME/cache for the non-root --user the adapter runs as (avoids mkdir /.cache EPERM).
# REQUESTS_CA_BUNDLE/PIP_CERT point pip+requests at the system store (they default to certifi's
# own bundle, which would NOT carry the corp root).
ENV HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    XDG_CACHE_HOME=/tmp/.cache \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt
