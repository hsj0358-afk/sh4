"""분석 결과 → 근거 (Phase 2-G).

## 이 모듈이 하는 일

지표를 근거로 **복사하지 않는다.** 여러 축이 같은 사실을 되풀이해 말할 때
그것을 **하나의 근거로 압축**하고, 그 근거를 만든 지표·축·출처를 잃지 않게
붙여 둔다.

    지표(Metric)      xG = 2.24            관측·계산된 수
          ↓
    발견(Finding)     기회 창출 수준이 높다  지표를 해석한 것
          ↓
    근거(Evidence)    독립적인 발견 하나 + 그것을 지지한 지표·축·출처
          ↓
    [Phase 3] 패널 입력

**지표 ≠ 근거이고, 근거의 개수는 근거의 세기가 아니다.** 지지 지표가 늘어도
근거 개수는 늘지 않는다 (§19·§20).

## 패턴을 문자열로 되읽지 않는다

`detect_*_patterns()` 는 `(코드, 라벨, 근거문자열)` 을 돌려준다. 구동 지표
이름이 구조로 남지 않지만, **그 문자열을 정규식으로 파싱하지 않는다.**
대신 `(축, 코드) → (finding_kind, anchor, drivers)` 를 아래 `CATALOG` 에
선언해 두고, 값은 축의 `Metric` 에서 직접 읽는다. detector 는 '언제 발견이
성립하나' 만 정하고 카탈로그는 '그 발견이 무엇에 관한 것인가' 를 정한다.

덕분에 2-B~2-F 의 출력 문자열과 수치를 **한 글자도 바꾸지 않는다.**

## 합치는 규칙 (§5)

같은 사실이면 근거 하나로 합치되, **자동으로 합치지 않는 조건**이 넷이다.

    같은 finding_kind + 같은 기간/표본 + 견줄 수 있는 원천/산출 방식
        → 근거 하나 (대표 축 + 나머지는 supporting provenance)

    표본이 다르면        → 따로 (recent6 ↔ recent3)
    산출 방식이 다르면    → 따로
    원천이 다르면        → 따로
    같은 값이어도 의미가 다르면 → 따로 (xG 가 '기회 창출' 과 '득점 대비
                                   기대' 두 발견의 재료일 수 있다)

## 하지 않는 것

승무패 추천·점수·투표를 만들지 않는다. 시장 확률(`Match.probs`)을 근거로
승격하지 않는다 — 그것은 패널이 자기 판단과 견주는 기준선(Market
Reference)이고 이 모듈은 아예 읽지 않는다.
"""
from __future__ import annotations

import logging

from . import analysis
from .models import (DERIVED, NEUTRAL, OBSERVED, EvidenceItem, Match,
                     MatchAnalysis, Signal, TeamAnalysis, UNKNOWN)

log = logging.getLogger(__name__)

# ---- 표본 문맥 (§10) -------------------------------------------------------
# `period` 와 중복 저장하지 않는다 — period 는 '어느 구간'(recent6 · home6),
# context 는 '어떤 종류의 비교' 다.
OVERALL = "overall"      # 시즌 전체
RECENT = "recent"        # 최근 N경기
VENUE = "venue"          # 그 장소의 표본 (전체의 부분집합)
SCHEDULE = "schedule"    # 상대 구성

# ---- (축, 패턴 코드) → 그 발견이 무엇에 관한 것인가 --------------------------
#
# `finding_kind` 가 **같은 사실인가**를 정한다. 축이 달라도 같으면 합친다.
# `anchor` 는 그 사실을 대표하는 지표이고, `drivers` 는 detector 가 실제로
# 본 지표 전부다 (지지 지표로 남는다).
#
# **여기가 detector 와 어긋나면 안 된다.** 카탈로그에 없는 코드가 나오면
# 근거를 만들지 않고 로그에 남긴다. 테스트가 라벨 표와 대조해 빠진 코드를
# 잡는다.
CATALOG: dict[tuple[str, str], tuple[str, str, tuple[str, ...]]] = {
    # 2-B 기회의 질
    ("chance_quality", "A"): ("shot_volume_vs_quality", "xg_per_shot",
                              ("shots", "xg_per_shot")),
    ("chance_quality", "B"): ("shot_volume_vs_quality", "xg_per_shot",
                              ("shots", "xg_per_shot")),
    # C 는 '만든 기회 대비 득점' 이다 — 2-D 의 득점↔xG 와 **같은 사실**이라
    # finding_kind 를 같게 둔다. 이것이 실측으로 확인된 중복이다.
    ("chance_quality", "C"): ("goals_vs_xg", "goals_minus_xg",
                              ("xg", "goals_minus_xg")),
    ("chance_quality", "D"): ("chance_and_execution", "xg", ("xg", "xgot")),
    # 2-C 수비의 질
    ("defensive_quality", "A"): ("conceded_volume_vs_quality",
                                 "npxga_per_shot_against",
                                 ("shots_against", "npxga_per_shot_against")),
    ("defensive_quality", "B"): ("conceded_volume_vs_quality",
                                 "npxga_per_shot_against",
                                 ("shots_against", "npxga_per_shot_against")),
    ("defensive_quality", "C"): ("goals_against_vs_npxga",
                                 "goals_against_minus_npxga",
                                 ("npxga", "goals_against_minus_npxga")),
    ("defensive_quality", "D"): ("conceded_chance_and_execution", "npxga",
                                 ("npxga", "xgot_against")),
    # 2-D 지속성
    ("sustainability", "A"): ("goals_vs_xg", "goals_minus_xg",
                              ("goals_minus_xg",)),
    ("sustainability", "B"): ("goals_vs_xg", "goals_minus_xg",
                              ("goals_minus_xg",)),
    ("sustainability", "C"): ("points_vs_xpts", "points_minus_xpts",
                              ("points_minus_xpts",)),
    ("sustainability", "D"): ("points_vs_xpts", "points_minus_xpts",
                              ("points_minus_xpts",)),
    # 2-E 장소 문맥 — **장소는 category 가 아니라 context 다** (§16).
    ("venue_context", "A"): ("venue_result_gap", "points_venue_gap",
                             ("points_venue_gap",)),
    ("venue_context", "B"): ("venue_attack_gap", "npxg_venue_gap",
                             ("npxg_venue_gap", "xg_venue_gap")),
    ("venue_context", "C"): ("venue_defense_gap", "npxga_venue_gap",
                             ("npxga_venue_gap",)),
    ("venue_context", "D"): ("venue_multi_gap", "points_venue_gap",
                             ("points_venue_gap",)),
}

# 축이 어느 category 에 속하나. 기존 `Metric.group` taxonomy 를 쓰되, 축
# 이름만으로 정하지 않고 anchor 지표의 group 을 우선 본다 (아래 `_category`).
_AXIS_FALLBACK_CATEGORY = {
    "chance_quality": "attack",
    "defensive_quality": "defense",
    "sustainability": "sustainability_gap",
    "venue_context": "result",
    "schedule_strength": analysis.SCHEDULE_GROUP,
}
# `Metric.group` → 근거 category. 같은 이야기를 하는 group 을 한 갈래로 모은다.
_GROUP_CATEGORY = {
    analysis.VOLUME: "attack", analysis.CHANCE_CREATION: "attack",
    analysis.EXECUTION: "attack",
    analysis.DEF_VOLUME: "defense", analysis.DEF_QUALITY: "defense",
    analysis.DEF_EXECUTION: "defense", analysis.DEF_OUTCOME: "defense",
    analysis.DEF_GAP: "defense",
    analysis.GAP: "sustainability_gap", analysis.MODEL_GROUP: "sustainability_gap",
    analysis.OUTCOME: "result", analysis.RESULT_GROUP: "result",
    analysis.VENUE_GAP_GROUP: "result",
    analysis.SCHEDULE_GROUP: analysis.SCHEDULE_GROUP,
}

# 2-F 는 detector 가 없다(문턱 미확정). 상대 구성 자체가 하나의 발견이고,
# 지표 둘이 **같은 발견을 지지**하므로 근거는 하나다 (§5-4).
SCHEDULE_FINDING = "opponent_level"
SCHEDULE_ANCHOR = "opponent_points"
SCHEDULE_DRIVERS = ("opponent_points", "opponent_goal_diff")

AXES = ("chance_quality", "defensive_quality", "sustainability",
        "venue_context", "schedule_strength")


def _context_of(period: str) -> str:
    if period == analysis.SEASON:
        return OVERALL
    if period.startswith("recent"):
        return RECENT
    return VENUE


def _category(axis_name: str, anchor: str) -> str:
    group = analysis.GROUPS.get(anchor, "")
    return _GROUP_CATEGORY.get(group) or _AXIS_FALLBACK_CATEGORY.get(
        axis_name, "")


def _values_of(axis, period: str) -> dict:
    """축의 `Metric` 을 detector 가 먹는 `{이름: (값, 표본, 비고)}` 로 되돌린다.

    **문자열을 파싱하지 않는다.** detector 를 그대로 다시 돌려 구조를 얻는다.
    """
    prefix = f"{period}."
    return {k[len(prefix):]: (m.value, m.sample_count, m.note)
            for k, m in axis.metrics.items() if k.startswith(prefix)}


def _periods_of(axis) -> list[str]:
    seen = {k.split(".", 1)[0] for k in axis.metrics}
    return sorted(seen, key=analysis.period_sort_key)


def _findings(axis_name: str, axis, config: dict, min_sample: int
              ) -> list[tuple[str, str, str, str]]:
    """축에서 `(기간, 코드, 라벨, 근거문자열)` 을 뽑는다.

    detector 를 축의 값으로 다시 돌린다 — 축이 이미 notes 에 적어 둔 문자열을
    되읽는 것보다 정확하고, 기간별로 나눠 볼 수 있다.
    """
    out = []
    for period in _periods_of(axis):
        values = _values_of(axis, period)
        if axis_name == "chance_quality":
            found = analysis.detect_patterns(values, config)
        elif axis_name == "defensive_quality":
            found = analysis.detect_defensive_patterns(values, config)
        elif axis_name == "sustainability":
            found = analysis.detect_sustainability_patterns(values, min_sample)
        elif axis_name == "venue_context":
            found = analysis.detect_venue_patterns(values, config)
        else:
            found = []
        for code, label, basis in found:
            out.append((period, code, label, basis))
    return out


def _sample_key(anchor) -> tuple:
    """표본 동일성. 표본이 다르면 같은 사실로 합치지 않는다 (§5-6).

    **anchor 하나만 본다.** 그 사실을 가리키는 지표가 anchor 이고, 곁들여
    보는 지표(2-B 가 득점↔xG 를 말할 때 함께 보는 xG 수준 같은 것)는 축마다
    다를 수 있다. 그것까지 열쇠에 넣으면 같은 사실이 축마다 갈라진다.

    `common_sample_count` 는 **열쇠에 넣지 않는다.** 그것은 표본 크기가
    아니라 '어떻게 셌나' 이고, 같은 6경기를 2-D 는 공통 표본으로 명시하고
    2-B 는 적지 않을 뿐이다. 대신 `_rank()` 가 그것을 보고 더 엄격하게 잰
    쪽을 대표로 고른다 (§6-1).

    한계: `Metric` 이 경기 ID 집합을 들고 다니지 않아 **표본 크기가 같지만
    경기가 다른 경우**는 구분하지 못한다. 기간·원천·산출 방식이 함께 같아야
    하므로 실제로 어긋날 여지는 좁지만, 완전한 동일성 검사는 아니다.
    """
    if anchor is None:
        return ()
    return (anchor.name, anchor.sample_count)


def _origin_key(anchor) -> tuple:
    """원천·산출 방식. 다르면 합치지 않는다 (§5-7)."""
    if anchor is None:
        return ()
    return (anchor.source, anchor.measurement_basis)


class _Candidate:
    """근거 후보 하나. 합치기 전 단계다."""

    __slots__ = ("team", "axis", "finding", "anchor", "period", "context",
                 "category", "claim", "basis", "metrics", "drivers")

    def __init__(self, team, axis, finding, anchor, period, context,
                 category, claim, basis, metrics, drivers):
        self.team = team
        self.axis = axis
        self.finding = finding
        self.anchor = anchor
        self.period = period
        self.context = context
        self.category = category
        self.claim = claim
        self.basis = basis
        self.metrics = metrics          # [Metric] — anchor 포함, 실재하는 것만
        self.drivers = drivers          # [str]

    @property
    def key(self) -> tuple:
        """**같은 사실인가**를 정하는 열쇠 (§5-3).

        지표 이름이 아니라 의미(finding)로 묶고, 표본과 원천이 같아야
        합쳐진다. 같은 값이어도 finding 이 다르면 열쇠가 달라 따로 남는다.
        """
        anchor = self.anchor_metric
        return (self.team, self.finding, self.context, self.period,
                _sample_key(anchor), _origin_key(anchor))

    @property
    def anchor_metric(self):
        for m in self.metrics:
            if m.name == self.anchor:
                return m
        return self.metrics[0] if self.metrics else None


def _rank(candidate: _Candidate) -> tuple:
    """대표를 고르는 순서 (§6). 앞이 작을수록 대표에 가깝다.

    1. **공통 표본을 쓴 분석이 먼저.** 2-D 는 양쪽 값이 다 있는 경기에서만
       차이를 만들므로 같은 사실을 더 엄격하게 잰 것이다.
    2. 원천·산출 방식이 적힌 것이 먼저.
    3. 지지 지표가 적은 쪽이 먼저 — 그 사실을 **더 직접** 말한다.
       (2-B 의 득점↔xG 는 xG 수준까지 얹어 말하므로 덜 직접적이다.)
    4. 그래도 같으면 축 이름 — 실행마다 같은 대표가 나오게 한다.

    특정 사례를 하드코딩하지 않는다. 이 규칙만으로 2-D 가 2-B 를 이긴다.
    """
    anchor = candidate.anchor_metric
    common = getattr(anchor, "common_sample_count", None) if anchor else None
    known = bool(anchor and anchor.source and anchor.measurement_basis)
    return (0 if common is not None else 1,
            0 if known else 1,
            len(candidate.drivers),
            candidate.axis)


def _claim_of(candidate: _Candidate) -> str:
    """화면에 나갈 한 줄. **추천 어휘를 쓰지 않는다** (§19).

    라벨은 detector 가 만든 상태 설명이고, 여기서는 어느 표본에서 관찰됐는지
    만 덧붙인다.
    """
    where = analysis.period_label(candidate.period)
    return f"{where} 표본에서 {candidate.claim} (관찰)"


def _candidates_for(team_analysis: TeamAnalysis, settings) -> list[_Candidate]:
    if team_analysis is None:
        return []
    team = team_analysis.team or ""
    min_sample = analysis.trend_min_sample(settings)
    configs = {
        "chance_quality": analysis.chance_quality_config(settings),
        "defensive_quality": analysis.defensive_quality_config(settings),
        "venue_context": analysis.venue_context_config(settings),
        "sustainability": {},
    }
    out: list[_Candidate] = []
    for axis_name in AXES:
        axis = getattr(team_analysis, axis_name, None)
        if axis is None or not axis.metrics:
            continue
        if axis_name == "schedule_strength":
            out.extend(_schedule_candidates(team, axis))
            continue
        for period, code, label, basis in _findings(
                axis_name, axis, configs.get(axis_name, {}), min_sample):
            spec = CATALOG.get((axis_name, code))
            if spec is None:
                log.debug("카탈로그에 없는 패턴 %s/%s — 근거로 만들지 않음",
                          axis_name, code)
                continue
            finding, anchor, drivers = spec
            metrics = [m for m in
                       (axis.get(analysis.metric_key(period, d))
                        for d in drivers) if m is not None]
            if not metrics:
                continue
            out.append(_Candidate(
                team, axis_name, finding, anchor, period,
                _context_of(period), _category(axis_name, anchor),
                label, basis, metrics, [m.name for m in metrics]))
    return out


def _schedule_candidates(team: str, axis) -> list[_Candidate]:
    """2-F 는 detector 가 없다 — 값이 있으면 그 자체가 상대 구성 발견이다.

    지표 둘(`opponent_points`·`opponent_goal_diff`)이 **같은 발견을
    지지**하므로 근거는 기간당 하나다 (§5-4).
    """
    out = []
    for period in _periods_of(axis):
        metrics = [m for m in
                   (axis.get(analysis.metric_key(period, d))
                    for d in SCHEDULE_DRIVERS) if m is not None]
        if not metrics:
            continue
        points = axis.get(analysis.metric_key(period, SCHEDULE_ANCHOR))
        if points is None:
            continue
        out.append(_Candidate(
            team, "schedule_strength", SCHEDULE_FINDING, SCHEDULE_ANCHOR,
            period, SCHEDULE, analysis.SCHEDULE_GROUP,
            "해당 기간 상대 구성의 성과 수준이 관찰됨",
            f"상대 경기당 승점 {points.value:.2f}", metrics,
            [m.name for m in metrics]))
    return out


def _same_metric_axes(team_analysis: TeamAnalysis, anchor,
                      chosen_axis: str) -> list[str]:
    """같은 지표를 **같은 정체성으로** 들고 있는 다른 축들 (§5-1).

    2-B 와 2-D 의 `goals_minus_xg` 처럼, 패턴이 한쪽에서만 떠도 같은 사실을
    다른 축이 들고 있으면 그 축을 supporting provenance 로 남긴다. 대표를
    골랐다고 원래 발견이 사라지면 안 된다 (§5-2).

    값·표본·원천·산출 방식이 하나라도 다르면 **같은 것으로 보지 않는다.**

    `common_sample_count` 는 **여기서도 보지 않는다** — `_sample_key()` 와
    같은 이유이고, 두 곳의 기준이 어긋나면 안 되기 때문이다. 실물 260048
    에서 2-B 와 2-D 의 `season.goals_minus_xg` 는 값(0.7599999999999998)·
    표본·원천·산출 방식이 전부 같고 **오직 2-D 만 공통 표본 수를 적어
    둔다.** 그것까지 대조하면, 두 축이 함께 발견했을 때는 근거 하나로
    합쳐지면서 2-D 만 발견했을 때는 2-B 가 provenance 에서 사라지는
    엇갈린 동작이 된다.
    """
    if anchor is None:
        return []
    key = analysis.metric_key(anchor.period, anchor.name)
    out = []
    for axis_name in AXES:
        if axis_name == chosen_axis:
            continue
        axis = getattr(team_analysis, axis_name, None)
        other = axis.get(key) if axis is not None else None
        if other is None:
            continue
        same = (other.value == anchor.value
                and _sample_key(other) == _sample_key(anchor)
                and _origin_key(other) == _origin_key(anchor))
        if same:
            out.append(axis_name)
    return out


def build_evidence(team_analysis: TeamAnalysis, settings) -> list[EvidenceItem]:
    """한 팀의 근거 목록. 같은 사실은 하나로 합친다."""
    groups: dict[tuple, list[_Candidate]] = {}
    for cand in _candidates_for(team_analysis, settings):
        groups.setdefault(cand.key, []).append(cand)

    items: list[EvidenceItem] = []
    for key, members in groups.items():
        members.sort(key=_rank)
        rep = members[0]
        anchor = rep.anchor_metric
        # 같은 사실을 말한 축: 함께 발견된 축 + 같은 지표를 들고 있는 축
        axes = {m.axis for m in members}
        axes.update(_same_metric_axes(team_analysis, anchor, rep.axis))
        axes.discard(rep.axis)
        metrics = {}
        for m in members:
            for metric in m.metrics:
                metrics[metric.name] = metric
        items.append(EvidenceItem(
            claim=_claim_of(rep),
            side=NEUTRAL,               # **추천이 아니다** — 항상 중립이다
            counter=False,
            metric=rep.anchor,
            value=anchor.value if anchor else None,
            comparison=rep.basis,
            period=rep.period,
            sample_count=anchor.sample_count if anchor else None,
            provenance=(anchor.provenance if anchor else OBSERVED),
            axis=rep.axis,
            team=rep.team,
            category=rep.category,
            context=rep.context,
            finding_kind=rep.finding,
            supporting_metrics=sorted(metrics),
            supporting_axes=sorted(axes),
            source=(anchor.source if anchor else ""),
            measurement_basis=(anchor.measurement_basis if anchor else ""),
        ))
    items.sort(key=_order)
    return items


def _order(item: EvidenceItem) -> tuple:
    """출력 순서 (§21). 집합·사전 순서에 기대지 않는다."""
    return (item.team, item.category, item.context,
            analysis.period_sort_key(item.period), item.finding_kind,
            item.metric)


def find_conflicts(items: list[EvidenceItem]) -> list[Signal]:
    """같은 팀·같은 사실인데 **표본에 따라 방향이 반대**인 경우 (§7).

    한쪽을 지우거나 점수로 상쇄하지 않는다 — 둘 다 남기고 관계만 적는다.
    `lean` 은 언제나 UNKNOWN 이다. 이것을 픽으로 읽으면 안 된다.
    """
    out: list[Signal] = []
    by_fact: dict[tuple, list[EvidenceItem]] = {}
    for item in items:
        if item.value is None:
            continue
        by_fact.setdefault((item.team, item.finding_kind), []).append(item)
    for (team, finding), group in sorted(by_fact.items()):
        highs = [i for i in group if i.value > 0]
        lows = [i for i in group if i.value < 0]
        if not highs or not lows:
            continue
        out.append(Signal(
            name=f"{finding} 방향 불일치",
            lean=UNKNOWN,               # **픽이 아니다**
            strength="",                # 세기를 매기지 않는다
            basis=(f"{team}: "
                   + " ↔ ".join(
                       f"{analysis.period_label(i.period)} {i.value:+.2f}"
                       for i in (highs[0], lows[0]))),
            sample_count=None,
            provenance=DERIVED,
            note="표본에 따라 방향이 다릅니다. 둘 다 그대로 둡니다."))
    return out


def attach_evidence(matches: list[Match], settings) -> None:
    """14경기에 근거를 붙인다. **분석을 다시 계산하지 않는다** (§30).

    이미 만들어진 `MatchAnalysis` 를 읽을 뿐이고, 소스를 다시 부르지 않는다.
    `Match.probs`(시장 확률)는 읽지도 쓰지도 않는다 (§18).
    """
    built = total = 0
    for match in matches:
        data = getattr(match, "analysis", None)
        if data is None:
            continue
        items: list[EvidenceItem] = []
        for side in ("home", "away"):
            items.extend(build_evidence(getattr(data, side, None), settings))
        items.sort(key=_order)
        data.evidence = items
        data.conflicts = find_conflicts(items)
        total += len(items)
        built += 1 if items else 0
    if total or built:
        supporting = sum(len(i.supporting_metrics)
                         for m in matches if m.analysis
                         for i in m.analysis.evidence)
        log.info("근거(2-G): %d경기 · 근거 %d건 · 지지 지표 %d개 "
                 "(개수는 세기가 아닙니다)", built, total, supporting)
