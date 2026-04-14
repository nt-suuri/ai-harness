import pytest

from agents.lib import prompts


def test_list_prompts_returns_sorted_known_names() -> None:
    names = prompts.list_prompts()
    assert names == sorted(names)
    assert "planner" in names
    assert "reviewer_quality" in names
    assert "reviewer_security" in names
    assert "reviewer_deps" in names
    assert "triager" in names
    assert "healthcheck" in names


def test_load_returns_nonempty_string() -> None:
    body = prompts.load("planner")
    assert isinstance(body, str)
    assert len(body) > 0


def test_load_unknown_prompt_raises_filenotfound() -> None:
    with pytest.raises(FileNotFoundError):
        prompts.load("does_not_exist")
