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

# 3단계 결과 보관본 (Phase 6-F-4). 클로드가 돌려준 **배열 그대로**이고
# canonical Panel Result 가 아니다 — 그쪽은 `[4]` 가 `panel_results/` 에
# 만든다. 둘을 같은 파일로 두면 '모델이 무엇을 말했나' 를 되짚을 수 없다.
MODERATOR_RESULT_FILE = "moderator_result.json"

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

    path = moderator_result_path(report.round_id or "unknown", base)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(array, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        out.add(panelimport.ERROR, "MODERATOR_RESULT_NOT_WRITTEN",
                f"파일을 쓰지 못했습니다: {exc}", field=str(path))
        return None, out
    return path, out


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
             outdir: Path | None = None) -> Workflow:
    """이 회차가 어디까지 왔나. **파일이 있느냐만 본다.**

    회차 자료(artifact)도 네트워크도 필요하지 않다 — 그래서 수집 전에도
    부를 수 있고, 상태를 따로 저장하지 않으므로 실제와 어긋날 수가 없다.
    """
    rid = str(round_id or "")
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
              todo=("[6] → [5] 로 보관해 둔 3단계 결과를 반영하십시오 "
                    "(기존 [4] 와 같은 경로입니다).")),
    ]
    return Workflow(round_id=rid, stages=stages, export_dir=folder,
                    export_files=tuple(files))


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
    "A_NOT_STARTED", "A_COMPLETE", "B_NOT_STARTED", "B_COMPLETE",
    "MODERATOR_INPUT_NOT_BUILT", "MODERATOR_INPUT_READY",
    "MODERATOR_RESULT_NOT_SAVED", "MODERATOR_RESULT_SAVED",
    "PANEL_RESULT_NOT_APPLIED", "PANEL_RESULT_COMPLETE",
    "STAGE_A", "STAGE_B", "STAGE_INPUT", "STAGE_RESULT", "STAGE_APPLY",
]
