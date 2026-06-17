# Sandbox image for the go-*-cli environments. `go test ./...` is built into the base; SAST is the
# generic Semgrep image. Only writable cache/HOME is baked so the non-root --user run never hits
# `mkdir /.cache: permission denied`.
FROM golang:1.23-alpine

# goimports powers the post-QA format pass (format_cmd): it removes unused imports — a HARD compile
# error in Go — so generated tests clear the compile gate without a Reviewer bounce. Install it onto
# the system PATH (runtime GOPATH=/tmp/go is an ephemeral tmpfs, so a $GOPATH/bin install would
# vanish). NON-FATAL: behind a TLS-intercepting corporate proxy the module fetch can't verify the
# proxy cert; rather than break the whole image build (build_sandbox_images.sh runs `set -e`), we
# warn and carry on — format_cmd falls back to the always-present `gofmt` when goimports is absent.
RUN GOPATH=/root/go GOBIN=/usr/local/bin go install golang.org/x/tools/cmd/goimports@latest \
    && rm -rf /root/go \
    || echo "WARN: goimports unavailable at build (offline/proxy) — format pass falls back to gofmt"

ENV HOME=/tmp \
    GOCACHE=/tmp/.cache/go-build \
    GOPATH=/tmp/go \
    GOMODCACHE=/tmp/go/pkg/mod
