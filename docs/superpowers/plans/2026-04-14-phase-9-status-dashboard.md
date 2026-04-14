# ai-harness — Phase 9: Status Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Add `GET /api/status` to the FastAPI backend that returns a JSON snapshot of the harness state — recent CI runs, recent deploys, open agent-issues count. Add a small React Dashboard component that fetches this and shows it. Makes the harness state visible at a glance from the deployed app.

**Architecture:**
- `apps/api/src/api/status.py` — new module with the `/api/status` endpoint, takes a fully-injected `gh_client` for testability.
- `apps/api/src/api/main.py` — register the router.
- `apps/web/src/Dashboard.tsx` — fetches `/api/status` and renders a status card.
- `apps/web/src/App.tsx` — embed `<Dashboard />` below the existing header.

No external API keys needed. The endpoint reads from the GitHub API using the same `GITHUB_TOKEN` env var as the agents.

**Tech Stack:** FastAPI, PyGithub, React 19. No new deps.

---

## File Structure

```
apps/api/src/api/
├── status.py                           NEW — GET /api/status
└── main.py                             MODIFY — include status router

apps/api/tests/
└── test_status.py                      NEW

apps/web/src/
├── Dashboard.tsx                       NEW
├── Dashboard.test.tsx                  NEW
└── App.tsx                             MODIFY — embed Dashboard
```

---

## Conventions

- Direct commits/pushes to main permitted.
- Push: `TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main`

---

### Task 1: `GET /api/status` endpoint

**Files:**
- Create: `apps/api/src/api/status.py`
- Modify: `apps/api/src/api/main.py`
- Create: `apps/api/tests/test_status.py`

- [ ] **Step 1: Failing tests**

Create `apps/api/tests/test_status.py`:

```python
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app


def test_status_returns_shape() -> None:
    fake_repo = MagicMock()
    fake_repo.get_workflow_runs.return_value = []
    fake_repo.get_issues.return_value = []

    with patch("api.status._repo", return_value=fake_repo):
        client = TestClient(app)
        resp = client.get("/api/status")

    assert resp.status_code == 200
    data = resp.json()
    assert "ci" in data
    assert "deploy" in data
    assert "open_autotriage_issues" in data
    assert isinstance(data["open_autotriage_issues"], int)


def test_status_counts_recent_runs() -> None:
    runs = [
        MagicMock(conclusion="success"),
        MagicMock(conclusion="success"),
        MagicMock(conclusion="failure"),
    ]
    fake_repo = MagicMock()

    def get_runs(workflow_file_name: str, **kwargs):
        if workflow_file_name == "ci.yml":
            return runs
        if workflow_file_name == "deploy.yml":
            return [MagicMock(conclusion="success")]
        return []

    fake_repo.get_workflow_runs.side_effect = get_runs
    fake_repo.get_issues.return_value = [MagicMock(), MagicMock()]

    with patch("api.status._repo", return_value=fake_repo):
        client = TestClient(app)
        resp = client.get("/api/status")

    data = resp.json()
    assert data["ci"]["success"] == 2
    assert data["ci"]["failure"] == 1
    assert data["deploy"]["success"] == 1
    assert data["deploy"]["failure"] == 0
    assert data["open_autotriage_issues"] == 2


def test_status_returns_503_when_no_token() -> None:
    with patch("api.status._repo", side_effect=KeyError("GITHUB_TOKEN")):
        client = TestClient(app)
        resp = client.get("/api/status")
    assert resp.status_code == 503
    assert "GITHUB_TOKEN" in resp.json()["detail"]
```

- [ ] **Step 2: Implement `status.py`**

Create `apps/api/src/api/status.py`:

```python
"""GET /api/status — snapshot of harness state from GitHub."""

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from github import Github
from github.Repository import Repository

router = APIRouter()

_DEFAULT_REPO = "nt-suuri/ai-harness"


def _repo() -> Repository:
    token = os.environ["GITHUB_TOKEN"]
    name = os.environ.get("GH_REPO", _DEFAULT_REPO)
    return Github(token).get_repo(name)


def _count_runs(repo: Repository, workflow_file: str) -> dict[str, int]:
    success = 0
    failure = 0
    for r in repo.get_workflow_runs(workflow_file_name=workflow_file)[:20]:
        if r.conclusion == "success":
            success += 1
        elif r.conclusion == "failure":
            failure += 1
    return {"success": success, "failure": failure}


@router.get("/api/status")
def get_status() -> dict[str, Any]:
    try:
        repo = _repo()
    except KeyError as e:
        raise HTTPException(status_code=503, detail=f"Missing env var: {e.args[0]}") from None

    ci = _count_runs(repo, "ci.yml")
    deploy = _count_runs(repo, "deploy.yml")
    autotriage_issues = list(repo.get_issues(state="open", labels=["autotriage"]))

    return {
        "ci": ci,
        "deploy": deploy,
        "open_autotriage_issues": len(autotriage_issues),
    }
```

- [ ] **Step 3: Register in main.py**

Edit `apps/api/src/api/main.py`. Add import + include_router. Final content:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.sentry import init_sentry
from api.status import router as status_router

init_sentry()

app = FastAPI(title="ai-harness api")
app.include_router(status_router)


@app.get("/api/ping")
def ping() -> dict[str, str]:
    return {"status": "pong"}


_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="web")
```

- [ ] **Step 4: Test + commit**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest apps/api -v
uv run ruff check apps/api
uv run mypy apps/api/src
git add apps/api/src/api/status.py apps/api/src/api/main.py apps/api/tests/test_status.py
git commit -m "feat(api): add GET /api/status endpoint"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

Expected: 6 passed (3 ping/sentry + 3 new status).

---

### Task 2: Dashboard React component

**Files:**
- Create: `apps/web/src/Dashboard.tsx`
- Create: `apps/web/src/Dashboard.test.tsx`
- Modify: `apps/web/src/App.tsx`

- [ ] **Step 1: Failing test**

Create `apps/web/src/Dashboard.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";

import { Dashboard } from "./Dashboard";

const mockFetch = vi.fn();

beforeEach(() => {
  mockFetch.mockReset();
  globalThis.fetch = mockFetch as unknown as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Dashboard", () => {
  it("shows loading initially", () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    render(<Dashboard />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("renders status when fetch resolves", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        ci: { success: 5, failure: 1 },
        deploy: { success: 2, failure: 0 },
        open_autotriage_issues: 3,
      }),
    });
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText(/CI/i)).toBeInTheDocument();
      expect(screen.getByText(/5/)).toBeInTheDocument();
    });
  });

  it("shows error message on fetch failure", async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 503 });
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Implement Dashboard**

Create `apps/web/src/Dashboard.tsx`:

```tsx
import { useEffect, useState } from "react";

interface Counts {
  success: number;
  failure: number;
}

interface Status {
  ci: Counts;
  deploy: Counts;
  open_autotriage_issues: number;
}

type State =
  | { kind: "loading" }
  | { kind: "ok"; data: Status }
  | { kind: "error"; status: number };

export function Dashboard() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    fetch("/api/status")
      .then(async (resp) => {
        if (!resp.ok) {
          setState({ kind: "error", status: resp.status });
          return;
        }
        const data = (await resp.json()) as Status;
        setState({ kind: "ok", data });
      })
      .catch(() => setState({ kind: "error", status: 0 }));
  }, []);

  if (state.kind === "loading") {
    return <section><p>Loading status…</p></section>;
  }
  if (state.kind === "error") {
    return <section><p>Status unavailable (HTTP {state.status})</p></section>;
  }
  const { data } = state;
  return (
    <section>
      <h2>Harness status</h2>
      <ul>
        <li>CI: {data.ci.success} success, {data.ci.failure} failure</li>
        <li>Deploys: {data.deploy.success} success, {data.deploy.failure} failure</li>
        <li>Open autotriage issues: {data.open_autotriage_issues}</li>
      </ul>
    </section>
  );
}
```

- [ ] **Step 3: Embed in App.tsx**

Replace `apps/web/src/App.tsx` entirely:

```tsx
import { Dashboard } from "./Dashboard";

export function App() {
  return (
    <main>
      <h1>ai-harness</h1>
      <p>Phase 1 (foundation) shipped 2026-04-14.</p>
      <Dashboard />
    </main>
  );
}
```

- [ ] **Step 4: Test + commit**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
pnpm --filter web test
pnpm --filter web typecheck
git add apps/web/src/Dashboard.tsx apps/web/src/Dashboard.test.tsx apps/web/src/App.tsx
git commit -m "feat(web): add Dashboard showing harness status"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

Expected: 4 passed (1 existing App + 3 new Dashboard).

---

## Phase 9 exit checklist

- [ ] `uv run pytest apps/api agents` passes (107 → 110 with 3 status tests)
- [ ] `pnpm --filter web test` passes (1 → 4 with 3 dashboard tests)
- [ ] `GET /api/status` returns JSON with `ci`, `deploy`, `open_autotriage_issues`
- [ ] Dashboard renders on `/`, fetches and displays status
- [ ] CI green
- [ ] Railway redeploy shows the new dashboard

## Out of scope

- Auth on /api/status (open endpoint — fine for solo lab demo)
- WebSocket live updates
- Per-agent cost dashboard (Phase 12)
- Charts / graphs (text only for MVP)
