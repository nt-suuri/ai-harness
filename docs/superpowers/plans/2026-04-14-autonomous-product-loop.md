# Autonomous Product-Development Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two gaps that keep the harness from shipping product features 24/7: (a) no agent decides what to build next, (b) bug issues require a human to apply `agent:build`.

**Architecture:** Add two new agents — `product_manager` (cron, 3×/day) picks the next feature from a YAML state file and opens a labelled GH issue; `product_analyzer` (post-release) reads shipped commits and updates the state file. Extend `triager` + `deployer` to auto-apply `agent:build` on severity≥important so bugs self-fix.

**Tech Stack:** Python 3.12, GitHub Models (`openai/gpt-4o-mini` via free tier), PyYAML, PyGithub, GitHub Actions (cron + `workflow_run`), pytest.

---

## Context: Why This Change

The user's goal is a loop that runs 3–5× per day without any human typing code or specs: "one product manager agent adds feature spec, another takes the task and implements, another reviews, another deploys, another monitors Sentry, another fixes bugs, another analyzes product and decides next request."

Current state: the chain `planner → reviewer → deploy → rollback-watch → triager` works, but the loop has two manual gates:

1. **Feature intake is human-only** — nobody autonomously files a feature-request issue. The user must paste `gh issue create --label agent:build` each time.
2. **Bug intake is human-gated** — `triager.py:164` and `deployer.py:92` create issues with labels `[bug, autotriage, severity]` but NOT `agent:build`. The issue body literally asks a human to add the label.

This plan closes both gates and adds a feedback agent so the next cycle's priorities reflect the last cycle's releases.

## Scope Check

Three sub-phases, each ships working software on its own:

- **P50** — auto-label bugs. One-file changes in two files, 4 tests, 2 commits. Closes the fixer loop.
- **P51** — Product Manager agent. New module + prompts + seed docs + workflow. Feature loop starts running.
- **P52** — Product Analyzer agent + guardrails. New module + workflow. State file stays current; docs-only loop prevented.

After P50: bug fix loop is 100% hands-off. After P51: feature loop runs 3×/day. After P52: full self-directing product cycle.

## File Structure

### Files created

| Path | Responsibility |
|---|---|
| `agents/src/agents/product_manager.py` | Read state + vision + open issues → pick/generate next feature → open labelled GH issue → mark state.yaml |
| `agents/src/agents/product_analyzer.py` | Read merged commits since last analysis → move shipped items to `shipped`, top up `backlog` → commit state.yaml `[skip ci]` |
| `agents/src/agents/lib/product_state.py` | Load + save `docs/product/state.yaml` atomically; expose read/mutate helpers |
| `agents/src/agents/lib/prompts/product_manager.md` | System prompt for PM agent |
| `agents/src/agents/lib/prompts/product_analyzer.md` | System prompt for analyzer agent |
| `agents/tests/test_product_state.py` | State file load/save/mutate tests |
| `agents/tests/test_product_manager.py` | PM end-to-end with mocked LLM + GH |
| `agents/tests/test_product_analyzer.py` | Analyzer with mocked LLM + GH |
| `docs/product/vision.md` | Human-written product vision. Seed value is intentionally empty — user fills it in once. |
| `docs/product/state.yaml` | Agent-maintained backlog/in-progress/shipped state |
| `.github/workflows/product-manager.yml` | Cron + workflow_dispatch trigger |
| `.github/workflows/product-analyzer.yml` | Triggered by `workflow_run: release-notes` |

### Files modified

| Path | Change |
|---|---|
| `agents/src/agents/triager.py` | Add `agent:build` to the labels list when `sev_label in (CRITICAL, IMPORTANT)` |
| `agents/src/agents/deployer.py` | Add `agent:build` to the regression-issue labels list (all regressions are high-priority by definition) |
| `agents/tests/test_triager.py` | New tests for conditional `agent:build` labelling |
| `agents/tests/test_deployer.py` | New test for `agent:build` on regression issues |
| `.github/workflows/deploy-prod.yml` | `paths-ignore: [docs/product/**]` so analyzer commits don't redeploy |
| `CLAUDE.md` | New "Autonomous product loop" section |
| `pyproject.toml` (root) | Add `pyyaml` to `agents` workspace deps |

---

# Phase P50 — Close the Fixer Loop

**Goal:** Triager and deployer auto-apply `agent:build` so bugs flow straight to the planner without a human.

## Task 1: Conditional auto-label in triager

**Files:**
- Modify: `agents/src/agents/triager.py:164`
- Test: `agents/tests/test_triager.py`

- [ ] **Step 1: Write the failing test**

Open `agents/tests/test_triager.py` and add these tests at the bottom:

```python
def test_critical_sentry_issue_gets_agent_build_label() -> None:
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []
    fake_repo.get_labels.return_value = []
    fake_repo.create_issue.return_value = MagicMock(number=42, html_url="u")

    with (
        patch("agents.triager.gh.repo", return_value=fake_repo),
        patch("agents.triager.sentry.list_issues", return_value=[{
            "id": "abc", "title": "KeyError", "permalink": "p",
            "count": "100", "userCount": "50",
        }]),
        patch("agents.triager._severity_label", return_value=labels.SEVERITY_CRITICAL),
    ):
        triager.triage_run(dry_run=False)

    applied = fake_repo.create_issue.call_args.kwargs["labels"]
    assert labels.AGENT_BUILD in applied
    assert labels.SEVERITY_CRITICAL in applied


def test_minor_sentry_issue_omits_agent_build_label() -> None:
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []
    fake_repo.get_labels.return_value = []
    fake_repo.create_issue.return_value = MagicMock(number=43, html_url="u")

    with (
        patch("agents.triager.gh.repo", return_value=fake_repo),
        patch("agents.triager.sentry.list_issues", return_value=[{
            "id": "xyz", "title": "Typo log", "permalink": "p",
            "count": "2", "userCount": "1",
        }]),
        patch("agents.triager._severity_label", return_value=labels.SEVERITY_MINOR),
    ):
        triager.triage_run(dry_run=False)

    applied = fake_repo.create_issue.call_args.kwargs["labels"]
    assert labels.AGENT_BUILD not in applied
    assert labels.SEVERITY_MINOR in applied
```

Make sure these imports exist at the top of the test file (add any missing):
```python
from unittest.mock import MagicMock, patch
from agents import triager
from agents.lib import labels
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest agents/tests/test_triager.py::test_critical_sentry_issue_gets_agent_build_label agents/tests/test_triager.py::test_minor_sentry_issue_omits_agent_build_label -v`

Expected: FAIL — `AGENT_BUILD` is not in applied labels.

- [ ] **Step 3: Implement the minimal fix**

Edit `agents/src/agents/triager.py` at line 164. Replace the single line:

```python
gh_issue = repo.create_issue(title=title, body=body, labels=[labels.BUG, labels.AUTOTRIAGE, sev_label])
```

With:

```python
issue_labels = [labels.BUG, labels.AUTOTRIAGE, sev_label]
if sev_label in (labels.SEVERITY_CRITICAL, labels.SEVERITY_IMPORTANT):
    issue_labels.append(labels.AGENT_BUILD)
gh_issue = repo.create_issue(title=title, body=body, labels=issue_labels)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest agents/tests/test_triager.py -v`

Expected: PASS on both new tests plus all pre-existing tests in the file.

- [ ] **Step 5: Commit**

```bash
git add agents/src/agents/triager.py agents/tests/test_triager.py
git commit -m "feat(triager): auto-apply agent:build for critical/important bugs

Closes the fixer loop: severity>=important triggers planner directly.
Minor bugs still wait for human review (protects LLM budget).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

## Task 2: Auto-label on regression issues

**Files:**
- Modify: `agents/src/agents/deployer.py:92`
- Test: `agents/tests/test_deployer.py`

- [ ] **Step 1: Write the failing test**

Append to `agents/tests/test_deployer.py`:

```python
def test_regression_issue_gets_agent_build_label() -> None:
    fake_repo = MagicMock()
    fake_repo.create_issue.return_value = MagicMock(number=99, html_url="u")

    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.count_events_since", side_effect=[1, 50]),
        patch.dict(os.environ, {
            "SENTRY_AUTH_TOKEN": "t",
            "SENTRY_ORG_SLUG": "o",
            "SENTRY_PROJECT_SLUG": "p",
        }, clear=True),
    ):
        deployer.watch_post_deploy(after_sha="abc123", window_minutes=10)

    applied = fake_repo.create_issue.call_args.kwargs["labels"]
    assert labels.AGENT_BUILD in applied
    assert labels.REGRESSION in applied
```

Confirm these imports at the top:
```python
import os
from unittest.mock import MagicMock, patch
from agents import deployer
from agents.lib import labels
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest agents/tests/test_deployer.py::test_regression_issue_gets_agent_build_label -v`

Expected: FAIL — `agent:build` not in applied labels.

- [ ] **Step 3: Implement the fix**

Edit `agents/src/agents/deployer.py` at line 92. Replace:

```python
issue = repo.create_issue(title=title, body=body, labels=[labels.REGRESSION, labels.AUTOTRIAGE])
```

With:

```python
issue = repo.create_issue(
    title=title,
    body=body,
    labels=[labels.REGRESSION, labels.AUTOTRIAGE, labels.AGENT_BUILD],
)
```

- [ ] **Step 4: Run all deployer tests**

Run: `uv run pytest agents/tests/test_deployer.py -v`

Expected: PASS on all tests.

- [ ] **Step 5: Commit**

```bash
git add agents/src/agents/deployer.py agents/tests/test_deployer.py
git commit -m "feat(deployer): auto-apply agent:build on regression issues

Regressions are always high-priority by definition — no human gate.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

# Phase P51 — Product Manager Agent

**Goal:** A new agent that runs 3×/day, reads state.yaml + vision.md + currently-open `agent:build` issues, picks (or generates) the next feature, and opens a labelled GH issue.

## Task 3: Seed product docs

**Files:**
- Create: `docs/product/vision.md`
- Create: `docs/product/state.yaml`

- [ ] **Step 1: Create the vision seed**

Write `docs/product/vision.md`:

```markdown
# Product Vision

> **Fill this in once, rarely update.** The Product Manager agent reads this file on every run. If it is empty, the agent exits with a "vision not set" note and does nothing.

## What are we building?

_One paragraph. What does a user do with this product? What problem does it solve?_

## Who is the user?

_Two or three sentences. Who matters? What do they care about?_

## Out of scope (negative constraints)

_List features the agent must NOT propose. Prevents drift._

- Do not propose features outside the monorepo at `apps/api`, `apps/web`, or `agents/`.
- Do not propose anything requiring paid third-party services beyond Railway + GitHub.
- Do not propose features that require the user's manual data entry.

## Current quarter focus

_One to three themes. Constrains what the PM picks from the backlog when multiple options tie._
```

- [ ] **Step 2: Create the initial state file**

Write `docs/product/state.yaml`:

```yaml
# State maintained by agents/product_analyzer.py and agents/product_manager.py.
# Humans may edit this file; agents will not overwrite human changes (they append + move entries).
max_open_agent_issues: 2
last_pm_run: null
last_analyzer_run: null

backlog:
  - id: B001
    title: "Smoke test /api/hello round-trip in CI"
    rationale: "Demo feature exists, but no E2E covers it."
    priority: normal
    added_by: seed
  - id: B002
    title: "Add /api/ping latency histogram to /api/status"
    rationale: "Dashboard shows CI counts but no runtime perf signal."
    priority: normal
    added_by: seed

in_progress: []

shipped: []

rejected: []
```

- [ ] **Step 3: Commit**

```bash
git add docs/product/vision.md docs/product/state.yaml
git commit -m "feat(product): seed vision + state docs for autonomous PM loop

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

## Task 4: state.yaml load/save library

**Files:**
- Create: `agents/src/agents/lib/product_state.py`
- Test: `agents/tests/test_product_state.py`
- Modify: `agents/pyproject.toml` (add `pyyaml` dep)

- [ ] **Step 1: Add pyyaml dependency**

Edit `agents/pyproject.toml` and add `"pyyaml>=6.0"` to the `dependencies` list. Run `uv sync --group dev --all-packages` to pick it up.

- [ ] **Step 2: Write the failing test**

Write `agents/tests/test_product_state.py`:

```python
from pathlib import Path

import pytest

from agents.lib import product_state


def test_load_parses_yaml(tmp_path: Path) -> None:
    p = tmp_path / "state.yaml"
    p.write_text("backlog:\n  - id: B001\n    title: A\n    priority: normal\n    added_by: seed\n    rationale: r\nin_progress: []\nshipped: []\nrejected: []\nmax_open_agent_issues: 2\nlast_pm_run: null\nlast_analyzer_run: null\n")
    state = product_state.load(p)
    assert state.max_open_agent_issues == 2
    assert len(state.backlog) == 1
    assert state.backlog[0].id == "B001"


def test_save_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "state.yaml"
    original = product_state.State(
        max_open_agent_issues=3,
        last_pm_run=None,
        last_analyzer_run=None,
        backlog=[product_state.Item(id="B002", title="T", priority="high", rationale="r", added_by="seed")],
        in_progress=[],
        shipped=[],
        rejected=[],
    )
    product_state.save(p, original)
    round_tripped = product_state.load(p)
    assert round_tripped.backlog[0].title == "T"
    assert round_tripped.max_open_agent_issues == 3


def test_move_to_in_progress_mutates(tmp_path: Path) -> None:
    state = product_state.State(
        max_open_agent_issues=2,
        last_pm_run=None,
        last_analyzer_run=None,
        backlog=[product_state.Item(id="B001", title="x", priority="normal", rationale="r", added_by="seed")],
        in_progress=[],
        shipped=[],
        rejected=[],
    )
    state.start("B001", issue_number=42)
    assert state.backlog == []
    assert state.in_progress[0].id == "B001"
    assert state.in_progress[0].issue_number == 42


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        product_state.load(tmp_path / "nope.yaml")
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest agents/tests/test_product_state.py -v`

Expected: FAIL with `ModuleNotFoundError: agents.lib.product_state`.

- [ ] **Step 4: Implement**

Write `agents/src/agents/lib/product_state.py`:

```python
"""Load + mutate + save docs/product/state.yaml."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Item:
    id: str
    title: str
    priority: str
    rationale: str
    added_by: str
    issue_number: int | None = None


@dataclass
class State:
    max_open_agent_issues: int
    last_pm_run: str | None
    last_analyzer_run: str | None
    backlog: list[Item] = field(default_factory=list)
    in_progress: list[Item] = field(default_factory=list)
    shipped: list[Item] = field(default_factory=list)
    rejected: list[Item] = field(default_factory=list)

    def start(self, item_id: str, *, issue_number: int) -> Item:
        for i, item in enumerate(self.backlog):
            if item.id == item_id:
                item.issue_number = issue_number
                self.in_progress.append(self.backlog.pop(i))
                return item
        raise KeyError(f"{item_id} not in backlog")

    def ship(self, item_id: str) -> Item:
        for i, item in enumerate(self.in_progress):
            if item.id == item_id:
                self.shipped.append(self.in_progress.pop(i))
                return self.shipped[-1]
        raise KeyError(f"{item_id} not in_progress")


def load(path: Path) -> State:
    data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    return State(
        max_open_agent_issues=int(data.get("max_open_agent_issues", 2)),
        last_pm_run=data.get("last_pm_run"),
        last_analyzer_run=data.get("last_analyzer_run"),
        backlog=[Item(**d) for d in data.get("backlog") or []],
        in_progress=[Item(**d) for d in data.get("in_progress") or []],
        shipped=[Item(**d) for d in data.get("shipped") or []],
        rejected=[Item(**d) for d in data.get("rejected") or []],
    )


def save(path: Path, state: State) -> None:
    payload = asdict(state)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(payload, sort_keys=False, default_flow_style=False))
    tmp.replace(path)
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest agents/tests/test_product_state.py -v`

Expected: PASS — 4/4.

- [ ] **Step 6: Commit**

```bash
git add agents/pyproject.toml agents/src/agents/lib/product_state.py agents/tests/test_product_state.py uv.lock
git commit -m "feat(agents): add product_state library for backlog YAML I/O

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

## Task 5: Product Manager system prompt

**Files:**
- Create: `agents/src/agents/lib/prompts/product_manager.md`

- [ ] **Step 1: Write the prompt**

Write `agents/src/agents/lib/prompts/product_manager.md`:

```markdown
You are the Product Manager agent for the ai-harness monorepo.

You will receive:
- VISION: the product vision (human-written, rarely changes).
- OPEN_ISSUES: currently-open GitHub issues with the `agent:build` label.
- STATE: the YAML-parsed `docs/product/state.yaml` content (backlog, in_progress, shipped, rejected).

Your job: decide whether to file ONE new GitHub issue for the next feature, or skip this run.

Decision rules:
1. If VISION is empty or missing, respond with exactly `DECISION: SKIP (vision-empty)` and stop.
2. If `len(OPEN_ISSUES) >= STATE.max_open_agent_issues`, respond with exactly `DECISION: SKIP (throttle)` and stop.
3. If the top backlog item matches an open issue or a shipped item by title similarity (>80%), skip it and consider the next one.
4. If the backlog has at least one item that does NOT duplicate open/shipped, pick it. Output:
```
DECISION: PICK
ID: <backlog item id>
TITLE: <issue title — exactly the backlog item's title>
BODY:
<4–10 sentence body: what to build, acceptance criteria, files likely to touch. End with the line "Refs: docs/product/state.yaml#<id>".>
```
5. If the backlog is empty or fully covered, propose ONE new backlog item that aligns with VISION and is not in shipped. Output:
```
DECISION: GENERATE
TITLE: <short imperative title>
BODY:
<same structure as PICK>
```

Hard rules:
- Respect negative constraints in VISION ("Out of scope" section). Never propose anything there.
- Never propose breaking changes to `agents/`, `apps/api`, `apps/web` public interfaces without a clear migration plan.
- Features must be small enough to ship in a single PR — 1–3 files.
- Do NOT output markdown fences, do NOT preface your response with "Here is my decision:" — start with `DECISION:` on line 1.
```

- [ ] **Step 2: Commit**

```bash
git add agents/src/agents/lib/prompts/product_manager.md
git commit -m "feat(prompts): add product_manager system prompt

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

## Task 6: Product Manager module

**Files:**
- Create: `agents/src/agents/product_manager.py`
- Test: `agents/tests/test_product_manager.py`

- [ ] **Step 1: Write the failing test**

Write `agents/tests/test_product_manager.py`:

```python
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents import product_manager
from agents.lib import labels, product_state


def _seed_state(tmp_path: Path) -> Path:
    state = product_state.State(
        max_open_agent_issues=2,
        last_pm_run=None,
        last_analyzer_run=None,
        backlog=[
            product_state.Item(
                id="B001", title="Smoke test hello endpoint",
                priority="normal", rationale="demo", added_by="seed",
            )
        ],
        in_progress=[],
        shipped=[],
        rejected=[],
    )
    p = tmp_path / "state.yaml"
    product_state.save(p, state)
    return p


def _seed_vision(tmp_path: Path, text: str = "A product harness.") -> Path:
    p = tmp_path / "vision.md"
    p.write_text(f"# Product Vision\n\n{text}\n")
    return p


@pytest.mark.asyncio
async def test_skip_when_vision_empty(tmp_path: Path) -> None:
    state_path = _seed_state(tmp_path)
    vision_path = _seed_vision(tmp_path, text="")
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []

    with patch("agents.product_manager.gh.repo", return_value=fake_repo):
        result = await product_manager.run(state_path, vision_path, dry_run=True)

    assert result == "skipped"
    fake_repo.create_issue.assert_not_called()


@pytest.mark.asyncio
async def test_skip_when_throttled(tmp_path: Path) -> None:
    state_path = _seed_state(tmp_path)
    vision_path = _seed_vision(tmp_path)
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = [MagicMock(), MagicMock()]

    with patch("agents.product_manager.gh.repo", return_value=fake_repo):
        result = await product_manager.run(state_path, vision_path, dry_run=True)

    assert result == "skipped"
    fake_repo.create_issue.assert_not_called()


@pytest.mark.asyncio
async def test_pick_from_backlog_opens_issue(tmp_path: Path) -> None:
    state_path = _seed_state(tmp_path)
    vision_path = _seed_vision(tmp_path)
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []
    created_issue = MagicMock(number=77, html_url="https://x")
    fake_repo.create_issue.return_value = created_issue

    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text",
        "text": "DECISION: PICK\nID: B001\nTITLE: Smoke test hello endpoint\nBODY:\nWrite a Playwright test that hits /api/hello?name=x and asserts the body.\nRefs: docs/product/state.yaml#B001",
    }]))

    with (
        patch("agents.product_manager.gh.repo", return_value=fake_repo),
        patch("agents.product_manager.run_agent", fake_llm),
    ):
        result = await product_manager.run(state_path, vision_path, dry_run=False)

    assert result == "picked"
    fake_repo.create_issue.assert_called_once()
    applied_labels = fake_repo.create_issue.call_args.kwargs["labels"]
    assert labels.AGENT_BUILD in applied_labels
    updated_state = product_state.load(state_path)
    assert updated_state.backlog == []
    assert updated_state.in_progress[0].id == "B001"
    assert updated_state.in_progress[0].issue_number == 77


@pytest.mark.asyncio
async def test_dry_run_does_not_open_issue(tmp_path: Path) -> None:
    state_path = _seed_state(tmp_path)
    vision_path = _seed_vision(tmp_path)
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []
    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text",
        "text": "DECISION: PICK\nID: B001\nTITLE: T\nBODY:\nBody\nRefs: x",
    }]))

    with (
        patch("agents.product_manager.gh.repo", return_value=fake_repo),
        patch("agents.product_manager.run_agent", fake_llm),
    ):
        result = await product_manager.run(state_path, vision_path, dry_run=True)

    assert result == "picked"
    fake_repo.create_issue.assert_not_called()
    updated_state = product_state.load(state_path)
    assert len(updated_state.backlog) == 1  # unchanged
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest agents/tests/test_product_manager.py -v`

Expected: FAIL — `ModuleNotFoundError: agents.product_manager`.

- [ ] **Step 3: Implement**

Write `agents/src/agents/product_manager.py`:

```python
"""PM agent: picks next feature from state.yaml backlog, opens a labelled GH issue."""

import argparse
import asyncio
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from agents.lib import gh, kill_switch, labels, product_state, prompts
from agents.lib.anthropic import run_agent

_DEFAULT_STATE = Path("docs/product/state.yaml")
_DEFAULT_VISION = Path("docs/product/vision.md")


def _vision_text(path: Path) -> str:
    text = path.read_text() if path.exists() else ""
    body = re.sub(r"^#.*$", "", text, flags=re.MULTILINE).strip()
    return body


async def run(state_path: Path, vision_path: Path, *, dry_run: bool) -> str:
    """Returns 'skipped' | 'picked' | 'generated'."""
    state = product_state.load(state_path)
    vision = _vision_text(vision_path)
    repo = gh.repo()
    open_issues = list(repo.get_issues(state="open", labels=[labels.AGENT_BUILD]))

    if not vision:
        return "skipped"
    if len(open_issues) >= state.max_open_agent_issues:
        return "skipped"

    user_prompt = (
        f"VISION:\n{vision}\n\n"
        f"OPEN_ISSUES ({len(open_issues)}):\n"
        + "\n".join(f"- #{i.number} {i.title}" for i in open_issues)
        + "\n\nSTATE:\n"
        + f"backlog: {[{'id': b.id, 'title': b.title} for b in state.backlog]}\n"
        + f"in_progress: {[{'id': b.id, 'title': b.title} for b in state.in_progress]}\n"
        + f"shipped: {[b.title for b in state.shipped]}\n"
    )
    system = prompts.load("product_manager")
    result = await run_agent(prompt=user_prompt, system=system, max_turns=3, allowed_tools=[])
    text = _extract_text(result.messages)
    decision = _parse_decision(text)

    if decision["kind"] == "SKIP":
        return "skipped"

    if not dry_run:
        body = decision["body"] + f"\n\n_Opened autonomously by Product Manager agent at {datetime.now(UTC).isoformat()}._"
        issue = repo.create_issue(
            title=decision["title"],
            body=body,
            labels=[labels.AGENT_BUILD],
        )
        if decision["kind"] == "PICK":
            state.start(decision["id"], issue_number=issue.number)
        elif decision["kind"] == "GENERATE":
            new_id = f"B{1 + len(state.backlog) + len(state.shipped) + len(state.in_progress):03d}"
            state.backlog.append(product_state.Item(
                id=new_id, title=decision["title"],
                priority="normal", rationale="generated by PM",
                added_by="pm-agent", issue_number=issue.number,
            ))
            state.start(new_id, issue_number=issue.number)
        state.last_pm_run = datetime.now(UTC).isoformat()
        product_state.save(state_path, state)

    return "picked" if decision["kind"] == "PICK" else "generated"


def _extract_text(messages: list[object]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


def _parse_decision(text: str) -> dict[str, str]:
    """Parse the structured response. Returns dict with 'kind', 'id' (if PICK), 'title', 'body'."""
    first = text.splitlines()[0] if text else ""
    if first.startswith("DECISION: SKIP"):
        return {"kind": "SKIP", "id": "", "title": "", "body": ""}

    kind = "PICK" if "DECISION: PICK" in first else "GENERATE"
    id_match = re.search(r"^ID:\s*(\S+)", text, flags=re.MULTILINE)
    title_match = re.search(r"^TITLE:\s*(.+)$", text, flags=re.MULTILINE)
    body_match = re.search(r"^BODY:\s*\n(.+)", text, flags=re.DOTALL | re.MULTILINE)
    return {
        "kind": kind,
        "id": id_match.group(1) if id_match else "",
        "title": title_match.group(1).strip() if title_match else "",
        "body": body_match.group(1).strip() if body_match else "",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agents.product_manager")
    parser.add_argument("--state", type=Path, default=_DEFAULT_STATE)
    parser.add_argument("--vision", type=Path, default=_DEFAULT_VISION)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    kill_switch.exit_if_paused()
    result = asyncio.run(run(args.state, args.vision, dry_run=args.dry_run))
    print(f"pm: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest agents/tests/test_product_manager.py -v`

Expected: PASS — 4/4.

- [ ] **Step 5: Commit**

```bash
git add agents/src/agents/product_manager.py agents/tests/test_product_manager.py
git commit -m "feat(agents): add product_manager agent (feature-intake side of the loop)

Reads state.yaml + vision + open agent:build issues; picks next backlog
item or generates one; opens GH issue with agent:build label; mutates
state.yaml atomically.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

## Task 7: Product Manager workflow

**Files:**
- Create: `.github/workflows/product-manager.yml`

- [ ] **Step 1: Write the workflow**

Write `.github/workflows/product-manager.yml`:

```yaml
name: product-manager

on:
  schedule:
    - cron: "0 6,12,18 * * *"
  workflow_dispatch:

permissions:
  contents: write
  issues: write
  models: read

jobs:
  pm:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    env:
      HARNESS_BACKEND: ${{ vars.HARNESS_BACKEND }}
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      GH_REPO: ${{ github.repository }}
    steps:
      - name: Check kill-switch
        env:
          PAUSE: ${{ vars.PAUSE_AGENTS }}
        run: |
          if [ "${PAUSE}" = "true" ]; then
            echo "PAUSE_AGENTS=true — skipping product-manager"
            exit 0
          fi
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
      - name: Configure git push auth
        run: |
          git config --global user.name "ai-harness-bot"
          git config --global user.email "ai-harness@local"
          git remote set-url origin "https://x-access-token:${GITHUB_TOKEN}@github.com/${GH_REPO}.git"
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --group dev --all-packages --frozen
      - name: Decide + maybe open issue
        run: uv run python -m agents.product_manager
      - name: Commit state.yaml if changed
        run: |
          if [ -n "$(git status --porcelain docs/product/state.yaml)" ]; then
            git add docs/product/state.yaml
            git commit -m "chore(pm): update state.yaml [skip ci]"
            git push origin HEAD:main
          fi
```

- [ ] **Step 2: Lint YAML**

Run: `uv run yamllint .github/workflows/product-manager.yml || true` (advisory — if yamllint isn't installed, skip).

Also manually verify: the file has `[skip ci]` in the commit message to prevent triggering deploy-prod.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/product-manager.yml
git commit -m "feat(workflows): schedule product-manager agent 3x/day

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

## Task 8: E2E verify Product Manager

**Files:** none created — verification only.

- [ ] **Step 1: Push changes + trigger dispatch**

```bash
git push origin main
gh workflow run product-manager.yml --repo nt-suuri/ai-harness
```

- [ ] **Step 2: Watch the run**

Run: `gh run watch $(gh run list --workflow=product-manager.yml --limit 1 --json databaseId --jq '.[0].databaseId') --exit-status`

Expected: Exit code 0. Log should contain `pm: skipped` (because `docs/product/vision.md` is still the empty template).

- [ ] **Step 3: Seed a real vision and re-trigger**

Edit `docs/product/vision.md` locally and fill in the "What are we building?" section with a single paragraph describing what the harness should grow into (e.g., "A sandbox for testing autonomous agent workflows. Users interact via the dashboard; agents maintain the codebase."). Commit and push.

Then: `gh workflow run product-manager.yml`

Expected log: `pm: picked` or `pm: generated`, and `gh issue list --label agent:build` shows one new issue referencing `docs/product/state.yaml#B001` (or a new ID).

- [ ] **Step 4: Confirm the downstream chain fires**

Run: `gh run list --limit 5`

Expected: within ~1 minute of the PM creating the issue, a `planner` run appears. Within 5–10 minutes, a PR is opened, and `reviewer` runs fire.

No commit — verification only.

---

# Phase P52 — Product Analyzer Agent + Deploy-Loop Guardrail

**Goal:** After each release, an agent moves shipped items into `state.shipped` and tops up `backlog`. Also: prevent docs/product/ changes from triggering a redeploy.

## Task 9: Product Analyzer system prompt

**Files:**
- Create: `agents/src/agents/lib/prompts/product_analyzer.md`

- [ ] **Step 1: Write the prompt**

Write `agents/src/agents/lib/prompts/product_analyzer.md`:

```markdown
You are the Product Analyzer agent.

You will receive:
- RECENT_COMMITS: titles + messages of merged commits since the previous analyzer run.
- CURRENT_BACKLOG: the `backlog` list from state.yaml.
- CURRENT_IN_PROGRESS: the `in_progress` list (each entry has id, title, issue_number).
- VISION: the product vision (read-only).

Produce TWO outputs:

1. `SHIPPED_IDS: <comma-separated list of in_progress item IDs whose title clearly matches a merged commit>`
2. `NEW_BACKLOG:` followed by zero to three new backlog entries in YAML list format:
   ```yaml
   - id: B???
     title: <short imperative title>
     rationale: <why — 1 sentence grounded in VISION or observed gap>
     priority: normal
     added_by: analyzer
   ```
   IDs must continue the numbering from state.yaml. Do not duplicate titles already in backlog, in_progress, or shipped.

If nothing shipped and backlog is adequately full (>=3 items), output `NEW_BACKLOG: []`.

Do NOT include markdown fences in your response. Start with `SHIPPED_IDS:` on line 1.
```

- [ ] **Step 2: Commit**

```bash
git add agents/src/agents/lib/prompts/product_analyzer.md
git commit -m "feat(prompts): add product_analyzer system prompt

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

## Task 10: Product Analyzer module

**Files:**
- Create: `agents/src/agents/product_analyzer.py`
- Test: `agents/tests/test_product_analyzer.py`

- [ ] **Step 1: Write the failing test**

Write `agents/tests/test_product_analyzer.py`:

```python
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents import product_analyzer
from agents.lib import product_state


def _state_with_in_progress(tmp_path: Path) -> Path:
    state = product_state.State(
        max_open_agent_issues=2,
        last_pm_run=None,
        last_analyzer_run=None,
        backlog=[],
        in_progress=[product_state.Item(
            id="B001", title="Smoke test hello endpoint",
            priority="normal", rationale="r", added_by="seed", issue_number=77,
        )],
        shipped=[],
        rejected=[],
    )
    p = tmp_path / "state.yaml"
    product_state.save(p, state)
    return p


@pytest.mark.asyncio
async def test_ships_in_progress_when_commit_matches(tmp_path: Path) -> None:
    state_path = _state_with_in_progress(tmp_path)
    vision_path = tmp_path / "vision.md"
    vision_path.write_text("Vision text")

    fake_repo = MagicMock()
    commit = MagicMock()
    commit.commit.message = "feat: smoke test hello endpoint round-trip"
    fake_repo.get_commits.return_value = [commit]

    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text",
        "text": "SHIPPED_IDS: B001\nNEW_BACKLOG: []",
    }]))

    with (
        patch("agents.product_analyzer.gh.repo", return_value=fake_repo),
        patch("agents.product_analyzer.run_agent", fake_llm),
    ):
        await product_analyzer.run(state_path, vision_path, dry_run=False)

    updated = product_state.load(state_path)
    assert len(updated.in_progress) == 0
    assert updated.shipped[0].id == "B001"


@pytest.mark.asyncio
async def test_appends_new_backlog_items(tmp_path: Path) -> None:
    state_path = _state_with_in_progress(tmp_path)
    vision_path = tmp_path / "vision.md"
    vision_path.write_text("Vision text")

    fake_repo = MagicMock()
    fake_repo.get_commits.return_value = []
    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text",
        "text": (
            "SHIPPED_IDS:\n"
            "NEW_BACKLOG:\n"
            "- id: B002\n  title: Add latency histogram\n  rationale: gap in /api/status\n  priority: normal\n  added_by: analyzer\n"
        ),
    }]))

    with (
        patch("agents.product_analyzer.gh.repo", return_value=fake_repo),
        patch("agents.product_analyzer.run_agent", fake_llm),
    ):
        await product_analyzer.run(state_path, vision_path, dry_run=False)

    updated = product_state.load(state_path)
    assert any(item.id == "B002" for item in updated.backlog)


@pytest.mark.asyncio
async def test_dry_run_does_not_mutate_state(tmp_path: Path) -> None:
    state_path = _state_with_in_progress(tmp_path)
    vision_path = tmp_path / "vision.md"
    vision_path.write_text("Vision text")
    original = state_path.read_text()

    fake_repo = MagicMock()
    fake_repo.get_commits.return_value = []
    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text",
        "text": "SHIPPED_IDS: B001\nNEW_BACKLOG: []",
    }]))

    with (
        patch("agents.product_analyzer.gh.repo", return_value=fake_repo),
        patch("agents.product_analyzer.run_agent", fake_llm),
    ):
        await product_analyzer.run(state_path, vision_path, dry_run=True)

    assert state_path.read_text() == original
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest agents/tests/test_product_analyzer.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Write `agents/src/agents/product_analyzer.py`:

```python
"""Product Analyzer: post-release agent that moves shipped items + tops up backlog."""

import argparse
import asyncio
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from agents.lib import gh, kill_switch, product_state, prompts
from agents.lib.anthropic import run_agent

_DEFAULT_STATE = Path("docs/product/state.yaml")
_DEFAULT_VISION = Path("docs/product/vision.md")
_COMMIT_LOOKBACK = 50


async def run(state_path: Path, vision_path: Path, *, dry_run: bool) -> None:
    state = product_state.load(state_path)
    vision = vision_path.read_text() if vision_path.exists() else ""
    repo = gh.repo()
    commits = list(repo.get_commits()[:_COMMIT_LOOKBACK])

    commit_blob = "\n".join(f"- {c.commit.message.splitlines()[0]}" for c in commits)

    user_prompt = (
        f"RECENT_COMMITS:\n{commit_blob}\n\n"
        f"CURRENT_BACKLOG:\n{[{'id': b.id, 'title': b.title} for b in state.backlog]}\n\n"
        f"CURRENT_IN_PROGRESS:\n{[{'id': b.id, 'title': b.title} for b in state.in_progress]}\n\n"
        f"VISION:\n{vision}\n"
    )
    system = prompts.load("product_analyzer")
    result = await run_agent(prompt=user_prompt, system=system, max_turns=3, allowed_tools=[])
    text = _extract_text(result.messages)

    shipped_ids = _parse_shipped(text)
    new_items = _parse_new_backlog(text)

    if dry_run:
        return

    for item_id in shipped_ids:
        try:
            state.ship(item_id)
        except KeyError:
            continue

    existing_titles = {i.title for i in state.backlog + state.in_progress + state.shipped}
    for new in new_items:
        if new["title"] in existing_titles:
            continue
        state.backlog.append(product_state.Item(
            id=new["id"], title=new["title"],
            priority=new.get("priority", "normal"),
            rationale=new.get("rationale", ""),
            added_by="analyzer",
        ))

    state.last_analyzer_run = datetime.now(UTC).isoformat()
    product_state.save(state_path, state)


def _extract_text(messages: list[object]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


def _parse_shipped(text: str) -> list[str]:
    m = re.search(r"^SHIPPED_IDS:\s*(.*)$", text, flags=re.MULTILINE)
    if not m:
        return []
    raw = m.group(1).strip()
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def _parse_new_backlog(text: str) -> list[dict[str, str]]:
    m = re.search(r"^NEW_BACKLOG:\s*(.*)", text, flags=re.DOTALL | re.MULTILINE)
    if not m:
        return []
    raw = m.group(1).strip()
    if raw in ("[]", ""):
        return []
    try:
        parsed = yaml.safe_load(raw) or []
    except yaml.YAMLError:
        return []
    return [dict(entry) for entry in parsed if isinstance(entry, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agents.product_analyzer")
    parser.add_argument("--state", type=Path, default=_DEFAULT_STATE)
    parser.add_argument("--vision", type=Path, default=_DEFAULT_VISION)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    kill_switch.exit_if_paused()
    asyncio.run(run(args.state, args.vision, dry_run=args.dry_run))
    print("analyzer: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest agents/tests/test_product_analyzer.py -v`

Expected: PASS — 3/3.

- [ ] **Step 5: Commit**

```bash
git add agents/src/agents/product_analyzer.py agents/tests/test_product_analyzer.py
git commit -m "feat(agents): add product_analyzer (post-release state updater)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

## Task 11: Product Analyzer workflow

**Files:**
- Create: `.github/workflows/product-analyzer.yml`

- [ ] **Step 1: Write the workflow**

Write `.github/workflows/product-analyzer.yml`:

```yaml
name: product-analyzer

on:
  workflow_run:
    workflows: [release-notes]
    types: [completed]
  workflow_dispatch:

permissions:
  contents: write
  models: read

jobs:
  analyze:
    if: github.event.workflow_run.conclusion == 'success' || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    timeout-minutes: 10
    env:
      HARNESS_BACKEND: ${{ vars.HARNESS_BACKEND }}
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      GH_REPO: ${{ github.repository }}
    steps:
      - name: Check kill-switch
        env:
          PAUSE: ${{ vars.PAUSE_AGENTS }}
        run: |
          if [ "${PAUSE}" = "true" ]; then
            echo "PAUSE_AGENTS=true — skipping product-analyzer"
            exit 0
          fi
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          fetch-depth: 50
      - name: Configure git push auth
        run: |
          git config --global user.name "ai-harness-bot"
          git config --global user.email "ai-harness@local"
          git remote set-url origin "https://x-access-token:${GITHUB_TOKEN}@github.com/${GH_REPO}.git"
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --group dev --all-packages --frozen
      - name: Analyze
        run: uv run python -m agents.product_analyzer
      - name: Commit state.yaml if changed
        run: |
          if [ -n "$(git status --porcelain docs/product/state.yaml)" ]; then
            git add docs/product/state.yaml
            git commit -m "chore(analyzer): update state.yaml [skip ci]"
            git push origin HEAD:main
          fi
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/product-analyzer.yml
git commit -m "feat(workflows): run product-analyzer after each release

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

## Task 12: Prevent docs/product/ changes from redeploying

**Files:**
- Modify: `.github/workflows/deploy-prod.yml`

- [ ] **Step 1: Add paths-ignore to the trigger**

Edit `.github/workflows/deploy-prod.yml`. Find the `on:` block and replace:

```yaml
on:
  push:
    branches: [main]
  workflow_dispatch:
```

With:

```yaml
on:
  push:
    branches: [main]
    paths-ignore:
      - 'docs/product/**'
      - 'docs/superpowers/**'
      - 'RELEASES.md'
      - '*.md'
  workflow_dispatch:
```

Also add the same `paths-ignore` block to `.github/workflows/deploy-dev.yml` if it exists (check first with `ls .github/workflows/deploy-dev.yml`).

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/deploy-prod.yml
# add deploy-dev.yml if it was also changed:
git add .github/workflows/deploy-dev.yml 2>/dev/null || true
git commit -m "fix(deploy): skip deploy when only docs change

Analyzer + release-notes commit markdown on every cycle; redeploying
the container for a markdown diff wastes Railway build minutes and
creates false rollback-watch signal.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

## Task 13: Document the new loop in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append the new section**

Open `CLAUDE.md` and insert this block immediately after the "Feature intake: `agent:build` label" section:

```markdown
## Autonomous product loop (P50–P52)

Three new moving parts close the full self-directing cycle:

1. **`product-manager.yml`** — cron 06/12/18 UTC + `workflow_dispatch`. Reads `docs/product/vision.md` + `docs/product/state.yaml` + currently-open `agent:build` issues. If vision is empty or >= `max_open_agent_issues` are open, exits with `pm: skipped`. Otherwise picks the top backlog item (or generates a new one), opens a GH issue with `agent:build`, and moves the item to `in_progress` in state.yaml. Commits state.yaml with `[skip ci]`.
2. **`product-analyzer.yml`** — triggered by `workflow_run: release-notes`. Reads the last 50 merged commits + vision + state. Moves items from `in_progress` → `shipped` when a matching commit is found; appends up to 3 new backlog items (LLM-proposed) grounded in vision. Commits state.yaml with `[skip ci]`.
3. **Triager + deployer auto-label** — issues created by `triager.py` (severity ≥ important) and all regression issues from `deployer.py` now include `agent:build`, so the planner fires without human intervention.

### Seeding the loop

1. Edit `docs/product/vision.md` once — fill in "What are we building?" and "Out of scope". The PM agent refuses to act on an empty vision.
2. Optionally seed `docs/product/state.yaml` with 2–3 backlog items you want built first. If unset, the PM agent will propose its own.
3. `gh workflow run product-manager.yml` to run it immediately (otherwise it fires at 06/12/18 UTC daily).

### Guardrails in place

- `max_open_agent_issues` in state.yaml throttles the PM (default 2) so planner never stacks more than N PRs.
- `deploy-prod.yml` has `paths-ignore: [docs/product/**, docs/superpowers/**, RELEASES.md, *.md]` — markdown-only commits don't deploy.
- Both PM and Analyzer commits use `[skip ci]` as belt-and-suspenders.
- Kill switch: `gh variable set PAUSE_AGENTS --body true` halts all autonomous workflows.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: describe autonomous product loop in CLAUDE.md

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

## Task 14: E2E verification

**Files:** none created — verification only.

- [ ] **Step 1: Push everything**

```bash
git push origin main
```

- [ ] **Step 2: Verify triager auto-label works**

Run the triager on demand with a seeded Sentry response:

```bash
gh workflow run triager.yml --repo nt-suuri/ai-harness
gh run watch $(gh run list --workflow=triager.yml --limit 1 --json databaseId --jq '.[0].databaseId') --exit-status
```

Expected: if Sentry reports any issue with severity≥important, a new GH issue appears with labels `[bug, autotriage, severity:*, agent:build]`.

Check: `gh issue list --label agent:build --state open`

- [ ] **Step 3: Fill in a real vision and trigger PM**

```bash
# edit docs/product/vision.md — paste a paragraph under "What are we building?"
git add docs/product/vision.md && git commit -m "chore(product): seed vision" && git push
gh workflow run product-manager.yml
gh run watch $(gh run list --workflow=product-manager.yml --limit 1 --json databaseId --jq '.[0].databaseId') --exit-status
```

Expected: run log shows `pm: picked` or `pm: generated`. `gh issue list --label agent:build --state open` shows a new issue. `state.yaml` has one fewer backlog item and one more in_progress.

- [ ] **Step 4: Confirm the full chain fires**

Within ~10 minutes of Step 3:

```bash
gh pr list --state open
```

Expected: one new PR opened by `app/github-actions` referencing the new issue.

```bash
gh run list --limit 10
```

Expected: chronological chain of runs — `product-manager` → `planner` → `reviewer` (3 matrix jobs) → `pr-describer`.

- [ ] **Step 5: After merge, verify analyzer fires**

Merge the PR. Wait 2–3 minutes.

```bash
gh run list --workflow=product-analyzer.yml --limit 1
```

Expected: one run triggered by `release-notes` completion, status `success`. Inspect `docs/product/state.yaml` — the in_progress item should now be in `shipped`.

No commit — verification only.

---

## Self-review notes

1. **Spec coverage:** every requirement in the user's spec has a task:
   - "product manager owner add feature spec" → Tasks 3, 5, 6, 7
   - "another agent take task and implement" → already exists (planner)
   - "another agent review" → already exists (reviewer)
   - "another agent deploy" → already exists (deploy-prod)
   - "another agent monitor Sentry" → already exists (rollback-watch, triager)
   - "another agent fix the bug" → Tasks 1, 2 close the gap (auto-label `agent:build`)
   - "another agent analyze product and next request" → Tasks 9, 10, 11
   - "looping 3-5 times per day" → Task 7 schedule 06/12/18 UTC (3× default; bump to 5 by editing the cron)

2. **Placeholder scan:** zero TODO/TBD. All code shown in full. All commit messages literal. All commands exact.

3. **Type consistency:** `Item`, `State`, `start()`, `ship()`, `max_open_agent_issues`, `last_pm_run`, `last_analyzer_run` — spelled identically across Tasks 4, 6, 10 and their tests.

## Verification plan (end-to-end)

After all 14 tasks land:

1. Edit `docs/product/vision.md` to fill in vision. Push.
2. `gh workflow run product-manager.yml` — expect `pm: picked`, new `agent:build` issue.
3. Within 10 min: planner PR opens, reviewer fires, CI passes (or reviewer posts real concerns — the loop catches real issues).
4. Merge PR → deploy → release-notes runs → product-analyzer runs → state.yaml updates (in_progress item → shipped).
5. Next cron run (06/12/18 UTC): PM picks the next backlog item.
6. Bug path: inject a runtime error into `/api/ping`, deploy, watch deployer open a regression issue with `agent:build`, watch planner auto-fix.

Both loops run with zero human typing — vision is the only human-written text per quarter.
