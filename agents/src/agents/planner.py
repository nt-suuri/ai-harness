"""Autonomous planner. Triggered by `agent:build` label on an issue.

Usage:
    python -m agents.planner --issue 42
    python -m agents.planner --issue 42 --dry-run
"""

import argparse
import asyncio
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from agents.lib import gh, kill_switch, planner_validate, prompts
from agents.lib.anthropic import run_agent

_MAX_TURNS = 80
_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep"]
_SLUG_MAX = 40


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.planner", description=__doc__)
    p.add_argument("--issue", type=int, required=True, help="GitHub issue number")
    p.add_argument("--dry-run", action="store_true", help="Plan only; skip branch/commit/push/PR")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _branch_name(issue_number: int, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    slug = slug[:_SLUG_MAX].rstrip("-")
    return f"feat/{issue_number}-{slug}"


def _run_git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _has_changes() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
    )
    return bool(result.stdout.strip())


def _changed_files(cwd: Path) -> list[str]:
    """Files modified or added in the working tree vs HEAD. Used for scoped validation."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=cwd, capture_output=True, text=True, check=True,
    )
    files: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path.strip())
    return files


def _extract_text(messages: list[Any]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


async def plan_and_open_pr(issue_number: int, *, dry_run: bool) -> int:
    """Return 0 on success, 1 if no changes produced, 2 on internal error."""
    repo = gh.repo()
    issue = repo.get_issue(issue_number)

    system = prompts.load("planner")
    user = (
        f"GitHub issue #{issue_number}: {issue.title}\n\n"
        f"Description:\n{issue.body or '(no description)'}\n\n"
        "Implement this. Write code + tests. Keep changes focused to what the issue asks for.\n"
        "When done, provide a brief 1-paragraph plan summary in your last message — it will be the PR description."
    )
    result = await run_agent(
        prompt=user,
        system=system,
        max_turns=_MAX_TURNS,
        allowed_tools=_ALLOWED_TOOLS,
    )
    plan_summary = _extract_text(result.messages)

    if dry_run:
        print(f"--- DRY RUN [issue #{issue_number}] ---")
        print(plan_summary)
        return 0

    REPO_ROOT = Path.cwd()

    def _safe_validate() -> list[str]:
        try:
            return planner_validate.validate(REPO_ROOT, _changed_files(REPO_ROOT))
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            return [f"validation crashed: {type(exc).__name__}: {exc}"]

    validation_errors = _safe_validate()
    if validation_errors:
        error_blob = "\n\n".join(validation_errors)[:4096]
        retry_prompt = (
            "Your previous changes failed validation:\n\n"
            + error_blob
            + "\n\nFix these errors. Do not change the overall approach — just address the specific issues above."
        )
        retry = await run_agent(
            prompt=retry_prompt,
            system=system,
            max_turns=_MAX_TURNS,
            allowed_tools=_ALLOWED_TOOLS,
        )
        plan_summary = _extract_text(retry.messages) or plan_summary
        validation_errors = _safe_validate()

    if validation_errors:
        issue.create_comment(
            "**Planner ran but validation failed after one retry.**\n\n"
            + "\n\n".join(validation_errors)[:4096]
            + "\n\nBranch not pushed. Please review manually."
        )
        return 2

    if not _has_changes():
        issue.create_comment(f"**Planner ran but made no changes.**\n\n{plan_summary}")
        return 1

    branch = _branch_name(issue_number, issue.title)
    _run_git("checkout", "-b", branch)
    _run_git("add", "-A")
    _run_git("commit", "-m", f"feat: {issue.title}\n\nCloses #{issue_number}")
    _run_git("push", "--force-with-lease", "-u", "origin", branch)

    existing = list(repo.get_pulls(state="open", head=f"{repo.owner.login}:{branch}"))
    if existing:
        pr = existing[0]
        pr.edit(body=f"Closes #{issue_number}\n\n**Plan summary (by planner agent):**\n\n{plan_summary}")
        print(f"Updated existing PR #{pr.number}: {pr.html_url}")
    else:
        pr = repo.create_pull(
            base="main",
            head=branch,
            title=f"feat: {issue.title}",
            body=(
                f"Closes #{issue_number}\n\n"
                f"**Plan summary (by planner agent):**\n\n{plan_summary}"
            ),
        )
        print(f"Opened PR #{pr.number}: {pr.html_url}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return asyncio.run(plan_and_open_pr(args.issue, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
