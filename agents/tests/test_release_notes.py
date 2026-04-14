import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

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


from agents.release_notes import (  # noqa: E402
    _build_user_prompt,
    _format_release_block,
    _next_tag,
    generate_release_notes,
)


def test_next_tag_format() -> None:
    from datetime import UTC, datetime

    tag = _next_tag(datetime(2026, 4, 14, 17, 42, tzinfo=UTC))
    assert tag == "v2026.04.14-1742"


def test_build_user_prompt_includes_target_and_commits() -> None:
    commits = [
        ("abc1234", "feat(api): add /health"),
        ("def5678", "fix(web): nav bug"),
    ]
    prompt = _build_user_prompt(target_tag="v2026.04.14-1742", commits=commits)
    assert "v2026.04.14-1742" in prompt
    assert "feat(api): add /health" in prompt
    assert "fix(web): nav bug" in prompt
    assert "abc1234" in prompt or "abc" in prompt


def test_format_release_block_strips_then_returns() -> None:
    raw = "  ## v1 — 2026-04-14\n\n### Highlights\n- thing\n  "
    block = _format_release_block(raw)
    assert block.startswith("## v1")
    assert block.endswith("- thing")


@pytest.mark.asyncio
async def test_generate_release_notes_returns_1_when_no_commits() -> None:
    fake_repo = MagicMock()
    fake_repo.compare.return_value = MagicMock(commits=[])
    with (
        patch("agents.release_notes.gh.repo", return_value=fake_repo),
        patch("agents.release_notes._latest_tag", return_value="v2026.04.13-0000"),
    ):
        rc = await generate_release_notes(since_tag=None, dry_run=False)
    assert rc == 1


@pytest.mark.asyncio
async def test_generate_release_notes_dry_run_skips_writes() -> None:
    fake_repo = MagicMock()
    fake_repo.compare.return_value = MagicMock(
        commits=[
            MagicMock(sha="abc1234", commit=MagicMock(message="feat: new thing")),
        ],
    )
    with (
        patch("agents.release_notes.gh.repo", return_value=fake_repo),
        patch("agents.release_notes._latest_tag", return_value="v2026.04.13-0000"),
        patch("agents.release_notes.prompts.load", return_value="sys"),
        patch("agents.release_notes.run_agent", new=AsyncMock()) as mock_run,
        patch("agents.release_notes._write_releases_md") as write_md,
        patch("agents.release_notes._run_git") as gitcmd,
    ):
        mock_run.return_value = MagicMock(
            messages=[{"type": "text", "text": "## v1 — 2026-04-14\n\n### Highlights\n- new thing"}],
            stopped_reason="complete",
        )
        rc = await generate_release_notes(since_tag=None, dry_run=True)

    assert rc == 0
    write_md.assert_not_called()
    gitcmd.assert_not_called()
    fake_repo.create_git_release.assert_not_called()


@pytest.mark.asyncio
async def test_generate_release_notes_writes_and_releases() -> None:
    fake_repo = MagicMock()
    fake_repo.compare.return_value = MagicMock(
        commits=[
            MagicMock(sha="abc1234", commit=MagicMock(message="feat: new thing")),
        ],
    )
    fake_repo.create_git_release.return_value = MagicMock(html_url="https://x/release")

    with (
        patch("agents.release_notes.gh.repo", return_value=fake_repo),
        patch("agents.release_notes._latest_tag", return_value="v2026.04.13-0000"),
        patch("agents.release_notes.prompts.load", return_value="sys"),
        patch("agents.release_notes.run_agent", new=AsyncMock()) as mock_run,
        patch("agents.release_notes._write_releases_md") as write_md,
        patch("agents.release_notes._run_git") as gitcmd,
    ):
        mock_run.return_value = MagicMock(
            messages=[{"type": "text", "text": "## v1 — 2026-04-14\n\n### Highlights\n- new thing"}],
            stopped_reason="complete",
        )
        rc = await generate_release_notes(since_tag=None, dry_run=False)

    assert rc == 0
    write_md.assert_called_once()
    gitcmd.assert_called()
    fake_repo.create_git_release.assert_called_once()
