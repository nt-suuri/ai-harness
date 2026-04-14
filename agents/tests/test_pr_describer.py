import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.pr_describer import _is_minimal_description, fill_pr_description


def test_cli_help() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.pr_describer", "--pr", "1", "--dry-run", "--help-check-only"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_cli_requires_pr() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.pr_describer", "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


@pytest.mark.parametrize("body,expected", [
    ("", True),
    (None, True),
    ("   ", True),
    ("\n\n", True),
    ("a", True),
    ("Just a quick fix", True),
    ("This PR adds a comprehensive new feature with multiple parts...", False),
])
def test_is_minimal_description(body: str | None, expected: bool) -> None:
    assert _is_minimal_description(body) is expected


@pytest.mark.asyncio
async def test_fill_pr_description_skips_when_already_described() -> None:
    fake_repo = MagicMock()
    fake_pr = MagicMock()
    fake_pr.title = "Add feature"
    fake_pr.body = "This PR introduces feature X with detailed implementation across multiple files."
    fake_repo.get_pull.return_value = fake_pr

    with patch("agents.pr_describer.gh.repo", return_value=fake_repo):
        rc = await fill_pr_description(42, dry_run=False)

    assert rc == 0
    fake_pr.edit.assert_not_called()


@pytest.mark.asyncio
async def test_fill_pr_description_writes_when_empty() -> None:
    fake_repo = MagicMock()
    fake_pr = MagicMock()
    fake_pr.title = "Add feature"
    fake_pr.body = ""
    fake_file = MagicMock()
    fake_file.filename = "x.py"
    fake_file.patch = "@@ -1 +1 @@\n+hello"
    fake_pr.get_files.return_value = [fake_file]
    fake_repo.get_pull.return_value = fake_pr

    with (
        patch("agents.pr_describer.gh.repo", return_value=fake_repo),
        patch("agents.pr_describer.prompts.load", return_value="sys"),
        patch("agents.pr_describer.run_agent", new=AsyncMock()) as mock_run,
    ):
        mock_run.return_value = MagicMock(
            messages=[{"type": "text", "text": "## Summary\n\nDid a thing."}],
            stopped_reason="complete",
        )
        rc = await fill_pr_description(42, dry_run=False)

    assert rc == 0
    fake_pr.edit.assert_called_once()
    new_body = fake_pr.edit.call_args.kwargs["body"]
    assert "Summary" in new_body


@pytest.mark.asyncio
async def test_fill_pr_description_dry_run_skips_edit() -> None:
    fake_repo = MagicMock()
    fake_pr = MagicMock()
    fake_pr.title = "x"
    fake_pr.body = ""
    fake_file = MagicMock(filename="a.py", patch="@@ +1 @@\n+x")
    fake_pr.get_files.return_value = [fake_file]
    fake_repo.get_pull.return_value = fake_pr

    with (
        patch("agents.pr_describer.gh.repo", return_value=fake_repo),
        patch("agents.pr_describer.prompts.load", return_value="sys"),
        patch("agents.pr_describer.run_agent", new=AsyncMock()) as mock_run,
    ):
        mock_run.return_value = MagicMock(
            messages=[{"type": "text", "text": "draft"}],
            stopped_reason="complete",
        )
        rc = await fill_pr_description(42, dry_run=True)

    assert rc == 0
    fake_pr.edit.assert_not_called()
