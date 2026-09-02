"""지속성 회귀 테스트 (Phase 2-D · 실제 ↔ 경기내용 ↔ 모델).

고정하려는 것은 다섯 가지다.

1. **같은 경기끼리만 뺀다.** 실제 6경기 · xG 4경기면 Gap 은 **공통 4경기**
   에서 계산하고, 실제 승점도 그 4경기로 다시 센다. 6으로 나누지 않는다.
2. **세 층을 섞지 않는다.** ACTUAL(최종 스코어) · UNDERLYING(슛 이벤트) ·
   MODEL(포아송)이 각각 다른 provenance 와 origin 을 갖는다.
3. **xPTS 를 다시 구현하지 않는다.** P1 의 `xpts.aggregate_team_xpts` 를
   부른다 (AST 로 고정).
4. **평균회귀를 예언하지 않는다.** 상태 라벨과 부호만 만든다. Gap 을
   Small/Moderate/Large 로 나누지 않는다.
5. **확률 격리.** predict / Match.probs 를 건드리지 않는다.

pytest 없이도 돈다:  python tests/test_sustainability.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import analysis, shots, xpts                          # noqa: E402
from toto.models import (DERIVED, MODEL, OBSERVED, MatchAnalysis,  # noqa: E402
                         Metric, SeasonMatch, TeamProfile, TeamRef,
                         TeamStats, revive_match_analysis)
from toto.settings import Settings                              # noqa: E402
from toto.shots import MatchShotAggregate, RecentShotAggregate   # noqa: E402

UTC = timezone.utc
TEAM = "우리팀"
US, THEM = 111, 222
WINDOWS = [10, 6, 5, 3]
MIN = analysis.DEFAULT_TREND_MIN_SAMPLE
SETTINGS = Settings(fotmob={"shot_recent_windows": WINDOWS,
                            "match_detail_matches": 6})


def kick(day: int) -> datetime:
    return datetime(2026, 4, day, 20, 0, tzinfo=UTC)


def own(mid, xg=1.0, npxg=0.9, xgot=0.8) -> MatchShotAggregate:
    return MatchShotAggregate(match_id=mid, team_id=US, opponent_id=THEM,
                              shots=10, xg=xg, npxg=npxg, xgot=xgot)


def opp(mid, xg=0.7) -> MatchShotAggregate:
    return MatchShotAggregate(match_id=mid, team_id=THEM, opponent_id=US,
                              shots=9, xg=xg)


def season(mids, gf=2, ga=1, start=1) -> list[SeasonMatch]:
    return [SeasonMatch(match_id=m, competition="epl", kickoff=kick(start + i),
                        kickoff_aware=True, home_team=TEAM, away_team=f"O{i}",
                        home_goals=gf, away_goals=ga, finished=True)
            for i, m in enumerate(mids)]


def profile(mids, *, own_rows=None, opp_rows=None, st=None) -> TeamProfile:
    p = TeamProfile(team=TeamRef(canonical=TEAM, fotmob_id=str(US)),
                    league="epl")
    p.stats = st if st is not None else TeamStats(
        played=len(mids), goals_for=2 * len(mids), goals_against=len(mids),
        points=3 * len(mids), wins=len(mids), xg_total=1.0 * len(mids),
        xga_total=0.7 * len(mids), xg_played=len(mids))
    p.shot_matches = list(own_rows if own_rows is not None
                          else [own(m) for m in mids])
    p.opponent_matches = list(opp_rows if opp_rows is not None
                              else [opp(m) for m in mids])
    p.shot_aggregates = {
        f"all{w}": RecentShotAggregate(
            team_id=US, window=w, requested_matches=w,
            available_matches=min(w, len(mids)), match_ids=mids[:w])
        for w in WINDOWS}
    return p


def build(mids, sm=None, *, own_rows=None, opp_rows=None, st=None,
          as_of=kick(30), quality=None, min_sample=MIN):
    return analysis.build_sustainability(
        profile(mids, own_rows=own_rows, opp_rows=opp_rows, st=st),
        TEAM, sm if sm is not None else season(mids), as_of, WINDOWS,
        quality=quality, min_sample=min_sample)


def metric(name, value, sample, source, basis) -> Metric:
    return Metric(name=name, label=name, value=value, period="recent6",
                  sample_count=sample, source=source,
                  measurement_basis=basis)


# --------------------------------------------------------------------------
# 22. 동일 경기 집합 — 이 축의 핵심
# --------------------------------------------------------------------------
def test_22_gap_uses_only_common_matches():
    """Actual = M1~M4, xG = M1~M3 이면 Gap 은 M1~M3 만 쓴다."""
    mids = ["m0", "m1", "m2", "m3"]
    rows = [own(m, xg=1.0) if i < 3 else own(m, xg=None, npxg=None, xgot=None)
            for i, m in enumerate(mids)]
    # M4 만 대량 득점 — 섞였다면 평균이 올라간다
    sm = season(mids[:3]) + [SeasonMatch(
        match_id="m3", competition="epl", kickoff=kick(4), kickoff_aware=True,
        home_team=TEAM, away_team="O3", home_goals=9, away_goals=0,
        finished=True)]
    axis = build(mids, sm, own_rows=rows)
    assert axis.value("recent6.goals") == 3.75, "실제 평균은 4경기 (2,2,2,9)"
    gap = axis.get("recent6.goals_minus_xg")
    assert gap.sample_count == 3, "공통 3경기여야 한다"
    assert abs(gap.value - 1.0) < 1e-9, \
        f"공통 3경기 기준 2.0-1.0=1.0 이어야 하는데 {gap.value}"
    assert "공통 3경기" in gap.note


def test_10_points_minus_xpts_uses_common_sample():
    """실제 6경기 · xG 4경기 → 공통 4경기. 6으로 나누지 않는다."""
    mids = [f"m{i}" for i in range(6)]
    rows = [own(m) if i < 4 else own(m, xg=None, npxg=None, xgot=None)
            for i, m in enumerate(mids)]
    opps = [opp(m) if i < 4 else opp(m, xg=None)
            for i, m in enumerate(mids)]
    axis = build(mids, own_rows=rows, opp_rows=opps)
    assert axis.get("recent6.points").sample_count == 6, "실제는 6경기"
    m = axis.get("recent6.points_minus_xpts")
    assert m.sample_count == 4, "공통 4경기여야 한다"
    assert axis.get("recent6.xpts").sample_count == 4
    # 손계산: 공통 4경기 실제 승점 3.0, xPTS 는 P1 이 계산
    xp = axis.value("recent6.xpts")
    assert abs(m.value - (3.0 - xp)) < 1e-9


def test_11_four_sample_counts_are_distinct():
    """requested / available / metric sample / common sample 이 다 다르다."""
    mids = [f"m{i}" for i in range(5)]           # 요청 6, 확보 5
    rows = [own(m) if i < 3 else own(m, xg=None, npxg=None, xgot=None)
            for i, m in enumerate(mids)]
    q = analysis.DataQuality()
    axis = build(mids, own_rows=rows, quality=q)
    entry = q.axes["sustainability.recent6"]
    assert entry["requested"] == 6
    assert entry["available_matches"] == 5
    assert axis.get("recent6.goals").sample_count == 5      # 지표 표본
    assert axis.get("recent6.xg").sample_count == 3
    assert axis.get("recent6.goals_minus_xg").sample_count == 3   # 공통
    # 공통 표본은 별도 칸으로도 실린다 — 차이 지표에만.
    assert axis.get("recent6.goals_minus_xg").common_sample_count == 3
    assert axis.get("recent6.goals").common_sample_count is None
    assert axis.get("recent6.xg").common_sample_count is None
    assert "공통 3경기" in axis.get("recent6.goals_minus_xg").note


def test_11_common_sample_survives_serialization():
    mids = [f"m{i}" for i in range(6)]
    rows = [own(m) if i < 4 else own(m, xg=None, npxg=None, xgot=None)
            for i, m in enumerate(mids)]
    opps = [opp(m) if i < 4 else opp(m, xg=None) for i, m in enumerate(mids)]
    ta = analysis.TeamAnalysis(team=TEAM)
    ta.sustainability = build(mids, own_rows=rows, opp_rows=opps)
    back = revive_match_analysis(asdict(MatchAnalysis(home=ta)))
    m = back.home.sustainability.get("recent6.points_minus_xpts")
    assert m.common_sample_count == 4, m.common_sample_count
    # 옛 저장본(이 칸이 없던 시절)도 되살아난다
    raw = asdict(MatchAnalysis(home=ta))
    for cell in raw["home"]["sustainability"]["metrics"].values():
        cell.pop("common_sample_count", None)
    old = revive_match_analysis(raw)
    assert old.home.sustainability.get(
        "recent6.points_minus_xpts").common_sample_count is None


# --------------------------------------------------------------------------
# 3~5. 세 층
# --------------------------------------------------------------------------
def test_3_actual_metrics():
    mids = ["m0", "m1", "m2"]
    axis = build(mids)
    assert axis.value("recent3.goals") == 2.0
    assert axis.value("recent3.points") == 3.0
    assert axis.get("recent3.goals").provenance == OBSERVED
    assert axis.get("recent3.goals").source == analysis.SEASON_MATCH_INDEX


def test_4_underlying_metrics():
    mids = ["m0", "m1", "m2"]
    axis = build(mids)
    for name in ("xg", "npxg", "xgot"):
        m = axis.get(f"recent3.{name}")
        assert m is not None and m.provenance == OBSERVED, name
        assert m.source == analysis.SHOTMAP, name
        assert m.measurement_basis == analysis.SHOT_EVENTS, name


def test_5_model_metric_is_marked_model():
    mids = ["m0", "m1", "m2"]
    axis = build(mids)
    m = axis.get("recent3.xpts")
    assert m is not None and m.provenance == MODEL
    assert m.source == analysis.XPTS_MODEL
    assert m.measurement_basis == analysis.POISSON_MODEL
    assert m.group == analysis.MODEL_GROUP


def test_15_xpts_is_not_reimplemented():
    """P1 을 부른다 — 포아송을 여기서 다시 만들지 않는다."""
    import inspect
    src = inspect.getsource(analysis.build_sustainability)
    assert "aggregate_team_xpts" in src
    for word in ("exp(", "factorial", "poisson_pmf", "math."):
        assert word not in src, word


def test_xpts_matches_p1_directly():
    """축의 xPTS 가 P1 을 직접 부른 값과 같아야 한다 (다른 경로, 같은 답)."""
    mids = ["m0", "m1", "m2"]
    axis = build(mids)
    sm = season(mids)
    xg_map = {m: (1.0, 0.7) for m in mids}      # 우리가 홈
    ref = xpts.aggregate_team_xpts(sm, xg_map, TEAM)
    assert abs(axis.value("recent3.xpts") - ref.xpts_per_match) < 1e-12


# --------------------------------------------------------------------------
# 6~9. Gap
# --------------------------------------------------------------------------
def test_6_to_9_all_four_gaps():
    mids = ["m0", "m1", "m2"]
    axis = build(mids)
    assert abs(axis.value("recent3.goals_minus_xg") - 1.0) < 1e-9
    assert abs(axis.value("recent3.goals_minus_npxg") - 1.1) < 1e-9
    assert abs(axis.value("recent3.goals_minus_xgot") - 1.2) < 1e-9
    assert axis.get("recent3.points_minus_xpts") is not None
    for name in ("goals_minus_xg", "goals_minus_npxg", "goals_minus_xgot",
                 "points_minus_xpts"):
        assert axis.get(f"recent3.{name}").provenance == DERIVED, name


def test_8_season_goals_never_meet_recent_npxg():
    """시즌 전체 득점과 최근 npxG 를 섞지 않는다 — 구조적으로 불가능하다."""
    mids = [f"m{i}" for i in range(3)]
    st = TeamStats(played=11, goals_for=22, goals_against=11, points=33,
                   xg_total=11.0, xga_total=8.0, xg_played=11)
    axis = build(mids, st=st)
    assert axis.get("season.npxg") is None, "시즌 npxG 는 없다"
    assert axis.get("season.goals_minus_npxg") is None
    # 최근 gap 은 최근 득점(2.0)에서 계산되지 시즌 득점(2.0)이 아니다 —
    # 키가 기간을 들고 있어 섞일 수 없다.
    for key, m in axis.metrics.items():
        assert key.startswith(m.period + "."), key


def test_9_xgot_gap_uses_only_matches_with_xgot():
    mids = [f"m{i}" for i in range(6)]
    rows = [own(m, xgot=0.8) if i < 3 else own(m, xgot=None)
            for i, m in enumerate(mids)]
    axis = build(mids, own_rows=rows)
    m = axis.get("recent6.goals_minus_xgot")
    assert m.sample_count == 3, "xGOT 이 있는 3경기만"
    assert abs(m.value - 1.2) < 1e-9
    assert axis.get("recent6.goals_minus_xg").sample_count == 6, \
        "xG 는 6경기 전부 있으므로 별개 표본"


# --------------------------------------------------------------------------
# 12·23. comparison_allowed
# --------------------------------------------------------------------------
def test_12_comparison_allowed_accepts_registered_pair():
    a = metric("goals", 2.0, 4, analysis.SEASON_MATCH_INDEX,
               analysis.FINAL_SCORE)
    e = metric("xg", 1.0, 4, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    ok, code, reason = analysis.comparison_allowed(
        a, e, common_sample=4, min_sample=3)
    assert ok is True, f"{code} {reason}"


def test_12_blocks_unregistered_basis_pair():
    a = metric("goals", 2.0, 4, analysis.SEASON_MATCH_INDEX,
               analysis.FINAL_SCORE)
    e = metric("xg", 1.0, 4, analysis.SEASON_STATS_FEED,
               analysis.OPPONENT_SHOT_EVENTS)
    # (final_score, opponent_shot_events) 는 등록돼 있다 → 다른 조합으로
    e2 = metric("xg", 1.0, 4, analysis.SHOTMAP, "무언가_새로운_방식")
    ok, code, _r = analysis.comparison_allowed(
        a, e2, common_sample=4, min_sample=3)
    assert ok is False and code == analysis.BLOCK_BASIS
    del e


def test_12_blocks_unknown_source_or_basis():
    a = metric("goals", 2.0, 4, "", "")
    e = metric("xg", 1.0, 4, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    ok, code, _r = analysis.comparison_allowed(
        a, e, common_sample=4, min_sample=3)
    assert ok is False and code == analysis.BLOCK_SOURCE


def test_12_blocks_different_match_set():
    a = metric("points", 3.0, 6, analysis.SEASON_MATCH_INDEX,
               analysis.FINAL_SCORE)
    e = metric("xpts", 1.5, 4, analysis.XPTS_MODEL, analysis.POISSON_MODEL)
    ok, code, reason = analysis.comparison_allowed(
        a, e, common_sample=4, min_sample=3, same_match_set=False)
    assert ok is False and code == analysis.BLOCK_MATCH_SET, reason


def test_12_blocks_no_common_and_small_sample():
    a = metric("goals", 2.0, 0, analysis.SEASON_MATCH_INDEX,
               analysis.FINAL_SCORE)
    e = metric("xg", 1.0, 0, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    ok, code, _r = analysis.comparison_allowed(
        a, e, common_sample=0, min_sample=3)
    assert ok is False and code == analysis.BLOCK_NO_COMMON

    ok2, code2, _r2 = analysis.comparison_allowed(
        a, e, common_sample=2, min_sample=3)
    assert ok2 is False and code2 == analysis.BLOCK_SAMPLE


def test_12_missing_side_blocks():
    e = metric("xg", 1.0, 4, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    assert analysis.comparison_allowed(None, e, common_sample=4,
                                       min_sample=3)[1] == \
        analysis.BLOCK_MISSING
    assert analysis.comparison_allowed(e, None, common_sample=4,
                                       min_sample=3)[1] == \
        analysis.BLOCK_MISSING


def test_23_season_vs_recent_xg_basis_differs():
    """시즌 xG(match_stat)와 최근 xG(shot_events)는 다른 방식이다."""
    assert analysis.metric_origin("season", "xg")[1] == analysis.MATCH_STAT
    assert analysis._SUSTAIN_ORIGIN["xg"][1] == analysis.SHOT_EVENTS
    # 트렌드 게이트는 이 둘을 막는다 (2-B 교정)
    a = metric("xg", 1.33, 10, analysis.SEASON_XG_TABLE, analysis.MATCH_STAT)
    b = metric("xg", 1.39, 6, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    assert analysis.trend_allowed("xg", a, b, same_match_set=False,
                                  min_sample=3)[0] is False


def test_23_final_score_sources_stay_comparable():
    assert analysis.sources_comparable(analysis.STANDINGS,
                                       analysis.SEASON_MATCH_INDEX)


def test_comparison_gate_is_not_the_trend_gate():
    """Gap 과 Trend 는 경기 집합 요구가 **반대**다."""
    import inspect
    src = inspect.getsource(analysis.build_sustainability)
    assert "comparison_allowed" in src
    assert "trend_allowed" not in src, "Gap 에 트렌드 게이트를 썼다"
    # 트렌드는 같은 경기 집합이면 차단, Gap 은 다른 경기 집합이면 차단
    a = metric("goals", 2.0, 4, analysis.SEASON_MATCH_INDEX,
               analysis.FINAL_SCORE)
    e = metric("xg", 1.0, 4, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    assert analysis.comparison_allowed(a, e, common_sample=4,
                                       min_sample=3)[0] is True


# --------------------------------------------------------------------------
# 17. 시즌 xPTS 제한
# --------------------------------------------------------------------------
def test_17_no_season_xpts():
    mids = ["m0", "m1", "m2"]
    st = TeamStats(played=11, goals_for=22, goals_against=11, points=33,
                   xg_total=11.0, xga_total=8.0, xg_played=11)
    axis = build(mids, st=st)
    assert axis.get("season.xpts") is None, "시즌 xPTS 를 만들었다"
    assert axis.get("season.points_minus_xpts") is None
    assert any("시즌 xPTS" in n for n in axis.notes), axis.notes


def test_17_season_gap_needs_matching_played_counts():
    mids = ["m0", "m1", "m2"]
    st = TeamStats(played=11, goals_for=22, points=33, goals_against=11,
                   xg_total=6.0, xga_total=4.0, xg_played=6)
    axis = build(mids, st=st)
    assert axis.get("season.goals_minus_xg") is None, \
        "경기 수가 다른데 시즌 gap 을 만들었다"
    assert axis.value("season.goals") == 2.0, "원값은 그대로"
    assert abs(axis.value("season.xg") - 1.0) < 1e-9


def test_17_season_gap_passes_the_same_gate():
    """시즌 차이도 최근과 **같은 문**(comparison_allowed)을 지난다."""
    mids = ["m0", "m1", "m2"]
    st = TeamStats(played=6, goals_for=12, points=18, goals_against=6,
                   xg_total=6.0, xga_total=4.0, xg_played=6)
    m = build(mids, st=st).get("season.goals_minus_xg")
    assert abs(m.value - 1.0) < 1e-9 and m.provenance == DERIVED
    assert m.common_sample_count == 6, "공통 표본은 6경기"
    assert "공통 6경기" in m.note
    # 표본이 게이트에 못 미치면 시즌 차이도 만들지 않는다
    st2 = TeamStats(played=2, goals_for=4, points=6, goals_against=2,
                    xg_total=2.0, xga_total=1.0, xg_played=2)
    axis = build(mids, st=st2, min_sample=3)
    assert axis.get("season.goals_minus_xg") is None
    assert axis.value("season.goals") == 2.0, "원값은 그대로 남는다"
    assert any("공통 표본 부족" in n for n in axis.notes), axis.notes


# --------------------------------------------------------------------------
# 25. Edge cases
# --------------------------------------------------------------------------
def test_25_actual_missing():
    mids = ["m0", "m1", "m2"]
    axis = build(mids, sm=[])            # 시즌 색인이 비었다
    assert axis.get("recent3.goals") is None
    assert axis.get("recent3.goals_minus_xg") is None
    assert axis.value("recent3.xg") == 1.0, "경기내용은 남는다"


def test_25_underlying_none_each():
    mids = ["m0", "m1", "m2"]
    for field, gap in (("xg", "goals_minus_xg"),
                       ("npxg", "goals_minus_npxg"),
                       ("xgot", "goals_minus_xgot")):
        rows = [own(m, **{field: None}) for m in mids]
        axis = build(mids, own_rows=rows)
        assert axis.get(f"recent3.{field}") is None, field
        assert axis.get(f"recent3.{gap}") is None, gap
        assert axis.value("recent3.goals") == 2.0, field


def test_25_xpts_none_when_opponent_xg_missing():
    mids = ["m0", "m1", "m2"]
    opps = [opp(m, xg=None) for m in mids]
    axis = build(mids, opp_rows=opps)
    assert axis.get("recent3.xpts") is None
    assert axis.get("recent3.points_minus_xpts") is None
    assert axis.value("recent3.xg") == 1.0, "우리 xG 는 남는다"


def test_25_one_team_xg_missing_drops_only_that_match():
    mids = ["m0", "m1", "m2", "m3"]
    opps = [opp(m) if i < 2 else opp(m, xg=None) for i, m in enumerate(mids)]
    axis = build(mids, opp_rows=opps)
    assert axis.get("recent6.xpts").sample_count == 2
    assert axis.get("recent6.goals_minus_xg").sample_count == 4, \
        "우리 xG 는 4경기 다 있으므로 이 gap 은 4경기"


def test_25_zero_xg_and_zero_points():
    mids = ["m0", "m1", "m2"]
    rows = [own(m, xg=0.0, npxg=0.0, xgot=0.0) for m in mids]
    sm = season(mids, gf=0, ga=1)          # 3전 3패, 무득점
    axis = build(mids, sm, own_rows=rows)
    assert axis.value("recent3.xg") == 0.0
    assert axis.get("recent3.xg").known is True
    assert axis.value("recent3.goals") == 0.0
    assert axis.value("recent3.points") == 0.0
    assert axis.value("recent3.goals_minus_xg") == 0.0, "0−0 은 0 이다"
    assert analysis.gap_state(0.0) == analysis.ALIGNED


def test_25_common_sample_zero():
    mids = ["m0", "m1", "m2"]
    rows = [own(m, xg=None, npxg=None, xgot=None) for m in mids]
    axis = build(mids, own_rows=rows)
    m = axis.get("recent3.goals_minus_xg")
    assert m is None, "공통 0경기인데 값을 만들었다"
    lines = [n for n in axis.notes if n.startswith("값 없음")]
    assert lines, "사유가 없다"


def test_25_insufficient_sample_blocks_gap():
    mids = ["m0", "m1"]                  # 2경기 < min_sample 3
    axis = build(mids, min_sample=3)
    m = axis.get("recent6.goals_minus_xg")
    assert m is None or m.value is None
    lines = " ".join(n for n in axis.notes if n.startswith("값 없음"))
    assert "표본 부족" in lines, lines


def test_25_none_is_not_zero():
    mids = ["m0", "m1", "m2"]
    rows = [own(m, xgot=None) for m in mids]
    axis = build(mids, own_rows=rows)
    assert axis.get("recent3.xgot") is None
    assert axis.value("recent3.xgot") != 0.0


def test_25_future_match_in_window_drops_the_period():
    """기준시각 이후 경기가 창에 섞이면 그 기간을 통째로 만들지 않는다."""
    mids = ["m0", "m1", "m2"]
    # m2 는 기준시각 뒤에 열린다
    sm = season(mids[:2]) + [SeasonMatch(
        match_id="m2", competition="epl", kickoff=kick(28), kickoff_aware=True,
        home_team=TEAM, away_team="O2", home_goals=5, away_goals=0,
        finished=True)]
    q = analysis.DataQuality()
    axis = build(mids, sm, as_of=kick(27), quality=q)
    assert axis.get("recent3.goals") is None
    assert axis.get("recent3.goals_minus_xg") is None
    assert (q.axes["sustainability.recent3"]["degraded_reason"]
            == "기준시각 이후 경기 혼입")
    assert any("기준시각 이후" in n for n in axis.notes)


def test_25_as_of_none_makes_no_recent_block():
    """기준이 없으면 과거 경기도 없다 — '전부' 로 두지 않는다."""
    mids = ["m0", "m1", "m2"]
    axis = build(mids, as_of=None)
    assert axis.get("recent3.goals") is None
    assert axis.get("recent3.points_minus_xpts") is None


def test_25_missing_window_and_missing_profile():
    prof = profile(["m0", "m1", "m2"])
    prof.shot_aggregates = {}                 # 슛 계층 창이 통째로 없다
    q = analysis.DataQuality()
    axis = analysis.build_sustainability(
        prof, TEAM, season(["m0", "m1", "m2"]), kick(30), WINDOWS,
        quality=q, min_sample=MIN)
    assert not [k for k in axis.metrics if k.startswith("recent")]
    assert q.axes["sustainability.recent6"]["degraded_reason"] == "슛 계층 창 없음"
    # 프로필 자체가 없어도 죽지 않는다
    empty = analysis.build_sustainability(None, TEAM, [], None, WINDOWS)
    assert empty.metrics == {} and empty.name == "sustainability"


def test_25_draw_is_one_point_not_missing():
    mids = ["m0", "m1", "m2"]
    sm = [SeasonMatch(match_id=m, competition="epl", kickoff=kick(1 + i),
                      kickoff_aware=True, home_team=TEAM, away_team=f"O{i}",
                      home_goals=1, away_goals=1, finished=True)
          for i, m in enumerate(mids)]
    axis = build(mids, sm)
    assert axis.value("recent3.points") == 1.0
    assert axis.value("recent3.goals") == 1.0
    assert axis.get("recent3.points_minus_xpts") is not None


def test_25_unfinished_match_in_window_drops_the_period():
    """끝나지 않은 경기는 과거가 아니다 — 그 창을 통째로 만들지 않는다.

    `matches_before()` 가 종료 경기만 돌려주므로 미종료 경기는 창에서
    '기준시각 이후' 와 같은 취급을 받는다. 결과의 절반만 든 창으로 실제와
    기대를 견주느니 만들지 않는 편이 낫다.
    """
    mids = ["m0", "m1", "m2"]
    sm = season(mids)
    sm[2].finished = False
    axis = build(mids, sm)
    assert axis.get("recent3.goals") is None
    assert axis.get("recent3.goals_minus_xg") is None
    assert any("기준시각 이후" in n for n in axis.notes)
    assert axis.value("season.goals") == 2.0, "시즌 원값은 그대로"


# --------------------------------------------------------------------------
# 13·14·21. 해석 금지 · 패턴
# --------------------------------------------------------------------------
def test_13_no_regression_language():
    mids = [f"m{i}" for i in range(6)]
    axis = build(mids)
    # 고정 문구는 "이 축은 그렇게 읽지 않는다" 를 밝히는 부정문이라 뺀다.
    body = [n for n in axis.notes if n not in analysis.SUSTAIN_DISCLAIMERS]
    assert len(body) < len(axis.notes), "고정 문구가 붙어 있어야 한다"
    text = " ".join(body) + " ".join(
        m.note + m.label for m in axis.metrics.values())
    for word in ("반등", "회귀", "하락 예상", "상승세", "곧 ", "다음 경기",
                 "추천", "픽", "베팅", "홈승", "무승부 선택", "원정승"):
        assert word not in text, f"{word} in output"


def test_14_no_gap_size_bands():
    """Small/Moderate/Large 등급을 만들지 않는다 — 검증된 기준이 없다."""
    import inspect
    src = inspect.getsource(analysis.build_sustainability) + \
        inspect.getsource(analysis.detect_sustainability_patterns)
    for word in ("small", "moderate", "large", "threshold"):
        assert word not in src.lower(), word
    assert "sustainability" not in (
        (Settings().analysis or {}).keys() if Settings().analysis else {})


def test_21_patterns_by_sign_only():
    values = {"goals_minus_xg": (-0.5, 6, ""),
              "points_minus_xpts": (0.8, 6, "")}
    got = analysis.detect_sustainability_patterns(values, 3)
    codes = [c for c, _l, _b in got]
    assert codes == ["A", "D"], codes
    flipped = {"goals_minus_xg": (0.5, 6, ""),
               "points_minus_xpts": (-0.8, 6, "")}
    assert [c for c, _l, _b in
            analysis.detect_sustainability_patterns(flipped, 3)] == ["B", "C"]


def test_21_small_sample_makes_no_pattern():
    values = {"goals_minus_xg": (-0.5, 2, ""),
              "points_minus_xpts": (0.8, 2, "")}
    assert analysis.detect_sustainability_patterns(values, 3) == []


def test_gap_state_labels():
    assert analysis.gap_state(None) == analysis.NOT_COMPARABLE
    assert analysis.gap_state(0.0) == analysis.ALIGNED
    assert analysis.gap_state(0.4) == analysis.ACTUAL_ABOVE
    assert analysis.gap_state(-0.4) == analysis.ACTUAL_BELOW


def test_28_no_recommendation_surface():
    import inspect
    banned = ("final_pick", "recommended_pick", "recommendation",
              "predicted_result", "best_bet", "regression_to_mean")
    src = inspect.getsource(analysis)
    for word in banned:
        assert word not in src, word
    mids = ["m0", "m1", "m2"]
    axis = build(mids)
    for key in axis.metrics:
        assert not any(w in key for w in banned)


# --------------------------------------------------------------------------
# 27. 확률 격리
# --------------------------------------------------------------------------
def test_27_probability_isolation():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(analysis))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "predict" not in (node.module or "")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "predict" not in alias.name
    assert "predict" not in vars(analysis)
    src = inspect.getsource(analysis.build_sustainability)
    for word in (".probs", "MatchProb", ".odds", "additive_probabilities"):
        assert word not in src, word


def test_27_run_all_leaves_probs_untouched():
    from toto import fixtures
    from toto.analyze import run_all
    matches = fixtures.build_demo_matches()
    run_all(matches, SETTINGS, season_matches=[])
    before = [(m.odds.home, m.odds.draw, m.odds.away) for m in matches]
    probs = [m.probs.as_tuple if m.probs else None for m in matches]
    analysis.attach_time_context(matches, SETTINGS, [])
    assert [(m.odds.home, m.odds.draw, m.odds.away)
            for m in matches] == before
    assert [m.probs.as_tuple if m.probs else None
            for m in matches] == probs


# --------------------------------------------------------------------------
# 19. TeamAnalysis 연결 · 직렬화
# --------------------------------------------------------------------------
def test_19_team_analysis_integration():
    mids = ["m0", "m1", "m2"]
    ta = analysis.build_team_analysis(
        profile(mids), TEAM, season(mids), kick(30), SETTINGS, is_home=True)
    assert ta.sustainability is not None
    assert ta.computed_axes() == ["time_context", "chance_quality",
                                  "defensive_quality", "sustainability"]
    assert ta.venue_context is None, "2-E 를 미리 만들었다"
    assert ta.schedule_strength is None
    assert "sustainability.recent6" in ta.data_quality.axes


def test_19_metric_metadata_is_complete():
    mids = ["m0", "m1", "m2"]
    axis = build(mids)
    for key, m in axis.metrics.items():
        if key.startswith("season."):
            continue
        assert m.provenance, key
        assert m.source, key
        assert m.measurement_basis, key
        assert m.sample_count is not None, key
        assert m.group, key


def test_serialization_round_trip():
    mids = ["m0", "m1", "m2"]
    ta = analysis.build_team_analysis(
        profile(mids), TEAM, season(mids), kick(30), SETTINGS)
    back = revive_match_analysis(asdict(MatchAnalysis(home=ta)))
    axis = back.home.sustainability
    assert axis is not None
    m = axis.get("recent3.xpts")
    assert m.provenance == MODEL
    assert m.measurement_basis == analysis.POISSON_MODEL


# --------------------------------------------------------------------------
# 24. 실물 260048
# --------------------------------------------------------------------------
UP = Path("/root/.claude/uploads/4f45b11b-6ed2-571d-8e30-3901a62afd1b")
REAL = UP / "da0dcdd0-match_5795372.json"


def _real_axis(team_name, tid, oid):
    if not REAL.exists():
        return None
    payload = json.loads(REAL.read_text())
    events = [shots.ShotEvent(**d) for d in payload["shots"]]
    aggs = shots.aggregate_match(events, payload["team_ids"]["home"],
                                 payload["team_ids"]["away"])
    kickoff = datetime(2026, 8, 23, 20, 0, tzinfo=analysis.KST)
    as_of = datetime(2026, 8, 29, 20, 0, tzinfo=analysis.KST)
    sm = [SeasonMatch(match_id="5795372", competition="epl", kickoff=kickoff,
                      kickoff_aware=True, home_team="Fulham",
                      away_team="Chelsea", home_fotmob_id=9879,
                      away_fotmob_id=8455, home_goals=2, away_goals=3,
                      finished=True)]
    p = TeamProfile(team=TeamRef(canonical=team_name, fotmob_id=str(tid)))
    p.stats = TeamStats(played=1, goals_for=3 if team_name == "Chelsea" else 2,
                        goals_against=2 if team_name == "Chelsea" else 3,
                        points=3 if team_name == "Chelsea" else 0,
                        xg_total=aggs[tid].npxg, xga_total=aggs[oid].npxg,
                        xg_played=1)
    p.shot_matches = [aggs[tid]]
    p.opponent_matches = [aggs[oid]]
    p.shot_aggregates = shots.aggregate_windows([aggs[tid]], tid, [6])
    return analysis.build_sustainability(p, team_name, sm, as_of, [6],
                                         min_sample=1), aggs[tid], aggs[oid]


def test_24_real_chelsea_actual_vs_underlying():
    got = _real_axis("Chelsea", 8455, 9879)
    if got is None:
        print("     (실물 캐시 없음 — 건너뜀)")
        return
    axis, mine, theirs = got
    assert axis.value("recent6.goals") == 3.0
    assert abs(axis.value("recent6.xg") - mine.xg) < 1e-12
    assert abs(axis.value("recent6.goals_minus_xg") - (3.0 - mine.xg)) < 1e-12
    assert axis.get("recent6.goals_minus_xg").sample_count == 1


def test_24_real_chelsea_actual_vs_xpts():
    got = _real_axis("Chelsea", 8455, 9879)
    if got is None:
        return
    axis, mine, theirs = got
    xp = axis.value("recent6.xpts")
    assert xp is not None
    ref = xpts.match_xpts(theirs.xg, mine.xg)     # 풀럼 홈 · 첼시 원정
    assert abs(xp - ref.away_xpts) < 1e-12, "P1 과 다른 값이 나왔다"
    assert abs(axis.value("recent6.points_minus_xpts") - (3.0 - xp)) < 1e-12


def test_24_real_fulham_side():
    got = _real_axis("Fulham", 9879, 8455)
    if got is None:
        return
    axis, mine, theirs = got
    assert axis.value("recent6.goals") == 2.0
    assert axis.value("recent6.points") == 0.0
    ref = xpts.match_xpts(mine.xg, theirs.xg)     # 풀럼이 홈
    assert abs(axis.value("recent6.xpts") - ref.home_xpts) < 1e-12
    assert axis.value("recent6.points_minus_xpts") < 0, \
        "0승점인데 기대승점보다 높게 나왔다"


# --------------------------------------------------------------------------
def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            print(f"  ERR  {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
