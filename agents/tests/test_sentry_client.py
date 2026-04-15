import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from agents.lib import sentry


def test_client_requires_sentry_auth_token() -> None:
    with patch.dict(os.environ, {}, clear=True), pytest.raises(KeyError):
        sentry._client()


def test_client_sets_bearer_header() -> None:
    with (
        patch.dict(os.environ, {"SENTRY_AUTH_TOKEN": "abc"}, clear=True),
        patch("agents.lib.sentry.httpx.Client") as client_cls,
    ):
        sentry._client()
        call_kwargs = client_cls.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer abc"
        assert call_kwargs["base_url"] == "https://sentry.io/api/0"
        assert call_kwargs["timeout"] == 30


def test_base_url_uses_region_when_set() -> None:
    with patch.dict(os.environ, {"SENTRY_REGION": "de"}, clear=True):
        assert sentry._base_url() == "https://de.sentry.io/api/0"


def test_base_url_defaults_when_region_unset() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert sentry._base_url() == "https://sentry.io/api/0"


def test_base_url_strips_and_lowercases_region() -> None:
    with patch.dict(os.environ, {"SENTRY_REGION": "  US  "}, clear=True):
        assert sentry._base_url() == "https://us.sentry.io/api/0"


def test_client_uses_regional_base_url() -> None:
    with (
        patch.dict(os.environ, {"SENTRY_AUTH_TOKEN": "abc", "SENTRY_REGION": "de"}, clear=True),
        patch("agents.lib.sentry.httpx.Client") as client_cls,
    ):
        sentry._client()
        assert client_cls.call_args.kwargs["base_url"] == "https://de.sentry.io/api/0"


def test_list_events_default_since_is_24h_ago() -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    fake_client.get.return_value = MagicMock(
        status_code=200,
        json=MagicMock(return_value=[{"id": "e1"}]),
    )

    with patch("agents.lib.sentry._client", return_value=fake_client):
        events = sentry.list_events("myorg", "myproj")

    assert events == [{"id": "e1"}]
    fake_client.get.assert_called_once()
    call = fake_client.get.call_args
    assert call.args[0] == "/projects/myorg/myproj/events/"
    since = call.kwargs["params"]["since"]
    since_dt = datetime.fromisoformat(since)
    now = datetime.now(UTC)
    assert timedelta(hours=23, minutes=59) <= now - since_dt <= timedelta(hours=24, minutes=1)


def test_list_events_custom_since() -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    fake_client.get.return_value = MagicMock(
        status_code=200,
        json=MagicMock(return_value=[]),
    )
    pinned = datetime(2026, 1, 1, tzinfo=UTC)

    with patch("agents.lib.sentry._client", return_value=fake_client):
        sentry.list_events("org", "proj", since=pinned)

    assert fake_client.get.call_args.kwargs["params"]["since"] == pinned.isoformat()


def test_list_events_raises_for_status() -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    resp = MagicMock()
    resp.raise_for_status.side_effect = Exception("401 unauthorized")
    fake_client.get.return_value = resp

    with patch("agents.lib.sentry._client", return_value=fake_client), pytest.raises(Exception, match="401"):
        sentry.list_events("o", "p")


def test_count_events_since_returns_int() -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    fake_client.get.return_value = MagicMock(
        status_code=200,
        json=MagicMock(return_value=[{"id": "e1"}, {"id": "e2"}, {"id": "e3"}]),
    )

    pinned = datetime(2026, 4, 14, 10, 0, 0, tzinfo=UTC)
    with patch("agents.lib.sentry._client", return_value=fake_client):
        n = sentry.count_events_since("myorg", "myproj", since=pinned)

    assert n == 3
    fake_client.get.assert_called_once()
    assert fake_client.get.call_args.kwargs["params"]["since"] == pinned.isoformat()


def test_count_events_since_returns_zero_on_empty() -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    fake_client.get.return_value = MagicMock(status_code=200, json=MagicMock(return_value=[]))

    with patch("agents.lib.sentry._client", return_value=fake_client):
        n = sentry.count_events_since("o", "p", since=datetime.now(UTC))

    assert n == 0


def test_list_issues_returns_list() -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    fake_client.get.return_value = MagicMock(
        status_code=200,
        json=MagicMock(return_value=[
            {"id": "1234", "title": "ZeroDivisionError", "count": "5"},
            {"id": "5678", "title": "KeyError: 'x'", "count": "1"},
        ]),
    )

    pinned = datetime(2026, 4, 14, tzinfo=UTC)
    with patch("agents.lib.sentry._client", return_value=fake_client):
        issues = sentry.list_issues("org", "proj", since=pinned)

    assert len(issues) == 2
    assert issues[0]["id"] == "1234"
    fake_client.get.assert_called_once()
    call = fake_client.get.call_args
    assert call.args[0] == "/projects/org/proj/issues/"
    assert call.kwargs["params"]["since"] == pinned.isoformat()


def test_list_issues_default_since_is_24h_ago() -> None:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None
    fake_client.get.return_value = MagicMock(status_code=200, json=MagicMock(return_value=[]))

    with patch("agents.lib.sentry._client", return_value=fake_client):
        sentry.list_issues("o", "p")

    since_str = fake_client.get.call_args.kwargs["params"]["since"]
    since_dt = datetime.fromisoformat(since_str)
    delta = datetime.now(UTC) - since_dt
    assert timedelta(hours=23, minutes=59) <= delta <= timedelta(hours=24, minutes=1)
