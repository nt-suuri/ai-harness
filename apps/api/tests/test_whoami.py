from fastapi.testclient import TestClient

from api.main import app


def test_whoami_returns_expected_response() -> None:
    client = TestClient(app)
    response = client.get("/api/whoami")
    assert response.status_code == 200
    assert response.json() == {"agent": "ai-harness-bot"}