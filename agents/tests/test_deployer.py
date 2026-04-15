import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agents import deployer
from agents.deployer import _detect_spike, watch_post_deploy
from agents.lib import labels


def test_deployer_cli_requires_after_sha() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.deployer", "--window-minutes", "10"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_deployer_cli_rejects_negative_window() -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.deployer",
            "--after-sha", "abc", "--window-minutes", "-5", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 1, 2)


@pytest.mark.parametrize("window", ["5", "10", "30"])
def test_deployer_cli_accepts_valid_window(window: str) -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.deployer",
            "--after-sha", "abc123", "--window-minutes", window, "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_detect_spike_returns_false_when_counts_low() -> None:
    assert _detect_spike(baseline_per_min=2.0, post_count=3, window_minutes=10) is False


def test_detect_spike_returns_true_when_3x_and_over_floor() -> None:
    assert _detect_spike(baseline_per_min=1.0, post_count=40, window_minutes=10) is True


def test_detect_spike_ignores_absolute_floor_of_five() -> None:
    assert _detect_spike(baseline_per_min=0.0, post_count=3, window_minutes=10) is False


def test_detect_spike_requires_both_ratio_and_floor() -> None:
    assert _detect_spike(baseline_per_min=0.1, post_count=6, window_minutes=10) is True


def test_watch_post_deploy_dry_run_skips_issue_creation() -> None:
    fake_repo = MagicMock()
    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.count_events_since", side_effect=[1, 30]),
        patch("agents.deployer.time.sleep") as fake_sleep,
        patch.dict("os.environ", {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p"}),
    ):
        rc = watch_post_deploy("abcd1234", 10, dry_run=True)

    assert rc == 1
    fake_repo.create_issue.assert_not_called()
    fake_sleep.assert_called_once()


def test_watch_post_deploy_opens_issue_on_spike() -> None:
    fake_repo = MagicMock()
    fake_repo.create_issue.return_value = MagicMock(number=42, html_url="https://x/42")

    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.count_events_since", side_effect=[1, 30]),
        patch("agents.deployer.time.sleep"),
        patch.dict("os.environ", {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p"}),
    ):
        rc = watch_post_deploy("abcd1234", 10, dry_run=False)

    assert rc == 1
    fake_repo.create_issue.assert_called_once()
    kwargs = fake_repo.create_issue.call_args.kwargs
    assert "abcd1234" in kwargs["title"] or "abcd1234" in kwargs["body"]
    labels = kwargs.get("labels", [])
    assert "regression" in labels


def test_watch_post_deploy_returns_zero_when_healthy() -> None:
    fake_repo = MagicMock()
    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.count_events_since", side_effect=[10, 3]),
        patch("agents.deployer.time.sleep"),
        patch.dict("os.environ", {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p"}),
    ):
        rc = watch_post_deploy("abcd1234", 10, dry_run=False)

    assert rc == 0
    fake_repo.create_issue.assert_not_called()


def test_watch_post_deploy_noop_when_sentry_not_configured() -> None:
    with patch.dict("os.environ", {}, clear=True):
        rc = watch_post_deploy("sha", 10, dry_run=False)
    assert rc == 0


def test_auto_revert_calls_git_revert_and_push() -> None:
    from agents.deployer import _auto_revert

    call_log: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: object) -> MagicMock:
        call_log.append(args)
        if args[:2] == ["git", "rev-parse"]:
            return MagicMock(stdout="newsha1234567\n", returncode=0)
        return MagicMock(stdout="", returncode=0)

    with patch("agents.deployer.subprocess.run", side_effect=fake_run):
        result = _auto_revert("deadbeef")

    assert result == "newsha1234567"
    assert any("revert" in " ".join(a) for a in call_log)
    assert any("push" in " ".join(a) for a in call_log)


def test_auto_revert_returns_none_on_failure() -> None:
    import subprocess as sp

    from agents.deployer import _auto_revert

    err = sp.CalledProcessError(1, ["git"], stderr="conflict")
    with patch("agents.deployer.subprocess.run", side_effect=err):
        result = _auto_revert("deadbeef")
    assert result is None


def test_watch_post_deploy_auto_rolls_back_when_flag_set() -> None:
    fake_repo = MagicMock()
    fake_repo.create_issue.return_value = MagicMock(number=42)

    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.count_events_since", side_effect=[1, 30]),
        patch("agents.deployer.time.sleep"),
        patch("agents.deployer._auto_revert", return_value="revertsha1") as revert,
        patch.dict("os.environ", {
            "SENTRY_ORG_SLUG": "o",
            "SENTRY_PROJECT_SLUG": "p",
            "AUTO_ROLLBACK": "true",
        }, clear=True),
    ):
        rc = watch_post_deploy("abcd1234", 10, dry_run=False)

    assert rc == 1
    revert.assert_called_once_with("abcd1234")
    fake_repo.create_issue.return_value.create_comment.assert_called_once()


def test_watch_post_deploy_no_auto_revert_when_flag_unset() -> None:
    fake_repo = MagicMock()
    fake_repo.create_issue.return_value = MagicMock(number=42)

    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.count_events_since", side_effect=[1, 30]),
        patch("agents.deployer.time.sleep"),
        patch("agents.deployer._auto_revert") as revert,
        patch.dict("os.environ", {
            "SENTRY_ORG_SLUG": "o",
            "SENTRY_PROJECT_SLUG": "p",
        }, clear=True),
    ):
        rc = watch_post_deploy("abcd1234", 10, dry_run=False)

    assert rc == 1
    revert.assert_not_called()


def test_regression_issue_gets_agent_build_label() -> None:
    fake_repo = MagicMock()
    fake_repo.create_issue.return_value = MagicMock(number=99, html_url="u")

    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.count_events_since", side_effect=[1, 50]),
        patch("agents.deployer.time.sleep"),
        patch.dict(os.environ, {
            "SENTRY_AUTH_TOKEN": "t",
            "SENTRY_ORG_SLUG": "o",
            "SENTRY_PROJECT_SLUG": "p",
        }, clear=True),
    ):
        deployer.watch_post_deploy("abc123", 10, dry_run=False)

    applied = fake_repo.create_issue.call_args.kwargs["labels"]
    assert labels.AGENT_BUILD in applied
    assert labels.REGRESSION in applied
