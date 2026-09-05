"""바탕화면 바로가기로 실행할 때 뜨는 대화형 메뉴.

메뉴 문구를 배치 파일이 아니라 파이썬에서 출력하는 이유:
윈도우 cmd 는 콘솔 코드페이지(한국어 윈도우는 cp949)로 배치 파일을 읽어서
한글이 깨지거나 명령이 잘릴 수 있다. 파이썬은 코드페이지와 무관하게
유니코드를 콘솔에 안전하게 쓰므로 여기서 출력하는 편이 확실하다.

`run_menu()` 는 **메뉴 1회**를 맡고, 반복은 `main()` 이 맡는다. 기능 하나를
쓰려고 프로그램을 다시 켜지 않아도 되게 하려는 것이고, 그래서 예외 격리와
입력 종료 판정도 전부 `main()` 의 루프 한 곳에 모여 있다.
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

BANNER = """
╔══════════════════════════════════════════════════════╗
║   ⚽  축구토토 승무패 분석 리포트                     ║
╚══════════════════════════════════════════════════════╝
"""

# 회차를 먼저 묻는 항목. 수집하는 기능은 **전부** 이 표시를 단다 —
# 실제 사용에서 회차를 지정하지 않고 도는 일이 없기 때문이다(자동 탐지는
# 회차를 비워서 고를 수 있다).
ROUND = "round"

ITEMS = [
    ("1", "회차 지정해서 수집",
     "배당률 + 순위·폼 + 경기 상세까지. 리포트를 만듭니다.",
     (ROUND, [])),
    # [2]·[3] 은 **[1] 에 더하는 것**이다. 먼저 [1] 을 돌릴 필요가 없고,
    # 리포트도 [1] 과 같은 것이 나온다.
    #
    # 예전에는 여기에 `--skip-whoscored` 를 붙였다. 근거가 둘이었는데 둘 다
    # 사라졌다 — (1) "정성 데이터가 한 번도 수집된 적이 없다"(§3-1)는 이제
    # 28/28팀 수집되고, (2) "10~20분을 더 쓴다"는 맞대결을 끄면서(§3-1)
    # 대부분 없어졌다. 게다가 후스코어드의 `shots_pg` 는 축 지표
    # (`season.shots`·`on_target_rate`·`xg_per_shot`)를 거쳐 **패널 자료에
    # 그대로 실린다** — 끄면 패널에게 줄 자료가 오히려 줄었다.
    #
    # 경기 상세(슛맵)가 있어야 근거가 생기고 근거가 없으면 패널을 부르지
    # 않으므로, `--skip-match-details` 는 여전히 붙일 수 없다.
    ("2", "패널 분석까지 (Claude API 필요 · 유료)",
     "[1] 과 같은 수집·리포트에 더해, 두 전문가의 해석과 사회자 종합을 "
     "붙입니다. ANTHROPIC_API_KEY 가 필요하고 경기마다 API 를 부릅니다.",
     (ROUND, ["--panel"])),
    # API 를 부르지 않는다. 같은 자료를 파일로 내서 클로드 채팅에 붙여넣는다.
    ("3", "패널 자료 내보내기 (클로드 채팅용 · API 불필요)",
     "[1] 과 같은 수집·리포트에 더해, 채팅에 넣을 지침과 단계별 시트를 "
     "reports/panel_<회차>/ 에 만듭니다. [1] 을 먼저 돌릴 필요 없습니다.",
     (ROUND, ["--panel-export"])),
    ("4", "폰에서 열기 (같은 와이파이)",
     "이미 만든 리포트를 폰으로 볼 수 있게 주소를 띄웁니다. 클라우드 계정 불필요.",
     ["--serve"]),
    ("9", "개발·진단 도구",
     "데모·캐시 비우기·수집 실패 진단·소스 점검. 평소에는 쓰지 않습니다.",
     "tools"),
]

# 평소 운영에는 쓰지 않지만 **지우지는 않는다.** 후스코어드 진단은 아직
# 남은 조사(§3-1 스타일 0팀)의 유일한 도구이고, 소스 점검은 새 지표를
# 붙일 때 "실물을 먼저 본다"(§1-4)를 지키는 자리다.
TOOLS = [
    ("1", "데모 보기 (네트워크 불필요)",
     "샘플 데이터로 화면만 확인합니다.", ["--demo"]),
    ("2", "캐시 지우고 다시 수집",
     "저장된 응답을 삭제하고 전부 새로 받습니다.", "clear-cache"),
    ("3", "후스코어드 수집 실패 진단",
     "저장된 원본을 분석해 원인을 출력합니다.", "diagnose"),
    ("4", "데이터 소스 점검 (FBref · FotMob · Sofascore)",
     "새 소스에 접속해 구조를 확인합니다. 파싱은 하지 않습니다.", "probe"),
    ("5", "저장된 점검 응답 다시 분석",
     "접속하지 않고 [4]가 저장해 둔 응답에서 지표 위치를 찾습니다.",
     "probe-analyze"),
]


def _ask(prompt: str) -> str | None:
    """한 줄 입력. **입력이 끝났으면(EOF) `None`** 을 돌려준다.

    빈 문자열과 `None` 을 나눠야 하는 이유는 메뉴가 루프가 됐기 때문이다.
    "그냥 Enter"(빈 문자열 → 기본 동작)와 "더 받을 입력이 없다"(파이프 종료·
    리다이렉트)를 같은 값으로 두면 후자가 기본 동작을 **무한히 반복**한다 —
    실측하면 `_ask()` 가 `''` 를 주고 호출부의 `or "1"` 이 1번 메뉴(전체
    수집)를 골라 버린다.

    `KeyboardInterrupt` 는 **잡지 않는다.** `main()` 에 '중단' 으로 끝내는
    정책이 이미 있는데 여기서 삼키면 그 정책에 닿지 못하고, Ctrl+C 가
    오히려 1번 메뉴를 실행시킨다.
    """
    try:
        return input(prompt).strip()
    except EOFError:
        print()
        return None


def _pause() -> bool:
    """결과를 읽을 시간을 준다. 입력이 끝났으면 False (루프를 끝낸다)."""
    print()
    return _ask("[Enter] 를 누르면 메뉴로 돌아갑니다: ") is not None


# 하위 메뉴에서 `[0]` 을 골랐을 때. `None`(종료)과 구분해야 한다.
BACK = object()


def _choose(items, prompt: str, default: str):
    """목록을 보여 주고 고른 항목을 돌려준다.

    돌려주는 값 셋을 구분한다 — `None` 은 종료(입력 끝 또는 `[0]`),
    `BACK` 은 하위 메뉴에서 뒤로, `()` 는 없는 번호다. 하나로 뭉뚱그리면
    하위 메뉴의 `[0]` 이 프로그램을 끝내 버린다.
    """
    for key, title, desc, _ in items:
        print(f"  [{key}] {title}")
        print(f"      {desc}")
    print("  [0] 뒤로" if items is TOOLS else "  [0] 종료")
    print()

    choice = _ask(prompt)
    if choice is None:                     # 입력이 끝났다 — 루프를 돌지 않는다
        print("입력이 끝나 종료합니다.")
        return None
    choice = choice or default
    if choice == "0":
        if items is TOOLS:
            return BACK
        print("종료합니다.")
        return None
    entry = next((e for e in items if e[0] == choice), None)
    if entry is None:
        print(f"'{choice}' 는 없는 번호입니다.")
        return ()
    return entry


def run_menu() -> int | None:
    """메뉴를 **한 번** 띄우고 선택에 맞는 인자를 만들어 실행한다.

    반복은 `main()` 이 맡는다 — 여기에 루프를 두면 종료 판정과 예외 격리가
    두 곳으로 흩어진다.

    Returns: 실행 결과 코드. 종료를 고르거나 입력이 끝나면 None.
    """
    print(BANNER)
    entry = _choose(ITEMS, "번호를 고르고 Enter (그냥 Enter 면 1번): ", "1")
    if entry is None:
        return None
    if entry == ():                        # 없는 번호
        return 1

    _, title, _, args = entry

    # 개발·진단 도구는 하위 메뉴로 내렸다. 평소 운영에 쓰지 않지만
    # 지우지는 않는다 — §3-1 조사와 §1-4 실물 확인의 도구다.
    if args == "tools":
        print()
        print("  — 개발·진단 도구 —")
        entry = _choose(TOOLS, "번호를 고르고 Enter (0 이면 뒤로): ", "0")
        if entry is None:
            return None
        if entry == ():
            return 1
        if entry is BACK:
            return ("back", 0)
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
        if rnd is None:                    # 캐시는 지웠지만 수집까지 가지 않는다
            print("입력이 끝나 수집은 하지 않았습니다.")
            return 1
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
        extra = ["--browser"] if (use_browser or "").lower().startswith("y") else []
        return ("diagnose", tool_main(extra))

    # 수집하는 항목은 **회차를 먼저 묻는다.** 실제 사용에서 회차를 지정하지
    # 않고 도는 일이 없다. 비워 두면 예전 [1] 처럼 판매중 회차를 탐지한다.
    if isinstance(args, tuple) and args and args[0] == ROUND:
        extra = list(args[1])
        rnd = _ask("회차 번호 (예: 260050 · 비우면 자동 탐지): ")
        if rnd is None:
            print("입력이 끝나 실행하지 않았습니다.")
            return 1
        args = (["--round", rnd] if rnd else []) + extra

    if "--serve" in args:                  # 공유만 하는 항목 (리포트를 만들지 않음)
        from .cli import main as cli_main
        return ("serve", cli_main(list(args)))

    args = list(args) + ["--open"]         # 끝나면 브라우저로 열어준다
    print()
    print(f"▶ {title}")
    print(f"  실행: python -m toto {' '.join(args)}")
    print("-" * 56)

    from .cli import main as cli_main
    return cli_main(args)


def _report(result) -> int:
    """한 번의 실행 결과를 사람이 읽을 문장으로 알린다."""
    kind, code = result if isinstance(result, tuple) else ("report", result)

    print()
    if code != 0:
        print(f"오류로 끝났습니다 (코드 {code}). 위 로그를 확인하세요.")
    elif kind == "back":
        print("메뉴로 돌아갑니다.")
    elif kind == "diagnose":
        print("진단을 마쳤습니다. 위 출력을 복사해서 전달하세요.")
    elif kind == "serve":
        print("공유를 마쳤습니다.")
    else:
        print("완료했습니다. 리포트는 reports 폴더에 있습니다.")
    return code


def main() -> int:
    """메뉴를 반복해서 띄운다. `[0]` 이나 입력 종료로만 빠져나간다.

    예외 격리를 **이 루프 한 곳**에 둔다. 기능 하나가 터졌다고 프로그램이
    죽으면 사용자가 다시 켜야 하는데, 메뉴를 루프로 만든 이유가 바로 그것을
    없애는 것이기 때문이다. 다만 `KeyboardInterrupt` 는 잡지 않는다 —
    Ctrl+C 로 멈추라는 뜻인데 삼키면 루프가 계속 돈다.

    돌려주는 값은 **마지막으로 실행한 기능의 코드**다. 한 번 쓰고 종료하면
    루프가 없던 때와 같은 값이 나온다.
    """
    last = 0
    while True:
        try:
            result = run_menu()
        except KeyboardInterrupt:
            print("\n중단했습니다.")
            return 130
        except Exception as exc:
            # 사용자에게는 한 줄, 로그에는 traceback (-v 로 볼 수 있다)
            log.exception("메뉴 실행 중 오류")
            print(f"\n오류가 발생했습니다: {exc}")
            print("다른 메뉴는 계속 사용할 수 있습니다.")
            last = 1
        else:
            if result is None:             # [0] 또는 입력 종료
                return last
            last = _report(result)

        if not _pause():                   # 입력이 끝났으면 루프를 끝낸다
            return last
