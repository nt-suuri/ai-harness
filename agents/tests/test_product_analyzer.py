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


@pytest.mark.asyncio
async def test_malformed_new_backlog_is_skipped_not_crashed(tmp_path: Path) -> None:
    state_path = _state_with_in_progress(tmp_path)
    vision_path = tmp_path / "vision.md"
    vision_path.write_text("Vision")

    fake_repo = MagicMock()
    fake_repo.get_commits.return_value = []
    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text",
        "text": "SHIPPED_IDS:\nNEW_BACKLOG: just a sentence, not a list",
    }]))

    with (
        patch("agents.product_analyzer.gh.repo", return_value=fake_repo),
        patch("agents.product_analyzer.run_agent", fake_llm),
    ):
        await product_analyzer.run(state_path, vision_path, dry_run=False)

    updated = product_state.load(state_path)
    assert updated.backlog == []  # malformed entry dropped, no corruption


@pytest.mark.asyncio
async def test_absent_shipped_ids_line_is_no_op(tmp_path: Path) -> None:
    state_path = _state_with_in_progress(tmp_path)
    vision_path = tmp_path / "vision.md"
    vision_path.write_text("Vision")

    fake_repo = MagicMock()
    fake_repo.get_commits.return_value = []
    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text",
        "text": "NEW_BACKLOG: []",
    }]))

    with (
        patch("agents.product_analyzer.gh.repo", return_value=fake_repo),
        patch("agents.product_analyzer.run_agent", fake_llm),
    ):
        await product_analyzer.run(state_path, vision_path, dry_run=False)

    updated = product_state.load(state_path)
    assert len(updated.in_progress) == 1  # nothing shipped
    assert updated.backlog == []


@pytest.mark.asyncio
async def test_duplicate_title_not_appended(tmp_path: Path) -> None:
    state = product_state.State(
        max_open_agent_issues=2,
        last_pm_run=None,
        last_analyzer_run=None,
        backlog=[product_state.Item(
            id="B001", title="Already here", priority="normal",
            rationale="r", added_by="seed",
        )],
        in_progress=[],
        shipped=[],
        rejected=[],
    )
    state_path = tmp_path / "state.yaml"
    product_state.save(state_path, state)
    vision_path = tmp_path / "vision.md"
    vision_path.write_text("V")

    fake_repo = MagicMock()
    fake_repo.get_commits.return_value = []
    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text",
        "text": (
            "SHIPPED_IDS:\nNEW_BACKLOG:\n"
            "- id: B002\n  title: Already here\n  rationale: dup\n  priority: normal\n  added_by: analyzer\n"
        ),
    }]))

    with (
        patch("agents.product_analyzer.gh.repo", return_value=fake_repo),
        patch("agents.product_analyzer.run_agent", fake_llm),
    ):
        await product_analyzer.run(state_path, vision_path, dry_run=False)

    updated = product_state.load(state_path)
    assert len(updated.backlog) == 1  # duplicate dropped
    assert updated.backlog[0].id == "B001"


@pytest.mark.asyncio
async def test_llm_suggested_ids_are_reassigned_sequentially(tmp_path: Path) -> None:
    """LLM-provided IDs are ignored; analyzer auto-assigns from max+1."""
    state = product_state.State(
        max_open_agent_issues=2,
        last_pm_run=None,
        last_analyzer_run=None,
        backlog=[product_state.Item(
            id="B005", title="Existing", priority="normal",
            rationale="r", added_by="seed",
        )],
        in_progress=[],
        shipped=[],
        rejected=[],
    )
    state_path = tmp_path / "state.yaml"
    product_state.save(state_path, state)
    vision_path = tmp_path / "vision.md"
    vision_path.write_text("V")

    fake_repo = MagicMock()
    fake_repo.get_commits.return_value = []
    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text",
        "text": (
            "SHIPPED_IDS:\nNEW_BACKLOG:\n"
            "- id: B001\n  title: New feature alpha\n  rationale: r\n  priority: normal\n  added_by: analyzer\n"
            "- id: B001\n  title: New feature beta\n  rationale: r\n  priority: normal\n  added_by: analyzer\n"
        ),
    }]))

    with (
        patch("agents.product_analyzer.gh.repo", return_value=fake_repo),
        patch("agents.product_analyzer.run_agent", fake_llm),
    ):
        await product_analyzer.run(state_path, vision_path, dry_run=False)

    updated = product_state.load(state_path)
    ids = {i.id for i in updated.backlog}
    assert ids == {"B005", "B006", "B007"}  # collision-free numbering from max+1


def test_next_id_num_from_empty_is_one() -> None:
    assert product_analyzer._next_id_num(set()) == 1


def test_next_id_num_skips_non_bprefixed_ids() -> None:
    assert product_analyzer._next_id_num({"B001", "X007", "B003", "foo"}) == 4
