---
skill_id: engineering_guide
type: global
nodes: [techlead, developer, qa, reviewer]
---
# Global Engineering Guide & Code Style

## Code Style
* **Testing**: Use the target ecosystem's native, standard testing framework. Do not introduce a third-party test framework when the standard library already provides one.
* **Type Boundaries**: Apply strict type boundaries. Reject ambiguous sub-types that could pass an implicit cast; validate the exact expected type at runtime.
* **State Preservation**: Store parameter values passed into constructors exactly as their original allowed types. No implicit coercion.
* **Error precedence under a streaming/O(1) constraint**: when one input can trigger more than one failure type (e.g. it is BOTH malformed/incomplete AND a wrong-typed/non-target structure), surface the more specific low-level fault (syntax/parse error) BEFORE the higher-level structural classification. Do NOT short-circuit on a first/partial signal — that misclassifies incomplete input. The constraint-respecting idiom: DRAIN the incremental parser to confirm well-formedness, letting its incomplete/parse error propagate (mapped to the documented syntax-error type); classify structure (e.g. "root is not the expected container") only once the document parsed cleanly. Never full-load the document to disambiguate when a streaming/O(1) constraint is in force.

## Integration Testing — In-Process Transport Limitations

When using an **in-process / in-memory HTTP test transport** (e.g. a test server that short-circuits the network stack), the client layer may silently drop or suppress headers whose value is an empty string before they reach the server-side request context. This is a transport-layer behavior, not a bug in the production code or the test assertion.

**Symptoms:** A header the test injects via the HTTP client is absent from the server's incoming request headers — the assertion fails with a null/missing value even though the production handler correctly handles that header.

**Fix pattern (language-independent):**
1. **Middleware/filter injection** — register a startup middleware or request filter that injects the problematic header directly into the server-side request context before routing, bypassing the client transport entirely. Use this for headers with empty or otherwise transport-unsafe values.
2. **Handler unit test** — call the route handler or controller action directly (no HTTP transport), constructing a fake/mock request context that contains the desired headers. This is the highest-fidelity approach for testing header-parsing logic in isolation.

**Avoid:** sending an empty-value header via the in-process HTTP client and asserting its presence server-side — the transport may strip it regardless of language or framework.

## Configuration & Bootability
* **Boot with zero required configuration.** Any value read from the environment MUST declare a safe in-code default; the application MUST start successfully with NO environment variables set. Environment variables OVERRIDE behavior — they never ENABLE startup. A configuration/settings object with a required, no-default, environment-sourced field is a defect: it crashes a freshly-deployed container (which provides no such variable) before serving a single request.

## Cloud runtime contract (long-running web services)
* When the application is a long-running web service (it listens on a port), it MUST satisfy its deployment target's runtime contract — restated in the ticket's architectural constraints. For a serverless-container target (e.g. Cloud Run) that means: bind the server to the port given by the `PORT` environment variable (default 8080) on host `0.0.0.0` (never localhost); remain stateless (no reliance on local-disk persistence between requests); and expose a lightweight health endpoint for liveness/readiness probes. A service that hardcodes a port, binds localhost, or cannot boot without external configuration will not run on the target.

## Security
* Zero tolerance for vulnerabilities. Run the ecosystem's standard SAST scanner before review.

## Data Governance & Privacy (GDPR-aligned)
* **PII in logs is forbidden.** Never emit user names, email addresses, query text, IP addresses,
  API keys, or any personally-identifiable value to any log sink. Log only opaque IDs, token
  counts, latency, and status codes.
* **Audit log**: any route that reads or mutates user data MUST append a structured entry to an
  audit log (table or append-only file) containing: timestamp (UTC), user/session ID (opaque),
  action (e.g. `"query"`, `"delete"`), and resource ID. Never include payload content.
* **Route separation**: unauthenticated public endpoints MUST be under `/api/public/`; any route
  that touches user data or internal state MUST be under `/api/internal/` (or equivalent
  access-controlled prefix) and require a valid session/token.
* **JWT / token comparison**: always use a constant-time equality function (e.g.
  `hmac.compare_digest` in Python) when comparing tokens or secrets; never use `==`.
* **Retention / right-to-erasure**: if the application stores user-generated content, provide a
  delete path that removes all associated records (DB rows + vector store objects) for a given
  user ID. Stub the implementation if the ticket scope does not cover the full flow, but declare
  the interface.
* **Dependency PII scope**: third-party clients (vector DB, LLM API) receive only the content
  strictly required for the operation — no user metadata, no internal IDs beyond the query text.
