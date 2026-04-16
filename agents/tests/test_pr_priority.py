from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents import pr_priority


def _mock_pr(number: int, title: str, labels: list[str], author: str, files: int) -> MagicMock:
    pr = MagicMock()
    pr.number = number
    pr.title = title
    pr.labels = [MagicMock(name=l) for l in labels]
    pr.user.login = author
    pr.changed_files = files
    pr.created_at = MagicMock(isoformat=MagicMock(return_value="2026-04-16T00:00:00"))
    return pr


@pytest.mark.asyncio
async def test_bug_fix_ranks_above_feature() -> None:
    repo = MagicMock()
    repo.get_pulls.return_value = [
        _mock_pr(10, "feat: new widget", ["agent:build"], "github-actions", 3),
        _mock_pr(11, "fix: crash on login", ["bug", "regression"], "github-actions", 1),
    ]
    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text",
        "text": "PRIORITY:\n1. #11 — bug fix\n2. #10 — feature\nMERGE_NEXT: #11",
    }]))
    with patch("agents.pr_priority.run_agent", fake_llm):
        result = await pr_priority.rank(repo)
    assert result == 11


@pytest.mark.asyncio
async def test_empty_list_returns_none() -> None:
    repo = MagicMock()
    repo.get_pulls.return_value = []
    result = await pr_priority.rank(repo)
    assert result is None


@pytest.mark.asyncio
async def test_dependabot_ranks_lowest() -> None:
    repo = MagicMock()
    repo.get_pulls.return_value = [
        _mock_pr(5, "chore(deps): bump foo", [], "dependabot", 2),
        _mock_pr(6, "feat: add endpoint", ["agent:build"], "github-actions", 3),
    ]
    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text",
        "text": "PRIORITY:\n1. #6 — feature\n2. #5 — deps\nMERGE_NEXT: #6",
    }]))
    with patch("agents.pr_priority.run_agent", fake_llm):
        result = await pr_priority.rank(repo)
    assert result == 6
