"""MCP server exposing harness operations to Claude Code (or any MCP client).

Run via:
    uv run python -m agents.mcp_server
or register in an MCP config (see .mcp/ai-harness.json).
"""

import contextlib
import io
import os
import subprocess

from mcp.server.fastmcp import FastMCP

from agents.lib import gh, labels

mcp = FastMCP("ai-harness")


@mcp.tool()
async def status() -> dict[str, object]:
    """Return harness status: CI/deploy success+failure counts (last 20 each), open autotriage count."""
    repo = gh.repo()
    ci_runs: list[object] = list(repo.get_workflow("ci.yml").get_runs()[:20])
    deploy_runs: list[object] = list(repo.get_workflow("deploy.yml").get_runs()[:20])
    autotriage: list[object] = list(repo.get_issues(state="open", labels=[labels.AUTOTRIAGE]))

    def _count(runs: list[object], conclusion: str) -> int:
        return sum(1 for r in runs if getattr(r, "conclusion", None) == conclusion)

    return {
        "ci": {
            "success": _count(ci_runs, "success"),
            "failure": _count(ci_runs, "failure"),
        },
        "deploy": {
            "success": _count(deploy_runs, "success"),
            "failure": _count(deploy_runs, "failure"),
        },
        "open_autotriage_issues": len(autotriage),
    }


@mcp.tool()
async def triage_dry_run(since_hours: int = 24) -> str:
    """Run the triager in dry-run mode (no GH writes). Returns log lines as a string.

    since_hours: lookback window for Sentry events (default 24).
    """
    from agents.triager import triage_run

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        triage_run(since_hours, dry_run=True)
    return buf.getvalue()


@mcp.tool()
async def pause_agents() -> str:
    """Halt all agent workflows by setting PAUSE_AGENTS=true on the repo."""
    repo = os.environ.get("GH_REPO", "nt-suuri/ai-harness")
    subprocess.run(
        ["gh", "variable", "set", "PAUSE_AGENTS", "--repo", repo, "--body", "true"],
        check=True,
    )
    return f"PAUSE_AGENTS=true set on {repo} — all agent workflows halted"


@mcp.tool()
async def resume_agents() -> str:
    """Resume agent workflows by clearing PAUSE_AGENTS on the repo."""
    repo = os.environ.get("GH_REPO", "nt-suuri/ai-harness")
    subprocess.run(
        ["gh", "variable", "delete", "PAUSE_AGENTS", "--repo", repo],
        check=False,  # ok if it didn't exist
    )
    return f"PAUSE_AGENTS cleared on {repo} — workflows will run on next trigger"


def main() -> None:
    """Run the MCP server over stdio (the default transport for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
