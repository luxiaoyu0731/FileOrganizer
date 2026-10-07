import hashlib
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_conflict(dest: Path) -> Path:
    """Append _001, _002 … if destination already exists."""
    if not dest.exists():
        return dest
    stem = dest.stem
    ext = dest.suffix
    parent = dest.parent
    for i in range(1, 1000):
        candidate = parent / f"{stem}_{i:03d}{ext}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Too many conflicts for {dest}")


def _check_disk_space(src: Path, dest_parent: Path) -> None:
    """Raise OSError if destination disk has insufficient free space."""
    try:
        file_size = src.stat().st_size
        disk = shutil.disk_usage(dest_parent if dest_parent.exists() else dest_parent.parent)
        # Require at least file_size + 10 MB headroom
        if disk.free < file_size + 10 * 1024 * 1024:
            raise OSError(
                f"目标磁盘空间不足：需要 {file_size // 1024 // 1024} MB，"
                f"剩余 {disk.free // 1024 // 1024} MB"
            )
    except OSError:
        raise
    except Exception:
        pass  # Non-fatal if disk_usage fails on unusual mounts


def safe_move(src: Path, dest: Path, *, archive_root: str | None = None) -> dict:
    """
    Copy src → dest (with conflict resolution), verify SHA256, then delete src.
    Returns action log entry.
    """
    if archive_root is not None and not dest.resolve().is_relative_to(Path(archive_root).resolve()):
        raise ValueError("Destination escapes archive root")
    src_hash = _sha256(src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _check_disk_space(src, dest.parent)

    owned = False
    try:
        # Exclusive creation closes the check-then-copy overwrite race.
        requested = dest
        for i in range(1000):
            dest = requested if i == 0 else requested.with_name(f"{requested.stem}_{i:03d}{requested.suffix}")
            try:
                target = dest.open("xb")
                owned = True
                break
            except FileExistsError:
                continue
        else:
            raise FileExistsError(f"Too many conflicts for {requested}")
        with target, src.open("rb") as source:
            shutil.copyfileobj(source, target)
            target.flush()
        shutil.copystat(src, dest)
        dest_hash = _sha256(dest)
        if src_hash != dest_hash or _sha256(src) != src_hash:
            dest.unlink(missing_ok=True)
            raise IOError(f"Hash mismatch after copy: {src} → {dest}")
        src.unlink()
        return {
            "action_type": "move",
            "source": str(src),
            "destination": str(dest),
            "file_hash": src_hash,
            "status": "success",
            "error": None,
        }
    except Exception as e:
        logger.error("Failed to move %s → %s: %s", src, dest, e)
        # Clean up partial copy
        if owned and dest.exists():
            try:
                dest.unlink()
            except Exception:
                pass
        return {
            "action_type": "move",
            "source": str(src),
            "destination": str(dest),
            "file_hash": src_hash,
            "status": "failed",
            "error": str(e),
        }
