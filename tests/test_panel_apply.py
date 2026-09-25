"""1·2단계 원문을 최종 Panel Result 에 싣는다 (Phase 6-F-14 · §1-49).

6-F-13 이 찾은 것 — 자동·수동 반영이 사회자 보관본 **하나만**
`--paste-panel-result` 에 넘겼다. 그 어댑터는 "분석가 원문이 없다" 는
전제로 만든 입구(4-F)라 모든 경기를 `부분` 으로 적었고, 체크포인트에
멀쩡히 있던 A·B 가 최종 파일·감사·HTML 어디에도 닿지 못했다.

    감사  01 | — | — | 2-1 | MODERATOR_ONLY

이 스위트가 지키는 것.

  A. 세 보관본이 있으면 **14경기 전부 `ok`** 로 들어간다
  B. 분석가 스코어가 **그대로** 옮겨진다 — `null` 은 `null` 로
  C. 요약·근거 문장·근거 ID 가 **그대로** 옮겨진다
  D. 짝은 **`match_no`** 로 짓는다 — 순서가 섞여도 같은 결과
  E. `--paste-panel-result` 는 **그대로** 사회자 전용 입구다
  F. 감사가 패널 14 · 부분 0 · 사회자 전용 0 을 센다
  G. 결정 유형이 실제 스코어끼리 견줘 나온다 (데이터·맞대결·둘 다·절충)
  H. HTML 스코어 흐름에 A → B → C 가 나온다
  I. 전부 끝난 회차는 **반영만** 다시 한다 — Claude 호출 0회

그리고 실패하는 쪽도 본다 — A·B 가 없으면 만들지 않고, 사회자 전용으로
조용히 강등하지 않으며, 앞서 있던 파일을 건드리지 않는다.

**실제 모델을 부르지 않는다.** 저장소의 `panel_work/`·`panel_results/`
는 한 글자도 건드리지 않는다 — 임시 폴더에서만 돈다.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import (cli, fixtures, panel, panelaudit, panelauto,  # noqa: E402
                  panelimport, panelpaste, panelwork, render)
from toto import settings as settings_mod                  # noqa: E402
from toto.analyze import run_all                           # noqa: E402
from toto.models import (EvidenceItem, MatchAnalysis, Report,  # noqa: E402
                         SeasonMatch, as_of_from_match)

# harness 를 두 벌 만들지 않는다 (§1-8).
from test_panel_auto import (                              # noqa: E402
    code_of, fn_node, make_fake, patched, scratch, source_of)
from test_panel_resume import Round, fake_cli                # noqa: E402

_PASSED = _FAILED = 0
REPO = Path(__file__).resolve().parent.parent
DA, MU = panel.DATA_ANALYST, panel.MATCHUP_ANALYST


def check(name, fn):
    global _PASSED, _FAILED
    try:
        fn()
    except AssertionError as exc:
        _FAILED += 1
        print(f"  FAIL {name}: {exc}")
    except Exception as exc:                                # noqa: BLE001
        _FAILED += 1
        print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    else:
        _PASSED += 1
        print(f"  ok   {name}")


# ==========================================================================
# 픽스처 — 14경기, 경기마다 근거 셋, 분석가 스코어가 **서로 다르다**
# ==========================================================================
# (A, B, 사회자가 한 일). A 스코어는 14경기 전부 다르다 — 한 칸 밀리면
# 곧바로 드러난다. 13번은 B 가 스코어를 내지 않았다 (`null`).
PLAN = {
    1: ((2, 1), (0, 0), "data"),
    2: ((1, 0), (1, 3), "matchup"),
    3: ((1, 1), (1, 1), "both"),
    4: ((2, 0), (0, 2), "compromise"),
    5: ((3, 1), (1, 2), "data"),
    6: ((0, 1), (2, 2), "matchup"),
    7: ((2, 2), (2, 2), "both"),
    8: ((3, 0), (1, 1), "data"),
    9: ((0, 0), (0, 2), "matchup"),
    10: ((1, 2), (1, 2), "both"),
    11: ((4, 1), (2, 1), "data"),
    12: ((0, 3), (3, 3), "matchup"),
    13: ((3, 2), None, "data"),
    14: ((2, 3), (1, 0), "matchup"),
}
COMPROMISE_SCORE = (1, 1)
EXPECTED_DECISION = {"data": panelaudit.ADOPTED_DATA,
                     "matchup": panelaudit.ADOPTED_MATCHUP,
                     "both": panelaudit.ADOPTED_BOTH,
                     "compromise": panelaudit.MODIFIED}

_SETTINGS = None
_BASE_REPORT = None


def settings():
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = settings_mod.load_settings()
    return _SETTINGS


def make_report(round_id="APPLY") -> Report:
    """데모 14경기 + 경기마다 근거 셋. **매번 새 객체**다 (붙이기가 경기를 바꾼다)."""
    global _BASE_REPORT
    if _BASE_REPORT is None:
        rep = Report(generated_at="2026-01-01 00:00")
        rep.matches = copy.deepcopy(fixtures.build_demo_matches())
        run_all(rep.matches, settings(), season_matches=rep.season_matches)
        for m in rep.matches:
            if m.analysis is None:
                m.analysis = MatchAnalysis()
            m.analysis.evidence = [
                EvidenceItem(claim=f"{m.no}번 근거 {k}", team=m.home.canonical,
                             category="attack", context="overall",
                             period="season", metric="goals",
                             value=1.0 + k, sample_count=5)
                for k in range(1, 4)]
        # 회차 경기마다 시즌 색인 항목 하나 (예정 경기). 실물처럼 match_id 가
        # 있어야 가져오기가 "번호로 잇는다" 경고 없이 권위 있는 ID 로 잇는다.
        rep.season_matches = [
            SeasonMatch(match_id=f"9900{m.no:02d}", competition=m.league,
                        kickoff=as_of_from_match(m), kickoff_aware=True,
                        home_team=m.home.canonical,
                        away_team=m.away.canonical, finished=False)
            for m in rep.matches]
        _BASE_REPORT = rep
    rep = copy.deepcopy(_BASE_REPORT)
    rep.round_id = round_id
    return rep


def score_of(pair):
    return (None, None) if pair is None else pair


def a_rows(report, order=None):
    rows = []
    for m in report.matches:
        h, a = score_of(PLAN[m.no][0])
        rows.append({"match_no": m.no, "predicted_home": h, "predicted_away": a,
                     "summary": f"데이터 {m.no}번 요약",
                     "rationale": [f"데이터 {m.no}번 근거 하나",
                                   f"데이터 {m.no}번 근거 둘"],
                     "evidence_ids": ["E001", "E002"]})
    return rows if order is None else [rows[i] for i in order]


def b_rows(report, order=None):
    rows = []
    for m in report.matches:
        h, a = score_of(PLAN[m.no][1])
        rows.append({"match_no": m.no, "predicted_home": h, "predicted_away": a,
                     "summary": f"맞대결 {m.no}번 요약",
                     "rationale": [f"맞대결 {m.no}번 근거"],
                     "evidence_ids": ["E003"]})
    return rows if order is None else [rows[i] for i in order]


def c_row(no, skipped=False):
    if skipped:
        return {"match_no": no, "simulations": 0, "distribution": [],
                "adopted_home": None, "adopted_away": None,
                "adopted_from": [],
                "conclusion": "이 경기는 토론을 돌리지 않았습니다.",
                "common_points": ["돌리지 않음"], "differences": [],
                "counterpoints": [], "uncertainty": [], "evidence_ids": []}
    a, b, kind = PLAN[no]
    dist = []
    if kind == "data":
        adopted, frm = a, [DA]
        dist.append({"home": a[0], "away": a[1], "count": 4 if b else 6,
                     "origin": DA})
        if b:
            dist.append({"home": b[0], "away": b[1], "count": 2,
                         "origin": MU})
    elif kind == "matchup":
        adopted, frm = b, [MU]
        dist += [{"home": b[0], "away": b[1], "count": 4, "origin": MU},
                 {"home": a[0], "away": a[1], "count": 2, "origin": DA}]
    elif kind == "both":
        adopted, frm = a, [DA, MU]
        dist.append({"home": a[0], "away": a[1], "count": 6, "origin": DA})
    else:
        adopted, frm = COMPROMISE_SCORE, []
        dist += [{"home": 1, "away": 1, "count": 3, "origin": "compromise"},
                 {"home": a[0], "away": a[1], "count": 2, "origin": DA},
                 {"home": b[0], "away": b[1], "count": 1, "origin": MU}]
    return {"match_no": no, "simulations": 6, "distribution": dist,
            "adopted_home": adopted[0], "adopted_away": adopted[1],
            "adopted_from": frm,
            "conclusion": (f"토론 결과 예상 스코어는 {adopted[0]}-{adopted[1]} "
                           f"입니다. {no}번 이유. 표본이 얕습니다."),
            "common_points": [f"{no}번 공통점"],
            "differences": [f"{no}번 차이"],
            "counterpoints": [], "uncertainty": [f"{no}번 불확실"],
            "evidence_ids": ["E001", "E003"],
            "market_relation": f"{no}번 시장 관계"}


def c_rows(report, skip=()):
    return [c_row(m.no, m.no in skip) for m in report.matches]


def dump(rows) -> str:
    return json.dumps(rows, ensure_ascii=False)


def seed(report, base, *, a=True, b=True, c=True, a_order=None, b_order=None,
         skip=()):
    """세 보관본을 **실제 저장 함수**로 넣는다 — 저장 검증을 함께 지난다."""
    if a:
        res = panelwork.save_stage(dump(a_rows(report, a_order)), DA, report,
                                   base)
        assert res.success, res.issues
    if b:
        res = panelwork.save_stage(dump(b_rows(report, b_order)), MU, report,
                                   base)
        assert res.success, res.issues
    if c:
        saved, res = panelwork.save_moderator_result(
            dump(c_rows(report, skip)), report, None, base)
        assert saved is not None, res.issues


def assembled(report=None, **kw):
    report = report or make_report()
    base = scratch()
    seed(report, base, **kw)
    data, result = panelwork.assemble_panel_result(report, None, base)
    return report, base, data, result


def imported(report=None, **kw):
    """조립 → canonical 파일 → 기존 가져오기(4-B)·감사(4-C). 저장소 밖에서."""
    report, base, data, _res = assembled(report, **kw)
    assert data is not None, _res.issues
    path = panelpaste.write_canonical(data, report.round_id, base)
    outcome = panelimport.run(path, report, None)
    return report, base, path, outcome, panelaudit.audit(outcome, report)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def by_no(data):
    return {b["match_number"]: b for b in data["matches"]}


# ==========================================================================
# A. 세 보관본이 있으면 14경기 전부 ok
# ==========================================================================
def test_a1_every_match_becomes_ok():
    report, _base, data, result = assembled()
    assert data is not None, [str(i) for i in result.issues]
    assert result.success and not result.errors, result.issues
    assert not result.warnings, [str(i) for i in result.warnings]
    assert result.imported_matches == 14 == len(report.matches)
    blocks = data["matches"]
    assert len(blocks) == 14
    for block in blocks:
        assert block["panel_status"] == panelimport.STATUS_OK, block
        assert "panel_status_reason" not in block
        for key in (DA, MU, panelimport.MODERATOR_ROLE):
            assert key in block, (block["match_number"], key)


def test_a2_same_schema_and_a_source_label():
    """새 스키마를 만들지 않는다 — 1.1 그대로, 출처 표시만 다르다."""
    report, _base, data, _res = assembled()
    assert data["schema_version"] == panelimport.SCHEMA_VERSION
    assert data["source"] == panelwork.APPLY_SOURCE
    assert data["source"] != "moderator-paste"


def test_a3_runs_carry_both_analyst_opinions():
    report, _base, path, outcome, _audit = imported()
    for m in report.matches:
        run = m.panel
        assert run is not None, m.no
        assert panelimport.status_of(run) == panelimport.STATUS_OK
        assert not panelimport.is_moderator_only(run), m.no
        assert sorted(o.role for o in run.opinions) == sorted((DA, MU))


# ==========================================================================
# B. 스코어가 그대로 옮겨진다
# ==========================================================================
def test_b1_scores_are_copied_not_recomputed():
    report, _base, data, _res = assembled()
    blocks = by_no(data)
    for no, (a, b, _kind) in PLAN.items():
        da, mu = blocks[no][DA], blocks[no][MU]
        assert (da["predicted_home"], da["predicted_away"]) == score_of(a), no
        assert (mu["predicted_home"], mu["predicted_away"]) == score_of(b), no


def test_b2_null_stays_null_not_zero():
    """B 가 스코어를 내지 않은 13번 — `0` 으로 채우지 않는다 (§1-5)."""
    report, _base, _path, _out, audit = imported()
    run = next(m.panel for m in report.matches if m.no == 13)
    mu = next(o for o in run.opinions if o.role == MU)
    assert mu.predicted_home is None and mu.predicted_away is None
    row = audit.by_match(13)
    assert row.matchup_analyst_score is None
    assert row.row[2] == "—"


def test_b3_attached_opinions_match_the_checkpoint_scores():
    report, _base, _path, _out, _audit = imported()
    for m in report.matches:
        ops = {o.role: o for o in m.panel.opinions}
        a, b, _k = PLAN[m.no]
        assert (ops[DA].predicted_home, ops[DA].predicted_away) == score_of(a)
        assert (ops[MU].predicted_home, ops[MU].predicted_away) == score_of(b)


# ==========================================================================
# C. 문장·근거 ID 가 그대로 옮겨진다 — 체크포인트는 한 바이트도 안 바뀐다
# ==========================================================================
def test_c1_analyst_blocks_are_the_raw_rows_minus_match_no():
    report, _base, data, _res = assembled()
    blocks = by_no(data)
    for row in a_rows(report):
        want = {k: v for k, v in row.items() if k != "match_no"}
        assert blocks[row["match_no"]][DA] == want, row["match_no"]
    for row in b_rows(report):
        want = {k: v for k, v in row.items() if k != "match_no"}
        assert blocks[row["match_no"]][MU] == want, row["match_no"]


def test_c2_moderator_block_is_the_raw_row_minus_match_no():
    report, _base, data, _res = assembled()
    blocks = by_no(data)
    for row in c_rows(report):
        want = {k: v for k, v in row.items() if k != "match_no"}
        assert blocks[row["match_no"]][panelimport.MODERATOR_ROLE] == want


def test_c3_attached_text_and_evidence_survive_import():
    report, _base, _path, _out, _audit = imported()
    for m in report.matches:
        ops = {o.role: o for o in m.panel.opinions}
        assert ops[DA].summary == f"데이터 {m.no}번 요약"
        assert list(ops[DA].rationale) == [f"데이터 {m.no}번 근거 하나",
                                           f"데이터 {m.no}번 근거 둘"]
        assert list(ops[DA].evidence_ids) == ["E001", "E002"]
        assert ops[MU].summary == f"맞대결 {m.no}번 요약"
        assert list(ops[MU].evidence_ids) == ["E003"]


def test_c4_checkpoints_are_not_modified():
    """A/B/C 보관본을 고치지 않는다 (금지 목록)."""
    report = make_report()
    base = scratch()
    seed(report, base)
    rid = report.round_id
    paths = [panelwork.path_for(rid, DA, base), panelwork.path_for(rid, MU, base),
             panelwork.moderator_result_path(rid, base)]
    before = [sha(p) for p in paths]
    data, _res = panelwork.assemble_panel_result(report, None, base)
    panelpaste.write_canonical(data, rid, base)
    assert [sha(p) for p in paths] == before


def test_c5_assembly_writes_nothing():
    """조립은 파일을 쓰지 않는다 — 쓰는 곳은 `write_canonical` 하나다."""
    report = make_report()
    base = scratch()
    seed(report, base)
    listing = sorted(str(p) for p in base.rglob("*"))
    panelwork.assemble_panel_result(report, None, base)
    assert sorted(str(p) for p in base.rglob("*")) == listing
    body = code_of(fn_node(panelwork, "assemble_panel_result"))
    for bad in ("write_text", "os.replace", "_atomic_write", "mkdir",
                "record_stage"):
        assert bad not in body, bad


# ==========================================================================
# D. match_no 로 짝짓는다 — 순서에 기대지 않는다
# ==========================================================================
def test_d1_shuffled_arrays_give_the_same_result():
    report = make_report()
    _r, _b, straight, _res = assembled(report)
    rev = list(range(13, -1, -1))
    mixed = [3, 0, 13, 7, 1, 12, 5, 9, 2, 11, 4, 10, 6, 8]
    _r, _b, shuffled, _res = assembled(make_report(), a_order=rev,
                                       b_order=mixed)
    assert shuffled is not None
    assert by_no(shuffled) == by_no(straight)


def test_d2_missing_analyst_checkpoint_fails_without_a_file():
    for skip_role in ("a", "b"):
        report = make_report()
        base = scratch()
        seed(report, base, **{skip_role: False})
        data, result = panelwork.assemble_panel_result(report, None, base)
        assert data is None, skip_role
        assert any(i.code == "MISSING_ANALYST" for i in result.errors)
        assert not panelimport.inbox_dir(base).exists(), "파일을 만들었다"


def test_d3_missing_moderator_checkpoint_fails():
    report = make_report()
    base = scratch()
    seed(report, base, c=False)
    data, result = panelwork.assemble_panel_result(report, None, base)
    assert data is None
    assert any(i.code == "MISSING_MODERATOR" for i in result.errors)


def test_d4_truncated_analyst_file_is_rejected_not_padded():
    """손으로 잘린 보관본 — 빠진 경기를 채우지 않는다."""
    report = make_report()
    base = scratch()
    seed(report, base)
    path = panelwork.path_for(report.round_id, DA, base)
    rows = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(rows[:10], ensure_ascii=False),
                    encoding="utf-8")
    data, result = panelwork.assemble_panel_result(report, None, base)
    assert data is None and result.errors


def test_d5_moderator_is_checked_against_the_real_proposals():
    """`ok` 경로는 사회자 전용보다 **엄격하다** — `adopted_from` 을 대조한다.

    2번 경기는 B 의 1-3 을 채택했는데 사회자가 "데이터 분석가" 라고 적었다.
    사회자 전용 경로(6-F-4 보관)는 제안 집합이 없어 그대로 받지만, A·B 를
    붙이면 그 거짓이 드러난다.
    """
    report = make_report()
    base = scratch()
    seed(report, base, c=False)
    rows = c_rows(report)
    rows[1]["adopted_from"] = [DA]
    saved, res = panelwork.save_moderator_result(dump(rows), report, None,
                                                 base)
    assert saved is not None, "사회자 전용 검증에서 이미 막혔다 — 전제가 틀렸다"
    data, result = panelwork.assemble_panel_result(report, None, base)
    assert data is None, "A·B 와 어긋난 사회자 결과를 통과시켰다"
    assert any(i.match_no == 2 for i in result.errors), result.issues


def test_d6_skipped_match_stays_skipped_without_analysts():
    """C 가 돌리지 않은 경기에는 A·B 를 붙이지 않는다 — 끝난 것처럼 안 보인다."""
    report, _base, data, result = assembled(skip=(14,))
    assert data is not None, [str(i) for i in result.issues]
    blocks = by_no(data)
    assert blocks[14]["panel_status"] == panelimport.STATUS_SKIPPED
    assert DA not in blocks[14] and MU not in blocks[14]
    assert sum(1 for b in data["matches"]
               if b["panel_status"] == panelimport.STATUS_OK) == 13


# ==========================================================================
# E. 사회자 전용 입구는 그대로다
# ==========================================================================
def test_e1_paste_path_is_still_moderator_only():
    report = make_report()
    base = scratch()
    path, result = panelpaste.apply(dump(c_rows(report)), report, None, base)
    assert path is not None, result.issues
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["source"] == "moderator-paste"
    assert all(b["panel_status"] == panelimport.STATUS_PARTIAL
               for b in data["matches"])
    outcome = panelimport.run(path, report, None)
    audit = panelaudit.audit(outcome, report)
    assert all(a.decision_type == panelaudit.MODERATOR_ONLY
               for a in audit.matches)
    assert all(a.row[1] == "—" and a.row[2] == "—" for a in audit.matches)


def test_e2_canonical_bytes_are_unchanged_by_the_shared_writer():
    """`apply()` 가 `write_canonical` 로 옮겨 가도 쓰는 바이트는 같다."""
    report = make_report()
    base = scratch()
    text = dump(c_rows(report))
    path, _res = panelpaste.apply(text, report, None, base)
    data, _issues = panelpaste.convert(text, report)
    assert path.read_bytes() == json.dumps(
        data, ensure_ascii=False, indent=1).encode("utf-8")
    assert not path.with_name(path.name + ".tmp").exists()


def test_e3_paste_flag_still_routes_to_the_paste_adapter():
    handler = code_of(fn_node(cli, "_handle_panel_file"))
    first = handler.index("args.paste_panel_result")
    assert handler.index("_paste_to_canonical") > first
    assert handler.index("_checkpoints_to_canonical") > \
        handler.index("_paste_to_canonical"), "붙여넣기 입구를 가로챘다"
    names = {a.dest for a in cli.build_parser()._actions}
    assert {"paste_panel_result", "apply_panel_work"} <= names


# ==========================================================================
# F. 감사가 세는 것
# ==========================================================================
def test_f1_audit_counts_fourteen_ran_and_nothing_partial():
    _report, _base, _path, outcome, audit = imported()
    assert audit.status == panelaudit.PASS, [str(i) for i in audit.issues]
    assert audit.coverage_status == panelaudit.COMPLETE
    cov = audit.coverage
    assert cov["panel_results"] == 14
    assert cov["panel_partial"] == 0
    assert cov["moderator_only"] == []
    assert cov["skipped_matches"] == []
    assert cov["data_analyst"] == cov["matchup_analyst"] == 14
    assert cov["moderator"] == 14
    assert cov["data_analyst_missing"] == cov["matchup_analyst_missing"] == []
    assert audit.adoption["panel_ran"] == 14
    # 4-B 의 가져오기 감사도 같은 사실을 센다 — 두 원안이 **비교 가능**해졌다.
    assert outcome.audit["panel_ok"] == 14
    assert outcome.audit["panel_partial"] == 0
    assert outcome.audit["analysts_agree"] == 3
    assert (outcome.audit["analysts_agree"]
            + outcome.audit["analysts_disagree"]) == 14


def test_f2_composition_line_does_not_say_moderator_only():
    _report, _base, _path, _out, audit = imported()
    line = panelaudit.composition_line(audit)
    assert line == "패널 14경기", line


# ==========================================================================
# G. 결정 유형 — 실제 스코어끼리 견줘 나온다
# ==========================================================================
def test_g1_decision_types_follow_the_real_scores():
    _report, _base, _path, _out, audit = imported()
    for no, (_a, _b, kind) in PLAN.items():
        assert audit.by_match(no).decision_type == EXPECTED_DECISION[kind], no
    ad = audit.adoption
    assert ad["adopted_data_analyst"] == 5
    assert ad["adopted_matchup_analyst"] == 5
    assert ad["adopted_both"] == 3
    assert ad["modified_or_compromise"] == 1
    assert ad["not_adopted"] == 0


def test_g2_initial_relation_is_known_where_both_scored():
    _report, _base, _path, _out, audit = imported()
    ad = audit.adoption
    assert ad["same_initial"] == 3
    assert ad["different_initial"] == 10
    assert ad["unknown_initial"] == 1           # 13번 — B 가 null


def test_g3_rows_show_three_stages():
    _report, _base, _path, _out, audit = imported()
    row = audit.by_match(2).row
    assert row == ("02", "1-0", "1-3", "1-3"), row
    row = audit.by_match(4).row
    assert row == ("04", "2-0", "0-2", "1-1"), row


# ==========================================================================
# H. HTML 스코어 흐름
# ==========================================================================
def test_h1_score_flow_shows_a_then_b_then_c():
    report, _base, _path, _out, _audit = imported()
    for m in report.matches:
        flow = render._score_flow(m)
        a, b, _kind = PLAN[m.no]
        assert "데이터 분석가" in flow and "맞대결·전술 분석가" in flow
        assert f"{a[0]} : {a[1]}" in flow, (m.no, flow)
        if b is not None:
            assert f"{b[0]} : {b[1]}" in flow, (m.no, flow)


def test_h2_report_has_no_moderator_only_title():
    report, _base, _path, _out, _audit = imported()
    html = render.render_report(report, settings())
    assert html.count("패널 분석 (두 전문가의 해석)") == 14
    assert "패널 분석 (사회자 결과만 반영)" not in html
    assert html.count('<p class="lbl">스코어 흐름</p>') == 14
    for m in report.matches:
        assert f"데이터 {m.no}번 요약" in html, m.no
        assert f"맞대결 {m.no}번 요약" in html, m.no


def test_h3_contrast_paste_report_still_says_moderator_only():
    report = make_report()
    base = scratch()
    path, _res = panelpaste.apply(dump(c_rows(report)), report, None, base)
    panelimport.run(path, report, None)
    html = render.render_report(report, settings())
    assert "패널 분석 (사회자 결과만 반영)" in html


# ==========================================================================
# I. 재개 — 반영만, Claude 0회
# ==========================================================================
def test_i1_all_done_round_only_applies_with_zero_calls():
    rnd = Round()
    rnd.seed_all()
    cli_calls, agent_calls = [], []
    inner = fake_cli(rnd)

    def recording(argv):
        cli_calls.append(list(argv))
        return inner(argv)

    os.environ[panelauto.AUTO_ENV] = str(rnd.base / "auto")
    try:
        with patched(run_agent=make_fake(rnd.report, agent_calls),
                     cli="/bin/true", existing_cli=recording,
                     sheet_dir=rnd.sheet):
            out = panelauto.run(rnd.report.round_id, rnd.report,
                                base=rnd.base, echo=lambda _l: None)
    finally:
        os.environ.pop(panelauto.AUTO_ENV, None)
    assert agent_calls == [], "끝난 단계를 다시 불렀다"
    assert cli_calls == [["--round", rnd.report.round_id,
                          "--apply-panel-work"]], cli_calls
    assert out.status == panelauto.AGENT_OK, out.stopped_reason


def test_i2_auto_path_no_longer_hands_c_alone_to_paste():
    body = code_of(fn_node(panelauto, "_run_stages"))
    assert "--apply-panel-work" in body
    assert "--paste-panel-result" not in body


def test_i3_menu_item_uses_the_same_flag():
    from toto import menu
    body = code_of(fn_node(menu, "_panel_work_for"))
    assert "--apply-panel-work" in body
    assert "--paste-panel-result" not in body


# ==========================================================================
# J. CLI 끝까지 — 파일 · 감사 · 출처 기록 · HTML (저장소 밖에서)
# ==========================================================================
class root_at:
    """`settings.ROOT` 를 임시 폴더로. 저장소의 파일을 건드리지 않는다."""

    def __init__(self, path: Path):
        self.path, self.saved = Path(path), None

    def __enter__(self):
        self.saved = settings_mod.ROOT
        settings_mod.ROOT = self.path
        return self.path

    def __exit__(self, *exc):
        settings_mod.ROOT = self.saved
        return False


def cli_args(report, out_html: Path) -> argparse.Namespace:
    return cli.build_parser().parse_args(
        ["--round", report.round_id, "--apply-panel-work",
         "-o", str(out_html)])


def repo_snapshot():
    dirs = [REPO / "panel_results", REPO / "panel_work"]
    return {str(p): p.stat().st_mtime_ns
            for d in dirs if d.is_dir() for p in d.rglob("*")}


def test_j1_cli_writes_file_audits_and_records_provenance():
    before = repo_snapshot()
    report = make_report()
    root = scratch()
    conf = settings()
    with root_at(root):
        seed(report, root)
        html_path = root / "out.html"
        rc = cli._panel_only(report, cli_args(report, html_path), conf, None)
        canonical = panelpaste.canonical_path(report.round_id)
        record = panelwork.stage_record(report.round_id,
                                        panelwork.STAGE_APPLY)
        cp_a = panelwork.path_for(report.round_id, DA)
        cp_b = panelwork.path_for(report.round_id, MU)
        cp_c = panelwork.moderator_result_path(report.round_id)
        state = panelwork.checkpoint_state(report.round_id,
                                           panelwork.STAGE_APPLY, report)
    assert rc == 0
    assert canonical.is_file() and str(canonical).startswith(str(root))
    data = json.loads(canonical.read_text(encoding="utf-8"))
    assert data["source"] == panelwork.APPLY_SOURCE
    assert report.source_status["패널 감사"].startswith(panelaudit.PASS)
    assert "Moderator" not in report.source_status["패널 가져오기"]
    assert record["status"] == panelwork.STAGE_COMPLETE
    assert record["sha256"] == sha(canonical)
    assert record["depends"] == {panelwork.STAGE_A: sha(cp_a),
                                 panelwork.STAGE_B: sha(cp_b),
                                 panelwork.STAGE_RESULT: sha(cp_c)}
    assert state.state == panelwork.CP_COMPLETE, state.reasons
    html = html_path.read_text(encoding="utf-8")
    assert "패널 분석 (사회자 결과만 반영)" not in html
    assert html.count('<p class="lbl">스코어 흐름</p>') == 14
    assert repo_snapshot() == before, "저장소의 panel_results/·panel_work/ 가 바뀌었다"


def test_j2_cli_failure_leaves_the_existing_file_untouched():
    """B 가 없으면 만들지 않고, 앞서 있던 파일을 덮지 않는다."""
    report = make_report()
    root = scratch()
    conf = settings()
    with root_at(root):
        seed(report, root, b=False)
        canonical = panelpaste.canonical_path(report.round_id)
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text('{"keep": "me"}', encoding="utf-8")
        before = sha(canonical)
        rc = cli._panel_only(report, cli_args(report, root / "out.html"),
                             conf, None)
        record = panelwork.stage_record(report.round_id,
                                        panelwork.STAGE_APPLY)
    assert rc == 1
    assert sha(canonical) == before, "실패한 반영이 기존 파일을 덮었다"
    assert not (root / "out.html").exists(), "실패했는데 리포트를 썼다"
    assert not record, "실패했는데 반영 기록이 남았다"
    assert report.source_status["패널 가져오기"].startswith("실패")
    assert all(getattr(m, "panel", None) is None for m in report.matches), \
        "사회자 전용으로 조용히 강등해 붙였다"


def test_j3_apply_and_paste_together_are_refused():
    args = cli.build_parser().parse_args(
        ["--round", "X", "--apply-panel-work", "--paste-panel-result", "f"])
    assert cli._apply_panel_work(args, settings()) == 1


def test_j4_missing_artifact_does_not_fall_back_to_collection():
    """저장본이 없으면 수집하지 않는다 — 별도 프로세스에서 모듈로 확인한다."""
    code = ("import sys; from toto import cli; "
            "rc = cli.main(['--round', 'ZZ_NO_SUCH_ROUND', "
            "'--apply-panel-work']); "
            "print(rc, any(k.startswith('toto.sources') for k in sys.modules),"
            " 'anthropic' in sys.modules)")
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
                          capture_output=True, text=True, timeout=120)
    assert proc.stdout.split()[-3:] == ["1", "False", "False"], (
        proc.stdout, proc.stderr[-800:])


# ==========================================================================
# K. 범위 — 바꾸지 않은 것
# ==========================================================================
def test_k1_one_direction_is_kept():
    """`panelpaste`·`panelimport`·`panelaudit` 는 `panelwork` 를 모른다."""
    for mod in (panelpaste, panelimport, panelaudit):
        assert "panelwork" not in source_of(mod), mod.__name__


def test_k2_only_one_writer_for_panel_results():
    assert "write_canonical" in code_of(fn_node(panelpaste, "apply"))
    writer = code_of(fn_node(cli, "_checkpoints_to_canonical"))
    assert "panelpaste.write_canonical" in writer
    for fn in ("_checkpoints_to_canonical", "_apply_panel_work"):
        body = code_of(fn_node(cli, fn))
        assert "write_text" not in body and "json.dumps" not in body, fn


def test_k3_no_recompute_no_new_schema_no_prompt_change():
    from toto import moderator
    body = code_of(fn_node(panelwork, "assemble_panel_result"))
    for bad in ("sum(", "round(", "mean", "/ ", "max(", "min(",
                "initial_scores", "schema_version"):
        assert bad not in body, bad
    assert panelimport.SCHEMA_VERSION == "1.1"
    assert panel.PANEL_PROMPT_VERSION == "5"
    assert moderator.MODERATOR_PROMPT_VERSION == "6"


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
