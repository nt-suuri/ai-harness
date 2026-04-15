from fastapi.testclient import TestClient

from api.main import app


def test_echo_returns_message() -> None:
    client = TestClient(app)
    response = client.get("/api/echo?msg=hello")
    assert response.status_code == 200
    assert response.json() == {"message": "hello"}


def test_echo_requires_msg() -> None:
    client = TestClient(app)
    response = client.get("/api/echo")
    assert response.status_code == 422
