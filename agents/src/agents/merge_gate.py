"""Merge Gate agent: reads reviewer verdicts + CI status, decides merge/reject/hold/wait."""

import re
import subprocess
from pathlib import Path
from typing import Any

from agents.lib import prompts
from agents.lib.anthropic import run_agent


async def decide(pr_number: int, *, repo: Any) -> tuple[str, str]:
    """Return (decision, feedback).

    decision: 'merged' | 'rejected' | 'waiting' | 'held'
    feedback: non-empty only when decision == 'rejected'
    """
    pr = repo.get_pull(pr_number)

    comments = [
        c.body for c in pr.get_issue_comments()
        if c.body.startswith("**Claude review")
    ]

    if not comments:
        return ("waiting", "")

    statuses = {
        s.context: s.state
        for s in repo.get_commit(pr.head.sha).get_statuses()
    }

    reviewer_block = "\n\n---\n\n".join(comments)
    ci_block = (
        "\n".join(f"- {ctx}: {state}" for ctx, state in statuses.items())
        or "No CI statuses found"
    )

    user_prompt = (
        f"PR_NUMBER: #{pr_number}\n\n"
        f"REVIEWER_COMMENTS:\n{reviewer_block}\n\n"
        f"CI_STATUS:\n{ci_block}"
    )

    system = prompts.load("merge_gate")
    result = await run_agent(prompt=user_prompt, system=system, max_turns=3, allowed_tools=[])
    text = _extract_text(result.messages)
    return _parse_decision(text, pr_number)


def _extract_text(messages: list[object]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


def _parse_decision(text: str, pr_number: int) -> tuple[str, str]:
    first = text.splitlines()[0] if text else ""

    if "DECISION: MERGE" in first:
        subprocess.run(
            ["gh", "pr", "merge", str(pr_number), "--auto", "--squash", "--delete-branch"],
            cwd=Path.cwd(), check=False,
        )
        return ("merged", "")

    if "DECISION: REJECT" in first:
        m = re.search(r"FEEDBACK:\s*\n(.+)", text, flags=re.DOTALL)
        feedback = m.group(1).strip() if m else "Reviewer rejected. See comments."
        return ("rejected", feedback)

    if "DECISION: HOLD" in first:
        return ("held", "")

    return ("waiting", "")
