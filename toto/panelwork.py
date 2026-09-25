"""1·2단계 분석 결과 보관과 3단계 입력 조립 (Phase 6-F-3).

6-F-1 이 실제 워크플로를 따라가 보니 사람이 하는 일은 **분석이 아니라
운반**이었고, 그 운반 중 한 곳이 프로그램이 정확히 할 수 있는 일을 모델의
주의력에 맡기고 있었다.

    회차 전체 `03_사회자자료.md` 의 `opinions` 는 `[]` 이고
    자리표시자조차 없다 (실측: `◀` 0회).

즉 지금은 **모델이 직접** `[A]`·`[B]` 배열에서 같은 `match_no` 객체 둘을
찾아 14경기의 `opinions` 자리에 끼워 넣는다. 한 칸 밀려도 프로그램은 알 수
없다 — 사회자 입력의 `opinions` 는 검증 대상이 아니기 때문이다. 이 모듈이
그 조립을 가져온다.

## 이 모듈은 Claude 를 부르지 않는다

**API 를 호출하는 코드가 여기에 없다.** `llm`·`anthropic` 을 import 하지
않고, `panel.run_match`·`panel.run_panel_role`·`panel.attach_panels`·
`moderator.run_moderator` 를 부르지 않는다 (테스트가 AST 로 고정한다).
분석 실행은 전부 사람이 클로드 채팅에서 한다. 프로그램이 하는 일은 넷이다.

  · 사람이 받아 온 1·2단계 응답을 **검증**한다
  · 통과한 것만 **보관**한다
  · A·B 의 `match_no` 집합이 같은지 **대조**한다
  · `match_no` 를 기준으로 **조립**해 완성된 사회자 자료를 만든다

## 검증기를 새로 만들지 않는다

경기 하나의 내용은 `panel.parse_opinion()` 이 본다 — API 경로가 쓰는 바로
그 함수다. 근거 ID 목록도 `build_panel_payload(match).evidence_ids` 에서
온다. 규칙을 두 벌 두면 채팅 경로와 API 경로가 조용히 갈라진다 (§1-8).

`match_no` 의 '양의 정수' 규칙은 `panelpaste._int_no()` 를 그대로 쓴다.
같은 규칙을 다시 적지 않기 위해서다 — 이 저장소는 그렇게 남의 모듈의
`_` 이름을 쓰는 선례가 이미 있다 (`panelaudit` → `panelimport._match_key`,
`panelimport` → `panel._score`).

## A 와 B 는 합쳐지기 전까지 서로를 모른다

`save_stage()` 는 **다른 역할의 파일을 읽지 않는다.** 읽으면 B 를 저장하는
과정이 A 를 들여다보는 셈이고, 그 경로가 생기면 언젠가 B 의 입력에 A 가
섞인다. 둘은 `build_completed_sheet()` 에서 **처음** 만난다 (테스트로 고정).

## 3단계 결과도 같은 자리에 둔다 (Phase 6-F-4)

6-F-3 까지 1·2단계는 보관됐는데 **3단계 결과만 보관되지 않았다** — 사용자가
붙여넣으면 곧바로 `[4]` 로 흘러가 `panel_results/` 에 canonical 판이 남고
클로드가 실제로 돌려준 배열은 사라졌다. 그래서 회차의 진행 상태를 파일로
읽을 수가 없었고, 같은 붙여넣기를 다시 쓰려면 채팅으로 돌아가야 했다.

`save_moderator_result()` 가 **검증을 통과한 것만** `moderator_result.json`
으로 남긴다. 1·2단계와 같은 규칙이다 — 원문 배열 그대로, 옆에 다 쓴 뒤
바꿔 끼우고, 실패하면 앞서 저장한 것이 그대로 남는다.

**새 결과 포맷을 만들지 않는다.** 보관본은 클로드의 3단계 응답 배열
그대로이고, 그것을 기존 `--paste-panel-result` 에 그대로 태우면
`panelpaste.apply()` → `panel_results/<회차>_panel_result.json` →
`panelimport.run()` → `panelaudit.audit()` 라는 **기존 `[4]` 경로**를 한
줄도 바꾸지 않고 지난다. 이 모듈은 `panel_results/` 에 쓰지 않는다.

## 상태는 파일이 정한다 — 상태 DB 를 만들지 않는다

`workflow()` 가 돌려주는 다섯 단계는 전부 **파일이 있느냐**로 정해진다.
따로 저장하는 상태 파일이 없으므로 사람이 파일을 지우면 상태도 같이
사라지고, 그 편이 실제와 어긋난 상태 기록이 남는 것보다 낫다.

첨부할 파일 이름은 **폴더를 읽어서** 만든다. `02_경기자료_3of7.md` 처럼
회차마다 개수와 이름이 달라지므로 코드에 적어 두면 조용히 낡는다 (§10).

## 있다 ≠ 쓸 수 있다 (Phase 6-F-12)

위 문단은 **사람이 화면에서 볼 때**는 지금도 맞다. 그런데 6-F-6 부터
`panelauto` 가 그 판정을 **재개 결정**에 쓰기 시작했다 — `done` 이 참이면
그 단계를 부르지 않는다. 존재만으로 건너뛰면 두 가지가 조용히 지나간다.

  · 손으로 고쳐졌거나 잘린 보관본이 '완료' 로 읽힌다. 뒤늦게 조립·반영
    단계에서 터지는데, 그때는 이미 다음 단계에 돈을 쓴 뒤다.
  · **출처가 다른** 보관본이 그대로 재사용된다. 회차를 다시 수집하면
    순위표·배당이 달라지는데(§1-1-7), 옛 A·B 를 그대로 두고 새 자료로
    만든 사회자 시트에 C 를 돌리면 **한 회차 안에 두 시점이 섞인다.**

그래서 재개 판정은 다섯 문을 지난다 — 파일이 있나 · 읽히나 · JSON 인가 ·
**기존 검증기**(`parse_stage` / `parse_moderator_result`)를 지나나 ·
기록된 출처가 지금 것과 맞나. 검증기를 새로 쓰지 않는다 (§1-8).

**출처 기록이 없는 것은 어긋난 것이 아니다.** 채팅 경로로 넣은 보관본과
6-F-12 이전의 파일에는 기록이 없다 — 그것을 '불일치' 로 보면 멀쩡한
체크포인트가 하루아침에 전부 무효가 된다. `unverified` 로 적고 **그대로
쓴다**. 6-F-7 이 인증 상태에서 `unknown` 을 `실패` 로 치지 않은 것과 같은
태도다 (§1-6).

출처는 `workflow_manifest.json` **한 장**에 모은다. 새 DB 도 아니고
`PanelResult` 스키마도 건드리지 않는다 — 보관본 자체는 **클로드가 돌려준
배열 그대로**여야 하므로(§6) 그 안에 메타데이터를 섞을 수 없다.

**이 모듈은 매니페스트를 읽어 판정만 하고, 자동 경로의 출처를 적는 것은
`panelauto` 다.** 무엇으로 만들었는지(packet·모델·세션)를 아는 쪽이
거기이기 때문이고, 그래서 수동 경로는 기록을 남기지 않아 자연히
`unverified` 가 된다 — 관측하지 않은 것을 적지 않는다 (§1-5).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import moderator, panel, panelexport, panelimport, panelpaste
from .models import PanelOpinion, Report

log = logging.getLogger(__name__)

# 중간 작업물. 재생성할 수 있으므로 `.gitignore` 에 넣는다 —
# `reports/`·`cache/` 와 같은 취급이고, 축적이 목적인 `data/rounds.csv`
# (§1-6-2)나 원자료인 `panel_results/`(§1-20)와는 다르다.
WORK_DIRNAME = "panel_work"

# 역할 → 파일 이름. 사람이 폴더를 열어 봤을 때 1단계·2단계가 바로 보이도록
# `a`·`b` 로 적는다 (채팅 지침의 "역할 A"·"역할 B" 와 같은 표기다).
ROLE_FILES = {
    panel.DATA_ANALYST: "analyst_a.json",
    panel.MATCHUP_ANALYST: "analyst_b.json",
}

# 사람이 `--role` 에 적을 짧은 이름. 내부 역할 식별자를 외우게 하지 않는다.
ROLE_ALIASES = {
    "a": panel.DATA_ANALYST, "analyst_a": panel.DATA_ANALYST,
    "b": panel.MATCHUP_ANALYST, "analyst_b": panel.MATCHUP_ANALYST,
    panel.DATA_ANALYST: panel.DATA_ANALYST,
    panel.MATCHUP_ANALYST: panel.MATCHUP_ANALYST,
}

# 완성본. **원본을 덮어쓰지 않는다** (§11) — 원본은 의견이 없는 판이고
# 이쪽은 프로그램이 조립한 판이라, 둘이 구분돼야 무엇을 첨부했는지 안다.
COMPLETED_SHEET = "03_사회자자료_완성.md"

# 3단계 결과 보관본 (Phase 6-F-4). 클로드가 돌려준 **배열 그대로**이고
# canonical Panel Result 가 아니다 — 그쪽은 `[4]` 가 `panel_results/` 에
# 만든다. 둘을 같은 파일로 두면 '모델이 무엇을 말했나' 를 되짚을 수 없다.
MODERATOR_RESULT_FILE = "moderator_result.json"

# 출처 기록 (Phase 6-F-12). 보관본 **옆**에 두고 보관본 자체는 건드리지
# 않는다 — 그 파일은 모델이 돌려준 배열 그대로여야 한다 (§6).
MANIFEST_FILE = "workflow_manifest.json"
MANIFEST_VERSION = "1"

# 붙여넣기 입력의 경기 번호 키. 1·2·3단계 출력이 전부 이 이름을 쓴다.
STAGE_NO = panelpaste.PASTE_NO


def _atomic_write(path: Path, payload: str) -> None:
    """옆에 다 쓰고 **바꿔 끼운다.** 쓰다 만 파일이 자리에 남지 않는다.

    1·2·3단계 보관본과 매니페스트가 **같은 함수**를 쓴다 — 세 곳에 따로
    적어 두면 한 곳만 고쳐진다 (§1-8). `fsync` 는 되는 자리에서만 한다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(payload)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except (OSError, AttributeError):
            # 일부 파일시스템·플랫폼에서 지원하지 않는다. 그 사실이
            # 저장을 실패로 만들지는 않는다.
            pass
    os.replace(tmp, path)


def work_dir(round_id: str, base: Path | None = None) -> Path:
    from .settings import ROOT
    root = Path(base) if base is not None else ROOT
    return root.joinpath(WORK_DIRNAME, str(round_id or "unknown"))


def resolve_role(name: str) -> str:
    """사람이 적은 이름 → 역할 식별자. 모르면 빈 문자열."""
    return ROLE_ALIASES.get((name or "").strip().lower(), "")


def path_for(round_id: str, role: str, base: Path | None = None) -> Path:
    return work_dir(round_id, base).joinpath(ROLE_FILES[role])


def moderator_result_path(round_id: str, base: Path | None = None) -> Path:
    return work_dir(round_id, base).joinpath(MODERATOR_RESULT_FILE)


# ==========================================================================
# 결과 — `panelimport` 의 어휘를 그대로 쓴다
# ==========================================================================
@dataclass
class StageResult:
    """한 단계의 검증·보관 결과. `Issue`·`ERROR`·`WARNING` 을 재사용한다."""
    role: str = ""
    round_id: str = ""
    expected_matches: int = 0
    saved_matches: int = 0
    path: Path | None = None
    issues: list = field(default_factory=list)

    @property
    def errors(self) -> list:
        return [i for i in self.issues if i.severity == panelimport.ERROR]

    @property
    def warnings(self) -> list:
        return [i for i in self.issues if i.severity == panelimport.WARNING]

    @property
    def success(self) -> bool:
        return self.path is not None and not self.errors

    def add(self, severity: str, code: str, message: str, **where) -> None:
        self.issues.append(
            panelimport.Issue(severity, code, message, **where))

    def status_line(self) -> str:
        """§1-6 어휘. 실패와 부분을 뭉뚱그리지 않는다."""
        ko = panel.ROLE_KO.get(self.role, self.role)
        if self.success and not self.issues:
            return (f"ok ({self.saved_matches}/{self.expected_matches}경기 "
                    f"· {ko} · {self.round_id}회차)")
        if self.success:
            return (f"부분 ({self.saved_matches}/{self.expected_matches}경기 "
                    f"· {ko}, 확인 필요 {len(self.warnings)}건)")
        return (f"실패 ({ko} · 오류 {len(self.errors)}건 — "
                f"저장하지 않았습니다)")


@dataclass
class BuildResult:
    """사회자 자료 조립 결과."""
    round_id: str = ""
    matches: int = 0
    path: Path | None = None
    issues: list = field(default_factory=list)

    @property
    def errors(self) -> list:
        return [i for i in self.issues if i.severity == panelimport.ERROR]

    @property
    def success(self) -> bool:
        return self.path is not None and not self.errors

    def add(self, severity: str, code: str, message: str, **where) -> None:
        self.issues.append(
            panelimport.Issue(severity, code, message, **where))

    def status_line(self) -> str:
        if self.success:
            return f"ok ({self.matches}경기 → {self.path})"
        return (f"실패 (오류 {len(self.errors)}건 — "
                f"사회자 자료를 만들지 않았습니다)")


def report_lines(result) -> list[str]:
    """사람이 읽을 요약. 오류를 숨기지 않는다."""
    return [result.status_line()] + [str(i) for i in result.issues]


# ==========================================================================
# 파싱과 검증 — 붙여넣기와 파일이 **같은 함수**를 지난다 (§15)
# ==========================================================================
def parse_stage(text: str, role: str, report: Report):
    """응답 원문 → (경기번호 → `PanelOpinion`, 원본 배열, 결과).

    구조는 여기서 보고 **내용은 `panel.parse_opinion()` 이 본다** — 스코어
    형식·근거 ID·필수 칸이 전부 그쪽 규칙이다. 어긋나면 고쳐 주지 않고
    실패시킨다 (§5-9).
    """
    out = StageResult(role=role, round_id=str(report.round_id or ""),
                      expected_matches=len(report.matches))

    def fail(code: str, why: str, **kw):
        out.add(panelimport.ERROR, code, why, **kw)

    raw = (text or "").strip()
    if not raw:
        fail("STAGE_EMPTY", "붙여넣은 내용이 없습니다")
        return {}, None, out
    try:
        data = json.loads(panelpaste._strip_fence(raw))
    except Exception as exc:                                # noqa: BLE001
        fail("STAGE_NOT_JSON", f"JSON 으로 읽지 못했습니다: {exc}")
        return {}, None, out
    if not isinstance(data, list):
        fail("STAGE_NOT_A_LIST",
             f"최상위가 배열이 아닙니다 ({type(data).__name__}) — 1·2단계 "
             f"결과는 경기 객체의 배열입니다")
        return {}, None, out
    if not data:
        fail("STAGE_EMPTY", "배열이 비어 있습니다")
        return {}, None, out

    by_no = {m.no: m for m in report.matches}
    opinions: dict[int, PanelOpinion] = {}
    seen: dict[int, int] = {}
    for i, item in enumerate(data):
        where = {"field": f"[{i}]"}
        if not isinstance(item, dict):
            fail("STAGE_ITEM_NOT_AN_OBJECT",
                 f"{i + 1}번째 항목이 객체가 아닙니다 "
                 f"({type(item).__name__})", **where)
            continue
        no = panelpaste._int_no(item.get(STAGE_NO))
        if no is None:
            fail("STAGE_MATCH_NO_INVALID",
                 f"{i + 1}번째 항목의 {STAGE_NO} 가 양의 정수가 아닙니다 "
                 f"({item.get(STAGE_NO)!r})", field=f"[{i}].{STAGE_NO}")
            continue
        if no in seen:
            fail("STAGE_DUPLICATE_MATCH_NO",
                 f"{STAGE_NO} {no} 이 두 번 나옵니다 (앞서 {seen[no]}번째)",
                 match_no=no, field=f"[{i}].{STAGE_NO}")
            continue
        seen[no] = i + 1
        match = by_no.get(no)
        if match is None:
            fail("STAGE_UNKNOWN_MATCH_NO",
                 f"{no}번 경기가 이 회차({report.round_id})에 없습니다",
                 match_no=no, field=f"[{i}].{STAGE_NO}")
            continue
        # 근거 ID 목록은 **그 경기의 payload** 에서 온다 — 회차 전체가
        # 아니다. 근거는 경기마다 다시 매겨지므로(§1-15) 다른 경기의 ID 를
        # 쓰면 여기서 걸린다.
        allowed = panel.build_panel_payload(match).evidence_ids
        try:
            opinions[no] = panel.parse_opinion(
                json.dumps(item, ensure_ascii=False), role, allowed)
        except panel.ValidationError as exc:
            fail("STAGE_OPINION_INVALID", str(exc), match_no=no,
                 field=f"[{i}]")

    missing = [m.no for m in report.matches if m.no not in seen]
    if missing:
        fail("STAGE_INCOMPLETE_ROUND",
             f"회차 {len(report.matches)}경기 중 {len(seen)}경기만 있습니다 — "
             f"빠진 경기: {', '.join(str(n) for n in missing)}번. 1·2단계 "
             f"결과 전체를 넣으십시오")

    if out.errors:
        return {}, None, out
    out.saved_matches = len(opinions)
    return opinions, data, out


def save_stage(text: str, role: str, report: Report,
               base: Path | None = None) -> StageResult:
    """검증 → (통과하면) 보관. **다른 역할의 파일을 읽지 않는다** (§18).

    검증을 통과한 경우에만 쓰므로, 실패해도 앞서 저장해 둔 결과가 그대로
    남는다 (§7·§16). 저장은 옆에 다 쓴 뒤 바꿔 끼운다.
    """
    _opinions, data, out = parse_stage(text, role, report)
    if out.errors or data is None:
        return out

    # 클로드가 돌려준 구조를 **그대로** 보관한다 (§6) — 프로그램이 재구성한
    # 판을 저장하면 나중에 "모델이 무엇을 말했나" 를 되짚을 수 없다.
    round_id = report.round_id or "unknown"
    path = path_for(round_id, role, base)
    body = json.dumps(data, ensure_ascii=False, indent=1)
    try:
        _atomic_write(path, body)
    except OSError as exc:
        out.add(panelimport.ERROR, "STAGE_NOT_SAVED",
                f"파일을 쓰지 못했습니다: {exc}", field=str(path))
        return out
    out.path = path
    # 출처 — **아는 것만 적는다.** packet·모델·세션은 자동 경로가 알고
    # 있으므로 `panelauto` 가 뒤이어 합쳐 넣는다 (§1-5).
    stage = STAGE_A if role == panel.DATA_ANALYST else STAGE_B
    record_stage(round_id, stage, base, sha256=_sha(body),
                 matches=out.saved_matches, created_at=now_utc(),
                 panel_prompt_version=panel.PANEL_PROMPT_VERSION,
                 status=STAGE_COMPLETE)
    return out


def load_stage(round_id: str, role: str, report: Report,
               base: Path | None = None):
    """보관본 → (경기번호 → `PanelOpinion`, 결과). 없으면 사유를 담는다.

    **저장할 때와 같은 검증을 다시 지난다** — 파일이 손으로 고쳐졌을 수
    있고, 그때 조용히 통과하면 조립이 틀린 채로 나간다.
    """
    opinions, _data, out = _read_stage(round_id, role, report, base)
    return opinions, out


def _read_stage(round_id: str, role: str, report: Report,
                base: Path | None = None):
    """보관본 → (의견, **원배열**, 결과). `load_stage` 와 최종 조립이 쓴다.

    조립(6-F-14)은 검증된 의견 객체가 아니라 **모델이 돌려준 배열 그대로**
    를 옮겨야 한다 — 의견 객체를 다시 dict 로 풀면 그것은 옮긴 것이 아니라
    다시 쓴 것이 된다. 그래서 읽기·검증은 한 벌이고 돌려주는 것만 늘렸다.
    """
    path = path_for(round_id, role, base)
    out = StageResult(role=role, round_id=str(round_id or ""),
                      expected_matches=len(report.matches))
    if not path.is_file():
        # `panelimport` 가 쓰는 코드를 그대로 쓴다 — 새 상태명을 늘리지
        # 않는다 (§17).
        out.add(panelimport.ERROR, "MISSING_ANALYST",
                f"{panel.ROLE_KO.get(role, role)} 결과가 없습니다 "
                f"({path}) — 먼저 그 단계 결과를 넣으십시오", field=role)
        return {}, None, out
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        # BOM·cp949 로 저장된 파일이 올라와 회차를 죽이지 않게 한다 (§1-7).
        out.add(panelimport.ERROR, "UNREADABLE", str(exc), field=str(path))
        return {}, None, out
    opinions, data, parsed = parse_stage(text, role, report)
    parsed.path = path if not parsed.errors else None
    return opinions, data, parsed


# ==========================================================================
# 조립 — A 와 B 가 여기서 **처음** 만난다
# ==========================================================================
def collect_opinions(report: Report, base: Path | None = None):
    """두 보관본을 읽어 `match_no` → 의견 목록. (dict, 결과).

    **번호로 짝짓는다 — 배열 순서에 기대지 않는다** (§9). 순서에 기대면
    한쪽이 정렬돼 오는 순간 조용히 어긋난다.
    """
    out = BuildResult(round_id=str(report.round_id or ""))
    per_role: dict[str, dict[int, PanelOpinion]] = {}
    for role in panel.ROLES:
        opinions, stage = load_stage(report.round_id or "", role,
                                     report, base)
        out.issues.extend(stage.issues)
        per_role[role] = opinions
    if out.errors:
        return {}, out

    # A·B 의 경기 집합이 같아야 한다 (§19·§20). 다르면 **채우지도 재정렬
    # 하지도 않고** 실패시킨다.
    sets = {role: set(ops) for role, ops in per_role.items()}
    a, b = panel.ROLES
    if sets[a] != sets[b]:
        only_a = sorted(sets[a] - sets[b])
        only_b = sorted(sets[b] - sets[a])
        out.add(panelimport.ERROR, "MATCH_NO_MISMATCH",
                f"1·2단계의 경기 번호가 다릅니다 — "
                f"1단계에만 {only_a or '없음'}, 2단계에만 "
                f"{only_b or '없음'}. 빠진 경기를 채우거나 번호를 "
                f"고치지 않습니다")
        return {}, out

    merged = {no: [per_role[a][no], per_role[b][no]]
              for no in sorted(sets[a])}
    out.matches = len(merged)
    return merged, out


def build_completed_sheet(report: Report, settings=None,
                          base: Path | None = None,
                          outdir: Path | None = None) -> BuildResult:
    """A·B 를 조립해 `03_사회자자료_완성.md` 를 만든다.

    **원본을 덮어쓰지 않는다** (§11). 자료 자체는 `panelexport` 가 만들고
    여기서는 의견만 넘긴다 — 사회자 입력의 모양을 두 곳에서 정하지 않는다.
    """
    merged, out = collect_opinions(report, base)
    if out.errors:
        return out

    round_id = report.round_id or "unknown"
    payloads = [panel.build_panel_payload(m) for m in report.matches]
    target = Path(outdir) if outdir else panelexport.round_dir(round_id)
    path = target.joinpath(COMPLETED_SHEET)
    body = panelexport.moderator_data_sheet(round_id, payloads,
                                            opinions_by_no=merged)
    try:
        _atomic_write(path, body)
    except OSError as exc:
        out.add(panelimport.ERROR, "SHEET_NOT_WRITTEN",
                f"파일을 쓰지 못했습니다: {exc}", field=str(path))
        return out
    out.path = path
    # **무엇을 먹고 만들어졌는지 적는다** (§14). 이 함수는 A·B 를 실제로
    # 읽었으므로 그 해시를 단언할 자격이 있다 — 뒤에 A 가 바뀌면 이
    # 조립본이 낡았다는 것이 해시 비교로 드러난다.
    record_stage(round_id, STAGE_INPUT, base, sha256=_sha(body),
                 matches=out.matches, created_at=now_utc(),
                 status=STAGE_COMPLETE,
                 depends={STAGE_A: _file_sha(path_for(round_id,
                                                      panel.DATA_ANALYST,
                                                      base)),
                          STAGE_B: _file_sha(path_for(round_id,
                                                      panel.MATCHUP_ANALYST,
                                                      base))})
    return out


def opinion_count(report: Report, base: Path | None = None) -> dict:
    """어느 단계까지 보관돼 있나. 화면에 한 줄로 보여 주려고 쓴다."""
    state = {}
    for role in panel.ROLES:
        path = path_for(report.round_id or "", role, base)
        state[role] = path.is_file()
    return state


# ==========================================================================
# 3단계 결과 보관 (Phase 6-F-4)
# ==========================================================================
def parse_moderator_result(text: str, report: Report, settings=None):
    """3단계 응답 원문 → (Panel Result dict, 원본 배열, 검증 결과).

    **검증기를 새로 쓰지 않는다.** 구조와 경기 연결은 `panelpaste.convert()`
    가, 내용(스코어·분포·근거 ID·금지 칸)은 `panelimport.validate()` 가
    본다 — 그리고 그것이 다시 `moderator.parse_result()` 를 부른다. 붙여넣기·
    파일·이 경로 셋이 **같은 문**을 지난다 (§1-8).

    `panelpaste.apply()` 와 다른 점은 하나뿐이다 — **파일을 쓰지 않는다.**
    `panel_results/` 는 `[4]` 의 자리이고 이 모듈은 거기에 쓰지 않는다.
    """
    data, issues = panelpaste.convert(text, report)
    if data is None:
        out = panelimport.PanelImportResult(
            round_id=str(report.round_id or ""),
            expected_matches=len(report.matches))
        out.issues = list(issues)
        return None, None, out

    out = panelimport.validate(data, report, settings)
    out.issues = list(issues) + list(out.issues)
    # `convert()` 가 통과한 시점에 이미 JSON 배열로 읽힌 텍스트다.
    array = json.loads(panelpaste._strip_fence((text or "").strip()))
    return data, array, out


def save_moderator_result(text: str, report: Report, settings=None,
                          base: Path | None = None):
    """검증 → (통과하면) 보관. (경로, 검증 결과).

    **통과한 것만 쓴다** — 깨진 붙여넣기가 남으면 다음 실행이 그것을 집어
    든다 (§16, 1·2단계와 같은 규칙). 실패해도 앞서 저장한 결과는 그대로다.

    보관하는 것은 **클로드가 돌려준 배열 그대로**다. canonical Panel Result
    로 옮겨 적지 않는다 — 그 판은 `[4]` 가 `panel_results/` 에 만들고, 두
    자리가 서로 다른 것을 담아야 '모델이 무엇을 말했나' 를 되짚을 수 있다.
    """
    data, array, out = parse_moderator_result(text, report, settings)
    if data is None or not out.success:
        return None, out

    round_id = report.round_id or "unknown"
    path = moderator_result_path(round_id, base)
    body = json.dumps(array, ensure_ascii=False, indent=1)
    try:
        _atomic_write(path, body)
    except OSError as exc:
        out.add(panelimport.ERROR, "MODERATOR_RESULT_NOT_WRITTEN",
                f"파일을 쓰지 못했습니다: {exc}", field=str(path))
        return None, out
    # 3단계는 사회자 자료와 A·B 를 보고 나온 것이다. **지금 자리에 있는
    # 것**을 적는다 — 붙여넣기 경로에서는 그것이 우리가 아는 전부다.
    record_stage(round_id, STAGE_RESULT, base, sha256=_sha(body),
                 matches=len(report.matches), created_at=now_utc(),
                 status=STAGE_COMPLETE,
                 moderator_prompt_version=moderator.MODERATOR_PROMPT_VERSION,
                 depends={
                     STAGE_A: _file_sha(path_for(round_id,
                                                 panel.DATA_ANALYST, base)),
                     STAGE_B: _file_sha(path_for(round_id,
                                                 panel.MATCHUP_ANALYST, base)),
                     STAGE_INPUT: _file_sha(
                         checkpoint_path(round_id, STAGE_INPUT, base))})
    return path, out


# ==========================================================================
# 최종 반영 — 세 보관본을 Panel Result 하나로 (Phase 6-F-14)
# ==========================================================================
# 이 경로로 만든 Panel Result 의 `source`. 채팅 붙여넣기(`moderator-paste`)와
# 파일을 열었을 때 구분되도록 이름을 따로 둔다. 검증기는 이 칸을 읽지 않는다.
APPLY_SOURCE = "panel-work"


def assemble_panel_result(report: Report, settings=None,
                          base: Path | None = None):
    """A·B·C 보관본 → Panel Result 1.1 dict. (dict | None, 검증 결과).

    6-F-13 이 찾은 것 — 자동·수동 반영이 사회자 보관본 **하나만**
    `--paste-panel-result` 에 넘겼다. 그 어댑터는 "1·2단계 원문이 없다" 는
    전제로 만든 것이라(4-F) 모든 경기를 `부분` 으로 적고 분석가 칸을 만들지
    않았고, 체크포인트에 멀쩡히 있던 A·B 가 최종 파일에 한 번도 닿지 못했다.

    **새 스키마를 만들지 않는다.** 1.1 의 `ok` 블록 — `data_analyst` ·
    `matchup_tactical_analyst` · `moderator` — 이 이미 셋을 받는다.

    **옮기기만 한다.** 스코어·요약·근거를 다시 계산하지 않는다.

      · A·B 는 `_read_stage()` 가 저장 때와 같은 문(`parse_stage`)으로 다시
        검증한 **원배열**에서 `match_no` 하나만 빼고 그대로 옮긴다.
      · C 는 `panelpaste.convert()` 로 경기를 잇는다 — 사회자 칸을 가르는
        규칙과 '돌리지 않은 경기' 판정을 두 벌 두지 않는다 (§1-8).
      · **짝은 `match_no` 로 짓는다.** 배열 순서에 기대지 않는다.
      · 내용 검증은 `panelimport.validate()` 한 곳이다. `ok` 경로라서 사회자의
        `adopted_from` 이 **실제 원안과 대조된다** — 사회자 전용 경로보다
        엄격하다.

    **C 가 돌리지 않은 경기(`생략`)에는 A·B 를 붙이지 않는다.** 붙이면
    `panelimport._not_run` 이 상태 모순으로 거부하고, 그 전에 뜻부터 틀린다 —
    패널이 끝나지 않은 경기를 끝난 것처럼 보이게 된다.

    **파일을 쓰지 않는다.** `panel_results/` 는 `[4]` 의 자리이고 이 모듈은
    거기에 쓰지 않는다(§1-41) — 쓰는 것은 `panelpaste.write_canonical()`
    하나다. A 나 B 가 없거나 깨졌으면 **만들지 않는다** — 빈 분석가를
    지어내지 않고, 사회자 전용으로 조용히 강등하지도 않는다.
    """
    rid = str(report.round_id or "")
    out = panelimport.PanelImportResult(round_id=rid,
                                        expected_matches=len(report.matches))

    rows: dict[str, dict] = {}
    for role in panel.ROLES:
        _ops, data, stage = _read_stage(rid, role, report, base)
        out.issues.extend(stage.issues)
        if not stage.errors and data is not None:
            rows[role] = {item[STAGE_NO]: item for item in data}

    mod_path = moderator_result_path(rid, base)
    try:
        text = mod_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        out.add(panelimport.ERROR, "MISSING_MODERATOR",
                f"3단계 결과가 없습니다 ({mod_path}) — 먼저 그 단계 결과를 "
                f"넣으십시오", field=panelimport.MODERATOR_ROLE)
        text = None
    except (OSError, UnicodeDecodeError) as exc:
        out.add(panelimport.ERROR, "UNREADABLE", str(exc),
                field=str(mod_path))
        text = None

    data = None
    if text is not None:
        data, issues = panelpaste.convert(text, report)
        out.issues.extend(issues)
    if out.errors or data is None:
        return None, out

    blocks = []
    for block in data["matches"]:
        no = block["match_number"]
        if block.get("panel_status") == panelimport.STATUS_SKIPPED:
            blocks.append(block)
            continue
        pair = {role: rows.get(role, {}).get(no) for role in panel.ROLES}
        missing = [panel.ROLE_KO.get(r, r) for r, v in pair.items()
                   if v is None]
        if missing:
            # 검증을 지난 세 배열은 회차 경기를 전부 덮으므로 여기에 닿지
            # 않는다. 규칙이 바뀌어 닿게 되면 **조용히 합치지 않는다.**
            out.add(panelimport.ERROR, "MATCH_NO_MISMATCH",
                    f"{no}번 경기가 {' · '.join(missing)} 결과에 없습니다 — "
                    f"빠진 경기를 채우거나 번호를 고치지 않습니다",
                    match_no=no)
            continue
        merged = {k: v for k, v in block.items()
                  if k not in ("panel_status", "panel_status_reason",
                               panelimport.MODERATOR_ROLE)}
        merged["panel_status"] = panelimport.STATUS_OK
        for role in panel.ROLES:
            merged[role] = {k: v for k, v in pair[role].items()
                            if k != STAGE_NO}
        merged[panelimport.MODERATOR_ROLE] = block[panelimport.MODERATOR_ROLE]
        blocks.append(merged)
    if out.errors:
        return None, out

    data = dict(data, source=APPLY_SOURCE, matches=blocks)
    result = panelimport.validate(data, report, settings)
    result.issues = list(out.issues) + list(result.issues)
    return (data if result.success else None), result


def record_applied(round_id: str, path: Path, matches: int,
                   base: Path | None = None) -> dict:
    """최종 반영의 출처를 적는다 (Phase 6-F-14).

    6-F-12 는 a·b·input·result 까지 적고 **반영에서 끊겼다** — 매니페스트는
    "C 가 이 A·B 로 만들어졌다" 를 알면서 최종 파일과는 이어지지 않았다.
    여기서 그 고리를 잇는다. 형식은 다른 단계와 같다 (`depends`).
    """
    rid = str(round_id or "unknown")
    return record_stage(
        rid, STAGE_APPLY, base, sha256=_file_sha(Path(path)),
        matches=matches, created_at=now_utc(), status=STAGE_COMPLETE,
        source=APPLY_SOURCE,
        depends={STAGE_A: _file_sha(path_for(rid, panel.DATA_ANALYST, base)),
                 STAGE_B: _file_sha(path_for(rid, panel.MATCHUP_ANALYST,
                                             base)),
                 STAGE_RESULT: _file_sha(moderator_result_path(rid, base))})


# ==========================================================================
# 워크플로 상태 (Phase 6-F-4) — **파일이 정한다. 상태 DB 가 없다**
# ==========================================================================
A_NOT_STARTED = "A_NOT_STARTED"
A_COMPLETE = "A_COMPLETE"
B_NOT_STARTED = "B_NOT_STARTED"
B_COMPLETE = "B_COMPLETE"
MODERATOR_INPUT_NOT_BUILT = "MODERATOR_INPUT_NOT_BUILT"
MODERATOR_INPUT_READY = "MODERATOR_INPUT_READY"
MODERATOR_RESULT_NOT_SAVED = "MODERATOR_RESULT_NOT_SAVED"
MODERATOR_RESULT_SAVED = "MODERATOR_RESULT_SAVED"
PANEL_RESULT_NOT_APPLIED = "PANEL_RESULT_NOT_APPLIED"
PANEL_RESULT_COMPLETE = "PANEL_RESULT_COMPLETE"

# 단계 키. 메뉴 번호와 맞춘다 — `[6]` 안의 1·2·3·4·5 다.
STAGE_A, STAGE_B = "a", "b"
STAGE_INPUT, STAGE_RESULT, STAGE_APPLY = "input", "result", "apply"

# 실행 순서. 의존성 전파가 이 순서를 따른다.
STAGE_ORDER = (STAGE_A, STAGE_B, STAGE_INPUT, STAGE_RESULT, STAGE_APPLY)

# 단계 → 그 단계가 서 있으려면 무엇이 먼저 서 있어야 하나 (§14).
# **A 와 B 는 서로를 모른다** — 둘 다 아무 단계에도 기대지 않는다.
STAGE_UPSTREAM = {
    STAGE_A: (),
    STAGE_B: (),
    STAGE_INPUT: (STAGE_A, STAGE_B),
    STAGE_RESULT: (STAGE_A, STAGE_B, STAGE_INPUT),
    STAGE_APPLY: (STAGE_RESULT,),
}

STAGE_ROLE = {STAGE_A: panel.DATA_ANALYST, STAGE_B: panel.MATCHUP_ANALYST}


# ==========================================================================
# 체크포인트 (Phase 6-F-12) — **있다 ≠ 쓸 수 있다**
# ==========================================================================
CP_MISSING = "missing"          # 파일이 없다
CP_UNREADABLE = "unreadable"    # 있는데 읽히지 않는다 (JSON 아님·인코딩)
CP_INVALID = "invalid"          # 읽혔는데 검증을 통과하지 못한다
CP_STALE = "stale"              # 검증은 통과하는데 **출처가 지금과 다르다**
CP_UNVERIFIED = "unverified"    # 통과했는데 출처 기록이 없다 — 쓴다
CP_COMPLETE = "complete"        # 통과 + 출처 일치

# 재사용해도 되는 상태. **`unverified` 가 여기 있는 것이 이 절의 핵심이다**
# — 기록이 없는 것과 어긋난 것은 다르다 (§1-6).
CP_USABLE = (CP_COMPLETE, CP_UNVERIFIED)

# 매니페스트에 적는 단계 시도 결과 (§17). `panelauto` 의 `AGENT_*` 는
# **실행 한 번의 분류**이고 이쪽은 **워크플로가 본 단계의 결말**이다 —
# `AGENT_USAGE_LIMIT` → `WORKFLOW_STOPPED_USAGE_LIMIT` 과 같은 두 층이다.
STAGE_COMPLETE = "STAGE_COMPLETE"
STAGE_FAILED = "STAGE_FAILED"
STAGE_FAILED_LIMIT = "STAGE_FAILED_LIMIT"

# A·B 가 같은 자료에서 나왔는지 보는 칸. 이름은 `panelpacket.
# source_manifest()` 가 이미 쓰는 것을 그대로 쓴다 (§1-8).
PACKET_KEYS = ("source_sha256_16", "packet_sha256", "packet_version",
               "panel_prompt_version")

# 재개 결정
REUSE = "reuse"
RERUN = "rerun"


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _file_sha(path: Path) -> str:
    """파일 내용의 해시. 못 읽으면 **빈 문자열** — 0 으로 치지 않는다.

    인코딩 실패도 '못 읽음' 이다. 한국어 윈도우에서 편집기가 cp949 로
    저장하면 `UnicodeDecodeError` 가 나는데(§1-7 과 같은 계열), 그것이
    올라가면 체크포인트 하나 때문에 회차 전체가 죽는다.
    """
    try:
        return _sha(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError):
        return ""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def manifest_path(round_id: str, base: Path | None = None) -> Path:
    return work_dir(round_id, base).joinpath(MANIFEST_FILE)


def read_manifest(round_id: str, base: Path | None = None) -> dict:
    """출처 기록. **없거나 깨졌으면 빈 dict** — 지어내지 않는다 (§1-5).

    기록이 없다고 체크포인트가 무효가 되지는 않는다. 그 경우는
    `unverified` 이고 그대로 쓴다.
    """
    path = manifest_path(round_id, base)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    if data.get("manifest_version") != MANIFEST_VERSION:
        # 판이 다르면 읽지 않는다 — 조용히 다른 뜻으로 해석하는 것보다
        # 못 읽는 편이 낫다 (`artifact` 와 같은 태도, §1-16).
        return {}
    return data


def stage_record(round_id: str, stage: str, base: Path | None = None) -> dict:
    rows = read_manifest(round_id, base).get("stages")
    row = rows.get(stage) if isinstance(rows, dict) else None
    return dict(row) if isinstance(row, dict) else {}


def record_stage(round_id: str, stage: str, base: Path | None = None,
                 **fields) -> dict:
    """그 단계의 출처를 적는다. 기존 칸은 **덮지 않고 합친다.**

    나눠 적는 이유는 아는 쪽이 다르기 때문이다 — 보관 함수는 무엇을
    저장했는지(해시·경기 수)를 알고, `panelauto` 는 무엇으로 만들었는지
    (packet·모델·세션)를 안다. 워크플로는 순차적이라 겹쳐 쓸 일이 없다.

    **실패해도 예외를 올리지 않는다.** 기록은 감사용이고, 그것 때문에
    보관이 실패하면 안 된다 (§1-6).
    """
    rid = str(round_id or "unknown")
    data = read_manifest(rid, base)
    data["manifest_version"] = MANIFEST_VERSION
    data["round"] = rid
    rows = data.get("stages")
    if not isinstance(rows, dict):
        rows = {}
    row = dict(rows.get(stage) or {})
    row.update({k: v for k, v in fields.items() if v is not None})
    row["stage"] = stage
    row.setdefault("created_at", now_utc())
    rows[stage] = row
    data["stages"] = rows
    try:
        _atomic_write(manifest_path(rid, base),
                      json.dumps(data, ensure_ascii=False, indent=1))
    except OSError as exc:
        log.warning("출처 기록을 쓰지 못했습니다 (%s 단계): %s", stage, exc)
    return row


def checkpoint_path(round_id: str, stage: str, base: Path | None = None,
                    outdir: Path | None = None) -> Path:
    """그 단계의 체크포인트 자리. **다섯 경로를 한 곳에서 정한다** (§1-8).

    `.tmp` 는 여기서 나오지 않는다 — 쓰다 만 파일이 체크포인트가 될 수
    없다는 것이 경로 단계에서 정해진다 (§5).
    """
    rid = str(round_id or "")
    if stage in STAGE_ROLE:
        return path_for(rid, STAGE_ROLE[stage], base)
    if stage == STAGE_RESULT:
        return moderator_result_path(rid, base)
    if stage == STAGE_INPUT:
        folder = Path(outdir) if outdir else panelexport.round_dir(rid)
        return folder.joinpath(COMPLETED_SHEET)
    if stage == STAGE_APPLY:
        return panelimport.inbox_dir(base).joinpath(
            f"{rid}{panelimport.FILE_SUFFIX}")
    raise KeyError(stage)


@dataclass
class Checkpoint:
    """한 단계의 체크포인트. **존재·검증·출처를 따로 담는다.**"""
    stage: str = ""
    path: Path | None = None
    state: str = CP_MISSING
    matches: int = 0
    sha256: str = ""                            # 지금 파일의 해시
    recorded: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)

    @property
    def exists(self) -> bool:
        return self.path is not None and self.path.is_file()

    @property
    def usable(self) -> bool:
        return self.state in CP_USABLE

    @property
    def verified(self) -> bool:
        return self.state == CP_COMPLETE


def _expect_mismatch(recorded: dict, expect: dict, keys) -> list:
    """기록과 지금이 어긋난 칸. **한쪽이 없으면 묻지 않는다.**"""
    out = []
    for key in keys:
        want, got = expect.get(key), recorded.get(key)
        if want and got and want != got:
            out.append(f"{key} 가 다릅니다 (기록 {got} · 지금 {want})")
    return out


def _depends_mismatch(recorded: dict, current: dict) -> list:
    """앞 단계가 기록된 뒤 바뀌었나. 기록이 없으면 묻지 않는다."""
    dep = recorded.get("depends")
    if not isinstance(dep, dict):
        return []
    out = []
    for key, was in dep.items():
        now = current.get(key)
        if was and now and was != now:
            out.append(f"{key} 가 바뀌었습니다")
    return out


def checkpoint_state(round_id: str, stage: str, report: Report | None = None,
                     base: Path | None = None, outdir: Path | None = None,
                     expect: dict | None = None, settings=None,
                     current: dict | None = None) -> Checkpoint:
    """다섯 문을 지난다 — 있나 · 읽히나 · JSON 인가 · 검증을 지나나 ·
    출처가 맞나.

    **검증기를 새로 쓰지 않는다** (§1-8). 1·2단계는 `parse_stage()`,
    3단계는 `parse_moderator_result()` — 보관할 때 지난 그 문이다.

    `report` 가 없으면 내용 검증을 **하지 않고** 존재만 본다. 6-F-4 부터
    `workflow()` 는 회차 자료 없이도 불릴 수 있어야 하고(§1-41), 그 경로의
    뜻을 바꾸지 않는다 — 대신 상태가 `unverified` 로 남아 "확인하지 않았다"
    는 사실이 드러난다.
    """
    out = Checkpoint(stage=stage)
    try:
        out.path = checkpoint_path(round_id, stage, base, outdir)
    except KeyError:
        out.reasons.append(f"모르는 단계입니다 ({stage})")
        return out
    if not out.path.is_file():
        out.state = CP_MISSING
        return out

    out.sha256 = _file_sha(out.path)
    if not out.sha256:
        out.state = CP_UNREADABLE
        out.reasons.append("파일을 읽지 못했습니다")
        return out
    out.recorded = stage_record(round_id, stage, base)

    # ---- 내용 검증 -------------------------------------------------------
    if report is None:
        out.state = CP_UNVERIFIED
        out.reasons.append("회차 자료가 없어 내용을 확인하지 않았습니다")
    else:
        why = _verify_content(out, stage, report, settings)
        if why:
            out.reasons.extend(why)
            return out

    # ---- 출처 -----------------------------------------------------------
    bad = []
    if stage in (STAGE_A, STAGE_B):
        bad += _expect_mismatch(out.recorded, expect or {}, PACKET_KEYS)
    elif stage == STAGE_RESULT:
        bad += _expect_mismatch(out.recorded, expect or {},
                                ("moderator_prompt_version",))
    bad += _depends_mismatch(out.recorded, current or {})
    if bad:
        out.state = CP_STALE
        out.reasons.extend(bad)
        return out

    was = out.recorded.get("sha256")
    if was and was != out.sha256:
        # 사람이 고쳤을 수 있다. 내용은 검증을 지났으므로 **버리지 않고**
        # 출처를 보증하지 않는다고만 적는다 — 고친 것을 이유로 돈이 드는
        # 재실행을 강요하지 않는다.
        out.state = CP_UNVERIFIED
        out.reasons.append("보관한 뒤 파일이 바뀌었습니다")
        return out
    if out.state == CP_UNVERIFIED:
        return out
    if not was:
        # **행이 있다는 것으로는 부족하다.** 실패한 시도만 적힌 행이 있을 수
        # 있고(`last_attempt`), 그것을 출처로 치면 확인하지 않은 파일이
        # `complete` 로 승격된다. 우리가 그 파일을 저장하며 해시를 적은
        # 경우에만 보증한다.
        out.state = CP_UNVERIFIED
        out.reasons.append("출처 기록이 없습니다 (수동 경로이거나 옛 파일)")
        return out
    out.state = CP_COMPLETE
    return out


def _verify_content(cp: Checkpoint, stage: str, report: Report,
                    settings=None) -> list:
    """내용 검증. 통과하면 `cp.state` 를 잠정 통과로 두고 빈 목록을 준다."""
    path = cp.path
    if stage in STAGE_ROLE:
        opinions, res = load_stage(report.round_id or "", STAGE_ROLE[stage],
                                   report, base=_base_of(path, stage))
        if res.errors:
            cp.state = CP_INVALID
            return [str(i) for i in res.errors[:4]]
        cp.matches = len(opinions)
        return []
    if stage == STAGE_RESULT:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            cp.state = CP_UNREADABLE
            return [str(exc)]
        data, _array, res = parse_moderator_result(text, report, settings)
        if data is None or not res.success:
            cp.state = CP_INVALID
            return [str(i) for i in res.errors[:4]]
        cp.matches = len(report.matches)
        return []
    if stage == STAGE_INPUT:
        # 조립본은 markdown 이다. 내용 검증은 **앞 단계가 이미 했고**
        # (`collect_opinions` 가 A·B 를 다시 검증한다) 여기서는 비어
        # 있지 않은지만 본다 — 같은 검사를 두 번 하지 않는다.
        try:
            body = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            cp.state = CP_UNREADABLE
            return [str(exc)]
        if not body.strip():
            cp.state = CP_INVALID
            return ["조립본이 비어 있습니다"]
        cp.matches = len(report.matches)
        return []
    if stage == STAGE_APPLY:
        # 반영본은 **매 실행 다시 만들어진다** (`_run_stages` 가 건너뛰지
        # 않는다). 그래서 재개 결정에 쓰이지 않고, 깊은 검증을 해도 달라질
        # 판단이 없다 — 읽히고 회차가 맞는지만 본다.
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            cp.state = CP_UNREADABLE
            return [str(exc)]
        rid = str(report.round_id or "")
        got = str((data or {}).get("round", "")) if isinstance(data, dict) \
            else ""
        if rid and got and rid != got:
            cp.state = CP_INVALID
            return [f"회차가 다릅니다 (파일 {got} · 지금 {rid})"]
        rows = (data or {}).get("matches") if isinstance(data, dict) else None
        cp.matches = len(rows) if isinstance(rows, list) else 0
        return []
    cp.state = CP_INVALID
    return [f"모르는 단계입니다 ({stage})"]


def _base_of(path: Path | None, stage: str) -> Path | None:
    """체크포인트 경로에서 `base` 를 되찾는다 (`load_stage` 에 넘기려고).

    `panel_work/<회차>/<파일>` 의 두 단계 위가 `base` 다. 기본 위치면
    `None` 을 돌려 기존 동작 그대로 간다.
    """
    if path is None or stage not in STAGE_ROLE:
        return None
    from .settings import ROOT
    root = path.parent.parent.parent
    try:
        return None if root == ROOT else root
    except OSError:
        return None


@dataclass
class StagePlan:
    """한 단계의 재개 결정. **판정과 사유를 함께 담는다.**"""
    stage: str = ""
    decision: str = RERUN
    checkpoint: Checkpoint | None = None
    reason: str = ""

    @property
    def reuse(self) -> bool:
        return self.decision == REUSE


@dataclass
class ResumePlan:
    round_id: str = ""
    stages: list = field(default_factory=list)

    def plan(self, stage: str) -> StagePlan | None:
        return next((s for s in self.stages if s.stage == stage), None)

    def reuse(self, stage: str) -> bool:
        row = self.plan(stage)
        return bool(row and row.reuse)

    @property
    def resume_from(self) -> str:
        """다시 돌려야 하는 **첫** 단계. 전부 재사용이면 빈 문자열."""
        row = next((s for s in self.stages if not s.reuse), None)
        return row.stage if row else ""

    def lines(self) -> list:
        out = []
        for row in self.stages:
            cp = row.checkpoint
            mark = "재사용" if row.reuse else "다시 실행"
            tail = f" — {row.reason}" if row.reason else ""
            out.append(f"  {row.stage}: {mark} "
                       f"({cp.state if cp else CP_MISSING}){tail}")
        return out


def resume_plan(report: Report | None, round_id: str = "",
                base: Path | None = None, outdir: Path | None = None,
                expect: dict | None = None, settings=None) -> ResumePlan:
    """어느 단계부터 다시 돌려야 하나. **모델을 부르지 않는다.**

    앞 단계를 다시 만들면 뒤 단계도 다시 만든다 (§14) — 옛 A 로 만든 C 를
    새 A 옆에 두면 한 회차 안에 두 시점이 섞인다.
    """
    rid = str(round_id or (report.round_id if report is not None else "") or "")
    out = ResumePlan(round_id=rid)
    current: dict = {}
    rerun: set = set()
    for stage in STAGE_ORDER:
        cp = checkpoint_state(rid, stage, report, base, outdir, expect,
                              settings, current)
        current[stage] = cp.sha256
        upstream = [s for s in STAGE_UPSTREAM[stage] if s in rerun]
        if upstream:
            rerun.add(stage)
            out.stages.append(StagePlan(
                stage=stage, decision=RERUN, checkpoint=cp,
                reason=f"앞 단계를 다시 만듭니다 ({', '.join(upstream)})"))
            continue
        if cp.usable:
            out.stages.append(StagePlan(
                stage=stage, decision=REUSE, checkpoint=cp,
                reason="; ".join(cp.reasons)))
            continue
        rerun.add(stage)
        out.stages.append(StagePlan(
            stage=stage, decision=RERUN, checkpoint=cp,
            reason="; ".join(cp.reasons) or _MISSING_KO.get(cp.state, "")))
    return out


_MISSING_KO = {CP_MISSING: "아직 없습니다"}


def force_rerun(plan: ResumePlan) -> ResumePlan:
    """모든 단계를 다시 실행으로 바꾼 **새 계획**을 준다 (§19).

    **판정 로직을 복제하지 않는다** — 이미 만든 계획의 결정만 뒤집고
    체크포인트 상태는 그대로 실어 둔다. 무엇이 있었는지는 그대로 보이고,
    쓰지 않을 뿐이다. 원래 계획을 고치지 않으므로 부르는 쪽이 둘을
    견줄 수 있다.
    """
    return ResumePlan(round_id=plan.round_id, stages=[
        StagePlan(stage=s.stage, decision=RERUN, checkpoint=s.checkpoint,
                  reason="다시 실행하도록 요청했습니다")
        for s in plan.stages])


@dataclass
class Stage:
    """워크플로 한 칸. **값은 전부 파일에서 읽는다.**"""
    key: str = ""
    title: str = ""
    state: str = ""
    done: bool = False
    path: Path | None = None
    detail: str = ""
    attachments: tuple = ()
    todo: str = ""
    # 6-F-12. `report` 를 준 호출에서만 채워진다 — 없으면 `None` 이고,
    # 그 사실이 곧 "내용을 확인하지 않았다" 는 뜻이다 (§1-5).
    checkpoint: Checkpoint | None = None

    def line(self) -> str:
        mark = "✔" if self.done else "·"
        tail = f" — {self.detail}" if self.detail else ""
        return f"  {mark} {self.title}: {self.state}{tail}"


@dataclass
class Workflow:
    round_id: str = ""
    stages: list = field(default_factory=list)
    export_dir: Path | None = None
    export_files: tuple = ()

    @property
    def done(self) -> bool:
        return all(s.done for s in self.stages)

    def stage(self, key: str) -> Stage | None:
        return next((s for s in self.stages if s.key == key), None)

    def next_stage(self) -> Stage | None:
        return next((s for s in self.stages if not s.done), None)


def _json_count(path: Path) -> str:
    """보관본에 경기가 몇 개 들어 있나. **못 읽으면 지어내지 않는다.**"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "내용을 읽지 못했습니다"
    if isinstance(data, list):
        return f"{len(data)}경기"
    if isinstance(data, dict):
        rows = data.get("matches")
        if isinstance(rows, list):
            return f"{len(rows)}경기"
    return "경기 수를 읽지 못했습니다"


def export_files(round_id: str, outdir: Path | None = None) -> list[Path]:
    """`[3]` 이 만든 자료 파일들. **폴더를 읽는다 — 이름을 적어 두지 않는다.**

    회차마다 `02_경기자료_3of7.md` 처럼 개수와 이름이 달라지므로, 코드에
    적어 두면 조용히 낡아 사용자에게 없는 파일을 첨부하라고 말하게 된다.
    """
    folder = Path(outdir) if outdir else panelexport.round_dir(round_id)
    if not folder.is_dir():
        return []
    return sorted((p for p in folder.glob("*.md") if p.is_file()),
                  key=lambda p: p.name)


def _by_prefix(files, prefix: str) -> tuple:
    return tuple(p for p in files if p.name.startswith(prefix))


def workflow(round_id: str, base: Path | None = None,
             outdir: Path | None = None, report: Report | None = None,
             expect: dict | None = None, settings=None) -> Workflow:
    """이 회차가 어디까지 왔나.

    **`report` 가 없으면 파일이 있느냐만 본다.** 회차 자료(artifact)도
    네트워크도 필요하지 않고, 그래서 수집 전에도 부를 수 있다 (§1-41).

    `report` 를 주면 6-F-12 의 다섯 문을 지난 결과가 실린다 — 내용이
    검증되고 출처가 대조된다. 그때 `done` 은 '파일이 있다' 가 아니라
    **'그대로 써도 된다'** 이고, 아니면 사유가 `detail` 에 남는다.
    """
    rid = str(round_id or "")
    plan = (resume_plan(report, rid, base, outdir, expect, settings)
            if report is not None else None)
    files = export_files(rid, outdir)
    folder = Path(outdir) if outdir else panelexport.round_dir(rid)

    # 첨부 목록. 1·2단계는 `02_경기자료*`, 3단계는 조립본(있으면)과 규격서다.
    material = _by_prefix(files, "02_")
    guide = _by_prefix(files, "00_")
    schema = _by_prefix(files, "04_")
    completed = folder.joinpath(COMPLETED_SHEET)
    sheet = ((completed,) if completed.is_file()
             else tuple(p for p in _by_prefix(files, "03_")))

    a_path = path_for(rid, panel.DATA_ANALYST, base)
    b_path = path_for(rid, panel.MATCHUP_ANALYST, base)
    mod_path = moderator_result_path(rid, base)
    panel_path = panelimport.inbox_dir(base).joinpath(
        f"{rid}{panelimport.FILE_SUFFIX}")

    def attach_note(paths) -> str:
        if not paths:
            return ("첨부할 자료가 없습니다 — 먼저 [3] 으로 회차 자료를 "
                    "내보내십시오")
        return "첨부: " + ", ".join(p.name for p in paths)

    stages = [
        Stage(key=STAGE_A, title="1단계 (데이터 분석가)",
              state=A_COMPLETE if a_path.is_file() else A_NOT_STARTED,
              done=a_path.is_file(),
              path=a_path if a_path.is_file() else None,
              detail=_json_count(a_path) if a_path.is_file() else "",
              attachments=guide + material,
              todo=("클로드 대화 #1 에서 1단계를 돌리고 응답 배열을 "
                    "[6] → [1] 로 넣으십시오. " + attach_note(material))),
        Stage(key=STAGE_B, title="2단계 (맞대결·전술 분석가)",
              state=B_COMPLETE if b_path.is_file() else B_NOT_STARTED,
              done=b_path.is_file(),
              path=b_path if b_path.is_file() else None,
              detail=_json_count(b_path) if b_path.is_file() else "",
              attachments=guide + material,
              todo=("클로드 대화 #2 에서 2단계를 돌리고 응답 배열을 "
                    "[6] → [2] 로 넣으십시오. 1단계와 **다른 대화**입니다. "
                    + attach_note(material))),
        Stage(key=STAGE_INPUT, title="3단계 자료 조립",
              state=(MODERATOR_INPUT_READY if completed.is_file()
                     else MODERATOR_INPUT_NOT_BUILT),
              done=completed.is_file(),
              path=completed if completed.is_file() else None,
              detail=COMPLETED_SHEET if completed.is_file() else "",
              attachments=(),
              todo="[6] → [3] 으로 1·2단계를 조립하십시오."),
        Stage(key=STAGE_RESULT, title="3단계 결과 보관",
              state=(MODERATOR_RESULT_SAVED if mod_path.is_file()
                     else MODERATOR_RESULT_NOT_SAVED),
              done=mod_path.is_file(),
              path=mod_path if mod_path.is_file() else None,
              detail=_json_count(mod_path) if mod_path.is_file() else "",
              attachments=sheet + schema,
              todo=("클로드 대화 #3 에서 3단계를 돌리고 응답 배열을 "
                    "[6] → [4] 로 넣으십시오. " + attach_note(sheet + schema))),
        Stage(key=STAGE_APPLY, title="리포트 반영",
              state=(PANEL_RESULT_COMPLETE if panel_path.is_file()
                     else PANEL_RESULT_NOT_APPLIED),
              done=panel_path.is_file(),
              path=panel_path if panel_path.is_file() else None,
              detail=_json_count(panel_path) if panel_path.is_file() else "",
              attachments=(),
              todo=("[6] → [5] 로 보관해 둔 1·2·3단계 결과를 함께 "
                    "반영하십시오.")),
    ]
    if plan is not None:
        _apply_plan(stages, plan)
    return Workflow(round_id=rid, stages=stages, export_dir=folder,
                    export_files=tuple(files))


# 파일은 있는데 그대로 쓸 수 없는 상태. **단계마다 이름을 만들지 않는다** —
# 뜻이 단계에 달려 있지 않기 때문이다.
CHECKPOINT_STALE = "CHECKPOINT_STALE"
CHECKPOINT_INVALID = "CHECKPOINT_INVALID"
CHECKPOINT_UNREADABLE = "CHECKPOINT_UNREADABLE"
CHECKPOINT_SUPERSEDED = "CHECKPOINT_SUPERSEDED"   # 자신은 멀쩡한데 앞이 바뀐다

_CP_STATE_NAME = {CP_STALE: CHECKPOINT_STALE,
                  CP_INVALID: CHECKPOINT_INVALID,
                  CP_UNREADABLE: CHECKPOINT_UNREADABLE}


def _apply_plan(stages: list, plan: ResumePlan) -> None:
    """검증·출처 결과를 단계 줄에 겹친다. **`report` 를 준 호출에만.**

    `report` 없는 호출의 출력은 한 글자도 바뀌지 않는다 (§1-41).
    """
    for st in stages:
        row = plan.plan(st.key)
        if row is None or row.checkpoint is None:
            continue
        cp = row.checkpoint
        st.checkpoint = cp
        st.done = row.reuse
        if not cp.exists:
            continue
        if not row.reuse:
            st.state = _CP_STATE_NAME.get(cp.state, CHECKPOINT_SUPERSEDED)
            st.detail = row.reason or st.detail
        elif row.reason:
            st.detail = (f"{st.detail} · {row.reason}" if st.detail
                         else row.reason)


def workflow_lines(wf: Workflow) -> list[str]:
    """화면에 낼 줄들. **판정하지 않고 상태와 다음 할 일만 적는다.**"""
    lines = [f"회차 {wf.round_id or '(미상)'} 진행 상태"]
    lines += [s.line() for s in wf.stages]
    if not wf.export_files:
        lines.append(f"  자료 폴더에 파일이 없습니다 — {wf.export_dir}")
    nxt = wf.next_stage()
    if nxt is None:
        lines.append("  다음 할 일: 없습니다 — 리포트까지 끝났습니다.")
    else:
        lines.append(f"  다음 할 일: {nxt.todo}")
    return lines


__all__ = [
    "WORK_DIRNAME", "ROLE_FILES", "ROLE_ALIASES", "COMPLETED_SHEET",
    "MODERATOR_RESULT_FILE",
    "StageResult", "BuildResult", "work_dir", "path_for", "resolve_role",
    "moderator_result_path", "parse_stage", "save_stage", "load_stage",
    "collect_opinions", "build_completed_sheet", "opinion_count",
    "report_lines", "parse_moderator_result", "save_moderator_result",
    "Stage", "Workflow", "workflow", "workflow_lines", "export_files",
    # 6-F-12 — 체크포인트·출처·재개
    "MANIFEST_FILE", "MANIFEST_VERSION", "STAGE_ORDER", "STAGE_UPSTREAM",
    "STAGE_ROLE", "PACKET_KEYS",
    "CP_MISSING", "CP_UNREADABLE", "CP_INVALID", "CP_STALE",
    "CP_UNVERIFIED", "CP_COMPLETE", "CP_USABLE",
    "STAGE_COMPLETE", "STAGE_FAILED", "STAGE_FAILED_LIMIT",
    "CHECKPOINT_STALE", "CHECKPOINT_INVALID", "CHECKPOINT_UNREADABLE",
    "CHECKPOINT_SUPERSEDED",
    "REUSE", "RERUN", "Checkpoint", "StagePlan", "ResumePlan",
    "manifest_path", "read_manifest", "stage_record", "record_stage",
    "force_rerun",
    # 6-F-14 — 세 보관본을 Panel Result 하나로
    "APPLY_SOURCE", "assemble_panel_result", "record_applied",
    "checkpoint_path", "checkpoint_state", "resume_plan", "now_utc",
    "A_NOT_STARTED", "A_COMPLETE", "B_NOT_STARTED", "B_COMPLETE",
    "MODERATOR_INPUT_NOT_BUILT", "MODERATOR_INPUT_READY",
    "MODERATOR_RESULT_NOT_SAVED", "MODERATOR_RESULT_SAVED",
    "PANEL_RESULT_NOT_APPLIED", "PANEL_RESULT_COMPLETE",
    "STAGE_A", "STAGE_B", "STAGE_INPUT", "STAGE_RESULT", "STAGE_APPLY",
]
