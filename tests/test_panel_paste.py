"""3단계 Moderator 결과 붙여넣기 회귀 테스트 (Phase 4-F).

고정하려는 것은 다섯 가지다.

1. **검증이 두 벌이 아니다.** 붙여넣기 어댑터는 구조와 경기 연결만 보고,
   내용은 `panelimport.validate()` → `moderator.parse_result()` 가 본다.
2. **없는 것을 만들지 않는다.** 3단계 결과에는 두 분석가의 원문이 없다 —
   `origin`·`adopted_from`·`conclusion` 으로 예상 스코어를 역추론하지 않는다.
3. **3단계 결과를 고치지 않는다.** `origin`·`adopted_from`·`distribution` 이
   원문 그대로 보존된다.
4. **통과할 때만 파일을 만든다.** 깨진 붙여넣기는 `panel_results/` 를
   건드리지 않는다.
5. **기존 파일 경로가 그대로 산다.** 붙여넣기가 만든 파일을 기존 importer 에
   다시 넣어도 같은 결과가 나온다.

pytest 없이도 돈다:  python tests/test_panel_paste.py
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import panelaudit, panelimport, panelpaste       # noqa: E402
from toto.settings import Settings                          # noqa: E402

import test_panel_import as T                               # noqa: E402

DA, MU = panelimport.DATA_ROLE, panelimport.MATCHUP_ROLE
S = T.S
FIXTURE = Path(__file__).with_name("fixtures").joinpath(
    "260052_moderator_result.json")


# --------------------------------------------------------------------------
# 픽스처 — 실물 260052 의 모양 (14경기 · 9·13·14번 미실행)
# --------------------------------------------------------------------------
def _normal(no: int) -> dict:
    """정상 경기 하나. 실물 3단계 결과의 칸 구성 그대로."""
    return {
        "match_no": no,
        "simulations": 30,
        "distribution": [
            {"home": 0, "away": 1, "count": 20, "origin": DA},
            {"home": 1, "away": 1, "count": 6, "origin": "compromise"},
            {"home": 0, "away": 0, "count": 4, "origin": "compromise"},
        ],
        "adopted_home": 0, "adopted_away": 1,
        "adopted_from": [DA, MU],
        "conclusion": f"토론 결과 {no}번 경기의 예상 스코어는 0-1 입니다. "
                      f"원정의 기회 창출이 앞섰습니다. 표본이 좁습니다.",
        "common_points": ["원정의 기회 창출이 앞선다"],
        "differences": ["홈 수비의 평가가 갈린다"],
        "counterpoints": ["홈의 최근 실점이 줄었다"],
        "market_relation": "시장 기준선과 방향은 같고 폭은 더 좁다.",
        "uncertainty": ["표본이 6경기로 좁다"],
        "evidence_ids": ["E001"],
    }


def _skipped(no: int) -> dict:
    """돌리지 않은 경기 — 260052 의 9·13·14번 실제 모양."""
    return {"match_no": no, "simulations": 0, "distribution": [],
            "adopted_home": None, "adopted_away": None}


SKIP = (9, 13, 14)


def _paste(n: int = 14) -> list[dict]:
    return [(_skipped(i) if i in SKIP else _normal(i))
            for i in range(1, n + 1)]


def _report(n: int = 14, evidence: int = 2):
    return T._report(n=n, evidence=evidence, round_id="260052")


def _text(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


def _apply(paste, report=None, base=None):
    report = report if report is not None else _report()
    base = base if base is not None else Path(tempfile.mkdtemp())
    text = paste if isinstance(paste, str) else _text(paste)
    return panelpaste.apply(text, report, S, base=base) + (report, base)


def _codes(result) -> set[str]:
    return {i.code for i in result.issues}


# --------------------------------------------------------------------------
# A. 파서 — 구조
# --------------------------------------------------------------------------
def test_a1_full_round_passes():
    path, res, report, _base = _apply(_paste())
    assert res.success, [str(i) for i in res.issues]
    assert not _codes(res), _codes(res)
    assert path is not None and path.exists()
    assert sorted(res.runs) == list(range(1, 15))


def test_a2_one_match_is_not_a_complete_round():
    """일부만 붙여넣은 것을 완전한 회차 결과로 치지 않는다."""
    path, res, _r, _b = _apply([_normal(1)])
    assert path is None, "불완전한 붙여넣기로 파일을 만들었다"
    assert "PASTE_INCOMPLETE_ROUND" in _codes(res), _codes(res)


def test_a3_duplicate_match_no():
    paste = _paste()
    paste[1]["match_no"] = 1
    path, res, _r, _b = _apply(paste)
    assert path is None
    assert "PASTE_DUPLICATE_MATCH_NO" in _codes(res), _codes(res)


def test_a4_unknown_match_no():
    paste = _paste()
    paste[0]["match_no"] = 99
    path, res, _r, _b = _apply(paste)
    assert path is None
    assert "PASTE_UNKNOWN_MATCH_NO" in _codes(res), _codes(res)


def test_a5_boolean_is_not_a_match_no():
    """`True` 는 `int` 의 하위형이라 그냥 두면 1번 경기가 된다."""
    paste = _paste()
    paste[0]["match_no"] = True
    path, res, _r, _b = _apply(paste)
    assert path is None
    assert "PASTE_MATCH_NO_INVALID" in _codes(res), _codes(res)


def test_a6_top_level_object_is_refused():
    path, res, _r, _b = _apply(_text({"matches": _paste()}))
    assert path is None
    assert "PASTE_NOT_A_LIST" in _codes(res), _codes(res)


def test_a7_broken_json_is_refused():
    path, res, _r, _b = _apply("[{oops")
    assert path is None
    assert "PASTE_NOT_JSON" in _codes(res), _codes(res)


def test_a8_non_object_item_is_refused():
    paste = _paste()
    paste[3] = "네 번째 경기"
    path, res, _r, _b = _apply(paste)
    assert path is None
    assert "PASTE_ITEM_NOT_AN_OBJECT" in _codes(res), _codes(res)


def test_a9_empty_paste_is_refused():
    for text in ("", "   ", "[]"):
        path, res, _r, _b = _apply(text)
        assert path is None, text
        assert "PASTE_EMPTY" in _codes(res), (text, _codes(res))


def test_a10_code_fence_is_stripped():
    """채팅에서 복사하면 ```json 울타리가 함께 온다."""
    text = "```json\n" + _text(_paste()) + "\n```"
    path, res, _r, _b = _apply(text)
    assert res.success, [str(i) for i in res.issues]
    assert path is not None


# --------------------------------------------------------------------------
# B. 내용 검증 — 기존 검증기를 그대로 쓴다
# --------------------------------------------------------------------------
def test_b1_unknown_evidence_id():
    paste = _paste()
    paste[0]["evidence_ids"] = ["E999"]
    path, res, _r, _b = _apply(paste)
    assert path is None
    assert "UNKNOWN_EVIDENCE_ID" in _codes(res), _codes(res)


def test_b2_evidence_absent_but_cited():
    report = _report(evidence=0)
    path, res, _r, _b = _apply(_paste(), report)
    assert path is None
    assert "EVIDENCE_ABSENT_BUT_CITED" in _codes(res), _codes(res)


def test_b3_forbidden_field():
    paste = _paste()
    paste[0]["winner"] = "home"
    path, res, _r, _b = _apply(paste)
    assert path is None
    assert "FORBIDDEN_FIELD" in _codes(res), _codes(res)


def test_b4_adopted_score_not_in_distribution():
    paste = _paste()
    paste[0]["adopted_home"], paste[0]["adopted_away"] = 4, 4
    path, res, _r, _b = _apply(paste)
    assert path is None
    assert "ADOPTED_NOT_IN_DISTRIBUTION" in _codes(res), _codes(res)


def test_b5_simulations_do_not_match_distribution():
    paste = _paste()
    paste[0]["simulations"] = 31
    path, res, _r, _b = _apply(paste)
    assert path is None
    assert "INVALID_DISTRIBUTION" in _codes(res), _codes(res)


def test_b6_zero_simulations_become_a_skipped_match():
    path, res, _r, _b = _apply(_paste())
    assert res.success
    for no in SKIP:
        run = res.runs[no]
        assert panelimport.status_of(run) == panelimport.STATUS_SKIPPED, no
        assert run.moderator is None, no
        assert run.opinions == (), no


def test_b7_the_adapter_does_not_reimplement_validation():
    """§16 — 규칙을 베끼면 두 경로가 조용히 갈라진다."""
    src = Path(panelpaste.__file__).read_text(encoding="utf-8")
    for banned in ("ValidationError", "adopted_home is not None and",
                   "FORBIDDEN_FIELDS", "count", "simulations >"):
        if banned == "count":
            continue
        assert banned not in src.split('"""', 2)[-1], banned
    # 내용 검증은 기존 함수가 한다.
    assert "panelimport.validate" in src


# --------------------------------------------------------------------------
# C. 경기 연결 — match_no → canonical match
# --------------------------------------------------------------------------
def test_c1_program_resolves_match_id_itself():
    path, res, report, _b = _apply(_paste())
    assert res.success
    ids = [a.match_id for a in panelaudit.audit(res, report).matches]
    assert ids[:3] == ["400001", "400002", "400003"], ids


def test_c2_team_names_come_from_the_round_not_the_paste():
    """사용자가 적지 않은 값을 추론하는 것이 아니라 프로그램이 채운다."""
    data, issues = panelpaste.convert(_text(_paste()), _report())
    assert not issues, [str(i) for i in issues]
    block = data["matches"][0]
    assert block["home_team"] and block["away_team"]
    assert "match_id" not in block, "match_id 를 만들어 넣었다"
    assert block["match_number"] == 1


def test_c3_paste_never_writes_a_match_id():
    """어댑터가 만드는 블록에 `match_id` 자리가 없다 — 프로그램이 구한다."""
    src = Path(panelpaste.__file__).read_text(encoding="utf-8")
    block = src.split("def _block(")[1].split("\ndef ")[0]
    assert "match_id" not in block, block
    data, _issues = panelpaste.convert(_text(_paste()), _report())
    assert all("match_id" not in b for b in data["matches"])


def test_c4_a_shifted_paste_is_caught_by_the_teams():
    """번호가 밀리면 다른 경기에 붙는다 — 팀 검증이 막는다."""
    report = _report()
    data, _issues = panelpaste.convert(_text(_paste()), report)
    # 1번 블록의 팀만 2번 경기 것으로 바꾼다 (어댑터 뒤의 문을 시험한다).
    data["matches"][0]["home_team"] = report.matches[1].home.display
    data["matches"][0]["away_team"] = report.matches[1].away.display
    res = panelimport.validate(data, report, S)
    assert not res.success
    assert "TEAM_MISMATCH" in _codes(res), _codes(res)


# --------------------------------------------------------------------------
# D. Moderator-only — 없는 것을 만들지 않는다
# --------------------------------------------------------------------------
def test_d1_no_analyst_opinions_are_invented():
    path, res, _r, _b = _apply(_paste())
    assert res.success
    for no, run in res.runs.items():
        assert run.opinions == (), no
        if no not in SKIP:
            assert panelimport.is_moderator_only(run), no


def test_d2_origin_is_preserved_not_recomputed():
    """§14 — 3단계 결과를 고치지 않는다."""
    path, res, _r, _b = _apply(_paste())
    mod = res.runs[1].moderator
    assert [t.origin for t in mod.distribution] == [DA, "compromise",
                                                    "compromise"]


def test_d3_adopted_from_is_preserved():
    path, res, _r, _b = _apply(_paste())
    mod = res.runs[1].moderator
    assert list(mod.adopted_from) == [DA, MU], mod.adopted_from
    assert "ADOPTED_FROM_RECOMPUTED" not in _codes(res), _codes(res)


def test_d4_analyst_scores_are_not_inferred_from_origin():
    path, res, report, _b = _apply(_paste())
    a = panelaudit.audit(res, report).matches[0]
    assert a.data_analyst_score is None, a.data_analyst_score
    assert a.matchup_analyst_score is None, a.matchup_analyst_score
    assert a.moderator_score == (0, 1)


def test_d5_decision_type_says_moderator_only():
    path, res, report, _b = _apply(_paste())
    au = panelaudit.audit(res, report)
    kinds = {a.match_no: a.decision_type for a in au.matches}
    assert kinds[1] == panelaudit.MODERATOR_ONLY, kinds[1]
    assert kinds[9] == panelaudit.PANEL_SKIPPED, kinds[9]


def test_d6_audit_separates_moderator_only_from_skipped():
    path, res, report, _b = _apply(_paste())
    au = panelaudit.audit(res, report)
    assert au.coverage["moderator_only"] == [n for n in range(1, 15)
                                             if n not in SKIP]
    assert au.coverage["skipped_matches"] == list(SKIP)
    lines = "\n".join(panelaudit.report_lines(au))
    assert "사회자 결과만 반영된 경기" in lines
    assert "1·2단계 분석가 원문은 이 입력에 없습니다" in lines


def test_d7_moderator_only_is_not_counted_as_a_complete_panel():
    path, res, report, _b = _apply(_paste())
    au = panelaudit.audit(res, report)
    assert au.coverage["panel_results"] == 0, "돌린 경기로 셌다"
    assert au.coverage["data_analyst"] == 0
    assert au.coverage["matchup_analyst"] == 0


def test_d8_report_says_moderator_only():
    from toto import render

    path, res, report, _b = _apply(_paste())
    assert panelimport.attach(res, report) == 14
    html = render.render_report(report, Settings())
    assert "사회자 결과만 반영했습니다" in html
    assert "1·2단계 분석가 원문은 이번 입력에 포함되지 않았습니다" in html
    assert "이 경기는 패널 분석을 하지 않았습니다" in html   # 9·13·14번


def test_d9_skipped_matches_show_no_fabricated_score():
    """생략 경기의 카드에는 스코어도 분포도 없다."""
    from toto import render

    path, res, report, _b = _apply(_paste())
    panelimport.attach(res, report)
    html = render.render_report(report, Settings())
    mark = f'<h3><span class="no">{SKIP[0]}</span>'
    assert mark in html, "생략 경기 카드를 찾지 못했다"
    card = html.split(mark)[1].split("<h3>")[0]
    assert "이 경기는 패널 분석을 하지 않았습니다" in card
    assert "토론 시뮬레이션" not in card, "하지 않은 토론을 그렸다"
    assert "Panel 종합 예상 스코어" not in card, "없는 스코어를 그렸다"


# --------------------------------------------------------------------------
# E. 파일 — 통과할 때만 만든다 / 기존 경로와 같은 결과
# --------------------------------------------------------------------------
def test_e1_invalid_paste_writes_nothing():
    base = Path(tempfile.mkdtemp())
    paste = _paste()
    paste[0]["evidence_ids"] = ["E999"]
    path, res, _r, _b = _apply(paste, base=base)
    assert path is None
    folder = base.joinpath(panelimport.INBOX_DIRNAME)
    assert not folder.exists() or not list(folder.glob("*.json"))


def test_e2_saved_file_is_a_valid_panel_result():
    path, res, report, _b = _apply(_paste())
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == panelimport.SCHEMA_VERSION
    assert data["round"] == "260052"
    assert len(data["matches"]) == 14
    assert path.name == "260052" + panelimport.FILE_SUFFIX


def test_e3_saved_file_reimports_identically():
    """§24 — 붙여넣기가 만든 파일을 기존 importer 에 다시 넣어도 같다."""
    path, res, report, _b = _apply(_paste())
    again = panelimport.run(path, _report(), S, attach_result=False)
    assert again.success, [str(i) for i in again.issues]
    assert sorted(again.runs) == sorted(res.runs)
    for no in res.runs:
        a, b = res.runs[no], again.runs[no]
        assert a.status == b.status, no
        assert (getattr(a.moderator, "adopted_home", None)
                == getattr(b.moderator, "adopted_home", None)), no
        assert ([t.origin for t in (getattr(a.moderator, "distribution", ()) or ())]
                == [t.origin for t in (getattr(b.moderator, "distribution", ()) or ())])


def test_e4_artifact_roundtrip_keeps_the_panel():
    from toto import artifact

    path, res, report, base = _apply(_paste())
    panelimport.attach(res, report)
    out = base.joinpath("art")
    assert artifact.save(report, outdir=out).startswith("ok")
    revived, why = artifact.load("260052", outdir=out)
    assert revived is not None, why
    for m in revived.matches:
        run = m.panel
        assert run is not None, m.no
        assert run.opinions == ()
        if m.no not in SKIP:
            assert panelimport.is_moderator_only(run), m.no
            assert run.moderator.adopted_home == 0


def test_e5_existing_json_import_is_untouched():
    """기존 파일 경로가 그대로 산다 — 두 분석가가 있는 파일."""
    report = T._report(n=2, evidence=1)
    data = T._payload(report, da=T._opinion(DA, 2, 1), mu=T._opinion(MU, 1, 1),
                      mod=T._mod(adopted=(1, 1), adopted_from=(MU,)))
    res = panelimport.validate(data, report, S)
    assert res.success, [str(i) for i in res.issues]
    assert not _codes(res), _codes(res)
    assert len(res.runs[1].opinions) == 2


def test_e6_paste_input_is_not_modified():
    paste = _paste()
    before = copy.deepcopy(paste)
    _apply(paste)
    assert paste == before, "입력을 바꿨다"


# --------------------------------------------------------------------------
# F. 실물 260052 픽스처
# --------------------------------------------------------------------------
def test_f1_fixture_exists_and_is_a_separate_file():
    """§19 — 픽스처를 소스에 하드코딩하지 않고 파일로 둔다."""
    assert FIXTURE.exists(), FIXTURE
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(rows, list) and len(rows) == 14


def test_f2_fixture_goes_through_the_whole_pipeline():
    from toto import artifact, render

    report = _report()
    base = Path(tempfile.mkdtemp())
    path, res = panelpaste.apply(FIXTURE.read_text(encoding="utf-8"),
                                 report, S, base=base)
    assert path is not None, [str(i) for i in res.issues]
    assert res.success and not _codes(res), _codes(res)

    au = panelaudit.audit(res, report)
    assert au.status in ("PASS", "CONDITIONAL"), au.status
    assert au.coverage_status == "COMPLETE", au.coverage_status
    assert len(au.coverage["moderator_only"]) == 11
    assert au.coverage["skipped_matches"] == list(SKIP)

    panelimport.attach(res, report)
    out = base.joinpath("art")
    assert artifact.save(report, outdir=out).startswith("ok")
    html = render.render_report(report, Settings())
    assert "사회자 결과만 반영했습니다" in html
    assert len(html.encode("utf-8")) > 50_000


def test_f3_fixture_has_no_match_id_and_no_forbidden_fields():
    raw = FIXTURE.read_text(encoding="utf-8")
    assert "match_id" not in raw
    for name in panelimport.FORBIDDEN_FIELDS:
        assert f'"{name}"' not in raw, name


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
