import subprocess

import pytest


def test_release_notes_cli_runs_with_dry_run() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.release_notes", "--dry-run", "--help-check-only"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_release_notes_cli_accepts_since_tag() -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.release_notes",
            "--since-tag", "v2026.04.13-0900", "--dry-run", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


@pytest.mark.parametrize("flag", ["--dry-run", ""])
def test_release_notes_cli_accepts_dry_run_flag_optional(flag: str) -> None:
    args = ["uv", "run", "python", "-m", "agents.release_notes", "--help-check-only"]
    if flag:
        args.append(flag)
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode == 0
