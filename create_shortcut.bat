@echo off
REM ===================================================================
REM  Creates a desktop shortcut for the soccer toto analysis tool.
REM  Run once (double-click). Safe to re-run - it overwrites.
REM
REM  Uses PowerShell for the shortcut COM call, with -ExecutionPolicy
REM  Bypass so the default restricted policy does not block it.
REM  ASCII-only, CRLF.
REM ===================================================================
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\create_shortcut.ps1"

echo.
pause
endlocal
