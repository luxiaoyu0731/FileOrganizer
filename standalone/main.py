"""
FileOrganizer Standalone — 傻瓜版单文件运行模式

无需 Python / Node.js / Electron 环境。
用户拿到可执行文件后双击即可，应用自动打开默认浏览器。

打包命令：
    bash standalone/build.sh        # macOS / Linux
    standalone\\build.bat            # Windows
"""

import logging
import sys
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

# ─── 路径设置 ────────────────────────────────────────────────────────────────
# PyInstaller 解包后路径为 sys._MEIPASS；开发模式下使用 ../backend
_HERE = Path(__file__).parent

if hasattr(sys, "_MEIPASS"):
    # 打包模式：后端模块在 _MEIPASS/backend/
    sys.path.insert(0, str(Path(sys._MEIPASS) / "backend"))
    _WEB_DIR = Path(sys._MEIPASS) / "web"
else:
    # 开发模式：引用上级目录的 backend/
    sys.path.insert(0, str(_HERE.parent / "backend"))
    _WEB_DIR = _HERE / "web"   # standalone/web/（由 build.sh 生成）

# ─── 后端依赖 ─────────────────────────────────────────────────────────────────
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config.schema import (
    AiConfig,
    ClassifyRequest,
    ExecuteRequest,
    HealthResponse,
    ScanConfig,
)
from rollback import rollback as rollback_module
from scanner.scan import scan_directory
from scanner.watcher import get_watcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PORT = 18924  # 与 Electron 版（18923）隔离，双版本可同时运行


# ─── 生命周期 ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log_dir = Path.home() / ".fileorganizer" / "logs"
    rollback_module.set_log_dir(log_dir)
    logger.info("FileOrganizer Standalone starting on http://127.0.0.1:%d", PORT)
    # 延迟 1.5 秒后打开浏览器，等待 uvicorn 就绪
    threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    yield
    watcher = get_watcher()
    if watcher.watching:
        watcher.stop()
    logger.info("FileOrganizer Standalone stopped.")


# ─── FastAPI 应用 ──────────────────────────────────────────────────────────────

app = FastAPI(title="FileOrganizer Standalone", version="0.1.0", lifespan=lifespan)


# ─── API 路由（与 backend/server.py 完全相同）─────────────────────────────────

@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


@app.post("/api/scan")
async def scan(config: ScanConfig) -> dict:
    files = scan_directory(config)
    return {"total": len(files), "files": [f.model_dump() for f in files]}


@app.post("/api/classify")
async def classify(request: ClassifyRequest) -> dict:
    from classifier.ai_classifier import classify_files
    results = await classify_files(request.files, request.ai_config)
    return {"classifications": results}


@app.post("/api/execute")
async def execute(request: ExecuteRequest) -> dict:
    from archiver.archiver import safe_move
    from renamer.renamer import build_destination

    actions = []
    for cls in request.classifications:
        src = Path(cls.path)
        if not src.exists():
            actions.append({
                "action_type": "move", "source": cls.path, "destination": "",
                "file_hash": "", "status": "skipped", "error": "源文件不存在",
            })
            continue
        dest = build_destination(cls.model_dump(), request.archive_root, request.rename_strategy)
        action = safe_move(src, dest)
        action["classification"] = {"category": cls.category, "confidence": cls.confidence}
        action["classification_method"] = cls.classification_method
        actions.append(action)

    executed = sum(1 for a in actions if a["status"] == "success")
    ai_model = request.ai_config.model if request.ai_config else ""
    rollback_module.write_operation_log(actions, mode="scan", ai_model=ai_model)
    return {"executed": executed, "total": len(actions), "actions": actions}


@app.post("/api/test-connection")
async def test_connection(ai_config: AiConfig) -> dict:
    from classifier.ai_classifier import test_connection as _test
    return await _test(ai_config)


@app.get("/api/history")
async def history() -> dict:
    return {"operations": rollback_module.list_operations()}


@app.post("/api/rollback")
async def rollback(body: dict) -> dict:
    operation_id = body.get("operation_id", "")
    result = rollback_module.rollback_operation(operation_id)
    if result.get("rolled_back", 0) > 0:
        rollback_module.write_operation_log([], mode="rollback", ai_model="")
    return result


class WatchStartRequest(BaseModel):
    paths: list[str]
    ai_config: AiConfig
    archive_root: str
    rename_strategy: str = "semantic_date"
    auto_execute: bool = False


@app.post("/api/watch/start")
async def watch_start(request: WatchStartRequest) -> dict:
    watcher = get_watcher()
    if watcher.watching:
        watcher.stop()
    watcher.start(
        paths=request.paths,
        ai_config=request.ai_config,
        archive_root=request.archive_root,
        rename_strategy=request.rename_strategy,
        auto_execute=request.auto_execute,
    )
    return {"status": "watching", "paths": request.paths}


@app.post("/api/watch/stop")
async def watch_stop() -> dict:
    get_watcher().stop()
    return {"status": "stopped"}


@app.get("/api/watch/status")
async def watch_status() -> dict:
    w = get_watcher()
    return {"watching": w.watching, "paths": w.paths, "recent": w.recent}


# ─── 静态文件（React 构建产物）────────────────────────────────────────────────
# 必须在所有 /api 路由之后挂载，避免被静态路由拦截

if _WEB_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(_WEB_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """所有非 API 路径返回 index.html（SPA 路由支持）"""
        return FileResponse(str(_WEB_DIR / "index.html"))
else:
    @app.get("/")
    async def no_web():
        return {"error": "前端未构建，请先运行 build.sh / build.bat"}


# ─── 入口 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
