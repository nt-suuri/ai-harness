# ai-harness — Phase 3: 3-Pass PR Reviewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every PR to `main` gets reviewed by Claude Opus 4.6 in three parallel passes (quality, security, deps). Each pass posts a PR comment AND sets a GitHub check run with `success` or `failure`. Branch protection adds these 3 checks to its required list so a rejected pass blocks merge.

**Architecture:** A single `agents/reviewer.py` script takes `--pass {quality|security|deps}` and `--pr <N>`. Fetches the PR diff via `agents.lib.gh`, loads the appropriate prompt via `agents.lib.prompts`, runs the agent via `agents.lib.anthropic.run_agent`, parses a `VERDICT: APPROVED|REJECTED` line from the response, posts a PR comment, creates a commit status. The GH Actions workflow `reviewer.yml` fans out to three parallel jobs on `pull_request` events.

**Tech Stack:** Python 3.12 + claude-agent-sdk + PyGithub + the `agents.lib.*` shared infrastructure from Phase 2. GitHub Actions matrix jobs.

**Working directory for every command:** `/Users/nt-suuri/workspace/lab/ai-harness`.

**Prior state (verified Phase 2 exit):**
- `agents/` workspace member with 5 lib modules (anthropic, gh, sentry, kill_switch, prompts) + 6 stub prompt .md files
- 34 tests green; CI `python / web / e2e / docker` all pass on `112bd21`
- Railway serving `/api/ping` → `pong`
- No PR workflow yet — all commits go direct to main for bootstrap phases

---

## File Structure

```
agents/
├── reviewer.py                         NEW — CLI entrypoint
├── src/agents/lib/prompts/
│   ├── reviewer_quality.md             EXPAND — stub → real prompt
│   ├── reviewer_security.md            EXPAND
│   └── reviewer_deps.md                EXPAND
└── tests/
    └── test_reviewer.py                NEW — unit + integration tests

.github/workflows/
└── reviewer.yml                        NEW — 3 parallel jobs on pull_request

CLAUDE.md                               UPDATE — document 3 new required checks
```

---

## Conventions

- All commands run from repo root.
- Lab permits direct commits/pushes to main. Push via:
  ```bash
  TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
  ```
- Ruff SIM117 is active — use combined `with a, b:` syntax, never nested `with`.
- Never `ruff --fix`; if ruff flags something, fix manually.
- Every task ends with a commit + push.

---

### Task 1: `reviewer.py` skeleton + CLI + dry-run + failing test

**Files:**
- Create: `agents/reviewer.py`
- Create: `agents/tests/test_reviewer.py`

- [ ] **Step 1: Write failing tests**

Create `agents/tests/test_reviewer.py`:
```python
import subprocess

import pytest


def test_reviewer_cli_requires_pass_arg() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.reviewer", "--pr", "1"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "pass" in result.stderr.lower() or "pass" in result.stdout.lower()


def test_reviewer_cli_rejects_unknown_pass() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.reviewer", "--pass", "bogus", "--pr", "1"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


@pytest.mark.parametrize("pass_name", ["quality", "security", "deps"])
def test_reviewer_cli_accepts_valid_pass(pass_name: str) -> None:
    # --dry-run with missing env won't make real API calls; should at least
    # parse CLI args without argparse-level failure.
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.reviewer",
            "--pass", pass_name, "--pr", "1", "--dry-run", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    # --help-check-only is a test-only flag that short-circuits after arg parsing.
    # If argparse rejects the args, we exit 2; if everything parses, we exit 0.
    assert result.returncode == 0, f"stderr: {result.stderr}"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_reviewer.py -v
```
Expected: `ModuleNotFoundError: No module named 'agents.reviewer'`.

- [ ] **Step 3: Implement `reviewer.py` skeleton**

Create `agents/reviewer.py`:
```python
"""3-pass PR reviewer. One invocation = one pass.

Usage:
    python -m agents.reviewer --pass quality --pr 42
    python -m agents.reviewer --pass security --pr 42 --dry-run
"""

import argparse
import asyncio
import sys

from agents.lib import gh, kill_switch, prompts
from agents.lib.anthropic import run_agent

_PASSES = ("quality", "security", "deps")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.reviewer", description=__doc__)
    p.add_argument("--pass", dest="pass_name", choices=_PASSES, required=True)
    p.add_argument("--pr", type=int, required=True, help="Pull request number")
    p.add_argument("--dry-run", action="store_true", help="Print result; skip posting comment/status")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


async def review_pr(pass_name: str, pr_number: int, *, dry_run: bool) -> int:
    """Return 0 if APPROVED, 1 if REJECTED, 2 on internal error."""
    raise NotImplementedError("Task 2 fills this in")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return asyncio.run(review_pr(args.pass_name, args.pr, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_reviewer.py -v
```
Expected: 5 passed (2 rejection tests + 3 parametrized valid-pass tests).

- [ ] **Step 5: Lint + typecheck**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run ruff check agents
uv run mypy agents/src agents/reviewer.py
```

Note: `agents/reviewer.py` is at the workspace-member root, not inside `src/agents/`. It's an entrypoint script, imported as `agents.reviewer` via the workspace's `-m` flag. Mypy will need to check it explicitly.

If mypy complains about `raise NotImplementedError` in the typed `async def`, that's fine — function still returns `int` via the `raise`.

- [ ] **Step 6: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/reviewer.py agents/tests/test_reviewer.py
git commit -m "feat(agents): reviewer.py CLI skeleton (Task 1)"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 2: Implement `review_pr()` — fetch diff, run agent, parse verdict

**Files:**
- Modify: `agents/reviewer.py` (replace the `NotImplementedError`)
- Modify: `agents/tests/test_reviewer.py` (add 4 unit tests for `review_pr`)

- [ ] **Step 1: Write the failing tests**

Append to `agents/tests/test_reviewer.py`:
```python
from unittest.mock import AsyncMock, MagicMock, patch

from agents.reviewer import _extract_verdict, review_pr


def test_extract_verdict_approved() -> None:
    body = "Lots of analysis here.\n\nVERDICT: APPROVED"
    assert _extract_verdict(body) == "success"


def test_extract_verdict_rejected() -> None:
    body = "Found a bug.\n\nVERDICT: REJECTED"
    assert _extract_verdict(body) == "failure"


def test_extract_verdict_missing_defaults_failure() -> None:
    # No verdict line → treat as failure (conservative; force the agent to be explicit)
    body = "I reviewed but forgot to say a verdict."
    assert _extract_verdict(body) == "failure"


@pytest.mark.asyncio
async def test_review_pr_dry_run_returns_rc_from_verdict() -> None:
    fake_repo = MagicMock()
    fake_pr = MagicMock()
    fake_pr.title = "Test PR"
    fake_pr.patch = "diff --git a/x b/x\n+hello"
    fake_repo.get_pull.return_value = fake_pr

    with (
        patch("agents.reviewer.gh.repo", return_value=fake_repo),
        patch("agents.reviewer.prompts.load", return_value="You are quality reviewer"),
        patch("agents.reviewer.run_agent", new=AsyncMock()) as mock_run,
    ):
        mock_run.return_value = MagicMock(
            messages=[
                {"type": "text", "text": "Analysis.\n\nVERDICT: APPROVED"},
            ],
            stopped_reason="complete",
        )
        rc = await review_pr("quality", 42, dry_run=True)

    assert rc == 0
    fake_repo.get_pull.assert_called_once_with(42)
    fake_pr.create_issue_comment.assert_not_called()  # dry-run suppresses side effects


@pytest.mark.asyncio
async def test_review_pr_live_posts_comment_and_sets_status() -> None:
    fake_repo = MagicMock()
    fake_pr = MagicMock()
    fake_pr.title = "Test PR"
    fake_pr.patch = "diff"
    fake_pr.head.sha = "abc123"
    fake_repo.get_pull.return_value = fake_pr

    with (
        patch("agents.reviewer.gh.repo", return_value=fake_repo),
        patch("agents.reviewer.prompts.load", return_value="sys"),
        patch("agents.reviewer.run_agent", new=AsyncMock()) as mock_run,
    ):
        mock_run.return_value = MagicMock(
            messages=[{"type": "text", "text": "problem.\n\nVERDICT: REJECTED"}],
            stopped_reason="complete",
        )
        rc = await review_pr("security", 7, dry_run=False)

    assert rc == 1
    fake_pr.create_issue_comment.assert_called_once()
    comment = fake_pr.create_issue_comment.call_args.args[0]
    assert "security" in comment.lower()
    fake_repo.get_commit.assert_called_once_with("abc123")
    status_call = fake_repo.get_commit.return_value.create_status.call_args
    assert status_call.kwargs["state"] == "failure"
    assert status_call.kwargs["context"] == "reviewer / security"
```

- [ ] **Step 2: Run — expect some FAIL (review_pr still raises NotImplementedError)**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_reviewer.py -v
```

- [ ] **Step 3: Implement the core logic**

Edit `/Users/nt-suuri/workspace/lab/ai-harness/agents/reviewer.py`. Replace the `review_pr` stub with:

```python
async def review_pr(pass_name: str, pr_number: int, *, dry_run: bool) -> int:
    """Return 0 if APPROVED, 1 if REJECTED."""
    repo = gh.repo()
    pr = repo.get_pull(pr_number)
    diff = pr.patch or ""
    system = prompts.load(f"reviewer_{pass_name}")
    user = (
        f"Review PR #{pr_number} titled: {pr.title}\n\n"
        f"Diff:\n```diff\n{diff}\n```\n\n"
        f"End your response with exactly one line: `VERDICT: APPROVED` or `VERDICT: REJECTED`."
    )
    result = await run_agent(
        prompt=user,
        system=system,
        max_turns=20,
        allowed_tools=[],
    )
    body = _extract_text(result.messages)
    state = _extract_verdict(body)
    comment = f"**Claude review — {pass_name}**\n\n{body}"

    if dry_run:
        print(f"--- DRY RUN [{pass_name}] rc={0 if state == 'success' else 1} ---")
        print(comment)
        return 0 if state == "success" else 1

    pr.create_issue_comment(comment)
    repo.get_commit(pr.head.sha).create_status(
        state=state,
        target_url="",
        description=f"Claude {pass_name} review",
        context=f"reviewer / {pass_name}",
    )
    return 0 if state == "success" else 1


def _extract_text(messages: list) -> str:
    """Join all text-type messages into a single body."""
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


def _extract_verdict(body: str) -> str:
    """Return 'success' if body ends with 'VERDICT: APPROVED', else 'failure'."""
    for line in reversed(body.splitlines()):
        line = line.strip()
        if line.startswith("VERDICT:"):
            return "success" if "APPROVED" in line.upper() else "failure"
    return "failure"
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_reviewer.py -v
```
Expected: 9 passed (5 CLI + 3 verdict parsers + 1 dry-run integration + 1 live integration = 10. Count the real output).

Actual expected count: 5 (Task 1) + 5 (this task: 3 verdict + 2 async integration) = 10 passed.

- [ ] **Step 5: Lint + typecheck**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run ruff check agents
uv run mypy agents/src agents/reviewer.py
```

If mypy complains about the `messages: list` parameter being too loose, annotate as `list[Any]`.

- [ ] **Step 6: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/reviewer.py agents/tests/test_reviewer.py
git commit -m "feat(agents): reviewer.py review_pr() with verdict parsing"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 3: Fill in `reviewer_quality.md`

**Files:**
- Modify: `agents/src/agents/lib/prompts/reviewer_quality.md`

- [ ] **Step 1: Replace the stub contents**

Open `/Users/nt-suuri/workspace/lab/ai-harness/agents/src/agents/lib/prompts/reviewer_quality.md` (currently a 3-line stub). Replace with:

```
# PR quality reviewer

You review pull requests on the ai-harness monorepo for code quality issues that actually matter.

## Scope

- Logic errors that produce wrong behavior
- Obvious performance regressions (O(n²) where O(n) exists, N+1 queries, unnecessary allocations in hot paths)
- Missing error handling on new code paths that can fail
- Dead code, unreachable branches, obvious duplication
- Bad naming that will mislead future readers
- Tests that mock too much and verify too little

## Out of scope

- Style preferences already enforced by ruff/mypy/tsc (auto-fixes run in CI)
- Bikeshedding (prefer-tabs-over-spaces, one-liner-vs-expanded)
- Suggestions that are hypothetical refactors unrelated to the diff

## Process

1. Read the PR title and full diff carefully.
2. Identify concrete issues. Cite `file:line` when possible.
3. Classify each: **Critical** (breaks something), **Important** (should fix before merge), **Minor** (polish; optional).
4. If the code is clean, say so briefly. Don't invent issues to look thorough.

## Output format

```
## Summary
[One paragraph.]

## Findings

### [Critical | Important | Minor] `path/to/file.py:123`
[1-2 sentences: what's wrong, what to do.]

...
```

Then, on the final line (no trailing prose):

- `VERDICT: APPROVED` — no Critical or Important issues found
- `VERDICT: REJECTED` — at least one Critical or Important issue

If in doubt, REJECT. Humans override with the PR approval.
```

- [ ] **Step 2: Verify prompts.load() still works**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_prompts.py -v
```
Expected: 3 passed (the stub expansion doesn't change the test contract).

- [ ] **Step 3: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/lib/prompts/reviewer_quality.md
git commit -m "feat(prompts): fill in reviewer_quality.md"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 4: Fill in `reviewer_security.md`

**Files:**
- Modify: `agents/src/agents/lib/prompts/reviewer_security.md`

- [ ] **Step 1: Replace**

Replace `/Users/nt-suuri/workspace/lab/ai-harness/agents/src/agents/lib/prompts/reviewer_security.md` with:

```
# PR security reviewer

You review pull requests on the ai-harness monorepo for security risks.

## In scope

- **Injection**: SQL, NoSQL, command, XSS, CSRF, SSRF, XXE
- **Secrets**: hardcoded tokens, API keys, credentials in diffs (even in test fixtures)
- **Auth boundaries**: new endpoints without auth, auth bypassed by a code path, privilege escalation
- **Input validation**: untrusted user input reaching filesystem/shell/DB
- **Deserialization**: `pickle.loads`, `yaml.load` (unsafe), eval, exec on inputs
- **CORS / headers**: overly permissive origins, missing security headers
- **Supply chain**: new dependency from an untrusted source, typosquatted names

## Out of scope

- Theoretical attacks with no realistic threat model for this app
- Generic "you should use HTTPS" comments when the repo already runs HTTPS via Railway
- Style / performance (other reviewers cover those)

## Process

1. Read the PR diff.
2. List concrete security concerns. Cite `file:line`.
3. Classify: **Critical** (exploitable today), **Important** (exploitable later / defense-in-depth failure), **Minor**.
4. If the diff has no security-relevant changes, say that and APPROVE.

## Output format

Same format as the quality reviewer: `## Summary`, `## Findings` with cited file:line, then a single final `VERDICT:` line.

- `VERDICT: APPROVED` — zero Critical, zero Important
- `VERDICT: REJECTED` — any Critical or Important

Err on the side of REJECTED for anything touching auth, secrets, or user input.
```

- [ ] **Step 2: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/lib/prompts/reviewer_security.md
git commit -m "feat(prompts): fill in reviewer_security.md"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 5: Fill in `reviewer_deps.md`

**Files:**
- Modify: `agents/src/agents/lib/prompts/reviewer_deps.md`

- [ ] **Step 1: Replace**

Replace `/Users/nt-suuri/workspace/lab/ai-harness/agents/src/agents/lib/prompts/reviewer_deps.md` with:

```
# PR dependency reviewer

You review pull requests on the ai-harness monorepo for dependency changes (Python `pyproject.toml` and JS `package.json`).

## Trigger

Act only if the diff touches:
- `pyproject.toml` (root or any workspace member)
- `apps/api/pyproject.toml`, `agents/pyproject.toml`
- `package.json` (root or `apps/web/package.json`)
- `uv.lock`, `pnpm-lock.yaml`

If the diff touches NONE of these, your review is:
```
## Summary

No dependency changes in this PR.

VERDICT: APPROVED
```

## In scope (when dep changes exist)

- New package with suspicious name (typosquat: `requests2`, `pylnx`, etc.)
- Package with recent install count spike or sole-maintainer risk
- License changes: GPL → non-GPL switches, license becoming stricter
- Version floors that allow known CVEs (e.g. `requests<2.32`)
- Downgrades of production deps without explanation
- Lockfile updates that silently bump unrelated transitive packages (>20 at once)

## Out of scope

- Style of how deps are declared (toml formatting etc.)
- Suggesting alternative libraries (not your job)

## Process

1. List dep changes added / removed / bumped / downgraded.
2. For each, assess risk: **Critical** (known CVE, untrusted source), **Important** (license change, major version bump with no migration notes), **Minor** (minor version bumps).
3. If no changes → trivially APPROVED.

## Output

Same format. Final line: `VERDICT: APPROVED` or `VERDICT: REJECTED`.
```

- [ ] **Step 2: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/lib/prompts/reviewer_deps.md
git commit -m "feat(prompts): fill in reviewer_deps.md"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 6: `reviewer.yml` GH Actions workflow

**Files:**
- Create: `.github/workflows/reviewer.yml`

- [ ] **Step 1: Write the workflow**

Create `/Users/nt-suuri/workspace/lab/ai-harness/.github/workflows/reviewer.yml`:

```yaml
name: reviewer

on:
  pull_request:
    branches: [main]

concurrency:
  group: reviewer-${{ github.event.pull_request.number }}
  cancel-in-progress: true

permissions:
  contents: read
  pull-requests: write
  statuses: write

jobs:
  review:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        pass: [quality, security, deps]
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
            echo "PAUSE_AGENTS=true — skipping reviewer"
            exit 0
          fi
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --group dev --all-packages --frozen
      - run: uv run python -m agents.reviewer --pass ${{ matrix.pass }} --pr ${{ github.event.pull_request.number }}
```

Note the three job names that will become required check contexts:
- `reviewer / review (quality)`
- `reviewer / review (security)`
- `reviewer / review (deps)`

(GitHub uses `<workflow-name> / <job-name> (<matrix-value>)` as the context by default.)

- [ ] **Step 2: Verify yaml parses**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run --with pyyaml python -c "import yaml; d = yaml.safe_load(open('.github/workflows/reviewer.yml')); print('jobs:', list(d['jobs'].keys()))"
```
Expected: `jobs: ['review']`.

- [ ] **Step 3: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add .github/workflows/reviewer.yml
git commit -m "ci: add reviewer workflow with 3-pass matrix"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 7: Set `ANTHROPIC_API_KEY` secret + add 3 new required checks to branch protection

**Manual note:** `ANTHROPIC_API_KEY` needs a real API key. If the controller/user doesn't have one ready, STOP and ask for it.

- [ ] **Step 1: Set the Anthropic secret**

The human provides an API key starting with `sk-ant-`. Run:
```bash
gh secret set ANTHROPIC_API_KEY --repo nt-suuri/ai-harness --body "<paste key>"
gh secret list --repo nt-suuri/ai-harness
```

Expected: `ANTHROPIC_API_KEY` appears in the list with an updated timestamp. Don't echo the key.

- [ ] **Step 2: Open a trivial test PR to trigger the reviewer workflow**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git checkout -b chore/test-reviewer
echo "" >> CLAUDE.md  # one-byte change to trigger CI
git add CLAUDE.md
git commit -m "chore: test reviewer workflow"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" chore/test-reviewer
gh pr create --base main --head chore/test-reviewer --title "Test reviewer workflow" --body "Trivial PR to register reviewer check contexts on GitHub."
```

Capture the PR number.

- [ ] **Step 3: Wait for reviewer workflow to run (one iteration OK, even if it fails)**

```bash
PR=<captured PR number>
sleep 30
gh run list --workflow=reviewer.yml --limit 3
```

Each of the three matrix jobs should appear. Wait for them to complete (or timeout — not critical that they succeed on this throwaway PR; we just need the check contexts to exist on GitHub).

- [ ] **Step 4: Update branch protection to require the 3 reviewer checks**

```bash
gh api -X PUT "repos/nt-suuri/ai-harness/branches/main/protection" \
  -f required_status_checks[strict]=true \
  -F 'required_status_checks[contexts][]=ci / python' \
  -F 'required_status_checks[contexts][]=ci / web' \
  -F 'required_status_checks[contexts][]=ci / e2e' \
  -F 'required_status_checks[contexts][]=ci / docker' \
  -F 'required_status_checks[contexts][]=reviewer / review (quality)' \
  -F 'required_status_checks[contexts][]=reviewer / review (security)' \
  -F 'required_status_checks[contexts][]=reviewer / review (deps)' \
  -F enforce_admins=false \
  -F required_pull_request_reviews[required_approving_review_count]=1 \
  -F required_pull_request_reviews[dismiss_stale_reviews]=false \
  -F required_pull_request_reviews[require_code_owner_reviews]=false \
  -f restrictions= \
  -F allow_force_pushes=false \
  -F allow_deletions=false
```

Verify:
```bash
gh api repos/nt-suuri/ai-harness/branches/main/protection -q '.required_status_checks.contexts'
```
Expected: 7 contexts total.

- [ ] **Step 5: Clean up the test PR**

Close without merging (the commit added nothing real):
```bash
gh pr close <PR>
git checkout main
git branch -D chore/test-reviewer
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" --delete chore/test-reviewer || true
```

---

### Task 8: Update `CLAUDE.md` to document the new required checks

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Edit the Branch protection section**

Open `/Users/nt-suuri/workspace/lab/ai-harness/CLAUDE.md`. Find:
```
- Required checks: `ci / python`, `ci / web`, `ci / e2e`, `ci / docker`.
- Phase 3 will add `reviewer / quality`, `reviewer / security`, `reviewer / deps`.
```

Replace with:
```
- Required checks: `ci / python`, `ci / web`, `ci / e2e`, `ci / docker`, `reviewer / review (quality)`, `reviewer / review (security)`, `reviewer / review (deps)`.
```

- [ ] **Step 2: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add CLAUDE.md
git commit -m "docs(repo): update required checks for Phase 3"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 9: E2E verification — open a real PR and watch all 3 reviewer jobs run

- [ ] **Step 1: Open a small real PR**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git checkout -b feat/phase-3-smoke
# Make a trivial but legitimate change — tighten one comment
sed -i.bak 's/Phase 1: foundation\./Phase 1 (foundation) shipped 2026-04-14./' apps/web/src/App.tsx
rm apps/web/src/App.tsx.bak
git add apps/web/src/App.tsx
git commit -m "chore(web): tighten foundation copy"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" feat/phase-3-smoke
gh pr create --base main --head feat/phase-3-smoke --title "Phase 3 smoke: tighten copy" --body "Sanity PR to exercise the 3-pass reviewer."
```

Capture the PR URL + number.

- [ ] **Step 2: Watch the reviewer workflow complete**

```bash
PR=<captured>
sleep 30
gh run list --workflow=reviewer.yml --limit 3
# Poll up to 10 × 30s for all 3 jobs to finish
for i in $(seq 1 10); do
  STATUS=$(gh pr checks $PR --json name,status,conclusion -q '[.[] | select(.name | startswith("reviewer")) | .conclusion] | join(",")')
  echo "attempt $i: reviewer checks = $STATUS"
  if echo "$STATUS" | grep -v "," | grep -v "null" > /dev/null; then
    : # any non-null conclusion means at least one job finished
  fi
  if [ $(gh pr checks $PR --json name,conclusion -q '[.[] | select(.name | startswith("reviewer")) | .conclusion] | length') -ge 3 ]; then
    ALL_DONE=$(gh pr checks $PR --json name,conclusion -q '[.[] | select(.name | startswith("reviewer")) | .conclusion] | all(. != null)')
    if [ "$ALL_DONE" = "true" ]; then break; fi
  fi
  sleep 30
done
gh pr checks $PR
```

Verify all three `reviewer / review (quality|security|deps)` checks appear with conclusions. Expected: all APPROVED on a trivial copy tweak (a trivial change should not trip quality/security/deps concerns).

- [ ] **Step 3: Verify Claude posted 3 PR comments**

```bash
gh pr view $PR --comments | head -80
```
Expected: 3 comments from the bot, each headed `**Claude review — <pass>**`.

- [ ] **Step 4: Merge or close**

If everything is clean and the reviewers approved, merge:
```bash
gh pr merge $PR --squash --delete-branch
```

If any unexpected failures, leave the PR open and investigate. Do NOT force-merge with failing reviewer checks — that defeats the purpose.

- [ ] **Step 5: Confirm main is still deploy-green after merge**

```bash
sleep 15
gh run list --workflow=deploy.yml --limit 1
```

Deploy workflow should run on the merge, succeed, and Railway should reflect the new copy. Verify:
```bash
sleep 120
curl -sS https://ai-harness-production.up.railway.app/ | grep -io 'phase 1[^<]*' | head -1
```
Expected: `Phase 1 (foundation) shipped 2026-04-14.`

---

## Phase 3 exit checklist

- [ ] `uv run pytest apps/api agents` passes (34 + 10 new reviewer tests = 44)
- [ ] `uv run mypy apps/api/src agents/src agents/reviewer.py` exits 0
- [ ] `uv run ruff check .` passes
- [ ] `agents/reviewer.py` exists and runs via `python -m agents.reviewer`
- [ ] 3 real review prompts (quality, security, deps) replace the Phase 2 stubs
- [ ] `.github/workflows/reviewer.yml` runs 3 parallel jobs on every PR
- [ ] `ANTHROPIC_API_KEY` secret set
- [ ] Branch protection requires the 3 new reviewer contexts
- [ ] A real PR has been reviewed by all 3 passes, merged, and the change is deployed live
- [ ] `CLAUDE.md` updated

## Out of scope (deferred to later phases)

| Feature | Phase |
|---|---|
| Planner agent (`agent:build` → PR) | 4 |
| Auto-rollback + circuit breaker | 5 |
| Triager + self-healing loop | 6 |
| Healthcheck + email digest | 7 |
| Canary replay harness | 7 |
| Per-pass cost dashboards | TBD |
| Allowed-tools whitelist per reviewer pass (Read diff only) | TBD — deferred for ergonomics |

## Self-review notes

- `_extract_verdict()` defaults to `"failure"` when no VERDICT line — intentional. Forces agents to be explicit; we'd rather over-reject than silently pass.
- `review_pr()` uses `pr.patch` (PyGithub attribute) — may return None for huge diffs; the `or ""` handles that gracefully.
- The `concurrency.group: reviewer-${{ github.event.pull_request.number }}` with `cancel-in-progress: true` means a new commit on a PR cancels any in-flight review and starts fresh. Saves tokens.
- `allowed_tools=[]` in `run_agent` — reviewer agents should NOT invoke tools; they just read + opine. Matches the "write-scoped token per workflow" principle from the master spec.
- The workflow's `permissions` block gives `pull-requests: write` (for comment) + `statuses: write` (for check run) and nothing else — minimal blast radius.
- Task 7 is manual-ish because it requires an `ANTHROPIC_API_KEY` that only the human has. If the user already set it as a repo secret earlier, Step 1 becomes a no-op.
