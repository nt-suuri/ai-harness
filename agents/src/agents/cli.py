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


@cli.command()
@click.option("--url", default="https://ai-harness-production.up.railway.app", help="Deployed app base URL")
def verify(url: str) -> None:
    """Live integration check — hits deployed app + GH API + reports."""
    import urllib.error
    import urllib.request
    from datetime import datetime, timedelta, timezone

    rows: list[tuple[str, bool, str]] = []

    # 1. /api/ping
    try:
        with urllib.request.urlopen(f"{url}/api/ping", timeout=15) as resp:
            ok = resp.status == 200 and json.loads(resp.read())["status"] == "pong"
            rows.append(("Deployed /api/ping", ok, f"HTTP {resp.status}"))
    except Exception as e:
        rows.append(("Deployed /api/ping", False, str(e)))

    # 2. /api/version
    try:
        with urllib.request.urlopen(f"{url}/api/version", timeout=15) as resp:
            data = json.loads(resp.read())
            rows.append(("Deployed /api/version", True, f"sha={data.get('sha')} env={data.get('env')} up={data.get('uptime_seconds')}s"))
    except Exception as e:
        rows.append(("Deployed /api/version", False, str(e)))

    # 3. /api/status
    try:
        with urllib.request.urlopen(f"{url}/api/status", timeout=15) as resp:
            data = json.loads(resp.read())
            ci = data.get("ci", {})
            dep = data.get("deploy", {})
            rows.append(("Deployed /api/status", True, f"ci={ci.get('success')}/{ci.get('failure')} deploy={dep.get('success')}/{dep.get('failure')} issues={data.get('open_autotriage_issues')}"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:80]
        rows.append(("Deployed /api/status", False, f"HTTP {e.code}: {body}"))
    except Exception as e:
        rows.append(("Deployed /api/status", False, str(e)))

    # 4. Workflows count
    repo_name = os.environ.get("GH_REPO", "nt-suuri/ai-harness")
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo_name}/actions/workflows"],
            capture_output=True, text=True, check=True,
        )
        wf = json.loads(result.stdout)
        names = [w["name"] for w in wf.get("workflows", [])]
        rows.append((f"Workflows ({len(names)})", True, ", ".join(names[:6]) + ("…" if len(names) > 6 else "")))
    except Exception as e:
        rows.append(("Workflows", False, str(e)))

    # 5. Secrets
    try:
        result = subprocess.run(
            ["gh", "secret", "list", "--repo", repo_name, "--json", "name"],
            capture_output=True, text=True, check=True,
        )
        secrets = [s["name"] for s in json.loads(result.stdout)]
        rows.append((f"Secrets ({len(secrets)} set)", True, ", ".join(secrets) or "(none)"))
    except Exception as e:
        rows.append(("Secrets", False, str(e)))

    # 6. Variables
    try:
        result = subprocess.run(
            ["gh", "variable", "list", "--repo", repo_name, "--json", "name,value"],
            capture_output=True, text=True, check=True,
        )
        variables = json.loads(result.stdout)
        var_str = ", ".join(f"{v['name']}={v['value']!r}" for v in variables) or "(none)"
        rows.append((f"Variables ({len(variables)} set)", True, var_str))
    except Exception as e:
        rows.append(("Variables", False, str(e)))

    # 7. Recent agent-created issues
    try:
        repo = gh.repo()
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)  # noqa: UP017
        recent = [i for i in repo.get_issues(state="all", labels=["autotriage"]) if i.created_at >= seven_days_ago]
        rows.append(("Recent autotriage issues (7d)", True, f"{len(recent)} created"))
    except Exception as e:
        rows.append(("Recent autotriage issues", False, str(e)))

    failed = 0
    for label, ok, detail in rows:
        mark = click.style("✓", fg="green") if ok else click.style("✗", fg="red")
        click.echo(f"  {mark}  {label:<32} {detail}")
        if not ok:
            failed += 1

    if failed:
        click.echo(f"\n{failed} verify check(s) failed", err=True)
        sys.exit(1)
    click.echo(f"\nAll {len(rows)} verify checks green.")


@cli.command(name="install-mcp")
@click.option("--scope", type=click.Choice(["user", "project"]), default="user", help="Where to register")
@click.option("--dry-run", is_flag=True)
def install_mcp(scope: str, dry_run: bool) -> None:
    """Register the ai-harness MCP server in Claude Code's config."""
    from pathlib import Path

    repo_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    server_entry = {
        "command": "uv",
        "args": ["run", "python", "-m", "agents.mcp_server"],
        "cwd": repo_root,
        "env": {"GH_REPO": os.environ.get("GH_REPO", "nt-suuri/ai-harness")},
    }

    config_path = Path.home() / ".claude.json" if scope == "user" else Path(repo_root) / ".mcp.json"

    config = json.loads(config_path.read_text()) if config_path.exists() else {}

    config.setdefault("mcpServers", {})
    existing = config["mcpServers"].get("ai-harness")

    if existing == server_entry:
        click.echo(f"ai-harness MCP already registered at {config_path}")
        return

    config["mcpServers"]["ai-harness"] = server_entry

    if dry_run:
        click.echo(f"--- DRY RUN [{config_path}] ---")
        click.echo(json.dumps(config, indent=2))
        return

    config_path.write_text(json.dumps(config, indent=2) + "\n")
    click.echo(f"Registered ai-harness MCP server at {config_path}")
    click.echo("Reload Claude Code (or your MCP client) to pick up the change.")


@cli.command(name="uninstall-mcp")
@click.option("--scope", type=click.Choice(["user", "project"]), default="user")
@click.option("--dry-run", is_flag=True)
def uninstall_mcp(scope: str, dry_run: bool) -> None:
    """Remove the ai-harness MCP server entry from Claude Code's config."""
    from pathlib import Path

    if scope == "user":
        config_path = Path.home() / ".claude.json"
    else:
        repo_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        config_path = Path(repo_root) / ".mcp.json"

    if not config_path.exists():
        click.echo(f"No config file at {config_path}; nothing to uninstall")
        return

    config = json.loads(config_path.read_text())
    servers = config.get("mcpServers", {})
    if "ai-harness" not in servers:
        click.echo(f"ai-harness not registered in {config_path}; nothing to do")
        return

    del servers["ai-harness"]
    if not servers:
        config.pop("mcpServers", None)

    if dry_run:
        click.echo(f"--- DRY RUN [{config_path}] ---")
        click.echo(json.dumps(config, indent=2))
        return

    config_path.write_text(json.dumps(config, indent=2) + "\n")
    click.echo(f"Removed ai-harness from {config_path}")


if __name__ == "__main__":
    cli()
