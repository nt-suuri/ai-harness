"""PR Priority agent: ranks open PRs by merge urgency."""

import re
from typing import Any

from agents.lib import prompts
from agents.lib.anthropic import run_agent


async def rank(repo: Any) -> int | None:
    """Returns the PR number that should be merged next, or None if no PR is ready."""
    open_prs = list(repo.get_pulls(state="open", sort="created", direction="asc"))
    if not open_prs:
        return None

    pr_descriptions: list[str] = []
    for pr in open_prs:
        labels = [lbl.name for lbl in pr.labels]
        files = pr.changed_files
        age = pr.created_at.isoformat() if pr.created_at else "unknown"
        pr_descriptions.append(
            f"- #{pr.number}: title=\"{pr.title}\", labels={labels}, "
            f"author={pr.user.login}, files_changed={files}, created={age}"
        )

    user_prompt = "OPEN_PRS:\n" + "\n".join(pr_descriptions)
    system = prompts.load("pr_priority")
    result = await run_agent(prompt=user_prompt, system=system, max_turns=3, allowed_tools=[])
    text = _extract_text(result.messages)
    return _parse_merge_next(text)


def _extract_text(messages: list[object]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


def _parse_merge_next(text: str) -> int | None:
    m = re.search(r"MERGE_NEXT:\s*#?(\d+|NONE)", text)
    if not m or m.group(1) == "NONE":
        return None
    return int(m.group(1))
