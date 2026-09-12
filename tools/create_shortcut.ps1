# 바탕화면에 "축구토토 분석" 바로가기를 만든다.
#
# create_shortcut.bat 을 더블클릭하면 이 스크립트가 실행된다.
# (배치 파일이 -ExecutionPolicy Bypass 로 호출하므로 실행 정책에 막히지 않는다)
#
# 여러 번 실행해도 안전하다 - 같은 이름의 바로가기를 덮어쓴다.
#
# [중요] 이 파일은 반드시 "BOM 있는 UTF-8" 로 저장해야 한다.
# Windows PowerShell 5.1 은 BOM 이 없으면 .ps1 을 ANSI(한국어 윈도우는
# cp949)로 읽어서 한글 문자열이 깨진다. 깨진 이름에는 '?' 가 섞이는데
# 이는 파일명에 쓸 수 없는 문자라 저장이 실패한다.
# .gitattributes 가 *.ps1 을 CRLF 로 고정하고, BOM 은 내용 바이트로 보존된다.

$ErrorActionPreference = 'Stop'

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

$desktop = [Environment]::GetFolderPath('Desktop')
if (-not (Test-Path $desktop)) {
    Write-Host "[실패] 바탕화면 폴더를 찾을 수 없습니다: $desktop"
    exit 1
}

function New-TotoShortcut([string]$name) {
    $path  = Join-Path $desktop ($name + '.lnk')
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($path)
    $sc.TargetPath       = $target
    $sc.WorkingDirectory = $repo
    $sc.Description      = 'Soccer toto win/draw/loss analysis report'
    $sc.WindowStyle      = 1
    if (Test-Path $icon) { $sc.IconLocation = "$icon,0" }
    $sc.Save()
    return $path
}

# 한글 이름으로 먼저 시도하고, 인코딩 문제가 남아 있으면 영문으로 대체한다.
$linkPath = $null
try {
    $linkPath = New-TotoShortcut '축구토토 분석'
} catch {
    Write-Host "[안내] 한글 이름으로 만들지 못해 영문 이름으로 대체합니다."
    Write-Host "       ($_)"
    try {
        $linkPath = New-TotoShortcut 'Soccer Toto Analysis'
    } catch {
        Write-Host "[실패] 바로가기를 만들지 못했습니다: $_"
        exit 1
    }
}

Write-Host ''
Write-Host '[완료] 바탕화면에 바로가기를 만들었습니다.'
Write-Host ''
Write-Host "  위치   : $linkPath"
Write-Host "  실행   : $target"
if (Test-Path $icon) { Write-Host "  아이콘 : $icon" }
Write-Host ''
Write-Host '이제 바탕화면 아이콘을 더블클릭하면 메뉴가 뜹니다.'
