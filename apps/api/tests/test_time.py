from datetime import datetime

from fastapi.testclient import TestClient

from api.main import app


def test_time_endpoint_returns_utc_isoformat() -> None:
    client = TestClient(app)
    response = client.get("/api/time")
    assert response.status_code == 200
    resp_json = response.json()
    assert "utc" in resp_json
    # Should be ISO8601 parseable
    parsed = datetime.fromisoformat(resp_json["utc"])
    assert parsed.tzinfo is not None  # Should be timezone-aware
