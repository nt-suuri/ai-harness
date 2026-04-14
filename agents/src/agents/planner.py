"""Autonomous planner. Triggered by `agent:build` label on an issue.

Usage:
    python -m agents.planner --issue 42
    python -m agents.planner --issue 42 --dry-run
"""

import argparse
import asyncio
import sys

from agents.lib import kill_switch


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.planner", description=__doc__)
    p.add_argument("--issue", type=int, required=True, help="GitHub issue number")
    p.add_argument("--dry-run", action="store_true", help="Plan only; skip branch/commit/push/PR")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


async def plan_and_open_pr(issue_number: int, *, dry_run: bool) -> int:
    """Return 0 on success, 1 on agent failure, 2 on internal error."""
    raise NotImplementedError("Task 2 fills this in")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return asyncio.run(plan_and_open_pr(args.issue, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
