"""Offline sample: manual categories, actual archive and rollback, disposable files."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from archiver.archiver import safe_move
from rollback.rollback import rollback_operation, set_log_dir, write_operation_log

def run(destination):
    root = Path(destination).absolute()
    root.mkdir(parents=True, exist_ok=False)
    set_log_dir(root / "operation-logs")
    contents = {"order-notes.txt": "SYNTHETIC: sample order, 12 units.\n", "budget.csv": "item,amount\nsample,120\n", "readme.md": "# Synthetic project\nNo customer data.\n"}
    source = root / "inbox"
    source.mkdir()
    actions = []
    for name, text in contents.items():
        file = source / name
        file.write_text(text)
        actions.append(safe_move(file, root / "archive" / "Sample project" / name))
    if any(a["status"] != "success" for a in actions):
        raise RuntimeError("Archive failed; retain sample directory for inspection")
    operation = write_operation_log(actions, mode="offline-sample", ai_model="none")
    print("Archived 3 synthetic files using real copy/checksum code.")
    restored = rollback_operation(operation)
    if restored["errors"] or restored["rolled_back"] != len(contents):
        raise RuntimeError(restored)
    for name, text in contents.items():
        assert hashlib.sha256((source / name).read_bytes()).digest() == hashlib.sha256(text.encode()).digest()
    result = {"synthetic": True, "model_calls": 0, "archived": len(actions), "restored": restored["rolled_back"], "checksums_verified": True}
    (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, help="New directory only; never use real files")
    run(parser.parse_args().destination)
