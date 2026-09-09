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

$trace = Join-Path $repo 'launcher_trace.log'
function Log($m) { Add-Content -Path $trace -Value ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m) }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$elevated = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Log ("start.ps1 begin (PID {0}, elevated={1})" -f $PID, $elevated)

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

# Launch python.exe in a hidden console: -WindowStyle Hidden shows no window
# at all, so it is visually identical to pythonw. Deliberately NOT pythonw.exe:
# there sys.stderr is None, which used to crash the app's logging on the first
# log line (src/main.py now guards against this, but python.exe is the
# proven path).
$pyw = $py
try {
Log ("launching: $pyw (hidden)")
    $proc = Start-Process -FilePath $pyw -ArgumentList 'src\main.py' -WorkingDirectory $repo -WindowStyle Hidden -PassThru
    Log ("Start-Process returned: PID {0}" -f $proc.Id)
} catch {
    Log ("Start-Process FAILED: $($_.Exception.Message)")
    throw
}
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
    Log "port is up - opening browser"
    Write-Host "GeoPort is up: http://localhost:$port"
    Start-Process "http://localhost:$port"
} else {
    $alive = (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) -ne $null
    Log ("port NOT up after 60s (python alive? {0})" -f $alive)
    Write-Warning "GeoPort did not come up in 60s - check GeoPort.log in the repo folder."
}
