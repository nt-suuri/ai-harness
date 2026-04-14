# ai-harness — Phase 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a deployable monorepo: FastAPI `/ping` endpoint + Vite/React shell + a CI gate on every PR + a manual-trigger Fly deploy. Exit criterion: `curl https://<app>.fly.dev/ping` returns `pong` AND any PR blocks merge until CI is green.

**Architecture:** Single git repo, uv-managed Python workspace, pnpm-managed JS workspace, two Fly processes (one app, two processes — `api` and `web`). CI is one GitHub Actions workflow. Deploy is one workflow triggered on push to `main`. No agents yet — Phase 2-7 add those.

**Tech Stack:** Python 3.12 + uv + FastAPI + sentry-sdk; TypeScript + Vite + React 19 + @sentry/react; pnpm 9; GitHub Actions; Fly.io (flyctl); ruff, mypy, pytest, vitest, playwright.

**Working directory for every command:** `/Users/nt-suuri/workspace/lab/ai-harness` unless stated otherwise.

---

## File Structure

```
ai-harness/
├── .github/workflows/
│   ├── ci.yml                PR gate
│   └── deploy.yml            manual trigger + push to main (no rollback yet)
├── .gitignore
├── apps/
│   ├── api/
│   │   ├── pyproject.toml
│   │   ├── src/api/__init__.py
│   │   ├── src/api/main.py
│   │   ├── src/api/sentry.py
│   │   └── tests/test_ping.py
│   └── web/
│       ├── package.json
│       ├── vite.config.ts
│       ├── tsconfig.json
│       ├── index.html
│       ├── src/main.tsx
│       ├── src/App.tsx
│       ├── src/sentry.ts
│       └── src/App.test.tsx
├── docs/superpowers/plans/
│   └── 2026-04-14-phase-1-foundation.md   (this file)
├── CLAUDE.md                  operator runbook (stub)
├── Dockerfile                 multi-stage: build web, bundle with api
├── fly.toml                   one app, two processes
├── package.json               pnpm workspace root
├── pnpm-workspace.yaml
├── pyproject.toml             uv workspace root
└── README.md
```

Every file listed above is created by a task below. No file is silently assumed.

---

## Conventions (apply to every task)

- **Commit cadence:** every task ends with a commit. Commit message format: `feat(<area>): <what>` or `chore(<area>): <what>`. `<area>` ∈ {`repo`, `api`, `web`, `ci`, `deploy`, `docs`}.
- **After every commit, push:** `git push` (within this lab the spec permits it).
- **Run commands from repo root** unless a task says otherwise.
- **Python:** always `uv run <tool>`, never plain `pytest`/`ruff`/`mypy`.
- **JS:** always `pnpm <cmd>`, never npm or yarn.

---

### Task 1: Initialize empty repo + .gitignore + README

**Files:**
- Create: `.gitignore`
- Create: `README.md`

- [ ] **Step 1: Verify directory is empty, then init git**

Run:
```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
ls -A
git init -b main
git config user.name "ai-harness-bot"
git config user.email "ai-harness@local"
```
Expected: `ls -A` prints nothing; `git init` prints `Initialized empty Git repository in .../ai-harness/.git/`.

- [ ] **Step 2: Write `.gitignore`**

Create `.gitignore`:
```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.ruff_cache/
.mypy_cache/
.pytest_cache/
dist/
build/

# JS
node_modules/
.pnpm-store/
apps/web/dist/
playwright-report/
test-results/

# Env
.env
.env.local
.env.*.local

# Editors
.vscode/
.idea/
.DS_Store

# Fly
.fly/
```

- [ ] **Step 3: Write `README.md`**

Create `README.md`:
```markdown
# ai-harness

Solo 24/7 AI development harness. See `docs/superpowers/plans/` for phase plans and
`/Users/nt-suuri/.claude/plans/structured-whistling-thompson.md` for the master spec.

## Quickstart

```bash
uv sync
pnpm install
uv run pytest
pnpm -r test
```

## Layout

- `apps/api` — FastAPI backend
- `apps/web` — Vite + React frontend
- `agents/` — Python agents (added in Phase 2+)
- `.github/workflows/` — CI + deploy
```
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore README.md
git commit -m "chore(repo): initialize repo with gitignore and README"
```

Do NOT push yet — no remote configured. Remote setup lands in Task 13.

---

### Task 2: Python workspace root (`pyproject.toml`)

**Files:**
- Create: `pyproject.toml` (workspace root, not a package)

- [ ] **Step 1: Write root `pyproject.toml`**

Create `pyproject.toml`:
```toml
[project]
name = "ai-harness"
version = "0.0.0"
description = "Solo 24/7 AI development harness"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["apps/api"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["apps/api/tests"]
pythonpath = ["apps/api/src"]
```

- [ ] **Step 2: Verify uv sees the workspace**

Run: `uv sync --dry-run`
Expected: output mentions `workspace` and does not error. (It will say nothing to sync yet because `apps/api` doesn't exist — that's fine, the next task creates it.)

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore(repo): add uv workspace root"
```

---

### Task 3: Write the failing test for `/ping`

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/src/api/__init__.py`
- Create: `apps/api/tests/__init__.py`
- Create: `apps/api/tests/test_ping.py`

- [ ] **Step 1: Create `apps/api/pyproject.toml`**

```toml
[project]
name = "api"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sentry-sdk[fastapi]>=2.18",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
    "ruff>=0.7",
    "mypy>=1.13",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/api"]
```

- [ ] **Step 2: Create empty `__init__.py` files**

```bash
mkdir -p apps/api/src/api apps/api/tests
: > apps/api/src/api/__init__.py
: > apps/api/tests/__init__.py
```

- [ ] **Step 3: Write the failing test**

Create `apps/api/tests/test_ping.py`:
```python
from fastapi.testclient import TestClient

from api.main import app


def test_ping_returns_pong() -> None:
    client = TestClient(app)
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "pong"}
```

- [ ] **Step 4: Sync and run the test — expect FAIL**

```bash
uv sync --all-extras
uv run pytest apps/api/tests/test_ping.py -v
```
Expected: `ModuleNotFoundError: No module named 'api.main'` or `ImportError`. This is the expected red state.

- [ ] **Step 5: Commit the failing test**

```bash
git add apps/api/pyproject.toml apps/api/src/api/__init__.py apps/api/tests/__init__.py apps/api/tests/test_ping.py pyproject.toml uv.lock
git commit -m "test(api): add failing /ping test"
```

---

### Task 4: Make `/ping` pass

**Files:**
- Create: `apps/api/src/api/main.py`

- [ ] **Step 1: Write `main.py`**

Create `apps/api/src/api/main.py`:
```python
from fastapi import FastAPI

app = FastAPI(title="ai-harness api")


@app.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "pong"}
```

- [ ] **Step 2: Run the test — expect PASS**

Run: `uv run pytest apps/api/tests/test_ping.py -v`
Expected: `1 passed`.

- [ ] **Step 3: Run ruff + mypy to confirm clean**

```bash
uv run ruff check apps/api
uv run mypy apps/api/src
```
Expected: both exit 0 with no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/api/main.py
git commit -m "feat(api): implement /ping endpoint"
```

---

### Task 5: Sentry init on the API (DSN-optional)

**Files:**
- Create: `apps/api/src/api/sentry.py`
- Modify: `apps/api/src/api/main.py`
- Create: `apps/api/tests/test_sentry.py`

Sentry init must be **safe when `SENTRY_DSN` is unset** — local dev and CI run without it. Only production has a real DSN.

- [ ] **Step 1: Write failing test**

Create `apps/api/tests/test_sentry.py`:
```python
import os
from unittest.mock import patch

from api.sentry import init_sentry


def test_init_sentry_noop_when_dsn_missing() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert init_sentry() is False


def test_init_sentry_called_when_dsn_set() -> None:
    with patch.dict(os.environ, {"SENTRY_DSN": "https://k@s.io/1"}):
        with patch("api.sentry.sentry_sdk.init") as mock_init:
            assert init_sentry() is True
            mock_init.assert_called_once()
```

- [ ] **Step 2: Run test — expect FAIL (module missing)**

Run: `uv run pytest apps/api/tests/test_sentry.py -v`
Expected: `ModuleNotFoundError: No module named 'api.sentry'`.

- [ ] **Step 3: Implement `sentry.py`**

Create `apps/api/src/api/sentry.py`:
```python
import os

import sentry_sdk


def init_sentry() -> bool:
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=0.1,
        environment=os.environ.get("ENV", "local"),
        release=os.environ.get("FLY_RELEASE_VERSION", "dev"),
    )
    return True
```

- [ ] **Step 4: Wire into `main.py`**

Replace `apps/api/src/api/main.py` contents:
```python
from fastapi import FastAPI

from api.sentry import init_sentry

init_sentry()

app = FastAPI(title="ai-harness api")


@app.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "pong"}
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `uv run pytest apps/api -v`
Expected: 3 tests pass (`test_ping_returns_pong` plus the two Sentry tests).

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/api/sentry.py apps/api/src/api/main.py apps/api/tests/test_sentry.py
git commit -m "feat(api): wire sentry init (DSN-optional)"
```

---

### Task 6: Scaffold the React app via Vite

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/index.html`
- Create: `apps/web/src/main.tsx`
- Create: `apps/web/src/App.tsx`
- Create: `apps/web/src/sentry.ts`
- Create: `apps/web/src/App.test.tsx`

- [ ] **Step 1: Create pnpm workspace root files**

Create `package.json`:
```json
{
  "name": "ai-harness",
  "private": true,
  "packageManager": "pnpm@9.12.0",
  "scripts": {
    "dev": "pnpm --filter web dev",
    "build": "pnpm --filter web build",
    "test": "pnpm -r test"
  }
}
```

Create `pnpm-workspace.yaml`:
```yaml
packages:
  - "apps/web"
```

- [ ] **Step 2: Create `apps/web/package.json`**

```json
{
  "name": "web",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@sentry/react": "^8.38.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.4",
    "jsdom": "^25.0.1",
    "typescript": "^5.7.2",
    "vite": "^6.0.3",
    "vitest": "^2.1.8"
  }
}
```

- [ ] **Step 3: Create `apps/web/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create `apps/web/vite.config.ts`**

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
  },
});
```

- [ ] **Step 5: Create `apps/web/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ai-harness</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Create `apps/web/src/sentry.ts`**

```ts
import * as Sentry from "@sentry/react";

export function initSentry(): boolean {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return false;
  Sentry.init({
    dsn,
    environment: import.meta.env.MODE,
    tracesSampleRate: 0.1,
  });
  return true;
}
```

- [ ] **Step 7: Create `apps/web/src/App.tsx`**

```tsx
export function App() {
  return (
    <main>
      <h1>ai-harness</h1>
      <p>Phase 1: foundation.</p>
    </main>
  );
}
```

- [ ] **Step 8: Create `apps/web/src/main.tsx`**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { initSentry } from "./sentry";

initSentry();

const root = document.getElementById("root");
if (!root) throw new Error("missing #root");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 9: Write failing component test**

Create `apps/web/src/App.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { App } from "./App";

describe("App", () => {
  it("renders the harness header", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /ai-harness/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 10: Install deps and run tests**

```bash
pnpm install
pnpm --filter web test
pnpm --filter web typecheck
pnpm --filter web build
```
Expected: test passes (1 test, 1 assertion), typecheck exits 0, build produces `apps/web/dist/`.

- [ ] **Step 11: Commit**

```bash
git add apps/web package.json pnpm-workspace.yaml pnpm-lock.yaml
git commit -m "feat(web): scaffold Vite+React shell with Sentry init"
```

---

### Task 7: Dockerfile that bundles api + web

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

The Fly app serves static web assets from the FastAPI process under `/`, and the api under `/api/*`. Keeps deploy to one process.

- [ ] **Step 1: Update `apps/api/src/api/main.py` to serve static web build**

Replace contents:
```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.sentry import init_sentry

init_sentry()

app = FastAPI(title="ai-harness api")


@app.get("/api/ping")
def ping() -> dict[str, str]:
    return {"status": "pong"}


_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="web")
```

- [ ] **Step 2: Update the ping test for new path**

Replace `apps/api/tests/test_ping.py`:
```python
from fastapi.testclient import TestClient

from api.main import app


def test_ping_returns_pong() -> None:
    client = TestClient(app)
    response = client.get("/api/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "pong"}
```

- [ ] **Step 3: Run test — expect PASS**

Run: `uv run pytest apps/api -v`
Expected: 3 tests pass.

- [ ] **Step 4: Write `Dockerfile`**

```dockerfile
# --- web build stage ---
FROM node:22-alpine AS web-build
WORKDIR /repo
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile --filter web
COPY apps/web apps/web
RUN pnpm --filter web build

# --- api runtime stage ---
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/api/src apps/api/src
RUN uv sync --frozen --no-dev
COPY --from=web-build /repo/apps/web/dist /app/apps/api/src/api/static
EXPOSE 8080
CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 5: Write `.dockerignore`**

```
.git/
.venv/
node_modules/
apps/web/dist/
apps/web/node_modules/
**/__pycache__/
**/.pytest_cache/
**/.mypy_cache/
**/.ruff_cache/
.github/
docs/
```

- [ ] **Step 6: Build locally to verify**

Run: `docker build -t ai-harness:test .`
Expected: build succeeds, final image tags `ai-harness:test`. If docker is not available locally, skip this step — CI will catch it in Task 9.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile .dockerignore apps/api/src/api/main.py apps/api/tests/test_ping.py
git commit -m "feat(repo): dockerize api+web as single-image deploy"
```

---

### Task 8: Playwright smoke test

**Files:**
- Create: `apps/web/playwright.config.ts`
- Create: `apps/web/e2e/ping.spec.ts`
- Modify: `apps/web/package.json` (add playwright dep + script)

- [ ] **Step 1: Add playwright to web package**

Edit `apps/web/package.json` devDependencies — add `"@playwright/test": "^1.49.0"`. Edit scripts — add `"e2e": "playwright test"`.

- [ ] **Step 2: Install**

```bash
pnpm install
pnpm --filter web exec playwright install --with-deps chromium
```

- [ ] **Step 3: Write `playwright.config.ts`**

Create `apps/web/playwright.config.ts`:
```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080" },
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command:
          "cd ../.. && uv run uvicorn api.main:app --host 127.0.0.1 --port 8080",
        url: "http://127.0.0.1:8080/api/ping",
        reuseExistingServer: false,
        timeout: 60_000,
      },
});
```

- [ ] **Step 4: Write e2e spec**

Create `apps/web/e2e/ping.spec.ts`:
```ts
import { expect, test } from "@playwright/test";

test("api /api/ping returns pong", async ({ request }) => {
  const res = await request.get("/api/ping");
  expect(res.status()).toBe(200);
  expect(await res.json()).toEqual({ status: "pong" });
});
```

- [ ] **Step 5: Run locally — expect PASS**

Run: `pnpm --filter web e2e`
Expected: 1 test passed. Playwright auto-starts uvicorn via the `webServer` block.

- [ ] **Step 6: Commit**

```bash
git add apps/web/playwright.config.ts apps/web/e2e/ping.spec.ts apps/web/package.json pnpm-lock.yaml
git commit -m "test(web): add playwright smoke for /api/ping"
```

---

### Task 9: CI workflow (`.github/workflows/ci.yml`)

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: ci

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --all-extras --frozen
      - run: uv run ruff check .
      - run: uv run mypy apps/api/src
      - run: uv run pytest apps/api -v

  web:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9.12.0
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter web typecheck
      - run: pnpm --filter web test
      - run: pnpm --filter web build

  e2e:
    runs-on: ubuntu-latest
    needs: [python, web]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - uses: pnpm/action-setup@v4
        with:
          version: 9.12.0
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: pnpm
      - run: uv sync --all-extras --frozen
      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter web exec playwright install --with-deps chromium
      - run: pnpm --filter web e2e

  docker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: false
          tags: ai-harness:ci
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add PR gate (python, web, e2e, docker)"
```

---

### Task 10: Fly.io config (`fly.toml`)

**Files:**
- Create: `fly.toml`

Fly app name: **`ai-harness`** (adjust in Task 13 if taken). Region: `nrt` (Tokyo — matches user timezone). Primary process serves both static web and api on port 8080.

- [ ] **Step 1: Write `fly.toml`**

```toml
app = "ai-harness"
primary_region = "nrt"

[build]
  dockerfile = "Dockerfile"

[env]
  ENV = "production"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = "suspend"
  auto_start_machines = true
  min_machines_running = 0

  [[http_service.checks]]
    grace_period = "10s"
    interval = "30s"
    method = "GET"
    path = "/api/ping"
    timeout = "5s"

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 256
```

- [ ] **Step 2: Commit**

```bash
git add fly.toml
git commit -m "chore(deploy): add fly.toml"
```

---

### Task 11: Deploy workflow (`.github/workflows/deploy.yml`)

**Files:**
- Create: `.github/workflows/deploy.yml`

This deploys on every push to `main` AND on manual `workflow_dispatch`. No rollback yet — Phase 5 adds the watcher.

- [ ] **Step 1: Write the workflow**

```yaml
name: deploy

on:
  push:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: deploy
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
    steps:
      - name: Check kill-switch
        env:
          PAUSE: ${{ vars.PAUSE_AGENTS }}
        run: |
          if [ "${PAUSE}" = "true" ]; then
            echo "PAUSE_AGENTS=true — skipping deploy"
            exit 0
          fi
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only --wait-timeout 300
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci(deploy): add push-to-main deploy workflow"
```

---

### Task 12: `CLAUDE.md` operator runbook

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Write `CLAUDE.md`**

```markdown
# ai-harness — operator rules

## Autonomy scope

- Agents MAY `git commit`, `git push`, and deploy **only within this repo**.
- Global user rules still apply outside this repo.
- Kill-switch: set repo variable `PAUSE_AGENTS=true` to halt every workflow.

## Branch protection (must be configured on GitHub)

- `main` is protected.
- Required checks: `ci / python`, `ci / web`, `ci / e2e`, `ci / docker`.
- Phase 3 will add `reviewer / quality`, `reviewer / security`, `reviewer / deps`.
- Require 1 human approval. No force-push. No direct push to `main`.

## Secrets

Stored as repo secrets:

| Secret | Used by | Phase added |
|---|---|---|
| `FLY_API_TOKEN` | deploy.yml | 1 |
| `ANTHROPIC_API_KEY` | all agents | 2 |
| `SENTRY_AUTH_TOKEN` | triager, healthcheck | 6 |
| `RESEND_API_KEY` | healthcheck | 7 |

## Local dev

```bash
uv sync --all-extras
pnpm install
# api
uv run uvicorn api.main:app --reload --port 8080
# web
pnpm --filter web dev
```
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(repo): add CLAUDE.md operator runbook"
```

---

### Task 13: Create GitHub remote + Fly app + secrets, then push

This task has **manual steps the agent cannot do for you**. Follow them in order.

- [ ] **Step 1: Create the GitHub repo**

Run (requires `gh` CLI authenticated as the user):
```bash
gh repo create ai-harness --private --source=. --remote=origin
```
If `gh` is not available: create `ai-harness` on github.com manually, then:
```bash
git remote add origin git@github.com:<your-user>/ai-harness.git
```

- [ ] **Step 2: Push**

```bash
git push -u origin main
```
Expected: push succeeds.

- [ ] **Step 3: Create Fly app**

```bash
flyctl auth login     # interactive, only if not already logged in
flyctl apps create ai-harness --org personal
```
If the name is taken, pick `ai-harness-<yourinitials>` and update `app = ` in `fly.toml`, commit, push.

- [ ] **Step 4: Get a Fly deploy token**

```bash
flyctl tokens create deploy -x 999999h -a ai-harness
```
Copy the token output.

- [ ] **Step 5: Set the GitHub secret**

```bash
gh secret set FLY_API_TOKEN --body "<paste token>"
```

- [ ] **Step 6: Configure branch protection**

Run:
```bash
gh api -X PUT "repos/{owner}/{repo}/branches/main/protection" \
  -F required_status_checks.strict=true \
  -F 'required_status_checks.contexts[]=ci / python' \
  -F 'required_status_checks.contexts[]=ci / web' \
  -F 'required_status_checks.contexts[]=ci / e2e' \
  -F 'required_status_checks.contexts[]=ci / docker' \
  -F enforce_admins=false \
  -F required_pull_request_reviews.required_approving_review_count=1 \
  -F restrictions= \
  -F allow_force_pushes=false \
  -F allow_deletions=false
```

- [ ] **Step 7: Commit any `fly.toml` rename (if step 3 forced one)**

```bash
git add fly.toml
git commit -m "chore(deploy): adjust fly app name" || echo "no change"
git push
```

---

### Task 14: First deploy + smoke test

- [ ] **Step 1: Trigger deploy via workflow_dispatch**

Run: `gh workflow run deploy.yml`

Or push any no-op commit to `main`:
```bash
git commit --allow-empty -m "chore(deploy): trigger first deploy"
git push
```

- [ ] **Step 2: Watch it succeed**

Run: `gh run watch`
Expected: `deploy / deploy` turns green within ~5 min.

- [ ] **Step 3: Hit the endpoint**

```bash
curl -sS https://ai-harness.fly.dev/api/ping
```
Expected: `{"status":"pong"}`

If you renamed the app in Task 13 step 3, use that hostname.

- [ ] **Step 4: Verify static web loads**

```bash
curl -sS -I https://ai-harness.fly.dev/ | head -1
```
Expected: `HTTP/2 200`.

- [ ] **Step 5: Celebrate the exit criterion**

Phase 1 is done when all of:

- [ ] `curl https://ai-harness.fly.dev/api/ping` returns `{"status":"pong"}`
- [ ] GitHub branch protection blocks merge to `main` without green CI + 1 approval
- [ ] A PR opened against `main` runs the 4 CI jobs (python, web, e2e, docker) and they all pass

No commit for this task — it's pure verification.

---

## Phase 1 exit checklist

- [ ] Working Fly deploy at `https://ai-harness.fly.dev/api/ping`
- [ ] Branch protection configured with the 4 CI checks required
- [ ] All 10+ commits pushed to `origin/main`
- [ ] `CLAUDE.md` committed
- [ ] `FLY_API_TOKEN` secret set
- [ ] Kill-switch variable `PAUSE_AGENTS` created (can be empty — workflow treats missing as off)

## What this phase does NOT build (deferred)

| Feature | Phase |
|---|---|
| `agents/` package + shared lib | 2 |
| Reviewer agent + 3-pass review | 3 |
| Planner agent + `agent:build` label | 4 |
| Auto-rollback + circuit breaker | 5 |
| Triager + self-healing loop | 6 |
| Healthcheck + email digest | 7 |
| Canary replay harness | 7 |

Each gets its own plan file in `docs/superpowers/plans/`.

## Self-review notes

- All file paths are relative to `/Users/nt-suuri/workspace/lab/ai-harness`.
- Every code step includes full code, not a diff hint.
- Every test step states expected pass/fail.
- Task 13 manual steps are clearly flagged.
- The `/ping` path moves from `/ping` → `/api/ping` in Task 7; tests and the Fly healthcheck are updated in-lock.
- `uv.lock` and `pnpm-lock.yaml` are committed when they first appear (Task 3, Task 6).
