# 0011 — Secure WSL Sandbox Binding & Real-Time FinOps Circuit Breaker

## Status

Accepted

## Context

Iteration 010 left two latent defects in the sandbox infrastructure and the
cost-control layer — one a host-level security hole, the other a FinOps blind spot:

1. **Unauthenticated remote root via the Docker API** — the WSL2 Docker daemon was
   bound to `tcp://0.0.0.0:2375` with no TLS (`daemon.json` `hosts`). Port 2375 is
   the plaintext Docker API; `0.0.0.0` publishes it on every interface, so any
   process on the local subnet could drive the daemon and, via a privileged bind
   mount, obtain **root on the Windows/WSL host**. A developer-convenience binding
   had become a remote-code-execution surface.

2. **A self-contradictory, broken setup chain** — `docs/docker-on-windows.md`
   claimed independence from Docker Desktop, while `docs/setup.md`'s troubleshooting
   table strictly required it ("make sure Docker Desktop is running"; "Docker
   Desktop manages permissions"). The chain also never installed the engine: it
   configured `daemon.json` for a `docker-ce` that no step had installed, so a clean
   machine could not reach a working runtime by following the guide.

3. **Cost telemetry the FSM could not act on** — Gemini token usage was extracted
   in real time from structured responses, but the out-of-band Developer agent
   (Claude CLI) was auditable **only retrospectively** via `npx ccusage`.
   `GlobalPipelineContext` carried no live Claude token counters, so the orchestrator
   had no in-loop budget signal. A pathological Developer ↔ Reviewer ↔ QA retry loop
   could therefore drain the API budget to exhaustion before any human saw the bill —
   the functional Circuit Breaker bounded *attempts*, but nothing bounded *spend*.

## Decision

Three coordinated changes harden the sandbox and make cost a first-class FSM signal:

- **Loopback-only Docker API binding** — the daemon `hosts` entry is restricted to
  `tcp://127.0.0.1:2375` (plus the unix socket). The API is reachable only from the
  same host, removing the subnet-exposed RCE surface while preserving the
  Windows-CLI → WSL-engine workflow (the client connects over loopback). `DOCKER_HOST`
  and the lazy-loader probe are aligned to `127.0.0.1`.

- **Infrastructure documentation refactor** — `docs/docker-on-windows.md` and
  `docs/setup.md` are rewritten to a single coherent chain: all Docker Desktop
  dependencies are purged (including the troubleshooting table), the explicit
  `docker-ce` engine installation step is added before daemon configuration, and the
  secure loopback binding is the documented default. The docs now describe a runtime
  a clean machine can actually reach.

- **Real-time Claude telemetry + Financial Circuit Breaker** — `GlobalPipelineContext`
  gains live token accounting for the Claude CLI Developer agent, so spend is tracked
  per call rather than reconciled after the fact. A Financial Circuit Breaker
  hard-halts the FSM the moment a configured budget threshold is breached during
  cyclic retries, dumping state for audit instead of looping to exhaustion — the cost
  analogue of the existing functional retry breaker.

## Consequences

- **Pros**: the host RCE is closed — the Docker API is no longer reachable off-host;
  the WSL2 runtime is deterministic and self-contained (no Docker Desktop, engine
  install is explicit), so the setup guide is reproducible on a clean machine; the
  API budget is protected from infinite-loop drain by a deterministic, real-time
  hard-halt rather than a post-mortem `ccusage` report.
- **Cons / constraints**: loopback binding means a Docker client on another host can
  no longer reach this daemon without an explicit, separately-secured tunnel (a
  deliberate trade-off favouring isolation over remote convenience); the Financial
  Circuit Breaker is a new hard-failure surface — a generous-but-finite budget can
  terminate a long but legitimate run mid-flight, so the threshold needs tuning per
  workload; live Claude token accounting depends on the CLI surfacing usage per
  invocation, and `npx ccusage` is retained only for historical billing
  reconciliation, not as the in-loop signal.
