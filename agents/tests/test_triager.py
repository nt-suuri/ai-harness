import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agents.triager import (
    _existing_marker_in_issues,
    _make_marker,
    _parse_severity,
    _severity_label,
    triage_run,
)


def test_make_marker_format() -> None:
    assert _make_marker("1234") == "<sentry-issue-id>1234</sentry-issue-id>"


def test_existing_marker_in_issues_finds_match() -> None:
    issues = [
        MagicMock(body="some text\n<sentry-issue-id>9999</sentry-issue-id>\nmore"),
        MagicMock(body="unrelated"),
    ]
    assert _existing_marker_in_issues(issues, _make_marker("9999")) is True


def test_existing_marker_in_issues_returns_false_when_absent() -> None:
    issues = [MagicMock(body="unrelated"), MagicMock(body="also unrelated")]
    assert _existing_marker_in_issues(issues, _make_marker("404")) is False


def test_existing_marker_in_issues_handles_none_body() -> None:
    issues = [MagicMock(body=None), MagicMock(body="x")]
    assert _existing_marker_in_issues(issues, _make_marker("404")) is False


def test_triage_run_noop_when_sentry_not_configured() -> None:
    with patch.dict(os.environ, {}, clear=True):
        rc = triage_run(24, dry_run=False)
    assert rc == 0


def test_triage_run_creates_new_issues_only() -> None:
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = [
        MagicMock(body="<sentry-issue-id>existing</sentry-issue-id>"),
    ]
    fake_repo.create_issue.return_value = MagicMock(number=99, html_url="https://x")

    fake_sentry_issues = [
        {
            "id": "existing",
            "title": "old known error",
            "culprit": "main.py:10",
            "count": "5",
            "permalink": "https://sentry.io/old",
            "level": "error",
        },
        {
            "id": "newone",
            "title": "ZeroDivisionError",
            "culprit": "math.py:42",
            "count": "1",
            "permalink": "https://sentry.io/new",
            "level": "error",
        },
    ]

    with (
        patch.dict(os.environ, {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p"}, clear=True),
        patch("agents.triager.gh.repo", return_value=fake_repo),
        patch("agents.triager.sentry.list_issues", return_value=fake_sentry_issues),
        patch("agents.triager._score_severity", return_value=5),
    ):
        rc = triage_run(24, dry_run=False)

    assert rc == 0
    fake_repo.create_issue.assert_called_once()
    kwargs = fake_repo.create_issue.call_args.kwargs
    assert "ZeroDivisionError" in kwargs["title"]
    assert "<sentry-issue-id>newone</sentry-issue-id>" in kwargs["body"]
    assert "https://sentry.io/new" in kwargs["body"]
    assert "bug" in kwargs["labels"]
    assert "autotriage" in kwargs["labels"]
    assert any(lbl.startswith("severity:") for lbl in kwargs["labels"])


def test_triage_run_dry_run_skips_create() -> None:
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []
    fake_sentry_issues = [
        {"id": "x", "title": "T", "culprit": "c", "count": "1", "permalink": "u", "level": "error"},
    ]

    with (
        patch.dict(os.environ, {"SENTRY_ORG_SLUG": "o", "SENTRY_PROJECT_SLUG": "p"}, clear=True),
        patch("agents.triager.gh.repo", return_value=fake_repo),
        patch("agents.triager.sentry.list_issues", return_value=fake_sentry_issues),
        patch("agents.triager._score_severity", return_value=5),
    ):
        rc = triage_run(24, dry_run=True)

    assert rc == 0
    fake_repo.create_issue.assert_not_called()


def test_triager_cli_accepts_no_args_with_help_check() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.triager", "--help-check-only"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_triager_cli_accepts_since_hours() -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.triager",
            "--since-hours", "48", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


@pytest.mark.parametrize("hours", ["1", "24", "168"])
def test_triager_cli_accepts_various_since_values(hours: str) -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.triager",
            "--since-hours", hours, "--dry-run", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_severity_label_critical() -> None:
    assert _severity_label(10) == "severity:critical"
    assert _severity_label(8) == "severity:critical"


def test_severity_label_important() -> None:
    assert _severity_label(7) == "severity:important"
    assert _severity_label(4) == "severity:important"


def test_severity_label_minor() -> None:
    assert _severity_label(3) == "severity:minor"
    assert _severity_label(1) == "severity:minor"


def test_parse_severity_basic() -> None:
    assert _parse_severity("Reasoning: x\nSEVERITY: 7") == 7


def test_parse_severity_returns_5_on_no_match() -> None:
    assert _parse_severity("no severity here") == 5


def test_parse_severity_clamps_out_of_range() -> None:
    assert _parse_severity("SEVERITY: 0") == 1
    assert _parse_severity("SEVERITY: 100") == 10


def test_parse_severity_uses_last_match() -> None:
    assert _parse_severity("SEVERITY: 3\nSEVERITY: 9") == 9
