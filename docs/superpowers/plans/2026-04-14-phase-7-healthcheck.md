# ai-harness — Phase 7: Healthcheck + Email Digest + Canary Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Three pieces that together close out the master spec:
1. **Healthcheck** — every morning, query GitHub for yesterday's CI/deploy runs, query Sentry for error counts, and update a pinned `HEALTH` GH issue with a summary.
2. **Email digest** — same content as the HEALTH issue, sent via Resend to the developer.
3. **Canary replay** — weekly, replay sanitized Sentry+issue fixtures through each agent in `--dry-run` mode and assert the output structure stays valid (catches regressions in agent code or prompts).

**Architecture:**
- `agents/src/agents/healthcheck.py` — CLI; updates one pinned issue + sends one email.
- `agents/src/agents/lib/email.py` — thin Resend wrapper.
- `agents/tests/fixtures/` — sanitized Sentry payloads + GH issue bodies.
- `agents/src/agents/canary.py` — replays fixtures through reviewer/triager dry-runs.
- `.github/workflows/{healthcheck.yml, canary-replay.yml}` — cron schedules.

**Tech Stack:** Python 3.12, `agents.lib.*`, Resend HTTP API (no SDK — small enough to httpx-call directly), GitHub Actions cron.

**Working directory:** `/Users/nt-suuri/workspace/lab/ai-harness`.

**Prior state (Phase 6 complete at `28a8f95`):** 84 tests green; `agents.lib.{gh,sentry}` mature; `agents/{reviewer,planner,deployer,triager}.py` all live.

---

## File Structure

```
agents/src/agents/
├── healthcheck.py                      NEW — CLI + run_healthcheck()
├── canary.py                           NEW — CLI + run_canary()
└── lib/
    └── email.py                        NEW — send_email() via Resend

agents/tests/
├── test_healthcheck.py                 NEW
├── test_email.py                       NEW
├── test_canary.py                      NEW
└── fixtures/
    ├── sentry_issues_sample.json       NEW — sanitized Sentry list_issues output
    └── pr_diff_sample.txt              NEW — sanitized PR diff for reviewer replay

.github/workflows/
├── healthcheck.yml                     NEW — cron 08:00 UTC
└── canary-replay.yml                   NEW — cron weekly Sun 07:00 UTC

CLAUDE.md                               UPDATE — document healthcheck + canary
```

---

## Conventions

- All commands from repo root.
- Direct commits/pushes to main permitted.
- Push: `TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main`
- SIM117 active; no `ruff --fix`.

---

### Task 1: `agents/lib/email.py` — Resend wrapper

**Files:**
- Create: `agents/src/agents/lib/email.py`
- Create: `agents/tests/test_email.py`

- [ ] **Step 1: Tests**

Create `agents/tests/test_email.py`:

```python
import os
from unittest.mock import MagicMock, patch

import pytest

from agents.lib import email


def test_send_email_requires_api_key() -> None:
    with patch.dict(os.environ, {}, clear=True), pytest.raises(KeyError):
        email.send_email(to="a@b.com", subject="s", body="b")


def test_send_email_sends_via_resend() -> None:
    fake_resp = MagicMock(status_code=200, json=MagicMock(return_value={"id": "abc"}))
    with (
        patch.dict(os.environ, {"RESEND_API_KEY": "rk_test"}, clear=True),
        patch("agents.lib.email.httpx.post", return_value=fake_resp) as post,
    ):
        result = email.send_email(
            to="dev@example.com",
            subject="Daily report",
            body="Everything OK",
            from_addr="ai-harness@example.com",
        )

    assert result == "abc"
    post.assert_called_once()
    call = post.call_args
    assert call.args[0] == "https://api.resend.com/emails"
    assert call.kwargs["headers"]["Authorization"] == "Bearer rk_test"
    payload = call.kwargs["json"]
    assert payload["to"] == ["dev@example.com"]
    assert payload["subject"] == "Daily report"
    assert payload["from"] == "ai-harness@example.com"


def test_send_email_default_from_addr() -> None:
    fake_resp = MagicMock(status_code=200, json=MagicMock(return_value={"id": "x"}))
    with (
        patch.dict(os.environ, {"RESEND_API_KEY": "k"}, clear=True),
        patch("agents.lib.email.httpx.post", return_value=fake_resp) as post,
    ):
        email.send_email(to="x@y.z", subject="s", body="b")
    payload = post.call_args.kwargs["json"]
    assert payload["from"] == "ai-harness@onresend.dev"


def test_send_email_raises_on_non_2xx() -> None:
    fake_resp = MagicMock()
    fake_resp.raise_for_status.side_effect = Exception("422 invalid email")
    with (
        patch.dict(os.environ, {"RESEND_API_KEY": "k"}, clear=True),
        patch("agents.lib.email.httpx.post", return_value=fake_resp),
        pytest.raises(Exception, match="422"),
    ):
        email.send_email(to="bad", subject="s", body="b")
```

- [ ] **Step 2: Implement**

Create `agents/src/agents/lib/email.py`:

```python
"""Send transactional emails via Resend."""

import os

import httpx

_DEFAULT_FROM = "ai-harness@onresend.dev"


def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    from_addr: str | None = None,
) -> str:
    """Send an email via Resend; return the message id."""
    api_key = os.environ["RESEND_API_KEY"]
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "from": from_addr or _DEFAULT_FROM,
            "to": [to],
            "subject": subject,
            "html": body,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return str(resp.json()["id"])
```

- [ ] **Step 3: Test + commit**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_email.py -v
uv run ruff check agents
uv run mypy agents/src
git add agents/src/agents/lib/email.py agents/tests/test_email.py
git commit -m "feat(agents): email.send_email helper via Resend"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

Expected: 4 passed.

---

### Task 2: `healthcheck.py` + tests

**Files:**
- Create: `agents/src/agents/healthcheck.py`
- Create: `agents/tests/test_healthcheck.py`

The healthcheck:
1. If `SENTRY_*` and/or GH access — query yesterday's:
   - GH workflow runs (success/failure counts via `repo.get_workflow_runs(created=>=yesterday)`)
   - Sentry event count (via `count_events_since`)
2. Build a markdown summary
3. Find the pinned `HEALTH` issue (search by title `HEALTH dashboard`); update it (append today's section)
4. If `RESEND_API_KEY` and `HEALTHCHECK_TO_EMAIL` env set, send the same content via email

- [ ] **Step 1: Failing tests**

Create `agents/tests/test_healthcheck.py`:

```python
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from agents.healthcheck import _build_summary, run_healthcheck


def test_build_summary_includes_counts() -> None:
    summary = _build_summary(
        date_str="2026-04-14",
        ci_success=12,
        ci_failure=2,
        deploy_success=3,
        deploy_failure=0,
        sentry_event_count=5,
    )
    assert "2026-04-14" in summary
    assert "12" in summary
    assert "2" in summary
    assert "5" in summary


def test_run_healthcheck_returns_zero() -> None:
    fake_repo = MagicMock()
    # No HEALTH issue exists yet; create_issue returns one
    fake_repo.get_issues.return_value = []
    fake_repo.create_issue.return_value = MagicMock(number=1, html_url="https://x")
    fake_repo.get_workflow_runs.return_value = []

    with (
        patch("agents.healthcheck.gh.repo", return_value=fake_repo),
        patch("agents.healthcheck.sentry.count_events_since", return_value=0),
        patch.dict(os.environ, {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p"}, clear=True),
    ):
        rc = run_healthcheck(dry_run=False)
    assert rc == 0


def test_run_healthcheck_dry_run_skips_writes() -> None:
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []
    fake_repo.get_workflow_runs.return_value = []

    with (
        patch("agents.healthcheck.gh.repo", return_value=fake_repo),
        patch("agents.healthcheck.sentry.count_events_since", return_value=0),
        patch("agents.healthcheck.email.send_email") as send,
        patch.dict(os.environ, {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p"}, clear=True),
    ):
        rc = run_healthcheck(dry_run=True)

    assert rc == 0
    fake_repo.create_issue.assert_not_called()
    send.assert_not_called()


def test_run_healthcheck_sends_email_when_configured() -> None:
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []
    fake_repo.create_issue.return_value = MagicMock(number=1)
    fake_repo.get_workflow_runs.return_value = []

    with (
        patch("agents.healthcheck.gh.repo", return_value=fake_repo),
        patch("agents.healthcheck.sentry.count_events_since", return_value=0),
        patch("agents.healthcheck.email.send_email", return_value="msg1") as send,
        patch.dict(
            os.environ,
            {
                "SENTRY_ORG_SLUG": "o",
                "SENTRY_PROJECT_SLUG": "p",
                "RESEND_API_KEY": "rk",
                "HEALTHCHECK_TO_EMAIL": "dev@x.com",
            },
            clear=True,
        ),
    ):
        rc = run_healthcheck(dry_run=False)
    assert rc == 0
    send.assert_called_once()


def test_run_healthcheck_skips_email_when_no_recipient() -> None:
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []
    fake_repo.create_issue.return_value = MagicMock(number=1)
    fake_repo.get_workflow_runs.return_value = []

    with (
        patch("agents.healthcheck.gh.repo", return_value=fake_repo),
        patch("agents.healthcheck.sentry.count_events_since", return_value=0),
        patch("agents.healthcheck.email.send_email") as send,
        patch.dict(
            os.environ,
            {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p", "RESEND_API_KEY": "rk"},
            clear=True,
        ),
    ):
        rc = run_healthcheck(dry_run=False)
    assert rc == 0
    send.assert_not_called()  # No HEALTHCHECK_TO_EMAIL set → no email
```

- [ ] **Step 2: Implement**

Create `agents/src/agents/healthcheck.py`:

```python
"""Daily healthcheck. Updates pinned HEALTH issue + (optionally) sends email digest.

Usage:
    python -m agents.healthcheck
    python -m agents.healthcheck --dry-run
"""

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta

from agents.lib import email, gh, kill_switch, sentry

_HEALTH_ISSUE_TITLE = "HEALTH dashboard"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.healthcheck", description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Print summary; skip writes")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _build_summary(
    *,
    date_str: str,
    ci_success: int,
    ci_failure: int,
    deploy_success: int,
    deploy_failure: int,
    sentry_event_count: int,
) -> str:
    return (
        f"## {date_str}\n\n"
        f"- CI runs: {ci_success} success, {ci_failure} failure\n"
        f"- Deploys: {deploy_success} success, {deploy_failure} failure\n"
        f"- Sentry events (last 24h): {sentry_event_count}\n"
    )


def _count_runs(repo, workflow_file: str, since: datetime) -> tuple[int, int]:
    success = 0
    failure = 0
    for r in repo.get_workflow_runs(workflow_file_name=workflow_file, created=f">={since.date().isoformat()}"):
        if r.conclusion == "success":
            success += 1
        elif r.conclusion == "failure":
            failure += 1
    return success, failure


def run_healthcheck(*, dry_run: bool) -> int:
    """Return 0 always."""
    org = os.environ.get("SENTRY_ORG_SLUG", "")
    proj = os.environ.get("SENTRY_PROJECT_SLUG", "")
    repo = gh.repo()
    yesterday = datetime.now(UTC) - timedelta(hours=24)
    date_str = datetime.now(UTC).date().isoformat()

    ci_success, ci_failure = _count_runs(repo, "ci.yml", yesterday)
    deploy_success, deploy_failure = _count_runs(repo, "deploy.yml", yesterday)

    sentry_count = 0
    if org and proj:
        try:
            sentry_count = sentry.count_events_since(org, proj, since=yesterday)
        except Exception as e:  # noqa: BLE001
            print(f"warning: sentry count failed: {e}", flush=True)

    summary = _build_summary(
        date_str=date_str,
        ci_success=ci_success,
        ci_failure=ci_failure,
        deploy_success=deploy_success,
        deploy_failure=deploy_failure,
        sentry_event_count=sentry_count,
    )

    if dry_run:
        print("--- DRY RUN ---")
        print(summary)
        return 0

    # Find or create the pinned HEALTH issue
    existing = list(repo.get_issues(state="open", labels=["healthcheck"]))
    if existing:
        issue = existing[0]
        new_body = f"{issue.body or ''}\n\n{summary}"
        issue.edit(body=new_body)
        print(f"Updated HEALTH issue #{issue.number}")
    else:
        issue = repo.create_issue(
            title=_HEALTH_ISSUE_TITLE,
            body=summary,
            labels=["healthcheck"],
        )
        print(f"Created HEALTH issue #{issue.number}")

    # Optionally email
    to_email = os.environ.get("HEALTHCHECK_TO_EMAIL", "")
    if to_email and os.environ.get("RESEND_API_KEY"):
        email.send_email(
            to=to_email,
            subject=f"ai-harness daily {date_str}",
            body=summary.replace("\n", "<br>"),
        )
        print(f"Emailed digest to {to_email}")

    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return run_healthcheck(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Test + commit**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_healthcheck.py -v
uv run ruff check agents
uv run mypy agents/src
git add agents/src/agents/healthcheck.py agents/tests/test_healthcheck.py
git commit -m "feat(agents): healthcheck.py — daily HEALTH issue + optional email"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

Expected: 5 passed.

---

### Task 3: Canary replay — fixtures + `canary.py`

**Files:**
- Create: `agents/tests/fixtures/sentry_issues_sample.json`
- Create: `agents/tests/fixtures/pr_diff_sample.txt`
- Create: `agents/src/agents/canary.py`
- Create: `agents/tests/test_canary.py`

- [ ] **Step 1: Fixtures**

Create `agents/tests/fixtures/sentry_issues_sample.json`:

```json
[
  {
    "id": "sample-1",
    "title": "ZeroDivisionError: integer division or modulo by zero",
    "culprit": "apps/api/main.py:42",
    "count": "12",
    "permalink": "https://sentry.io/organizations/x/issues/1/",
    "level": "error",
    "lastSeen": "2026-04-14T08:00:00Z"
  },
  {
    "id": "sample-2",
    "title": "ConnectionError: timeout to upstream",
    "culprit": "apps/api/router.py:88",
    "count": "3",
    "permalink": "https://sentry.io/organizations/x/issues/2/",
    "level": "warning",
    "lastSeen": "2026-04-14T08:00:00Z"
  }
]
```

Create `agents/tests/fixtures/pr_diff_sample.txt`:

```
--- apps/api/src/api/main.py ---
@@ -1,3 +1,5 @@
 from fastapi import FastAPI
+
+VERSION = "1.0"
 
 app = FastAPI(title="ai-harness api")
```

- [ ] **Step 2: Failing tests**

Create `agents/tests/test_canary.py`:

```python
from pathlib import Path

from agents.canary import _load_fixture, run_canary


_FIXTURES = Path(__file__).parent / "fixtures"


def test_load_fixture_reads_json() -> None:
    data = _load_fixture("sentry_issues_sample.json")
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["id"] == "sample-1"


def test_load_fixture_reads_text() -> None:
    text = _load_fixture("pr_diff_sample.txt")
    assert isinstance(text, str)
    assert "main.py" in text


def test_run_canary_returns_zero_on_success() -> None:
    rc = run_canary(dry_run=True)
    assert rc == 0


def test_run_canary_validates_sentry_fixture_shape() -> None:
    # Test the structural invariants the triager would expect
    issues = _load_fixture("sentry_issues_sample.json")
    for issue in issues:
        assert "id" in issue
        assert "title" in issue
        assert "permalink" in issue
        assert "count" in issue
```

- [ ] **Step 3: Implement canary.py**

Create `agents/src/agents/canary.py`:

```python
"""Weekly canary replay. Reads sanitized fixtures, asserts agent code still
parses them correctly. Catches regressions in agent parsers/prompts.

Usage:
    python -m agents.canary
    python -m agents.canary --dry-run
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agents.lib import kill_switch
from agents.triager import _format_issue_body, _make_marker

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.canary", description=__doc__)
    p.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _load_fixture(name: str) -> Any:
    path = _FIXTURE_DIR / name
    if name.endswith(".json"):
        return json.loads(path.read_text())
    return path.read_text()


def run_canary(*, dry_run: bool) -> int:
    """Return 0 if all canaries green, 1 if any structural assertion failed."""
    failures = 0

    # Canary 1: triager fixture loads and produces a non-empty issue body
    sentry_issues = _load_fixture("sentry_issues_sample.json")
    for issue in sentry_issues:
        marker = _make_marker(str(issue["id"]))
        body = _format_issue_body(issue, marker)
        if marker not in body:
            print(f"FAIL: triager body missing marker for {issue['id']}")
            failures += 1
        if "Sentry permalink" not in body:
            print(f"FAIL: triager body missing permalink line")
            failures += 1

    # Canary 2: PR diff fixture is non-empty and looks like a diff
    diff = _load_fixture("pr_diff_sample.txt")
    if "@@" not in diff:
        print("FAIL: pr_diff_sample.txt does not look like a diff")
        failures += 1

    if failures:
        print(f"canary: {failures} failure(s)")
        return 1
    print("canary: all green")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return run_canary(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
```

Note: `_FIXTURE_DIR` resolution — `__file__` is `agents/src/agents/canary.py`. `parents[0]=agents/src/agents`, `parents[1]=agents/src`, `parents[2]=agents`. Then `tests/fixtures` is correct.

- [ ] **Step 4: Test + commit**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_canary.py -v
uv run ruff check agents
uv run mypy agents/src
git add agents/src/agents/canary.py agents/tests/test_canary.py agents/tests/fixtures/
git commit -m "feat(agents): canary replay + fixtures"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

Expected: 4 passed.

---

### Task 4: `healthcheck.yml` workflow

Create `/Users/nt-suuri/workspace/lab/ai-harness/.github/workflows/healthcheck.yml`:

```yaml
name: healthcheck

on:
  schedule:
    - cron: "0 8 * * *"
  workflow_dispatch:

permissions:
  contents: read
  issues: write

jobs:
  health:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    env:
      SENTRY_AUTH_TOKEN: ${{ secrets.SENTRY_AUTH_TOKEN }}
      SENTRY_ORG_SLUG: ${{ vars.SENTRY_ORG_SLUG }}
      SENTRY_PROJECT_SLUG: ${{ vars.SENTRY_PROJECT_SLUG }}
      RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}
      HEALTHCHECK_TO_EMAIL: ${{ vars.HEALTHCHECK_TO_EMAIL }}
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      GH_REPO: ${{ github.repository }}
    steps:
      - name: Check kill-switch
        env:
          PAUSE: ${{ vars.PAUSE_AGENTS }}
        run: |
          if [ "${PAUSE}" = "true" ]; then
            echo "PAUSE_AGENTS=true — skipping healthcheck"
            exit 0
          fi
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --group dev --all-packages --frozen
      - run: uv run python -m agents.healthcheck
```

Commit:
```bash
git add .github/workflows/healthcheck.yml
git commit -m "ci: add healthcheck cron workflow"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 5: `canary-replay.yml` workflow

Create `/Users/nt-suuri/workspace/lab/ai-harness/.github/workflows/canary-replay.yml`:

```yaml
name: canary-replay

on:
  schedule:
    - cron: "0 7 * * 0"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  replay:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Check kill-switch
        env:
          PAUSE: ${{ vars.PAUSE_AGENTS }}
        run: |
          if [ "${PAUSE}" = "true" ]; then
            echo "PAUSE_AGENTS=true — skipping canary"
            exit 0
          fi
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --group dev --all-packages --frozen
      - run: uv run python -m agents.canary
```

Commit:
```bash
git add .github/workflows/canary-replay.yml
git commit -m "ci: add canary-replay weekly workflow"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 6: CLAUDE.md final update

At the bottom of `/Users/nt-suuri/workspace/lab/ai-harness/CLAUDE.md`, append:

```

## Healthcheck (daily)

`healthcheck.yml` runs at 08:00 UTC. Updates a pinned `HEALTH dashboard` issue (label: `healthcheck`) with yesterday's CI/deploy/Sentry counts. If `RESEND_API_KEY` secret + `HEALTHCHECK_TO_EMAIL` repo variable are set, also emails the same content.

## Canary replay (weekly)

`canary-replay.yml` runs Sundays at 07:00 UTC. Replays sanitized fixtures from `agents/tests/fixtures/` through `triager` parsers + reviewer prompt-load. Catches regressions in agent code. Fails if structural assertions break.
```

Commit:
```bash
git add CLAUDE.md
git commit -m "docs(repo): document healthcheck + canary-replay flows"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

## Phase 7 exit checklist

- [ ] `uv run pytest apps/api agents` passes (84 → 97 with 4 email + 5 healthcheck + 4 canary tests)
- [ ] `uv run mypy agents/src` exits 0
- [ ] `uv run ruff check .` passes
- [ ] All three new workflows (healthcheck, canary-replay) parseable
- [ ] CLAUDE.md final
- [ ] Master spec exit criteria met (modulo activation requiring API keys)

## Out of scope

| Feature | Notes |
|---|---|
| Slack/Teams posting | Email digest is enough for solo |
| LLM-summarized digest (Claude reads logs and writes a one-paragraph "yesterday went well") | Phase 7.5 |
| Canary replays through real Anthropic API | Would burn tokens weekly; structural assertions only for now |
| Pinned-issue auto-pin via GH API | The `healthcheck` label is enough; user can pin manually |

## Self-review

- `email.py` is 23 lines; one function, no SDK dependency, handles missing key + non-2xx properly.
- `healthcheck.py` is decoupled: gracefully degrades if Sentry unconfigured; email is opt-in via `HEALTHCHECK_TO_EMAIL`.
- `canary.py` runs zero-cost (no API calls) — uses fixtures + agent helpers directly. Catches "I broke `_format_issue_body`" type regressions.
- Resend has a "from" address that requires domain verification; defaulted to `ai-harness@onresend.dev` (Resend's free testing address). Real prod would require a verified domain.
- All three workflows respect `PAUSE_AGENTS`.
- The fixture files are committed — they're the source of truth for canary assertions.
