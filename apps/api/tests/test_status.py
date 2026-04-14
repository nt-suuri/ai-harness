from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.status import _cache


@pytest.fixture(autouse=True)
def clear_status_cache():
    _cache._store.clear()
    yield
    _cache._store.clear()


def test_status_returns_shape() -> None:
    fake_repo = MagicMock()
    fake_repo.get_workflow.return_value.get_runs.return_value = []
    fake_repo.get_issues.return_value = []

    with patch("api.status._repo", return_value=fake_repo):
        client = TestClient(app)
        resp = client.get("/api/status")

    assert resp.status_code == 200
    data = resp.json()
    assert "ci" in data
    assert "deploy" in data
    assert "open_autotriage_issues" in data
    assert isinstance(data["open_autotriage_issues"], int)


def test_status_counts_recent_runs() -> None:
    ci_runs = [
        MagicMock(conclusion="success"),
        MagicMock(conclusion="success"),
        MagicMock(conclusion="failure"),
    ]
    deploy_runs = [MagicMock(conclusion="success")]

    fake_repo = MagicMock()

    def get_workflow(workflow_file_name: str) -> MagicMock:
        wf = MagicMock()
        if workflow_file_name == "ci.yml":
            wf.get_runs.return_value = ci_runs
        elif workflow_file_name == "deploy.yml":
            wf.get_runs.return_value = deploy_runs
        else:
            wf.get_runs.return_value = []
        return wf

    fake_repo.get_workflow.side_effect = get_workflow
    fake_repo.get_issues.return_value = [MagicMock(), MagicMock()]

    with patch("api.status._repo", return_value=fake_repo):
        client = TestClient(app)
        resp = client.get("/api/status")

    data = resp.json()
    assert data["ci"]["success"] == 2
    assert data["ci"]["failure"] == 1
    assert data["deploy"]["success"] == 1
    assert data["deploy"]["failure"] == 0
    assert data["open_autotriage_issues"] == 2


def test_status_returns_503_when_no_token() -> None:
    with patch("api.status._repo", side_effect=KeyError("GITHUB_TOKEN")):
        client = TestClient(app)
        resp = client.get("/api/status")
    assert resp.status_code == 503
    assert "GITHUB_TOKEN" in resp.json()["detail"]
