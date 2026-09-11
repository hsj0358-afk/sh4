"""Panel Result JSON 가져오기 (Phase 4-B).

Phase 4-A 가 프로그램 → 클로드 채팅 방향의 인터페이스라면, 이 모듈은
**반대 방향**이다.

    클로드 채팅 프로젝트 → 260050_panel_result.json → 프로그램

## 검증을 새로 쓰지 않는다

Phase 3 가 이미 같은 응답을 검증하고 있다 — API 로 받든 파일로 받든
**같은 자료이므로 같은 문을 지나야 한다.** 그래서 경기 하나의 내용 검증은
`panel.parse_opinion()` 과 `moderator.parse_result()` 를 **그대로 부른다.**
dict 를 다시 JSON 문자열로 직렬화해서 넘기는 것이 돌아가는 것처럼 보이지만,
그렇게 해야 두 경로가 **한 글자도 갈라지지 않는다** — 검증 규칙을 여기에
베끼면 한쪽만 고쳐져 조용히 어긋난다(이 프로젝트가 여러 번 겪은 일이다).

그 두 함수가 이미 막는 것:

  · 정수가 아닌 스코어 (`"2"` · `1.5` · `True` · 음수)
  · payload 에 없는 근거 ID
  · `distribution` 의 count 합 ≠ `simulations`
  · 분포에 없는 스코어를 채택
  · `adopted_from` 이 가리키는 역할이 그 스코어를 내지 않음
  · 스코어를 채택했는데 `conclusion` 이 빔

이 모듈이 새로 더하는 것은 **회차 단위**의 문이다 — schema_version · round ·
경기 수 · match_id 중복/누락/미상 · 팀 정체성 · 역할 이름 · 금지 필드 ·
근거 범위(다른 경기의 ID) · 감사(audit).

## 판정하지 않는 것

**패널 의견의 내용을 평가하지 않는다.** 어느 분석가가 더 옳은지, 합의도가
얼마인지, 신뢰도가 몇 %인지 만들지 않는다. 이 계층이 묻는 것은 하나다 —
**"구조적으로 유효한 Panel Result 인가?"**

**분포는 확률이 아니다.** `count / simulations` 를 계산하지 않는다 (§1-10).
횟수를 그대로 보존하고, 백분율·confidence·consensus 로 바꾸지 않는다.

**승무패를 만들지 않는다.** `2-1` 을 '홈승' 으로 옮기는 helper 가 없다.

## 부분 import 를 허용하지 않는다

한 경기라도 필수 구조가 깨지면 **전체를 정상으로 취급하지 않는다.** 잘못된
패널 결과가 일부 경기만 리포트에 섞이는 것을 막기 위해서다. 다만 어느
경기가 왜 문제인지는 전부 기록한다 — 사용자가 고쳐 다시 넣을 수 있어야 한다.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from . import moderator, panel
from .models import Match, ModeratorResult, PanelOpinion, PanelRun, Report

log = logging.getLogger("toto")

# 1.0 은 계속 읽는다. 1.1 은 `panel_status` 를 쓰는 파일이다 — 새 칸이 없는
# 1.1 파일은 1.0 과 완전히 같은 뜻이고, 1.0 파일이 `panel_status` 를 쓰면
# 경고만 남기고 받아 준다(막을 이유가 없다).
SCHEMA_VERSION = "1.1"
SUPPORTED_VERSIONS = ("1.0", "1.1")

# 패널 실행 상태. **새 어휘를 만들지 않는다** — §1-6 의 네 상태 그대로다.
#
# 나누는 이유는 하나다. `simulations=0 · distribution=[] · adopted=null` 은
# 지금도 통과하지만, 그것이 **"토론했는데 못 골랐다"** 인지 **"애초에 돌리지
# 않았다"** 인지 구분할 자리가 없었다. 260052 의 9·13·14번이 뒤쪽인데
# 커버리지에는 앞쪽으로 셌다.
STATUS_OK = "ok"
STATUS_PARTIAL = "부분"
STATUS_FAILED = "실패"
STATUS_SKIPPED = "생략"
PANEL_STATUSES = (STATUS_OK, STATUS_PARTIAL, STATUS_FAILED, STATUS_SKIPPED)
# `ok` 가 아닌 상태 — 분석가·사회자 내용을 요구하지 않는다.
NOT_RUN_STATUSES = (STATUS_PARTIAL, STATUS_FAILED, STATUS_SKIPPED)


def status_of(run) -> str:
    """`PanelRun.status` 에서 상태 낱말만. 모르면 `ok` 로 본다.

    상태를 `"생략 (사유)"` 처럼 **낱말 + 괄호 사유**로 적는 것은 이 프로젝트가
    §1-6 에서 쭉 써 온 형식이고, `render._panel_block` 도 이미 그 앞 낱말을
    본다. 새 필드를 만들지 않고 그 규칙을 그대로 읽는다.
    """
    head = (getattr(run, "status", "") or "").split(" (")[0].strip()
    return head if head in PANEL_STATUSES else STATUS_OK

# 이 파일이 만든 결과라는 표시. Phase 3 의 LLM 캐시와 **섞지 않는다** —
# 저쪽은 프로그램이 API 를 부르던 구조의 저장소이고, 이쪽은 사람이 채팅에서
# 만들어 온 외부 산출물이다.
IMPORT_SOURCE = "chat-import"

DATA_ROLE = moderator.DATA_ROLE
MATCHUP_ROLE = moderator.MATCHUP_ROLE
MODERATOR_ROLE = "moderator"
ANALYST_ROLES = (DATA_ROLE, MATCHUP_ROLE)

ERROR, WARNING = "ERROR", "WARNING"

# 패널이 만들어서는 안 되는 칸. 자리가 없어 조용히 버려지는 것과 별개로,
# **들어왔다는 사실 자체를 오류로 잡는다** — 지침을 어긴 응답이라는 뜻이고
# 그런 응답의 다른 칸도 믿기 어렵다.
FORBIDDEN_FIELDS = (
    "winner", "result", "wdl", "pick", "lean", "recommendation",
    "confidence", "favorite", "toss_up", "strength", "probability",
    "probabilities", "consensus_score", "consensus", "expected_winner",
    "score_probability", "panel_confidence",
)

# 시장은 분석가가 아니다 (§1-9 불변조건 1). 역할 이름으로도 들어올 수 없다.
FORBIDDEN_ROLES = ("market_reference", "market_analyst", "market", "moderator")

# 경기를 어떻게 이었나. **외부 계약과 내부 식별자를 나누는 자리다.**
#
# 수동 Panel 경로에는 `match_id` 가 없다 — `PanelPayload` 에 그 칸이 없어서
# (`panel.py`) 1·2·3단계 자료 어디에도 실리지 않는다. 채팅이 줄 수 있는
# 식별자는 `match_number` 와 팀 이름뿐이고, 회차 안에서 번호는 유일하므로
# 그것으로 경기 하나가 정해진다. `match_id` 는 프로그램이 시즌 색인에서
# 스스로 구한다 (`_match_key`).
LINK_ID = "id"
LINK_NUMBER = "number"


@dataclass(frozen=True)
class Issue:
    """검증에서 나온 문제 하나.

    `severity` 는 둘뿐이다 — `ERROR` 는 안전하게 가져올 수 없다는 뜻이고,
    `WARNING` 은 가져올 수는 있으나 사람이 확인해야 한다는 뜻이다.
    임의의 문턱으로 '나쁜 패널' 을 판정하지 않는다.
    """
    severity: str
    code: str
    message: str
    match_id: str = ""
    match_no: int | None = None
    field: str = ""

    def __str__(self) -> str:
        where = " ".join(x for x in (
            f"[{self.match_no:02d}]" if self.match_no else "",
            f"match_id={self.match_id}" if self.match_id else "",
            self.field) if x)
        return f"{self.severity} {self.code}: {self.message}" + (
            f" ({where})" if where else "")


@dataclass
class PanelImportResult:
    """가져오기 결과. **원본과 검증 결과를 분리해 담는다.**

    `runs` 는 검증을 통과한 경기의 `PanelRun` 이고, `success` 가 False 면
    호출부는 그것을 리포트에 붙이지 않는다 (부분 import 금지).
    """
    success: bool = False
    round_id: str = ""
    schema_version: str = ""
    generated_at: str = ""
    expected_matches: int = 0
    imported_matches: int = 0
    issues: list[Issue] = field(default_factory=list)
    runs: dict[int, PanelRun] = field(default_factory=dict)   # 경기 번호 → 결과
    # 검증을 통과한 경기 전부. `runs` 와 다르다 — `runs` 는 **회차 전체가
    # 성공했을 때만** 채워지는 부착용 결과이고, 이쪽은 실패한 회차에서도
    # "무엇이 읽혔나" 를 남긴다. 4-C 감사가 이것을 읽는다.
    parsed: dict[int, PanelRun] = field(default_factory=dict)
    audit: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == WARNING]

    def add(self, severity: str, code: str, message: str, **where) -> None:
        self.issues.append(Issue(severity, code, message, **where))

    def status_line(self) -> str:
        """§1-6 어휘. 실패와 부분을 뭉뚱그리지 않는다."""
        if not self.issues and self.success:
            return (f"ok ({self.imported_matches}/{self.expected_matches}경기, "
                    f"{self.round_id}회차)")
        if self.success:
            return (f"부분 ({self.imported_matches}/{self.expected_matches}경기 "
                    f"가져옴, 확인 필요 {len(self.warnings)}건)")
        return (f"실패 (오류 {len(self.errors)}건, 경고 "
                f"{len(self.warnings)}건 — 가져오지 않았습니다)")


# ==========================================================================
# 받은 파일을 두는 곳
# ==========================================================================
# 사용자가 클로드 채팅에서 받은 JSON 을 넣는 폴더. 경로를 매번 입력받지
# 않으려고 **한 자리로 정한다** — 여러 곳을 뒤지면 어느 파일이 쓰였는지
# 사용자가 알 수 없다.
INBOX_DIRNAME = "panel_results"
FILE_SUFFIX = "_panel_result.json"


def inbox_dir(base: Path | None = None) -> Path:
    from .settings import ROOT
    # `/` 대신 `joinpath` 를 쓴다 — 경로 결합도 AST 로는 나눗셈이라,
    # "분포를 확률로 바꾸지 않는다" 를 지키는 검사에 걸린다 (§1-15).
    return (Path(base) if base is not None else ROOT).joinpath(INBOX_DIRNAME)


def find_panel_files(base: Path | None = None) -> list[Path]:
    """`panel_results/` 의 Panel Result 파일들. 회차 번호 순으로.

    **임의로 하나를 고르지 않는다** — 목록을 돌려주고 고르는 것은 부르는
    쪽 몫이다. 여러 개일 때 조용히 하나를 쓰면 엉뚱한 회차를 붙일 수 있다.
    """
    folder = inbox_dir(base)
    if not folder.is_dir():
        return []
    return sorted((p for p in folder.glob("*.json") if p.is_file()),
                  key=lambda p: (p.name, p))


def round_of(path: Path) -> str:
    """파일에서 회차를 읽는다. 파일 이름이 아니라 **내용**이 기준이다.

    이름은 바뀔 수 있고 내용의 `round` 가 실제로 검증에 쓰이는 값이다.
    읽지 못하면 이름에서 짐작하되, 그것도 안 되면 빈 문자열이다.
    """
    data, _why = load(path)
    if isinstance(data, dict):
        found = _text(str(data.get("round") or ""))
        if found:
            return found
    stem = path.name[:-len(FILE_SUFFIX)] if path.name.endswith(FILE_SUFFIX) \
        else path.stem
    return stem if stem.isdigit() else ""


# ==========================================================================
# 읽기
# ==========================================================================
def load(path: Path | str) -> tuple[dict | None, str]:
    """파일 → dict. **사용자가 지정한 파일만 읽는다.**

    JSON 안의 문자열을 경로로 해석하거나 실행하지 않는다 — 이 파일은 모델이
    만든 외부 텍스트다.
    """
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"파일을 읽지 못했습니다: {exc}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"JSON 파싱 실패: {exc}"
    if not isinstance(data, dict):
        return None, "최상위가 JSON 객체가 아닙니다"
    return data, ""


# ==========================================================================
# 작은 검사들
# ==========================================================================
def _forbidden_in(obj, path: str) -> list[tuple[str, str]]:
    """중첩된 어디에 있든 금지 칸을 찾는다. (경로, 이름) 목록."""
    found = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else str(key)
            if key in FORBIDDEN_FIELDS:
                found.append((here, key))
            found += _forbidden_in(value, here)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            found += _forbidden_in(value, f"{path}[{i}]")
    return found


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _round_equal(a, b) -> bool:
    """회차 비교. 문자열/숫자가 섞여도 **같은 회차인지만** 본다.

    형식이 달라 헷갈리는 경우를 조용히 통과시키지 않으려고, 양쪽을 문자열로
    맞춰 놓고 비교한다. 빈 값은 어느 쪽이든 불일치다.
    """
    sa, sb = _text(str(a)) if a is not None else "", \
        _text(str(b)) if b is not None else ""
    return bool(sa) and sa == sb


def _match_key(match: Match, report: Report) -> str:
    """이 경기의 authoritative id. 없으면 빈 문자열이다.

    Phase 4-A 와 **같은 규칙**으로 시즌 색인에서 찾는다 — 경기자료 MD 에
    적힌 `match_id` 와 여기서 찾는 값이 달라지면 안 된다.
    """
    from .match_material import _status_of
    _status, sm = _status_of(match, report)
    return getattr(sm, "match_id", "") or ""


# ==========================================================================
# 경기 하나
# ==========================================================================
def _opinion(block, role: str, allowed_ids, result: PanelImportResult,
             where: dict) -> PanelOpinion | None:
    """분석가 의견 하나. **`panel.parse_opinion()` 을 그대로 쓴다.**"""
    if not isinstance(block, dict):
        result.add(ERROR, "MISSING_ANALYST", f"{role} 블록이 없습니다",
                   field=role, **where)
        return None
    declared = _text(block.get("role"))
    if declared and declared != role:
        result.add(ERROR, "ROLE_MISMATCH",
                   f"role 이 '{declared}' 로 적혀 있습니다 (기대: {role})",
                   field=f"{role}.role", **where)
        return None
    if declared in FORBIDDEN_ROLES and declared != role:
        result.add(ERROR, "FORBIDDEN_ROLE",
                   f"'{declared}' 는 분석가 역할이 아닙니다",
                   field=f"{role}.role", **where)
        return None
    try:
        return panel.parse_opinion(json.dumps(block, ensure_ascii=False),
                                   role, allowed_ids, model=IMPORT_SOURCE,
                                   prompt_version=SCHEMA_VERSION)
    except panel.ValidationError as exc:
        code = ("UNKNOWN_EVIDENCE_ID" if "근거 ID" in str(exc)
                else "INVALID_ANALYST")
        result.add(ERROR, code, str(exc), field=role, **where)
        return None


def _moderator(block, opinions, allowed_ids, sims: int,
               result: PanelImportResult, where: dict) -> ModeratorResult | None:
    """사회자. **`moderator.parse_result()` 를 그대로 쓴다.**"""
    if not isinstance(block, dict):
        result.add(ERROR, "MISSING_MODERATOR", "moderator 블록이 없습니다",
                   field=MODERATOR_ROLE, **where)
        return None
    declared = _text(block.get("role"))
    if declared and declared != MODERATOR_ROLE:
        result.add(ERROR, "ROLE_MISMATCH",
                   f"moderator.role 이 '{declared}' 입니다",
                   field="moderator.role", **where)
        return None

    body = dict(block)
    if "simulations" not in body:
        # 설정값으로 대신 재되, **대신 쟀다는 사실을 남긴다.** 하드코딩 30 을
        # 쓰지 않는다 (라운드 수는 config 로 바꿀 수 있다).
        body["simulations"] = sum(
            d.get("count", 0) for d in (body.get("distribution") or [])
            if isinstance(d, dict) and isinstance(d.get("count"), int))
        result.add(WARNING, "SIMULATIONS_MISSING",
                   f"simulations 가 없어 distribution 합계로 대신했습니다 "
                   f"(설정값 {sims})", field="moderator.simulations", **where)

    order = tuple(allowed_ids)
    by_role = {o.role: o for o in opinions}
    shared, data_only, matchup_only = moderator.split_evidence(
        getattr(by_role.get(DATA_ROLE), "evidence_ids", ()),
        getattr(by_role.get(MATCHUP_ROLE), "evidence_ids", ()), order)
    try:
        return moderator.parse_result(
            json.dumps(body, ensure_ascii=False),
            panels_seen=tuple(o.role for o in opinions),
            shared=shared, data_only=data_only, matchup_only=matchup_only,
            allowed_ids=order,
            allowed_scores=moderator.proposed_scores(opinions),
            model=IMPORT_SOURCE, prompt_version=SCHEMA_VERSION)
    except moderator.ValidationError as exc:
        text = str(exc)
        if "근거 ID" in text:
            code = "UNKNOWN_EVIDENCE_ID"
        elif "adopted_from" in text:
            code = "ADOPTED_FROM_MISMATCH"
        elif "distribution" in text or "simulations" in text:
            code = "INVALID_DISTRIBUTION"
        elif "라운드에서도" in text or "낸 의견이 없습니다" in text:
            code = "ADOPTED_NOT_IN_DISTRIBUTION"
        else:
            code = "INVALID_MODERATOR"
        result.add(ERROR, code, text, field=MODERATOR_ROLE, **where)
        return None


def _check_adopted_from(declared, mod: ModeratorResult, opinions,
                        result: PanelImportResult, where: dict) -> None:
    """`adopted_from` 의 **의미**를 확인한다.

    정의(§5): 채택한 스코어와 **같은 스코어를 처음 제안한** 역할의 목록.

    `moderator.parse_result()` 는 두 가지를 한다 — 모델이 적은 역할이 그
    스코어를 내지 않았으면 **거부**하고(그건 ERROR 로 이미 나간다), 그 밖의
    경우 제안 집합에서 **다시 계산**한다. 그래서 저장된 값은 언제나 옳다.

    다만 여기서는 **모델이 보낸 원값**(`declared`)과 견준다. 다르면 조용히
    고쳐 준 것이 되므로 그 사실을 남긴다 — 지침을 어긴 응답이라는 뜻이고,
    같은 응답의 다른 칸도 확인해 볼 이유가 된다.
    """
    if mod.adopted_home is None:
        return
    proposals = moderator.proposed_scores(opinions)
    pair = (mod.adopted_home, mod.adopted_away)
    sent = {str(r) for r in (declared or []) if isinstance(r, str)}
    if sent == set(mod.adopted_from):
        return
    result.add(WARNING, "ADOPTED_FROM_RECOMPUTED",
               f"adopted_from 을 실제 원안으로 다시 정했습니다 — 파일 "
               f"{sorted(sent) or '[]'} → {list(mod.adopted_from) or '[]'} "
               f"(채택 {pair[0]}-{pair[1]}, 원안 "
               + " · ".join(f"{r} {h}-{a}"
                            for r, (h, a) in sorted(proposals.items())) + ")",
               field="moderator.adopted_from", **where)


def _check_evidence_scope(block, allowed_ids, result: PanelImportResult,
                          where: dict) -> None:
    """다른 경기의 근거 ID 를 쓰지 않았는지.

    근거 ID 는 **경기마다 다시 매겨진다** (`panel.evidence_rows`). 그래서
    '이 회차에 있는 ID' 가 아니라 **'이 경기에 있는 ID'** 여야 한다 —
    `parse_opinion`·`parse_result` 에 이 경기의 목록만 넘기므로 이미 걸리지만,
    근거가 0건인 경기에서 무엇이 잘못됐는지 분명히 하려고 따로 적는다.
    """
    if allowed_ids:
        return
    for name in (DATA_ROLE, MATCHUP_ROLE, MODERATOR_ROLE):
        part = block.get(name)
        ids = (part or {}).get("evidence_ids") if isinstance(part, dict) else None
        if ids:
            result.add(ERROR, "EVIDENCE_ABSENT_BUT_CITED",
                       f"이 경기에는 근거가 하나도 없는데 {list(ids)} 를 "
                       f"인용했습니다. 근거가 없으면 evidence_ids 는 [] 여야 "
                       f"합니다", field=f"{name}.evidence_ids", **where)


def _panel_status(block, version: str, result: PanelImportResult,
                  where: dict) -> tuple[str, str]:
    """(상태, 사유). 없으면 `ok` — 1.0 파일이 그대로 통과한다.

    `ok` 가 아니면 **사유를 반드시 적어야 한다.** 사유 없는 '생략' 은 "왜
    없는지" 를 남기라는 §1-6 과 어긋나고, 나중에 그 경기를 다시 볼 때
    수집 실패였는지 자료 부족이었는지 알 수 없다.
    """
    raw = block.get("panel_status")
    if raw is None:
        return STATUS_OK, ""
    status = _text(str(raw))
    if status not in PANEL_STATUSES:
        result.add(ERROR, "PANEL_STATUS_INVALID",
                   f"panel_status '{status}' 는 없는 상태입니다 "
                   f"(가능: {', '.join(PANEL_STATUSES)})",
                   field="panel_status", **where)
        return STATUS_OK, ""
    reason = _text(block.get("panel_status_reason"))
    if status != STATUS_OK:
        if version == "1.0":
            result.add(WARNING, "PANEL_STATUS_IN_1_0",
                       f"schema_version 1.0 파일이 panel_status 를 씁니다 — "
                       f"이 칸은 1.1 부터입니다 (읽기는 했습니다)",
                       field="panel_status", **where)
        if not reason:
            result.add(ERROR, "PANEL_STATUS_REASON_MISSING",
                       f"panel_status 가 '{status}' 인데 사유가 없습니다 — "
                       f"panel_status_reason 에 실제 사유를 적으십시오",
                       field="panel_status_reason", **where)
    return status, reason


def _not_run(block, match: Match, status: str, reason: str,
             allowed_ids, result: PanelImportResult, where: dict) -> PanelRun:
    """실행하지 않은 경기. **내용을 만들지 않는다.**

    분석가·사회자 블록은 있어도 되고 없어도 된다 — 260052 의 실제 출력이
    `simulations: 0 · distribution: []` 인 사회자 블록을 달고 있어서
    없애라고 요구할 수 없다. 다만 **내용이 실려 있으면** 상태와 어긋나므로
    그때는 오류다: 실행하지 않았다는데 스코어가 있으면 둘 중 하나가 거짓이다.

    돌려주는 `PanelRun` 은 의견도 사회자도 없다. 여기서 가짜 의견이나
    `simulations=30` 을 지어내지 않는다.
    """
    clashes = []
    for role in ANALYST_ROLES:
        part = block.get(role)
        if isinstance(part, dict) and (part.get("predicted_home") is not None
                                       or part.get("predicted_away") is not None):
            clashes.append(f"{role} 에 예상 스코어가 있습니다")
    mod = block.get(MODERATOR_ROLE)
    if isinstance(mod, dict):
        if mod.get("adopted_home") is not None or mod.get("adopted_away") is not None:
            clashes.append("moderator 에 채택 스코어가 있습니다")
        if mod.get("distribution"):
            clashes.append("moderator 에 토론 분포가 있습니다")
    for text in clashes:
        result.add(ERROR, "PANEL_STATUS_CONTRADICTION",
                   f"panel_status 가 '{status}' 인데 {text} — 실행했다면 "
                   f"panel_status 를 'ok' 로, 실행하지 않았다면 그 내용을 "
                   f"빼십시오", field="panel_status", **where)
    _check_evidence_scope(block, allowed_ids, result, where)
    return PanelRun(status=f"{status} ({reason})" if reason else status,
                    opinions=(),
                    role_status={r: status for r in ANALYST_ROLES},
                    market_reference=panel.market_reference(match),
                    evidence_ids=allowed_ids, payload_hash="", moderator=None)


def _is_team(given: str, ref) -> bool:
    """이 이름이 그 팀인가. 채팅이 보는 이름과 같은 표기만 받는다.

    자료에 실리는 이름은 `match.home.display or match.home.canonical`
    (`panel.build_panel_payload`)이라, 그대로 옮겨 적으면 반드시 맞는다.
    """
    return given in (ref.display, ref.canonical, ref.name_ko)


def _check_teams(block, match: Match, linked_by: str,
                 result: PanelImportResult, where: dict) -> None:
    """팀 정체성. **번호로 이었으면 이것이 유일한 확인 수단이다.**

    회차 안에서 `match_number` 는 유일하므로 번호만으로 경기 하나가 정해진다.
    그러나 번호가 한 칸 밀린 파일도 번호만 보면 그대로 통과한다 — 잘못된
    경기에 붙는 것을 막는 것이 이 검사이고, 그래서 번호로 이은 경우에는
    팀 이름을 **선택이 아니라 필수**로 요구한다. 검증할 수 없는 링크를
    조용히 통과시키지 않는다 (§1-6).

    `match_id` 로 이었으면 지금까지처럼 **있을 때만** 본다 — 그쪽은 이미
    강한 키이고, 옛 파일이 팀 이름 없이도 읽혀야 한다.
    """
    home = _text(block.get("home_team"))
    away = _text(block.get("away_team"))
    if linked_by == LINK_NUMBER and not (home and away):
        missing = " · ".join(
            k for k, v in (("home_team", home), ("away_team", away)) if not v)
        result.add(ERROR, "MATCH_LINK_UNVERIFIED",
                   f"match_id 없이 match_number 로 이었는데 {missing} 가 "
                   f"없습니다 — 번호만으로는 잘못된 경기에 붙어도 알 수 "
                   f"없으므로 팀 이름이 필요합니다 (이 경기는 "
                   f"'{match.home.display}' vs '{match.away.display}')",
                   field="home_team", **where)
        return
    # 홈/원정이 통째로 뒤바뀐 것은 **한 줄로** 알린다 — 두 팀이 다 틀렸다고
    # 적으면 정작 무엇이 잘못됐는지 흐려진다.
    if (home and away and _is_team(home, match.away)
            and _is_team(away, match.home)):
        result.add(ERROR, "TEAM_MISMATCH",
                   f"홈/원정이 뒤바뀌었습니다 — 파일 '{home}' vs '{away}', "
                   f"이 경기는 '{match.home.display}' vs "
                   f"'{match.away.display}'", field="home_team", **where)
        return
    for key, given, ref in (("home_team", home, match.home),
                            ("away_team", away, match.away)):
        if given and not _is_team(given, ref):
            result.add(ERROR, "TEAM_MISMATCH",
                       f"{key} 가 '{given}' 인데 이 경기는 "
                       f"'{ref.display}' 입니다", field=key, **where)


def _import_match(block, match: Match, mid: str, sims: int,
                  result: PanelImportResult,
                  version: str = SCHEMA_VERSION,
                  linked_by: str = LINK_ID) -> PanelRun | None:
    where = {"match_id": mid, "match_no": match.no}
    rows = panel.evidence_rows(match)
    allowed_ids = tuple(r["id"] for r in rows)

    for path, name in _forbidden_in(block, ""):
        result.add(ERROR, "FORBIDDEN_FIELD",
                   f"'{name}' 은 만들 수 없는 칸입니다 (승무패·추천·확신도)",
                   field=path, **where)

    _check_teams(block, match, linked_by, result, where)

    status, reason = _panel_status(block, version, result, where)
    if status != STATUS_OK:
        # 실행하지 않은 경기는 여기서 끝난다 — 분석가·사회자를 요구하지
        # 않고, 통과시키려고 `common_points` 한 줄을 지어내게 하지 않는다.
        return _not_run(block, match, status, reason, allowed_ids,
                        result, where)

    given_no = block.get("match_number")
    if isinstance(given_no, int) and given_no != match.no:
        # 번호는 표시용 보조 식별자다. 어긋나도 match_id 를 버리지 않는다.
        result.add(WARNING, "MATCH_NUMBER_MISMATCH",
                   f"match_number 가 {given_no} 인데 이 경기는 {match.no} "
                   f"번입니다 (match_id 를 기준으로 연결했습니다)",
                   field="match_number", **where)

    _check_evidence_scope(block, allowed_ids, result, where)

    opinions = []
    for role in ANALYST_ROLES:
        op = _opinion(block.get(role), role, allowed_ids, result, where)
        if op is not None:
            opinions.append(op)
    if len(opinions) != len(ANALYST_ROLES):
        return None

    mod = _moderator(block.get(MODERATOR_ROLE), opinions, allowed_ids, sims,
                     result, where)
    if mod is None:
        return None
    _check_adopted_from(
        (block.get(MODERATOR_ROLE) or {}).get("adopted_from"),
        mod, opinions, result, where)

    return PanelRun(status=f"ok (2/2 분석가 · {IMPORT_SOURCE})",
                    opinions=tuple(opinions),
                    role_status={r: "ok" for r in ANALYST_ROLES},
                    market_reference=panel.market_reference(match),
                    evidence_ids=allowed_ids,
                    payload_hash="", moderator=mod)


# ==========================================================================
# 감사 — 세기만 하고 판정하지 않는다
# ==========================================================================
def _audit(runs: dict[int, PanelRun], result: PanelImportResult) -> None:
    """회차 전체를 훑어 **사실만** 센다.

    "어느 분석가가 더 옳다"·"합의도가 높다" 를 만들지 않는다. 260050 에서
    실제로 나온 상태(맞대결 분석가 origin 0회)를 사람이 볼 수 있게 하는 것이
    목적이다.
    """
    origins: dict[str, int] = {}
    agree = disagree = compromise = adopted_data = adopted_matchup = 0
    # **실행한 경기만 센다.** 생략한 경기를 섞으면 "두 분석가가 한 번도
    # 갈리지 않았다" 같은 경고가 실행하지도 않은 경기 때문에 뜬다.
    by_status: dict[str, int] = {}
    ran = {}
    for no, run in runs.items():
        state = status_of(run)
        by_status[state] = by_status.get(state, 0) + 1
        if state == STATUS_OK:
            ran[no] = run
    for run in ran.values():
        mod = run.moderator
        by_role = {o.role: (o.predicted_home, o.predicted_away)
                   for o in run.opinions}
        da, mu = by_role.get(DATA_ROLE), by_role.get(MATCHUP_ROLE)
        if da is not None and mu is not None:
            if da == mu:
                agree += 1
            else:
                disagree += 1
        for tally in getattr(mod, "distribution", ()) or ():
            origins[tally.origin] = origins.get(tally.origin, 0) + 1
        roles = set(getattr(mod, "adopted_from", ()) or ())
        if getattr(mod, "adopted_home", None) is not None and not roles:
            compromise += 1
        if DATA_ROLE in roles:
            adopted_data += 1
        if MATCHUP_ROLE in roles:
            adopted_matchup += 1

    result.audit = {
        "matches": len(runs),
        "panel_ok": by_status.get(STATUS_OK, 0),
        "panel_skipped": by_status.get(STATUS_SKIPPED, 0),
        "panel_failed": by_status.get(STATUS_FAILED, 0),
        "panel_partial": by_status.get(STATUS_PARTIAL, 0),
        "analysts_agree": agree,
        "analysts_disagree": disagree,
        "adopted_from_data_analyst": adopted_data,
        "adopted_from_matchup_analyst": adopted_matchup,
        "adopted_compromise": compromise,
        "distribution_origin_rows": dict(sorted(origins.items())),
    }

    # 260050 에서 실제로 나온 상태다. **그 자체로 오류는 아니다** — 두
    # 분석가가 늘 같은 스코어를 냈다면 그럴 수 있다. 다만 보이게 한다.
    if ran and not origins.get(MATCHUP_ROLE):
        result.add(WARNING, "MATCHUP_ORIGIN_ZERO",
                   f"분포에서 맞대결·전술 분석가 원안이 한 번도 나오지 "
                   f"않았습니다 (두 분석가 의견 일치 {agree}경기 / 불일치 "
                   f"{disagree}경기). 분석가가 참여하지 않은 것과는 다른 "
                   f"상태입니다 — 위 수치로 구분하십시오")
    if ran and not disagree:
        result.add(WARNING, "ANALYSTS_NEVER_DISAGREE",
                   f"{len(ran)}경기 전부에서 두 분석가의 원안 스코어가 "
                   f"같습니다. 토론이 실제로 갈릴 여지가 있었는지 확인하십시오")


# ==========================================================================
# 회차
# ==========================================================================
def validate(data: dict, report: Report, settings=None) -> PanelImportResult:
    """Panel Result → 검증 결과. **원본 텍스트를 고치지 않는다.**"""
    result = PanelImportResult(
        round_id=_text(str(report.round_id or "")),
        expected_matches=len(report.matches))
    sims = (moderator.simulations_of(settings) if settings is not None
            else moderator.DEBATE_SIMULATIONS)

    version = _text(str(data.get("schema_version") or ""))
    result.schema_version = version
    if not version:
        result.add(ERROR, "SCHEMA_VERSION_MISSING",
                   "schema_version 이 없습니다", field="schema_version")
    elif version not in SUPPORTED_VERSIONS:
        result.add(ERROR, "SCHEMA_VERSION_UNSUPPORTED",
                   f"지원하지 않는 schema_version '{version}' "
                   f"(지원: {', '.join(SUPPORTED_VERSIONS)})",
                   field="schema_version")
    result.generated_at = _text(str(data.get("generated_at") or ""))

    if not _round_equal(data.get("round"), report.round_id):
        result.add(ERROR, "ROUND_MISMATCH",
                   f"회차가 다릅니다 — 파일 '{data.get('round')}' / "
                   f"현재 '{report.round_id}'", field="round")

    blocks = data.get("matches")
    if not isinstance(blocks, list):
        result.add(ERROR, "MATCHES_MISSING", "matches 가 목록이 아닙니다",
                   field="matches")
        return result
    if len(blocks) != len(report.matches):
        result.add(ERROR, "MATCH_COUNT_MISMATCH",
                   f"경기 수가 다릅니다 — 파일 {len(blocks)}경기 / "
                   f"현재 회차 {len(report.matches)}경기", field="matches")

    # 이 회차의 authoritative id 표. `match_id` 를 모르는 경기가 있으면
    # 그것부터 알린다 — 이름으로 잇지 않는다.
    by_id: dict[str, Match] = {}
    unknown_id = []
    for m in report.matches:
        mid = _match_key(m, report)
        if mid:
            by_id[mid] = m
        else:
            unknown_id.append(m)
    if unknown_id:
        result.add(WARNING, "LOCAL_MATCH_ID_MISSING",
                   f"현재 회차의 {len(unknown_id)}경기가 시즌 색인에서 "
                   f"match_id 를 얻지 못했습니다 "
                   f"({', '.join(str(m.no) for m in unknown_id)}번) — "
                   f"그 경기는 경기 번호로 잇습니다")

    seen: dict[str, int] = {}
    matched: dict[int, dict] = {}
    links: dict[int, str] = {}          # 경기번호 → 무엇으로 이었나
    by_no = {m.no: m for m in report.matches}
    for i, block in enumerate(blocks):
        if not isinstance(block, dict):
            result.add(ERROR, "MATCH_NOT_AN_OBJECT",
                       f"matches[{i}] 가 객체가 아닙니다", field=f"matches[{i}]")
            continue
        mid = _text(str(block.get("match_id") or ""))
        raw_no = block.get("match_number")
        # `True` 는 `int` 의 하위형이라 그냥 두면 1번 경기가 된다 (§1-9).
        no = (raw_no if isinstance(raw_no, int)
              and not isinstance(raw_no, bool) else None)
        if mid:
            if mid in seen:
                result.add(ERROR, "DUPLICATE_MATCH_ID",
                           f"match_id 가 두 번 나옵니다 (앞서 "
                           f"{seen[mid]}번째)", match_id=mid,
                           field=f"matches[{i}].match_id")
                continue
            seen[mid] = i + 1

        # ---- 해소 순서: match_id → match_number → 실패 -------------------
        target, how = (by_id.get(mid) if mid else None), LINK_ID
        if target is None and no is not None:
            target, how = by_no.get(no), LINK_NUMBER
            if target is not None and mid:
                # 파일의 id 가 이 회차의 id 가 아니다. **조용히 다른 경기에
                # 붙이지 않는다** — 번호와 팀으로 이은 뒤 그 사실을 남기고,
                # 값은 프로그램의 authoritative id 를 쓴다.
                result.add(WARNING, "MATCH_ID_MISMATCH",
                           f"파일의 match_id '{mid}' 는 이 회차의 값이 "
                           f"아닙니다 — match_number {no} 와 팀 이름으로 "
                           f"이었고 회차의 match_id "
                           f"'{_match_key(target, report) or '없음'}' 를 "
                           f"씁니다", match_id=mid, match_no=target.no,
                           field=f"matches[{i}].match_id")
        if target is None:
            result.add(ERROR, "UNKNOWN_MATCH_ID",
                       f"이 회차에 없는 경기입니다 (match_id="
                       f"{mid or '없음'}, match_number={raw_no})",
                       match_id=mid, field=f"matches[{i}]")
            continue
        if target.no in matched:
            result.add(ERROR, "DUPLICATE_MATCH",
                       f"{target.no}번 경기가 두 번 나옵니다",
                       match_id=mid, match_no=target.no)
            continue
        matched[target.no] = block
        links[target.no] = how

    for m in report.matches:
        if m.no not in matched:
            result.add(ERROR, "MATCH_MISSING",
                       f"{m.no}번 경기({m.title})가 파일에 없습니다",
                       match_id=_match_key(m, report), match_no=m.no)

    runs: dict[int, PanelRun] = {}
    for m in report.matches:
        block = matched.get(m.no)
        if block is None:
            continue
        run = _import_match(block, m, _match_key(m, report), sims, result,
                            version, links.get(m.no, LINK_ID))
        if run is not None:
            runs[m.no] = run

    result.imported_matches = len(runs)
    result.parsed = dict(runs)          # 실패해도 남는다 (4-C 감사용)
    _audit(runs, result)
    # **부분 import 를 정상으로 취급하지 않는다.** 오류가 하나라도 있거나
    # 경기가 하나라도 빠지면 붙이지 않는다.
    result.success = (not result.errors
                      and len(runs) == len(report.matches)
                      and bool(runs))
    if result.success:
        result.runs = runs
    return result


def attach(result: PanelImportResult, report: Report) -> int:
    """검증을 통과한 결과만 리포트에 붙인다. 붙인 경기 수를 돌려준다.

    **기존 분석 결과를 건드리지 않는다** — `Match.panel` 에만 얹는다.
    """
    if not result.success:
        return 0
    n = 0
    for match in report.matches:
        run = result.runs.get(match.no)
        if run is not None:
            match.panel = run
            n += 1
    return n


def run(path: Path | str, report: Report, settings=None,
        attach_result: bool = True) -> PanelImportResult:
    """파일 하나를 읽어 검증하고, 통과하면 리포트에 붙인다."""
    data, why = load(path)
    if data is None:
        out = PanelImportResult(round_id=str(report.round_id or ""),
                                expected_matches=len(report.matches))
        out.add(ERROR, "UNREADABLE", why, field=str(path))
        return out
    out = validate(data, report, settings)
    if attach_result:
        attach(out, report)
    return out


def report_lines(result: PanelImportResult) -> list[str]:
    """사람이 읽을 검증 요약. 오류를 숨기지 않는다."""
    lines = [result.status_line()]
    a = result.audit
    if a:
        lines.append(
            f"  감사: 두 분석가 원안 일치 {a['analysts_agree']} / 불일치 "
            f"{a['analysts_disagree']} · 채택 출처 — 데이터 "
            f"{a['adopted_from_data_analyst']} · 맞대결 "
            f"{a['adopted_from_matchup_analyst']} · 절충 "
            f"{a['adopted_compromise']}")
        origins = a.get("distribution_origin_rows") or {}
        lines.append("  분포 origin 줄 수: " + (", ".join(
            f"{k} {v}" for k, v in origins.items()) or "없음"))
    for issue in result.issues:
        lines.append(f"  {issue}")
    return lines
