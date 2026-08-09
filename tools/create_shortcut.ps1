# 바탕화면에 "축구토토 분석" 바로가기를 만든다.
#
# create_shortcut.bat 을 더블클릭하면 이 스크립트가 실행된다.
# (배치 파일이 -ExecutionPolicy Bypass 로 호출하므로 실행 정책에 막히지 않는다)
#
# 여러 번 실행해도 안전하다 — 같은 이름의 바로가기를 덮어쓴다.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$repo   = Split-Path -Parent $PSScriptRoot
$target = Join-Path $repo 'toto_menu.bat'
$icon   = Join-Path $repo 'assets\toto.ico'

if (-not (Test-Path $target)) {
    Write-Host "[실패] 실행 파일을 찾을 수 없습니다: $target"
    Write-Host "       저장소 폴더 안에서 create_shortcut.bat 을 실행했는지 확인하세요."
    exit 1
}

# 아이콘이 없으면 만들어 본다 (표준 라이브러리만 사용)
if (-not (Test-Path $icon)) {
    $py = Join-Path $repo '.venv\Scripts\python.exe'
    if (-not (Test-Path $py)) { $py = 'python' }
    try {
        & $py (Join-Path $repo 'tools\make_icon.py') | Out-Null
    } catch {
        Write-Host "[안내] 아이콘 생성을 건너뜁니다: $_"
    }
}

$desktop  = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktop '축구토토 분석.lnk'

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($linkPath)
$sc.TargetPath       = $target
$sc.WorkingDirectory = $repo
$sc.Description      = '축구토토 승무패 14경기 분석 리포트 생성'
$sc.WindowStyle      = 1
if (Test-Path $icon) { $sc.IconLocation = "$icon,0" }
$sc.Save()

Write-Host ''
Write-Host '[완료] 바탕화면에 바로가기를 만들었습니다.'
Write-Host ''
Write-Host "  이름   : 축구토토 분석"
Write-Host "  위치   : $linkPath"
Write-Host "  실행   : $target"
if (Test-Path $icon) { Write-Host "  아이콘 : $icon" }
Write-Host ''
Write-Host '이제 바탕화면 아이콘을 더블클릭하면 메뉴가 뜹니다.'
