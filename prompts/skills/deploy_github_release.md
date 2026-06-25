---
skill_id: deploy_github_release
type: domain
triggers: [github-release]
nodes: [devops]
---
DEPLOY TARGET: GitHub Releases (CLI tools / libraries). This is the PLATFORM layer — HOW to publish a versioned artifact on GitHub, independent of the app's shape. NO runtime container, NO Cloud Run.

## Release workflow (tag-gated)
- The build/test job runs on push to the default branch; the **release/publish job runs ONLY on a version tag** (`tags: ['v*']`, gated e.g. `if: startsWith(github.ref, 'refs/tags/v')`) so a plain merge to the default branch never publishes.
- **Add `contents: write`** to `permissions` (required both to create the GitHub Release and to push the README commit below).
- Publish the built artifact: attach binaries/packages to a GitHub Release (e.g. `softprops/action-gh-release`) and/or publish to the language's package registry. (If you instead push a CLI image to Google Artifact Registry, authenticate via WIF — see the GCP platform guidance, `deploy_gcp` — and never inline credentials.)
- **Give the release step an explicit `id: release`** so its outputs are accessible in later steps. For `softprops/action-gh-release` the relevant output is `outputs.url` (the HTML URL of the created GitHub Release).

## Post-release: publish the release URL into the README
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
