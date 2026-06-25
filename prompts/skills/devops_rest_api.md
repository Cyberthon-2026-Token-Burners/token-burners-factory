---
skill_id: devops_rest_api
type: domain
triggers: [api]
nodes: [devops]
---
ARCHETYPE: REST API / web service — deploy to Google Cloud Run.

## Dockerfile
- Multi-stage build: a build stage that installs/compiles dependencies, then a slim runtime stage that copies only the artifact + runtime deps.
- Run as a NON-root user (create one and `USER` it before the entry point).
- The container MUST listen on the port from the `PORT` environment variable (Cloud Run injects it; default 8080). Bind to `0.0.0.0`, not localhost.
- End with an explicit `CMD`/`ENTRYPOINT` that starts the HTTP server.

## deploy.yml (GitHub Actions → Cloud Run)
- Trigger on push to the default branch.
- If you add a pre-deploy build/test/lint step, run the **canonical project commands supplied in the prompt verbatim** (the given `build_cmd`/`test_cmd`/`lint_cmd`). Do NOT invent extra linters/formatters/type-checkers the project was not validated against.
- `permissions: { id-token: write, contents: write }` — `id-token: write` is required for WIF; `contents: write` is required for the post-deploy README commit (see below).
- Authenticate with `google-github-actions/auth` using `workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}` and `service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}` — NO key JSON.
- Build + deploy with `google-github-actions/deploy-cloudrun` (source or image deploy), passing the service name, `${{ vars.GCP_PROJECT_ID }}`, and `${{ vars.GCP_REGION }}`. For an image deploy, build the Artifact Registry path from `${{ vars.GCP_REGION }}`, `${{ vars.GCP_PROJECT_ID }}`, and `${{ vars.GCP_REGISTRY_NAME }}`.
- **Give the deploy step an explicit `id: deploy`** so its `outputs.url` (the live Cloud Run URL) is accessible in later steps.
- Secrets vs variables (the org is pre-provisioned this way — see docs/guides/devops_setup.md): `GCP_WIF_PROVIDER` + `GCP_SERVICE_ACCOUNT` are repository **secrets** (`${{ secrets.* }}`); `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_REGISTRY_NAME` are repository **variables** (`${{ vars.* }}`). Never inline a key, project id, or region.
- **After the deploy step, add a "Update README with deployment URL" step** that:
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

## .env.example
- List runtime variables the service reads (e.g. `PORT`, any datastore URL placeholder) with placeholder values only.
