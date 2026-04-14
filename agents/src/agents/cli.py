import asyncio
import os
import subprocess
import sys

import click

from agents.lib import gh


@click.group()
def cli() -> None:
    """ai-harness operator CLI."""


@cli.command()
def status() -> None:
    """Print harness status (recent CI/deploy counts, open agent issues)."""
    from typing import Any

    repo = gh.repo()
    ci_runs: list[Any] = list(repo.get_workflow("ci.yml").get_runs()[:20])
    deploy_runs: list[Any] = list(repo.get_workflow("deploy.yml").get_runs()[:20])
    autotriage: list[Any] = list(repo.get_issues(state="open", labels=["autotriage"]))

    ci_ok = sum(1 for r in ci_runs if r.conclusion == "success")
    ci_fail = sum(1 for r in ci_runs if r.conclusion == "failure")
    deploy_ok = sum(1 for r in deploy_runs if r.conclusion == "success")
    deploy_fail = sum(1 for r in deploy_runs if r.conclusion == "failure")

    click.echo(f"CI:      {ci_ok} success / {ci_fail} failure (last {len(ci_runs)})")
    click.echo(f"Deploy:  {deploy_ok} success / {deploy_fail} failure (last {len(deploy_runs)})")
    click.echo(f"Open autotriage issues: {len(autotriage)}")


@cli.command()
@click.option("--pr", type=int, required=True)
@click.option("--pass", "pass_name", type=click.Choice(["quality", "security", "deps"]), required=True)
@click.option("--dry-run", is_flag=True)
def review(pr: int, pass_name: str, dry_run: bool) -> None:
    """Run a single PR review pass."""
    from agents.reviewer import review_pr

    rc = asyncio.run(review_pr(pass_name, pr, dry_run=dry_run))
    sys.exit(rc)


@cli.command()
@click.option("--issue", type=int, required=True)
@click.option("--dry-run", is_flag=True)
def plan(issue: int, dry_run: bool) -> None:
    """Run the planner against an issue."""
    from agents.planner import plan_and_open_pr

    rc = asyncio.run(plan_and_open_pr(issue, dry_run=dry_run))
    sys.exit(rc)


@cli.command()
@click.option("--since-hours", type=int, default=24)
@click.option("--dry-run", is_flag=True)
def triage(since_hours: int, dry_run: bool) -> None:
    """Run the triager."""
    from agents.triager import triage_run

    rc = triage_run(since_hours, dry_run=dry_run)
    sys.exit(rc)


@cli.command(name="deployer-watch")
@click.option("--after-sha", required=True)
@click.option("--window-minutes", type=int, default=10)
@click.option("--dry-run", is_flag=True)
def deployer_watch(after_sha: str, window_minutes: int, dry_run: bool) -> None:
    """Run the post-deploy rollback watcher."""
    from agents.deployer import watch_post_deploy

    rc = watch_post_deploy(after_sha, window_minutes, dry_run=dry_run)
    sys.exit(rc)


@cli.command()
@click.option("--dry-run", is_flag=True)
def healthcheck(dry_run: bool) -> None:
    """Run the daily healthcheck (HEALTH issue + optional email)."""
    from agents.healthcheck import run_healthcheck

    rc = run_healthcheck(dry_run=dry_run)
    sys.exit(rc)


@cli.command()
@click.option("--stale-days", type=int, default=14)
@click.option("--dry-run", is_flag=True)
def stale(stale_days: int, dry_run: bool) -> None:
    """Close stale autotriage issues."""
    from agents.stale import run_stale_close

    rc = run_stale_close(stale_days, dry_run=dry_run)
    sys.exit(rc)


@cli.command(name="release-notes")
@click.option("--since-tag", default=None)
@click.option("--dry-run", is_flag=True)
def release_notes(since_tag: str | None, dry_run: bool) -> None:
    """Generate release notes via Claude."""
    from agents.release_notes import generate_release_notes

    rc = asyncio.run(generate_release_notes(since_tag=since_tag, dry_run=dry_run))
    sys.exit(rc)


@cli.command()
def canary() -> None:
    """Run the weekly canary fixture replay."""
    from agents.canary import run_canary

    rc = run_canary(dry_run=False)
    sys.exit(rc)


def _set_pause(value: str) -> None:
    repo = os.environ.get("GH_REPO", "nt-suuri/ai-harness")
    if value:
        subprocess.run(
            ["gh", "variable", "set", "PAUSE_AGENTS", "--repo", repo, "--body", value],
            check=True,
        )
    else:
        subprocess.run(
            ["gh", "variable", "delete", "PAUSE_AGENTS", "--repo", repo],
            check=False,
        )


@cli.command()
def pause() -> None:
    """Halt all agent workflows (sets PAUSE_AGENTS=true)."""
    _set_pause("true")
    click.echo("PAUSE_AGENTS=true — all agent workflows halted")


@cli.command()
def resume() -> None:
    """Resume agent workflows (clears PAUSE_AGENTS)."""
    _set_pause("")
    click.echo("PAUSE_AGENTS cleared — workflows will run on next trigger")


if __name__ == "__main__":
    cli()
