# ai-harness — Phase 10: Stale Issue Closer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Auto-close `autotriage`-labeled issues that have had no activity for 14+ days. Keeps the issue list useful (real backlog) instead of accumulating noise from one-off Sentry events that never recurred.

**Architecture:** `agents/src/agents/stale.py` is a CLI (`--stale-days 14`, `--dry-run`). Iterates open issues with label `autotriage`, checks `updated_at`, closes ones older than threshold with a comment explaining why. `.github/workflows/stale.yml` runs weekly.

**Tech Stack:** Python 3.12, PyGithub, `agents.lib.*`. No LLM call (cost-free).

**Working dir:** `/Users/nt-suuri/workspace/lab/ai-harness`.

**Prior state:** Phase 9 complete at `83b282d`. 115 Python tests + 4 web tests.

---

## File Structure

```
agents/src/agents/
└── stale.py                            NEW — CLI + run_stale_close()

agents/tests/
└── test_stale.py                       NEW

.github/workflows/
└── stale.yml                           NEW — weekly cron

CLAUDE.md                               UPDATE
```

---

### Task 1: stale.py + workflow + tests (single subagent)

**Files:**
- Create: `agents/src/agents/stale.py`
- Create: `agents/tests/test_stale.py`
- Create: `.github/workflows/stale.yml`
- Modify: `CLAUDE.md`

- [ ] **Tests** (`agents/tests/test_stale.py`):

```python
import os
import subprocess
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from agents.stale import _is_stale, run_stale_close


def test_cli_runs_with_dry_run() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.stale", "--dry-run", "--help-check-only"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_cli_accepts_stale_days() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.stale", "--stale-days", "30", "--help-check-only"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_is_stale_true_when_old() -> None:
    old = datetime.now(UTC) - timedelta(days=20)
    assert _is_stale(old, threshold_days=14) is True


def test_is_stale_false_when_recent() -> None:
    recent = datetime.now(UTC) - timedelta(days=3)
    assert _is_stale(recent, threshold_days=14) is False


def test_is_stale_naive_datetime_treated_as_utc() -> None:
    # PyGithub may return naive datetimes — handle gracefully
    naive_old = (datetime.now(UTC) - timedelta(days=20)).replace(tzinfo=None)
    assert _is_stale(naive_old, threshold_days=14) is True


def test_run_stale_close_closes_old_issues() -> None:
    fake_repo = MagicMock()
    old_issue = MagicMock(number=1, updated_at=datetime.now(UTC) - timedelta(days=30))
    new_issue = MagicMock(number=2, updated_at=datetime.now(UTC) - timedelta(days=2))
    fake_repo.get_issues.return_value = [old_issue, new_issue]

    with patch("agents.stale.gh.repo", return_value=fake_repo):
        rc = run_stale_close(stale_days=14, dry_run=False)

    assert rc == 0
    old_issue.create_comment.assert_called_once()
    old_issue.edit.assert_called_once_with(state="closed", state_reason="not_planned")
    new_issue.edit.assert_not_called()


def test_run_stale_close_dry_run_skips_writes() -> None:
    fake_repo = MagicMock()
    old_issue = MagicMock(number=1, updated_at=datetime.now(UTC) - timedelta(days=30))
    fake_repo.get_issues.return_value = [old_issue]

    with patch("agents.stale.gh.repo", return_value=fake_repo):
        rc = run_stale_close(stale_days=14, dry_run=True)

    assert rc == 0
    old_issue.create_comment.assert_not_called()
    old_issue.edit.assert_not_called()
```

- [ ] **Implementation** (`agents/src/agents/stale.py`):

```python
"""Close autotriage issues that have had no activity for N days.

Usage:
    python -m agents.stale
    python -m agents.stale --stale-days 30 --dry-run
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta

from agents.lib import gh, kill_switch


_CLOSE_COMMENT = (
    "Closing as stale (no activity for {days}+ days). The triager will reopen "
    "automatically if the underlying error recurs."
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.stale", description=__doc__)
    p.add_argument("--stale-days", type=int, default=14, help="Threshold (default 14)")
    p.add_argument("--dry-run", action="store_true", help="List candidates; skip writes")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _is_stale(updated_at: datetime, *, threshold_days: int) -> bool:
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    age = datetime.now(UTC) - updated_at
    return age >= timedelta(days=threshold_days)


def run_stale_close(stale_days: int, *, dry_run: bool) -> int:
    """Return 0 always."""
    repo = gh.repo()
    issues = list(repo.get_issues(state="open", labels=["autotriage"]))

    closed = 0
    skipped = 0
    for issue in issues:
        if not _is_stale(issue.updated_at, threshold_days=stale_days):
            skipped += 1
            continue
        if dry_run:
            print(f"DRY RUN — would close #{issue.number} (updated {issue.updated_at})")
            closed += 1
            continue
        issue.create_comment(_CLOSE_COMMENT.format(days=stale_days))
        issue.edit(state="closed", state_reason="not_planned")
        print(f"Closed stale issue #{issue.number}")
        closed += 1

    print(f"stale-close: closed={closed} skipped={skipped} total={len(issues)}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return run_stale_close(args.stale_days, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Workflow** (`.github/workflows/stale.yml`):

```yaml
name: stale

on:
  schedule:
    - cron: "0 10 * * 0"
  workflow_dispatch:

permissions:
  contents: read
  issues: write

jobs:
  close:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    env:
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      GH_REPO: ${{ github.repository }}
    steps:
      - name: Check kill-switch
        env:
          PAUSE: ${{ vars.PAUSE_AGENTS }}
        run: |
          if [ "${PAUSE}" = "true" ]; then
            echo "PAUSE_AGENTS=true — skipping stale"
            exit 0
          fi
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --group dev --all-packages --frozen
      - run: uv run python -m agents.stale --stale-days 14
```

- [ ] **CLAUDE.md append**:

```

## Stale issue closer (weekly)

`stale.yml` runs Sundays at 10:00 UTC. Closes any open issue with label `autotriage` whose `updated_at` is more than 14 days ago. Adds a comment explaining the close. The triager will reopen automatically if the underlying error recurs (Sentry id-based dedup).

Override threshold via `workflow_dispatch` UI input (not currently exposed; edit the workflow's `--stale-days` flag if you need a different value).
```

- [ ] **Test + commit**:

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_stale.py -v
uv run ruff check agents
uv run mypy agents/src
git add agents/src/agents/stale.py agents/tests/test_stale.py .github/workflows/stale.yml CLAUDE.md
git commit -m "feat(agents): stale closer for autotriage issues"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

Expected: 7 passed.

---

## Phase 10 exit checklist

- [ ] `uv run pytest apps/api agents` passes (115 → 122)
- [ ] `uv run ruff check .` passes
- [ ] `agents.stale` runs via `python -m`
- [ ] `.github/workflows/stale.yml` weekly cron exists
- [ ] CLAUDE.md updated
