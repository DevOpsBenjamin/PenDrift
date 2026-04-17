@echo off
title PenDrift
cd /d "%~dp0"

set CONDA_DIR=%~dp0conda
set ENV_DIR=%~dp0server-python\env

:: Check setup was run
if not exist "%ENV_DIR%\python.exe" (
    echo [ERROR] Environment not found. Run SetupPython.bat first.
    pause
    exit /b 1
)

:: Activate local conda + project env
call "%CONDA_DIR%\condabin\conda.bat" activate "%ENV_DIR%"

:: Start the server
cd /d "%~dp0server-python"
echo Starting PenDrift on http://localhost:3000 ...
python run.py
pause
