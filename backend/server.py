import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.schema import (
    AiConfig,
    ClassifyRequest,
    ExecuteRequest,
    HealthResponse,
    ScanConfig,
)
from pydantic import BaseModel as _BaseModel


class TreeClassifyRequest(_BaseModel):
    """Extends ClassifyRequest with an optional caller-supplied request_id for progress tracking."""
    files: list
    ai_config: AiConfig
    request_id: str = ""
from rollback import rollback as rollback_module
from scanner.scan import scan_directory
from scanner.watcher import get_watcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_dir = Path.home() / ".fileorganizer" / "logs"
    rollback_module.set_log_dir(log_dir)
    yield
    # Graceful shutdown: stop watcher
    watcher = get_watcher()
    if watcher.watching:
        watcher.stop()


app = FastAPI(title="FileOrganizer Backend", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


# ─── Scan ─────────────────────────────────────────────────────────────────────

@app.post("/api/scan")
async def scan(config: ScanConfig) -> dict:
    files = scan_directory(config)
    return {"total": len(files), "files": [f.model_dump() for f in files]}


# ─── Classify ─────────────────────────────────────────────────────────────────

@app.post("/api/classify")
async def classify(request: ClassifyRequest) -> dict:
    from classifier.ai_classifier import classify_files
    results = await classify_files(request.files, request.ai_config)
    return {"classifications": results}


@app.post("/api/classify/tree")
async def classify_tree(request: TreeClassifyRequest) -> dict:
    """
    Holistic classification: analyses all files together and produces a
    dynamic two-level folder hierarchy with AI-generated folder names.

    Accepts an optional `request_id` field; pair with GET
    /api/classify/tree/progress/{request_id} for real-time progress.

    Response shape:
      {
        "tree": { "L1": { "L2": [path, ...] } },
        "assignments": { path: { "level1": "L1", "level2": "L2" } }
      }
    """
    from classifier.tree_classifier import classify_tree as _classify_tree, clear_progress, is_cancelled
    from config.schema import ScanResult
    files = [ScanResult(**f) if isinstance(f, dict) else f for f in request.files]
    try:
        result = await _classify_tree(files, request.ai_config, request.request_id)
    except Exception as e:
        clear_progress(request.request_id)
        if is_cancelled(request.request_id):
            return {"cancelled": True, "tree": {}, "assignments": {}}
        raise
    clear_progress(request.request_id)
    return result


@app.get("/api/classify/tree/progress/{request_id}")
async def classify_tree_progress(request_id: str) -> dict:
    """Poll real-time progress for an in-flight /api/classify/tree request."""
    from classifier.tree_classifier import get_progress
    return get_progress(request_id)


@app.post("/api/classify/tree/cancel/{request_id}")
async def classify_tree_cancel(request_id: str) -> dict:
    """Cancel an in-flight classification by request_id."""
    from classifier.tree_classifier import cancel_classification, clear_progress
    cancel_classification(request_id)
    clear_progress(request_id)
    logger.info("Classification cancelled: %s", request_id)
    return {"cancelled": True}


# ─── Execute ──────────────────────────────────────────────────────────────────

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
    operation_id = rollback_module.write_operation_log(actions, mode="scan", ai_model=ai_model)

    # Auto-cleanup empty folders in scan paths after archiving
    auto_cleanup = {"removed": [], "errors": []}
    if executed > 0 and hasattr(request, "scan_paths") and request.scan_paths:
        auto_cleanup = _cleanup_dirs(request.scan_paths)
        logger.info("Auto-cleanup after execute: removed %d empty dirs", len(auto_cleanup["removed"]))

    return {
        "executed": executed, "total": len(actions), "actions": actions,
        "operation_id": operation_id, "auto_cleanup": auto_cleanup,
    }


# ─── Cleanup empty directories ────────────────────────────────────────────────

def _cleanup_dirs(paths: list[str]) -> dict:
    """
    Shared helper: recursively delete empty directories inside the given paths.
    Directories containing only system junk files (.DS_Store, Thumbs.db, desktop.ini)
    are treated as empty — the junk files are deleted first, then the directory.
    Returns {"removed": [...], "errors": [...]}.
    """
    import os
    removed: list[str] = []
    errors: list[str] = []
    _JUNK = {".DS_Store", "Thumbs.db", "desktop.ini"}

    for root_str in paths:
        root = Path(root_str)
        if not root.is_dir():
            continue
        for dirpath_str, dirnames, filenames in os.walk(root_str, topdown=False):
            dirpath = Path(dirpath_str)
            if dirpath == root:
                continue
            try:
                entries = list(dirpath.iterdir())
                real_entries = [e for e in entries if e.name not in _JUNK]
                if not real_entries:
                    # Remove junk files first, then the directory
                    for e in entries:
                        e.unlink()
                    dirpath.rmdir()
                    removed.append(str(dirpath))
                    logger.info("Removed empty dir: %s", dirpath)
            except Exception as e:
                errors.append(f"{dirpath}: {e}")

    return {"removed": removed, "errors": errors}


@app.post("/api/cleanup-empty-dirs")
async def cleanup_empty_dirs(body: dict) -> dict:
    """
    Recursively delete empty directories inside the given scan paths.
    Request body: {"scan_paths": ["/path/to/dir1", ...]}
    """
    return _cleanup_dirs(body.get("scan_paths", []))


# ─── AI connection test ───────────────────────────────────────────────────────

@app.post("/api/test-connection")
async def test_connection(ai_config: AiConfig) -> dict:
    from classifier.ai_classifier import test_connection as _test
    return await _test(ai_config)


# ─── History & Rollback ───────────────────────────────────────────────────────

@app.get("/api/history")
async def history() -> dict:
    return {"operations": rollback_module.list_operations()}


@app.post("/api/rollback")
async def rollback(body: dict) -> dict:
    operation_id = body.get("operation_id", "")
    result = rollback_module.rollback_operation(operation_id)

    # Log the rollback with full action details
    if result.get("rolled_back", 0) > 0:
        rollback_module.write_operation_log(
            result.get("rollback_actions", []),
            mode="rollback", ai_model="", dry_run=False,
        )
        # Auto-cleanup empty folders in archive directories
        cleanup_dirs = result.get("cleanup_dirs", [])
        if cleanup_dirs:
            # Find unique root directories (go up to find the archive root)
            root_dirs = set()
            for d in cleanup_dirs:
                p = Path(d)
                # Walk up to find the shallowest existing parent
                while p.parent != p and p.parent.exists():
                    p = p.parent
                    if p.exists():
                        root_dirs.add(str(p))
                        break
            if root_dirs:
                cleanup_result = _cleanup_dirs(list(root_dirs))
                result["auto_cleanup"] = cleanup_result
                logger.info("Auto-cleanup after rollback: removed %d empty dirs",
                            len(cleanup_result["removed"]))

    # Remove internal fields from response
    result.pop("rollback_actions", None)
    result.pop("cleanup_dirs", None)
    return result


# ─── Watch ────────────────────────────────────────────────────────────────────

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
    watcher = get_watcher()
    watcher.stop()
    return {"status": "stopped"}


@app.get("/api/watch/status")
async def watch_status() -> dict:
    watcher = get_watcher()
    return {
        "watching": watcher.watching,
        "paths": watcher.paths,
        "recent": watcher.recent,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=18923)
