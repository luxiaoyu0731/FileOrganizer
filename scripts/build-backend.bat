@echo off
REM Build Python backend as a single Windows executable using PyInstaller
REM Run from the project root: scripts\build-backend.bat

setlocal

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
set BACKEND_DIR=%PROJECT_ROOT%\backend
set OUTPUT_DIR=%PROJECT_ROOT%\build\backend

echo [build-backend] Building Python backend for Windows...

cd /d "%BACKEND_DIR%"

REM Install PyInstaller if needed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [build-backend] Installing PyInstaller...
    pip install pyinstaller
)

REM Clean previous build
if exist "%OUTPUT_DIR%" rmdir /s /q "%OUTPUT_DIR%"
mkdir "%OUTPUT_DIR%"

REM Build the sidecar binary
pyinstaller ^
    --onefile ^
    --name file-organizer-backend ^
    --distpath "%OUTPUT_DIR%" ^
    --workpath "%PROJECT_ROOT%\build\pyinstaller-work" ^
    --specpath "%PROJECT_ROOT%\build" ^
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
    server.py

if errorlevel 1 (
    echo [build-backend] ERROR: PyInstaller build failed.
    exit /b 1
)

echo [build-backend] Done: %OUTPUT_DIR%\file-organizer-backend.exe
endlocal
