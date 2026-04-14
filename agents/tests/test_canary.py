from pathlib import Path

from agents.canary import _load_fixture, run_canary

_FIXTURES = Path(__file__).parent / "fixtures"


def test_load_fixture_reads_json() -> None:
    data = _load_fixture("sentry_issues_sample.json")
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["id"] == "sample-1"


def test_load_fixture_reads_text() -> None:
    text = _load_fixture("pr_diff_sample.txt")
    assert isinstance(text, str)
    assert "main.py" in text


def test_run_canary_returns_zero_on_success() -> None:
    rc = run_canary(dry_run=True)
    assert rc == 0


def test_run_canary_validates_sentry_fixture_shape() -> None:
    issues = _load_fixture("sentry_issues_sample.json")
    for issue in issues:
        assert "id" in issue
        assert "title" in issue
        assert "permalink" in issue
        assert "count" in issue
