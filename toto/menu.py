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

# 메뉴 번호는 **사용자가 일하는 순서**다 (Phase 6-F-6 §42). 기능이 추가된
# 순서가 아니다. 실제 흐름은 셋뿐이다.
#
#     ① 회차 분석  →  ② 패널 자동 분석  →  ③ 최종 리포트
#
# 그래서 그 셋을 앞에 두고, 단계별 수동 진행·복구는 `[4]` 하위로, 개발용은
# `[9]` 하위로 내렸다. **CLI 인자는 하나도 바뀌지 않는다** (§32) — 메뉴는
# 예전과 똑같이 기존 인자를 만들어 같은 경로를 태울 뿐이다.
ITEMS = [
    ("1", "회차 분석",
     "회차 데이터 수집 · 정량·정성 분석 · 기본 리포트 생성.",
     (ROUND, [])),
    # Phase 6-F-6 의 핵심 진입점. **Claude Code(claude -p)로 돌고 Anthropic
    # API 를 직접 부르지 않는다** — 레거시 `--panel` 과 다른 경로다.
    ("2", "패널 자동 분석",
     "A 데이터 분석가 · B 맞대결·전술 분석가 · C 사회자를 자동으로 돌리고 "
     "리포트 반영까지 한 번에 합니다. Claude 구독으로 실행하며 복사·"
     "붙여넣기가 필요 없습니다.",
     "panel-auto"),
    ("3", "최종 리포트 다시 만들기",
     "저장된 회차 분석으로 HTML 만 다시 그립니다. 수집하지 않습니다.",
     "rerender"),
    ("4", "패널 수동 진행·복구",
     "클로드 채팅으로 직접 돌리거나, 자동 분석이 멈춘 지점을 손으로 "
     "이어서 처리합니다.",
     "panel-manual"),
    ("5", "폰에서 열기 (같은 와이파이)",
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
    # [6] 은 개발 도구가 아니라 **운영 단계**다 (경기가 끝난 뒤 결과를
    # 붙인다). 다만 Phase 6-C-2 는 CLI 를 먼저 안정화하는 단계라 메뉴 번호
    # 체계를 건드리지 않고 여기에 둔다 — 운영 메뉴로 올릴지는 실제로 몇
    # 회차 돌려 본 뒤에 정한다.
    ("6", "회차 결과 정산 (경기 종료 후)",
     "이미 기록된 회차에 실제 경기 결과만 채웁니다. 배당·확률·기록 시각은 "
     "그대로 두고 리포트도 다시 만들지 않습니다.", "settle"),
    # 레거시 API 패널 (Phase 3-B). **지우지 않고 격리한다** (6-F-6 §33) —
    # 동작도 `--panel` 인자도 그대로이고, 정상 workflow 에서 실수로 고르지
    # 않도록 개발 도구 아래로 내렸을 뿐이다. 평소에는 `[2] 패널 자동 분석`
    # 을 쓴다 (구독 인증 · API 과금 없음).
    ("7", "레거시 API 패널 실행 (Anthropic API 키 필요 · 유료)",
     "예전 방식입니다. ANTHROPIC_API_KEY 로 경기마다 API 를 부르고 별도 "
     "과금이 발생합니다. 보통은 [2] 패널 자동 분석을 쓰십시오.",
     (ROUND, ["--panel"])),
    # 준비 점검 (6-F-7 후속). 실물 윈도우에서 `[2]` 가 preflight 에서
    # 멈췄는데, 그때까지 "준비됐나" 를 묻는 방법이 실제 호출을 시작해 보는
    # 것뿐이었다. 이것은 **비용 0** 이다.
    ("8", "패널 자동 분석 준비 점검 (비용 0)",
     "claude 실행 파일·로그인·저장본·모델을 확인하고 멈춥니다. "
     "모델을 부르지 않습니다.", (ROUND, ["--panel-auto-check"])),
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


def _pick_panel_file():
    """`panel_results/` 에서 쓸 파일을 고른다. (경로, 회차) 또는 None.

    **임의로 하나를 고르지 않는다.** 여러 개면 사용자가 고르고, 회차를 알 수
    없으면 물어본다 — 엉뚱한 회차에 붙이는 것이 안 붙이는 것보다 나쁘다.
    """
    from . import panelimport

    folder = panelimport.inbox_dir()
    files = panelimport.find_panel_files()
    if not files:
        print()
        print(f"  {folder} 에 패널 결과 파일이 없습니다.")
        print("  클로드 채팅 3단계에서 만든 "
              f"<회차>{panelimport.FILE_SUFFIX} 을 그 폴더에 넣어 주세요.")
        print(f"  예: {folder / ('260052' + panelimport.FILE_SUFFIX)}")
        return None

    rounds = [panelimport.round_of(p) for p in files]
    if len(files) == 1:
        path, rnd = files[0], rounds[0]
        print(f"\n  파일: {path.name}"
              + (f" (회차 {rnd})" if rnd else " — 회차를 읽지 못했습니다"))
    else:
        print("\n  패널 결과 파일이 여러 개입니다. 하나를 고르세요.")
        for i, (p, r) in enumerate(zip(files, rounds), start=1):
            print(f"  [{i}] {p.name}" + (f"  (회차 {r})" if r else ""))
        answer = _ask(f"번호를 고르고 Enter (1~{len(files)}): ")
        if answer is None:
            print("입력이 끝나 실행하지 않았습니다.")
            return None
        if not answer.isdigit() or not 1 <= int(answer) <= len(files):
            print(f"'{answer}' 는 없는 번호입니다.")
            return None
        path, rnd = files[int(answer) - 1], rounds[int(answer) - 1]

    if not rnd:
        # 파일에서 회차를 못 읽었다. 지어내지 않고 물어본다 (§1-5).
        rnd = _ask("회차 번호를 입력하세요 (예: 260052): ")
        if rnd is None or not rnd:
            print("회차를 알 수 없어 실행하지 않았습니다.")
            return None
    return path, rnd


PASTE_END = "END"


def _read_paste(what: str = "3단계 Moderator 결과(JSON 배열)") -> str | None:
    """여러 줄 붙여넣기를 읽는다. 끝은 `END` 한 줄 (Phase 4-F).

    `what` 은 안내 문구만 바꾼다 — 6-F-3 이 1·2단계 응답도 같은 방식으로
    받으면서 루프를 한 곳에 모았다. 기본값이 4-F 의 문구 그대로라 `[4]` 의
    화면은 바뀌지 않는다.

    **한 줄 입력으로 받지 않는다** — 3단계 결과는 14경기가 들어간 긴 JSON
    배열이고, 윈도우 콘솔은 붙여넣기를 줄 단위로 흘려보낸다.

    `EOF`(Ctrl+Z/Ctrl+D)도 끝으로 본다. `KeyboardInterrupt` 는 **잡지
    않는다** — 메뉴 루프의 "중단했습니다 → 130" 정책에 그대로 올라가야
    한다 (§1-7-1).
    """
    print(f"\n  {what}를 통째로 붙여넣으세요.")
    print(f"  다 붙여넣은 뒤 마지막 줄에 {PASTE_END} 만 입력하고 Enter.")
    print("  (취소하려면 그냥 Enter 로 끝내세요)\n")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == PASTE_END:
            break
        lines.append(line)
    text = "\n".join(lines).strip()
    if not text:
        print("붙여넣은 내용이 없어 실행하지 않았습니다.")
        return None
    return text


def _paste_panel() -> list[str] | None:
    """`[4] → [1]` 3단계 결과 붙여넣기. CLI 인자를 만들어 돌려준다.

    **검증·감사를 여기서 다시 구현하지 않는다** — 원문을 임시 파일로 넘기고
    `--paste-panel-result` 가 같은 경로를 태운다 (§1-20 과 같은 이유).
    """
    import tempfile
    from pathlib import Path

    rnd = _ask("회차 번호를 입력하세요 (예: 260052): ")
    if rnd is None or not rnd.strip():
        print("회차를 알 수 없어 실행하지 않았습니다.")
        return None
    rnd = rnd.strip()
    text = _read_paste()
    if text is None:
        return None
    tmp = Path(tempfile.mkdtemp(prefix="toto_paste_")) / f"{rnd}_moderator.json"
    tmp.write_text(text, encoding="utf-8")
    print(f"\n  {len(text):,}자를 읽었습니다. 검증합니다…")
    return ["--round", rnd, "--paste-panel-result", str(tmp)]


# `[4]` 안에서 고르는 두 입력 경로. **기존 파일 경로를 없애지 않는다.**
PANEL_INPUTS = [
    ("1", "3단계 Moderator 결과 붙여넣기",
     "클로드 채팅 3단계 응답을 그대로 붙여넣습니다. JSON 파일을 따로 만들 "
     "필요가 없습니다."),
    ("2", "Panel Result JSON 파일 가져오기",
     "panel_results/ 에 넣어 둔 <회차>_panel_result.json 을 씁니다."),
]


# `[6]` 안에서 고르는 세 가지. **클로드를 부르는 항목이 하나도 없다** —
# 분석은 사람이 채팅에서 하고 여기서는 그 결과를 넣고 조립할 뿐이다.
PANEL_WORK = [
    ("1", "1단계(데이터 분석가) 결과 넣기",
     "클로드 대화 #1 의 JSON 배열을 붙여넣습니다. 검증을 통과하면 "
     "panel_work/ 에 보관합니다."),
    ("2", "2단계(맞대결·전술 분석가) 결과 넣기",
     "클로드 대화 #2 의 JSON 배열을 붙여넣습니다. 1단계와 **따로** "
     "보관하고, 여기서 1단계 결과를 읽지 않습니다."),
    ("3", "사회자 자료 만들기 (1·2단계 조립)",
     "보관해 둔 두 결과를 경기 번호로 짝지어 03_사회자자료_완성.md 를 "
     "만듭니다. `◀ … ▶` 붙여넣기가 필요 없어집니다."),
    # Phase 6-F-4. 3단계 결과도 같은 자리에 보관하고, 그 보관본을 **기존
    # [4] 경로**에 그대로 태운다 — 새 결과 포맷을 만들지 않는다.
    ("4", "3단계(Moderator) 결과 넣기",
     "클로드 대화 #3 의 JSON 배열을 붙여넣습니다. 검증을 통과하면 "
     "panel_work/ 에 보관합니다. 아직 리포트에 반영하지는 않습니다."),
    ("5", "리포트에 반영 (보관해 둔 3단계 결과)",
     "[4] 로 넣어 둔 결과를 검증·가져오기·감사·리포트 갱신까지 합니다 — "
     "메뉴 [4] 와 같은 경로입니다."),
    ("6", "진행 상태 보기",
     "이 회차가 어디까지 왔는지, 다음에 무엇을 할지, 어느 파일을 첨부할지 "
     "보여 줍니다. 아무것도 고치지 않습니다."),
]


def _confirm_overwrite(path, what: str) -> bool:
    """이미 있는 보관본을 갈아 끼울지 묻는다 (Phase 6-F-4 §13).

    **기본은 아니오**다. 실수로 Enter 를 눌러 앞서 받아 둔 결과를 잃는 것이
    다시 한 번 붙여넣는 것보다 나쁘다.

    묻는 자리가 메뉴인 이유는 CLI 가 비대화형이기 때문이다 — CLI 의 동작은
    6-F-3 그대로 두고(회귀), 사람이 실제로 앉아 있는 자리에서만 묻는다.
    """
    if not path.is_file():
        return True
    print(f"\n  기존 {what} 결과가 존재합니다. ({path})")
    answer = _ask("  새 결과로 교체하시겠습니까? [y/N]: ")
    if (answer or "").strip().lower() in {"y", "yes"}:
        return True
    print("  그대로 두었습니다. 실행하지 않았습니다.")
    return False


def _panel_work_args() -> list[str] | None:
    """단계별 항목 하나를 골라 CLI 인자를 만든다.

    **검증·조립을 여기서 다시 구현하지 않는다** — CLI 와 같은 경로를 태운다
    (§1-20 의 `[4]` 와 같은 이유). 두 곳에서 다른 결과가 나오면 어느 쪽도
    믿을 수 없다.
    """
    print("\n  무엇을 할까요?")
    for key, title, why in PANEL_WORK:
        print(f"  [{key}] {title}")
        print(f"      {why}")
    print("  [0] 뒤로")
    answer = (_ask("번호를 고르고 Enter (0 이면 뒤로): ") or "0").strip()
    if answer == "0":
        return None
    if answer not in {k for k, _t, _w in PANEL_WORK}:
        print(f"'{answer}' 는 없는 번호입니다.")
        return None
    return _panel_work_for(answer)


def _panel_work_for(answer: str) -> list[str] | None:
    """고른 번호 → CLI 인자. 메뉴를 다시 그리지 않는다.

    6-F-6 이 이것을 떼어냈다 — 새 `[4] 패널 수동 진행·복구` 가 자기 번호로
    같은 기능을 부르는데, 안에서 하위 메뉴를 또 그리면 두 번 묻게 된다.
    **동작은 그대로다.**
    """
    import tempfile
    from pathlib import Path
    from . import panel, panelwork

    rnd = _ask("회차 번호를 입력하세요 (예: 260054): ")
    if rnd is None or not rnd.strip():
        print("회차를 알 수 없어 실행하지 않았습니다.")
        return None
    rnd = rnd.strip()

    if answer == "3":
        return ["--round", rnd, "--build-moderator-input"]
    if answer == "6":
        return ["--round", rnd, "--panel-workflow-status"]

    if answer == "5":
        # **1·2·3단계 보관본을 함께 반영한다** (6-F-14) — 자동 경로와 같은
        # 인자다. 예전에는 3단계 보관본만 `--paste-panel-result` 에 넘겨
        # 1·2단계 원문이 최종 결과에서 빠졌다 (6-F-13). 검증은 CLI 가 한다.
        saved = panelwork.moderator_result_path(rnd)
        if not saved.is_file():
            print(f"\n  보관된 3단계 결과가 없습니다. ({saved})")
            print("  먼저 [4] 로 3단계 결과를 넣으십시오.")
            return None
        print(f"\n  1·2·3단계 보관본을 함께 반영합니다: {saved.parent}")
        return ["--round", rnd, "--apply-panel-work"]

    if answer == "4":
        if not _confirm_overwrite(panelwork.moderator_result_path(rnd),
                                  "3단계 Moderator"):
            return None
        text = _read_paste()
        if text is None:
            return None
        tmp = (Path(tempfile.mkdtemp(prefix="toto_stage_"))
               / f"{rnd}_{panelwork.MODERATOR_RESULT_FILE}")
        tmp.write_text(text, encoding="utf-8")
        print(f"\n  {len(text):,}자를 읽었습니다. 검증합니다…")
        return ["--round", rnd, "--save-moderator-result", str(tmp)]

    role = panel.DATA_ANALYST if answer == "1" else panel.MATCHUP_ANALYST
    if not _confirm_overwrite(panelwork.path_for(rnd, role),
                              panel.ROLE_KO[role]):
        return None
    text = _read_paste(f"{panel.ROLE_KO[role]} 응답(JSON 배열)")
    if text is None:
        return None
    tmp = (Path(tempfile.mkdtemp(prefix="toto_stage_"))
           / f"{rnd}_{panelwork.ROLE_FILES[role]}")
    tmp.write_text(text, encoding="utf-8")
    print(f"\n  {len(text):,}자를 읽었습니다. 검증합니다…")
    return ["--round", rnd, "--save-panel-opinion", str(tmp),
            "--role", role]


# `[4] 패널 수동 진행·복구` 의 하위 항목. 예전 `[3]`(자료 내보내기)·
# `[4]`(결과 반영)·`[6]`(단계별 진행)을 **한자리에 모은 것**이고, 부르는
# 것은 전부 기존 함수다 — 새 경로를 만들지 않았다 (6-F-6 §35).
PANEL_MANUAL = [
    ("1", "채팅용 자료 내보내기",
     "클로드 채팅에 넣을 지침과 단계별 시트를 reports/panel_<회차>/ 에 "
     "만듭니다."),
    ("2", "1단계(데이터 분석가) 결과 넣기", "채팅 응답 배열을 보관합니다."),
    ("3", "2단계(맞대결·전술 분석가) 결과 넣기",
     "1단계와 **따로** 보관합니다."),
    ("4", "사회자 자료 만들기 (1·2단계 조립)",
     "보관본을 경기 번호로 짝지어 03_사회자자료_완성.md 를 만듭니다."),
    ("5", "3단계(Moderator) 결과 넣기", "채팅 3단계 응답을 보관합니다."),
    ("6", "리포트에 반영 (보관해 둔 3단계 결과)",
     "검증·가져오기·감사·리포트 갱신까지 합니다."),
    ("7", "Panel Result JSON 파일 가져오기",
     "panel_results/ 에 넣어 둔 <회차>_panel_result.json 을 씁니다."),
    ("8", "진행 상태 보기",
     "이 회차가 어디까지 왔는지와 다음에 할 일을 보여 줍니다."),
]

# 수동 메뉴 번호 → 기존 `_panel_work_for()` 의 번호. 기능을 옮긴 것이지
# 새로 만든 것이 아니라는 사실이 이 표에 그대로 드러난다.
_MANUAL_TO_WORK = {"2": "1", "3": "2", "4": "3", "5": "4", "6": "5", "8": "6"}


def _panel_manual_args() -> list[str] | None:
    """`[4]` 하위에서 하나를 골라 CLI 인자를 만든다."""
    print("\n  — 패널 수동 진행·복구 —")
    for key, title, why in PANEL_MANUAL:
        print(f"  [{key}] {title}")
        print(f"      {why}")
    print("  [0] 뒤로")
    answer = (_ask("번호를 고르고 Enter (0 이면 뒤로): ") or "0").strip()
    if answer == "0":
        return None

    if answer == "1":                       # 예전 [3]
        rnd = _ask("회차 번호 (예: 260050 · 비우면 자동 탐지): ")
        if rnd is None:
            print("입력이 끝나 실행하지 않았습니다.")
            return None
        return (["--round", rnd] if rnd else []) + ["--panel-export"]

    if answer == "7":                       # 예전 [4] → [2] 파일 경로
        picked = _pick_panel_file()
        if picked is None:
            return None
        path, rnd = picked
        return ["--round", rnd,
                "--import-panel-result", str(path),
                "--audit-panel-result", str(path)]

    work = _MANUAL_TO_WORK.get(answer)
    if work is None:
        print(f"'{answer}' 는 없는 번호입니다.")
        return None
    return _panel_work_for(work)


def _panel_auto_args() -> list[str] | None:
    """`[2] 패널 자동 분석`. **회차를 비워 둘 수 없다.**

    저장된 회차 분석을 읽어 돌리므로 자동 탐지가 없다 — 어느 회차를
    분석할지 지어낼 수 없다 (§1-5).
    """
    rnd = _ask("회차 번호를 입력하세요 (예: 260054): ")
    if rnd is None or not rnd.strip():
        print("회차를 알 수 없어 실행하지 않았습니다.")
        return None
    argv = ["--round", rnd.strip(), "--panel-auto"]
    # **기본은 재개다** (6-F-12 §19). 끝난 단계를 다시 부르면 Claude 세션
    # 3회를 다시 쓰므로 일부러 골라야 한다 — 기본값이 '아니오' 인 이유다.
    again = _ask("끝난 단계도 처음부터 다시 돌릴까요? "
                 "(Claude 세션 3회를 다시 씁니다) [y/N]: ")
    if (again or "").strip().lower() in ("y", "yes", "ㅇ"):
        argv.append("--panel-auto-rerun")
    return argv


def _rerender_args() -> list[str] | None:
    """`[3] 최종 리포트 다시 만들기`. 저장본 경로를 만들어 넘긴다."""
    from . import artifact

    rnd = _ask("회차 번호를 입력하세요 (예: 260054): ")
    if rnd is None or not rnd.strip():
        print("회차를 알 수 없어 실행하지 않았습니다.")
        return None
    path = artifact.path_for(rnd.strip())
    if not path.is_file():
        print(f"\n  저장된 회차 분석이 없습니다. ({path})")
        print("  먼저 [1] 회차 분석을 돌리십시오.")
        return None
    return ["--rerender-artifact", str(path)]


def _panel_apply_args() -> list[str] | None:
    """`[4]` 의 두 입력 경로 중 하나를 골라 CLI 인자를 만든다."""
    print("\n  패널 결과를 어떻게 넣을까요?")
    for key, title, why in PANEL_INPUTS:
        print(f"  [{key}] {title}")
        print(f"      {why}")
    print("  [0] 뒤로")
    answer = (_ask("번호를 고르고 Enter (기본 1): ") or "1").strip()
    if answer == "0":
        return None
    if answer == "2":
        picked = _pick_panel_file()
        if picked is None:
            return None
        path, rnd = picked
        return ["--round", rnd,
                "--import-panel-result", str(path),
                "--audit-panel-result", str(path)]
    if answer != "1":
        print(f"'{answer}' 는 없는 번호입니다.")
        return None
    return _paste_panel()


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

    # 클로드 채팅에서 받은 Panel Result 를 되붙인다. **여기서 검증·감사를
    # 다시 구현하지 않는다** — CLI 와 같은 인자를 만들어 같은 경로를 태운다
    # (§43). 두 곳에서 다른 결과가 나오면 어느 쪽도 믿을 수 없다.
    if args == "panel-apply":
        built = _panel_apply_args()
        if built is None:
            return 1
        args = built

    # 1·2단계 결과 보관과 3단계 자료 조립 (Phase 6-F-3). **클로드를 부르지
    # 않는다** — 검증·조립도 여기서 다시 구현하지 않고 CLI 를 그대로 태운다.
    if args == "panel-work":
        built = _panel_work_args()
        if built is None:
            return 1
        args = built

    # 패널 자동 분석 (Phase 6-F-6). **여기서 오케스트레이션을 다시 쓰지
    # 않는다** — CLI 인자를 만들어 같은 경로를 태운다 (§1-20 과 같은 이유).
    if args == "panel-auto":
        built = _panel_auto_args()
        if built is None:
            return 1
        args = built

    # 예전 [3]·[4]·[6] 을 모은 자리. 부르는 것은 전부 기존 함수다.
    if args == "panel-manual":
        built = _panel_manual_args()
        if built is None:
            return 1
        args = built

    if args == "rerender":
        built = _rerender_args()
        if built is None:
            return 1
        args = built

    # 회차 결과 정산 (Phase 6-C-2). **회차를 비워 둘 수 없다** — 정산은
    # 지정한 회차 하나만 손대는 것이 규칙이라(§5) 자동 탐지가 없다.
    # 리포트를 만들지 않으므로 `--open` 을 붙이지 않는다.
    if args == "settle":
        rnd = _ask("정산할 회차 번호 (예: 260052): ")
        if rnd is None:
            print("입력이 끝나 실행하지 않았습니다.")
            return 1
        if not rnd.strip():
            print("회차를 지정해야 합니다 — 정산은 회차 하나만 처리합니다.")
            return 1
        from .cli import main as cli_main
        return ("settle", cli_main(["--settle-round", rnd.strip()]))

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

    # 근거 0건이면 채팅용 시트가 통째로 안 나온다 — 시즌 초에는 그게
    # 정상 상태다. 다 돌린 뒤 지침 파일 하나만 남은 것을 보고서야 알게
    # 하지 않으려고, 시작할 때 한 번 묻는다. 기본은 아니오다.
    if "--panel-export" in args:
        wide = _ask("근거가 없는 경기도 축 지표만으로 낼까요? "
                    "(시즌 초에 필요합니다) (y/N): ")
        if wide is None:
            print("입력이 끝나 실행하지 않았습니다.")
            return 1
        if wide.lower().startswith("y"):
            args = [a for a in args if a != "--panel-export"]
            args.append("--panel-export-all")

    if "--serve" in args:                # 공유만 하는 항목 (리포트를 만들지 않음)
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
    elif kind == "settle":
        print("정산을 마쳤습니다. 경기 전 기록은 그대로입니다 "
              "(data/round_matches.csv).")
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
