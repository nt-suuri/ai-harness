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
