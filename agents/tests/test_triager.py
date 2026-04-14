import subprocess

import pytest


def test_triager_cli_accepts_no_args_with_help_check() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.triager", "--help-check-only"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_triager_cli_accepts_since_hours() -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.triager",
            "--since-hours", "48", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


@pytest.mark.parametrize("hours", ["1", "24", "168"])
def test_triager_cli_accepts_various_since_values(hours: str) -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.triager",
            "--since-hours", hours, "--dry-run", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
