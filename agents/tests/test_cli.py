import subprocess
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from agents.cli import cli


def test_cli_help_lists_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ["status", "review", "plan", "triage", "healthcheck", "stale", "canary", "pause", "resume"]:
        assert cmd in result.output


def test_status_command_prints_counts() -> None:
    runner = CliRunner()
    fake_repo = MagicMock()
    fake_workflow = MagicMock()
    fake_workflow.get_runs.return_value = [
        MagicMock(conclusion="success"),
        MagicMock(conclusion="failure"),
    ]
    fake_repo.get_workflow.return_value = fake_workflow
    fake_repo.get_issues.return_value = []

    with patch("agents.cli.gh.repo", return_value=fake_repo):
        result = runner.invoke(cli, ["status"])

    assert result.exit_code == 0
    assert "CI:" in result.output
    assert "Deploy:" in result.output
    assert "Open autotriage" in result.output


def test_pause_invokes_gh_variable_set() -> None:
    runner = CliRunner()
    with patch("agents.cli.subprocess.run") as run:
        result = runner.invoke(cli, ["pause"])
    assert result.exit_code == 0
    run.assert_called_once()
    args = run.call_args.args[0]
    assert "PAUSE_AGENTS" in args
    assert "true" in args


def test_resume_invokes_gh_variable_delete() -> None:
    runner = CliRunner()
    with patch("agents.cli.subprocess.run") as run:
        result = runner.invoke(cli, ["resume"])
    assert result.exit_code == 0
    run.assert_called_once()
    args = run.call_args.args[0]
    assert "delete" in args
    assert "PAUSE_AGENTS" in args


def test_review_command_calls_review_pr() -> None:
    runner = CliRunner()

    async def fake_review(*args: object, **kwargs: object) -> int:
        return 0

    with patch("agents.reviewer.review_pr", side_effect=fake_review):
        result = runner.invoke(cli, ["review", "--pr", "42", "--pass", "quality"])
    assert result.exit_code == 0


def test_triage_command_calls_triage_run() -> None:
    runner = CliRunner()
    with patch("agents.triager.triage_run", return_value=0) as tr:
        result = runner.invoke(cli, ["triage", "--dry-run"])
    assert result.exit_code == 0
    tr.assert_called_once()


def test_canary_command_runs() -> None:
    runner = CliRunner()
    with patch("agents.canary.run_canary", return_value=0) as fn:
        result = runner.invoke(cli, ["canary"])
    assert result.exit_code == 0
    fn.assert_called_once()


def test_harness_entry_point_works() -> None:
    """Verify `harness --help` works after `uv sync` registers the entry point."""
    result = subprocess.run(
        ["uv", "run", "harness", "--help"],
        capture_output=True,
        text=True,
        cwd="/Users/nt-suuri/workspace/lab/ai-harness",
    )
    assert result.returncode == 0
    assert "ai-harness operator CLI" in result.stdout
