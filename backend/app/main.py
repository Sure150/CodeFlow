from fastapi import FastAPI

app = FastAPI(title="CodeFlow")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
