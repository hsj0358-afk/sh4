"""휴식·경기 밀도에 유럽대회를 넣는다 — `fotmob.schedule_*` (§1-65).

시즌 색인에 국내리그 피드만 들어 있어서, 목요일 UCL 을 치른 팀의 직전 경기가
지난 주말 리그 경기로 잡혔다. 대회 피드에서 경기 목록만 받아 색인에 합친다.
국내리그 분석 모집단에는 섞이지 않는다 (§1-30).

    python tests/test_schedule_competitions.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from toto import analyze, models                                  # noqa: E402
from toto.models import (Match, SeasonMatch, TeamProfile, TeamRef,  # noqa: E402
                         TeamStats)
from toto.normalize import TeamResolver                           # noqa: E402
from toto.settings import Settings, load_settings                 # noqa: E402
from toto.sources import fotmob                                   # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "fotmob" / "continental" / "ucl_2025_2026.json"
ARSENAL_ID = 9825          # 실물 UCL 응답의 Arsenal teamId


def _resolver(tmp: Path) -> TeamResolver:
    return TeamResolver(learned_file=tmp / "teams.learned.yaml",
                        league_file=tmp / "teams.league.yaml")


def _settings(schedule=("ucl",)) -> Settings:
    return Settings(leagues={"epl": {"ko": "프리미어리그", "fotmob_id": 47},
                             "ucl": {"ko": "챔피언스리그", "type": "continental",
                                     "fotmob_id": 42}},
                    whoscored={}, fotmob={"schedule_competitions": list(schedule)})


def _row(mid, utc, home, away, home_id=None, away_id=None, finished=True):
    return {"id": mid, "utc": utc, "home_name": home, "away_name": away,
            "home_id": home_id, "away_id": away_id, "home_goals": 1 if finished else None,
            "away_goals": 0 if finished else None, "finished": finished}


def _sm(mid, comp, kickoff, home, away):
    return SeasonMatch(match_id=mid, competition=comp, kickoff=kickoff,
                       kickoff_raw="", kickoff_aware=True, home_team=home,
                       away_team=away, home_goals=1, away_goals=0, finished=True)


# ==========================================================================
# A. 설정
# ==========================================================================
def test_a1_config_lists_three_competitions():
    assert fotmob.schedule_competitions(load_settings()) == ["ucl", "uel", "conference"]


def test_a2_domestic_unknown_and_duplicates_are_skipped():
    s = _settings(schedule=("ucl", "epl", "nope", "ucl"))
    assert fotmob.schedule_competitions(s) == ["ucl"]


def test_a3_empty_config_means_nothing():
    assert fotmob.schedule_competitions(_settings(schedule=())) == []


# ==========================================================================
# B. 팀 연결
# ==========================================================================
def test_b1_real_fixture_links_by_team_id():
    with tempfile.TemporaryDirectory() as t:
        rows = fotmob._schedule_rows(json.loads(FIXTURE.read_text(encoding="utf-8")))
        parsed, links = fotmob.schedule_matches(rows, {ARSENAL_ID: "Arsenal"},
                                                _resolver(Path(t)))
    hits = [m for m in parsed if "Arsenal" in (m["home"], m["away"])]
    assert hits and hits[0]["id"] == "4947178", hits
    assert links["id"] >= 1


def test_b2_unknown_opponent_is_kept_as_blank_not_invented():
    rows = [_row("1", "2026-10-01T19:00:00Z", "Zzyzx United", "Arsenal FC",
                 home_id=1, away_id=ARSENAL_ID)]
    with tempfile.TemporaryDirectory() as t:
        parsed, _ = fotmob.schedule_matches(rows, {ARSENAL_ID: "Arsenal"},
                                            _resolver(Path(t)))
    assert len(parsed) == 1
    assert parsed[0]["home"] == "" and parsed[0]["away"] == "Arsenal"


def test_b3_both_unknown_is_dropped():
    rows = [_row("1", "2026-10-01T19:00:00Z", "Zzyzx United", "Qwerty FC", 1, 2)]
    with tempfile.TemporaryDirectory() as t:
        parsed, _ = fotmob.schedule_matches(rows, {}, _resolver(Path(t)))
    assert parsed == []


def test_b4_names_resolve_strictly():
    """`Rangers` 가 `Angers` 에 붙지 않는다 (§1-29)."""
    rows = [_row("1", "2026-10-01T19:00:00Z", "Rangers", "Zzyzx United", 1, 2)]
    with tempfile.TemporaryDirectory() as t:
        r = _resolver(Path(t))
        parsed, _ = fotmob.schedule_matches(rows, {}, r)
        assert parsed == []
        assert not r._dirty                  # 학습하지 않는다


def test_b5_id_wins_over_name():
    rows = [_row("1", "2026-10-01T19:00:00Z", "Chelsea", "X", ARSENAL_ID, 2)]
    with tempfile.TemporaryDirectory() as t:
        parsed, links = fotmob.schedule_matches(rows, {ARSENAL_ID: "Arsenal"},
                                                _resolver(Path(t)))
    assert parsed[0]["home"] == "Arsenal" and links["id"] == 1


# ==========================================================================
# C. 휴식 — 대회를 가로지른다, 분석 모집단은 그대로
# ==========================================================================
def _mixed_season():
    utc = timezone.utc
    season = [_sm("d1", "epl", datetime(2026, 9, 26, 14, 0, tzinfo=utc),
                  "Arsenal", "Chelsea")]
    rows = [_row("u1", "2026-09-30T19:00:00Z", "Zzyzx United", "Arsenal",
                 home_id=1, away_id=ARSENAL_ID)]
    with tempfile.TemporaryDirectory() as t:
        parsed, _ = fotmob.schedule_matches(rows, {ARSENAL_ID: "Arsenal"},
                                            _resolver(Path(t)))
    fotmob.merge_season(season, parsed, "ucl")
    return season


def test_c1_previous_match_is_the_ucl_one():
    season = _mixed_season()
    kickoff = datetime(2026, 10, 4, 14, 0, tzinfo=timezone.utc)
    ctx = models.rest_context(season, "Arsenal", kickoff)
    assert ctx.previous_competition == "ucl"
    assert ctx.rest_hours == 3 * 24 + 19
    assert ctx.rest_days == 3
    # 리그만 보면 8일 — 고치기 전에 리포트에 나오던 값
    league_only = models.rest_context(season, "Arsenal", kickoff, competition="epl")
    assert league_only.rest_days == 8


def test_c2_domestic_population_excludes_ucl():
    season = _mixed_season()
    scoped, _ = models.scope_to_competition(season, "epl")
    assert [m.match_id for m in scoped] == ["d1"]


def test_c3_build_rest_days_carries_competition():
    season = _mixed_season()
    m = Match(no=1, home=TeamRef(display="아스널", canonical="Arsenal"),
              away=TeamRef(display="X", canonical="Chelsea"))
    m.kickoff_kst = "2026-10-04 23:00"
    m.home_profile = TeamProfile(team=m.home)
    m.away_profile = TeamProfile(team=m.away)
    analyze.build_rest_days([m], season)
    assert m.home_profile.previous_competition == "ucl"
    assert m.home_profile.rest_days == 3
    assert m.away_profile.previous_competition == "epl"


# ==========================================================================
# D. enrich — 시즌 색인을 받는 실행에서만 받는다
# ==========================================================================
class _FakeBrowser:
    available = True

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _run(season_out, schedule_rows):
    calls = []
    match = Match(no=1, home=TeamRef(display="H", canonical="Arsenal"),
                  away=TeamRef(display="A", canonical="Chelsea"))
    match.league = "epl"
    match.home_profile = TeamProfile(team=match.home)
    match.away_profile = TeamProfile(team=match.away)
    feed = {"teams": {"Arsenal": {"stats": TeamStats(), "form": [],
                                  "fotmob_id": str(ARSENAL_ID), "page_url": ""},
                      "Chelsea": {"stats": TeamStats(), "form": [],
                                  "fotmob_id": "8455", "page_url": ""}},
            "matches": []}
    saved = fotmob.FotMobBrowser, fotmob.read_league, fotmob._read_schedule
    fotmob.FotMobBrowser = _FakeBrowser
    fotmob.read_league = lambda b, s, key, r, cache=None: feed
    fotmob._read_schedule = (lambda b, s, key, r, c:
                             (calls.append(key), schedule_rows)[1])
    try:
        with tempfile.TemporaryDirectory() as t:
            fotmob.enrich([match], _settings(), _resolver(Path(t)), cache=None,
                          season_out=season_out)
    finally:
        fotmob.FotMobBrowser, fotmob.read_league, fotmob._read_schedule = saved
    return calls


def test_d1_enrich_merges_ucl_into_season_index():
    season = []
    rows = [_row("u1", "2026-09-30T19:00:00Z", "Zzyzx United", "Arsenal",
                 home_id=1, away_id=ARSENAL_ID)]
    assert _run(season, rows) == ["ucl"]
    assert [(m.match_id, m.competition, m.away_team) for m in season] == \
        [("u1", "ucl", "Arsenal")]


def test_d2_no_season_index_no_request():
    assert _run(None, []) == []


def test_d3_failed_competition_adds_nothing():
    season = []
    assert _run(season, None) == ["ucl"]
    assert season == []


def test_d4_cache_holds_unresolved_rows():
    class Cache:
        def __init__(self):
            self.store = {}

        def get(self, ns, key):
            return self.store.get((ns, key))

        def set(self, ns, key, value):
            self.store[(ns, key)] = value

    c = Cache()
    rows = [_row("u1", "2026-09-30T19:00:00Z", "A", "B", 1, 2)]
    c.set("fotmob", "schedule_ucl", {"_v": fotmob._CACHE_VERSION, "rows": rows})
    got = fotmob._read_schedule(None, _settings(), "ucl", None, c)
    assert got == rows
    c.set("fotmob", "schedule_ucl", {"_v": -1, "rows": rows})
    # 판이 다르면 캐시를 쓰지 않고 받으러 간다 — 리그 ID 를 못 정하면 None (실패)
    saved = fotmob.resolve_league_id
    fotmob.resolve_league_id = lambda *a, **k: None
    try:
        assert fotmob._read_schedule(None, _settings(), "ucl", None, c) is None
    finally:
        fotmob.resolve_league_id = saved


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    raise SystemExit(main())
