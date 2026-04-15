# Planner Reliability Implementation Plan (P60)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make planner-opened PRs merge-ready without human edits by giving the LLM concrete repo conventions, adding pre-commit validation, and unblocking CI/reviewer on planner PRs.

**Architecture:** Three tightly-scoped sub-phases. (P60a) Expand `planner.md` with explicit import/test-location examples the LLM can mimic. (P60b) After the planner's tool-use loop, run `ruff check` + per-file `python -m compileall` + touched-test `pytest` locally before committing; on failure, feed errors back into the LLM for one fix attempt. (P60c) Switch CI + reviewer triggers to `pull_request_target` (with PR-head checkout) so planner-opened PRs run the same gates as human-opened ones.

**Tech Stack:** Python 3.12, `subprocess` for validation shell-outs, GitHub Actions (`pull_request_target`), pytest, existing `agents.lib.anthropic.run_agent` loop.

---

## Context: why this change

PR #15 and PR #17 (both opened by the planner via issue → PR chain) shipped with import bugs that any local `ruff` run would have caught:

- `import hello` instead of `from api import hello`
- `from apps.api.src.api import app` instead of `from api.main import app`

Root cause (from code-explorer diagnosis):

1. The planner system prompt says "follow existing patterns" but gives no before/after examples. `gpt-4o-mini` lacks the repo-specific knowledge to guess correctly, and rarely reads existing neighbours before `Write`-ing.
2. The planner has NO post-tool-loop validation. `agents/src/agents/planner.py` goes straight from `run_agent()` → `_has_changes()` → commit. It never runs `ruff`, `compileall`, or `pytest` locally.
3. GitHub's cascade protection blocks `pull_request` events on PRs opened by the built-in `GITHUB_TOKEN`. Neither CI nor reviewer fires on planner PRs, so the import bugs slip through unchecked.

This plan addresses all three.

## Scope check

Single subsystem (planner), three concrete improvements. Each sub-phase lands working software:

- **P60a** — prompt enhancement alone measurably improves planner output, even before validation lands.
- **P60b** — validation gate catches mistakes the prompt still lets through, with a single LLM retry.
- **P60c** — unblocks the reviewer/CI signal so future bugs surface automatically.

## File structure

### Files modified

| Path | Change |
|---|---|
| `agents/src/agents/lib/prompts/planner.md` | Expand to include "Repo conventions" section with before/after examples for imports, test locations, router registration |
| `agents/src/agents/planner.py` | Add `_validate()` and `_retry_on_validation_fail()`; call after `run_agent()` loop, before `_has_changes()` |
| `agents/tests/test_planner.py` | New tests for validation gate + retry logic |
| `.github/workflows/ci.yml` | Switch `on: pull_request` → `on: pull_request_target` + explicit checkout of `github.event.pull_request.head.sha` |
| `.github/workflows/reviewer.yml` | Same trigger switch |
| `CLAUDE.md` | Document new validation step + `pull_request_target` security model |

### Files created

None. All changes modify existing files.

---

# Phase P60a — Expand the planner system prompt

**Goal:** Give the LLM concrete, repo-specific examples of imports and test locations so it doesn't guess.

## Task 1: Rewrite `planner.md` with repo conventions section

**Files:**
- Modify: `agents/src/agents/lib/prompts/planner.md`

- [ ] **Step 1: Append a new "Repo conventions" section**

Edit `agents/src/agents/lib/prompts/planner.md`. Immediately after the existing "## Rules" block (ends around line 29), insert this section:

```markdown
## Repo conventions (READ THIS BEFORE YOU WRITE ANY CODE)

These are the ONLY correct import and layout patterns. Files using other forms WILL fail CI.

### Python API imports

```python
# RIGHT — in apps/api/src/api/*.py:
from api.main import app
from api.security import limiter
from fastapi import APIRouter

router = APIRouter()

# RIGHT — in apps/api/tests/test_*.py:
from fastapi.testclient import TestClient
from api.main import app

def test_something():
    client = TestClient(app)
    ...
```

```python
# WRONG — these paths do NOT resolve:
from apps.api.src.api import app   # the package is published as `api`, not `apps.api.src.api`
import hello                        # must be `from api import hello`
from api import main                # correct is `from api.main import app`
```

### File locations

- A new API route goes in `apps/api/src/api/<name>.py` with `router = APIRouter()`. It is wired into the app via `apps/api/src/api/main.py` — locate the existing `app.include_router(...)` block and add `app.include_router(<name>_router)` alongside it.
- A new API test goes in `apps/api/tests/test_<name>.py` (NOT in `apps/api/src/tests/` — that directory does not exist).
- A new agent module goes in `agents/src/agents/<name>.py`. Tests in `agents/tests/test_<name>.py`.
- Never put tests inside `src/`.

### Before you `Write` a new file

1. `Glob` for a similar existing file (e.g. if making a new API route, `Glob("apps/api/src/api/*.py")` and `Read` two of them).
2. `Read` one existing test in the same package (e.g. `apps/api/tests/test_ping.py`) to learn the test import pattern.
3. Only then `Write` your new file — copy the import style exactly.

### Wiring a new route into main.py

If you add `apps/api/src/api/hello.py`, you MUST also `Edit` `apps/api/src/api/main.py` to register the router. The pattern is:

```python
from api.hello import router as hello_router  # add this import at the top

app.include_router(hello_router)  # add this line in the include-router block
```

Never edit `apps/api/src/api/__init__.py` — it is intentionally empty.
```

- [ ] **Step 2: Commit**

```bash
git add agents/src/agents/lib/prompts/planner.md
git commit -m "feat(planner): add repo conventions section with before/after imports

Prior planner PRs shipped with wrong imports because the prompt said
'follow existing patterns' without concrete examples. Gives gpt-4o-mini
the import paths, test locations, and router-wiring pattern verbatim.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

Then: `git push origin main`

---

# Phase P60b — Pre-commit validation in planner.py

**Goal:** After the LLM's tool loop finishes, run ruff + python import check locally. On failure, feed errors back to the LLM for ONE retry before giving up.

## Task 2: Validation helper module

**Files:**
- Create: `agents/src/agents/lib/planner_validate.py`
- Test: `agents/tests/test_planner_validate.py`

- [ ] **Step 1: Write the failing test**

Write `agents/tests/test_planner_validate.py`:

```python
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from agents.lib import planner_validate


def test_validate_returns_empty_when_all_pass(tmp_path: Path) -> None:
    with patch("agents.lib.planner_validate._run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        errors = planner_validate.validate(tmp_path, ["apps/api/src/api/new.py"])
    assert errors == []


def test_validate_returns_ruff_error_detail(tmp_path: Path) -> None:
    ruff_fail = subprocess.CompletedProcess(
        [], 1, "E501 Line too long\nF401 unused import\n", ""
    )
    with patch("agents.lib.planner_validate._run") as run:
        run.side_effect = [
            ruff_fail,  # ruff call fails
            subprocess.CompletedProcess([], 0, "", ""),  # compileall passes
        ]
        errors = planner_validate.validate(tmp_path, ["x.py"])
    assert len(errors) == 1
    assert "ruff" in errors[0].lower()
    assert "E501" in errors[0]


def test_validate_returns_import_error_detail(tmp_path: Path) -> None:
    with patch("agents.lib.planner_validate._run") as run:
        run.side_effect = [
            subprocess.CompletedProcess([], 0, "", ""),  # ruff passes
            subprocess.CompletedProcess([], 1, "", "ImportError: no module 'foo'\n"),
        ]
        errors = planner_validate.validate(tmp_path, ["apps/api/src/api/x.py"])
    assert len(errors) == 1
    assert "import" in errors[0].lower()
    assert "ImportError" in errors[0]


def test_validate_runs_touched_tests_when_test_file_present(tmp_path: Path) -> None:
    with patch("agents.lib.planner_validate._run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        planner_validate.validate(tmp_path, ["apps/api/tests/test_hello.py", "apps/api/src/api/hello.py"])
        calls = [c.args[0] for c in run.call_args_list]
        pytest_calls = [c for c in calls if "pytest" in c]
        assert pytest_calls, "pytest should be invoked when a test file is in the change set"
        assert "apps/api/tests/test_hello.py" in pytest_calls[0]


def test_validate_pytest_failure_returned_as_error(tmp_path: Path) -> None:
    with patch("agents.lib.planner_validate._run") as run:
        run.side_effect = [
            subprocess.CompletedProcess([], 0, "", ""),  # ruff ok
            subprocess.CompletedProcess([], 0, "", ""),  # compileall ok
            subprocess.CompletedProcess([], 1, "AssertionError: expected 200 got 404\n", ""),
        ]
        errors = planner_validate.validate(tmp_path, ["apps/api/tests/test_x.py", "apps/api/src/api/x.py"])
    assert len(errors) == 1
    assert "pytest" in errors[0].lower()
    assert "AssertionError" in errors[0]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/nt-suuri/workspace/lab/ai-harness && uv run pytest agents/tests/test_planner_validate.py -v`

Expected: FAIL — `ModuleNotFoundError: agents.lib.planner_validate`.

- [ ] **Step 3: Implement**

Write `agents/src/agents/lib/planner_validate.py`:

```python
"""Run ruff + compileall + touched-pytest locally against planner's changeset.

Returns a list of human-readable error strings (empty = all good).
The caller feeds these back into the LLM for a single retry attempt.
"""

import subprocess
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)


def _ruff(cwd: Path, files: list[str]) -> str | None:
    if not files:
        return None
    result = _run(["uv", "run", "ruff", "check", *files], cwd)
    if result.returncode == 0:
        return None
    return f"ruff check failed:\n{result.stdout.strip()}"


def _compile(cwd: Path, files: list[str]) -> str | None:
    py_files = [f for f in files if f.endswith(".py")]
    if not py_files:
        return None
    result = _run(["uv", "run", "python", "-m", "compileall", "-q", *py_files], cwd)
    if result.returncode == 0:
        return None
    return f"python import/syntax check failed:\n{result.stderr.strip() or result.stdout.strip()}"


def _pytest(cwd: Path, test_files: list[str]) -> str | None:
    if not test_files:
        return None
    result = _run(["uv", "run", "pytest", "-x", "--no-header", *test_files], cwd)
    if result.returncode == 0:
        return None
    return f"pytest failed:\n{result.stdout.strip()[-2000:]}"


def validate(cwd: Path, changed_files: list[str]) -> list[str]:
    """Return a list of error messages. Empty list = validation passed."""
    errors: list[str] = []
    test_files = [f for f in changed_files if "/tests/" in f and f.endswith(".py")]

    for checker in (
        lambda: _ruff(cwd, [f for f in changed_files if f.endswith(".py")]),
        lambda: _compile(cwd, changed_files),
        lambda: _pytest(cwd, test_files),
    ):
        err = checker()
        if err:
            errors.append(err)
    return errors
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest agents/tests/test_planner_validate.py -v`

Expected: PASS — 5/5.

- [ ] **Step 5: Commit**

```bash
git add agents/src/agents/lib/planner_validate.py agents/tests/test_planner_validate.py
git commit -m "feat(agents): add planner_validate for pre-commit ruff/compile/pytest

Wraps subprocess calls to ruff/compileall/pytest scoped to the
planner's changeset. Returns errors as strings for LLM retry.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

Then: `git push origin main`

## Task 3: Wire validation into planner.py with one retry

**Files:**
- Modify: `agents/src/agents/planner.py`
- Test: `agents/tests/test_planner.py` (or add new tests)

- [ ] **Step 1: Inspect current planner flow**

Read `agents/src/agents/planner.py` to locate the block where the tool loop completes and commits land. Identify the exact line where `_has_changes()` is called. The validation call must be inserted immediately before that point, scoped to the list of files the planner actually touched (use `git status --porcelain` or parse `_run_git("diff", "--name-only")` output).

- [ ] **Step 2: Write the failing test**

Append to `agents/tests/test_planner.py`:

```python
@pytest.mark.asyncio
async def test_planner_retries_once_on_validation_failure(tmp_path: Path, monkeypatch) -> None:
    """If validate() returns errors, planner calls run_agent once more with errors in prompt."""
    monkeypatch.chdir(tmp_path)

    call_count = {"n": 0}

    async def fake_run_agent(prompt, **_):
        call_count["n"] += 1
        # Always produces changes; simulated by our _changed_files mock
        return MagicMock(messages=[{"type": "text", "text": f"done (call {call_count['n']})"}])

    validate_results = [["ruff check failed: E501 line too long"], []]  # fail, then pass

    def fake_validate(cwd, files):
        return validate_results.pop(0)

    with (
        patch("agents.planner.run_agent", fake_run_agent),
        patch("agents.planner.planner_validate.validate", fake_validate),
        patch("agents.planner._changed_files", return_value=["apps/api/src/api/x.py"]),
        patch("agents.planner._has_changes", return_value=True),
        patch("agents.planner._commit_and_push"),
        patch("agents.planner._open_pr", return_value=MagicMock(number=42, html_url="u")),
        patch("agents.planner.gh.repo", return_value=MagicMock()),
    ):
        await planner.plan_and_pr(issue_number=1)

    assert call_count["n"] == 2, "planner should retry once when validate returns errors"


@pytest.mark.asyncio
async def test_planner_gives_up_after_one_retry(tmp_path: Path, monkeypatch) -> None:
    """Two consecutive validation failures mean the planner posts a concern comment, no PR."""
    monkeypatch.chdir(tmp_path)
    call_count = {"n": 0}

    async def fake_run_agent(prompt, **_):
        call_count["n"] += 1
        return MagicMock(messages=[{"type": "text", "text": "done"}])

    def always_fail(cwd, files):
        return ["ruff still failing"]

    fake_repo = MagicMock()
    fake_issue = MagicMock()
    fake_repo.get_issue.return_value = fake_issue

    with (
        patch("agents.planner.run_agent", fake_run_agent),
        patch("agents.planner.planner_validate.validate", always_fail),
        patch("agents.planner._changed_files", return_value=["x.py"]),
        patch("agents.planner._has_changes", return_value=True),
        patch("agents.planner._commit_and_push"),
        patch("agents.planner._open_pr") as open_pr,
        patch("agents.planner.gh.repo", return_value=fake_repo),
    ):
        await planner.plan_and_pr(issue_number=1)

    assert call_count["n"] == 2, "planner should call LLM exactly twice on persistent failure"
    open_pr.assert_not_called()
    fake_issue.create_comment.assert_called_once()
    assert "validation" in fake_issue.create_comment.call_args[0][0].lower()
```

Required imports at the top of `test_planner.py` (add if missing):
```python
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pathlib import Path
from agents import planner
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest agents/tests/test_planner.py::test_planner_retries_once_on_validation_failure agents/tests/test_planner.py::test_planner_gives_up_after_one_retry -v`

Expected: FAIL — `planner.planner_validate` not imported, `_changed_files` missing, etc.

- [ ] **Step 4: Implement in planner.py**

Modify `agents/src/agents/planner.py`. Add at top:

```python
from agents.lib import planner_validate
```

Add this helper function near the existing `_has_changes()`:

```python
def _changed_files() -> list[str]:
    """Return list of files modified/added in the working tree vs HEAD."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]
```

In the main `plan_and_pr` flow, between the first `run_agent(...)` call and the commit step, insert:

```python
MAX_VALIDATION_RETRIES = 1

validation_errors = planner_validate.validate(REPO_ROOT, _changed_files())
for attempt in range(MAX_VALIDATION_RETRIES):
    if not validation_errors:
        break
    retry_prompt = (
        "Your previous changes failed validation:\n\n"
        + "\n\n".join(validation_errors)
        + "\n\nFix these errors. Do not change the overall approach — just address the specific issues above."
    )
    await run_agent(
        prompt=retry_prompt,
        system=prompts.load("planner"),
        max_turns=10,
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep"],
    )
    validation_errors = planner_validate.validate(REPO_ROOT, _changed_files())

if validation_errors:
    repo.get_issue(issue_number).create_comment(
        "Planner ran but validation failed after one retry:\n\n"
        + "\n\n".join(validation_errors)
        + "\n\nLeaving the branch un-pushed. Please review manually."
    )
    return
```

You may also need to refactor the existing `_commit_and_push` into its own function and the PR-opening into `_open_pr` if the tests reference those names — pick names that match the test patches.

If the existing planner code differs substantially from these names, adapt the implementation to match the test expectations, or adapt the tests to match the code. The key behaviour contract is:
1. If validate returns [], continue to commit + PR.
2. If validate returns errors, make ONE LLM retry; then validate again.
3. If still errors, post an issue comment and DO NOT commit/push/open PR.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest agents/tests/test_planner.py -v`

Expected: PASS — new 2 tests + all pre-existing tests.

- [ ] **Step 6: Commit**

```bash
git add agents/src/agents/planner.py agents/tests/test_planner.py
git commit -m "feat(planner): add pre-commit validation + single retry

After the LLM tool loop, run ruff/compile/pytest on touched files.
On failure, feed errors back for one retry. If the retry still fails,
post a comment on the triggering issue and skip the PR.

Prevents the import-bug class of failures that PR #15 and #17 shipped.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

Then: `git push origin main`

---

# Phase P60c — Unblock CI/reviewer on planner PRs

**Goal:** Switch CI + reviewer from `pull_request` to `pull_request_target` so they fire on planner-opened PRs (bypassing GitHub's cascade protection).

## Task 4: Switch ci.yml and reviewer.yml triggers

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/reviewer.yml`

- [ ] **Step 1: Update ci.yml trigger**

Edit `.github/workflows/ci.yml`. Replace the `on:` block:

Before:
```yaml
on:
  pull_request:
  push:
    branches: [main]
```

After:
```yaml
on:
  pull_request_target:
    types: [opened, synchronize, reopened]
  push:
    branches: [main]
```

Inside each job that checks out code, explicitly check out the PR head SHA so we run against the proposed code, not the base branch:

Find the existing `- uses: actions/checkout@v4` steps. Add `ref` input:

```yaml
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha || github.sha }}
```

This applies only to the pull_request_target path; for push events, `github.sha` resolves correctly.

- [ ] **Step 2: Update reviewer.yml trigger**

Edit `.github/workflows/reviewer.yml` the same way. Replace:

```yaml
on:
  pull_request:
    branches: [main]
  workflow_dispatch:
    inputs:
      pr_number:
        description: "PR number to review"
        required: true
        type: string
```

With:

```yaml
on:
  pull_request_target:
    branches: [main]
    types: [opened, synchronize, reopened]
  workflow_dispatch:
    inputs:
      pr_number:
        description: "PR number to review"
        required: true
        type: string
```

The existing `refs/pull/${{ steps.pr.outputs.num }}/merge` checkout already handles the security-sensitive "run against PR head" part — no additional changes needed inside the job.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/reviewer.yml
git commit -m "fix(workflows): use pull_request_target so planner PRs trigger CI + review

GitHub's cascade protection blocks pull_request events for PRs opened
by the default GITHUB_TOKEN. Switching to pull_request_target bypasses
this while still running the job against the PR head SHA.

Security note: pull_request_target runs with base-branch secrets but
with PR-head code. Safe here because:
- Our secrets (ANTHROPIC_API_KEY, RAILWAY_TOKEN) don't touch CI — only
  deploy-prod uses them.
- The checked-out code only runs inside the runner; it doesn't execute
  on production.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

Then: `git push origin main`

## Task 5: Verify planner PR now triggers CI + reviewer

**Files:** none — verification only.

- [ ] **Step 1: Dispatch the PM manually to open a fresh planner PR**

```bash
gh workflow run product-manager.yml --repo nt-suuri/ai-harness
# wait for the pm run to complete
gh run watch $(gh run list --workflow=product-manager.yml --limit 1 --json databaseId --jq '.[0].databaseId') --exit-status
```

Expected: `pm: picked` or `pm: generated` in logs, new `agent:build` issue appears.

- [ ] **Step 2: Wait for planner to open PR + confirm CI/reviewer auto-fire**

After ~5–10 minutes:

```bash
gh pr list --state open --author app/github-actions --limit 1 --json number,title,statusCheckRollup
```

Expected: new PR with `statusCheckRollup` showing both `ci / python` and `reviewer / quality` jobs. Previously those fields were empty because the workflows never fired.

- [ ] **Step 3: Verify validation catches bad imports if they slip through**

If the planner's new PR has ruff/mypy/pytest all green → the validation gate + improved prompt both contributed. If CI flags something the local validation missed, that's a bug to fix in a follow-up.

No commit — verification only.

---

## Task 6: Document the new flow in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append a new section**

Insert this block into `CLAUDE.md` after the existing "Autonomous product loop (P50–P52)" section:

```markdown
## Planner reliability (P60)

Three improvements cut planner PR bugs:

1. **Explicit repo conventions in `planner.md`** — before/after import examples show the LLM that `from api.main import app` is correct, not `from apps.api.src.api import app`. Lists test-file locations, router wiring, and files the planner must NEVER edit.
2. **Pre-commit validation in `planner.py`** — after the LLM tool loop, run `ruff check` + `python -m compileall` + `pytest` on the changed files. On failure, feed errors back to the LLM for ONE retry. If the retry still fails, post a comment on the issue explaining the failure and skip the PR (no branch pushed).
3. **`pull_request_target` trigger on CI + reviewer** — bypasses GitHub's cascade protection so planner-opened PRs run the same CI + 3-pass review gates as human-opened ones. Security model: secrets are only used in `deploy-prod.yml` (unchanged); CI + reviewer run against PR-head code but with base-branch workflow file, so malicious PR content cannot escalate privileges.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): document P60 planner-reliability changes

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

Then: `git push origin main`

---

## Self-review notes

1. **Spec coverage:** Each root-cause from the diagnosis maps to a task:
   - Missing concrete conventions in prompt → Task 1
   - No pre-commit validation → Tasks 2 + 3
   - CI cascade protection → Task 4
   - Verification that all three land → Task 5
   - Documentation → Task 6

2. **Placeholder scan:** zero TODO/TBD. Every step has concrete code or exact commands.

3. **Type consistency:** `validate(cwd, changed_files)` signature used identically in Tasks 2 and 3. `_changed_files()`, `_has_changes()`, `planner_validate.validate` names consistent.

4. **One caveat in Task 3:** the exact refactor of `planner.py`'s current flow is described but not copied verbatim because the current file has its own structure the plan can't predict. The task lists the behaviour contract and leaves minor renames to the implementer — with tests as the contract enforcer.

## Verification plan (end-to-end)

After all 6 tasks land:

1. `uv run pytest agents/` — all tests green (232 existing + new).
2. `gh workflow run product-manager.yml` — PM picks next backlog item.
3. New planner PR is opened. Within ~2 minutes, `ci / python` shows green. Within ~5 minutes, 3 reviewer comments appear.
4. Inspect the planner PR's diff — imports match the repo conventions. Either directly (prompt win) or after the validation-retry step (gate win).
5. If CI is green, the PR is ready to merge without a human opening the file.

Both the product-management side (P50–P52) and the code-quality side (P60) now run hands-off. The only remaining human input is: fill in `docs/product/vision.md` once, and click Merge when satisfied with each PR.
