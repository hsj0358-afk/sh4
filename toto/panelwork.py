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
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
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

# 붙여넣기 입력의 경기 번호 키. 1·2·3단계 출력이 전부 이 이름을 쓴다.
STAGE_NO = panelpaste.PASTE_NO


def work_dir(round_id: str, base: Path | None = None) -> Path:
    from .settings import ROOT
    root = Path(base) if base is not None else ROOT
    return root.joinpath(WORK_DIRNAME, str(round_id or "unknown"))


def resolve_role(name: str) -> str:
    """사람이 적은 이름 → 역할 식별자. 모르면 빈 문자열."""
    return ROLE_ALIASES.get((name or "").strip().lower(), "")


def path_for(round_id: str, role: str, base: Path | None = None) -> Path:
    return work_dir(round_id, base).joinpath(ROLE_FILES[role])


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
    path = path_for(report.round_id or "unknown", role, base)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        out.add(panelimport.ERROR, "STAGE_NOT_SAVED",
                f"파일을 쓰지 못했습니다: {exc}", field=str(path))
        return out
    out.path = path
    return out


def load_stage(round_id: str, role: str, report: Report,
               base: Path | None = None):
    """보관본 → (경기번호 → `PanelOpinion`, 결과). 없으면 사유를 담는다.

    **저장할 때와 같은 검증을 다시 지난다** — 파일이 손으로 고쳐졌을 수
    있고, 그때 조용히 통과하면 조립이 틀린 채로 나간다.
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
        return {}, out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        out.add(panelimport.ERROR, "UNREADABLE", str(exc), field=str(path))
        return {}, out
    opinions, _data, parsed = parse_stage(text, role, report)
    parsed.path = path if not parsed.errors else None
    return opinions, parsed


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
    try:
        target.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            panelexport.moderator_data_sheet(round_id, payloads,
                                             opinions_by_no=merged),
            encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        out.add(panelimport.ERROR, "SHEET_NOT_WRITTEN",
                f"파일을 쓰지 못했습니다: {exc}", field=str(path))
        return out
    out.path = path
    return out


def opinion_count(report: Report, base: Path | None = None) -> dict:
    """어느 단계까지 보관돼 있나. 화면에 한 줄로 보여 주려고 쓴다."""
    state = {}
    for role in panel.ROLES:
        path = path_for(report.round_id or "", role, base)
        state[role] = path.is_file()
    return state


__all__ = [
    "WORK_DIRNAME", "ROLE_FILES", "ROLE_ALIASES", "COMPLETED_SHEET",
    "StageResult", "BuildResult", "work_dir", "path_for", "resolve_role",
    "parse_stage", "save_stage", "load_stage", "collect_opinions",
    "build_completed_sheet", "opinion_count", "report_lines",
]
