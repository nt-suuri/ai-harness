from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

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
    expected = {"reviewer", "planner", "deployer", "triager", "healthcheck", "stale", "release_notes", "canary", "pr_describer", "issue_labeler"}
    assert expected.issubset(names)


def test_agent_detail_returns_known_agent() -> None:
    fake_repo = MagicMock()
    fake_workflow = MagicMock()
    fake_run = MagicMock(
        conclusion="success",
        created_at=datetime(2026, 4, 14, 10, tzinfo=UTC),
        head_sha="abcdef1234567890",
        html_url="https://github.com/x/runs/123",
    )
    fake_workflow.get_runs.return_value = [fake_run]
    fake_repo.get_workflow.return_value = fake_workflow

    with patch("api.agents._repo", return_value=fake_repo):
        client = TestClient(app)
        resp = client.get("/api/agents/reviewer")

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "reviewer"
    assert data["last_run"]["conclusion"] == "success"
    assert data["last_run"]["head_sha"] == "abcdef1"


def test_agent_detail_unknown_returns_404() -> None:
    client = TestClient(app)
    resp = client.get("/api/agents/nonexistent")
    assert resp.status_code == 404


def test_agent_detail_no_runs_returns_null_last_run() -> None:
    fake_repo = MagicMock()
    fake_workflow = MagicMock()
    fake_workflow.get_runs.return_value = []
    fake_repo.get_workflow.return_value = fake_workflow

    with patch("api.agents._repo", return_value=fake_repo):
        client = TestClient(app)
        resp = client.get("/api/agents/triager")
    data = resp.json()
    assert data["last_run"] is None


def test_agent_detail_no_token_returns_null_last_run() -> None:
    with patch("api.agents._repo", side_effect=KeyError("GITHUB_TOKEN")):
        client = TestClient(app)
        resp = client.get("/api/agents/canary")
    data = resp.json()
    assert data["last_run"] is None


def test_agent_runs_returns_list() -> None:
    fake_repo = MagicMock()
    fake_workflow = MagicMock()
    fake_run = MagicMock(
        conclusion="success",
        created_at=datetime(2026, 4, 14, 10, tzinfo=UTC),
        head_sha="abc1234567890",
        html_url="https://github.com/x/runs/1",
    )
    runs = [fake_run, fake_run, fake_run]
    fake_workflow.get_runs.return_value = runs
    fake_repo.get_workflow.return_value = fake_workflow

    with patch("api.agents._repo", return_value=fake_repo):
        client = TestClient(app)
        resp = client.get("/api/agents/reviewer/runs?limit=2")

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "reviewer"
    assert data["workflow_file"] == "reviewer.yml"
    assert len(data["runs"]) <= 2
    assert data["runs"][0]["head_sha"] == "abc1234"


def test_agent_runs_unknown_agent_returns_404() -> None:
    client = TestClient(app)
    resp = client.get("/api/agents/nonexistent/runs")
    assert resp.status_code == 404


def test_agent_runs_invalid_limit_returns_400() -> None:
    client = TestClient(app)
    resp = client.get("/api/agents/reviewer/runs?limit=999")
    assert resp.status_code == 400


def test_agent_runs_no_token_returns_503() -> None:
    with patch("api.agents._repo", side_effect=KeyError("GITHUB_TOKEN")):
        client = TestClient(app)
        resp = client.get("/api/agents/triager/runs")
    assert resp.status_code == 503
