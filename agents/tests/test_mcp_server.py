from unittest.mock import MagicMock, patch

import pytest


def test_mcp_module_imports() -> None:
    from agents import mcp_server

    assert hasattr(mcp_server, "mcp")
    assert hasattr(mcp_server, "main")


@pytest.mark.asyncio
async def test_status_tool_returns_shape() -> None:
    from agents.mcp_server import status

    fake_workflow = MagicMock()
    fake_workflow.get_runs.return_value = [
        MagicMock(conclusion="success"),
        MagicMock(conclusion="success"),
        MagicMock(conclusion="failure"),
    ]
    fake_repo = MagicMock()
    fake_repo.get_workflow.return_value = fake_workflow
    fake_repo.get_issues.return_value = []

    with patch("agents.mcp_server.gh.repo", return_value=fake_repo):
        result = await status()

    assert "ci" in result
    assert "deploy" in result
    assert "open_autotriage_issues" in result
    assert result["ci"]["success"] == 2
    assert result["ci"]["failure"] == 1


@pytest.mark.asyncio
async def test_triage_dry_run_returns_string() -> None:
    from agents.mcp_server import triage_dry_run

    with patch("agents.triager.triage_run", return_value=0):
        out = await triage_dry_run(24)

    assert isinstance(out, str)


@pytest.mark.asyncio
async def test_pause_agents_invokes_gh_variable_set() -> None:
    from agents.mcp_server import pause_agents

    with patch("agents.mcp_server.subprocess.run") as run:
        result = await pause_agents()

    assert "PAUSE_AGENTS" in result
    run.assert_called_once()
    args = run.call_args.args[0]
    assert "set" in args
    assert "true" in args


@pytest.mark.asyncio
async def test_resume_agents_invokes_gh_variable_delete() -> None:
    from agents.mcp_server import resume_agents

    with patch("agents.mcp_server.subprocess.run") as run:
        result = await resume_agents()

    assert "cleared" in result.lower()
    run.assert_called_once()
    args = run.call_args.args[0]
    assert "delete" in args
