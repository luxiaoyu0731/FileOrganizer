import json
from pathlib import Path
import subprocess
import sys


def test_free_sample_reports_real_moves_and_refuses_reuse(tmp_path):
    script = Path(__file__).resolve().parents[3] / 'examples/try_archive.py'
    destination = tmp_path / 'sample'
    run = subprocess.run([sys.executable, str(script), '--destination', str(destination)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    result = json.loads((destination / 'result.json').read_text())
    assert result['model_calls'] == 0 and result['archived'] == result['restored'] == 3
    report = (destination / 'sample-result.md').read_text()
    for file in (destination / 'inbox').iterdir():
        assert f'inbox/{file.name}' in report and f'archive/Sample project/{file.name}' in report
    before = (destination / 'result.json').read_bytes()
    repeat = subprocess.run([sys.executable, str(script), '--destination', str(destination)], capture_output=True)
    assert repeat.returncode != 0 and (destination / 'result.json').read_bytes() == before
