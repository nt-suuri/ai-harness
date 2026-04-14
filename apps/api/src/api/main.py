from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.sentry import init_sentry

init_sentry()

app = FastAPI(title="ai-harness api")


@app.get("/api/ping")
def ping() -> dict[str, str]:
    return {"status": "pong"}


_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="web")
