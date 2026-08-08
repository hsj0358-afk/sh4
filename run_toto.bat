@echo off
REM ===================================================================
REM  축구토토 승무패 분석 리포트 실행 (Windows)
REM
REM  사용법 (이 파일이 있는 폴더에서):
REM    run_toto.bat --demo                네트워크 없이 샘플 리포트
REM    run_toto.bat --skip-whoscored      배당률까지만 (빠름)
REM    run_toto.bat                       전체 수집
REM
REM  .venv 폴더가 있으면 그 안의 파이썬을 쓴다.
REM  (PowerShell 실행 정책 때문에 activate 가 막히는 경우를 피하려고
REM   가상환경을 활성화하지 않고 직접 실행한다.)
REM
REM  시간대: 윈도우 시스템 시각을 그대로 쓴다. 한국에서 쓰신다면
REM  이미 KST 이므로 따로 설정할 것이 없다.
REM ===================================================================
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m toto %*
) else (
    python -m toto %*
)

endlocal
