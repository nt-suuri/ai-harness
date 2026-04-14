import os
from unittest.mock import MagicMock, patch

from agents.healthcheck import _build_summary, _summarize, run_healthcheck


def test_build_summary_includes_counts() -> None:
    summary = _build_summary(
        date_str="2026-04-14",
        ci_success=12,
        ci_failure=2,
        deploy_success=3,
        deploy_failure=0,
        sentry_event_count=5,
    )
    assert "2026-04-14" in summary
    assert "12" in summary
    assert "2" in summary
    assert "5" in summary


def test_run_healthcheck_returns_zero() -> None:
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []
    fake_repo.create_issue.return_value = MagicMock(number=1, html_url="https://x")
    fake_workflow = MagicMock()
    fake_workflow.get_runs.return_value = []
    fake_repo.get_workflow.return_value = fake_workflow

    with (
        patch("agents.healthcheck.gh.repo", return_value=fake_repo),
        patch("agents.healthcheck.sentry.count_events_since", return_value=0),
        patch("agents.healthcheck._summarize", return_value=""),
        patch.dict(os.environ, {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p"}, clear=True),
    ):
        rc = run_healthcheck(dry_run=False)
    assert rc == 0


def test_run_healthcheck_dry_run_skips_writes() -> None:
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []
    fake_workflow = MagicMock()
    fake_workflow.get_runs.return_value = []
    fake_repo.get_workflow.return_value = fake_workflow

    with (
        patch("agents.healthcheck.gh.repo", return_value=fake_repo),
        patch("agents.healthcheck.sentry.count_events_since", return_value=0),
        patch("agents.healthcheck.email.send_email") as send,
        patch("agents.healthcheck._summarize", return_value=""),
        patch.dict(os.environ, {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p"}, clear=True),
    ):
        rc = run_healthcheck(dry_run=True)

    assert rc == 0
    fake_repo.create_issue.assert_not_called()
    send.assert_not_called()


def test_run_healthcheck_sends_email_when_configured() -> None:
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []
    fake_repo.create_issue.return_value = MagicMock(number=1)
    fake_workflow = MagicMock()
    fake_workflow.get_runs.return_value = []
    fake_repo.get_workflow.return_value = fake_workflow

    with (
        patch("agents.healthcheck.gh.repo", return_value=fake_repo),
        patch("agents.healthcheck.sentry.count_events_since", return_value=0),
        patch("agents.healthcheck.email.send_email", return_value="msg1") as send,
        patch("agents.healthcheck._summarize", return_value=""),
        patch.dict(
            os.environ,
            {
                "SENTRY_ORG_SLUG": "o",
                "SENTRY_PROJECT_SLUG": "p",
                "RESEND_API_KEY": "rk",
                "HEALTHCHECK_TO_EMAIL": "dev@x.com",
            },
            clear=True,
        ),
    ):
        rc = run_healthcheck(dry_run=False)
    assert rc == 0
    send.assert_called_once()


def test_run_healthcheck_skips_email_when_no_recipient() -> None:
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []
    fake_repo.create_issue.return_value = MagicMock(number=1)
    fake_workflow = MagicMock()
    fake_workflow.get_runs.return_value = []
    fake_repo.get_workflow.return_value = fake_workflow

    with (
        patch("agents.healthcheck.gh.repo", return_value=fake_repo),
        patch("agents.healthcheck.sentry.count_events_since", return_value=0),
        patch("agents.healthcheck.email.send_email") as send,
        patch("agents.healthcheck._summarize", return_value=""),
        patch.dict(
            os.environ,
            {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p", "RESEND_API_KEY": "rk"},
            clear=True,
        ),
    ):
        rc = run_healthcheck(dry_run=False)
    assert rc == 0
    send.assert_not_called()


def test_build_summary_with_intro() -> None:
    summary = _build_summary(
        date_str="2026-04-14",
        ci_success=10,
        ci_failure=0,
        deploy_success=2,
        deploy_failure=0,
        sentry_event_count=0,
        intro="Healthy day with no issues.",
    )
    assert "Healthy day" in summary
    assert "## 2026-04-14" in summary
    assert "10 success" in summary


def test_build_summary_without_intro_unchanged() -> None:
    summary = _build_summary(
        date_str="2026-04-14",
        ci_success=10,
        ci_failure=0,
        deploy_success=2,
        deploy_failure=0,
        sentry_event_count=0,
    )
    assert "## 2026-04-14\n\n-" in summary


def test_summarize_returns_empty_when_no_api_key() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert _summarize({"date_str": "2026-04-14"}) == ""
