---
skill_id: react_frontend
type: domain
triggers: [react, frontend, vite, tsx, spa, dashboard, ui]
nodes: [techlead, developer, qa, reviewer]
---
LANGUAGE TARGET: React 19 + TypeScript (Vite SPA) — production rules for frontend code executed in
the `node:22-alpine` sandbox and served as a static bundle by the backend server.

---

## Monorepo Layout (fullstack Python + React coexistence) — CRITICAL

When this SPA lives in the **same repository as a Python backend** (FastAPI in `src/`), the
following layout is MANDATORY — the engine runs `npm ci` and `npm test` from the **repo root**:

```
<repo-root>/
  package.json       ← MUST be at root (engine sandbox drives npm from here)
  package-lock.json  ← committed; npm ci restores from this
  vite.config.ts     ← at root
  tsconfig.json      ← at root
  tsconfig.app.json  ← at root
  index.html         ← Vite entry point, at root
  eslint.config.js   ← at root (lint gate checks here)
  frontend/          ← ALL React/TypeScript source lives here (NOT src/ — reserved for Python)
    main.tsx
    App.tsx
    components/
    pages/
    api/
  static/            ← empty placeholder dir; CI copies dist/ here for FastAPI StaticFiles
  src/               ← Python backend (DO NOT put React files here)
  requirements.txt
```

- **`frontend/` not `src/`** — `src/` is reserved for the Python package. A `frontend/` source dir
  avoids the naming collision and signals intent to every reader.
- **`package.json` at root** — the `node-22-web` sandbox runs `npm ci` and `npm test` from the
  repo root. A `package.json` only inside `frontend/` is invisible to the pipeline.
- **`static/` placeholder** — create an empty `static/.gitkeep`; FastAPI mounts it via
  `StaticFiles(directory="static", html=True)`. CI populates it from the Vite build (`dist/`).

---

## Scaffold & Toolchain

- `package.json` MUST include `"build": "tsc -b && vite build"` and `"test": "vitest run"`. The engine drives tests via `npm test` — exit non-zero on failure.
- Always commit `package-lock.json`; `npm ci` restores deterministically.
- **TypeScript strict mode** (`"strict": true`). `tsc --noEmit` MUST pass with zero errors.
- `vite.config.ts` (at root): point Vite at the `frontend/` source dir, enable the **React
  Compiler**, API proxy for dev, and configure Vitest test includes:
  ```ts
  import { defineConfig } from 'vite'
  import react from '@vitejs/plugin-react'
  import tailwindcss from '@tailwindcss/vite'

  export default defineConfig({
    root: '.',
    build: { outDir: 'dist' },
    plugins: [
      react({ babel: { plugins: [['babel-plugin-react-compiler', {}]] } }),
      tailwindcss(),
    ],
    server: { proxy: { '/api': 'http://localhost:8080' } },
    test: {
      environment: 'jsdom',
      include: ['frontend/**/*.{test,spec}.{ts,tsx}'],
      globals: true,
      setupFiles: ['frontend/setupTests.ts'],
    },
  })
  ```
  In production the SPA and API share the same origin (FastAPI serves `static/`).

**Minimal runtime deps:** `react@19`, `react-dom@19`, `react-router-dom` v6, `@tanstack/react-query` v5, Tailwind CSS (`tailwindcss`, `@tailwindcss/vite`). **devDep:** `babel-plugin-react-compiler`. No Redux, no Zustand — React Query for GET queries; `useActionState`/`useContext` for form/UI state.

---

## Component & Type Patterns — HIGH

- **Function components only** — named `function`, not `const Arrow =`, so React DevTools shows the name automatically.
- **Ban `any`** — validate API shapes at the boundary with an explicit `interface`; never cast `response.json() as T` without a guard.
- **Props: interfaces, not inline types** for shapes with more than 2 fields.
- **Explicit conditional rendering** — `condition ? <A /> : null`; never `condition && <A />` when condition can be `0` or `NaN`:
  ```tsx
  {count > 0 ? <Badge count={count} /> : null}  // Correct
  {count && <Badge count={count} />}             // Incorrect — renders "0"
  ```
- **Hoist static JSX** to module scope — avoids object re-creation on every render.
- **`useId()`** for form label/input association (React 18+). Never `Math.random()` for element IDs — causes hydration mismatches:
  ```tsx
  function EmailField() {
    const id = useId()
    return <><label htmlFor={id}>Email</label><input id={id} type="email" /></>
  }
  ```
- **Array immutability in state** — `.sort()` mutates in-place and breaks React reconciliation:
  ```ts
  const sorted = items.toSorted((a, b) => a.score - b.score)   // ES2023
  const sorted = [...items].sort((a, b) => a.score - b.score)  // fallback
  ```

---

## Data Fetching — CRITICAL

**Use `@tanstack/react-query` for ALL server state.** `useEffect + useState` for fetching produces no deduplication, no loading/error states, and no cache.

```ts
// api/client.ts — typed fetch wrapper; single place for the auth header
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = sessionStorage.getItem('jwt')
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  })
  if (!res.ok) throw new ApiError(res.status, await res.text())
  return res.json() as Promise<T>
}
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}
```

```ts
// Query
const { data, isPending } = useQuery({ queryKey: ['key'], queryFn: () => apiFetch<T>('/api/...') })
// Mutation
const mutation = useMutation({
  mutationFn: (body: Req) => apiFetch<Res>('/api/...', { method: 'POST', body: JSON.stringify(body) }),
})
```

**No waterfalls** — independent fetches run in parallel via `Promise.all` or React Query `enabled`; never sequential `await` chains for unrelated resources.

**React 19 form actions** — use `useActionState` instead of `useState + onSubmit` for mutations that originate from forms:
```ts
const [state, formAction, isPending] = useActionState(
  async (_prev: Result | null, formData: FormData) =>
    apiFetch<Result>('/api/...', { method: 'POST', body: JSON.stringify(Object.fromEntries(formData)) }),
  null
)
// <form action={formAction}> — no onSubmit, no manual isPending state
```

**Optimistic UI** — use `useOptimistic` for instant feedback before the server responds (chat messages, list appends):
```ts
const [optimistic, addOptimistic] = useOptimistic(
  messages,
  (prev, msg: Message) => [...prev, { ...msg, pending: true }]
)
// addOptimistic({ role: 'user', text }) renders immediately; replaced by real state on resolve
```

---

## Re-render Optimization — MEDIUM

- **Narrow effect deps** — `[user.id]` not `[user]`; primitive values only.
- **Lazy state init** for storage reads: `useState(() => sessionStorage.getItem('jwt'))`.
- **React Compiler handles memoization** — do NOT add `memo`, `useMemo`, or `useCallback` pre-emptively. The Compiler auto-memoizes components and derived values. Only add manual memoization when the profiler shows a specific bottleneck the Compiler missed.
- **`startTransition`** — for non-urgent updates (search, filter) to keep UI responsive.
- **Stable callbacks in effects** (`useLatest` pattern) — read the latest callback without adding it to effect deps; prevents stale closures and avoids unnecessary re-runs:
  ```ts
  function useLatest<T>(value: T) {
    const ref = useRef(value)
    useEffect(() => { ref.current = value }, [value])
    return ref
  }
  // const cbRef = useLatest(onSearch)
  // useEffect(() => { cbRef.current(query) }, [query])  // onSearch NOT in deps
  ```
- **`content-visibility: auto`** on list items (100+ rows):
  ```css
  .list-item { content-visibility: auto; contain-intrinsic-size: 0 64px; }
  ```

---

## Bundle Size — HIGH

- **Direct imports, not barrel files** — barrel re-exports load entire libraries (1500+ modules for icon libs). Configure `optimizePackageImports` in `vite.config.ts` for known-heavy packages.
- **`lazy()` + `<Suspense>`** for routes and heavy components not needed on initial render:
  ```ts
  const FeedbackPage = lazy(() => import('./pages/FeedbackPage'))
  // <Suspense fallback={<Skeleton />}><FeedbackPage /></Suspense>
  ```
- **Defer non-critical libs** (analytics, monitoring) — load after mount, not in the top bundle.

---

## Auth & Security — HIGH

- **JWT in `sessionStorage` only** — tab-scoped, clears on close. `localStorage` persists across sessions and is not suitable for PII-access tokens.
- **`ProtectedRoute`** — redirect before rendering any protected content:
  ```tsx
  function ProtectedRoute({ children }: { children: ReactNode }) {
    const token = useAuthToken()  // reads sessionStorage; null if absent
    return token ? <>{children}</> : <Navigate to="/login" replace />
  }
  ```
- **Never log tokens, passwords, or PII** to `console.*`.
- **No `dangerouslySetInnerHTML`** with user-controlled content; sanitize with `DOMPurify` if rich text is required.
- **`npm audit --audit-level=high`** in CI — zero tolerance for HIGH vulnerabilities.

---

## Build Integration — MEDIUM

Multi-stage Dockerfile: Node stage builds `frontend/dist/`; Python stage copies it in:
```dockerfile
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
# ... install Python deps ...
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
```

FastAPI SPA mount — **skip gracefully if `dist/` is absent** so `/health` always responds:
```python
DIST = Path(__file__).parent / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
    @app.get("/{p:path}", include_in_schema=False)
    async def spa(p: str) -> FileResponse:
        return FileResponse(DIST / "index.html")
```

---

## Test Pattern — HIGH

- Runner: **Vitest** + **`@testing-library/react`**. Do NOT add Jest alongside.
- Colocate: `ChatPage.tsx` → `ChatPage.test.tsx`.
- **`act()` — import from `react`**, not `react-dom/test-utils` (deprecated React 18, removed React 19):
  ```ts
  import { act } from 'react'                    // Correct
  import { act } from 'react-dom/test-utils'     // Incorrect — removed in React 19
  ```
  React 19 removed API map: `Simulate.*` → `fireEvent.*`; `renderIntoDocument` → `render`; `findRenderedDOMComponentWithTag` → `getByRole`.
- **StrictMode call counts (React 19)** — `useEffect` no longer double-invokes in development. A spy that expected 2 calls (React 18 strict) should now expect 1. Render-phase code (component body) still fires twice.
- **Mock `fetch` globally** in `vitest.setup.ts` (`global.fetch = vi.fn()`).
  Per-test: `vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({...}), { status: 200 }))`.
  After each: `vi.clearAllMocks()`.
- **Mock `sessionStorage`**: `vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('mock-jwt')`.
- **Test shape:** `describe` / `it`; `userEvent` for interactions (not `fireEvent`); React Query wrapper:
  ```ts
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {children}
    </QueryClientProvider>
  )
  // render(<Page />, { wrapper })
  // await userEvent.click(screen.getByRole('button', { name: /send/i }))
  // expect(await screen.findByText(/result/i)).toBeInTheDocument()
  ```
- **Assert on role/label/text, never CSS class names.** `findBy*` for async; `getBy*` for synchronously present elements.
