"""Post-deploy rollback watcher. Waits, then uses LLM to assess Sentry errors.

Usage:
    python -m agents.deployer --after-sha abc123 --window-minutes 10
    python -m agents.deployer --after-sha abc123 --dry-run
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta

from agents.lib import gh, kill_switch, labels, sentry


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.deployer", description=__doc__)
    p.add_argument("--after-sha", required=True, help="Commit SHA that was just deployed")
    p.add_argument("--window-minutes", type=int, default=10, help="Monitor window (default 10)")
    p.add_argument("--dry-run", action="store_true", help="Check only; skip issue creation")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _sentry_config() -> tuple[str, str]:
    org = os.environ.get("SENTRY_ORG_SLUG", "")
    proj = os.environ.get("SENTRY_PROJECT_SLUG", "")
    return org, proj


def watch_post_deploy(sha: str, window_minutes: int, *, dry_run: bool) -> int:
    """Return 0 if healthy, 1 if regression detected, 2 on internal error."""
    from agents.smart_rollback import analyze

    org, proj = _sentry_config()
    if not org or not proj:
        print("SENTRY_ORG_SLUG or SENTRY_PROJECT_SLUG unset — skipping spike check", flush=True)
        return 0

    now = datetime.now(UTC)
    baseline_since = now - timedelta(minutes=60)
    baseline_events = sentry.list_events(org, proj, since=baseline_since)

    time.sleep(window_minutes * 60)

    post_events = sentry.list_events(org, proj, since=now)

    decision, analysis = asyncio.run(analyze(sha, baseline_events, post_events))
    decision_lower = decision.lower()

    if decision_lower == "ignore":
        print(f"Post-deploy OK (LLM: IGNORE) — {analysis}", flush=True)
        return 0

    title = f"Regression detected after deploy {sha[:7]}"
    body = (
        f"Post-deploy analysis after commit `{sha}`.\n\n"
        f"**LLM Decision:** {decision}\n\n"
        f"**Analysis:** {analysis}\n\n"
        f"- Baseline events (60m prior): {len(baseline_events)}\n"
        f"- Post-deploy events ({window_minutes}m window): {len(post_events)}\n\n"
        f"Investigate or revert the commit."
    )

    if dry_run:
        print("--- DRY RUN --- would open issue:")
        print(f"Title: {title}")
        print(body)
        return 1

    repo = gh.repo()
    issue_labels = [labels.REGRESSION, labels.AUTOTRIAGE, labels.AGENT_BUILD]
    issue = repo.create_issue(title=title, body=body, labels=issue_labels)
    print(f"Opened regression issue #{issue.number}: {issue.html_url}", flush=True)

    if decision_lower == "revert" and os.environ.get("AUTO_ROLLBACK", "").strip().lower() == "true":
        rolled_back = _auto_revert(sha)
        if rolled_back:
            issue.create_comment(f"Auto-rollback: reverted commit `{sha[:7]}` (see `{rolled_back}`).")

    return 1


def _auto_revert(sha: str) -> str | None:
    """git revert <sha> && git push. Returns the revert commit SHA on success, None on failure."""
    try:
        subprocess.run(
            ["git", "-c", "user.name=ai-harness-bot",
             "-c", "user.email=ai-harness@local",
             "revert", "--no-edit", sha],
            check=True, capture_output=True, text=True,
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "push", "origin", "HEAD:main"],
            check=True, capture_output=True, text=True,
        )
        print(f"Auto-reverted {sha[:7]} as {head[:7]}", flush=True)
        return head
    except subprocess.CalledProcessError as e:
        print(f"Auto-revert failed: {e.stderr}", flush=True)
        return None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return watch_post_deploy(args.after_sha, args.window_minutes, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
