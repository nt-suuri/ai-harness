from fastapi import APIRouter

router = APIRouter()

@router.get("/api/whoami")
def get_whoami() -> dict[str, str]:
    return {"agent": "ai-harness-bot"}