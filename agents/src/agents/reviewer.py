"""3-pass PR reviewer. One invocation = one pass.

Usage:
    python -m agents.reviewer --pass quality --pr 42
    python -m agents.reviewer --pass security --pr 42 --dry-run
"""

import argparse
import asyncio
import sys

from agents.lib import kill_switch

_PASSES = ("quality", "security", "deps")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.reviewer", description=__doc__)
    p.add_argument("--pass", dest="pass_name", choices=_PASSES, required=True)
    p.add_argument("--pr", type=int, required=True, help="Pull request number")
    p.add_argument("--dry-run", action="store_true", help="Print result; skip posting")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


async def review_pr(pass_name: str, pr_number: int, *, dry_run: bool) -> int:
    """Return 0 if APPROVED, 1 if REJECTED. Task 2 implements this."""
    raise NotImplementedError("Task 2 fills this in")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return asyncio.run(review_pr(args.pass_name, args.pr, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
