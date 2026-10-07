#!/usr/bin/env bash
set -euo pipefail

fileorganizer_python="${FILEORGANIZER_PYTHON:-python3}"
if [[ "$fileorganizer_python" == */* && "$fileorganizer_python" != /* ]]; then
  fileorganizer_python="$PWD/$fileorganizer_python"
fi

cd "$(dirname "$0")/../backend"

echo "Building Python backend with PyInstaller..."
"$fileorganizer_python" -m PyInstaller \
  --clean \
  --noconfirm \
  --onefile \
  --name file-organizer-backend \
  --add-data "config:config" \
  --add-data "scanner:scanner" \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols \
  --hidden-import uvicorn.protocols.http \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan \
  --hidden-import uvicorn.lifespan.on \
  server.py

mkdir -p ../build/backend
cp dist/file-organizer-backend ../build/backend/
echo "Done! Binary at build/backend/file-organizer-backend"
