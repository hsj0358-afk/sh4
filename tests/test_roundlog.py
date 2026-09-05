"""회차 기록 축적 회귀 테스트 (`toto/roundlog.py`).

지나간 회차는 되돌릴 수 없다. 그래서 매 실행이 그 회차를 남기고, 다음 실행이
이미 받아 온 시즌 경기 색인으로 지난 회차를 정산한다 — **새 소스를 붙이지
않는다.**

pytest 없이도 돈다:  python tests/test_roundlog.py
"""
from __future__ import annotations

import ast
import csv
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import roundlog                                      # noqa: E402
from toto.models import (                                      # noqa: E402
    Match, MatchProb, Odds, Report, RoundVerdict, SeasonMatch, TeamRef)


def _match(no: int, home: str, away: str, *, odds=True, kickoff="2026-08-09 18:00"):
    m = Match(no=no,
              home=TeamRef(display=home, canonical=home),
              away=TeamRef(display=away, canonical=away))
    m.league, m.league_ko, m.kickoff_kst = "epl", "프리미어리그", kickoff
    if odds:
        m.odds = Odds(home=1.80, draw=3.60, away=4.20)
        m.probs = MatchProb(home=0.5400, draw=0.2600, away=0.2000,
                            overround=1.05, margin_per_option=0.0167)
    return m


def _report(round_id="260050", matches=None, season=None) -> Report:
    r = Report(round_id=round_id,
               generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
    r.matches = matches if matches is not None else [
        _match(1, "Arsenal", "Chelsea"), _match(2, "Fulham", "Everton")]
    r.season_matches = season or []
    r.verdict = RoundVerdict(n=len(r.matches), expected=7.14, sigma=1.82,
                             z=-1.85, p_ge11=0.03, bet=False)
    return r


def _sandbox():
    """CSV 를 임시 폴더로 돌린다 — 저장소의 실제 기록을 건드리지 않는다."""
    d = Path(tempfile.mkdtemp())
    roundlog.ROUND_FILE = d / "rounds.csv"
    roundlog.MATCH_FILE = d / "round_matches.csv"
    return d


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------- 기본 기록
def test_a1_writes_one_row_per_match():
    _sandbox()
    status = roundlog.record(_report())
    assert status.startswith("ok"), status
    assert len(_rows(roundlog.MATCH_FILE)) == 2


def test_a2_writes_one_row_per_round():
    _sandbox()
    roundlog.record(_report())
    assert len(_rows(roundlog.ROUND_FILE)) == 1


def test_a3_odds_and_probabilities_are_kept():
    _sandbox()
    roundlog.record(_report())
    row = _rows(roundlog.MATCH_FILE)[0]
    assert row["odds_home"] == "1.80", row
    assert row["p_home"] == "0.5400", row
    assert row["pick"] == "H" and row["p_pick"] == "0.5400", row


def test_a4_missing_odds_stay_blank_not_zero():
    """없는 값은 빈칸이다 (§1-5)."""
    _sandbox()
    roundlog.record(_report(matches=[_match(1, "A", "B", odds=False)]))
    row = _rows(roundlog.MATCH_FILE)[0]
    for key in ("odds_home", "p_home", "pick", "p_pick"):
        assert row[key] == "", f"{key}={row[key]!r}"


def test_a5_demo_is_not_recorded():
    _sandbox()
    status = roundlog.record(_report(round_id="DEMO"))
    assert status.startswith("생략"), status
    assert not roundlog.MATCH_FILE.exists()


def test_a6_no_round_id_is_not_recorded():
    _sandbox()
    assert roundlog.record(_report(round_id="")).startswith("생략")


# ------------------------------------------------------------- 재실행 안전
def test_b1_rerunning_the_same_round_does_not_duplicate():
    _sandbox()
    roundlog.record(_report())
    roundlog.record(_report())
    assert len(_rows(roundlog.MATCH_FILE)) == 2, "같은 회차가 두 번 쌓였다"
    assert len(_rows(roundlog.ROUND_FILE)) == 1


def test_b2_different_rounds_accumulate():
    _sandbox()
    roundlog.record(_report(round_id="260050"))
    roundlog.record(_report(round_id="260051"))
    rows = _rows(roundlog.MATCH_FILE)
    assert len(rows) == 4, rows
    assert {r["round"] for r in rows} == {"260050", "260051"}


def test_b3_rows_are_sorted_by_round_then_number():
    _sandbox()
    roundlog.record(_report(round_id="260051"))
    roundlog.record(_report(round_id="260050"))
    rows = _rows(roundlog.MATCH_FILE)
    assert [(r["round"], r["no"]) for r in rows] == [
        ("260050", "1"), ("260050", "2"), ("260051", "1"), ("260051", "2")]


# ---------------------------------------------------------------- 자동 정산
def _season(home, away, hg, ag, when="2026-08-09 18:00", finished=True):
    return SeasonMatch(match_id="1", home_team=home, away_team=away,
                       home_goals=hg, away_goals=ag, finished=finished,
                       kickoff=datetime.strptime(when, "%Y-%m-%d %H:%M"))


def test_c1_past_round_is_settled_from_the_season_index():
    _sandbox()
    roundlog.record(_report(round_id="260050"))
    roundlog.record(_report(round_id="260051", season=[
        _season("Arsenal", "Chelsea", 3, 1),
        _season("Fulham", "Everton", 1, 1)]))
    rows = [r for r in _rows(roundlog.MATCH_FILE) if r["round"] == "260050"]
    assert rows[0]["result"] == "H" and rows[0]["home_goals"] == "3", rows[0]
    assert rows[1]["result"] == "D", rows[1]


def test_c2_pick_hit_is_recorded():
    _sandbox()
    roundlog.record(_report(round_id="260050"))
    roundlog.record(_report(round_id="260051", season=[
        _season("Arsenal", "Chelsea", 3, 1),      # 픽 H → 적중
        _season("Fulham", "Everton", 0, 2)]))     # 픽 H → 실패
    rows = [r for r in _rows(roundlog.MATCH_FILE) if r["round"] == "260050"]
    assert rows[0]["pick_hit"] == "1", rows[0]
    assert rows[1]["pick_hit"] == "0", rows[1]


def test_c3_unfinished_match_is_not_settled():
    _sandbox()
    roundlog.record(_report(round_id="260050"))
    roundlog.record(_report(round_id="260051", season=[
        _season("Arsenal", "Chelsea", None, None, finished=False)]))
    row = _rows(roundlog.MATCH_FILE)[0]
    assert row["result"] == "", row


def test_c4_wrong_date_is_not_settled():
    """같은 팀 짝이 시즌에 두 번 나온다. 날짜가 멀면 채우지 않는다."""
    _sandbox()
    roundlog.record(_report(round_id="260050"))
    roundlog.record(_report(round_id="260051", season=[
        _season("Arsenal", "Chelsea", 3, 1, when="2026-12-20 18:00")]))
    row = _rows(roundlog.MATCH_FILE)[0]
    assert row["result"] == "", "먼 날짜의 경기로 정산했다"


def test_c5_ambiguous_pair_is_left_blank():
    """가릴 수 없으면 비워 둔다 — 틀린 결과가 빈칸보다 나쁘다."""
    _sandbox()
    roundlog.record(_report(round_id="260050",
                            matches=[_match(1, "Arsenal", "Chelsea", kickoff="")]))
    roundlog.record(_report(round_id="260051", season=[
        _season("Arsenal", "Chelsea", 3, 1, when="2026-08-09 18:00"),
        _season("Arsenal", "Chelsea", 0, 0, when="2027-01-10 18:00")]))
    row = _rows(roundlog.MATCH_FILE)[0]
    assert row["result"] == "", row


def test_c6_settlement_rolls_up_to_the_round_row():
    _sandbox()
    roundlog.record(_report(round_id="260050"))
    roundlog.record(_report(round_id="260051", season=[
        _season("Arsenal", "Chelsea", 3, 1),
        _season("Fulham", "Everton", 0, 2)]))
    rnd = [r for r in _rows(roundlog.ROUND_FILE) if r["round"] == "260050"][0]
    assert rnd["settled_matches"] == "2" and rnd["hits"] == "1", rnd


def test_c7_already_settled_rows_are_not_overwritten():
    _sandbox()
    roundlog.record(_report(round_id="260050"))
    roundlog.record(_report(round_id="260051", season=[
        _season("Arsenal", "Chelsea", 3, 1)]))
    first = _rows(roundlog.MATCH_FILE)[0]["settled_at"]
    roundlog.record(_report(round_id="260052", season=[
        _season("Arsenal", "Chelsea", 9, 9)]))
    row = _rows(roundlog.MATCH_FILE)[0]
    assert row["home_goals"] == "3", "이미 정산된 행을 덮어썼다"
    assert row["settled_at"] == first


# ---------------------------------------------------------------- 파일 규칙
def test_d1_written_with_bom_for_excel():
    """한국어 윈도우 엑셀이 BOM 없는 UTF-8 을 cp949 로 읽어 깨뜨린다 (§1-7)."""
    _sandbox()
    roundlog.record(_report())
    assert roundlog.MATCH_FILE.read_bytes()[:3] == b"\xef\xbb\xbf"


def test_d2_korean_survives_a_round_trip():
    _sandbox()
    roundlog.record(_report())
    assert _rows(roundlog.MATCH_FILE)[0]["league"] == "프리미어리그"


def test_d3_unreadable_file_does_not_crash():
    d = _sandbox()
    roundlog.MATCH_FILE.write_bytes(b"\xff\xfe not a csv")
    assert roundlog.record(_report()).startswith("ok")
    assert d.exists()


def test_d4_old_file_missing_columns_is_read():
    """열이 늘어난 뒤에도 옛 파일을 읽을 수 있어야 한다."""
    _sandbox()
    roundlog.MATCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with roundlog.MATCH_FILE.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["round", "no", "home", "away"])
        w.writeheader()
        w.writerow({"round": "260049", "no": "1", "home": "A", "away": "B"})
    assert roundlog.record(_report()).startswith("ok")
    rounds = {r["round"] for r in _rows(roundlog.MATCH_FILE)}
    assert "260049" in rounds, "옛 행이 사라졌다"


# ---------------------------------------------------------------- 금지 사항
def test_e1_does_not_fetch_anything():
    """결과는 이미 받아 온 시즌 색인에서만 온다 — 새 소스를 붙이지 않는다."""
    src = Path(roundlog.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = {"requests", "urllib", "http", "playwright"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in banned, a.name
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            assert root not in banned, node.module
            assert "sources" not in (node.module or ""), node.module


def test_e2_no_recommendation_fields():
    """기록은 평가용이다. 추천을 만들어 두는 자리를 두지 않는다 (§1-3)."""
    for name in ("recommendation", "confidence", "lean", "advice"):
        assert name not in roundlog.MATCH_FIELDS, name
        assert name not in roundlog.ROUND_FIELDS, name


def test_e3_pick_comes_from_predict_not_recomputed():
    """argmax 를 다시 구현하지 않는다 — MatchProb.pick 을 읽는다 (§1-2).

    `max()` 자체를 금지하지는 않는다 — 정산 시각을 고르는 데도 쓴다. 확률
    셋을 견주는 코드가 없는지를 본다.
    """
    src = Path(roundlog.__file__).read_text(encoding="utf-8")
    assert "probs.pick" in src, "픽을 predict 의 값에서 읽지 않는다"
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            names = {getattr(n, "attr", "") for n in ast.walk(node)}
            assert not ({"home", "draw", "away"} & names), \
                "roundlog 안에서 확률을 견주고 있다"


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
