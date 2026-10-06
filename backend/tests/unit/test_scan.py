import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import tempfile

import pytest

from config.schema import ScanConfig
from scanner.scan import scan_directory


def test_scan_returns_files():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "test.txt").write_text("hello")
        config = ScanConfig(paths=[tmp])
        results = scan_directory(config)
        assert len(results) == 1
        assert results[0].extension == ".txt"


def test_scan_excludes_hidden():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".hidden").write_text("hidden")
        (Path(tmp) / "visible.txt").write_text("visible")
        config = ScanConfig(paths=[tmp])
        results = scan_directory(config)
        assert len(results) == 1
        assert results[0].extension == ".txt"


def test_scan_excludes_ds_store():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".DS_Store").write_bytes(b"\x00" * 10)
        (Path(tmp) / "real.pdf").write_bytes(b"%PDF-1.4")
        config = ScanConfig(paths=[tmp])
        results = scan_directory(config)
        assert len(results) == 1
        assert results[0].extension == ".pdf"


def test_scan_excludes_temp_files():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "downloading.crdownload").write_bytes(b"partial")
        (Path(tmp) / "done.zip").write_bytes(b"PK\x03\x04")
        config = ScanConfig(paths=[tmp])
        results = scan_directory(config)
        assert len(results) == 1
        assert results[0].extension == ".zip"


def test_scan_includes_stable_fast_identity():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "file.txt").write_text("content")
        config = ScanConfig(paths=[tmp])
        results = scan_directory(config)
        assert len(results[0].sha256) == 32
        assert results[0].sha256 == scan_directory(config)[0].sha256


def test_scan_nonexistent_path():
    config = ScanConfig(paths=["/nonexistent/path/xyz"])
    results = scan_directory(config)
    assert results == []


def test_scan_skips_empty_files():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "empty.txt").write_bytes(b"")
        (Path(tmp) / "nonempty.txt").write_text("data")
        config = ScanConfig(paths=[tmp])
        results = scan_directory(config)
        assert len(results) == 1
        assert results[0].path.endswith("nonempty.txt")


def test_scan_skips_symlinks():
    import os
    with tempfile.TemporaryDirectory() as tmp:
        real = Path(tmp) / "real.txt"
        real.write_text("content")
        link = Path(tmp) / "link.txt"
        try:
            os.symlink(str(real), str(link))
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks not supported on this platform")
        config = ScanConfig(paths=[tmp])
        results = scan_directory(config)
        paths = [r.path for r in results]
        assert not any("link.txt" in p for p in paths), "Symlink should be excluded"
        assert any("real.txt" in p for p in paths), "Real file should be included"


def test_scan_max_size_excludes_large_files():
    with tempfile.TemporaryDirectory() as tmp:
        small = Path(tmp) / "small.txt"
        small.write_bytes(b"x" * 100)
        large = Path(tmp) / "large.bin"
        large.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MB
        config = ScanConfig(paths=[tmp], max_size_mb=1)
        results = scan_directory(config)
        assert len(results) == 1
        assert results[0].path.endswith("small.txt")
