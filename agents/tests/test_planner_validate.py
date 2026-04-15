import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from agents.lib import planner_validate


def test_validate_returns_empty_when_all_pass(tmp_path: Path) -> None:
    with patch("agents.lib.planner_validate._run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        errors = planner_validate.validate(tmp_path, ["apps/api/src/api/new.py"])
    assert errors == []


def test_validate_returns_ruff_error_detail(tmp_path: Path) -> None:
    ruff_fail = subprocess.CompletedProcess(
        [], 1, "E501 Line too long\nF401 unused import\n", ""
    )
    with patch("agents.lib.planner_validate._run") as run:
        run.side_effect = [
            ruff_fail,  # ruff call fails
            subprocess.CompletedProcess([], 0, "", ""),  # compileall passes
        ]
        errors = planner_validate.validate(tmp_path, ["x.py"])
    assert len(errors) == 1
    assert "ruff" in errors[0].lower()
    assert "E501" in errors[0]


def test_validate_returns_import_error_detail(tmp_path: Path) -> None:
    with patch("agents.lib.planner_validate._run") as run:
        run.side_effect = [
            subprocess.CompletedProcess([], 0, "", ""),  # ruff passes
            subprocess.CompletedProcess([], 1, "", "ImportError: no module 'foo'\n"),
        ]
        errors = planner_validate.validate(tmp_path, ["apps/api/src/api/x.py"])
    assert len(errors) == 1
    assert "import" in errors[0].lower()
    assert "ImportError" in errors[0]


def test_validate_runs_touched_tests_when_test_file_present(tmp_path: Path) -> None:
    with patch("agents.lib.planner_validate._run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        planner_validate.validate(tmp_path, ["apps/api/tests/test_hello.py", "apps/api/src/api/hello.py"])
        calls = [c.args[0] for c in run.call_args_list]
        pytest_calls = [c for c in calls if "pytest" in c]
        assert pytest_calls, "pytest should be invoked when a test file is in the change set"
        assert "apps/api/tests/test_hello.py" in pytest_calls[0]


def test_validate_pytest_failure_returned_as_error(tmp_path: Path) -> None:
    with patch("agents.lib.planner_validate._run") as run:
        run.side_effect = [
            subprocess.CompletedProcess([], 0, "", ""),  # ruff ok
            subprocess.CompletedProcess([], 0, "", ""),  # compileall ok
            subprocess.CompletedProcess([], 1, "AssertionError: expected 200 got 404\n", ""),
        ]
        errors = planner_validate.validate(tmp_path, ["apps/api/tests/test_x.py", "apps/api/src/api/x.py"])
    assert len(errors) == 1
    assert "pytest" in errors[0].lower()
    assert "AssertionError" in errors[0]


def test_validate_collects_all_three_errors_when_all_fail(tmp_path: Path) -> None:
    with patch("agents.lib.planner_validate._run") as run:
        run.side_effect = [
            subprocess.CompletedProcess([], 1, "E501 line too long", ""),  # ruff fails
            subprocess.CompletedProcess([], 1, "", "SyntaxError"),           # compile fails
            subprocess.CompletedProcess([], 1, "FAILED test_x", ""),         # pytest fails
        ]
        errors = planner_validate.validate(
            tmp_path, ["apps/api/src/api/x.py", "apps/api/tests/test_x.py"]
        )
    assert len(errors) == 3, f"expected 3 errors, got {len(errors)}: {errors}"
    assert any("ruff" in e.lower() for e in errors)
    assert any("syntax" in e.lower() or "import" in e.lower() for e in errors)
    assert any("pytest" in e.lower() for e in errors)


def test_validate_drops_absolute_and_traversal_paths(tmp_path: Path) -> None:
    """Security guard: absolute paths and .. segments are filtered before any subprocess call."""
    with patch("agents.lib.planner_validate._run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        errors = planner_validate.validate(
            tmp_path, ["/etc/passwd", "../../../etc/passwd", "apps/api/src/api/ok.py"]
        )
    assert errors == []
    # Verify the subprocess was called only with the safe file:
    for call in run.call_args_list:
        cmd = call.args[0]
        assert "/etc/passwd" not in cmd
        assert "../../../etc/passwd" not in cmd


def test_validate_returns_timeout_error_when_subprocess_hangs(tmp_path: Path) -> None:
    """TimeoutExpired is converted to a failed CompletedProcess, not propagated."""
    with patch("agents.lib.planner_validate.subprocess.run") as raw_run:
        raw_run.side_effect = subprocess.TimeoutExpired(cmd=["ruff"], timeout=120)
        errors = planner_validate.validate(tmp_path, ["apps/api/src/api/x.py"])
    # timeout hits ruff first — we get a ruff-failure error that mentions the timeout
    assert len(errors) >= 1
    assert "timed out" in errors[0].lower() or "ruff" in errors[0].lower()
