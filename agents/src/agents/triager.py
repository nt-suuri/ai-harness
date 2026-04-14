"""Nightly triager. Pulls Sentry issues, opens GH issues for new ones.

Usage:
    python -m agents.triager
    python -m agents.triager --since-hours 24 --dry-run
"""

import argparse
import sys

from agents.lib import kill_switch


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.triager", description=__doc__)
    p.add_argument("--since-hours", type=int, default=24, help="Lookback window (default 24)")
    p.add_argument("--dry-run", action="store_true", help="Print what would be opened; skip GH writes")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def triage_run(since_hours: int, *, dry_run: bool) -> int:
    """Return 0 always (cron-friendly). Logs counts to stdout."""
    raise NotImplementedError("Task 3 fills this in")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return triage_run(args.since_hours, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
