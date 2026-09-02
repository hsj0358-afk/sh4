"""상대 강도 회귀 테스트 (Phase 2-F · Strength of Schedule).

고정하려는 것은 다섯 가지다.

1. **self-exclusion.** 상대의 성적에서 이 팀과의 경기를 뺀다. 빼지 않으면
   "우리가 그 상대를 이겼다" 가 그 상대의 강도로 들어가고, 그 강도로 다시
   우리 성과를 설명하는 순환이 생긴다.
2. **시점은 그 경기 이전.** cutoff 는 `matches_before` 하나뿐이고 현재
   순위표 스냅샷을 값으로 쓰지 않는다.
3. **상대 연결은 숫자 teamId.** 팀명 문자열로 찾지 않는다.
4. **단일 점수를 만들지 않는다.** 관찰값과 표본만 둔다.
5. **피지표를 만들지 않는다.** "상대가 강해서 허용했다" 와 "수비가 나쁘다"
   를 갈라 두기 위해 2-C 의 지표를 이 축에 두지 않는다.

pytest 없이도 돈다:  python tests/test_schedule_strength.py
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

from toto import analysis, shots                              # noqa: E402
from toto.models import (DERIVED, OBSERVED, MatchAnalysis,    # noqa: E402
                         SeasonMatch, TeamProfile, TeamRef, TeamStats,
                         revive_match_analysis)
from toto.settings import Settings                            # noqa: E402

UTC = timezone.utc
US, A, B, C = 1, 2, 3, 4
NAME = {US: "US", A: "A", B: "B", C: "C"}
WINDOWS = [6, 3]
OPEN = {"min_sample": 1, "opponent_min_matches": 1, "thresholds": {}}
UP = Path("/root/.claude/uploads/4f45b11b-6ed2-571d-8e30-3901a62afd1b")


def kick(day: int) -> datetime:
    return datetime(2026, 4, day, 20, 0, tzinfo=UTC)


def sm(mid, day, home, away, hg, ag, *, finished=True,
       competition="epl") -> SeasonMatch:
    return SeasonMatch(match_id=mid, competition=competition,
                       kickoff=kick(day), kickoff_aware=True,
                       home_team=NAME[home], away_team=NAME[away],
                       home_fotmob_id=home, away_fotmob_id=away,
                       home_goals=hg, away_goals=ag, finished=finished)


def profile(team_id=US, st=None) -> TeamProfile:
    p = TeamProfile(team=TeamRef(canonical=NAME[team_id],
                                 fotmob_id=str(team_id)), league="epl")
    p.stats = st if st is not None else TeamStats()
    return p


def build(season, *, team=US, as_of=kick(30), venue=analysis.HOME,
          cfg=None, quality=None, windows=None, prof=None):
    return analysis.build_schedule_strength(
        prof if prof is not None else profile(team), NAME[team], season,
        as_of, windows if windows is not None else WINDOWS, venue=venue,
        config=cfg or OPEN, quality=quality)


# 기본 픽스처. A 는 US 를 4-0 으로 이겼고 B 에게 두 번 졌다.
#   US 와의 경기를 빼면 A 는 2패 · 승점 0.0 · 득실 -1.5
#   빼지 않으면            1승2패 · 승점 1.0 · 득실  0.0
BASE = [sm("m1", 1, A, US, 4, 0),
        sm("m2", 2, A, B, 0, 1),
        sm("m3", 3, B, A, 2, 0),
        sm("m4", 10, US, A, 1, 1)]


# --------------------------------------------------------------------------
# 1. self-exclusion — 이 축의 핵심
# --------------------------------------------------------------------------
def test_1_self_exclusion_hand_check():
    axis = build(BASE)
    assert axis.value("recent6.opponent_points") == 0.0, \
        "US 와의 경기(A 4-0 US)가 A 의 강도에 섞였다"
    assert abs(axis.value("recent6.opponent_goal_diff") - (-1.5)) < 1e-12


def test_1_without_exclusion_the_number_would_differ():
    """빼지 않았다면 승점 1.0 · 득실 0.0 이 나온다 — 그게 아님을 고정한다."""
    axis = build(BASE)
    assert axis.value("recent6.opponent_points") != 1.0
    assert axis.value("recent6.opponent_goal_diff") != 0.0


def test_1_exclusion_is_by_id_not_name():
    """이름이 달라도 숫자 ID 가 같으면 우리 경기로 보고 뺀다."""
    rows = [sm("m1", 1, A, US, 4, 0), sm("m2", 2, A, B, 0, 1),
            sm("m3", 3, B, A, 2, 0), sm("m4", 10, US, A, 1, 1)]
    rows[0].home_team = "A"           # 상대 이름은 그대로
    rows[0].away_team = "다른표기"      # 우리 이름만 다르게 표기됨
    axis = build(rows)
    assert axis.value("recent6.opponent_points") == 0.0, \
        "숫자 ID 로 우리 경기를 알아보지 못했다"


def test_1_opponent_record_direct():
    got = analysis.opponent_record(BASE, "A", A, kick(10), "US", US)
    assert got is not None
    points, gd, n = got
    assert n == 2, "US 와의 경기를 빼면 2경기"
    assert points == 0.0 and abs(gd - (-1.5)) < 1e-12
    # 빼지 않으면(없는 팀을 제외 대상으로 주면) 3경기가 된다
    other = analysis.opponent_record(BASE, "A", A, kick(10), "없는팀", 99)
    assert other[2] == 3 and other[0] == 1.0


# --------------------------------------------------------------------------
# 2. 시점
# --------------------------------------------------------------------------
def test_2_only_matches_before_the_fixture_count():
    """m4(10일) 의 상대 강도에 m4 이후 경기가 섞이지 않는다."""
    rows = BASE + [sm("m5", 20, A, C, 9, 0)]     # A 의 대승, m4 뒤
    axis = build(rows)
    assert axis.value("recent6.opponent_points") == 0.0, "미래가 섞였다"


def test_2_cutoff_is_matches_before_only():
    node = ast.parse(
        inspect.getsource(analysis.opponent_record).lstrip()).body[0]
    calls = {getattr(n.func, "id", "") for n in ast.walk(node)
             if isinstance(n, ast.Call)}
    assert "matches_before" in calls
    compares = [n for n in ast.walk(node) if isinstance(n, ast.Compare)
                and any(isinstance(x, ast.Attribute) and x.attr == "kickoff"
                        for x in ast.walk(n))]
    assert not compares, "kickoff 을 직접 비교하는 두 번째 cutoff"


def test_2_as_of_none_gives_nothing():
    axis = build(BASE, as_of=None)
    assert not [k for k in axis.metrics if k.startswith("recent")]


def test_2_unfinished_opponent_match_is_not_counted():
    rows = [sm("m1", 1, A, B, 0, 1), sm("m2", 2, B, A, 2, 0, finished=False),
            sm("m3", 10, US, A, 1, 1)]
    got = analysis.opponent_record(rows, "A", A, kick(10), "US", US)
    assert got[2] == 1, "미종료 경기를 셌다"


def test_2_snapshot_rank_is_never_used():
    """순위표 스냅샷(rank·points)이 값에 섞이지 않는다."""
    st = TeamStats(played=38, points=99, rank=1)
    axis = build(BASE, prof=profile(US, st))
    assert axis.value("recent6.opponent_points") == 0.0
    src = inspect.getsource(analysis.build_schedule_strength) \
        + inspect.getsource(analysis._sos_values) \
        + inspect.getsource(analysis.opponent_record)
    for banned in (".rank", "standings", "STANDINGS"):
        assert banned not in src, banned


# --------------------------------------------------------------------------
# 3. 상대 연결
# --------------------------------------------------------------------------
def test_3_opponent_lookup():
    m = sm("m1", 1, US, A, 1, 0)
    assert analysis.opponent_in(m, "US") == "A"
    assert analysis.opponent_id_in(m, "US") == A
    assert analysis.opponent_in(m, "A") == "US"
    assert analysis.opponent_id_in(m, "A") == US
    assert analysis.opponent_in(m, "모르는팀") == ""
    assert analysis.opponent_id_in(m, "모르는팀") is None


def test_3_unknown_opponent_leaves_a_reason():
    rows = [SeasonMatch(match_id="m1", competition="epl", kickoff=kick(1),
                        kickoff_aware=True, home_team="US", away_team="",
                        home_fotmob_id=US, away_fotmob_id=None,
                        home_goals=1, away_goals=0, finished=True)]
    q = analysis.DataQuality()
    axis = build(rows, quality=q)
    assert axis.get("recent6.opponent_points") is None
    assert any("값 없음" in n for n in axis.notes), axis.notes


# --------------------------------------------------------------------------
# 4. 표본
# --------------------------------------------------------------------------
def test_4_thin_opponent_is_dropped():
    """상대의 이전 경기가 기준 미만이면 그 경기를 표본에서 뺀다."""
    cfg = {"min_sample": 1, "opponent_min_matches": 3, "thresholds": {}}
    axis = build(BASE, cfg=cfg)
    assert axis.get("recent6.opponent_points") is None, \
        "A 는 이전 2경기뿐인데 기준 3을 통과했다"
    assert any("값 없음" in n for n in axis.notes)


def test_4_resolved_reports_coverage():
    axis = build(BASE)
    m = axis.get("season.opponent_resolved")
    assert m.value == 1.0, "강도를 만든 경기는 m4 하나"
    assert m.sample_count == 2, "US 의 과거 경기는 m1·m4 둘"
    assert "1/2경기" in m.note and "제외" in m.note
    assert m.provenance == DERIVED


def test_4_reason_is_written_once_not_on_every_metric():
    """제외 사유는 한 지표에만 적는다 — 같은 말을 세 번 세지 않는다."""
    axis = build(BASE)
    carrying = [k for k, m in axis.metrics.items()
                if k.startswith("season.") and "제외" in m.note]
    assert carrying == ["season.opponent_resolved"], carrying


def test_4_min_sample_blocks_the_period():
    cfg = {"min_sample": 3, "opponent_min_matches": 1, "thresholds": {}}
    q = analysis.DataQuality()
    axis = build(BASE, cfg=cfg, quality=q)
    assert axis.get("recent6.opponent_points") is None
    assert axis.get("recent6.opponent_resolved") is None
    assert "표본 부족" in q.axes["schedule_strength.recent6"]["degraded_reason"]


def test_4_sample_counts_are_separate():
    q = analysis.DataQuality()
    axis = build(BASE, quality=q, windows=[6])
    entry = q.axes["schedule_strength.recent6"]
    assert entry["requested"] == 6
    assert entry["available_matches"] == 2, "US 의 과거 경기 수"
    assert axis.get("recent6.opponent_points").sample_count == 1


def test_4_none_is_not_zero():
    axis = build([], as_of=kick(30))
    assert axis.get("recent6.opponent_points") is None
    assert axis.value("recent6.opponent_points") != 0.0


# --------------------------------------------------------------------------
# 5. 기간 · 장소
# --------------------------------------------------------------------------
def test_5_venue_split_matches_2e_definition():
    """장소 구간은 2-E 와 같은 경기 집합이다 — 최근 N경기 중 그 장소."""
    rows = [sm("m1", 1, A, B, 0, 1), sm("m2", 2, B, A, 2, 0),
            sm("m3", 5, US, A, 1, 0),      # 홈
            sm("m4", 6, A, US, 0, 1)]      # 원정
    q = analysis.DataQuality()
    axis = build(rows, quality=q)
    assert q.axes["schedule_strength.recent6"]["available_matches"] == 2
    assert q.axes["schedule_strength.home6"]["available_matches"] == 1
    assert any("최근 6경기 중 1경기가 홈" in n for n in axis.notes), axis.notes
    q2 = analysis.DataQuality()
    away = build(rows, venue=analysis.AWAY, quality=q2)
    assert q2.axes["schedule_strength.away6"]["available_matches"] == 1
    assert "home6" not in {k.split(".")[0] for k in away.metrics}


def test_5_venue_unknown_still_builds_overall():
    axis = build(BASE, venue=None)
    assert axis.get("recent6.opponent_points") is not None
    assert not [k for k in axis.metrics
                if k.startswith(("home", "away"))]


def test_5_windows_come_from_settings():
    axis = build(BASE, windows=[5])
    periods = {k.split(".")[0] for k in axis.metrics}
    assert "recent5" in periods and "recent6" not in periods


def test_5_period_labels_reuse_existing():
    assert analysis.period_label("recent6") == "최근 6경기"
    assert analysis.period_label("home6") == "최근 6경기 중 홈"
    assert analysis.period_label(analysis.SEASON) == "시즌"


# --------------------------------------------------------------------------
# 6. 다른 competition
# --------------------------------------------------------------------------
def test_6_other_competition_is_not_mixed():
    """색인은 리그 피드에서만 만들어지지만, 섞여 들어와도 구분된다."""
    rows = [sm("m1", 1, A, B, 0, 1, competition="epl"),
            sm("m2", 2, B, A, 2, 0, competition="epl"),
            sm("m3", 10, US, A, 1, 1, competition="epl")]
    cup = rows + [sm("m9", 3, A, C, 5, 0, competition="cup")]
    plain = analysis.opponent_record(rows, "A", A, kick(10), "US", US)
    mixed = analysis.opponent_record(cup, "A", A, kick(10), "US", US)
    assert plain[2] == 2
    assert mixed[2] == 3, "지금은 색인에 실린 경기를 전부 센다"
    # 리그를 걸러 넘기면 컵 경기가 빠진다 (호출부 책임)
    league_only = [m for m in cup if m.competition == "epl"]
    assert analysis.opponent_record(
        league_only, "A", A, kick(10), "US", US)[2] == 2


# --------------------------------------------------------------------------
# 7. 하지 않는 것
# --------------------------------------------------------------------------
def test_7_no_single_score():
    src = (inspect.getsource(analysis.build_schedule_strength)
           + inspect.getsource(analysis._sos_values)
           + inspect.getsource(analysis.opponent_record))
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    for banned in ("sos_score", "strength_score", "schedule_score",
                   "adjusted_", "difficulty_score", "final_pick",
                   "recommended_pick", "recommendation"):
        assert banned not in code, banned
    for name in analysis.SPECS:
        assert not name.endswith("_score"), name


def test_7_no_defensive_metrics_in_this_axis():
    """2-C 와 갈라 둔다 — '상대가 강했다' 와 '수비가 나쁘다' 는 다른 말이다."""
    axis = build(BASE)
    for key in axis.metrics:
        name = key.split(".", 1)[1]
        assert "against" not in name, key
        assert name not in ("npxga", "xga", "shots_against"), key


def test_7_no_correction_of_our_own_performance():
    """성과를 강도로 나누거나 곱하지 않는다."""
    axis = build(BASE)
    for key in axis.metrics:
        name = key.split(".", 1)[1]
        assert name.startswith("opponent_"), f"우리 성과 지표가 섞였다: {key}"


def test_7_no_recursive_opponent_of_opponent():
    src = inspect.getsource(analysis.opponent_record)
    assert "opponent_record(" not in src.split("\n", 1)[1], "재귀 가중"


def test_7_no_language_of_judgement():
    axis = build(BASE)
    body = [n for n in axis.notes if n not in analysis.SOS_DISCLAIMERS]
    assert len(body) < len(axis.notes), "고정 문구가 붙어 있어야 한다"
    text = " ".join(body) + " ".join(
        m.note + m.label for m in axis.metrics.values())
    for word in ("강한 일정", "약한 일정", "유리", "불리", "과대", "과소",
                 "추천", "픽", "승리 확률", "강팀", "약팀"):
        assert word not in text, f"{word} in output"


def test_7_thresholds_are_empty_by_default():
    """실물 분산을 관측하지 못해 문턱을 비워 두었다 — 임의값을 넣지 않는다."""
    cfg = analysis.schedule_strength_config(Settings())
    assert cfg["thresholds"] == {}
    assert cfg["min_sample"] >= 1 and cfg["opponent_min_matches"] >= 1


def test_7_config_overrides_are_read():
    s = Settings(analysis={"schedule_strength": {
        "min_sample": 5, "opponent_min_matches": 4,
        "thresholds": {"x": 1.5}}})
    cfg = analysis.schedule_strength_config(s)
    assert cfg["min_sample"] == 5 and cfg["opponent_min_matches"] == 4
    assert cfg["thresholds"]["x"] == 1.5


# --------------------------------------------------------------------------
# 8. 메타데이터 · 직렬화
# --------------------------------------------------------------------------
def test_8_source_and_basis():
    axis = build(BASE)
    for key, m in axis.metrics.items():
        assert m.source == analysis.SEASON_MATCH_INDEX, key
        assert m.measurement_basis == analysis.OPPONENT_RECORD, key
        assert m.group == analysis.SCHEDULE_GROUP, key
        assert m.direction == "", f"{key} 에 방향을 정했다"


def test_8_basis_is_distinct_from_our_own_final_score():
    """우리 승점과 상대 승점이 같은 basis 면 문이 둘을 빼는 것을 못 막는다."""
    assert analysis.OPPONENT_RECORD != analysis.FINAL_SCORE
    ours = analysis.Metric(name="points", value=1.5, period="recent6",
                           sample_count=6,
                           source=analysis.SEASON_MATCH_INDEX,
                           measurement_basis=analysis.FINAL_SCORE)
    theirs = analysis.Metric(name="opponent_points", value=1.8,
                             period="recent6", sample_count=6,
                             source=analysis.SEASON_MATCH_INDEX,
                             measurement_basis=analysis.OPPONENT_RECORD)
    ok, code, _r = analysis.comparison_allowed(
        ours, theirs, common_sample=6, min_sample=3)
    assert ok is False and code == analysis.BLOCK_BASIS
    ok2, code2, _r2 = analysis.comparison_allowed(
        ours, theirs, common_sample=6, min_sample=3,
        relation=analysis.SUBSET)
    assert ok2 is False and code2 in (analysis.BLOCK_METRIC,
                                      analysis.BLOCK_BASIS)


def test_8_group_does_not_collide_with_existing():
    assert analysis.SCHEDULE_GROUP not in (
        analysis.VOLUME, analysis.CHANCE_CREATION, analysis.EXECUTION,
        analysis.GAP, analysis.OUTCOME, analysis.RESULT_GROUP,
        analysis.DEF_VOLUME, analysis.DEF_QUALITY, analysis.DEF_EXECUTION,
        analysis.DEF_GAP, analysis.DEF_OUTCOME, analysis.MODEL_GROUP,
        analysis.VENUE_GAP_GROUP)


def test_8_serialization_round_trip():
    ta = analysis.TeamAnalysis(team="US", is_home=True)
    ta.schedule_strength = build(BASE)
    raw = asdict(MatchAnalysis(home=ta))
    back = revive_match_analysis(json.loads(json.dumps(raw, default=str)))
    axis = back.home.schedule_strength
    assert axis.value("recent6.opponent_points") == 0.0
    assert axis.get("recent6.opponent_points").measurement_basis == \
        analysis.OPPONENT_RECORD
    assert axis.notes == ta.schedule_strength.notes


def test_8_degraded_reason_survives_serialization():
    cfg = {"min_sample": 3, "opponent_min_matches": 1, "thresholds": {}}
    q = analysis.DataQuality()
    ta = analysis.TeamAnalysis(team="US", is_home=True, data_quality=q)
    ta.schedule_strength = build(BASE, cfg=cfg, quality=q)
    raw = asdict(MatchAnalysis(home=ta))
    back = revive_match_analysis(json.loads(json.dumps(raw, default=str)))
    entry = back.home.data_quality.axes["schedule_strength.recent6"]
    assert "표본 부족" in entry["degraded_reason"]
    assert any("값 없음" in n for n in back.home.schedule_strength.notes)


# --------------------------------------------------------------------------
# 9. 연결 · 확률 격리
# --------------------------------------------------------------------------
def test_9_team_analysis_integration():
    s = Settings(fotmob={"shot_recent_windows": [6, 3],
                         "match_detail_matches": 6})
    ta = analysis.build_team_analysis(
        profile(US), "US", BASE, kick(30), s, is_home=True)
    assert ta.schedule_strength is not None
    assert ta.computed_axes() == ["time_context", "chance_quality",
                                  "defensive_quality", "sustainability",
                                  "venue_context", "schedule_strength"]
    assert "schedule_strength.recent6" in ta.data_quality.axes


def test_9_built_even_when_side_unknown():
    s = Settings(fotmob={"shot_recent_windows": [6, 3]})
    ta = analysis.build_team_analysis(
        profile(US), "US", BASE, kick(30), s, is_home=None)
    assert ta.venue_context is None, "장소를 모르면 2-E 는 만들지 않는다"
    assert ta.schedule_strength is not None, "2-F 는 장소와 무관하다"


def test_9_probability_isolation():
    for fn in (analysis.build_schedule_strength, analysis._sos_values,
               analysis.opponent_record):
        node = ast.parse(inspect.getsource(fn).lstrip()).body[0]
        banned = {"predict", "probs", "MatchProb", "odds",
                  "additive_probabilities"}
        for n in ast.walk(node):
            if isinstance(n, ast.Name):
                assert n.id not in banned, f"{fn.__name__}: {n.id}"
            if isinstance(n, ast.Attribute):
                assert n.attr not in banned, f"{fn.__name__}: .{n.attr}"


def test_9_run_all_leaves_probs_and_odds_untouched():
    from toto import fixtures
    from toto.analyze import run_all
    s = Settings(fotmob={"shot_recent_windows": [6, 3],
                         "match_detail_matches": 6})
    matches = fixtures.build_demo_matches()
    run_all(matches, s, season_matches=[])
    before = [(m.odds.home, m.odds.draw, m.odds.away) for m in matches]
    probs = [m.probs.as_tuple if m.probs else None for m in matches]
    assert any(p is not None for p in probs)
    run_all(matches, s, season_matches=[])
    assert [(m.odds.home, m.odds.draw, m.odds.away)
            for m in matches] == before
    assert [m.probs.as_tuple if m.probs else None for m in matches] == probs


# --------------------------------------------------------------------------
# 10. 실물 260048
# --------------------------------------------------------------------------
def _real_row():
    payload = json.loads((UP / "da0dcdd0-match_5795372.json").read_text())
    events = [shots.ShotEvent(**d) for d in payload["shots"]]
    hid, aid = payload["team_ids"]["home"], payload["team_ids"]["away"]
    goals = {hid: 0, aid: 0}
    for e in events:
        if e.event_type == "Goal" and not e.is_own_goal:
            goals[e.team_id] += 1
    return SeasonMatch(
        match_id="5795372", competition="epl",
        kickoff=datetime(2026, 8, 23, 20, 0, tzinfo=analysis.KST),
        kickoff_aware=True, home_team="Fulham", away_team="Chelsea",
        home_fotmob_id=hid, away_fotmob_id=aid,
        home_goals=goals[hid], away_goals=goals[aid], finished=True), hid, aid


def test_10_real_260048_has_no_opponent_history():
    """실물 캐시는 팀당 과거 1경기뿐 — 상대 강도가 만들어지지 않는 게 정답."""
    if not UP.exists():
        return
    row, hid, aid = _real_row()
    as_of = datetime(2026, 8, 29, 20, 0, tzinfo=analysis.KST)
    p = TeamProfile(team=TeamRef(canonical="Fulham", fotmob_id=str(hid)))
    p.stats = TeamStats()
    axis = analysis.build_schedule_strength(
        p, "Fulham", [row], as_of, [6], venue=analysis.HOME, config=OPEN)
    assert axis.get("recent6.opponent_points") is None, \
        "상대(첼시)의 이전 경기가 없는데 값을 만들었다"
    assert any("값 없음" in n for n in axis.notes), axis.notes
    # 억지로 0 을 만들지 않는다
    assert axis.value("recent6.opponent_points") != 0.0


def test_10_real_opponent_is_linked_by_id():
    if not UP.exists():
        return
    row, hid, aid = _real_row()
    assert analysis.opponent_id_in(row, "Fulham") == aid
    assert analysis.opponent_id_in(row, "Chelsea") == hid
    assert analysis.opponent_in(row, "Fulham") == "Chelsea"


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
