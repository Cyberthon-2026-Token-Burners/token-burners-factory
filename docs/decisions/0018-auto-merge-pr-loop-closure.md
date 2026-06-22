# 0018 — Close the Autonomy Loop to `main` via an Auto-Merged PR (forge seam, `--auto-merge`, E2)

## Status

Accepted (extends [0008](0008-git-anchored-sessions-atomic-commit.md) atomic-commit transaction,
[0012](0012-virtual-separation-monorepo-planes.md) import discipline, [0017](0017-nexus-executor-auto-dispatch.md)
`run_executor` seam)

## Context

The autonomy loop stopped one step short of `main`. On full success the executor made the atomic
`feat(<ticket>): …` commit on the `feat/ticket-<id>` branch and, with `--push`, ran `git push -u origin
HEAD` — and **stopped** ([runner.py `finalize_transaction`](../../src/executor/runner.py#L249)). Verified,
gate-passing work sat on a feature branch; landing it in `base_branch` still required a human. `base_branch`
was only a **diff anchor + fetch ref**, never a merge target, and there was **no PR / merge / `gh` / GitHub
API** in the engine at all (greenfield).

Three constraints shaped the design (raised up front in planning):
- **Self-approval is forbidden.** GitHub will not let a PR's author approve their own PR, so a *real*
  approval needs a **second identity** (a separate token), or the merge must bypass approval via admin
  privileges. The identity model had to be decided, not assumed.
- **Branch protection / required checks.** The engine already runs build/test/SAST locally; on a protected
  repo an immediate merge can still be refused until *remote* required checks pass.
- **Provider lock-in.** The interface had to stay generic so a GitLab (`glab`) / Bitbucket backend can follow
  without touching the call sites.

A latent robustness gap also surfaced only once the loop actually reached the network: agent-authored text
(the PR title/body, the commit subject) and a blocking Gemini network call were each crossing a process
boundary **with no guard** — see *Consequences → Hardening*.

## Decision

Add a `--auto-merge` flag that, on PIPELINE SUCCESS, opens a PR from `feat/ticket-<id>` into `base_branch`
and squash-merges it — through a **provider-agnostic forge seam**, GitHub-first via the `gh` CLI.

- **Forge seam — `src/shared/utils/forge.py`** (`open_pr` / `approve_pr` / `merge_pr`). Subprocess-first,
  mirroring `git_helpers.py` and the `runner._run_checked` auth idiom: a copied env with interactive prompts
  disabled (`GH_PROMPT_DISABLED=1`), a wall-clock ceiling on every network call (`GH_NETWORK_TIMEOUT`, 300 s),
  and `GITHUB_TOKEN` read from the inherited env (never on disk). `gh` infers owner/repo from the clone's
  `origin` remote, so every call runs with `cwd=repo_dir` — no URL/owner parsing. Lives in the **shared**
  plane so it is provider-swappable behind the three function names.
- **`--auto-merge` flag** (`RunConfig.auto_merge`, `store_true`) — **implies `--push`** (`push = args.push or
  args.auto_merge`, wired through all five `RunConfig` constructions). A new step `finalize_pr(ctx, cfg)`
  runs **after** `finalize_transaction` in the success block, wrapped so the FinOps report/summary still
  print even on a hard merge failure ([runner.py:1259-1265](../../src/executor/runner.py#L1259)):
  `try: if cfg.auto_merge: await finalize_pr(ctx, cfg) finally: write_finops_report; log_finops_summary`.
- **`open_pr` is idempotent (resume-safe).** It first `gh pr view`s the head branch: an existing **OPEN** PR
  into the **same** base is reused; one already **MERGED** returns `None` (caller skips the merge); an open PR
  targeting a *different* base is not ours → create a fresh one. This makes `--resume` after a partial merge
  safe (relates to BACKLOG #23).
- **Identity model — direct `--admin` squash-merge, approve best-effort.** `merge_pr` does
  `gh pr merge --squash --admin --delete-branch`, which closes the loop immediately on repos without required
  checks. `approve_pr` is **strictly best-effort**: it runs **only** when a separate `GITHUB_REVIEWER_TOKEN`
  is present (passed as `GH_TOKEN` via `env_extra`, a *different* identity), and any `gh` failure
  (self-approval rejected, token lacks permission) is **logged and swallowed** — control returns to the
  merge. Without the reviewer token, approval is skipped and the `--admin` merge still lands the work.
- **Protected-repo path.** If the immediate `--admin` merge is refused for *pending required checks*
  (`_PENDING_CHECKS_HINTS` matched in stderr), `merge_pr` falls back to `gh pr merge --auto` — queuing the
  merge to land once remote CI goes green. `GITHUB_MERGE_STRATEGY=auto` forces the queued path up front.
- **Fail-fast preflight.** `check_environment(require_forge=cfg.auto_merge)` additionally requires `gh` on
  PATH **and** a non-empty `GITHUB_TOKEN` when `--auto-merge`, so a misconfigured forge aborts before any
  tokens are spent.
- **Failure policy.** `merge_pr` is the loop-closing step, so a *genuine* merge failure `sys.exit(1)`s
  (consistent with `_run_checked`); `approve_pr` never aborts; `open_pr` is idempotent. The bridge stays in
  the entry/worker layer — the control plane never learns about PRs (ADR 0012 discipline held).

## Consequences

- **Pros.** A single `--idea … --repo … --auto-execute --push --auto-merge` invocation now goes idea → plan
  → built → committed → **PR opened, approved, squash-merged into `main`** — the full autonomy loop closes
  with no human hand-off. The seam is provider-agnostic (GitLab/Bitbucket need only a new `open_pr`/
  `approve_pr`/`merge_pr` impl), idempotent on resume, and protected-repo-aware.
- **Cons / constraints.** A *real* approval requires operating a **second GitHub identity** (a collaborator
  with write access whose `GITHUB_REVIEWER_TOKEN` is configured); without it the loop relies on `--admin`
  bypass, which needs admin rights on the repo. A merge performed with the Actions `secrets.GITHUB_TOKEN`
  will **not** trigger downstream workflows (GitHub suppresses event cascades from that token) — a real PAT
  is required if the merge must kick off further automation. `gh` must be installed (documented in
  `docs/guides/setup.md`). A PAT embedded in a `--repo` URL persists verbatim into `project.json` + the
  clone's `.git/config`; prefer the env-var credential helper (carried over from ADR 0017).

### Hardening (boundary guards added during live E2 validation)

Two crashes/hangs that only manifested once the loop reached the network were fixed at the **process
boundary**, where they belong:

- **Embedded-NUL argv crash → `sanitize_for_argv`.** A corrupted glyph in a Nexus-authored ticket (a `©`
  mangled to `\x00`) flowed into the PR body; POSIX `execvp` rejects any argv element containing a NUL, so
  `gh pr create --body …` raised `ValueError: embedded null byte`. Fixed with one SSOT helper
  (`src/shared/utils/subprocess_helpers.py` `sanitize_for_argv` — strips C0 controls + DEL, keeps
  `\t`/`\n`/`\r`) applied at **both** subprocess boundaries: `forge._run_gh` and `runner._run_checked` (the
  commit path had the identical latent exposure). Cleaning the glyph at *ingest* is a deferred BACKLOG item.
- **Unbounded Gemini call hang → `GEMINI_REQUEST_TIMEOUT`.** A stalled structured Gemini request (observed
  while *building* the Reviewer's context via `fallback_semantic_search`) hung the executor forever:
  `run_structured_llm` ran the blocking SDK call in `run_in_executor` with no timeout, `with_api_retry` only
  fires on *exceptions*, and the genai client carried no request ceiling. Fixed at the SSOT: the shared
  client is now built with `http_options=types.HttpOptions(timeout=GEMINI_REQUEST_TIMEOUT * 1000)` (300 s,
  env-overridable), so a stall *raises* → `with_api_retry` backs off → fails fast. Covers **every** structured
  role (PO/SA/TPM/TechLead/QA/Reviewer/TechWriter/Arbiter), not just the Reviewer.

> Validated end-to-end on demo project `cli-python-json-csv` (`002_exec_TASK-01_…211011`): one self-healing
> reroute (cycle 1 → README verbatim fix → cycle 2 approved), then PR #1 opened, **approved via
> `GITHUB_REVIEWER_TOKEN`**, and **squash-merged into `main`** — $0.4434 / $10.00, 40,215 tokens.
> Archive: [iteration_18](../releases/iteration_18/iteration_18_README.md).
