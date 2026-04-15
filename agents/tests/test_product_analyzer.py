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
