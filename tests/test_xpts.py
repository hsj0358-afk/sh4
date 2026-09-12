"""독립 포아송 기대승점 회귀 테스트 (Phase 2 P1).

`toto/xpts.py` 는 **모델**이다. 피나클 배당 확률(`toto/predict.py`, 시장이
매긴 값)과 섞이면 안 되므로, 두 모듈이 서로를 import 하지 않는다는 것까지
테스트로 고정한다.

손계산 대조는 **다른 경로**로 한다 — 구현은 점화식
`p(k) = p(k-1)·λ/k` 을 쓰고, 테스트는 교과서 공식
`exp(-λ)·λ^k/k!` 을 쓴다. 같은 코드를 두 번 부르는 게 아니다.

pytest 없이도 돈다:  python tests/test_xpts.py
"""
from __future__ import annotations

import math
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import xpts                                          # noqa: E402
from toto.models import (MODEL, AnalysisAxis, Match, MatchAnalysis,  # noqa: E402
                         Metric, SeasonMatch, revive_match_analysis)

UTC = timezone.utc
TOL = 1e-9


def ref_pmf(lam: float, k: int) -> float:
    """교과서 공식. 구현(점화식)과 다른 경로다."""
    return math.exp(-lam) * lam ** k / math.factorial(k)


# --------------------------------------------------------------------------
# 1. poisson pmf
# --------------------------------------------------------------------------
def test_poisson_pmf_matches_textbook_formula():
    for lam in (0.0, 0.3, 1.0, 1.75, 3.0, 5.5):
        got = xpts.poisson_pmf(lam)
        assert len(got) == xpts.MAX_GOALS + 1
        for k, p in enumerate(got):
            assert abs(p - ref_pmf(lam, k)) < 1e-12, f"λ={lam} k={k}"


def test_poisson_pmf_zero_lambda():
    got = xpts.poisson_pmf(0.0)
    assert got[0] == 1.0, "xG 0 이면 무득점이 확실하다"
    assert all(p == 0.0 for p in got[1:])


def test_poisson_pmf_rejects_bad_lambda():
    for bad in (-0.1, float("nan"), float("inf"), 1e6):
        try:
            xpts.poisson_pmf(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad} 를 받아들였다")


def test_poisson_pmf_no_overflow_at_high_lambda():
    """점화식이라 λ^k 가 넘치지 않는다."""
    got = xpts.poisson_pmf(20.0)
    assert all(math.isfinite(p) and p >= 0 for p in got)


# --------------------------------------------------------------------------
# 2·3. 결과 확률 · 손계산
# --------------------------------------------------------------------------
def test_hand_calculation_symmetric():
    """λ 가 같으면 홈승·원정승 확률이 같아야 한다."""
    r = xpts.match_xpts(1.0, 1.0)
    assert abs(r.home_win_probability - r.away_win_probability) < TOL
    # 무승부는 Σ P(k)² — 독립 경로로 검산
    ref_draw = sum(ref_pmf(1.0, k) ** 2 for k in range(xpts.MAX_GOALS + 1))
    assert abs(r.draw_probability - ref_draw) < 1e-12
    assert abs(r.draw_probability - 0.30850832) < 1e-7
    assert abs(r.home_win_probability - 0.34574573) < 1e-7


def test_hand_calculation_both_zero():
    """xG 0/0 → 0-0 이 확실 → 무승부 확률 1."""
    r = xpts.match_xpts(0.0, 0.0)
    assert r.draw_probability == 1.0
    assert r.home_win_probability == 0.0 and r.away_win_probability == 0.0
    assert r.home_xpts == 1.0 and r.away_xpts == 1.0
    assert r.probability_sum == 1.0 and r.tail_mass == 0.0


def test_hand_calculation_asymmetric():
    """xG 2.0 vs 0.5 — 홈이 크게 우세해야 한다."""
    r = xpts.match_xpts(2.0, 0.5)
    ref_h = sum(ref_pmf(2.0, i) * ref_pmf(0.5, j)
                for i in range(10) for j in range(10) if i > j)
    assert abs(r.home_win_probability - ref_h) < 1e-12
    assert r.home_win_probability > r.away_win_probability
    assert r.home_xpts > r.away_xpts
    assert abs(r.home_win_probability - 0.73094) < 1e-4


def test_outcome_probabilities_partition():
    """승·무·패가 겹치지 않고 합이 probability_sum 이다."""
    for h, a in ((1.0, 1.0), (2.3, 0.7), (0.4, 3.1), (0.0, 1.0)):
        r = xpts.match_xpts(h, a)
        total = (r.home_win_probability + r.draw_probability
                 + r.away_win_probability)
        assert abs(total - r.probability_sum) < TOL


def test_higher_xg_side_is_favoured():
    for h, a in ((2.0, 1.0), (1.6, 0.9), (0.9, 1.6)):
        r = xpts.match_xpts(h, a)
        if h > a:
            assert r.home_win_probability > r.away_win_probability
            assert r.home_xpts > r.away_xpts
        else:
            assert r.away_win_probability > r.home_win_probability


# --------------------------------------------------------------------------
# 4. xPTS
# --------------------------------------------------------------------------
def test_xpts_formula():
    r = xpts.match_xpts(1.4, 1.1)
    assert abs(r.home_xpts
               - (3 * r.home_win_probability + r.draw_probability)) < TOL
    assert abs(r.away_xpts
               - (3 * r.away_win_probability + r.draw_probability)) < TOL


def test_xpts_sum_is_not_three():
    """**두 팀 xPTS 의 합은 3 이 아니다.** 무승부가 양쪽에 1점씩 들어간다."""
    r = xpts.match_xpts(1.0, 1.0)
    total = r.home_xpts + r.away_xpts
    assert abs(total - 3.0) > 0.2, "3 이 나오면 공식이 잘못된 것"
    assert abs(total - 2.69149) < 1e-4
    # 관계식: 합 = 3·(P(H)+P(A)) + 2·P(D) = 3·합계 − P(D)
    assert abs(total - (3 * r.probability_sum - r.draw_probability)) < TOL


def test_xpts_uses_truncated_probabilities_not_normalised():
    """정규화한 확률로 xPTS 를 만들지 않는다 — 절단 오차가 숨는다."""
    r = xpts.match_xpts(3.5, 3.5)
    norm_h = r.home_win_probability / r.probability_sum
    norm_d = r.draw_probability / r.probability_sum
    assert abs(r.home_xpts - (3 * norm_h + norm_d)) > 1e-9


# --------------------------------------------------------------------------
# 5·6. 확률합 · tail mass
# --------------------------------------------------------------------------
def test_probability_sum_and_tail_mass():
    for h, a in ((1.0, 1.0), (2.0, 0.5), (0.1, 0.1)):
        r = xpts.match_xpts(h, a)
        assert abs(r.tail_mass - (1.0 - r.probability_sum)) < TOL
        assert r.tail_mass >= -TOL
        assert r.probability_sum <= 1.0 + TOL
        assert r.tail_mass < 1e-3, f"평범한 xG 인데 누락이 크다: {r.tail_mass}"


def test_tail_mass_grows_with_lambda():
    """λ 가 커지면 0~9 절단에서 새는 양이 늘어난다 — 감추지 않는다."""
    small = xpts.match_xpts(1.0, 1.0).tail_mass
    big = xpts.match_xpts(4.0, 4.0).tail_mass
    assert big > small
    assert big > 0.01, "λ=4/4 에서는 1% 넘게 샌다"


def test_probabilities_are_not_renormalised():
    r = xpts.match_xpts(4.0, 4.0)
    assert r.probability_sum < 1.0 - 1e-3, "합이 1로 맞춰졌다 = 재분배했다"


# --------------------------------------------------------------------------
# 7. None / 0 구분
# --------------------------------------------------------------------------
def test_none_input_yields_all_none():
    for h, a, who in ((None, 1.0, "홈"), (1.0, None, "원정"), (None, None, "홈")):
        r = xpts.match_xpts(h, a)
        assert r.home_win_probability is None and r.draw_probability is None
        assert r.away_win_probability is None
        assert r.home_xpts is None and r.away_xpts is None
        assert r.probability_sum is None and r.tail_mass is None
        assert r.available is False
        assert who in r.reason, r.reason


def test_zero_is_a_real_value_not_missing():
    """xG 0 은 '데이터 없음'이 아니다 — 계산된다."""
    r = xpts.match_xpts(0.0, 1.2)
    assert r.available is True
    assert r.home_win_probability == 0.0, "무득점 기대면 홈승 확률 0"
    # 홈이 0골 확실 → 원정승 확률 = P(원정이 1골 이상) = 1 − e^(−1.2)
    assert abs(r.away_win_probability - (1 - math.exp(-1.2))) < 1e-6
    assert r.home_xpts == r.draw_probability, "홈 기대승점은 무승부 몫뿐"
    assert xpts.match_xpts(0.0, 0.0).available is True


def test_invalid_input_is_reported_not_crashed():
    r = xpts.match_xpts(-1.0, 1.0)
    assert r.available is False and "계산 불가" in r.reason


# --------------------------------------------------------------------------
# 8. 수치 안정성 (§12)
# --------------------------------------------------------------------------
def test_numeric_invariants():
    for h in (0.0, 0.05, 0.8, 1.5, 3.0, 6.0):
        for a in (0.0, 0.3, 1.1, 2.5, 5.0):
            r = xpts.match_xpts(h, a)
            for p in (r.home_win_probability, r.draw_probability,
                      r.away_win_probability):
                assert 0.0 - TOL <= p <= 1.0 + TOL, f"{h}/{a} 확률 {p}"
            for x in (r.home_xpts, r.away_xpts):
                assert 0.0 - TOL <= x <= 3.0 + TOL, f"{h}/{a} xPTS {x}"
            assert r.probability_sum <= 1.0 + TOL
            assert r.tail_mass >= -TOL


def test_very_small_xg():
    r = xpts.match_xpts(0.01, 0.01)
    assert r.draw_probability > 0.98, "거의 확실히 0-0"
    assert abs(r.home_xpts - r.away_xpts) < TOL


# --------------------------------------------------------------------------
# 9. provenance
# --------------------------------------------------------------------------
def test_result_is_marked_model():
    r = xpts.match_xpts(1.5, 1.0)
    assert r.provenance == MODEL == "model"


def test_as_axis_marks_every_metric_as_model():
    axis = xpts.match_xpts(1.5, 1.0).as_axis()
    assert isinstance(axis, AnalysisAxis)
    assert set(axis.metrics) == {"home_win_probability", "draw_probability",
                                 "away_win_probability", "home_xpts",
                                 "away_xpts"}
    for m in axis.metrics.values():
        assert isinstance(m, Metric) and m.provenance == MODEL
        assert m.period == "match" and m.sample_count == 1
    assert any("포아송" in n for n in axis.notes)
    assert any("절단" in n for n in axis.notes), "절단 사실을 남겨야 한다"


def test_as_axis_when_unavailable_has_no_metrics():
    axis = xpts.match_xpts(None, 1.0).as_axis()
    assert axis.metrics == {}, "값이 없는데 축을 채우면 안 된다"
    assert axis.notes and "없음" in axis.notes[0]


# --------------------------------------------------------------------------
# 10. import 격리 — 시장 확률과 모델 확률의 분리 (§16)
# --------------------------------------------------------------------------
def test_xpts_does_not_import_predict():
    src = (Path(__file__).resolve().parent.parent / "toto" / "xpts.py").read_text(
        encoding="utf-8")
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert "predict" not in stripped, f"predict 를 import 한다: {line}"


def test_predict_does_not_import_xpts():
    src = (Path(__file__).resolve().parent.parent / "toto" / "predict.py").read_text(
        encoding="utf-8")
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert "xpts" not in stripped, f"xpts 를 import 한다: {line}"


def test_xpts_never_reads_match_probs():
    src = (Path(__file__).resolve().parent.parent / "toto" / "xpts.py").read_text(
        encoding="utf-8")
    for bad in (".probs", "MatchProb", "additive_probabilities", ".odds"):
        assert bad not in src, f"xpts.py 가 {bad} 를 참조한다"


def test_market_and_model_probabilities_stay_separate():
    """모델 계산이 Match.probs 를 건드리지 않는다."""
    from toto.predict import additive_probabilities
    m = Match(no=1)
    m.probs = additive_probabilities(2.00, 3.50, 4.00)
    market_before = m.probs.as_tuple

    m.analysis = MatchAnalysis()
    m.analysis.model = xpts.match_xpts(1.6, 1.1).as_axis()

    assert m.probs.as_tuple == market_before, "시장 확률이 바뀌었다"
    model_home = m.analysis.model.value("home_win_probability")
    assert model_home != m.probs.home, "두 확률은 서로 다른 값이어야 한다"


# --------------------------------------------------------------------------
# 11. MatchAnalysis 연결
# --------------------------------------------------------------------------
def test_match_analysis_model_axis_roundtrip():
    ma = MatchAnalysis(as_of=datetime(2026, 8, 29, tzinfo=UTC))
    ma.model = xpts.match_xpts(1.8, 0.9).as_axis()
    back = revive_match_analysis(asdict(ma))
    assert isinstance(back.model, AnalysisAxis)
    assert back.model.get("home_xpts").provenance == MODEL
    assert abs(back.model.value("home_xpts")
               - ma.model.value("home_xpts")) < TOL


def test_match_analysis_still_has_no_pick_field():
    from dataclasses import fields
    names = {f.name for f in fields(MatchAnalysis)}
    assert "model" in names
    for bad in ("final_pick", "recommendation", "predicted_result", "pick"):
        assert bad not in names


# --------------------------------------------------------------------------
# 12·13. 시즌/최근 집계 · 표본 수
# --------------------------------------------------------------------------
def _season():
    def sm(mid, home, away, day):
        return SeasonMatch(match_id=mid, home_team=home, away_team=away,
                           kickoff=datetime(2026, 8, day, 14, tzinfo=UTC),
                           finished=True)
    return [sm("M1", "Arsenal", "Chelsea", 10),
            sm("M2", "Everton", "Arsenal", 15),
            sm("M3", "Arsenal", "Fulham", 20),
            sm("M4", "Arsenal", "Everton", 25)]


XG = {"M1": (2.0, 0.5), "M2": (0.8, 1.4), "M3": (1.5, 1.0)}   # M4 는 xG 없음


def test_team_aggregation_sums_correct_side():
    got = xpts.aggregate_team_xpts(_season(), XG, "Arsenal")
    assert got.team == "Arsenal"
    assert got.requested_matches == 4, "넘겨받은 아스널 경기 수"
    assert got.available_matches == 3, "그중 xG 가 있던 경기"
    assert got.match_ids == ["M1", "M2", "M3"]
    expected = (xpts.match_xpts(2.0, 0.5).home_xpts       # M1 홈
                + xpts.match_xpts(0.8, 1.4).away_xpts     # M2 원정
                + xpts.match_xpts(1.5, 1.0).home_xpts)    # M3 홈
    assert abs(got.xpts_sum - expected) < TOL


def test_requested_and_available_are_different_concepts():
    got = xpts.aggregate_team_xpts(_season(), XG, "Arsenal")
    assert got.requested_matches != got.available_matches
    assert got.sample_count == got.available_matches == 3
    assert abs(got.coverage - 0.75) < TOL, "커버리지를 감추지 않는다"
    assert abs(got.xpts_per_match - got.xpts_sum / 3) < TOL, \
        "있는 경기 수로만 나눈다"


def test_matches_without_xg_are_not_counted_as_zero():
    """xG 가 없는 경기를 0점으로 치면 평균이 조용히 낮아진다."""
    got = xpts.aggregate_team_xpts(_season(), XG, "Arsenal")
    all_xg = dict(XG, M4=(1.0, 1.0))
    more = xpts.aggregate_team_xpts(_season(), all_xg, "Arsenal")
    assert more.available_matches == 4
    assert more.xpts_sum > got.xpts_sum
    # 없던 경기를 0 으로 쳤다면 평균이 3/4 로 줄었을 것이다
    assert got.xpts_per_match > got.xpts_sum / 4


def test_aggregation_ignores_other_teams_and_duplicates():
    got = xpts.aggregate_team_xpts(_season() + _season(), XG, "Chelsea")
    assert got.requested_matches == 1 and got.match_ids == ["M1"]
    assert abs(got.xpts_sum - xpts.match_xpts(2.0, 0.5).away_xpts) < TOL
    assert xpts.aggregate_team_xpts(_season(), XG, "Nobody").requested_matches == 0


def test_aggregation_with_no_xg_yields_none_not_zero():
    got = xpts.aggregate_team_xpts(_season(), {}, "Arsenal")
    assert got.xpts_sum is None and got.xpts_per_match is None
    assert got.available_matches == 0 and got.requested_matches == 4
    axis = got.as_axis()
    assert axis.metrics == {} and "표본 부족" in axis.notes[0]


def test_team_axis_reports_coverage():
    axis = xpts.aggregate_team_xpts(_season(), XG, "Arsenal").as_axis()
    assert axis.requested_matches == 4 and axis.available_matches == 3
    assert axis.get("xpts_per_match").provenance == MODEL
    assert axis.get("xpts_sum").sample_count == 3
    assert any("3/4" in n for n in axis.notes), "커버리지가 드러나야 한다"


def test_aggregation_does_not_filter_by_time_itself():
    """시점 필터는 호출부(matches_before) 책임 — 여기서 두 번 걸지 않는다."""
    import inspect
    src = inspect.getsource(xpts.aggregate_team_xpts)
    assert "kickoff" not in src, "집계 함수가 시점을 다시 본다"


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
