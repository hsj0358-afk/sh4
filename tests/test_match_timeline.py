"""팀 경기 시간축과 휴식 계산 회귀 테스트 (Phase 6-D-8).

**묻는 것은 하나다 — 이 팀이 마지막으로 뛴 것이 언제인가.**

예전 구현은 세 군데에서 틀렸다.

```python
kickoff = _parse_date(match.kickoff_kst.split(" ")[0])   # ① 시각을 버린다
last    = _parse_date(profile.form[0].date)              # ② 한 리그의 폼
delta   = (kickoff - last).days                          # ③ 달력 뺄셈
```

②가 이 Phase 의 핵심이다 — 목요일 UCL 을 치르고 토요일 EPL 을 뛴 팀의
'직전 경기' 가 **지난 주 EPL** 로 잡혔다. 폼은 `read_league` 가 받은 한
리그의 경기로만 만들어지기 때문이다.

실물로도 확인됐다 (260052 · 엘체):

```
직전 경기  2026-09-07 19:30 UTC = 2026-09-08 04:30 KST
현재 경기  2026-09-13 01:30 KST
실제 간격  4일 21시간 → 4일        옛 계산  09-13 − 09-07 = 6일
```

pytest 없이도 돈다:  python tests/test_match_timeline.py
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from toto import analysis, analyze, models                    # noqa: E402
from toto.models import (KST, REST_WINDOW_DAYS, Match,        # noqa: E402
                         SeasonMatch, TeamProfile, TeamRef,
                         in_competition, in_kst, rest_context,
                         team_timeline)
from toto.settings import Settings                            # noqa: E402

UTC = timezone.utc
TEAM = "Liverpool"


def sm(mid, when, competition, *, home=TEAM, away="Milan",
       finished=True, tz=KST):
    """시간축 한 건. `when` 은 `(월, 일, 시, 분)`."""
    month, day, hour, minute = when
    return SeasonMatch(
        match_id=str(mid), competition=competition,
        home_team=home, away_team=away,
        home_goals=1 if finished else None,
        away_goals=0 if finished else None,
        finished=finished,
        kickoff=datetime(2026, month, day, hour, minute, tzinfo=tz),
        kickoff_aware=True)


def at(month, day, hour=18, minute=0, tz=KST):
    return datetime(2026, month, day, hour, minute, tzinfo=tz)


def ids(rows) -> list[str]:
    return [str(m.match_id) for m in rows]


# ==========================================================================
# A. 시간축 정렬 (§14-A)
# ==========================================================================
SHUFFLED = [sm(3, (9, 16, 21, 0), "epl"),
            sm(1, (9, 10, 21, 0), "epl"),
            sm(2, (9, 13, 19, 0), "ucl")]


def test_a1_timeline_is_chronological():
    assert ids(team_timeline(SHUFFLED, TEAM)) == ["1", "2", "3"]


def test_a2_input_order_does_not_matter():
    a = ids(team_timeline(SHUFFLED, TEAM))
    b = ids(team_timeline(list(reversed(SHUFFLED)), TEAM))
    c = ids(team_timeline(sorted(SHUFFLED, key=lambda m: m.match_id), TEAM))
    assert a == b == c


def test_a3_same_kickoff_orders_by_match_id():
    same = [sm("b", (9, 10, 21, 0), "epl"), sm("a", (9, 10, 21, 0), "ucl")]
    assert ids(team_timeline(same, TEAM)) == ["a", "b"]
    assert ids(team_timeline(list(reversed(same)), TEAM)) == ["a", "b"]


def test_a4_other_teams_are_not_in_this_timeline():
    pool = SHUFFLED + [sm(9, (9, 11, 20, 0), "epl", home="Arsenal",
                          away="Chelsea")]
    assert "9" not in ids(team_timeline(pool, TEAM))


def test_a5_timeline_reuses_the_project_sort_key():
    """정렬 규칙을 여기서 다시 적지 않는다 (§1-8)."""
    src = inspect.getsource(models.team_timeline)
    assert "sort_key" in src
    assert "kickoff <" not in src and "kickoff >" not in src


# ==========================================================================
# B. 대회를 가로지른다 (§14-B)
# ==========================================================================
CROSS = [sm(1, (9, 10, 21, 0), "epl"),
         sm(2, (9, 13, 19, 0), "ucl"),
         sm(3, (9, 16, 21, 0), "epl")]


def test_b1_one_timeline_across_competitions():
    assert ids(team_timeline(CROSS, TEAM)) == ["1", "2", "3"]
    assert {m.competition for m in team_timeline(CROSS, TEAM)} == {"epl", "ucl"}


def test_b2_uel_and_conference_join_the_same_timeline():
    pool = CROSS + [sm(4, (9, 11, 20, 0), "uel"),
                    sm(5, (9, 12, 20, 0), "conference")]
    got = team_timeline(pool, TEAM)
    assert ids(got) == ["1", "4", "5", "2", "3"]
    assert {m.competition for m in got} == {
        "epl", "ucl", "uel", "conference"}


def test_b3_a_single_competition_can_still_be_asked_for():
    assert ids(team_timeline(CROSS, TEAM, competition="epl")) == ["1", "3"]


# ==========================================================================
# C. 시간축은 문맥이고 모집단이 아니다 (§14-C · §22-6)
# ==========================================================================
def test_c1_timeline_does_not_widen_the_analysis_population():
    """EPL 분석의 모집단이 UCL 을 포함하도록 바뀌지 않는다."""
    assert len(in_competition(CROSS, "epl")) == 2
    assert len(team_timeline(CROSS, TEAM)) == 3


def test_c2_domestic_axes_are_unchanged_by_continental_matches():
    def axes(season):
        m = Match(no=1, league="epl",
                  home=TeamRef(canonical=TEAM, display=TEAM),
                  away=TeamRef(canonical="Milan", display="Milan"),
                  kickoff_kst="2026-09-20 20:00")
        m.home_profile = TeamProfile(team=m.home)
        m.away_profile = TeamProfile(team=m.away)
        analysis.attach_time_context([m], Settings(), season)
        return json.dumps(asdict(m.analysis), sort_keys=True,
                          ensure_ascii=False, default=str)

    only_epl = [m for m in CROSS if m.competition == "epl"]
    assert axes(only_epl) == axes(CROSS)


def test_c3_rest_does_not_touch_the_analysis_axes():
    src = inspect.getsource(analyze.build_rest_days)
    for banned in ("analysis", "time_context", "attach_time_context"):
        assert banned not in src, banned


# ==========================================================================
# D·E. 대회를 가로지르는 직전 경기 — 이 Phase 의 핵심 (§14-D·E · §16)
# ==========================================================================
def test_d1_thursday_ucl_is_the_previous_match_of_saturday_epl():
    """§16 의 예시 그대로 — 목 UCL → 토 EPL."""
    season = [sm(1, (9, 10, 20, 0), "ucl")]
    ctx = rest_context(season, TEAM, at(9, 13, 18, 30))
    assert ctx.previous_match_id == "1"
    assert ctx.previous_competition == "ucl"


def test_d2_the_old_same_league_answer_would_have_been_different():
    """EPL 만 보면 지난 주 EPL 이 직전 경기가 된다 — 그게 고친 결함이다."""
    season = [sm("epl_old", (9, 6, 20, 0), "epl"),
              sm("ucl_new", (9, 10, 20, 0), "ucl")]
    now = at(9, 13, 18, 30)
    assert rest_context(season, TEAM, now).previous_match_id == "ucl_new"
    # 옛 동작을 재현하면(리그로 좁히면) 다른 답이 나온다
    assert rest_context(season, TEAM, now,
                        competition="epl").previous_match_id == "epl_old"


def test_e1_previous_is_the_thursday_ucl_not_the_monday_epl():
    """월 EPL → 목 UCL → 토 EPL 에서 토요일의 직전은 **목 UCL**."""
    ctx = rest_context(CROSS, TEAM, at(9, 19, 21, 0))
    assert ctx.previous_match_id == "3"          # 9/16 EPL
    ctx2 = rest_context(CROSS, TEAM, at(9, 16, 21, 0))
    assert ctx2.previous_match_id == "2"         # 9/13 UCL
    assert ctx2.previous_competition == "ucl"


def test_e2_uel_can_also_be_the_previous_match():
    season = [sm(1, (9, 10, 20, 0), "epl"), sm(2, (9, 12, 20, 0), "uel")]
    assert rest_context(season, TEAM, at(9, 14, 20, 0)).previous_competition \
        == "uel"


# ==========================================================================
# F·G. 실제 시간 차이 (§14-F·G · §22-1·5)
# ==========================================================================
def test_f1_two_hours_across_midnight():
    """월 23:00 → 화 01:00 은 **2시간**이지 1일이 아니다."""
    season = [sm(1, (9, 14, 23, 0), "epl")]
    ctx = rest_context(season, TEAM, at(9, 15, 1, 0))
    assert ctx.rest_hours == 2.0
    assert ctx.rest_days == 0


def test_f2_rest_days_is_the_floor_of_the_real_gap():
    season = [sm(1, (9, 10, 20, 0), "ucl")]
    ctx = rest_context(season, TEAM, at(9, 13, 18, 30))
    assert abs(ctx.rest_hours - 70.5) < 1e-9
    assert ctx.rest_days == 2                    # 70.5h = 2.9375일


def test_f3_rest_hours_is_not_derived_from_rest_days():
    """`rest_hours = rest_days * 24` 가 아니다 (§22-5)."""
    season = [sm(1, (9, 10, 20, 0), "epl")]
    ctx = rest_context(season, TEAM, at(9, 13, 18, 30))
    assert ctx.rest_hours != ctx.rest_days * 24


def test_g1_utc_and_kst_are_compared_on_one_basis():
    """소스는 UTC, 회차는 KST — 표기가 달라도 같은 순간이면 같은 값이다."""
    utc_side = [sm(1, (9, 10, 11, 0), "epl", tz=UTC)]     # = 9/10 20:00 KST
    kst_side = [sm(1, (9, 10, 20, 0), "epl", tz=KST)]
    now = at(9, 13, 18, 30)
    a = rest_context(utc_side, TEAM, now)
    b = rest_context(kst_side, TEAM, now)
    assert a.rest_hours == b.rest_hours == 70.5


def test_g2_a_date_boundary_does_not_inflate_the_gap():
    """실물 260052 엘체 사례 — UTC 날짜로 재면 2일이 더 붙는다."""
    season = [sm(1, (9, 7, 19, 30), "laliga", tz=UTC)]   # = 9/8 04:30 KST
    ctx = rest_context(season, TEAM, at(9, 13, 1, 30))
    assert ctx.rest_hours == 117.0
    assert ctx.rest_days == 4
    # 달력으로 재면 09-13 − 09-07 = 6 이 나온다. 그 값이 아니어야 한다.
    assert ctx.rest_days != 6


def test_g3_no_calendar_subtraction_survives_in_the_code():
    for fn in (models.rest_context, analyze.build_rest_days):
        code = inspect.getsource(fn)
        body = code[code.index('"""', code.index('"""') + 3) + 3:]
        assert ".days" not in body, fn.__name__
        assert ".date()" not in body, fn.__name__


# ==========================================================================
# H·I. 없는 것과 미래 (§14-H·I · §22-4)
# ==========================================================================
def test_h1_first_match_has_no_rest():
    ctx = rest_context([], TEAM, at(9, 13))
    assert ctx.rest_hours is None
    assert ctx.rest_days is None
    assert ctx.previous_match_id == ""


def test_h2_none_is_not_zero():
    ctx = rest_context([], TEAM, at(9, 13))
    assert ctx.rest_days is not 0            # noqa: F632 — 0 과 None 을 가른다
    assert ctx.rest_days is None


def test_h3_unknown_kickoff_yields_nothing():
    assert rest_context(CROSS, TEAM, None).rest_days is None


def test_i1_future_matches_are_never_the_previous_match():
    season = [sm(1, (9, 10, 20, 0), "epl"), sm(9, (9, 20, 20, 0), "ucl")]
    assert rest_context(season, TEAM, at(9, 13)).previous_match_id == "1"


def test_i2_a_match_at_the_same_kickoff_is_not_previous():
    """같은 시각 경기는 선후를 알 수 없다 — 엄격한 `<` (§1-1-4)."""
    now = at(9, 13, 18, 30)
    season = [sm(1, (9, 13, 18, 30), "epl")]
    assert rest_context(season, TEAM, now).previous_match_id == ""


def test_i3_only_past_matches_count_in_the_windows():
    season = [sm(1, (9, 10, 20, 0), "epl"), sm(9, (9, 14, 20, 0), "ucl")]
    ctx = rest_context(season, TEAM, at(9, 13))
    assert ctx.window_counts[7] == 1


# ==========================================================================
# J·K·M·N. 식별과 결측 (§14-J·K·M·N)
# ==========================================================================
def test_j1_duplicate_match_id_appears_once():
    dup = [sm(1, (9, 10, 20, 0), "epl"), sm(1, (9, 10, 20, 0), "ucl")]
    assert ids(team_timeline(dup, TEAM)) == ["1"]


def test_j2_duplicates_do_not_inflate_the_density():
    dup = [sm(1, (9, 10, 20, 0), "epl"), sm(1, (9, 10, 20, 0), "epl")]
    assert rest_context(dup, TEAM, at(9, 13)).window_counts[7] == 1


def test_k1_same_pair_different_match_id_both_stay():
    pair = [sm(100, (9, 10, 20, 0), "ucl"), sm(200, (9, 12, 20, 0), "ucl")]
    assert ids(team_timeline(pair, TEAM)) == ["100", "200"]


def test_m1_a_match_without_kickoff_is_not_used():
    broken = SeasonMatch(match_id="x", competition="epl", home_team=TEAM,
                         away_team="Milan", finished=True, kickoff=None)
    assert ids(team_timeline([broken] + CROSS, TEAM)) == ["1", "2", "3"]


def test_m2_a_match_without_an_id_is_not_used():
    anon = sm("", (9, 12, 20, 0), "epl")
    assert ids(team_timeline([anon] + CROSS, TEAM)) == ["1", "2", "3"]


def test_m3_unfinished_past_matches_are_not_rest_references():
    """킥오프가 지났는데 끝나지 않았으면 연기됐을 수 있다."""
    season = [sm(1, (9, 10, 20, 0), "epl"),
              sm(2, (9, 12, 20, 0), "epl", finished=False)]
    assert rest_context(season, TEAM, at(9, 13)).previous_match_id == "1"


def test_n1_legacy_index_without_competition_still_works():
    """6-D-5 이전 저장본처럼 대회 표시가 없어도 시간축이 선다."""
    legacy = [SeasonMatch(match_id=str(i), home_team=TEAM, away_team="Milan",
                          home_goals=1, away_goals=0, finished=True,
                          kickoff=at(9, d, 20, 0), kickoff_aware=True)
              for i, d in enumerate((10, 13), start=1)]
    assert ids(team_timeline(legacy, TEAM)) == ["1", "2"]
    assert rest_context(legacy, TEAM, at(9, 16)).previous_match_id == "2"


def test_n2_legacy_index_is_not_filtered_away_by_a_competition_ask():
    """`scope_to_competition` 의 '표시 없음' 규칙을 그대로 따른다 (§1-30)."""
    legacy = [SeasonMatch(match_id="1", home_team=TEAM, away_team="Milan",
                          home_goals=1, away_goals=0, finished=True,
                          kickoff=at(9, 10, 20, 0), kickoff_aware=True)]
    assert ids(team_timeline(legacy, TEAM, competition="epl")) == ["1"]


# ==========================================================================
# L. 창 경계 (§14-L · §9)
# ==========================================================================
def test_l1_windows_use_the_configured_days():
    assert REST_WINDOW_DAYS == (7, 10, 14)
    ctx = rest_context(CROSS, TEAM, at(9, 20, 21, 0))
    assert sorted(ctx.window_counts) == [7, 10, 14]


def test_l2_counts_grow_with_the_window():
    season = [sm(1, (9, 5, 20, 0), "epl"),     # 15일 전
              sm(2, (9, 11, 20, 0), "ucl"),    # 9일 전
              sm(3, (9, 17, 20, 0), "epl")]    # 3일 전
    ctx = rest_context(season, TEAM, at(9, 20, 20, 0))
    assert ctx.window_counts[7] == 1
    assert ctx.window_counts[10] == 2
    assert ctx.window_counts[14] == 2


def test_l3_exactly_seven_days_ago_is_excluded():
    """경계는 **양쪽 다 열려 있다** — `현재 − N일 < 킥오프 < 현재`.

    주 1회 같은 시각에 치르는 팀은 `matches_last_7d` 가 0 이 된다는 뜻이다.
    직관과 어긋날 수 있어 여기 못 박아 둔다 — 정하지 않는 것보다 낫다.
    """
    now = at(9, 20, 20, 0)
    season = [sm(1, (9, 13, 20, 0), "epl")]          # 정확히 7일 전
    assert rest_context(season, TEAM, now).window_counts[7] == 0
    # 1분만 늦어도 들어온다
    season2 = [sm(1, (9, 13, 20, 1), "epl")]
    assert rest_context(season2, TEAM, now).window_counts[7] == 1


def test_l4_the_current_match_is_not_counted():
    now = at(9, 20, 20, 0)
    season = [sm(1, (9, 20, 20, 0), "epl")]
    assert rest_context(season, TEAM, now).window_counts[7] == 0


def test_l6_zero_and_unknown_are_different():
    """색인이 이 팀을 모르면 `{}`, 봤는데 없으면 `0` 이다 (§1-5).

    둘을 같이 두면 '최근 7일 경기 0' 이 '자료가 없다' 를 가린다.
    """
    known = rest_context([sm(1, (9, 20, 20, 0), "epl")], TEAM, at(9, 20, 20, 0))
    assert known.window_counts == {7: 0, 10: 0, 14: 0}
    unknown = rest_context([sm(1, (9, 10, 20, 0), "epl", home="Arsenal",
                               away="Chelsea")], TEAM, at(9, 20))
    assert unknown.window_counts == {}


def test_l5_windows_count_across_competitions():
    ctx = rest_context(CROSS, TEAM, at(9, 17, 21, 0))
    assert ctx.window_counts[7] == 2          # 9/13 UCL · 9/16 EPL


# ==========================================================================
# O. 기존 구현 교체 · 호환 (§11 · §14-O · §18)
# ==========================================================================
def test_o1_the_old_form_based_path_is_gone():
    src = inspect.getsource(analyze.build_rest_days)
    code = src[src.index('"""', src.index('"""') + 3) + 3:]
    assert "form" not in code, "폼으로 되돌아갔다"
    assert "_parse_date" not in code


def test_o2_no_duplicate_v2_api():
    """`build_rest_days_v2` 같은 중복 API 를 만들지 않았다 (§11).

    `dir()` 에는 `models` 에서 가져온 `rest_context` 도 보이므로, 이 모듈이
    **정의한** 이름만 센다.
    """
    tree = ast.parse((ROOT / "toto" / "analyze.py").read_text(encoding="utf-8"))
    defined = [n.name for n in tree.body
               if isinstance(n, ast.FunctionDef) and "rest" in n.name.lower()]
    assert defined == ["build_rest_days"], defined


def test_o3_rest_days_keeps_its_type_for_the_report():
    """화면 문구가 `휴식 N일` 이라 정수 계약을 유지한다."""
    season = [sm(1, (9, 10, 20, 0), "epl")]
    ctx = rest_context(season, TEAM, at(9, 13, 18, 30))
    assert isinstance(ctx.rest_days, int)
    assert isinstance(ctx.rest_hours, float)


def test_o4_build_rest_days_without_an_index_makes_nothing():
    """색인이 없으면 폼으로 되돌아가지 않고 비워 둔다 (`--demo` 가 이 경우)."""
    m = Match(no=1, league="epl",
              home=TeamRef(canonical=TEAM, display=TEAM),
              away=TeamRef(canonical="Milan", display="Milan"),
              kickoff_kst="2026-09-13 18:30")
    m.home_profile = TeamProfile(team=m.home)
    m.away_profile = TeamProfile(team=m.away)
    analyze.build_rest_days([m])
    assert m.home_profile.rest_days is None
    assert m.home_profile.rest_hours is None


def test_o5_build_rest_days_fills_from_the_index():
    m = Match(no=1, league="epl",
              home=TeamRef(canonical=TEAM, display=TEAM),
              away=TeamRef(canonical="Milan", display="Milan"),
              kickoff_kst="2026-09-16 21:00")
    m.home_profile = TeamProfile(team=m.home)
    m.away_profile = TeamProfile(team=m.away)
    analyze.build_rest_days([m], CROSS)
    assert m.home_profile.rest_days == 3          # 9/13 19:00 → 9/16 21:00
    assert m.home_profile.rest_hours == 74.0
    assert m.home_profile.match_density[7] == 2


def test_o6_profile_defaults_are_backward_compatible():
    p = TeamProfile(team=TeamRef())
    assert p.rest_days is None and p.rest_hours is None
    assert p.match_density == {}


def test_o7_old_artifact_revives_without_the_new_fields():
    body = {"team": {"canonical": TEAM}, "rest_days": 7}
    out = models._revive_profile(body)
    assert out.rest_days == 7
    assert out.rest_hours is None
    assert out.match_density == {}


def test_o8_density_survives_a_json_round_trip():
    p = TeamProfile(team=TeamRef(), match_density={7: 2, 10: 3, 14: 4})
    back = models._revive_profile(json.loads(json.dumps(asdict(p))))
    assert back.match_density == {7: 2, 10: 3, 14: 4}


def test_o9_real_artifact_still_reads_and_keeps_its_values():
    from toto import artifact
    path = ROOT / "data" / "artifacts" / "260052.json"
    if not path.exists():
        return
    rep, why = artifact.load_path(str(path))
    assert not why, why
    filled = [p.rest_days for m in rep.matches
              for p in (m.home_profile, m.away_profile) if p]
    assert len(filled) == 28 and all(v is not None for v in filled)


def test_o10_real_index_builds_a_timeline():
    from toto import artifact
    path = ROOT / "data" / "artifacts" / "260052.json"
    if not path.exists():
        return
    rep, _ = artifact.load_path(str(path))
    line = team_timeline(rep.season_matches, "Liverpool")
    assert line, "실물 색인에서 시간축이 서지 않았다"
    stamps = [in_kst(m.kickoff) for m in line]
    assert stamps == sorted(stamps)
    assert len({m.match_id for m in line}) == len(line)


# ==========================================================================
# P. 금지 — 이 Phase 가 만들지 않은 것
# ==========================================================================
def test_p1_no_synthetic_match_duration():
    """105분 같은 경기시간을 지어내지 않는다."""
    src = inspect.getsource(models.rest_context)
    for banned in ("105", "90", "finished_at", "duration"):
        assert banned not in src, banned


def test_p2_rest_does_not_reach_probability_or_picks():
    src = inspect.getsource(analyze.build_rest_days)
    for banned in ("probs", "odds", "predict", "pick", "recommend"):
        assert banned not in src, banned


def test_p3_no_new_match_model():
    """`SeasonMatch` 를 그대로 쓴다 — 경기 모델을 복제하지 않았다 (§2)."""
    assert all(isinstance(m, SeasonMatch) for m in team_timeline(CROSS, TEAM))
    for banned in ("MatchTimeline", "TeamSchedule", "TeamFixtureHistory"):
        assert not hasattr(models, banned), banned


def test_p4_timeline_does_not_collect_anything():
    """이미 받아 둔 색인만 읽는다 — 새 수집 경로를 만들지 않았다 (§12)."""
    tree = ast.parse((ROOT / "toto" / "models.py").read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
        elif isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
    assert not {m for m in mods if "sources" in m or m == "requests"}, mods


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
    raise SystemExit(main())
