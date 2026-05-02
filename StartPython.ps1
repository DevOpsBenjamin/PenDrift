$ErrorActionPreference = 'Stop'
$envDir = Join-Path $PSScriptRoot 'server-python\env'
$python = Join-Path $envDir 'python.exe'

if (-not (Test-Path $python)) {
    Write-Host "[ERROR] Environment not found. Run SetupPython.bat first." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $PSScriptRoot 'client\dist\index.html'))) {
    Write-Host "[WARN] client\dist missing - run BuildClient.bat first to serve the UI." -ForegroundColor Yellow
    Write-Host "       Continuing with API only..." -ForegroundColor Yellow
    Write-Host ""
}

Push-Location (Join-Path $PSScriptRoot 'server-python')
try {
    Write-Host "Starting PenDrift on http://localhost:3000  (Ctrl+C to stop)`n"
    & $python run.py
}
finally {
    Pop-Location
}
