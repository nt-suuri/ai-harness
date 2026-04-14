# ai-harness — Phase 8: AI-Generated Release Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** After every successful deploy to `main`, an agent reads the new commits since the last release, writes user-facing release notes via Claude Sonnet 4.6, prepends them to `RELEASES.md`, creates a GitHub Release tagged with the deploy commit, and (optionally) posts the release summary as a comment on closed issues that landed in this batch.

**Why this phase:** Master spec calls for AI-native ops across "every function". The most valuable beyond-engineering piece for a solo lab is automated release notes — it's user-facing, runs on existing infra (no third-party social accounts to configure), and turns the firehose of merge commits into something readable.

**Scope cuts vs. master spec:**
- ❌ Daily social posts (no Twitter/Bluesky account configured for this lab)
- ❌ Feature intro videos (way out of scope for MVP)
- ❌ Marketing summaries (no audience)
- ✅ Release notes — concrete, useful, reuses gh + anthropic infra

**Architecture:** `agents/src/agents/release_notes.py` is a CLI (`--since-tag <prev>`, `--dry-run`). It:
1. Reads commits between the last release tag and `HEAD` via PyGithub
2. Filters out housekeeping commits (chore/docs/ci unless flagged)
3. Asks Claude Sonnet 4.6 to write a structured release-notes blob
4. Prepends to `RELEASES.md` and commits the change to main directly
5. Creates a GH Release with the same content

`.github/workflows/release-notes.yml` runs on `workflow_run` of `deploy` succeeded.

**Tech Stack:** Python 3.12, claude-agent-sdk (Sonnet 4.6 — release notes don't need Opus), PyGithub, `agents.lib.*` shared infra.

**Working directory:** `/Users/nt-suuri/workspace/lab/ai-harness`.

**Prior state (Phase 7 complete at `4a190f4`):** 97 tests, 17 source files, 8 workflows. Master spec exit reached.

---

## File Structure

```
agents/src/agents/
├── release_notes.py                    NEW — CLI + run_release_notes()
└── lib/prompts/
    └── release_notes.md                NEW — system prompt for the agent

agents/tests/
└── test_release_notes.py               NEW

.github/workflows/
└── release-notes.yml                   NEW — on: workflow_run deploy succeeded

RELEASES.md                             NEW — initial empty/seeded changelog
CLAUDE.md                               UPDATE
```

---

## Conventions

- All commands from repo root.
- Direct commits/pushes to main permitted.
- Push: `TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main`
- SIM117 active; no `ruff --fix`.

---

### Task 1: Add `release_notes` system prompt

**Files:**
- Create: `agents/src/agents/lib/prompts/release_notes.md`

- [ ] **Step 1: Write the prompt**

Create `agents/src/agents/lib/prompts/release_notes.md`:

```
# Release notes writer

You are the release-notes writer for the ai-harness repository. You read a list of commits and write user-facing release notes.

## Input

You'll receive:
- A target version tag (e.g. `v2026.04.14-1742`)
- A list of commit SHAs + subjects + bodies between the previous release and HEAD

## Output (strict format)

```markdown
## <version-tag> — <YYYY-MM-DD>

### Highlights
- Bullet point per genuinely user-visible change. 1 line each. Plain English.

### Fixes
- Bullet point per bugfix. Cite issue # if mentioned in commit body.

### Internal
- Brief catch-all for housekeeping (deps, CI, refactor, docs). Group by topic, don't list each commit.
```

## Rules

1. **No marketing fluff.** No "exciting", "powerful", "blazing fast". Just what changed.
2. **One line per bullet.** Compress. If a feature touched 4 files, that's still one bullet.
3. **Group housekeeping.** "Updated 3 dev dependencies" beats listing each commit.
4. **Skip empty sections.** If there are no fixes, omit the `### Fixes` heading.
5. **Verbs in past tense.** "Added X", "Fixed Y", not "Adds" or "Fixing".
6. **Cite issues only when commit body says `Closes #N` or `Fixes #N`.** Don't invent links.
7. **No commit SHAs in the output.** Users don't care.

## What is "user-facing"?

- New API endpoints, new UI features, new CLI flags → Highlights
- Fixed bugs that affected a real user path → Fixes
- Refactors, dep bumps, CI tweaks, internal lint fixes, doc updates → Internal

If a "feat:" commit only touches infrastructure with no end-user effect, demote to Internal.
```

- [ ] **Step 2: Verify prompts.list_prompts() picks it up**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run python -c "from agents.lib import prompts; print(prompts.list_prompts())"
```

Expected: list now includes `release_notes` alphabetically among the existing 6.

Update `test_prompts.py` if it has a strict count assertion. Look at the existing test:

```python
def test_list_prompts_returns_sorted_known_names() -> None:
    names = prompts.list_prompts()
    assert names == sorted(names)
    assert "planner" in names
    ...
```

The existing test only asserts membership of specific names, not total count — no edit needed. Verify by running:

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_prompts.py -v
```

Expected: 3 passed (unchanged).

- [ ] **Step 3: Commit + push**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
git add agents/src/agents/lib/prompts/release_notes.md
git commit -m "feat(prompts): add release_notes system prompt"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 2: `release_notes.py` skeleton + 3 CLI tests

**Files:**
- Create: `agents/src/agents/release_notes.py`
- Create: `agents/tests/test_release_notes.py`

- [ ] **Step 1: Failing tests**

Create `agents/tests/test_release_notes.py`:

```python
import subprocess

import pytest


def test_release_notes_cli_runs_with_dry_run() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.release_notes", "--dry-run", "--help-check-only"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_release_notes_cli_accepts_since_tag() -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.release_notes",
            "--since-tag", "v2026.04.13-0900", "--dry-run", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


@pytest.mark.parametrize("flag", ["--dry-run", ""])
def test_release_notes_cli_accepts_dry_run_flag_optional(flag: str) -> None:
    args = ["uv", "run", "python", "-m", "agents.release_notes", "--help-check-only"]
    if flag:
        args.append(flag)
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode == 0
```

- [ ] **Step 2: Implement skeleton**

Create `agents/src/agents/release_notes.py`:

```python
"""Release-notes generator. Reads commits since last tag, asks Claude to write notes.

Usage:
    python -m agents.release_notes
    python -m agents.release_notes --since-tag v2026.04.13-0900 --dry-run
"""

import argparse
import asyncio
import sys

from agents.lib import kill_switch


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.release_notes", description=__doc__)
    p.add_argument("--since-tag", help="Previous release tag (default: most recent tag, or all of HEAD)")
    p.add_argument("--dry-run", action="store_true", help="Print notes; skip RELEASES.md write + GH release")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


async def generate_release_notes(*, since_tag: str | None, dry_run: bool) -> int:
    """Return 0 on success, 1 on no-commits-since-last-tag, 2 on internal error."""
    raise NotImplementedError("Task 3 fills this in")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return asyncio.run(generate_release_notes(since_tag=args.since_tag, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Test + commit**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_release_notes.py -v
uv run ruff check agents
uv run mypy agents/src
git add agents/src/agents/release_notes.py agents/tests/test_release_notes.py
git commit -m "feat(agents): release_notes.py CLI skeleton"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

Expected: 3 passed (one parametrize collapses to 2 actual tests since one is empty-flag).

---

### Task 3: Implement `generate_release_notes()`

**Files:**
- Modify: `agents/src/agents/release_notes.py`
- Modify: `agents/tests/test_release_notes.py`
- Create: `RELEASES.md` (seed)

Logic:
1. Find the most recent git tag (or use `--since-tag`). If no tag exists, use first commit on main.
2. List commits between that tag and HEAD via `git log --oneline --no-merges <prev>..HEAD`.
3. If empty → return 1 (nothing to release).
4. Generate next tag: `v{YYYY.MM.DD}-{HHMM}` based on now in UTC.
5. Ask Claude with the release_notes prompt + the commit list.
6. Parse the agent's response (the markdown body).
7. Prepend to `RELEASES.md` (or create file if missing).
8. Commit the file change to main directly.
9. Create a GH Release tagged at the next version, body = notes.
10. Push.

- [ ] **Step 1: Append tests**

Append to `agents/tests/test_release_notes.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

from agents.release_notes import (
    _build_user_prompt,
    _format_release_block,
    _next_tag,
    generate_release_notes,
)


def test_next_tag_format() -> None:
    from datetime import UTC, datetime

    tag = _next_tag(datetime(2026, 4, 14, 17, 42, tzinfo=UTC))
    assert tag == "v2026.04.14-1742"


def test_build_user_prompt_includes_target_and_commits() -> None:
    commits = [
        ("abc1234", "feat(api): add /health"),
        ("def5678", "fix(web): nav bug"),
    ]
    prompt = _build_user_prompt(target_tag="v2026.04.14-1742", commits=commits)
    assert "v2026.04.14-1742" in prompt
    assert "feat(api): add /health" in prompt
    assert "fix(web): nav bug" in prompt
    assert "abc1234" in prompt or "abc" in prompt


def test_format_release_block_strips_then_returns() -> None:
    raw = "  ## v1 — 2026-04-14\n\n### Highlights\n- thing\n  "
    block = _format_release_block(raw)
    assert block.startswith("## v1")
    assert block.endswith("- thing")


@pytest.mark.asyncio
async def test_generate_release_notes_returns_1_when_no_commits() -> None:
    fake_repo = MagicMock()
    fake_repo.compare.return_value = MagicMock(commits=[])
    with (
        patch("agents.release_notes.gh.repo", return_value=fake_repo),
        patch("agents.release_notes._latest_tag", return_value="v2026.04.13-0000"),
    ):
        rc = await generate_release_notes(since_tag=None, dry_run=False)
    assert rc == 1


@pytest.mark.asyncio
async def test_generate_release_notes_dry_run_skips_writes() -> None:
    fake_repo = MagicMock()
    fake_repo.compare.return_value = MagicMock(
        commits=[
            MagicMock(sha="abc1234", commit=MagicMock(message="feat: new thing")),
        ],
    )
    with (
        patch("agents.release_notes.gh.repo", return_value=fake_repo),
        patch("agents.release_notes._latest_tag", return_value="v2026.04.13-0000"),
        patch("agents.release_notes.prompts.load", return_value="sys"),
        patch("agents.release_notes.run_agent", new=AsyncMock()) as mock_run,
        patch("agents.release_notes._write_releases_md") as write_md,
        patch("agents.release_notes._run_git") as gitcmd,
    ):
        mock_run.return_value = MagicMock(
            messages=[{"type": "text", "text": "## v1 — 2026-04-14\n\n### Highlights\n- new thing"}],
            stopped_reason="complete",
        )
        rc = await generate_release_notes(since_tag=None, dry_run=True)

    assert rc == 0
    write_md.assert_not_called()
    gitcmd.assert_not_called()
    fake_repo.create_git_release.assert_not_called()


@pytest.mark.asyncio
async def test_generate_release_notes_writes_and_releases() -> None:
    fake_repo = MagicMock()
    fake_repo.compare.return_value = MagicMock(
        commits=[
            MagicMock(sha="abc1234", commit=MagicMock(message="feat: new thing")),
        ],
    )
    fake_repo.create_git_release.return_value = MagicMock(html_url="https://x/release")

    with (
        patch("agents.release_notes.gh.repo", return_value=fake_repo),
        patch("agents.release_notes._latest_tag", return_value="v2026.04.13-0000"),
        patch("agents.release_notes.prompts.load", return_value="sys"),
        patch("agents.release_notes.run_agent", new=AsyncMock()) as mock_run,
        patch("agents.release_notes._write_releases_md") as write_md,
        patch("agents.release_notes._run_git") as gitcmd,
    ):
        mock_run.return_value = MagicMock(
            messages=[{"type": "text", "text": "## v1 — 2026-04-14\n\n### Highlights\n- new thing"}],
            stopped_reason="complete",
        )
        rc = await generate_release_notes(since_tag=None, dry_run=False)

    assert rc == 0
    write_md.assert_called_once()
    gitcmd.assert_called()  # git add + commit + push
    fake_repo.create_git_release.assert_called_once()
```

- [ ] **Step 2: Implement**

Replace `agents/src/agents/release_notes.py`:

```python
"""Release-notes generator. Reads commits since last tag, asks Claude to write notes.

Usage:
    python -m agents.release_notes
    python -m agents.release_notes --since-tag v2026.04.13-0900 --dry-run
"""

import argparse
import asyncio
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.lib import gh, kill_switch, prompts
from agents.lib.anthropic import run_agent

_RELEASES_FILE = Path(__file__).resolve().parents[3] / "RELEASES.md"
_MAX_TURNS = 20


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.release_notes", description=__doc__)
    p.add_argument("--since-tag", help="Previous release tag (default: most recent tag, or all of HEAD)")
    p.add_argument("--dry-run", action="store_true", help="Print notes; skip RELEASES.md write + GH release")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _next_tag(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return now.strftime("v%Y.%m.%d-%H%M")


def _latest_tag(repo: Any) -> str | None:
    tags = list(repo.get_tags()[:1])
    if not tags:
        return None
    return str(tags[0].name)


def _run_git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _write_releases_md(block: str) -> None:
    existing = _RELEASES_FILE.read_text() if _RELEASES_FILE.exists() else "# Releases\n\n"
    _RELEASES_FILE.write_text(f"# Releases\n\n{block}\n\n{existing.removeprefix('# Releases').lstrip()}".strip() + "\n")


def _build_user_prompt(*, target_tag: str, commits: list[tuple[str, str]]) -> str:
    lines = [
        f"Target tag: {target_tag}",
        f"Date: {datetime.now(UTC).date().isoformat()}",
        "",
        "Commits since last release:",
    ]
    for sha, msg in commits:
        lines.append(f"- {sha[:7]} {msg.splitlines()[0]}")
    lines.append("")
    lines.append("Write the release notes for these commits.")
    return "\n".join(lines)


def _extract_text(messages: list[Any]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


def _format_release_block(raw: str) -> str:
    return raw.strip()


async def generate_release_notes(*, since_tag: str | None, dry_run: bool) -> int:
    """Return 0 on success, 1 if no commits, 2 on internal error."""
    repo = gh.repo()
    prev_tag = since_tag or _latest_tag(repo)
    target_tag = _next_tag()

    if prev_tag:
        comparison = repo.compare(prev_tag, "main")
        commits_raw = list(comparison.commits)
    else:
        # No tag yet — list last 50 commits on main
        commits_raw = list(repo.get_commits(sha="main")[:50])

    if not commits_raw:
        print("No commits since last release; nothing to do", flush=True)
        return 1

    commits = [(c.sha, c.commit.message) for c in commits_raw]

    system = prompts.load("release_notes")
    user = _build_user_prompt(target_tag=target_tag, commits=commits)
    result = await run_agent(
        prompt=user,
        system=system,
        max_turns=_MAX_TURNS,
        allowed_tools=[],
    )
    block = _format_release_block(_extract_text(result.messages))

    if dry_run:
        print(f"--- DRY RUN [target {target_tag}] ---")
        print(block)
        return 0

    _write_releases_md(block)
    _run_git("add", "RELEASES.md")
    _run_git(
        "-c", "user.name=ai-harness-bot",
        "-c", "user.email=ai-harness@local",
        "commit",
        "-m", f"chore(release): {target_tag}",
    )
    _run_git("push")

    release = repo.create_git_release(
        tag=target_tag,
        name=target_tag,
        message=block,
        target_commitish="main",
    )
    print(f"Created release {target_tag}: {release.html_url}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return asyncio.run(generate_release_notes(since_tag=args.since_tag, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Seed `RELEASES.md`**

Create `/Users/nt-suuri/workspace/lab/ai-harness/RELEASES.md`:

```markdown
# Releases

All notable user-facing changes. Auto-generated by `agents/release_notes.py` after each successful deploy.
```

- [ ] **Step 4: Test + commit**

```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run pytest agents/tests/test_release_notes.py -v
uv run ruff check agents
uv run mypy agents/src
git add agents/src/agents/release_notes.py agents/tests/test_release_notes.py RELEASES.md
git commit -m "feat(agents): release_notes.py with Claude-generated CHANGELOG"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

Expected: 9 passed (3 CLI + 3 helper + 3 async).

---

### Task 4: `release-notes.yml` workflow

Create `/Users/nt-suuri/workspace/lab/ai-harness/.github/workflows/release-notes.yml`:

```yaml
name: release-notes

on:
  workflow_run:
    workflows: [deploy]
    types: [completed]
  workflow_dispatch:

permissions:
  contents: write

jobs:
  notes:
    if: github.event_name == 'workflow_dispatch' || (github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.head_branch == 'main')
    runs-on: ubuntu-latest
    timeout-minutes: 10
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
            echo "PAUSE_AGENTS=true — skipping release-notes"
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
      - run: uv run python -m agents.release_notes
```

Verify + commit:
```bash
cd /Users/nt-suuri/workspace/lab/ai-harness
uv run --with pyyaml python -c "
import yaml
d = yaml.safe_load(open('.github/workflows/release-notes.yml'))
print('jobs:', list(d['jobs'].keys()))
print('permissions:', d['permissions'])
"
git add .github/workflows/release-notes.yml
git commit -m "ci: add release-notes workflow on deploy success"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

### Task 5: CLAUDE.md final update

At the bottom of `/Users/nt-suuri/workspace/lab/ai-harness/CLAUDE.md`, append:

```

## Release notes (per deploy)

`release-notes.yml` runs after every successful deploy to main. It:

1. Lists commits since the last release tag
2. Asks Claude Sonnet 4.6 to write structured release notes
3. Prepends them to `RELEASES.md`, commits the file
4. Creates a tagged GitHub Release (`v{YYYY.MM.DD}-{HHMM}`)

Requires `ANTHROPIC_API_KEY` secret. Without it, the workflow will fail at the `run_agent` step (visible in run logs); the previous deploy is not affected.
```

Commit:
```bash
git add CLAUDE.md
git commit -m "docs(repo): document release-notes workflow"
TOKEN=$(gh auth token) && git push "https://${TOKEN}@github.com/nt-suuri/ai-harness.git" main
```

---

## Phase 8 exit checklist

- [ ] `uv run pytest apps/api agents` passes (97 → 106 with 9 release_notes tests)
- [ ] `uv run mypy agents/src` exits 0
- [ ] `uv run ruff check .` passes
- [ ] `agents.release_notes` runs via `python -m`
- [ ] `RELEASES.md` exists at repo root with seed content
- [ ] `.github/workflows/release-notes.yml` exists, fires on deploy.yml success
- [ ] CLAUDE.md final
- [ ] Master spec exit (modulo activation requiring ANTHROPIC_API_KEY)

## Out of scope (Phase 9+)

- Daily social posts (no Twitter/Bluesky/Mastodon configured)
- Marketing summaries (no audience)
- Feature intro motion graphics (way out of scope)
- Slack/Discord webhook posting of release notes
- Auto-link releases to Sentry deploy markers
- Translated release notes (multiple languages)

## Self-review

- Tag format `v{YYYY.MM.DD}-{HHMM}` is unique-per-minute and sortable.
- `_latest_tag` returns None when no tags exist — first run takes "all of HEAD" as the comparison range.
- `_write_releases_md` strips the existing `# Releases` header before re-emitting it, so we always have exactly one top-level heading.
- `dry_run` skips git + GH-release creation — same pattern as other agents.
- Sonnet 4.6 (not Opus) — release notes are summarization, no deep reasoning needed.
- Agent has `allowed_tools=[]` — pure text-in, text-out. No file writes.
- Workflow chains via `workflow_run` after deploy — same pattern as `rollback-watch`.
- `workflow_dispatch` also enabled so the user can manually generate notes for missed deploys.
