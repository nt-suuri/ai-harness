"""OpenAI-compatible adapter for GitHub Models (free tier), with tool-use loop."""

import asyncio
import os
import random
from dataclasses import dataclass
from typing import Any

import httpx

from agents.lib import tool_executors


async def _post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: dict[str, object],
    *,
    max_attempts: int = 6,
) -> httpx.Response:
    """POST with exponential backoff on 429. GH Models free tier rate-limits aggressively."""
    for attempt in range(max_attempts):
        resp = await client.post(url, headers=headers, json=body)
        if resp.status_code != 429 or attempt == max_attempts - 1:
            return resp
        retry_after = resp.headers.get("retry-after")
        delay = float(retry_after) if retry_after else min(60.0, 2.0 ** attempt)
        delay += random.uniform(0, 1.0)
        await asyncio.sleep(delay)
    return resp  # unreachable but mypy-friendly

_BASE_URL = "https://models.github.ai/inference"
_DEFAULT_MODEL = os.environ.get("GITHUB_MODELS_DEFAULT_MODEL", "openai/gpt-4o-mini")
_MAX_TOOL_RESULT_CHARS = 8_000  # GH Models 413s if messages grow too large

_TOOL_SCHEMAS = {
    "Read": {
        "type": "function",
        "function": {
            "name": "Read",
            "description": "Read the contents of a file (UTF-8, up to 256 KiB).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "relative to repo root"}},
                "required": ["path"],
            },
        },
    },
    "Write": {
        "type": "function",
        "function": {
            "name": "Write",
            "description": "Write content to a file (creates or overwrites).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "relative to repo root"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    "Edit": {
        "type": "function",
        "function": {
            "name": "Edit",
            "description": "Replace old_string with new_string in a file. old_string must be unique.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    "Glob": {
        "type": "function",
        "function": {
            "name": "Glob",
            "description": "List files matching a glob pattern (e.g. 'apps/**/*.py').",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        },
    },
    "Grep": {
        "type": "function",
        "function": {
            "name": "Grep",
            "description": "Search for a regex pattern in files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                },
                "required": ["pattern"],
            },
        },
    },
}


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
    allowed = list(allowed_tools) if allowed_tools else []
    tools = [_TOOL_SCHEMAS[t] for t in allowed if t in _TOOL_SCHEMAS]

    model = os.environ.get("GITHUB_MODELS_MODEL", _DEFAULT_MODEL)
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    messages: list[dict[str, object]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    collected: list[object] = []
    stopped_reason = "complete"

    async with httpx.AsyncClient(timeout=180) as client:
        for _ in range(max_turns):
            body: dict[str, object] = {"model": model, "messages": messages, "max_tokens": 4096}
            if tools:
                body["tools"] = tools
                body["tool_choice"] = "auto"
            resp = await _post_with_retry(client, f"{_BASE_URL}/chat/completions", headers, body)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]
            finish = choice.get("finish_reason")

            text = msg.get("content") or ""
            if text:
                collected.append({"type": "text", "text": text})

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls or finish == "stop":
                break

            messages.append({
                "role": "assistant",
                "content": text or None,
                "tool_calls": tool_calls,
            })
            for call in tool_calls:
                name = call["function"]["name"]
                args = call["function"]["arguments"]
                result = tool_executors.execute(name, args)
                if len(result) > _MAX_TOOL_RESULT_CHARS:
                    result = result[:_MAX_TOOL_RESULT_CHARS] + "\n...[truncated]"
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result,
                })
        else:
            stopped_reason = "turn_cap"

    return _AgentResult(messages=collected, stopped_reason=stopped_reason)
