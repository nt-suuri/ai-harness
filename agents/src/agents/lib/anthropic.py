"""Wrapper around claude-agent-sdk OR github-models, selected by HARNESS_BACKEND env."""

import os
from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk import query as _sdk_query


@dataclass(frozen=True)
class AgentResult:
    messages: list[Any]
    stopped_reason: str  # "complete" | "turn_cap"


async def _run_anthropic(
    prompt: str,
    *,
    system: str,
    max_turns: int,
    allowed_tools: list[str],
) -> AgentResult:
    options = ClaudeAgentOptions(
        system_prompt=system,
        max_turns=max_turns,
        allowed_tools=allowed_tools,
    )
    messages: list[Any] = []
    async for message in _sdk_query(prompt=prompt, options=options):
        messages.append(message)
    return AgentResult(messages=messages, stopped_reason="complete")


async def _run_github_models(
    prompt: str,
    *,
    system: str,
    max_turns: int,
    allowed_tools: list[str],
) -> AgentResult:
    from agents.lib import github_models

    result = await github_models.run_agent(
        prompt,
        system=system,
        max_turns=max_turns,
        allowed_tools=allowed_tools,
    )
    return AgentResult(messages=result.messages, stopped_reason=result.stopped_reason)


async def run_agent(
    prompt: str,
    *,
    system: str,
    max_turns: int = 20,
    allowed_tools: list[str] | None = None,
) -> AgentResult:
    """Run an LLM agent. Backend chosen by HARNESS_BACKEND env var:

    - "anthropic" (default): claude-agent-sdk
    - "github_models": GitHub Models free tier (no tool use; allowed_tools must be empty)
    """
    backend = os.environ.get("HARNESS_BACKEND", "anthropic").lower().strip()
    tools = list(allowed_tools) if allowed_tools else []

    if backend == "github_models":
        return await _run_github_models(
            prompt, system=system, max_turns=max_turns, allowed_tools=tools
        )
    return await _run_anthropic(
        prompt, system=system, max_turns=max_turns, allowed_tools=tools
    )
