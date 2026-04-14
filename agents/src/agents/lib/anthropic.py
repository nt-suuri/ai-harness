from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk import query as _sdk_query


@dataclass(frozen=True)
class AgentResult:
    messages: list[Any]
    stopped_reason: str  # "complete" | "turn_cap"


async def run_agent(
    prompt: str,
    *,
    system: str,
    max_turns: int = 20,
    allowed_tools: list[str] | None = None,
) -> AgentResult:
    options = ClaudeAgentOptions(
        system_prompt=system,
        max_turns=max_turns,
        allowed_tools=list(allowed_tools) if allowed_tools else [],
    )
    messages: list[Any] = []
    async for message in _sdk_query(prompt=prompt, options=options):
        messages.append(message)
    return AgentResult(messages=messages, stopped_reason="complete")
