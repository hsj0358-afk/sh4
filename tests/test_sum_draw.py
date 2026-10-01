"""지침 §8 회차로그의 `sum_draw` — 화면 줄과 저장 행 (리팩터링 Phase 3 M10).

`sum_draw` 는 회차 경기들의 **시장 무승부 확률 합**이다 (배당이 있는
경기만). 같은 §8 칸이 두 군데로 나간다.

    cli._log_line()          실행 로그의 "회차로그 1줄 (지침 §8)"   11번째 칸
    roundlog._round_row()    data/rounds.csv 의 회차 행            `sum_draw`

두 자리가 같은 식을 따로 적고 있었다. 사람이 로그에서 본 값과 파일에 쌓인
값이 같아야 하므로 계산은 한 곳(`roundlog.sum_draw`)이 하고, 두 출력은
각자의 칸 서식(`.2f`)으로 적는다.

이 스위트가 지키는 것은 **관측되는 값**이다 — 두 출력의 글자가 그대로이고
서로 같다. 기대값은 제품 식으로 계산하지 않고 숫자를 그대로 적었다.

pytest 없이도 돈다:  python tests/test_sum_draw.py
"""
from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import realdata                                                  # noqa: E402
from toto import cli, roundlog                                   # noqa: E402
from toto.models import Match, Report, TeamRef                   # noqa: E402
from toto.predict import MatchProb, RoundVerdict                 # noqa: E402

_PASSED = _FAILED = _SKIPPED = 0
SUM_DRAW_COLUMN = 10          # `_log_line` 의 " | " 로 나눈 11번째 칸


def check(name, fn):
    global _PASSED, _FAILED, _SKIPPED
    try:
        fn()
    except realdata.SkipTest as exc:
        _SKIPPED += 1
        print(f"  - {name}: SKIP {exc}")
    except Exception as exc:                                 # noqa: BLE001
        _FAILED += 1
        print(f"  ✗ {name}: {type(exc).__name__}: {exc}")
    else:
        _PASSED += 1
        print(f"  ✓ {name}")


def _report(draws, *, n=None) -> Report:
    """`draws` 의 각 값이 한 경기의 무승부 확률. `None` 이면 배당 없음."""
    matches = []
    for i, d in enumerate(draws, start=1):
        m = Match(no=i, home=TeamRef(display=f"홈{i}"),
                  away=TeamRef(display=f"원정{i}"))
        if d is not None:
            m.probs = MatchProb(home=round(1 - d - 0.3, 6), draw=d, away=0.3)
        matches.append(m)
    r = Report(round_id="990010", generated_at="2026-09-28 10:00")
    r.matches = matches
    r.verdict = RoundVerdict(n=len(matches) if n is None else n,
                             expected=7.0, sigma=1.5, z=-2.0, p_ge11=0.02)
    return r


def _log_cell(report: Report) -> str:
    return cli._log_line(report).split(" | ")[SUM_DRAW_COLUMN]


def _row_cell(report: Report) -> str:
    return roundlog._round_row(report)["sum_draw"]


# --------------------------------------------------------------------------
# A. 값 — 글자 그대로
# --------------------------------------------------------------------------
CASES = [
    ([0.25, 0.30], "0.55"),
    ([0.25, None, 0.30], "0.55"),         # 배당 없는 경기는 더하지 않는다
    ([None, None], "0.00"),
    ([0.2849, 0.2849, 0.2849], "0.85"),   # 0.8547 → 반올림
    ([0.333, 0.333, 0.334], "1.00"),
    ([0.28] * 14, "3.92"),
]


def test_a1_log_line_cell():
    for draws, want in CASES:
        assert _log_cell(_report(draws)) == want, (draws, _log_cell(
            _report(draws)))


def test_a2_csv_row_cell():
    for draws, want in CASES:
        assert _row_cell(_report(draws)) == want, (draws, _row_cell(
            _report(draws)))


def test_a3_row_is_skipped_without_a_verdict():
    """회차 행은 승산이 있을 때만 만든다 — 그대로다."""
    r = _report([0.25])
    r.verdict = None
    assert roundlog._round_row(r) is None
    assert roundlog._round_row(_report([0.25], n=0)) is None


def test_a4_log_line_shape_is_unchanged():
    line = cli._log_line(_report([0.25, 0.30]))
    assert line == ("990010 | 2026-09-28 | 2 | 7.00 | 1.50 | -2.00 | 2% | "
                    "패스 |  |  | 0.55 |  |  |  |  | 정산 전"), line


def test_a5_csv_file_carries_the_same_text():
    d = Path(tempfile.mkdtemp())
    saved = (roundlog.ROUND_FILE, roundlog.MATCH_FILE)
    roundlog.ROUND_FILE = d / "rounds.csv"
    roundlog.MATCH_FILE = d / "round_matches.csv"
    try:
        roundlog.record(_report([0.25, None, 0.30]))
        with roundlog.ROUND_FILE.open(encoding="utf-8-sig",
                                      newline="") as fh:
            [row] = list(csv.DictReader(fh))
    finally:
        roundlog.ROUND_FILE, roundlog.MATCH_FILE = saved
    assert row["sum_draw"] == "0.55", row


# --------------------------------------------------------------------------
# B. 두 출력이 같은 값을 적는다
# --------------------------------------------------------------------------
def test_b1_log_and_csv_agree():
    for draws, _want in CASES:
        r = _report(draws)
        assert _log_cell(r) == _row_cell(r), draws


def test_b2_log_and_csv_agree_on_the_real_round():
    path = realdata.require()
    report = realdata.load_artifact(path)
    if report.verdict is None or not report.verdict.n:
        raise AssertionError("실물 저장본에 회차 승산이 없다")
    assert _log_cell(report) == _row_cell(report)
    # 저장본 JSON 의 14경기 `probs.draw` 를 직접 더한 값 3.378919 (M10 조사 때
    # 제품 코드를 거치지 않고 잰 것).
    assert _row_cell(report) == "3.38", _row_cell(report)


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        check(name, fn)
    total = _PASSED + _FAILED
    print(f"\n{_PASSED}/{total} 통과" + (f" · 건너뜀 {_SKIPPED}"
                                        if _SKIPPED else ""))
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
