@echo off
title PenDrift - Build client
cd /d "%~dp0"

echo Installing client dependencies...
cd client
call pnpm install --frozen-lockfile
if errorlevel 1 (
    echo [ERROR] pnpm install failed.
    pause
    exit /b 1
)

echo.
echo Building client (vite build)...
call pnpm build
if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo [OK] Client built to client\dist
pause
