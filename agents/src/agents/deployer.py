"""Post-deploy rollback watcher. Waits, then checks Sentry error rate.

Usage:
    python -m agents.deployer --after-sha abc123 --window-minutes 10
    python -m agents.deployer --after-sha abc123 --dry-run
"""

import argparse
import os
import sys
import time
from datetime import UTC, datetime, timedelta

from agents.lib import gh, kill_switch, sentry

_SPIKE_RATIO = 3.0
_SPIKE_ABSOLUTE_FLOOR = 5


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.deployer", description=__doc__)
    p.add_argument("--after-sha", required=True, help="Commit SHA that was just deployed")
    p.add_argument("--window-minutes", type=int, default=10, help="Monitor window (default 10)")
    p.add_argument("--dry-run", action="store_true", help="Check only; skip issue creation")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _detect_spike(*, baseline_per_min: float, post_count: int, window_minutes: int) -> bool:
    """Spike if post rate > baseline * ratio AND post_count > absolute floor."""
    post_per_min = post_count / max(window_minutes, 1)
    above_ratio = post_per_min > baseline_per_min * _SPIKE_RATIO
    above_floor = post_count > _SPIKE_ABSOLUTE_FLOOR
    return above_ratio and above_floor


def _sentry_config() -> tuple[str, str]:
    org = os.environ.get("SENTRY_ORG_SLUG", "")
    proj = os.environ.get("SENTRY_PROJECT_SLUG", "")
    return org, proj


def watch_post_deploy(sha: str, window_minutes: int, *, dry_run: bool) -> int:
    """Return 0 if healthy, 1 if regression detected, 2 on internal error."""
    org, proj = _sentry_config()
    if not org or not proj:
        print("SENTRY_ORG_SLUG or SENTRY_PROJECT_SLUG unset — skipping spike check", flush=True)
        return 0

    now = datetime.now(UTC)
    baseline_since = now - timedelta(minutes=60)
    baseline_count = sentry.count_events_since(org, proj, since=baseline_since)
    baseline_per_min = baseline_count / 60.0

    time.sleep(window_minutes * 60)

    post_count = sentry.count_events_since(org, proj, since=now)

    spike = _detect_spike(
        baseline_per_min=baseline_per_min,
        post_count=post_count,
        window_minutes=window_minutes,
    )

    if not spike:
        print(
            f"Post-deploy OK: baseline={baseline_per_min:.2f}/min, "
            f"post={post_count} over {window_minutes}m — no spike",
            flush=True,
        )
        return 0

    title = f"Regression detected after deploy {sha[:7]}"
    body = (
        f"Post-deploy error rate spiked after commit `{sha}`.\n\n"
        f"- Baseline (60m prior): {baseline_count} events "
        f"({baseline_per_min:.2f}/min)\n"
        f"- Post-deploy ({window_minutes}m window): {post_count} events "
        f"({post_count / window_minutes:.2f}/min)\n"
        f"- Trigger: rate x{_SPIKE_RATIO} AND count > {_SPIKE_ABSOLUTE_FLOOR}\n\n"
        f"Investigate or revert the commit."
    )

    if dry_run:
        print("--- DRY RUN --- would open issue:")
        print(f"Title: {title}")
        print(body)
        return 1

    repo = gh.repo()
    issue = repo.create_issue(title=title, body=body, labels=["regression", "autotriage"])
    print(f"Opened regression issue #{issue.number}: {issue.html_url}", flush=True)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return watch_post_deploy(args.after_sha, args.window_minutes, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
