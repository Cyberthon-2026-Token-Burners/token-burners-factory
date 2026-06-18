---
name: pipeline-fsm-loops
description: The executor FSM cycle — phase order, the five distinct loops (which consume retry budget, which don't), the two isolated feedback channels, and every termination state.
metadata:
  type: reference
---

# EXECUTOR FSM: CYCLE, LOOPS, CHANNELS, TERMINATION

SSOT: `src/executor/runner.py` `main()`. The control-plane (PO→SA→TPM) is linear with no loops; all
cycling lives here. Related: [[repo-module-map]], [[agent-contracts]], [[config-constant-convention]].

## Outer cycle
`for attempt in range(ctx.current_attempt, max_retries + 1)` — `max_retries = 3` (bare literal, the
[[config-constant-convention]] outlier). `current_attempt` is bumped **before** `save_checkpoint`, so a
resumed run never re-spends a cycle. Phase order inside one cycle:
1. financial breaker → reset BOTH feedback channels (save `prev_dev_trace`/`prev_qa_trace`, clear `error_trace`/`qa_error_trace` to `""`).
2. `skip_developer = regenerate_tests AND not prev_dev_trace AND review_report is not None`.
3. **QA generate + signature-lint** — only when `regenerate_tests` (see below).
4. **Developer + guardrails** — unless `skip_developer`.
5. financial breaker → **QA test-compile gate** → `parallel(run_qa_unit_tests, run_security_scan)`.
6. **Reviewer** → financial breaker → decision/routing → checkpoint.

`regenerate_tests = ctx.needs_test_regeneration()` (`models.py`): True when the last review rejected
tests **OR no test snapshot exists yet**. So on **cycle 1 QA generates tests BEFORE the Developer runs**
(contract-first); `production_code_snapshot` is empty then — QA works from the contract + topology only.

`all_gates_passed = qa_success ∧ sec_success ∧ code_quality_approved ∧ test_integrity_approved`.
On `not all_gates_passed`: `error_trace ← dev_diagnostic_payload`, `qa_error_trace ← qa_diagnostic_payload`
(both `_cap_text`-capped); if `not test_integrity_approved` → `regenerate_tests = True` for next cycle.

## The five loops
Only the **outer retry** loop consumes functional budget; the four inner loops are FREE fast-fail
reroutes that bypass the (expensive) Reviewer until they clear or hit their cap.
- **Outer retry** — bound `max_retries=3`; driven by Reviewer rejection / gate failure.
- **QA signature-lint** — bound `QA_LINT_MAX_REROUTES`; runs when `regenerate_tests`; `lint_test_suite_consistency` vs contract signatures.
- **Developer guardrail** — bound `GUARDRAIL_MAX_REROUTES`; three checks in sequence: missing contract files → documentation-justification (`enforce_documentation_guardrail`) → compile gate (`run_build_gate`).
- **QA test-compile gate** — bound `QA_GATE_MAX_REROUTES`; only TEST-only compile failures reroute to QA; env/network or production-referencing failures fall through to the Reviewer.
- **Compile env-retry** — bound 1; an environmental/network build error retries once, else hard-halt.

## Two isolated feedback channels
`ctx.error_trace` → Developer only (from `ReviewReport.dev_diagnostic_payload`); `ctx.qa_error_trace` →
QA only (from `qa_diagnostic_payload`). Reset every cycle; `run_developer_node(ctx, prev_dev_trace)` and
`run_qa_agent_node(ctx, prev_qa_trace)` consume them. The Developer can't edit tests and QA can't edit
production code, so mis-routing deadlocks the run. NOTE: the isolation is enforced by the Reviewer
prompt, not by code — the router copies both payloads unconditionally (hardening: docs/BACKLOG.md #18).
Distinct from the CLAUDE.md-vs-prompts boundary in [[feedback-context-isolation]].

## Termination states
- **Success** — `run_techwriter_node` (updates the living ADR) → `finalize_transaction` (atomic commit) → return.
- **Retries exhausted** — loop ends → `_abort_with_incident("Retries exhausted")`.
- **Financial breaker** — `enforce_financial_circuit_breaker` at 6 checkpoints; gates primarily on `PIPELINE_BUDGET_USD` ([[token-budget-excludes-cache]]).
- **Hard-halt** — misplaced contract file at cap, persistently undocumented new file, or persistent environmental build error.
- **Deadlock guard** — gate FAILED but Reviewer approved BOTH code and tests (no agent-fixable defect) → fail fast instead of looping to the breaker.

Abort writes `reports/incident_report.json` and `sys.exit(1)`; it does NOT `git reset` the staged run
clone (resume hygiene gap — docs/BACKLOG.md #23). Debug entry point: [[debugging-protocol]].
