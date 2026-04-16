import os
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents import deployer
from agents.deployer import watch_post_deploy
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


def test_watch_post_deploy_dry_run_skips_issue_creation() -> None:
    fake_repo = MagicMock()
    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.list_events", return_value=[{"title": "err"}]),
        patch("agents.deployer.time.sleep"),
        patch("agents.deployer.asyncio.run", return_value=("REVERT", "new bug found")),
        patch.dict("os.environ", {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p"}),
    ):
        rc = watch_post_deploy("abcd1234", 10, dry_run=True)

    assert rc == 1
    fake_repo.create_issue.assert_not_called()


def test_watch_post_deploy_opens_issue_on_revert() -> None:
    fake_repo = MagicMock()
    fake_repo.create_issue.return_value = MagicMock(number=42, html_url="https://x/42")

    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.list_events", return_value=[{"title": "err"}]),
        patch("agents.deployer.time.sleep"),
        patch("agents.deployer.asyncio.run", return_value=("REVERT", "new bug")),
        patch.dict("os.environ", {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p"}),
    ):
        rc = watch_post_deploy("abcd1234", 10, dry_run=False)

    assert rc == 1
    fake_repo.create_issue.assert_called_once()
    kwargs = fake_repo.create_issue.call_args.kwargs
    assert "abcd1234" in kwargs["title"] or "abcd1234" in kwargs["body"]
    assert "regression" in kwargs.get("labels", [])


def test_watch_post_deploy_opens_issue_on_alert() -> None:
    fake_repo = MagicMock()
    fake_repo.create_issue.return_value = MagicMock(number=43, html_url="https://x/43")

    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.list_events", return_value=[]),
        patch("agents.deployer.time.sleep"),
        patch("agents.deployer.asyncio.run", return_value=("ALERT", "ambiguous spike")),
        patch.dict("os.environ", {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p"}),
    ):
        rc = watch_post_deploy("abcd1234", 10, dry_run=False)

    assert rc == 1
    fake_repo.create_issue.assert_called_once()


def test_watch_post_deploy_returns_zero_on_ignore() -> None:
    fake_repo = MagicMock()
    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.list_events", return_value=[]),
        patch("agents.deployer.time.sleep"),
        patch("agents.deployer.asyncio.run", return_value=("IGNORE", "all clear")),
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


def test_watch_post_deploy_auto_rolls_back_on_revert_decision() -> None:
    fake_repo = MagicMock()
    fake_repo.create_issue.return_value = MagicMock(number=42)

    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.list_events", return_value=[]),
        patch("agents.deployer.time.sleep"),
        patch("agents.deployer.asyncio.run", return_value=("REVERT", "new errors")),
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


def test_watch_post_deploy_no_auto_revert_on_alert() -> None:
    fake_repo = MagicMock()
    fake_repo.create_issue.return_value = MagicMock(number=42)

    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.list_events", return_value=[]),
        patch("agents.deployer.time.sleep"),
        patch("agents.deployer.asyncio.run", return_value=("ALERT", "ambiguous")),
        patch("agents.deployer._auto_revert") as revert,
        patch.dict("os.environ", {
            "SENTRY_ORG_SLUG": "o",
            "SENTRY_PROJECT_SLUG": "p",
            "AUTO_ROLLBACK": "true",
        }, clear=True),
    ):
        rc = watch_post_deploy("abcd1234", 10, dry_run=False)

    assert rc == 1
    # ALERT decision should not trigger auto-revert even with flag set
    revert.assert_not_called()


def test_regression_issue_gets_agent_build_label() -> None:
    fake_repo = MagicMock()
    fake_repo.create_issue.return_value = MagicMock(number=99, html_url="u")

    with (
        patch("agents.deployer.gh.repo", return_value=fake_repo),
        patch("agents.deployer.sentry.list_events", return_value=[]),
        patch("agents.deployer.time.sleep"),
        patch("agents.deployer.asyncio.run", return_value=("REVERT", "bug found")),
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
