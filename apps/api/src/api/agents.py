"""GET /api/agents — introspect available agent CLIs."""

from fastapi import APIRouter

router = APIRouter()


_AGENTS = [
    {"name": "reviewer", "purpose": "3-pass PR reviewer", "trigger": "pull_request", "module": "agents.reviewer"},
    {"name": "planner", "purpose": "Implements feature from issue", "trigger": "issues.labeled (agent:build)", "module": "agents.planner"},
    {"name": "deployer", "purpose": "Post-deploy spike watcher", "trigger": "workflow_run (deploy)", "module": "agents.deployer"},
    {"name": "triager", "purpose": "Sentry → GH issue dedupe", "trigger": "schedule (0 9 * * *)", "module": "agents.triager"},
    {"name": "healthcheck", "purpose": "Daily HEALTH dashboard", "trigger": "schedule (0 8 * * *)", "module": "agents.healthcheck"},
    {"name": "stale", "purpose": "Close inactive autotriage issues", "trigger": "schedule (0 10 * * 0)", "module": "agents.stale"},
    {"name": "release_notes", "purpose": "Auto CHANGELOG + GH Release", "trigger": "workflow_run (deploy)", "module": "agents.release_notes"},
    {"name": "canary", "purpose": "Weekly fixture replay", "trigger": "schedule (0 7 * * 0)", "module": "agents.canary"},
]


@router.get("/api/agents")
def get_agents() -> dict[str, object]:
    return {"count": len(_AGENTS), "agents": _AGENTS}
