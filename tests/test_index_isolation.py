"""시즌 색인 모집단 분리 회귀 테스트 (Phase 6-D-5).

**묻는 것은 하나다 — 국내리그 분석이 보는 경기와 대륙대회 경기가 한 표본으로
섞이지 않는가.**

지금까지 이것이 안전했던 것은 규칙 덕분이 아니라 **색인이 국내리그만 담았기
때문**이다. 실측 260052 색인 722경기(`epl` 380 · `laliga` 342)에서 두 대회
이상에 나오는 팀이 **0명**이라, `team_history()` 의 팀 이름 필터가 우연히
대회 필터와 같은 일을 했다. 대륙대회가 색인에 들어오는 순간 그 전제가 깨진다 —
리버풀은 `epl` 과 `ucl` 양쪽에 있다.

이 파일이 고정하는 것:

  · 경계는 `models.in_competition` / `scope_to_competition` **한 곳**에 있다.
  · `competition` 이 비면 **거르지 않는다**. '모든 공식대회' 가 아니라
    **기존 동작의 보존**이다 (6-D-5 §8).
  · **대회 표시가 없는 옛 저장본은 거르지 않는다.** 거르면 전부 사라진다.
  · `match_id` 조회는 좁히지 않는다 — 그 자체로 권위 있는 식별자다 (§15).
  · 국내리그 결과가 **한 칸도 바뀌지 않는다.**

pytest 없이도 돈다:  python tests/test_index_isolation.py
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

from toto import analysis, match_material, models, roundlog   # noqa: E402
from toto.models import (Match, Report, SeasonMatch, TeamProfile,  # noqa: E402
                         TeamRef, competitions_in,
                         find_season_match, find_season_match_by_id,
                         in_competition, is_labeled, matches_before,
                         scope_to_competition)
from toto.normalize import TeamResolver                       # noqa: E402
from toto.settings import Settings                            # noqa: E402

UTC = timezone.utc
EPL, UCL = "epl", "ucl"
LIV, ARS, CHE = "Liverpool", "Arsenal", "Chelsea"
RMA, PSG = "Real Madrid", "Paris Saint-Germain"


def sm(mid, home, away, day, competition, hg=2, ag=1, finished=True):
    """시즌 색인 한 건. 기본은 종료 경기다."""
    return SeasonMatch(
        match_id=str(mid), home_team=home, away_team=away,
        home_goals=hg if finished else None,
        away_goals=ag if finished else None,
        finished=finished, competition=competition,
        kickoff=datetime(2026, 9, day, 18, 0, tzinfo=UTC),
        kickoff_aware=True)


# 리버풀이 두 대회에 모두 나온다 — 6-D-5 가 막으려는 바로 그 상황이다.
#   epl : 리버풀 3경기 (3승)
#   ucl : 리버풀 2경기 (2패)
MIXED = [
    sm(101, LIV, ARS, 1, EPL, 3, 0),
    sm(102, CHE, LIV, 2, EPL, 0, 2),
    sm(103, LIV, CHE, 3, EPL, 1, 0),
    sm(201, LIV, RMA, 4, UCL, 0, 4),
    sm(202, PSG, LIV, 5, UCL, 5, 0),
    sm(301, ARS, CHE, 6, EPL, 1, 1),
    sm(401, RMA, PSG, 7, UCL, 2, 2),
]
AS_OF = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)

UNLABELED = [SeasonMatch(match_id=m.match_id, home_team=m.home_team,
                         away_team=m.away_team, home_goals=m.home_goals,
                         away_goals=m.away_goals, finished=m.finished,
                         kickoff=m.kickoff, kickoff_aware=True)
             for m in MIXED]


def ids(rows) -> list[str]:
    return [str(m.match_id) for m in rows]


# ==========================================================================
# A. Test 1 — 국내리그 분석은 국내리그 경기만 본다
# ==========================================================================
def test_a1_domestic_history_excludes_continental():
    """`competition="epl"` 이면 UCL 경기가 한 건도 들어오지 않는다."""
    rows = analysis.team_history(MIXED, LIV, AS_OF, competition=EPL)
    assert ids(rows) == ["101", "102", "103"], ids(rows)
    assert all(m.competition == EPL for m in rows)


def test_a2_domestic_record_is_not_polluted_by_continental_results():
    """리버풀은 리그 3승 · UCL 2패다. 리그 모집단에 패배가 섞이면 안 된다."""
    rows = analysis.team_history(MIXED, LIV, AS_OF, competition=EPL)
    won = sum(1 for m in rows
              if (m.home_team == LIV and m.home_goals > m.away_goals)
              or (m.away_team == LIV and m.away_goals > m.home_goals))
    assert (len(rows), won) == (3, 3), (len(rows), won)


def test_a3_conceded_goals_do_not_leak_across_competitions():
    """UCL 에서 9실점했지만 리그 모집단의 실점은 0 이다."""
    rows = analysis.team_history(MIXED, LIV, AS_OF, competition=EPL)
    conceded = sum(m.away_goals if m.home_team == LIV else m.home_goals
                   for m in rows)
    assert conceded == 0, conceded


# ==========================================================================
# B. Test 2 — 대륙대회 모집단도 따로 선다
# ==========================================================================
def test_b1_continental_history_excludes_domestic():
    rows = analysis.team_history(MIXED, LIV, AS_OF, competition=UCL)
    assert ids(rows) == ["201", "202"], ids(rows)


def test_b2_two_populations_are_disjoint():
    dom = set(ids(analysis.team_history(MIXED, LIV, AS_OF, competition=EPL)))
    con = set(ids(analysis.team_history(MIXED, LIV, AS_OF, competition=UCL)))
    assert not (dom & con), dom & con


def test_b3_union_equals_unfiltered_history():
    """두 모집단을 합치면 거르지 않은 것과 같다 — 경기를 잃지 않았다."""
    dom = ids(analysis.team_history(MIXED, LIV, AS_OF, competition=EPL))
    con = ids(analysis.team_history(MIXED, LIV, AS_OF, competition=UCL))
    every = ids(analysis.team_history(MIXED, LIV, AS_OF))
    assert sorted(dom + con) == sorted(every), (dom, con, every)


def test_b4_unknown_competition_yields_empty_not_everything():
    """표시가 있는 색인에 없는 대회를 물으면 **빈 목록**이다.

    '그 대회 경기를 담지 않은 색인' 이 맞는 답이고, 없는 모집단을 다른 대회
    경기로 채우는 것이 이 Phase 가 막으려는 오염이다.
    """
    assert analysis.team_history(MIXED, LIV, AS_OF, competition="uel") == []


# ==========================================================================
# C. Test 3 — 대회별 history API
# ==========================================================================
def test_c1_team_history_takes_competition():
    sig = inspect.signature(analysis.team_history)
    assert "competition" in sig.parameters
    assert sig.parameters["competition"].default is None


def test_c2_in_competition_is_a_pure_filter():
    assert ids(in_competition(MIXED, EPL)) == ["101", "102", "103", "301"]
    assert ids(in_competition(MIXED, UCL)) == ["201", "202", "401"]


def test_c3_filter_and_cutoff_are_orthogonal():
    """모집단과 시점은 순서를 바꿔 적용해도 같다."""
    a = matches_before(in_competition(MIXED, EPL), AS_OF)
    b = in_competition(matches_before(MIXED, AS_OF), EPL)
    assert ids(a) == ids(b), (ids(a), ids(b))


def _code_of(fn) -> str:
    """설명문을 뺀 본문. 규칙을 '적어 둔 것' 과 '실행하는 것' 은 다르다."""
    tree = ast.parse(inspect.getsource(fn).lstrip())
    node = tree.body[0]
    body = node.body[1:] if (isinstance(node.body[0], ast.Expr)
                             and isinstance(node.body[0].value, ast.Constant)
                             and isinstance(node.body[0].value.value, str)
                             ) else node.body
    return "\n".join(ast.unparse(n) for n in body)


def test_c4_team_history_does_not_compare_competition_itself():
    """경계 규칙은 `models` 한 곳에 있다 — 여기서 다시 적지 않는다 (§1-8)."""
    code = _code_of(analysis.team_history)
    assert ".competition" not in code, code
    assert "scope_to_competition" in code


def test_c5_cutoff_still_comes_from_models_only():
    """6-D-5 가 시점 규칙을 건드리지 않았다."""
    code = _code_of(analysis.team_history)
    assert "matches_before" in code
    assert "kickoff" not in code, code


# ==========================================================================
# D. Test 4 — 기존 호출부의 뜻을 바꾸지 않았다
# ==========================================================================
def test_d1_default_none_means_no_filter_not_all_competitions():
    """`competition=None` 은 '거르지 않는다' 이지 '모든 공식대회' 가 아니다.

    둘은 지금 같은 결과를 내지만 **뜻이 다르다.** 기본값이 정책이 되면
    호출부가 의도를 밝히지 않아도 대회가 섞이기 시작한다.
    """
    a = analysis.team_history(MIXED, LIV, AS_OF)
    b = analysis.team_history(MIXED, LIV, AS_OF, competition=None)
    assert ids(a) == ids(b) == ["101", "102", "103", "201", "202"]


def test_d2_empty_string_also_does_not_filter():
    assert ids(analysis.team_history(MIXED, LIV, AS_OF, competition="")) \
        == ["101", "102", "103", "201", "202"]


def test_d3_scope_reports_why_it_did_not_filter():
    """조용히 거르지 않고 넘어가지 않는다 (§1-6-1)."""
    rows, why = scope_to_competition(MIXED, "")
    assert len(rows) == len(MIXED) and why == models.SCOPE_NO_TARGET
    rows, why = scope_to_competition(MIXED, EPL)
    assert len(rows) == 4 and why == ""


def test_d4_scope_never_mutates_the_input():
    before = list(MIXED)
    scope_to_competition(MIXED, EPL)
    in_competition(MIXED, UCL)
    assert MIXED == before


def test_d5_build_team_analysis_defaults_to_no_filter():
    sig = inspect.signature(analysis.build_team_analysis)
    assert sig.parameters["competition"].default == ""


# ==========================================================================
# E. Test 5 — 국내리그 축 결과가 오염되지 않는다
# ==========================================================================
def _match(no, home, away, league, day=21):
    m = Match(no=no, league=league,
              home=TeamRef(canonical=home, display=home),
              away=TeamRef(canonical=away, display=away),
              kickoff_kst=f"2026-09-{day:02d} 20:00")
    m.home_profile = TeamProfile(team=m.home)
    m.away_profile = TeamProfile(team=m.away)
    return m


def _axes(season, league=EPL):
    m = _match(1, LIV, ARS, league)
    analysis.attach_time_context([m], Settings(), season)
    return json.dumps(asdict(m.analysis), sort_keys=True,
                      ensure_ascii=False, default=str)


def test_e1_adding_continental_matches_changes_nothing_domestic():
    """리그 색인에 UCL 경기를 얹어도 리그 분석이 한 글자도 바뀌지 않는다.

    3-F 의 누수 검사와 같은 방식이다 — 같은 자료에 섞이면 안 되는 것을
    얹고 **바이트가 같은지** 본다.
    """
    only = [m for m in MIXED if m.competition == EPL]
    assert _axes(only) == _axes(MIXED)


def test_e2_negative_control_the_comparison_can_detect_a_change():
    """음성 대조 — 아무것도 안 만들어서 같은 것이 아님을 보인다."""
    only = [m for m in MIXED if m.competition == EPL]
    extra = only + [sm(999, LIV, CHE, 8, EPL, 0, 7)]
    assert _axes(only) != _axes(extra)


# 색인에서 오는 값은 `recentN.*` 다 — `season.*` 은 순위표(TeamStats)에서
# 오므로 합성 프로필에는 없다. 창 10 이면 이 픽스처의 과거 경기가 다 들어간다.
def test_e3_attach_passes_each_match_its_own_league():
    tc = json.loads(_axes(MIXED, league=EPL))["home"]["time_context"]
    # UCL 2패가 섞였다면 승점·실점이 달라진다. 리그 3승만 보고 있어야 한다.
    pts = tc["metrics"].get("recent10.points")
    assert pts is not None and abs(pts["value"] - 3.0) < 1e-9, pts
    assert pts["sample_count"] == 3, pts
    ga = tc["metrics"].get("recent10.goals_against")
    assert ga is not None and abs(ga["value"] - 0.0) < 1e-9, ga


def test_e4_continental_match_sees_only_continental():
    tc = json.loads(_axes(MIXED, league=UCL))["home"]["time_context"]
    pts = tc["metrics"].get("recent10.points")
    assert pts is not None and abs(pts["value"] - 0.0) < 1e-9, pts
    assert pts["sample_count"] == 2, pts
    ga = tc["metrics"].get("recent10.goals_against")
    assert ga is not None and abs(ga["value"] - 4.5) < 1e-9, ga


def test_e5_boundary_is_applied_in_one_place():
    """축마다 걸지 않는다 — `build_team_analysis` 한 곳이다."""
    src = inspect.getsource(analysis.build_team_analysis)
    assert src.count("scope_to_competition") == 1, src
    for builder in ("build_time_context", "build_chance_quality",
                    "build_defensive_quality", "build_sustainability",
                    "build_venue_context", "build_schedule_strength"):
        body = inspect.getsource(getattr(analysis, builder))
        assert "scope_to_competition" not in body, builder
        assert ".competition" not in body, builder


# ==========================================================================
# F. Test 6 — match_id 는 권위 있는 식별자다 (§15)
# ==========================================================================
def test_f1_id_lookup_is_not_narrowed_by_competition():
    """ID 조회에는 `competition` 인자가 **없다.**

    소스 경기 ID 는 그 자체로 유일하므로 대회로 좁힐 이유가 없고, 좁히면
    '리그 키가 어긋나서 아는 경기를 못 찾는' 새 실패가 생긴다.
    """
    assert "competition" not in inspect.signature(
        find_season_match_by_id).parameters


def test_f2_id_lookup_finds_across_competitions():
    assert find_season_match_by_id(MIXED, "201").competition == UCL
    assert find_season_match_by_id(MIXED, "101").competition == EPL


def test_f3_duplicate_ids_still_refuse_to_pick():
    dup = [sm(1, LIV, ARS, 1, EPL), sm(1, LIV, CHE, 2, UCL)]
    assert find_season_match_by_id(dup, "1") is None


def test_f4_team_date_lookup_can_be_narrowed():
    """가장 약한 식별 단계(팀 짝 + 날짜)에만 경계가 붙는다."""
    assert "competition" in inspect.signature(find_season_match).parameters


# ==========================================================================
# G. Test 7 — 같은 두 팀이 두 대회에서 만난다
# ==========================================================================
CLASH = [
    sm(501, LIV, ARS, 10, EPL, 2, 0),
    sm(502, LIV, ARS, 11, "fa_cup", 0, 3),
]
WINDOW = timedelta(days=4)


def test_g1_without_competition_the_window_holds_both_and_refuses():
    """오늘의 동작 — 둘이 들어오면 `None` 이다. 안전하지만 못 찾은 것이다."""
    when = datetime(2026, 9, 10, 18, 0, tzinfo=UTC)
    assert find_season_match(CLASH, LIV, ARS, when, WINDOW) is None


def test_g2_with_competition_the_right_one_is_found():
    when = datetime(2026, 9, 10, 18, 0, tzinfo=UTC)
    hit = find_season_match(CLASH, LIV, ARS, when, WINDOW, competition=EPL)
    assert hit is not None and hit.match_id == "501"
    cup = find_season_match(CLASH, LIV, ARS, when, WINDOW,
                            competition="fa_cup")
    assert cup is not None and cup.match_id == "502"


def test_g3_history_keeps_the_two_meetings_apart():
    a = analysis.team_history(CLASH, LIV, AS_OF, competition=EPL)
    b = analysis.team_history(CLASH, LIV, AS_OF, competition="fa_cup")
    assert (ids(a), ids(b)) == (["501"], ["502"])


def test_g4_callers_that_know_the_competition_pass_it():
    """`roundlog._prematch_id` · `match_material._status_of` 가 넘긴다."""
    for fn in (roundlog._prematch_id, match_material._status_of):
        src = inspect.getsource(fn)
        assert "competition=" in src, fn.__name__


def test_g5_settlement_fallback_is_deliberately_unscoped():
    """CSV 의 `league` 칸은 대회 키가 아니다 — 그 사실을 적어 두었다."""
    src = inspect.getsource(roundlog._lookup)
    assert "competition=" not in src
    assert "league_ko" in src, "왜 걸지 않았는지가 본문에 없다"


# ==========================================================================
# H. Test 8 — 옛 저장본 호환 (대회 표시가 없다)
# ==========================================================================
def test_h1_competition_has_a_default_so_old_bodies_revive():
    """`SeasonMatch(**body)` 에 `competition` 이 없어도 깨지지 않는다."""
    body = {"match_id": "1", "home_team": LIV, "away_team": ARS}
    assert SeasonMatch(**body).competition == ""


def test_h2_unlabeled_index_is_not_filtered_away():
    """거르면 722경기가 0경기가 된다 — 분석이 통째로 빈다."""
    rows, why = scope_to_competition(UNLABELED, EPL)
    assert len(rows) == len(UNLABELED)
    assert why == models.SCOPE_UNLABELED


def test_h3_unlabeled_history_matches_pre_change_behaviour():
    assert ids(analysis.team_history(UNLABELED, LIV, AS_OF,
                                     competition=EPL)) \
        == ids(analysis.team_history(UNLABELED, LIV, AS_OF))


def test_h4_unlabeled_axes_are_identical_with_or_without_a_target():
    m1, m2 = _match(1, LIV, ARS, EPL), _match(1, LIV, ARS, "")
    analysis.attach_time_context([m1], Settings(), UNLABELED)
    analysis.attach_time_context([m2], Settings(), UNLABELED)
    assert (json.dumps(asdict(m1.analysis), sort_keys=True, default=str)
            == json.dumps(asdict(m2.analysis), sort_keys=True, default=str))


def test_h5_one_label_is_enough_to_call_the_index_labeled():
    """부분 표시는 표시된 것으로 친다 — 섞인 색인을 '표시 없음' 으로 보면
    경계가 통째로 풀린다."""
    part = UNLABELED[:-1] + [MIXED[-1]]
    assert is_labeled(part)
    assert len(scope_to_competition(part, UCL)[0]) == 1


def test_h6_unlabeled_find_season_match_still_works():
    when = datetime(2026, 9, 1, 18, 0, tzinfo=UTC)
    hit = find_season_match(UNLABELED, LIV, ARS, when, WINDOW,
                            competition=EPL)
    assert hit is not None and hit.match_id == "101"


# ==========================================================================
# I. Test 9 — 대회 메타데이터
# ==========================================================================
def test_i1_competitions_in_counts_each_key():
    assert competitions_in(MIXED) == {EPL: 4, UCL: 3}


def test_i2_competitions_in_keeps_unlabeled_visible():
    assert competitions_in(UNLABELED) == {"": 7}


def test_i3_is_labeled_distinguishes_the_two_indexes():
    assert is_labeled(MIXED) and not is_labeled(UNLABELED)
    assert not is_labeled([])


def test_i4_season_match_competition_is_written_in_one_place_only():
    """`SeasonMatch(competition=…)` 를 만드는 곳은 수집기 한 곳이다.

    `H2HEntry.competition` 처럼 **이름만 같은 다른 칸**이 있으므로 생성자를
    보고 가른다 — 이름으로만 세면 데모 픽스처까지 걸린다.
    """
    hits = set()
    for path in sorted((ROOT / "toto").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "SeasonMatch"
                    and any(k.arg == "competition" for k in node.keywords)):
                hits.add(path.name)
    assert hits == {"fotmob.py"}, sorted(hits)


def test_i5_population_is_logged_not_silent():
    """어느 대회에서 몇 경기를 봤는지 로그에 남는다 (§1-6-1)."""
    src = inspect.getsource(analysis.attach_time_context)
    assert "모집단" in src and "competitions_in" in src


def test_i6_identity_and_type_are_not_confused():
    """`SeasonMatch.competition`(정체) 과 6-D-3 의 type(성격)은 다르다.

    경계는 정체로만 판정한다 — `league_type`·`strict_team_match` 를 보지
    않는다. 대회 성격이 바뀐다고 모집단이 달라지면 안 된다.
    """
    for fn in (models.in_competition, models.scope_to_competition,
               analysis.team_history, analysis.build_team_analysis):
        src = inspect.getsource(fn)
        for banned in ("league_type", "strict_team_match", "CONTINENTAL"):
            assert banned not in src, (fn.__name__, banned)


def test_i7_no_competition_key_is_hardcoded_in_the_boundary():
    """대회 키를 코드에 박지 않는다 (6-D-5 §10)."""
    for fn in (models.in_competition, models.scope_to_competition,
               models.is_labeled, analysis.team_history,
               analysis.build_team_analysis):
        src = inspect.getsource(fn)
        for node in ast.walk(ast.parse(src.lstrip())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                low = node.value.lower()
                for key in ("ucl", "uel", "epl", "laliga", "cup",
                            "champions", "europa"):
                    assert key not in low.split() and low != key, \
                        (fn.__name__, node.value)


# ==========================================================================
# J. Test 10 — teams.yaml 오염 없음
# ==========================================================================
def test_j1_boundary_never_touches_the_resolver():
    for fn in (models.in_competition, models.scope_to_competition,
               analysis.team_history, analysis.build_team_analysis,
               analysis.attach_time_context):
        src = inspect.getsource(fn)
        for banned in ("TeamResolver", "resolve(", "set_league", "_learn"):
            assert banned not in src, (fn.__name__, banned)


def test_j2_running_the_analysis_does_not_dirty_the_resolver():
    r = TeamResolver()
    before = (r._dirty, r._league_dirty)
    m = _match(1, LIV, ARS, EPL)
    analysis.attach_time_context([m], Settings(), MIXED)
    assert (r._dirty, r._league_dirty) == before == (False, False)


def test_j3_learned_files_are_not_created():
    for name in ("teams.learned.yaml", "teams.league.yaml"):
        p = ROOT / "data" / name
        assert not p.exists(), f"{name} 가 생겼다"


def test_j4_analysis_still_does_not_import_sources():
    """모집단 경계를 만들면서 수집기를 끌어들이지 않았다."""
    tree = ast.parse((ROOT / "toto" / "analysis.py").read_text("utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
        elif isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
    assert not {m for m in mods if "sources" in m or m in ("requests",
                                                           "cache")}, mods


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
