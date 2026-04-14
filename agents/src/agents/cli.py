import asyncio
import json
import os
import shutil
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


@cli.command()
def doctor() -> None:
    """Check operator environment health."""
    rows: list[tuple[str, bool, str]] = []

    rows.append(("gh CLI", shutil.which("gh") is not None, shutil.which("gh") or "missing"))
    rows.append(("uv CLI", shutil.which("uv") is not None, shutil.which("uv") or "missing"))
    rows.append(("railway CLI", shutil.which("railway") is not None, shutil.which("railway") or "missing"))
    rows.append(("flyctl", shutil.which("flyctl") is not None, shutil.which("flyctl") or "missing (not used by current pipeline)"))

    gh_token_ok = bool(os.environ.get("GITHUB_TOKEN"))
    if not gh_token_ok:
        try:
            tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
            gh_token_ok = bool(tok)
        except Exception:
            gh_token_ok = False
    rows.append(("GitHub auth", gh_token_ok, "via env or gh auth"))

    rows.append(("ANTHROPIC_API_KEY", bool(os.environ.get("ANTHROPIC_API_KEY")), "shell env"))
    rows.append(("SENTRY_AUTH_TOKEN", bool(os.environ.get("SENTRY_AUTH_TOKEN")), "shell env"))
    rows.append(("RESEND_API_KEY", bool(os.environ.get("RESEND_API_KEY")), "shell env"))

    try:
        repo = gh.repo()
        rows.append(("Repo access", True, repo.full_name))
    except Exception as e:
        rows.append(("Repo access", False, f"error: {e}"))

    try:
        result = subprocess.run(
            ["gh", "variable", "list", "--repo", os.environ.get("GH_REPO", "nt-suuri/ai-harness"), "--json", "name,value"],
            capture_output=True,
            text=True,
            check=True,
        )
        vars_data = json.loads(result.stdout)
        pause_var = next((v for v in vars_data if v["name"] == "PAUSE_AGENTS"), None)
        if pause_var is None:
            rows.append(("PAUSE_AGENTS", True, "unset (running)"))
        else:
            paused = pause_var["value"].strip().lower() == "true"
            rows.append(("PAUSE_AGENTS", not paused, "PAUSED" if paused else f"running (value={pause_var['value']!r})"))
    except Exception as e:
        rows.append(("PAUSE_AGENTS", False, f"could not check: {e}"))

    for label, ok, detail in rows:
        mark = click.style("✓", fg="green") if ok else click.style("✗", fg="red")
        click.echo(f"  {mark}  {label:<22} {detail}")

    failed = sum(1 for _, ok, _ in rows if not ok)
    if failed:
        click.echo(f"\n{failed} check(s) failed.", err=True)
        sys.exit(1)
    click.echo("\nAll checks green.")


@cli.command()
@click.option("--workflow", "-w", default="ci.yml")
@click.option("--limit", "-n", type=int, default=10)
def logs(workflow: str, limit: int) -> None:
    """Show recent workflow run summaries."""
    from typing import Any

    repo = gh.repo()
    runs: list[Any] = list(repo.get_workflow(workflow).get_runs()[:limit])
    if not runs:
        click.echo(f"No runs for {workflow}")
        return
    for r in runs:
        status_color = {"success": "green", "failure": "red", None: "yellow"}.get(r.conclusion, "white")
        status_text = r.conclusion or r.status
        click.echo(
            f"  {click.style(status_text or 'queued', fg=status_color):<20} "
            f"{r.head_sha[:7]}  {r.created_at.strftime('%Y-%m-%d %H:%M')}  "
            f"{r.head_commit.message.splitlines()[0][:60] if r.head_commit else ''}"
        )


@cli.command(name="next-tag")
def next_tag() -> None:
    """Print the tag that release-notes would create now."""
    from agents.release_notes import _next_tag

    click.echo(_next_tag())


@cli.command(name="self-test")
def self_test() -> None:
    """Smoke-test every agent's CLI + run the canary fixture replay."""
    agents = ["reviewer", "planner", "deployer", "triager", "healthcheck", "stale", "release_notes", "canary"]

    rows: list[tuple[str, bool, str]] = []

    for name in agents:
        result = subprocess.run(
            ["uv", "run", "python", "-m", f"agents.{name}", "--help"],
            capture_output=True,
            text=True,
        )
        ok = result.returncode == 0
        detail = "CLI loaded" if ok else f"exit={result.returncode}"
        rows.append((f"agents.{name} CLI", ok, detail))

    from agents.canary import run_canary

    canary_ok = run_canary(dry_run=False) == 0
    rows.append(("canary fixture replay", canary_ok, "all green" if canary_ok else "structural assertion failed"))

    failed = 0
    for label, ok, detail in rows:
        mark = click.style("✓", fg="green") if ok else click.style("✗", fg="red")
        click.echo(f"  {mark}  {label:<30} {detail}")
        if not ok:
            failed += 1

    if failed:
        click.echo(f"\n{failed} self-test(s) failed", err=True)
        sys.exit(1)
    click.echo("\nAll self-tests green.")


if __name__ == "__main__":
    cli()
