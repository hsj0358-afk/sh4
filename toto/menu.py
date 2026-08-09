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
    ("1", "전체 수집 (배당률 + 후스코어드 상세)",
     "10~20분 소요. 가장 상세한 리포트.", []),
    ("2", "빠른 수집 (배당률·순위 위주)",
     "1~2분. 후스코어드를 건너뜁니다.", ["--skip-whoscored"]),
    ("3", "회차 지정해서 수집",
     "회차 번호를 직접 입력합니다.", None),          # None = 추가 입력 필요
    ("4", "데모 보기 (네트워크 불필요)",
     "샘플 데이터로 화면만 확인합니다.", ["--demo"]),
    ("5", "캐시 비우고 새로 수집",
     "저장된 응답을 무시하고 다시 받습니다.", ["--no-cache"]),
    ("6", "후스코어드 수집 실패 진단",
     "저장된 실패 원본을 분석해 원인을 출력합니다.", "diagnose"),
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

    # 진단 도구는 별도 스크립트 (리포트를 만들지 않으므로 따로 표시)
    if args == "diagnose":
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from tools.diagnose_whoscored import main as diag_main  # type: ignore
        return ("diagnose", diag_main([]))   # 빈 인자 — sys.argv 의 --menu 를 쓰지 않게

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
