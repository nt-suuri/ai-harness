import subprocess
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from agents.stale import _is_stale, run_stale_close


def test_cli_runs_with_dry_run() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.stale", "--dry-run", "--help-check-only"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_cli_accepts_stale_days() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.stale", "--stale-days", "30", "--help-check-only"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_is_stale_true_when_old() -> None:
    old = datetime.now(UTC) - timedelta(days=20)
    assert _is_stale(old, threshold_days=14) is True


def test_is_stale_false_when_recent() -> None:
    recent = datetime.now(UTC) - timedelta(days=3)
    assert _is_stale(recent, threshold_days=14) is False


def test_is_stale_naive_datetime_treated_as_utc() -> None:
    naive_old = (datetime.now(UTC) - timedelta(days=20)).replace(tzinfo=None)
    assert _is_stale(naive_old, threshold_days=14) is True


def test_run_stale_close_closes_old_issues() -> None:
    fake_repo = MagicMock()
    old_issue = MagicMock(number=1, updated_at=datetime.now(UTC) - timedelta(days=30))
    new_issue = MagicMock(number=2, updated_at=datetime.now(UTC) - timedelta(days=2))
    fake_repo.get_issues.return_value = [old_issue, new_issue]

    with patch("agents.stale.gh.repo", return_value=fake_repo):
        rc = run_stale_close(stale_days=14, dry_run=False)

    assert rc == 0
    old_issue.create_comment.assert_called_once()
    old_issue.edit.assert_called_once_with(state="closed", state_reason="not_planned")
    new_issue.edit.assert_not_called()


def test_run_stale_close_dry_run_skips_writes() -> None:
    fake_repo = MagicMock()
    old_issue = MagicMock(number=1, updated_at=datetime.now(UTC) - timedelta(days=30))
    fake_repo.get_issues.return_value = [old_issue]

    with patch("agents.stale.gh.repo", return_value=fake_repo):
        rc = run_stale_close(stale_days=14, dry_run=True)

    assert rc == 0
    old_issue.create_comment.assert_not_called()
    old_issue.edit.assert_not_called()
