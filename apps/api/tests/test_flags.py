import json

import pytest
from fastapi.testclient import TestClient

from api.flags import _load_flags, is_enabled
from api.main import app


@pytest.fixture
def flags_file(tmp_path, monkeypatch):
    f = tmp_path / "feature-flags.json"
    monkeypatch.setattr("api.flags._FLAGS_FILE", f)
    return f


def test_load_flags_missing_file_returns_empty(flags_file) -> None:
    assert _load_flags() == {}


def test_load_flags_malformed_returns_empty(flags_file) -> None:
    flags_file.write_text("not json")
    assert _load_flags() == {}


def test_load_flags_parses_valid(flags_file) -> None:
    flags_file.write_text(json.dumps({"dark_mode": True, "beta": False}))
    assert _load_flags() == {"dark_mode": True, "beta": False}


def test_is_enabled_bool(flags_file) -> None:
    flags_file.write_text(json.dumps({"a": True, "b": False}))
    assert is_enabled("a") is True
    assert is_enabled("b") is False


def test_is_enabled_missing(flags_file) -> None:
    flags_file.write_text(json.dumps({}))
    assert is_enabled("missing") is False


def test_is_enabled_string_variants(flags_file) -> None:
    flags_file.write_text(json.dumps({
        "t": "true", "y": "yes", "one": "1", "on": "on",
        "f": "false", "n": "no", "zero": "0",
    }))
    assert is_enabled("t") is True
    assert is_enabled("y") is True
    assert is_enabled("one") is True
    assert is_enabled("on") is True
    assert is_enabled("f") is False
    assert is_enabled("n") is False
    assert is_enabled("zero") is False


def test_api_flags_returns_data(flags_file) -> None:
    flags_file.write_text(json.dumps({"dark_mode": True}))
    client = TestClient(app)
    resp = client.get("/api/flags")
    assert resp.status_code == 200
    assert resp.json() == {"dark_mode": True}


def test_api_flag_by_name_found(flags_file) -> None:
    flags_file.write_text(json.dumps({"dark_mode": "yes"}))
    client = TestClient(app)
    resp = client.get("/api/flags/dark_mode")
    assert resp.status_code == 200
    assert resp.json() == {"name": "dark_mode", "enabled": True}


def test_api_flag_by_name_404(flags_file) -> None:
    flags_file.write_text(json.dumps({}))
    client = TestClient(app)
    resp = client.get("/api/flags/missing")
    assert resp.status_code == 404
