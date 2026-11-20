from pathlib import Path
from subprocess import SubprocessError, TimeoutExpired
from threading import Lock

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .analyzer import Analysis, analyze_python
from .folder_picker import choose_folder

app = FastAPI(title="CodeFlow")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])
folder_picker_lock = Lock()


class AnalyzeRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/choose-directory")
def choose_directory(request: Request) -> dict[str, str | None]:
    if request.headers.get("origin") != f"{request.url.scheme}://{request.headers.get('host')}":
        raise HTTPException(status_code=403, detail="请从 CodeFlow 的本地页面打开文件夹选择窗口")
    if not folder_picker_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="文件夹选择窗口已打开")
    try:
        return {"path": choose_folder()}
    except TimeoutExpired as error:
        raise HTTPException(status_code=408, detail="文件夹选择超时，请重试") from error
    except (OSError, SubprocessError, ValueError) as error:
        raise HTTPException(status_code=503, detail="无法打开系统文件夹选择窗口，请手动输入项目路径") from error
    finally:
        folder_picker_lock.release()


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
