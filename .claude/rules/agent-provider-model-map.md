---
paths:
  - "src/nexus/*.py"
  - "src/nexus/agents/*.py"
  - "src/development/agents/*.py"
  - "src/deployment/agents/*.py"
  - "src/shared/utils/llm.py"
  - "src/shared/core/config.py"
  - "src/shared/core/observability.py"
---

# Agent → provider / model map

## The provider switch (`MODEL_PROVIDER` env / `--provider` CLI)
The map below is the **DEFAULT** (mixed) routing. A single knob forces the WHOLE pipeline onto one
provider, resolved in `config.py` (`active_provider()`, set once from the env at import and overridable by
`set_model_provider()` which `parse_args` calls for the `--provider` flag — applied BEFORE any role resolves
a model or `check_environment` runs; a runtime knob, NOT persisted, re-pass it on `--resume`). Aliases
(`normalize_provider`): `api`/`google`/`gemini` → Gemini; `claude`/`claude-code`/`cli` → Claude Code CLI;
`anthropic`/`claude-api` → Anthropic API; unset/`default` → mixed. States:
- **default (mixed)** — exactly the map below (Gemini structured roles + Claude-CLI Developer).
- **gemini** (`api`/`google`/`gemini`) — Gemini EVERYWHERE: structured roles keep their `ROLE_MODELS` Gemini
  models AND the Developer runs on a **structured Gemini emitter** (`developer.py::_run_developer_gemini` →
  `run_structured_llm("developer", DeveloperFileSet, …)` with `DEVELOPER_GEMINI_MODEL`, single-shot full-file
  output written into the sandbox `repo/` — NOT the agentic CLI). No Claude calls anywhere.
- **claude** (`claude`/`claude-code`/`cli`) — the **subscription Claude Code CLI EVERYWHERE, NO API key**:
  the Developer is the agentic CLI (as in default) AND every structured role runs through the SAME CLI in a
  one-shot JSON mode — `run_structured_llm` routes to `_run_structured_via_claude_cli` (`llm.py`), which
  embeds the role's Pydantic JSON Schema in the prompt, calls `run_claude_cli_oneshot`
  (`subprocess_helpers.py`, print-mode `claude -p`, no file edits, throwaway cwd), then extracts + validates
  + re-prompts the JSON (`CLAUDE_CLI_MODEL`). Cost is authoritative (CLI-reported). No Gemini, no API key.
- **anthropic** (`anthropic`/`claude-api`) — the **Anthropic API** for every structured role
  (`instructor.from_anthropic`, `get_anthropic_instructor_client`, `CLAUDE_API_MODEL`, `ANTHROPIC_MAX_TOKENS`;
  needs `ANTHROPIC_API_KEY` + the OPTIONAL `anthropic` package); the Developer stays the agentic Claude CLI.

`structured_role_routing(role)` returns `(model, label, provider)` per the active provider; `developer_provider()`
returns the Developer backend. `check_environment` is **provider-aware** — it requires only the keys/binaries
the active provider actually exercises (`GEMINI_API_KEY` only when Gemini runs, `ANTHROPIC_API_KEY` only under
**anthropic**, the `claude` binary whenever the CLI is used — default/claude/anthropic; **claude needs no API
key**). The role list below is provider-independent (`structured_role_routing` keeps each role's display label
from `ROLE_MODELS`, so telemetry/plane attribution is unchanged on every path).

**Gemini, via `run_structured_llm`** (`src/shared/utils/llm.py` → instructor + `instructor_client`,
forced structured Pydantic output): the **development** plane's **TechLead, QA, Reviewer, Technical Writer,
Arbiter (failure triage / contract self-healing)** and the **deployment** plane's **DevOps (post-batch
deploy-scaffolding, E4)**, plus the Nexus control plane's **PO, SA, TPM** (and, under provider=gemini ONLY,
the **Developer** via the `DeveloperFileSet` emitter). Each role's model + display label is in `ROLE_MODELS`
(`src/shared/core/config.py`; `DEVOPS_MODEL` registers `devops`); under provider=claude `structured_role_routing`
routes the role through the Claude Code CLI one-shot JSON adapter (`CLAUDE_CLI_MODEL`), and under
provider=anthropic it swaps the model to `CLAUDE_API_MODEL` and the client to the Anthropic instructor client
(passing the required `max_tokens`). On a structured failure the cause (e.g.
Gemini `RECITATION`) is surfaced by `describe_finish_reason` (`observability.py`) via `with_api_retry`.
`run_structured_llm` also relocates any Jinja-marker (`{{ }}`/`{% %}`) **system** message to a user turn
(`_relocate_jinja_system_messages`) — instructor's GenAI path rejects Jinja in system messages, which a
config-teaching prompt (the DevOps `${{ secrets.* }}`) would otherwise trip; a fast-path no-op for every
marker-free role. Every structured call is
wall-clock-bounded: `instructor_client` is built with a `GEMINI_REQUEST_TIMEOUT` (default 300 s, env-overridable)
`http_options` ceiling, so a stalled request *raises* (then `with_api_retry` backs off and fails fast)
instead of hanging the run forever — `with_api_retry` only catches exceptions, never a silent stall.

**Claude Code CLI** — TWO call shapes: `run_claude_cli` (agentic, file-editing) drives the **Developer**
under every provider except gemini (there it's the Gemini emitter); `run_claude_cli_oneshot` (print-mode,
non-agentic) drives the **structured roles** under provider=claude (the one-shot JSON adapter above). The
agentic Developer edits files directly in the run's `repo/`, re-sending its prompt/transcript each turn (hence cache-heavy). A
subscription **session/usage-limit block** is recognized by `detect_claude_quota_block` (the CLI emits one
"hit your session limit" line, edits nothing, bills 0 tokens) and fails fast with a `🚨 PROVIDER QUOTA HALT`
(`ClaudeCliQuotaExhausted`) — an infrastructure condition, NOT a wrong-work agent defect; see the
`tbf-analyze-run` provider-quota class.

**FinOps** (see [token-budget-excludes-cache](token-budget-excludes-cache.md) + [finops-app-budget](finops-app-budget.md)):
Gemini cost is **estimated** from `MODEL_PRICING_MATRIX`; the Claude **CLI** cost is **authoritative**
(reported by the CLI) — for BOTH the agentic Developer and the provider=claude structured roles. The Anthropic
**API** structured path (provider=anthropic) is **estimated** from `ANTHROPIC_PRICING` via
`estimate_anthropic_cost_usd` (the raw API returns token counts, no cost). `log_token_usage` branches on the
response shape — a CLI usage dict (`_ClaudeCliRaw.claude_cli_usage`) vs Gemini `usage_metadata` vs Anthropic
`.usage` — and all Claude paths roll up under provider key `"claude"` in the summary. The breaker is
**money-only** (ADR 0022): it gates on `total_cost_usd` against the threaded application
budget — tokens (fresh input + output; cache read/write tracked separately, excluded) are reported, never a
ceiling. Per-agent telemetry via `log_token_usage(telemetry, …)`, which also attributes the **plane** (from
`AGENT_PLANE`) and the per-call **wall-clock** (read from the `run_structured_llm` `LAST_LLM_ELAPSED_S`
ContextVar — no change to its 2-tuple return); the Developer (Claude) records directly with `plane="development"`.
`log_finops_summary` prints the GRAND TOTAL with per-agent + per-plane subtotals + total time. All planes
record into a `PipelineTelemetry`; the batch merges them into `BatchState.app_telemetry`. Related:
[repo-module-map](repo-module-map.md), [agent-contracts](agent-contracts.md).
