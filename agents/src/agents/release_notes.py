"""Release-notes generator. Reads commits since last tag, asks Claude to write notes.

Usage:
    python -m agents.release_notes
    python -m agents.release_notes --since-tag v2026.04.13-0900 --dry-run
"""

import argparse
import asyncio
import sys

from agents.lib import kill_switch


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.release_notes", description=__doc__)
    p.add_argument("--since-tag", help="Previous release tag (default: most recent tag, or all of HEAD)")
    p.add_argument("--dry-run", action="store_true", help="Print notes; skip RELEASES.md write + GH release")
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


async def generate_release_notes(*, since_tag: str | None, dry_run: bool) -> int:
    """Return 0 on success, 1 on no-commits-since-last-tag, 2 on internal error."""
    raise NotImplementedError("Task 3 fills this in")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return asyncio.run(generate_release_notes(since_tag=args.since_tag, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
