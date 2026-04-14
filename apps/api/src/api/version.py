import os
import platform
import time

from fastapi import APIRouter, Request

from api.security import limiter

router = APIRouter()

_STARTED_AT = time.monotonic()


@router.get("/api/version")
@limiter.limit("60/minute")
def get_version(request: Request) -> dict[str, str | int]:
    sha = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "dev")
    return {
        "sha": sha[:7] if sha != "dev" else "dev",
        "env": os.environ.get("ENV", "local"),
        "python": platform.python_version(),
        "uptime_seconds": int(time.monotonic() - _STARTED_AT),
    }
