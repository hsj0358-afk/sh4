"""대륙대회 수집·색인 회귀 테스트 (Phase 6-D-7).

**묻는 것은 둘이다.**

  1. UCL·UEL·Conference 가 국내리그와 **다른 모집단**으로 서고, 서로도 섞이지
     않는가.
  2. 한 대회 안에서 **리그 페이즈와 녹아웃이 하나의 모집단**으로 남는가.

그리고 그 사이에 이번 Phase 가 실제로 고친 결함이 하나 있다.

    소스가 같은 경기 ID 를 두 이름으로 준다 — `id`(일정)와 `matchId`(브래킷).
    `id` 만 읽던 동안 같은 경기가 두 벌로 남았고, 브래킷으로만 온 경기는
    ID 없는 경기가 되어 시즌 색인에서 통째로 빠졌다.

fixture 는 **실물 응답에서 잘라낸 것**이다 (`tests/fixtures/fotmob/
continental/`). 구조를 지어내지 않았고 값도 관측된 그대로다.

**live 수집은 검증하지 않는다.** 이 저장소의 원격 세션에서 fotmob.com 이
차단돼 있다(§2-1). 여기서 PASS 하는 것은 **parser·dedup·색인 격리**이지
live acquisition 이 아니다.

과거 시즌 요청은 뒤에 사용자 PC 실측으로 답이 났다 — `season=` 하나면 통하고
`ccode3` 는 무의미하다(§1-33). 그래도 이 파일의 H 절은 **6-D-7 이 URL 을
건드리지 않았다**는 사실을 그대로 고정한다. 받을 수 있다는 것과 받기로
정하는 것은 다른 일이고, 뒤쪽은 6-D-6 소관이다.

pytest 없이도 돈다:  python tests/test_continental_collection.py
"""
from __future__ import annotations

import ast
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from toto import analysis, models                              # noqa: E402
from toto.models import (Match, SeasonMatch, TeamProfile,      # noqa: E402
                         TeamRef, competitions_in,
                         in_competition, scope_to_competition)
from toto.normalize import TeamResolver                        # noqa: E402
from toto.settings import (CONTINENTAL, LEAGUE,                # noqa: E402
                           Settings, load_settings)
from toto.sources import fotmob as F                           # noqa: E402

FX = ROOT / "tests" / "fixtures" / "fotmob" / "continental"
COMPETITIONS = ("ucl", "uel", "conference")
DOMESTIC = ("epl", "laliga", "bundesliga", "seriea",
            "ligue1", "kleague1", "kleague2", "jleague")
UTC = timezone.utc


def fixture(tag: str) -> dict:
    return json.loads((FX / f"{tag}_2025_2026.json").read_text(encoding="utf-8"))


def raw_nodes(body) -> list[dict]:
    return [n for n in F._walk(body) if F._is_match(n)]


def sm(mid, home, away, day, competition, hg=1, ag=0):
    return SeasonMatch(match_id=str(mid), home_team=home, away_team=away,
                       home_goals=hg, away_goals=ag, finished=True,
                       competition=competition,
                       kickoff=datetime(2026, 9, day, 18, 0, tzinfo=UTC),
                       kickoff_aware=True)


# ==========================================================================
# A. 대회 등록 (§39)
# ==========================================================================
def test_a1_three_competitions_are_registered():
    s = load_settings()
    for key in COMPETITIONS:
        assert key in s.leagues, f"{key} 가 설정에 없다"


def test_a2_all_three_are_continental():
    s = load_settings()
    for key in COMPETITIONS:
        assert s.league_type(key) == CONTINENTAL, key


def test_a3_none_of_them_owns_team_league():
    """대회 표로 팀의 국내 소속을 고치지 않는다 (6-D-3)."""
    s = load_settings()
    for key in COMPETITIONS:
        assert s.owns_team_league(key) is False, key


def test_a4_all_three_are_strict():
    """팀명을 정확일치로만 해석한다 (6-D-4)."""
    s = load_settings()
    for key in COMPETITIONS:
        assert s.strict_team_match(key) is True, key


def test_a5_domestic_leagues_are_untouched():
    s = load_settings()
    for key in DOMESTIC:
        assert s.league_type(key) == LEAGUE, key
        assert s.owns_team_league(key) is True, key
        assert s.strict_team_match(key) is False, key


def test_a6_source_id_lives_in_config_not_in_code():
    """리그 ID 를 파서에 박지 않는다 (§1-1-1)."""
    s = load_settings()
    ids = {k: (s.leagues[k] or {}).get("fotmob_id") for k in COMPETITIONS}
    assert all(isinstance(v, int) for v in ids.values()), ids
    src = (ROOT / "toto" / "sources" / "fotmob.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            assert node.value not in set(ids.values()), \
                f"리그 ID {node.value} 가 소스에 박혀 있다"


# ==========================================================================
# B. 경기 식별 (§6 · §35 · §36)
# ==========================================================================
def test_b1_match_id_reads_both_source_names():
    """소스가 `id` 로도 `matchId` 로도 준다 — 한 규칙으로 읽는다."""
    assert F.match_id_of({"id": 5161880}) == "5161880"
    assert F.match_id_of({"matchId": 5161880}) == "5161880"
    assert F.match_id_of({"id": "5161880"}) == "5161880"
    assert F.match_id_of({}) == ""


def test_b2_id_wins_over_match_id_when_both_present():
    assert F.match_id_of({"id": 1, "matchId": 2}) == "1"


def test_b3_booleans_are_not_ids():
    """`True` 는 `int` 의 하위형이다 (§1-9)."""
    assert F.match_id_of({"id": True}) == ""
    assert F.match_id_of({"id": False, "matchId": 7}) == "7"


def test_b4_blank_is_not_an_id():
    for bad in ("", "   ", None, 0):
        assert F.match_id_of({"id": bad}) == "", bad


def test_b5_same_pair_different_match_id_both_survive():
    """같은 두 팀이 한 대회에서 두 번 만난다 — 둘 다 남아야 한다 (§35)."""
    season = [sm(100, "Liverpool", "Milan", 1, "ucl"),
              sm(200, "Liverpool", "Milan", 20, "ucl")]
    got = in_competition(season, "ucl")
    assert {m.match_id for m in got} == {"100", "200"}


def test_b6_cross_competition_same_pair_both_survive():
    """같은 두 팀이 UCL 과 UEL 에서 만나도 둘 다 남는다 (§36)."""
    season = [sm(100, "Liverpool", "Milan", 1, "ucl"),
              sm(300, "Liverpool", "Milan", 2, "uel")]
    assert {m.match_id for m in in_competition(season, "ucl")} == {"100"}
    assert {m.match_id for m in in_competition(season, "uel")} == {"300"}


def test_b7_team_pair_is_not_the_identity():
    """팀 짝으로 가르면 위 두 경기 중 하나가 사라진다 — 그렇지 않다."""
    season = [sm(100, "Liverpool", "Milan", 1, "ucl"),
              sm(200, "Liverpool", "Milan", 20, "ucl")]
    assert len({m.match_id for m in season}) == 2
    assert len({(m.home_team, m.away_team) for m in season}) == 1


# ==========================================================================
# C. 중복 제거 (§7 · §8 · §33 · §34)
# ==========================================================================
def test_c1_dual_path_duplicates_collapse_to_unique_ids():
    """input N → unique match_id M → final M (§33).

    fixture 는 실물 구조다 — 같은 녹아웃 경기가 일정(`id`)과 브래킷
    (`matchId`) 양쪽에 실려 있다.
    """
    for tag in COMPETITIONS:
        body = fixture(tag)
        raw = raw_nodes(body)
        out = F._match_list(body)
        ids = [F.match_id_of(n) for n in out]
        assert len(raw) > len(out), f"{tag}: 중복이 없으면 이 fixture 가 틀렸다"
        assert all(ids), f"{tag}: ID 없는 레코드가 남았다"
        assert len(ids) == len(set(ids)), f"{tag}: 중복 ID 가 남았다"
        assert len(out) == len(set(ids))


def test_c2_every_deduped_id_comes_from_all_matches():
    """브래킷 사본이 새 경기를 만들어 내지 않는다."""
    for tag in COMPETITIONS:
        body = fixture(tag)
        allm = {str(m["id"]) for m in body["fixtures"]["allMatches"]}
        got = {F.match_id_of(n) for n in F._match_list(body)}
        assert got == allm, (tag, got ^ allm)


def test_c3_knockout_matches_keep_their_id():
    """브래킷으로만 온 경기가 ID 없는 경기가 되지 않는다.

    예전에는 `_parse_matches` 가 `raw.get("id")` 만 읽어서, 브래킷 레코드가
    바탕으로 뽑히면 ID 가 `None` 이 되고 시즌 색인에서 통째로 빠졌다.
    """
    body = fixture("ucl")
    bracket_ids = {str(m["matchId"])
                   for m in body["playoff"]["rounds"][0]["matches"]}
    assert bracket_ids, "fixture 에 브래킷이 없다"
    got = {F.match_id_of(n) for n in F._match_list(body)}
    assert bracket_ids <= got, bracket_ids - got


def test_c4_merge_is_order_independent():
    """`merge(a, b) == merge(b, a)` (§34)."""
    a = {"home": {"name": "A"}, "away": {"name": "B"}, "id": 1,
         "round": "1", "roundName": 1, "status": {"finished": True}}
    b = {"home": {"name": "A"}, "away": {"name": "B"}, "matchId": 1,
         "pageUrl": "/x", "status": {"finished": True}}
    assert F._merge_match_records(a, b) == F._merge_match_records(b, a)


def test_c5_merge_never_overwrites_an_existing_value():
    """킥오프가 경로마다 다를 수 있다 — 바탕 값을 덮지 않는다 (§10)."""
    a = {"home": {"name": "A"}, "away": {"name": "B"}, "id": 1,
         "round": "1", "roundName": 1,
         "status": {"utcTime": "2026-05-20T17:00:00.000Z"}}
    b = {"home": {"name": "A"}, "away": {"name": "B"}, "matchId": 1,
         "status": {"utcTime": "2026-05-20T19:00:00.000Z"}}
    merged = F._merge_match_records(a, b)
    assert merged["status"]["utcTime"] == "2026-05-20T17:00:00.000Z"


def test_c6_merge_fills_only_empty_fields():
    """더 많이 아는 쪽이 바탕이고, 바탕에 **없는 칸만** 채운다."""
    a = {"home": {"name": "A"}, "away": {"name": "B"}, "id": 1,
         "round": "3", "roundName": 3, "status": {"finished": True}}
    b = {"home": {"name": "A"}, "away": {"name": "B"}, "matchId": 1,
         "pageUrl": "/m/1", "round": "9"}
    merged = F._merge_match_records(a, b)
    assert merged["round"] == "3"          # 바탕(a)에 있던 값은 그대로
    assert merged["pageUrl"] == "/m/1"     # 바탕에 없던 칸만 채운다
    assert merged["status"] == {"finished": True}


def test_c6b_base_is_the_record_that_knows_more():
    """바탕 고르기가 입력 순서가 아니라 **아는 양**으로 정해진다.

    브래킷 레코드(`away·home·matchId·pageUrl·status`)는 일정 레코드
    (`…·id·round·roundName·status`)의 부분집합이라, 실물에서는 언제나
    일정 쪽이 바탕이 된다.
    """
    small = {"home": {"name": "A"}, "away": {"name": "B"}, "matchId": 1,
             "pageUrl": "/m/1", "status": {"finished": True}}
    big = {"home": {"name": "A"}, "away": {"name": "B"}, "id": 1,
           "pageUrl": "/m/1", "round": "3", "roundName": 3,
           "status": {"finished": True}}
    for merged in (F._merge_match_records(small, big),
                   F._merge_match_records(big, small)):
        assert merged["round"] == "3"
        assert F.match_id_of(merged) == "1"


def test_c7_match_list_is_stable_when_source_order_flips():
    """일정과 브래킷의 순서를 바꿔도 같은 색인이 나온다 (§34)."""
    for tag in COMPETITIONS:
        body = fixture(tag)
        flipped = {"details": body["details"],
                   "playoff": body["playoff"],
                   "fixtures": body["fixtures"]}
        a = sorted(F.match_id_of(n) for n in F._match_list(body))
        b = sorted(F.match_id_of(n) for n in F._match_list(flipped))
        assert a == b, tag


def test_c8_dedup_is_a_no_op_without_duplicates():
    """중복이 없으면 예전과 똑같이 동작한다 — 국내리그가 이 경우다."""
    body = {"fixtures": {"allMatches": [
        {"id": i, "home": {"name": f"H{i}"}, "away": {"name": f"A{i}"},
         "status": {"finished": True, "utcTime": f"2026-09-0{i}T18:00:00Z"}}
        for i in range(1, 6)]}}
    out = F._match_list(body)
    assert len(out) == 5
    # `_walk` 는 스택이라 순회 순서가 문서 순서와 다르다 (§1-1-2). 뒤에서
    # `_parse_matches` 가 킥오프로 다시 정렬하므로 여기서는 **무엇이 남았나**
    # 만 본다 — 순서를 단언하면 이 Phase 와 무관한 것을 고정하게 된다.
    assert sorted(F.match_id_of(n) for n in out) == ["1", "2", "3", "4", "5"]


def test_c9_records_without_any_id_keep_their_own_space():
    """ID 없는 노드가 ID 있는 경기와 섞이지 않는다.

    ID 가 없는 레코드는 팀 짝으로 모을 수밖에 없는데, 그 키가 ID 공간과
    같은 자리를 쓰면 팀 짝이 식별자가 되어 버린다 (§44-10).
    """
    body = {"a": {"id": 7, "home": {"name": "H"}, "away": {"name": "A"},
                  "status": {"utcTime": "2026-09-01T18:00:00Z"}},
            "b": {"home": {"name": "H"}, "away": {"name": "A"},
                  "score": "1 - 0"}}
    out = F._match_list(body)
    assert len(out) == 2
    assert sorted(F.match_id_of(n) for n in out) == ["", "7"]


def test_c10_id_less_records_never_reach_the_season_index():
    """ID 가 없으면 색인에 담지 않는다 (§1-1-4). 예전 규칙 그대로다."""
    rows = [{"id": None, "home": "A", "away": "B", "utc": "",
             "home_goals": 1, "away_goals": 0, "finished": True},
            {"id": "42", "home": "A", "away": "B", "utc": "",
             "home_goals": 1, "away_goals": 0, "finished": True}]
    got = F.season_matches_from(rows, "ucl")
    assert [m.match_id for m in got] == ["42"]


# ==========================================================================
# D. 대회 모집단 (§13 · §19 · §40)
# ==========================================================================
def test_d1_league_phase_and_knockout_share_one_population():
    """대회 안에서 단계로 쪼개지 않는다 (§19)."""
    body = fixture("ucl")
    bracket = {str(m["matchId"])
               for m in body["playoff"]["rounds"][0]["matches"]}
    rows = [{"id": F.match_id_of(n), "home": "H", "away": "A", "utc": "",
             "home_goals": 1, "away_goals": 0, "finished": True}
            for n in F._match_list(body)]
    season = F.season_matches_from(rows, "ucl")
    assert {m.competition for m in season} == {"ucl"}
    got = {m.match_id for m in season}
    assert bracket <= got, "녹아웃이 대회 모집단에서 빠졌다"
    assert len(got) > len(bracket), "리그 페이즈가 빠졌다"


def test_d2_competition_key_is_the_registered_one():
    for tag in COMPETITIONS:
        rows = [{"id": "1", "home": "H", "away": "A", "utc": "",
                 "home_goals": 0, "away_goals": 0, "finished": True}]
        assert F.season_matches_from(rows, tag)[0].competition == tag


def test_d3_three_competitions_are_separate_populations():
    season = (F.season_matches_from(
                  [{"id": "1", "home": "H", "away": "A", "utc": "",
                    "home_goals": 0, "away_goals": 0, "finished": True}], "ucl")
              + F.season_matches_from(
                  [{"id": "2", "home": "H", "away": "A", "utc": "",
                    "home_goals": 0, "away_goals": 0, "finished": True}], "uel")
              + F.season_matches_from(
                  [{"id": "3", "home": "H", "away": "A", "utc": "",
                    "home_goals": 0, "away_goals": 0, "finished": True}],
                  "conference"))
    assert competitions_in(season) == {"ucl": 1, "uel": 1, "conference": 1}
    for tag, mid in (("ucl", "1"), ("uel", "2"), ("conference", "3")):
        assert [m.match_id for m in in_competition(season, tag)] == [mid]


def test_d4_merge_season_dedupes_across_calls():
    out: list = []
    rows = [{"id": "9", "home": "H", "away": "A", "utc": "",
             "home_goals": 1, "away_goals": 1, "finished": True}]
    F.merge_season(out, rows, "ucl")
    F.merge_season(out, rows, "ucl")
    assert len(out) == 1


# ==========================================================================
# E. strict resolver (§26 · §27)
# ==========================================================================
KNOWN_FALSE = [
    ("Rangers", "Angers"), ("Lillestrøm", "Lille"),
    ("Lillestroem", "Lille"), ("Queens Park Rangers", "Angers"),
    ("Birmingham City", "Manchester City"), ("Chester FC", "Manchester City"),
    ("Charlton", "Athletic Club"), ("Oldham", "Athletic Club"),
    ("Wigan Athletic", "Athletic Club"),
]


def test_e1_known_false_matches_never_come_back():
    r = TeamResolver()
    for name, wrong in KNOWN_FALSE:
        got = r.resolve(name, learn=False, quiet=True, strict=True)
        assert got != wrong, f"{name} → {wrong} 가 되살아났다"


def test_e2_continental_collection_path_is_strict():
    s = load_settings()
    for key in COMPETITIONS:
        assert s.strict_team_match(key) is True, key


def test_e3_strict_does_not_learn():
    r = TeamResolver()
    for name, _ in KNOWN_FALSE:
        r.resolve(name, learn=True, quiet=True, strict=True)
    assert r._dirty is False
    assert r._league_dirty is False


def test_e4_coverage_is_reported_not_padded():
    """해석되지 않는 팀을 fuzzy 로 채우지 않는다 (§26)."""
    body = fixture("uel")
    r = TeamResolver()
    strict_rows = F._parse_matches(body, r, strict=True)
    loose_rows = F._parse_matches(body, TeamResolver(), strict=False)
    assert len(strict_rows) <= len(loose_rows)
    assert r.strict_blocked or len(strict_rows) <= len(loose_rows)


# ==========================================================================
# F. 색인 격리 (§17 · §18 · §37)
# ==========================================================================
MIXED = ([sm(1000 + i, "Arsenal", "Chelsea", 1 + i, "epl") for i in range(10)]
         + [sm(2000 + i, "Arsenal", "Milan", 1 + i, "ucl") for i in range(3)]
         + [sm(3000 + i, "Arsenal", "Roma", 1 + i, "uel") for i in range(2)])


def test_f1_each_population_keeps_its_own_size():
    """EPL 10 · UCL 3 · UEL 2 — 국내가 15 로 늘면 FAIL (§37)."""
    assert len(in_competition(MIXED, "epl")) == 10
    assert len(in_competition(MIXED, "ucl")) == 3
    assert len(in_competition(MIXED, "uel")) == 2
    assert len(MIXED) == 15


def test_f2_domestic_analysis_does_not_see_continental():
    as_of = datetime(2026, 9, 25, tzinfo=UTC)
    rows = analysis.team_history(MIXED, "Arsenal", as_of, competition="epl")
    assert len(rows) == 10
    assert {m.competition for m in rows} == {"epl"}


def test_f3_continental_query_excludes_the_other_competition():
    assert {m.competition
            for m in scope_to_competition(MIXED, "ucl")[0]} == {"ucl"}
    assert {m.competition
            for m in scope_to_competition(MIXED, "uel")[0]} == {"uel"}


def test_f4_adding_continental_changes_no_domestic_axis():
    """색인에 대륙대회를 얹어도 국내 분석이 한 글자도 바뀌지 않는다."""
    def axes(season):
        m = Match(no=1, league="epl",
                  home=TeamRef(canonical="Arsenal", display="Arsenal"),
                  away=TeamRef(canonical="Chelsea", display="Chelsea"),
                  kickoff_kst="2026-09-25 20:00")
        m.home_profile = TeamProfile(team=m.home)
        m.away_profile = TeamProfile(team=m.away)
        analysis.attach_time_context([m], Settings(), season)
        from dataclasses import asdict
        return json.dumps(asdict(m.analysis), sort_keys=True,
                          ensure_ascii=False, default=str)

    only = [m for m in MIXED if m.competition == "epl"]
    assert axes(only) == axes(MIXED)


def test_f5_isolation_uses_the_existing_api():
    """6-D-5 의 API 를 다시 만들지 않는다 (§18)."""
    assert hasattr(models, "in_competition")
    assert hasattr(models, "scope_to_competition")
    src = (ROOT / "toto" / "sources" / "fotmob.py").read_text(encoding="utf-8")
    for banned in ("def in_competition", "def scope_to_competition"):
        assert banned not in src, banned


# ==========================================================================
# G. 팀 소속 오염 (§38)
# ==========================================================================
def test_g1_continental_collection_never_rewrites_team_league():
    """UCL 표를 읽었다고 리버풀 소속이 `ucl` 이 되지 않는다."""
    s = load_settings()
    r = TeamResolver()
    before = dict(getattr(r, "_league", {}) or {})
    for key in COMPETITIONS:
        assert s.owns_team_league(key) is False, key
    assert dict(getattr(r, "_league", {}) or {}) == before


def test_g2_no_learned_files_are_created():
    for name in ("teams.learned.yaml", "teams.league.yaml"):
        assert not (ROOT / "data" / name).exists(), name


def test_g3_set_league_is_still_called_from_one_place():
    hits = []
    for path in sorted((ROOT / "toto").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "set_league"):
                hits.append(path.name)
    assert hits == ["fotmob.py"], hits


# ==========================================================================
# H. 캐시 정체 (§29 · §40)
# ==========================================================================
def test_h1_each_competition_has_its_own_cache_entry():
    keys = {k: F.league_cache_key(k) for k in COMPETITIONS + DOMESTIC}
    assert len(set(keys.values())) == len(keys), keys


def test_h2_default_key_is_byte_identical_to_the_old_one():
    """시즌을 안 주면 예전 키와 글자까지 같다 — 옛 캐시가 그대로 읽힌다."""
    for key in DOMESTIC:
        assert F.league_cache_key(key) == f"league_{key}"
        assert F.league_cache_key(key, None) == f"league_{key}"
        assert F.league_cache_key(key, "") == f"league_{key}"


def test_h3_season_separates_the_cache_entry():
    """`ucl 2025/2026` 과 `ucl 2026/2027` 이 다른 칸에 앉는다 (§40)."""
    a = F.league_cache_key("ucl", "2025/2026")
    b = F.league_cache_key("ucl", "2026/2027")
    assert a != b, (a, b)
    assert a != F.league_cache_key("ucl")
    assert F.league_cache_key("uel", "2025/2026") != a


def test_h4_cache_key_has_no_path_separator():
    """`/` 가 파일 이름으로 새어 나가지 않는다."""
    assert "/" not in F.league_cache_key("ucl", "2025/2026")


def test_h5_no_season_query_was_added_to_the_url():
    """URL 은 그대로다 — 받을 수 있는 것과 받기로 정한 것은 다르다 (§14).

    6-D-7 당시의 근거는 "BLOCKED 라 지어내지 않는다" 였다. 실측 뒤 근거가
    둘로 갈렸다 (§1-33).

      · `season=`  통하는 것이 확인됐다. 넣지 않은 이유는 **무엇을 언제 받을지가
                   6-D-6 소관**이기 때문이지 못 받아서가 아니다.
      · `ccode3`   2)와 3) 응답의 바이트 수와 시즌 필드가 **전부 같았다.**
                   효과가 관측되지 않은 파라미터를 붙이지 않는다.
      · `x-mas`    production 경로가 알아서 붙인다. 손으로 만들지 않는다.
    """
    assert F.LEAGUE_PATH == "/api/data/leagues?id={id}"
    src = (ROOT / "toto" / "sources" / "fotmob.py").read_text(encoding="utf-8")
    assert "ccode3" not in src
    assert "x-mas" not in src.lower()


def test_h6_cache_version_was_raised_for_a_real_format_change():
    """저장되는 `matches` 모양이 달라졌으므로 판을 올렸다 (§1-4)."""
    assert F._CACHE_VERSION == 10


# ==========================================================================
# I. 직렬화 호환 (§30 · §41)
# ==========================================================================
def test_i1_competition_is_optional_when_reviving():
    body = {"match_id": "1", "home_team": "A", "away_team": "B"}
    assert SeasonMatch(**body).competition == ""


def test_i2_existing_artifact_still_reads():
    from toto import artifact
    path = ROOT / "data" / "artifacts" / "260052.json"
    if not path.exists():
        return                                   # 저장본이 없으면 건너뛴다
    rep, why = artifact.load_path(str(path))
    assert not why, why
    assert len(rep.matches) == 14
    assert competitions_in(rep.season_matches) == {"epl": 380, "laliga": 342}


def test_i3_domestic_artifact_has_no_continental_match():
    from toto import artifact
    path = ROOT / "data" / "artifacts" / "260052.json"
    if not path.exists():
        return
    rep, _ = artifact.load_path(str(path))
    for key in COMPETITIONS:
        assert in_competition(rep.season_matches, key) == [], key


def test_i4_parsed_id_is_a_string_and_survives_a_round_trip():
    rows = F._parse_matches(fixture("ucl"), TeamResolver(), strict=True)
    assert rows, "fixture 에서 해석된 경기가 없다"
    for row in rows:
        assert isinstance(row["id"], str), row["id"]
    frozen = json.loads(json.dumps({"matches": rows}))
    assert F.season_matches_from(frozen["matches"], "ucl")


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
