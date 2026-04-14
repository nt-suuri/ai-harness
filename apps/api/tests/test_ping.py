from fastapi.testclient import TestClient

from api.main import app


def test_ping_returns_pong() -> None:
    client = TestClient(app)
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "pong"}
