"""예측 모델 경기장 · 챔피언 — `toto/history.py` · `ratings.py` · `stacker.py` ·
`arena.py` · `champion.py` · `tools/model_arena.py` (§1-67).

    python tests/test_model_arena.py

네트워크·캐시 파일 없이 돈다. 합성 시즌으로 확인한다. numpy 가 필요한
테스트(출력층 맞추기 · 경기장)는 numpy 가 없으면 SKIP 이다.
"""
from __future__ import annotations

import ast
import json
import math
import random
import subprocess
import sys
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from toto import champion as C                 # noqa: E402
from toto import history as H                  # noqa: E402
from toto import ratings as R                  # noqa: E402
from toto import stacker as S                  # noqa: E402
from toto.models import Match, Report, SeasonMatch, TeamRef   # noqa: E402

UTC = timezone.utc


def _need_numpy():
    try:
        import numpy  # noqa: F401
    except ImportError:
        raise unittest.SkipTest("numpy 없음 — 경기장 전용")


def _pois(rng, lam):
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p < limit:
            return k
        k += 1


def synth(seasons=4, teams=12, league="epl", seed=3, start_year=2010,
          strength=None, relegate=0):
    """두 번씩 맞붙는 합성 리그. 시즌마다 하위 `relegate` 팀을 새 팀으로 바꾼다."""
    rng = random.Random(seed)
    names = [f"T{i:02d}" for i in range(teams)]
    st = strength or {t: math.exp(0.08 * (i - teams / 2)) for i, t in enumerate(names)}
    rows, newc = [], 0
    for s in range(seasons):
        y = start_year + s
        code = H.season_code(y)
        pairs = [(h, a) for h in names for a in names if h != a]
        rng.shuffle(pairs)
        day = date(y, 8, 10)
        for i, (h, a) in enumerate(pairs):
            d = day + timedelta(days=7 * (i // (teams // 2)))
            lh, la = 1.45 * st[h] / st[a], 1.1 * st[a] / st[h]
            rows.append(H.HistMatch(
                league=league, season=code, date=d, time="15:00", home=h, away=a,
                hg=_pois(rng, lh), ag=_pois(rng, la),
                hs=_pois(rng, lh * 9), as_=_pois(rng, la * 9),
                hst=_pois(rng, lh * 3), ast=_pois(rng, la * 3)))
        if relegate:
            weakest = sorted(names, key=lambda t: st[t])[:relegate]
            for t in weakest:
                names.remove(t)
                newc += 1
                n = f"N{newc:02d}"
                names.append(n)
                st[n] = st[t] * 0.95
    rows.sort(key=lambda m: (m.date, m.league, m.home, m.away))
    return rows


# --------------------------------------------------------------------------
# A. 과거 기록 읽기
# --------------------------------------------------------------------------
def test_a1_parse_main_format():
    text = ("Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HS,AS,HST,AST,PSH,PSD,PSA,"
            "PSCH,PSCD,PSCA,AvgH,AvgD,AvgA\n"
            "E0,09/08/2019,20:00,Liverpool,Norwich,4,1,H,15,12,7,5,1.14,10.0,21.0,"
            "1.13,10.5,22.0,1.15,9.0,19.0\n"
            "E0,10/08/19,,Arsenal,Spurs,,,,,,,,,,,,,,,,\n")
    rows = H.parse(text, "epl", "1920")
    assert len(rows) == 1                       # 스코어 없는 줄은 담지 않는다
    m = rows[0]
    assert m.date == date(2019, 8, 9) and m.result == "H"
    assert m.hst == 7 and m.ast == 5
    assert m.odds_open == (1.14, 10.0, 21.0)
    assert m.odds_close == (1.13, 10.5, 22.0)
    assert m.odds_avg == (1.15, 9.0, 19.0)


def test_a2_two_digit_year_and_missing_values_stay_none():
    text = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nSP1,02/09/00,Betis,Celta,0,0\n"
    m = H.parse(text, "laliga", "0001")[0]
    assert m.date == date(2000, 9, 2) and m.result == "D"
    assert m.hs is None and m.hst is None and m.odds_open is None


def test_a3_extra_league_format():
    text = ("Country,League,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA\n"
            "Japan,J1 League,2026/2027,15/08/2026,11:00,Kashima,Urawa,2,1,H,2.1,3.3,3.6\n")
    m = H.parse(text, "jleague", "x")[0]
    assert m.season == "2026/2027" and m.odds_close == (2.1, 3.3, 3.6)
    assert m.odds_open is None


def test_a4_season_codes():
    assert H.season_code(2025) == "2526" and H.season_code(1999) == "9900"
    assert H.current_season_start(date(2026, 11, 3)) == 2026
    assert H.current_season_start(date(2026, 3, 1)) == 2025
    assert H.season_codes(2024, 2026) == ["2425", "2526", "2627"]


def test_a5_bad_odds_rejected():
    text = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,PSH,PSD,PSA\nE0,01/01/20,A,B,1,0,1.0,3,4\n"
    assert H.parse(text, "epl", "1920")[0].odds_open is None


# --------------------------------------------------------------------------
# B. 평점 엔진 — 미래를 보지 않는다
# --------------------------------------------------------------------------
def _engines():
    return [R.Elo(), R.Pi(), R.DynPoisson("goals"), R.DynPoisson("sot")]


def test_b1_features_ignore_own_and_future_results():
    rows = synth(seasons=2)
    base = [f for _, f in R.replay(rows, _engines())]
    cut = len(rows) // 2
    day = rows[cut].date
    changed = [replace(m, hg=9, ag=0, hst=20) if m.date >= day else m for m in rows]
    after = [f for _, f in R.replay(changed, _engines())]
    for i, m in enumerate(rows):
        if m.date <= day:
            assert after[i] == base[i], (i, m.date)      # 그 날짜까지의 특징은 같다
    assert any(after[i] != base[i] for i, m in enumerate(rows) if m.date > day)


def test_b2_same_day_matches_do_not_see_each_other():
    rows = synth(seasons=1)
    day = rows[40].date
    same = [i for i, m in enumerate(rows) if m.date == day]
    assert len(same) > 1
    base = [f for _, f in R.replay(rows, _engines())]
    first = same[0]
    flipped = list(rows)
    flipped[first] = replace(rows[first], hg=0, ag=7)
    after = [f for _, f in R.replay(flipped, _engines())]
    for i in same:
        assert after[i] == base[i]


def test_b3_deterministic():
    rows = synth(seasons=2)
    a = [f for _, f in R.replay(rows, _engines())]
    b = [f for _, f in R.replay(rows, _engines())]
    assert a == b


def test_b4_learns_strength():
    rows = synth(seasons=3)
    elo = R.Elo()
    R.replay(rows, [elo])
    r = {t: v[0] for (lg, t), v in elo.teams.items()}
    assert r["T11"] > r["T00"]


def test_b5_promoted_team_starts_from_bottom_not_mean():
    rows = synth(seasons=3, relegate=2)
    elo = R.Elo(carry=1.0)
    seen = {}

    def grab(m, f):
        if m.home.startswith("N") and m.home not in seen:
            seen[m.home] = f["elo_diff"]
    first_new = next(m for m in rows if m.home.startswith("N"))
    R.replay(rows, [elo], on_features=grab)
    lg = elo.leagues["epl"]
    assert lg.prior is not None and lg.prior[0] < 0       # 하위 팀 평균은 평균 아래
    assert first_new.season != rows[0].season


def test_b6_state_roundtrip():
    rows = synth(seasons=2)
    engines = _engines()
    R.replay(rows, engines)
    target = rows[-1]
    for e in engines:
        clone = R.Engine.from_state(json.loads(json.dumps(e.state())))
        assert clone.features(target) == e.features(target)


def test_b7_missing_shots_skip_update():
    rows = synth(seasons=1)
    eng = R.DynPoisson("sot")
    R.replay([replace(m, hst=None, ast=None) for m in rows], [eng])
    assert all(v == (0.0, 0.0) for v in eng.teams.values())


def test_b8_season_regression_pulls_to_mean():
    rows = synth(seasons=2)
    s1 = [m for m in rows if m.season == rows[0].season]
    elo = R.Elo(carry=0.5)
    R.replay(s1, [elo])
    before = {t: v[0] for (lg, t), v in elo.teams.items()}
    nxt = next(m for m in rows if m.season != rows[0].season)
    elo.see_season("epl", nxt.season)
    after = {t: v[0] for (lg, t), v in elo.teams.items()}
    mean = sum(before.values()) / len(before)
    for t in before:
        assert abs(after[t] - mean) <= abs(before[t] - mean) * 0.5 + 1e-9


# --------------------------------------------------------------------------
# C. 출력층
# --------------------------------------------------------------------------
def test_c1_derive_names():
    raw = {"goals_lh": 0.5, "goals_la": 0.1, "elo_diff": -2.0}
    assert S.derive(raw, ["goals_diff", "goals_sum", "abs:elo_diff"]) == [0.4, 0.6, 2.0]
    assert S.derive(raw, ["sot_diff"]) is None


def test_c2_predict_is_distribution_pure_python():
    st = S.Stacker(features=["x"], mean=[0.0], std=[1.0], w_home=[0.8], w_away=[-0.8],
                   b_home={"": 0.4}, b_away={"": 0.1})
    p = st.predict([1.0], "epl")
    assert abs(sum(p) - 1) < 1e-12 and p[0] > p[2]
    assert st.predict([-3.0])[2] > st.predict([-3.0])[0]


def test_c3_fit_learns_direction_and_roundtrips():
    _need_numpy()
    rng = random.Random(1)
    X, y, lg = [], [], []
    for _ in range(3000):
        x = rng.gauss(0, 1)
        zh, za = 0.3 + 1.2 * x, -0.2 - 1.2 * x
        e = [math.exp(zh), 1.0, math.exp(za)]
        u = rng.random() * sum(e)
        y.append("H" if u < e[0] else "D" if u < e[0] + e[1] else "A")
        X.append([x])
        lg.append("epl" if rng.random() < 0.5 else "laliga")
    st = S.fit(X, y, lg, ["x"], l2=0.1)
    assert st.w_home[0] > 0.8 and st.w_away[0] < -0.8
    back = S.Stacker.from_dict(json.loads(json.dumps(st.to_dict())))
    assert back.predict([0.3], "epl") == st.predict([0.3], "epl")
    assert set(st.b_home) == {"", "epl", "laliga"}


# --------------------------------------------------------------------------
# D. 경기장
# --------------------------------------------------------------------------
def test_d1_fyear():
    from toto import arena as A
    assert A.fyear(date(2025, 7, 1)) == 2025 and A.fyear(date(2025, 6, 30)) == 2024


def test_d2_walk_forward_trains_only_on_earlier_seasons():
    _need_numpy()
    from toto import arena as A
    rows = synth(seasons=6, start_year=2001)
    store = A.FeatureStore(rows)
    cand = A.solo({"kind": "elo", "k": 20, "hfa": 60, "carry": 0.8, "gd": "log"})
    models = {}
    X = [S.derive(f, cand.features) for f in store.merged(cand.engines)]
    A._walk_stack(rows, X, cand, {2004, 2005}, keep_models=models)
    for year, model in models.items():
        n_before = sum(1 for m in rows if A.TRAIN_FROM <= A.fyear(m.date) < year)
        assert model.meta["n"] == n_before
    # 시험 시즌의 결과를 바꿔도 그 시즌 예측은 같다
    p1 = A.predict(cand, store, {2005})
    changed = [replace(m, hg=0, ag=5) if A.fyear(m.date) >= 2005 else m for m in rows]
    p2 = A.predict(cand, A.FeatureStore(changed), {2005})
    first = min(i for i, m in enumerate(rows) if A.fyear(m.date) == 2005)
    day = rows[first].date
    for i, m in enumerate(rows):
        if m.date == day:
            assert p1[i] == p2[i]


def test_d3_losses_known_values():
    from toto import arena as A
    ll, rps, brier, hit = A.losses((0.5, 0.3, 0.2), "H")
    assert abs(ll + math.log(0.5)) < 1e-12
    assert abs(rps - 0.5 * (0.25 + 0.04)) < 1e-12
    assert abs(brier - (0.25 + 0.09 + 0.04)) < 1e-12 and hit == 1.0
    assert A.losses((0.5, 0.3, 0.2), "D")[3] == 0.0


def test_d4_compare_is_paired_and_signed():
    _need_numpy()
    from toto import arena as A
    rows = synth(seasons=1)
    good = [(0.9, 0.05, 0.05) if m.result == "H" else (0.05, 0.9, 0.05)
            if m.result == "D" else (0.05, 0.05, 0.9) for m in rows]
    flat = [(1 / 3, 1 / 3, 1 / 3)] * len(rows)
    idx = list(range(len(rows)))
    r = A.compare(rows, flat, good, idx, resamples=300)
    assert r["d_logloss"] > 0 and r["p_b_better"] == 1.0 and A.gate(r)
    r2 = A.compare(rows, good, flat, idx, resamples=300)
    assert r2["d_logloss"] < 0 and not A.gate(r2)
    partial = [None] * 10 + flat[10:]
    assert A.compare(rows, partial, good, idx, resamples=50)["n"] == len(rows) - 10


def test_d5_dc_probs_sum_and_rho_adds_draws():
    from toto import arena as A
    p0 = A.dc_probs(1.3, 1.1)
    p1 = A.dc_probs(1.3, 1.1, rho=-0.1)
    assert abs(sum(p0) - 1) < 1e-12 and abs(sum(p1) - 1) < 1e-12
    assert p1[1] > p0[1]


def test_d6_market_uses_project_margin_method():
    from toto import arena as A
    from toto.predict import additive_probabilities
    p = A.market_probs((2.0, 3.5, 4.0))
    q = additive_probabilities(2.0, 3.5, 4.0)
    assert p == (q.home, q.draw, q.away)


def test_d7_holdout_never_used_by_search():
    src = (ROOT / "tools" / "model_arena.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "cmd_run")
    body = ast.get_source_segment(src, run)
    # 도전자를 고르는 줄은 개발 점수(`b["dev"]`)만 본다
    pick = body[body.index("# 6. 도전자"):body.index("# 7. 시장")]
    assert "hold" not in pick and '["dev"]' in pick


# --------------------------------------------------------------------------
# E. 챔피언 — 리포트 경로
# --------------------------------------------------------------------------
def _toy_state(rows):
    from toto.arena import Candidate
    cand = Candidate(name="toy", kind="stack",
                     engines=[{"kind": "elo", "k": 20, "hfa": 60, "carry": 0.8, "gd": "log"}],
                     features=["elo_diff"])
    stack = S.Stacker(features=["elo_diff"], mean=[0.0], std=[1.0], w_home=[0.5],
                      w_away=[-0.5], b_home={"": 0.3}, b_away={"": -0.1})
    state, _ = C.build_state(cand, rows, stack=stack)
    state["teams"] = {"epl": {t: t for m in rows for t in (m.home, m.away)}}
    return state


def test_e1_refuses_state_that_saw_the_match():
    rows = synth(seasons=1)
    state = _toy_state(rows)
    last = rows[-1].date
    ko = datetime(last.year, last.month, last.day, 12, tzinfo=UTC)
    f, why = C.forecast_from_state(state, "epl", "T00", "T11", ko)
    assert f is None and "사후" in why
    f, why = C.forecast_from_state(state, "epl", "T00", "T11", ko + timedelta(days=1))
    assert f is not None and abs(f.p_home + f.p_draw + f.p_away - 1) < 1e-12


def test_e2_unknown_league_and_team():
    rows = synth(seasons=1)
    state = _toy_state(rows)
    ko = datetime(2030, 1, 1, tzinfo=UTC)
    assert "리그" in C.forecast_from_state(state, "kleague1", "T00", "T11", ko)[1]
    assert "팀" in C.forecast_from_state(state, "epl", "T00", "Nobody", ko)[1]
    assert C.forecast_from_state(None, "epl", "T00", "T11", ko)[1] == C.REASON_NO_STATE


def test_e3_replays_only_season_matches_after_state_and_before_kickoff():
    rows = synth(seasons=1)
    state = _toy_state(rows)
    through = date.fromisoformat(state["data_through"])
    def sm(i, d, hg, ag, fin=True):
        return SeasonMatch(match_id=str(i), competition="epl",
                           kickoff=datetime(d.year, d.month, d.day, 15, tzinfo=UTC),
                           kickoff_aware=True, home_team="T00", away_team="T11",
                           home_goals=hg, away_goals=ag, finished=fin)
    ko = datetime.combine(through + timedelta(days=10), datetime.min.time(), UTC)
    season = [sm(1, through, 9, 0),                       # 상태에 이미 든 날짜
              sm(2, through + timedelta(days=3), 5, 0),   # 배운다
              sm(3, through + timedelta(days=12), 9, 0),  # 킥오프 뒤 — 쓰지 않는다
              sm(4, through + timedelta(days=4), None, None, fin=False)]
    base, _ = C.forecast_from_state(state, "epl", "T00", "T11", ko)
    f, _ = C.forecast_from_state(state, "epl", "T00", "T11", ko, season=season)
    assert base.replayed == 0 and f.replayed == 1
    assert f.p_home > base.p_home
    # 다른 대회 경기는 섞이지 않는다
    other = [replace(season[1], competition="ucl", match_id="9")]
    g, _ = C.forecast_from_state(state, "epl", "T00", "T11", ko, season=season + other)
    assert g.replayed == 1


def test_e4_fd_names_point_to_real_canonicals():
    from toto.normalize import TeamResolver
    r = TeamResolver()
    for fd, canon in C.FD_NAMES.items():
        assert r.resolve(canon, learn=False, quiet=True, strict=True) == canon, (fd, canon)


def test_e5_no_market_in_independent_path():
    """독립 경로(엔진·출력층·챔피언)는 배당도 시장 확률도 읽지 않는다 (§1-27)."""
    for mod in ("ratings", "stacker", "champion"):
        tree = ast.parse((ROOT / "toto" / f"{mod}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").endswith("predict"), mod
                assert "predict" not in [a.name for a in node.names], mod
            if isinstance(node, ast.Import):
                assert not any(a.name.endswith("predict") for a in node.names), mod
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("odds_open", "odds_close", "odds_avg",
                                         "odds", "probs") or (
                    mod == "champion" and node.attr == "probs"
                    and isinstance(node.value, ast.Name) and node.value.id == "self"), (mod, node.attr)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not node.value.startswith("mkt_"), mod


def test_e6_panel_never_sees_the_model():
    for mod in ("panel", "panelpacket", "panelexport", "moderator", "match_material",
                "panelauto", "panelwork", "evidence", "analysis"):
        src = (ROOT / "toto" / f"{mod}.py").read_text(encoding="utf-8")
        for bad in ("champion", "arena", "ratings", "stacker"):
            assert f"import {bad}" not in src and f" {bad}," not in src.split("\n\n")[0], (mod, bad)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    assert a.name not in ("champion", "arena", "ratings", "stacker"), (mod, a.name)


def test_e7_runtime_path_needs_no_numpy():
    code = (
        "import sys, json\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "sys.modules['numpy'] = None\n"
        "from datetime import datetime, timezone\n"
        "from toto import champion, ratings, stacker\n"
        "st = stacker.Stacker(features=['elo_diff'], mean=[0.0], std=[1.0], w_home=[1.0],"
        " w_away=[-1.0], b_home={'': 0.2}, b_away={'': 0.0})\n"
        "e = ratings.Elo(); e.teams[('epl','A')] = (50.0,); e.teams[('epl','B')] = (-50.0,)\n"
        "state = {'version': 1, 'data_through': '2026-01-01', 'league_last': {'epl': '2026-01-01'},"
        " 'engines': [e.state()], 'stacker': st.to_dict(), 'teams': {'epl': {'A': 'A', 'B': 'B'}}}\n"
        "f, why = champion.forecast_from_state(state, 'epl', 'A', 'B', datetime(2026, 2, 1, tzinfo=timezone.utc))\n"
        "print(round(f.p_home + f.p_draw + f.p_away, 9), f.p_home > f.p_away)\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["1.0", "True"]


def test_e8_champion_id_tracks_spec_not_name():
    a = {"name": "x", "kind": "stack", "engines": [{"kind": "elo"}], "features": ["elo_diff"],
         "l2": 1.0, "per_league": True, "window": 0}
    assert C.champion_id(a) == C.champion_id(dict(a, name="y"))
    assert C.champion_id(a) != C.champion_id(dict(a, l2=2.0))


def test_e9_state_from_other_champion_is_ignored():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "s.json"
        p.write_text(json.dumps({"version": C.STATE_VERSION, "champion": "zzz",
                                 "data_through": "2030-01-01"}), encoding="utf-8")
        champ = C.load_champion()
        st = C.load_state(paths=(p,))
        if champ is not None:
            assert st is None
        else:
            assert st is not None


def test_e10_update_refreshes_engines_keeps_stacker():
    """`--model-update` 는 출력층을 다시 맞추지 않고(numpy 없이) 엔진만 굴린다."""
    import tempfile
    from toto.arena import Candidate
    rows = synth(seasons=2)
    cand = Candidate(name="toy", kind="stack",
                     engines=[{"kind": "elo", "k": 20, "hfa": 60, "carry": 0.8, "gd": "log"}],
                     features=["elo_diff"])
    stack = S.Stacker(features=["elo_diff"], mean=[0.0], std=[1.0], w_home=[0.5],
                      w_away=[-0.5], b_home={"": 0.3}, b_away={"": -0.1})
    old = rows[: len(rows) // 2]
    saved = {k: getattr(C, k) for k in ("CHAMPION_FILE", "STATE_FILE", "FRESH_STATE_FILE")}
    saved_h = {k: getattr(H, k) for k in ("fetch", "load")}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        try:
            C.CHAMPION_FILE = tmp / "champion.json"
            C.STATE_FILE = tmp / "state.json"
            C.FRESH_STATE_FILE = tmp / "fresh" / "state.json"
            assert C.update() == "생략 (챔피언 없음)"
            rec = C.save_champion(cand, {"n": 1}, {"p_b_better": 1.0}, against="x",
                                  path=C.CHAMPION_FILE)
            st, _ = C.build_state(cand, old, stack=stack)
            C.save_state(st, C.STATE_FILE)
            H.fetch = lambda refresh=True: {"ok": 1, "cached": 0, "failed": []}
            H.load = lambda: (rows, [])
            line = C.update()
            assert line.startswith("ok (자료 " + rows[-1].date.isoformat()), line
            fresh = json.loads(C.FRESH_STATE_FILE.read_text(encoding="utf-8"))
            assert fresh["stacker"] == st["stacker"] and fresh["champion"] == rec["id"]
            assert fresh["data_through"] > st["data_through"]
            got = C.load_state(paths=(C.FRESH_STATE_FILE, C.STATE_FILE))
            assert got["data_through"] == fresh["data_through"]   # 더 최근 것을 쓴다
        finally:
            for k, v in saved.items():
                setattr(C, k, v)
            for k, v in saved_h.items():
                setattr(H, k, v)


def test_e11_committed_champion_is_consistent():
    """커밋된 챔피언·상태가 서로 맞고, 리포트 경로가 그것을 읽는다."""
    champ = C.load_champion()
    if champ is None:
        raise unittest.SkipTest("챔피언 없음")
    state = json.loads(C.STATE_FILE.read_text(encoding="utf-8"))
    assert state["champion"] == champ["id"] == C.champion_id(champ["candidate"])
    assert champ["candidate"]["kind"] == "stack"
    assert champ["gate"]["p_b_better"] >= 0.95
    st = S.Stacker.from_dict(state["stacker"])
    assert st.features == champ["candidate"]["features"]
    assert {e["kind"] for e in state["engines"]} == {e["kind"] for e in champ["candidate"]["engines"]}


def test_e12_cli_branch_before_collection():
    src = (ROOT / "toto" / "cli.py").read_text(encoding="utf-8")
    assert src.index("if args.model_update:") < src.index("# ---- 1. 경기 목록")
    assert '"--model-update"' in src and '"--skip-model-update"' in src
    assert 'report.source_status["예측모델"]' in src


# --------------------------------------------------------------------------
# F. 리포트
# --------------------------------------------------------------------------
def _match():
    return Match(no=1, home=TeamRef(name_ko="아스널", canonical="Arsenal", display="아스널"),
                 away=TeamRef(name_ko="첼시", canonical="Chelsea", display="첼시"),
                 league="epl", kickoff_kst="2099-01-01 21:00")


def test_f1_no_season_index_no_block():
    from toto import render
    assert render._model_block(_match(), Report(round_id="1", matches=[])) == ""


def test_f2_champion_block_text_has_no_pick_words():
    from toto import render
    src = ast.get_source_segment((ROOT / "toto" / "render.py").read_text(encoding="utf-8"),
                                 next(n for n in ast.parse((ROOT / "toto" / "render.py").read_text(encoding="utf-8")).body
                                      if isinstance(n, ast.FunctionDef) and n.name == "_champion_block"))
    for bad in ("추천합니다", "홈승", "원정승", "favorite", "베팅"):
        assert bad not in src
    assert "합치지 않습니다" in src and "추천이 아닙니다" in src


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    raise SystemExit(main())
