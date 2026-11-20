from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .analyzer import Analysis, analyze_python

app = FastAPI(title="CodeFlow")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])


class AnalyzeRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
def analyze(body: AnalyzeRequest, request: Request) -> Analysis:
    origin = request.headers.get("origin")
    if origin is not None and origin != f"{request.url.scheme}://{request.headers.get('host')}":
        raise HTTPException(status_code=403, detail="请通过 CodeFlow 的本地页面发起扫描")

    if not body.path.strip():
        raise HTTPException(status_code=400, detail="请输入项目目录")
    try:
        root = Path(body.path.strip()).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise HTTPException(status_code=400, detail="请选择一个目录")
    except (OSError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail="目录不存在或无法访问") from error
    return analyze_python(root)
