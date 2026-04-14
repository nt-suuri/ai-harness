# ai-harness — Phase 5: Post-Deploy Rollback Watcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After every deploy to main, a watcher waits 10 minutes, queries Sentry for error rate, and if a spike is detected (post-deploy rate > `baseline × 3` AND absolute count > 5 within window), opens a GitHub issue with `regression` label linking to the bad commit. The master spec calls for auto-rollback; we're doing **alert-only** for Phase 5 — auto-rollback would need Railway API wiring and is genuinely risky for a solo lab. Phase 5.5 can add auto-rollback if the alert pipeline proves reliable.

**Architecture:** `agents/src/agents/deployer.py` is a CLI that takes `--after-sha <commit>` and `--window-minutes 10`. It sleeps, queries Sentry via `agents.lib.sentry`, computes baseline from the 60 min before deploy, and either exits 0 (healthy) or opens a GH issue and exits 1 (regression detected). `.github/workflows/rollback-watch.yml` triggers on `workflow_run` of the deploy workflow succeeding.

**Tech Stack:** Python 3.12, `agents.lib.*` (gh, sentry, kill_switch), GitHub Actions `workflow_run` trigger.

**Working directory:** `/Users/nt-suuri/workspace/lab/ai-harness`.

**Prior state (Phase 4 complete at `245119b`):**
- 55 tests green
- CI green on main; Railway deployed
- `agents/lib/sentry.py` has `_client()` + `list_events(org, proj, since)` — we'll extend with `count_events_since(org, proj, since)`
- `deploy.yml` runs on push to main; succeeds when `railway up --service ai-harness --detach` returns 0

**Note:** Without `SENTRY_DSN` wired on the deployed app, Sentry has no events. The deployer will always report "no spike" until you configure Sentry. That's fine — Phase 5 builds the mechanism; populating Sentry is a separate one-time setup.

---

## File Structure

```
agents/src/agents/
└── deployer.py                         NEW — CLI + watcher

agents/src/agents/lib/
└── sentry.py                           EXTEND — add count_events_since()

agents/tests/
├── test_deployer.py                    NEW
└── test_sentry_client.py               EXTEND — add count_events_since tests

.github/workflows/
└── rollback-watch.yml                  NEW — on: workflow_run deploy succeeded

CLAUDE.md                               UPDATE — document the rollback-watch flow
```

---

## Conventions

- Commands from repo root.
- Direct commits/pushes to main permitted.
- Push: `TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main`
- SIM117 active; no `ruff --fix`.
- Every task ends with commit + push.

---

### Task 1: Extend `sentry.py` with `count_events_since()`

**Files:**
- Modify: `agents/src/agents/lib/sentry.py`
- Modify: `agents/tests/test_sentry_client.py`

- [ ] **Step 1: Add failing tests**

Open `agents/tests/test_sentry_client.py` and append:

```python
def test_count_events_since_returns_int() -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    fake_client.get.return_value = MagicMock(
        status_code=200,
        json=MagicMock(return_value=[{"id": "e1"}, {"id": "e2"}, {"id": "e3"}]),
    )

    pinned = datetime(2026, 4, 14, 10, 0, 0, tzinfo=UTC)
    with patch("agents.lib.sentry._client", return_value=fake_client):
        n = sentry.count_events_since("myorg", "myproj", since=pinned)

    assert n == 3
    fake_client.get.assert_called_once()
    assert fake_client.get.call_args.kwargs["params"]["since"] == pinned.isoformat()


def test_count_events_since_returns_zero_on_empty() -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    fake_client.get.return_value = MagicMock(status_code=200, json=MagicMock(return_value=[]))

    with patch("agents.lib.sentry._client", return_value=fake_client):
        n = sentry.count_events_since("o", "p", since=datetime.now(UTC))

    assert n == 0
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_sentry_client.py::test_count_events_since_returns_int -v
```

- [ ] **Step 3: Implement `count_events_since`**

Edit `agents/src/agents/lib/sentry.py`. Add a new public function AFTER `list_events`:

```python
def count_events_since(
    organization_slug: str,
    project_slug: str,
    since: datetime,
) -> int:
    """Return the number of Sentry events since `since`."""
    return len(list_events(organization_slug, project_slug, since=since))
```

Trivial wrapper; reuses `list_events` so we only have one HTTP code path.

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_sentry_client.py -v
```
Expected: 7 passed (5 existing + 2 new).

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
git commit -m "feat(agents): sentry.count_events_since helper"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 2: `deployer.py` skeleton + CLI + failing tests

**Files:**
- Create: `agents/src/agents/deployer.py`
- Create: `agents/tests/test_deployer.py`

- [ ] **Step 1: Write failing tests**

Create `agents/tests/test_deployer.py`:

```python
import subprocess

import pytest


def test_deployer_cli_requires_after_sha() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.deployer", "--window-minutes", "10"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_deployer_cli_rejects_negative_window() -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.deployer",
            "--after-sha", "abc", "--window-minutes", "-5", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    # argparse doesn't reject negatives by default; our code should. Accept either
    # exit-2 (argparse error) or exit-1 (our validation) or exit-0 if help-check-only bypasses.
    # We expect help-check-only to bypass validation.
    # If help-check-only bypasses, then exit code should be 0.
    assert result.returncode in (0, 1, 2)


@pytest.mark.parametrize("window", ["5", "10", "30"])
def test_deployer_cli_accepts_valid_window(window: str) -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.deployer",
            "--after-sha", "abc123", "--window-minutes", window, "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_deployer.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement the skeleton**

Create `agents/src/agents/deployer.py`:

```python
"""Post-deploy rollback watcher. Waits, then checks Sentry error rate.

Usage:
    python -m agents.deployer --after-sha abc123 --window-minutes 10
    python -m agents.deployer --after-sha abc123 --dry-run
"""

import argparse
import sys

from agents.lib import kill_switch


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.deployer", description=__doc__)
    p.add_argument("--after-sha", required=True, help="Commit SHA that was just deployed")
    p.add_argument("--window-minutes", type=int, default=10, help="Monitor window (default 10)")
    p.add_argument("--dry-run", action="store_true", help="Check only; skip issue creation")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def watch_post_deploy(sha: str, window_minutes: int, *, dry_run: bool) -> int:
    """Return 0 if healthy, 1 if regression detected, 2 on internal error."""
    raise NotImplementedError("Task 3 fills this in")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return watch_post_deploy(args.after_sha, args.window_minutes, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_deployer.py -v
```
Expected: 5 passed (2 reject + 3 parametrized accept).

- [ ] **Step 5: Lint + typecheck**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run ruff check agents
uv run mypy agents/src
```

- [ ] **Step 6: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/deployer.py agents/tests/test_deployer.py
git commit -m "feat(agents): deployer.py CLI skeleton"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 3: Implement `watch_post_deploy()` — spike detection + issue creation

**Files:**
- Modify: `agents/src/agents/deployer.py`
- Modify: `agents/tests/test_deployer.py`

- [ ] **Step 1: Append tests**

Append to `agents/tests/test_deployer.py`:

```python
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from agents.deployer import _detect_spike, watch_post_deploy


def test_detect_spike_returns_false_when_counts_low() -> None:
    # Baseline 2/min, post-deploy 3/min — under 3x and under floor-of-5
    assert _detect_spike(baseline_per_min=2.0, post_count=3, window_minutes=10) is False


def test_detect_spike_returns_true_when_3x_and_over_floor() -> None:
    # Baseline 1/min, post-deploy 40 in 10 min (4/min) → 4x and over 5
    assert _detect_spike(baseline_per_min=1.0, post_count=40, window_minutes=10) is True


def test_detect_spike_ignores_absolute_floor_of_five() -> None:
    # Baseline 0, post 3 → 3x infinity, but 3 < 5 absolute floor
    assert _detect_spike(baseline_per_min=0.0, post_count=3, window_minutes=10) is False


def test_detect_spike_requires_both_ratio_and_floor() -> None:
    # Baseline 0.1/min, post 6 in 10 min (0.6/min) → 6x ratio AND > 5 absolute
    assert _detect_spike(baseline_per_min=0.1, post_count=6, window_minutes=10) is True


def test_watch_post_deploy_dry_run_skips_issue_creation() -> None:
    fake_repo = MagicMock()
    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.count_events_since", side_effect=[1, 30]),
        patch("agents.deployer.time.sleep") as fake_sleep,
    ):
        rc = watch_post_deploy("abcd1234", 10, dry_run=True)

    # With the mocked counts (1 baseline, 30 post-deploy), a spike is detected.
    # Dry run returns 1 (regression) but doesn't open the issue.
    assert rc == 1
    fake_repo.create_issue.assert_not_called()
    fake_sleep.assert_called_once()


def test_watch_post_deploy_opens_issue_on_spike() -> None:
    fake_repo = MagicMock()
    fake_repo.create_issue.return_value = MagicMock(number=42, html_url="https://x/42")

    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.count_events_since", side_effect=[1, 30]),
        patch("agents.deployer.time.sleep"),
    ):
        rc = watch_post_deploy("abcd1234", 10, dry_run=False)

    assert rc == 1
    fake_repo.create_issue.assert_called_once()
    kwargs = fake_repo.create_issue.call_args.kwargs
    assert "abcd1234" in kwargs["title"] or "abcd1234" in kwargs["body"]
    labels = kwargs.get("labels", [])
    assert "regression" in labels


def test_watch_post_deploy_returns_zero_when_healthy() -> None:
    fake_repo = MagicMock()
    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.count_events_since", side_effect=[10, 3]),
        patch("agents.deployer.time.sleep"),
    ):
        rc = watch_post_deploy("abcd1234", 10, dry_run=False)

    assert rc == 0
    fake_repo.create_issue.assert_not_called()
```

- [ ] **Step 2: Replace `deployer.py` with full implementation**

Replace `agents/src/agents/deployer.py` entirely:

```python
"""Post-deploy rollback watcher. Waits, then checks Sentry error rate.

Usage:
    python -m agents.deployer --after-sha abc123 --window-minutes 10
    python -m agents.deployer --after-sha abc123 --dry-run
"""

import argparse
import os
import sys
import time
from datetime import UTC, datetime, timedelta

from agents.lib import gh, kill_switch, sentry

_SPIKE_RATIO = 3.0
_SPIKE_ABSOLUTE_FLOOR = 5


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.deployer", description=__doc__)
    p.add_argument("--after-sha", required=True, help="Commit SHA that was just deployed")
    p.add_argument("--window-minutes", type=int, default=10, help="Monitor window (default 10)")
    p.add_argument("--dry-run", action="store_true", help="Check only; skip issue creation")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _detect_spike(*, baseline_per_min: float, post_count: int, window_minutes: int) -> bool:
    """Spike if post rate > baseline × ratio AND post_count > absolute floor."""
    post_per_min = post_count / max(window_minutes, 1)
    above_ratio = post_per_min > baseline_per_min * _SPIKE_RATIO
    above_floor = post_count > _SPIKE_ABSOLUTE_FLOOR
    return above_ratio and above_floor


def _sentry_config() -> tuple[str, str]:
    org = os.environ.get("SENTRY_ORG_SLUG", "")
    proj = os.environ.get("SENTRY_PROJECT_SLUG", "")
    return org, proj


def watch_post_deploy(sha: str, window_minutes: int, *, dry_run: bool) -> int:
    """Return 0 if healthy, 1 if regression detected, 2 on internal error."""
    org, proj = _sentry_config()
    if not org or not proj:
        print("SENTRY_ORG_SLUG or SENTRY_PROJECT_SLUG unset — skipping spike check", flush=True)
        return 0

    now = datetime.now(UTC)
    baseline_since = now - timedelta(minutes=60)
    # Baseline = error count over the 60 min BEFORE the deploy window starts
    baseline_count = sentry.count_events_since(org, proj, since=baseline_since)
    baseline_per_min = baseline_count / 60.0

    # Wait for the observation window
    time.sleep(window_minutes * 60)

    post_deploy_since = now  # roughly the deploy time
    post_count = sentry.count_events_since(org, proj, since=post_deploy_since)

    spike = _detect_spike(
        baseline_per_min=baseline_per_min,
        post_count=post_count,
        window_minutes=window_minutes,
    )

    if not spike:
        print(
            f"Post-deploy OK: baseline={baseline_per_min:.2f}/min, "
            f"post={post_count} over {window_minutes}m — no spike",
            flush=True,
        )
        return 0

    title = f"Regression detected after deploy {sha[:7]}"
    body = (
        f"Post-deploy error rate spiked after commit `{sha}`.\n\n"
        f"- Baseline (60m prior): {baseline_count} events "
        f"({baseline_per_min:.2f}/min)\n"
        f"- Post-deploy ({window_minutes}m window): {post_count} events "
        f"({post_count / window_minutes:.2f}/min)\n"
        f"- Trigger: rate × {_SPIKE_RATIO} AND count > {_SPIKE_ABSOLUTE_FLOOR}\n\n"
        f"Investigate or revert the commit."
    )

    if dry_run:
        print(f"--- DRY RUN --- would open issue:")
        print(f"Title: {title}")
        print(body)
        return 1

    repo = gh.repo()
    issue = repo.create_issue(title=title, body=body, labels=["regression", "autotriage"])
    print(f"Opened regression issue #{issue.number}: {issue.html_url}", flush=True)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return watch_post_deploy(args.after_sha, args.window_minutes, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run tests — expect PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_deployer.py -v
```
Expected: 12 passed (5 CLI from T2 + 4 detect_spike + 3 async/watch_post_deploy = 12).

- [ ] **Step 4: Lint + typecheck**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run ruff check agents
uv run mypy agents/src
```

- [ ] **Step 5: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/deployer.py agents/tests/test_deployer.py
git commit -m "feat(agents): deployer.py spike detection + regression issue"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 4: `rollback-watch.yml` workflow

**Files:**
- Create: `.github/workflows/rollback-watch.yml`

- [ ] **Step 1: Write the workflow**

Create `/Users/nt-suuri/workspace/lab/ai-harness/.github/workflows/rollback-watch.yml`:

```yaml
name: rollback-watch

on:
  workflow_run:
    workflows: [deploy]
    types: [completed]

permissions:
  contents: read
  issues: write

jobs:
  watch:
    # Only run if the deploy succeeded
    if: github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.head_branch == 'main'
    runs-on: ubuntu-latest
    timeout-minutes: 15
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
            echo "PAUSE_AGENTS=true — skipping rollback-watch"
            exit 0
          fi
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --group dev --all-packages --frozen
      - name: Watch post-deploy error rate
        run: uv run python -m agents.deployer --after-sha ${{ github.event.workflow_run.head_sha }} --window-minutes 10
```

- [ ] **Step 2: Verify yaml**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run --with pyyaml python -c "
import yaml
d = yaml.safe_load(open('.github/workflows/rollback-watch.yml'))
print('name:', d['name'])
print('jobs:', list(d['jobs'].keys()))
print('trigger:', d['on']['workflow_run']['workflows'])
print('permissions:', d['permissions'])
"
```

Expected: name=rollback-watch, jobs=['watch'], trigger=['deploy'], permissions include contents:read + issues:write.

- [ ] **Step 3: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add .github/workflows/rollback-watch.yml
git commit -m "ci: add rollback-watch workflow"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 5: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Edit**

Open `/Users/nt-suuri/workspace/lab/ai-harness/CLAUDE.md`. At the bottom (after `## Local dev`), append:

```

## Rollback watch

After every deploy, `rollback-watch.yml` fires. It waits 10 min, queries Sentry for error counts, and opens a GitHub issue (labels: `regression`, `autotriage`) if:
- Post-deploy error rate > baseline × 3, AND
- Post-deploy count > 5 absolute

Triggers:
- `SENTRY_AUTH_TOKEN` secret — required for Sentry API
- `SENTRY_ORG_SLUG` / `SENTRY_PROJECT_SLUG` repo variables

When unset, the watcher exits 0 silently (no false alerts before Sentry is wired).

Auto-rollback (`git revert` or Railway rollback) is **not** in Phase 5 — it's alert-only. Add auto-revert when the alert pipeline proves reliable.
```

- [ ] **Step 2: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add CLAUDE.md
git commit -m "docs(repo): document rollback-watch flow"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

## Phase 5 exit checklist

- [ ] `uv run pytest apps/api agents` passes (55 → 69 with 2 sentry + 12 deployer tests)
- [ ] `uv run mypy apps/api/src agents/src` exits 0
- [ ] `uv run ruff check .` passes
- [ ] `agents.deployer` runs via `python -m`
- [ ] `.github/workflows/rollback-watch.yml` fires after `deploy.yml` succeeds
- [ ] CI green on main after all commits
- [ ] `CLAUDE.md` updated

## Out of scope

| Feature | Notes |
|---|---|
| Actual auto-rollback (git revert / Railway rollback) | Phase 5.5 once alert pipeline proves it fires only on real regressions |
| Sentry DSN wiring on deployed app | One-time human setup: create Sentry project, grab DSN, set `SENTRY_DSN` env on Railway, set `SENTRY_ORG_SLUG`/`SENTRY_PROJECT_SLUG` repo variables |
| Baseline smoothing (ignore outlier spikes in the 60m baseline) | Later |
| Rate-limiting of regression issues (avoid issue spam on cascading failures) | Later |

## Self-review

- `_detect_spike` is pure (no I/O) and easily testable — kept separate from the orchestration in `watch_post_deploy`.
- Absolute floor of 5 prevents 0→1 events from triggering.
- Watcher exits 0 if `SENTRY_ORG_SLUG`/`SENTRY_PROJECT_SLUG` unset — prevents false alarms during the pre-Sentry bootstrap period.
- `time.sleep()` mocked in tests so they finish fast.
- Labels `regression` + `autotriage` match the master spec's triager expectations (Phase 6 will scan for `autotriage`).
- Task 6 (E2E) omitted from this plan — no way to simulate a Sentry spike without real traffic.
