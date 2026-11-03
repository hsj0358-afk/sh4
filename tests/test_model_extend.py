"""확장 탐색의 새 엔진 — 순위표(걸린 것) · 선수 · 시간척도 tag · 앞으로 고르기 (§1-68).

    python tests/test_model_extend.py

네트워크·캐시 파일 없이 돈다. 합성 경기로 확인한다. numpy 가 필요한 테스트는
numpy 가 없으면 SKIP 이다.
"""
from __future__ import annotations

import ast
import json
import sys
import unittest
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import arena as A                    # noqa: E402
from toto import champion as C                 # noqa: E402
from toto import history as H                  # noqa: E402
from toto import ratings as R                  # noqa: E402
from toto import stacker as S                  # noqa: E402
from test_model_arena import synth             # noqa: E402


def _m(day, home, away, hg, ag, season="2425", league="epl", **kw):
    return H.HistMatch(league=league, season=season, date=day, time="", home=home,
                       away=away, hg=hg, ag=ag, **kw)


def _round_robin(teams, start, season="2425", result=None):
    """두 번씩 맞붙는 일정. result(h, a) → (hg, ag)."""
    rows, day = [], start
    pairs = [(h, a) for h in teams for a in teams if h != a]
    for i, (h, a) in enumerate(pairs):
        hg, ag = result(h, a) if result else (1, 1)
        rows.append(_m(day + timedelta(days=i), h, a, hg, ag, season=season))
    return rows


# --------------------------------------------------------------------------
# A. 순위표 — 걸린 것
# --------------------------------------------------------------------------
def _strong_first(h, a):
    order = {"T0": 0, "T1": 1, "T2": 2, "T3": 3, "T4": 4, "T5": 5}
    return (2, 0) if order[h] < order[a] else (0, 2)


def test_a1_everyone_has_stakes_at_season_start():
    eng = R.Table()
    teams = [f"T{i}" for i in range(6)]
    first = _round_robin(teams, date(2024, 8, 1), result=_strong_first)
    R.replay(first, [eng])
    nxt = _m(date(2025, 8, 1), "T0", "T5", 0, 0, season="2526")
    f = eng.features(nxt)
    assert f["tbl_st_h"] == 1.0 and f["tbl_st_a"] == 1.0 and f["tbl_st_diff"] == 0.0
    assert f["tbl_late"] == 0.0 and f["tbl_dead_sum"] == 0.0


def test_a2_late_season_settled_teams_have_nothing_at_stake():
    """한 팀이 경계에서 남은 경기로 딸 수 있는 승점보다 멀면 0 이다."""
    eng = R.Table(rel=1, eur=1, slack=0.0)
    teams = [f"T{i}" for i in range(6)]
    prev = _round_robin(teams, date(2023, 8, 1), season="2324", result=_strong_first)
    cur = _round_robin(teams, date(2024, 8, 1), result=_strong_first)
    R.replay(prev + cur[:-2], [eng])
    last = cur[-1]                     # T5 vs T4 — 마지막 경기 전
    f = eng.features(last)
    # 우승(T0)은 이미 정해졌고 T5 는 이미 꼴찌다 → 두 팀 다 우승과 무관.
    assert f["tbl_top_diff"] == 0.0
    assert 0.0 <= f["tbl_st_h"] <= 1.0 and 0.0 <= f["tbl_st_a"] <= 1.0
    assert f["tbl_late"] >= 0.85


def test_a3_relegation_boundary_is_alive_for_both_sides():
    eng = R.Table(rel=1, eur=1, slack=3.0)
    teams = ["A", "B", "C", "D"]
    pts = {"A": 30, "B": 20, "C": 10, "D": 10}
    eng.see_season("epl", "2425")
    eng.globals["epl"] = (10.0, 4.0)                 # 시즌 10경기 · 4팀
    for t, p in pts.items():
        eng.teams[("epl", t)] = (float(p), 9.0, 0.0)
    f = eng.features(_m(date(2025, 5, 1), "C", "D", 0, 0))
    assert f["tbl_rel_diff"] == 0.0                  # 둘 다 강등 경계에 붙어 있다
    assert f["tbl_st_h"] == 1.0 and f["tbl_st_a"] == 1.0
    g = eng.features(_m(date(2025, 5, 1), "A", "C", 0, 0))
    assert g["tbl_st_h"] < g["tbl_st_a"]              # A 는 우승 확정 · C 는 강등 경계


def test_a3b_last_match_with_no_slack_does_not_divide_by_zero():
    eng = R.Table(slack=0.0)
    eng.see_season("epl", "2425")
    eng.globals["epl"] = (2.0, 2.0)
    eng.teams[("epl", "A")] = (3.0, 2.0, 1.0)
    eng.teams[("epl", "B")] = (3.0, 2.0, -1.0)
    f = eng.features(_m(date(2025, 5, 1), "A", "B", 0, 0))
    assert 0.0 <= f["tbl_st_h"] <= 1.0


def test_a4_new_season_resets_table_and_learns_length():
    eng = R.Table()
    teams = [f"T{i}" for i in range(4)]
    R.replay(_round_robin(teams, date(2024, 8, 1)), [eng])
    eng.see_season("epl", "2526")
    assert not any(k[0] == "epl" for k in eng.teams)
    assert eng.globals["epl"] == (6.0, 4.0)          # 2 × (4 − 1) 경기 · 4팀


def test_a5_state_roundtrip():
    eng = R.Table()
    rows = synth(seasons=2)
    R.replay(rows[:-5], [eng])
    back = R.Engine.from_state(json.loads(json.dumps(eng.state())))
    for m in rows[-5:]:
        assert back.features(m) == eng.features(m)


def _close(a, b, tol=1e-4):
    """상태 파일은 선수 값을 소수 다섯째 자리로 줄여 담는다."""
    assert set(a) == set(b), (a, b)
    assert all(abs(a[k] - b[k]) < tol for k in a), (a, b)


# --------------------------------------------------------------------------
# B. 선수
# --------------------------------------------------------------------------
def _lineup(home_ids, away_ids, unavailable_home=(), rating=7.0):
    def side(ids, unav):
        return {"starters": [[p, rating, None, 1] for p in ids], "subs": [],
                "unavailable": [[p, "injury"] for p in unav]}
    return {"home": side(home_ids, unavailable_home), "away": side(away_ids, ())}


def test_b1_player_values_follow_the_xg_margin():
    eng = R.Player(k=0.01)
    good, bad = [f"g{i}" for i in range(11)], [f"b{i}" for i in range(11)]
    day = date(2024, 8, 1)
    rows = []
    for i in range(40):
        h, a = (good, bad) if i % 2 == 0 else (bad, good)
        hx, ax = (2.0, 0.5) if i % 2 == 0 else (0.5, 2.0)
        rows.append(_m(day + timedelta(days=i), "G" if i % 2 == 0 else "B",
                       "B" if i % 2 == 0 else "G", 1, 1, hxg=hx, axg=ax,
                       lineup=_lineup(h, a)))
    R.replay(rows, [eng])
    assert eng.players["g0"][0] > 0 > eng.players["b0"][0]
    f = eng.features(_m(day + timedelta(days=60), "G", "B", 0, 0))
    assert f["ply_diff"] > 0 and f["ply_has"] == 1.0


def test_b2_unavailable_list_is_not_used():
    """과거 기록의 결장 명단은 경기 뒤에 정리된 것이다 — 특징에 쓰지 않는다."""
    eng = R.Player(k=0.01)
    xi = [f"g{i}" for i in range(11)]
    eng.lastxi[("epl", "G")] = list(xi)
    eng.lastxi[("epl", "B")] = [f"b{i}" for i in range(11)]
    for p in xi:
        eng.players[p] = [0.2, 5, 7.0]
    full = eng.features(_m(date(2025, 1, 1), "G", "B", 0, 0, lineup=_lineup([], [])))
    hurt = eng.features(_m(date(2025, 1, 1), "G", "B", 0, 0,
                           lineup=_lineup([], [], unavailable_home=["g0", "g1"])))
    assert full == hurt and abs(full["ply_diff"] - 2.2) < 1e-9
    src = (ROOT / "toto" / "ratings.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    consts = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
              and isinstance(n.value, str) and not n.value.startswith("\n")
              and len(n.value) < 40}
    assert "unavailable" not in consts


def test_b3_no_lineup_means_no_learning_and_no_attribute_error():
    """리포트 경로의 경기(명단 · xG 칸 없음)에서도 돈다."""
    from types import SimpleNamespace
    eng = R.Player()
    m = SimpleNamespace(league="epl", season="2425", date=date(2025, 1, 1),
                        home="G", away="B", hg=1, ag=0)
    assert eng.features(m)["ply_has"] == 0.0
    eng.update(m)
    assert eng.players == {}


def test_b4_state_roundtrip():
    eng = R.Player()
    rows = [_m(date(2024, 8, 1) + timedelta(days=i), "G", "B", 1, 0, hxg=1.0, axg=0.4,
               lineup=_lineup([f"g{j}" for j in range(11)], [f"b{j}" for j in range(11)]))
            for i in range(5)]
    R.replay(rows, [eng])
    back = R.Engine.from_state(json.loads(json.dumps(eng.state())))
    m = _m(date(2024, 9, 1), "G", "B", 0, 0)
    _close(back.features(m), eng.features(m))


# --------------------------------------------------------------------------
# C. 시간척도 tag · 확장
# --------------------------------------------------------------------------
def test_c1_tag_renames_features_and_is_absent_by_default():
    assert "tag" not in R.make({"kind": "dp", "stat": "goals"}).params
    eng = R.make({"kind": "dp", "stat": "goals", "eta": 0.06, "tag": "gf"})
    m = _m(date(2025, 1, 1), "G", "B", 0, 0)
    assert set(eng.features(m)) == {"gf_lh", "gf_la"}


def test_c2_extend_replaces_only_untagged_goals_mix():
    base = A.Candidate(name="b", kind="stack",
                       engines=[{"kind": "dp", "stat": "goals", "eta": 0.02},
                                {"kind": "dp", "stat": "goals", "eta": 0.06, "tag": "gf"}],
                       features=["goals_diff", "gf_diff"])
    out = A.extend(base, ("mix", "mix1", [], [], 1.0))
    assert out.engines[0]["mix"] == 1.0 and "mix" not in out.engines[1]
    assert base.engines[0].get("mix") is None              # 원래 후보는 그대로
    tb = A.extend(out, ("tbl", "tbl3", [{"kind": "tbl"}], ["tbl_st_diff", "gf_diff"], None))
    assert tb.features == ["goals_diff", "gf_diff", "tbl_st_diff"]
    assert tb.name == "b+mix1+tbl3"
    pi = A.extend(A.Candidate(name="p", kind="stack", engines=[{"kind": "pi", "lam": 0.03},
                                                               {"kind": "dp", "stat": "goals"}],
                              features=[]), ("pimix", "pimix1", [], [], ("pi", 1.0)))
    assert pi.engines[0]["mix"] == 1.0 and "mix" not in pi.engines[1]
    assert "mix" not in R.make({"kind": "pi"}).params


def test_c3_library_specs_build_and_features_exist():
    rows = synth(seasons=1)
    for fam, label, engines, feats, mix in A.extend_library():
        engs = [R.make(e) for e in engines]
        got = {}
        for e in engs:
            got.update(e.features(rows[0]))
        for f in feats:
            assert S._value(got, f) is not None, (label, f)


def test_c4_forward_select_uses_only_dev_years_and_one_per_family():
    try:
        import numpy  # noqa: F401
    except ImportError:
        raise unittest.SkipTest("numpy 없음")
    rows = synth(seasons=6, start_year=2015)
    store = A.FeatureStore(rows)
    base = A.Candidate(name="b", kind="stack",
                       engines=[{"kind": "elo", "k": 20, "hfa": 60, "carry": 0.8,
                                 "gd": "log"}],
                       features=["elo_diff"])
    lib = [("tbl", "tbl3", [{"kind": "tbl"}], ["tbl_st_diff"], None),
           ("fast", "fast0.06", [{"kind": "dp", "stat": "goals", "eta": 0.06, "tag": "gf"}],
            ["gf_diff", "gf_sum"], None),
           ("fast", "fast0.1", [{"kind": "dp", "stat": "goals", "eta": 0.1, "tag": "gf"}],
            ["gf_diff", "gf_sum"], None)]
    seen = []
    real = A.dev_logloss

    def spy(cand, st, years=A.DEV_YEARS):
        seen.append(tuple(years))
        return real(cand, st, years)

    A.dev_logloss = spy
    try:
        saved = A.TRAIN_FROM
        A.TRAIN_FROM = 2015
        best, steps, tried = A.forward_select(base, store, years=(2018, 2019), log=lambda *a: None,
                                              library=lib, min_gain=-1.0, max_steps=5)
    finally:
        A.dev_logloss = real
        A.TRAIN_FROM = saved
    assert set(seen) == {(2018, 2019)}
    fams = [s[0] for s in steps[1:]]
    assert len(fams) == 2                               # 가족마다 한 번 → 두 단계에서 멈춘다
    assert sum(1 for e in best.engines if e.get("tag") == "gf") == 1


# --------------------------------------------------------------------------
# D. 리포트 경로 — 명단 엔진은 FotMob 이 있어야 갱신된다
# --------------------------------------------------------------------------
def test_d1_needs_fotmob_for_lineup_and_xg_mix_engines():
    assert C.needs_fotmob({"engines": [{"kind": "ply"}]})
    assert C.needs_fotmob({"engines": [{"kind": "dp", "stat": "goals", "mix": 1.0}]})
    assert C.needs_fotmob({"engines": [{"kind": "pi", "mix": 0.5}]})
    assert not C.needs_fotmob({"engines": [{"kind": "tbl"}, {"kind": "dp", "stat": "goals"}]})


def test_d2_runtime_forecast_with_table_and_player_engines():
    """출력층 계수를 손으로 둔 상태로 리포트 경로를 돌린다 (numpy 없이)."""
    from datetime import datetime, timezone
    rows = synth(seasons=2)
    cand = A.Candidate(name="toy", kind="stack",
                       engines=[{"kind": "tbl"}, {"kind": "ply"}],
                       features=["tbl_st_diff", "ply_diff"])
    stack = S.Stacker(features=["tbl_st_diff", "ply_diff"], mean=[0.0, 0.0], std=[1.0, 1.0],
                      w_home=[0.2, 0.1], w_away=[-0.2, -0.1], b_home={"": 0.3},
                      b_away={"": -0.1})
    state, _ = C.build_state(cand, rows, stack=stack)
    state["teams"] = {"epl": {t: t for m in rows for t in (m.home, m.away)}}
    state = json.loads(json.dumps(state))
    kick = datetime(rows[-1].date.year + 1, 8, 20, 15, tzinfo=timezone.utc)
    fc, why = C.forecast_from_state(state, "epl", rows[0].home, rows[0].away, kick)
    assert fc is not None, why
    assert abs(fc.p_home + fc.p_draw + fc.p_away - 1.0) < 1e-9


def test_d3_new_engines_do_not_read_odds():
    tree = ast.parse((ROOT / "toto" / "ratings.py").read_text(encoding="utf-8"))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"odds_open", "odds_close", "odds_avg", "predict"}


def main() -> int:
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    raise SystemExit(main())
