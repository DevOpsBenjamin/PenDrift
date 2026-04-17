@echo off
title PenDrift Setup
cd /d "%~dp0"

echo ============================================
echo  PenDrift - Setup
echo ============================================
echo.

set CONDA_DIR=%~dp0conda
set ENV_DIR=%~dp0server-python\env
set MINICONDA_URL=https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe
set INSTALLER=%~dp0miniconda_installer.exe

:: Step 1: Install miniconda locally if not present
if exist "%CONDA_DIR%\condabin\conda.bat" (
    echo [OK] Local Miniconda found.
) else (
    echo Downloading Miniconda...
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%MINICONDA_URL%' -OutFile '%INSTALLER%'}"
    if not exist "%INSTALLER%" (
        echo [ERROR] Download failed.
        pause
        exit /b 1
    )
    echo Installing Miniconda locally to %CONDA_DIR% ...
    start /wait "" "%INSTALLER%" /S /InstallationType=JustMe /RegisterPython=0 /AddToPath=0 /D=%CONDA_DIR%
    del "%INSTALLER%" 2>nul
    if not exist "%CONDA_DIR%\condabin\conda.bat" (
        echo [ERROR] Miniconda installation failed.
        pause
        exit /b 1
    )
    echo [OK] Miniconda installed locally.
)

:: Step 2: Create or update conda env inside the project
echo.
call "%CONDA_DIR%\condabin\conda.bat" activate base

if exist "%ENV_DIR%\python.exe" (
    echo Updating conda environment...
    call "%CONDA_DIR%\condabin\conda.bat" env update -f server-python\environment.yml -p "%ENV_DIR%" --prune
) else (
    echo Creating conda environment...
    call "%CONDA_DIR%\condabin\conda.bat" env create -f server-python\environment.yml -p "%ENV_DIR%"
)

if errorlevel 1 (
    echo [ERROR] Environment creation failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Setup complete!
echo.
echo  Run StartPython.bat to launch PenDrift.
echo  llama-server will be auto-downloaded on
echo  first use from the Settings page.
echo ============================================
pause
