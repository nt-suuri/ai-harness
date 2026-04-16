import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.smart_rollback import analyze, _parse_response, _format_events


def _fake_result(text: str) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    result = MagicMock()
    result.messages = [msg]
    return result


@pytest.mark.asyncio
async def test_new_error_type_triggers_revert() -> None:
    llm_response = (
        "DECISION: REVERT\n"
        "ANALYSIS: A new AttributeError in checkout.py appeared post-deploy that was absent in baseline. "
        "The error stack trace points directly to code changed in this commit. "
        "This is a clear application regression requiring immediate rollback."
    )
    with patch("agents.smart_rollback.run_agent", new=AsyncMock(return_value=_fake_result(llm_response))):
        decision, analysis = await analyze(
            "abc1234",
            baseline_events=[{"title": "TimeoutError", "message": "connection timeout"}],
            post_events=[
                {"title": "TimeoutError", "message": "connection timeout"},
                {"title": "AttributeError: 'NoneType' has no attribute 'id'", "message": ""},
            ],
        )
    assert decision == "REVERT"
    assert "regression" in analysis.lower() or "AttributeError" in analysis


@pytest.mark.asyncio
async def test_stable_errors_ignored() -> None:
    llm_response = (
        "DECISION: IGNORE\n"
        "ANALYSIS: Error patterns post-deploy are consistent with baseline levels. "
        "All observed errors are infrastructure-related connection timeouts with no new error types. "
        "No action required."
    )
    with patch("agents.smart_rollback.run_agent", new=AsyncMock(return_value=_fake_result(llm_response))):
        decision, analysis = await analyze(
            "abc1234",
            baseline_events=[{"title": "ConnectionReset"}, {"title": "ConnectionReset"}],
            post_events=[{"title": "ConnectionReset"}],
        )
    assert decision == "IGNORE"
    assert len(analysis) > 0


@pytest.mark.asyncio
async def test_ambiguous_spike_alerts() -> None:
    llm_response = (
        "DECISION: ALERT\n"
        "ANALYSIS: Error count increased post-deploy but the error types are ambiguous — "
        "could be transient load or a real regression in the new authentication flow. "
        "Opening an issue for manual investigation is the prudent course."
    )
    with patch("agents.smart_rollback.run_agent", new=AsyncMock(return_value=_fake_result(llm_response))):
        decision, analysis = await analyze(
            "abc1234",
            baseline_events=[{"title": "AuthError"}],
            post_events=[{"title": "AuthError"}, {"title": "AuthError"}, {"title": "AuthError"}],
        )
    assert decision == "ALERT"
    assert len(analysis) > 0


def test_parse_response_handles_unknown_decision() -> None:
    decision, _ = _parse_response("DECISION: UNKNOWN\nANALYSIS: something")
    assert decision == "ALERT"


def test_parse_response_case_insensitive() -> None:
    decision, analysis = _parse_response("decision: revert\nanalysis: bad deploy")
    assert decision == "REVERT"
    assert "bad deploy" in analysis


def test_format_events_empty() -> None:
    assert _format_events([]) == "(none)"


def test_format_events_aggregates_by_title() -> None:
    events = [{"title": "OOMError"}, {"title": "OOMError"}, {"title": "TimeoutError"}]
    result = _format_events(events)
    assert "OOMError: 2" in result
    assert "TimeoutError: 1" in result
