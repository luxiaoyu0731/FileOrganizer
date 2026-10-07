"""A relative interpreter must survive the build script changing directory."""
import os
import shutil
import subprocess
from pathlib import Path


def test_build_accepts_relative_interpreter_with_spaces(tmp_path):
    repo=tmp_path/'fixture'; (repo/'scripts').mkdir(parents=True); (repo/'backend').mkdir()
    script=Path(__file__).resolve().parents[3]/'scripts/build-backend.sh'
    shutil.copyfile(script,repo/'scripts/build-backend.sh')
    python=repo/'tools with spaces'/'python'; python.parent.mkdir()
    python.write_text('#!/bin/sh\nmkdir -p dist\nprintf compiled > dist/file-organizer-backend\n')
    python.chmod(0o700)
    result=subprocess.run(['bash','scripts/build-backend.sh'],cwd=repo,
        env={**os.environ,'FILEORGANIZER_PYTHON':'tools with spaces/python'},capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert (repo/'build/backend/file-organizer-backend').read_text()=='compiled'
