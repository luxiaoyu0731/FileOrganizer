"""Adversarial paths, concurrent moves and retryable recovery."""
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))
from archiver import archiver
from renamer.renamer import build_destination
from rollback import rollback


@pytest.mark.parametrize('segment', ['.', '..'])
def test_dot_segments_rejected(tmp_path, segment):
    with pytest.raises(ValueError):
        build_destination({'path': '/input/note.txt', 'sub_path': [segment]}, str(tmp_path), 'preserve_original')


def test_existing_symlink_cannot_escape_root(tmp_path):
    root = tmp_path / 'archive'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / 'docs').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        build_destination({'path': '/input/note.txt', 'category': 'docs'}, str(root), 'preserve_original')


def test_model_date_cannot_create_directories(tmp_path):
    dest = build_destination({'path': '/input/note.txt', 'metadata': {'created_date': '../../bad/date'}}, str(tmp_path), 'semantic_date')
    assert dest.parent == tmp_path / '其他'


def test_concurrent_moves_preserve_every_payload(tmp_path):
    sources = []
    for i in range(12):
        src = tmp_path / f'source-{i}.txt'
        src.write_text(str(i))
        sources.append(src)
    with ThreadPoolExecutor(max_workers=12) as pool:
        actions = list(pool.map(lambda p: archiver.safe_move(p, tmp_path / 'archive' / 'same.txt'), sources))
    assert all(a['status'] == 'success' for a in actions)
    assert {p.read_text() for p in (tmp_path / 'archive').iterdir()} == {str(i) for i in range(12)}


def test_failed_copy_preserves_existing_destination_and_source(tmp_path, monkeypatch):
    src = tmp_path / 'source.txt'
    src.write_text('source')
    dest = tmp_path / 'saved.txt'
    dest.write_text('existing')
    monkeypatch.setattr(archiver.shutil, 'copyfileobj', lambda source, target: target.write(b'corrupt'))
    assert archiver.safe_move(src, dest)['status'] == 'failed'
    assert src.read_text() == 'source'
    assert dest.read_text() == 'existing'
    assert not (tmp_path / 'saved_001.txt').exists()


def test_partial_rollback_can_retry_only_unfinished_actions(tmp_path):
    rollback.set_log_dir(tmp_path / 'logs')
    actions = []
    for i in range(2):
        src = tmp_path / f'original-{i}.txt'
        src.write_text(str(i))
        actions.append(archiver.safe_move(src, tmp_path / 'archive' / src.name))
    op = rollback.write_operation_log(actions)
    broken = Path(actions[1]['destination'])
    broken.write_text('changed')
    assert rollback.rollback_operation(op)['rolled_back'] == 1
    broken.write_text('1')
    second = rollback.rollback_operation(op)
    assert second['rolled_back'] == 1
    assert second['errors'] == []
    assert (tmp_path / 'original-0.txt').read_text() == '0'
    assert not (tmp_path / 'original-0_recovered.txt').exists()
    assert rollback.rollback_operation(op)['rolled_back'] == 0


def test_rollback_id_cannot_read_outside_log_directory(tmp_path):
    rollback.set_log_dir(tmp_path / 'logs')
    assert rollback.rollback_operation('../outside')['errors'] == ['无效操作记录标识']
