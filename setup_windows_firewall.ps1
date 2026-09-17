# setup_windows_firewall.ps1 — GeoPort Wi-Fi / Windows Firewall fix
#
# Per the GeoPort FAQ (FAQ.md, "Windows Specific"): the firewall must allow
# GeoPort on BOTH Private and Public networks. When running from source the
# rules covering geoport-windows-v4.0.2.exe do not apply to python.exe, and
# the WinTun tunnel adapter prompt may have been answered for one profile
# only.
#
# This script (must run ELEVATED — right-click > Run as administrator):
#   1. Adds inbound-allow rules for every existing pymobiledevice3 WinTun
#      tunnel adapter (the "network adapter" prompt from FAQ figure 3).
#   2. Adds an inbound-allow rule for the venv python.exe that runs GeoPort.
#   3. Widens the existing Public-only rules for geoport-windows-v4.0.2.exe
#      to all profiles (FAQ option 1: "Allow both Public and Private").
#
# Idempotent: safe to re-run; existing rules are left as-is.

$ErrorActionPreference = 'Stop'
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$report = @()

# --- 1. WinTun tunnel adapter(s) -------------------------------------------
$adapters = Get-NetAdapter | Where-Object { $_.Name -like 'pymobiledevice3-tunnel-*' }
if (-not $adapters) {
    $report += 'note: no pymobiledevice3-tunnel-* adapters present yet (rules are added when one exists)'
}
foreach ($a in $adapters) {
    $name = "GeoPort tunnel adapter inbound ($($a.Name))"
    if (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue) {
        $report += "exists : $name"
    }
    else {
        New-NetFirewallRule -DisplayName $name `
            -Description 'GeoPort FAQ: inbound allow on pymobiledevice3 WinTun tunnel adapter, all profiles' `
            -Direction Inbound -Action Allow -Profile Any -InterfaceAlias $a.Name | Out-Null
        $report += "created: $name"
    }
}

# --- 2. venv python.exe -----------------------------------------------------
if (Test-Path $venvPython) {
    $name = 'GeoPort python (venv) inbound'
    if (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue) {
        $report += "exists : $name"
    }
    else {
        New-NetFirewallRule -DisplayName $name `
            -Description 'GeoPort FAQ: inbound allow for python.exe running GeoPort from source, all profiles' `
            -Direction Inbound -Action Allow -Profile Any -Program $venvPython | Out-Null
        $report += "created: $name"
    }
}
else {
    $report += "skipped: venv python not found at $venvPython"
}

# --- 3. Widen existing installed-exe rules (Public only) -> all profiles ---
Get-NetFirewallRule -DisplayName 'geoport-windows-v4.0.2.exe' -ErrorAction SilentlyContinue |
    ForEach-Object {
        if ($_.Profile -ne 'Any') {
            Set-NetFirewallRule -Name $_.Name -Profile Any | Out-Null
            $report += "widened profile -> Any: $($_.Name)"
        }
    }

# --- Verify -----------------------------------------------------------------
Write-Host '=== Report ==='
$report | ForEach-Object { Write-Host $_ }
Write-Host ''
Write-Host '=== GeoPort firewall rules now ==='
Get-NetFirewallRule -DisplayName 'GeoPort*' |
    Select-Object DisplayName, Direction, Action, Enabled, Profile, InterfaceAlias, Program |
    Format-Table -AutoSize | Out-String -Width 250
Read-Host 'Press Enter to close'
