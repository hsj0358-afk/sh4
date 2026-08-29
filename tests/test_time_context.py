"""시간축 분석 회귀 테스트 (Phase 2-A · Time Context).

여기서 고정하려는 것은 세 가지다.

1. **시즌과 최근이 섞이지 않는다.** 키가 `기간.지표` 라서 구조적으로 못 섞는다.
2. **표본 세 가지가 구분된다.** requested / available / metric sample_count.
   평균은 언제나 그 지표의 표본 수로 나눈다.
3. **미래가 새지 않는다.** cutoff 는 `models.matches_before` 하나뿐이고
   같은 시각 경기는 제외된다.

pytest 없이도 돈다:  python tests/test_time_context.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import analysis                                       # noqa: E402
from toto.models import (DERIVED, OBSERVED, Match, SeasonMatch,  # noqa: E402
                         TeamProfile, TeamRef, TeamStats)
from toto.settings import Settings                              # noqa: E402
from toto.shots import RecentShotAggregate                      # noqa: E402

UTC = timezone.utc
HOME_TEAM = "Alpha FC"
AWAY_TEAM = "Beta United"
WINDOWS = [10, 6, 5, 3]
TH = dict(analysis.DEFAULT_TREND_THRESHOLDS)


def kick(day: int, hour: int = 20) -> datetime:
    return datetime(2026, 4, day, hour, 0, tzinfo=UTC)


def season_stats(**over) -> TeamStats:
    """시즌 순위표 + 시즌 통계 피드 (10경기 표본)."""
    base = dict(played=10, wins=5, draws=2, losses=3,
                goals_for=15, goals_against=10, points=17,
                shots_pg=12.0, shots_on_target_pg=4.0, big_chances_pg=2.0,
                xg_total=14.0, xga_total=11.0, xg_played=10)
    base.update(over)
    return TeamStats(**base)


def history(team: str, n: int, *, start_day: int = 1,
            goals=(2, 1)) -> list[SeasonMatch]:
    """`team` 이 홈으로 치른 n 경기. 하루 간격, 전부 종료."""
    out = []
    for i in range(n):
        out.append(SeasonMatch(
            match_id=f"m{i}", competition="epl", kickoff=kick(start_day + i),
            kickoff_aware=True, home_team=team, away_team=f"Opp{i}",
            home_goals=goals[0], away_goals=goals[1], finished=True))
    return out


def window(team_id: int, n: int, available: int, sums: dict,
           counts: dict, match_ids=None) -> RecentShotAggregate:
    return RecentShotAggregate(
        team_id=team_id, window=n, venue="all", requested_matches=n,
        available_matches=available,
        match_ids=list(match_ids or [f"m{i}" for i in range(available)]),
        sums=dict(sums), counts=dict(counts))


def profile(stats: TeamStats | None = None, aggregates=None) -> TeamProfile:
    p = TeamProfile(team=TeamRef(canonical=HOME_TEAM, name_ko="알파",
                                 fotmob_id="111"), league="epl")
    p.stats = stats if stats is not None else season_stats()
    p.shot_aggregates = aggregates or {}
    return p


def build(prof, season, as_of, windows=None, quality=None, detail=6):
    return analysis.build_time_context(
        prof, HOME_TEAM, season, as_of, windows or WINDOWS, TH,
        detail_window=detail, quality=quality)


# --------------------------------------------------------------------------
# 1~5. 기간
# --------------------------------------------------------------------------
def test_1_season_period_present():
    axis = build(profile(), history(HOME_TEAM, 10), kick(30))
    assert axis.value("season.goals") == 1.5, "15득점 / 10경기"
    assert axis.value("season.points") == 1.7
    assert abs(axis.value("season.xg") - 1.4) < 1e-9
    assert axis.get("season.goals").period == analysis.SEASON


def test_2_recent10_period_present():
    aggs = {"all10": window(111, 10, 8, {"npxg": 12.0}, {"npxg": 8})}
    axis = build(profile(aggregates=aggs), history(HOME_TEAM, 10), kick(30))
    assert abs(axis.value("recent10.npxg") - 1.5) < 1e-9
    assert axis.get("recent10.npxg").period == "recent10"


def test_3_recent6_period_present():
    aggs = {"all6": window(111, 6, 6, {"xgot": 6.6}, {"xgot": 6})}
    axis = build(profile(aggregates=aggs), history(HOME_TEAM, 10), kick(30))
    assert abs(axis.value("recent6.xgot") - 1.1) < 1e-9


def test_4_recent5_period_present():
    axis = build(profile(), history(HOME_TEAM, 10), kick(30))
    assert axis.value("recent5.points") == 3.0, "5경기 전승 → 경기당 3점"
    assert axis.get("recent5.points").sample_count == 5


def test_5_recent3_period_present():
    axis = build(profile(), history(HOME_TEAM, 10), kick(30))
    assert axis.value("recent3.goals") == 2.0
    assert axis.get("recent3.goals").sample_count == 3


def test_periods_are_not_merged():
    """시즌 값과 최근 값이 한 칸에 섞이지 않는다 — 키가 기간을 들고 있다."""
    aggs = {"all6": window(111, 6, 6, {"xg": 12.0}, {"xg": 6})}
    axis = build(profile(aggregates=aggs), history(HOME_TEAM, 10), kick(30))
    assert abs(axis.value("season.xg") - 1.4) < 1e-9
    assert abs(axis.value("recent6.xg") - 2.0) < 1e-9
    for key, metric in axis.metrics.items():
        assert key.startswith(metric.period + "."), f"{key} 기간 불일치"


def test_window_count_is_not_hardcoded():
    axis = build(profile(), history(HOME_TEAM, 10), kick(30), windows=[7, 2])
    assert "recent7.points" in axis.metrics
    assert "recent2.points" in axis.metrics
    assert not any(k.startswith("recent6.") for k in axis.metrics)


def test_periods_from_settings_falls_back_to_shot_windows():
    s = Settings(fotmob={"shot_recent_windows": [4, 9]})
    assert analysis.periods_from(s) == [9, 4]
    s.analysis = {"periods": [3, 3, 5]}
    assert analysis.periods_from(s) == [5, 3], "중복 제거 + 내림차순"


def test_thresholds_come_from_config_not_code():
    s = Settings(analysis={"trend_thresholds": {"xg": 9.9, "bogus": -1}})
    th = analysis.thresholds_from(s)
    assert th["xg"] == 9.9, "설정이 기본값을 덮어써야 한다"
    assert "bogus" not in th, "음수 문턱은 받지 않는다"
    assert th["goals"] == analysis.DEFAULT_TREND_THRESHOLDS["goals"]


# --------------------------------------------------------------------------
# 6~9. 표본
# --------------------------------------------------------------------------
def test_6_requested_vs_available():
    """요청 6경기, 확보 4경기 — 둘을 같은 수로 뭉뚱그리지 않는다."""
    quality = analysis.DataQuality()
    axis = build(profile(), history(HOME_TEAM, 4), kick(30), quality=quality)
    entry = quality.axes["time_context.recent6"]
    assert entry["requested"] == 6
    assert entry["available_matches"] == 4
    assert any("4/6경기" in n for n in axis.notes), axis.notes


def test_7_metric_specific_sample_count():
    """npxG 가 4경기에만 있으면 **4로 나눈다**. 6으로 나누지 않는다."""
    aggs = {"all6": window(111, 6, 6,
                           {"npxg": 6.0, "shots": 66.0},
                           {"npxg": 4, "shots": 6})}
    axis = build(profile(aggregates=aggs), history(HOME_TEAM, 6), kick(30))
    assert axis.value("recent6.npxg") == 1.5, "6.0/4 이어야 한다"
    assert axis.get("recent6.npxg").sample_count == 4
    assert axis.value("recent6.shots") == 11.0
    assert axis.get("recent6.shots").sample_count == 6


def test_8_partial_missing_metric_is_absent_not_zero():
    """한 지표만 통째로 빠지면 그 칸이 없어야 한다 — 0 으로 채우지 않는다."""
    aggs = {"all6": window(111, 6, 6, {"shots": 60.0}, {"shots": 6})}
    axis = build(profile(aggregates=aggs), history(HOME_TEAM, 6), kick(30))
    assert "recent6.shots" in axis.metrics
    assert "recent6.npxg" not in axis.metrics, "없는 값을 0 으로 만들었다"
    assert axis.value("recent6.npxg") is None


def test_9_zero_is_a_real_value():
    """0 은 값이다. None 과 다르다."""
    aggs = {"all6": window(111, 6, 6, {"npxg": 0.0}, {"npxg": 6})}
    axis = build(profile(aggregates=aggs), history(HOME_TEAM, 6), kick(30))
    assert axis.value("recent6.npxg") == 0.0
    assert axis.get("recent6.npxg").known is True

    goalless = history(HOME_TEAM, 3, goals=(0, 0))
    axis2 = build(profile(), goalless, kick(30))
    assert axis2.value("recent3.goals") == 0.0
    assert axis2.value("recent3.points") == 1.0, "무승부 3경기 → 경기당 1점"
    assert axis2.value("recent3.wins") == 0.0
    assert axis2.get("recent3.wins").known is True


def test_early_season_single_match_is_not_an_error():
    stats = season_stats(played=1, wins=1, draws=0, losses=0,
                         goals_for=3, goals_against=2, points=3, xg_played=1,
                         xg_total=1.4, xga_total=1.1)
    aggs = {"all6": window(111, 6, 1, {"npxg": 1.33}, {"npxg": 1})}
    quality = analysis.DataQuality()
    axis = build(profile(stats, aggs), history(HOME_TEAM, 1), kick(30),
                 quality=quality)
    assert any("1/6경기" in n for n in axis.notes), axis.notes
    assert axis.value("recent6.npxg") == 1.33
    assert quality.axes["time_context.recent6"]["available"] is True


def test_coverage_is_not_turned_into_a_score():
    """커버리지가 confidence 로 둔갑하지 않는다."""
    quality = analysis.DataQuality()
    build(profile(), history(HOME_TEAM, 3), kick(30), quality=quality)
    for entry in quality.axes.values():
        assert set(entry) == {"available", "requested", "available_matches",
                              "degraded_reason"}
        for key, value in entry.items():
            assert "confidence" not in key and "score" not in key
            assert not isinstance(value, float), f"{key} 가 점수처럼 보인다"


def test_missing_shot_layer_leaves_a_reason():
    axis = build(profile(aggregates={}), history(HOME_TEAM, 6), kick(30))
    assert "recent6.npxg" not in axis.metrics
    assert any("슛 계층" in n for n in axis.notes), axis.notes


# --------------------------------------------------------------------------
# 10~12. 트렌드
# --------------------------------------------------------------------------
# 트렌드는 **원천과 산출 방식이 같은 지표에서만** 만들어진다. 득점은 시즌
# (순위표)과 최근(시즌 경기 색인) 모두 최종 스코어를 센 값이라 비교할 수
# 있다. xG 는 시즌이 경기 스탯, 최근이 슛맵 합산이라 비교할 수 없다 —
# 그쪽은 tests/test_trend_validity.py 가 다룬다.
def test_10_recent_higher_than_season():
    stats = season_stats(goals_for=15, played=10)          # 1.50
    axis = build(profile(stats), history(HOME_TEAM, 10), kick(30))
    trend = axis.get("trend6.goals")                       # 최근 2.00
    assert abs(trend.value - 0.5) < 1e-9
    assert analysis.parse_trend_band(trend) == analysis.HIGHER
    assert trend.provenance == DERIVED
    for word in ("상승세", "전력", "강팀", "추천"):
        assert word not in trend.note, f"{word} 라고 단정했다"


def test_11_recent_lower_than_season():
    stats = season_stats(goals_for=25, played=10)          # 2.50
    axis = build(profile(stats), history(HOME_TEAM, 10, goals=(1, 0)),
                 kick(30))
    trend = axis.get("trend6.goals")                       # 최근 1.00
    assert abs(trend.value + 1.5) < 1e-9
    assert analysis.parse_trend_band(trend) == analysis.LOWER


def test_12_recent_similar_to_season():
    stats = season_stats(goals_for=20, played=10)          # 2.00
    axis = build(profile(stats), history(HOME_TEAM, 10), kick(30))
    trend = axis.get("trend6.goals")                       # 최근 2.00
    assert trend.value == 0.0
    assert analysis.parse_trend_band(trend) == analysis.SIMILAR


def test_trend_band_uses_the_configured_threshold():
    assert analysis.trend_band("xg", 0.24, TH)[0] == analysis.SIMILAR
    assert analysis.trend_band("xg", 0.26, TH)[0] == analysis.HIGHER
    loose = dict(TH, xg=1.0)
    assert analysis.trend_band("xg", 0.26, loose)[0] == analysis.SIMILAR
    assert analysis.trend_band("unknown_metric", 0.5, TH)[0] == analysis.HIGHER


def test_trend_only_where_both_periods_exist():
    """시즌에 없는 지표는 트렌드도 없다 (npxG·xGOT 는 시즌 피드에 없다)."""
    aggs = {"all6": window(111, 6, 6, {"npxg": 9.0}, {"npxg": 6})}
    axis = build(profile(aggregates=aggs), history(HOME_TEAM, 6), kick(30))
    assert "recent6.npxg" in axis.metrics
    assert "trend6.npxg" not in axis.metrics
    assert "season.npxg" not in axis.metrics


def test_trend_is_not_reused_as_a_strength_score():
    """파생 차이값이 다시 합산되지 않는다 — 축에 총점 항목이 없어야 한다."""
    aggs = {"all6": window(111, 6, 6, {"xg": 15.0}, {"xg": 6})}
    axis = build(profile(aggregates=aggs), history(HOME_TEAM, 6), kick(30))
    for key in axis.metrics:
        tail = key.split(".", 1)[1]
        assert tail not in ("score", "total", "form_score", "strength")


# --------------------------------------------------------------------------
# 13~14. 방향
# --------------------------------------------------------------------------
def test_13_offensive_metrics_are_higher_better():
    for name in ("goals", "xg", "npxg", "xgot", "shots_on_target",
                 "shots_inside_box", "big_chances", "points", "xgd"):
        assert analysis.SPECS[name][2] == analysis.HIGHER_BETTER, name


def test_14_defensive_metrics_are_lower_better():
    for name in ("goals_against", "npxga", "xgot_against", "shots_against",
                 "shots_on_target_against"):
        assert analysis.SPECS[name][2] == analysis.LOWER_BETTER, name


def test_direction_lands_on_the_metric():
    aggs = {"all6": window(111, 6, 6, {"xg": 9.0}, {"xg": 6})}
    axis = build(profile(aggregates=aggs), history(HOME_TEAM, 6), kick(30))
    assert axis.get("recent6.xg").direction == analysis.HIGHER_BETTER
    assert axis.get("season.goals_against").direction == analysis.LOWER_BETTER
    assert axis.get("trend6.xg").direction == analysis.HIGHER_BETTER


def test_undirected_metrics_stay_blank():
    """슈팅 수·무승부는 많다고 좋은 게 아니다 — 방향을 정하지 않는다."""
    for name in ("shots", "draws"):
        assert analysis.SPECS[name][2] == "", name
    covered = (analysis.SPEC_DIRECTIONS | analysis.EXTRA_DIRECTIONS
               | analysis.UNDIRECTED)
    assert covered == set(analysis.SPECS), "분류되지 않은 지표가 있다"
    assert not (analysis.SPEC_DIRECTIONS & analysis.EXTRA_DIRECTIONS)


# --------------------------------------------------------------------------
# 15~17. 시점
# --------------------------------------------------------------------------
def test_15_as_of_cutoff_limits_the_history():
    season = history(HOME_TEAM, 10)              # 4/1 ~ 4/10
    early = build(profile(), season, kick(6))    # 4/1~4/5 만 (5경기)
    late = build(profile(), season, kick(30))
    assert early.available_matches == 5
    assert late.available_matches == 10
    assert early.get("recent10.points").sample_count == 5


def test_16_same_timestamp_is_excluded():
    """같은 시각에 시작하는 경기는 쓰지 않는다 (엄격한 `<`)."""
    season = history(HOME_TEAM, 3)               # 4/1, 4/2, 4/3 · 20:00
    axis = build(profile(), season, kick(3))     # 4/3 20:00 기준
    assert axis.available_matches == 2, "동시각 경기가 섞였다"
    later = build(profile(), season, kick(3, 21))
    assert later.available_matches == 3


def test_17_future_matches_never_enter():
    season = history(HOME_TEAM, 3)
    season.append(SeasonMatch(
        match_id="future", competition="epl", kickoff=kick(20),
        kickoff_aware=True, home_team=HOME_TEAM, away_team="Opp9",
        home_goals=9, away_goals=0, finished=True))
    axis = build(profile(), season, kick(5))
    assert axis.available_matches == 3
    assert axis.value("recent10.goals") == 2.0, "9득점 경기가 새어 들었다"


def test_future_match_in_shot_window_drops_shot_metrics():
    """슛 창은 다시 자를 수 없으니, 오염되면 값을 만들지 않는다."""
    season = history(HOME_TEAM, 3)
    season.append(SeasonMatch(
        match_id="m9", competition="epl", kickoff=kick(20), kickoff_aware=True,
        home_team=HOME_TEAM, away_team="Opp9", home_goals=1, away_goals=0,
        finished=True))
    aggs = {"all6": window(111, 6, 4, {"npxg": 8.0}, {"npxg": 4},
                           match_ids=["m0", "m1", "m2", "m9"])}
    axis = build(profile(aggregates=aggs), season, kick(5))
    assert "recent6.npxg" not in axis.metrics
    assert any("기준시각 이후" in n for n in axis.notes), axis.notes
    assert axis.value("recent6.goals") == 2.0, "결과 지표는 남아야 한다"


def test_unverifiable_window_is_flagged_not_silently_used():
    aggs = {"all6": window(111, 6, 2, {"npxg": 3.0}, {"npxg": 2},
                           match_ids=["unknown1", "unknown2"])}
    axis = build(profile(aggregates=aggs), history(HOME_TEAM, 3), kick(30))
    assert axis.value("recent6.npxg") == 1.5
    assert any("확인하지 못한" in n for n in axis.notes), axis.notes


def test_no_duplicate_cutoff_logic():
    """cutoff 는 matches_before 하나뿐 — 모듈이 kickoff 을 직접 비교하지 않는다."""
    import inspect
    src = inspect.getsource(analysis)
    body = src.split("def team_history", 1)[1]
    assert ".kickoff" not in body, "두 번째 cutoff 경로가 생겼다"


def test_as_of_from_match_uses_kst():
    m = Match(no=1, kickoff_kst="2026-08-29 20:00")
    got = analysis.as_of_from_match(m)
    assert got is not None and got.tzinfo is not None
    assert got.utcoffset() == timedelta(hours=9)
    assert got.astimezone(UTC).hour == 11, "20:00 KST = 11:00 UTC"
    assert analysis.as_of_from_match(Match(no=2, kickoff_kst="")) is None
    assert analysis.as_of_from_match(Match(no=3, kickoff_kst="언제?")) is None


def test_missing_as_of_leaves_history_empty_with_a_note():
    axis = build(profile(), history(HOME_TEAM, 6), None)
    assert axis.available_matches == 0
    assert "recent6.points" not in axis.metrics
    assert any("기준시각" in n for n in axis.notes), axis.notes


# --------------------------------------------------------------------------
# 수비 지표 · 경기 상세 창
# --------------------------------------------------------------------------
def test_defensive_recent_only_on_the_detail_window():
    stats = season_stats(recent_matches=6,
                         recent_counts={"npxga_recent": 5,
                                        "shots_against_recent": 6},
                         npxga_recent=6.0, shots_against_recent=72.0)
    aggs = {f"all{n}": window(111, n, min(n, 6), {"npxg": 6.0}, {"npxg": 6})
            for n in WINDOWS}
    axis = build(profile(stats, aggs), history(HOME_TEAM, 6), kick(30),
                 detail=6)
    assert axis.value("recent6.npxga") == 1.2, "6.0/5 (표본 5)"
    assert axis.get("recent6.npxga").sample_count == 5
    assert axis.value("recent6.shots_against") == 12.0
    assert "recent3.npxga" not in axis.metrics, "창이 하나뿐인 값을 퍼뜨렸다"
    assert "recent10.npxga" not in axis.metrics


def test_npxgd_needs_matching_samples():
    stats = season_stats(recent_matches=6,
                         recent_counts={"npxga_recent": 5},
                         npxga_recent=5.0)
    aggs = {"all6": window(111, 6, 6, {"npxg": 6.0}, {"npxg": 6})}
    axis = build(profile(stats, aggs), history(HOME_TEAM, 6), kick(30))
    assert "recent6.npxgd" not in axis.metrics, "표본이 다른데 뺐다"
    assert any("npxGD" in n for n in axis.notes), axis.notes

    stats2 = season_stats(recent_matches=6,
                          recent_counts={"npxga_recent": 6},
                          npxga_recent=6.0)
    axis2 = build(profile(stats2, aggs), history(HOME_TEAM, 6), kick(30))
    assert axis2.value("recent6.npxgd") == 0.0


# --------------------------------------------------------------------------
# 통합 · 금지사항
# --------------------------------------------------------------------------
def test_team_analysis_integration():
    s = Settings(fotmob={"shot_recent_windows": [6, 3],
                         "match_detail_matches": 6})
    ta = analysis.build_team_analysis(
        profile(), HOME_TEAM, history(HOME_TEAM, 6), kick(30), s,
        is_home=True)
    assert ta.time_context is not None
    # 2-A·2-B·2-C 세 축이 채워진다. 나머지(2-D~2-F)는 여전히 None 이어야
    # 한다 — 빈 축을 넣어 분석이 끝난 것처럼 보이게 하지 않는다.
    assert ta.computed_axes() == ["time_context", "chance_quality",
                                  "defensive_quality"]
    assert ta.sustainability is None and ta.venue_context is None
    assert ta.schedule_strength is None
    assert ta.fotmob_id == 111
    assert ta.is_home is True
    assert ta.data_quality is not None
    assert "time_context.recent6" in ta.data_quality.axes


def test_attach_does_not_touch_probs_or_odds():
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
    assert all(m.analysis is not None for m in matches)


def test_no_recommendation_surface():
    """추천을 표현할 수 있는 이름이 축에 들어오지 않는다."""
    import inspect
    banned = ("final_pick", "recommended_pick", "recommendation",
              "predicted_result", "best_bet")
    src = inspect.getsource(analysis)
    for word in banned:
        assert word not in src, word
    aggs = {"all6": window(111, 6, 6, {"xg": 9.0}, {"xg": 6})}
    axis = build(profile(aggregates=aggs), history(HOME_TEAM, 6), kick(30))
    for key in axis.metrics:
        assert not any(w in key for w in banned)


def test_xpts_is_not_recomputed_here():
    """2-A 는 xPTS 를 부르지 않는다 (P1 의 값, 연결은 2-D).

    문서에서 언급하는 것은 괜찮다 — **호출·import 가 없어야** 한다.
    """
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(analysis))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "xpts" not in alias.name, alias.name
        elif isinstance(node, ast.ImportFrom):
            assert "xpts" not in (node.module or ""), node.module
        elif isinstance(node, ast.Name):
            assert node.id != "xpts", "xpts 를 참조한다"
    assert "xpts" not in vars(analysis), "런타임에 xpts 가 붙어 있다"


def test_provenance_is_marked():
    aggs = {"all6": window(111, 6, 6, {"xg": 9.0}, {"xg": 6})}
    axis = build(profile(aggregates=aggs), history(HOME_TEAM, 6), kick(30))
    assert axis.get("season.goals").provenance == OBSERVED
    assert axis.get("recent6.xg").provenance == OBSERVED
    assert axis.get("trend6.xg").provenance == DERIVED


def test_season_snapshot_mismatch_is_disclosed():
    """순위표는 수집 시점 스냅샷이라 as_of 로 잘리지 않는다 — 밝힌다."""
    axis = build(profile(season_stats(played=10)), history(HOME_TEAM, 10),
                 kick(6))
    assert any("스냅샷" in n for n in axis.notes), axis.notes


def test_metric_labels_exist_for_every_spec():
    for name, (label, unit, direction, group) in analysis.SPECS.items():
        assert label, name
        assert unit in ("per_match", "count", "per_shot", "%"), name
        assert direction in (analysis.HIGHER_BETTER, analysis.LOWER_BETTER, "")
        assert group in ("attack", "defense", "result"), name


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
