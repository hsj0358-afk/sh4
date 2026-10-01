@echo off
REM ===================================================================
REM  Soccer toto (Korean sports lottery) analysis report launcher.
REM
REM  Usage, from the folder containing this file:
REM    run_toto.bat --demo                 offline sample report
REM    run_toto.bat --skip-whoscored       odds only (fast)
REM    run_toto.bat --round 260043         specific round
REM    run_toto.bat                        full collection
REM
REM  If a .venv folder exists, its python.exe is used directly. The venv is
REM  deliberately NOT activated: PowerShell execution policy often blocks
REM  Activate.ps1.
REM
REM  Timezone: the Windows system clock is used as-is (already KST in Korea).
REM
REM  NOTE: this file must keep CRLF line endings and stay ASCII-only.
REM  cmd.exe seeks batch files by byte offset; LF-only endings make it
REM  resume mid-command (symptom: "'oto.bat' is not recognized").
REM  .gitattributes pins the line endings.
REM ===================================================================
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m toto %*
) else (
    python -m toto %*
)

endlocal
