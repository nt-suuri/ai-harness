"""OpenAI-compatible adapter for GitHub Models (free tier).

Used when HARNESS_BACKEND=github_models. Does NOT support tools (allowed_tools must be empty).
"""

import os
from dataclasses import dataclass
from typing import Any

import httpx

_BASE_URL = "https://models.github.ai/inference"
_DEFAULT_MODEL = os.environ.get("GITHUB_MODELS_DEFAULT_MODEL", "openai/gpt-4o-mini")


@dataclass(frozen=True)
class _AgentResult:
    """Local mirror of agents.lib.anthropic.AgentResult; do not import to avoid cycles."""

    messages: list[Any]
    stopped_reason: str


def _token() -> str:
    return os.environ.get("GITHUB_MODELS_TOKEN") or os.environ["GITHUB_TOKEN"]


async def run_agent(
    prompt: str,
    *,
    system: str,
    max_turns: int = 20,
    allowed_tools: list[str] | None = None,
) -> _AgentResult:
    if allowed_tools:
        raise NotImplementedError(
            "github_models backend does not support tools yet — "
            "set HARNESS_BACKEND=anthropic for the planner agent"
        )

    model = os.environ.get("GITHUB_MODELS_MODEL", _DEFAULT_MODEL)
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 4096,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{_BASE_URL}/chat/completions", headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

    text = data["choices"][0]["message"]["content"]
    msg = {"type": "text", "text": text}
    return _AgentResult(messages=[msg], stopped_reason="complete")
