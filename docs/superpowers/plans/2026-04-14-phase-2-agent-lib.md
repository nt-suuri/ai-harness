# ai-harness — Phase 2: Agent Shared Lib Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `agents/` as a uv workspace member containing `agents/lib/` — five focused modules (anthropic, gh, sentry, kill_switch, prompts) plus version-controlled prompt stubs and a knowledge yaml — all unit-tested with mocked external clients. Every future agent (reviewer, planner, triager, healthcheck, deployer) will import from `agents.lib`.

**Architecture:** One Python package, src-layout, uv workspace member. Each lib module is tiny (≤100 lines), has one clear responsibility, imports only what it needs, and can be tested in isolation against mocked external clients. No agent logic lives here — only the infrastructure agents stand on.

**Tech Stack:** Python 3.12 + uv + pytest + PyGithub + httpx + claude-agent-sdk + PyYAML. Reuses existing ruff/mypy config from the root pyproject.

**Working directory for every command:** `/Users/nt-suuri/workspace/lab/ai-harness` unless stated otherwise.

**Prior state (verified Phase 1 exit):**
- Monorepo live at `https://ai-harness-production.up.railway.app`
- Root pyproject has `[tool.uv.workspace] members = ["apps/api"]` and `[dependency-groups] dev = [pytest, pytest-asyncio, httpx, ruff, mypy]`
- `[tool.ruff.lint.isort] known-first-party = ["api"]`
- CI `ci.yml` runs python/web/e2e/docker on every PR; deploy.yml fires on push to main via Railway
- `docs/`, `CLAUDE.md`, `Dockerfile`, `railway.json`, `scripts/set-railway-token.sh` all committed
- `apps/api/src/api/main.py` serves `/api/ping` + static web; `/` mounts `StaticFiles` if `api/static/` exists

---

## File Structure

```
agents/
├── pyproject.toml                      workspace member, declares deps
├── src/
│   └── agents/
│       ├── __init__.py                 empty
│       └── lib/
│           ├── __init__.py             empty (re-exports are explicit per-use)
│           ├── kill_switch.py          PAUSE_AGENTS env → bool + exit helper
│           ├── prompts.py              load + list named .md prompts
│           ├── prompts/
│           │   ├── planner.md          stub (Phase 4 fills it)
│           │   ├── reviewer_quality.md stub (Phase 3)
│           │   ├── reviewer_security.md stub (Phase 3)
│           │   ├── reviewer_deps.md    stub (Phase 3)
│           │   ├── triager.md          stub (Phase 6)
│           │   └── healthcheck.md      stub (Phase 7)
│           ├── gh.py                   PyGithub client + repo helpers
│           ├── sentry.py               Sentry REST client (list_events, counts_by_fingerprint)
│           └── anthropic.py            claude-agent-sdk wrapper with turn/token caps
├── knowledge/
│   └── known_false_positives.yaml      durable triager knowledge (empty list initially)
└── tests/
    ├── __init__.py
    ├── test_kill_switch.py
    ├── test_prompts.py
    ├── test_gh.py
    ├── test_sentry.py
    ├── test_anthropic.py
    └── test_knowledge.py
```

Every file is created by a task below. Nothing silently assumed.

---

## Conventions (apply to every task)

- **Commit cadence:** every task ends with a commit + push. Messages: `feat(agents): ...`, `test(agents): ...`, `chore(agents): ...`. Push via:
  ```bash
  TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
  ```
  (SSH key on the Mac is for a different GitHub account; HTTPS + gh token works.)

  The lab permits direct-to-main pushes. Future phases will introduce PR-based flow, but Phase 2 bootstrap stays on main for velocity.

- **Run all commands from repo root.** Always `uv run <tool>` (never bare), `uv run pytest`, `uv run mypy`, etc.

- **Test discipline:** every module gets a TDD red → green. Mock external clients (PyGithub, httpx, claude-agent-sdk); do NOT make real HTTP calls in unit tests.

- **Module size target:** ≤100 lines per lib module. If a module grows, stop and escalate.

---

### Task 1: Scaffold the `agents/` package + add to workspace

**Files:**
- Create: `agents/pyproject.toml`
- Create: `agents/src/agents/__init__.py` (empty)
- Create: `agents/src/agents/lib/__init__.py` (empty)
- Create: `agents/tests/__init__.py` (empty)
- Modify: `pyproject.toml` (add `agents` to workspace members)
- Modify: `pyproject.toml` (add `agents` to `known-first-party`)
- Modify: `pyproject.toml` (add `agents/tests` to pytest testpaths; add `agents/src` to pythonpath)

- [ ] **Step 1: Create `agents/pyproject.toml`**

```toml
[project]
name = "agents"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = [
    "claude-agent-sdk>=0.1",
    "PyGithub>=2.4",
    "httpx>=0.27",
    "PyYAML>=6.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agents"]
```

- [ ] **Step 2: Create package + test skeleton files**

```bash
mkdir -p agents/src/agents/lib/prompts agents/tests agents/knowledge
: > agents/src/agents/__init__.py
: > agents/src/agents/lib/__init__.py
: > agents/tests/__init__.py
```

- [ ] **Step 3: Update root `pyproject.toml`**

Open `/Users/nt-suuri/workspace/lab/ai-harness/pyproject.toml` and make three edits:

**3a.** Add `agents` to workspace members:
```toml
[tool.uv.workspace]
members = ["apps/api", "agents"]
```

**3b.** Add `agents` to `known-first-party`:
```toml
[tool.ruff.lint.isort]
known-first-party = ["api", "agents"]
```

**3c.** Add agents tests to pytest:
```toml
[tool.pytest.ini_options]
testpaths = ["apps/api/tests", "agents/tests"]
pythonpath = ["apps/api/src", "agents/src"]
```

Preserve all other blocks verbatim.

- [ ] **Step 4: Resolve the workspace**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv lock
uv sync --group dev --all-packages
```

Expected: `Resolved N packages` with no errors. Lockfile regenerated.

- [ ] **Step 5: Verify package is importable from root venv**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run python -c "import agents.lib; print('ok')"
```

Expected: `ok`. Fails if workspace/pythonpath isn't set correctly.

- [ ] **Step 6: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/ pyproject.toml uv.lock
git commit -m "chore(agents): scaffold agents workspace member"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 2: `kill_switch.py` (simplest module first)

**Files:**
- Create: `agents/src/agents/lib/kill_switch.py`
- Create: `agents/tests/test_kill_switch.py`

- [ ] **Step 1: Write the failing tests**

Create `agents/tests/test_kill_switch.py`:
```python
import os
from unittest.mock import patch

import pytest

from agents.lib.kill_switch import agents_paused, exit_if_paused


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("TRUE", True),
        ("  true  ", True),
        ("True", True),
        ("false", False),
        ("", False),
        ("1", False),
        ("yes", False),
    ],
)
def test_agents_paused_env_var(value: str, expected: bool) -> None:
    with patch.dict(os.environ, {"PAUSE_AGENTS": value}, clear=True):
        assert agents_paused() is expected


def test_agents_paused_unset_env_var() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert agents_paused() is False


def test_exit_if_paused_noop_when_unpaused() -> None:
    with patch.dict(os.environ, {}, clear=True):
        exit_if_paused()  # should not raise


def test_exit_if_paused_raises_system_exit_0_when_paused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.dict(os.environ, {"PAUSE_AGENTS": "true"}, clear=True):
        with pytest.raises(SystemExit) as excinfo:
            exit_if_paused()
        assert excinfo.value.code == 0
        captured = capsys.readouterr()
        assert "PAUSE_AGENTS" in captured.out
```

- [ ] **Step 2: Run the test — expect FAIL (module missing)**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_kill_switch.py -v
```
Expected: `ModuleNotFoundError: No module named 'agents.lib.kill_switch'`.

- [ ] **Step 3: Implement `kill_switch.py`**

Create `agents/src/agents/lib/kill_switch.py`:
```python
"""Repo-wide kill-switch. Every agent workflow calls `exit_if_paused()` early."""

import os
import sys


def agents_paused() -> bool:
    return os.environ.get("PAUSE_AGENTS", "").strip().lower() == "true"


def exit_if_paused() -> None:
    if agents_paused():
        print("PAUSE_AGENTS=true — exiting", flush=True)
        sys.exit(0)
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_kill_switch.py -v
```
Expected: 11 passed (8 parametrize + 1 unset + 2 exit-helper).

- [ ] **Step 5: Lint + typecheck**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run ruff check agents
uv run mypy agents/src
```
Both exit 0.

- [ ] **Step 6: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/lib/kill_switch.py agents/tests/test_kill_switch.py
git commit -m "feat(agents): add kill_switch.py (PAUSE_AGENTS gate)"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 3: `prompts.py` + six stub prompt files

**Files:**
- Create: `agents/src/agents/lib/prompts.py`
- Create: `agents/src/agents/lib/prompts/planner.md`
- Create: `agents/src/agents/lib/prompts/reviewer_quality.md`
- Create: `agents/src/agents/lib/prompts/reviewer_security.md`
- Create: `agents/src/agents/lib/prompts/reviewer_deps.md`
- Create: `agents/src/agents/lib/prompts/triager.md`
- Create: `agents/src/agents/lib/prompts/healthcheck.md`
- Create: `agents/tests/test_prompts.py`

- [ ] **Step 1: Write the failing tests**

Create `agents/tests/test_prompts.py`:
```python
import pytest

from agents.lib import prompts


def test_list_prompts_returns_sorted_known_names() -> None:
    names = prompts.list_prompts()
    assert names == sorted(names)
    assert "planner" in names
    assert "reviewer_quality" in names
    assert "reviewer_security" in names
    assert "reviewer_deps" in names
    assert "triager" in names
    assert "healthcheck" in names


def test_load_returns_nonempty_string() -> None:
    body = prompts.load("planner")
    assert isinstance(body, str)
    assert len(body) > 0


def test_load_unknown_prompt_raises_filenotfound() -> None:
    with pytest.raises(FileNotFoundError):
        prompts.load("does_not_exist")
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_prompts.py -v
```
Expected: ImportError or ModuleNotFoundError.

- [ ] **Step 3: Implement `prompts.py`**

Create `agents/src/agents/lib/prompts.py`:
```python
"""Load agent system prompts from sibling .md files."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load(name: str) -> str:
    return (_PROMPTS_DIR / f"{name}.md").read_text()


def list_prompts() -> list[str]:
    return sorted(p.stem for p in _PROMPTS_DIR.glob("*.md"))
```

- [ ] **Step 4: Create the six stub prompts**

All prompts start minimal — Phase 3/4/6/7 will fill them out. Each file's exact content is shown below.

`agents/src/agents/lib/prompts/planner.md`:
```
# Planner agent

Role: given a GitHub issue, decompose it into an implementation plan, write the code, write tests, and open a PR.

Scope (Phase 4 will expand this): placeholder. Do not invoke this agent yet.
```

`agents/src/agents/lib/prompts/reviewer_quality.md`:
```
# PR quality reviewer

Role: review a PR diff for logic errors, performance issues, maintainability, naming, and code smell.

Scope (Phase 3 will expand this): placeholder.
```

`agents/src/agents/lib/prompts/reviewer_security.md`:
```
# PR security reviewer

Role: review a PR diff for injection risks, authentication boundaries, secret handling, and OWASP top-10 patterns.

Scope (Phase 3 will expand this): placeholder.
```

`agents/src/agents/lib/prompts/reviewer_deps.md`:
```
# PR dependency reviewer

Role: review added/updated dependencies for supply-chain risk, license issues, and known CVEs.

Scope (Phase 3 will expand this): placeholder.
```

`agents/src/agents/lib/prompts/triager.md`:
```
# Triager agent

Role: every 24h, cluster recent Sentry events, score severity, and open/update GitHub issues. Dedupe against open issues. Reopen closed issues when regressions recur.

Scope (Phase 6 will expand this): placeholder.
```

`agents/src/agents/lib/prompts/healthcheck.md`:
```
# Healthcheck agent

Role: every morning, summarize yesterday's deploys, error counts, test-run green rate. Update the pinned HEALTH issue and send email digest via Resend.

Scope (Phase 7 will expand this): placeholder.
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_prompts.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Lint + typecheck**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run ruff check agents
uv run mypy agents/src
```

- [ ] **Step 7: Update `agents/pyproject.toml` to include .md files in the wheel**

Hatchling by default only includes .py files in packages. Since tests dynamically load .md sibling files via `__file__`, a wheel build would omit them. Fix now (future-proofing — not needed for dev since we import from source, but needed if we ever build a wheel).

Edit `agents/pyproject.toml`. Change the build target block from:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/agents"]
```

to:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/agents"]

[tool.hatch.build.targets.wheel.force-include]
"src/agents/lib/prompts" = "agents/lib/prompts"
```

- [ ] **Step 8: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/lib/prompts.py \
        agents/src/agents/lib/prompts/ \
        agents/tests/test_prompts.py \
        agents/pyproject.toml
git commit -m "feat(agents): add prompts loader + six stub prompt files"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 4: `knowledge/known_false_positives.yaml` + tiny schema test

**Files:**
- Create: `agents/knowledge/known_false_positives.yaml`
- Create: `agents/tests/test_knowledge.py`

- [ ] **Step 1: Write the failing test**

Create `agents/tests/test_knowledge.py`:
```python
from pathlib import Path

import yaml

_KNOWLEDGE = Path(__file__).resolve().parents[1] / "knowledge" / "known_false_positives.yaml"


def test_knowledge_file_exists() -> None:
    assert _KNOWLEDGE.is_file()


def test_knowledge_file_is_valid_yaml() -> None:
    data = yaml.safe_load(_KNOWLEDGE.read_text())
    assert isinstance(data, dict)


def test_knowledge_has_expected_top_level_key() -> None:
    data = yaml.safe_load(_KNOWLEDGE.read_text())
    assert "false_positives" in data
    assert isinstance(data["false_positives"], list)


def test_each_entry_has_required_fields() -> None:
    data = yaml.safe_load(_KNOWLEDGE.read_text())
    required = {"fingerprint", "reason", "added", "added_by"}
    for entry in data["false_positives"]:
        assert required.issubset(entry.keys()), f"missing keys in {entry}"
```

- [ ] **Step 2: Run — expect FAIL (file missing)**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_knowledge.py -v
```
Expected: `assert False` on `test_knowledge_file_exists`.

- [ ] **Step 3: Create the yaml file**

Create `agents/knowledge/known_false_positives.yaml`:
```yaml
# Durable agent knowledge: triager-confirmed false-positive error fingerprints.
#
# Entries are added by humans OR by the triager agent via PR.
# Each entry:
#   - fingerprint:  Sentry issue fingerprint or a regex pattern matching it
#   - reason:       one-line human explanation for later auditors
#   - added:        YYYY-MM-DD
#   - added_by:     "human" or "triager-<run-id>"

false_positives: []
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_knowledge.py -v
```
Expected: 4 passed (the "each entry" test trivially passes on empty list).

- [ ] **Step 5: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/knowledge/known_false_positives.yaml agents/tests/test_knowledge.py
git commit -m "feat(agents): seed knowledge/known_false_positives.yaml"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 5: `gh.py` (PyGithub wrapper)

**Files:**
- Create: `agents/src/agents/lib/gh.py`
- Create: `agents/tests/test_gh.py`

- [ ] **Step 1: Write the failing tests**

Create `agents/tests/test_gh.py`:
```python
import os
from unittest.mock import MagicMock, patch

import pytest

from agents.lib import gh


def test_client_requires_github_token() -> None:
    gh._client.cache_clear()
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(KeyError):
            gh._client()


def test_client_caches_instance() -> None:
    gh._client.cache_clear()
    with patch.dict(os.environ, {"GITHUB_TOKEN": "t1"}, clear=True):
        with patch("agents.lib.gh.Github") as gh_cls:
            gh_cls.return_value = MagicMock(name="gh_instance")
            a = gh._client()
            b = gh._client()
            assert a is b
            gh_cls.assert_called_once_with("t1")


def test_repo_uses_env_default() -> None:
    gh._client.cache_clear()
    with patch.dict(
        os.environ,
        {"GITHUB_TOKEN": "t", "GH_REPO": "acme/proj"},
        clear=True,
    ):
        with patch("agents.lib.gh.Github") as gh_cls:
            client = MagicMock()
            gh_cls.return_value = client
            gh.repo()
            client.get_repo.assert_called_once_with("acme/proj")


def test_repo_explicit_fullname_overrides_env() -> None:
    gh._client.cache_clear()
    with patch.dict(
        os.environ,
        {"GITHUB_TOKEN": "t", "GH_REPO": "acme/proj"},
        clear=True,
    ):
        with patch("agents.lib.gh.Github") as gh_cls:
            client = MagicMock()
            gh_cls.return_value = client
            gh.repo("other/thing")
            client.get_repo.assert_called_once_with("other/thing")


def test_repo_default_falls_back_to_nt_suuri_ai_harness() -> None:
    gh._client.cache_clear()
    with patch.dict(os.environ, {"GITHUB_TOKEN": "t"}, clear=True):
        with patch("agents.lib.gh.Github") as gh_cls:
            client = MagicMock()
            gh_cls.return_value = client
            gh.repo()
            client.get_repo.assert_called_once_with("nt-suuri/ai-harness")
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_gh.py -v
```
Expected: ImportError / module missing.

- [ ] **Step 3: Implement `gh.py`**

Create `agents/src/agents/lib/gh.py`:
```python
"""PyGithub client + repo-scoped helpers used by every agent."""

import os
from functools import cache

from github import Github
from github.Repository import Repository

_DEFAULT_REPO = "nt-suuri/ai-harness"


@cache
def _client() -> Github:
    token = os.environ["GITHUB_TOKEN"]
    return Github(token)


def repo(fullname: str | None = None) -> Repository:
    name = fullname or os.environ.get("GH_REPO", _DEFAULT_REPO)
    return _client().get_repo(name)
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_gh.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Lint + typecheck**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run ruff check agents
uv run mypy agents/src
```

If mypy complains about `github` types not existing, `ignore_missing_imports = true` is already set in root pyproject — it should pass. If not, investigate before adding workarounds.

- [ ] **Step 6: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/lib/gh.py agents/tests/test_gh.py
git commit -m "feat(agents): add gh.py (cached PyGithub client + repo helper)"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 6: `sentry.py` (REST client)

**Files:**
- Create: `agents/src/agents/lib/sentry.py`
- Create: `agents/tests/test_sentry.py`

- [ ] **Step 1: Write the failing tests**

Create `agents/tests/test_sentry.py`:
```python
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from agents.lib import sentry


def test_client_requires_sentry_auth_token() -> None:
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(KeyError):
            sentry._client()


def test_client_sets_bearer_header() -> None:
    with patch.dict(os.environ, {"SENTRY_AUTH_TOKEN": "abc"}, clear=True):
        with patch("agents.lib.sentry.httpx.Client") as client_cls:
            sentry._client()
            call_kwargs = client_cls.call_args.kwargs
            assert call_kwargs["headers"]["Authorization"] == "Bearer abc"
            assert call_kwargs["base_url"] == "https://sentry.io/api/0"
            assert call_kwargs["timeout"] == 30


def test_list_events_default_since_is_24h_ago() -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    fake_client.get.return_value = MagicMock(
        status_code=200,
        json=MagicMock(return_value=[{"id": "e1"}]),
    )

    with patch("agents.lib.sentry._client", return_value=fake_client):
        events = sentry.list_events("myorg", "myproj")

    assert events == [{"id": "e1"}]
    fake_client.get.assert_called_once()
    call = fake_client.get.call_args
    assert call.args[0] == "/projects/myorg/myproj/events/"
    since = call.kwargs["params"]["since"]
    # parseable ISO-8601
    since_dt = datetime.fromisoformat(since)
    now = datetime.now(UTC)
    # should be within 24h + a few seconds of slack
    assert timedelta(hours=23, minutes=59) <= now - since_dt <= timedelta(hours=24, minutes=1)


def test_list_events_custom_since() -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    fake_client.get.return_value = MagicMock(
        status_code=200,
        json=MagicMock(return_value=[]),
    )
    pinned = datetime(2026, 1, 1, tzinfo=UTC)

    with patch("agents.lib.sentry._client", return_value=fake_client):
        sentry.list_events("org", "proj", since=pinned)

    assert fake_client.get.call_args.kwargs["params"]["since"] == pinned.isoformat()


def test_list_events_raises_for_status() -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    resp = MagicMock()
    resp.raise_for_status.side_effect = Exception("401 unauthorized")
    fake_client.get.return_value = resp

    with patch("agents.lib.sentry._client", return_value=fake_client):
        with pytest.raises(Exception, match="401"):
            sentry.list_events("o", "p")
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_sentry.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `sentry.py`**

Create `agents/src/agents/lib/sentry.py`:
```python
"""Minimal Sentry REST API client — list_events, counts_by_fingerprint."""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

_BASE_URL = "https://sentry.io/api/0"


def _client() -> httpx.Client:
    token = os.environ["SENTRY_AUTH_TOKEN"]
    return httpx.Client(
        base_url=_BASE_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )


def list_events(
    organization_slug: str,
    project_slug: str,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    if since is None:
        since = datetime.now(UTC) - timedelta(hours=24)
    with _client() as c:
        resp = c.get(
            f"/projects/{organization_slug}/{project_slug}/events/",
            params={"since": since.isoformat()},
        )
        resp.raise_for_status()
        return resp.json()
```

Note: `counts_by_fingerprint` is NOT in this task. It's a Phase 6 addition (triager). This task only ships `list_events` plus the shared `_client`.

- [ ] **Step 4: Run — expect PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_sentry.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Lint + typecheck**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run ruff check agents
uv run mypy agents/src
```

- [ ] **Step 6: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/lib/sentry.py agents/tests/test_sentry.py
git commit -m "feat(agents): add sentry.py (REST client with list_events)"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 7: `anthropic.py` (claude-agent-sdk wrapper)

**Files:**
- Create: `agents/src/agents/lib/anthropic.py`
- Create: `agents/tests/test_anthropic.py`

**Pre-reading:** the `claude-agent-sdk` package exposes an async `query` function that yields message objects. Before coding, use Context7 (or `uv run python -c "import claude_agent_sdk; help(claude_agent_sdk)"`) to confirm the exact import path and options class name for the version that `uv lock` resolved. If names differ from what this task specifies, ADAPT the implementation but keep the tested PUBLIC API unchanged.

The PUBLIC API this module must expose:
```python
async def run_agent(
    prompt: str,
    *,
    system: str,
    max_turns: int = 20,
    allowed_tools: list[str] | None = None,
) -> AgentResult: ...
```

and
```python
@dataclass(frozen=True)
class AgentResult:
    messages: list[object]
    stopped_reason: str  # "complete" | "turn_cap"
```

- [ ] **Step 1: Write the failing tests**

Create `agents/tests/test_anthropic.py`:
```python
from unittest.mock import AsyncMock, patch

import pytest

from agents.lib.anthropic import AgentResult, run_agent


def _async_iter(items: list[object]):
    async def _gen():
        for item in items:
            yield item

    return _gen()


@pytest.mark.asyncio
async def test_run_agent_returns_messages_and_complete_reason() -> None:
    fake_messages = [{"role": "assistant", "text": "hi"}, {"role": "assistant", "text": "bye"}]
    with patch("agents.lib.anthropic._sdk_query") as m:
        m.return_value = _async_iter(fake_messages)
        result = await run_agent("do the thing", system="you are helpful")
    assert isinstance(result, AgentResult)
    assert result.messages == fake_messages
    assert result.stopped_reason == "complete"


@pytest.mark.asyncio
async def test_run_agent_passes_max_turns_and_allowed_tools_to_sdk() -> None:
    with patch("agents.lib.anthropic._sdk_query") as m:
        m.return_value = _async_iter([])
        await run_agent(
            "p",
            system="s",
            max_turns=5,
            allowed_tools=["Read", "Grep"],
        )
    call_kwargs = m.call_args.kwargs
    options = call_kwargs["options"]
    # the options object comes from the SDK; we at least verify the attrs we pass
    assert getattr(options, "max_turns", None) == 5
    assert getattr(options, "allowed_tools", None) == ["Read", "Grep"]
    assert getattr(options, "system_prompt", None) == "s"


@pytest.mark.asyncio
async def test_run_agent_empty_allowed_tools_default() -> None:
    with patch("agents.lib.anthropic._sdk_query") as m:
        m.return_value = _async_iter([])
        await run_agent("p", system="s")
    options = m.call_args.kwargs["options"]
    assert getattr(options, "allowed_tools", None) == []
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_anthropic.py -v
```
Expected: ImportError.

- [ ] **Step 3: Verify SDK API shape**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run python -c "import claude_agent_sdk; print(dir(claude_agent_sdk))"
```

You should see `query` and an options dataclass. Typical names: `ClaudeAgentOptions`, `AgentOptions`, or similar. Capture the actual names before writing the implementation.

- [ ] **Step 4: Implement `anthropic.py`**

Create `agents/src/agents/lib/anthropic.py`:

```python
"""Wrapper around claude-agent-sdk with turn cap + structured result."""

from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk import query as _sdk_query


@dataclass(frozen=True)
class AgentResult:
    messages: list[Any]
    stopped_reason: str  # "complete" | "turn_cap"


async def run_agent(
    prompt: str,
    *,
    system: str,
    max_turns: int = 20,
    allowed_tools: list[str] | None = None,
) -> AgentResult:
    options = ClaudeAgentOptions(
        system_prompt=system,
        max_turns=max_turns,
        allowed_tools=list(allowed_tools) if allowed_tools else [],
    )
    messages: list[Any] = []
    async for message in _sdk_query(prompt=prompt, options=options):
        messages.append(message)
    return AgentResult(messages=messages, stopped_reason="complete")
```

**If the SDK's actual import names differ** (e.g., options class is `AgentOptions` not `ClaudeAgentOptions`), adapt the import line and class-construction line. Keep the exported `AgentResult` and `run_agent` signatures EXACTLY as shown — tests depend on them.

- [ ] **Step 5: Run — expect PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_anthropic.py -v
```

If tests fail because `_sdk_query` isn't the function name anymore, update the wrapper's `from ... import query as _sdk_query` line to the current alias. The tests patch `agents.lib.anthropic._sdk_query` — that name must exist as a module attribute.

Expected: 3 passed.

- [ ] **Step 6: Lint + typecheck**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run ruff check agents
uv run mypy agents/src
```

- [ ] **Step 7: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/lib/anthropic.py agents/tests/test_anthropic.py
git commit -m "feat(agents): add anthropic.py (claude-agent-sdk wrapper)"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 8: Update CI to test `agents/`

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Edit the `python` job to also pytest agents**

Open `/Users/nt-suuri/workspace/lab/ai-harness/.github/workflows/ci.yml`. Find the `python` job:

```yaml
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --group dev --all-packages --frozen
      - run: uv run ruff check .
      - run: uv run mypy apps/api/src
      - run: uv run pytest apps/api -v
```

Change the final two steps to:

```yaml
      - run: uv run mypy apps/api/src agents/src
      - run: uv run pytest apps/api agents -v
```

Every other job (web, e2e, docker) stays unchanged.

- [ ] **Step 2: Run both paths locally to confirm**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run mypy apps/api/src agents/src
uv run pytest apps/api agents -v
```

Expected: mypy `Success: no issues found`; pytest shows 3 api tests + all agents tests passing (kill_switch ~11, prompts 3, gh 5, sentry 5, anthropic 3, knowledge 4 ≈ 31 from agents).

- [ ] **Step 3: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add .github/workflows/ci.yml
git commit -m "ci: include agents/ in mypy + pytest steps"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

- [ ] **Step 4: Watch CI go green**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
sleep 10
gh run list --workflow=ci.yml --limit 1
```

Poll until `completed / success`. If CI fails, fetch logs:
```bash
gh run view <RUN_ID> --log-failed | head -80
```

Fix forward. Do not proceed until CI is green.

---

### Task 9: End-to-end smoke + Phase 2 exit verification

- [ ] **Step 1: Import check from root venv**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run python -c "
from agents.lib.anthropic import run_agent
from agents.lib.gh import repo
from agents.lib.sentry import list_events
from agents.lib.kill_switch import agents_paused, exit_if_paused
from agents.lib import prompts
print('imports ok')
print('prompts:', prompts.list_prompts())
"
```

Expected: `imports ok` followed by the sorted prompt names:
```
imports ok
prompts: ['healthcheck', 'planner', 'reviewer_deps', 'reviewer_quality', 'reviewer_security', 'triager']
```

- [ ] **Step 2: Full test suite**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest apps/api agents -v
uv run mypy apps/api/src agents/src
uv run ruff check .
```

All green, zero errors.

- [ ] **Step 3: Confirm nothing in apps/ broke**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
pnpm --filter web test
pnpm --filter web typecheck
```

Also confirm Railway is still serving:
```bash
curl -sS -m 10 https://ai-harness-production.up.railway.app/api/ping
```
Expected: `{"status":"pong"}`.

- [ ] **Step 4: Confirm git state is clean**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git status --porcelain
git log --oneline -n 12
```

Expected: working tree empty (or only known untracked). 8 new commits from Phase 2 atop Phase 1's history.

No commit for this task — it's pure verification.

---

## Phase 2 exit checklist

- [ ] `uv run pytest apps/api agents` passes (all tests)
- [ ] `uv run mypy apps/api/src agents/src` exits 0
- [ ] `uv run ruff check .` passes
- [ ] `uv run python -c "from agents.lib.anthropic import run_agent; ..."` imports cleanly
- [ ] All six prompt stubs exist (planner, reviewer_quality, reviewer_security, reviewer_deps, triager, healthcheck)
- [ ] `agents/knowledge/known_false_positives.yaml` valid YAML, schema-compliant empty list
- [ ] CI (ci.yml) green on main — now running agents tests too
- [ ] Railway is still serving `/api/ping` → `pong`
- [ ] 8 new commits pushed to origin/main

## What this phase does NOT build (deferred)

| Feature | Phase |
|---|---|
| Reviewer agent (3 parallel passes) | 3 |
| Planner agent (`agent:build` label → PR) | 4 |
| Deployer + rollback watcher | 5 |
| Triager + self-healing loop | 6 |
| Healthcheck + email digest + canary replay | 7 |

Each gets its own plan file.

## Self-review notes

- Module sizes target ≤100 lines; `anthropic.py`, `gh.py`, `sentry.py`, `kill_switch.py` all land well under.
- `prompts.py` is a pure file loader — zero coupling to other lib modules; its tests don't need mocks.
- `_client()` in both `gh.py` and `sentry.py` reads the auth token lazily at call time — no import-time side effects. Test hermeticity preserved.
- Test counts to expect when running `uv run pytest agents`: 11 (kill_switch) + 3 (prompts) + 4 (knowledge) + 5 (gh) + 5 (sentry) + 3 (anthropic) = 31.
- Task 7 (anthropic) has a built-in escape hatch: if the SDK's import names differ from what this plan assumes, the implementer adapts the imports but keeps the public API (`run_agent`, `AgentResult`) stable — tests will still pass.
- Root `uv.lock` is regenerated in Task 1 when `uv lock` is run after adding the new workspace member. Each Task N commit stages `uv.lock` only if a step in that task changed it (Task 1 only, mostly).
