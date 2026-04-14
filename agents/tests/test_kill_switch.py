import os
from unittest.mock import patch

import pytest

from agents.lib.kill_switch import agents_paused, exit_if_paused


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("TRUE", True),
        ("  true  ", True),
        ("True", True),
        ("false", False),
        ("", False),
        ("1", False),
        ("yes", False),
    ],
)
def test_agents_paused_env_var(value: str, expected: bool) -> None:
    with patch.dict(os.environ, {"PAUSE_AGENTS": value}, clear=True):
        assert agents_paused() is expected


def test_agents_paused_unset_env_var() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert agents_paused() is False


def test_exit_if_paused_noop_when_unpaused() -> None:
    with patch.dict(os.environ, {}, clear=True):
        exit_if_paused()  # should not raise


def test_exit_if_paused_raises_system_exit_0_when_paused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.dict(os.environ, {"PAUSE_AGENTS": "true"}, clear=True):
        with pytest.raises(SystemExit) as excinfo:
            exit_if_paused()
        assert excinfo.value.code == 0
        captured = capsys.readouterr()
        assert "PAUSE_AGENTS" in captured.out
