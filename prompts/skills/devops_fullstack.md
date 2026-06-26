---
skill_id: devops_fullstack
type: domain
triggers: [fullstack, multiservice, weaviate, postgres, vector_db, multi_container, react_frontend]
nodes: [devops]
---
ARCHETYPE: Full-stack web service with auxiliary data stores (relational DB + vector DB).  
App SHAPE only — GCP/Cloud Run deploy mechanics live in the `deploy_gcp` platform skill.

DEPLOY TARGET: Google Cloud Run — follow `deploy_gcp` for WIF auth, image build/push, Cloud Run
deploy step, and the public-invoker grant.

## Dockerfile (Python / FastAPI + React SPA)
Multi-stage build — frontend first, then API with static files embedded:

```dockerfile
# ── Stage 1: build frontend ──────────────────────────────────────────────────
# package.json is at the REPO ROOT (engine sandbox requires it there); source is in frontend/
FROM node:20-slim AS frontend-build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY frontend/ ./frontend/
COPY vite.config.ts tsconfig*.json index.html ./
RUN npm run build          # outputs to /app/dist

# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim AS api
WORKDIR /app

# System deps for compiled Python packages (psycopg2-binary needs libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
# Embed the built SPA so FastAPI can serve it as StaticFiles
COPY --from=frontend-build /app/dist ./static/

RUN useradd -u 1000 -m appuser
USER appuser

ENV PORT=8080
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

## docker-compose.yml (local development / CI integration tests)
```yaml
version: "3.9"
services:
  api:
    build: .
    ports: ["8080:8080"]
    environment:
      DATABASE_URL: postgresql://app:app@db:5432/appdb
      WEAVIATE_URL: http://weaviate:8080
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      GEMINI_API_KEY: ${GEMINI_API_KEY:-}
      PORT: "8080"
    depends_on:
      db:
        condition: service_healthy
      weaviate:
        condition: service_healthy

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: appdb
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app"]
      interval: 5s
      timeout: 5s
      retries: 5

  weaviate:
    image: semitechnologies/weaviate:1.25.0
    ports: ["8081:8080"]
    environment:
      QUERY_DEFAULTS_LIMIT: 25
      AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: "true"
      PERSISTENCE_DATA_PATH: /var/lib/weaviate
      DEFAULT_VECTORIZER_MODULE: none
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8080/v1/.well-known/ready"]
      interval: 10s
      timeout: 5s
      retries: 6
```

## .env.example
```
PORT=8080
DATABASE_URL=postgresql://app:app@localhost:5432/appdb
WEAVIATE_URL=http://localhost:8081
WEAVIATE_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
```
Every variable MUST have a safe in-code default — the service boots with all vars unset.

## deploy.yml (CI/CD additions for full-stack)
- `package.json` is at the **repo root** — `npm ci` and `npm run build` run from the repo root
  (no `working-directory: frontend`). The Dockerfile Stage 1 also copies from root.
- The multi-stage Docker build handles the frontend compilation internally — no separate `npm build`
  step in CI is required before `docker build`. The context is the repo root.
- Do NOT run Weaviate or Postgres as separate CI services for the build/lint step — mock them in
  unit tests.
- The actual GCP deploy job comes from the `deploy_gcp` platform skill.

## Health endpoint
- Expose `GET /health` → `{"status": "ok"}` with HTTP 200. No auth required.
- For readiness: include lightweight DB ping (`SELECT 1`) and Weaviate `.is_ready()` check;
  return HTTP 503 if either fails (Cloud Run readiness probe will hold traffic).

## GCP Production Topology
- **API**: Cloud Run (stateless; `PORT` from environment).
- **PostgreSQL**: Cloud SQL for PostgreSQL 15 (connect via Unix socket `/cloudsql/<instance-connection-name>`
  or Cloud SQL Auth Proxy; set `DATABASE_URL` via Secret Manager).
- **Weaviate**: Weaviate Cloud Services (WCS) serverless cluster; `WEAVIATE_URL` + `WEAVIATE_API_KEY`
  from Secret Manager.
- **Secrets**: store `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, DB credentials, and `WEAVIATE_API_KEY`
  in GCP Secret Manager; surface them as environment variables via `--set-secrets` in the Cloud Run
  deploy step (reference the `deploy_gcp` skill for the exact flag).
