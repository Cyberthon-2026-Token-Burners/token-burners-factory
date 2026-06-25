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
- Steps: check out → set up the language runtime → install deps → build → run the test suite → run the lint/style check. The package/release job runs only on a version tag.
- For the build / test / lint steps, run the **canonical project commands supplied in the prompt verbatim** (e.g. the given `build_cmd`, `test_cmd`, `lint_cmd`). Do NOT invent or version-pin extra linters/formatters/type-checkers (no bare `ruff check`, `mypy`, `eslint`, … unless it IS the supplied command) — a CI stricter than what the code was validated against fails immediately. If no lint command is supplied, omit the lint step.
- Publish the built artifact: attach binaries/packages to a GitHub Release (e.g. `softprops/action-gh-release`) and/or publish to the language's package registry, or push a CLI image to Google Artifact Registry. For the Artifact Registry path, authenticate via WIF (`id-token: write`, `google-github-actions/auth` with `${{ secrets.GCP_WIF_PROVIDER }}` + `${{ secrets.GCP_SERVICE_ACCOUNT }}`) and build the registry path from `${{ vars.GCP_REGION }}`, `${{ vars.GCP_PROJECT_ID }}`, `${{ vars.GCP_REGISTRY_NAME }}`. Choose what matches the artifact; NEVER inline credentials.
- **Give the release step an explicit `id: release`** so its outputs are accessible in later steps. For `softprops/action-gh-release` the relevant output is `outputs.url` (the HTML URL of the created GitHub Release).
- **Add `contents: write`** to `permissions` (required both to create the GitHub Release and to push the README commit below).
- **After the release step, add an "Update README with release URL" step** that:
  1. Reads the release URL from `${{ steps.release.outputs.url }}`.
  2. If `README.md` contains the marker `<!-- RELEASE_URL_START -->`, replaces everything between `<!-- RELEASE_URL_START -->` and `<!-- RELEASE_URL_END -->` with a markdown link to the release. If the markers are absent, appends a new `## 📦 Latest Release` section with the markers and the link.
  3. Commits only when `README.md` actually changed (`git diff --exit-code`); the commit message MUST end with `[skip ci]` to prevent a re-trigger loop.
  4. Pushes via the default `GITHUB_TOKEN` — no extra secret needed when `contents: write` is set.

  Reference implementation for the step:
  ```yaml
        - name: Update README with release URL
          run: |
            RELEASE_URL="${{ steps.release.outputs.url }}"
            perl -i -0pe \
              "s|<!-- RELEASE_URL_START -->.*?<!-- RELEASE_URL_END -->|<!-- RELEASE_URL_START -->\n**Latest release:** [$RELEASE_URL]($RELEASE_URL)\n<!-- RELEASE_URL_END -->|s" \
              README.md || true
            if ! grep -q "RELEASE_URL_START" README.md; then
              printf '\n## 📦 Latest Release\n<!-- RELEASE_URL_START -->\n**Latest release:** [%s](%s)\n<!-- RELEASE_URL_END -->\n' \
                "$RELEASE_URL" "$RELEASE_URL" >> README.md
            fi
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git diff --exit-code README.md || \
              (git add README.md && \
               git commit -m "docs: update latest release URL [skip ci]" && \
               git push)
  ```

## .env.example
- Usually unnecessary for a CLI; include only if the tool reads runtime configuration from the environment.
