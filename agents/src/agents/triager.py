"""Nightly triager. Pulls Sentry issues, opens GH issues for new ones.

Usage:
    python -m agents.triager
    python -m agents.triager --since-hours 24 --dry-run
"""

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from agents.lib import gh, kill_switch, labels, prompts, sentry


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


def _find_issue_by_marker(issues: list[Any], marker: str) -> Any | None:
    for issue in issues:
        body = getattr(issue, "body", None) or ""
        if marker in body:
            return issue
    return None


def _format_issue_body(s_issue: dict[str, Any], marker: str) -> str:
    return (
        f"{marker}\n\n"
        f"**Sentry permalink:** {s_issue.get('permalink', '(none)')}\n"
        f"**Culprit:** `{s_issue.get('culprit', '(unknown)')}`\n"
        f"**Count (last 24h):** {s_issue.get('count', '?')}\n"
        f"**Level:** {s_issue.get('level', '?')}\n\n"
        "Apply `agent:build` label to have the planner attempt a fix."
    )


def _severity_label(score: int) -> str:
    if score >= 8:
        return labels.SEVERITY_CRITICAL
    if score >= 4:
        return labels.SEVERITY_IMPORTANT
    return labels.SEVERITY_MINOR


def _parse_severity(text: str) -> int:
    """Parse `SEVERITY: <int>` from the LAST matching line. Returns 5 on parse failure (medium)."""
    import re

    matches = re.findall(r"SEVERITY:\s*(\d+)", text)
    if not matches:
        return 5
    try:
        score = int(matches[-1])
    except ValueError:
        return 5
    return max(1, min(10, score))


async def _score_severity_async(s_issue: dict[str, Any]) -> int:
    import json

    from agents.lib.anthropic import run_agent

    system = prompts.load("triager_severity")
    user = "Score the severity of this Sentry issue:\n\n" + json.dumps(
        {
            "title": s_issue.get("title", ""),
            "culprit": s_issue.get("culprit", ""),
            "count": s_issue.get("count", "?"),
            "level": s_issue.get("level", "?"),
        },
        indent=2,
    )
    result = await run_agent(prompt=user, system=system, max_turns=5, allowed_tools=[])
    text = ""
    for m in result.messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            text += str(m["text"]) + "\n"
        elif hasattr(m, "text"):
            text += str(m.text) + "\n"
    return _parse_severity(text)


def _score_severity(s_issue: dict[str, Any]) -> int:
    """Sync wrapper. Returns 5 (medium) on any error so we never block triage."""
    try:
        return asyncio.run(_score_severity_async(s_issue))
    except Exception as e:
        print(f"warning: severity scoring failed for {s_issue.get('id')}: {e}", flush=True)
        return 5


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
    existing_open = list(repo.get_issues(state="open", labels=[labels.AUTOTRIAGE]))
    existing_closed = list(repo.get_issues(state="closed", labels=[labels.AUTOTRIAGE]))

    new_count = 0
    deduped = 0
    reopened = 0
    for s_issue in sentry_issues:
        sentry_id = str(s_issue.get("id", ""))
        if not sentry_id:
            continue
        marker = _make_marker(sentry_id)
        if _existing_marker_in_issues(existing_open, marker):
            deduped += 1
            continue
        closed_match = _find_issue_by_marker(existing_closed, marker)
        if closed_match is not None:
            if dry_run:
                print(f"DRY RUN — would reopen #{closed_match.number} as regression: {s_issue.get('title')}")
            else:
                closed_match.edit(state="open")
                closed_match.add_to_labels(labels.REGRESSION)
                closed_match.create_comment(
                    f"Regression detected — this error recurred in Sentry. "
                    f"Reopened + labeled `{labels.REGRESSION}`."
                )
                print(f"Reopened regression issue #{closed_match.number}")
            reopened += 1
            continue

        title = f"[autotriage] {s_issue.get('title', 'Unknown error')}"
        body = _format_issue_body(s_issue, marker)
        if dry_run:
            score = _score_severity(s_issue)
            print(f"DRY RUN — would create: {title} (severity:{score})")
            new_count += 1
            continue

        score = _score_severity(s_issue)
        sev_label = _severity_label(score)
        gh_issue = repo.create_issue(title=title, body=body, labels=[labels.BUG, labels.AUTOTRIAGE, sev_label])
        print(f"Created issue #{gh_issue.number}: {title}", flush=True)
        new_count += 1

    print(
        f"triaged: total_sentry={len(sentry_issues)} new_gh={new_count} deduped={deduped} reopened={reopened}",
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
