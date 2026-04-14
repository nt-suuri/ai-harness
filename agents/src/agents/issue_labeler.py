"""Issue auto-labeler. Reads a new issue, asks Claude to pick labels from an allow-list.

Usage:
    python -m agents.issue_labeler --issue 42
    python -m agents.issue_labeler --issue 42 --dry-run
"""

import argparse
import asyncio
import json
import re
import sys
from typing import Any

from agents.lib import gh, kill_switch, prompts
from agents.lib.anthropic import run_agent

ALLOWED_LABELS = frozenset({
    "area:api",
    "area:web",
    "area:agents",
    "area:ci",
    "area:docs",
    "priority:high",
    "priority:low",
})

_MAX_TURNS = 10


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.issue_labeler", description=__doc__)
    p.add_argument("--issue", type=int, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _extract_text(messages: list[Any]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


def _extract_labels(body: str) -> list[str]:
    """Find the LAST JSON array in `body` and return only allowed labels from it."""
    matches = re.findall(r"\[[^\[\]]*\]", body)
    if not matches:
        return []
    try:
        candidates = json.loads(matches[-1])
    except json.JSONDecodeError:
        return []
    if not isinstance(candidates, list):
        return []
    return [str(c) for c in candidates if isinstance(c, str) and c in ALLOWED_LABELS]


async def label_issue(issue_number: int, *, dry_run: bool) -> int:
    """Return 0 always."""
    repo = gh.repo()
    issue = repo.get_issue(issue_number)

    existing = {getattr(label, "name", "") for label in issue.labels}
    if existing & set(ALLOWED_LABELS):
        print(f"Issue #{issue_number} already has managed labels {existing & set(ALLOWED_LABELS)}; skipping")
        return 0

    system = prompts.load("issue_labeler")
    user = (
        f"Issue #{issue_number}: {issue.title}\n\n"
        f"Body:\n{issue.body or '(no body)'}\n\n"
        "Pick labels per the system prompt rules."
    )
    result = await run_agent(
        prompt=user,
        system=system,
        max_turns=_MAX_TURNS,
        allowed_tools=[],
    )
    text = _extract_text(result.messages)
    labels = _extract_labels(text)

    if not labels:
        print("No valid labels extracted from agent response; skipping")
        return 0

    if dry_run:
        print(f"--- DRY RUN [issue #{issue_number}] would apply: {labels} ---")
        return 0

    issue.add_to_labels(*labels)
    print(f"Applied labels {labels} to issue #{issue_number}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return asyncio.run(label_issue(args.issue, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
