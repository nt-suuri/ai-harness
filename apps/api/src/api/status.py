import os
from typing import Any

from fastapi import APIRouter, HTTPException
from github import Github
from github.Repository import Repository

router = APIRouter()

_DEFAULT_REPO = "nt-suuri/ai-harness"


def _repo() -> Repository:
    token = os.environ["GITHUB_TOKEN"]
    name = os.environ.get("GH_REPO", _DEFAULT_REPO)
    return Github(token).get_repo(name)


def _count_runs(repo: Repository, workflow_file: str) -> dict[str, int]:
    success = 0
    failure = 0
    runs = repo.get_workflow(workflow_file).get_runs()
    for run in list(runs)[:20]:
        if run.conclusion == "success":
            success += 1
        elif run.conclusion == "failure":
            failure += 1
    return {"success": success, "failure": failure}


@router.get("/api/status")
def get_status() -> dict[str, Any]:
    try:
        repo = _repo()
    except KeyError as e:
        raise HTTPException(status_code=503, detail=f"Missing env var: {e.args[0]}") from None

    ci = _count_runs(repo, "ci.yml")
    deploy = _count_runs(repo, "deploy.yml")
    autotriage_issues = list(repo.get_issues(state="open", labels=["autotriage"]))

    return {
        "ci": ci,
        "deploy": deploy,
        "open_autotriage_issues": len(autotriage_issues),
    }
