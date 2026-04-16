from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents import test_triage


def _mock_run_agent(text: str) -> AsyncMock:
    return AsyncMock(return_value=MagicMock(messages=[{"type": "text", "text": text}]))


@pytest.mark.asyncio
async def test_assertion_error_is_real_bug() -> None:
    response = "CATEGORY: REAL_BUG\nEXPLANATION: Assertion in changed file failed.\nACTION: fix"
    with patch("agents.test_triage.run_agent", _mock_run_agent(response)):
        category, action = await test_triage.categorize(
            "AssertionError: expected 1 got 2", ["agents/src/agents/foo.py"]
        )
    assert category == "REAL_BUG"
    assert action == "fix"


@pytest.mark.asyncio
async def test_timeout_is_environment() -> None:
    response = "CATEGORY: ENVIRONMENT\nEXPLANATION: Network timeout unrelated to code change.\nACTION: escalate"
    with patch("agents.test_triage.run_agent", _mock_run_agent(response)):
        category, action = await test_triage.categorize(
            "ConnectionError: timed out", ["agents/src/agents/bar.py"]
        )
    assert category == "ENVIRONMENT"
    assert action == "escalate"


@pytest.mark.asyncio
async def test_import_error_in_unchanged_file_is_unrelated() -> None:
    response = "CATEGORY: UNRELATED\nEXPLANATION: Import error in untouched file.\nACTION: skip"
    with patch("agents.test_triage.run_agent", _mock_run_agent(response)):
        category, action = await test_triage.categorize(
            "ImportError: cannot import name 'X'", ["agents/src/agents/new_feature.py"]
        )
    assert category == "UNRELATED"
    assert action == "skip"


@pytest.mark.asyncio
async def test_flaky_recommends_retry() -> None:
    response = "CATEGORY: FLAKY\nEXPLANATION: Timing-sensitive test that sometimes fails.\nACTION: retry"
    with patch("agents.test_triage.run_agent", _mock_run_agent(response)):
        category, action = await test_triage.categorize(
            "FAILED tests/test_race.py::test_concurrent - AssertionError",
            ["agents/src/agents/baz.py"],
        )
    assert category == "FLAKY"
    assert action == "retry"
