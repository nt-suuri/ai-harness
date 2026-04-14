import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.reviewer import _extract_verdict, review_pr


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
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.reviewer",
            "--pass", pass_name, "--pr", "1", "--dry-run", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_extract_verdict_approved() -> None:
    body = "Lots of analysis here.\n\nVERDICT: APPROVED"
    assert _extract_verdict(body) == "success"


def test_extract_verdict_rejected() -> None:
    body = "Found a bug.\n\nVERDICT: REJECTED"
    assert _extract_verdict(body) == "failure"


def test_extract_verdict_missing_defaults_failure() -> None:
    body = "I reviewed but forgot to say a verdict."
    assert _extract_verdict(body) == "failure"


@pytest.mark.asyncio
async def test_review_pr_dry_run_returns_rc_from_verdict() -> None:
    fake_repo = MagicMock()
    fake_pr = MagicMock()
    fake_pr.title = "Test PR"
    fake_file = MagicMock()
    fake_file.filename = "x.py"
    fake_file.patch = "@@ -0,0 +1 @@\n+hello"
    fake_pr.get_files.return_value = [fake_file]
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
    fake_pr.create_issue_comment.assert_not_called()


@pytest.mark.asyncio
async def test_review_pr_live_posts_comment_and_sets_status() -> None:
    fake_repo = MagicMock()
    fake_pr = MagicMock()
    fake_pr.title = "Test PR"
    fake_file = MagicMock()
    fake_file.filename = "y.py"
    fake_file.patch = "@@ -1 +1 @@\n-old\n+new"
    fake_pr.get_files.return_value = [fake_file]
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


def test_fetch_diff_concatenates_per_file_patches() -> None:
    from agents.reviewer import _fetch_diff

    file_a = MagicMock()
    file_a.filename = "apps/api/main.py"
    file_a.patch = "@@ -1 +1 @@\n-foo\n+bar"

    file_b = MagicMock()
    file_b.filename = "apps/web/App.tsx"
    file_b.patch = "@@ -10 +10 @@\n-old\n+new"

    pr = MagicMock()
    pr.get_files.return_value = [file_a, file_b]

    diff = _fetch_diff(pr)
    assert "apps/api/main.py" in diff
    assert "apps/web/App.tsx" in diff
    assert "-foo" in diff
    assert "+bar" in diff
    assert "-old" in diff
    assert "+new" in diff


def test_fetch_diff_skips_files_without_patch() -> None:
    from agents.reviewer import _fetch_diff

    binary = MagicMock()
    binary.filename = "logo.png"
    binary.patch = None

    text = MagicMock()
    text.filename = "x.py"
    text.patch = "@@ -1 +1 @@\n+hi"

    pr = MagicMock()
    pr.get_files.return_value = [binary, text]

    diff = _fetch_diff(pr)
    assert "logo.png" not in diff
    assert "x.py" in diff
    assert "+hi" in diff
