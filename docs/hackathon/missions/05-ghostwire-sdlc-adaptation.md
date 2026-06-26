# GHOSTWIRE — SDLC Adaptation Plan
*"Adapt the factory. Aim the cannon. Fire."*

> **Context:** This document maps the gaps between the current Token Burners Factory engine and the
> requirements of Mission 05 (GHOSTWIRE — Corporate Intelligence Grid), then prescribes every change
> needed to execute the mission autonomously with `--auto-execute`.

---

## 1. What the Engine Already Handles

| Capability | Status |
|---|---|
| Python / FastAPI backend generation | ✅ |
| SQLAlchemy ORM + `requirements.txt` | ✅ |
| Docker-sandboxed build + unit tests | ✅ |
| GCP Cloud Run deployment scaffold | ✅ |
| Auto-merge PRs (`--auto-merge`) | ✅ |
| Application-wide budget ceiling (`--budget`) | ✅ |
| Multi-ticket batch execution (`--auto-execute`) | ✅ |
| Retry / circuit-breaker / FSM resume | ✅ |

---

## 2. Gap Analysis

| Area | Gap | Severity |
|---|---|---|
| RAG pipeline / vector DB patterns | No skill for Weaviate client, embedding generation, context retrieval | 🔴 Critical |
| External AI API (Claude as user-facing service) | No skill; Developer doesn't know how to call `anthropic` SDK from generated code | 🔴 Critical |
| GDPR / RBAC compliance rules | `engineering_guide.md` is silent on PII handling, audit logs, role separation | 🔴 Critical |
| Multi-service docker-compose (API + Postgres + Weaviate) | DevOps skills only cover single-service Cloud Run | 🟠 High |
| React frontend | No React skill exists | 🟡 Medium (post-MVP) |
| SA model too lightweight for multi-module architecture | `SA_MODEL = GEMINI_2_5_FLASH` — risks shallow blueprint | 🟠 High |
| Python sandbox missing `libpq` for psycopg2 | `docker/python.Dockerfile` may fail on `psycopg2-binary` install | 🟡 Medium |

---

## 3. Adaptation Plan

### 3.1 New Prompt Skills

#### `prompts/skills/python_rag.md`
- **Nodes:** `techlead`, `developer`, `reviewer`
- **Triggers:** `[rag, weaviate, vector, embedding, retrieval]`
- **Content:**
  - Weaviate Python client: env-driven `WEAVIATE_URL` + `WEAVIATE_API_KEY`, safe defaults so app boots without them
  - Embedding generation via `google.generativeai` (`models/text-embedding-004`) or configurable provider
  - Schema creation: class definition, `text2vec-contextionary` / `none` vectorizer
  - Ingest pipeline: chunk text → embed → batch upsert into Weaviate
  - Retrieval pipeline: query → embed → `near_vector` search → top-k context assembly
  - Grounded-response contract: if retrieval returns 0 results → return `"no relevant context found"`, never hallucinate
  - Test pattern: `unittest.mock.patch("weaviate.connect_to_weaviate_cloud")` — never spin a real Weaviate in CI

#### `prompts/skills/external_ai_api.md`
- **Nodes:** `techlead`, `developer`, `reviewer`
- **Triggers:** `[claude, anthropic, llm, ai_api, generative]`
- **Content:**
  - `anthropic.AsyncAnthropic` client; API key from `ANTHROPIC_API_KEY` env, default `""` — app must start without it
  - Async `messages.create` with `max_tokens`, `system`, `messages` params
  - Retry on `anthropic.RateLimitError` with exponential backoff (max 3 retries)
  - Prompt construction: system prompt from config constant, user query + assembled RAG context injected as user message
  - Response extraction: `response.content[0].text`
  - Test pattern: `unittest.mock.patch("anthropic.AsyncAnthropic")` — always mock; never call real API in tests
  - Security: `ANTHROPIC_API_KEY` must never appear in logs, responses, or error messages

#### `prompts/skills/devops_fullstack.md`
- **Nodes:** `devops`
- **Triggers:** `[fullstack, multiservice, weaviate, postgres, vector_db]`
- **Content:**
  - Single-stage `Dockerfile` for the FastAPI app (multi-stage optional)
  - `docker-compose.yml` for local dev: services `api`, `postgres:15`, `semitechnologies/weaviate`
  - Required env vars: `DATABASE_URL`, `WEAVIATE_URL`, `ANTHROPIC_API_KEY`, `PORT` (default `8080`)
  - Every env var must have a safe in-code default — container must boot with zero configuration
  - Mandatory `/health` endpoint for Cloud Run liveness probe
  - GCP topology: Cloud Run for API, Cloud SQL (PostgreSQL) or AlloyDB for DB, Weaviate Serverless or self-hosted Cloud Run for vector store
  - CI/CD: GitHub Actions — `test → build → push image → deploy Cloud Run → grant public invoker`

### 3.2 Update `prompts/skills/engineering_guide.md`

Add a **GDPR & RBAC** section:

```
## GDPR & Data Governance (mandatory for any app handling employee / HR data)
- PII fields (feedback text, employee names, performance scores) MUST NEVER appear in logs, HTTP
  responses to unauthenticated callers, or error messages.
- Every AI-generated decision (team selection, feedback summary) MUST be written to a structured
  audit log with: timestamp, actor_id, model_used, input_hash (not raw input), output_summary.
- Route separation is mandatory: /api/public/* for unauthenticated external callers;
  /api/internal/* requires a valid JWT with role "internal" or "admin".
- JWT verification must use a constant-time comparison; never log raw tokens.
- SAST (Bandit) must pass with zero HIGH/MEDIUM findings before review gate.
```

### 3.3 Config Changes (`src/shared/core/config.py`)

Upgrade models for the GHOSTWIRE run — complex multi-module architecture needs deeper reasoning:

```python
SA_MODEL  = GEMINI_2_5_PRO     # was GEMINI_2_5_FLASH — deeper architectural reasoning needed
DEVELOPER_EFFORT = EFFORT_HIGH  # was EFFORT_MEDIUM — complex RAG + external API integrations
```

> **Revert after the hackathon** — these cost ~3× more per token.

### 3.4 Docker Sandbox (`docker/python.Dockerfile`)

Ensure `psycopg2-binary` installs cleanly on `python:3.12-slim`. Add system dependency:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
 && rm -rf /var/lib/apt/lists/*
```

> `psycopg2-binary` ships a pre-compiled wheel so `libpq-dev` is technically redundant at runtime —
> but it prevents build failures on certain slim image variants. Alternatively, use `psycopg[binary]`
> (psycopg3) which is more reliably pre-compiled.

---

## 4. Ticket Decomposition Strategy

The `--idea` prompt must guide the SA agent toward **7 atomic tickets** (not one monolith).
If SA collapses them, use the `--run` single-ticket mode to execute them manually in order.

| Ticket | Scope | Key outputs |
|---|---|---|
| **TASK-01** | Database foundation | PostgreSQL schema (employees, projects, feedback, embeddings_cache), Alembic migrations, SQLAlchemy models, Pydantic schemas |
| **TASK-02** | Shared intelligence layer | Weaviate client wrapper, embedding service, data ingest pipeline (seed from JSON fixtures) |
| **TASK-03** | Public AI Chatbot module | `POST /api/public/chat` — intent detection, RAG retrieval, Claude API response, grounded-only contract |
| **TASK-04** | Feedback Intelligence Engine | `POST /api/internal/feedback/analyze` — sentiment + theme extraction, Claude summarization, structured JSON output (strengths / weaknesses / risks / confidence) |
| **TASK-05** | AI Team Assembler | `POST /api/internal/teams/assemble` — skill-match scoring (embeddings cosine), experience + feedback weighting, team optimization output with gaps + alternatives |
| **TASK-06** | DevOps scaffold | Dockerfile, docker-compose.yml, GitHub Actions CI/CD, GCP Cloud Run deploy, .env.example |
| **TASK-07** *(stretch)* | React internal dashboard | Feedback view, team assembly UI — skip for MVP if time is short |

**Dependency order:** TASK-01 → TASK-02 → TASK-03 / TASK-04 / TASK-05 (parallel) → TASK-06 → TASK-07

---

## 5. Execution Commands

### Step 1 — Nexus Planning (~10 min)

```bash
wsl -e bash -lc "source venv/bin/activate && python3 main.py \
  --idea 'GHOSTWIRE Corporate Intelligence Grid. Python 3.12 FastAPI monolith with three core modules.
  MODULE 1 — Public AI Chatbot: RAG over company data (case studies, job openings, tech expertise),
  intent detection client-vs-candidate, Claude API (anthropic SDK) for grounded response generation,
  max response latency 2s, hallucination-free (grounded-only, fallback to clarification question).
  MODULE 2 — Feedback Intelligence Engine: ingest peer/manager/self-review text (bulk POST),
  extract strengths/weaknesses/behavioral signals/burnout-risk via Claude API, output structured JSON
  {strengths, weaknesses, risks, team_dynamics_signals, confidence_score}, GDPR-compliant (no PII
  in logs), internal-only endpoint.
  MODULE 3 — AI Team Assembler: given new project description + constraints (timeline, budget,
  timezone), score employees on skill match (embeddings cosine), experience fit, feedback score,
  availability, team compatibility; output {team: [{employee_id, role, match_score}], gaps, risks,
  alternatives} with reasoning; internal-only endpoint.
  Shared infrastructure: PostgreSQL (employees, projects, feedback, project_history tables),
  Weaviate vector DB (company docs collection, employee skill vectors collection), shared embedding
  service (Google genai text-embedding-004).
  Security: JWT-based RBAC (public vs internal roles), audit log for every AI decision (timestamp,
  model, input_hash, output_summary), zero PII in logs, Bandit SAST clean.
  Decompose into minimum 6 atomic tickets in dependency order.' \
  --repo <TARGET_REPO_URL>"
```

### Step 2 — Human Review

Open `runs/<project>/NNN_nexus_plan_.../artifacts/` and verify:
- At least 6 TASK-*.md files
- TASK-01 covers DB schema before TASK-02 covers Weaviate
- No single ticket trying to implement all 3 modules at once

Iterate the idea prompt if decomposition is wrong, then re-run Nexus.

### Step 3 — Full Autonomous Execution

```bash
wsl -e bash -lc "source venv/bin/activate && python3 main.py \
  --resume <project> \
  --auto-execute \
  --scaffold-deploy \
  --budget 25"
```

> `--budget 25` — GHOSTWIRE is a 7-ticket multi-module build with complex integrations.
> Expected spend: ~$12–18 for a clean run; $25 gives headroom for retries.

### Monitoring

```bash
# Tail the audit log live
wsl -e bash -lc "tail -f runs/<project>/<NNN>_exec_*/logs/sdlc_audit.log"

# If a circuit breaker fires, diagnose and resume
# Use the /tbf-analyze-run skill, then:
wsl -e bash -lc "source venv/bin/activate && python3 main.py --resume <project>"
```

---

## 6. Risk Register

| Risk | Probability | Mitigation |
|---|---|---|
| Weaviate not available in test sandbox → import error | High | `python_rag.md` must mandate `unittest.mock.patch` for all Weaviate calls in tests |
| Claude API rate limit during CI test | High | `external_ai_api.md` mandates mock in all tests; `ANTHROPIC_API_KEY=test` is safe |
| SA generates a monolithic TASK-01 covering everything | Medium | Idea prompt explicitly states "minimum 6 atomic tickets in dependency order" |
| `psycopg2-binary` fails in Docker sandbox | Medium | Use `psycopg[binary]` (psycopg3) or add `libpq-dev` to `python.Dockerfile` |
| DEVELOPER_EFFORT=high → CLI timeout | Low | Set `DEVELOPER_CLI_TIMEOUT=1800` env var before the run |
| GDPR rules cause Reviewer to reject every PR | Low | Rules are additive guidance, not blockers — audit log is the artefact, not a gate |

---

## 7. Three-Day Timeline

```
Day 1 · June 26 (today)
├── 14:00 – 16:00   Implement adaptation (Blocks 3.1 – 3.4): create skills, update config, Dockerfile
├── 16:00 – 16:30   Craft & test idea prompt; run Nexus planning
├── 16:30 – 17:00   Human review of TASK-*.md; iterate if needed
└── 17:00+          Launch --auto-execute --budget 15 (first 3–4 tickets overnight)

Day 2 · June 27
├── Morning          Monitor FSM cycles; diagnose any halts with /tbf-analyze-run
├── Afternoon        Remaining tickets; iterate prompts for any repeated failures
└── Evening          All backend tickets merged; DevOps scaffold running
                     ⚠️  Build submission deadline: 14:00

Day 3 · June 28 (Finals only — top 10)
├── Morning          GCP Cloud Run deploy live; smoke-test all 3 endpoints
├── Afternoon        Demo prep: record each module responding correctly
└── 18:30            Live pitch to jury
```

---

## 8. Definition of Done

The mission is complete when:
- [ ] `GET /health` returns `200` on the deployed Cloud Run URL
- [ ] `POST /api/public/chat` returns a grounded, non-hallucinated answer about GodTech
- [ ] `POST /api/internal/feedback/analyze` returns structured JSON with `confidence_score`
- [ ] `POST /api/internal/teams/assemble` returns a ranked team with `match_score` per member
- [ ] All unit tests pass in the Docker sandbox (green QA gate)
- [ ] Bandit SAST: zero HIGH/MEDIUM findings
- [ ] No PII fields in any log line
- [ ] Audit log records every AI decision with `input_hash` + `output_summary`

---

*// ADAPTATION_PLAN_END · GHOSTWIRE · Cyberthone 2026*
