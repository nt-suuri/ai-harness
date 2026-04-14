import subprocess


def test_planner_cli_requires_issue_arg() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.planner"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_planner_cli_rejects_non_int_issue() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "agents.planner", "--issue", "abc"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_planner_cli_accepts_int_issue_with_help_check_only() -> None:
    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "agents.planner",
            "--issue", "42", "--dry-run", "--help-check-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
