import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.issue_labeler import ALLOWED_LABELS, _extract_labels, label_issue


def test_cli_help() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.issue_labeler", "--issue", "1", "--dry-run", "--help-check-only"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_cli_requires_issue() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.issue_labeler", "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_extract_labels_finds_json_array() -> None:
    body = 'My reasoning here.\n\n["area:api", "priority:high"]'
    assert _extract_labels(body) == ["area:api", "priority:high"]


def test_extract_labels_filters_invalid() -> None:
    body = '["area:api", "made-up-label", "priority:high"]'
    labels = _extract_labels(body)
    assert "area:api" in labels
    assert "priority:high" in labels
    assert "made-up-label" not in labels


def test_extract_labels_handles_missing() -> None:
    body = "No JSON here."
    assert _extract_labels(body) == []


def test_extract_labels_handles_invalid_json() -> None:
    body = "Stuff\n[invalid json"
    assert _extract_labels(body) == []


def test_allowed_labels_includes_known() -> None:
    assert "area:api" in ALLOWED_LABELS
    assert "priority:high" in ALLOWED_LABELS


@pytest.mark.asyncio
async def test_label_issue_applies_returned_labels() -> None:
    fake_repo = MagicMock()
    fake_issue = MagicMock()
    fake_issue.title = "Bug in /api/foo"
    fake_issue.body = "It crashes"
    fake_issue.labels = []  # already labelled?
    fake_repo.get_issue.return_value = fake_issue

    with (
        patch("agents.issue_labeler.gh.repo", return_value=fake_repo),
        patch("agents.issue_labeler.prompts.load", return_value="sys"),
        patch("agents.issue_labeler.run_agent", new=AsyncMock()) as mock_run,
    ):
        mock_run.return_value = MagicMock(
            messages=[{"type": "text", "text": 'reasoning\n\n["area:api", "priority:high"]'}],
            stopped_reason="complete",
        )
        rc = await label_issue(7, dry_run=False)

    assert rc == 0
    fake_issue.add_to_labels.assert_called_once()
    args = fake_issue.add_to_labels.call_args.args
    assert "area:api" in args
    assert "priority:high" in args


@pytest.mark.asyncio
async def test_label_issue_dry_run_skips_apply() -> None:
    fake_repo = MagicMock()
    fake_issue = MagicMock()
    fake_issue.title = "x"
    fake_issue.body = "y"
    fake_issue.labels = []
    fake_repo.get_issue.return_value = fake_issue

    with (
        patch("agents.issue_labeler.gh.repo", return_value=fake_repo),
        patch("agents.issue_labeler.prompts.load", return_value="sys"),
        patch("agents.issue_labeler.run_agent", new=AsyncMock()) as mock_run,
    ):
        mock_run.return_value = MagicMock(
            messages=[{"type": "text", "text": '["area:web"]'}],
            stopped_reason="complete",
        )
        rc = await label_issue(7, dry_run=True)

    assert rc == 0
    fake_issue.add_to_labels.assert_not_called()


@pytest.mark.asyncio
async def test_label_issue_skips_already_labelled() -> None:
    fake_repo = MagicMock()
    fake_issue = MagicMock()
    fake_issue.title = "x"
    fake_issue.body = "y"
    # PyGithub returns Label objects with .name
    label_obj = MagicMock()
    label_obj.name = "area:api"
    fake_issue.labels = [label_obj]
    fake_repo.get_issue.return_value = fake_issue

    with patch("agents.issue_labeler.gh.repo", return_value=fake_repo):
        rc = await label_issue(7, dry_run=False)

    assert rc == 0
    fake_issue.add_to_labels.assert_not_called()
