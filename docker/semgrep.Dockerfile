# Generic SAST image: Semgrep with rules VENDORED at build time so the gate runs fully OFFLINE
# (--network none). Stock `semgrep/semgrep` + `--config auto` calls semgrep.dev at runtime, which
# fails behind a corporate TLS proxy (the container's CA store lacks the corporate CA). Building here
# goes through the WSL/daemon trust store (which DOES have the CA), so the clone succeeds; at runtime
# no network is needed at all.
FROM semgrep/semgrep:1.92.0

# Pin the ruleset for reproducibility. Keep only the stacks we support to keep the image lean.
ARG SEMGREP_RULES_TAG=v1.92.0
RUN (command -v git >/dev/null 2>&1 || (apk add --no-cache git 2>/dev/null || (apt-get update && apt-get install -y --no-install-recommends git))) \
    && git clone --depth 1 --branch "${SEMGREP_RULES_TAG}" https://github.com/semgrep/semgrep-rules /tmp/semgrep-rules \
    && mkdir -p /opt/semgrep-rules \
    && for d in python go javascript typescript csharp generic; do \
         if [ -d "/tmp/semgrep-rules/$d" ]; then cp -r "/tmp/semgrep-rules/$d" /opt/semgrep-rules/; fi; \
       done \
    && rm -rf /tmp/semgrep-rules

# Run as the calling (non-root) user; rules live read-only in the image.
