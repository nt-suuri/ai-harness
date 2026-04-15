from datetime import UTC, datetime

from fastapi import APIRouter

router = APIRouter()

@router.get("/api/time")
def get_time() -> dict:
    utc_now = datetime.now(UTC).isoformat()
    return {"utc": utc_now}
