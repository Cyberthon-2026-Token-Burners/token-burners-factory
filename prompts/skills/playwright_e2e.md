---
skill_id: playwright_e2e
type: domain
triggers: [playwright, e2e, end-to-end, browser-test, acceptance-test, smoke-test]
nodes: [techlead, developer, qa, reviewer]
---
LANGUAGE TARGET: Playwright — E2E / acceptance tests for a React 19 SPA + FastAPI backend.

## Critical Constraint — QA Sandbox vs CI
The engine's QA sandbox (`node-22-web`) has **no browser binaries** and runs `npm test` (Vitest
unit tests only). Playwright tests MUST live in a separate `e2e/` directory and be invoked via
`npm run test:e2e` — this script is **NOT** mapped to `npm test`, so the sandbox never tries to
run them. Playwright tests execute exclusively in CI (a dedicated GitHub Actions job).

## File Layout
```
<repo-root>/
  e2e/
    playwright.config.ts   ← Playwright config (at e2e/ root)
    tests/
      chatbot.spec.ts
      feedback.spec.ts
      team-assembler.spec.ts
    fixtures/
      auth.ts              ← shared auth state helper
  playwright-package.json  ← RENAMED to avoid `npm ci` picking it up in the sandbox;
                             CI installs it explicitly: `npm install --prefix e2e`
```

> **Why `playwright-package.json`?** If Playwright's `package.json` sits at the repo root or is
> named `package.json` inside `e2e/`, the sandbox's `npm ci` may attempt to install it and fail on
> browser binary downloads. Renaming it `playwright-package.json` keeps the sandbox clean; CI
> installs it explicitly with `--prefix`.

`playwright-package.json` contents:
```json
{
  "name": "ghostwire-e2e",
  "private": true,
  "devDependencies": {
    "@playwright/test": "^1.45.0"
  },
  "scripts": {
    "test:e2e": "playwright test"
  }
}
```

## Playwright Config (`e2e/playwright.config.ts`)
```ts
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:8080',
    trace: 'on-first-retry',
  },
  // Spin up Vite preview against a built bundle for local runs.
  // In CI, point BASE_URL at the deployed Cloud Run URL (no webServer needed).
  webServer: process.env.BASE_URL ? undefined : {
    command: 'npm run build && npx vite preview --port 8080',
    port: 8080,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    cwd: '../',  // repo root where package.json lives
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
})
```

## Auth Fixture (`e2e/fixtures/auth.ts`)
Pre-seed `sessionStorage` JWT so protected pages don't redirect to login on every test:
```ts
import { test as base } from '@playwright/test'

export const test = base.extend({
  page: async ({ page }, use) => {
    await page.addInitScript(() => {
      sessionStorage.setItem('jwt', 'test-token-e2e')
    })
    await use(page)
  },
})
export { expect } from '@playwright/test'
```

## Test Patterns

### Public Chatbot (`chatbot.spec.ts`)
```ts
import { test, expect } from '@playwright/test'

test('chatbot returns a grounded answer', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('textbox', { name: /ask/i }).fill('What services does Godeltech offer?')
  await page.getByRole('button', { name: /send/i }).click()
  await expect(page.getByTestId('chat-response')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByTestId('chat-response')).not.toBeEmpty()
})

test('chatbot shows error state on API failure', async ({ page }) => {
  await page.route('/api/chat', route => route.fulfill({ status: 500 }))
  await page.goto('/')
  await page.getByRole('textbox', { name: /ask/i }).fill('hello')
  await page.getByRole('button', { name: /send/i }).click()
  await expect(page.getByRole('alert')).toBeVisible()
})
```

### Feedback Dashboard (`feedback.spec.ts`)
```ts
import { test, expect } from '../fixtures/auth'

test('feedback dashboard renders summary cards', async ({ page }) => {
  await page.route('/api/feedback/summary*', route =>
    route.fulfill({
      json: { strengths: ['Leadership'], weaknesses: [], risks: [], team_dynamics_signals: [], confidence_score: 0.9 },
    })
  )
  await page.goto('/feedback')
  await expect(page.getByTestId('strengths-card')).toContainText('Leadership')
  await expect(page.getByTestId('confidence-score')).toContainText('0.9')
})
```

### Team Assembler (`team-assembler.spec.ts`)
```ts
import { test, expect } from '../fixtures/auth'

test('team assembler shows match scores', async ({ page }) => {
  await page.route('/api/teams/assemble', route =>
    route.fulfill({
      json: { team: [{ employee_id: 'uuid-1', role: 'backend', match_score: 0.92 }], gaps: [], risks: [], alternatives: [] },
    })
  )
  await page.goto('/teams')
  await page.getByRole('textbox', { name: /project description/i }).fill('Build a REST API')
  await page.getByRole('button', { name: /assemble/i }).click()
  await expect(page.getByTestId('team-member-uuid-1')).toContainText('0.92')
})
```

## CI — GitHub Actions Job
Add a separate job in the deploy workflow (after the Cloud Run deploy step):

```yaml
  e2e:
    name: Playwright E2E
    runs-on: ubuntu-latest
    needs: deploy   # run after the Cloud Run deploy job
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'

      - name: Install Playwright deps
        run: npm install --prefix e2e --package-lock=false

      - name: Install browsers
        run: npx --prefix e2e playwright install --with-deps chromium

      - name: Run E2E tests
        env:
          BASE_URL: ${{ steps.deploy.outputs.url }}  # Cloud Run URL from deploy job
        run: npx --prefix e2e playwright test

      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: e2e/playwright-report/
```

## `data-testid` Convention
Every interactive element tested by Playwright MUST carry a `data-testid` attribute — do NOT rely
on brittle CSS selectors or positional locators:
```tsx
<div data-testid="chat-response">{response}</div>
<button data-testid="send-button">Send</button>
```
Use `getByRole` for semantic elements (buttons, inputs, headings) and `getByTestId` for containers.

## Security
- Never hardcode real credentials in `e2e/` tests. Use `process.env.*` and inject from CI secrets.
- Mock all `/api/*` routes that touch real user data in tests that don't need live API responses —
  prevents PII leakage into test reports.
