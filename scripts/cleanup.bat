@echo off
setlocal

REM ============================================================
REM  Cleanup old logs and reports, keep only recent N days.
REM
REM  Usage:
REM    cleanup.bat          keep latest 3 days
REM    cleanup.bat 7        keep latest 7 days
REM
REM  Notes:
REM    - Deletes by last-modified date (older than N days).
REM    - logs\    : deletes *.log (console.log, runner_*.log).
REM    - reports\batch\      : deletes report dirs (timestamp dirs).
REM    - reports\ top-level  : deletes other report dirs (except batch).
REM ============================================================

set "DAYS=3"
if not "%~1"=="" set "DAYS=%~1"

REM Script lives in scripts\ , project root is its parent directory.
set "ROOT=%~dp0.."
set "LOGS=%ROOT%logs"
set "REPORTS=%ROOT%reports"

echo == Cleanup: keep latest %DAYS% days ==

REM 1) Delete *.log files older than N days under logs
if exist "%LOGS%" (
    echo [logs] %LOGS%
    forfiles /p "%LOGS%" /m *.log /d -%DAYS% /c "cmd /c if @isdir==FALSE del /q @path" 2>nul
)

REM 2) Delete report dirs older than N days under reports\batch
if exist "%REPORTS%\batch" (
    echo [reports\batch] %REPORTS%\batch
    forfiles /p "%REPORTS%\batch" /d -%DAYS% /c "cmd /c if @isdir==TRUE rd /s /q @path" 2>nul
)

REM 3) Delete other top-level report dirs (except batch) older than N days
if exist "%REPORTS%" (
    echo [reports] %REPORTS%
    forfiles /p "%REPORTS%" /d -%DAYS% /c "cmd /c if @isdir==TRUE if not @file==batch rd /s /q ""@path""" 2>nul
)

echo == Done ==
endlocal
