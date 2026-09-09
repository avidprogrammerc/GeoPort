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
set TRACE=%~dp0launcher_trace.log
call :log "BAT start (from: %0)"

rem --- Already running? Just open the UI. ---
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 54321 -State Listen -ErrorAction SilentlyContinue) { Start-Process 'http://localhost:54321'; exit 1 }"
if %errorlevel%==1 ( call :log "already running - opened browser" & exit /b )
call :log "port 54321 free"

rem --- Elevate this batch once, then run the launcher hidden. ---
net session >nul 2>&1
if %errorlevel%==0 goto :run
call :log "not elevated - requesting UAC (Start-Process -Verb RunAs)"
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WindowStyle Hidden"
call :log "elevation call returned (user answered UAC)"
exit /b

:run
call :log "ELEVATED branch - running start.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
call :log "start.ps1 finished (errorlevel=%errorlevel%)"
exit /b

:log
echo [%date% %time%] %~1 >> "%TRACE%"
exit /b
