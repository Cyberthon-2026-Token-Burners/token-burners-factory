# Sandbox image for the node-20-web environment. `npm test` / `npm` are built into the base; SAST is
# the generic Semgrep image. Writable HOME/npm cache for the non-root --user run.
FROM node:20-alpine

# Corporate root CA (see go.Dockerfile): trust it BEFORE any npm restore. Safe no-op when no cert is
# staged (dir present via certs/.gitkeep).
COPY certs/ /usr/local/share/ca-certificates/
RUN command -v update-ca-certificates >/dev/null && update-ca-certificates || true

# NODE_EXTRA_CA_CERTS points node/npm at the system store (npm uses its own CA handling otherwise).
ENV HOME=/tmp \
    npm_config_cache=/tmp/.npm \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
