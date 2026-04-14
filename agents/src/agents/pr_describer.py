"""PR description auto-filler. When a PR is opened with empty/minimal body,
read the diff and ask Claude Sonnet 4.6 to write a structured description.

Usage:
    python -m agents.pr_describer --pr 42
    python -m agents.pr_describer --pr 42 --dry-run
"""

import argparse
import asyncio
import sys
from typing import Any

from agents.lib import gh, kill_switch, prompts
from agents.lib.anthropic import run_agent

_MAX_TURNS = 20
_MIN_BODY_CHARS = 60


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.pr_describer", description=__doc__)
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _is_minimal_description(body: str | None) -> bool:
    if not body:
        return True
    return len(body.strip()) < _MIN_BODY_CHARS


def _fetch_diff(pr: Any) -> str:
    pieces: list[str] = []
    for f in pr.get_files():
        patch = getattr(f, "patch", None)
        if patch:
            pieces.append(f"--- {f.filename} ---\n{patch}")
    return "\n\n".join(pieces)


def _extract_text(messages: list[Any]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


async def fill_pr_description(pr_number: int, *, dry_run: bool) -> int:
    """Return 0 always (no-op if PR already has a description)."""
    repo = gh.repo()
    pr = repo.get_pull(pr_number)

    if not _is_minimal_description(pr.body):
        print(f"PR #{pr_number} already has a description ({len(pr.body or '')} chars); skipping")
        return 0

    diff = _fetch_diff(pr)
    if not diff:
        print(f"PR #{pr_number} has no diff (empty or binary-only); skipping")
        return 0

    system = prompts.load("pr_describer")
    user = (
        f"PR #{pr_number} title: {pr.title}\n\n"
        f"Diff:\n```diff\n{diff}\n```\n\n"
        "Write the PR description per the system rules."
    )
    result = await run_agent(
        prompt=user,
        system=system,
        max_turns=_MAX_TURNS,
        allowed_tools=[],
    )
    new_body = _extract_text(result.messages)

    if dry_run:
        print(f"--- DRY RUN [PR #{pr_number}] ---")
        print(new_body)
        return 0

    pr.edit(body=new_body)
    print(f"Updated PR #{pr_number} description ({len(new_body)} chars)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return asyncio.run(fill_pr_description(args.pr, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
