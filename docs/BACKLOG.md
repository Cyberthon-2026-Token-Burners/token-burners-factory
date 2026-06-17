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

## 3. TASK-01 mandated baseline artifacts don't survive the run — ✅ RESOLVED
**Was:** the Developer wrote code + `README.md` but skipped non-code contracted files (`.gitignore`,
`LICENSE`), and nothing verified the contract was complete (confirmed in `run_bb7a…`: those two
missing across all cycles). `finalize_transaction` commits the whole staged tree, so the files were
simply never created.
**Fixed by:** `_missing_contract_files(ctx)` in `runner.py` (non-test `files_to_modify` paths absent
from the working tree) + a fast-fail reroute in the Developer loop that re-invokes the dev with the
missing-file list (no functional budget; soft fall-through at the cap); plus a `developer.md`
CONTRACT COMPLETENESS guardrail to create EVERY contracted file incl. `.gitignore`/`LICENSE`/manifests.

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

## 8. [P2] Misleading gate failure surface buries the real error — ✅ RESOLVED
**Was:** `[GATE][FUNCTIONAL-TESTS] Failure raw output:` showed only `go: no module dependencies to
download` — a benign exit-0 stderr line from the `go mod download` restore phase — burying the real
test/compile errors.
**Fixed by:** `run_qa_unit_tests` / `run_build_gate` now keep **successful**-restore output OUT of the
returned failure context (debug-logged only); the failure lines are exclusively the test/build phase's
output. Restore output is still surfaced when restore itself fails.

---
New items from `run_3dc1e2043ea74ed082f47ec1744e4d8e` (Go `json2csv`, `CIRCUIT BREAKER OPEN` after 4
cycles — both gates red EVERY cycle). Root cause: QA writes a root-level `main_test.go` declared
`package converter` colocated with `main.go` (`package main`) → `could not import main (cannot import
"main")`, the same build failure every cycle. The Reviewer correctly flags it as a zombie, but the
disposal is undone by regeneration within the same QA node run. (The Reviewer's cycle-1 `go.mod module
== "main"` / "circular imports" diagnosis was a hallucination — `go.mod` is `github.com/godeltech/jsonconv`.)

## 9. [P0] QA emitted a wrong-package test (root `main_test.go` as `package converter`) — ✅ RESOLVED (reframed)
**Was:** every cycle `go test ./...` failed with `could not import main (cannot import "main")` — a root
`main_test.go` declared `package converter` next to `main.go`'s `package main`. The original fix (extend
the Go package guard to rewrite a wrong-but-present clause) was rejected as per-language hardcode.
**Fixed by (ADR 0014):** made test correctness skills-driven and DE-HARDCODED the QA agent instead of
adding more mechanical rewriting. Removed the Go package guard, the Python-only AST merge, the
`env_language=="go"` branch, and the `uses_ast`/`fence_lang` profile keys; QA now has ONE language-neutral
whole-file assembly path. Added **TEST-FILE IDENTITY FIDELITY** + **Thin / untestable module** rules to
`prompts/system/qa.md`, concrete package/namespace/placement idioms to `go_qa.md`/`python_qa.md`/
`dotnet_qa.md`, and `reviewer.md` case **(c) WRONG TEST PACKAGE/NAMESPACE** so a slip-through is caught by
the compile gate and routed to QA (not the Developer → no deadlock). Partly addresses #11.

## 10. [P0] Zombie disposal is a no-op — QA regenerates the file it was told to delete
**Symptom:** log shows `🗑️ Zombie test disposed: main_test.go` then, same cycle,
`QA generated test files: [...main_test.go...]` — the Reviewer's `zombie_tests_to_delete` verdict can
never stick, so the breaker is inevitable.
**Cause:** in `run_qa_agent_node` ([qa.py:226](src/executor/agents/qa.py#L226)) disposal runs BEFORE
the generation loop, and the disposed module is still in `target_modules` (derived from
`files_to_modify` via `derive_test_target`), so QA recreates the identical test every cycle.
**Fix direction:** feed `zombie_tests_to_delete` into generation as a hard exclusion — drop any module
whose derived test path is a flagged zombie from `target_modules` (and skip writing it), so a
condemned test file is not resurrected. Disposal must persist across regeneration.

## 11. [P1] Reviewer hallucinates production defects not present in the gate output
**Symptom:** cycle 1 `code_quality_approved=false` + `dev_diagnostic_payload` "rename go.mod module
from `main`, fix circular imports" — none of which exist (`go.mod` is `github.com/godeltech/jsonconv`,
imports are correct). Burned a Developer reroute on a phantom; the real fault was entirely in the test
file.
**Fix direction:** constrain the Reviewer prompt so `code_quality_approved=false` / `dev_diagnostic_payload`
must cite a verbatim line from the actual gate output (build/test/SAST), not inferred structure; when
the only failing file refs are test files, the production verdict must default to approved.

## 12. [env] Build the Semgrep sandbox image before runs (operational, not code) — ✅ RESOLVED
**Was:** `[GATE][SAST-SECURITY]` FAILED with `pull access denied for sdlc-sandbox/semgrep` — the image
wasn't built; AND the build itself failed: `docker/semgrep.Dockerfile` pinned `SEMGREP_RULES_TAG=v1.92.0`,
but the `semgrep-rules` repo carries NO tags (it is versioned separately from the CLI), so
`git clone --branch v1.92.0` → `Remote branch v1.92.0 not found`.
**Fixed by:** pinning a commit SHA on the stable `release` branch (`SEMGREP_RULES_REF=818d4cc…`) and
fetching it directly (`git init` + `git fetch --depth 1 origin <SHA>` + `checkout FETCH_HEAD`) — fully
reproducible, no dependency on a tag/moving branch. Verified: image builds, 6 rule dirs + 921 rules
vendored, scan runs `--network none`. Still consider a preflight image-existence check (see below).

---
New items from `run_410195801a124f369ccb6c6052fb5257` (Python `json2csv`-style; Developer succeeded
exit 0 but the post-Developer guardrail/snapshot misbehaved). The Developer created a VALID
`requirements.txt` and ran `python -c …`/`pip install`, which produced `__pycache__/*.pyc`.

## 13. [P1] Doc guardrail flags valid manifests/config as "undocumented" — must exempt non-source files
**Symptom:** `[GUARDRAIL] 1 undocumented new file(s): ['requirements.txt']` → fast-fail reroute to the
Developer, even though `requirements.txt` is a legitimate, correctly-formed Python dependency manifest.
**Cause:** `enforce_documentation_guardrail` ([runner.py:433](src/executor/runner.py#L433)) flags ANY
uncontracted, newly-added file whose top `GUARDRAIL_TOP_LINES` carry no comment lead-in. Manifests /
lockfiles / config (`requirements.txt`, `go.mod`/`go.sum`, `package.json`, `*.csproj`, `tsconfig.json`)
and doc artifacts often can't or shouldn't carry an architectural-justification comment — the guardrail
is meant to catch hallucinated/orphan CODE files, not infra.
**Fix direction (generic, all envs):** restrict guardrail candidates to actual stack SOURCE files via the
registry SSOT `is_testable_source(env_id, rel)` (True only for real source; already filters
docs/config/markers/lockfiles). Non-source files are never required to carry a justification comment.
Preserves the guardrail's intent for genuinely uncontracted source the Developer adds without a comment.

## 14. [P1] Build artifacts (`__pycache__/*.pyc`) pollute the production snapshot when no `.gitignore` exists — ✅ RESOLVED (TPM-level)
**Was:** `[SNAPSHOT] Captured 9 production file(s)` included `src/__pycache__/*.pyc` — bytecode the
Developer's `python -c`/`pip install` generated, staged by `git add -A` because the business ticket's
clone of `main` had no `.gitignore`. A generic engine-side artifact filter was REJECTED (no per-stack
hardcode in the snapshot).
**Fixed by (TPM):** the planner now emits a dedicated **`TASK-00` repository-preparation** ticket that
runs FIRST and idempotently verifies presence+currency of `.gitignore`/`README.md`/`LICENSE` (creating/
reconciling them); all business tickets start at `TASK-01` and are forbidden from carrying baseline
files. A complete, env-tailored `.gitignore` established by `TASK-00` keeps later business tickets'
snapshots clean — no engine filter.
**Limitation (by design):** each ticket runs in an isolated `git clone --depth 1` of `main`
([runner.py bootstrap_session](src/executor/runner.py)), so `TASK-00`'s `.gitignore` only protects a
later business ticket once `TASK-00` is run and merged to `main` before that ticket clones. A single
isolated business-ticket run against a baseline-less `main` can still pollute — accepted trade-off of
the TPM-only approach (no generic filter, per decision).
