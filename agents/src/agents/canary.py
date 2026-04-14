"""Weekly canary replay. Reads sanitized fixtures, asserts agent code still
parses them correctly. Catches regressions in agent parsers/prompts.

Usage:
    python -m agents.canary
    python -m agents.canary --dry-run
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agents.lib import kill_switch
from agents.triager import _format_issue_body, _make_marker

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agents.canary", description=__doc__)
    p.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--help-check-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _load_fixture(name: str) -> Any:
    path = _FIXTURE_DIR / name
    if name.endswith(".json"):
        return json.loads(path.read_text())
    return path.read_text()


def run_canary(*, dry_run: bool) -> int:
    """Return 0 if all canaries green, 1 if any structural assertion failed."""
    failures = 0

    sentry_issues = _load_fixture("sentry_issues_sample.json")
    for issue in sentry_issues:
        marker = _make_marker(str(issue["id"]))
        body = _format_issue_body(issue, marker)
        if marker not in body:
            print(f"FAIL: triager body missing marker for {issue['id']}")
            failures += 1
        if "Sentry permalink" not in body:
            print("FAIL: triager body missing permalink line")
            failures += 1

    diff = _load_fixture("pr_diff_sample.txt")
    if "@@" not in diff:
        print("FAIL: pr_diff_sample.txt does not look like a diff")
        failures += 1

    if failures:
        print(f"canary: {failures} failure(s)")
        return 1
    print("canary: all green")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.help_check_only:
        return 0
    kill_switch.exit_if_paused()
    return run_canary(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
