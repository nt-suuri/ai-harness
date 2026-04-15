import json
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
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["uv", "run", "harness", "--help"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    assert result.returncode == 0
    assert "ai-harness operator CLI" in result.stdout


def test_doctor_runs_and_reports() -> None:
    runner = CliRunner()
    fake_repo = MagicMock(full_name="nt-suuri/ai-harness")
    with (
        patch("agents.cli.gh.repo", return_value=fake_repo),
        patch("agents.cli.subprocess.run") as run,
    ):
        run.return_value = MagicMock(stdout='[{"name":"PAUSE_AGENTS","value":""}]', returncode=0)
        result = runner.invoke(cli, ["doctor"])
    assert "checks" in result.output.lower() or "✓" in result.output or "✗" in result.output


def test_logs_command_lists_runs() -> None:
    runner = CliRunner()
    from datetime import UTC, datetime

    fake_run = MagicMock(
        conclusion="success",
        status="completed",
        head_sha="abc1234567",
        created_at=datetime(2026, 4, 14, 12, 0, tzinfo=UTC),
        head_commit=MagicMock(message="feat: a thing"),
    )
    fake_workflow = MagicMock()
    fake_workflow.get_runs.return_value = [fake_run]
    fake_repo = MagicMock()
    fake_repo.get_workflow.return_value = fake_workflow

    with patch("agents.cli.gh.repo", return_value=fake_repo):
        result = runner.invoke(cli, ["logs"])

    assert result.exit_code == 0
    assert "abc1234" in result.output


def test_logs_empty_runs() -> None:
    runner = CliRunner()
    fake_workflow = MagicMock()
    fake_workflow.get_runs.return_value = []
    fake_repo = MagicMock()
    fake_repo.get_workflow.return_value = fake_workflow

    with patch("agents.cli.gh.repo", return_value=fake_repo):
        result = runner.invoke(cli, ["logs", "--workflow", "x.yml"])
    assert result.exit_code == 0
    assert "No runs" in result.output


def test_next_tag_prints_tag_format() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["next-tag"])
    assert result.exit_code == 0
    import re

    assert re.search(r"v\d{4}\.\d{2}\.\d{2}-\d{4}", result.output)


def test_self_test_command_runs() -> None:
    runner = CliRunner()
    fake_result = MagicMock(returncode=0, stdout="usage:", stderr="")
    with (
        patch("agents.cli.subprocess.run", return_value=fake_result),
        patch("agents.canary.run_canary", return_value=0),
    ):
        result = runner.invoke(cli, ["self-test"])
    assert result.exit_code == 0
    assert "All self-tests green" in result.output


def test_self_test_command_reports_failure_on_canary_fail() -> None:
    runner = CliRunner()
    fake_result = MagicMock(returncode=0, stdout="usage:", stderr="")
    with (
        patch("agents.cli.subprocess.run", return_value=fake_result),
        patch("agents.canary.run_canary", return_value=1),
    ):
        result = runner.invoke(cli, ["self-test"])
    assert result.exit_code == 1
    assert "failed" in result.output


def test_verify_command_runs() -> None:
    runner = CliRunner()
    fake_repo = MagicMock()
    fake_repo.get_issues.return_value = []

    fake_resp = MagicMock()
    fake_resp.status = 200
    fake_resp.read.return_value = b'{"status":"pong","sha":"abc1234","env":"local","uptime_seconds":10,"ci":{"success":1,"failure":0},"deploy":{"success":1,"failure":0},"open_autotriage_issues":0}'
    fake_resp.__enter__ = MagicMock(return_value=fake_resp)
    fake_resp.__exit__ = MagicMock(return_value=None)

    def subprocess_side_effect(*args: object, **kwargs: object) -> MagicMock:
        cmd = args[0]
        if isinstance(cmd, list):
            joined = " ".join(cmd)
            if "actions/workflows" in joined:
                return MagicMock(returncode=0, stdout='{"workflows":[{"name":"ci"}]}')
            if "secret" in joined:
                return MagicMock(returncode=0, stdout='[{"name":"RAILWAY_TOKEN"}]')
            if "variable" in joined:
                return MagicMock(returncode=0, stdout='[]')
        return MagicMock(returncode=0, stdout='{}')

    with (
        patch("agents.cli.subprocess.run", side_effect=subprocess_side_effect),
        patch("agents.cli.gh.repo", return_value=fake_repo),
        patch("urllib.request.urlopen", return_value=fake_resp),
    ):
        result = runner.invoke(cli, ["verify"])

    assert result.exit_code == 0
    assert "verify checks green" in result.output


def test_install_mcp_writes_user_config(tmp_path, monkeypatch) -> None:
    """In user scope with dry-run, output shows config without writing."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    runner = CliRunner()
    with patch("agents.cli.subprocess.run") as run:
        run.return_value = MagicMock(stdout=str(tmp_path) + "\n", returncode=0)
        result = runner.invoke(cli, ["install-mcp", "--scope", "user", "--dry-run"])

    assert result.exit_code == 0
    assert "DRY RUN" in result.output or "ai-harness" in result.output


def test_install_mcp_dry_run_does_not_write(tmp_path, monkeypatch) -> None:
    """In dry-run, no file should be written."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    runner = CliRunner()
    with patch("agents.cli.subprocess.run") as run:
        run.return_value = MagicMock(stdout=str(tmp_path) + "\n", returncode=0)
        result = runner.invoke(cli, ["install-mcp", "--scope", "project", "--dry-run"])

    assert result.exit_code == 0
    assert not (tmp_path / ".mcp.json").exists()


def test_install_mcp_writes_project_config(tmp_path, monkeypatch) -> None:
    """In project scope without dry-run, .mcp.json is created."""
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    with patch("agents.cli.subprocess.run") as run:
        run.return_value = MagicMock(stdout=str(tmp_path) + "\n", returncode=0)
        result = runner.invoke(cli, ["install-mcp", "--scope", "project"])

    assert result.exit_code == 0
    config_file = tmp_path / ".mcp.json"
    assert config_file.exists()
    config = json.loads(config_file.read_text())
    assert "ai-harness" in config["mcpServers"]
    assert config["mcpServers"]["ai-harness"]["command"] == "uv"


def test_uninstall_mcp_when_not_registered(tmp_path, monkeypatch) -> None:
    """Uninstalling when entry doesn't exist prints 'nothing to do'."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    with patch("agents.cli.subprocess.run") as run:
        run.return_value = MagicMock(stdout=str(tmp_path) + "\n", returncode=0)
        result = runner.invoke(cli, ["uninstall-mcp", "--scope", "project"])
    assert result.exit_code == 0
    assert "nothing" in result.output.lower() or "no config" in result.output.lower()


def test_uninstall_mcp_removes_entry(tmp_path, monkeypatch) -> None:
    """Uninstalling removes ai-harness entry and preserves other servers."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / ".mcp.json"
    config_file.write_text(json.dumps({
        "mcpServers": {
            "ai-harness": {"command": "uv"},
            "other": {"command": "node"},
        },
    }))

    runner = CliRunner()
    with patch("agents.cli.subprocess.run") as run:
        run.return_value = MagicMock(stdout=str(tmp_path) + "\n", returncode=0)
        result = runner.invoke(cli, ["uninstall-mcp", "--scope", "project"])

    assert result.exit_code == 0
    assert "Removed" in result.output
    config = json.loads(config_file.read_text())
    assert "ai-harness" not in config["mcpServers"]
    assert "other" in config["mcpServers"]


def test_uninstall_mcp_dry_run(tmp_path, monkeypatch) -> None:
    """Dry-run prints config without modifying file."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / ".mcp.json"
    config_file.write_text(json.dumps({"mcpServers": {"ai-harness": {"command": "uv"}}}))

    runner = CliRunner()
    with patch("agents.cli.subprocess.run") as run:
        run.return_value = MagicMock(stdout=str(tmp_path) + "\n", returncode=0)
        result = runner.invoke(cli, ["uninstall-mcp", "--scope", "project", "--dry-run"])

    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    config_after = json.loads(config_file.read_text())
    assert "ai-harness" in config_after["mcpServers"]
