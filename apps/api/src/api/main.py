# smoke test for reviewer via GH Models
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.agents import router as agents_router
from api.security import SecurityHeadersMiddleware, cors_origins, limiter
from api.sentry import init_sentry
from api.status import router as status_router
from api.version import router as version_router

init_sentry()

app = FastAPI(title="ai-harness api")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SecurityHeadersMiddleware)

origins = cors_origins()
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Authorization", "Content-Type"],
    )

app.include_router(status_router)
app.include_router(version_router)
app.include_router(agents_router)


@app.get("/api/ping")
@limiter.limit("120/minute")
def ping(request: Request) -> dict[str, str]:
    return {"status": "pong"}


_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="web")
