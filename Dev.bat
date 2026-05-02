@echo off
title PenDrift Dev
cd /d "%~dp0"

set ENV_DIR=%~dp0server-python\env

:: Check setup
if not exist "%ENV_DIR%\python.exe" (
    echo [ERROR] Run SetupPython.bat first.
    pause
    exit /b 1
)

:: Start both: Python backend + Vite dev server
echo Starting PenDrift dev mode...
echo   Backend:  http://localhost:3000
echo   Frontend: http://localhost:5173
echo.

start "PenDrift Backend" cmd /k "set PENDRIFT_DEV=1 && cd server-python && "%ENV_DIR%\python.exe" run.py"
timeout /t 2 /nobreak >nul
start "PenDrift Frontend" cmd /k "cd client && pnpm dev"

echo Both servers starting. Open http://localhost:5173
pause
