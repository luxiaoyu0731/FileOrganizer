"""
Watchdog-based file watcher with debounce and auto-classify pipeline.
"""
import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from config.schema import AiConfig, ScanConfig
from scanner.scan import HIDDEN_PREFIXES, SYSTEM_FILES, TEMP_EXTENSIONS

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 5.0

# Files in-flight (being written to)
_IN_FLIGHT_SUFFIXES = {".crdownload", ".part", ".download", ".partial", ".tmp"}


class _DebounceHandler(FileSystemEventHandler):
    """Accumulates new/modified file events and fires callback after debounce."""

    def __init__(self, callback: Callable[[list[str]], None], debounce: float = DEBOUNCE_SECONDS):
        self._callback = callback
        self._debounce = debounce
        self._pending: dict[str, float] = {}  # path → last event time
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None

    def _eligible(self, path: str) -> bool:
        p = Path(path)
        if p.name in SYSTEM_FILES:
            return False
        if p.name.startswith(HIDDEN_PREFIXES):
            return False
        if p.suffix.lower() in TEMP_EXTENSIONS | _IN_FLIGHT_SUFFIXES:
            return False
        if not p.is_file():
            return False
        return True

    def _schedule(self) -> None:
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(self._debounce, self._fire)
        self._timer.daemon = True
        self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            paths = list(self._pending.keys())
            self._pending.clear()
        if paths:
            logger.info("[watcher] Firing pipeline for %d files", len(paths))
            self._callback(paths)

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        if self._eligible(event.src_path):
            with self._lock:
                self._pending[event.src_path] = time.monotonic()
            self._schedule()

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        if self._eligible(event.src_path):
            with self._lock:
                self._pending[event.src_path] = time.monotonic()
            self._schedule()


class FileWatcher:
    def __init__(self) -> None:
        self._observer: Optional[Observer] = None
        self._watching = False
        self._paths: list[str] = []
        self._ai_config: Optional[AiConfig] = None
        self._auto_execute: bool = False
        self._archive_root: str = ""
        self._rename_strategy: str = "semantic_date"
        self._recent: list[dict] = []  # last 50 processed entries
        self._lock = threading.Lock()

    @property
    def watching(self) -> bool:
        return self._watching

    @property
    def paths(self) -> list[str]:
        return self._paths

    @property
    def recent(self) -> list[dict]:
        with self._lock:
            return list(self._recent)

    def start(
        self,
        paths: list[str],
        ai_config: AiConfig,
        archive_root: str,
        rename_strategy: str = "semantic_date",
        auto_execute: bool = False,
    ) -> None:
        if self._watching:
            self.stop()

        self._paths = paths
        self._ai_config = ai_config
        self._archive_root = archive_root
        self._rename_strategy = rename_strategy
        self._auto_execute = auto_execute

        handler = _DebounceHandler(self._on_new_files)
        self._observer = Observer()
        for path in paths:
            p = Path(path).expanduser().resolve()
            if p.exists() and p.is_dir():
                self._observer.schedule(handler, str(p), recursive=True)
                logger.info("[watcher] Watching: %s", p)

        self._observer.start()
        self._watching = True
        logger.info("[watcher] Started watching %d paths", len(paths))

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        self._watching = False
        logger.info("[watcher] Stopped")

    def _on_new_files(self, file_paths: list[str]) -> None:
        """Run classify+archive pipeline in a new thread."""
        thread = threading.Thread(
            target=self._run_pipeline,
            args=(file_paths,),
            daemon=True,
        )
        thread.start()

    def _run_pipeline(self, file_paths: list[str]) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_pipeline(file_paths))
        finally:
            loop.close()

    async def _async_pipeline(self, file_paths: list[str]) -> None:
        from classifier.ai_classifier import classify_files
        from config.schema import ScanResult
        import hashlib, os
        from datetime import datetime, timezone

        scan_results = []
        for p in file_paths:
            path = Path(p)
            if not path.exists():
                continue
            try:
                stat = path.stat()
                h = hashlib.sha256()
                with path.open("rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
                scan_results.append(ScanResult(
                    path=str(path),
                    size_bytes=stat.st_size,
                    modified_time=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    extension=path.suffix.lower(),
                    sha256=h.hexdigest(),
                ))
            except Exception as e:
                logger.warning("[watcher] Could not stat %s: %s", p, e)

        if not scan_results or not self._ai_config:
            return

        classifications = await classify_files(scan_results, self._ai_config)

        entries = []
        if self._auto_execute and self._archive_root:
            from archiver.archiver import safe_move
            from renamer.renamer import build_destination
            from rollback import rollback as rollback_module

            actions = []
            for cls in classifications:
                src = Path(cls["path"])
                if not src.exists():
                    continue
                dest = build_destination(cls, self._archive_root, self._rename_strategy)
                action = safe_move(src, dest)
                action["classification"] = {"category": cls["category"], "confidence": cls["confidence"]}
                action["classification_method"] = cls["classification_method"]
                actions.append(action)
                entries.append({
                    "path": cls["path"],
                    "category": cls["category"],
                    "destination": action.get("destination", ""),
                    "status": action["status"],
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                })

            rollback_module.write_operation_log(
                actions, mode="watch", ai_model=self._ai_config.model
            )
        else:
            for cls in classifications:
                entries.append({
                    "path": cls["path"],
                    "category": cls["category"],
                    "destination": "",
                    "status": "pending",
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                })

        with self._lock:
            self._recent = (entries + self._recent)[:50]


# Singleton
_watcher = FileWatcher()


def get_watcher() -> FileWatcher:
    return _watcher
