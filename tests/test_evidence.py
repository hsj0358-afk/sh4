"""근거 생성 회귀 테스트 (Phase 2-G · Evidence Generator).

고정하려는 것은 다섯 가지다.

1. **지표를 근거로 복사하지 않는다.** 근거의 최소 단위는 발견(Finding)이고,
   여러 지표가 한 발견을 지지하면 근거는 하나다.
2. **같은 사실은 하나로 합친다.** 축이 달라도 finding·기간·표본·원천이
   같으면 대표 하나 + 나머지는 supporting provenance 다.
3. **자동으로 합치지 않는 조건이 넷이다.** 표본·산출 방식·원천이 다르거나
   의미가 다르면 따로 남는다.
4. **근거의 개수는 세기가 아니다.** 지지 지표가 늘어도 근거는 안 늘어난다.
5. **추천도 점수도 시장 확률도 없다.**

pytest 없이도 돈다:  python tests/test_evidence.py
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import analysis, evidence                            # noqa: E402
from toto.models import (DERIVED, NEUTRAL, OBSERVED, UNKNOWN,  # noqa: E402
                         AnalysisAxis, EvidenceItem, MatchAnalysis, Metric,
                         TeamAnalysis, revive_match_analysis)
from toto.settings import Settings                             # noqa: E402

UTC = timezone.utc
S = Settings(analysis={"trend_min_sample": 3})


def metric(name, value, period, sample, *, common=None,
           source=analysis.DERIVED_SOURCE, basis=analysis.MIXED_BASIS,
           provenance=DERIVED) -> Metric:
    return Metric(name=name, label=analysis.SPECS.get(name, (name,))[0],
                  value=value, period=period, sample_count=sample,
                  common_sample_count=common, provenance=provenance,
                  unit=analysis.SPECS.get(name, ("", ""))[1],
                  direction=analysis.SPECS.get(name, ("", "", ""))[2]
                  if name in analysis.SPECS else "",
                  group=analysis.GROUPS.get(name, ""),
                  source=source, measurement_basis=basis)


def shot(name, value, period, sample) -> Metric:
    return metric(name, value, period, sample, source=analysis.SHOTMAP,
                  basis=analysis.SHOT_EVENTS, provenance=OBSERVED)


def axis(name, cells) -> AnalysisAxis:
    ax = AnalysisAxis(name=name)
    for m in cells:
        ax.metrics[analysis.metric_key(m.period, m.name)] = m
    return ax


def team_with(**axes) -> TeamAnalysis:
    ta = TeamAnalysis(team=axes.pop("team", "T"),
                      is_home=axes.pop("is_home", True))
    for key, value in axes.items():
        setattr(ta, key, value)
    return ta


# 2-B 패턴 C(xG 높고 득점−xG 낮음) + 2-D 패턴 A(같은 gap) 가 동시에 뜨는 짝
def dup_pair(period="recent6", sample=6, gap=-0.40, basis=None):
    cq = axis("chance_quality", [
        shot("xg", 1.70, period, sample),
        metric("goals_minus_xg", gap, period, sample)])
    su = axis("sustainability", [
        metric("goals_minus_xg", gap, period, sample, common=sample,
               basis=basis or analysis.MIXED_BASIS)])
    return cq, su


# --------------------------------------------------------------------------
# A. Metric → Evidence
# --------------------------------------------------------------------------
def test_a1_metric_is_not_copied_into_evidence():
    """지표만 있고 발견이 없으면 근거도 없다."""
    ta = team_with(chance_quality=axis("chance_quality", [
        shot("xg", 1.10, "recent6", 6),          # 문턱(1.60) 아래
        shot("shots", 11.0, "recent6", 6)]))
    assert evidence.build_evidence(ta, S) == []


def test_a2_below_threshold_is_not_promoted():
    ta = team_with(sustainability=axis("sustainability", [
        metric("goals_minus_xg", 0.0, "recent6", 6, common=6)]))
    assert evidence.build_evidence(ta, S) == [], "차이 0 은 발견이 아니다"


def test_a3_small_sample_is_not_promoted():
    ta = team_with(sustainability=axis("sustainability", [
        metric("goals_minus_xg", -0.40, "recent6", 2, common=2)]))
    assert evidence.build_evidence(ta, S) == [], "표본 2 는 최소 3 미만"


def test_a4_finding_becomes_a_candidate():
    ta = team_with(sustainability=axis("sustainability", [
        metric("goals_minus_xg", -0.40, "recent6", 6, common=6)]))
    items = evidence.build_evidence(ta, S)
    assert len(items) == 1
    assert items[0].finding_kind == "goals_vs_xg"
    assert items[0].metric == "goals_minus_xg"


def test_a5_several_metrics_one_evidence():
    """한 발견을 여러 지표가 지지해도 근거는 하나다 (§4)."""
    ta = team_with(chance_quality=axis("chance_quality", [
        shot("xg", 1.70, "recent6", 6), shot("xgot", 1.50, "recent6", 6)]))
    items = evidence.build_evidence(ta, S)
    assert len(items) == 1
    assert sorted(items[0].supporting_metrics) == ["xg", "xgot"]


# --------------------------------------------------------------------------
# B. Deduplication
# --------------------------------------------------------------------------
def test_b4_same_metric_meaning_sample_gives_one():
    cq, su = dup_pair()
    items = evidence.build_evidence(team_with(chance_quality=cq,
                                              sustainability=su), S)
    assert len(items) == 1, [i.axis for i in items]


def test_b5_different_sample_gives_two():
    cq = axis("chance_quality", [
        shot("xg", 1.70, "recent6", 6),
        metric("goals_minus_xg", -0.40, "recent6", 6)])
    su = axis("sustainability", [
        metric("goals_minus_xg", -0.40, "recent3", 3, common=3)])
    items = evidence.build_evidence(team_with(chance_quality=cq,
                                              sustainability=su), S)
    assert len(items) == 2, [(i.axis, i.period) for i in items]


def test_b6_different_basis_gives_two():
    cq, su = dup_pair(basis=analysis.OPPONENT_RECORD)
    items = evidence.build_evidence(team_with(chance_quality=cq,
                                              sustainability=su), S)
    assert len(items) == 2, [i.measurement_basis for i in items]


def test_b7_same_value_different_meaning_gives_two():
    """같은 xG 가 두 발견의 재료여도 합치지 않는다 (§5-5)."""
    cq = axis("chance_quality", [
        shot("xg", 2.24, "recent6", 6), shot("xgot", 2.02, "recent6", 6),
        metric("goals_minus_xg", -0.40, "recent6", 6)])
    su = axis("sustainability", [
        metric("goals_minus_xg", -0.40, "recent6", 6, common=6)])
    items = evidence.build_evidence(team_with(chance_quality=cq,
                                              sustainability=su), S)
    kinds = sorted(i.finding_kind for i in items)
    assert kinds == ["chance_and_execution", "goals_vs_xg"], kinds


def test_b8_different_metrics_one_finding_one_evidence():
    """상대 승점과 득실차는 같은 발견을 지지한다 (§5-4)."""
    sos = axis("schedule_strength", [
        metric("opponent_points", 1.82, "recent6", 6,
               source=analysis.SEASON_MATCH_INDEX,
               basis=analysis.OPPONENT_RECORD, provenance=OBSERVED),
        metric("opponent_goal_diff", 0.74, "recent6", 6,
               source=analysis.SEASON_MATCH_INDEX,
               basis=analysis.OPPONENT_RECORD, provenance=OBSERVED)])
    items = evidence.build_evidence(team_with(schedule_strength=sos), S)
    assert len(items) == 1
    assert sorted(items[0].supporting_metrics) == ["opponent_goal_diff",
                                                   "opponent_points"]


def test_b9_supporting_metrics_are_all_kept():
    cq, su = dup_pair()
    item = evidence.build_evidence(team_with(chance_quality=cq,
                                             sustainability=su), S)[0]
    assert sorted(item.supporting_metrics) == ["goals_minus_xg", "xg"]


def test_b10_supporting_axes_are_all_kept():
    cq, su = dup_pair()
    item = evidence.build_evidence(team_with(chance_quality=cq,
                                             sustainability=su), S)[0]
    assert item.axis == "sustainability"
    assert item.supporting_axes == ["chance_quality"]


def test_b11_representative_is_deterministic():
    cq, su = dup_pair()
    first = evidence.build_evidence(team_with(chance_quality=cq,
                                              sustainability=su), S)
    # 축을 반대 순서로 붙여도 같은 대표가 나온다
    ta = TeamAnalysis(team="T", is_home=True)
    ta.sustainability, ta.chance_quality = su, cq
    second = evidence.build_evidence(ta, S)
    assert [i.axis for i in first] == [i.axis for i in second]
    assert first[0].axis == "sustainability"


def test_b12_order_is_deterministic():
    cq = axis("chance_quality", [
        shot("xg", 1.70, "recent6", 6), shot("xgot", 1.50, "recent6", 6),
        metric("goals_minus_xg", -0.40, "recent6", 6)])
    su = axis("sustainability", [
        metric("goals_minus_xg", -0.40, "recent6", 6, common=6),
        metric("points_minus_xpts", 0.5, "recent6", 6, common=6)])
    ta = team_with(chance_quality=cq, sustainability=su)
    runs = [[(i.category, i.context, i.period, i.finding_kind)
             for i in evidence.build_evidence(ta, S)] for _ in range(5)]
    assert all(r == runs[0] for r in runs)
    assert runs[0] == sorted(runs[0]), "정렬 규칙이 적용되지 않았다"


# --------------------------------------------------------------------------
# C. 실측으로 확인된 중복 (§28)
# --------------------------------------------------------------------------
def test_c13_known_duplicate_becomes_one():
    cq, su = dup_pair()
    items = evidence.build_evidence(team_with(chance_quality=cq,
                                              sustainability=su), S)
    assert len(items) == 1


def test_c14_sustainability_is_representative():
    cq, su = dup_pair()
    assert evidence.build_evidence(
        team_with(chance_quality=cq, sustainability=su), S)[0].axis \
        == "sustainability"


def test_c15_chance_quality_is_supporting():
    cq, su = dup_pair()
    item = evidence.build_evidence(team_with(chance_quality=cq,
                                             sustainability=su), S)[0]
    assert "chance_quality" in item.supporting_axes


def test_c16_supporting_axis_survives_even_without_its_own_finding():
    """2-B 패턴이 안 떠도 같은 지표를 들고 있으면 provenance 로 남는다.

    §28 의 `+0.76` 사례다 — 그 값에서는 2-B 패턴 C 가 뜨지 않지만 2-B 가
    같은 `goals_minus_xg` 를 들고 있으므로 supporting 으로 남아야 한다.
    """
    cq = axis("chance_quality", [
        metric("goals_minus_xg", 0.76, "recent6", 6)])
    su = axis("sustainability", [
        metric("goals_minus_xg", 0.76, "recent6", 6)])
    items = evidence.build_evidence(team_with(chance_quality=cq,
                                              sustainability=su), S)
    assert len(items) == 1, "근거가 하나여야 한다"
    assert items[0].axis == "sustainability"
    assert items[0].supporting_axes == ["chance_quality"], \
        "2-B 가 provenance 에서 사라졌다"


def test_c16a_provenance_survives_the_common_count_asymmetry():
    """2-D 만 공통 표본 수를 적는다 — 그것 때문에 갈라지면 안 된다.

    실물 260048 의 모양이다: 두 축의 `season.goals_minus_xg` 가 값·표본·
    원천·산출 방식까지 같은데 `common_sample_count` 만 2-D 에 있다.
    합치기 열쇠(`_sample_key`)가 그것을 보지 않으므로 provenance 도 봐서는
    안 된다 — 보면 '둘 다 발견하면 합쳐지고 하나만 발견하면 사라지는'
    엇갈린 동작이 된다.
    """
    cq = axis("chance_quality", [
        metric("goals_minus_xg", 0.7599999999999998, "season", 6)])
    su = axis("sustainability", [
        metric("goals_minus_xg", 0.7599999999999998, "season", 6, common=6)])
    items = evidence.build_evidence(team_with(chance_quality=cq,
                                              sustainability=su), S)
    assert len(items) == 1
    assert items[0].axis == "sustainability", "공통 표본을 쓴 쪽이 대표다"
    assert items[0].supporting_axes == ["chance_quality"], \
        "공통 표본 수 차이만으로 provenance 가 끊겼다"


def test_c16b_provenance_needs_the_same_identity():
    """값이 달라지면 같은 사실로 보지 않는다."""
    cq = axis("chance_quality", [
        metric("goals_minus_xg", 0.10, "recent6", 6)])
    su = axis("sustainability", [
        metric("goals_minus_xg", 0.76, "recent6", 6)])
    item = evidence.build_evidence(team_with(chance_quality=cq,
                                             sustainability=su), S)[0]
    assert item.supporting_axes == []


# --------------------------------------------------------------------------
# D. Venue
# --------------------------------------------------------------------------
def venue_axis(venue="home", period="home6", gap=0.55):
    return axis("venue_context", [
        metric(f"points{analysis.VENUE_GAP_SUFFIX}", gap, period, 4,
               common=4, source=analysis.DERIVED_SOURCE,
               basis=analysis.FINAL_SCORE)])


def test_d17_venue_is_not_a_category():
    item = evidence.build_evidence(
        team_with(venue_context=venue_axis()), S)[0]
    assert item.category != "venue", "장소를 category 로 만들었다"
    assert item.category in ("result", "attack", "defense")


def test_d18_venue_is_a_context():
    item = evidence.build_evidence(
        team_with(venue_context=venue_axis()), S)[0]
    assert item.context == evidence.VENUE
    assert item.period == "home6"


def test_d19_home_and_away_use_the_same_rule():
    home = evidence.build_evidence(
        team_with(team="H", is_home=True,
                  venue_context=venue_axis("home", "home6")), S)
    away = evidence.build_evidence(
        team_with(team="A", is_home=False,
                  venue_context=venue_axis("away", "away6")), S)
    assert len(home) == len(away) == 1
    assert home[0].finding_kind == away[0].finding_kind
    assert home[0].category == away[0].category
    assert home[0].context == away[0].context == evidence.VENUE


def test_d20_small_venue_sample_makes_no_evidence():
    ax = axis("venue_context", [
        metric(f"points{analysis.VENUE_GAP_SUFFIX}", 0.55, "home6", 2,
               common=2, basis=analysis.FINAL_SCORE)])
    assert evidence.build_evidence(team_with(venue_context=ax), S) == []


# --------------------------------------------------------------------------
# E. Schedule
# --------------------------------------------------------------------------
def sos_axis(period="recent6", sample=6):
    return axis("schedule_strength", [
        metric("opponent_points", 1.82, period, sample,
               source=analysis.SEASON_MATCH_INDEX,
               basis=analysis.OPPONENT_RECORD, provenance=OBSERVED),
        metric("opponent_goal_diff", 0.74, period, sample,
               source=analysis.SEASON_MATCH_INDEX,
               basis=analysis.OPPONENT_RECORD, provenance=OBSERVED)])


def test_e21_schedule_group_is_kept():
    item = evidence.build_evidence(
        team_with(schedule_strength=sos_axis()), S)[0]
    assert item.category == analysis.SCHEDULE_GROUP
    assert item.context == evidence.SCHEDULE


def test_e22_no_single_sos_score():
    src = inspect.getsource(evidence)
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    for banned in ("sos_score", "strength_score", "evidence_score",
                   "adjusted_performance", "net_score"):
        assert banned not in code, banned


def test_e23_values_are_passed_through_unchanged():
    ax = sos_axis()
    item = evidence.build_evidence(
        team_with(schedule_strength=ax), S)[0]
    assert item.value == 1.82, "상대 강도 값을 바꿨다"
    assert item.sample_count == 6


def test_e24_missing_schedule_makes_no_evidence():
    assert evidence.build_evidence(
        team_with(schedule_strength=axis("schedule_strength", [])), S) == []


def test_e25_opponent_record_basis_is_kept():
    item = evidence.build_evidence(
        team_with(schedule_strength=sos_axis()), S)[0]
    assert item.measurement_basis == analysis.OPPONENT_RECORD
    assert item.source == analysis.SEASON_MATCH_INDEX


# --------------------------------------------------------------------------
# F. Conflict
# --------------------------------------------------------------------------
def conflicting():
    su = axis("sustainability", [
        metric("goals_minus_xg", 0.60, "recent6", 6, common=6),
        metric("goals_minus_xg", -0.50, "recent3", 3, common=3)])
    return team_with(sustainability=su)


def test_f26_opposing_evidence_can_coexist():
    items = evidence.build_evidence(conflicting(), S)
    assert len(items) == 2
    assert {i.value for i in items} == {0.60, -0.50}


def test_f27_nothing_is_deleted_and_a_relation_is_recorded():
    items = evidence.build_evidence(conflicting(), S)
    conflicts = evidence.find_conflicts(items)
    assert len(items) == 2, "한쪽을 지웠다"
    assert len(conflicts) == 1
    assert conflicts[0].lean == UNKNOWN, "픽으로 읽힐 수 있다"
    assert conflicts[0].strength == "", "세기를 매겼다"


def test_f28_no_score_or_vote():
    src = inspect.getsource(evidence)
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    for banned in ("vote", "net_evidence", "tally", "weight"):
        assert banned not in code.lower(), banned
    tree = ast.parse(inspect.getsource(evidence))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            assert "score" not in node.name.lower(), node.name


# --------------------------------------------------------------------------
# G. Market
# --------------------------------------------------------------------------
def test_g29_market_probability_never_becomes_evidence():
    from toto import fixtures
    from toto.analyze import run_all
    s = Settings(fotmob={"shot_recent_windows": [6, 3],
                         "match_detail_matches": 6})
    matches = fixtures.build_demo_matches()
    run_all(matches, s, season_matches=[])
    for m in matches:
        for item in (m.analysis.evidence if m.analysis else []):
            assert "probab" not in item.metric.lower()
            assert item.category != "market"
            for word in ("배당", "확률", "market"):
                assert word not in item.claim, item.claim


def test_g30_no_probability_references_in_the_module():
    tree = ast.parse(inspect.getsource(evidence))
    banned = {"predict", "probs", "MatchProb", "odds",
              "additive_probabilities", "implied"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id not in banned, node.id
        if isinstance(node, ast.Attribute):
            assert node.attr not in banned, node.attr
    imports = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
               for a in n.names]
    imports += [n.module for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) and n.module]
    assert not any("predict" in (i or "") for i in imports)


def test_g31_market_reference_is_untouched():
    from toto import fixtures
    from toto.analyze import run_all
    s = Settings(fotmob={"shot_recent_windows": [6, 3]})
    matches = fixtures.build_demo_matches()
    run_all(matches, s, season_matches=[])
    before = [(m.odds.home, m.odds.draw, m.odds.away) for m in matches]
    probs = [m.probs.as_tuple if m.probs else None for m in matches]
    run_all(matches, s, season_matches=[])
    assert [(m.odds.home, m.odds.draw, m.odds.away)
            for m in matches] == before
    assert [m.probs.as_tuple if m.probs else None for m in matches] == probs


# --------------------------------------------------------------------------
# H. 추천 격리
# --------------------------------------------------------------------------
def test_h32_h33_no_recommendation_fields():
    src = inspect.getsource(evidence)
    for banned in ("final_pick", "recommended_pick", "recommendation",
                   "predicted_result", "best_bet"):
        assert banned not in src, banned
    item = EvidenceItem()
    for banned in ("final_pick", "recommendation", "predicted_result"):
        assert not hasattr(item, banned), banned


def test_h34_no_pick_language_in_claims():
    cq, su = dup_pair()
    ta = team_with(chance_quality=cq, sustainability=su,
                   schedule_strength=sos_axis(),
                   venue_context=venue_axis())
    for item in evidence.build_evidence(ta, S):
        for word in ("추천", "승 예상", "유리", "불리", "확실", "강력",
                     "가능성이 높", "더 강하다"):
            assert word not in item.claim, f"{word}: {item.claim}"


def test_h35_side_stays_neutral():
    cq, su = dup_pair()
    for item in evidence.build_evidence(
            team_with(chance_quality=cq, sustainability=su), S):
        assert item.side == NEUTRAL, "근거가 결과를 지지하게 만들었다"


def test_h35b_count_is_not_used_as_strength():
    """지지 지표가 늘어도 근거 개수는 늘지 않는다 (§20)."""
    one = axis("chance_quality", [shot("xg", 1.70, "recent6", 6),
                                  shot("xgot", 1.50, "recent6", 6)])
    items = evidence.build_evidence(team_with(chance_quality=one), S)
    assert len(items) == 1 and len(items[0].supporting_metrics) == 2


# --------------------------------------------------------------------------
# I. 데이터 품질
# --------------------------------------------------------------------------
def test_i36_none_is_not_zero():
    ax = axis("sustainability", [
        metric("goals_minus_xg", None, "recent6", 6, common=6)])
    assert evidence.build_evidence(team_with(sustainability=ax), S) == []


def test_i37_missing_axis_is_skipped():
    assert evidence.build_evidence(team_with(), S) == []
    assert evidence.build_evidence(None, S) == []


def test_i38_incomparable_origin_is_not_merged():
    cq, su = dup_pair(basis=analysis.SHOT_EVENTS)
    items = evidence.build_evidence(team_with(chance_quality=cq,
                                              sustainability=su), S)
    assert len(items) == 2


def test_i39_sample_count_is_preserved():
    cq, su = dup_pair(sample=5)
    item = evidence.build_evidence(team_with(chance_quality=cq,
                                             sustainability=su), S)[0]
    assert item.sample_count == 5


def test_i40_serialization_round_trip():
    cq, su = dup_pair()
    ta = team_with(chance_quality=cq, sustainability=su)
    ma = MatchAnalysis(home=ta)
    ma.evidence = evidence.build_evidence(ta, S)
    ma.conflicts = evidence.find_conflicts(ma.evidence)
    back = revive_match_analysis(json.loads(json.dumps(asdict(ma),
                                                       default=str)))
    assert len(back.evidence) == 1
    item = back.evidence[0]
    assert item.finding_kind == "goals_vs_xg"
    assert item.supporting_axes == ["chance_quality"]
    assert item.supporting_metrics == ["goals_minus_xg", "xg"]
    assert item.measurement_basis == analysis.MIXED_BASIS


def test_i40b_old_payload_without_new_fields_revives():
    cq, su = dup_pair()
    ta = team_with(chance_quality=cq, sustainability=su)
    ma = MatchAnalysis(home=ta)
    ma.evidence = evidence.build_evidence(ta, S)
    raw = asdict(ma)
    for cell in raw["evidence"]:
        for key in ("team", "category", "context", "finding_kind",
                    "supporting_metrics", "supporting_axes", "source",
                    "measurement_basis"):
            cell.pop(key, None)
    back = revive_match_analysis(raw)
    assert back.evidence[0].finding_kind == ""
    assert back.evidence[0].supporting_metrics == []


# --------------------------------------------------------------------------
# 카탈로그 무결성 · 파이프라인
# --------------------------------------------------------------------------
def test_catalog_covers_every_pattern_code():
    """detector 가 만들 수 있는 코드가 카탈로그에 전부 있어야 한다."""
    expected = set()
    for axis_name, labels in (
            ("chance_quality", analysis.PATTERN_LABELS),
            ("defensive_quality", analysis.DEFENSIVE_PATTERN_LABELS),
            ("sustainability", analysis.SUSTAIN_PATTERN_LABELS),
            ("venue_context", analysis.VENUE_PATTERN_LABELS)):
        for code in labels:
            expected.add((axis_name, code))
    missing = expected - set(evidence.CATALOG)
    assert not missing, f"카탈로그에 없는 패턴: {sorted(missing)}"
    extra = set(evidence.CATALOG) - expected
    assert not extra, f"detector 에 없는 항목: {sorted(extra)}"


def test_catalog_metric_names_exist():
    for (axis_name, code), (_kind, anchor, drivers) in \
            evidence.CATALOG.items():
        assert anchor in analysis.SPECS, f"{axis_name}/{code}: {anchor}"
        assert anchor in drivers, f"{axis_name}/{code}: anchor 가 driver 에 없다"
        for name in drivers:
            assert name in analysis.SPECS, f"{axis_name}/{code}: {name}"


# --------------------------------------------------------------------------
# J. 리포트 출력 (§22)
# --------------------------------------------------------------------------
def rendered(items, conflicts=(), team="T", display="팀"):
    from toto.models import Match, Odds, TeamRef
    from toto.render import _evidence_block
    m = Match(no=1, league="epl", league_ko="프리미어리그", kickoff_kst="x",
              home=TeamRef(canonical=team, display=display),
              away=TeamRef(canonical="X", display="상대"), odds=Odds())
    m.analysis = MatchAnalysis(home=TeamAnalysis(team=team, is_home=True))
    m.analysis.evidence = list(items)
    m.analysis.conflicts = list(conflicts)
    return _evidence_block(m)


def test_j41_no_evidence_no_block():
    assert rendered([]) == "", "근거가 없는데 빈 블록을 냈다"


def test_j42_block_shows_the_claim_and_its_metrics():
    cq, su = dup_pair()
    items = evidence.build_evidence(team_with(chance_quality=cq,
                                              sustainability=su), S)
    html = rendered(items)
    assert "근거 (관찰된 사실)" in html
    assert "goals_minus_xg" in html and "xg" in html
    assert "n=6" in html, "표본 수가 화면에 없다"


def test_j43_supporting_axis_is_named_in_korean():
    cq, su = dup_pair()
    items = evidence.build_evidence(team_with(chance_quality=cq,
                                              sustainability=su), S)
    html = rendered(items)
    assert "기회의 질" in html, "지지 축이 영어 키로 나가고 있다"
    assert "chance_quality" not in html


def test_j44_count_is_never_drawn_as_strength():
    """개수를 막대·게이지·점수로 그리지 않는다 (§20)."""
    cq, su = dup_pair()
    items = evidence.build_evidence(team_with(chance_quality=cq,
                                              sustainability=su), S)
    html = rendered(items)
    assert "<svg" not in html, "근거를 그림으로 세고 있다"
    for word in ("점수", "신뢰도", "강도 %", "width:"):
        assert word not in html, word
    assert "근거의 개수는 근거의 세기가 아닙니다" in html


def test_j45_block_has_no_external_reference():
    cq, su = dup_pair()
    items = evidence.build_evidence(team_with(chance_quality=cq,
                                              sustainability=su), S)
    html = rendered(items)
    for token in ("http://", "https://", "<script", "<iframe", "fetch("):
        assert token not in html, token


def test_j46_conflict_is_shown_without_a_lean():
    cq = axis("chance_quality", [
        shot("xg", 1.70, "recent6", 6),
        metric("goals_minus_xg", -0.40, "recent6", 6)])
    su = axis("sustainability", [
        metric("goals_minus_xg", 0.55, "recent3", 3, common=3)])
    ta = team_with(chance_quality=cq, sustainability=su)
    items = evidence.build_evidence(ta, S)
    sigs = evidence.find_conflicts(items)
    assert sigs, "방향 불일치가 만들어지지 않았다"
    html = rendered(items, sigs)
    assert "방향이 엇갈리는 관찰" in html
    assert "둘 다 그대로 둡니다" in html
    for word in ("UNKNOWN", "lean", "우세", "유력"):
        assert word not in html, word


def test_j47_report_says_it_does_not_recommend():
    cq, su = dup_pair()
    items = evidence.build_evidence(team_with(chance_quality=cq,
                                              sustainability=su), S)
    assert "승무패를 추천하지 않습니다" in rendered(items)


def test_patterns_are_not_reparsed_from_strings():
    """notes 문자열을 되읽지 않는다 (§13).

    문자열 검색은 쓰지 않는다 — 주석과 로그 문구에 '패턴' 이라는 낱말이
    나오는 것만으로 걸리기 때문이다(실제로 걸렸다). 구조로 본다:

      · 정규식을 들이지 않았는가
      · 축의 `notes` 를 읽지 않는가 (`patterns_in` 포함)
      · detector 를 직접 부르는가
    """
    tree = ast.parse(inspect.getsource(evidence))
    imports = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
               for a in n.names]
    assert "re" not in imports, "정규식으로 패턴 문자열을 파싱하고 있다"

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr != "notes", "축 notes 를 읽고 있다"
            assert node.attr != "patterns_in", "notes 에서 패턴 줄을 뽑고 있다"
        if isinstance(node, ast.Name):
            assert node.id != "patterns_in", "notes 에서 패턴 줄을 뽑고 있다"

    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    for detector in ("detect_patterns", "detect_defensive_patterns",
                     "detect_sustainability_patterns", "detect_venue_patterns"):
        assert detector in called, f"{detector} 를 직접 부르지 않는다"


def test_pipeline_attaches_without_recomputing_sources():
    from toto import fixtures
    from toto.analyze import run_all
    s = Settings(fotmob={"shot_recent_windows": [6, 3],
                         "match_detail_matches": 6})
    matches = fixtures.build_demo_matches()
    run_all(matches, s, season_matches=[])
    for m in matches:
        assert m.analysis is not None
        assert isinstance(m.analysis.evidence, list)
        assert isinstance(m.analysis.conflicts, list)


def test_attach_does_not_call_sources():
    """근거 생성이 소스를 다시 부르지 않는다 (§30)."""
    tree = ast.parse(inspect.getsource(evidence))
    imports = [n.module for n in ast.walk(tree)
               if isinstance(n, ast.ImportFrom) and n.module]
    imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                for a in n.names]
    for banned in ("sources", "fotmob", "pinnacle", "betman", "whoscored",
                   "requests", "cache"):
        assert not any(banned in (i or "") for i in imports), banned


# --------------------------------------------------------------------------
def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as exc:
            bad += 1
            print(f"  FAIL {name}: {exc}")
        except Exception as exc:                       # noqa: BLE001
            bad += 1
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - bad}/{len(tests)} 통과")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
