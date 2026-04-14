import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from github import Github
from github.Repository import Repository

from api.security import TTLCache, limiter, require_token

router = APIRouter()

_DEFAULT_REPO = "nt-suuri/ai-harness"
_cache = TTLCache(ttl_seconds=60)


def _repo() -> Repository:
    token = os.environ["GITHUB_TOKEN"]
    name = os.environ.get("GH_REPO", _DEFAULT_REPO)
    return Github(token).get_repo(name)


def _count_runs(repo: Repository, workflow_file: str) -> dict[str, int]:
    success = 0
    failure = 0
    for r in list(repo.get_workflow(workflow_file).get_runs())[:20]:
        if r.conclusion == "success":
            success += 1
        elif r.conclusion == "failure":
            failure += 1
    return {"success": success, "failure": failure}


@router.get("/api/status")
@limiter.limit("30/minute")
def get_status(request: Request, _: None = Depends(require_token)) -> dict[str, Any]:
    cached = _cache.get("status")
    if cached is not None:
        return cached  # type: ignore[return-value]
    try:
        repo = _repo()
    except KeyError as e:
        raise HTTPException(status_code=503, detail=f"Missing env var: {e.args[0]}") from None

    ci = _count_runs(repo, "ci.yml")
    deploy = _count_runs(repo, "deploy.yml")
    # keep "autotriage" inline — avoid apps/api depending on agents/
    autotriage_issues = list(repo.get_issues(state="open", labels=["autotriage"]))

    result = {
        "ci": ci,
        "deploy": deploy,
        "open_autotriage_issues": len(autotriage_issues),
    }
    _cache.set("status", result)
    return result
