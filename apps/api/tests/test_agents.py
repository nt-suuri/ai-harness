from fastapi.testclient import TestClient

from api.main import app


def test_agents_returns_list() -> None:
    client = TestClient(app)
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert "count" in data
    assert "agents" in data
    assert data["count"] == len(data["agents"])
    assert data["count"] >= 8


def test_agents_each_has_required_fields() -> None:
    client = TestClient(app)
    data = client.get("/api/agents").json()
    required = {"name", "purpose", "trigger", "module"}
    for agent in data["agents"]:
        assert required.issubset(agent.keys()), f"missing keys in {agent}"


def test_agents_includes_known_names() -> None:
    client = TestClient(app)
    data = client.get("/api/agents").json()
    names = {a["name"] for a in data["agents"]}
    expected = {"reviewer", "planner", "deployer", "triager", "healthcheck", "stale", "release_notes", "canary"}
    assert expected.issubset(names)
