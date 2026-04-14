"""3-pass PR reviewer. One invocation = one pass.

Usage:
    python -m agents.reviewer --pass quality --pr 42
    python -m agents.reviewer --pass security --pr 42 --dry-run
"""

import argparse
import asyncio
import sys
from typing import Any

from agents.lib import gh, kill_switch, prompts
from agents.lib.anthropic import run_agent

_PASSES = ("quality", "security", "deps")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.reviewer", description=__doc__)
    p.add_argument("--pass", dest="pass_name", choices=_PASSES, required=True)
    p.add_argument("--pr", type=int, required=True, help="Pull request number")
    p.add_argument("--dry-run", action="store_true", help="Print result; skip posting")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _fetch_diff(pr: Any) -> str:
    """Concatenate per-file patches from PyGithub's get_files()."""
    pieces: list[str] = []
    for f in pr.get_files():
        patch = getattr(f, "patch", None)
        if patch:
            pieces.append(f"--- {f.filename} ---\n{patch}")
    return "\n\n".join(pieces)


async def review_pr(pass_name: str, pr_number: int, *, dry_run: bool) -> int:
    """Return 0 if APPROVED, 1 if REJECTED."""
    repo = gh.repo()
    pr = repo.get_pull(pr_number)
    diff = _fetch_diff(pr)
    system = prompts.load(f"reviewer_{pass_name}")
    user = (
        f"Review PR #{pr_number} titled: {pr.title}\n\n"
        f"Diff:\n```diff\n{diff}\n```\n\n"
        "End your response with exactly one line: `VERDICT: APPROVED` or `VERDICT: REJECTED`."
    )
    result = await run_agent(
        prompt=user,
        system=system,
        max_turns=20,
        allowed_tools=[],
    )
    body = _extract_text(result.messages)
    state = _extract_verdict(body)
    comment = f"**Claude review — {pass_name}**\n\n{body}"

    if dry_run:
        print(f"--- DRY RUN [{pass_name}] rc={0 if state == 'success' else 1} ---")
        print(comment)
        return 0 if state == "success" else 1

    pr.create_issue_comment(comment)
    repo.get_commit(pr.head.sha).create_status(
        state=state,
        target_url="",
        description=f"Claude {pass_name} review",
        context=f"reviewer / {pass_name}",
    )
    return 0 if state == "success" else 1


def _extract_text(messages: list[Any]) -> str:
    """Join all text-type messages into a single body."""
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


def _extract_verdict(body: str) -> str:
    """Return 'success' if body ends with 'VERDICT: APPROVED', else 'failure'."""
    for raw in reversed(body.splitlines()):
        line = raw.strip()
        if line.startswith("VERDICT:"):
            return "success" if "APPROVED" in line.upper() else "failure"
    return "failure"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return asyncio.run(review_pr(args.pass_name, args.pr, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
