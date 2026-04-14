from fastapi import FastAPI

app = FastAPI(title="ai-harness api")


@app.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "pong"}
