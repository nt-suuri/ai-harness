import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.lib import github_models


@pytest.mark.asyncio
async def test_raises_when_tools_requested() -> None:
    with pytest.raises(NotImplementedError, match="tools"):
        await github_models.run_agent("x", system="y", allowed_tools=["Read"])


@pytest.mark.asyncio
async def test_calls_gh_models_endpoint() -> None:
    fake_resp = MagicMock(status_code=200)
    fake_resp.json = MagicMock(return_value={
        "choices": [{"message": {"content": "Hi from GH Models"}}],
    })
    fake_resp.raise_for_status = MagicMock(return_value=None)

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=fake_resp)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_x"}, clear=True),
        patch("agents.lib.github_models.httpx.AsyncClient", return_value=fake_client),
    ):
        result = await github_models.run_agent("hello", system="be brief")

    fake_client.post.assert_called_once()
    call = fake_client.post.call_args
    assert call.args[0].endswith("/chat/completions")
    assert call.kwargs["headers"]["Authorization"] == "Bearer ghp_x"
    body = call.kwargs["json"]
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1]["content"] == "hello"
    assert result.stopped_reason == "complete"
    assert result.messages[0]["text"] == "Hi from GH Models"


@pytest.mark.asyncio
async def test_uses_github_models_token_when_set() -> None:
    fake_resp = MagicMock(status_code=200)
    fake_resp.json = MagicMock(return_value={"choices": [{"message": {"content": "ok"}}]})
    fake_resp.raise_for_status = MagicMock(return_value=None)

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=fake_resp)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "fallback", "GITHUB_MODELS_TOKEN": "specific"},
            clear=True,
        ),
        patch("agents.lib.github_models.httpx.AsyncClient", return_value=fake_client),
    ):
        await github_models.run_agent("x", system="y")

    headers = fake_client.post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer specific"
