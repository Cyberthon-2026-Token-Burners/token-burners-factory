# Backlog

Deferred fixes surfaced by the analysis of `run_9305be1f473f4337830b6d8bad0ddc29` (Go `json2csv`
pipeline that hit `CIRCUIT BREAKER OPEN` after 3 cycles). Item #1 (Developer CLI `cwd` sandbox
isolation) was fixed separately; the items below remain open.

## 1. Developer agent must never touch test files (`*_test.go` cascade)
**Symptom:** with Go colocation, QA writes `*_test.go` into the Developer's own package, and the
Developer edited, commented, then deleted them.
**Evidence (run audit log):**
- L206 — *"test files are missing `package` declarations … Applying the Dependency Fix Rule to add the declarations"* → dev edits tests.
- L218, L320–321, L331–336 — `enforce_documentation_guardrail` flags the QA tests as the dev's "undocumented new files" and forces architectural-justification comments into them.
- L623 — Ghost-File-GC then makes the dev delete both test files.
- L269 — contradicts the role_constraint *"You cannot edit tests."*
**Fix direction:**
- Exclude `*_test.go` (and language test patterns) from `build_production_snapshot`,
  `enforce_documentation_guardrail`, and Ghost-File-GC.
- Resolve the guard contradiction: the `CRITICAL DEPENDENCY FIX RULE` must NOT authorize editing test
  files; tests must not block the Developer's compile step.

## 2. Gate execution environment is broken for Go (compile/test/SAST must actually run)
**Symptom:** correct code still fails the gates; the Developer also self-reports builds it can't run.
**Evidence:**
- L797 — functional gate: `failed to initialize build cache at /.cache/go-build: mkdir /.cache: permission denied` (no writable `GOCACHE`/`HOME` after sandbox least-privilege hardening).
- L798, L885 — SAST gate: `gosec` binary absent from `golang:1.23-alpine`, so the Go SAST gate can never pass.
- L336 — Developer claims *"Build is clean"* although `go` is not on the host PATH (hallucinated self-build).
**Fix direction (`src/shared/core/docker_adapter.py`):**
- Provide writable `GOCACHE=/tmp/.cache`, `HOME=/tmp`, `GOPATH` (tmp) in the sandbox env so
  `go test ./...` can run under least-privilege.
- Ship `gosec` (custom Go image) or swap the Go SAST tool to one present in the image.
- Compilation/tests belong to the gate ONLY — the Developer agent should not attempt to build/test.

## 3. TASK-01 mandated baseline artifacts don't survive the run
**Symptom:** the contract included `.gitignore` and `LICENSE`, but the final repo tree had only
`README.md`, `go.mod`, `src/cmd/json2csv/main.go`, `src/internal/converter/converter.go`.
**Fix direction:** investigate why mandated TASK-01 files (`.gitignore`, `LICENSE`) are lost across
the develop/snapshot/retry cycles and ensure baseline artifacts persist to the final commit.
