"""경기 상세(matchDetails) 파싱 회귀 테스트 (Phase 1-B).

시즌 통계 29종에 **없는** 지표(npxG·xGOT·오픈플레이/세트피스 xG·총슈팅·
피슈팅·박스 안팎)는 `api/data/matchDetails` 에만 있다. 그 파싱 경로를
픽스처로 고정한다. 네트워크를 쓰지 않는다.

픽스처의 모양은 Phase 0 [8] 저장본 재분석에서 **실물로 확인한 것**만 옮겼다.

  · content.stats.Periods.All.stats[]  — 7개 그룹, 각 그룹의 stats[] 가 지표 줄
  · 지표 줄        — {"key": ..., "stats": [홈값, 원정값]}  (2원소)
  · content.shotmap.shots[] — teamId · situation · expectedGoals ·
                              expectedGoalsOnTarget · isOnTarget · isFromInsideBox

값 자체(예: EPL 어느 경기의 npxG)는 단언하지 않는다. 검증하는 것은
**어떤 모양을 어떤 필드로 옮기는가** 이다.

pytest 없이도 돈다:  python tests/test_match_details.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto.models import TeamStats, fill_stats                  # noqa: E402
from toto.sources import fotmob                                # noqa: E402

_HOME_ID, _AWAY_ID = 8650, 8455        # 합성 팀 ID (실제 값을 단언하지 않는다)


def _row(key: str, home, away, title: str = "") -> dict:
    return {"key": key, "title": title or key, "stats": [home, away]}


def _match_details(home_id: int = _HOME_ID, away_id: int = _AWAY_ID) -> dict:
    """실측 구조를 그대로 흉내낸 matchDetails 응답 하나.

    그룹 dict 도 `key`/`stats` 를 갖는다 — 그쪽 `stats` 는 dict 목록이므로
    지표 줄과 구분돼야 한다. 그 구분을 실제로 시험하려고 그룹을 넣었다.
    """
    return {
        "general": {"matchId": "4193495", "homeTeam": {"id": home_id},
                    "awayTeam": {"id": away_id}},
        "content": {
            "stats": {"Periods": {"All": {"stats": [
                {"key": "top_stats", "title": "Top stats", "stats": [
                    _row("BallPossesion", "58%", "42%", "Ball possession"),
                    _row("expected_goals", 1.84, 0.92, "Expected goals (xG)"),
                    _row("total_shots", 16, 9, "Total shots"),
                ]},
                {"key": "shots", "title": "Shots", "stats": [
                    _row("ShotsOnTarget", 7, 3, "Shots on target"),
                    _row("shots_inside_box", 11, 4, "Shots inside box"),
                    _row("shots_outside_box", 5, 5, "Shots outside box"),
                ]},
                {"key": "expected_goals", "title": "Expected goals", "stats": [
                    _row("expected_goals_non_penalty", 1.08, 0.92,
                         "Expected goals (xG) excl. penalty"),
                    _row("expected_goals_on_target", 2.10, 0.65, "xGOT"),
                    _row("expected_goals_open_play", 0.74, 0.55),
                    _row("expected_goals_set_play", 0.34, 0.37),
                ]},
                {"key": "discipline", "title": "Discipline", "stats": [
                    _row("yellow_cards", 2, 3),
                    # 값이 둘 다 없는 줄은 무시돼야 한다
                    _row("var_checks", None, None),
                ]},
            ]}}},
            "shotmap": {"shots": [
                # 홈: 일반 3개(0.30/0.18/0.60) + PK 1개(0.76) → xG 1.84, npxG 1.08
                {"id": 1, "teamId": home_id, "situation": "RegularPlay",
                 "expectedGoals": 0.30, "expectedGoalsOnTarget": 0.40,
                 "isOnTarget": True, "isFromInsideBox": True},
                {"id": 2, "teamId": home_id, "situation": "FromCorner",
                 "expectedGoals": 0.18, "expectedGoalsOnTarget": None,
                 "isOnTarget": False, "isFromInsideBox": True},
                {"id": 3, "teamId": home_id, "situation": "FastBreak",
                 "expectedGoals": 0.60, "expectedGoalsOnTarget": 0.85,
                 "isOnTarget": True, "isFromInsideBox": True},
                {"id": 4, "teamId": home_id, "situation": "Penalty",
                 "expectedGoals": 0.76, "expectedGoalsOnTarget": 0.85,
                 "isOnTarget": True, "isFromInsideBox": True},
                # 원정: 일반 2개 (0.52/0.40) → xG = npxG = 0.92
                {"id": 5, "teamId": away_id, "situation": "RegularPlay",
                 "expectedGoals": 0.52, "expectedGoalsOnTarget": 0.30,
                 "isOnTarget": True, "isFromInsideBox": True},
                {"id": 6, "teamId": away_id, "situation": "FreeKick",
                 "expectedGoals": 0.40, "expectedGoalsOnTarget": 0.35,
                 "isOnTarget": True, "isFromInsideBox": False},
            ]},
        },
    }


class FakeBrowser:
    """요청 URL 을 기록하는 가짜 FotMob 세션."""

    base = "https://www.fotmob.com"
    available = True

    def __init__(self, payloads: dict | None = None):
        self.payloads = payloads or {}
        self.calls: list[str] = []

    def abs_url(self, path):
        return self.base + path

    def get_json(self, url):
        self.calls.append(url)
        for mid, payload in self.payloads.items():
            if f"matchId={mid}" in url:
                return payload
        return None


class MemCache:
    """toto.cache.Cache 의 get/set 만 흉내낸 메모리 캐시."""

    def __init__(self):
        self.store: dict[tuple[str, str], object] = {}

    def get(self, source, key):
        return self.store.get((source, key))

    def set(self, source, key, value):
        self.store[(source, key)] = value


# --------------------------------------------------------------------------
# 1. 숫자 한 칸 읽기 — 표기가 섞여 있다
# --------------------------------------------------------------------------
def test_stat_number_handles_mixed_notation():
    f = fotmob._stat_number
    assert f(16) == 16.0
    assert f(1.84) == 1.84
    assert f("58%") == 58.0
    assert f("12 (30%)") == 12.0        # 앞 숫자가 실제 값, 괄호는 비율
    assert f("-0.35") == -0.35
    assert f(None) is None
    assert f("-") is None
    assert f(True) is None, "bool 을 1.0 으로 읽으면 안 된다"


# --------------------------------------------------------------------------
# 2. 지표 줄 찾기 — 경로가 아니라 모양으로
# --------------------------------------------------------------------------
def test_match_stat_pairs_finds_leaf_rows():
    pairs = fotmob._match_stat_pairs(_match_details())
    assert pairs["expected_goals_non_penalty"] == (1.08, 0.92)
    assert pairs["expected_goals_on_target"] == (2.10, 0.65)
    assert pairs["total_shots"] == (16.0, 9.0)
    assert pairs["ShotsOnTarget"] == (7.0, 3.0)
    assert pairs["shots_inside_box"] == (11.0, 4.0)
    assert pairs["shots_outside_box"] == (5.0, 5.0)
    assert pairs["BallPossesion"] == (58.0, 42.0)


def test_match_stat_pairs_ignores_group_nodes():
    """그룹 dict 도 key/stats 를 갖는다. 그 stats 는 dict 목록이라 제외돼야 한다."""
    pairs = fotmob._match_stat_pairs(_match_details())
    # 'shots' 는 그룹 key 이면서 지표 key 가 아니다
    assert "shots" not in pairs
    assert "top_stats" not in pairs
    # 값이 둘 다 없는 줄도 빠진다
    assert "var_checks" not in pairs


def test_match_stat_pairs_survives_split_shape():
    """그룹 계층이 없어도(평평해도) 같은 줄을 찾아낸다 — 경로를 박지 않았다는 뜻."""
    flat = {"whatever": {"rows": [_row("total_shots", 16, 9)]}}
    assert fotmob._match_stat_pairs(flat)["total_shots"] == (16.0, 9.0)


# --------------------------------------------------------------------------
# 3. 슛맵 합산 — PK 는 실제 분류로 뺀다 (0.76 상수 추정이 아니다)
# --------------------------------------------------------------------------
def test_shot_totals_excludes_penalty_from_npxg():
    totals = fotmob._shot_totals(_match_details())
    home, away = totals[_HOME_ID], totals[_AWAY_ID]

    assert round(home["xg"], 4) == 1.84         # PK 포함
    assert round(home["npxg"], 4) == 1.08       # PK 제외
    assert round(home["xg"] - home["npxg"], 4) == 0.76
    assert home["shots"] == 4 and home["on_target"] == 3
    assert round(home["xgot"], 4) == 2.10       # None 은 0 으로

    assert round(away["xg"], 4) == round(away["npxg"], 4) == 0.92
    assert away["shots"] == 2 and away["on_target"] == 2


def test_shot_totals_picks_longest_list():
    """선수별로 쪼개진 부분 목록이 아니라 경기 전체 슛맵을 써야 한다."""
    data = _match_details()
    partial = {"player": {"shots": data["content"]["shotmap"]["shots"][:1]}}
    data["content"]["partialSomewhere"] = partial
    totals = fotmob._shot_totals(data)
    assert totals[_HOME_ID]["shots"] == 4, "부분 목록을 잡으면 합계가 조용히 모자란다"


def test_shot_totals_empty_when_no_shotmap():
    assert fotmob._shot_totals({"content": {"stats": {}}}) == {}


# --------------------------------------------------------------------------
# 4. 경기 1건 → 팀별 지표 (피지표는 상대 값)
# --------------------------------------------------------------------------
def test_read_match_details_maps_fields_and_against():
    browser = FakeBrowser({"111": _match_details()})
    got = fotmob.read_match_details(browser, {"id": "111"})
    assert got is not None

    home, away = got["home"], got["away"]
    assert home["npxg"] == 1.08 and home["xgot"] == 2.10
    assert home["shots"] == 16.0 and home["shots_on_target"] == 7.0
    assert home["shots_inside_box"] == 11.0 and home["shots_outside_box"] == 5.0
    assert home["xg_open_play"] == 0.74 and home["xg_set_play"] == 0.34

    # 홈의 '피지표' 는 원정의 값이다 (그 반대도)
    assert home["npxga"] == 0.92 == away["npxg"]
    assert home["shots_against"] == 9.0 == away["shots"]
    assert home["shots_on_target_against"] == 3.0 == away["shots_on_target"]
    assert home["xgot_against"] == 0.65 == away["xgot"]
    assert away["npxga"] == 1.08 and away["shots_against"] == 16.0


def test_read_match_details_keeps_shotmap_check_separate():
    """슛맵 합산은 대조용으로만 남기고, 지표 값을 덮어쓰지 않는다."""
    got = fotmob.read_match_details(
        FakeBrowser({"111": _match_details()}), {"id": "111"})
    assert round(got["check"][_HOME_ID]["npxg"], 4) == 1.08
    assert got["home"]["npxg"] == 1.08          # 경기 스탯 값을 그대로 쓴다


def test_read_match_details_no_id_no_request():
    browser = FakeBrowser({"111": _match_details()})
    assert fotmob.read_match_details(browser, {"home": "A", "away": "B"}) is None
    assert browser.calls == [], "id 가 없는데 요청을 보냈다"


def test_read_match_details_caches_failure_to_avoid_refetch():
    """스탯이 없는 경기는 빈 값을 캐시해 같은 회차에서 재요청하지 않는다."""
    cache = MemCache()
    browser = FakeBrowser({"111": {"content": {"noStatsHere": True}}})
    assert fotmob.read_match_details(browser, {"id": "111"}, cache=cache) is None
    assert len(browser.calls) == 1
    assert fotmob.read_match_details(browser, {"id": "111"}, cache=cache) is None
    assert len(browser.calls) == 1, "실패를 캐시하지 않아 다시 요청했다"


def test_read_match_details_uses_cache():
    cache = MemCache()
    browser = FakeBrowser({"111": _match_details()})
    first = fotmob.read_match_details(browser, {"id": "111"}, cache=cache)
    second = fotmob.read_match_details(browser, {"id": "111"}, cache=cache)
    assert first == second
    assert len(browser.calls) == 1, "캐시가 있는데 다시 요청했다"


# --------------------------------------------------------------------------
# 5. 최근 종료 경기 고르기
# --------------------------------------------------------------------------
def _m(mid, home, away, finished=True, utc="2026-08-01T10:00:00Z"):
    return {"id": mid, "home": home, "away": away, "finished": finished,
            "utc": utc, "home_goals": 1, "away_goals": 0, "date": utc[:10]}


def test_recent_finished_filters_and_limits():
    matches = [
        _m("1", "Arsenal", "Chelsea"),
        _m("2", "Everton", "Arsenal"),
        _m("3", "Arsenal", "Liverpool", finished=False),   # 미종료 제외
        {"id": None, "home": "Arsenal", "away": "Spurs",
         "finished": True},                                # id 없음 제외
        _m("5", "Chelsea", "Liverpool"),                    # 다른 팀 제외
        _m("6", "Arsenal", "Fulham"),
    ]
    got = fotmob._recent_finished(matches, "Arsenal", 2)
    assert [m["id"] for m in got] == ["1", "2"], "최신순 앞에서 N건이어야 한다"
    assert len(fotmob._recent_finished(matches, "Arsenal", 10)) == 3


# --------------------------------------------------------------------------
# 6. 팀별 합산 — 같은 경기를 두 팀이 공유해도 요청은 1회
# --------------------------------------------------------------------------
def _teams(*names) -> dict[str, dict]:
    ids = {"Arsenal": _HOME_ID, "Chelsea": _AWAY_ID}
    return {n: {"stats": TeamStats(), "fotmob_id": str(ids.get(n, 1)),
                "page_url": ""} for n in names}


def test_attach_match_details_aggregates_both_sides_with_one_request():
    teams = _teams("Arsenal", "Chelsea")
    matches = [_m("111", "Arsenal", "Chelsea")]
    browser = FakeBrowser({"111": _match_details()})

    filled, fetched = fotmob.attach_match_details(
        browser, teams, matches, count=6, league_key="epl")

    assert (filled, fetched) == (2, 1)
    assert len(browser.calls) == 1, "같은 경기를 두 번 받았다"

    home = teams["Arsenal"]["stats"]
    away = teams["Chelsea"]["stats"]
    assert home.recent_matches == 1 and away.recent_matches == 1
    assert home.npxg_recent == 1.08 and home.npxga_recent == 0.92
    assert away.npxg_recent == 0.92 and away.npxga_recent == 1.08
    assert home.shots_recent == 16.0 and away.shots_recent == 9.0


def test_attach_match_details_sums_over_multiple_matches():
    teams = _teams("Arsenal", "Chelsea")
    matches = [_m("111", "Arsenal", "Chelsea", utc="2026-08-08T10:00:00Z"),
               _m("222", "Chelsea", "Arsenal", utc="2026-08-01T10:00:00Z")]
    browser = FakeBrowser({"111": _match_details(), "222": _match_details()})

    filled, fetched = fotmob.attach_match_details(
        browser, teams, matches, count=6, league_key="epl")
    assert (filled, fetched) == (2, 2)

    arsenal = teams["Arsenal"]["stats"]
    assert arsenal.recent_matches == 2
    # 1차전은 홈(1.08), 2차전은 원정(0.92)
    assert round(arsenal.npxg_recent, 4) == 2.00
    assert round(arsenal.npxg_recent_pg, 4) == 1.00
    assert arsenal.shots_recent == 25.0 and arsenal.shots_recent_pg == 12.5


def test_attach_match_details_skips_when_count_zero():
    teams = _teams("Arsenal", "Chelsea")
    browser = FakeBrowser({"111": _match_details()})
    got = fotmob.attach_match_details(browser, teams, [_m("111", "Arsenal", "Chelsea")],
                                      count=0, league_key="epl")
    assert got == (0, 0)
    assert browser.calls == [], "0 인데 요청을 보냈다"
    assert teams["Arsenal"]["stats"].recent_matches is None


def test_attach_match_details_survives_failed_match():
    """한 경기가 실패해도 나머지로 합산하고, 표본 크기는 성공분만 센다."""
    teams = _teams("Arsenal", "Chelsea")
    matches = [_m("111", "Arsenal", "Chelsea", utc="2026-08-08T10:00:00Z"),
               _m("999", "Chelsea", "Arsenal", utc="2026-08-01T10:00:00Z")]
    browser = FakeBrowser({"111": _match_details()})     # 999 는 None 을 돌려준다

    filled, fetched = fotmob.attach_match_details(
        browser, teams, matches, count=6, league_key="epl")
    assert (filled, fetched) == (2, 1)
    assert teams["Arsenal"]["stats"].recent_matches == 1
    assert teams["Arsenal"]["stats"].npxg_recent == 1.08


def test_check_lookup_accepts_int_and_str_team_id():
    """캐시를 거치면 JSON 이 teamId 를 문자열 키로 바꾼다. 둘 다 받아야 한다."""
    check = {_HOME_ID: {"npxg": 1.08}}
    assert fotmob._check_for(check, _HOME_ID)["npxg"] == 1.08
    assert fotmob._check_for(check, str(_HOME_ID))["npxg"] == 1.08
    assert fotmob._check_for({str(_HOME_ID): {"npxg": 1.08}}, _HOME_ID) is not None
    assert fotmob._check_for(check, "") is None
    assert fotmob._check_for(check, "not-a-number") is None
    assert fotmob._check_for(None, _HOME_ID) is None


# --------------------------------------------------------------------------
# 7. 파생값 — 재료가 없으면 None (지어내지 않는다)
# --------------------------------------------------------------------------
def test_per_recent_needs_sample_size():
    s = TeamStats(npxg_recent=6.0)
    assert s.npxg_recent_pg is None, "표본 크기 없이 경기당 값을 만들면 안 된다"
    s.recent_matches = 0
    assert s.npxg_recent_pg is None, "0 으로 나누면 안 된다"
    s.recent_matches = 4
    assert s.npxg_recent_pg == 1.5


def test_per_recent_divides_by_that_metric_own_sample():
    """지표마다 표본이 다르다 — 빠진 경기를 0 으로 치면 안 된다.

    Phase 1-B 검증에서 실제로 걸린 결함이다. 6경기를 받았지만 npxG 가
    3경기에만 있으면, 합계 3.0 을 6 으로 나눠 0.5 가 됐다. 참값은 1.0 이다.
    """
    s = TeamStats(recent_matches=6, npxg_recent=3.0, shots_recent=60.0,
                  recent_counts={"npxg_recent": 3})
    assert s.npxg_recent_pg == 1.0, "빠진 경기를 0 으로 쳤다"
    assert s.shots_recent_pg == 10.0, "표본 정보가 없는 지표는 경기 수로 나눈다"

    # 정보가 없으면(옛 캐시) recent_matches 로 되돌아간다 — 죽지 않는다
    assert TeamStats(recent_matches=6, npxg_recent=3.0).npxg_recent_pg == 0.5


def test_attach_records_per_metric_sample_size():
    """일부 경기에만 있는 지표는 그 경기 수만 센다."""
    full = _match_details()
    partial = _match_details()
    # 두 번째 경기에서 expected_goals 그룹을 통째로 뺀다 (npxG·xGOT 없음)
    partial["content"]["stats"]["Periods"]["All"]["stats"] = [
        g for g in partial["content"]["stats"]["Periods"]["All"]["stats"]
        if g["key"] != "expected_goals"]

    teams = _teams("Arsenal", "Chelsea")
    matches = [_m("111", "Arsenal", "Chelsea", utc="2026-08-08T10:00:00Z"),
               _m("222", "Arsenal", "Chelsea", utc="2026-08-01T10:00:00Z")]
    fotmob.attach_match_details(FakeBrowser({"111": full, "222": partial}),
                                teams, matches, count=6, league_key="epl")

    st = teams["Arsenal"]["stats"]
    assert st.recent_matches == 2
    assert st.recent_counts["npxg_recent"] == 1, "없는 경기까지 셌다"
    assert st.recent_counts["shots_recent"] == 2
    assert st.npxg_recent == 1.08
    assert st.npxg_recent_pg == 1.08, "1경기치를 2로 나눴다"
    assert st.shots_recent_pg == 16.0


def test_recent_counts_survives_cache_roundtrip():
    """캐시(JSON)를 거쳐도 표본 정보가 살아 있어야 한다."""
    from dataclasses import asdict
    st = TeamStats(recent_matches=6, npxg_recent=3.0,
                   recent_counts={"npxg_recent": 3})
    back = TeamStats(**json.loads(json.dumps(asdict(st))))
    assert back.npxg_recent_pg == 1.0
    # 표본 정보가 없던 옛 캐시도 되살아나야 한다 (죽지 않는 게 우선)
    old = asdict(st)
    del old["recent_counts"]
    assert TeamStats(**old).npxg_recent_pg == 0.5


def test_inside_box_share_and_xgot_delta():
    s = TeamStats(recent_matches=5, shots_inside_box_recent=45.0,
                  shots_outside_box_recent=15.0,
                  xgot_recent=7.5, npxg_recent=6.0)
    assert s.inside_box_shot_share == 75.0
    assert s.xgot_delta_recent == 1.5

    half = TeamStats(recent_matches=5, shots_inside_box_recent=45.0)
    assert half.inside_box_shot_share is None, "반쪽 재료로 비율을 만들면 안 된다"
    assert TeamStats(recent_matches=5, xgot_recent=7.5).xgot_delta_recent is None


def test_all_recent_derived_properties_exist_and_are_none_by_default():
    s = TeamStats()
    names = ["npxg_recent_pg", "npxga_recent_pg", "xgot_recent_pg",
             "xgot_against_recent_pg", "xg_open_play_recent_pg",
             "xg_set_play_recent_pg", "shots_recent_pg", "shots_against_recent_pg",
             "shots_on_target_recent_pg", "shots_on_target_against_recent_pg",
             "shots_inside_box_recent_pg", "shots_outside_box_recent_pg",
             "inside_box_shot_share", "xgot_delta_recent"]
    for name in names:
        assert getattr(s, name) is None, f"{name} 이 빈 상태에서 값을 냈다"


# --------------------------------------------------------------------------
# 8. 기존 규칙이 깨지지 않는가
# --------------------------------------------------------------------------
def test_new_fields_still_fill_only_when_empty():
    """뒤에 오는 소스가 앞 소스 값을 덮어쓰지 않는다 (CLAUDE.md §1-1)."""
    dst = TeamStats(npxg_recent=5.0, recent_matches=6)
    fill_stats(dst, TeamStats(npxg_recent=9.9, recent_matches=1, xgot_recent=8.0))
    assert dst.npxg_recent == 5.0 and dst.recent_matches == 6
    assert dst.xgot_recent == 8.0, "빈 칸은 채워야 한다"


def test_match_id_is_kept_by_parse_matches():
    """경기 상세는 id 로 요청한다. _parse_matches 가 id 를 버리면 전부 멈춘다."""
    from toto.normalize import TeamResolver
    data = {"matches": {"allMatches": [{
        "id": "4193495", "round": 3,
        "home": {"name": "Arsenal"}, "away": {"name": "Chelsea"},
        "status": {"finished": True, "scoreStr": "2 - 1",
                   "utcTime": "2026-08-01T10:00:00Z"},
    }]}}
    got = fotmob._parse_matches(data, TeamResolver())
    assert got and got[0]["id"] == "4193495"


def test_cache_version_bumped_for_new_fields():
    """파싱을 고쳤으면 캐시 버전을 올린다 (CLAUDE.md §1-4)."""
    assert fotmob._CACHE_VERSION >= 3
    # 옛 버전 캐시는 되살리지 않는다
    assert fotmob._revive({"_v": 2, "teams": {}, "matches": []}) is None


def test_season_feed_fields_exist():
    """시즌 피드에서 새로 받는 값들이 TeamStats 에 자리가 있는가."""
    s = TeamStats()
    for name in ("set_piece_goals", "set_piece_goals_conceded", "penalties_won",
                 "penalties_conceded", "yellow_cards", "red_cards",
                 "accurate_crosses_pg", "accurate_long_balls_pg"):
        assert hasattr(s, name), name
        assert getattr(s, name) is None


# --------------------------------------------------------------------------
# 9. 리포트까지 이어지는가 — 값이 없으면 블록이 통째로 빠져야 한다
# --------------------------------------------------------------------------
def _match_for_render(home_stats: TeamStats, away_stats: TeamStats):
    from toto.models import Match, TeamProfile, TeamRef
    home = TeamRef(name_ko="아스널", canonical="Arsenal", display="아스널")
    away = TeamRef(name_ko="첼시", canonical="Chelsea", display="첼시")
    m = Match(no=1, league="epl", home=home, away=away)
    m.home_profile = TeamProfile(team=home, stats=home_stats)
    m.away_profile = TeamProfile(team=away, stats=away_stats)
    return m


def test_recent_block_renders_with_sample_size():
    from toto.render import _recent_block
    from toto.settings import load_settings
    s = load_settings()
    stats = TeamStats(recent_matches=6, npxg_recent=7.2, npxga_recent=4.8,
                      shots_recent=90.0, shots_inside_box_recent=54.0,
                      shots_outside_box_recent=36.0)
    html = _recent_block(_match_for_render(stats, stats), s)
    assert "최근 경기 슈팅·xG 프로필" in html
    assert "최근 6경기 평균" in html, "표본 크기를 적어야 한다"
    assert "시즌 누계가 아닙니다" in html, "시즌 지표와 구분해 적어야 한다"
    assert "npxG(PK 제외)" in html


def test_recent_block_warns_when_sample_sizes_differ():
    from toto.render import _recent_block
    from toto.settings import load_settings
    home = TeamStats(recent_matches=6, npxg_recent=7.2)
    away = TeamStats(recent_matches=3, npxg_recent=3.0)
    html = _recent_block(_match_for_render(home, away), load_settings())
    assert "6경기(홈팀)" in html and "3경기(원정팀)" in html
    assert "주의" in html


def test_recent_block_disappears_without_match_details():
    """--skip-match-details 로 돌린 실행에서는 블록이 나오지 않는다.

    빈 표나 0 을 그리면 '값이 0 이다' 로 읽힌다 (CLAUDE.md §1-5).
    """
    from toto.render import _recent_block
    from toto.settings import load_settings
    empty = TeamStats(played=20, points=35)        # 시즌 지표만 있는 상태
    assert _recent_block(_match_for_render(empty, empty), load_settings()) == ""


def test_season_feed_metrics_are_per_game_in_compare():
    """누계를 그대로 나란히 두지 않는다 — 소화 경기수가 다르면 왜곡된다."""
    from toto.settings import load_settings
    keys = {m["key"] for m in load_settings().compare_metrics}
    assert "set_piece_goals_pg" in keys
    assert "set_piece_goals" not in keys, "누계를 비교표에 그대로 넣었다"

    s = TeamStats(played=20, goals_for=30, set_piece_goals=9.0, yellow_cards=50.0)
    assert s.set_piece_goals_pg == 0.45
    assert s.yellow_cards_pg == 2.5
    assert s.set_piece_goal_share == 30.0
    assert TeamStats(set_piece_goals=9.0).set_piece_goals_pg is None


def test_recent_and_season_metric_keys_never_overlap():
    """같은 지표가 두 블록에 섞여 표본이 뒤엉키는 일을 막는다."""
    from toto.settings import load_settings
    s = load_settings()
    season = {m["key"] for m in s.compare_metrics} | {
        m["key"] for m in s.radar_metrics}
    recent = {m["key"] for m in s.recent_metrics}
    assert not (season & recent), season & recent
    assert all("recent" in k or k == "inside_box_shot_share" for k in recent)


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
