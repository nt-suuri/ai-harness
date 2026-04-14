"""GET /api/version — deployed build info."""

import os
import platform
import time

from fastapi import APIRouter

router = APIRouter()

_STARTED_AT = time.monotonic()


@router.get("/api/version")
def get_version() -> dict[str, str | int]:
    sha = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "dev")
    return {
        "sha": sha[:7] if sha != "dev" else "dev",
        "env": os.environ.get("ENV", "local"),
        "python": platform.python_version(),
        "uptime_seconds": int(time.monotonic() - _STARTED_AT),
    }
