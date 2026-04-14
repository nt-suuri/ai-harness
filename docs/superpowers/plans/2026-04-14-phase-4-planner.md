# ai-harness — Phase 4: Autonomous Planner Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a GitHub issue gets the `agent:build` label, the planner agent reads the issue, uses `claude-agent-sdk` (Opus 4.6) with filesystem tools to write code + tests on a feature branch, and opens a PR referencing the issue. The PR then goes through the Phase 3 reviewer flow.

**Architecture:** `agents/planner.py` is a CLI (`--issue N`, `--dry-run`) invoked by `.github/workflows/planner.yml` on `issues.labeled == agent:build`. Inside the runner, it checks out the repo, creates `feat/<issue-number>-<slug>` branch, calls `run_agent()` with `allowed_tools=["Read", "Write", "Edit", "Glob", "Grep"]` (no Bash — Claude writes blind; CI validates), commits what changed, pushes, and opens a PR.

**Tech Stack:** Python 3.12, claude-agent-sdk (Opus 4.6), PyGithub, git CLI, `agents.lib.*` shared infrastructure.

**Working directory:** `/Users/nt-suuri/workspace/lab/ai-harness`.

**Prior state (Phase 3 ongoing at commit `ef45ea2`):**
- 46 tests green (3 api + 43 agents)
- `reviewer.py` built; `reviewer.yml` deployed; `ANTHROPIC_API_KEY` pending user action
- `agents/lib/` fully available; `agents/src/agents/reviewer.py` is the existing entrypoint pattern to mirror

---

## File Structure

```
agents/src/agents/
└── planner.py                          NEW — entrypoint

agents/src/agents/lib/prompts/
└── planner.md                          EXPAND — stub → real prompt

agents/tests/
└── test_planner.py                     NEW

.github/workflows/
└── planner.yml                         NEW — on issues labeled agent:build

CLAUDE.md                               UPDATE — add `agent:build` label doc
```

---

## Conventions

- All commands from repo root.
- Lab permits direct commits/pushes to main. Push via:
  ```bash
  TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
  ```
- SIM117 active; combined-with syntax; no `ruff --fix`.
- Every task commits + pushes.

---

### Task 1: `planner.py` skeleton + CLI + failing tests

**Files:**
- Create: `agents/src/agents/planner.py`
- Create: `agents/tests/test_planner.py`

- [ ] **Step 1: Write failing tests**

Create `agents/tests/test_planner.py`:

```python
import subprocess

import pytest


def test_planner_cli_requires_issue_arg() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.planner"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_planner_cli_rejects_non_int_issue() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.planner", "--issue", "abc"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_planner_cli_accepts_int_issue_with_help_check() -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.planner",
            "--issue", "42", "--dry-run", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_planner.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement the skeleton**

Create `agents/src/agents/planner.py`:

```python
"""Autonomous planner. Triggered by `agent:build` label on an issue.

Usage:
    python -m agents.planner --issue 42
    python -m agents.planner --issue 42 --dry-run
"""

import argparse
import asyncio
import sys

from agents.lib import kill_switch


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.planner", description=__doc__)
    p.add_argument("--issue", type=int, required=True, help="GitHub issue number")
    p.add_argument("--dry-run", action="store_true", help="Plan only; skip branch/commit/push/PR")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


async def plan_and_open_pr(issue_number: int, *, dry_run: bool) -> int:
    """Return 0 on success, 1 on agent failure, 2 on internal error."""
    raise NotImplementedError("Task 2 fills this in")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return asyncio.run(plan_and_open_pr(args.issue, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run — expect 3 PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_planner.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Lint + typecheck**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run ruff check agents
uv run mypy agents/src
```

- [ ] **Step 6: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/planner.py agents/tests/test_planner.py
git commit -m "feat(agents): planner.py CLI skeleton"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 2: Implement `plan_and_open_pr()` — the actual planner logic

**Files:**
- Modify: `agents/src/agents/planner.py`
- Modify: `agents/tests/test_planner.py`

This is the meatiest task. The planner must:
1. Read the issue body from GitHub
2. Generate a branch name from the issue title
3. Run the Claude agent with filesystem tools (`Read`, `Write`, `Edit`, `Glob`, `Grep`) — NOT `Bash` (blind-write; CI validates)
4. Check if anything actually changed (`git diff --stat`)
5. Commit + push the branch
6. Open a PR referencing the issue

- [ ] **Step 1: Write the failing tests**

Append to `agents/tests/test_planner.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

from agents.planner import _branch_name, plan_and_open_pr


def test_branch_name_simple_title() -> None:
    assert _branch_name(42, "Add dark mode toggle") == "feat/42-add-dark-mode-toggle"


def test_branch_name_lowercases_and_slugifies() -> None:
    name = _branch_name(7, "Fix THE /api/users endpoint!!!")
    assert name == "feat/7-fix-the-api-users-endpoint"


def test_branch_name_truncates_long_titles() -> None:
    long = "a " * 80
    name = _branch_name(1, long.strip())
    # Slug should be bounded — 50-char slug + "feat/1-" prefix
    assert len(name) <= 60


@pytest.mark.asyncio
async def test_plan_and_open_pr_dry_run_no_side_effects() -> None:
    fake_repo = MagicMock()
    fake_issue = MagicMock()
    fake_issue.title = "Add ping"
    fake_issue.body = "Please add /ping endpoint"
    fake_repo.get_issue.return_value = fake_issue

    with (
        patch("agents.planner.gh.repo", return_value=fake_repo),
        patch("agents.planner.prompts.load", return_value="you are planner"),
        patch("agents.planner.run_agent", new=AsyncMock()) as mock_run,
        patch("agents.planner._run_git") as git,
    ):
        mock_run.return_value = MagicMock(
            messages=[{"type": "text", "text": "Done."}],
            stopped_reason="complete",
        )
        rc = await plan_and_open_pr(5, dry_run=True)

    assert rc == 0
    git.assert_not_called()
    fake_repo.create_pull.assert_not_called()


@pytest.mark.asyncio
async def test_plan_and_open_pr_opens_pr_when_changes_present() -> None:
    fake_repo = MagicMock()
    fake_issue = MagicMock()
    fake_issue.title = "Add ping"
    fake_issue.body = "Please add /ping endpoint"
    fake_repo.get_issue.return_value = fake_issue
    fake_repo.create_pull.return_value = MagicMock(number=99, html_url="https://x/99")

    with (
        patch("agents.planner.gh.repo", return_value=fake_repo),
        patch("agents.planner.prompts.load", return_value="sys"),
        patch("agents.planner.run_agent", new=AsyncMock()) as mock_run,
        patch("agents.planner._run_git") as git,
        patch("agents.planner._has_changes", return_value=True),
    ):
        mock_run.return_value = MagicMock(
            messages=[{"type": "text", "text": "Plan: add /ping."}],
            stopped_reason="complete",
        )
        rc = await plan_and_open_pr(5, dry_run=False)

    assert rc == 0
    # git called at least for checkout -b, add, commit, push
    assert git.call_count >= 4
    fake_repo.create_pull.assert_called_once()
    create_kwargs = fake_repo.create_pull.call_args.kwargs
    assert create_kwargs["base"] == "main"
    assert "Closes #5" in create_kwargs["body"]


@pytest.mark.asyncio
async def test_plan_and_open_pr_returns_1_when_agent_made_no_changes() -> None:
    fake_repo = MagicMock()
    fake_issue = MagicMock()
    fake_issue.title = "Add ping"
    fake_issue.body = "..."
    fake_repo.get_issue.return_value = fake_issue

    with (
        patch("agents.planner.gh.repo", return_value=fake_repo),
        patch("agents.planner.prompts.load", return_value="sys"),
        patch("agents.planner.run_agent", new=AsyncMock()) as mock_run,
        patch("agents.planner._run_git") as git,
        patch("agents.planner._has_changes", return_value=False),
    ):
        mock_run.return_value = MagicMock(
            messages=[{"type": "text", "text": "No changes needed."}],
            stopped_reason="complete",
        )
        rc = await plan_and_open_pr(5, dry_run=False)

    assert rc == 1
    fake_repo.create_pull.assert_not_called()
    # The agent's response should still be posted as a comment on the issue
    fake_issue.create_comment.assert_called_once()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_planner.py -v
```

- [ ] **Step 3: Implement `plan_and_open_pr()` + helpers**

Replace `agents/src/agents/planner.py` entirely with:

```python
"""Autonomous planner. Triggered by `agent:build` label on an issue.

Usage:
    python -m agents.planner --issue 42
    python -m agents.planner --issue 42 --dry-run
"""

import argparse
import asyncio
import re
import subprocess
import sys
from typing import Any

from agents.lib import gh, kill_switch, prompts
from agents.lib.anthropic import run_agent

_MAX_TURNS = 80
_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep"]
_SLUG_MAX = 40


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.planner", description=__doc__)
    p.add_argument("--issue", type=int, required=True, help="GitHub issue number")
    p.add_argument("--dry-run", action="store_true", help="Plan only; skip branch/commit/push/PR")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _branch_name(issue_number: int, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    slug = slug[:_SLUG_MAX].rstrip("-")
    return f"feat/{issue_number}-{slug}"


def _run_git(*args: str) -> str:
    """Run git with given args; return stdout. Raises on nonzero."""
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _has_changes() -> bool:
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True)
    return bool(result.stdout.strip())


def _extract_text(messages: list[Any]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


async def plan_and_open_pr(issue_number: int, *, dry_run: bool) -> int:
    """Return 0 on success, 1 if no changes produced, 2 on internal error."""
    repo = gh.repo()
    issue = repo.get_issue(issue_number)

    system = prompts.load("planner")
    user = (
        f"GitHub issue #{issue_number}: {issue.title}\n\n"
        f"Description:\n{issue.body or '(no description)'}\n\n"
        "Implement this. Write code + tests. Keep changes focused to what the issue asks for.\n"
        "When done, provide a brief 1-paragraph plan summary in your last message — it will be the PR description."
    )
    result = await run_agent(
        prompt=user,
        system=system,
        max_turns=_MAX_TURNS,
        allowed_tools=_ALLOWED_TOOLS,
    )
    plan_summary = _extract_text(result.messages)

    if dry_run:
        print(f"--- DRY RUN [issue #{issue_number}] ---")
        print(plan_summary)
        return 0

    if not _has_changes():
        # Agent didn't change anything. Post the summary as a comment on the issue.
        issue.create_comment(
            f"**Planner ran but made no changes.**\n\n{plan_summary}"
        )
        return 1

    branch = _branch_name(issue_number, issue.title)
    _run_git("checkout", "-b", branch)
    _run_git("add", "-A")
    _run_git(
        "-c", "user.name=ai-harness-bot",
        "-c", "user.email=ai-harness@local",
        "commit",
        "-m", f"feat: {issue.title}\n\nCloses #{issue_number}",
    )
    _run_git("push", "-u", "origin", branch)

    pr = repo.create_pull(
        base="main",
        head=branch,
        title=f"feat: {issue.title}",
        body=(
            f"Closes #{issue_number}\n\n"
            f"**Plan summary (by planner agent):**\n\n{plan_summary}"
        ),
    )
    print(f"Opened PR #{pr.number}: {pr.html_url}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return asyncio.run(plan_and_open_pr(args.issue, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests — expect 8 PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_planner.py -v
```

Expected: 8 passed (3 CLI from Task 1 + 3 branch_name + 1 dry_run + 1 live PR + 1 no-changes = 9. Verify actual count.)

Actually: 3 CLI + 3 branch + 3 async = 9 passed.

- [ ] **Step 5: Lint + typecheck**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run ruff check agents
uv run mypy agents/src
```

- [ ] **Step 6: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/planner.py agents/tests/test_planner.py
git commit -m "feat(agents): planner.py implements plan_and_open_pr()"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 3: Fill in `planner.md` prompt

**Files:**
- Modify: `agents/src/agents/lib/prompts/planner.md`

- [ ] **Step 1: Replace the stub**

Replace `/Users/nt-suuri/workspace/lab/ai-harness/agents/src/agents/lib/prompts/planner.md` entirely with:

```
# Planner agent

You are the autonomous planner for the ai-harness repository. You take a GitHub issue description and implement it — write code, write tests, make it pass CI.

## Repo context

This is a monorepo with:
- `apps/api/` — FastAPI backend in Python 3.12 (uv-managed)
- `apps/web/` — Vite + React + TypeScript frontend
- `agents/` — Python agents (you are one of them)
- `.github/workflows/` — CI + deploy

Python: uv workspace. Add deps via `agents/pyproject.toml` or `apps/api/pyproject.toml`. Never touch root pyproject unless adding a workspace member.

JS: pnpm workspace. Deps in `apps/web/package.json`.

Tests: pytest for python, vitest for web, playwright for e2e.

Linters: ruff (Python), tsc (TypeScript), mypy (Python strict). Your code WILL be rejected if it doesn't pass these.

## Rules

1. **Focused changes only.** Implement exactly what the issue asks. Do NOT refactor unrelated code.
2. **Always add tests.** Every new function, endpoint, or component gets a test. TDD-style: failing test → implementation → passing test.
3. **Small files.** If a file grows past ~150 lines, split it. Every file has one clear responsibility.
4. **Follow existing patterns.** Before writing a new API endpoint, look at an existing one (e.g., `apps/api/src/api/main.py`) and match its style.
5. **No style fights.** The codebase uses ruff auto-fixes + Prettier defaults. Don't impose your own style.
6. **Ask via issue comment, not chat.** If the issue is ambiguous, post a clarifying comment — don't guess.
7. **Don't touch `main`.** You work on a feature branch that will be PR'd.

## Tools you have

- `Read`, `Write`, `Edit` for file operations
- `Glob`, `Grep` for search
- You do NOT have `Bash`. You cannot run tests or install packages yourself. CI will run tests for you — write clean code and trust the pipeline.

## Output

Your **final message** becomes the PR description. Make it:
- One-paragraph summary of what you did
- Bullet list of files changed (3-5 max)
- Any manual steps a human needs to take (e.g., "set new env var FOO")

If the issue turns out to be a no-op (e.g., already implemented, or blocked by something else), say so in your final message and do NOT modify any files. The workflow detects no changes and posts your message as an issue comment instead of opening a PR.
```

- [ ] **Step 2: Verify prompts load test still passes**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_prompts.py -v
```
Expected: 3 passed.

- [ ] **Step 3: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/lib/prompts/planner.md
git commit -m "feat(prompts): fill in planner.md with real instructions"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 4: `planner.yml` GH Actions workflow

**Files:**
- Create: `.github/workflows/planner.yml`

- [ ] **Step 1: Write the workflow**

Create `/Users/nt-suuri/workspace/lab/ai-harness/.github/workflows/planner.yml`:

```yaml
name: planner

on:
  issues:
    types: [labeled]

permissions:
  contents: write
  pull-requests: write
  issues: write

jobs:
  plan:
    if: github.event.label.name == 'agent:build'
    runs-on: ubuntu-latest
    timeout-minutes: 30
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      GH_REPO: ${{ github.repository }}
    steps:
      - name: Check kill-switch
        env:
          PAUSE: ${{ vars.PAUSE_AGENTS }}
        run: |
          if [ "${PAUSE}" = "true" ]; then
            echo "PAUSE_AGENTS=true — skipping planner"
            exit 0
          fi
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --group dev --all-packages --frozen
      - name: Plan and open PR
        run: uv run python -m agents.planner --issue ${{ github.event.issue.number }}
```

- [ ] **Step 2: Verify yaml**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run --with pyyaml python -c "
import yaml
d = yaml.safe_load(open('.github/workflows/planner.yml'))
print('name:', d['name'])
print('jobs:', list(d['jobs'].keys()))
print('if:', d['jobs']['plan']['if'])
print('permissions:', d['permissions'])
"
```

Expected: name=planner, jobs=['plan'], if contains `agent:build`, permissions include `contents: write`, `pull-requests: write`, `issues: write`.

- [ ] **Step 3: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add .github/workflows/planner.yml
git commit -m "ci: add planner workflow on agent:build label"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 5: Update `CLAUDE.md` — document `agent:build` label

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Edit**

Open `CLAUDE.md`. After the `## Branch protection` section, before `## Secrets`, insert a new section:

```
## Feature intake: `agent:build` label

- Open a GitHub issue describing what you want.
- Apply the `agent:build` label.
- `planner.yml` fires → `agents/planner.py` runs Opus 4.6 with filesystem tools.
- Planner opens a PR on a `feat/<issue>-<slug>` branch, referencing the issue.
- PR goes through CI + 3-pass reviewer + 1 human approval, then merges.

If planner makes no changes, it posts its plan summary as an issue comment instead.

Kill-switch: `PAUSE_AGENTS=true` halts planner workflows.

```

- [ ] **Step 2: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add CLAUDE.md
git commit -m "docs(repo): document agent:build label for planner workflow"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 6: E2E smoke — apply `agent:build` to a test issue (BLOCKED on ANTHROPIC_API_KEY)

**Pre-requisite:** `ANTHROPIC_API_KEY` is set as a repo secret. If not, this task is blocked — a subagent cannot create the key.

- [ ] **Step 1: Create a test issue**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
gh issue create --title "Add /api/health endpoint returning current git SHA" \
  --body "Add a FastAPI route GET /api/health that returns the current git SHA from the FLY_RELEASE_VERSION env var, or 'dev' if unset. Write a unit test for it."
```

Capture the issue number.

- [ ] **Step 2: Apply the label**

```bash
gh issue edit <N> --add-label "agent:build"
```

If the label doesn't exist, create it first:
```bash
gh label create agent:build --color "5319e7" --description "Planner agent should implement this"
gh issue edit <N> --add-label "agent:build"
```

- [ ] **Step 3: Watch the planner workflow**

```bash
sleep 15
gh run list --workflow=planner.yml --limit 1
```

Poll up to 20 × 60s:
```bash
RUN_ID=<captured>
for i in $(seq 1 20); do
  STATUS=$(gh run view $RUN_ID --json status,conclusion -q '"\(.status)\t\(.conclusion // "pending")"')
  echo "attempt $i: $STATUS"
  if echo "$STATUS" | grep -q "^completed"; then break; fi
  sleep 60
done
```

- [ ] **Step 4: Verify a PR was opened**

```bash
gh pr list --state open --head "feat/<ISSUE_NUMBER>-"
```

Expected: one PR linked to the issue. Read the PR body — it should contain "Closes #<ISSUE>" and a plan summary.

- [ ] **Step 5: Let reviewer.yml run on the new PR**

Switch to watching the reviewer workflow on that PR. Once all 3 passes complete, read the quality/security/deps comments.

- [ ] **Step 6: Merge if clean, close if not**

If reviewers approve and CI is green, merge:
```bash
gh pr merge <PR> --squash --delete-branch
```

Otherwise close and examine what went wrong.

---

## Phase 4 exit checklist

- [ ] `uv run pytest apps/api agents` passes (46 → 55 with 9 planner tests)
- [ ] `uv run mypy apps/api/src agents/src` exits 0
- [ ] `uv run ruff check .` passes
- [ ] `agents/src/agents/planner.py` runs via `python -m agents.planner`
- [ ] Real `planner.md` prompt (not stub)
- [ ] `.github/workflows/planner.yml` fires on `agent:build` label
- [ ] `CLAUDE.md` documents the `agent:build` flow
- [ ] (Blocked on API key) A real issue has gone through planner → PR → reviewer → merge

## Out of scope

| Feature | Phase |
|---|---|
| Auto-deploy + rollback | 5 |
| Triager (Sentry → auto-issue) | 6 |
| Healthcheck digest | 7 |
| Planner using `Bash` tool (run tests locally before opening PR) | TBD — current blind-write + CI-validation is simpler |
| Planner retry on CI failure | TBD — Phase 5+ |

## Self-review notes

- Planner does NOT have `Bash` tool. It writes blind. CI catches failures. The PR gets 3 reviewer passes + human approval before merging. Multiple safety nets.
- `_has_changes()` after the agent run — if Claude decided there was nothing to do, we post its explanation as an issue comment and return rc=1. No empty PRs.
- Turn cap `_MAX_TURNS = 80` — matches master spec for the planner role.
- Branch naming deterministic: `feat/<N>-<slug>`, slug ≤40 chars. No collisions with other bots.
- Task 2's test set expects 9 total planner tests. Task 1 shipped 3 CLI tests; Task 2 adds 3 branch_name + 3 async = 9.
- Task 6 is blocked on the same API key gap as Phase 3 Task 7. It's the same secret — setting it once unblocks both phases.
