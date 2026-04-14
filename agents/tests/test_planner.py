import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.planner import _branch_name, plan_and_open_pr


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


def test_planner_cli_accepts_int_issue_with_help_check_only() -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.planner",
            "--issue", "42", "--dry-run", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_branch_name_simple_title() -> None:
    assert _branch_name(42, "Add dark mode toggle") == "feat/42-add-dark-mode-toggle"


def test_branch_name_lowercases_and_slugifies() -> None:
    name = _branch_name(7, "Fix THE /api/users endpoint!!!")
    assert name == "feat/7-fix-the-api-users-endpoint"


def test_branch_name_truncates_long_titles() -> None:
    long = "a " * 80
    name = _branch_name(1, long.strip())
    # Slug bounded — feat/1- prefix (7 chars) + 40 char slug = 47 max
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
        patch("agents.planner._run_git"),
        patch("agents.planner._has_changes", return_value=False),
    ):
        mock_run.return_value = MagicMock(
            messages=[{"type": "text", "text": "No changes needed."}],
            stopped_reason="complete",
        )
        rc = await plan_and_open_pr(5, dry_run=False)

    assert rc == 1
    fake_repo.create_pull.assert_not_called()
    fake_issue.create_comment.assert_called_once()
