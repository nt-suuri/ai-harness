import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.lib.anthropic import AgentResult, run_agent


def _async_iter(items: list[object]):
    async def _gen():
        for item in items:
            yield item

    return _gen()


@pytest.mark.asyncio
async def test_run_agent_returns_messages_and_complete_reason() -> None:
    fake_messages = [{"role": "assistant", "text": "hi"}, {"role": "assistant", "text": "bye"}]
    with patch("agents.lib.anthropic._sdk_query") as m:
        m.return_value = _async_iter(fake_messages)
        result = await run_agent("do the thing", system="you are helpful")
    assert isinstance(result, AgentResult)
    assert result.messages == fake_messages
    assert result.stopped_reason == "complete"


@pytest.mark.asyncio
async def test_run_agent_passes_max_turns_and_allowed_tools_to_sdk() -> None:
    with patch("agents.lib.anthropic._sdk_query") as m:
        m.return_value = _async_iter([])
        await run_agent(
            "p",
            system="s",
            max_turns=5,
            allowed_tools=["Read", "Grep"],
        )
    call_kwargs = m.call_args.kwargs
    options = call_kwargs["options"]
    assert getattr(options, "max_turns", None) == 5
    assert getattr(options, "allowed_tools", None) == ["Read", "Grep"]
    assert getattr(options, "system_prompt", None) == "s"


@pytest.mark.asyncio
async def test_run_agent_empty_allowed_tools_default() -> None:
    with patch("agents.lib.anthropic._sdk_query") as m:
        m.return_value = _async_iter([])
        await run_agent("p", system="s")
    options = m.call_args.kwargs["options"]
    assert getattr(options, "allowed_tools", None) == []


@pytest.mark.asyncio
async def test_run_agent_routes_to_github_models_when_backend_set() -> None:
    fake_result = MagicMock(messages=[{"type": "text", "text": "via GH"}], stopped_reason="complete")

    with (
        patch.dict("os.environ", {"HARNESS_BACKEND": "github_models"}, clear=False),
        patch("agents.lib.anthropic._run_github_models", new=AsyncMock(return_value=fake_result)) as gh,
    ):
        result = await run_agent("p", system="s")

    gh.assert_called_once()
    assert result.messages[0]["text"] == "via GH"


@pytest.mark.asyncio
async def test_run_agent_default_backend_is_anthropic() -> None:
    fake_result = MagicMock(messages=[], stopped_reason="complete")

    env = {k: v for k, v in os.environ.items() if k != "HARNESS_BACKEND"}
    with (
        patch.dict("os.environ", env, clear=True),
        patch("agents.lib.anthropic._run_anthropic", new=AsyncMock(return_value=fake_result)) as anth,
    ):
        await run_agent("p", system="s")

    anth.assert_called_once()
