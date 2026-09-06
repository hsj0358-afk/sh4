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

SCHEMA_VERSION = "1.0"
SUPPORTED_VERSIONS = ("1.0",)

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


def _import_match(block, match: Match, mid: str, sims: int,
                  result: PanelImportResult) -> PanelRun | None:
    where = {"match_id": mid, "match_no": match.no}
    rows = panel.evidence_rows(match)
    allowed_ids = tuple(r["id"] for r in rows)

    for path, name in _forbidden_in(block, ""):
        result.add(ERROR, "FORBIDDEN_FIELD",
                   f"'{name}' 은 만들 수 없는 칸입니다 (승무패·추천·확신도)",
                   field=path, **where)

    # 팀 정체성. match_id 가 primary key 이고 팀 이름은 **확인용**이다.
    for key, ref in (("home_team", match.home), ("away_team", match.away)):
        given = _text(block.get(key))
        if given and given not in (ref.display, ref.canonical, ref.name_ko):
            result.add(ERROR, "TEAM_MISMATCH",
                       f"{key} 가 '{given}' 인데 이 경기는 "
                       f"'{ref.display}' 입니다", field=key, **where)

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
    for run in runs.values():
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
        "analysts_agree": agree,
        "analysts_disagree": disagree,
        "adopted_from_data_analyst": adopted_data,
        "adopted_from_matchup_analyst": adopted_matchup,
        "adopted_compromise": compromise,
        "distribution_origin_rows": dict(sorted(origins.items())),
    }

    # 260050 에서 실제로 나온 상태다. **그 자체로 오류는 아니다** — 두
    # 분석가가 늘 같은 스코어를 냈다면 그럴 수 있다. 다만 보이게 한다.
    if runs and not origins.get(MATCHUP_ROLE):
        result.add(WARNING, "MATCHUP_ORIGIN_ZERO",
                   f"분포에서 맞대결·전술 분석가 원안이 한 번도 나오지 "
                   f"않았습니다 (두 분석가 의견 일치 {agree}경기 / 불일치 "
                   f"{disagree}경기). 분석가가 참여하지 않은 것과는 다른 "
                   f"상태입니다 — 위 수치로 구분하십시오")
    if runs and not disagree:
        result.add(WARNING, "ANALYSTS_NEVER_DISAGREE",
                   f"{len(runs)}경기 전부에서 두 분석가의 원안 스코어가 "
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
    for i, block in enumerate(blocks):
        if not isinstance(block, dict):
            result.add(ERROR, "MATCH_NOT_AN_OBJECT",
                       f"matches[{i}] 가 객체가 아닙니다", field=f"matches[{i}]")
            continue
        mid = _text(str(block.get("match_id") or ""))
        no = block.get("match_number")
        if mid:
            if mid in seen:
                result.add(ERROR, "DUPLICATE_MATCH_ID",
                           f"match_id 가 두 번 나옵니다 (앞서 "
                           f"{seen[mid]}번째)", match_id=mid,
                           field=f"matches[{i}].match_id")
                continue
            seen[mid] = i + 1
        target = by_id.get(mid)
        if target is None and isinstance(no, int):
            # match_id 를 우리 쪽이 모르는 경우에만 번호로 잇는다.
            target = next((m for m in report.matches if m.no == no), None)
            if target is not None and _match_key(target, report):
                target = None       # 우리는 아는데 파일의 id 가 다르다
        if target is None:
            result.add(ERROR, "UNKNOWN_MATCH_ID",
                       f"이 회차에 없는 경기입니다 (match_id="
                       f"{mid or '없음'}, match_number={no})",
                       match_id=mid, field=f"matches[{i}]")
            continue
        if target.no in matched:
            result.add(ERROR, "DUPLICATE_MATCH",
                       f"{target.no}번 경기가 두 번 나옵니다",
                       match_id=mid, match_no=target.no)
            continue
        matched[target.no] = block

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
        run = _import_match(block, m, _match_key(m, report), sims, result)
        if run is not None:
            runs[m.no] = run

    result.imported_matches = len(runs)
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
