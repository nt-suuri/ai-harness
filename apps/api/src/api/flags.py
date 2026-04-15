import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from api.security import limiter

router = APIRouter()

_FLAGS_FILE = Path(__file__).resolve().parents[4] / "feature-flags.json"


def _load_flags() -> dict[str, Any]:
    if not _FLAGS_FILE.is_file():
        return {}
    try:
        data = json.loads(_FLAGS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def is_enabled(name: str) -> bool:
    value = _load_flags().get(name, False)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return False


@router.get("/api/flags")
@limiter.limit("60/minute")
def get_flags(request: Request) -> dict[str, Any]:
    return _load_flags()


@router.get("/api/flags/{name}")
@limiter.limit("60/minute")
def get_flag(request: Request, name: str) -> dict[str, bool | str]:
    flags = _load_flags()
    if name not in flags:
        raise HTTPException(status_code=404, detail=f"Unknown flag: {name}")
    return {"name": name, "enabled": is_enabled(name)}
