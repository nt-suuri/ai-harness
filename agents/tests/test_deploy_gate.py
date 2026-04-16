from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents import deploy_gate


@pytest.mark.asyncio
async def test_low_risk_new_file_deploys() -> None:
    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text", "text": "DECISION: DEPLOY\nRISK: low\nREASON: New file only, no existing edits.",
    }]))
    with (
        patch("agents.deploy_gate.run_agent", fake_llm),
        patch("agents.deploy_gate.subprocess.run", return_value=MagicMock(stdout="new.py | 10 +\n")),
        patch("agents.deploy_gate.gh.repo") as mock_repo,
    ):
        mock_wf = MagicMock()
        mock_wf.get_runs.return_value = []
        mock_repo.return_value.get_workflow.return_value = mock_wf
        result = await deploy_gate.assess("abc123")
    assert result == "deploy"


@pytest.mark.asyncio
async def test_high_risk_security_change_holds() -> None:
    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text", "text": "DECISION: HOLD\nRISK: high\nREASON: Touches security.py auth middleware.",
    }]))
    with (
        patch("agents.deploy_gate.run_agent", fake_llm),
        patch("agents.deploy_gate.subprocess.run", return_value=MagicMock(stdout="security.py | 20 +-\n")),
        patch("agents.deploy_gate.gh.repo") as mock_repo,
    ):
        mock_wf = MagicMock()
        mock_wf.get_runs.return_value = []
        mock_repo.return_value.get_workflow.return_value = mock_wf
        result = await deploy_gate.assess("abc123")
    assert result == "hold"


@pytest.mark.asyncio
async def test_medium_risk_deploys_with_watch() -> None:
    fake_llm = AsyncMock(return_value=MagicMock(messages=[{
        "type": "text", "text": "DECISION: DEPLOY_AND_WATCH\nRISK: medium\nREASON: New endpoint, 80 lines.",
    }]))
    with (
        patch("agents.deploy_gate.run_agent", fake_llm),
        patch("agents.deploy_gate.subprocess.run", return_value=MagicMock(stdout="api.py | 80 +\n")),
        patch("agents.deploy_gate.gh.repo") as mock_repo,
    ):
        mock_wf = MagicMock()
        mock_wf.get_runs.return_value = []
        mock_repo.return_value.get_workflow.return_value = mock_wf
        result = await deploy_gate.assess("abc123")
    assert result == "deploy_and_watch"
