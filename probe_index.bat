@echo off
REM ===================================================================
REM  Season match index probe - measures whether the FotMob league feed
REM  carries the whole season (the go/no-go for Strength of Schedule).
REM
REM  Usage, from the folder containing this file:
REM    probe_index.bat                          today's cache, all leagues
REM    probe_index.bat --day 2026-08-29         a specific cache date
REM    probe_index.bat --leagues epl,seriea     only these leagues
REM    probe_index.bat --no-cache               ignore cache, collect fresh
REM
REM  Reads and counts only. It does not write analysis data.
REM
REM  Same venv rule as run_toto.bat: use .venv\Scripts\python.exe directly
REM  when it exists. The venv is deliberately NOT activated, because
REM  PowerShell execution policy often blocks Activate.ps1.
REM
REM  NOTE: this file must keep CRLF line endings and stay ASCII-only.
REM  cmd.exe seeks batch files by byte offset; LF-only endings make it
REM  resume mid-command. .gitattributes pins the line endings.
REM ===================================================================
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" tools\probe_season_index.py %*
) else (
    python tools\probe_season_index.py %*
)

echo.
pause
endlocal
