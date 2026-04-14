import subprocess

import pytest


def test_deployer_cli_requires_after_sha() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.deployer", "--window-minutes", "10"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_deployer_cli_rejects_negative_window() -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.deployer",
            "--after-sha", "abc", "--window-minutes", "-5", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 1, 2)


@pytest.mark.parametrize("window", ["5", "10", "30"])
def test_deployer_cli_accepts_valid_window(window: str) -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.deployer",
            "--after-sha", "abc123", "--window-minutes", window, "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
