@echo off
REM ============================================================
REM FileOrganizer Standalone 构建脚本 (Windows)
REM 产物：standalone\dist\file-organizer.exe （单文件可执行）
REM
REM 执行环境要求（仅开发者机器需要）：
REM   - Python 3.11+
REM   - Node.js 18+
REM   - npm
REM ============================================================
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
set STANDALONE_DIR=%SCRIPT_DIR%
set OUTPUT_DIR=%STANDALONE_DIR%dist
set WEB_DIR=%STANDALONE_DIR%web

echo =========================================
echo  FileOrganizer Standalone Build (Windows)
echo =========================================

REM ── Step 1: 安装 Python 依赖 ──────────────────────────────
echo.
echo [1/4] 安装 Python 依赖...
pip install -r "%STANDALONE_DIR%requirements.txt" --quiet
if errorlevel 1 ( echo ERROR: pip install 失败 & exit /b 1 )

REM ── Step 2: 构建 React 前端 ────────────────────────────────
echo.
echo [2/4] 构建前端（fetch 模式，无 Electron）...
cd /d "%PROJECT_ROOT%"
call npm install --silent
if errorlevel 1 ( echo ERROR: npm install 失败 & exit /b 1 )
call npx vite build --config vite.standalone.config.ts
if errorlevel 1 ( echo ERROR: vite build 失败 & exit /b 1 )
echo       前端构建完成 -^> standalone\web\

REM ── Step 3: PyInstaller 打包 ───────────────────────────────
echo.
echo [3/4] PyInstaller 打包中...
cd /d "%STANDALONE_DIR%"

if exist "%OUTPUT_DIR%" rmdir /s /q "%OUTPUT_DIR%"
if exist "build" rmdir /s /q "build"

pyinstaller ^
    --onefile ^
    --name file-organizer ^
    --distpath "%OUTPUT_DIR%" ^
    --workpath "%STANDALONE_DIR%build\pyinstaller-work" ^
    --specpath "%STANDALONE_DIR%build" ^
    --add-data "%PROJECT_ROOT%backend;backend" ^
    --add-data "%WEB_DIR%;web" ^
    --hidden-import=pymupdf ^
    --hidden-import=pdfplumber ^
    --hidden-import=PIL ^
    --hidden-import=piexif ^
    --hidden-import=pillow_heif ^
    --hidden-import=docx ^
    --hidden-import=openpyxl ^
    --hidden-import=pptx ^
    --hidden-import=mutagen ^
    --hidden-import=openai ^
    --hidden-import=watchdog.observers ^
    --hidden-import=watchdog.events ^
    --hidden-import=fastapi ^
    --hidden-import=uvicorn ^
    --hidden-import=uvicorn.logging ^
    --hidden-import=uvicorn.loops ^
    --hidden-import=uvicorn.loops.auto ^
    --hidden-import=uvicorn.protocols ^
    --hidden-import=uvicorn.protocols.http ^
    --hidden-import=uvicorn.protocols.http.auto ^
    --hidden-import=uvicorn.lifespan ^
    --hidden-import=uvicorn.lifespan.on ^
    "%STANDALONE_DIR%main.py"

if errorlevel 1 ( echo ERROR: PyInstaller 打包失败 & exit /b 1 )

REM ── Step 4: 完成 ───────────────────────────────────────────
echo.
echo [4/4] 完成！
echo.
echo   可执行文件：%OUTPUT_DIR%\file-organizer.exe
echo.
echo   分发方式：
echo     将 dist\file-organizer.exe 复制给用户
echo     用户双击即可，浏览器自动打开
echo.
echo   访问地址：http://127.0.0.1:18924
echo =========================================
endlocal
