"""사전 스냅샷 불변성과 시장 캘리브레이션 (Phase 6-B).

Phase 6-A 조사에서 **덮어쓰기 두 군데**를 찾았다.

  · `artifact.save()` 가 무조건 덮어써서, 결과가 나온 뒤 같은 회차를 다시
    돌리면 킥오프 전 스냅샷이 사후 스냅샷으로 조용히 교체됐다.
  · `roundlog.record()` 가 같은 회차 행을 통째로 교체해서 `odds_*`·`p_*` 가
    사후 값으로 바뀌었다. 결과(`result`)는 보존됐지만 **확률이 바뀌면**
    그 회차는 시장 캘리브레이션 표본으로 쓸 수 없다.

둘을 고쳤고 여기서 고정한다. 그리고 **잴 수 있는 것이 무엇인지**도 함께
고정한다 — 이 프로젝트에는 대상 경기의 독립적인 모델 확률이 없으므로
`Market ↔ Actual` 하나뿐이다.

기존 `tests/test_time_safety.py` 의 21개는 그대로 두고 중복하지 않는다.
저쪽은 **분석 입력**에 미래가 섞이지 않는가를 보고, 이쪽은 **저장된 사전
스냅샷**이 사후에 바뀌지 않는가를 본다.

pytest 없이도 돈다:  python tests/test_market_eval.py
"""
from __future__ import annotations

import ast
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import artifact, marketeval, roundlog                # noqa: E402
from toto.models import Match, Report, TeamRef                 # noqa: E402
from toto.predict import additive_probabilities                # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

KICKOFF = "2026-09-12 23:00"
BEFORE = datetime(2026, 9, 12, 0, 11)      # 킥오프 23시간 전
AFTER = datetime(2026, 9, 13, 4, 0)        # 킥오프 뒤


def _match(no: int, odds: tuple[float, float, float], kickoff=KICKOFF) -> Match:
    m = Match(no=no, home=TeamRef(name_ko="홈", canonical=f"Home{no}"),
              away=TeamRef(name_ko="원정", canonical=f"Away{no}"))
    m.kickoff_kst = kickoff
    m.league = "epl"
    m.odds.home, m.odds.draw, m.odds.away = odds
    m.odds.source = "arcadia-api"
    m.probs = additive_probabilities(*odds)
    return m


def _report(odds=(2.00, 3.50, 4.00), round_id="260099", n=2) -> Report:
    r = Report(round_id=round_id, generated_at="2026-09-12 00:11")
    r.matches = [_match(i + 1, odds) for i in range(n)]
    return r


# --------------------------------------------------------------------------
# A. artifact — 시작한 회차의 저장본을 덮어쓰지 않는다
# --------------------------------------------------------------------------
def test_a1_first_save_is_allowed():
    with tempfile.TemporaryDirectory() as d:
        s = artifact.save(_report(), outdir=Path(d), now=BEFORE)
        assert s.startswith("ok"), s


def test_a2_prematch_resave_still_overwrites():
    """아직 한 경기도 시작하지 않았으면 옛것도 새것도 사전 스냅샷이다 —
    수집이 반쯤 실패한 뒤 다시 돌리는 것이 정상 흐름이라 막지 않는다."""
    with tempfile.TemporaryDirectory() as d:
        artifact.save(_report(), outdir=Path(d), now=BEFORE)
        s = artifact.save(_report((1.50, 4.00, 6.00)), outdir=Path(d), now=BEFORE)
        assert s.startswith("ok"), s
        rep, why = artifact.load(_report().round_id, outdir=Path(d))
        assert rep is not None, why
        assert abs(rep.matches[0].odds.home - 1.50) < 1e-9   # 새 값이 들어갔다


def test_a3_after_kickoff_the_saved_snapshot_is_frozen():
    """**Test B** — 사후 재실행이 사전 artifact 를 덮어쓰지 않는다."""
    with tempfile.TemporaryDirectory() as d:
        artifact.save(_report(), outdir=Path(d), now=BEFORE)
        s = artifact.save(_report((1.10, 9.00, 20.0)), outdir=Path(d), now=AFTER)
        assert s.startswith("생략"), s
        assert "사전 스냅샷 보존" in s, s
        rep, why = artifact.load("260099", outdir=Path(d))
        assert rep is not None, why
        assert abs(rep.matches[0].odds.home - 2.00) < 1e-9, "사전 배당이 바뀌었다"


def test_a4_first_save_after_kickoff_is_still_allowed():
    """파일이 아예 없으면 늦게라도 남긴다 — 평가에서 빼면 되고,
    그 판정은 `recorded_at` 으로 한다."""
    with tempfile.TemporaryDirectory() as d:
        s = artifact.save(_report(), outdir=Path(d), now=AFTER)
        assert s.startswith("ok"), s


def test_a5_unknown_kickoff_is_not_assumed_prematch():
    rep = _report()
    for m in rep.matches:
        m.kickoff_kst = ""
    assert artifact.is_prematch(rep, BEFORE) is False


def test_a6_prematch_uses_the_analysis_cutoff_helper():
    """시각 파싱을 새로 만들지 않았다 (§1-8)."""
    src = (ROOT / "toto" / "artifact.py").read_text(encoding="utf-8")
    assert "as_of_from_match" in src
    assert "strptime" not in src, "artifact 가 kickoff 을 따로 파싱한다"


def test_a7_rerender_path_is_untouched():
    """저장본 읽기는 그대로여야 한다 (5-E3a)."""
    with tempfile.TemporaryDirectory() as d:
        artifact.save(_report(), outdir=Path(d), now=BEFORE)
        rep, why = artifact.load_path(Path(d) / "260099.json")
        assert rep is not None, why
        assert len(rep.matches) == 2


# --------------------------------------------------------------------------
# B. roundlog — 사전 값은 얼고 결과만 채워진다
# --------------------------------------------------------------------------
def _rows(monkey_dir: Path, report: Report, now: datetime) -> list[dict]:
    """`record()` 를 임시 폴더에 돌리고 경기 행을 돌려준다."""
    old_m, old_r = roundlog.MATCH_FILE, roundlog.ROUND_FILE
    real_now = roundlog.datetime
    roundlog.MATCH_FILE = monkey_dir / "round_matches.csv"
    roundlog.ROUND_FILE = monkey_dir / "rounds.csv"

    class _Clock:
        @staticmethod
        def now():
            return now
        strptime = staticmethod(datetime.strptime)
    roundlog.datetime = _Clock
    try:
        roundlog.record(report)
        return roundlog._read(roundlog.MATCH_FILE, roundlog.MATCH_FIELDS)
    finally:
        roundlog.MATCH_FILE, roundlog.ROUND_FILE = old_m, old_r
        roundlog.datetime = real_now


def test_b1_pre_match_probability_survives_a_later_run():
    """**Test A** — 같은 회차를 두 번 돌려도 최초 시장 확률이 안 바뀐다."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        first = _rows(p, _report(), BEFORE)
        assert first[0]["p_home"] and first[0]["odds_home"] == "2.00"
        later = _rows(p, _report((1.10, 9.00, 20.0)), AFTER)
        assert later[0]["odds_home"] == "2.00", "사후 배당이 덮어썼다"
        assert later[0]["p_home"] == first[0]["p_home"], "사후 확률이 덮어썼다"


def test_b2_every_pre_match_field_is_identical():
    """**Test E** — 결과 칸 말고는 값이 한 글자도 안 바뀐다."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        before = _rows(p, _report(), BEFORE)[0]
        after = _rows(p, _report((1.10, 9.00, 20.0)), AFTER)[0]
        for f in roundlog.MATCH_FIELDS:
            if f in roundlog.RESULT_FIELDS:
                continue
            assert before[f] == after[f], f


def test_b3_prematch_rerun_still_refreshes():
    """킥오프 전이면 새 배당으로 갱신된다 — 얼리는 것은 시작한 뒤부터다."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        _rows(p, _report(), BEFORE)
        later = _rows(p, _report((1.50, 4.00, 6.00)), BEFORE)
        assert later[0]["odds_home"] == "1.50"


def test_b4_settlement_only_fills_result_fields():
    """**Test C** — 정산은 결과만 채우고 사전 값을 건드리지 않는다."""
    row = {f: "" for f in roundlog.MATCH_FIELDS}
    row.update({"round": "260099", "no": "1", "home_canon": "Home1",
                "away_canon": "Away1", "kickoff_kst": KICKOFF,
                "odds_home": "2.00", "p_home": "0.4185", "pick": "H"})
    frozen = dict(row)

    from toto.models import SeasonMatch
    rep = Report(round_id="260100")
    rep.season_matches = [SeasonMatch(
        match_id="x1", competition="epl",
        kickoff=datetime(2026, 9, 12, 14, 0), kickoff_aware=False,
        home_team="Home1", away_team="Away1",
        home_goals=2, away_goals=1, finished=True)]
    assert roundlog.settle_rows([row], rep.season_matches).settled_now == 1
    assert row["result"] == "H" and row["pick_hit"] == "1"
    for f in roundlog.MATCH_FIELDS:
        if f not in roundlog.RESULT_FIELDS:
            # `match_id` 는 옛 행이 처음 확보할 때만 채워진다 (6-C-2 §4).
            if f == roundlog.ID_FIELD and not frozen[f]:
                continue
            assert row[f] == frozen[f], f


def test_b5_already_settled_rows_are_not_resettled():
    row = {f: "" for f in roundlog.MATCH_FIELDS}
    row.update({"round": "260099", "no": "1", "home_canon": "Home1",
                "away_canon": "Away1", "kickoff_kst": KICKOFF, "result": "D"})
    from toto.models import SeasonMatch
    rep = Report(round_id="260100")
    rep.season_matches = [SeasonMatch(
        match_id="x1", competition="epl",
        kickoff=datetime(2026, 9, 12, 14, 0), kickoff_aware=False,
        home_team="Home1", away_team="Away1",
        home_goals=2, away_goals=1, finished=True)]
    assert roundlog.settle_rows([row], rep.season_matches).settled_now == 0
    assert row["result"] == "D"


def test_b6_rows_missing_from_the_new_round_are_kept():
    """기록은 축적이 목적이다 — 목록에서 빠졌다고 버리지 않는다."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        _rows(p, _report(n=3), BEFORE)
        later = _rows(p, _report(n=2), AFTER)
        assert {r["no"] for r in later} == {"1", "2", "3"}


def test_b7_unknown_kickoff_freezes():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        r1 = _report()
        for m in r1.matches:
            m.kickoff_kst = ""
        _rows(p, r1, BEFORE)
        r2 = _report((1.10, 9.00, 20.0))
        for m in r2.matches:
            m.kickoff_kst = ""
        later = _rows(p, r2, BEFORE)
        assert later[0]["odds_home"] == "2.00"


def test_b8_status_line_says_it_preserved():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        _rows(p, _report(), BEFORE)
        old_m, old_r = roundlog.MATCH_FILE, roundlog.ROUND_FILE
        real = roundlog.datetime
        roundlog.MATCH_FILE = p / "round_matches.csv"
        roundlog.ROUND_FILE = p / "rounds.csv"

        class _Clock:
            @staticmethod
            def now():
                return AFTER
            strptime = staticmethod(datetime.strptime)
        roundlog.datetime = _Clock
        try:
            s = roundlog.record(_report((1.10, 9.00, 20.0)))
        finally:
            roundlog.MATCH_FILE, roundlog.ROUND_FILE = old_m, old_r
            roundlog.datetime = real
        assert "사전 스냅샷 보존" in s, s


# --------------------------------------------------------------------------
# C. 평가 대상 고르기 — 모자라면 빼고 사유를 남긴다
# --------------------------------------------------------------------------
def _row(**kw) -> dict:
    base = {f: "" for f in roundlog.MATCH_FIELDS}
    base.update({"round": "260099", "no": "1", "league": "epl",
                 "kickoff_kst": KICKOFF, "recorded_at": "2026-09-12 00:11",
                 "home": "홈", "away": "원정",
                 "p_home": "0.4000", "p_draw": "0.3000", "p_away": "0.3000",
                 "result": "H", "home_goals": "2", "away_goals": "1"})
    base.update(kw)
    return base


def test_c1_complete_row_is_selected():
    picked, dropped = marketeval.select([_row()])
    assert len(picked) == 1 and not dropped


def test_c2_missing_probability_is_excluded():
    picked, dropped = marketeval.select([_row(p_draw="")])
    assert not picked and "시장 확률이 없습니다" in dropped[0].reason


def test_c3_missing_result_is_excluded():
    picked, dropped = marketeval.select([_row(result="")])
    assert not picked and "실제 결과가 없습니다" in dropped[0].reason


def test_c4_post_kickoff_probability_is_excluded():
    """**Test D** — 킥오프 이후에 기록된 확률은 사전 스냅샷이 아니다."""
    picked, dropped = marketeval.select(
        [_row(recorded_at="2026-09-13 04:00")])
    assert not picked
    assert "킥오프 이후" in dropped[0].reason, dropped[0].reason


def test_c5_duplicate_match_is_excluded_once():
    picked, dropped = marketeval.select([_row(), _row()])
    assert len(picked) == 1
    assert "두 번" in dropped[0].reason


def test_c6_probabilities_must_sum_to_one():
    picked, dropped = marketeval.select(
        [_row(p_home="0.9000", p_draw="0.9000", p_away="0.9000")])
    assert not picked and "합이 1이 아닙니다" in dropped[0].reason


def test_c7_none_is_never_turned_into_zero():
    picked, _ = marketeval.select([_row(home_goals="", away_goals="")])
    assert picked[0].home_goals is None and picked[0].away_goals is None


def test_c8_unreadable_timestamps_are_excluded():
    picked, dropped = marketeval.select([_row(recorded_at="언제")])
    assert not picked and "읽지 못했" in dropped[0].reason


# --------------------------------------------------------------------------
# D. 지표
# --------------------------------------------------------------------------
def _ev(ph, pd_, pa, actual) -> marketeval.EvalRow:
    return marketeval.EvalRow(round_id="R", no=1,
                              market={"H": ph, "D": pd_, "A": pa},
                              actual=actual)


def test_d1_favorite_accuracy():
    rows = [_ev(0.6, 0.2, 0.2, "H"), _ev(0.6, 0.2, 0.2, "A"),
            _ev(0.2, 0.2, 0.6, "A"), _ev(0.2, 0.6, 0.2, "D")]
    assert abs(marketeval.market_favorite_accuracy(rows) - 0.75) < 1e-12


def test_d2_brier_is_zero_for_a_perfect_forecast():
    assert abs(marketeval.brier_score([_ev(1.0, 0.0, 0.0, "H")])) < 1e-12


def test_d3_brier_is_two_for_a_perfectly_wrong_forecast():
    assert abs(marketeval.brier_score([_ev(1.0, 0.0, 0.0, "A")]) - 2.0) < 1e-12


def test_d4_brier_hand_computed():
    # (0.6−1)² + (0.2−0)² + (0.2−0)² = 0.16 + 0.04 + 0.04 = 0.24
    assert abs(marketeval.brier_score([_ev(0.6, 0.2, 0.2, "H")]) - 0.24) < 1e-12


def test_d5_log_loss_hand_computed():
    import math
    got = marketeval.log_loss([_ev(0.5, 0.3, 0.2, "H")])
    assert abs(got - (-math.log(0.5))) < 1e-12


def test_d6_log_loss_clips_zero_instead_of_exploding():
    got = marketeval.log_loss([_ev(0.0, 0.5, 0.5, "H")])
    assert got is not None and got < float("inf")


def test_d7_empty_sample_gives_none_not_zero():
    for fn in (marketeval.market_favorite_accuracy, marketeval.brier_score,
               marketeval.log_loss):
        assert fn([]) is None, fn.__name__


def test_d8_calibration_counts_three_pairs_per_match():
    bins = marketeval.calibration_table([_ev(0.6, 0.2, 0.2, "H")])
    assert sum(b.count for b in bins) == 3


def test_d9_calibration_bin_values():
    rows = [_ev(0.65, 0.2, 0.15, "H"), _ev(0.65, 0.2, 0.15, "A")]
    bins = {(b.low, b.high): b for b in marketeval.calibration_table(rows)}
    b = bins[(0.6, 0.7)]
    assert b.count == 2
    assert abs(b.mean_predicted - 0.65) < 1e-12
    assert abs(b.actual_frequency - 0.5) < 1e-12      # 둘 중 하나만 홈승


def test_d10_empty_bins_are_none_not_zero():
    bins = marketeval.calibration_table([_ev(0.6, 0.2, 0.2, "H")])
    empty = [b for b in bins if b.count == 0]
    assert empty and all(b.mean_predicted is None
                         and b.actual_frequency is None for b in empty)


def test_d11_probability_of_one_lands_in_the_top_bin():
    bins = marketeval.calibration_table([_ev(1.0, 0.0, 0.0, "H")])
    assert bins[-1].count == 1


# --------------------------------------------------------------------------
# E. 경계 — 모델 확률을 만들지 않고, 보정값을 되돌려 넣지 않는다
# --------------------------------------------------------------------------
SRC = (ROOT / "toto" / "marketeval.py").read_text(encoding="utf-8")


BODY = SRC.split('"""', 2)[-1]          # 모듈 설명을 뺀 본문


def test_e1_no_model_probability_field():
    """지금은 시장뿐이다. 없는 것을 있는 것처럼 두지 않는다.

    모듈 설명에는 "만들지 않는다" 고 적혀 있으므로 **본문만** 본다.
    """
    assert "model_probability" not in BODY
    assert "model_p_" not in BODY


def test_e2_does_not_import_predict_or_touch_probs():
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module not in ("predict", "models", ".predict"), node.module
        if isinstance(node, ast.Import):
            for a in node.names:
                assert "predict" not in a.name, a.name
    assert "Match.probs" not in SRC.replace("`Match.probs`", "")


def test_e3_makes_no_recommendation():
    """추천을 만들지 않는다. '추천' 은 **부정문으로만** 나온다 (§1-17)."""
    for banned in ("recommend", "confidence", "신뢰도", "확신도"):
        assert banned not in BODY, banned
    import re
    for m in re.finditer("추천", BODY):
        tail = BODY[m.start():m.start() + 20]
        assert "않" in tail or "아니" in tail, tail


def test_e4_favorite_is_not_called_a_pick():
    assert hasattr(marketeval.EvalRow, "favorite")
    for banned in ("def pick", "def recommendation", "def winner"):
        assert banned not in SRC, banned


def test_e5_summary_with_no_sample_says_so():
    s = marketeval.evaluate([_row(result="")])
    assert s.evaluated == 0
    text = marketeval.format_summary(s)
    assert "평가할 표본이 없습니다" in text
    for banned in ("Brier", "로그 손실"):
        assert banned not in text.split("평가할 표본이 없습니다")[1]


def test_e6_summary_names_what_it_measured():
    s = marketeval.evaluate([_row()])
    text = marketeval.format_summary(s)
    assert "시장" in text
    assert "모델 확률이 아직 없어" in text


def test_e7_evaluate_does_not_mutate_input():
    rows = [_row()]
    snapshot = [dict(r) for r in rows]
    marketeval.evaluate(rows)
    assert rows == snapshot


def test_e8_reuses_roundlog_reader():
    """새 CSV 파서를 만들지 않았다 (§1-8)."""
    assert "roundlog._read" in SRC
    for node in ast.walk(ast.parse(SRC)):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name != "csv", "CSV 파서를 새로 만들었다"


def test_e9_cli_market_eval_does_not_collect():
    """수집 구간 **앞**에서 갈라진다 — `--rerender-artifact` 와 같은 자리.

    재는 자리는 `main()` **안**이다. 파일 전체에서 찾으면, 수집기를 지연
    import 하는 다른 함수가 앞쪽에 생길 때(6-C-2 의 `_settle_round`) 첫
    등장 위치가 그리로 옮겨 가 엉뚱한 판정이 된다.
    """
    import inspect

    from toto import cli
    src = inspect.getsource(cli.main)
    i = src.index("args.market_eval")
    j = src.index("from .sources import")
    assert i < j, "market-eval 분기가 수집 구간 뒤에 있다"


# --------------------------------------------------------------------------
# F. 실제 파이프라인 한 바퀴
# --------------------------------------------------------------------------
def test_f1_end_to_end_round_trip():
    """기록 → 정산 → 평가. 사전 확률이 살아남고 지표가 나온다."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        rows = _rows(p, _report(n=1), BEFORE)
        # 다음 회차 실행이 결과를 채운다
        from toto.models import SeasonMatch
        nxt = Report(round_id="260100")
        nxt.season_matches = [SeasonMatch(
            match_id="x1", competition="epl",
            kickoff=datetime(2026, 9, 12, 14, 0), kickoff_aware=False,
            home_team="Home1", away_team="Away1",
            home_goals=2, away_goals=1, finished=True)]
        roundlog.settle_rows(rows, nxt.season_matches)

        s = marketeval.evaluate(rows)
        assert s.evaluated == 1, s.exclusion_counts
        assert s.rows[0].actual == "H"
        want = additive_probabilities(2.00, 3.50, 4.00)     # 사전 배당 그대로
        assert abs(s.rows[0].market["H"] - want.home) < 1e-4
        assert s.brier is not None and s.logloss is not None
        assert s.favorite_accuracy == 1.0


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
