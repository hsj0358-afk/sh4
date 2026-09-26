"""일정 문맥 — 휴식·경기 밀도를 분석에 잇는다 (Phase 6-D-9B).

6-D-8 이 **대회를 가로지르는 시간축**(`models.team_timeline`)과 거기서 잰
휴식(`models.rest_context`)을 만들었는데, 그 값이 프로필에만 앉아 있고
`휴식 N일` 한 줄 말고는 아무 데도 닿지 않았다. 이 Phase 가 그것을 분석
결과와 화면·경기자료까지 잇는다.

**지키는 것 셋.**

  · **다시 계산하지 않는다.** `build_rest_days()` 가 이미 부른
    `rest_context()` 의 결과를 읽어 옮길 뿐이다 — 같은 값을 두 번 구하면
    두 경로가 조용히 갈라진다 (§1-8).
  · **경기력 지표가 아니다.** `TeamAnalysis.AXES` 밖이고, 방향이 없고,
    레이더·직접 비교에 올라가지 않으며, 여섯 축에 합산되지 않는다.
  · **대회를 가로질렀다는 사실을 잃지 않는다.** 목요일 UCL 을 뛰고 토요일
    EPL 을 뛰었으면 직전 경기가 **UCL** 이었다는 것이 남아야 한다 —
    `build_rest_days` 가 그 셋을 버리고 있었다.

pytest 없이도 돈다:  python tests/test_schedule_context.py
"""
from __future__ import annotations

import inspect
import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from toto import analysis, analyze, match_material, render     # noqa: E402
from toto.models import (Match, SeasonMatch, TeamAnalysis,     # noqa: E402
                         TeamProfile, TeamRef, rest_context,
                         revive_team_analysis, team_timeline)
from toto.settings import Settings, load_settings              # noqa: E402

UTC = timezone.utc
TEAM = "Arsenal"
OPP = "Milan"
SETTINGS = Settings()


def sm(mid: str, comp: str, when: datetime, *, team: str = TEAM,
       finished: bool = True) -> SeasonMatch:
    return SeasonMatch(
        match_id=mid, competition=comp, kickoff=when, kickoff_aware=True,
        home_team=team, away_team=f"Opp{mid}",
        home_goals=1, away_goals=0, finished=finished)


def match(kickoff_kst: str = "2026-09-19 20:00") -> Match:
    m = Match(no=1, league="epl",
              home=TeamRef(canonical=TEAM, display=TEAM),
              away=TeamRef(canonical=OPP, display=OPP),
              kickoff_kst=kickoff_kst)
    m.home_profile = TeamProfile(team=m.home, league="epl")
    m.away_profile = TeamProfile(team=m.away, league="epl")
    return m


def run(season, kickoff_kst: str = "2026-09-19 20:00") -> Match:
    """실제 실행과 같은 순서 — 휴식을 먼저 재고 축을 붙인다."""
    m = match(kickoff_kst)
    analyze.build_rest_days([m], season)
    analysis.attach_time_context([m], SETTINGS, season)
    return m


def home_axis(m: Match):
    return m.analysis.home.schedule_context


def val(axis, name):
    return axis.value(f"{analysis.SCHEDULE_PERIOD}.{name}") if axis else None


# 목 UCL → 토 EPL. 이 Phase 가 지키려는 바로 그 인접이다.
#   UCL   2026-09-17 19:00 UTC
#   EPL   2026-09-19 11:00 UTC  (= 20:00 KST)   → 40시간
CROSS = [
    sm("1", "epl", datetime(2026, 9, 5, 19, 0, tzinfo=UTC)),
    sm("2", "epl", datetime(2026, 9, 13, 14, 0, tzinfo=UTC)),
    sm("3", "ucl", datetime(2026, 9, 17, 19, 0, tzinfo=UTC)),
]


# ==========================================================================
# A. RestContext 가 손실 없이 전달된다
# ==========================================================================
def test_a1_axis_matches_rest_context_exactly():
    """축의 수는 `rest_context()` 가 준 수와 **정확히 같다.**"""
    m = run(CROSS)
    ctx = rest_context(CROSS, TEAM, analysis.as_of_from_match(m))
    axis = home_axis(m)
    assert val(axis, "rest_hours") == ctx.rest_hours
    assert val(axis, "rest_days") == float(ctx.rest_days)
    for days, count in ctx.window_counts.items():
        assert val(axis, f"matches_last_{days}d") == float(count)


def test_a2_profile_keeps_every_rest_context_field():
    """프로필이 여섯 칸을 다 들고 있다 — 예전에는 셋을 버렸다."""
    m = run(CROSS)
    p = m.home_profile
    ctx = rest_context(CROSS, TEAM, analysis.as_of_from_match(m))
    assert p.rest_hours == ctx.rest_hours
    assert p.rest_days == ctx.rest_days
    assert p.match_density == dict(ctx.window_counts)
    assert p.previous_match_id == ctx.previous_match_id
    assert p.previous_competition == ctx.previous_competition
    assert p.previous_kickoff == ctx.previous_kickoff


def test_a3_no_recomputation_in_the_axis_builder():
    """축은 시간축을 다시 만들지 않는다 (§2)."""
    src = inspect.getsource(analysis.build_schedule_context)
    for word in ("team_timeline", "rest_context", "matches_before",
                 "SeasonMatch"):
        assert word not in src, word
    # 시즌 색인도 기준시각도 받지 않는다 — 받으면 다시 잴 수 있게 된다.
    params = inspect.signature(analysis.build_schedule_context).parameters
    assert list(params) == ["profile"], params


def test_a4_builder_is_not_given_the_season_index():
    src = inspect.getsource(analysis.build_team_analysis)
    assert "build_schedule_context(profile)" in src


def test_a5_units_are_honest():
    """43.5 는 개수가 아니라 시간이다 — 단위를 맞추려고 거짓말하지 않는다."""
    assert analysis.SPECS["rest_hours"][1] == "hours"
    assert analysis.SPECS["rest_days"][1] == "days"
    for n in ("matches_last_7d", "matches_last_10d", "matches_last_14d"):
        assert analysis.SPECS[n][1] == "count"


# ==========================================================================
# B. 대회를 가로지른다 — 직전 경기가 UCL 이었다는 사실이 남는다
# ==========================================================================
def test_b1_previous_match_is_the_ucl_one():
    m = run(CROSS)
    p = m.home_profile
    assert p.previous_competition == "ucl", "대회가 사라졌다"
    assert p.previous_match_id == "3"
    assert p.previous_kickoff == datetime(2026, 9, 17, 19, 0, tzinfo=UTC)


def test_b2_rest_is_measured_across_competitions():
    """같은 리그의 지난 경기가 아니라 **목요일 UCL** 과의 간격이다."""
    m = run(CROSS)
    axis = home_axis(m)
    # 손계산: 2026-09-19 11:00 UTC − 2026-09-17 19:00 UTC = 1일 16시간 = 40h
    assert val(axis, "rest_hours") == 40.0, val(axis, "rest_hours")
    assert val(axis, "rest_days") == 1.0
    # 리그만 보면 직전이 9/13 14:00 UTC 라 5일 21시간(141h)이 나온다 —
    # **그 차이가 이 Phase 가 지키는 것이다.**
    only_epl = [x for x in CROSS if x.competition == "epl"]
    league_only = rest_context(only_epl, TEAM, analysis.as_of_from_match(m))
    assert league_only.rest_hours == 141.0, league_only.rest_hours
    assert league_only.rest_days == 5
    assert league_only.previous_competition == "epl"


def test_b3_competition_appears_in_the_axis_notes():
    axis = home_axis(run(CROSS))
    line = next(n for n in axis.notes if n.startswith("직전 공식 경기"))
    assert "ucl" in line, line
    assert "경기 3" in line, line


def test_b4_no_fatigue_verdict_is_created():
    """대회 종류로 유·불리를 판정하지 않는다 (§9)."""
    src = inspect.getsource(analysis.build_schedule_context)
    for banned in ("continental_fatigue", "fatigue", "advantage",
                   "disadvantage", "congested", "리스크", "불리", "유리하"):
        assert banned not in src, banned
    axis = home_axis(run(CROSS))
    for note in axis.notes:
        assert "불리" not in note or "정하지 않" in note, note


def test_b5_timeline_itself_is_unchanged():
    """6-D-8 의 시간축 정의를 건드리지 않았다."""
    line = team_timeline(CROSS, TEAM)
    assert [x.match_id for x in line] == ["1", "2", "3"]


# ==========================================================================
# C. 밀도 — 창 정의가 6-D-8 그대로다
# ==========================================================================
def test_c1_density_matches_rest_context():
    m = run(CROSS)
    ctx = rest_context(CROSS, TEAM, analysis.as_of_from_match(m))
    assert m.home_profile.match_density == dict(ctx.window_counts)
    assert set(ctx.window_counts) == {7, 10, 14}


def test_c2_window_boundaries_were_not_changed():
    """경계는 양쪽 다 열려 있다 — 정확히 N일 전 경기는 들어가지 않는다."""
    now = datetime(2026, 9, 19, 11, 0, tzinfo=UTC)
    exact = [sm("9", "epl", now - timedelta(days=7))]
    ctx = rest_context(exact, TEAM, now)
    assert ctx.window_counts[7] == 0, "경계 정의가 바뀌었다"
    assert ctx.window_counts[10] == 1


def test_c3_zero_is_a_real_observation():
    """0경기는 **관측값**이다 — 값이 나와야 하고 빈칸이 아니다 (§1-5).

    9/5 한 경기만 있는 팀은 9/19 기준으로 7일·10일 창이 0 이고 14일 창도 0
    이다(9/5 11:00 이 경계라 19:00 은 들어간다 — 아래에서 확인한다).
    """
    old_only = [sm("1", "epl", datetime(2026, 9, 5, 19, 0, tzinfo=UTC))]
    axis = home_axis(run(old_only))
    assert val(axis, "matches_last_7d") == 0.0
    assert val(axis, "matches_last_10d") == 0.0
    assert val(axis, "matches_last_14d") == 1.0
    assert axis.get(f"{analysis.SCHEDULE_PERIOD}.matches_last_7d") is not None


def test_c4_window_names_are_not_hardcoded():
    src = inspect.getsource(analysis.build_schedule_context)
    assert "matches_last_7d" not in src
    assert 'f"matches_last_{int(days)}d"' in src


# ==========================================================================
# D. 없는 것을 0 으로 채우지 않는다
# ==========================================================================
def test_d1_first_match_has_no_rest():
    m = run([])                       # 색인이 없다
    assert m.home_profile.rest_hours is None
    assert m.home_profile.rest_days is None
    assert m.analysis.home.schedule_context is None, "빈 축을 만들었다"


def test_d2_no_previous_match_keeps_none():
    """이 팀의 과거 경기가 없으면 휴식은 `None` 이고 0 이 아니다."""
    future_only = [sm("5", "epl", datetime(2026, 10, 1, 19, 0, tzinfo=UTC))]
    m = run(future_only)
    assert m.home_profile.rest_hours is None
    assert m.home_profile.rest_hours != 0
    axis = home_axis(m)
    # 밀도는 관측됐으므로(시간축에 이 팀이 있다) 축은 만들어진다.
    assert axis is not None
    assert axis.get(f"{analysis.SCHEDULE_PERIOD}.rest_hours") is None
    assert any("찾지 못해" in n for n in axis.notes), axis.notes


def test_d3_unknown_team_makes_no_axis():
    m = run([sm("6", "epl", datetime(2026, 9, 10, 19, 0, tzinfo=UTC),
                team="다른팀")])
    assert m.home_profile.match_density == {}
    assert m.analysis.home.schedule_context is None


def test_d4_render_says_no_data_not_zero():
    axis = analysis.build_schedule_context(_partial_profile())
    cell = render._schedule_cell(axis, "matches_last_7d")
    assert "데이터 없음" in cell, cell
    assert ">0" not in cell


def _partial_profile() -> TeamProfile:
    p = TeamProfile(team=TeamRef(canonical=TEAM, display=TEAM))
    p.rest_hours, p.rest_days = 43.5, 1
    return p                                   # 밀도가 없다


# ==========================================================================
# E. 기존 여섯 축이 바뀌지 않는다
# ==========================================================================
def _six(m: Match) -> str:
    out = {}
    for side in ("home", "away"):
        ta = getattr(m.analysis, side)
        if ta is None:
            continue
        for name in TeamAnalysis.AXES:
            ax = getattr(ta, name)
            if ax is not None:
                out[f"{side}.{name}"] = asdict(ax)
    return json.dumps(out, sort_keys=True, ensure_ascii=False, default=str)


def test_e1_six_axes_do_not_see_schedule_context():
    m = run(CROSS)
    dump = _six(m)
    for word in ("rest_hours", "rest_days", "matches_last",
                 "schedule_context", "match_schedule"):
        assert word not in dump, word


def test_e2_schedule_context_is_not_in_the_axis_registry():
    assert "schedule_context" not in TeamAnalysis.AXES
    assert len(TeamAnalysis.AXES) == 6
    assert TeamAnalysis().computed_axes() == []


def test_e3_adding_rest_does_not_change_the_six_axes():
    """휴식이 있든 없든 여섯 축의 값이 같다."""
    with_rest = run(CROSS)
    m = match()
    analysis.attach_time_context([m], SETTINGS, CROSS)   # 휴식을 재지 않았다
    assert m.home_profile.rest_hours is None
    assert _six(m) == _six(with_rest), "여섯 축이 휴식에 따라 달라졌다"


def test_e4_no_direction_and_no_threshold():
    for name in analysis.SCHEDULE_CONTEXT_SPECS:
        assert analysis.SPECS[name][2] == "", name
        assert name in analysis.UNDIRECTED, name
    axis = home_axis(run(CROSS))
    for metric in axis.metrics.values():
        assert metric.direction == "", metric
        assert metric.group == analysis.SCHEDULE_CONTEXT_GROUP


def test_e5_provenance_is_recorded():
    axis = home_axis(run(CROSS))
    for metric in axis.metrics.values():
        assert metric.source == analysis.SEASON_MATCH_INDEX
        assert metric.measurement_basis == analysis.MATCH_SCHEDULE
        # 표본 수를 지어내지 않는다 — 평균낸 값이 아니다.
        assert metric.sample_count is None, metric


def test_e6_schedule_basis_is_its_own_quantity():
    """일정은 스코어·슛·상대 성적과 **다른 양**이다 — basis 를 나눈다."""
    others = {analysis.FINAL_SCORE, analysis.MATCH_STAT,
              analysis.SHOT_EVENTS, analysis.OPPONENT_SHOT_EVENTS,
              analysis.OPPONENT_RECORD, analysis.POISSON_MODEL}
    assert analysis.MATCH_SCHEDULE not in others
    assert analysis.MATCH_SCHEDULE not in analysis.COMPARABLE_SOURCES


def test_e7_probability_and_pick_are_untouched():
    from toto import predict
    src = inspect.getsource(predict)
    for word in ("rest_hours", "rest_days", "match_density",
                 "schedule_context"):
        assert word not in src, word


# ==========================================================================
# F. 왕복과 화면
# ==========================================================================
def test_f1_artifact_round_trip_keeps_the_axis():
    m = run(CROSS)
    back = revive_team_analysis(asdict(m.analysis.home))
    assert back.schedule_context is not None
    assert (back.schedule_context.metrics.keys()
            == home_axis(m).metrics.keys())
    assert val(back.schedule_context, "rest_hours") == 40.0


def test_f2_old_artifact_has_no_axis_and_does_not_crash():
    """6-D-9B 이전 저장본에는 이 축이 없다 — `None` 으로 되살아난다."""
    body = {"team": TEAM, "time_context": None}
    back = revive_team_analysis(body)
    assert back is not None and back.schedule_context is None
    m = match()
    m.analysis = None
    assert render._schedule_block(m) == ""


def test_f3_block_shows_the_facts():
    html = render._schedule_block(run(CROSS))
    assert "일정 문맥" in html
    assert "40.0시간" in html and "(1일)" in html
    assert "ucl" in html
    assert "유리·불리를 정하지 않았습니다" in html


def test_f4_block_uses_no_new_css():
    html = render._schedule_block(run(CROSS))
    import re
    allowed = {"block", "meta", "tablewrap", "mini", "num", "nodata",
               "lbl", "mnotes"}
    used = set()
    for attr in re.findall(r'class="([^"]+)"', html):
        used |= set(attr.split())
    assert used <= allowed, used - allowed


def test_f5_not_in_direct_comparison_or_radar():
    flat = {n for _a, n in render._DIRECT_ROWS}
    keys = set()
    for spec in load_settings().radar_metrics:
        keys |= {str(spec.get(k, "")) for k in ("key", "home_key", "away_key")}
    for name in analysis.SCHEDULE_CONTEXT_SPECS:
        assert name not in flat, name
        assert name not in keys, name


def test_f6_match_material_carries_the_facts():
    from toto.models import Report
    rep = Report(round_id="X")
    rep.matches = [run(CROSS)]
    md = match_material.build(rep)
    assert "직전 공식 경기 이후 휴식" in md
    assert "40.0시간 (1일)" in md
    assert "최근 7일 공식 경기 수" in md
    assert "ucl" in md


def test_f7_no_recommendation_wording():
    html = render._schedule_block(run(CROSS))
    for banned in ("추천", "유력", "확신도", "우위", "홈승", "원정승"):
        assert banned not in html, banned


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
