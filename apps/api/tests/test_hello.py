import pytest
from fastapi.testclient import TestClient
from apps.api.src.api import app

def test_hello_default():
    client = TestClient(app)
    response = client.get("/api/hello")
    assert response.status_code == 200
    assert response.json() == {"greeting": "Hello, world!"}


def test_hello_name():
    client = TestClient(app)
    response = client.get("/api/hello?name=claude")
    assert response.status_code == 200
    assert response.json() == {"greeting": "Hello, claude!"}
