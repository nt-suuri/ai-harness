"""Test Failure Triage agent: categorizes pytest failures as real bug / flaky / environment / unrelated."""

import re

from agents.lib import prompts
from agents.lib.anthropic import run_agent


async def categorize(test_output: str, changed_files: list[str]) -> tuple[str, str]:
    """Returns (category, action) where category is REAL_BUG|FLAKY|ENVIRONMENT|UNRELATED
    and action is retry|fix|skip|escalate."""
    user_prompt = (
        f"TEST_OUTPUT:\n{test_output[-3000:]}\n\n"
        f"CHANGED_FILES:\n" + "\n".join(f"- {f}" for f in changed_files)
    )
    system = prompts.load("test_triage")
    result = await run_agent(prompt=user_prompt, system=system, max_turns=3, allowed_tools=[])
    text = _extract_text(result.messages)
    return _parse(text)


def _extract_text(messages: list[object]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


def _parse(text: str) -> tuple[str, str]:
    cat_match = re.search(r"^CATEGORY:\s*(\S+)", text, flags=re.MULTILINE)
    act_match = re.search(r"^ACTION:\s*(\S+)", text, flags=re.MULTILINE)
    category = cat_match.group(1) if cat_match else "REAL_BUG"
    action = act_match.group(1) if act_match else "fix"
    return (category, action)
