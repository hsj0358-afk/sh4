@echo off
REM ===================================================================
REM  Soccer toto analysis - interactive launcher (desktop shortcut target)
REM
REM  The menu text itself is printed by Python, not by this file:
REM  cmd.exe reads batch files using the console code page (cp949 on
REM  Korean Windows), so non-ASCII here risks mojibake or truncated
REM  commands. Python writes Unicode to the console safely.
REM
REM  Must stay ASCII-only with CRLF line endings (.gitattributes pins it).
REM ===================================================================
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m toto --menu
) else (
    python -m toto --menu
)

echo.
pause
endlocal
