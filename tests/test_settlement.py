"""경기 결과 정산 (Phase 6-C-2).

Phase 6-C-1 조사가 셋을 찾았다.

  · 권위 있는 식별자(FotMob `match_id`)를 `_settle()` 이 손에 쥐고도
    **CSV 경계에서 버렸다.** 그래서 정산은 매번 팀명·날짜로 다시 가려야 했고,
    팀 별칭이 바뀌면(§1-22) 조용히 못 찾았다.
  · `find_season_match()` 가 **naive UTC 와 naive KST 를 직접 뺐다.**
    옳게 짝지은 경기에도 9시간이 남았고, ±4일 창이 그것을 우연히 흡수하고
    있었다 — 창을 8시간으로 줄이면 67/67 이 0/67 이 된다(실측).
  · 결과를 채우려면 **회차 하나를 12분짜리 전체 수집으로 다시 돌려야** 했다.
    정산 전용 경로가 없었다.

여기서 셋을 고정한다. 기존 `tests/test_roundlog.py`(23개)·
`tests/test_market_eval.py`(44개)는 그대로 두고 중복하지 않는다 — 저쪽은
기록 축적과 사전 스냅샷 동결을 보고, 이쪽은 **결과가 붙는 경로**를 본다.

pytest 없이도 돈다:  python tests/test_settlement.py
"""
from __future__ import annotations

import ast
import csv
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import artifact, marketeval, roundlog                # noqa: E402
from toto.models import (KST, Match, MatchProb, Odds, Report,  # noqa: E402
                         RoundVerdict, SeasonMatch, TeamRef, find_season_match,
                         find_season_match_by_id, in_kst)

ROOT = Path(__file__).resolve().parent.parent
UTC = timezone.utc

KICKOFF = "2026-09-12 23:00"          # KST
KICKOFF_UTC = datetime(2026, 9, 12, 14, 0, tzinfo=UTC)   # 같은 순간


# --------------------------------------------------------------------------
# 도구
# --------------------------------------------------------------------------
def _match(no: int, home="Arsenal", away="Chelsea", *, kickoff=KICKOFF,
           odds=(2.00, 3.50, 4.00)) -> Match:
    m = Match(no=no, home=TeamRef(display=home, canonical=home),
              away=TeamRef(display=away, canonical=away))
    m.league, m.league_ko, m.kickoff_kst = "epl", "프리미어리그", kickoff
    m.odds = Odds(home=odds[0], draw=odds[1], away=odds[2])
    m.probs = MatchProb(home=0.5400, draw=0.2600, away=0.2000,
                        overround=1.05, margin_per_option=0.0167)
    return m


def _report(round_id="260052", matches=None, season=None) -> Report:
    r = Report(round_id=round_id, generated_at="2026-09-12 00:11")
    r.matches = matches if matches is not None else [_match(1)]
    r.season_matches = season or []
    r.verdict = RoundVerdict(n=len(r.matches), expected=7.14, sigma=1.82,
                             z=-1.85, p_ge11=0.03, bet=False)
    return r


def _sm(mid="5868011", home="Arsenal", away="Chelsea", *,
        kickoff=KICKOFF_UTC, hg=None, ag=None, finished=False) -> SeasonMatch:
    """실물과 같은 모양 — kickoff 은 **UTC aware** 다 (FotMob 이 `...Z`)."""
    return SeasonMatch(match_id=mid, competition="epl", kickoff=kickoff,
                       kickoff_raw="", kickoff_aware=kickoff.tzinfo is not None,
                       home_team=home, away_team=away,
                       home_goals=hg, away_goals=ag, finished=finished)


def _sandbox() -> Path:
    d = Path(tempfile.mkdtemp())
    roundlog.ROUND_FILE = d / "rounds.csv"
    roundlog.MATCH_FILE = d / "round_matches.csv"
    return d


def _rows() -> list[dict]:
    with roundlog.MATCH_FILE.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# ==========================================================================
# A. match_id 가 CSV 경계까지 보존된다
# ==========================================================================
def test_a1_match_id_is_a_column():
    assert "match_id" in roundlog.MATCH_FIELDS


def test_a2_prematch_row_carries_the_source_id():
    """경기 전 스냅샷에 이미 ID 가 실린다 — 색인에 예정 상태로 있으므로."""
    _sandbox()
    roundlog.record(_report(season=[_sm()]))
    assert _rows()[0]["match_id"] == "5868011"


def test_a3_no_id_is_invented_when_the_index_cannot_tell():
    """가리지 못하면 빈칸이다. ID 를 지어내지 않는다 (§1-5)."""
    _sandbox()
    roundlog.record(_report(season=[]))
    assert _rows()[0]["match_id"] == ""


def test_a4_old_csv_without_the_column_still_reads():
    """열이 없던 옛 파일도 그대로 읽힌다 (backward compatible read)."""
    _sandbox()
    roundlog.MATCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with roundlog.MATCH_FILE.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["round", "no", "home", "away",
                                           "home_canon", "away_canon", "pick"])
        w.writeheader()
        w.writerow({"round": "260050", "no": "1", "home": "A", "away": "B",
                    "home_canon": "Arsenal", "away_canon": "Chelsea",
                    "pick": "H"})
    assert roundlog.record(_report()).startswith("ok")
    old = [r for r in _rows() if r["round"] == "260050"][0]
    assert old["match_id"] == "", "없던 값을 만들어 냈다"
    assert old["home_canon"] == "Arsenal", "옛 행이 깨졌다"


def test_a5_legacy_row_gains_the_id_when_settled():
    """폴백으로 찾았으면 그때 ID 를 **처음** 싣는다 (§4 의 예외)."""
    _sandbox()
    roundlog.record(_report(round_id="260050"))
    rows = _rows()
    assert rows[0]["match_id"] == ""
    roundlog.record(_report(round_id="260051", season=[
        _sm(hg=3, ag=1, finished=True)]))
    row = [r for r in _rows() if r["round"] == "260050"][0]
    assert row["match_id"] == "5868011"
    assert row["result"] == "H"


def test_a6_existing_id_is_never_rewritten():
    """이미 값이 있으면 바꾸지 않는다 — 보강이지 교정이 아니다."""
    rows = [{"round": "260050", "no": "1", "match_id": "OLD", "pick": "H",
             "home_canon": "Arsenal", "away_canon": "Chelsea",
             "kickoff_kst": KICKOFF, "result": ""}]
    out = roundlog.settle_rows(rows, [_sm(mid="OLD", hg=2, ag=0,
                                          finished=True)])
    assert rows[0]["match_id"] == "OLD"
    assert out.linked_ids == 0


# ==========================================================================
# B. match_id 가 폴백보다 먼저다
# ==========================================================================
def _row(**kw) -> dict:
    """CSV 한 행. `_read()` 가 돌려주는 것과 같이 **모든 열이 있다.**"""
    base = {k: "" for k in roundlog.MATCH_FIELDS}
    base.update({"round": "260050", "no": "1", "pick": "H",
                 "home": "홈", "away": "원정",
                 "home_canon": "Arsenal", "away_canon": "Chelsea",
                 "kickoff_kst": KICKOFF})
    base.update(kw)
    return base


def test_b1_team_rename_no_longer_breaks_settlement():
    """팀 별칭이 바뀌어도(§1-22) ID 가 같으면 정산된다."""
    rows = [_row(match_id="5868011", home_canon="옛이름", away_canon="옛이름2")]
    out = roundlog.settle_rows(rows, [_sm(hg=1, ag=1, finished=True)])
    assert out.settled_now == 1 and rows[0]["result"] == "D"
    assert out.by_id == 1


def test_b2_kickoff_moved_far_does_not_block_an_id_match():
    """ID 가 맞으면 킥오프를 다시 보지 않는다 (연기된 경기)."""
    rows = [_row(match_id="5868011", kickoff_kst="2026-08-01 20:00")]
    out = roundlog.settle_rows(rows, [_sm(hg=2, ag=0, finished=True)])
    assert out.settled_now == 1 and rows[0]["result"] == "H"


def test_b3_fallback_still_works_without_an_id():
    rows = [_row()]
    out = roundlog.settle_rows(rows, [_sm(hg=0, ag=2, finished=True)])
    assert out.settled_now == 1 and rows[0]["result"] == "A"
    assert out.by_id == 0


def test_b4_a_known_id_that_is_not_finished_is_not_guessed_by_name():
    """ID 가 있는데 색인에 종료 경기로 없으면 **팀명으로 뒤집지 않는다.**"""
    rows = [_row(match_id="9999")]
    out = roundlog.settle_rows(rows, [_sm(mid="5868011", hg=3, ag=0,
                                          finished=True)])
    assert out.settled_now == 0 and rows[0]["result"] == ""
    assert roundlog.NO_FINISHED in out.reasons


def test_b5_duplicate_ids_are_refused_not_picked():
    dup = [_sm(mid="X", hg=1, ag=0, finished=True),
           _sm(mid="X", home="A", away="B", hg=0, ag=3, finished=True)]
    assert find_season_match_by_id(dup, "X") is None
    rows = [_row(match_id="X")]
    assert roundlog.settle_rows(rows, dup).settled_now == 0


def test_b6_empty_canonicals_are_reported_not_matched():
    rows = [_row(home_canon="", away_canon="")]
    out = roundlog.settle_rows(rows, [_sm(hg=1, ag=0, finished=True)])
    assert out.settled_now == 0
    assert roundlog.NO_CANON in out.reasons


# ==========================================================================
# C. 시간대 — 기준을 통일했다 (창을 줄여서 고치지 않았다)
# ==========================================================================
def test_c1_no_naive_tz_stripping_survives_in_the_matcher():
    """`replace(tzinfo=None)` 로 표시를 떼어 빼는 코드가 남아 있지 않다."""
    src = (ROOT / "toto" / "models.py").read_text(encoding="utf-8")
    body = src[src.index("def find_season_match("):]
    body = body[:body.index("\n@dataclass")]
    assert "replace(tzinfo=None)" not in body, body


def test_c2_utc_and_kst_are_the_same_instant():
    assert in_kst(KICKOFF_UTC) == in_kst(datetime(2026, 9, 12, 23, 0))
    assert abs(in_kst(KICKOFF_UTC)
               - in_kst(datetime(2026, 9, 12, 23, 0))) == timedelta(0)


def test_c3_correct_pair_now_has_zero_gap():
    """예전에는 9시간이 남았다. 지금은 0 이다."""
    sm = _sm()
    row_dt = datetime.strptime(KICKOFF, "%Y-%m-%d %H:%M")
    assert abs(in_kst(sm.kickoff) - in_kst(row_dt)) == timedelta(0)


def test_c4_a_one_hour_window_is_enough_now():
    """**창을 줄이지 않고** 고쳤다는 증거 — 1시간 창에서도 맞는다.

    운영 창은 여전히 ±4일이다(같은 팀 짝이 시즌에 두 번 나오므로). 여기서
    보는 것은 9시간 오차가 사라졌다는 사실뿐이다.
    """
    season = [_sm(hg=1, ag=0, finished=True)]
    row_dt = datetime.strptime(KICKOFF, "%Y-%m-%d %H:%M")
    assert find_season_match(season, "Arsenal", "Chelsea", row_dt,
                             timedelta(hours=1), finished_only=True) is not None


def test_c5_the_operational_window_is_unchanged():
    assert roundlog._SETTLE_WINDOW == timedelta(days=4)
    from toto import match_material
    assert match_material.MATCH_WINDOW == timedelta(days=4)


def test_c6_naive_on_both_sides_behaves_exactly_as_before():
    """양쪽이 다 naive 면 같은 표시가 붙어 차이가 그대로다 — 기존 회귀."""
    naive = datetime(2026, 9, 12, 23, 0)
    season = [SeasonMatch(match_id="1", home_team="Arsenal",
                          away_team="Chelsea", kickoff=naive, finished=True,
                          home_goals=2, away_goals=1)]
    hit = find_season_match(season, "Arsenal", "Chelsea", naive,
                            timedelta(days=4), finished_only=True)
    assert hit is not None and hit.result == "H"


def test_c7_real_artifact_67_finished_matches_still_self_match():
    """실물 회귀 — 저장본 260052 의 종료 경기 전부가 자기 자신을 찾는다.

    Phase 6-C-1 에서 이 실험이 9시간 오차를 드러냈다. 같은 실험을 그대로
    돌린다. 저장본이 없는 환경에서는 건너뛴다(원격 세션은 소스가 차단돼 있어
    저장본을 만들 수 없다, §2-1).
    """
    path = ROOT / "data" / "artifacts" / "260052.json"
    if not path.exists():
        return
    rep, why = artifact.load_path(path)
    assert rep is not None, why
    season = [sm for sm in rep.season_matches
              if sm.finished and sm.home_goals is not None
              and sm.away_goals is not None]
    assert len(season) >= 60, len(season)
    for sm in season:
        kst = sm.kickoff.astimezone(KST).strftime("%Y-%m-%d %H:%M")
        hit = find_season_match(season, sm.home_team, sm.away_team,
                                roundlog._kickoff_date(kst),
                                roundlog._SETTLE_WINDOW, finished_only=True)
        assert hit is not None and hit.match_id == sm.match_id, sm.match_id
        # 그리고 **창을 1시간으로 줄여도** 맞는다 (오차가 사라졌다).
        tight = find_season_match(season, sm.home_team, sm.away_team,
                                  roundlog._kickoff_date(kst),
                                  timedelta(hours=1), finished_only=True)
        assert tight is not None, sm.match_id


# ==========================================================================
# D. 경기 전 스냅샷은 정산으로 바뀌지 않는다
# ==========================================================================
_FROZEN = ("round", "no", "recorded_at", "league", "kickoff_kst",
           "home", "away", "home_canon", "away_canon",
           "odds_home", "odds_draw", "odds_away",
           "p_home", "p_draw", "p_away", "pick", "p_pick", "gap", "toss_up")


def test_d1_settlement_changes_only_the_result_fields():
    _sandbox()
    roundlog.record(_report(round_id="260050", season=[_sm()]))
    before = dict(_rows()[0])
    out, why = roundlog.settle("260050", [_sm(hg=3, ag=1, finished=True)])
    assert out is not None, why
    after = dict(_rows()[0])
    for f in _FROZEN:
        assert before[f] == after[f], f
    assert after["result"] == "H" and after["home_goals"] == "3"


def test_d2_the_id_is_not_changed_by_settlement_either():
    _sandbox()
    roundlog.record(_report(round_id="260050", season=[_sm()]))
    assert _rows()[0]["match_id"] == "5868011"
    roundlog.settle("260050", [_sm(hg=0, ag=0, finished=True)])
    assert _rows()[0]["match_id"] == "5868011"


def test_d3_result_fields_are_exactly_the_five():
    assert roundlog.RESULT_FIELDS == ("home_goals", "away_goals", "result",
                                      "pick_hit", "settled_at")
    assert set(_FROZEN) | set(roundlog.RESULT_FIELDS) \
        | {"match_id"} == set(roundlog.MATCH_FIELDS)


# ==========================================================================
# E. 결과 칸이 정확히 채워진다
# ==========================================================================
def test_e1_all_five_fields_are_filled():
    rows = [_row()]
    roundlog.settle_rows(rows, [_sm(hg=2, ag=1, finished=True)],
                         stamp="2026-09-14 10:00")
    assert rows[0]["home_goals"] == "2"
    assert rows[0]["away_goals"] == "1"
    assert rows[0]["result"] == "H"
    assert rows[0]["pick_hit"] == "1"
    assert rows[0]["settled_at"] == "2026-09-14 10:00"


def test_e2_pick_hit_is_zero_when_the_pick_missed():
    rows = [_row(pick="A")]
    roundlog.settle_rows(rows, [_sm(hg=2, ag=1, finished=True)])
    assert rows[0]["pick_hit"] == "0"


def test_e3_no_pick_leaves_pick_hit_blank():
    rows = [_row(pick="")]
    roundlog.settle_rows(rows, [_sm(hg=1, ag=1, finished=True)])
    assert rows[0]["result"] == "D" and rows[0]["pick_hit"] == ""


def test_e4_an_unfinished_match_is_never_settled():
    rows = [_row()]
    out = roundlog.settle_rows(rows, [_sm(hg=None, ag=None, finished=False)])
    assert out.settled_now == 0 and rows[0]["result"] == ""
    assert out.unsettled == 1


def test_e5_finished_without_a_score_is_not_settled():
    """`None` 을 0 으로 바꾸지 않는다 (§1-5)."""
    rows = [_row()]
    out = roundlog.settle_rows(rows, [_sm(hg=None, ag=None, finished=True)])
    assert out.settled_now == 0 and rows[0]["home_goals"] == ""


def test_e6_counts_add_up():
    """`rows = already + settled_now + unsettled` 가 언제나 성립한다."""
    rows = [_row(no="1"), _row(no="2", match_id="Z"),
            _row(no="3", result="H", home_goals="1", away_goals="0")]
    out = roundlog.settle_rows(rows, [_sm(hg=1, ag=0, finished=True)])
    assert out.rows == out.already + out.settled_now + out.unsettled == 3


# ==========================================================================
# F. 이미 정산된 경기는 다시 쓰지 않는다
# ==========================================================================
def test_f1_second_settlement_changes_nothing():
    _sandbox()
    roundlog.record(_report(round_id="260050", season=[_sm()]))
    roundlog.settle("260050", [_sm(hg=3, ag=1, finished=True)])
    first = dict(_rows()[0])
    roundlog.settle("260050", [_sm(hg=9, ag=9, finished=True)])
    assert dict(_rows()[0]) == first, "이미 정산된 행을 덮어썼다"


def test_f2_a_conflict_is_reported_not_applied():
    rows = [_row(result="H", home_goals="2", away_goals="0",
                 settled_at="2026-09-14 10:00")]
    out = roundlog.settle_rows(rows, [_sm(hg=1, ag=1, finished=True)])
    assert rows[0]["result"] == "H" and rows[0]["home_goals"] == "2"
    assert len(out.conflicts) == 1 and "기록 H" in out.conflicts[0]
    assert out.already == 1 and out.settled_now == 0


def test_f3_matching_result_is_not_a_conflict():
    rows = [_row(result="D", home_goals="1", away_goals="1")]
    out = roundlog.settle_rows(rows, [_sm(hg=1, ag=1, finished=True)])
    assert out.conflicts == []


# ==========================================================================
# G. 지정 회차만 처리한다
# ==========================================================================
def test_g1_other_rounds_are_untouched():
    _sandbox()
    roundlog.record(_report(round_id="260050", season=[_sm()]))
    roundlog.record(_report(round_id="260051", matches=[
        _match(1, "Fulham", "Everton", kickoff="2026-09-20 20:00")]))
    before = {r["round"]: dict(r) for r in _rows()}
    roundlog.settle("260050", [
        _sm(hg=1, ag=0, finished=True),
        _sm(mid="777", home="Fulham", away="Everton",
            kickoff=datetime(2026, 9, 20, 11, 0, tzinfo=UTC),
            hg=4, ag=4, finished=True)])
    after = {r["round"]: dict(r) for r in _rows()}
    assert after["260051"] == before["260051"], "다른 회차를 건드렸다"
    assert after["260050"]["result"] == "H"


def test_g2_a_missing_round_is_not_created():
    _sandbox()
    roundlog.record(_report(round_id="260050"))
    out, why = roundlog.settle("999999", [_sm(hg=1, ag=0, finished=True)])
    assert out is None and "경기 전 기록이 없습니다" in why
    assert {r["round"] for r in _rows()} == {"260050"}


def test_g3_nothing_to_do_does_not_rewrite_the_file():
    _sandbox()
    roundlog.record(_report(round_id="260050", season=[_sm()]))
    stamp = roundlog.MATCH_FILE.stat().st_mtime_ns
    raw = roundlog.MATCH_FILE.read_bytes()
    out, why = roundlog.settle("260050", [])
    assert out is not None and out.settled_now == 0
    assert roundlog.MATCH_FILE.read_bytes() == raw
    assert roundlog.MATCH_FILE.stat().st_mtime_ns == stamp


def test_g4_settle_only_touches_its_own_round_rows():
    rows = [_row(round="260050"), _row(round="260051", no="1")]
    out = roundlog.settle_rows(rows, [_sm(hg=1, ag=0, finished=True)],
                               round_id="260050")
    assert out.rows == 1
    assert rows[0]["result"] == "H" and rows[1]["result"] == ""


# ==========================================================================
# H. artifact 와 리포트를 건드리지 않는다
# ==========================================================================
def test_h1_settlement_does_not_import_render_or_artifact():
    """정산은 화면을 만들지 않는다 — 저장본도 리포트도 손대지 않는다."""
    src = (ROOT / "toto" / "roundlog.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "render" not in (node.module or ""), node.module
            assert "artifact" not in (node.module or ""), node.module


def test_h2_settle_round_does_not_write_the_artifact():
    _sandbox()
    with tempfile.TemporaryDirectory() as d:
        rep = _report(round_id="260050", season=[_sm()])
        artifact.save(rep, outdir=Path(d), now=datetime(2026, 9, 12, 0, 11))
        path = Path(d) / "260050.json"
        raw = path.read_bytes()
        roundlog.record(rep)
        roundlog.settle("260050", [_sm(hg=3, ag=1, finished=True)])
        assert path.read_bytes() == raw, "정산이 저장본을 다시 썼다"


def test_h3_artifact_freeze_policy_is_unchanged():
    rep = _report(round_id="260050", season=[_sm()])
    with tempfile.TemporaryDirectory() as d:
        artifact.save(rep, outdir=Path(d), now=datetime(2026, 9, 12, 0, 11))
        after = artifact.save(rep, outdir=Path(d),
                              now=datetime(2026, 9, 14, 4, 0))
        assert after.startswith("생략") and "사전 스냅샷 보존" in after


def test_h4_cli_settle_branch_runs_before_collection():
    """수집 구간 **앞**에서 갈라진다 — 베트맨·피나클·후스코어드를 부르지 않는다."""
    src = (ROOT / "toto" / "cli.py").read_text(encoding="utf-8")
    assert src.index("args.settle_round") < src.index("from .sources import betman")
    assert "_settle_round(args, settings)" in src


# ==========================================================================
# I. market-eval 연계
# ==========================================================================
def test_i1_unsettled_rows_are_not_evaluated():
    _sandbox()
    roundlog.record(_report(round_id="260050", season=[_sm()]))
    s = marketeval.evaluate(marketeval.load_rows(roundlog.MATCH_FILE))
    assert s.evaluated == 0
    assert any("실제 결과" in e.reason for e in s.excluded)


def test_i2_settled_rows_become_evaluable():
    _sandbox()
    roundlog.record(_report(round_id="260050", season=[_sm()]))
    roundlog.settle("260050", [_sm(hg=3, ag=1, finished=True)])
    s = marketeval.evaluate(marketeval.load_rows(roundlog.MATCH_FILE))
    assert s.evaluated == 1, s.exclusion_counts
    assert s.rows[0].actual == "H"


def test_i3_metric_values_are_unchanged_by_this_phase():
    """지표 계산 자체는 건드리지 않았다 — 손계산과 같아야 한다."""
    rows = [marketeval.EvalRow(market={"H": 0.5, "D": 0.3, "A": 0.2},
                               actual="H")]
    assert abs(marketeval.brier_score(rows) - (0.25 + 0.09 + 0.04)) < 1e-12
    assert marketeval.market_favorite_accuracy(rows) == 1.0


def test_i4_market_eval_still_ignores_the_new_column():
    """`match_id` 를 더해도 평가 조건은 그대로다 (§10)."""
    src = (ROOT / "toto" / "marketeval.py").read_text(encoding="utf-8")
    assert "match_id" not in src


# ==========================================================================
# J. 공유 구조 — 정산 로직을 두 벌로 두지 않는다
# ==========================================================================
def test_j1_both_paths_call_the_same_function():
    src = (ROOT / "toto" / "roundlog.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    callers = {node.name for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef)
               and "settle_rows" in ast.dump(node)}
    assert {"record", "settle"} <= callers, callers


def test_j2_roundlog_still_fetches_nothing():
    """결과는 넘겨받은 색인에서만 온다 — 새 소스를 붙이지 않는다 (§1-6-2)."""
    src = (ROOT / "toto" / "roundlog.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = {"requests", "urllib", "http", "playwright"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in banned, a.name
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned, node.module
            assert "sources" not in (node.module or ""), node.module


def test_j3_no_new_result_parser_in_fotmob():
    """색인 전용 경로도 **같은 `_parse_matches`** 를 쓴다 (§17)."""
    src = (ROOT / "toto" / "sources" / "fotmob.py").read_text(encoding="utf-8")
    body = src[src.index("def _read_season("):]
    assert "_parse_matches(data, resolver)" in body
    for word in ("score", "goals"):
        assert f'"{word}"' not in body.split("def ", 2)[0], word


def test_j4_season_index_reuses_merge_season():
    from toto.sources import fotmob
    src = (ROOT / "toto" / "sources" / "fotmob.py").read_text(encoding="utf-8")
    assert src.count("def merge_season(") == 1
    assert "merge_season(" in src[src.index("def enrich("):]
    assert "merge_season(" in src[src.index("def season_index("):
                                  src.index("def _read_season(")]
    assert hasattr(fotmob, "season_index")


def test_j5_season_cache_uses_its_own_key():
    """부분 결과를 `league_{key}` 에 쓰면 다음 수집이 그것을 적중으로 읽는다."""
    from toto.sources import fotmob
    assert fotmob.SEASON_CACHE_KEY == "season_{key}"
    body = (ROOT / "toto" / "sources" / "fotmob.py").read_text(encoding="utf-8")
    body = body[body.index("def _read_season("):]
    assert 'cache.set("fotmob", f"league_' not in body


def test_j6_season_index_without_leagues_is_skipped_not_failed():
    from toto.sources import fotmob
    from toto.settings import load_settings
    season, status = fotmob.season_index(load_settings(), None, [])
    assert season == [] and status.startswith("생략")


def test_j6b_a_full_cache_hit_never_opens_a_browser():
    """`[1]` 을 돌린 날이면 접속하지 않는다 — 브라우저조차 띄우지 않는다.

    브라우저를 띄우면 이 테스트가 터진다(원격 세션은 소스가 차단돼 있다).
    그래서 '안 띄운다' 를 **실행으로** 확인할 수 있다.
    """
    from toto.cache import Cache
    from toto.settings import load_settings
    from toto.sources import fotmob

    with tempfile.TemporaryDirectory() as d:
        cache = Cache(root=Path(d), day="today")
        cache.set("fotmob", "league_epl", fotmob._freeze({
            "teams": {},
            "matches": [{"id": 5795446, "date": "2026-09-12",
                         "utc": "2026-09-12T14:00:00Z",
                         "home": "Arsenal", "away": "Chelsea",
                         "home_id": 9825, "away_id": 8455,
                         "home_goals": 2, "away_goals": 1, "finished": True}],
        }))
        season, status = fotmob.season_index(
            load_settings(), None, ["epl"], cache=cache)
    assert len(season) == 1 and season[0].match_id == "5795446"
    assert season[0].finished and season[0].result == "H"
    assert status.startswith("ok") and "캐시 1리그" in status
    assert "--no-cache" in status, "캐시를 썼다는 사실과 우회 방법을 안 적었다"


def test_j7_no_recommendation_leaks_into_the_new_fields():
    for name in ("recommendation", "confidence", "lean", "advice", "pick_ok"):
        assert name not in roundlog.MATCH_FIELDS, name


# ==========================================================================
# K. 부분 성공과 파일 보호
# ==========================================================================
def test_k1_one_unmatched_row_does_not_block_the_others():
    _sandbox()
    roundlog.record(_report(round_id="260050", matches=[
        _match(1, "Arsenal", "Chelsea"),
        _match(2, "Fulham", "Everton", kickoff="2026-09-12 23:00")]))
    out, why = roundlog.settle("260050", [_sm(hg=2, ag=0, finished=True)])
    assert out is not None, why
    assert out.settled_now == 1 and out.unsettled == 1
    rows = sorted(_rows(), key=lambda r: r["no"])
    assert rows[0]["result"] == "H" and rows[1]["result"] == ""
    assert sum(out.reasons.values()) == 1


def test_k2_writes_are_atomic():
    """옆에 다 쓴 뒤 바꿔 끼운다 — 도중에 죽어도 반쯤 잘린 파일이 안 남는다."""
    src = (ROOT / "toto" / "roundlog.py").read_text(encoding="utf-8")
    body = src[src.index("def _write("):src.index("def _kickoff_date(")]
    assert "os.replace" in body
    assert '.tmp' in body


def test_k3_no_temp_file_is_left_behind():
    _sandbox()
    roundlog.record(_report(round_id="260050"))
    leftovers = list(roundlog.MATCH_FILE.parent.glob("*.tmp"))
    assert leftovers == [], leftovers


def test_k4_bom_survives_the_atomic_write():
    _sandbox()
    roundlog.record(_report(round_id="260050"))
    assert roundlog.MATCH_FILE.read_bytes()[:3] == b"\xef\xbb\xbf"


# --------------------------------------------------------------------------
def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as exc:
            bad += 1
            print(f"  FAIL {fn.__name__}: {exc}")
        except Exception as exc:                        # noqa: BLE001
            bad += 1
            print(f"  ERR  {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - bad}/{len(tests)} 통과")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
