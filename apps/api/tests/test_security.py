import os
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.security import TTLCache, cors_origins, require_token
from api.status import _cache


def test_security_headers_on_response() -> None:
    client = TestClient(app)
    resp = client.get("/api/ping")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" in resp.headers


def test_require_token_noop_when_env_unset() -> None:
    with patch.dict(os.environ, {}, clear=True):
        require_token(None)
        require_token("anything")


def test_require_token_rejects_missing_when_required() -> None:
    with patch.dict(os.environ, {"STATUS_API_TOKEN": "secret"}, clear=True):
        with pytest.raises(HTTPException) as exc:
            require_token(None)
        assert exc.value.status_code == 401


def test_require_token_rejects_wrong_when_required() -> None:
    with patch.dict(os.environ, {"STATUS_API_TOKEN": "secret"}, clear=True):
        with pytest.raises(HTTPException) as exc:
            require_token("Bearer wrongtoken")
        assert exc.value.status_code == 403


def test_require_token_accepts_correct() -> None:
    with patch.dict(os.environ, {"STATUS_API_TOKEN": "secret"}, clear=True):
        require_token("Bearer secret")


def test_cors_origins_default_empty() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert cors_origins() == []


def test_cors_origins_parses_comma_list() -> None:
    with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://a.com, https://b.com"}, clear=True):
        assert cors_origins() == ["https://a.com", "https://b.com"]


def test_ttl_cache_get_set() -> None:
    cache = TTLCache(ttl_seconds=60)
    assert cache.get("k") is None
    cache.set("k", {"v": 1})
    assert cache.get("k") == {"v": 1}


def test_ttl_cache_expires() -> None:
    cache = TTLCache(ttl_seconds=0)
    cache.set("k", "v")
    time.sleep(0.01)
    assert cache.get("k") is None


def test_ping_with_invalid_token_still_works() -> None:
    with patch.dict(os.environ, {"STATUS_API_TOKEN": "secret"}, clear=True):
        client = TestClient(app)
        resp = client.get("/api/ping")
    assert resp.status_code == 200
    assert resp.json() == {"status": "pong"}


def test_status_requires_token_when_set() -> None:
    _cache._store.clear()
    with patch.dict(os.environ, {"STATUS_API_TOKEN": "secret"}, clear=True):
        client = TestClient(app)
        resp = client.get("/api/status")
    assert resp.status_code == 401


def _basic(user: str, pw: str) -> str:
    import base64
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


def test_basic_auth_disabled_by_default() -> None:
    with patch.dict(os.environ, {}, clear=True):
        client = TestClient(app)
        resp = client.get("/api/ping")
    assert resp.status_code == 200


def test_basic_auth_blocks_root_when_enabled() -> None:
    with patch.dict(os.environ, {"DASHBOARD_USER": "admin", "DASHBOARD_PASSWORD": "pw"}, clear=True):
        client = TestClient(app)
        resp = client.get("/")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"].startswith("Basic")


def test_basic_auth_accepts_valid_credentials() -> None:
    with patch.dict(os.environ, {"DASHBOARD_USER": "admin", "DASHBOARD_PASSWORD": "pw"}, clear=True):
        client = TestClient(app)
        resp = client.get("/api/ping", headers={"Authorization": _basic("admin", "pw")})
    assert resp.status_code == 200


def test_basic_auth_rejects_wrong_password() -> None:
    with patch.dict(os.environ, {"DASHBOARD_USER": "admin", "DASHBOARD_PASSWORD": "pw"}, clear=True):
        client = TestClient(app)
        resp = client.get("/", headers={"Authorization": _basic("admin", "nope")})
    assert resp.status_code == 401


def test_basic_auth_exempts_ping_for_healthchecks() -> None:
    with patch.dict(os.environ, {"DASHBOARD_USER": "admin", "DASHBOARD_PASSWORD": "pw"}, clear=True):
        client = TestClient(app)
        resp = client.get("/api/ping")
    assert resp.status_code == 200


def test_status_accepts_correct_token() -> None:
    _cache._store.clear()
    fake_repo = MagicMock()
    fake_workflow = MagicMock()
    fake_workflow.get_runs.return_value = []
    fake_repo.get_workflow.return_value = fake_workflow
    fake_repo.get_issues.return_value = []

    with (
        patch.dict(os.environ, {"STATUS_API_TOKEN": "secret"}, clear=True),
        patch("api.status._repo", return_value=fake_repo),
    ):
        client = TestClient(app)
        resp = client.get("/api/status", headers={"Authorization": "Bearer secret"})
    assert resp.status_code == 200
