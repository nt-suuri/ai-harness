import os
from unittest.mock import MagicMock, patch

import pytest

from agents.lib import gh


def test_client_requires_github_token() -> None:
    gh._client.cache_clear()
    with patch.dict(os.environ, {}, clear=True), pytest.raises(KeyError):
        gh._client()


def test_client_caches_instance() -> None:
    gh._client.cache_clear()
    with patch.dict(os.environ, {"GITHUB_TOKEN": "t1"}, clear=True), patch("agents.lib.gh.Github") as gh_cls:
        gh_cls.return_value = MagicMock(name="gh_instance")
        a = gh._client()
        b = gh._client()
        assert a is b
        gh_cls.assert_called_once_with("t1")


def test_repo_uses_env_default() -> None:
    gh._client.cache_clear()
    with patch.dict(
        os.environ,
        {"GITHUB_TOKEN": "t", "GH_REPO": "acme/proj"},
        clear=True,
    ), patch("agents.lib.gh.Github") as gh_cls:
        client = MagicMock()
        gh_cls.return_value = client
        gh.repo()
        client.get_repo.assert_called_once_with("acme/proj")


def test_repo_explicit_fullname_overrides_env() -> None:
    gh._client.cache_clear()
    with patch.dict(
        os.environ,
        {"GITHUB_TOKEN": "t", "GH_REPO": "acme/proj"},
        clear=True,
    ), patch("agents.lib.gh.Github") as gh_cls:
        client = MagicMock()
        gh_cls.return_value = client
        gh.repo("other/thing")
        client.get_repo.assert_called_once_with("other/thing")


def test_repo_default_falls_back_to_nt_suuri_ai_harness() -> None:
    gh._client.cache_clear()
    with patch.dict(os.environ, {"GITHUB_TOKEN": "t"}, clear=True), patch("agents.lib.gh.Github") as gh_cls:
        client = MagicMock()
        gh_cls.return_value = client
        gh.repo()
        client.get_repo.assert_called_once_with("nt-suuri/ai-harness")
