"""시장 기준 가장 그럴듯한 스코어 — toto/marketscore.py (§1-64).

시장 확률의 파생값이 리포트의 시장 기준선 블록에만 나가고, 패널 자료에는
가지 않는지 본다.

    python tests/test_market_score.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from toto import marketscore, render, xpts            # noqa: E402
from toto.predict import MatchProb                    # noqa: E402

import tests.test_panel_auto as PA                    # noqa: E402


def _probs(lh, la) -> MatchProb:
    r = xpts.match_xpts(lh, la)
    total = (r.home_win_probability + r.draw_probability
             + r.away_win_probability)
    return MatchProb(home=r.home_win_probability / total,
                     draw=r.draw_probability / total,
                     away=r.away_win_probability / total)


def _imports(module_path: Path) -> set:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
    return names


# ==========================================================================
# A. 계산
# ==========================================================================
def test_a1_recovers_expected_goals_and_mode():
    ms = marketscore.most_likely(_probs(1.4, 1.1))
    assert abs(ms.home_goals - 1.4) < 0.02 and abs(ms.away_goals - 1.1) < 0.02
    assert (ms.home, ms.away) == (1, 1) and ms.label == "1 - 1"
    assert ms.fit_error < 0.001
    strong = marketscore.most_likely(_probs(2.2, 0.6))
    assert (strong.home, strong.away) == (2, 0)


def test_a2_probability_is_the_mode_of_the_fitted_poisson():
    ms = marketscore.most_likely(_probs(1.3, 0.9))
    best = max(marketscore.score_probability(ms.home_goals, ms.away_goals, i, j)
               for i in range(10) for j in range(10))
    assert ms.probability == best


def test_a3_deterministic():
    p = MatchProb(home=0.45, draw=0.28, away=0.27)
    assert marketscore.most_likely(p) == marketscore.most_likely(p)


def test_a4_missing_or_broken_probs_give_none_not_zero():
    assert marketscore.most_likely(None) is None
    assert marketscore.most_likely(MatchProb()) is None              # 0/0/0
    assert marketscore.most_likely(
        MatchProb(home=0.6, draw=0.0, away=0.4)) is None             # 0 확률
    assert marketscore.most_likely(
        MatchProb(home=0.6, draw=0.3, away=0.3)) is None             # 합 1.2
    assert marketscore.most_likely(object()) is None


def test_a5_does_not_import_predict():
    names = _imports(ROOT / "toto" / "marketscore.py")
    assert "predict" not in names and "toto.predict" not in names


# ==========================================================================
# B. 경계 — 패널에는 가지 않는다
# ==========================================================================
def test_b1_panel_side_modules_do_not_import_it():
    for mod in ("panel", "panelpacket", "panelexport", "moderator",
                "match_material", "panelauto", "panelwork", "evidence",
                "analysis"):
        names = _imports(ROOT / "toto" / f"{mod}.py")
        assert "marketscore" not in names, mod


def test_b2_panel_payload_has_no_market_score():
    from toto import panel
    for match in PA.demo_matches(3):
        text = panel.serialize_payload(panel.build_panel_payload(match))
        assert "가장 그럴듯한" not in text and "home_goals" not in text


def test_b3_only_the_odds_block_calls_it():
    tree = ast.parse((ROOT / "toto" / "render.py").read_text(encoding="utf-8"))
    callers = set()
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and getattr(
                        node.func, "id", "") == "_market_mode_line":
                    callers.add(fn.name)
    assert callers == {"_odds_block"}, callers


# ==========================================================================
# C. 리포트 줄
# ==========================================================================
def test_c1_line_shows_score_probability_and_expected_goals():
    line = render._market_mode_line(_probs(1.4, 1.1))
    assert "시장 기준 가장 그럴듯한 스코어 <b>1 - 1</b>" in line
    assert "기대 득점 <b>1.40</b> · <b>1.10</b>" in line
    assert "패널에는 전달되지 않습니다" in line
    assert "재현 오차" not in line                 # 잘 맞으면 적지 않는다


def test_c2_no_outcome_labels():
    line = render._market_mode_line(_probs(2.2, 0.6))
    for word in ("홈승", "원정승", "무승부", "추천", "픽", "승리"):
        assert word not in line, word


def test_c3_missing_probs_give_empty_line():
    assert render._market_mode_line(None) == ""
    assert render._market_mode_line(MatchProb()) == ""


def test_c4_poor_fit_is_said():
    # 무승부가 독립 포아송으로는 닿을 수 없을 만큼 낮은 시장
    line = render._market_mode_line(MatchProb(home=0.48, draw=0.04, away=0.48))
    assert "재현 오차" in line


def test_c5_demo_report_has_one_line_per_match_with_odds():
    from toto import fixtures
    from toto.analyze import attach_probabilities
    matches = fixtures.build_demo_matches()
    attach_probabilities(matches)
    with_odds = [m for m in matches if m.probs and m.odds.available]
    assert len(with_odds) == len(matches) == 14
    blocks = [render._odds_block(m) for m in with_odds]
    assert all("시장 기준 가장 그럴듯한 스코어" in b for b in blocks)


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    raise SystemExit(main())
