"""Release-notes generator. Reads commits since last tag, asks Claude to write notes.

Usage:
    python -m agents.release_notes
    python -m agents.release_notes --since-tag v2026.04.13-0900 --dry-run
"""

import argparse
import asyncio
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.lib import gh, kill_switch, prompts
from agents.lib.anthropic import run_agent

_RELEASES_FILE = Path(__file__).resolve().parents[3] / "RELEASES.md"
_MAX_TURNS = 20


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.release_notes", description=__doc__)
    p.add_argument("--since-tag", help="Previous release tag (default: most recent tag, or all of HEAD)")
    p.add_argument("--dry-run", action="store_true", help="Print notes; skip RELEASES.md write + GH release")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _next_tag(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return now.strftime("v%Y.%m.%d-%H%M")


def _latest_tag(repo: Any) -> str | None:
    tags = list(repo.get_tags()[:1])
    if not tags:
        return None
    return str(tags[0].name)


def _run_git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _write_releases_md(block: str) -> None:
    existing = _RELEASES_FILE.read_text() if _RELEASES_FILE.exists() else "# Releases\n\n"
    body = existing.removeprefix("# Releases").lstrip()
    _RELEASES_FILE.write_text(f"# Releases\n\n{block}\n\n{body}".strip() + "\n")


def _build_user_prompt(*, target_tag: str, commits: list[tuple[str, str]]) -> str:
    lines = [
        f"Target tag: {target_tag}",
        f"Date: {datetime.now(UTC).date().isoformat()}",
        "",
        "Commits since last release:",
    ]
    for sha, msg in commits:
        lines.append(f"- {sha[:7]} {msg.splitlines()[0]}")
    lines.append("")
    lines.append("Write the release notes for these commits.")
    return "\n".join(lines)


def _extract_text(messages: list[Any]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


def _format_release_block(raw: str) -> str:
    return raw.strip()


async def generate_release_notes(*, since_tag: str | None, dry_run: bool) -> int:
    """Return 0 on success, 1 if no commits, 2 on internal error."""
    repo = gh.repo()
    prev_tag = since_tag or _latest_tag(repo)
    target_tag = _next_tag()

    if prev_tag:
        comparison = repo.compare(prev_tag, "main")
        commits_raw = list(comparison.commits)
    else:
        commits_raw = list(repo.get_commits(sha="main")[:50])

    if not commits_raw:
        print("No commits since last release; nothing to do", flush=True)
        return 1

    commits = [(c.sha, c.commit.message) for c in commits_raw]

    system = prompts.load("release_notes")
    user = _build_user_prompt(target_tag=target_tag, commits=commits)
    result = await run_agent(
        prompt=user,
        system=system,
        max_turns=_MAX_TURNS,
        allowed_tools=[],
    )
    block = _format_release_block(_extract_text(result.messages))

    if dry_run:
        print(f"--- DRY RUN [target {target_tag}] ---")
        print(block)
        return 0

    _write_releases_md(block)
    _run_git("add", "RELEASES.md")
    _run_git(
        "-c", "user.name=ai-harness-bot",
        "-c", "user.email=ai-harness@local",
        "commit",
        "-m", f"chore(release): {target_tag}",
    )
    _run_git("push")

    release = repo.create_git_release(
        tag=target_tag,
        name=target_tag,
        message=block,
        target_commitish="main",
    )
    print(f"Created release {target_tag}: {release.html_url}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return asyncio.run(generate_release_notes(since_tag=args.since_tag, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
