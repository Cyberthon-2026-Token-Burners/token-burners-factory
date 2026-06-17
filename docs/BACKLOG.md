# Backlog

Deferred fixes surfaced by the analysis of `run_9305be1f473f4337830b6d8bad0ddc29` (Go `json2csv`
pipeline that hit `CIRCUIT BREAKER OPEN` after 3 cycles). Item #1 (Developer CLI `cwd` sandbox
isolation) was fixed separately; the items below remain open.

## 1. Developer agent must never touch test files (`*_test.go` cascade) — ✅ RESOLVED
**Was:** with Go colocation QA writes `*_test.go` into the Developer's package; the Python-only test
filter let them leak into `production_code_snapshot`, so the doc guardrail flagged them and the dev
commented/deleted them.
**Fixed by:** env-aware `is_test_file()` SSOT used by `build_production_snapshot` (colocated tests
excluded for every language); a hard "TEST FILES ARE OFF-LIMITS" gate in `developer.md` (dependency-fix
rule scoped to production); SA/TPM prompts demarcate production vs test.

## 2. Gate execution environment is broken (compile/test/SAST must actually run) — ✅ RESOLVED
**Was:** stock images lacked the gate tools (no `pytest`/`bandit` in `python:3.12-slim`, no `gosec`
in `golang:1.23-alpine`) and the non-root run hit `mkdir /.cache: permission denied` (L797/L798).
**Fixed by:** per-env custom sandbox images (`docker/*.Dockerfile` + `scripts/build_sandbox_images.sh`)
carrying the test runner + writable `HOME`/cache; a generic **Semgrep** SAST image for ALL languages
(`SAST_IMAGE`/`SAST_CMD`); `docker_adapter.run_in_image` injecting `sandbox_env` + resource limits +
`--cap-drop ALL` + tmpfs; and a network-ON dependency-restore phase (`setup_cmd`) before the
network-OFF test phase in `gates.py`.

## 4. Restrict egress during the dependency-restore phase
**Why:** the dependency-restore phase (`setup_cmd`) runs with `--network bridge`. Package managers
execute install hooks (e.g. npm `postinstall`) → an exfiltration surface for LLM-authored code. Test
execution and SAST both stay `--network none` (SAST is now offline — see #6), so only restore keeps a
network window.
**Fix direction:** route restore through an egress-restricted proxy (allowlist package registries),
or vendor dependencies offline, so no phase has unrestricted network.

## 3. TASK-01 mandated baseline artifacts don't survive the run
**Symptom:** the contract included `.gitignore` and `LICENSE`, but the final repo tree had only
`README.md`, `go.mod`, `src/cmd/json2csv/main.go`, `src/internal/converter/converter.go`.
**Fix direction:** investigate why mandated TASK-01 files (`.gitignore`, `LICENSE`) are lost across
the develop/snapshot/retry cycles and ensure baseline artifacts persist to the final commit.

---
New items from `run_bb7a268aad844656910343c081e44f3e` (Go `json2csv`, `CIRCUIT BREAKER OPEN` after 3
cycles — both gates red EVERY cycle). The surfaced line (`go: no module dependencies to download`) was
a red herring; the real causes are below.

## 5. [P0] QA emits SYNTACTICALLY INVALID Go test files (no `package` clause) — ✅ RESOLVED
**Was:** every cycle both gates failed with `processor_test.go:1:1: expected 'package', found 'import'`
— QA test files started with `import (...)` and had no `package <name>` first line; QA regenerated the
same broken shape each cycle → breaker.
**Fixed by:** `go_qa.md` now hard-requires `package <pkg>` as the file's first line (with a shape
example + Assembly Contract placement); and a deterministic guard in `qa.py`
(`_ensure_go_package_clause` / `_derive_go_package`) prepends/hoists the `package` clause for Go test
files — package derived exactly from the colocated production sibling in the snapshot, else a
convention heuristic (`main` for `cmd/`, else dir basename). Guarantees parseable Go regardless of the
model's delta shaping.

## 6. [P1] Semgrep `--config auto` fails behind a corporate TLS proxy AND needs network — ✅ RESOLVED
**Was:** SAST failed every cycle with `semgrep.dev … CERTIFICATE_VERIFY_FAILED` — `--config auto`
fetched rulesets over a corporate MITM proxy whose CA the Semgrep container didn't trust.
**Fixed by:** a custom `sdlc-sandbox/semgrep` image (`docker/semgrep.Dockerfile`) with rules VENDORED
at build time; `SAST_CMD = semgrep scan --error --metrics off --config /opt/semgrep-rules /workspace`
run with `--network none`. Fully offline → no `semgrep.dev` call, no CA dependency, and the SAST
network window is closed (see #4).

## 7. [P1] Go compile gate parses colocated `_test.go` → leaks test errors to the Developer — ✅ RESOLVED
**Was:** `go build ./...` parses colocated `*_test.go` during package loading, so a broken test file
failed the compile gate and rerouted the Developer with test errors it's forbidden to fix.
**Fixed by:** `build_failure_is_test_only(environment_id, log_lines)` in `gates.py` (parses the
build output's `path:line` refs; True iff every referenced file is a test file per `is_test_file`).
The compile-gate branch in `runner.py` now breaks (falls through to the gates → Reviewer → QA channel)
on a test-only build failure instead of rerouting the Developer. Combined with #5 (parseable test
files), well-formed tests no longer fail the build at all.

## 8. [P2] Misleading gate failure surface buries the real error
**Symptom:** `[GATE][FUNCTIONAL-TESTS] Failure raw output:` showed only
`go: no module dependencies to download` — an INFORMATIONAL stderr line from `go mod download`
(exit 0, stdlib-only project), while the actual compile errors were elsewhere in the stream.
**Fix direction:** drop restore-phase stderr (and known-benign informational lines) from the
functional-failure context shown to the operator/Reviewer; surface the build/test phase's real
diagnostics. Keeps `_extract_failure_context` pointed at the true root cause.
