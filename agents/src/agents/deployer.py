"""Post-deploy rollback watcher. Waits, then checks Sentry error rate.

Usage:
    python -m agents.deployer --after-sha abc123 --window-minutes 10
    python -m agents.deployer --after-sha abc123 --dry-run
"""

import argparse
import sys

from agents.lib import kill_switch


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.deployer", description=__doc__)
    p.add_argument("--after-sha", required=True, help="Commit SHA that was just deployed")
    p.add_argument("--window-minutes", type=int, default=10, help="Monitor window (default 10)")
    p.add_argument("--dry-run", action="store_true", help="Check only; skip issue creation")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def watch_post_deploy(sha: str, window_minutes: int, *, dry_run: bool) -> int:
    """Return 0 if healthy, 1 if regression detected, 2 on internal error."""
    raise NotImplementedError("Task 3 fills this in")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return watch_post_deploy(args.after_sha, args.window_minutes, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
