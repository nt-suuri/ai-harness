"""Nightly triager. Pulls Sentry issues, opens GH issues for new ones.

Usage:
    python -m agents.triager
    python -m agents.triager --since-hours 24 --dry-run
"""

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from agents.lib import gh, kill_switch, sentry


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.triager", description=__doc__)
    p.add_argument("--since-hours", type=int, default=24, help="Lookback window (default 24)")
    p.add_argument("--dry-run", action="store_true", help="Print what would be opened; skip GH writes")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _make_marker(sentry_id: str) -> str:
    return f"<sentry-issue-id>{sentry_id}</sentry-issue-id>"


def _existing_marker_in_issues(issues: list[Any], marker: str) -> bool:
    for issue in issues:
        body = getattr(issue, "body", None) or ""
        if marker in body:
            return True
    return False


def _format_issue_body(s_issue: dict[str, Any], marker: str) -> str:
    return (
        f"{marker}\n\n"
        f"**Sentry permalink:** {s_issue.get('permalink', '(none)')}\n"
        f"**Culprit:** `{s_issue.get('culprit', '(unknown)')}`\n"
        f"**Count (last 24h):** {s_issue.get('count', '?')}\n"
        f"**Level:** {s_issue.get('level', '?')}\n\n"
        "Apply `agent:build` label to have the planner attempt a fix."
    )


def triage_run(since_hours: int, *, dry_run: bool) -> int:
    """Return 0 always. Logs counts."""
    org = os.environ.get("SENTRY_ORG_SLUG", "")
    proj = os.environ.get("SENTRY_PROJECT_SLUG", "")
    if not org or not proj:
        print("SENTRY_ORG_SLUG/SENTRY_PROJECT_SLUG unset — skipping triage", flush=True)
        return 0

    since = datetime.now(UTC) - timedelta(hours=since_hours)
    sentry_issues = sentry.list_issues(org, proj, since=since)

    repo = gh.repo()
    existing = list(repo.get_issues(state="all", labels=["autotriage"]))

    new_count = 0
    deduped = 0
    for s_issue in sentry_issues:
        sentry_id = str(s_issue.get("id", ""))
        if not sentry_id:
            continue
        marker = _make_marker(sentry_id)
        if _existing_marker_in_issues(existing, marker):
            deduped += 1
            continue

        title = f"[autotriage] {s_issue.get('title', 'Unknown error')}"
        body = _format_issue_body(s_issue, marker)
        if dry_run:
            print(f"DRY RUN — would create: {title}")
            new_count += 1
            continue

        gh_issue = repo.create_issue(title=title, body=body, labels=["bug", "autotriage"])
        print(f"Created issue #{gh_issue.number}: {title}", flush=True)
        new_count += 1

    print(
        f"triaged: total_sentry={len(sentry_issues)} new_gh={new_count} deduped={deduped}",
        flush=True,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return triage_run(args.since_hours, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
