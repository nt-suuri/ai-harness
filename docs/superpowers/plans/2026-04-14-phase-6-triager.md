# ai-harness — Phase 6: Self-Healing Triager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every night at 09:00 UTC, the triager pulls the last 24h of Sentry-grouped issues, dedupes against existing GitHub issues (by Sentry issue ID embedded in the body), and opens new bug issues with labels `bug`, `autotriage`. This closes the self-healing loop: error in prod → issue → human or planner picks it up → fix PR → reviewer + CI gate → merge → deployer watcher confirms resolution next night.

**Architecture:** `agents/src/agents/triager.py` is a CLI (`--since-hours 24`, `--dry-run`). Uses `agents.lib.sentry` to fetch issue list, `agents.lib.gh` to search/create GH issues. Embeds `sentry-issue-id: <id>` in issue body for deduplication. `.github/workflows/triager.yml` runs on cron schedule.

**Tech Stack:** Python 3.12, `agents.lib.*`, GitHub Actions cron.

**Working directory:** `/Users/nt-suuri/workspace/lab/ai-harness`.

**Prior state (Phase 5 complete at `a734fd0`):**
- 70 tests green
- `rollback-watch.yml` armed and verified to fire correctly
- `agents.lib.sentry` exposes `_client()`, `list_events()`, `count_events_since()`

**Out of scope (deferred to Phase 6.5):** LLM-based severity scoring, regression detection (reopen closed issues), known_false_positives.yaml filtering, fingerprint-regex dedup beyond Sentry issue ID. MVP keeps it simple: one Sentry issue → one GH issue, never more.

---

## File Structure

```
agents/src/agents/lib/
└── sentry.py                           EXTEND — add list_issues()

agents/src/agents/
└── triager.py                          NEW — CLI + triage_run()

agents/tests/
├── test_sentry_client.py               EXTEND — add 2 list_issues tests
└── test_triager.py                     NEW

.github/workflows/
└── triager.yml                         NEW — cron 09:00 UTC

CLAUDE.md                               UPDATE — document triager flow
```

---

## Conventions

- All commands from repo root.
- Direct commits/pushes to main permitted.
- Push: `TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main`
- SIM117 active; no `ruff --fix`.

---

### Task 1: Extend `sentry.py` with `list_issues()`

**Files:**
- Modify: `agents/src/agents/lib/sentry.py`
- Modify: `agents/tests/test_sentry_client.py`

Sentry's `/api/0/projects/{org}/{proj}/issues/` endpoint returns grouped issues (one per fingerprint), each with `id`, `title`, `culprit`, `count`, `firstSeen`, `lastSeen`, `permalink`, `level`. We need a function that returns this list, filtered by `since`.

- [ ] **Step 1: Append failing tests**

Append to `agents/tests/test_sentry_client.py`:

```python
def test_list_issues_returns_list() -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    fake_client.get.return_value = MagicMock(
        status_code=200,
        json=MagicMock(return_value=[
            {"id": "1234", "title": "ZeroDivisionError", "count": "5"},
            {"id": "5678", "title": "KeyError: 'x'", "count": "1"},
        ]),
    )

    pinned = datetime(2026, 4, 14, tzinfo=UTC)
    with patch("agents.lib.sentry._client", return_value=fake_client):
        issues = sentry.list_issues("org", "proj", since=pinned)

    assert len(issues) == 2
    assert issues[0]["id"] == "1234"
    fake_client.get.assert_called_once()
    call = fake_client.get.call_args
    assert call.args[0] == "/projects/org/proj/issues/"
    assert call.kwargs["params"]["since"] == pinned.isoformat()


def test_list_issues_default_since_is_24h_ago() -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    fake_client.get.return_value = MagicMock(status_code=200, json=MagicMock(return_value=[]))

    with patch("agents.lib.sentry._client", return_value=fake_client):
        sentry.list_issues("o", "p")

    since_str = fake_client.get.call_args.kwargs["params"]["since"]
    since_dt = datetime.fromisoformat(since_str)
    delta = datetime.now(UTC) - since_dt
    assert timedelta(hours=23, minutes=59) <= delta <= timedelta(hours=24, minutes=1)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_sentry_client.py::test_list_issues_returns_list -v
```

- [ ] **Step 3: Implement `list_issues`**

Edit `agents/src/agents/lib/sentry.py`. After `count_events_since`, append:

```python
def list_issues(
    organization_slug: str,
    project_slug: str,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return Sentry's grouped issues since `since` (default 24h ago)."""
    if since is None:
        since = datetime.now(UTC) - timedelta(hours=24)
    with _client() as c:
        resp = c.get(
            f"/projects/{organization_slug}/{project_slug}/issues/",
            params={"since": since.isoformat()},
        )
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 4: Run — expect 9 PASS in sentry tests**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_sentry_client.py -v
```
Expected: 9 passed (7 prior + 2 new).

- [ ] **Step 5: Lint + typecheck**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run ruff check agents
uv run mypy agents/src
```

- [ ] **Step 6: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/lib/sentry.py agents/tests/test_sentry_client.py
git commit -m "feat(agents): sentry.list_issues helper"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 2: `triager.py` skeleton + CLI + failing tests

**Files:**
- Create: `agents/src/agents/triager.py`
- Create: `agents/tests/test_triager.py`

- [ ] **Step 1: Write failing tests**

Create `agents/tests/test_triager.py`:

```python
import subprocess

import pytest


def test_triager_cli_accepts_no_args_with_help_check() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.triager", "--help-check-only"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_triager_cli_accepts_since_hours() -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.triager",
            "--since-hours", "48", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


@pytest.mark.parametrize("hours", ["1", "24", "168"])
def test_triager_cli_accepts_various_since_values(hours: str) -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.triager",
            "--since-hours", hours, "--dry-run", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_triager.py -v
```

- [ ] **Step 3: Implement skeleton**

Create `agents/src/agents/triager.py`:

```python
"""Nightly triager. Pulls Sentry issues, opens GH issues for new ones.

Usage:
    python -m agents.triager
    python -m agents.triager --since-hours 24 --dry-run
"""

import argparse
import sys

from agents.lib import kill_switch


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.triager", description=__doc__)
    p.add_argument("--since-hours", type=int, default=24, help="Lookback window (default 24)")
    p.add_argument("--dry-run", action="store_true", help="Print what would be opened; skip GH writes")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def triage_run(since_hours: int, *, dry_run: bool) -> int:
    """Return 0 always (cron-friendly). Logs counts to stdout."""
    raise NotImplementedError("Task 3 fills this in")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return triage_run(args.since_hours, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run — expect 5 PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_triager.py -v
```

- [ ] **Step 5: Lint + typecheck**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run ruff check agents
uv run mypy agents/src
```

- [ ] **Step 6: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/triager.py agents/tests/test_triager.py
git commit -m "feat(agents): triager.py CLI skeleton"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 3: Implement `triage_run()` — fetch + dedupe + create

**Files:**
- Modify: `agents/src/agents/triager.py`
- Modify: `agents/tests/test_triager.py`

Logic:
1. If `SENTRY_ORG_SLUG`/`SENTRY_PROJECT_SLUG` unset → exit 0 silently
2. Fetch Sentry issues since `since_hours` ago
3. For each Sentry issue:
   - Generate marker `<sentry-issue-id>{id}</sentry-issue-id>`
   - Search existing GH issues for that marker (use repo.get_issues with state=all + filter by body)
   - If found → skip (dedup)
   - If not found → create GH issue with title, body (containing marker + sentry permalink + culprit + count), labels=[bug, autotriage]
4. Print summary: `triaged: total_sentry=X, new_gh=Y, deduped=Z`

- [ ] **Step 1: Append tests**

Append to `agents/tests/test_triager.py`:

```python
import os
from unittest.mock import MagicMock, patch

from agents.triager import _existing_marker_in_issues, _make_marker, triage_run


def test_make_marker_format() -> None:
    assert _make_marker("1234") == "<sentry-issue-id>1234</sentry-issue-id>"


def test_existing_marker_in_issues_finds_match() -> None:
    issues = [
        MagicMock(body="some text\n<sentry-issue-id>9999</sentry-issue-id>\nmore"),
        MagicMock(body="unrelated"),
    ]
    assert _existing_marker_in_issues(issues, _make_marker("9999")) is True


def test_existing_marker_in_issues_returns_false_when_absent() -> None:
    issues = [MagicMock(body="unrelated"), MagicMock(body="also unrelated")]
    assert _existing_marker_in_issues(issues, _make_marker("404")) is False


def test_existing_marker_in_issues_handles_none_body() -> None:
    issues = [MagicMock(body=None), MagicMock(body="x")]
    assert _existing_marker_in_issues(issues, _make_marker("404")) is False


def test_triage_run_noop_when_sentry_not_configured() -> None:
    with patch.dict(os.environ, {}, clear=True):
        rc = triage_run(24, dry_run=False)
    assert rc == 0


def test_triage_run_creates_new_issues_only() -> None:
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = [
        MagicMock(body="<sentry-issue-id>existing</sentry-issue-id>"),
    ]
    fake_repo.create_issue.return_value = MagicMock(number=99, html_url="https://x")

    fake_sentry_issues = [
        {
            "id": "existing",
            "title": "old known error",
            "culprit": "main.py:10",
            "count": "5",
            "permalink": "https://sentry.io/old",
            "level": "error",
        },
        {
            "id": "newone",
            "title": "ZeroDivisionError",
            "culprit": "math.py:42",
            "count": "1",
            "permalink": "https://sentry.io/new",
            "level": "error",
        },
    ]

    with (
        patch.dict(os.environ, {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p"}, clear=True),
        patch("agents.triager.gh.repo", return_value=fake_repo),
        patch("agents.triager.sentry.list_issues", return_value=fake_sentry_issues),
    ):
        rc = triage_run(24, dry_run=False)

    assert rc == 0
    fake_repo.create_issue.assert_called_once()
    kwargs = fake_repo.create_issue.call_args.kwargs
    assert "ZeroDivisionError" in kwargs["title"]
    assert "<sentry-issue-id>newone</sentry-issue-id>" in kwargs["body"]
    assert "https://sentry.io/new" in kwargs["body"]
    assert "bug" in kwargs["labels"]
    assert "autotriage" in kwargs["labels"]


def test_triage_run_dry_run_skips_create() -> None:
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []
    fake_sentry_issues = [
        {"id": "x", "title": "T", "culprit": "c", "count": "1", "permalink": "u", "level": "error"},
    ]

    with (
        patch.dict(os.environ, {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p"}, clear=True),
        patch("agents.triager.gh.repo", return_value=fake_repo),
        patch("agents.triager.sentry.list_issues", return_value=fake_sentry_issues),
    ):
        rc = triage_run(24, dry_run=True)

    assert rc == 0
    fake_repo.create_issue.assert_not_called()
```

- [ ] **Step 2: Run — expect FAIL on the new tests**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_triager.py -v
```

- [ ] **Step 3: Implement triage_run + helpers**

Replace `agents/src/agents/triager.py` entirely:

```python
"""Nightly triager. Pulls Sentry issues, opens GH issues for new ones.

Usage:
    python -m agents.triager
    python -m agents.triager --since-hours 24 --dry-run
"""

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from agents.lib import gh, kill_switch, sentry


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.triager", description=__doc__)
    p.add_argument("--since-hours", type=int, default=24, help="Lookback window (default 24)")
    p.add_argument("--dry-run", action="store_true", help="Print what would be opened; skip GH writes")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _make_marker(sentry_id: str) -> str:
    return f"<sentry-issue-id>{sentry_id}</sentry-issue-id>"


def _existing_marker_in_issues(issues: list[Any], marker: str) -> bool:
    for issue in issues:
        body = getattr(issue, "body", None) or ""
        if marker in body:
            return True
    return False


def _format_issue_body(s_issue: dict[str, Any], marker: str) -> str:
    return (
        f"{marker}\n\n"
        f"**Sentry permalink:** {s_issue.get('permalink', '(none)')}\n"
        f"**Culprit:** `{s_issue.get('culprit', '(unknown)')}`\n"
        f"**Count (last 24h):** {s_issue.get('count', '?')}\n"
        f"**Level:** {s_issue.get('level', '?')}\n\n"
        "Apply `agent:build` label to have the planner attempt a fix."
    )


def triage_run(since_hours: int, *, dry_run: bool) -> int:
    """Return 0 always. Logs counts."""
    org = os.environ.get("SENTRY_ORG_SLUG", "")
    proj = os.environ.get("SENTRY_PROJECT_SLUG", "")
    if not org or not proj:
        print("SENTRY_ORG_SLUG/SENTRY_PROJECT_SLUG unset — skipping triage", flush=True)
        return 0

    since = datetime.now(UTC) - timedelta(hours=since_hours)
    sentry_issues = sentry.list_issues(org, proj, since=since)

    repo = gh.repo()
    # Pull all autotriage-labelled issues (open + closed) for dedupe
    existing = list(repo.get_issues(state="all", labels=["autotriage"]))

    new_count = 0
    deduped = 0
    for s_issue in sentry_issues:
        sentry_id = str(s_issue.get("id", ""))
        if not sentry_id:
            continue
        marker = _make_marker(sentry_id)
        if _existing_marker_in_issues(existing, marker):
            deduped += 1
            continue

        title = f"[autotriage] {s_issue.get('title', 'Unknown error')}"
        body = _format_issue_body(s_issue, marker)
        if dry_run:
            print(f"DRY RUN — would create: {title}")
            new_count += 1
            continue

        gh_issue = repo.create_issue(title=title, body=body, labels=["bug", "autotriage"])
        print(f"Created issue #{gh_issue.number}: {title}", flush=True)
        new_count += 1

    print(
        f"triaged: total_sentry={len(sentry_issues)} new_gh={new_count} deduped={deduped}",
        flush=True,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return triage_run(args.since_hours, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run — expect 12 PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_triager.py -v
```
Expected: 12 passed (5 CLI + 4 helper + 3 triage_run = 12).

- [ ] **Step 5: Lint + typecheck**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run ruff check agents
uv run mypy agents/src
```

- [ ] **Step 6: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/triager.py agents/tests/test_triager.py
git commit -m "feat(agents): triager.py with Sentry→GH dedupe-by-marker"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 4: `triager.yml` cron workflow

**Files:**
- Create: `.github/workflows/triager.yml`

- [ ] **Step 1: Write the workflow**

Create `/Users/nt-suuri/workspace/lab/ai-harness/.github/workflows/triager.yml`:

```yaml
name: triager

on:
  schedule:
    - cron: "0 9 * * *"
  workflow_dispatch:

permissions:
  contents: read
  issues: write

jobs:
  triage:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    env:
      SENTRY_AUTH_TOKEN: ${{ secrets.SENTRY_AUTH_TOKEN }}
      SENTRY_ORG_SLUG: ${{ vars.SENTRY_ORG_SLUG }}
      SENTRY_PROJECT_SLUG: ${{ vars.SENTRY_PROJECT_SLUG }}
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      GH_REPO: ${{ github.repository }}
    steps:
      - name: Check kill-switch
        env:
          PAUSE: ${{ vars.PAUSE_AGENTS }}
        run: |
          if [ "${PAUSE}" = "true" ]; then
            echo "PAUSE_AGENTS=true — skipping triager"
            exit 0
          fi
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --group dev --all-packages --frozen
      - name: Triage
        run: uv run python -m agents.triager --since-hours 24
```

- [ ] **Step 2: Verify yaml**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run --with pyyaml python -c "
import yaml
d = yaml.safe_load(open('.github/workflows/triager.yml'))
print('name:', d['name'])
print('jobs:', list(d['jobs'].keys()))
print('schedule:', d['on']['schedule'])
"
```

- [ ] **Step 3: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add .github/workflows/triager.yml
git commit -m "ci: add triager cron workflow"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 5: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append section**

At the bottom of `/Users/nt-suuri/workspace/lab/ai-harness/CLAUDE.md`, append:

```

## Triager (nightly self-healing)

`triager.yml` runs at 09:00 UTC daily (and on `workflow_dispatch`). It:

1. Pulls the last 24h of Sentry-grouped issues
2. For each, checks if a GH issue with marker `<sentry-issue-id>{id}</sentry-issue-id>` already exists (open or closed → dedupe)
3. Creates new GH issues with labels `bug`, `autotriage` and a Sentry permalink in the body

To enable, populate:
- `SENTRY_AUTH_TOKEN` secret
- `SENTRY_ORG_SLUG` / `SENTRY_PROJECT_SLUG` repo variables

Without these, the triager exits 0 silently.

To trigger the loop manually: open the auto-created issue → add `agent:build` label → planner takes over.
```

- [ ] **Step 2: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add CLAUDE.md
git commit -m "docs(repo): document triager nightly flow"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

## Phase 6 exit checklist

- [ ] `uv run pytest apps/api agents` passes (70 → 84 with 2 sentry + 12 triager tests)
- [ ] `uv run mypy agents/src` exits 0
- [ ] `uv run ruff check .` passes
- [ ] `agents.triager` runs via `python -m`
- [ ] `.github/workflows/triager.yml` exists with cron `0 9 * * *`
- [ ] CLAUDE.md updated

## Out of scope (Phase 6.5+)

| Feature | Notes |
|---|---|
| LLM-based severity scoring | Use Claude Sonnet to score severity:1-10 |
| Reopen closed issues on regression | Add `level=regression` label |
| `known_false_positives.yaml` filtering | Skip Sentry IDs in the YAML file |
| Auto-attach to existing issues if title matches semantically | Beyond marker-based dedup |
| Slack/Teams alert on new issues | Use existing Resend or add a webhook secret |

## Self-review

- Marker `<sentry-issue-id>{id}</sentry-issue-id>` is HTML-comment-friendly inside markdown but visible on hover — a deliberate choice; humans can see what triager linked.
- Dedup checks `state="all"` so closed issues count too — prevents reopen cascades.
- `triage_run` returns 0 always (per `cron-friendly` design); errors are logged but don't fail the workflow.
- `_existing_marker_in_issues` handles None body defensively (some issues may have empty body).
- Triager itself does no LLM call — pure data shuffling. Cheap and reliable.
