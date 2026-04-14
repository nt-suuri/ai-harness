"""Daily healthcheck. Updates pinned HEALTH issue + (optionally) sends email digest.

Usage:
    python -m agents.healthcheck
    python -m agents.healthcheck --dry-run
"""

import argparse
import asyncio
import json as _json
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from agents.lib import email, gh, kill_switch, labels, prompts, sentry

_HEALTH_ISSUE_TITLE = "HEALTH dashboard"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.healthcheck", description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Print summary; skip writes")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _build_summary(
    *,
    date_str: str,
    ci_success: int,
    ci_failure: int,
    deploy_success: int,
    deploy_failure: int,
    sentry_event_count: int,
    intro: str = "",
) -> str:
    intro_block = f"{intro}\n\n" if intro else ""
    return (
        f"## {date_str}\n\n"
        f"{intro_block}"
        f"- CI runs: {ci_success} success, {ci_failure} failure\n"
        f"- Deploys: {deploy_success} success, {deploy_failure} failure\n"
        f"- Sentry events (last 24h): {sentry_event_count}\n"
    )


async def _summarize_async(stats: dict[str, int | str]) -> str:
    from agents.lib.anthropic import run_agent

    system = prompts.load("healthcheck_summary")
    user = "Summarize this healthcheck:\n\n" + _json.dumps(stats, indent=2)
    result = await run_agent(prompt=user, system=system, max_turns=5, allowed_tools=[])
    parts: list[str] = []
    for m in result.messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


def _summarize(stats: dict[str, int | str]) -> str:
    """Sync wrapper; returns empty string on any failure (so digest still generates)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return ""
    try:
        return asyncio.run(_summarize_async(stats))
    except Exception as e:
        print(f"warning: healthcheck summary failed: {e}", flush=True)
        return ""


def _count_runs(repo: Any, workflow_file: str, since: datetime) -> tuple[int, int]:
    success = 0
    failure = 0
    workflow = repo.get_workflow(workflow_file)
    for r in workflow.get_runs(created=f">={since.date().isoformat()}"):
        if r.conclusion == "success":
            success += 1
        elif r.conclusion == "failure":
            failure += 1
    return success, failure


def run_healthcheck(*, dry_run: bool) -> int:
    """Return 0 always."""
    org = os.environ.get("SENTRY_ORG_SLUG", "")
    proj = os.environ.get("SENTRY_PROJECT_SLUG", "")
    repo = gh.repo()
    yesterday = datetime.now(UTC) - timedelta(hours=24)
    date_str = datetime.now(UTC).date().isoformat()

    ci_success, ci_failure = _count_runs(repo, "ci.yml", yesterday)
    deploy_success, deploy_failure = _count_runs(repo, "deploy.yml", yesterday)

    sentry_count = 0
    if org and proj:
        try:
            sentry_count = sentry.count_events_since(org, proj, since=yesterday)
        except Exception as e:
            print(f"warning: sentry count failed: {e}", flush=True)

    intro = _summarize({
        "date_str": date_str,
        "ci_success": ci_success,
        "ci_failure": ci_failure,
        "deploy_success": deploy_success,
        "deploy_failure": deploy_failure,
        "sentry_event_count": sentry_count,
    })
    summary = _build_summary(
        date_str=date_str,
        ci_success=ci_success,
        ci_failure=ci_failure,
        deploy_success=deploy_success,
        deploy_failure=deploy_failure,
        sentry_event_count=sentry_count,
        intro=intro,
    )

    if dry_run:
        print("--- DRY RUN ---")
        print(summary)
        return 0

    existing = list(repo.get_issues(state="open", labels=[labels.HEALTHCHECK]))
    if existing:
        issue = existing[0]
        new_body = f"{issue.body or ''}\n\n{summary}"
        issue.edit(body=new_body)
        print(f"Updated HEALTH issue #{issue.number}")
    else:
        issue = repo.create_issue(
            title=_HEALTH_ISSUE_TITLE,
            body=summary,
            labels=[labels.HEALTHCHECK],
        )
        print(f"Created HEALTH issue #{issue.number}")

    to_email = os.environ.get("HEALTHCHECK_TO_EMAIL", "")
    if to_email and os.environ.get("RESEND_API_KEY"):
        email.send_email(
            to=to_email,
            subject=f"ai-harness daily {date_str}",
            body=summary.replace("\n", "<br>"),
        )
        print(f"Emailed digest to {to_email}")

    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return run_healthcheck(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
