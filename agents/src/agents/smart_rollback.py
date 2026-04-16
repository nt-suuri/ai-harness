"""LLM-based rollback decision: revert / alert / ignore."""

import json
import re
from typing import Any

from agents.lib import prompts
from agents.lib.anthropic import run_agent


def _format_events(events: list[dict[str, Any]]) -> str:
    if not events:
        return "(none)"
    summary: dict[str, int] = {}
    for e in events:
        title = e.get("title") or e.get("message") or "unknown"
        summary[title] = summary.get(title, 0) + 1
    lines = [f"- {title}: {count}" for title, count in sorted(summary.items(), key=lambda x: -x[1])]
    return "\n".join(lines)


def _parse_response(text: str) -> tuple[str, str]:
    decision_match = re.search(r"DECISION:\s*(\w+)", text, re.IGNORECASE)
    analysis_match = re.search(r"ANALYSIS:\s*(.+?)(?:\n\n|\Z)", text, re.IGNORECASE | re.DOTALL)

    raw_decision = decision_match.group(1).upper() if decision_match else "ALERT"
    decision = raw_decision if raw_decision in ("REVERT", "ALERT", "IGNORE") else "ALERT"
    analysis = analysis_match.group(1).strip() if analysis_match else text.strip()
    return decision, analysis


async def analyze(
    deploy_sha: str,
    baseline_events: list[dict[str, Any]],
    post_events: list[dict[str, Any]],
) -> tuple[str, str]:
    """Returns (decision, analysis). Decision is REVERT, ALERT, or IGNORE."""
    system = prompts.load("smart_rollback")
    user = (
        f"DEPLOY_SHA: {deploy_sha}\n\n"
        f"BASELINE_ERRORS (60m before deploy):\n{_format_events(baseline_events)}\n\n"
        f"POST_DEPLOY_ERRORS (10m after deploy):\n{_format_events(post_events)}"
    )
    result = await run_agent(prompt=user, system=system, max_turns=5, allowed_tools=[])

    text = ""
    for m in result.messages:
        if isinstance(m, dict) and m.get("type") == "text":
            text += str(m.get("text", "")) + "\n"
        elif hasattr(m, "text"):
            text += str(m.text) + "\n"

    return _parse_response(text)
