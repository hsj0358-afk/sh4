"""Panel 미실행 상태와 운영 워크플로 (Phase 4-B 계약 보완).

260052 운영에서 드러난 문제 하나가 출발점이다. 9·13·14번 경기는 패널
토론을 **실행하지 않았는데**, 계약에 그것을 적을 자리가 없어서

  · 정상 실행과 구분되지 않고 (`PanelRun.status` 가 하드코딩이었다)
  · 커버리지에 정상 실행으로 섞이고
  · 파서를 통과시키려고 **하지도 않은 토론의 `common_points` 를 지어내야**
    했다.

고정하려는 것은 다섯 가지다.

1. **schema 1.0 파일은 그대로 읽힌다.** 새 칸은 선택이다.
2. **`panel_status` 로 실행 여부를 적는다.** 어휘는 §1-6 의 넷 그대로.
3. **가짜 자료를 만들지 않는다.** 실행하지 않았으면 `simulations` 를 30으로
   지어내지 않고, 없는 토론의 공통점·차이도 지어내지 않는다.
4. **감사가 둘을 섞지 않는다.** 실행한 경기와 실행하지 않은 경기를 따로 센다.
5. **사유가 없으면 받지 않는다.** '생략' 만 적고 왜인지 안 적을 수 없다.

pytest 없이도 돈다:  python tests/test_panel_status.py
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import panelaudit, panelimport, render                 # noqa: E402
from test_panel_import import (DA, MU, S, _mod, _opinion,        # noqa: E402
                               _payload, _report)

SKIPPED = panelimport.STATUS_SKIPPED
REASON = "분석 대상 팀의 상세 데이터가 없어 Panel 분석을 수행하지 않음"


def _skip(block, status=SKIPPED, reason=REASON, keep_moderator=False):
    """실행하지 않은 경기 블록. **내용을 지어내지 않는다.**"""
    block["panel_status"] = status
    if reason:
        block["panel_status_reason"] = reason
    block.pop(DA, None)
    block.pop(MU, None)
    if keep_moderator:
        # 260052 의 실제 출력 모양 — 사회자 블록은 있고 값만 비어 있다.
        block["moderator"] = {"role": "moderator", "simulations": 0,
                              "distribution": [], "adopted_home": None,
                              "adopted_away": None, "adopted_from": [],
                              "conclusion": "", "common_points": [],
                              "differences": [], "counterpoints": [],
                              "uncertainty": [], "evidence_ids": []}
    else:
        block.pop("moderator", None)
    return block


def _run(data, report):
    return panelimport.validate(data, report, S)


def _codes(res) -> set[str]:
    return {i.code for i in res.issues}


# --------------------------------------------------------------------------
# A. schema 호환
# --------------------------------------------------------------------------
def test_a1_schema_1_0_still_imports():
    """기존 파일이 한 글자도 바뀌지 않고 그대로 읽혀야 한다."""
    report = _report(n=2)
    data = _payload(report)
    data["schema_version"] = "1.0"
    res = _run(data, report)
    assert res.success, [str(i) for i in res.issues]
    assert res.schema_version == "1.0"
    assert res.audit["panel_ok"] == 2
    assert res.audit["panel_skipped"] == 0


def test_a2_schema_1_1_is_supported():
    assert panelimport.SCHEMA_VERSION == "1.1"
    assert set(panelimport.SUPPORTED_VERSIONS) == {"1.0", "1.1"}
    report = _report(n=2)
    data = _payload(report)
    data["schema_version"] = "1.1"
    assert _run(data, report).success


def test_a3_unknown_version_still_rejected():
    report = _report(n=2)
    data = _payload(report)
    data["schema_version"] = "2.0"
    assert "SCHEMA_VERSION_UNSUPPORTED" in _codes(_run(data, report))


def test_a4_status_vocabulary_is_the_project_one():
    """새 상태 체계를 만들지 않는다 — §1-6 의 넷 그대로다."""
    assert panelimport.PANEL_STATUSES == ("ok", "부분", "실패", "생략")


# --------------------------------------------------------------------------
# B. 생략 — 실행하지 않은 경기
# --------------------------------------------------------------------------
def test_b1_skipped_match_imports_without_fake_content():
    report = _report(n=2)
    data = _payload(report)
    _skip(data["matches"][0])
    res = _run(data, report)
    assert res.success, [str(i) for i in res.issues]
    run = res.runs[1]
    assert panelimport.status_of(run) == SKIPPED
    assert run.opinions == (), "실행하지 않았는데 의견을 만들었다"
    assert run.moderator is None, "실행하지 않았는데 사회자를 만들었다"
    assert REASON in run.status


def test_b2_real_260052_shape_is_accepted():
    """9·13·14번의 실제 출력(사회자 블록에 0·[])을 고치라고 요구하지 않는다."""
    report = _report(n=2)
    data = _payload(report)
    _skip(data["matches"][0], keep_moderator=True)
    res = _run(data, report)
    assert res.success, [str(i) for i in res.issues]
    assert res.runs[1].moderator is None


def test_b3_role_status_is_not_disguised_as_ok():
    report = _report(n=1)
    data = _payload(report)
    _skip(data["matches"][0])
    run = _run(data, report).runs[1]
    assert set(run.role_status.values()) == {SKIPPED}, run.role_status
    assert "2/2 분석가" not in run.status


def test_b4_reason_is_required():
    report = _report(n=1)
    data = _payload(report)
    _skip(data["matches"][0], reason="")
    res = _run(data, report)
    assert not res.success
    assert "PANEL_STATUS_REASON_MISSING" in _codes(res)


def test_b5_unknown_status_is_rejected():
    report = _report(n=1)
    data = _payload(report)
    _skip(data["matches"][0], status="skipped")
    assert "PANEL_STATUS_INVALID" in _codes(_run(data, report))


def test_b6_content_contradicting_the_status_is_rejected():
    """실행하지 않았다는데 스코어가 있으면 둘 중 하나가 거짓이다."""
    report = _report(n=1)
    data = _payload(report)
    block = data["matches"][0]
    block["panel_status"] = SKIPPED
    block["panel_status_reason"] = REASON      # 분석가·사회자는 그대로 둔다
    res = _run(data, report)
    assert not res.success
    assert "PANEL_STATUS_CONTRADICTION" in _codes(res)


def test_b7_failed_and_partial_are_distinct_states():
    for status in ("실패", "부분"):
        report = _report(n=1)
        data = _payload(report)
        _skip(data["matches"][0], status=status, reason="사유")
        res = _run(data, report)
        assert res.success, (status, [str(i) for i in res.issues])
        assert panelimport.status_of(res.runs[1]) == status


def test_b8_ok_matches_still_need_everything():
    """생략을 열어 줬다고 정상 경기의 문이 헐거워지면 안 된다."""
    report = _report(n=1)
    data = _payload(report)
    del data["matches"][0][MU]
    res = _run(data, report)
    assert not res.success
    assert "MISSING_ANALYST" in _codes(res)


def test_b9_no_fake_simulations():
    """실행하지 않은 경기의 simulations 가 30 으로 채워지지 않는다."""
    report = _report(n=2)
    data = _payload(report)
    _skip(data["matches"][0], keep_moderator=True)
    res = _run(data, report)
    au = panelaudit.audit(res, report)
    assert au.by_match(1).simulations == 0
    assert au.by_match(2).simulations == 30


def test_b10_1_0_file_using_the_new_field_is_warned_not_blocked():
    report = _report(n=2)
    data = _payload(report)
    data["schema_version"] = "1.0"
    _skip(data["matches"][0])
    res = _run(data, report)
    assert res.success, [str(i) for i in res.issues]
    assert "PANEL_STATUS_IN_1_0" in _codes(res)


# --------------------------------------------------------------------------
# C. 4-C 감사 — 실행한 경기와 아닌 경기를 섞지 않는다
# --------------------------------------------------------------------------
def _round_260052():
    """14경기 · 9·13·14번 미실행 (실제 260052 모양)."""
    report = _report(n=14)
    data = _payload(report)
    data["schema_version"] = "1.1"
    for no in (9, 13, 14):
        _skip(data["matches"][no - 1], keep_moderator=True)
    res = _run(data, report)
    return res, report


def test_c1_260052_counts_are_split():
    res, report = _round_260052()
    assert res.success, [str(i) for i in res.issues]
    assert res.audit["panel_ok"] == 11
    assert res.audit["panel_skipped"] == 3

    au = panelaudit.audit(res, report)
    cov = au.coverage
    assert cov["matches_total"] == 14
    assert cov["panel_results"] == 11, cov
    assert cov["panel_skipped"] == 3, cov
    assert cov["skipped_matches"] == [9, 13, 14], cov


def test_c2_analyst_coverage_is_over_the_matches_that_ran():
    """생략한 경기 때문에 "분석가가 빠졌다" 로 보이면 안 된다."""
    res, report = _round_260052()
    cov = panelaudit.audit(res, report).coverage
    assert cov["data_analyst"] == 11
    assert cov["matchup_analyst"] == 11
    assert cov["moderator"] == 11
    for key in ("data_analyst_missing", "matchup_analyst_missing",
                "moderator_missing"):
        assert cov[key] == [], (key, cov[key])


def test_c3_coverage_is_complete_when_nothing_is_missing():
    res, report = _round_260052()
    au = panelaudit.audit(res, report)
    assert au.coverage_status == panelaudit.COMPLETE, au.coverage


def test_c4_skipped_match_gets_its_own_decision_type():
    res, report = _round_260052()
    au = panelaudit.audit(res, report)
    assert au.by_match(9).decision_type == panelaudit.PANEL_SKIPPED
    assert au.by_match(9).panel_status == SKIPPED
    assert REASON in au.by_match(9).panel_status_reason
    assert au.by_match(1).decision_type != panelaudit.PANEL_SKIPPED
    # 승무패 뜻을 갖는 상태를 만들지 않는다.
    for banned in ("HOME", "AWAY", "DRAW", "WIN", "PICK"):
        assert banned not in panelaudit.PANEL_SKIPPED


def test_c5_skipped_matches_stay_out_of_the_agreement_stats():
    res, report = _round_260052()
    ad = panelaudit.audit(res, report).adoption
    counted = (ad["same_initial"] + ad["different_initial"]
               + ad["unknown_initial"])
    assert counted == 11, ad
    assert ad["panel_ran"] == 11 and ad["panel_not_run"] == 3, ad
    assert ad["panel_skipped"] == 3, ad


def test_c6_false_warnings_are_gone():
    """생략 경기 때문에 "한 번도 갈리지 않았다" 가 뜨면 안 된다."""
    report = _report(n=3)
    data = _payload(report)
    # 실행한 두 경기는 의견이 갈린다 (DA 2-1 · 맞대결 1-1).
    _skip(data["matches"][2])
    res = _run(data, report)
    assert "ANALYSTS_NEVER_DISAGREE" not in _codes(res), \
        [str(i) for i in res.issues]


def test_c7_audit_report_names_the_skipped_matches():
    res, report = _round_260052()
    text = "\n".join(panelaudit.report_lines(panelaudit.audit(res, report)))
    assert "패널을 돌린 경기: 11" in text
    assert "생략: 3" in text
    assert "9번" in text and "13번" in text and "14번" in text
    assert "돌린 11경기 기준" in text


# --------------------------------------------------------------------------
# D. 화면 — 가짜 스코어를 만들지 않는다
# --------------------------------------------------------------------------
def test_d1_skipped_match_shows_the_real_state():
    res, report = _round_260052()
    panelimport.attach(res, report)
    match = next(m for m in report.matches if m.no == 9)
    html = render._panel_block(match)
    assert "패널 분석을 하지 않았습니다" in html
    assert REASON in html, "사유가 화면에 없다"
    for banned in ("0 : 0", "홈승", "원정승", "추천합니다"):
        assert banned not in html, banned


def test_d2_summary_and_round_card_say_skipped():
    res, report = _round_260052()
    panelimport.attach(res, report)
    match = next(m for m in report.matches if m.no == 9)
    summary = render._decision_summary(match)
    assert "Panel 분석" in summary and SKIPPED in summary
    assert "고를 근거가 자료에 없었습니다" not in summary, \
        "돌리지 않은 것을 '못 골랐다' 로 적었다"
    card = render._summary_panel(match)
    assert SKIPPED in card
    for banned in ("홈승", "원정승", "0 : 0"):
        assert banned not in card, banned


def test_d3_matches_that_ran_are_unchanged():
    res, report = _round_260052()
    panelimport.attach(res, report)
    match = next(m for m in report.matches if m.no == 1)
    html = render._panel_block(match)
    assert "Panel 종합 예상 스코어" in html
    assert "패널 분석을 하지 않았습니다" not in html


# --------------------------------------------------------------------------
# E. 받은 파일 폴더
# --------------------------------------------------------------------------
def test_e1_inbox_is_one_place():
    assert panelimport.INBOX_DIRNAME == "panel_results"
    assert panelimport.inbox_dir().name == "panel_results"


def test_e2_finds_files_and_reads_the_round_from_content():
    base = Path(tempfile.mkdtemp())
    folder = base.joinpath(panelimport.INBOX_DIRNAME)
    folder.mkdir()
    for rnd in ("260052", "260050"):
        folder.joinpath(f"{rnd}_panel_result.json").write_text(
            json.dumps({"schema_version": "1.1", "round": rnd,
                        "matches": []}), encoding="utf-8")
    found = panelimport.find_panel_files(base)
    assert [p.name for p in found] == ["260050_panel_result.json",
                                       "260052_panel_result.json"]
    assert [panelimport.round_of(p) for p in found] == ["260050", "260052"]


def test_e3_round_comes_from_content_not_the_filename():
    """이름은 바뀔 수 있고, 검증에 쓰이는 값은 내용의 `round` 다."""
    base = Path(tempfile.mkdtemp())
    folder = base.joinpath(panelimport.INBOX_DIRNAME)
    folder.mkdir()
    path = folder.joinpath("아무이름.json")
    path.write_text(json.dumps({"round": "260052"}), encoding="utf-8")
    assert panelimport.round_of(path) == "260052"


def test_e4_missing_folder_is_empty_not_an_error():
    assert panelimport.find_panel_files(Path(tempfile.mkdtemp())) == []


def test_e5_unreadable_file_gives_no_round_instead_of_guessing():
    base = Path(tempfile.mkdtemp())
    folder = base.joinpath(panelimport.INBOX_DIRNAME)
    folder.mkdir()
    path = folder.joinpath("broken.json")
    path.write_text("{not json", encoding="utf-8")
    assert panelimport.round_of(path) == ""


# --------------------------------------------------------------------------
# F. 하지 않는 것
# --------------------------------------------------------------------------
def test_f1_no_wdl_from_the_new_state():
    """`"홈승"` 을 금지어로 두면 이 모듈이 스스로 적은 부정문에 걸린다 —
    docstring 이 "'홈승' 으로 옮기는 helper 가 없다" 라고 말하고 있다.
    함수 이름으로 검사하고, 부정문이 남아 있는지를 따로 본다.
    """
    src = Path(panelimport.__file__).read_text(encoding="utf-8")
    for banned in ("def _wdl", "def _winner", "def _pick", "winner ="):
        assert banned not in src, banned
    assert "'홈승' 으로 옮기는 helper 가 없다" in src


def test_f2_skipped_never_becomes_a_score():
    res, report = _round_260052()
    au = panelaudit.audit(res, report)
    for no in (9, 13, 14):
        a = au.by_match(no)
        assert a.moderator_score is None
        assert a.data_analyst_score is None
        assert a.matchup_analyst_score is None
        assert a.row[1:] == ("—", "—", "—"), a.row


def test_f3_original_file_is_not_modified():
    report = _report(n=2)
    data = _payload(report)
    _skip(data["matches"][0], keep_moderator=True)
    before = copy.deepcopy(data)
    _run(data, report)
    assert data == before, "입력 dict 를 고쳤다"


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
