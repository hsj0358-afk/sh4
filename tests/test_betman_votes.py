"""베트맨 투표 현황 — 파싱 · 저장 · 기록 · 화면 · 격리 (§1-68).

    python tests/test_betman_votes.py
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_match_contract import DOMESTIC, real_row  # noqa: E402

from toto import render, roundlog, votes  # noqa: E402
from toto.models import (Match, MatchProb, Report, TeamRef, Votes,  # noqa: E402
                         revive_report)
from toto.sources import betman  # noqa: E402

# 실측 260055 의 1·2경기 셀 (cache/debug/betman_cells_260055.json · 2026-11-21 점검)
REAL_1 = ["투표율\n56.8%\n(2,448,704)", "투표율\n27.9%\n(1,201,009)",
          "투표율\n15.3%\n(659,115)"]
REAL_2 = ["투표율\n62.7%\n(2,699,707)", "투표율\n24.7%\n(1,065,287)",
          "투표율\n12.6%\n(543,834)"]


def _row(no, cells_votes):
    row = real_row(no, *DOMESTIC[no - 1])
    row["cells"][3:6] = cells_votes
    return row


def _round(vote_cells=None):
    return [_row(i, (vote_cells or {}).get(i, REAL_1)) for i in range(1, 15)]


def _probs(h, d, a, _pick=None):
    return MatchProb(home=h, draw=d, away=a)


def _match(no, counts=None, probs=None):
    m = Match(no=no, home=TeamRef(name_ko="가", display="가"),
              away=TeamRef(name_ko="나", display="나"))
    if counts is not None:
        m.votes = Votes(*counts, captured_at="2026-11-21 14:30")
    m.probs = probs
    return m


# ---------------------------------------------------------------- A 파싱
def test_a1_real_cells_parse_in_home_draw_away_order():
    v, why = betman._votes(REAL_1)
    assert why == ""
    assert (v.home, v.draw, v.away) == (2448704, 1201009, 659115)
    assert v.total == 4308828


def test_a2_shares_come_from_counts_not_rounded_pct():
    v, _ = betman._votes(REAL_1)
    h, d, a = v.shares()
    assert abs(h - 2448704 / 4308828) < 1e-12
    assert abs(h + d + a - 1) < 1e-12


def test_a3_two_cells_is_not_read():
    v, why = betman._votes(REAL_1[:2])
    assert not v.available and "2개" in why


def test_a4_counts_that_disagree_with_pct_are_not_read():
    bad = ["투표율\n56.8%\n(659,115)", REAL_1[1], "투표율\n15.3%\n(2,448,704)"]
    v, why = betman._votes(bad)
    assert not v.available and "맞지 않음" in why


def test_a5_no_vote_cells():
    v, why = betman._votes(["1경기", "26.09.26 (토) 01:00"])
    assert not v.available and why == "투표율 칸 없음"


def test_a6_zero_votes_are_observed_but_have_no_shares():
    zero = ["투표율\n0.0%\n(0)"] * 3
    v, why = betman._votes(zero)
    assert why == "" and v.available and v.total == 0
    assert v.shares() is None


def test_a7_round_contract_passes_without_votes():
    rows = _round({5: ["-", "-", "-"]})
    matches = betman.match_list(rows, 14, "R")
    assert len(matches) == 14
    assert not matches[4].votes.available
    assert all(m.votes.available for m in matches if m.no != 5)


def test_a8_parser_does_not_stamp_time():
    """수집 시각은 fetch_matches 가 붙인다 — 파서는 시계를 보지 않는다."""
    matches = betman.match_list(_round(), 14, "R")
    assert all(m.votes.captured_at == "" for m in matches)


def test_a9_real_second_match():
    rows = _round({2: REAL_2})
    m = betman.match_list(rows, 14, "R")[1]
    assert (m.votes.home, m.votes.draw, m.votes.away) == (2699707, 1065287, 543834)


# ---------------------------------------------------------------- B 저장 · 기록
def test_b1_artifact_round_trip_keeps_votes():
    rep = Report(round_id="R", matches=[_match(1, (10, 20, 30))])
    back = revive_report(json.loads(json.dumps(rep.to_dict())))
    v = back.matches[0].votes
    assert (v.home, v.draw, v.away, v.captured_at) == (10, 20, 30, "2026-11-21 14:30")


def test_b2_old_artifact_without_votes_revives_empty():
    rep = Report(round_id="R", matches=[_match(1)])
    d = json.loads(json.dumps(rep.to_dict()))
    del d["matches"][0]["votes"]
    v = revive_report(d).matches[0].votes
    assert not v.available and v.captured_at == ""


def test_b3_roundlog_keeps_counts_and_time():
    rep = Report(round_id="R", matches=[_match(1, (10, 20, 30)), _match(2)])
    rows = roundlog._match_rows(rep)
    assert (rows[0]["vote_home"], rows[0]["vote_draw"], rows[0]["vote_away"],
            rows[0]["votes_at"]) == ("10", "20", "30", "2026-11-21 14:30")
    assert (rows[1]["vote_home"], rows[1]["votes_at"]) == ("", "")
    assert set(rows[0]) == set(roundlog.MATCH_FIELDS)


def test_b4_vote_columns_are_prematch_not_result():
    for name in ("vote_home", "vote_draw", "vote_away", "votes_at"):
        assert name in roundlog.MATCH_FIELDS
        assert name not in roundlog.RESULT_FIELDS


# ---------------------------------------------------------------- C 파생
def test_c1_diff_pp():
    m = _match(1, (50, 30, 20), _probs(0.40, 0.35, 0.25, "H"))
    dh, dd, da = votes.diff_pp(m)
    assert abs(dh - 10) < 1e-9 and abs(dd + 5) < 1e-9 and abs(da + 5) < 1e-9
    assert votes.diff_pp(_match(2, (1, 1, 1))) is None


def test_c2_round_top_combo():
    ms = [_match(1, (60, 30, 10), _probs(0.5, 0.3, 0.2, "H")),
          _match(2, (20, 30, 50), _probs(0.5, 0.3, 0.2, "H"))]
    rv = votes.round_votes(ms)
    assert rv.with_votes == 2 and rv.total == 100
    assert abs(rv.top_share - 0.6 * 0.5) < 1e-12
    assert abs(rv.top_copies - 30) < 1e-9
    assert abs(rv.top_market - 0.5 * 0.2) < 1e-12
    assert rv.differ == [2]


def test_c3_round_combo_needs_every_match():
    ms = [_match(1, (60, 30, 10)), _match(2)]
    rv = votes.round_votes(ms)
    assert rv.with_votes == 1 and rv.top_share is None and rv.top_copies is None


def test_c4_tie_is_not_resolved():
    ms = [_match(1, (40, 40, 20)), _match(2, (60, 30, 10))]
    rv = votes.round_votes(ms)
    assert rv.ties == [1] and rv.top_share is None


def test_c5_totals_differ_means_no_copies():
    ms = [_match(1, (60, 30, 10)), _match(2, (70, 20, 30))]
    rv = votes.round_votes(ms)
    assert rv.total is None and rv.top_share is not None and rv.top_copies is None


# ---------------------------------------------------------------- D 화면
def _report(ms):
    return Report(round_id="R", matches=ms)


def test_d1_block_shows_shares_counts_and_diff():
    m = _match(1, (2448704, 1201009, 659115), _probs(0.52, 0.28, 0.20, "H"))
    html = render._votes_block(m, _report([m]))
    assert "56.8%" in html and "4,308,828표" in html and "2026-11-21 14:30" in html
    assert "투표 − 시장" in html and "+4.8%p" in html


def test_d2_no_votes_anywhere_no_block():
    m = _match(1)
    assert render._votes_block(m, _report([m])) == ""
    assert render._summary_votes(m, render._any_votes([m])) == ""
    assert render._round_votes_block([m]) == ""


def test_d3_missing_votes_when_others_have_them():
    a, b = _match(1, (1, 2, 3)), _match(2)
    html = render._votes_block(b, _report([a, b]))
    assert "읽지 못했습니다" in html
    assert "투표 정보 없음" in render._summary_votes(b, True)


def test_d4_no_pick_words():
    ms = [_match(i, (60, 30, 10), _probs(0.4, 0.3, 0.3, "D")) for i in (1, 2)]
    text = (render._votes_block(ms[0], _report(ms)) + render._round_votes_block(ms)
            + render._summary_votes(ms[0], True))
    for word in ("추천", "가치", "역배", "유력", "홈승", "원정승", "베팅"):
        assert word not in text, word


def test_d5_demo_shows_votes():
    from toto.fixtures import build_demo_matches

    ms = build_demo_matches()
    assert all(m.votes.available for m in ms)
    assert len({m.votes.total for m in ms}) == 1


# ---------------------------------------------------------------- E 격리
ISOLATED = ("panel.py", "panelpacket.py", "panelexport.py", "moderator.py",
            "match_material.py", "evidence.py", "analysis.py", "panelauto.py",
            "panelwork.py", "predict.py", "statmodel.py")


def test_e1_panel_and_analysis_do_not_read_votes():
    for name in ISOLATED:
        tree = ast.parse((ROOT / "toto" / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in ("votes", "toto.votes"), name
                assert not any(a.name in ("votes", "Votes") for a in node.names), name
            if isinstance(node, ast.Import):
                assert not any(a.name == "toto.votes" for a in node.names), name
            if isinstance(node, ast.Attribute):
                assert node.attr != "votes", f"{name}: .votes"


def test_e2_panel_payload_has_no_votes():
    from toto import panel
    from toto.fixtures import build_demo_matches

    m = build_demo_matches()[0]
    text = panel.serialize_payload(panel.build_panel_payload(m))
    assert "vote" not in text and "투표" not in text


def main() -> int:
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    sys.exit(main())
