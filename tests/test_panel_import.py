"""Panel Result JSON 가져오기 회귀 테스트 (Phase 4-B).

고정하려는 것은 여섯 가지다.

1. **검증이 두 벌이 아니다.** 경기 하나의 내용은 `panel.parse_opinion()` 과
   `moderator.parse_result()` 가 검사한다 — API 로 받든 파일로 받든 같은 문을
   지난다.
2. **두 분석가의 원안이 보존된다.** DA · 맞대결 · 사회자 채택 셋을 언제나
   따로 확인할 수 있다.
3. **근거를 지어내면 잡힌다.** 근거 0건인 경기에서 `E001` 을 쓰면 오류다
   (260050 에서 실제로 나온 상태의 회귀 픽스처).
4. **부분 import 를 정상으로 취급하지 않는다.** 한 경기라도 깨지면 붙이지
   않는다.
5. **판정하지 않는다.** 확률·확신도·승무패를 만들지 않는다.
6. **원문을 고치지 않는다.**

pytest 없이도 돈다:  python tests/test_panel_import.py
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import panelimport                                     # noqa: E402
from toto.models import (EvidenceItem, Match, MatchAnalysis,     # noqa: E402
                         Odds, Report, SeasonMatch, TeamAnalysis, TeamRef)
from toto.settings import Settings                               # noqa: E402

DA = panelimport.DATA_ROLE
MU = panelimport.MATCHUP_ROLE
S = Settings(panel={"debate_simulations": 30})


# --------------------------------------------------------------------------
# 픽스처
# --------------------------------------------------------------------------
def _ev(claim="기회 창출이 많다") -> EvidenceItem:
    return EvidenceItem(claim=claim, metric="npxg", value=2.4,
                        period="recent6", sample_count=6, team="Arsenal",
                        category="attack", context="recent",
                        finding_kind="chance", source="shotmap",
                        measurement_basis="shot_events")


# 경기마다 **다른 팀 짝**을 쓴다. 같은 짝이 여러 번 나오면 시즌 색인에서
# 가릴 수 없어(`find_season_match` 가 옳게 거부한다) match_id 가 비고,
# 그러면 이 테스트가 재려는 것과 다른 경로를 타게 된다.
_TEAMS = [("Arsenal", "Chelsea"), ("Liverpool", "Everton"),
          ("Man City", "Burnley"), ("Spurs", "Fulham"),
          ("Newcastle", "Brentford"), ("Villa", "Wolves"),
          ("Leeds", "Palace"), ("Forest", "Bournemouth"),
          ("Brighton", "Sunderland"), ("West Ham", "Leicester"),
          ("Inter", "Napoli"), ("Roma", "Atalanta"),
          ("Juventus", "Milan"), ("Bologna", "Sassuolo")]


def _match(no=1, evidence=1, home=None, away=None) -> Match:
    home = home or _TEAMS[(no - 1) % len(_TEAMS)][0]
    away = away or _TEAMS[(no - 1) % len(_TEAMS)][1]
    m = Match(no=no, league="epl",
              home=TeamRef(display=home, canonical=home, name_ko=home),
              away=TeamRef(display=away, canonical=away, name_ko=away))
    m.league_ko, m.kickoff_kst = "프리미어리그", f"2026-09-{no:02d} 20:00"
    m.odds = Odds(home=2.1, draw=3.4, away=3.6, source="arcadia-api")
    m.analysis = MatchAnalysis(home=TeamAnalysis(team=home, is_home=True),
                               away=TeamAnalysis(team=away, is_home=False),
                               evidence=[_ev() for _ in range(evidence)])
    return m


def _season(match: Match, mid: str) -> SeasonMatch:
    return SeasonMatch(
        match_id=mid, competition="epl",
        kickoff=datetime.strptime(match.kickoff_kst, "%Y-%m-%d %H:%M"),
        home_team=match.home.canonical, away_team=match.away.canonical,
        finished=False)


def _report(n=1, evidence=1, round_id="260050") -> Report:
    r = Report(generated_at="2026-09-06 12:00", round_id=round_id)
    r.matches = [_match(no=i, evidence=evidence) for i in range(1, n + 1)]
    r.season_matches = [_season(m, f"400{m.no:03d}") for m in r.matches]
    return r


def _opinion(role, home=2, away=1, ids=None, summary="핵심 판단입니다."):
    return {"role": role, "predicted_home": home, "predicted_away": away,
            "summary": summary, "rationale": ["근거 해석 한 줄"],
            "evidence_ids": list(ids if ids is not None else ["E001"])}


# 기본 픽스처는 **깨끗한 경우**여야 한다. 채택 1-1 은 맞대결의 원안이므로
# `adopted_from` 도 그렇게 적는다 — 비워 두면 재계산 경고가 늘 따라붙어
# 다른 테스트가 무엇을 재는지 흐려진다.
def _mod(adopted=(1, 1), adopted_from=(MU,), dist=None, sims=30,
         ids=None, conclusion="30회 토론 결과 예상 스코어는 1-1 입니다."):
    body = {
        "role": "moderator",
        "simulations": sims,
        "distribution": list(dist if dist is not None else [
            {"home": 2, "away": 1, "count": 19, "origin": DA},
            {"home": 1, "away": 1, "count": 11, "origin": MU}]),
        "adopted_home": adopted[0], "adopted_away": adopted[1],
        "adopted_from": list(adopted_from),
        "conclusion": conclusion,
        "common_points": ["표본이 작다"], "differences": ["스코어가 갈린다"],
        "counterpoints": [], "market_relation": "",
        "uncertainty": ["표본 2경기"],
        "evidence_ids": list(ids if ids is not None else []),
    }
    return body


def _block(match: Match, mid: str, da=None, mu=None, mod=None) -> dict:
    return {"match_id": mid, "match_number": match.no,
            "home_team": match.home.display, "away_team": match.away.display,
            DA: da if da is not None else _opinion(DA, 2, 1),
            MU: mu if mu is not None else _opinion(MU, 1, 1),
            "moderator": mod if mod is not None else _mod()}


def _payload(report: Report, **per_match) -> dict:
    blocks = []
    for m in report.matches:
        mid = f"400{m.no:03d}"
        blocks.append(_block(m, mid, **per_match))
    return {"schema_version": "1.0", "round": report.round_id,
            "generated_at": "2026-09-06T14:00:00+09:00", "matches": blocks}


def _run(data, report=None, settings=S):
    report = report if report is not None else _report()
    return panelimport.validate(data, report, settings), report


def _codes(result) -> set[str]:
    return {i.code for i in result.issues}


# --------------------------------------------------------------------------
# A. 골든 케이스 (§27 Case 1~5)
# --------------------------------------------------------------------------
def _case(da, mu, adopted, adopted_from, dist=None):
    report = _report()
    data = _payload(report,
                    da=_opinion(DA, *da), mu=_opinion(MU, *mu),
                    mod=_mod(adopted=adopted, adopted_from=adopted_from,
                             dist=dist))
    return panelimport.validate(data, report, S)


def test_a1_case1_moderator_takes_the_matchup_score():
    """DA 2-1 · 맞대결 1-1 · 사회자 1-1 — 맞대결 원안이다."""
    res = _case((2, 1), (1, 1), (1, 1), [])
    assert res.success, [str(i) for i in res.issues]
    mod = res.runs[1].moderator
    assert (mod.adopted_home, mod.adopted_away) == (1, 1)
    # `adopted_from` 을 비워 보냈지만 실제로는 맞대결의 원안이다.
    # **조용히 고치지 않는다** — 다시 정하고 그 사실을 남긴다 (§5).
    assert mod.adopted_from == (MU,), mod.adopted_from
    assert "ADOPTED_FROM_RECOMPUTED" in _codes(res), _codes(res)


def test_a2_case2_data_analyst_original_is_adopted():
    res = _case((2, 1), (1, 1), (2, 1), [DA])
    assert res.success, [str(i) for i in res.issues]
    assert res.runs[1].moderator.adopted_from == (DA,)
    assert "ADOPTED_FROM_RECOMPUTED" not in _codes(res)


def test_a3_case3_matchup_original_is_adopted():
    res = _case((2, 1), (1, 2), (1, 2), [MU],
                dist=[{"home": 2, "away": 1, "count": 12, "origin": DA},
                      {"home": 1, "away": 2, "count": 18, "origin": MU}])
    assert res.success, [str(i) for i in res.issues]
    assert res.runs[1].moderator.adopted_from == (MU,)


def test_a4_case4_both_analysts_proposed_the_same_score():
    res = _case((1, 1), (1, 1), (1, 1), [DA, MU],
                dist=[{"home": 1, "away": 1, "count": 30, "origin": DA}])
    assert res.success, [str(i) for i in res.issues]
    assert set(res.runs[1].moderator.adopted_from) == {DA, MU}


def test_a5_case5_compromise_score():
    """어느 쪽도 처음에 내지 않은 스코어. `adopted_from` 은 빈 목록이다."""
    res = _case((2, 1), (1, 1), (2, 0), [],
                dist=[{"home": 2, "away": 1, "count": 12, "origin": DA},
                      {"home": 1, "away": 1, "count": 8, "origin": MU},
                      {"home": 2, "away": 0, "count": 10,
                       "origin": "compromise"}])
    assert res.success, [str(i) for i in res.issues]
    mod = res.runs[1].moderator
    assert (mod.adopted_home, mod.adopted_away) == (2, 0)
    assert mod.adopted_from == ()
    assert res.audit["adopted_compromise"] == 1


def test_a6_case6_wrong_adopted_from_is_caught():
    """DA 2-1 · 맞대결 1-1 인데 채택 1-1 을 DA 것이라고 했다 → 오류."""
    res = _case((2, 1), (1, 1), (1, 1), [DA])
    assert not res.success
    assert "ADOPTED_FROM_MISMATCH" in _codes(res)
    assert any("내지 않았습니다" in i.message for i in res.errors)


# --------------------------------------------------------------------------
# B. 근거 (§27 Case 7·8 · §10 · §11)
# --------------------------------------------------------------------------
def test_b1_case7_unknown_evidence_id():
    report = _report(evidence=1)                   # E001 하나뿐
    data = _payload(report, da=_opinion(DA, 2, 1, ids=["E999"]))
    res, _ = _run(data, report)
    assert not res.success
    assert "UNKNOWN_EVIDENCE_ID" in _codes(res)


def test_b2_case8_no_evidence_but_ids_cited():
    """**260050 회귀 픽스처.** 근거 0건인데 E001·E002 를 인용했다."""
    report = _report(evidence=0)
    data = _payload(report, da=_opinion(DA, 2, 1, ids=["E001", "E002"]))
    res, _ = _run(data, report)
    assert not res.success
    assert "EVIDENCE_ABSENT_BUT_CITED" in _codes(res)
    assert any("[] 여야" in i.message for i in res.errors)


def test_b3_empty_evidence_ids_pass_when_there_is_no_evidence():
    report = _report(evidence=0)
    data = _payload(report, da=_opinion(DA, 2, 1, ids=[]),
                    mu=_opinion(MU, 1, 1, ids=[]))
    res, _ = _run(data, report)
    assert res.success, [str(i) for i in res.issues]


def test_b4_evidence_is_scoped_to_the_match():
    """근거 ID 는 **경기마다 다시 매겨진다** — 1번의 E002 를 2번이 쓸 수 없다."""
    report = _report(n=2, evidence=1)              # 두 경기 다 E001 하나
    report.matches[0].analysis.evidence.append(_ev("두 번째 근거"))
    data = _payload(report)
    data["matches"][1][DA]["evidence_ids"] = ["E002"]   # 2번엔 E002 가 없다
    res, _ = _run(data, report)
    assert not res.success
    assert "UNKNOWN_EVIDENCE_ID" in _codes(res)
    assert any(i.match_no == 2 for i in res.errors), [str(i) for i in res.errors]


def test_b5_program_never_creates_evidence():
    src = inspect.getsource(panelimport)
    assert "E001" not in src and "E00" not in src, "ID 를 코드에 박았다"


# --------------------------------------------------------------------------
# C. 경기 대응 (§13 · §27 Case 10~12)
# --------------------------------------------------------------------------
def test_c1_case10_duplicate_match_id():
    report = _report(n=2)
    data = _payload(report)
    data["matches"][1]["match_id"] = data["matches"][0]["match_id"]
    res, _ = _run(data, report)
    assert not res.success
    assert "DUPLICATE_MATCH_ID" in _codes(res)


def test_c2_case11_missing_match():
    report = _report(n=2)
    data = _payload(report)
    data["matches"].pop()
    res, _ = _run(data, report)
    assert not res.success
    assert "MATCH_COUNT_MISMATCH" in _codes(res)
    assert "MATCH_MISSING" in _codes(res)


def test_c3_case12_unknown_match_id():
    report = _report(n=1)
    data = _payload(report)
    data["matches"][0]["match_id"] = "9999999"
    res, _ = _run(data, report)
    assert not res.success
    assert "UNKNOWN_MATCH_ID" in _codes(res)


def test_c4_team_identity_is_checked_against_the_id():
    report = _report()
    data = _payload(report)
    data["matches"][0]["home_team"] = "Liverpool"
    res, _ = _run(data, report)
    assert not res.success
    assert "TEAM_MISMATCH" in _codes(res)


def test_c5_match_number_is_only_a_display_id():
    """번호가 어긋나도 `match_id` 로 잇는다 — 다른 경기에 붙이지 않는다."""
    report = _report(n=2)
    data = _payload(report)
    data["matches"][0]["match_number"] = 7
    res, _ = _run(data, report)
    assert res.success, [str(i) for i in res.issues]
    assert "MATCH_NUMBER_MISMATCH" in _codes(res)
    # 1번 경기의 결과가 1번에 붙었다.
    assert res.runs[1].opinions[0].summary == "핵심 판단입니다."


def test_c6_count_mismatch_is_an_error():
    report = _report(n=2)
    data = _payload(_report(n=1))
    data["round"] = report.round_id
    res, _ = _run(data, report)
    assert not res.success
    assert "MATCH_COUNT_MISMATCH" in _codes(res)


# --------------------------------------------------------------------------
# D. 스키마 · 회차 (§12 · §27 Case 13·15)
# --------------------------------------------------------------------------
def test_d1_case15_round_mismatch():
    report = _report()
    data = _payload(report)
    data["round"] = "260051"
    res, _ = _run(data, report)
    assert not res.success
    assert "ROUND_MISMATCH" in _codes(res)


def test_d2_round_as_number_still_matches():
    """회차를 숫자로 적어도 같은 회차면 통과한다 — 형식만 다른 경우다."""
    report = _report()
    data = _payload(report)
    data["round"] = 260050
    res, _ = _run(data, report)
    assert "ROUND_MISMATCH" not in _codes(res)


def test_d3_missing_round_is_an_error():
    report = _report()
    data = _payload(report)
    del data["round"]
    res, _ = _run(data, report)
    assert "ROUND_MISMATCH" in _codes(res)


def test_d4_schema_version_is_required_and_checked():
    report = _report()
    data = _payload(report)
    del data["schema_version"]
    assert "SCHEMA_VERSION_MISSING" in _codes(_run(data, report)[0])
    data["schema_version"] = "9.9"
    assert "SCHEMA_VERSION_UNSUPPORTED" in _codes(_run(data, report)[0])


def test_d5_case13_string_score_is_rejected():
    report = _report()
    data = _payload(report, da=_opinion(DA, "2", 1))
    res, _ = _run(data, report)
    assert not res.success
    assert "INVALID_ANALYST" in _codes(res)


def test_d6_bool_and_negative_scores_are_rejected():
    for bad in (True, -1, 1.5):
        report = _report()
        data = _payload(report, da=_opinion(DA, bad, 1))
        res, _ = _run(data, report)
        assert not res.success, bad
        assert "INVALID_ANALYST" in _codes(res), bad


def test_d7_malformed_json_is_reported_not_raised():
    path = Path(tempfile.mkdtemp()) / "bad.json"
    path.write_text("{ not json", encoding="utf-8")
    res = panelimport.run(path, _report(), S)
    assert not res.success
    assert "UNREADABLE" in _codes(res)


def test_d8_missing_file_is_reported():
    res = panelimport.run(Path(tempfile.mkdtemp()) / "nope.json", _report(), S)
    assert not res.success and "UNREADABLE" in _codes(res)


# --------------------------------------------------------------------------
# E. 역할 · 금지 필드 (§6 · §15 · §27 Case 14)
# --------------------------------------------------------------------------
def test_e1_case14_forbidden_field_is_rejected():
    for bad in ("winner", "pick", "confidence", "recommendation",
                "favorite", "probability"):
        report = _report()
        data = _payload(report)
        data["matches"][0]["moderator"][bad] = "home"
        res, _ = _run(data, report)
        assert not res.success, bad
        assert "FORBIDDEN_FIELD" in _codes(res), bad


def test_e2_market_is_not_an_analyst_role():
    report = _report()
    data = _payload(report, da={**_opinion(DA), "role": "market_analyst"})
    res, _ = _run(data, report)
    assert not res.success
    assert "ROLE_MISMATCH" in _codes(res) or "FORBIDDEN_ROLE" in _codes(res)


def test_e3_missing_analyst_is_an_error():
    report = _report()
    data = _payload(report)
    del data["matches"][0][MU]
    res, _ = _run(data, report)
    assert not res.success
    assert "MISSING_ANALYST" in _codes(res)


def test_e4_missing_moderator_is_an_error():
    report = _report()
    data = _payload(report)
    del data["matches"][0]["moderator"]
    res, _ = _run(data, report)
    assert not res.success
    assert "MISSING_MODERATOR" in _codes(res)


# --------------------------------------------------------------------------
# F. 분포 (§8 · §34)
# --------------------------------------------------------------------------
def test_f1_counts_must_add_up():
    report = _report()
    data = _payload(report, mod=_mod(sims=30, dist=[
        {"home": 1, "away": 1, "count": 10, "origin": MU}]))
    res, _ = _run(data, report)
    assert not res.success
    assert "INVALID_DISTRIBUTION" in _codes(res)


def test_f2_adopted_must_appear_in_the_distribution():
    report = _report()
    data = _payload(report, mod=_mod(adopted=(3, 3)))
    res, _ = _run(data, report)
    assert not res.success
    assert "ADOPTED_NOT_IN_DISTRIBUTION" in _codes(res)


def test_f3_origin_is_recomputed_from_the_proposals():
    """`origin` 을 모델 말대로 믿지 않는다 (3-C 규칙 그대로)."""
    report = _report()
    data = _payload(report, mod=_mod(dist=[
        {"home": 2, "away": 1, "count": 19, "origin": MU},   # 틀린 origin
        {"home": 1, "away": 1, "count": 11, "origin": DA}]))
    res, _ = _run(data, report)
    assert res.success, [str(i) for i in res.issues]
    origins = {(t.home, t.away): t.origin
               for t in res.runs[1].moderator.distribution}
    assert origins[(2, 1)] == DA and origins[(1, 1)] == MU


def test_f4_missing_simulations_is_a_warning_not_a_hardcoded_30():
    report = _report()
    data = _payload(report, mod=_mod())
    del data["matches"][0]["moderator"]["simulations"]
    res, _ = _run(data, report)
    assert res.success, [str(i) for i in res.issues]
    assert "SIMULATIONS_MISSING" in _codes(res)
    assert res.runs[1].moderator.simulations == 30
    src = inspect.getsource(panelimport)
    assert "== 30" not in src and "!= 30" not in src, "30 을 박아 뒀다"


def test_f5_distribution_is_never_turned_into_a_probability():
    tree = ast.parse(inspect.getsource(panelimport))
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(
                node.op, (ast.Div, ast.FloorDiv)):
            raise AssertionError("나눗셈이 있다 (분포를 확률로 바꾸고 있나)")
        if isinstance(node, ast.Call):
            fn = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
            assert fn not in ("mean", "fmean", "median", "average"), fn


# --------------------------------------------------------------------------
# G. 감사 (§9 · §27 Case 9)
# --------------------------------------------------------------------------
def test_g1_case9_matchup_origin_zero_is_a_warning_not_an_error():
    """260050 에서 실제로 나온 상태다. **그 자체로는 오류가 아니다.**"""
    report = _report(n=3)
    data = _payload(report, da=_opinion(DA, 1, 1), mu=_opinion(MU, 1, 1),
                    mod=_mod(adopted=(1, 1), adopted_from=[DA, MU], dist=[
                        {"home": 1, "away": 1, "count": 30, "origin": DA}]))
    res, _ = _run(data, report)
    assert res.success, [str(i) for i in res.issues]
    assert "MATCHUP_ORIGIN_ZERO" in _codes(res)
    assert res.audit["distribution_origin_rows"].get(MU) is None


def test_g2_audit_separates_zero_origin_from_a_missing_analyst():
    """origin 0회와 '분석가가 없었다' 는 다른 상태다 (§9)."""
    report = _report(n=2)
    data = _payload(report, da=_opinion(DA, 1, 1), mu=_opinion(MU, 1, 1),
                    mod=_mod(adopted=(1, 1), adopted_from=[DA, MU], dist=[
                        {"home": 1, "away": 1, "count": 30, "origin": DA}]))
    res, _ = _run(data, report)
    assert res.audit["analysts_agree"] == 2, res.audit
    assert res.audit["analysts_disagree"] == 0
    # 분석가는 둘 다 참여했다 — 그 사실이 결과에 남아 있다.
    for run in res.runs.values():
        assert {o.role for o in run.opinions} == {DA, MU}
    warn = next(i for i in res.warnings if i.code == "MATCHUP_ORIGIN_ZERO")
    assert "참여하지 않은 것과는 다른" in warn.message


def test_g3_audit_counts_disagreement_and_compromise():
    report = _report(n=2)
    data = _payload(report)
    data["matches"][1]["moderator"] = _mod(
        adopted=(2, 0), adopted_from=[], dist=[
            {"home": 2, "away": 1, "count": 12, "origin": DA},
            {"home": 2, "away": 0, "count": 18, "origin": "compromise"}])
    res, _ = _run(data, report)
    assert res.success, [str(i) for i in res.issues]
    assert res.audit["analysts_disagree"] == 2
    assert res.audit["adopted_compromise"] == 1
    assert res.audit["adopted_from_matchup_analyst"] == 1


def test_g4_report_lines_show_the_audit_without_judging():
    report = _report(n=2)
    res, _ = _run(_payload(report), report)
    text = "\n".join(panelimport.report_lines(res))
    assert "감사" in text and "분포 origin" in text
    for banned in ("신뢰", "정확", "우세", "%"):
        assert banned not in text, banned


# --------------------------------------------------------------------------
# G-2. 260050 실물 재현 픽스처 (§28)
#
# 이 대화에서 확인된 260050 Panel Result 의 특징을 그대로 만든다.
# **정상 결과로 표시하지 않는다** — 오류·주의를 정확히 잡아내는지 보는
# 감사 픽스처다.
# --------------------------------------------------------------------------
def _like_260050(evidence=0) -> tuple[dict, Report]:
    """14경기 · 두 분석가가 늘 같은 원안 · 맞대결 origin 0 · E001 인용."""
    report = _report(n=14, evidence=evidence)
    blocks = []
    for m in report.matches:
        blocks.append(_block(
            m, f"400{m.no:03d}",
            da=_opinion(DA, 2, 1, ids=["E001"]),
            mu=_opinion(MU, 2, 1, ids=["E001"]),
            mod=_mod(adopted=(2, 1), adopted_from=[DA, MU], ids=["E001"],
                     dist=[{"home": 2, "away": 1, "count": 30,
                            "origin": DA}],
                     conclusion="30회 토론 결과 예상 스코어는 2-1 입니다.")))
    return ({"schema_version": "1.0", "round": report.round_id,
             "generated_at": "2026-09-06T14:00:00+09:00",
             "matches": blocks}, report)


def test_g5_260050_shape_is_not_silently_accepted():
    """근거 0건인데 E001 을 썼다 — 14경기 전부에서 잡혀야 한다."""
    data, report = _like_260050(evidence=0)
    res, _ = _run(data, report)
    assert not res.success, "실물의 문제를 정상으로 받았다"
    cited = [i for i in res.errors if i.code == "EVIDENCE_ABSENT_BUT_CITED"]
    assert len(cited) == 14 * 3, len(cited)      # 두 분석가 + 사회자
    assert res.runs == {}


def test_g6_260050_shape_with_evidence_passes_but_warns():
    """근거가 실제로 있으면 가져올 수는 있다. 다만 감사가 상태를 드러낸다."""
    data, report = _like_260050(evidence=1)
    res, _ = _run(data, report)
    assert res.success, [str(i) for i in res.issues][:5]
    assert res.audit["matches"] == 14
    assert res.audit["analysts_agree"] == 14
    assert res.audit["analysts_disagree"] == 0
    assert res.audit["distribution_origin_rows"].get(MU) is None
    codes = _codes(res)
    assert "MATCHUP_ORIGIN_ZERO" in codes
    assert "ANALYSTS_NEVER_DISAGREE" in codes
    # 그래도 **오류는 아니다** — 두 분석가가 늘 같은 스코어를 냈을 수 있다.
    assert not res.errors


def test_g7_260050_shape_keeps_all_three_scores_separable():
    """§4 — DA · 맞대결 · 사회자 셋을 언제나 따로 볼 수 있어야 한다."""
    data, report = _like_260050(evidence=1)
    res, _ = _run(data, report)
    run = res.runs[1]
    assert (run.opinion(DA).predicted_home,
            run.opinion(DA).predicted_away) == (2, 1)
    assert (run.opinion(MU).predicted_home,
            run.opinion(MU).predicted_away) == (2, 1)
    assert (run.moderator.adopted_home, run.moderator.adopted_away) == (2, 1)


# --------------------------------------------------------------------------
# H. 원본 보존 · 부분 import 금지 (§21 · §23)
# --------------------------------------------------------------------------
def test_h1_imported_text_is_unchanged():
    report = _report()
    long_text = "  줄바꿈\n과 **굵게** 가 든 원문  "
    data = _payload(report, da=_opinion(DA, 2, 1, summary=long_text))
    res, _ = _run(data, report)
    op = res.runs[1].opinion(DA)
    assert op.summary == long_text.strip(), "원문을 고쳤다"
    assert "**굵게**" in op.summary, "markdown 을 해석했다"


def test_h2_input_dict_is_not_mutated():
    report = _report()
    data = _payload(report)
    before = copy.deepcopy(data)
    panelimport.validate(data, report, S)
    assert data == before, "입력 JSON 을 바꿨다"


def test_h3_one_broken_match_blocks_the_whole_import():
    report = _report(n=3)
    data = _payload(report)
    data["matches"][2]["match_id"] = "9999999"
    res, _ = _run(data, report)
    assert not res.success
    assert res.runs == {}, "실패인데 결과를 남겼다"
    assert "UNKNOWN_MATCH_ID" in _codes(res), _codes(res)
    assert panelimport.attach(res, report) == 0
    assert all(m.panel is None for m in report.matches)


def test_h4_successful_import_attaches_to_matches():
    report = _report(n=2)
    res, _ = _run(_payload(report), report)
    assert res.success
    assert panelimport.attach(res, report) == 2
    for m in report.matches:
        assert m.panel is not None
        assert m.panel.status.startswith("ok")
        assert m.panel.moderator is not None


def test_h5_analysis_data_is_untouched():
    from dataclasses import asdict
    report = _report(n=2)
    before = [asdict(m.analysis) for m in report.matches]
    res, _ = _run(_payload(report), report)
    panelimport.attach(res, report)
    assert [asdict(m.analysis) for m in report.matches] == before


# --------------------------------------------------------------------------
# I. 검증이 두 벌이 아니다 (§2)
# --------------------------------------------------------------------------
def test_i1_uses_the_phase3_validators():
    src = inspect.getsource(panelimport)
    assert "panel.parse_opinion(" in src
    assert "moderator.parse_result(" in src


def test_i2_score_rules_are_not_copied_here():
    """`_score`·`_goals` 같은 검사를 여기에 베끼지 않는다."""
    tree = ast.parse(inspect.getsource(panelimport))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in ("_score", "_goals", "_scores"), node.name


def test_i3_no_wdl_helper_exists():
    src = inspect.getsource(panelimport)
    # `consensus` 는 **금지 목록 상수**에 이름으로 들어 있다 — 그것을 막는
    # 코드이지 만드는 코드가 아니므로 함수 정의만 본다.
    for banned in ("def _winner", "def _wdl", "def _to_result",
                   "def _pick", "def _consensus"):
        assert banned not in src, banned
    assert "consensus" in panelimport.FORBIDDEN_FIELDS


def test_i4_llm_cache_is_not_reused_as_import_storage():
    """Phase 3 의 LLM 캐시는 API 호출용이다 — import 저장소로 쓰지 않는다."""
    tree = ast.parse(inspect.getsource(panelimport))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.lstrip("."))
        elif isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
    for banned in ("cache", "llm", "requests", "sources", "evidence"):
        assert not any(m == banned or m.startswith(banned + ".")
                       for m in mods), banned


def test_i5_cli_flags_are_wired():
    src = (Path(__file__).resolve().parent.parent / "toto"
           / "cli.py").read_text(encoding="utf-8")
    assert "--import-panel-result" in src
    assert "--validate-panel-result" in src
    assert "attach_result=args.import_panel_result is not None" in src


def test_i6_validate_only_does_not_attach():
    report = _report()
    path = Path(tempfile.mkdtemp()) / "p.json"
    path.write_text(json.dumps(_payload(report), ensure_ascii=False),
                    encoding="utf-8")
    res = panelimport.run(path, report, S, attach_result=False)
    assert res.success
    assert all(m.panel is None for m in report.matches), "검사만인데 붙였다"


# --------------------------------------------------------------------------
# J. 파일 경로 안전 (§32)
# --------------------------------------------------------------------------
def test_j1_json_cannot_point_at_another_file():
    """Panel Result 안의 문자열을 경로로 해석하지 않는다."""
    src = inspect.getsource(panelimport)
    assert "read_text" in src
    tree = ast.parse(src)
    readers = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
               and getattr(n.func, "attr", "") in ("read_text", "open",
                                                   "read_bytes")]
    assert len(readers) == 1, "파일을 읽는 자리가 하나여야 한다"


def test_j2_status_line_uses_the_project_vocabulary():
    report = _report()
    ok, _ = _run(_payload(report), report)
    assert ok.status_line().startswith("ok")
    data = _payload(report)
    data["round"] = "999"
    bad, _ = _run(data, report)
    assert bad.status_line().startswith("실패")
    assert "가져오지 않았습니다" in bad.status_line()


# --------------------------------------------------------------------------
def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as exc:
            bad += 1
            print(f"  FAIL {name}: {exc}")
        except Exception as exc:                            # noqa: BLE001
            bad += 1
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - bad}/{len(tests)} 통과")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
