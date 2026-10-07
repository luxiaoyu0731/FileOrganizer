import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from archiver.archiver import _resolve_conflict, _sha256, safe_move

logger = logging.getLogger(__name__)

_LOG_DIR: Path | None = None


def set_log_dir(log_dir: Path) -> None:
    global _LOG_DIR
    _LOG_DIR = log_dir
    log_dir.mkdir(parents=True, exist_ok=True)


def _get_log_dir() -> Path:
    if _LOG_DIR:
        return _LOG_DIR
    fallback = Path.home() / ".fileorganizer" / "logs"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def write_operation_log(
    actions: list[dict],
    mode: str = "scan",
    dry_run: bool = False,
    ai_model: str = "",
) -> str:
    operation_id = str(uuid.uuid4())
    log = {
        "operation_id": operation_id,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "mode": mode,
        "dry_run": dry_run,
        "ai_model_used": ai_model,
        "actions": actions,
    }
    log_path = _get_log_dir() / f"{operation_id}.json"
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2))
    logger.info("Operation log written: %s", log_path)
    return operation_id


def list_operations() -> list[dict]:
    logs = []
    for f in sorted(_get_log_dir().glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
            logs.append(data)
        except Exception:
            continue
    return logs


def rollback_operation(operation_id: str) -> dict:
    if not operation_id or Path(operation_id).name != operation_id or "/" in operation_id or "\\" in operation_id:
        return {"rolled_back": 0, "errors": ["无效操作记录标识"]}
    log_path = _get_log_dir() / f"{operation_id}.json"
    if not log_path.exists():
        return {"rolled_back": 0, "errors": [f"操作记录不存在：{operation_id}"]}

    log = json.loads(log_path.read_text())

    # Prevent double rollback
    if log.get("rolled_back"):
        return {"rolled_back": 0, "errors": ["此操作已经被回滚过"]}

    rolled_back = 0
    errors = []
    rollback_actions = []

    for action in log.get("actions", []):
        if action.get("rollback_status") == "success" or action.get("status") != "success" or action.get("action_type") != "move":
            continue
        dest = Path(action["destination"])
        src = Path(action["source"])
        expected_hash = action.get("file_hash", "")

        if not dest.exists():
            errors.append(f"目标文件不存在，跳过：{dest}")
            continue

        # Verify hash hasn't changed
        current_hash = _sha256(dest)
        if expected_hash and current_hash != expected_hash:
            errors.append(f"文件已被修改，跳过回滚：{dest}")
            continue

        # Restore to original location
        restore_path = src
        if src.exists():
            restore_path = _resolve_conflict(src.with_name(src.stem + "_recovered" + src.suffix))
        try:
            restored = safe_move(dest, restore_path)
            if restored["status"] != "success":
                raise OSError(restored["error"])
            restore_path = Path(restored["destination"])
            action["rollback_status"] = "success"
            action["restored_to"] = str(restore_path)
            rolled_back += 1
            rollback_actions.append({
                "action_type": "restore",
                "source": str(dest),
                "destination": str(restore_path),
                "file_hash": expected_hash,
                "status": "success",
                "error": None,
            })
        except Exception as e:
            errors.append(f"回滚失败 {dest}: {e}")
            rollback_actions.append({
                "action_type": "restore",
                "source": str(dest),
                "destination": str(restore_path),
                "file_hash": "",
                "status": "failed",
                "error": str(e),
            })

    # Mark the original operation as rolled back
    if rolled_back > 0:
        log["rolled_back"] = all(
            a.get("rollback_status") == "success"
            for a in log.get("actions", [])
            if a.get("status") == "success" and a.get("action_type") == "move"
        )
        log["rolled_back_at"] = datetime.now(tz=timezone.utc).isoformat()
        temporary = log_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(log, ensure_ascii=False, indent=2))
        temporary.replace(log_path)

    # Collect destination directories for cleanup
    dest_dirs = set()
    for action in log.get("actions", []):
        if action.get("destination"):
            dest_dirs.add(str(Path(action["destination"]).parent))

    return {
        "rolled_back": rolled_back,
        "errors": errors,
        "rollback_actions": rollback_actions,
        "cleanup_dirs": list(dest_dirs),
    }
