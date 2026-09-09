# GeoPort - one-click launcher (runs the source build, no console window)
#
# Requires: Python 3.10-3.12 (https://www.python.org/downloads/) on PATH.
# 'uv' is used if available (much faster); otherwise plain pip.
# First run creates .\.venv and installs requirements.txt.
#
# Usage:  right-click -> Run with PowerShell   (or double-click, if .ps1 is
#         allowed by your execution policy: powershell -ExecutionPolicy Bypass -File start.ps1)

$ErrorActionPreference = 'Stop'
$repo  = $PSScriptRoot
$py    = Join-Path $repo '.venv\Scripts\python.exe'
$port  = 54321

if (-not (Test-Path $py)) {
    Write-Host "First run: creating .venv and installing dependencies (can take a few minutes)..."
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv venv --python 3.11 (Join-Path $repo '.venv') | Out-Null
        uv pip install --python $py -r (Join-Path $repo 'requirements.txt')
    } else {
        python -m venv (Join-Path $repo '.venv')
        & $py -m pip install --upgrade pip
        & $py -m pip install -r (Join-Path $repo 'requirements.txt')
    }
}

# Already running?
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "GeoPort is already running on http://localhost:$port"
    Start-Process "http://localhost:$port"
    exit 0
}

# Prefer pythonw (no console window at all). uv-created venvs don't ship
# pythonw.exe, so fall back to python.exe in a hidden console - visually the
# same (the app logs to <repo>\GeoPort.log either way). When launched via
# GeoPort.bat the process is already elevated, so pyuac's self-relaunch is a
# no-op.
$pyw = Join-Path $repo '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pyw)) { $pyw = $py }
Start-Process -FilePath $pyw -ArgumentList 'src\main.py' -WorkingDirectory $repo -WindowStyle Hidden
Write-Host "Starting GeoPort..."

$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        $ok = $true
        break
    }
}

if ($ok) {
    Write-Host "GeoPort is up: http://localhost:$port"
    Start-Process "http://localhost:$port"
} else {
    Write-Warning "GeoPort did not come up in 60s - check GeoPort.log in the repo folder."
}
