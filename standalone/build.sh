#!/usr/bin/env bash
# ============================================================
# FileOrganizer Standalone 构建脚本 (macOS / Linux)
# 产物：standalone/dist/file-organizer  （单文件可执行）
#
# 执行环境要求（仅开发者机器需要）：
#   - Python 3.11+
#   - Node.js 18+
#   - npm
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STANDALONE_DIR="$SCRIPT_DIR"
OUTPUT_DIR="$STANDALONE_DIR/dist"
WEB_DIR="$STANDALONE_DIR/web"

echo "========================================="
echo " FileOrganizer Standalone Build (macOS/Linux)"
echo "========================================="

# ── Step 1: 安装 Python 依赖 ──────────────────────────────────
echo ""
echo "[1/4] 安装 Python 依赖..."
pip install -r "$STANDALONE_DIR/requirements.txt" --quiet

# ── Step 2: 构建 React 前端（Standalone 版）─────────────────
echo ""
echo "[2/4] 构建前端（fetch 模式，无 Electron）..."
cd "$PROJECT_ROOT"
npm install --silent
npx vite build --config config/vite.standalone.config.ts
echo "      前端构建完成 → standalone/web/"

# ── Step 3: PyInstaller 打包 ─────────────────────────────────
echo ""
echo "[3/4] PyInstaller 打包中..."
cd "$STANDALONE_DIR"

rm -rf "$OUTPUT_DIR" build __pycache__

# 将 backend/ 目录和 web/ 目录一起打包进二进制
pyinstaller \
    --onefile \
    --name file-organizer \
    --distpath "$OUTPUT_DIR" \
    --workpath "$STANDALONE_DIR/build/pyinstaller-work" \
    --specpath "$STANDALONE_DIR/build" \
    --add-data "$PROJECT_ROOT/backend:backend" \
    --add-data "$WEB_DIR:web" \
    --hidden-import=pymupdf \
    --hidden-import=pdfplumber \
    --hidden-import=PIL \
    --hidden-import=piexif \
    --hidden-import=pillow_heif \
    --hidden-import=docx \
    --hidden-import=openpyxl \
    --hidden-import=pptx \
    --hidden-import=mutagen \
    --hidden-import=openai \
    --hidden-import=watchdog.observers \
    --hidden-import=watchdog.events \
    --hidden-import=fastapi \
    --hidden-import=uvicorn \
    --hidden-import=uvicorn.logging \
    --hidden-import=uvicorn.loops \
    --hidden-import=uvicorn.loops.auto \
    --hidden-import=uvicorn.protocols \
    --hidden-import=uvicorn.protocols.http \
    --hidden-import=uvicorn.protocols.http.auto \
    --hidden-import=uvicorn.lifespan \
    --hidden-import=uvicorn.lifespan.on \
    "$STANDALONE_DIR/main.py"

# ── Step 4: 完成 ─────────────────────────────────────────────
echo ""
echo "[4/4] 完成！"
echo ""
echo "  可执行文件：$OUTPUT_DIR/file-organizer"
echo ""
echo "  分发方式："
echo "    将 dist/file-organizer 复制给用户"
echo "    用户双击（或终端运行）即可，浏览器自动打开"
echo ""
echo "  访问地址：http://127.0.0.1:18924"
echo "========================================="
