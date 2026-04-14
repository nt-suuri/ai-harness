import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


def test_version_returns_shape() -> None:
    client = TestClient(app)
    resp = client.get("/api/version")
    assert resp.status_code == 200
    data = resp.json()
    assert "sha" in data
    assert "env" in data
    assert "python" in data
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], int)
    assert data["uptime_seconds"] >= 0


def test_version_sha_dev_when_unset() -> None:
    with patch.dict(os.environ, {}, clear=True):
        client = TestClient(app)
        resp = client.get("/api/version")
    data = resp.json()
    assert data["sha"] == "dev"
    assert data["env"] == "local"


def test_version_sha_truncated_to_7_chars() -> None:
    full = "abc123456789def0"
    with patch.dict(os.environ, {"RAILWAY_GIT_COMMIT_SHA": full, "ENV": "production"}):
        client = TestClient(app)
        resp = client.get("/api/version")
    data = resp.json()
    assert data["sha"] == "abc1234"
    assert data["env"] == "production"


def test_version_python_format() -> None:
    client = TestClient(app)
    data = client.get("/api/version").json()
    parts = data["python"].split(".")
    assert len(parts) >= 2
    assert int(parts[0]) >= 3
