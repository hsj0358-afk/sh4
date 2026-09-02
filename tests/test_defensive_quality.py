"""수비의 질 회귀 테스트 (Phase 2-C).

고정하려는 것은 다섯 가지다.

1. **피지표는 상대 팀의 같은 경기 집계에서 온다.** 상대가 친 슛이 우리
   피슛이고, 상대의 npxG 가 우리 npxGA 다. 연결은 `opponent_id`(숫자
   teamId)로만 한다 — 팀명으로 찾지 않는다.
2. **상대가 0슛이어도 그 경기가 표본에 남는다.** 빠지면 가장 잘 막은
   경기가 사라져 피슛 평균이 위로 치우친다.
3. **실점은 슛맵이 아니라 최종 스코어**에서 온다 (자책골 때문).
4. **표본 셋을 구분한다.** requested / available / metric sample_count.
5. **트렌드는 2-B 교정의 `trend_allowed()` 를 그대로 쓴다.** 2-C 가 자체
   비교 로직을 만들지 않는다.

pytest 없이도 돈다:  python tests/test_defensive_quality.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import analysis, shots                               # noqa: E402
from toto.models import DERIVED, OBSERVED, SeasonMatch         # noqa: E402
from toto.models import TeamProfile, TeamRef, TeamStats        # noqa: E402
from toto.settings import Settings                             # noqa: E402
from toto.shots import MatchShotAggregate, RecentShotAggregate  # noqa: E402

UTC = timezone.utc
TEAM = "Alpha FC"
US, THEM = 111, 222
WINDOWS = [10, 6, 5, 3]
CFG = {"min_sample": 3,
       "thresholds": dict(analysis.DEFAULT_DEFENSIVE_QUALITY["thresholds"])}
MIN = analysis.DEFAULT_TREND_MIN_SAMPLE


def kick(day: int, hour: int = 20) -> datetime:
    return datetime(2026, 4, day, hour, 0, tzinfo=UTC)


def opp(mid: str, *, shots=12, sot=5, inside=7, outside=5,
        xg=1.4, npxg=1.2, xgot=1.0, team_id=THEM,
        is_home=False) -> MatchShotAggregate:
    """상대 팀이 그 경기에서 한 것 = 우리가 허용한 것."""
    return MatchShotAggregate(
        match_id=mid, team_id=team_id, is_home=is_home, opponent_id=US,
        shots=shots, shots_on_target=sot, shots_inside_box=inside,
        shots_outside_box=outside, xg=xg, npxg=npxg, xgot=xgot)


def mine(mid: str, *, is_home=True) -> MatchShotAggregate:
    return MatchShotAggregate(
        match_id=mid, team_id=US, is_home=is_home, opponent_id=THEM,
        shots=10, shots_on_target=4, shots_inside_box=6,
        shots_outside_box=4, xg=1.0, npxg=1.0, xgot=0.9)


def season(mids, goals_for=1, goals_against=2, start_day=1
           ) -> list[SeasonMatch]:
    return [SeasonMatch(
        match_id=mid, competition="epl", kickoff=kick(start_day + i),
        kickoff_aware=True, home_team=TEAM, away_team=f"Opp{i}",
        home_goals=goals_for, away_goals=goals_against, finished=True)
        for i, mid in enumerate(mids)]


def window(mids, requested=6) -> RecentShotAggregate:
    return RecentShotAggregate(
        team_id=US, window=requested, venue="all",
        requested_matches=requested, available_matches=len(mids),
        match_ids=list(mids), sums={}, counts={})


def stats(**over) -> TeamStats:
    base = dict(played=6, goals_for=6, goals_against=12, points=6,
                wins=2, draws=0, losses=4, shots_pg=12.0,
                shots_on_target_pg=4.8, xg_total=9.0, xga_total=12.0,
                xg_played=6)
    base.update(over)
    return TeamStats(**base)


def profile(opponents, mids=None, st=None) -> TeamProfile:
    p = TeamProfile(team=TeamRef(canonical=TEAM, fotmob_id=str(US)),
                    league="epl")
    p.stats = st if st is not None else stats()
    ids = list(mids if mids is not None else [o.match_id for o in opponents])
    p.opponent_matches = list(opponents)
    p.shot_matches = [mine(m) for m in ids]
    p.shot_aggregates = {f"all{w}": window(ids[:w], w) for w in WINDOWS}
    return p


def build(prof, sm, as_of=kick(30), windows=None, cfg=None, quality=None,
          min_sample=MIN):
    return analysis.build_defensive_quality(
        prof, TEAM, sm, as_of, windows or WINDOWS, cfg or CFG,
        thresholds=analysis.DEFAULT_TREND_THRESHOLDS, quality=quality,
        min_sample=min_sample)


# --------------------------------------------------------------------------
# 1~4. 상대 연결 (opponent linkage)
# --------------------------------------------------------------------------
def test_1_home_to_away_opponent():
    aggs = shots.aggregate_match([
        shots.ShotEvent(match_id="m0", team_id=US, expected_goals=0.3),
        shots.ShotEvent(match_id="m0", team_id=THEM, expected_goals=0.5),
    ], home_id=US, away_id=THEM)
    assert aggs[US].opponent_id == THEM
    assert aggs[US].is_home is True


def test_2_away_to_home_opponent():
    aggs = shots.aggregate_match([
        shots.ShotEvent(match_id="m0", team_id=US, expected_goals=0.3),
        shots.ShotEvent(match_id="m0", team_id=THEM, expected_goals=0.5),
    ], home_id=THEM, away_id=US)
    assert aggs[US].opponent_id == THEM
    assert aggs[US].is_home is False


def test_3_unknown_opponent_stays_none():
    aggs = shots.aggregate_match([
        shots.ShotEvent(match_id="m0", team_id=US, expected_goals=0.3)])
    assert aggs[US].opponent_id is None, "짐작해서 채우면 안 된다"


def test_4_opponent_with_zero_shots_is_still_linked():
    """상대가 한 슛도 안 쳤어도 home/away id 를 알면 이어진다."""
    aggs = shots.aggregate_match([
        shots.ShotEvent(match_id="m0", team_id=US, expected_goals=0.3)],
        home_id=US, away_id=THEM)
    assert aggs[US].opponent_id == THEM
    assert THEM not in aggs, "슛이 없으면 집계 자체가 안 만들어진다"

    empty = shots.empty_aggregate("m0", THEM, is_home=False, opponent_id=US)
    assert empty.shots == 0
    assert empty.xg == 0.0 and empty.npxg == 0.0 and empty.xgot == 0.0
    assert empty.opponent_id == US


def test_zero_shot_opponent_enters_the_defensive_sample():
    mids = ["m0", "m1", "m2"]
    opponents = [opp("m0", shots=12), opp("m1", shots=12),
                 shots.empty_aggregate("m2", THEM, is_home=False,
                                       opponent_id=US)]
    axis = build(profile(opponents, mids), season(mids))
    assert axis.value("recent3.shots_against") == 8.0, "(12+12+0)/3"
    assert axis.get("recent3.shots_against").sample_count == 3
    assert abs(axis.value("recent3.npxga") - 0.8) < 1e-9, "(1.2+1.2+0.0)/3"


# --------------------------------------------------------------------------
# 5~10. 수비 집계
# --------------------------------------------------------------------------
def test_5_shots_against():
    mids = ["m0", "m1"]
    axis = build(profile([opp("m0", shots=10), opp("m1", shots=20)], mids),
                 season(mids))
    assert axis.value("recent6.shots_against") == 15.0


def test_6_shots_on_target_against():
    mids = ["m0", "m1"]
    axis = build(profile([opp("m0", sot=3), opp("m1", sot=7)], mids),
                 season(mids))
    assert axis.value("recent6.shots_on_target_against") == 5.0


def test_7_box_shots_against():
    mids = ["m0"]
    axis = build(profile([opp("m0", inside=9, outside=4)], mids),
                 season(mids))
    assert axis.value("recent6.shots_inside_box_against") == 9.0
    assert axis.value("recent6.shots_outside_box_against") == 4.0


def test_8_npxga_is_the_opponents_npxg():
    mids = ["m0", "m1"]
    axis = build(profile([opp("m0", npxg=0.8), opp("m1", npxg=2.0)], mids),
                 season(mids))
    assert abs(axis.value("recent6.npxga") - 1.4) < 1e-9


def test_9_xgot_against_is_the_opponents_xgot():
    mids = ["m0", "m1"]
    axis = build(profile([opp("m0", xgot=0.5), opp("m1", xgot=1.5)], mids),
                 season(mids))
    assert axis.value("recent6.xgot_against") == 1.0


def test_10_goals_against_from_the_final_score():
    mids = ["m0", "m1"]
    axis = build(profile([opp("m0"), opp("m1")], mids),
                 season(mids, goals_against=3))
    assert axis.value("recent6.goals_against") == 3.0
    assert axis.get("recent6.goals_against").provenance == OBSERVED
    assert axis.get("recent6.goals_against").source == \
        analysis.SEASON_MATCH_INDEX


def test_npxga_per_shot_against():
    """분자·분모가 둘 다 있는 경기만. 합계끼리 나눈다."""
    mids = ["m0", "m1"]
    opponents = [opp("m0", shots=10, npxg=1.0),
                 opp("m1", shots=30, npxg=2.0)]
    axis = build(profile(opponents, mids), season(mids))
    got = axis.value("recent6.npxga_per_shot_against")
    assert abs(got - 0.075) < 1e-9, "3.0/40 (경기별 비율의 평균이 아니다)"
    assert abs(got - (0.1 + 2 / 30) / 2) > 0.005


def test_defensive_gaps():
    mids = ["m0"]
    axis = build(profile([opp("m0", npxg=1.2, xgot=1.0)], mids),
                 season(mids, goals_against=3))
    assert abs(axis.value("recent6.goals_against_minus_npxga") - 1.8) < 1e-9
    assert abs(
        axis.value("recent6.goals_against_minus_xgot_against") - 2.0) < 1e-9


def test_gap_metrics_have_no_direction():
    """실점이 기대보다 적다고 골키퍼가 잘한 것이 아니다 (§9)."""
    mids = ["m0"]
    axis = build(profile([opp("m0")], mids), season(mids))
    for name in ("goals_against_minus_npxga",
                 "goals_against_minus_xgot_against"):
        assert axis.get(f"recent6.{name}").direction == "", name


def test_no_goalkeeper_or_defense_score():
    """이런 이름의 지표를 만들지 않는다. (주석에서 '만들지 않는다'고
    적는 것은 괜찮다 — 코드에 없어야 한다는 뜻이다.)"""
    import inspect
    banned = ("goalkeeper_score", "goalkeeper_skill", "defense_score",
              "finishing_conceded", "save_quality", "recommendation_score")
    lines = [ln for ln in inspect.getsource(analysis).splitlines()
             if not ln.lstrip().startswith("#")]
    for word in banned:
        for line in lines:
            assert word not in line, line.strip()
    for name in analysis.SPECS:
        assert not any(w in name for w in banned), name
    mids = ["m0"]
    axis = build(profile([opp("m0")], mids), season(mids))
    for key in axis.metrics:
        assert not any(w in key for w in banned)


# --------------------------------------------------------------------------
# 11~14. 표본
# --------------------------------------------------------------------------
def test_11_requested_vs_available():
    mids = ["m0", "m1", "m2", "m3"]                  # 요청 6, 확보 4
    quality = analysis.DataQuality()
    axis = build(profile([opp(m) for m in mids], mids), season(mids),
                 quality=quality)
    entry = quality.axes["defensive_quality.recent6"]
    assert entry["requested"] == 6
    assert entry["available_matches"] == 4
    assert any("4/6경기" in n for n in axis.notes), axis.notes


def test_12_metric_specific_sample_count():
    """npxGA 가 2경기에만 있으면 2로 나눈다. 피슛은 4로 나눈다."""
    mids = ["m0", "m1", "m2", "m3"]
    opponents = [opp("m0", shots=10, npxg=1.0), opp("m1", shots=10, npxg=1.0),
                 opp("m2", shots=10, npxg=None), opp("m3", shots=10,
                                                     npxg=None)]
    axis = build(profile(opponents, mids), season(mids))
    assert axis.value("recent6.npxga") == 1.0
    assert axis.get("recent6.npxga").sample_count == 2
    assert axis.value("recent6.shots_against") == 10.0
    assert axis.get("recent6.shots_against").sample_count == 4
    ratio = axis.get("recent6.npxga_per_shot_against")
    assert abs(ratio.value - 0.1) < 1e-9, "2.0/20 (40 이 아니라)"
    assert ratio.sample_count == 2


def test_13_missing_opponent_metric_is_absent_not_zero():
    mids = ["m0"]
    axis = build(profile([opp("m0", npxg=None, xgot=None)], mids),
                 season(mids))
    assert axis.get("recent6.npxga") is None
    assert axis.get("recent6.xgot_against") is None
    assert axis.get("recent6.goals_against_minus_npxga") is None
    assert axis.value("recent6.shots_against") == 12.0, "피슛은 남는다"


def test_14_zero_is_not_none():
    mids = ["m0"]
    axis = build(profile([opp("m0", shots=0, sot=0, inside=0, outside=0,
                              xg=0.0, npxg=0.0, xgot=0.0)], mids),
                 season(mids, goals_against=0))
    assert axis.value("recent6.shots_against") == 0.0
    assert axis.get("recent6.shots_against").known is True
    assert axis.value("recent6.npxga") == 0.0
    assert axis.value("recent6.goals_against") == 0.0
    assert axis.get("recent6.npxga_per_shot_against") is None, \
        "0 으로 나눌 수 없다"


def test_missing_opponent_rows_are_reported():
    mids = ["m0", "m1", "m2"]
    axis = build(profile([opp("m0")], mids), season(mids))   # 2건이 없다
    assert axis.get("recent3.shots_against").sample_count == 1
    assert any("잇지 못한" in n for n in axis.notes), axis.notes


def test_no_opponent_data_at_all():
    mids = ["m0", "m1"]
    prof = profile([], mids)
    axis = build(prof, season(mids))
    assert not any(k.startswith("recent") for k in axis.metrics)
    assert any("상대 팀의 경기별 집계가 없습니다" in n for n in axis.notes)


def test_duplicate_match_id_is_counted_once():
    mids = ["m0", "m0", "m1"]           # 창에 같은 경기가 두 번
    prof = profile([opp("m0", shots=10), opp("m1", shots=20)], mids)
    axis = build(prof, season(["m0", "m1"]))
    # opponent_rows 는 창의 match_ids 를 그대로 따라가므로 중복이 두 번 온다.
    # 창을 만드는 aggregate_recent 가 이미 중복을 제거한다는 것을 확인한다.
    ordered = [opp("m0"), opp("m0"), opp("m1")]
    agg = shots.aggregate_recent(ordered, THEM, 6)
    assert agg.available_matches == 2, "같은 경기를 두 번 세면 안 된다"
    assert agg.match_ids == ["m0", "m1"]
    del axis


# --------------------------------------------------------------------------
# 15~19. 기간
# --------------------------------------------------------------------------
def test_15_to_18_all_recent_windows():
    mids = [f"m{i}" for i in range(10)]
    axis = build(profile([opp(m) for m in mids], mids), season(mids))
    for w in (3, 5, 6, 10):
        assert axis.value(f"recent{w}.shots_against") == 12.0, w
        assert axis.get(f"recent{w}.npxga") is not None, w


def test_19_season_period():
    axis = build(profile([], mids=[]), season([]))
    assert axis.value("season.goals_against") == 2.0, "12/6"
    assert axis.value("season.xga") == 2.0, "12.0/6"
    assert axis.get("season.npxga") is None, "시즌에는 npxGA 가 없다"
    assert axis.get("season.xgot_against") is None
    assert any("npxGA·피xGOT" in n for n in axis.notes), axis.notes


def test_recent10_is_capped_by_available_details():
    """요청 10, 경기 상세는 6경기뿐 — 없는 4경기를 0으로 채우지 않는다."""
    mids = [f"m{i}" for i in range(6)]
    quality = analysis.DataQuality()
    axis = build(profile([opp(m) for m in mids], mids), season(mids),
                 quality=quality)
    entry = quality.axes["defensive_quality.recent10"]
    assert entry["requested"] == 10
    assert entry["available_matches"] == 6
    assert axis.value("recent10.shots_against") == 12.0, "6경기 평균"


def test_periods_are_not_merged():
    mids = ["m0", "m1", "m2", "m3", "m4", "m5"]
    opponents = [opp(m, shots=20) for m in mids[:3]] + \
                [opp(m, shots=10) for m in mids[3:]]
    axis = build(profile(opponents, mids), season(mids))
    assert axis.value("recent3.shots_against") == 20.0
    assert axis.value("recent6.shots_against") == 15.0
    for key, metric in axis.metrics.items():
        assert key.startswith(metric.period + "."), key


# --------------------------------------------------------------------------
# 20~24. 트렌드 — 2-B 교정 게이트를 그대로 쓴다
# --------------------------------------------------------------------------
def test_defensive_quality_has_no_own_trend_logic():
    """자체 비교 로직을 만들지 않는다 (§2)."""
    import inspect
    src = inspect.getsource(analysis.build_defensive_quality)
    assert "trend_allowed" in src
    assert "sources_comparable" not in src, "게이트를 다시 구현했다"
    assert ".kickoff" not in src, "cutoff 를 다시 구현했다"
    assert "matches_before" in src


def test_20_comparable_source_allows_trend():
    """실점은 시즌(순위표)·최근(경기 색인) 모두 최종 스코어다."""
    mids = [f"m{i}" for i in range(10)]
    st = stats(played=10, goals_against=10)                 # 시즌 1.00
    axis = build(profile([opp(m) for m in mids], mids, st=st),
                 season(mids, goals_against=3))             # 최근 3.00
    trend = axis.get("trend6.goals_against")
    assert trend is not None and abs(trend.value - 2.0) < 1e-9
    assert analysis.parse_trend_band(trend) == analysis.HIGHER


def test_21_different_source_blocks_trend():
    """시즌 피슛은 통계 피드, 최근 피슛은 상대 슛맵 — 빼지 않는다."""
    mids = [f"m{i}" for i in range(10)]
    st = stats(played=10, shots_against_pg=11.0)
    axis = build(profile([opp(m) for m in mids], mids, st=st), season(mids))
    assert axis.value("season.shots_against") == 11.0
    assert axis.value("recent6.shots_against") == 12.0
    trend = axis.get("trend6.shots_against")
    assert trend is not None and trend.value is None
    assert analysis.parse_trend_band(trend) == analysis.NOT_MEANINGFUL
    assert analysis.SEASON_STATS_FEED in trend.note
    assert analysis.SHOTMAP in trend.note


def test_22_different_basis_blocks_trend():
    ok, code, reason = analysis.trend_allowed(
        "npxga",
        analysis.Metric(name="npxga", period="season", value=1.2,
                        sample_count=10, source=analysis.SHOTMAP,
                        measurement_basis=analysis.MATCH_STAT),
        analysis.Metric(name="npxga", period="recent6", value=1.4,
                        sample_count=6, source=analysis.SHOTMAP,
                        measurement_basis=analysis.OPPONENT_SHOT_EVENTS),
        same_match_set=False, min_sample=MIN)
    assert ok is False and code == analysis.BLOCK_BASIS, reason


def test_23_same_match_set_blocks_trend():
    mids = ["m0", "m1", "m2"]
    st = stats(played=3, goals_against=6)
    axis = build(profile([opp(m) for m in mids], mids, st=st),
                 season(mids, goals_against=2))
    trend = axis.get("trend6.goals_against")
    assert trend is not None and trend.value is None
    assert "동일 경기" in trend.note


def test_24_insufficient_sample_blocks_trend():
    mids = [f"m{i}" for i in range(10)]
    st = stats(played=10, goals_against=10)
    axis = build(profile([opp(m) for m in mids], mids, st=st), season(mids),
                 min_sample=8)
    assert axis.get("trend6.goals_against").value is None
    assert "표본 부족" in axis.get("trend6.goals_against").note


def test_npxga_never_gets_a_trend_because_season_has_none():
    mids = [f"m{i}" for i in range(10)]
    axis = build(profile([opp(m) for m in mids], mids,
                         st=stats(played=10)), season(mids))
    assert axis.value("recent6.npxga") is not None
    assert "trend6.npxga" not in axis.metrics, "시즌 값이 없는데 트렌드를 만들었다"


# --------------------------------------------------------------------------
# Source / basis / group / provenance
# --------------------------------------------------------------------------
def test_source_and_basis_are_recorded():
    mids = ["m0"]
    axis = build(profile([opp("m0")], mids), season(mids))
    for name in ("shots_against", "shots_on_target_against",
                 "shots_inside_box_against", "npxga", "xgot_against"):
        m = axis.get(f"recent6.{name}")
        assert m.source == analysis.SHOTMAP, name
        assert m.measurement_basis == analysis.OPPONENT_SHOT_EVENTS, name
    assert axis.get("season.goals_against").source == analysis.STANDINGS
    assert axis.get("season.xga").source == analysis.SEASON_XG_TABLE


def test_opponent_basis_differs_from_teamstats_path():
    """2-A 의 같은 이름 지표와 원천이 다르다는 것이 기록돼 있어야 한다."""
    assert analysis.metric_origin("recent6", "npxga") == (
        analysis.MATCH_STATS, analysis.MATCH_STAT), "2-A 경로"
    assert analysis.DEFENSIVE_SHOTMAP_ORIGIN["npxga"] == (
        analysis.SHOTMAP, analysis.OPPONENT_SHOT_EVENTS), "2-C 경로"
    assert analysis.OPPONENT_SHOT_EVENTS != analysis.SHOT_EVENTS


def test_provenance_split():
    mids = ["m0"]
    axis = build(profile([opp("m0")], mids), season(mids))
    assert axis.get("recent6.goals_against").provenance == OBSERVED
    for name in ("shots_against", "npxga", "xgot_against",
                 "npxga_per_shot_against", "goals_against_minus_npxga"):
        assert axis.get(f"recent6.{name}").provenance == DERIVED, name
    assert axis.get("season.goals_against").provenance == OBSERVED


def test_group_metadata_separates_attack_and_defense():
    mids = ["m0"]
    axis = build(profile([opp("m0")], mids), season(mids))
    expect = {
        "shots_against": analysis.DEF_VOLUME,
        "shots_on_target_against": analysis.DEF_VOLUME,
        "shots_inside_box_against": analysis.DEF_VOLUME,
        "npxga": analysis.DEF_QUALITY,
        "npxga_per_shot_against": analysis.DEF_QUALITY,
        "xgot_against": analysis.DEF_EXECUTION,
        "goals_against_minus_npxga": analysis.DEF_GAP,
        "goals_against": analysis.DEF_OUTCOME,
    }
    for name, group in expect.items():
        assert axis.get(f"recent6.{name}").group == group, name
    assert analysis.GROUPS["shots"] == analysis.VOLUME
    assert analysis.GROUPS["shots_against"] != analysis.VOLUME


# --------------------------------------------------------------------------
# 패턴
# --------------------------------------------------------------------------
def test_pattern_a_many_shots_low_quality():
    values = {"shots_against": (18.0, 6, ""),
              "npxga_per_shot_against": (0.06, 6, "")}
    got = analysis.detect_defensive_patterns(values, CFG)
    assert [c for c, _l, _b in got] == ["A"]


def test_pattern_b_few_shots_high_quality():
    values = {"shots_against": (7.0, 6, ""),
              "npxga_per_shot_against": (0.15, 6, "")}
    assert [c for c, _l, _b in
            analysis.detect_defensive_patterns(values, CFG)] == ["B"]


def test_pattern_c_conceding_more_than_expected():
    values = {"npxga": (0.7, 6, ""),
              "goals_against_minus_npxga": (0.9, 6, "")}
    assert [c for c, _l, _b in
            analysis.detect_defensive_patterns(values, CFG)] == ["C"]


def test_pattern_d_high_quality_chances_allowed():
    values = {"npxga": (1.9, 6, ""), "xgot_against": (1.7, 6, "")}
    assert [c for c, _l, _b in
            analysis.detect_defensive_patterns(values, CFG)] == ["D"]


def test_small_sample_produces_no_pattern():
    values = {"shots_against": (18.0, 2, ""),
              "npxga_per_shot_against": (0.06, 2, "")}
    assert analysis.detect_defensive_patterns(values, CFG) == []


def test_pattern_thresholds_come_from_config():
    s = Settings(analysis={"defensive_quality": {
        "min_sample": 1, "thresholds": {"shots_against_high": 5.0}}})
    cfg = analysis.defensive_quality_config(s)
    assert cfg["min_sample"] == 1
    assert cfg["thresholds"]["shots_against_high"] == 5.0
    assert cfg["thresholds"]["npxga_high"] == \
        analysis.DEFAULT_DEFENSIVE_QUALITY["thresholds"]["npxga_high"]


def test_patterns_are_not_scores_and_never_recommend():
    mids = [f"m{i}" for i in range(6)]
    opponents = [opp(m, shots=20, npxg=1.0) for m in mids]
    axis = build(profile(opponents, mids), season(mids))
    for line in analysis.patterns_in(axis):
        for word in ("추천", "픽", "베팅", "점수", "홈승", "원정승",
                     "골키퍼", "좋은 수비"):
            assert word not in line, f"{word} in {line}"


# --------------------------------------------------------------------------
# 시점 · Home/Away · 통합
# --------------------------------------------------------------------------
def test_future_match_in_window_drops_the_period():
    mids = ["m0", "m1"]
    sm = season(["m0"]) + [SeasonMatch(
        match_id="m1", competition="epl", kickoff=kick(20), kickoff_aware=True,
        home_team=TEAM, away_team="Z", home_goals=0, away_goals=5,
        finished=True)]
    axis = build(profile([opp(m) for m in mids], mids), sm, as_of=kick(5))
    assert not any(k.startswith("recent3.") for k in axis.metrics)
    assert any("기준시각 이후" in n for n in axis.notes), axis.notes


def test_home_away_flag_is_preserved_for_2e():
    """2-E 가 쓸 수 있도록 경기별 홈/원정을 보존한다 (여기서 뒤집지 않는다)."""
    mids = ["m0", "m1"]
    opponents = [opp("m0", is_home=False), opp("m1", is_home=True)]
    prof = profile(opponents, mids)
    assert [o.is_home for o in prof.opponent_matches] == [False, True]
    axis = build(prof, season(mids))
    assert axis.value("recent6.shots_against") == 12.0
    import inspect
    src = inspect.getsource(analysis.build_defensive_quality)
    assert "is_home" not in src, "2-C 가 홈/원정을 해석하고 있다 (2-E 소관)"


def test_team_analysis_integration():
    s = Settings(fotmob={"shot_recent_windows": [6, 3],
                         "match_detail_matches": 6})
    mids = ["m0", "m1", "m2"]
    ta = analysis.build_team_analysis(
        profile([opp(m) for m in mids], mids), TEAM, season(mids),
        kick(30), s, is_home=True)
    assert ta.defensive_quality is not None
    assert ta.computed_axes() == ["time_context", "chance_quality",
                                  "defensive_quality", "sustainability"]
    assert ta.venue_context is None, "2-E 를 미리 만들었다"
    assert "defensive_quality.recent6" in ta.data_quality.axes


def test_serialization_round_trip():
    from dataclasses import asdict
    from toto.models import MatchAnalysis, revive_match_analysis
    s = Settings(fotmob={"shot_recent_windows": [6, 3],
                         "match_detail_matches": 6})
    mids = ["m0", "m1", "m2"]
    ta = analysis.build_team_analysis(
        profile([opp(m) for m in mids], mids), TEAM, season(mids), kick(30), s)
    back = revive_match_analysis(asdict(MatchAnalysis(home=ta)))
    axis = back.home.defensive_quality
    assert axis is not None
    m = axis.get("recent6.npxga")
    assert m.measurement_basis == analysis.OPPONENT_SHOT_EVENTS
    assert m.group == analysis.DEF_QUALITY


def test_does_not_touch_probs_or_odds():
    from toto import fixtures
    from toto.analyze import run_all
    s = Settings(fotmob={"shot_recent_windows": [6, 3],
                         "match_detail_matches": 6})
    matches = fixtures.build_demo_matches()
    run_all(matches, s, season_matches=[])
    before = [(m.odds.home, m.odds.draw, m.odds.away) for m in matches]
    probs = [m.probs.as_tuple if m.probs else None for m in matches]
    analysis.attach_time_context(matches, s, [])
    assert [(m.odds.home, m.odds.draw, m.odds.away)
            for m in matches] == before
    assert [m.probs.as_tuple if m.probs else None
            for m in matches] == probs


# --------------------------------------------------------------------------
# 실물 260048 — 세 경기 교차검증
# --------------------------------------------------------------------------
UP = Path("/root/.claude/uploads/4f45b11b-6ed2-571d-8e30-3901a62afd1b")
REAL = {"5795366": UP / "09d404b5-match_5795366.json",
        "5795364": UP / "a7b5163e-match_5795364.json",
        "5795372": UP / "da0dcdd0-match_5795372.json"}


def _real_pairs():
    """[(match_id, home_agg, away_agg)] — 실물 캐시에서. 없으면 빈 목록."""
    out = []
    for mid, path in REAL.items():
        if not path.exists():
            return []
        payload = json.loads(path.read_text())
        events = [shots.ShotEvent(**d) for d in payload["shots"]]
        hid = payload["team_ids"]["home"]
        aid = payload["team_ids"]["away"]
        aggs = shots.aggregate_match(events, hid, aid)
        out.append((mid, aggs[hid], aggs[aid]))
    return out


def test_real_260048_home_defence_equals_away_attack():
    pairs = _real_pairs()
    if not pairs:
        print("     (실물 캐시 없음 — 건너뜀)")
        return
    assert len(pairs) == 3
    for mid, home, away in pairs:
        assert home.opponent_id == away.team_id, mid
        assert away.opponent_id == home.team_id, mid
        # 홈의 수비 = 원정의 공격
        prof = TeamProfile(team=TeamRef(canonical="H",
                                        fotmob_id=str(home.team_id)))
        prof.stats = TeamStats()
        prof.opponent_matches = [away]
        prof.shot_aggregates = {"all6": RecentShotAggregate(
            team_id=home.team_id, window=6, requested_matches=6,
            available_matches=1, match_ids=[mid])}
        axis = analysis.build_defensive_quality(
            prof, "H", [], None, [6], CFG)
        assert axis.value("recent6.shots_against") == float(away.shots), mid
        assert axis.value("recent6.shots_on_target_against") == \
            float(away.shots_on_target), mid
        assert abs(axis.value("recent6.npxga") - away.npxg) < 1e-12, mid
        assert abs(axis.value("recent6.xgot_against") - away.xgot) < 1e-12, mid


def test_real_260048_away_defence_equals_home_attack():
    pairs = _real_pairs()
    if not pairs:
        return
    for mid, home, away in pairs:
        prof = TeamProfile(team=TeamRef(canonical="A",
                                        fotmob_id=str(away.team_id)))
        prof.stats = TeamStats()
        prof.opponent_matches = [home]
        prof.shot_aggregates = {"all6": RecentShotAggregate(
            team_id=away.team_id, window=6, requested_matches=6,
            available_matches=1, match_ids=[mid])}
        axis = analysis.build_defensive_quality(
            prof, "A", [], None, [6], CFG)
        assert axis.value("recent6.shots_against") == float(home.shots), mid
        assert abs(axis.value("recent6.npxga") - home.npxg) < 1e-12, mid
        assert abs(axis.value("recent6.xgot_against") - home.xgot) < 1e-12, mid


def test_real_260048_matches_the_match_stat_table():
    """상대 슛맵 합산이 경기 스탯의 상대 값과 맞는지 대조."""
    if not all(p.exists() for p in REAL.values()):
        return
    worst = 0.0
    for mid, path in REAL.items():
        payload = json.loads(path.read_text())
        home_view = payload["home"]        # 홈 팀 관점의 경기 상세 집계
        events = [shots.ShotEvent(**d) for d in payload["shots"]]
        aggs = shots.aggregate_match(events, payload["team_ids"]["home"],
                                     payload["team_ids"]["away"])
        away = aggs[payload["team_ids"]["away"]]
        assert away.shots == home_view["shots_against"], mid
        assert away.shots_on_target == \
            home_view["shots_on_target_against"], mid
        worst = max(worst, abs(away.npxg - home_view["npxga"]))
        worst = max(worst, abs(away.xgot - home_view["xgot_against"]))
    assert worst < 0.1, f"슛맵과 경기 스탯 차이가 큽니다: {worst}"


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
