"""Start only the just-built backend in a disposable home; no models or files scanned."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="file-preview-") as tmp:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port=s.getsockname()[1]
    env={**os.environ,"HOME":tmp,"FILEORGANIZER_PORT":str(port),"FILEORGANIZER_HOST":"127.0.0.1"}
    with open(Path(tmp)/"startup.log","w") as log:
        child=subprocess.Popen([str(Path(sys.argv[1]).resolve())],cwd=tmp,env=env,stdout=log,stderr=log)
        try:
            for _ in range(90):
                if child.poll() is not None:
                    raise RuntimeError("Packaged backend exited before readiness")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health",timeout=1) as response:
                        if response.status == 200:
                            print("PASS: packaged backend health endpoint")
                            break
                except (OSError,TimeoutError):
                    time.sleep(1)
            else:
                raise RuntimeError("Packaged backend readiness timed out")
        finally:
            child.terminate()
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait()
