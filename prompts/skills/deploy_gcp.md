---
skill_id: deploy_gcp
type: domain
triggers: [gcp, cloud-run]
nodes: [devops]
---
DEPLOY TARGET: Google Cloud Run (web services) via Workload Identity Federation. This is the PLATFORM layer — HOW to deploy to GCP, independent of the app's shape. The archetype skill defines the container/server; this skill defines the GCP deploy workflow.

## Authentication — Workload Identity Federation (NO embedded credentials)
- Authenticate with `google-github-actions/auth` using `workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}` and `service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}` — NEVER a key JSON, token, or password.
- `permissions: { id-token: write, contents: write }` — `id-token: write` is required for WIF; `contents: write` is required for the post-deploy README commit (below).
- Secrets vs variables (the org is pre-provisioned this way — see docs/guides/devops_setup.md): `GCP_WIF_PROVIDER` + `GCP_SERVICE_ACCOUNT` are repository **secrets** (`${{ secrets.* }}`); `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_REGISTRY_NAME` are repository **variables** (`${{ vars.* }}`). Never inline a key, project id, or region.

## Build + push the image (Artifact Registry)
- Configure docker auth for Artifact Registry: `gcloud auth configure-docker ${{ vars.GCP_REGION }}-docker.pkg.dev --quiet`.
- Build the image tag from `${{ vars.GCP_REGION }}`, `${{ vars.GCP_PROJECT_ID }}`, `${{ vars.GCP_REGISTRY_NAME }}` (e.g. `${REGION}-docker.pkg.dev/${PROJECT}/${REGISTRY}/<service>:${{ github.sha }}`), then `docker build` + `docker push`.

## Deploy to Cloud Run
- Deploy with `google-github-actions/deploy-cloudrun@v2`, passing `service`, the pushed `image`, and `region: ${{ vars.GCP_REGION }}`.
- **Give the deploy step an explicit `id: deploy`** so its `outputs.url` (the live Cloud Run URL) is accessible in later steps.
- **PUBLIC ACCESS (REQUIRED for a public web service):** grant unauthenticated invocation so the service is reachable from the internet — pass `flags: '--allow-unauthenticated'` to the deploy step. WITHOUT it, Cloud Run rejects every anonymous request with HTTP 403 ("The request was not authenticated. Either allow unauthenticated invocations or set the proper Authorization header."). Only OMIT this for an explicitly private/internal service (which then requires an IAM `roles/run.invoker` binding for its callers instead).
- The container listens on `$PORT` (Cloud Run injects it) and binds `0.0.0.0` — that is the archetype skill's Dockerfile/server concern; this deploy step does not set the port.

## Cloud SQL (only for a database-backed CRUD service)
- Attach the instance to the Cloud Run revision via `--add-cloudsql-instances` (or the Cloud SQL Auth Proxy), referencing `${{ secrets.CLOUD_SQL_CONNECTION_NAME }}`.
- If the app has a schema/migrations step, run migrations against the database BEFORE the new revision serves traffic (a migrate step gated on the same WIF auth).

## Post-deploy: publish the live URL into the README
- **After the deploy step, add an "Update README with deployment URL" step** that:
  1. Reads the URL from `${{ steps.deploy.outputs.url }}`.
  2. If `README.md` already contains the marker `<!-- DEPLOYMENT_URL_START -->`, replaces everything between `<!-- DEPLOYMENT_URL_START -->` and `<!-- DEPLOYMENT_URL_END -->` with a markdown link to the live URL. If the markers are absent, appends a new `## 🚀 Live Deployment` section with the markers and the link.
  3. Uses `perl -i -0pe` for the in-place multiline replacement (available on all ubuntu-latest runners).
  4. Commits only when `README.md` actually changed (`git diff --exit-code`); the commit message MUST end with `[skip ci]` to prevent a re-trigger loop.
  5. Pushes to the current branch with the default `GITHUB_TOKEN` (no extra secret needed — `contents: write` above covers it).

  Reference implementation for the step:
  ```yaml
        - name: Update README with deployment URL
          run: |
            LIVE_URL="${{ steps.deploy.outputs.url }}"
            perl -i -0pe \
              "s|<!-- DEPLOYMENT_URL_START -->.*?<!-- DEPLOYMENT_URL_END -->|<!-- DEPLOYMENT_URL_START -->\n**Live:** [$LIVE_URL]($LIVE_URL)\n<!-- DEPLOYMENT_URL_END -->|s" \
              README.md || true
            if ! grep -q "DEPLOYMENT_URL_START" README.md; then
              printf '\n## 🚀 Live Deployment\n<!-- DEPLOYMENT_URL_START -->\n**Live:** [%s](%s)\n<!-- DEPLOYMENT_URL_END -->\n' \
                "$LIVE_URL" "$LIVE_URL" >> README.md
            fi
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git diff --exit-code README.md || \
              (git add README.md && \
               git commit -m "docs: update live deployment URL [skip ci]" && \
               git push)
  ```
