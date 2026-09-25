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
$portFile = Join-Path $repo 'GeoPort.port'

# main.py writes GeoPort.port when it has to abandon 54321 (e.g. Windows has
# excluded that port from the ephemeral range on this boot). Re-read it on
# every poll so the watcher finds the UI on the fallback port.
function Get-EffectivePort {
    $p = $port
    if (Test-Path $portFile) {
        $candidate = (Get-Content $portFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($candidate -match '^\d+$' -and [int]$candidate -ge 1 -and [int]$candidate -le 65535) {
            $p = [int]$candidate
        }
    }
    return $p
}

function Test-PortListening($p) {
    return [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}

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

# Already running? Check the default port and the last recorded one.
$up = $false
$upPort = $null
foreach ($p in @($port, (Get-EffectivePort))) {
    if (Test-PortListening $p) { $up = $true; $upPort = $p; break }
}
if ($up) {
    Write-Host "GeoPort is already running on http://localhost:$upPort"
    Start-Process "http://localhost:$upPort"
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
    if (Test-PortListening (Get-EffectivePort)) {
        $ok = $true
        break
    }
}

if ($ok) {
    Log "port is up (main.py opens the browser itself - don't open it again here)"
    Write-Host "GeoPort is up: http://localhost:$(Get-EffectivePort)"
} else {
    $alive = (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) -ne $null
    Log ("port NOT up after 60s (python alive? {0})" -f $alive)
    Write-Warning "GeoPort did not come up in 60s - check GeoPort.log in the repo folder."
    # Surface the failure - everything else in this launcher is hidden.
    try {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "GeoPort did not start within 60 seconds.\n\nSee launcher_trace.log and GeoPort.log in the GeoPort folder for details.",
            "GeoPort launcher", "OK", "Error") | Out-Null
    } catch { }
}
