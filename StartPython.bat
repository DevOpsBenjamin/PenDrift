@echo off
title PenDrift
cd /d "%~dp0"

set ENV_DIR=%~dp0server-python\env

if not exist "%ENV_DIR%\python.exe" (
    echo [ERROR] Environment not found. Run SetupPython.bat first.
    pause
    exit /b 1
)

if not exist "%~dp0client\dist\index.html" (
    echo [WARN] client\dist missing — run BuildClient.bat first to serve the UI.
    echo        Continuing with API only...
    echo.
)

cd /d "%~dp0server-python"
echo Starting PenDrift on http://localhost:3000  (Ctrl+C to stop)
echo.

"%ENV_DIR%\python.exe" run.py
