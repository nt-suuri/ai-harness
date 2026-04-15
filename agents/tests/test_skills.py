import pytest

from agents.lib import skills


def test_available_returns_expected_skills() -> None:
    names = skills.available()
    assert "test-driven-development" in names
    assert "systematic-debugging" in names
    assert "verification-before-completion" in names
    assert "requesting-code-review" in names
    assert "writing-plans" in names


def test_load_returns_text() -> None:
    text = skills.load("systematic-debugging")
    assert len(text) > 100
    assert "debug" in text.lower()


def test_load_missing_raises() -> None:
    with pytest.raises(FileNotFoundError):
        skills.load("does-not-exist")
