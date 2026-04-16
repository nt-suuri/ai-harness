import subprocess
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="timed out after 120s")


def _ruff(cwd: Path, files: list[str]) -> str | None:
    if not files:
        return None
    result = _run(["uv", "run", "ruff", "check", *files], cwd)
    if result.returncode == 0:
        return None
    return f"ruff check failed:\n{result.stdout.strip()}"


def _compile(cwd: Path, files: list[str]) -> str | None:
    py_files = [f for f in files if f.endswith(".py")]
    if not py_files:
        return None
    result = _run(["uv", "run", "python", "-m", "compileall", "-q", *py_files], cwd)
    if result.returncode == 0:
        return None
    return f"python import/syntax check failed:\n{result.stderr.strip() or result.stdout.strip()}"


def _pytest(cwd: Path, test_files: list[str]) -> str | None:
    if not test_files:
        return None
    result = _run(["uv", "run", "pytest", "-x", "--no-header", *test_files], cwd)
    if result.returncode == 0:
        return None
    return f"pytest failed:\n{result.stdout.strip()[-2000:]}"


def ruff_fix(cwd: Path, changed_files: list[str]) -> None:
    """Best-effort auto-fix ruff violations in-place. Silent on failure."""
    py_files = [
        f for f in changed_files
        if f.endswith(".py") and not Path(f).is_absolute() and ".." not in Path(f).parts
    ]
    if not py_files:
        return
    _run(["uv", "run", "ruff", "check", "--fix", "--unsafe-fixes", *py_files], cwd)


def validate(cwd: Path, changed_files: list[str]) -> list[str]:
    """Return a list of error messages. Empty list = validation passed."""
    safe_files = [
        f for f in changed_files
        if not Path(f).is_absolute() and ".." not in Path(f).parts
    ]
    py_files = [f for f in safe_files if f.endswith(".py")]
    test_files = [f for f in safe_files if "/tests/" in f and f.endswith(".py")]

    errors: list[str] = []
    for err in (_ruff(cwd, py_files), _compile(cwd, safe_files), _pytest(cwd, test_files)):
        if err:
            errors.append(err)
    return errors


async def validate_with_triage(cwd: Path, changed_files: list[str]) -> list[str]:
    """Like validate(), but categorizes pytest failures via the test triage agent."""
    from agents.test_triage import categorize

    errors = validate(cwd, changed_files)
    triaged: list[str] = []
    for err in errors:
        if err.startswith("pytest failed:"):
            category, action = await categorize(err, changed_files)
            if category == "FLAKY":
                test_files = [f for f in changed_files if "/tests/" in f and f.endswith(".py")]
                retry_err = _pytest(cwd, test_files)
                if retry_err is None:
                    continue
            elif category == "UNRELATED":
                continue
            triaged.append(f"pytest failed ({category}, action={action}):\n{err.split(':', 1)[1].strip()}")
        else:
            triaged.append(err)
    return triaged
