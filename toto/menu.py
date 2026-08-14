"""바탕화면 바로가기로 실행할 때 뜨는 대화형 메뉴.

메뉴 문구를 배치 파일이 아니라 파이썬에서 출력하는 이유:
윈도우 cmd 는 콘솔 코드페이지(한국어 윈도우는 cp949)로 배치 파일을 읽어서
한글이 깨지거나 명령이 잘릴 수 있다. 파이썬은 코드페이지와 무관하게
유니코드를 콘솔에 안전하게 쓰므로 여기서 출력하는 편이 확실하다.
"""
from __future__ import annotations

import sys

BANNER = """
╔══════════════════════════════════════════════════════╗
║   ⚽  축구토토 승무패 분석 리포트                     ║
╚══════════════════════════════════════════════════════╝
"""

ITEMS = [
    ("1", "전체 수집 (배당률 + 순위·폼 + 후스코어드 상세)",
     "10~20분 소요. 가장 상세한 리포트.", []),
    ("2", "빠른 수집 (배당률 + 순위·폼)",
     "1~2분. 순위·홈원정 승점·최근 폼까지 나옵니다 "
     "(후스코어드 강점/약점만 생략).", ["--skip-whoscored"]),
    ("3", "회차 지정해서 수집",
     "회차 번호를 직접 입력합니다.", None),          # None = 추가 입력 필요
    ("4", "데모 보기 (네트워크 불필요)",
     "샘플 데이터로 화면만 확인합니다.", ["--demo"]),
    ("5", "캐시 지우고 처음부터 다시 수집",
     "저장된 응답을 삭제하고 전부 새로 받습니다.", "clear-cache"),
    ("6", "후스코어드 수집 실패 진단",
     "저장된 실패 원본을 분석해 원인을 출력합니다.", "diagnose"),
    ("7", "데이터 소스 점검 (FBref · FotMob · Sofascore)",
     "새 소스에 접속해 구조를 확인합니다. 파싱은 하지 않습니다.", "probe"),
    ("8", "저장된 점검 응답 다시 분석",
     "접속하지 않고 [7]이 저장해 둔 응답에서 지표 위치를 찾습니다.",
     "probe-analyze"),
]


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def run_menu() -> int | None:
    """메뉴를 띄우고 선택에 맞는 인자를 만들어 실행한다.

    Returns: 실행 결과 코드. 사용자가 종료를 고르면 None (실행한 게 없음).
    """
    print(BANNER)
    for key, title, desc, _ in ITEMS:
        print(f"  [{key}] {title}")
        print(f"      {desc}")
    print("  [0] 종료")
    print()

    choice = _ask("번호를 고르고 Enter (그냥 Enter 면 1번): ") or "1"
    if choice == "0":
        print("종료합니다.")
        return None

    entry = next((e for e in ITEMS if e[0] == choice), None)
    if entry is None:
        print(f"'{choice}' 는 없는 번호입니다.")
        return 1

    _, title, _, args = entry

    # 캐시를 실제로 지운다. --no-cache 는 읽기만 건너뛰고 낡은 파일은
    # 그대로 남아서, 파서를 고쳐도 옛 결과가 계속 쓰이는 일이 있었다.
    if args == "clear-cache":
        import shutil
        from .cache import CACHE_ROOT
        removed = 0
        if CACHE_ROOT.exists():
            for child in CACHE_ROOT.iterdir():
                if child.name == "browser":     # 봇 통과 쿠키는 남긴다
                    continue
                shutil.rmtree(child, ignore_errors=True) if child.is_dir() \
                    else child.unlink(missing_ok=True)
                removed += 1
        print(f"캐시 {removed}개 항목을 지웠습니다 "
              f"(브라우저 프로필은 유지).")
        rnd = _ask("회차 번호 (비우면 자동 탐지): ")
        args = ["--round", rnd] if rnd else []

    # 진단·점검 도구는 별도 스크립트 (리포트를 만들지 않으므로 따로 표시)
    if args in ("diagnose", "probe", "probe-analyze"):
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        if args == "diagnose":
            from tools.diagnose_whoscored import main as tool_main  # type: ignore
            return ("diagnose", tool_main([]))  # 빈 인자 — sys.argv 의 --menu 무시
        from tools.probe_sources import main as tool_main  # type: ignore
        if args == "probe-analyze":
            return ("diagnose", tool_main(["--analyze"]))
        use_browser = _ask("차단될 때를 대비해 브라우저로 시도할까요? (y/N): ")
        extra = ["--browser"] if use_browser.lower().startswith("y") else []
        return ("diagnose", tool_main(extra))

    if args is None:                       # 회차 직접 입력
        rnd = _ask("회차 번호 (예: 260043): ")
        if not rnd:
            print("회차를 입력하지 않아 취소했습니다.")
            return 1
        args = ["--round", rnd]

    args = list(args) + ["--open"]         # 끝나면 브라우저로 열어준다
    print()
    print(f"▶ {title}")
    print(f"  실행: python -m toto {' '.join(args)}")
    print("-" * 56)

    from .cli import main as cli_main
    return cli_main(args)


def main() -> int:
    try:
        result = run_menu()
    except KeyboardInterrupt:
        print("\n중단했습니다.")
        return 130

    if result is None:                     # 사용자가 종료를 고름
        return 0

    kind, code = result if isinstance(result, tuple) else ("report", result)

    print()
    if code != 0:
        print(f"오류로 끝났습니다 (코드 {code}). 위 로그를 확인하세요.")
    elif kind == "diagnose":
        print("진단을 마쳤습니다. 위 출력을 복사해서 전달하세요.")
    else:
        print("완료했습니다. 리포트는 reports 폴더에 있습니다.")
    return code
