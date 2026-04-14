"""GET /api/agents and /api/agents/{name} — introspect available agent CLIs."""

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from github import Github
from github.Repository import Repository
from github.WorkflowRun import WorkflowRun

router = APIRouter()


_AGENTS = [
    {"name": "reviewer", "purpose": "3-pass PR reviewer", "trigger": "pull_request", "module": "agents.reviewer", "workflow_file": "reviewer.yml"},
    {"name": "planner", "purpose": "Implements feature from issue", "trigger": "issues.labeled (agent:build)", "module": "agents.planner", "workflow_file": "planner.yml"},
    {"name": "deployer", "purpose": "Post-deploy spike watcher", "trigger": "workflow_run (deploy)", "module": "agents.deployer", "workflow_file": "rollback-watch.yml"},
    {"name": "triager", "purpose": "Sentry → GH issue dedupe", "trigger": "schedule (0 9 * * *)", "module": "agents.triager", "workflow_file": "triager.yml"},
    {"name": "healthcheck", "purpose": "Daily HEALTH dashboard", "trigger": "schedule (0 8 * * *)", "module": "agents.healthcheck", "workflow_file": "healthcheck.yml"},
    {"name": "stale", "purpose": "Close inactive autotriage issues", "trigger": "schedule (0 10 * * 0)", "module": "agents.stale", "workflow_file": "stale.yml"},
    {"name": "release_notes", "purpose": "Auto CHANGELOG + GH Release", "trigger": "workflow_run (deploy)", "module": "agents.release_notes", "workflow_file": "release-notes.yml"},
    {"name": "canary", "purpose": "Weekly fixture replay", "trigger": "schedule (0 7 * * 0)", "module": "agents.canary", "workflow_file": "canary-replay.yml"},
]

_DEFAULT_REPO = "nt-suuri/ai-harness"


def _repo() -> Repository:
    token = os.environ["GITHUB_TOKEN"]
    name = os.environ.get("GH_REPO", _DEFAULT_REPO)
    return Github(token).get_repo(name)


def _last_run(repo: Repository, workflow_file: str) -> dict[str, Any] | None:
    runs: list[Any] = list(repo.get_workflow(workflow_file).get_runs()[:1])
    if not runs:
        return None
    r = runs[0]
    return {
        "conclusion": r.conclusion,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "head_sha": r.head_sha[:7] if r.head_sha else None,
        "html_url": r.html_url,
    }


@router.get("/api/agents")
def get_agents() -> dict[str, object]:
    return {"count": len(_AGENTS), "agents": _AGENTS}


@router.get("/api/agents/{name}")
def get_agent_detail(name: str) -> dict[str, Any]:
    agent = next((a for a in _AGENTS if a["name"] == name), None)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {name}")
    result: dict[str, Any] = dict(agent)
    last_run_value: dict[str, Any] | None
    try:
        repo = _repo()
        last_run_value = _last_run(repo, str(agent["workflow_file"]))
    except KeyError:
        last_run_value = None
    except Exception as e:
        last_run_value = {"error": str(e)}
    result["last_run"] = last_run_value
    return result


@router.get("/api/agents/{name}/runs")
def get_agent_runs(name: str, limit: int = 10) -> dict[str, Any]:
    agent = next((a for a in _AGENTS if a["name"] == name), None)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {name}")
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=400, detail="limit must be 1..50")

    try:
        repo = _repo()
    except KeyError as e:
        raise HTTPException(status_code=503, detail=f"Missing env var: {e.args[0]}") from None

    runs_raw: list[WorkflowRun] = list(repo.get_workflow(str(agent["workflow_file"])).get_runs()[:limit])
    runs = [
        {
            "conclusion": r.conclusion,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "head_sha": r.head_sha[:7] if r.head_sha else None,
            "html_url": r.html_url,
        }
        for r in runs_raw
    ]

    return {
        "name": name,
        "workflow_file": agent["workflow_file"],
        "runs": runs,
    }
