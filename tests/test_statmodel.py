"""통계 모델 기준선 · 백테스트 — `toto/statmodel.py` · `tools/backtest_statmodel.py` (§1-66).

    python tests/test_statmodel.py
"""
from __future__ import annotations

import ast
import csv
import math
import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import backtest_statmodel as BT                                  # noqa: E402
from toto import render, roundlog, statmodel as S                # noqa: E402
from toto.models import (Match, Report, SeasonMatch, TeamRef,     # noqa: E402
                         MODEL)
from toto.settings import Settings, load_settings                 # noqa: E402

UTC = timezone.utc
START = datetime(2026, 8, 15, 14, 0, tzinfo=UTC)


def _pois(rng, lam):
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p < limit:
            return k
        k += 1


def _season(rounds=12, comp="epl", seed=7, strength=None, home_boost=None,
            start=START, prefix=""):
    rng = random.Random(seed)
    teams = [f"{prefix}T{i:02d}" for i in range(20)]
    st = strength or {t: math.exp(0.05 * (i - 10)) for i, t in enumerate(teams)}
    hb = home_boost or {}
    out, mid = [], 0
    for r in range(rounds):
        order = teams[:]
        rng.shuffle(order)
        for i in range(0, 20, 2):
            h, a = order[i], order[i + 1]
            mid += 1
            out.append(SeasonMatch(
                match_id=f"{comp}{prefix}{mid}", competition=comp,
                kickoff=start + timedelta(days=7 * r), kickoff_aware=True,
                home_team=h, away_team=a,
                home_goals=_pois(rng, 1.5 * st[h] * hb.get(h, 1.0) / st[a]),
                away_goals=_pois(rng, 1.15 * st[a] / st[h]), finished=True))
    return out


AS_OF = START + timedelta(days=7 * 12)


# ==========================================================================
# A. 모델
# ==========================================================================
def test_a1_stronger_home_team_is_favoured_and_deterministic():
    season = _season()
    f, why = S.forecast(season, "epl", "T19", "T00", AS_OF)
    assert why == "" and f is not None
    assert f.p_home > f.p_away and f.home_goals > f.away_goals
    assert f.provenance == MODEL
    assert abs(f.p_home + f.p_draw + f.p_away + f.tail_mass - 1.0) < 1e-12
    again, _ = S.forecast(list(reversed(season)), "epl", "T19", "T00", AS_OF)
    assert again == f                                    # 순서·난수에 기대지 않는다


def test_a2_future_matches_never_change_the_forecast():
    season = _season()
    base, _ = S.forecast(season, "epl", "T05", "T09", AS_OF)
    future = _season(rounds=4, seed=99, start=AS_OF, prefix="F")
    # 같은 팀 이름으로 미래 경기를 덧붙인다 — 결과가 극단적이어도 바뀌면 안 된다
    for m in future:
        m.home_team, m.away_team = "T05", "T09"
        m.home_goals, m.away_goals = 9, 0
    same_time = SeasonMatch(match_id="now", competition="epl", kickoff=AS_OF,
                            kickoff_aware=True, home_team="T05", away_team="T09",
                            home_goals=9, away_goals=0, finished=True)
    got, _ = S.forecast(season + future + [same_time], "epl", "T05", "T09", AS_OF)
    assert got == base


def test_a3_other_competitions_do_not_mix_in():
    season = _season()
    base, _ = S.forecast(season, "epl", "T05", "T09", AS_OF)
    ucl = _season(rounds=6, comp="ucl", seed=3)
    for m in ucl:
        m.home_goals, m.away_goals = 7, 0
    got, _ = S.forecast(season + ucl, "epl", "T05", "T09", AS_OF)
    assert got == base


def test_a4_unknown_target_or_unlabeled_index_refuses():
    season = _season()
    assert S.forecast(season, "", "T05", "T09", AS_OF) == (None, S.REASON_NO_TARGET)
    assert S.forecast(season, "epl", "T05", "T09", None) == (None, S.REASON_NO_ASOF)
    for m in season:
        m.competition = ""
    assert S.forecast(season, "epl", "T05", "T09", AS_OF) == (None, S.REASON_UNLABELED)


def test_a5_small_samples_are_refused_with_counts():
    season = _season(rounds=1)
    f, why = S.forecast(season, "epl", "T05", "T09", AS_OF)
    assert f is None and why.startswith(S.REASON_LEAGUE_SMALL) and "10경기" in why
    season = _season(rounds=3)
    f, why = S.forecast(season, "epl", "T05", "T09", AS_OF,
                        S.ModelConfig(min_team_matches=5))
    assert f is None and why.startswith(S.REASON_TEAM_SMALL)


def test_a6_venue_split_sees_a_home_specialist():
    """홈에서만 강한 팀 — 장소 분리 모델이 그 팀의 홈 경기를 더 높게 본다."""
    season = _season(rounds=20, home_boost={"T10": 2.2}, seed=11)
    plain, _ = S.forecast(season, "epl", "T10", "T11",
                          START + timedelta(days=140))
    venue, _ = S.forecast(season, "epl", "T10", "T11",
                          START + timedelta(days=140),
                          S.ModelConfig(venue_split=True))
    assert venue.home_goals > plain.home_goals
    assert venue.home_venue_matches < venue.home_matches


def test_a7_half_life_follows_recent_form():
    early = _season(rounds=10, seed=5)
    late = _season(rounds=6, seed=6, start=START + timedelta(days=70), prefix="")
    for m in early:                                   # 예전엔 T00 이 크게 졌다
        if "T00" in (m.home_team, m.away_team):
            m.home_goals, m.away_goals = ((0, 4) if m.home_team == "T00" else (4, 0))
    for m in late:
        m.match_id = "late" + m.match_id
        if "T00" in (m.home_team, m.away_team):        # 최근엔 크게 이긴다
            m.home_goals, m.away_goals = ((4, 0) if m.home_team == "T00" else (0, 4))
    season = early + late
    at = START + timedelta(days=7 * 17)
    # 가중치를 주면 유효 표본이 줄어 당김(shrink)이 세진다 — 그 효과와 섞이지
    # 않게 당김을 작게 둔다.
    flat, _ = S.forecast(season, "epl", "T00", "T05", at,
                         S.ModelConfig(shrink_matches=1))
    recent, _ = S.forecast(season, "epl", "T00", "T05", at,
                           S.ModelConfig(half_life_days=21, shrink_matches=1))
    assert recent.home_goals > flat.home_goals


def test_a8_config_from_settings_and_bad_values():
    cfg = S.config_from(load_settings())
    assert cfg == S.ModelConfig()                      # 기본값이 설정에 그대로 있다
    bad = Settings(analysis={"statmodel": {"shrink_matches": "x",
                                           "half_life_days": "abc",
                                           "min_team_matches": -2,
                                           "venue_split": True}})
    got = S.config_from(bad)
    assert got.shrink_matches == 5.0 and got.half_life_days is None
    assert got.min_team_matches == 1 and got.venue_split is True
    assert S.config_from(Settings()) == S.ModelConfig()


# ==========================================================================
# B. 경계 — 시장·패널과 섞지 않는다
# ==========================================================================
def _imports(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    return names


def test_b1_model_does_not_import_market_engine():
    names = _imports(ROOT / "toto" / "statmodel.py")
    assert "predict" not in names and "panel" not in names


def test_b2_panel_side_never_sees_the_model():
    for mod in ("panel", "panelpacket", "panelexport", "moderator",
                "match_material", "panelauto", "panelwork", "evidence",
                "analysis"):
        names = _imports(ROOT / "toto" / f"{mod}.py")
        assert "statmodel" not in names, mod


def test_b3_model_has_no_pick_fields():
    fields = set(S.Forecast.__dataclass_fields__)
    for bad in ("pick", "recommendation", "winner", "lean", "confidence"):
        assert bad not in fields


def _report_with(season, league="epl", home="T19", away="T00",
                 kickoff="2026-11-07 23:00"):
    m = Match(no=1, home=TeamRef(display="홈", canonical=home),
              away=TeamRef(display="원정", canonical=away))
    m.league = league
    m.kickoff_kst = kickoff
    return m, Report(round_id="999", season_matches=season, matches=[m])


def test_b4_report_block_shows_probabilities_and_samples():
    m, rep = _report_with(_season())
    html = render._model_block(m, rep, Settings())
    assert "통계 모델 기준선" in html and "기대 득점" in html
    assert "패널에는 전달되지 않습니다" in html and "<svg" in html
    for bad in ("추천", "픽", "홈승", "원정승"):
        assert bad not in html


def test_b5_block_is_absent_without_index_or_prior_matches():
    m, rep = _report_with([])
    assert render._model_block(m, rep, Settings()) == ""
    m, rep = _report_with(_season(), league="laliga")      # 그 대회 경기가 없다
    assert render._model_block(m, rep, Settings()) == ""
    m, rep = _report_with(_season(rounds=1))               # 있는데 모자라다
    out = render._model_block(m, rep, Settings())
    assert "리그 표본 부족" in out


# ==========================================================================
# C. 백테스트
# ==========================================================================
def test_c1_each_prediction_uses_only_earlier_matches():
    season = _season(rounds=8)
    cfg = S.ModelConfig()
    result = BT.run(season, load_settings(), [cfg])
    assert result["common"] > 0
    # 같은 경기를 '그 이전만 남긴 색인' 으로 다시 예측하면 같은 값이다
    target = season[-1]
    trimmed = [m for m in season if m.kickoff < target.kickoff]
    a, _ = S.forecast(season, "epl", target.home_team, target.away_team,
                      target.kickoff, cfg)
    b, _ = S.forecast(trimmed, "epl", target.home_team, target.away_team,
                      target.kickoff, cfg)
    assert a == b


def test_c2_market_is_joined_by_match_id_on_the_same_matches():
    season = _season(rounds=8)
    target = season[-1]
    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "round_matches.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=roundlog.MATCH_FIELDS)
            w.writeheader()
            hg, ag = target.home_goals, target.away_goals
            w.writerow({"round": "999", "no": 1, "match_id": target.match_id,
                        "p_home": "0.5", "p_draw": "0.3", "p_away": "0.2",
                        "home_goals": hg, "away_goals": ag,
                        "result": BT.actual_of(target),
                        "recorded_at": "2026-09-01 10:00",
                        "kickoff_kst": "2026-12-31 23:00"})
            w.writerow({"round": "998", "no": 1, "match_id": "nope",
                        "p_home": "0.5", "p_draw": "0.3", "p_away": "0.2",
                        "home_goals": 1, "away_goals": 0, "result": "H",
                        "recorded_at": "2026-09-01 10:00",
                        "kickoff_kst": "2026-12-31 23:00"})
        market = BT.market_by_match_id(path)
    assert set(market) == {target.match_id, "nope"}
    result = BT.run(season, load_settings(), [S.ModelConfig()], market)
    vm = result["vs_market"]
    assert vm["ids"] == 1 and vm["market"].n == 1
    assert vm["not_in_index_rounds"] == ["998"]
    text = "\n".join(BT.lines(result, ["x"], [], season))
    assert "시장과 같은 경기 — 1경기" in text


def test_c3_variants_are_scored_on_the_same_matches():
    season = _season(rounds=8)
    cfgs = BT.configs([0, 30], [5], "both")
    result = BT.run(season, load_settings(), cfgs)
    ns = {s.n for name, s in result["table"].items()}
    assert ns == {result["common"]}
    assert len(result["diffs"]) == len(cfgs) - 1


def test_c4_json_inside_repo_is_refused_and_nothing_is_written():
    assert BT.main(["--artifacts", str(ROOT / "nope.json"),
                    "--json", str(ROOT / "out.json")]) == 2
    assert not (ROOT / "out.json").exists()
    src = (ROOT / "tools" / "backtest_statmodel.py").read_text(encoding="utf-8")
    for bad in ("artifact.save", "roundlog.record", "_write(", "settle"):
        assert bad not in src


def test_c5_rps_matches_hand_calculation():
    sure_h = {"H": 1.0, "D": 0.0, "A": 0.0}
    assert BT.rps_of(sure_h, "H") == 0.0
    assert BT.rps_of(sure_h, "A") == 1.0
    assert abs(BT.rps_of(sure_h, "D") - 0.5) < 1e-12
    third = {o: 1 / 3 for o in "HDA"}
    assert abs(BT.rps_of(third, "D") - 1 / 9) < 1e-12
    # 순서를 반영한다 — 홈승을 확신했는데 무승부가 원정승보다 덜 나쁘다
    assert BT.rps_of(sure_h, "D") < BT.rps_of(sure_h, "A")
    s = BT.Score()
    s.add({"H": 0.5, "D": 0.3, "A": 0.2}, "H")
    assert abs(s.rps - BT.rps_of({"H": 0.5, "D": 0.3, "A": 0.2}, "H")) < 1e-12
    assert "RPS" in s.line("x")


def test_c6_blend_is_linear_and_zero_weight_is_market():
    m = {"H": 0.5, "D": 0.3, "A": 0.2}
    f = {"H": 0.2, "D": 0.3, "A": 0.4}            # 합 0.9 — 절단분처럼 맞춘다
    assert BT.blend(m, f, 0.0) == BT.normalized(m)
    assert all(abs(v - BT.normalized(f)[o]) < 1e-12
               for o, v in BT.blend(m, f, 1.0).items())
    half = BT.blend(m, f, 0.5)
    assert abs(sum(half.values()) - 1.0) < 1e-12
    assert abs(half["H"] - (0.5 * 0.5 + 0.5 * 0.2 / 0.9)) < 1e-12


def _rows(model_good: bool, rounds=("1", "2", "3"), per=6):
    rows = []
    for r in rounds:
        for i in range(per):
            actual = "HDA"[i % 3]
            market = {"H": 0.45, "D": 0.28, "A": 0.27}
            model = ({o: (0.8 if o == actual else 0.1) for o in "HDA"}
                     if model_good else dict(market))
            rows.append((r, market, model, actual))
    return rows


def test_c7_cross_validation_picks_weight_from_other_rounds_only():
    good = BT.blend_study(_rows(True))
    assert set(good["chosen"]) == {"1", "2", "3"}
    assert all(w == max(BT.BLEND_WEIGHTS) for w in good["chosen"].values())
    assert good["cv"]["diff_brier"][0] < 0
    assert BT.verdict(*good["cv"]["diff_brier"][:2]).startswith("시장보다 낮다")
    # 모델이 시장과 같으면 비중은 동점 → 시장 쪽(0)을 고르고 차이는 0
    same = BT.blend_study(_rows(False))
    assert set(same["chosen"].values()) == {0.0}
    assert same["cv"]["diff_brier"][0] == 0.0
    assert BT.verdict(*same["cv"]["diff_brier"][:2]).startswith("판정 불가") \
        or "구별되지" in BT.verdict(*same["cv"]["diff_brier"][:2])
    # 뺀 회차의 모델 값을 바꿔도 그 회차에 고른 비중은 바뀌지 않는다
    rows = _rows(True)
    spoiled = [(r, m, ({"H": 0.0, "D": 0.0, "A": 1.0} if r == "2" else f), y)
               for r, m, f, y in rows]
    assert BT.blend_study(spoiled)["chosen"]["2"] == good["chosen"]["2"]
    # 회차가 하나면 교차검증을 하지 않는다
    one = BT.blend_study(_rows(True, rounds=("1",)))
    assert one["cv"] is None and one["in_sample"]


def test_c8_blend_section_runs_end_to_end_and_stays_in_the_tool():
    season = _season(rounds=10)
    last = [m for m in season if m.kickoff >= season[-1].kickoff - timedelta(days=7)]
    market = {m.match_id: ("R1" if m.kickoff < season[-1].kickoff else "R2", i,
                           {"H": 0.45, "D": 0.28, "A": 0.27})
              for i, m in enumerate(last, 1)}
    result = BT.run(season, load_settings(), [S.ModelConfig()], market)
    b = result["vs_market"]["blend"][S.ModelConfig().name]
    assert b["n"] == result["vs_market"]["ids"] > 0
    assert set(b["chosen"]) == {"R1", "R2"}
    text = "\n".join(BT.lines(result, ["x"], [], season))
    assert "시장 + 모델 혼합" in text and "교차검증" in text
    # 혼합은 도구 안에서만 — 운영 모듈은 이 도구를 모른다
    for path in (ROOT / "toto").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                 for a in n.names}
        names |= {n.module or "" for n in ast.walk(tree)
                  if isinstance(n, ast.ImportFrom)}
        assert not any("backtest_statmodel" in x for x in names), path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    raise SystemExit(main())
