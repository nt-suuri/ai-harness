from unittest.mock import patch

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
