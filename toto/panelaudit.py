"""Panel Audit — 패널이 **어떤 과정을 거쳤는지** 구조적으로 기록한다
(Phase 4-C).

## 감사는 패널 위에 있지 않다

이 계층은 패널의 분석이 옳은지 판정하지 않는다. 묻는 것은 하나다.

    **무슨 일이 있었는가?**

그래서 다음을 만들지 않는다 — "데이터 분석가가 더 신뢰할 만하다" ·
"30회 중 19회니까 2-1 이 유력하다" · "맞대결 origin 0 이니 실패했다" ·
합의도 · 확신도 · 패널 확률 · 승무패. 해석은 사용자와 (아직 없는) 별도
평가 시스템의 몫이다.

## 4-B 를 다시 검증하지 않는다

`panelimport` 가 이미 schema · round · match_id · 팀 정체성 · 역할 · 스코어 ·
근거 ID · `adopted_from` 을 검증한다. 여기서는 그 결과(`PanelImportResult`)
를 **읽어서 회차 단위로 집계**할 뿐이다.

    Panel Result → 4-B ImportResult → 4-C AuditResult

## 반드시 나누는 두 가지

**분석가가 있었나(participation)** 와 **분포에 그 원안이 나왔나(origin)** 는
다른 것이다. 260050 에서 맞대결·전술 분석가의 origin 이 0회였는데, 그것은
그 분석가가 참여하지 않았다는 뜻이 **아니다** — 두 분석가가 늘 같은 스코어를
냈으면 그럴 수 있다. 그래서 커버리지와 origin 을 따로 세고, 경고 문구에
그 사실을 적는다.

## 없는 것을 추론하지 않는다

현재 schema 는 토론 30회의 **결과 분포만** 담는다. 라운드별 대화 내용 ·
어느 축에서 출발했는지 · 어떤 근거를 썼는지 · 사회자의 내부 추론은 자료에
없다. 분포만 가지고 그것을 되짚지 않고, `UNOBSERVED` 로 남긴다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import panelimport
from .models import Report
from .panelimport import ERROR, WARNING, Issue, PanelImportResult

log = logging.getLogger("toto")

DA = panelimport.DATA_ROLE
MU = panelimport.MATCHUP_ROLE
COMPROMISE = "compromise"

# 회차 감사 상태.
PASS, CONDITIONAL, FAIL = "PASS", "CONDITIONAL", "FAIL"
# 커버리지 상태.
COMPLETE, PARTIAL, FAILED = "COMPLETE", "PARTIAL", "FAILED"

# 두 분석가의 **처음** 스코어 관계. 점수가 아니라 관계 라벨이다.
SAME_INITIAL, DIFFERENT_INITIAL = "SAME_INITIAL_SCORE", "DIFFERENT_INITIAL_SCORE"
UNKNOWN_INITIAL = "UNKNOWN_INITIAL_SCORE"

# 사회자가 무엇을 했나. **파생 감사 필드**이고 `adopted_from`(원본 필드)과
# 자리를 나눈다 — 원본을 덮어쓰지 않는다.
ADOPTED_DATA = "ADOPTED_DATA_ANALYST"
ADOPTED_MATCHUP = "ADOPTED_MATCHUP_ANALYST"
ADOPTED_BOTH = "ADOPTED_BOTH"
MODIFIED = "MODIFIED_OR_COMPROMISE"
NOT_ADOPTED = "NOT_ADOPTED"
# 패널을 **돌리지 않은** 경기. `NOT_ADOPTED`(돌렸는데 못 골랐다)와 다르다 —
# 승무패 의미는 없고, 무슨 일이 있었나만 적는 감사 전용 라벨이다.
PANEL_SKIPPED = "PANEL_SKIPPED"
# 3단계 결과만 들어온 경기 (Phase 4-F). `PANEL_SKIPPED`(돌리지 않았다)와도,
# `MODIFIED_OR_COMPROMISE`(분석가 둘과 다른 값을 골랐다)와도 다르다 —
# **분석가의 원안이 이 입력에 없어서 견줄 것이 없다.**
MODERATOR_ONLY = "MODERATOR_ONLY"

# 패널 실행 상태는 4-B 의 어휘를 그대로 쓴다 (§1-6). 여기서 새로 만들지 않는다.
STATUS_OK = panelimport.STATUS_OK
STATUS_SKIPPED = panelimport.STATUS_SKIPPED
STATUS_FAILED = panelimport.STATUS_FAILED
STATUS_PARTIAL = panelimport.STATUS_PARTIAL

# 자료에 없는 것. 추론하지 않는다는 표시다.
UNOBSERVED = "UNOBSERVED"

# 분포만으로는 알 수 없는 것들. 보고서에 그대로 적는다.
NOT_IN_SCHEMA = (
    "라운드별 토론 내용",
    "라운드마다 출발한 분석 축",
    "라운드마다 인용한 근거",
    "사회자의 내부 추론 과정",
)


def _label(home, away) -> str:
    return f"{home}-{away}" if home is not None and away is not None else "—"


@dataclass
class PanelMatchAudit:
    """경기 하나의 감사 기록. **새 점수를 만들지 않는다.**"""
    match_no: int = 0
    match_id: str = ""
    # 패널을 실제로 돌렸나 (4-B `panel_status`). `ok` 가 아니면 아래 스코어·
    # 분포 칸은 전부 비어 있고, 그것이 정답이다.
    panel_status: str = STATUS_OK
    panel_status_reason: str = ""
    home_team: str = ""
    away_team: str = ""
    data_analyst_score: tuple | None = None
    matchup_analyst_score: tuple | None = None
    moderator_score: tuple | None = None
    initial_score_relation: str = UNKNOWN_INITIAL
    decision_type: str = NOT_ADOPTED
    adopted_from: tuple[str, ...] = ()       # 원본 필드 (4-B 가 확인한 값)
    simulations: int = 0
    distribution_total: int = 0
    distribution_origins: dict = field(default_factory=dict)
    evidence_available: int = 0              # 이 경기의 실제 근거 수
    evidence_cited: tuple[str, ...] = ()     # 인용된 ID (중복 제거)
    issue_codes: tuple[str, ...] = ()

    @property
    def row(self) -> tuple[str, str, str, str]:
        """`Match | DA | Matchup | Moderator` 표 한 줄 (§9)."""
        return (f"{self.match_no:02d}",
                _label(*(self.data_analyst_score or (None, None))),
                _label(*(self.matchup_analyst_score or (None, None))),
                _label(*(self.moderator_score or (None, None))))


@dataclass
class PanelAuditResult:
    """회차 감사 결과. 4-D/4-E 가 이 구조를 그대로 읽을 수 있어야 한다."""
    round_id: str = ""
    status: str = FAIL
    coverage_status: str = FAILED
    coverage: dict = field(default_factory=dict)
    matches: list[PanelMatchAudit] = field(default_factory=list)
    adoption: dict = field(default_factory=dict)
    distribution: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    consistency: dict = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    not_in_schema: tuple[str, ...] = NOT_IN_SCHEMA

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == WARNING]

    def by_match(self, no: int) -> PanelMatchAudit | None:
        return next((m for m in self.matches if m.match_no == no), None)


# ==========================================================================
# 관계 분류 — **계산이 아니라 라벨이다**
# ==========================================================================
def initial_relation(da, mu) -> str:
    """두 분석가의 처음 스코어 관계. 신뢰도·합의도로 쓰지 않는다."""
    if da is None or mu is None:
        return UNKNOWN_INITIAL
    return SAME_INITIAL if da == mu else DIFFERENT_INITIAL


def decision_type(adopted, da, mu) -> str:
    """사회자가 무엇을 했나. **어느 쪽이 옳은지가 아니다.**

    `adopted_from` 을 되읽지 않고 **실제 스코어끼리 견줘** 정한다 — 원본
    필드가 비어 있어도(절충) 옳게 나오고, 4-B 의 재계산과 어긋날 수 없다.
    """
    if adopted is None:
        return NOT_ADOPTED
    hit_da, hit_mu = adopted == da, adopted == mu
    if hit_da and hit_mu:
        return ADOPTED_BOTH
    if hit_da:
        return ADOPTED_DATA
    if hit_mu:
        return ADOPTED_MATCHUP
    return MODIFIED


# ==========================================================================
# 감사
# ==========================================================================
def _match_audit(no: int, match, run, codes) -> PanelMatchAudit:
    ops = {o.role: o for o in (getattr(run, "opinions", ()) or ())}
    mod = getattr(run, "moderator", None)
    state = panelimport.status_of(run)
    raw = getattr(run, "status", "") or ""
    why = raw.split(" (", 1)[1].rstrip(")") if " (" in raw else ""

    def score(role):
        o = ops.get(role)
        if o is None or o.predicted_home is None or o.predicted_away is None:
            return None
        return (o.predicted_home, o.predicted_away)

    da, mu = score(DA), score(MU)
    adopted = None
    if mod is not None and mod.adopted_home is not None:
        adopted = (mod.adopted_home, mod.adopted_away)

    origins: dict[str, int] = {}
    total = 0
    for tally in (getattr(mod, "distribution", ()) or ()):
        origins[tally.origin] = origins.get(tally.origin, 0) + tally.count
        total += tally.count

    cited = []
    for holder in (*ops.values(), mod):
        for eid in (getattr(holder, "evidence_ids", ()) or ()):
            if eid not in cited:
                cited.append(eid)

    return PanelMatchAudit(
        match_no=no, match_id=getattr(run, "payload_hash", "") or "",
        panel_status=state,
        panel_status_reason=why if state != STATUS_OK else "",
        home_team=getattr(getattr(match, "home", None), "display", ""),
        away_team=getattr(getattr(match, "away", None), "display", ""),
        data_analyst_score=da, matchup_analyst_score=mu,
        moderator_score=adopted,
        initial_score_relation=initial_relation(da, mu),
        # 돌리지 않은 경기를 "못 골랐다"로 적지 않는다. 사회자 결과만 들어온
        # 경기도 마찬가지다 — 분석가 원안이 없어 견줄 수가 없다.
        decision_type=(MODERATOR_ONLY if panelimport.is_moderator_only(run)
                       else PANEL_SKIPPED if state != STATUS_OK
                       else decision_type(adopted, da, mu)),
        adopted_from=tuple(getattr(mod, "adopted_from", ()) or ()),
        simulations=getattr(mod, "simulations", 0) or 0,
        distribution_total=total, distribution_origins=origins,
        evidence_available=len(getattr(run, "evidence_ids", ()) or ()),
        evidence_cited=tuple(cited), issue_codes=tuple(sorted(set(codes))))


def match_audit(match, run) -> PanelMatchAudit | None:
    """경기 하나의 감사 기록. **리포트(4-D)가 이 구조를 그대로 읽는다.**

    회차 감사(`audit`)와 **같은 함수**로 만든다. 화면이 결정 유형을 따로
    계산하기 시작하면 감사 보고서의 결정 유형과 갈라질 수 있고, 그러면 둘 중
    어느 쪽도 믿을 수 없게 된다.

    `PanelImportResult` 를 요구하지 않는다 — 채팅에서 받아 온 패널
    (`--import-panel-result`)이든 곧바로 실행한 패널(`--panel`)이든 화면에
    닿을 때는 똑같이 `PanelRun` 이고, 둘을 다르게 읽을 이유가 없다.
    """
    if run is None:
        return None
    return _match_audit(getattr(match, "no", 0) or 0, match, run, ())


def _coverage(report: Report, parsed: dict, imp: PanelImportResult) -> dict:
    """커버리지. **누락 경기 번호까지 남긴다** (§5).

    **패널을 돌린 경기와 돌리지 않은 경기를 섞지 않는다.** 예전에는
    `data_analyst 14/14` 처럼 회차 전체를 분모로 썼는데, 260052 처럼 3경기를
    실행하지 않은 회차에서는 그 수가 거짓이 된다 — 분석가가 있었던 것도
    아니고 빠뜨린 것도 아니기 때문이다. 이제 분모는 **`ok` 경기 수**이고,
    실행하지 않은 경기는 상태별로 따로 센다.
    """
    ran = {no: run for no, run in parsed.items()
           if panelimport.status_of(run) == STATUS_OK}

    # **돌리지 않겠다고 밝힌 경기**만 뺀다. 파일에 있었는데 깨져서 못 읽은
    # 경기는 그대로 '누락' 이다 — 그 둘을 같이 빼면 import 오류가 커버리지에서
    # 사라진다.
    declared_skip = {no for no, run in parsed.items()
                     if panelimport.status_of(run) != STATUS_OK}

    def missing(pred) -> list[int]:
        return [m.no for m in report.matches
                if m.no not in declared_skip and not pred(ran.get(m.no))]

    def has_role(run, role) -> bool:
        return run is not None and any(
            o.role == role for o in (run.opinions or ()))

    def count(state: str) -> int:
        return sum(1 for run in parsed.values()
                   if panelimport.status_of(run) == state)

    return {
        "matches_total": len(report.matches),
        # 파일에 들어 있던 경기 전부 (실행 여부와 무관).
        "panel_blocks": len(parsed),
        "panel_missing": [m.no for m in report.matches if m.no not in parsed],
        # 실제로 패널을 돌린 경기. 아래 분석가·사회자 수의 분모다.
        "panel_results": len(ran),
        "panel_skipped": count(STATUS_SKIPPED),
        "panel_failed": count(STATUS_FAILED),
        "panel_partial": count(STATUS_PARTIAL),
        # 3단계 결과만 들어온 경기 (Phase 4-F). 돌리지 않은 경기와 **다르다**.
        "moderator_only": sorted(
            no for no, run in parsed.items()
            if panelimport.is_moderator_only(run)),
        "skipped_matches": sorted(
            no for no, run in parsed.items()
            if panelimport.status_of(run) != STATUS_OK
            and not panelimport.is_moderator_only(run)),
        "data_analyst": sum(1 for run in ran.values() if has_role(run, DA)),
        "data_analyst_missing": missing(lambda r: has_role(r, DA)),
        "matchup_analyst": sum(1 for run in ran.values() if has_role(run, MU)),
        "matchup_analyst_missing": missing(lambda r: has_role(r, MU)),
        "moderator": sum(1 for run in ran.values()
                         if getattr(run, "moderator", None)),
        "moderator_missing": missing(
            lambda r: getattr(r, "moderator", None) is not None),
        "import_errors": len(imp.errors),
    }


def composition_line(result: PanelAuditResult) -> str:
    """배지에 적을 한 줄 — **무엇이 실제로 반영됐나** (Phase 4-F UI §4).

    `부분 (14/14경기 가져옴)` 만으로는 사용자가 무엇을 얻었는지 알 수 없다.
    셋을 나눠 적는다 — 판정하지 않고 세기만 한다.

    **"14/14경기 분석 완료" 처럼 적지 않는다.** 사회자만 반영된 경기를
    완전한 패널로 보이게 하는 표현이다 (§13).
    """
    cov = result.coverage or {}
    parts = []
    if cov.get("panel_results"):
        parts.append(f"패널 {cov['panel_results']}경기")
    if cov.get("moderator_only"):
        parts.append(f"Moderator 결과 {len(cov['moderator_only'])}경기")
    for key, label in (("panel_skipped", "생략"),
                       ("panel_failed", "실패")):
        if cov.get(key):
            parts.append(f"{label} {cov[key]}경기")
    return " · ".join(parts)


def _consistency(audits: list[PanelMatchAudit],
                 result: PanelAuditResult) -> dict:
    """회차 안에서 모든 경기가 **같은 패널 계약**을 썼는지 (§44).

    `schema_version` 은 이 프로젝트의 계약에서 회차 단위 칸이라 4-B 가 이미
    확인한다. 여기서는 경기마다 **구조가 같은지**를 본다 — 시뮬레이션 횟수가
    제각각이면 같은 절차를 밟았다고 보기 어렵다.
    """
    sims = sorted({a.simulations for a in audits if a.simulations})
    if len(sims) > 1:
        result.issues.append(Issue(
            WARNING, "SIMULATION_COUNT_VARIES",
            f"경기마다 토론 횟수가 다릅니다: {sims} — 같은 절차를 밟았는지 "
            f"확인하십시오", field="moderator.simulations"))
    return {"simulation_counts": sims,
            "roles_per_match": sorted({
                len([s for s in (a.data_analyst_score, a.matchup_analyst_score)
                     if s is not None]) for a in audits}) or [0]}


def audit(imp: PanelImportResult, report: Report) -> PanelAuditResult:
    """4-B 결과 → 회차 감사. **분석값을 다시 계산하지 않는다.**"""
    out = PanelAuditResult(round_id=str(report.round_id or ""))
    parsed = dict(imp.parsed or {})

    codes_by_match: dict[int, list[str]] = {}
    for issue in imp.issues:
        if issue.match_no:
            codes_by_match.setdefault(issue.match_no, []).append(issue.code)

    by_no = {m.no: m for m in report.matches}
    for no in sorted(parsed):
        out.matches.append(_match_audit(no, by_no.get(no), parsed[no],
                                        codes_by_match.get(no, ())))
    # match_id 는 회차 분석 쪽의 authoritative id 를 쓴다 (§7).
    for a in out.matches:
        match = by_no.get(a.match_no)
        if match is not None:
            a.match_id = panelimport._match_key(match, report)

    out.coverage = _coverage(report, parsed, imp)
    out.issues = list(imp.issues)

    # ---- 채택 (§13) — 세기만 한다. 승률·신뢰도가 아니다 -------------------
    # **패널을 돌린 경기만 센다.** 실행하지 않은 경기를 "채택 없음" 으로
    # 세면 사회자가 하지도 않은 일이 통계에 들어간다.
    ran = [a for a in out.matches if a.panel_status == STATUS_OK]
    kinds = [a.decision_type for a in ran]
    out.adoption = {
        "panel_ran": len(ran),
        "panel_not_run": len(out.matches) - len(ran),
        "adopted_data_analyst": kinds.count(ADOPTED_DATA),
        "adopted_matchup_analyst": kinds.count(ADOPTED_MATCHUP),
        "adopted_both": kinds.count(ADOPTED_BOTH),
        "modified_or_compromise": kinds.count(MODIFIED),
        "not_adopted": kinds.count(NOT_ADOPTED),
        "panel_skipped": sum(1 for a in out.matches
                             if a.decision_type == PANEL_SKIPPED),
        "same_initial": sum(1 for a in ran
                            if a.initial_score_relation == SAME_INITIAL),
        "different_initial": sum(
            1 for a in ran
            if a.initial_score_relation == DIFFERENT_INITIAL),
        "unknown_initial": sum(
            1 for a in ran
            if a.initial_score_relation == UNKNOWN_INITIAL),
    }

    # ---- 분포 (§15·§17) — 횟수만. 확률로 바꾸지 않는다 --------------------
    origins: dict[str, int] = {}
    totals = []
    for a in ran:
        for name, count in a.distribution_origins.items():
            origins[name] = origins.get(name, 0) + count
        totals.append(a.distribution_total)
    out.distribution = {
        "origin_counts": dict(sorted(origins.items())),
        "round_totals": totals,
        "matches_with_distribution": sum(1 for t in totals if t),
        "unobserved": list(NOT_IN_SCHEMA),
    }

    # ---- 근거 (§21) -------------------------------------------------------
    ev_codes = {"UNKNOWN_EVIDENCE_ID", "EVIDENCE_ABSENT_BUT_CITED"}
    out.evidence = {
        "matches_with_evidence": sum(1 for a in ran
                                     if a.evidence_available),
        "matches_without_evidence": sum(1 for a in ran
                                        if not a.evidence_available),
        "citations": sum(len(a.evidence_cited) for a in ran),
        "invalid_citation_issues": sum(1 for i in imp.issues
                                       if i.code in ev_codes),
    }

    out.consistency = _consistency(ran, out)

    # ---- 상태 ------------------------------------------------------------
    cov = out.coverage
    ok_n = cov["panel_results"]
    full = (cov["panel_blocks"] == cov["matches_total"] > 0
            and cov["data_analyst"] == ok_n
            and cov["matchup_analyst"] == ok_n
            and cov["moderator"] == ok_n)
    if imp.errors or not cov["matches_total"]:
        # 4-B 오류가 있으면 COMPLETE 로 적지 않는다 (§6).
        out.coverage_status = FAILED if not parsed else PARTIAL
        out.status = FAIL
    elif full:
        out.coverage_status = COMPLETE
        out.status = CONDITIONAL if out.warnings else PASS
    else:
        out.coverage_status = PARTIAL
        out.status = FAIL
    return out


# ==========================================================================
# 사람이 읽을 요약
# ==========================================================================
def report_lines(result: PanelAuditResult) -> list[str]:
    """회차 감사 요약. **구조적 사실만 적는다** (§32)."""
    cov, ad = result.coverage, result.adoption
    total = cov.get("matches_total", 0)
    ran = cov.get("panel_results", 0)
    lines = [f"{result.round_id} PANEL AUDIT — {result.status} "
             f"(커버리지 {result.coverage_status})", "",
             "패널 실행 상태"]
    miss = cov.get("panel_missing") or []
    lines.append(f"- 파일에 있는 경기: {cov.get('panel_blocks', 0)}/{total}"
                 + (f" · 누락 {', '.join(f'{n}번' for n in miss)}" if miss else ""))
    lines.append(f"- 패널을 돌린 경기: {ran}")
    for key, label in (("panel_skipped", "생략"), ("panel_failed", "실패"),
                       ("panel_partial", "부분")):
        if cov.get(key):
            lines.append(f"- {label}: {cov[key]}")
    if cov.get("moderator_only"):
        # **돌리지 않은 것과 섞지 않는다** — 사회자는 돌았고 분석가 원문만
        # 이 입력에 없다 (Phase 4-F).
        lines.append(
            "- 사회자 결과만 반영된 경기: "
            + ", ".join(f"{n}번" for n in cov["moderator_only"])
            + " (1·2단계 분석가 원문은 이 입력에 없습니다)")
    if cov.get("skipped_matches"):
        lines.append("- 돌리지 않은 경기: "
                     + ", ".join(f"{n}번" for n in cov["skipped_matches"]))

    # 분모는 **돌린 경기 수**다. 회차 전체를 분모로 쓰면 생략한 경기 때문에
    # "분석가가 빠졌다" 처럼 보인다.
    lines += ["", f"커버리지 (돌린 {ran}경기 기준)"]
    for key, label in (("data_analyst", "데이터 분석가"),
                       ("matchup_analyst", "맞대결·전술 분석가"),
                       ("moderator", "사회자")):
        miss = cov.get(f"{key}_missing") or []
        tail = f" · 누락 {', '.join(f'{n}번' for n in miss)}" if miss else ""
        lines.append(f"- {label}: {cov.get(key, 0)}/{ran}{tail}")

    lines += ["", "두 분석가의 처음 의견",
              f"- 같음: {ad.get('same_initial', 0)}",
              f"- 다름: {ad.get('different_initial', 0)}"]
    if ad.get("unknown_initial"):
        lines.append(f"- 알 수 없음: {ad['unknown_initial']}")

    lines += ["", "사회자 결정 (무엇을 했나 — 누가 옳은지가 아니다)",
              f"- 데이터 분석가 원안: {ad.get('adopted_data_analyst', 0)}",
              f"- 맞대결 분석가 원안: {ad.get('adopted_matchup_analyst', 0)}",
              f"- 둘 다 같은 원안: {ad.get('adopted_both', 0)}",
              f"- 수정/절충: {ad.get('modified_or_compromise', 0)}"]
    if ad.get("not_adopted"):
        lines.append(f"- 채택 없음: {ad['not_adopted']}")

    origins = result.distribution.get("origin_counts") or {}
    lines += ["", "토론 수렴 분포의 origin (횟수 · 확률이 아니다)"]
    lines += [f"- {k}: {v}" for k, v in origins.items()] or ["- 없음"]

    ev = result.evidence
    lines += ["", "근거",
              f"- 근거가 있는 경기: {ev.get('matches_with_evidence', 0)}",
              f"- 근거가 없는 경기: {ev.get('matches_without_evidence', 0)}",
              f"- 인용된 ID: {ev.get('citations', 0)}",
              f"- 참조 오류: {ev.get('invalid_citation_issues', 0)}"]

    if result.matches:
        lines += ["", "경기별 스코어 흐름 (DA → 맞대결 → 사회자)",
                  "경기 | 데이터 | 맞대결 | 사회자 | 결정"]
        for a in result.matches:
            no, da, mu, mod = a.row
            tail = (f" — {a.panel_status_reason}"
                    if a.panel_status != STATUS_OK and a.panel_status_reason
                    else "")
            lines.append(f"{no} | {da} | {mu} | {mod} | "
                         f"{a.decision_type}{tail}")

    lines += ["", "자료에 없는 것 (추론하지 않는다)"]
    lines += [f"- {x}: {UNOBSERVED}" for x in result.not_in_schema]

    if result.issues:
        lines += ["", "확인 사항"]
        lines += [f"- {i}" for i in result.issues]
    return lines
