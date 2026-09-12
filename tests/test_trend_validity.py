"""트렌드 유효성 회귀 테스트 (Phase 2-B 교정).

## 왜 이 파일이 생겼나

실물 260048 에서 풀럼의 값이 이랬다.

    시즌 xG   1.33   ← 경기 스탯 값
    최근 xG   1.39   ← 슛맵 이벤트 합산
    트렌드    +0.06

**같은 한 경기**다. +0.06 은 경기력 변화가 아니라 두 측정 방식의 차이였다
(슛맵은 슛마다 xG 를 반올림해 주므로 합치면 누적된다). 이런 숫자를 추세로
적으면 안 된다.

그래서 빼기 전에 여섯 가지를 본다 (`analysis.trend_allowed`).

    1. 같은 지표
    2. 직접 비교 가능한 원천
    3. 같은 산출 방식
    4. 서로 다른 경기 집합
    5. 표본이 최소 기준 이상
    6. 표본 수가 유효

하나라도 어긋나면 **값을 None 으로 두고 사유를 남긴다.**

pytest 없이도 돈다:  python tests/test_trend_validity.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import analysis                                       # noqa: E402
from toto.models import DERIVED, Metric, SeasonMatch            # noqa: E402
from toto.models import TeamProfile, TeamRef, TeamStats         # noqa: E402
from toto.settings import Settings                              # noqa: E402
from toto.shots import RecentShotAggregate                      # noqa: E402

UTC = timezone.utc
TEAM = "Alpha FC"
TEAM_ID = 111
WINDOWS = [10, 6, 5, 3]
TH = dict(analysis.DEFAULT_TREND_THRESHOLDS)
MIN = analysis.DEFAULT_TREND_MIN_SAMPLE


def kick(day: int, hour: int = 20) -> datetime:
    return datetime(2026, 4, day, hour, 0, tzinfo=UTC)


def season_stats(**over) -> TeamStats:
    base = dict(played=10, wins=5, draws=2, losses=3,
                goals_for=15, goals_against=10, points=17,
                shots_pg=12.0, shots_on_target_pg=4.0, big_chances_pg=2.0,
                xg_total=14.0, xga_total=11.0, xg_played=10)
    base.update(over)
    return TeamStats(**base)


def history(n: int, *, goals=(2, 1), start_day: int = 1) -> list[SeasonMatch]:
    return [SeasonMatch(
        match_id=f"m{i}", competition="epl", kickoff=kick(start_day + i),
        kickoff_aware=True, home_team=TEAM, away_team=f"Opp{i}",
        home_goals=goals[0], away_goals=goals[1], finished=True)
        for i in range(n)]


def window(n: int, available: int, sums: dict, counts: dict
           ) -> RecentShotAggregate:
    return RecentShotAggregate(
        team_id=TEAM_ID, window=n, venue="all", requested_matches=n,
        available_matches=available,
        match_ids=[f"m{i}" for i in range(available)],
        sums=dict(sums), counts=dict(counts))


def profile(stats=None, aggregates=None) -> TeamProfile:
    p = TeamProfile(team=TeamRef(canonical=TEAM, fotmob_id=str(TEAM_ID)),
                    league="epl")
    p.stats = stats if stats is not None else season_stats()
    p.shot_aggregates = aggregates or {}
    return p


def build(prof, sm, as_of=kick(30), min_sample=MIN):
    return analysis.build_time_context(
        prof, TEAM, sm, as_of, WINDOWS, TH, detail_window=6,
        min_sample=min_sample)


def metric(name, period, value, sample, source, basis) -> Metric:
    return Metric(name=name, label=name, value=value, period=period,
                  sample_count=sample, source=source, measurement_basis=basis)


# --------------------------------------------------------------------------
# 1. 같은 원천 · 같은 방식 · 다른 경기 → 허용
# --------------------------------------------------------------------------
def test_1_same_source_same_basis_different_matches_allows_trend():
    axis = build(profile(season_stats(goals_for=15, played=10)), history(10))
    trend = axis.get("trend6.goals")
    assert trend is not None
    assert abs(trend.value - 0.5) < 1e-9, "1.50 → 2.00"
    assert analysis.parse_trend_band(trend) == analysis.HIGHER
    assert trend.provenance == DERIVED


def test_final_score_sources_are_declared_comparable():
    """순위표와 시즌 경기 색인은 둘 다 최종 스코어를 센다."""
    assert analysis.sources_comparable(analysis.STANDINGS,
                                       analysis.SEASON_MATCH_INDEX)
    assert analysis.sources_comparable(analysis.SHOTMAP, analysis.SHOTMAP)


def test_result_metrics_all_get_trends():
    axis = build(profile(season_stats(played=10)), history(10))
    for name in ("goals", "goals_against", "points", "goal_diff"):
        m = axis.get(f"trend6.{name}")
        assert m is not None and m.value is not None, name


def test_win_draw_loss_counts_get_no_trend():
    """시즌 5승(10경기)과 최근 3승(3경기)을 빼면 -2 가 나온다. 추세가 아니다."""
    axis = build(profile(season_stats(played=10)), history(10))
    for name in ("wins", "draws", "losses"):
        m = axis.get(f"trend6.{name}")
        assert m is not None and m.value is None, name
        assert "누적 개수" in m.note, m.note
    assert axis.value("season.wins") == 5.0, "원값은 그대로"
    assert axis.value("recent6.wins") == 6.0
    assert axis.value("trend6.points") is not None, "경기당 승점은 비교 가능"


# --------------------------------------------------------------------------
# 2. 다른 원천 → 차단
# --------------------------------------------------------------------------
def test_2_different_source_blocks_trend():
    a = metric("shots", "season", 12.0, 10, analysis.SEASON_STATS_FEED,
               analysis.MATCH_STAT)
    b = metric("shots", "recent6", 15.0, 6, analysis.SHOTMAP,
               analysis.MATCH_STAT)      # 방식은 같게 두고 원천만 다르게
    ok, _code, reason = analysis.trend_allowed(
        "shots", a, b, same_match_set=False, min_sample=MIN)
    assert ok is False
    assert "원천" in reason, reason


def test_unknown_source_is_not_comparable():
    assert analysis.sources_comparable("", analysis.SHOTMAP) is False
    assert analysis.sources_comparable(analysis.SHOTMAP, "") is False


# --------------------------------------------------------------------------
# 3. 다른 산출 방식 → 차단  (풀럼 xG 문제 그 자체)
# --------------------------------------------------------------------------
def test_3_different_basis_blocks_trend():
    a = metric("xg", "season", 1.33, 10, analysis.SEASON_XG_TABLE,
               analysis.MATCH_STAT)
    b = metric("xg", "recent6", 1.39, 6, analysis.SEASON_XG_TABLE,
               analysis.SHOT_EVENTS)     # 원천은 같게 두고 방식만 다르게
    ok, _code, reason = analysis.trend_allowed(
        "xg", a, b, same_match_set=False, min_sample=MIN)
    assert ok is False
    assert "산출 방식" in reason, reason


def test_xg_trend_is_blocked_in_the_axis():
    """표본·경기집합이 전부 넉넉해도 xG 트렌드는 만들어지지 않는다."""
    aggs = {"all6": window(6, 6, {"xg": 15.0}, {"xg": 6})}      # 2.50
    axis = build(profile(season_stats(played=10), aggs), history(10))
    assert axis.value("season.xg") is not None
    assert axis.value("recent6.xg") == 2.5
    trend = axis.get("trend6.xg")
    assert trend is not None, "사유를 남기려면 지표는 있어야 한다"
    assert trend.value is None, "측정 방식이 다른데 값을 만들었다"
    assert analysis.parse_trend_band(trend) == analysis.NOT_MEANINGFUL
    assert analysis.SEASON_XG_TABLE in trend.note, trend.note
    assert analysis.SHOTMAP in trend.note, trend.note
    assert any("trend 미생성" in n and "xG" in n for n in axis.notes), axis.notes
    assert sum("xG" in n and "trend 미생성" in n for n in axis.notes) == 1, \
        "창과 무관한 사유를 창마다 반복해 적었다"


def test_shot_volume_trend_is_blocked_too():
    """슈팅도 시즌은 통계 피드, 최근은 슛맵이라 빼지 않는다."""
    aggs = {"all6": window(6, 6, {"shots": 90.0, "shots_on_target": 30.0},
                           {"shots": 6, "shots_on_target": 6})}
    axis = build(profile(season_stats(played=10), aggs), history(10))
    for name in ("shots", "shots_on_target"):
        m = axis.get(f"trend6.{name}")
        assert m is not None and m.value is None, name


def test_origin_table_marks_the_real_split():
    assert analysis.metric_origin("season", "xg") == (
        analysis.SEASON_XG_TABLE, analysis.MATCH_STAT)
    assert analysis.metric_origin("recent6", "xg") == (
        analysis.SHOTMAP, analysis.SHOT_EVENTS)
    assert analysis.metric_origin("season", "goals") == (
        analysis.STANDINGS, analysis.FINAL_SCORE)
    assert analysis.metric_origin("recent6", "goals") == (
        analysis.SEASON_MATCH_INDEX, analysis.FINAL_SCORE)


def test_origin_lands_on_every_metric():
    aggs = {"all6": window(6, 6, {"xg": 9.0, "npxg": 9.0}, {"xg": 6,
                                                            "npxg": 6})}
    axis = build(profile(season_stats(played=10), aggs), history(10))
    for key, m in axis.metrics.items():
        if key.startswith("trend"):
            continue
        assert m.source, f"{key} 에 source 가 없다"
        assert m.measurement_basis, f"{key} 에 measurement_basis 가 없다"


# --------------------------------------------------------------------------
# 4. 같은 경기 집합 → 차단
# --------------------------------------------------------------------------
def test_4_same_match_set_blocks_trend():
    a = metric("goals", "season", 3.0, 1, analysis.STANDINGS,
               analysis.FINAL_SCORE)
    b = metric("goals", "recent6", 3.0, 1, analysis.SEASON_MATCH_INDEX,
               analysis.FINAL_SCORE)
    ok, _code, reason = analysis.trend_allowed(
        "goals", a, b, same_match_set=True, min_sample=1)
    assert ok is False
    assert "동일 경기" in reason, reason


def test_same_match_set_detected_in_the_axis():
    """시즌 6경기 · 최근 6경기면 같은 경기다 — 트렌드를 만들지 않는다."""
    axis = build(profile(season_stats(played=6, goals_for=12)), history(6))
    trend = axis.get("trend6.goals")
    assert trend is not None and trend.value is None
    assert "동일 경기" in trend.note
    # 더 짧은 창은 진짜 부분집합이라 허용된다.
    assert axis.get("trend3.goals").value is not None


def test_recent_window_larger_than_season_is_the_same_set():
    axis = build(profile(season_stats(played=6, goals_for=12)), history(6))
    assert axis.get("trend10.goals").value is None


# --------------------------------------------------------------------------
# 5. 표본 부족 → 차단
# --------------------------------------------------------------------------
def test_5_small_sample_blocks_trend():
    a = metric("goals", "season", 3.0, 10, analysis.STANDINGS,
               analysis.FINAL_SCORE)
    b = metric("goals", "recent3", 2.0, 2, analysis.SEASON_MATCH_INDEX,
               analysis.FINAL_SCORE)
    ok, _code, reason = analysis.trend_allowed(
        "goals", a, b, same_match_set=False, min_sample=3)
    assert ok is False and "표본 부족" in reason, reason


def test_small_sample_blocked_in_the_axis():
    axis = build(profile(season_stats(played=10)), history(10))
    assert axis.get("trend6.goals").value is not None, "6경기는 충분"
    assert axis.get("trend3.goals").value is not None, "3경기는 최소 기준"
    tight = build(profile(season_stats(played=10)), history(10), min_sample=5)
    assert tight.get("trend3.goals").value is None
    assert "표본 부족" in tight.get("trend3.goals").note


def test_6_invalid_sample_counts_block_trend():
    good = metric("goals", "season", 3.0, 10, analysis.STANDINGS,
                  analysis.FINAL_SCORE)
    for bad in (None, 0, -1):
        b = metric("goals", "recent6", 2.0, bad,
                   analysis.SEASON_MATCH_INDEX, analysis.FINAL_SCORE)
        ok, _code, reason = analysis.trend_allowed(
            "goals", good, b, same_match_set=False, min_sample=1)
        assert ok is False, bad
        assert "표본" in reason, reason


def test_min_sample_comes_from_config():
    s = Settings(analysis={"trend_min_sample": 7})
    assert analysis.trend_min_sample(s) == 7
    assert analysis.trend_min_sample(Settings()) == MIN
    assert analysis.trend_min_sample(
        Settings(analysis={"trend_min_sample": "x"})) == MIN
    assert analysis.trend_min_sample(
        Settings(analysis={"trend_min_sample": 0})) == 1


def test_mismatched_metric_names_block_trend():
    a = metric("goals", "season", 3.0, 10, analysis.STANDINGS,
               analysis.FINAL_SCORE)
    b = metric("xg", "recent6", 2.0, 6, analysis.STANDINGS,
               analysis.FINAL_SCORE)
    ok, _code, reason = analysis.trend_allowed(
        "goals", a, b, same_match_set=False, min_sample=1)
    assert ok is False and "지표" in reason


def test_missing_side_blocks_trend():
    a = metric("goals", "season", 3.0, 10, analysis.STANDINGS,
               analysis.FINAL_SCORE)
    assert analysis.trend_allowed("goals", a, None, same_match_set=False,
                                  min_sample=1)[0] is False
    assert analysis.trend_allowed("goals", None, a, same_match_set=False,
                                  min_sample=1)[0] is False


# --------------------------------------------------------------------------
# 6~7. 원래 값은 그대로다
# --------------------------------------------------------------------------
def test_6_raw_values_are_untouched():
    """교정은 trend 만 건드린다. observed·derived 원값은 그대로여야 한다."""
    aggs = {"all6": window(6, 6, {"xg": 15.0, "npxg": 12.0, "xgot": 9.0,
                                  "shots": 90.0, "shots_on_target": 30.0},
                           {"xg": 6, "npxg": 6, "xgot": 6, "shots": 6,
                            "shots_on_target": 6})}
    axis = build(profile(season_stats(played=10), aggs), history(10))
    assert axis.value("recent6.xg") == 2.5
    assert axis.value("recent6.npxg") == 2.0
    assert axis.value("recent6.xgot") == 1.5
    assert axis.value("recent6.shots") == 15.0
    assert abs(axis.value("season.xg") - 1.4) < 1e-9
    assert axis.value("season.shots") == 12.0
    assert axis.value("season.goals") == 1.5
    assert axis.value("recent6.goals") == 2.0
    assert axis.value("recent6.points") == 3.0


def test_7_chance_quality_is_unchanged():
    """2-B 계산은 트렌드를 만들지 않으므로 교정의 영향을 받지 않는다."""
    from toto.shots import MatchShotAggregate
    rows = [MatchShotAggregate(match_id=f"m{i}", team_id=TEAM_ID, shots=10,
                               shots_on_target=4, shots_inside_box=6,
                               shots_outside_box=4, xg=1.0, npxg=1.0,
                               xgot=0.8) for i in range(3)]
    prof = profile(season_stats(played=10))
    prof.shot_matches = rows
    prof.shot_aggregates = {f"all{w}": window(w, 3, {}, {}) for w in WINDOWS}
    axis = analysis.build_chance_quality(
        prof, TEAM, history(10), kick(30), WINDOWS,
        analysis.chance_quality_config(Settings()))
    assert axis.value("recent6.xg_per_shot") == 0.1
    assert axis.value("recent6.box_shot_share") == 60.0
    assert axis.value("recent6.on_target_rate") == 40.0
    assert abs(axis.value("recent6.goals_minus_xg") - 1.0) < 1e-9
    assert not any(k.startswith("trend") for k in axis.metrics), \
        "2-B 축은 트렌드를 만들지 않는다"


def test_chance_quality_metrics_carry_origin():
    from toto.shots import MatchShotAggregate
    rows = [MatchShotAggregate(match_id="m0", team_id=TEAM_ID, shots=10,
                               shots_on_target=4, shots_inside_box=6,
                               shots_outside_box=4, xg=1.0, npxg=1.0,
                               xgot=0.8)]
    prof = profile(season_stats(played=10))
    prof.shot_matches = rows
    prof.shot_aggregates = {f"all{w}": window(w, 1, {}, {}) for w in WINDOWS}
    axis = analysis.build_chance_quality(
        prof, TEAM, history(10), kick(30), WINDOWS,
        analysis.chance_quality_config(Settings()))
    m = axis.get("recent6.xg_per_shot")
    assert m.source == analysis.DERIVED_SOURCE
    assert m.measurement_basis == analysis.SHOT_EVENTS
    assert axis.get("recent6.xg").source == analysis.SHOTMAP


# --------------------------------------------------------------------------
# 실물 260048 — 풀럼
# --------------------------------------------------------------------------
UP = Path("/root/.claude/uploads/4f45b11b-6ed2-571d-8e30-3901a62afd1b")
REAL = UP / "da0dcdd0-match_5795372.json"


def _real_fulham_axis():
    """실물 캐시로 풀럼 프로필을 만든다. 캐시가 없으면 None."""
    if not REAL.exists():
        return None
    from toto import shots as shot_layer
    payload = json.loads(REAL.read_text())
    events = [shot_layer.ShotEvent(**d) for d in payload["shots"]]
    aggs = shot_layer.aggregate_match(events, payload["team_ids"]["home"],
                                      payload["team_ids"]["away"])
    fulham = aggs[9879]
    side = payload["home"]
    stats = TeamStats(
        played=1, wins=0, draws=0, losses=1, goals_for=2, goals_against=3,
        points=0, big_chances_pg=2.0, shots_on_target_pg=6.0,
        shots_pg=side["shots"], xg_total=side["npxg"], xga_total=2.24,
        xg_played=1)
    prof = TeamProfile(team=TeamRef(canonical="Fulham", fotmob_id="9879"),
                       league="epl")
    prof.stats = stats
    prof.shot_matches = [fulham]
    prof.shot_aggregates = shot_layer.aggregate_windows([fulham], 9879,
                                                        WINDOWS)
    kickoff = datetime(2026, 8, 23, 20, 0, tzinfo=analysis.KST)
    season = [SeasonMatch(match_id="5795372", competition="epl",
                          kickoff=kickoff, kickoff_aware=True,
                          home_team="Fulham", away_team="Chelsea",
                          home_fotmob_id=9879, away_fotmob_id=8455,
                          home_goals=2, away_goals=3, finished=True)]
    as_of = datetime(2026, 8, 29, 20, 0, tzinfo=analysis.KST)
    return analysis.build_time_context(
        prof, "Fulham", season, as_of, WINDOWS, TH, detail_window=6,
        min_sample=MIN)


def test_real_fulham_xg_trend_is_gone():
    axis = _real_fulham_axis()
    if axis is None:
        print("     (실물 캐시 없음 — 건너뜀)")
        return
    assert abs(axis.value("season.xg") - 1.33) < 0.01, "시즌 원값은 그대로"
    assert abs(axis.value("recent6.xg") - 1.385) < 0.01, "최근 원값도 그대로"
    trend = axis.get("trend6.xg")
    assert trend is not None and trend.value is None, \
        "+0.06 이 아직 추세로 남아 있다"
    assert analysis.parse_trend_band(trend) == analysis.NOT_MEANINGFUL


def test_real_fulham_goals_trend_is_gone_for_same_match_reason():
    axis = _real_fulham_axis()
    if axis is None:
        return
    trend = axis.get("trend6.goals")
    assert trend is not None and trend.value is None
    assert "동일 경기" in trend.note or "표본 부족" in trend.note, trend.note
    assert axis.value("recent6.goals") == 2.0, "원값은 그대로"


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
