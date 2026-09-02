"""장소 문맥 회귀 테스트 (Phase 2-E · 홈/원정).

고정하려는 것은 다섯 가지다.

1. **실제 홈/원정으로 거른다.** 팀 이름이나 경기 수로 추정하지 않는다.
2. **기간을 새로 만들지 않는다.** 최근 N경기를 먼저 잡고 그중 그 장소의
   경기를 고른다 — 최근 5경기 중 홈이 1경기면 `home5` 는 1경기다.
3. **장소 표본은 전체 표본의 부분집합이다.** 경기 ID 로 확인하고,
   확인되지 않으면 장소차를 만들지 않는다.
4. **장소차는 같은 지표를 같은 방식으로 잰 두 값의 차이다.** 원천이나
   산출 방식이 다르면 만들지 않는다.
5. **우위 점수도 추천도 만들지 않는다.**

pytest 없이도 돈다:  python tests/test_venue_context.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import analysis, shots                              # noqa: E402
from toto.models import (DERIVED, OBSERVED, MatchAnalysis,    # noqa: E402
                         Metric, SeasonMatch, TeamProfile, TeamRef,
                         TeamStats, revive_match_analysis)
from toto.settings import Settings                            # noqa: E402
from toto.shots import MatchShotAggregate                     # noqa: E402

UTC = timezone.utc
TEAM = "우리팀"
US, THEM = 111, 222
WINDOWS = [6, 3]
CFG = analysis.venue_context_config(Settings())
UP = Path("/root/.claude/uploads/4f45b11b-6ed2-571d-8e30-3901a62afd1b")


def kick(day: int) -> datetime:
    return datetime(2026, 4, day, 20, 0, tzinfo=UTC)


def season(n=6, *, home_first=True, gf_home=3, ga_home=0,
           gf_away=0, ga_away=2) -> list[SeasonMatch]:
    """홈·원정이 번갈아 나오는 n경기. 홈에서 이기고 원정에서 진다."""
    out = []
    for i in range(n):
        home = (i % 2 == 0) if home_first else (i % 2 == 1)
        gf, ga = (gf_home, ga_home) if home else (gf_away, ga_away)
        out.append(SeasonMatch(
            match_id=f"m{i}", competition="epl", kickoff=kick(1 + i),
            kickoff_aware=True,
            home_team=TEAM if home else f"O{i}",
            away_team=f"O{i}" if home else TEAM,
            home_goals=gf if home else ga,
            away_goals=ga if home else gf, finished=True))
    return out


def mine(mid, i, *, xg=None, shots_n=None):
    return MatchShotAggregate(
        match_id=mid, team_id=US, opponent_id=THEM,
        shots=shots_n if shots_n is not None else (12 if i % 2 == 0 else 8),
        shots_on_target=5 if i % 2 == 0 else 2,
        xg=xg if xg is not None else (2.0 if i % 2 == 0 else 0.8),
        npxg=xg if xg is not None else (2.0 if i % 2 == 0 else 0.8),
        xgot=1.5 if i % 2 == 0 else 0.5)


def theirs(mid, i):
    return MatchShotAggregate(
        match_id=mid, team_id=THEM, opponent_id=US,
        shots=6 if i % 2 == 0 else 15,
        shots_on_target=2 if i % 2 == 0 else 6,
        xg=0.5 if i % 2 == 0 else 2.2, npxg=0.5 if i % 2 == 0 else 2.2,
        xgot=0.3 if i % 2 == 0 else 1.8)


def profile(n=6, *, own=None, opp=None, st=None) -> TeamProfile:
    p = TeamProfile(team=TeamRef(canonical=TEAM, fotmob_id=str(US)),
                    league="epl")
    p.stats = st if st is not None else TeamStats(played=n)
    p.shot_matches = list(own if own is not None
                          else [mine(f"m{i}", i) for i in range(n)])
    p.opponent_matches = list(opp if opp is not None
                              else [theirs(f"m{i}", i) for i in range(n)])
    return p


def build(venue=analysis.HOME, *, sm=None, prof=None, as_of=kick(30),
          quality=None, cfg=None, windows=None):
    rows = season() if sm is None else sm
    return analysis.build_venue_context(
        prof if prof is not None else profile(), TEAM, rows, as_of,
        windows if windows is not None else WINDOWS, venue,
        config=cfg or CFG, quality=quality)


def metric(name, value, sample, source, basis, period="home6") -> Metric:
    return Metric(name=name, label=name, value=value, period=period,
                  sample_count=sample, source=source,
                  measurement_basis=basis)


# --------------------------------------------------------------------------
# A·B. 장소 필터
# --------------------------------------------------------------------------
def test_a_home_filter_picks_only_home_matches():
    rows = season()
    picked = analysis.venue_rows(rows, TEAM, analysis.HOME)
    assert [m.match_id for m in picked] == ["m0", "m2", "m4"]
    for m in picked:
        assert m.home_team == TEAM, "홈 경기가 아니다"


def test_b_away_filter_picks_only_away_matches():
    rows = season()
    picked = analysis.venue_rows(rows, TEAM, analysis.AWAY)
    assert [m.match_id for m in picked] == ["m1", "m3", "m5"]
    for m in picked:
        assert m.away_team == TEAM, "원정 경기가 아니다"


def test_a_venue_of_does_not_guess():
    m = season(1)[0]
    assert analysis.venue_of(m, TEAM) == analysis.HOME
    assert analysis.venue_of(m, "다른팀") is None, "이름이 안 맞으면 None"


def test_b_away_context_uses_away_samples():
    axis = build(analysis.AWAY)
    assert axis.value("away_season.points") == 0.0, "원정 3패"
    assert axis.value("away_season.goals") == 0.0
    assert axis.value("away_season.goals_against") == 2.0
    assert abs(axis.value("away6.xg") - 0.8) < 1e-9


# --------------------------------------------------------------------------
# C. 미래 경기 제외
# --------------------------------------------------------------------------
def test_c_future_matches_are_excluded():
    rows = season(6)
    # m4·m5 는 기준시각 뒤
    axis = build(analysis.HOME, sm=rows, as_of=kick(4, ))
    assert axis.value("season.points") is not None
    # 남은 홈 경기는 m0·m2 뿐
    assert axis.get("home_season.points").sample_count == 2
    assert axis.get("season.points").sample_count == 3


def test_c_as_of_none_gives_nothing():
    axis = build(analysis.HOME, as_of=None)
    assert not axis.metrics, "기준이 없으면 과거도 없다"


def test_c_unfinished_match_is_not_history():
    rows = season(6)
    rows[4].finished = False
    axis = build(analysis.HOME, sm=rows)
    assert axis.get("home_season.points").sample_count == 2, "m0·m2 만"


def test_c_cutoff_uses_matches_before_only():
    """이 함수는 kickoff 을 직접 비교하지 않는다 (누수 방지는 한 곳)."""
    import ast
    import inspect
    node = ast.parse(
        inspect.getsource(analysis.build_venue_context).lstrip()).body[0]
    names = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
    assert "kickoff" not in names
    calls = {getattr(n.func, "id", "") for n in ast.walk(node)
             if isinstance(n, ast.Call)}
    assert "team_history" in calls


# --------------------------------------------------------------------------
# D·E. 승점 · 득점 손계산
# --------------------------------------------------------------------------
def test_d_home_points_per_match():
    axis = build(analysis.HOME)
    assert axis.value("home_season.points") == 3.0, "홈 3승"
    assert axis.value("season.points") == 1.5, "3승 3패 → 9/6"
    assert axis.value("home_season.points_venue_gap") == 1.5


def test_e_goals_and_goals_against():
    axis = build(analysis.HOME)
    assert axis.value("home_season.goals") == 3.0
    assert axis.value("home_season.goals_against") == 0.0
    assert axis.value("season.goals") == 1.5          # (3+0)*3 / 6
    assert axis.value("season.goals_against") == 1.0  # (0+2)*3 / 6
    assert axis.value("home_season.goals_venue_gap") == 1.5
    assert axis.value("home_season.goals_against_venue_gap") == -1.0


def test_e_draw_is_one_point():
    rows = [SeasonMatch(match_id=f"m{i}", competition="epl",
                        kickoff=kick(1 + i), kickoff_aware=True,
                        home_team=TEAM, away_team=f"O{i}",
                        home_goals=1, away_goals=1, finished=True)
            for i in range(4)]
    axis = build(analysis.HOME, sm=rows)
    assert axis.value("home_season.points") == 1.0
    assert axis.value("home_season.points_venue_gap") == 0.0, \
        "전부 홈이면 장소차는 정확히 0"


# --------------------------------------------------------------------------
# F. 표본 수
# --------------------------------------------------------------------------
def test_f_sample_counts_are_separate():
    q = analysis.DataQuality()
    axis = build(analysis.HOME, quality=q)
    entry = q.axes["venue_context.home6"]
    assert entry["requested"] == 6
    assert entry["available_matches"] == 3, "최근 6경기 중 홈 3경기"
    assert axis.get("home6.points").sample_count == 3
    assert axis.get("home6.xg").sample_count == 3


def test_f_metric_sample_differs_from_available():
    """xG 가 없는 경기가 섞이면 그 지표의 표본만 줄어든다."""
    own = [MatchShotAggregate(match_id=f"m{i}", team_id=US, opponent_id=THEM,
                              shots=12, xg=None if i == 0 else 2.0,
                              npxg=None if i == 0 else 2.0, xgot=1.5)
           for i in range(6)]
    q = analysis.DataQuality()
    axis = build(analysis.HOME, prof=profile(own=own), quality=q)
    assert q.axes["venue_context.home6"]["available_matches"] == 3
    assert axis.get("home6.points").sample_count == 3, "승점은 3경기 전부"
    assert axis.get("home6.xg").sample_count == 2, "xG 는 2경기뿐"
    assert axis.value("home6.xg") == 2.0


def test_f_venue_window_is_not_a_new_window():
    """최근 3경기 중 홈이 1경기면 `home3` 는 1경기다 (§8)."""
    q = analysis.DataQuality()
    axis = build(analysis.HOME, quality=q)
    assert q.axes["venue_context.home3"]["available_matches"] == 1
    assert q.axes["venue_context.home3"]["requested"] == 3
    assert axis.get("home3.points").sample_count == 1
    assert any("최근 3경기 중 1경기" in n for n in axis.notes), axis.notes


def test_f_period_labels():
    assert analysis.period_label("home_season") == "홈 시즌"
    assert analysis.period_label("away_season") == "원정 시즌"
    assert analysis.period_label("home6") == "최근 6경기 중 홈"
    assert analysis.period_label("away3") == "최근 3경기 중 원정"
    assert analysis.period_label("recent6") == "최근 6경기", "기존 라벨 유지"
    assert analysis.period_label("season") == "시즌"


# --------------------------------------------------------------------------
# G. None ≠ 0
# --------------------------------------------------------------------------
def test_g_missing_metric_is_not_zero():
    own = [MatchShotAggregate(match_id=f"m{i}", team_id=US, opponent_id=THEM,
                              shots=12, xg=None, npxg=None, xgot=None)
           for i in range(6)]
    axis = build(analysis.HOME, prof=profile(own=own))
    assert axis.get("home6.xg") is None
    assert axis.value("home6.xg") != 0.0
    assert axis.get("home6.shots") is not None, "슈팅은 남아 있다"


def test_g_zero_is_a_real_value():
    own = [MatchShotAggregate(match_id=f"m{i}", team_id=US,
                              opponent_id=THEM, shots=0, xg=0.0, npxg=0.0,
                              xgot=0.0) for i in range(6)]
    axis = build(analysis.HOME, prof=profile(own=own))
    assert axis.value("home6.xg") == 0.0
    assert axis.value("home6.shots") == 0.0


def test_g_no_shot_rows_leaves_only_actuals():
    p = profile()
    p.shot_matches = []
    p.opponent_matches = []
    axis = build(analysis.HOME, prof=p)
    assert axis.value("home6.points") == 3.0
    for name in ("xg", "npxg", "xgot", "shots", "npxga", "shots_against"):
        assert axis.get(f"home6.{name}") is None, name


# --------------------------------------------------------------------------
# H. 장소차
# --------------------------------------------------------------------------
def test_h_venue_gap_is_venue_minus_overall():
    axis = build(analysis.HOME)
    for name in ("points", "goals", "xg", "npxg", "shots", "npxga",
                 "shots_against"):
        venue = axis.value(f"home6.{name}")
        overall = axis.value(f"recent6.{name}")
        gap = axis.value(f"home6.{name}{analysis.VENUE_GAP_SUFFIX}")
        assert abs(gap - (venue - overall)) < 1e-12, name


def test_h_gap_carries_common_sample_and_is_derived():
    m = build(analysis.HOME).get("home6.xg_venue_gap")
    assert m.provenance == DERIVED
    assert m.sample_count == 3 and m.common_sample_count == 3
    assert "⊂" in m.note, m.note
    assert m.direction == "", "장소차에 방향을 정하지 않는다"
    assert m.group == analysis.VENUE_GAP_GROUP


def test_h_gap_basis_is_inherited_not_mixed():
    axis = build(analysis.HOME)
    assert axis.get("home6.xg_venue_gap").measurement_basis == \
        analysis.SHOT_EVENTS
    assert axis.get("home6.npxga_venue_gap").measurement_basis == \
        analysis.OPPONENT_SHOT_EVENTS
    assert axis.get("home_season.points_venue_gap").measurement_basis == \
        analysis.FINAL_SCORE
    assert axis.get("home6.xg_venue_gap").source == analysis.DERIVED_SOURCE


def test_h_all_venue_matches_means_zero_gap():
    rows = [SeasonMatch(match_id=f"m{i}", competition="epl",
                        kickoff=kick(1 + i), kickoff_aware=True,
                        home_team=TEAM, away_team=f"O{i}",
                        home_goals=2, away_goals=1, finished=True)
            for i in range(4)]
    axis = build(analysis.HOME, sm=rows)
    for name in ("points", "goals", "goals_against"):
        assert axis.value(f"home_season.{name}_venue_gap") == 0.0, name


def test_h_overall_block_has_no_gap():
    axis = build(analysis.HOME)
    for key in axis.metrics:
        if key.startswith(("season.", "recent")):
            assert not key.endswith(analysis.VENUE_GAP_SUFFIX), key


# --------------------------------------------------------------------------
# I. 비교 불가
# --------------------------------------------------------------------------
def test_i_subset_gate_requires_same_metric():
    a = metric("xg", 1.0, 3, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    b = metric("npxg", 1.0, 6, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    ok, code, _r = analysis.comparison_allowed(
        a, b, common_sample=3, min_sample=3, relation=analysis.SUBSET)
    assert ok is False and code == analysis.BLOCK_METRIC


def test_i_subset_gate_requires_same_basis():
    a = metric("xg", 1.0, 3, analysis.SEASON_XG_TABLE, analysis.MATCH_STAT)
    b = metric("xg", 1.0, 6, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    ok, code, _r = analysis.comparison_allowed(
        a, b, common_sample=3, min_sample=3, relation=analysis.SUBSET)
    assert ok is False and code == analysis.BLOCK_BASIS, code


def test_i_subset_gate_requires_comparable_source():
    a = metric("xg", 1.0, 3, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    b = metric("xg", 1.0, 6, "무언가_새로운_피드", analysis.SHOT_EVENTS)
    ok, code, _r = analysis.comparison_allowed(
        a, b, common_sample=3, min_sample=3, relation=analysis.SUBSET)
    assert ok is False and code == analysis.BLOCK_SOURCE


def test_i_subset_gate_requires_containment():
    a = metric("xg", 1.0, 3, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    b = metric("xg", 1.0, 6, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    ok, code, _r = analysis.comparison_allowed(
        a, b, common_sample=3, min_sample=3, same_match_set=False,
        relation=analysis.SUBSET)
    assert ok is False and code == analysis.BLOCK_NOT_SUBSET


def test_i_subset_gate_requires_sample():
    a = metric("xg", 1.0, 2, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    b = metric("xg", 1.0, 6, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    ok, code, _r = analysis.comparison_allowed(
        a, b, common_sample=2, min_sample=3, relation=analysis.SUBSET)
    assert ok is False and code == analysis.BLOCK_SAMPLE


def test_i_same_set_gate_is_unchanged():
    """2-D 의 판단은 한 줄도 바뀌지 않는다."""
    a = metric("goals", 2.0, 4, analysis.SEASON_MATCH_INDEX,
               analysis.FINAL_SCORE)
    e = metric("xg", 1.0, 4, analysis.SHOTMAP, analysis.SHOT_EVENTS)
    assert analysis.comparison_allowed(
        a, e, common_sample=4, min_sample=3)[0] is True
    # 같은 basis 끼리는 2-D 규칙에서 여전히 막힌다 (등록된 쌍이 아니다)
    b = metric("goals", 1.0, 4, analysis.SEASON_MATCH_INDEX,
               analysis.FINAL_SCORE)
    ok, code, _r = analysis.comparison_allowed(
        a, b, common_sample=4, min_sample=3)
    assert ok is False and code == analysis.BLOCK_BASIS


def test_i_small_venue_sample_blocks_the_gap():
    axis = build(analysis.HOME)
    assert axis.get("home3.points") is not None, "원값은 남는다"
    assert axis.get("home3.points_venue_gap") is None, "1경기로 장소차 금지"


def test_i_gap_is_not_a_trend():
    """장소차와 트렌드는 다른 문을 쓴다."""
    import ast
    import inspect
    node = ast.parse(
        inspect.getsource(analysis.build_venue_context).lstrip()).body[0]
    calls = {getattr(n.func, "id", "") for n in ast.walk(node)
             if isinstance(n, ast.Call)}
    assert "comparison_allowed" in calls
    assert "trend_allowed" not in calls
    assert "trend_band" not in calls


# --------------------------------------------------------------------------
# J. 사유 보존
# --------------------------------------------------------------------------
def test_j_reason_survives_to_notes_and_quality():
    q = analysis.DataQuality()
    axis = build(analysis.HOME, quality=q)
    assert axis.get("home3.points_venue_gap") is None
    assert any("공통 표본 부족" in n for n in axis.notes), axis.notes
    assert "공통 표본 부족" in q.axes["venue_context.home3"]["degraded_reason"]


def test_j_reason_is_merged_across_periods():
    axis = build(analysis.HOME)
    lines = [n for n in axis.notes if n.startswith("값 없음")]
    assert len(lines) == 1, lines


def test_j_serialization_round_trip():
    ta = analysis.TeamAnalysis(team=TEAM, is_home=True)
    ta.venue_context = build(analysis.HOME)
    raw = asdict(MatchAnalysis(home=ta))
    back = revive_match_analysis(json.loads(json.dumps(raw, default=str)))
    axis = back.home.venue_context
    assert axis.value("home6.points") == 3.0
    gap = axis.get("home6.xg_venue_gap")
    assert gap.common_sample_count == 3 and gap.provenance == DERIVED
    assert gap.measurement_basis == analysis.SHOT_EVENTS
    assert axis.notes == ta.venue_context.notes


def test_j_no_venue_when_side_unknown():
    q = analysis.DataQuality()
    axis = analysis.build_venue_context(profile(), TEAM, season(), kick(30),
                                        WINDOWS, "", quality=q)
    assert not axis.metrics
    assert q.axes["venue_context"]["degraded_reason"] == "장소 미상"


# --------------------------------------------------------------------------
# K. 기존 정의와의 일관성
# --------------------------------------------------------------------------
def test_k_overall_recent_matches_2a_definition():
    """전체 최근 구간의 실제 결과는 2-A 와 같은 함수·같은 값이다."""
    rows = season()
    history = analysis.team_history(rows, TEAM, kick(30))
    expect, _n = analysis._result_values(history, TEAM, 6)
    axis = build(analysis.HOME, sm=rows)
    for name in ("points", "goals", "goals_against"):
        assert abs(axis.value(f"recent6.{name}") - expect[name][0]) < 1e-12


def test_k_windows_come_from_settings():
    axis = build(analysis.HOME, windows=[5])
    assert "home5" in {k.split(".")[0] for k in axis.metrics}
    assert "home6" not in {k.split(".")[0] for k in axis.metrics}


def test_k_venue_subset_of_overall_ids():
    rows = season()
    history = analysis.team_history(rows, TEAM, kick(30))
    recent = history[-6:]
    picked = [m for m in recent if analysis.venue_of(m, TEAM) == analysis.HOME]
    assert {m.match_id for m in picked} <= {m.match_id for m in recent}


def test_k_snapshot_disagreement_is_noted():
    st = TeamStats(played=6, home_played=9)      # 스냅샷이 더 많다
    axis = build(analysis.HOME, prof=profile(st=st))
    assert any("스냅샷" in n for n in axis.notes), axis.notes
    assert axis.value("home_season.points") == 3.0, "값은 색인 기준 그대로"


# --------------------------------------------------------------------------
# 12·17·18·19. 하지 않는 것
# --------------------------------------------------------------------------
def test_no_wdl_venue_metric():
    axis = build(analysis.HOME)
    for key in axis.metrics:
        assert key.split(".")[-1] not in ("wins", "draws", "losses"), key
        for banned in ("home_wins", "away_wins", "home_draws"):
            assert banned not in key


def test_no_composite_score():
    import inspect
    src = (inspect.getsource(analysis.build_venue_context)
           + inspect.getsource(analysis.detect_venue_patterns))
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    for banned in ("home_strength_score", "away_strength_score",
                   "venue_advantage_score", "home_edge_score",
                   "final_pick", "recommended_pick", "recommendation",
                   "predicted_result", "best_bet"):
        assert banned not in code, banned
    for name in analysis.SPECS:
        assert not name.endswith("_score"), name


def test_no_strength_of_schedule():
    import inspect
    src = inspect.getsource(analysis.build_venue_context).lower()
    for banned in ("schedule_strength", "strength_of_schedule", "sos",
                   "opponent_strength"):
        assert banned not in src, banned


def test_patterns_are_descriptive_and_thresholded():
    values = {"points_venue_gap": (1.5, 3, ""),
              "npxg_venue_gap": (0.4, 3, ""),
              "npxga_venue_gap": (-0.4, 3, "")}
    got = analysis.detect_venue_patterns(values, CFG)
    assert [c for c, _l, _b in got] == ["A", "B", "C", "D"]
    # 표본이 모자라면 아무 패턴도 만들지 않는다
    small = {k: (v[0], 1, v[2]) for k, v in values.items()}
    assert analysis.detect_venue_patterns(small, CFG) == []
    # 문턱 아래면 만들지 않는다
    tiny = {k: (v[0] / 10, 3, v[2]) for k, v in values.items()}
    assert analysis.detect_venue_patterns(tiny, CFG) == []


def test_pattern_d_needs_two_directions_agreeing():
    """D 는 A~C 를 다시 세는 것이 아니다 (증거 중복 방지)."""
    only_points = {"points_venue_gap": (1.5, 3, "")}
    codes = [c for c, _l, _b in
             analysis.detect_venue_patterns(only_points, CFG)]
    assert codes == ["A"], codes
    mixed = {"points_venue_gap": (1.5, 3, ""),
             "npxg_venue_gap": (-0.9, 3, "")}    # 방향이 다르다
    codes = [c for c, _l, _b in analysis.detect_venue_patterns(mixed, CFG)]
    assert "D" not in codes, codes


def test_thresholds_come_from_config():
    s = Settings(analysis={"venue_context": {
        "min_sample": 2, "thresholds": {"points_gap_high": 9.9}}})
    cfg = analysis.venue_context_config(s)
    assert cfg["min_sample"] == 2 and cfg["thresholds"]["points_gap_high"] == 9.9
    assert cfg["thresholds"]["attack_gap_high"] == 0.25, "나머지는 기본값"
    values = {"points_venue_gap": (1.5, 3, "")}
    assert analysis.detect_venue_patterns(values, cfg) == [], "문턱 위로 올렸다"


def test_no_language_of_recommendation():
    axis = build(analysis.HOME)
    # 고정 문구는 "이 축은 그것이 아니다" 를 밝히는 부정문이라 뺀다.
    body = [n for n in axis.notes if n not in analysis.VENUE_DISCLAIMERS]
    assert len(body) < len(axis.notes), "고정 문구가 붙어 있어야 한다"
    text = " ".join(body) + " ".join(
        m.note + m.label for m in axis.metrics.values())
    for word in ("추천", "픽", "베팅", "홈승", "원정승", "우위", "유리",
                 "강팀", "약팀"):
        assert word not in text, f"{word} in output"


# --------------------------------------------------------------------------
# 22. TeamAnalysis 연결 · 확률 격리
# --------------------------------------------------------------------------
def test_team_analysis_integration():
    s = Settings(fotmob={"shot_recent_windows": [6, 3],
                         "match_detail_matches": 6})
    ta = analysis.build_team_analysis(
        profile(), TEAM, season(), kick(30), s, is_home=True)
    assert ta.computed_axes() == ["time_context", "chance_quality",
                                  "defensive_quality", "sustainability",
                                  "venue_context"]
    assert ta.schedule_strength is None, "2-F 를 미리 만들었다"
    assert "venue_context.home6" in ta.data_quality.axes
    assert ta.venue_context.value("home_season.points") == 3.0


def test_away_team_gets_away_context():
    s = Settings(fotmob={"shot_recent_windows": [6, 3],
                         "match_detail_matches": 6})
    ta = analysis.build_team_analysis(
        profile(), TEAM, season(), kick(30), s, is_home=False)
    assert "away_season" in {k.split(".")[0] for k in
                             ta.venue_context.metrics}
    assert "home_season" not in {k.split(".")[0] for k in
                                 ta.venue_context.metrics}


def test_unknown_side_makes_no_axis():
    s = Settings(fotmob={"shot_recent_windows": [6, 3]})
    ta = analysis.build_team_analysis(
        profile(), TEAM, season(), kick(30), s, is_home=None)
    assert ta.venue_context is None
    assert ta.data_quality.axes["venue_context"]["degraded_reason"] == "장소 미상"


def test_probability_isolation():
    import ast
    import inspect
    node = ast.parse(
        inspect.getsource(analysis.build_venue_context).lstrip()).body[0]
    banned = {"predict", "probs", "MatchProb", "odds",
              "additive_probabilities"}
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            assert n.id not in banned, n.id
        if isinstance(n, ast.Attribute):
            assert n.attr not in banned, n.attr


def test_run_all_leaves_probs_and_odds_untouched():
    from toto import fixtures
    from toto.analyze import run_all
    s = Settings(fotmob={"shot_recent_windows": [6, 3],
                         "match_detail_matches": 6})
    matches = fixtures.build_demo_matches()
    run_all(matches, s, season_matches=[])       # 확률은 여기서 만들어진다
    before = [(m.odds.home, m.odds.draw, m.odds.away) for m in matches]
    probs = [m.probs.as_tuple if m.probs else None for m in matches]
    assert any(p is not None for p in probs), "확률이 있어야 비교가 의미 있다"
    run_all(matches, s, season_matches=[])       # 두 번째 실행이 바꾸지 않는다
    assert [(m.odds.home, m.odds.draw, m.odds.away)
            for m in matches] == before
    assert [m.probs.as_tuple if m.probs else None for m in matches] == probs


# --------------------------------------------------------------------------
# 23. 리포트 출력
# --------------------------------------------------------------------------
def _one_match_report():
    from toto.models import Match, Odds, Report
    m = Match(no=1, league="epl", kickoff_kst="2026-04-30 20:00",
              home=TeamRef(canonical=TEAM, display=TEAM),
              away=TeamRef(canonical="상대", display="상대"),
              odds=Odds(home=2.0, draw=3.4, away=3.8))
    m.home_profile = profile()
    m.away_profile = TeamProfile(team=m.away, league="epl", stats=TeamStats())
    s = Settings(fotmob={"shot_recent_windows": [6, 3],
                         "match_detail_matches": 6})
    analysis.attach_time_context([m], s, season_matches=season())
    return Report(round_id="T", generated_at="fixed", matches=[m]), s


def test_report_shows_venue_context():
    from toto.render import render_report
    report, s = _one_match_report()
    html = render_report(report, s)
    assert "홈/원정 문맥" in html
    assert "장소차" in html
    assert "n=3" in html, "표본 수가 보여야 한다"
    assert "1.50" in html or "+1.50" in html


def test_report_stays_self_contained():
    import re
    from toto.render import render_report
    report, s = _one_match_report()
    html = render_report(report, s)
    assert not re.findall(r'(?:src|href)\s*=\s*"(?:https?:)?//', html)
    for banned in ("<script src", "<iframe", "fetch(", "XMLHttpRequest"):
        assert banned not in html, banned


def test_report_never_recommends():
    from toto.render import render_report
    report, s = _one_match_report()
    html = render_report(report, s)
    i = html.find("홈/원정 문맥")
    end = html.find("</article>", i)
    block = html[i:end if end > i else i + 6000]
    # 고정 문구(부정문)는 빼고 본다 — 이 축이 하지 않는 일을 밝히는 자리다.
    block = block.replace("승무패를 추천하지 않습니다", "")
    for word in ("추천", "우위", "베팅", "홈승", "원정승"):
        assert word not in block, word


# --------------------------------------------------------------------------
# 28. 실물 260048
# --------------------------------------------------------------------------
def _real(mid, filename):
    payload = json.loads((UP / filename).read_text())
    events = [shots.ShotEvent(**d) for d in payload["shots"]]
    hid, aid = payload["team_ids"]["home"], payload["team_ids"]["away"]
    goals = {hid: 0, aid: 0}
    for e in events:
        if e.event_type == "Goal" and not e.is_own_goal:
            goals[e.team_id] += 1
    return payload, hid, aid, shots.aggregate_match(events, hid, aid), goals


def _real_axis(team, tid, oid, aggs, goals, hid, aid, venue, min_sample=1):
    row = SeasonMatch(
        match_id="5795372", competition="epl",
        kickoff=datetime(2026, 8, 23, 20, 0, tzinfo=analysis.KST),
        kickoff_aware=True, home_team="Fulham", away_team="Chelsea",
        home_fotmob_id=hid, away_fotmob_id=aid,
        home_goals=goals[hid], away_goals=goals[aid], finished=True)
    p = TeamProfile(team=TeamRef(canonical=team, fotmob_id=str(tid)))
    p.stats = TeamStats()
    p.shot_matches = [aggs[tid]]
    p.opponent_matches = [aggs[oid]]
    cfg = {"min_sample": min_sample,
           "thresholds": dict(CFG["thresholds"])}
    return analysis.build_venue_context(
        p, team, [row], datetime(2026, 8, 29, 20, 0, tzinfo=analysis.KST),
        [6], venue, config=cfg)


def test_28_real_fulham_home_context():
    if not UP.exists():
        return
    _pay, hid, aid, aggs, goals = _real("5795372",
                                        "da0dcdd0-match_5795372.json")
    axis = _real_axis("Fulham", hid, aid, aggs, goals, hid, aid,
                      analysis.HOME)
    assert axis.value("home_season.goals") == 2.0
    assert axis.value("home_season.goals_against") == 3.0
    assert axis.value("home_season.points") == 0.0
    assert abs(axis.value("home6.xg") - aggs[hid].xg) < 1e-12
    assert abs(axis.value("home6.npxg") - aggs[hid].npxg) < 1e-12
    assert abs(axis.value("home6.xgot") - aggs[hid].xgot) < 1e-12
    assert axis.value("home6.shots") == float(aggs[hid].shots)
    assert abs(axis.value("home6.npxga") - aggs[aid].npxg) < 1e-12
    assert axis.value("home6.shots_against") == float(aggs[aid].shots)
    # 과거 경기가 전부 홈이므로 장소차는 정확히 0 이어야 한다
    for name in ("points", "goals", "xg", "npxg", "shots", "npxga"):
        assert axis.value(f"home6.{name}_venue_gap") == 0.0, name


def test_28_real_chelsea_away_context():
    if not UP.exists():
        return
    _pay, hid, aid, aggs, goals = _real("5795372",
                                        "da0dcdd0-match_5795372.json")
    axis = _real_axis("Chelsea", aid, hid, aggs, goals, hid, aid,
                      analysis.AWAY)
    assert axis.value("away_season.goals") == 3.0
    assert axis.value("away_season.points") == 3.0
    assert abs(axis.value("away6.xg") - aggs[aid].xg) < 1e-12
    assert axis.value("away6.shots") == float(aggs[aid].shots)
    assert abs(axis.value("away6.npxga") - aggs[hid].npxg) < 1e-12
    # 첼시는 이 경기에서 원정이므로 홈 표본이 0 이다
    home = _real_axis("Chelsea", aid, hid, aggs, goals, hid, aid,
                      analysis.HOME)
    assert home.get("home_season.points") is None
    assert home.get("home6.xg") is None


def test_28_real_venue_filter_is_not_by_name_only():
    if not UP.exists():
        return
    _pay, hid, aid, aggs, goals = _real("5795372",
                                        "da0dcdd0-match_5795372.json")
    row = SeasonMatch(match_id="5795372", competition="epl",
                      kickoff=datetime(2026, 8, 23, 20, 0,
                                       tzinfo=analysis.KST),
                      kickoff_aware=True, home_team="Fulham",
                      away_team="Chelsea", home_fotmob_id=hid,
                      away_fotmob_id=aid, home_goals=goals[hid],
                      away_goals=goals[aid], finished=True)
    assert analysis.venue_of(row, "Fulham") == analysis.HOME
    assert analysis.venue_of(row, "Chelsea") == analysis.AWAY
    assert analysis.venue_of(row, "Arsenal") is None


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
