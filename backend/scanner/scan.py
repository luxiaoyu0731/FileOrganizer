import hashlib
import logging
import platform
from datetime import datetime, timezone
from pathlib import Path

from config.schema import ScanConfig, ScanResult

logger = logging.getLogger(__name__)

HIDDEN_PREFIXES = (".",)
SYSTEM_FILES = {".DS_Store", "Thumbs.db", "desktop.ini", ".localized"}
TEMP_EXTENSIONS = {".tmp", ".crdownload", ".part", ".download", ".partial"}

# Directories that should never be scanned (version control internals only).
# Dev artifacts (venv, node_modules, etc.) are still scanned so the UI can
# show accurate file counts — they are filtered pre-classification and
# auto-assigned back to their parent project group post-classification.
EXCLUDED_DIRS = {
    ".git", ".svn", ".hg",
}

# Windows MAX_PATH limit
_WIN_MAX_PATH = 260


def _fast_id(path: Path, stat) -> str:
    """
    Instant unique file identifier based on path + size + mtime.
    Reading file content for SHA-256 at scan time is far too slow for large
    files (3-D assets, videos, etc.).  The archiver computes a real SHA-256
    after each copy for integrity verification, so we don't need it here.
    """
    key = f"{path}\x00{stat.st_size}\x00{stat.st_mtime}"
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()


def _should_exclude(path: Path, config: ScanConfig) -> bool:
    name = path.name
    if name in SYSTEM_FILES:
        return True
    if name.startswith(HIDDEN_PREFIXES):
        return True
    if path.suffix.lower() in TEMP_EXTENSIONS:
        return True
    if name in config.exclude_patterns:
        return True
    # Skip symlinks to avoid loops and unintended targets
    if path.is_symlink():
        logger.debug("Skipping symlink: %s", path)
        return True
    stat = path.stat()
    # Skip empty files
    if stat.st_size == 0:
        logger.debug("Skipping empty file: %s", path)
        return True
    size_mb = stat.st_size / (1024 * 1024)
    if size_mb > config.max_size_mb:
        return True
    # Warn about long paths on Windows
    if platform.system() == "Windows" and len(str(path)) > _WIN_MAX_PATH:
        logger.warning("Path exceeds Windows MAX_PATH (%d chars), skipping: %s", len(str(path)), path)
        return True
    return False


def _in_excluded_dir(path: Path) -> bool:
    """Check if any ancestor directory is in the exclusion list."""
    for part in path.parts:
        if part in EXCLUDED_DIRS or part.endswith(".egg-info"):
            return True
    return False


def scan_directory(config: ScanConfig) -> list[ScanResult]:
    results: list[ScanResult] = []
    for root_str in config.paths:
        root = Path(root_str).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            continue
        for file_path in root.rglob("*"):
            # Skip symlinks at iteration level too (covers directory symlinks)
            if file_path.is_symlink():
                continue
            if not file_path.is_file():
                continue
            # Skip files inside excluded directories (venv, node_modules, etc.)
            if _in_excluded_dir(file_path.relative_to(root)):
                continue
            if _should_exclude(file_path, config):
                continue
            try:
                stat = file_path.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                sha = _fast_id(file_path, stat)
                results.append(
                    ScanResult(
                        path=str(file_path),
                        size_bytes=stat.st_size,
                        modified_time=mtime,
                        extension=file_path.suffix.lower(),
                        sha256=sha,
                    )
                )
            except (PermissionError, OSError) as e:
                logger.debug("Skipping inaccessible file %s: %s", file_path, e)
                continue
    return results
