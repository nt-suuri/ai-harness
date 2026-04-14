from fastapi import FastAPI

from api.sentry import init_sentry

init_sentry()

app = FastAPI(title="ai-harness api")


@app.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "pong"}
