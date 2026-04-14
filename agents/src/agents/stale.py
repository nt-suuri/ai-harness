"""Close autotriage issues that have had no activity for N days.

Usage:
    python -m agents.stale
    python -m agents.stale --stale-days 30 --dry-run
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta

from agents.lib import gh, kill_switch, labels

_CLOSE_COMMENT = (
    "Closing as stale (no activity for {days}+ days). The triager will reopen "
    "automatically if the underlying error recurs."
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.stale", description=__doc__)
    p.add_argument("--stale-days", type=int, default=14, help="Threshold (default 14)")
    p.add_argument("--dry-run", action="store_true", help="List candidates; skip writes")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _is_stale(updated_at: datetime, *, threshold_days: int) -> bool:
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    age = datetime.now(UTC) - updated_at
    return age >= timedelta(days=threshold_days)


def run_stale_close(stale_days: int, *, dry_run: bool) -> int:
    """Return 0 always."""
    repo = gh.repo()
    issues = list(repo.get_issues(state="open", labels=[labels.AUTOTRIAGE]))

    closed = 0
    skipped = 0
    for issue in issues:
        if not _is_stale(issue.updated_at, threshold_days=stale_days):
            skipped += 1
            continue
        if dry_run:
            print(f"DRY RUN — would close #{issue.number} (updated {issue.updated_at})")
            closed += 1
            continue
        issue.create_comment(_CLOSE_COMMENT.format(days=stale_days))
        issue.edit(state="closed", state_reason="not_planned")
        print(f"Closed stale issue #{issue.number}")
        closed += 1

    print(f"stale-close: closed={closed} skipped={skipped} total={len(issues)}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return run_stale_close(args.stale_days, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
