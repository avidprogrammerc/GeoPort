@echo off
rem ============================================================
rem  GeoPort - one-click launcher.  Just double-click.
rem
rem  * If GeoPort is already running: reopens the browser, done
rem    (no UAC, no waiting).
rem  * Otherwise: one UAC prompt (the app needs Administrator
rem    for iOS 17+ USB tunnels), then starts with no console
rem    window - a map-pin tray icon appears and your browser
rem    opens when the app is ready.
rem ============================================================
setlocal

rem --- Already running? Just open the UI. ---
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 54321 -State Listen -ErrorAction SilentlyContinue) { Start-Process 'http://localhost:54321'; exit 1 }"
if %errorlevel%==1 exit /b

rem --- Elevate this batch once, then run the launcher hidden. ---
net session >nul 2>&1
if %errorlevel%==0 goto :run
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WindowStyle Hidden"
exit /b

:run
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
