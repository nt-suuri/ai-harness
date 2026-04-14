import subprocess

import pytest


def test_reviewer_cli_requires_pass_arg() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.reviewer", "--pr", "1"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "pass" in result.stderr.lower() or "pass" in result.stdout.lower()


def test_reviewer_cli_rejects_unknown_pass() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.reviewer", "--pass", "bogus", "--pr", "1"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


@pytest.mark.parametrize("pass_name", ["quality", "security", "deps"])
def test_reviewer_cli_accepts_valid_pass(pass_name: str) -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.reviewer",
            "--pass", pass_name, "--pr", "1", "--dry-run", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
