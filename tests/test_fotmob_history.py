"""FotMob 경기별 기록 — `toto/fmhistory.py` (§1-68).

    python tests/test_fotmob_history.py

네트워크 없이 돈다. 경기 상세는 실물 응답(2026-11-03)의 **모양**을 옮겨 적은
작은 픽스처다 — 원본은 저장소에 넣지 않는다.
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from toto import fmhistory as F        # noqa: E402
from toto import history as H          # noqa: E402
from toto import ratings as R          # noqa: E402


def detail(mid=1, home=(10, "Alpha FC"), away=(20, "Beta United"), score=(2, 1),
           xg=("1.84", "0.62"), coverage="xG", unavailable=()):
    def stat(key, title, vals):
        return {"key": key, "title": title, "stats": list(vals)}
    return {
        "general": {"matchId": str(mid), "coverageLevel": coverage,
                    "matchTimeUTCDate": "2024-09-14T14:00:00.000Z"},
        "header": {"teams": [{"name": home[1], "id": home[0], "score": score[0]},
                             {"name": away[1], "id": away[0], "score": score[1]}]},
        "content": {
            "stats": {"Periods": {
                "All": {"stats": [
                    {"title": "Top stats", "key": "top_stats", "stats": [
                        stat("BallPossesion", "Ball possession", [55, 45]),
                        stat("expected_goals", "xG", list(xg)),
                        stat("total_shots", "Total shots", [14, 7]),
                        stat("big_chance", "Big chances", [3, 1])]},
                    {"title": "Expected goals (xG)", "key": "expected_goals", "stats": [
                        stat("expected_goals", "xG", [None, None]),
                        stat("expected_goals_non_penalty", "npxG", ["1.08", "0.62"]),
                        stat("expected_goals_on_target", "xGOT", ["2.10", "0.40"])]},
                    {"title": "Passes", "key": "passes", "stats": [
                        stat("touches_opp_box", "Touches", [31, 12])]}]},
                # 전반 표 — 이 값을 읽으면 틀린다 (§1-1-2)
                "FirstHalf": {"stats": [{"title": "Top stats", "key": "top_stats", "stats": [
                    stat("expected_goals", "xG", ["0.30", "0.10"])]}]}}},
            "lineup": {
                "homeTeam": {"id": home[0], "rating": 7.1, "formation": "4-3-3",
                             "starters": [{"id": 1, "usualPlayingPositionId": 0,
                                           "performance": {"rating": 7.0,
                                                           "substitutionEvents": [{"time": 70, "type": "subOut"}]}}],
                             "subs": [{"id": 2, "usualPlayingPositionId": 3,
                                       "performance": {"rating": 6.5,
                                                       "substitutionEvents": [{"time": 70, "type": "subIn"}]}},
                                      {"id": 3, "performance": {}}],
                             "unavailable": [{"id": 9, "unavailability": {"type": "injury"}}
                                             for _ in unavailable],
                             "coach": {"id": 77}},
                "awayTeam": {"id": away[0], "rating": 6.4, "formation": "4-4-2",
                             "starters": [], "subs": [], "unavailable": [],
                             "coach": {"id": 88}}}},
    }


def fixture(mid=1, home=(10, "Alpha FC"), away=(20, "Beta United"), day="2024-09-14"):
    return {"id": str(mid), "home": {"id": str(home[0]), "name": home[1]},
            "away": {"id": str(away[0]), "name": away[1]},
            "status": {"utcTime": f"{day}T14:00:00Z", "finished": True}}


# --------------------------------------------------------------------------
def test_a1_compact_reads_whole_match_table_only():
    rec = F.compact(detail(), fixture(), "epl", "2024/2025")
    st = rec["stats"]
    assert st["xg"] == [1.84, 0.62]                      # 전반 0.30 이 아니다
    assert st["npxg"] == [1.08, 0.62] and st["xgot"] == [2.10, 0.40]
    assert st["big_chances"] == [3.0, 1.0] and st["touches_box"] == [31.0, 12.0]
    assert rec["score"] == [2, 1] and rec["coverage"] == "xG"
    assert rec["detail_ids"] == [10, 20]


def test_a2_lineup_minutes_and_unavailable():
    rec = F.compact(detail(unavailable=[1]), fixture(), "epl", "2024/2025")
    h = rec["lineup"]["home"]
    assert h["starters"] == [[1, 7.0, 70, 0]]
    assert h["subs"] == [[2, 6.5, 70, 3]]                # 뛰지 않은 교체는 빠진다
    assert h["unavailable"] == [[9, "injury"]] and h["coach"] == 77


def test_a3_missing_xg_stays_missing():
    d = detail(coverage="ratings")
    for sec in d["content"]["stats"]["Periods"]["All"]["stats"]:
        sec["stats"] = [x for x in sec["stats"] if not x["key"].startswith("expected")]
    rec = F.compact(d, fixture(), "epl", "2018/2019")
    assert "xg" not in rec["stats"] and "npxg" not in rec["stats"]
    assert F._values(rec).get("hxg") is None


def test_a4_season_start():
    assert F.season_start("2020/2021") == 2020 and F.season_start("2022") == 2022
    assert F.season_start("x") == 0


# --------------------------------------------------------------------------
class FakeFetcher:
    def __init__(self, fixtures):
        self.fixtures, self.requests, self.calls = fixtures, 0, []

    def get_json(self, path):
        self.calls.append(path)
        self.requests += 1
        if "matchDetails" in path:
            mid = int(path.split("=")[-1])
            fx = next(f for f in self.fixtures if f["id"] == str(mid))
            return detail(mid=mid, home=(int(fx["home"]["id"]), fx["home"]["name"]),
                          away=(int(fx["away"]["id"]), fx["away"]["name"]))
        if "season=" in path:
            return {"details": {"selectedSeason": "2024/2025"},
                    "fixtures": {"allMatches": self.fixtures}}
        return {"allAvailableSeasons": ["2024/2025", "2019/2020"]}


def test_b1_fetch_resumes_and_skips_old_seasons():
    fxs = [fixture(i, (10 + i, f"H{i}"), (50 + i, f"A{i}")) for i in range(1, 6)]
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        ff = FakeFetcher(fxs)
        out = F.fetch(["epl"], cache_dir=d, limit=3, log_fn=lambda *_: None,
                      fetcher=ff, workers=1)
        assert out["new"] == 3
        assert not any("2019" in c for c in ff.calls)       # xG 이전 시즌은 받지 않는다
        ff2 = FakeFetcher(fxs)
        out = F.fetch(["epl"], cache_dir=d, log_fn=lambda *_: None, fetcher=ff2, workers=1)
        assert out["new"] == 2 and out["skipped"] == 3
        assert len([c for c in ff2.calls if "matchDetails" in c]) == 2
        assert len(F.load(["epl"], cache_dir=d)) == 5


def test_b1b_since_fetches_only_recent_matches():
    days = ["2024-08-20", "2024-09-01", "2024-09-20", "2024-10-05"]
    fxs = [fixture(i + 1, (10 + i, f"H{i}"), (50 + i, f"A{i}"), day=d)
           for i, d in enumerate(days)]
    with tempfile.TemporaryDirectory() as tmp:
        ff = FakeFetcher(fxs)
        out = F.fetch(["epl"], cache_dir=Path(tmp), log_fn=lambda *_: None, fetcher=ff,
                      workers=1, since=date(2024, 9, 15))
        assert out["new"] == 2
        assert {r["id"] for r in F.load(["epl"], cache_dir=Path(tmp))} == {"3", "4"}


def test_b2_wrong_season_reply_is_not_stored():
    class Wrong(FakeFetcher):
        def get_json(self, path):
            data = super().get_json(path)
            if "season=" in path:
                data["details"]["selectedSeason"] = "2026/2027"
            return data
    with tempfile.TemporaryDirectory() as tmp:
        out = F.fetch(["epl"], cache_dir=Path(tmp), log_fn=lambda *_: None,
                      fetcher=Wrong([fixture()]), workers=1)
        assert out["new"] == 0 and F.load(["epl"], cache_dir=Path(tmp)) == []


# --------------------------------------------------------------------------
def _fd(day, home, away, hg, ag, league="epl", season="2425"):
    return H.HistMatch(league=league, season=season, date=date.fromisoformat(day),
                       time="", home=home, away=away, hg=hg, ag=ag)


def _rec(mid, day, home, away, score, xg=(1.5, 0.5), league="epl"):
    return {"id": str(mid), "league": league, "season": "2024/2025",
            "utc": f"{day}T14:00:00Z", "home": {"id": home[0], "name": home[1]},
            "away": {"id": away[0], "name": away[1]}, "detail_ids": [home[0], away[0]],
            "score": list(score), "stats": {"xg": list(xg)}, "lineup": {}}


def test_c1_attach_joins_by_date_score_and_name_votes():
    days = ["2024-08-1" + str(i) for i in range(6)]
    fd, recs = [], []
    for i, day in enumerate(days):                         # 같은 팀 짝을 여러 번
        fd.append(_fd(day, "Man City", "Spurs", i, 0))
        recs.append(_rec(100 + i, day, (1, "Manchester City"), (2, "Tottenham"), (i, 0),
                         xg=(1.0 + i, 0.3)))
    # 같은 날 같은 스코어 경기가 둘 — 이름 표로 가른다
    fd.append(_fd("2024-09-01", "Man City", "Spurs", 1, 1))
    fd.append(_fd("2024-09-01", "Spurs", "Man City", 1, 1))
    recs.append(_rec(200, "2024-09-01", (1, "Manchester City"), (2, "Tottenham"), (1, 1), xg=(2.2, 0.9)))
    recs.append(_rec(201, "2024-09-01", (2, "Tottenham"), (1, "Manchester City"), (1, 1), xg=(0.4, 1.7)))
    out, st, used = F.attach(fd, recs)
    by = {(m.date.isoformat(), m.home): m for m in out}
    assert by[("2024-08-13", "Man City")].hxg == 4.0
    assert by[("2024-09-01", "Man City")].hxg == 2.2
    assert by[("2024-09-01", "Spurs")].hxg == 0.4
    assert st["joined"] == 8 and len(used) == 8


def test_c2_score_mismatch_is_not_joined():
    days = ["2024-08-01", "2024-08-15", "2024-09-01", "2024-09-15"]
    fd = [_fd(d, "A", "B", 1, 0) for d in days]
    recs = [_rec(i, d, (1, "A"), (2, "B"), (1, 0)) for i, d in enumerate(days[:3])]
    recs.append(_rec(9, days[3], (1, "A"), (2, "B"), (3, 3)))   # 다른 결과
    out, st, _ = F.attach(fd, recs)
    assert out[3].hxg is None and st["joined"] == 3


def test_c3_reversed_orientation_is_dropped():
    r = _rec(1, "2024-08-10", (1, "A"), (2, "B"), (1, 0))
    r["detail_ids"] = [2, 1]                                 # 경기 상세는 반대라고 말한다
    out, st, _ = F.attach([_fd("2024-08-10", "A", "B", 1, 0)], [r])
    assert out[0].hxg is None


def test_c4_fd_values_are_not_overwritten():
    m = H.HistMatch(league="epl", season="2627", date=date(2026, 8, 21), time="",
                    home="A", away="B", hg=1, ag=0, hxg=1.88, axg=0.2)
    r = _rec(1, "2026-08-21", (1, "A"), (2, "B"), (1, 0), xg=(9.0, 9.0))
    r["stats"]["npxg"] = [1.5, 0.2]
    out, _, _ = F.attach([m], [r])
    assert out[0].hxg == 1.88 and out[0].hnpxg == 1.5


def test_c5_kleague_rows_come_from_fotmob_only():
    recs = [_rec(1, "2024-03-02", (5, "Ulsan HD"), (6, "Jeonbuk"), (2, 0), league="kleague1")]
    rows = F.to_hist(recs, {"kleague1"})
    assert len(rows) == 1 and rows[0].home == "Ulsan HD" and rows[0].hxg == 1.5
    assert rows[0].season == "2024/2025" and rows[0].fm_id == "1"


# --------------------------------------------------------------------------
def test_c6_missing_fd_season_is_filled_with_fd_names():
    """football-data 가 통째로 빠뜨린 시즌(J리그 2026 특별 시즌)은 FotMob 으로 채운다."""
    fd, recs = [], []
    day = date(2025, 3, 1)
    for i in range(4):
        d = day.replace(day=1 + 7 * i)
        fd.append(_fd(d.isoformat(), "Kashima", "Urawa", 1, 0, league="jleague", season="2025"))
        r = _rec(str(100 + i), d.isoformat(), (1, "Kashima Antlers"), (2, "Urawa Reds"), [1, 0],
                 league="jleague")
        r["season"] = "2025"
        recs.append(r)
    gap = _rec("900", "2026-03-01", (2, "Urawa Reds"), (1, "Kashima Antlers"), [2, 2],
               league="jleague")
    gap["season"] = "2026"
    odd = _rec("901", "2026-03-08", (2, "Urawa Reds"), (77, "New Club"), [0, 1],
               league="jleague")
    odd["season"] = "2026"
    rows, st = F.combined(fd, recs + [gap, odd], extra_leagues=())
    got = [m for m in rows if m.season == "2026"]
    assert st["gap_rows"] == 1 and len(got) == 1
    assert (got[0].home, got[0].away, got[0].hg, got[0].ag) == ("Urawa", "Kashima", 2, 2)
    # 기간이 football-data 와 겹치면 채우지 않는다.
    late = _fd("2026-03-02", "Kashima", "Urawa", 0, 0, league="jleague", season="2026")
    rows2, st2 = F.combined(fd + [late], recs + [gap], extra_leagues=())
    assert st2["gap_rows"] == 0


def test_d1_xg_engine_skips_matches_without_xg():
    rows = [_fd("2024-08-10", "A", "B", 3, 0)]
    eng = R.DynPoisson("xg")
    R.replay(rows, [eng])
    assert all(v == (0.0, 0.0) for v in eng.teams.values())
    lin = R.LinRating("rating")
    R.replay(rows, [lin])
    assert all(v == (0.0,) for v in lin.teams.values())


def test_d2_lin_engine_learns_margin():
    rows = [H.HistMatch(league="epl", season="2425", date=date(2024, 8, 10 + i), time="",
                        home="A", away="B", hg=1, ag=0, hxg=2.0, axg=0.5)
            for i in range(10)]
    lin = R.LinRating("xgd", k=0.1, hfa_lr=0.0)
    R.replay(rows, [lin])
    assert lin.teams[("epl", "A")][0] > lin.teams[("epl", "B")][0]


def test_e1_no_new_parser_and_no_raw_storage():
    src = (ROOT / "toto" / "fmhistory.py").read_text(encoding="utf-8")
    assert "_match_stat_pairs" in src and "_home_away_ids" in src
    tree = ast.parse(src)
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "write_bytes" not in names                          # 원본을 쌓지 않는다


def test_e2_league_ids_are_the_verified_ones():
    assert F.LEAGUES["epl"][0] == 47 and F.LEAGUES["seriea"][0] == 55
    assert F.LEAGUES["kleague1"][0] == 9080
    assert "kleague2" not in F.LEAGUES                          # xG 가 없다


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    raise SystemExit(main())
