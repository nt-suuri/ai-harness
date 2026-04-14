import os
from unittest.mock import MagicMock, patch

import pytest

from agents.lib import email


def test_send_email_requires_api_key() -> None:
    with patch.dict(os.environ, {}, clear=True), pytest.raises(KeyError):
        email.send_email(to="a@b.com", subject="s", body="b")


def test_send_email_sends_via_resend() -> None:
    fake_resp = MagicMock(status_code=200, json=MagicMock(return_value={"id": "abc"}))
    with (
        patch.dict(os.environ, {"RESEND_API_KEY": "rk_test"}, clear=True),
        patch("agents.lib.email.httpx.post", return_value=fake_resp) as post,
    ):
        result = email.send_email(
            to="dev@example.com",
            subject="Daily report",
            body="Everything OK",
            from_addr="ai-harness@example.com",
        )

    assert result == "abc"
    post.assert_called_once()
    call = post.call_args
    assert call.args[0] == "https://api.resend.com/emails"
    assert call.kwargs["headers"]["Authorization"] == "Bearer rk_test"
    payload = call.kwargs["json"]
    assert payload["to"] == ["dev@example.com"]
    assert payload["subject"] == "Daily report"
    assert payload["from"] == "ai-harness@example.com"


def test_send_email_default_from_addr() -> None:
    fake_resp = MagicMock(status_code=200, json=MagicMock(return_value={"id": "x"}))
    with (
        patch.dict(os.environ, {"RESEND_API_KEY": "k"}, clear=True),
        patch("agents.lib.email.httpx.post", return_value=fake_resp) as post,
    ):
        email.send_email(to="x@y.z", subject="s", body="b")
    payload = post.call_args.kwargs["json"]
    assert payload["from"] == "ai-harness@onresend.dev"


def test_send_email_raises_on_non_2xx() -> None:
    fake_resp = MagicMock()
    fake_resp.raise_for_status.side_effect = Exception("422 invalid email")
    with (
        patch.dict(os.environ, {"RESEND_API_KEY": "k"}, clear=True),
        patch("agents.lib.email.httpx.post", return_value=fake_resp),
        pytest.raises(Exception, match="422"),
    ):
        email.send_email(to="bad", subject="s", body="b")
