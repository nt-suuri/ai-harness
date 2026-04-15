from pathlib import Path

import pytest

from agents.lib import product_state


def test_load_parses_yaml(tmp_path: Path) -> None:
    p = tmp_path / "state.yaml"
    p.write_text("backlog:\n  - id: B001\n    title: A\n    priority: normal\n    added_by: seed\n    rationale: r\nin_progress: []\nshipped: []\nrejected: []\nmax_open_agent_issues: 2\nlast_pm_run: null\nlast_analyzer_run: null\n")
    state = product_state.load(p)
    assert state.max_open_agent_issues == 2
    assert len(state.backlog) == 1
    assert state.backlog[0].id == "B001"


def test_save_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "state.yaml"
    original = product_state.State(
        max_open_agent_issues=3,
        last_pm_run=None,
        last_analyzer_run=None,
        backlog=[product_state.Item(id="B002", title="T", priority="high", rationale="r", added_by="seed")],
        in_progress=[],
        shipped=[],
        rejected=[],
    )
    product_state.save(p, original)
    round_tripped = product_state.load(p)
    assert round_tripped.backlog[0].title == "T"
    assert round_tripped.max_open_agent_issues == 3


def test_move_to_in_progress_mutates(tmp_path: Path) -> None:
    state = product_state.State(
        max_open_agent_issues=2,
        last_pm_run=None,
        last_analyzer_run=None,
        backlog=[product_state.Item(id="B001", title="x", priority="normal", rationale="r", added_by="seed")],
        in_progress=[],
        shipped=[],
        rejected=[],
    )
    state.start("B001", issue_number=42)
    assert state.backlog == []
    assert state.in_progress[0].id == "B001"
    assert state.in_progress[0].issue_number == 42


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        product_state.load(tmp_path / "nope.yaml")


def test_ship_moves_in_progress_to_shipped(tmp_path: Path) -> None:
    state = product_state.State(
        max_open_agent_issues=2,
        last_pm_run=None,
        last_analyzer_run=None,
        backlog=[],
        in_progress=[product_state.Item(
            id="B001", title="x", priority="normal",
            rationale="r", added_by="seed", issue_number=42,
        )],
        shipped=[],
        rejected=[],
    )
    result = state.ship("B001")
    assert state.in_progress == []
    assert state.shipped[0].id == "B001"
    assert result.id == "B001"


def test_ship_missing_id_raises_keyerror() -> None:
    state = product_state.State(
        max_open_agent_issues=2, last_pm_run=None, last_analyzer_run=None,
        backlog=[], in_progress=[], shipped=[], rejected=[],
    )
    with pytest.raises(KeyError, match="B999"):
        state.ship("B999")


def test_start_missing_id_raises_keyerror() -> None:
    state = product_state.State(
        max_open_agent_issues=2, last_pm_run=None, last_analyzer_run=None,
        backlog=[], in_progress=[], shipped=[], rejected=[],
    )
    with pytest.raises(KeyError, match="B999"):
        state.start("B999", issue_number=1)


def test_load_on_malformed_yaml_raises_valueerror(tmp_path: Path) -> None:
    p = tmp_path / "state.yaml"
    p.write_text(": not: valid: yaml: at: all\n  : :\n")
    with pytest.raises(ValueError, match="invalid state file"):
        product_state.load(p)


def test_load_on_empty_file_uses_defaults(tmp_path: Path) -> None:
    p = tmp_path / "state.yaml"
    p.write_text("")
    state = product_state.load(p)
    assert state.max_open_agent_issues == 2
    assert state.backlog == []
