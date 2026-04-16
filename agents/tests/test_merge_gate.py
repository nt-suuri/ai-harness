from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents import merge_gate


def _mock_pr(comments: list[str], statuses: dict[str, str]) -> tuple[MagicMock, list[MagicMock]]:
    pr = MagicMock()
    pr.get_issue_comments.return_value = [MagicMock(body=c) for c in comments]
    pr.head.sha = "abc123"
    mock_statuses = [MagicMock(context=k, state=v) for k, v in statuses.items()]
    return pr, mock_statuses


@pytest.mark.asyncio
async def test_merge_when_all_approved() -> None:
    pr, statuses = _mock_pr(
        [
            "**Claude review — quality**\n\nVERDICT: APPROVED",
            "**Claude review — security**\n\nVERDICT: APPROVED",
            "**Claude review — deps**\n\nVERDICT: APPROVED",
        ],
        {"ci / python": "success", "ci / web": "success"},
    )
    repo = MagicMock()
    repo.get_pull.return_value = pr
    repo.get_commit.return_value.get_statuses.return_value = statuses

    fake_llm = AsyncMock(return_value=MagicMock(messages=[{"type": "text", "text": "DECISION: MERGE"}]))

    with (
        patch("agents.merge_gate.run_agent", fake_llm),
        patch("agents.merge_gate.subprocess.run"),
    ):
        decision, feedback = await merge_gate.decide(1, repo=repo)

    assert decision == "merged"
    assert feedback == ""


@pytest.mark.asyncio
async def test_reject_when_any_rejected() -> None:
    pr, statuses = _mock_pr(
        [
            "**Claude review — quality**\n\nVERDICT: REJECTED\nBad imports",
            "**Claude review — security**\n\nVERDICT: APPROVED",
            "**Claude review — deps**\n\nVERDICT: APPROVED",
        ],
        {},
    )
    repo = MagicMock()
    repo.get_pull.return_value = pr
    repo.get_commit.return_value.get_statuses.return_value = statuses

    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text",
        "text": "DECISION: REJECT\nFEEDBACK:\nFix the import order in main.py",
    }]))

    with patch("agents.merge_gate.run_agent", fake_llm):
        decision, feedback = await merge_gate.decide(1, repo=repo)

    assert decision == "rejected"
    assert "import" in feedback.lower()


@pytest.mark.asyncio
async def test_wait_when_no_comments() -> None:
    pr, _ = _mock_pr([], {})
    repo = MagicMock()
    repo.get_pull.return_value = pr

    decision, feedback = await merge_gate.decide(1, repo=repo)

    assert decision == "waiting"
    assert feedback == ""


@pytest.mark.asyncio
async def test_hold_when_ci_failed() -> None:
    pr, statuses = _mock_pr(
        [
            "**Claude review — quality**\n\nVERDICT: APPROVED",
            "**Claude review — security**\n\nVERDICT: APPROVED",
            "**Claude review — deps**\n\nVERDICT: APPROVED",
        ],
        {"ci / python": "failure"},
    )
    repo = MagicMock()
    repo.get_pull.return_value = pr
    repo.get_commit.return_value.get_statuses.return_value = statuses

    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text",
        "text": "DECISION: HOLD (ci-failed)",
    }]))

    with patch("agents.merge_gate.run_agent", fake_llm):
        decision, feedback = await merge_gate.decide(1, repo=repo)

    assert decision == "held"
    assert feedback == ""
