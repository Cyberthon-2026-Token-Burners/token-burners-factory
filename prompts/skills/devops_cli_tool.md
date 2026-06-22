---
skill_id: devops_cli_tool
type: domain
triggers: [cli]
nodes: [devops]
---
ARCHETYPE: CLI tool / library — NO runtime container, NO Cloud Run.

## Hard rule
- Generate **NO Dockerfile** (`dockerfile_content` MUST be null) and **NO Cloud Run deploy step**. A CLI/library has no long-running server to deploy. Deploying it to Cloud Run is a hard error.

## deploy.yml (GitHub Actions → build / test / release)
- Trigger on push to the default branch (build + test) and on a version tag (`tags: ['v*']`) for the release/publish job.
- Build matrix across the relevant runtime versions for the application's language (e.g. multiple language/runtime versions and, where applicable, OS targets).
- Steps: check out → set up the language runtime → install deps → build → run the test suite. The package/release job runs only on a version tag.
- Publish the built artifact: attach binaries/packages to a GitHub Release (e.g. `softprops/action-gh-release`) and/or publish to the language's package registry, or push a CLI image to Google Artifact Registry (authenticating via WIF, `id-token: write`, `google-github-actions/auth`) — choose what matches the artifact. NEVER inline credentials.

## .env.example
- Usually unnecessary for a CLI; include only if the tool reads runtime configuration from the environment.
