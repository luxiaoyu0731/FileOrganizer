"""
Integration tests for rollback: write log → rollback → verify file restored.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import hashlib
import tempfile

from archiver.archiver import safe_move
from rollback import rollback as rollback_module


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ─── Full round-trip ──────────────────────────────────────────────────────────

def test_rollback_restores_file():
    with tempfile.TemporaryDirectory() as tmp:
        rollback_module.set_log_dir(Path(tmp) / "logs")

        src = Path(tmp) / "original" / "doc.txt"
        src.parent.mkdir()
        src.write_text("important content")
        original_hash = _sha256(src)

        dest = Path(tmp) / "archive" / "doc.txt"
        action = safe_move(src, dest)
        assert action["status"] == "success"

        op_id = rollback_module.write_operation_log([action], mode="scan")

        result = rollback_module.rollback_operation(op_id)

        assert result["rolled_back"] == 1
        assert result["errors"] == []
        assert src.exists(), "Original file should be restored"
        assert _sha256(src) == original_hash, "Hash must match after rollback"
        assert not dest.exists(), "Archive copy should be deleted after rollback"


def test_rollback_skips_modified_file():
    with tempfile.TemporaryDirectory() as tmp:
        rollback_module.set_log_dir(Path(tmp) / "logs")

        src = Path(tmp) / "src" / "data.bin"
        src.parent.mkdir()
        src.write_bytes(b"\x00" * 100)

        dest = Path(tmp) / "archive" / "data.bin"
        action = safe_move(src, dest)
        assert action["status"] == "success"

        op_id = rollback_module.write_operation_log([action], mode="scan")

        # Tamper with the archived file
        dest.write_bytes(b"\xFF" * 100)

        result = rollback_module.rollback_operation(op_id)

        assert result["rolled_back"] == 0
        assert len(result["errors"]) == 1
        assert "已被修改" in result["errors"][0]


def test_rollback_handles_missing_dest():
    with tempfile.TemporaryDirectory() as tmp:
        rollback_module.set_log_dir(Path(tmp) / "logs")

        src = Path(tmp) / "src" / "file.txt"
        src.parent.mkdir()
        src.write_text("hello")

        dest = Path(tmp) / "archive" / "file.txt"
        action = safe_move(src, dest)
        op_id = rollback_module.write_operation_log([action], mode="scan")

        # Remove dest before rollback
        dest.unlink()

        result = rollback_module.rollback_operation(op_id)
        assert result["rolled_back"] == 0
        assert any("不存在" in e for e in result["errors"])


def test_rollback_recovered_suffix_on_conflict():
    with tempfile.TemporaryDirectory() as tmp:
        rollback_module.set_log_dir(Path(tmp) / "logs")

        src = Path(tmp) / "src" / "note.txt"
        src.parent.mkdir()
        src.write_text("original")

        dest = Path(tmp) / "archive" / "note.txt"
        action = safe_move(src, dest)
        op_id = rollback_module.write_operation_log([action], mode="scan")

        # Occupy the original source path before rollback
        src.write_text("new file at original path")

        result = rollback_module.rollback_operation(op_id)

        assert result["rolled_back"] == 1
        recovered = src.with_name("note_recovered.txt")
        assert recovered.exists(), "Should recover to _recovered path"
        assert recovered.read_text() == "original"


def test_rollback_unknown_operation_id():
    with tempfile.TemporaryDirectory() as tmp:
        rollback_module.set_log_dir(Path(tmp) / "logs")

        result = rollback_module.rollback_operation("nonexistent-uuid-1234")
        assert result["rolled_back"] == 0
        assert len(result["errors"]) == 1


def test_list_operations_returns_all():
    with tempfile.TemporaryDirectory() as tmp:
        rollback_module.set_log_dir(Path(tmp) / "logs")

        for i in range(3):
            rollback_module.write_operation_log([], mode="scan", ai_model=f"model-{i}")

        ops = rollback_module.list_operations()
        assert len(ops) == 3
