"""기회의 질 / 공격 실행 회귀 테스트 (Phase 2-B).

고정하려는 것은 네 가지다.

1. **비율은 합계끼리 나눈다.** 경기별 비율의 평균이 아니다 — 슛이 적은
   경기가 과대 대표되면 안 된다.
2. **분자와 분모의 표본이 같다.** xG 가 4경기에만 있으면 그 4경기의 슛으로
   나눈다. 6경기치 슛을 분모로 쓰지 않는다.
3. **0 과 None 이 다르다.** xG=0 · 슛>0 이면 슛당 xG 는 0.0 이고,
   xG=None 이면 None 이다. 분모가 0 이면 None 이다(0 이 답이 아니다).
4. **`xGOT − npxG` 를 만들지 않는다.** PK 포함 기준이 달라 하나의 지표로
   쓸 수 없다.

pytest 없이도 돈다:  python tests/test_chance_quality.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import analysis                                       # noqa: E402
from toto.models import DERIVED, OBSERVED, SeasonMatch          # noqa: E402
from toto.models import TeamProfile, TeamRef, TeamStats         # noqa: E402
from toto.settings import Settings                              # noqa: E402
from toto.shots import MatchShotAggregate, RecentShotAggregate  # noqa: E402

UTC = timezone.utc
TEAM = "Alpha FC"
TEAM_ID = 111
WINDOWS = [10, 6, 5, 3]
CFG = {"min_sample": 3,
       "thresholds": dict(analysis.DEFAULT_CHANCE_QUALITY["thresholds"])}


def kick(day: int, hour: int = 20) -> datetime:
    return datetime(2026, 4, day, hour, 0, tzinfo=UTC)


def match(mid: str, *, shots=10, sot=4, inside=6, outside=4,
          xg=1.0, npxg=1.0, xgot=0.9) -> MatchShotAggregate:
    return MatchShotAggregate(
        match_id=mid, team_id=TEAM_ID, is_home=True, shots=shots,
        shots_on_target=sot, shots_inside_box=inside,
        shots_outside_box=outside, xg=xg, npxg=npxg, xgot=xgot)


def season(mids, goals_for=2, goals_against=1, start_day=1
           ) -> list[SeasonMatch]:
    out = []
    for i, mid in enumerate(mids):
        out.append(SeasonMatch(
            match_id=mid, competition="epl", kickoff=kick(start_day + i),
            kickoff_aware=True, home_team=TEAM, away_team=f"Opp{i}",
            home_goals=goals_for, away_goals=goals_against, finished=True))
    return out


def window(mids, requested=6) -> RecentShotAggregate:
    """창은 합계·표본 수만 들고 있다 (실제 구조와 같게 채운다)."""
    return RecentShotAggregate(
        team_id=TEAM_ID, window=requested, venue="all",
        requested_matches=requested, available_matches=len(mids),
        match_ids=list(mids), sums={}, counts={})


def stats(**over) -> TeamStats:
    base = dict(played=6, goals_for=12, goals_against=6, points=12,
                wins=4, draws=0, losses=2, shots_pg=12.0,
                shots_on_target_pg=4.8, big_chances_pg=2.0,
                xg_total=9.0, xga_total=6.0, xg_played=6)
    base.update(over)
    return TeamStats(**base)


def profile(rows, mids=None, st=None, requested=6) -> TeamProfile:
    p = TeamProfile(team=TeamRef(canonical=TEAM, fotmob_id=str(TEAM_ID)),
                    league="epl")
    p.stats = st if st is not None else stats()
    ids = list(mids if mids is not None else [r.match_id for r in rows])
    p.shot_matches = list(rows)
    p.shot_aggregates = {f"all{w}": window(ids[:w], w) for w in WINDOWS}
    return p


def build(prof, sm, as_of=kick(30), windows=None, cfg=None, quality=None):
    return analysis.build_chance_quality(
        prof, TEAM, sm, as_of, windows or WINDOWS, cfg or CFG, quality)


# --------------------------------------------------------------------------
# 1. 기간
# --------------------------------------------------------------------------
def test_season_period_present():
    axis = build(profile([], mids=[]), season([]))
    assert axis.value("season.shots") == 12.0
    assert axis.value("season.xg") == 1.5, "9.0/6"
    assert axis.value("season.goals") == 2.0
    assert axis.get("season.shots").period == analysis.SEASON


def test_all_recent_periods_present():
    mids = [f"m{i}" for i in range(10)]
    rows = [match(m) for m in mids]
    axis = build(profile(rows, mids), season(mids))
    for w in (10, 6, 5, 3):
        assert axis.value(f"recent{w}.shots") == 10.0, w
        assert axis.get(f"recent{w}.xg_per_shot") is not None, w


def test_periods_are_not_merged():
    mids = ["m0", "m1", "m2"]
    rows = [match(m, shots=20, xg=4.0) for m in mids]
    axis = build(profile(rows, mids), season(mids))
    assert axis.value("season.shots") == 12.0
    assert axis.value("recent3.shots") == 20.0
    for key, metric in axis.metrics.items():
        assert key.startswith(metric.period + "."), key


# --------------------------------------------------------------------------
# 2. 파생지표 — 합계끼리 나눈다
# --------------------------------------------------------------------------
def test_ratio_is_sum_over_sum_not_mean_of_ratios():
    """경기별 비율의 평균이면 0.15, 합계끼리면 0.10 이다."""
    rows = [match("m0", shots=1, xg=0.2, npxg=0.2),
            match("m1", shots=9, xg=0.7, npxg=0.7)]
    axis = build(profile(rows), season(["m0", "m1"]))
    got = axis.value("recent3.xg_per_shot")
    assert abs(got - 0.09) < 1e-9, f"합계 기준 0.9/10 이어야 한다: {got}"
    mean_of_ratios = (0.2 / 1 + 0.7 / 9) / 2
    assert abs(got - mean_of_ratios) > 0.01, "평균의 평균을 만들었다"


def test_xg_per_shot_uses_only_matches_with_both():
    """xG 가 2경기에만 있으면 그 2경기의 슛으로 나눈다 (§10)."""
    rows = [match("m0", shots=10, xg=1.0), match("m1", shots=10, xg=1.0),
            match("m2", shots=10, xg=None), match("m3", shots=10, xg=None)]
    axis = build(profile(rows), season(["m0", "m1", "m2", "m3"]))
    m = axis.get("recent6.xg_per_shot")
    assert abs(m.value - 0.10) < 1e-9, "2.0/20 이어야 한다 (40 이 아니라)"
    assert m.sample_count == 2, "표본은 xG 가 있던 경기 수"
    assert axis.get("recent6.shots").sample_count == 4


def test_npxg_per_shot_independent_sample():
    rows = [match("m0", shots=8, npxg=1.6), match("m1", shots=12, npxg=None)]
    axis = build(profile(rows), season(["m0", "m1"]))
    m = axis.get("recent6.npxg_per_shot")
    assert abs(m.value - 0.20) < 1e-9
    assert m.sample_count == 1


def test_box_shot_share_is_percent():
    rows = [match("m0", shots=10, inside=7, outside=3)]
    axis = build(profile(rows), season(["m0"]))
    m = axis.get("recent3.box_shot_share")
    assert m.value == 70.0, "프로젝트 관례는 % 다"
    assert m.unit == "%"


def test_on_target_rate_is_percent():
    rows = [match("m0", shots=20, sot=5)]
    axis = build(profile(rows), season(["m0"]))
    assert axis.value("recent3.on_target_rate") == 25.0


def test_gaps_use_final_score_not_shotmap_goals():
    """득점은 슛맵이 아니라 최종 스코어. 자책골 때문이다."""
    rows = [match("m0", xg=1.0, npxg=1.0, xgot=0.8)]
    axis = build(profile(rows), season(["m0"], goals_for=3))
    assert axis.value("recent3.goals") == 3.0
    assert abs(axis.value("recent3.goals_minus_xg") - 2.0) < 1e-9
    assert abs(axis.value("recent3.goals_minus_npxg") - 2.0) < 1e-9
    assert abs(axis.value("recent3.goals_minus_xgot") - 2.2) < 1e-9


def test_gap_skips_matches_without_a_known_score():
    rows = [match("m0", xg=1.0), match("m9", xg=5.0)]   # m9 는 색인에 없다
    axis = build(profile(rows), season(["m0"], goals_for=2))
    m = axis.get("recent6.goals_minus_xg")
    assert abs(m.value - 1.0) < 1e-9, "스코어를 아는 경기만 써야 한다"
    assert m.sample_count == 1
    assert "미상" in m.note


def test_xgot_minus_npxg_is_never_created():
    """§6 — PK 포함 기준이 달라 하나의 지표로 만들지 않는다."""
    rows = [match("m0")]
    axis = build(profile(rows), season(["m0"]))
    banned = ("xgot_delta", "xgot_minus_npxg", "npxg_minus_xgot",
              "finishing", "conversion", "결정력")
    for key, metric in axis.metrics.items():
        for word in banned:
            assert word not in key, key
            assert word not in metric.name, metric.name
    import inspect
    src = inspect.getsource(analysis.build_chance_quality)
    assert "xgot_delta" not in src


# --------------------------------------------------------------------------
# 3. Edge cases (§18)
# --------------------------------------------------------------------------
def test_zero_shots_gives_none_not_zero():
    rows = [match("m0", shots=0, sot=0, inside=0, outside=0,
                  xg=0.0, npxg=0.0, xgot=0.0)]
    axis = build(profile(rows), season(["m0"]))
    assert axis.value("recent3.shots") == 0.0, "슈팅 0 은 실제 값이다"
    assert axis.get("recent3.xg_per_shot") is None, "0 으로 나눌 수 없다"
    assert axis.get("recent3.box_shot_share") is None
    assert axis.get("recent3.on_target_rate") is None


def test_zero_xg_with_shots_is_zero():
    rows = [match("m0", shots=10, xg=0.0, npxg=0.0, xgot=0.0)]
    axis = build(profile(rows), season(["m0"], goals_for=0))
    assert axis.value("recent3.xg") == 0.0
    assert axis.value("recent3.xg_per_shot") == 0.0, "None 이 아니라 0.0"
    assert axis.get("recent3.xg_per_shot").known is True
    assert axis.value("recent3.goals") == 0.0
    assert axis.value("recent3.goals_minus_xg") == 0.0


def test_none_xg_gives_none_ratio():
    rows = [match("m0", shots=10, xg=None, npxg=None, xgot=None)]
    axis = build(profile(rows), season(["m0"]))
    assert axis.get("recent3.xg") is None
    assert axis.get("recent3.xg_per_shot") is None
    assert axis.get("recent3.goals_minus_xg") is None
    assert axis.value("recent3.shots") == 10.0, "슈팅은 남아야 한다"


def test_none_xgot_only_drops_its_own_metrics():
    rows = [match("m0", xg=1.2, npxg=1.2, xgot=None)]
    axis = build(profile(rows), season(["m0"]))
    assert axis.get("recent3.xgot") is None
    assert axis.get("recent3.goals_minus_xgot") is None
    assert axis.value("recent3.xg_per_shot") is not None


def test_none_denominator_drops_the_match_not_the_metric():
    """분모가 없는 경기는 표본에서 빠진다 (0 으로 치지 않는다)."""
    rows = [{"match_id": "m0", "team_id": TEAM_ID, "shots": None,
             "shots_on_target": 3, "shots_inside_box": 2,
             "shots_outside_box": 1, "xg": 1.0, "npxg": 1.0, "xgot": 0.8},
            {"match_id": "m1", "team_id": TEAM_ID, "shots": 10,
             "shots_on_target": 4, "shots_inside_box": 6,
             "shots_outside_box": 4, "xg": 2.0, "npxg": 2.0, "xgot": 1.5}]
    prof = profile([], mids=["m0", "m1"])
    prof.shot_matches = rows
    axis = build(prof, season(["m0", "m1"]))
    m = axis.get("recent6.xg_per_shot")
    assert abs(m.value - 0.20) < 1e-9, "슛이 있는 경기만: 2.0/10"
    assert m.sample_count == 1
    assert axis.get("recent6.shots").sample_count == 1
    assert axis.get("recent6.xg").sample_count == 2, "xG 자체는 2경기다"


def test_empty_window_makes_nothing():
    axis = build(profile([], mids=[]), season([]))
    assert not any(k.startswith("recent") for k in axis.metrics)


# --------------------------------------------------------------------------
# 4. 표본 (§9)
# --------------------------------------------------------------------------
def test_requested_available_and_metric_sample_are_distinct():
    mids = ["m0", "m1", "m2", "m3", "m4"]          # 요청 6, 확보 5
    rows = [match(m, xg=1.0 if i < 4 else None) for i, m in enumerate(mids)]
    quality = analysis.DataQuality()
    axis = build(profile(rows, mids), season(mids), quality=quality)
    entry = quality.axes["chance_quality.recent6"]
    assert entry["requested"] == 6
    assert entry["available_matches"] == 5
    assert axis.get("recent6.shots").sample_count == 5
    assert axis.get("recent6.xg").sample_count == 4
    assert axis.get("recent6.xg_per_shot").sample_count == 4


def test_metric_mean_matches_the_window_aggregate():
    """경기별 평균이 슛 계층 창의 avg() 와 같아야 한다 (다른 경로, 같은 답)."""
    from toto import shots as shot_layer
    mids = ["m0", "m1", "m2"]
    rows = [match("m0", shots=8, xg=1.0), match("m1", shots=12, xg=None),
            match("m2", shots=10, xg=2.0)]
    agg = shot_layer.aggregate_recent(rows, TEAM_ID, 6)
    prof = profile(rows, mids)
    prof.shot_aggregates["all6"] = agg
    axis = build(prof, season(mids))
    assert abs(axis.value("recent6.xg") - agg.avg("xg")) < 1e-12
    assert abs(axis.value("recent6.shots") - agg.avg("shots")) < 1e-12
    assert axis.get("recent6.xg").sample_count == agg.sample("xg") == 2


def test_window_fallback_requires_a_complete_sample():
    """경기별 원재료가 없으면 표본이 완전히 일치할 때만 비율을 만든다."""
    from toto import shots as shot_layer
    rows = [match("m0", shots=10, xg=1.0), match("m1", shots=10, xg=None)]
    agg = shot_layer.aggregate_recent(rows, TEAM_ID, 6)
    prof = profile([], mids=["m0", "m1"])          # shot_matches 를 비운다
    prof.shot_aggregates["all6"] = agg
    axis = build(prof, season(["m0", "m1"]))
    assert axis.value("recent6.xg") is not None, "관측값은 창에서 나온다"
    assert axis.get("recent6.xg_per_shot") is None, "표본 불일치인데 만들었다"
    assert any("원재료" in n for n in axis.notes), axis.notes

    rows2 = [match("m0", shots=10, xg=1.0), match("m1", shots=10, xg=3.0)]
    agg2 = shot_layer.aggregate_recent(rows2, TEAM_ID, 6)
    prof2 = profile([], mids=["m0", "m1"])
    prof2.shot_aggregates["all6"] = agg2
    axis2 = build(prof2, season(["m0", "m1"]))
    assert abs(axis2.value("recent6.xg_per_shot") - 0.2) < 1e-9
    assert axis2.get("recent6.goals_minus_xg") is None, "차이는 못 만든다"


def test_season_skips_ratios_when_samples_differ():
    axis = build(profile([], mids=[]), season([]),
                 )   # played=6, xg_played=6 → 계산됨
    assert axis.get("season.xg_per_shot") is not None
    prof = profile([], mids=[], st=stats(xg_played=4))
    axis2 = build(prof, season([]))
    assert axis2.get("season.xg_per_shot") is None
    assert axis2.get("season.goals_minus_xg") is None
    assert any("표본" in n for n in axis2.notes), axis2.notes


# --------------------------------------------------------------------------
# 5. Provenance · direction · group
# --------------------------------------------------------------------------
def test_provenance_split():
    rows = [match("m0")]
    axis = build(profile(rows), season(["m0"]))
    for name in ("shots", "shots_on_target", "shots_inside_box", "xg",
                 "npxg", "xgot", "goals"):
        m = axis.get(f"recent3.{name}")
        assert m is not None and m.provenance == OBSERVED, name
    for name in ("xg_per_shot", "npxg_per_shot", "box_shot_share",
                 "on_target_rate", "goals_minus_xg", "goals_minus_npxg",
                 "goals_minus_xgot"):
        m = axis.get(f"recent3.{name}")
        assert m is not None and m.provenance == DERIVED, name


def test_no_model_provenance_in_this_phase():
    from toto.models import MODEL
    rows = [match("m0")]
    axis = build(profile(rows), season(["m0"]))
    assert all(m.provenance != MODEL for m in axis.metrics.values())


def test_gap_metrics_have_no_direction():
    """득점−xG 가 양수라고 좋은 게 아니다 — 방향을 정하지 않는다."""
    rows = [match("m0")]
    axis = build(profile(rows), season(["m0"]))
    for name in ("goals_minus_xg", "goals_minus_npxg", "goals_minus_xgot"):
        assert axis.get(f"recent3.{name}").direction == "", name
    assert axis.get("recent3.xg_per_shot").direction == analysis.HIGHER_BETTER


def test_group_metadata():
    rows = [match("m0")]
    axis = build(profile(rows), season(["m0"]))
    expect = {
        "shots": analysis.VOLUME, "shots_on_target": analysis.VOLUME,
        "shots_inside_box": analysis.VOLUME,
        "xg": analysis.CHANCE_CREATION, "npxg": analysis.CHANCE_CREATION,
        "xg_per_shot": analysis.CHANCE_CREATION,
        "npxg_per_shot": analysis.CHANCE_CREATION,
        "box_shot_share": analysis.CHANCE_CREATION,
        "xgot": analysis.EXECUTION, "on_target_rate": analysis.EXECUTION,
        "goals_minus_xg": analysis.GAP, "goals_minus_npxg": analysis.GAP,
        "goals_minus_xgot": analysis.GAP,
        "goals": analysis.OUTCOME,
    }
    for name, group in expect.items():
        assert axis.get(f"recent3.{name}").group == group, name


def test_groups_are_metadata_not_scores():
    """묶음은 중복 근거를 피하기 위한 라벨이지 가중치가 아니다."""
    import inspect
    import re
    src = inspect.getsource(analysis.build_chance_quality)
    for word in ("weight", "score", "points", "rating", "rank"):
        hit = re.search(rf"\b{word}\b", src)
        assert hit is None, f"{word}: {src[max(0, hit.start()-40):hit.end()+40]}"
    assert "GROUPS" in inspect.getsource(analysis._metric)


# --------------------------------------------------------------------------
# 6. 패턴 (§13, §14)
# --------------------------------------------------------------------------
def test_pattern_a_high_shots_low_quality():
    values = {"shots": (18.0, 6, ""), "xg_per_shot": (0.07, 6, "")}
    got = analysis.detect_patterns(values, CFG)
    assert [c for c, _l, _b in got] == ["A"]
    assert "낮음" in got[0][1]


def test_pattern_b_low_shots_high_quality():
    values = {"shots": (8.0, 6, ""), "xg_per_shot": (0.16, 6, "")}
    assert [c for c, _l, _b in analysis.detect_patterns(values, CFG)] == ["B"]


def test_pattern_c_goals_below_xg():
    values = {"xg": (2.0, 6, ""), "goals_minus_xg": (-0.8, 6, "")}
    assert [c for c, _l, _b in analysis.detect_patterns(values, CFG)] == ["C"]


def test_pattern_d_high_xg_and_xgot():
    values = {"xg": (2.0, 6, ""), "xgot": (1.9, 6, "")}
    assert [c for c, _l, _b in analysis.detect_patterns(values, CFG)] == ["D"]


def test_small_sample_produces_no_pattern():
    values = {"shots": (18.0, 2, ""), "xg_per_shot": (0.07, 2, "")}
    assert analysis.detect_patterns(values, CFG) == []


def test_pattern_thresholds_come_from_config():
    s = Settings(analysis={"chance_quality": {
        "min_sample": 1, "thresholds": {"shots_high": 5.0,
                                        "xg_per_shot_low": 0.5}}})
    cfg = analysis.chance_quality_config(s)
    assert cfg["min_sample"] == 1
    assert cfg["thresholds"]["shots_high"] == 5.0
    assert cfg["thresholds"]["xg_high"] == \
        analysis.DEFAULT_CHANCE_QUALITY["thresholds"]["xg_high"]
    values = {"shots": (6.0, 1, ""), "xg_per_shot": (0.1, 1, "")}
    assert [c for c, _l, _b in analysis.detect_patterns(values, cfg)] == ["A"]


def test_patterns_never_predict_or_recommend():
    rows = [match(f"m{i}", shots=20, xg=1.0, npxg=1.0, xgot=1.9)
            for i in range(6)]
    mids = [r.match_id for r in rows]
    axis = build(profile(rows, mids), season(mids, goals_for=0))
    lines = analysis.patterns_in(axis)
    assert lines, "패턴이 하나는 나와야 하는 표본이다"
    banned = ("추천", "픽", "베팅", "반등", "결정력", "홈승", "무승부 추천",
              "원정승", "예상", "반드시")
    for line in lines:
        for word in banned:
            assert word not in line, f"{word} in {line}"


def test_pattern_lines_are_discoverable():
    values = {"shots": (18.0, 6, ""), "xg_per_shot": (0.07, 6, "")}
    assert analysis.detect_patterns(values, CFG)[0][0] in analysis.PATTERN_LABELS


# --------------------------------------------------------------------------
# 7. 시점 · 통합 · 보호
# --------------------------------------------------------------------------
def test_future_match_in_window_drops_the_period():
    mids = ["m0", "m1"]
    rows = [match(m) for m in mids]
    sm = season(["m0"]) + [SeasonMatch(
        match_id="m1", competition="epl", kickoff=kick(20), kickoff_aware=True,
        home_team=TEAM, away_team="Z", home_goals=5, away_goals=0,
        finished=True)]
    axis = build(profile(rows, mids), sm, as_of=kick(5))
    assert not any(k.startswith("recent3.") for k in axis.metrics)
    assert any("기준시각 이후" in n for n in axis.notes), axis.notes


def test_cutoff_is_shared_with_2a():
    """자체 cutoff 로직을 만들지 않는다 — matches_before 만 쓴다."""
    import inspect
    src = inspect.getsource(analysis.build_chance_quality)
    assert "matches_before" in src
    assert ".kickoff" not in src


def test_team_analysis_integration():
    s = Settings(fotmob={"shot_recent_windows": [6, 3],
                         "match_detail_matches": 6})
    mids = ["m0", "m1", "m2"]
    rows = [match(m) for m in mids]
    ta = analysis.build_team_analysis(
        profile(rows, mids), TEAM, season(mids), kick(30), s, is_home=True)
    assert ta.chance_quality is not None
    assert ta.time_context is not None
    assert ta.defensive_quality is None, "2-C 를 미리 만들었다"
    assert "chance_quality.recent6" in ta.data_quality.axes
    assert "time_context.recent6" in ta.data_quality.axes


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


def test_chance_quality_does_not_touch_xpts_or_predict():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(analysis))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "xpts" not in (node.module or "")
            assert "predict" not in (node.module or "")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "xpts" not in alias.name and "predict" not in alias.name
    assert "xpts" not in vars(analysis) and "predict" not in vars(analysis)


def test_no_recommendation_surface():
    import inspect
    banned = ("final_pick", "recommended_pick", "recommendation",
              "predicted_result", "best_bet", "finishing_score")
    src = inspect.getsource(analysis)
    for word in banned:
        assert word not in src, word


def test_serialization_round_trip():
    from dataclasses import asdict
    from toto.models import MatchAnalysis, revive_match_analysis
    s = Settings(fotmob={"shot_recent_windows": [6, 3],
                         "match_detail_matches": 6})
    mids = ["m0", "m1", "m2"]
    rows = [match(m) for m in mids]
    ta = analysis.build_team_analysis(
        profile(rows, mids), TEAM, season(mids), kick(30), s)
    back = revive_match_analysis(asdict(MatchAnalysis(home=ta)))
    axis = back.home.chance_quality
    assert axis is not None
    assert axis.get("recent3.xg_per_shot").group == analysis.CHANCE_CREATION
    assert axis.get("recent3.xg_per_shot").provenance == DERIVED


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
