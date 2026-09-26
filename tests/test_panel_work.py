"""1·2단계 결과 보관 + 3단계 입력 조립 회귀 (Phase 6-F-3 · CLAUDE.md §1-40).

지키려는 것 셋이다.

  1. A 결과를 잃지 않는다        — 검증 통과분만, 원자적으로 보관한다
  2. B 결과를 A 와 섞지 않는다   — 저장·검증 경로가 서로를 읽지 않는다
  3. A+B 를 사람이 재조립하지 않는다 — `match_no` 로 프로그램이 짝짓는다

그리고 **클로드를 부르지 않는다** — 이 Phase 는 분석 실행을 자동화하지
않는다. A 절이 그것을 AST 로 고정한다.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import (fixtures, moderator, panel, panelexport,  # noqa: E402
                  panelimport, panelwork, settings as settings_mod)
from toto.analyze import run_all                            # noqa: E402
from toto.models import Report                              # noqa: E402

_PASSED = _FAILED = 0


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
# 픽스처 — 실물 형식과 같은 모양으로 만든다
# ==========================================================================
_REPORT = None


def demo_report() -> Report:
    global _REPORT
    if _REPORT is None:
        rep = Report(generated_at="2026-01-01 00:00")
        rep.round_id = "DEMO"
        rep.matches = fixtures.build_demo_matches()
        run_all(rep.matches, settings_mod.load_settings(),
                season_matches=rep.season_matches)
        _REPORT = rep
    return _REPORT


def allowed_ids(match) -> list[str]:
    return list(panel.build_panel_payload(match).evidence_ids)


def stage_array(report: Report, tag: str, *, numbers=None,
                extra: dict | None = None) -> str:
    """분석가 응답 배열. 경기마다 **구분되는** 문장을 넣는다.

    K 절(정확한 결합)이 이것에 기댄다 — 같은 문장이면 1번 의견이 7번에
    붙어도 통과해 버린다.
    """
    rows = []
    for match in report.matches:
        if numbers is not None and match.no not in numbers:
            continue
        row = {"match_no": match.no,
               "predicted_home": 2, "predicted_away": 1,
               "summary": f"{tag}{match.no} 요약",
               "rationale": [f"{tag}{match.no} 근거"],
               "evidence_ids": allowed_ids(match)}
        if extra:
            row.update(extra)
        rows.append(row)
    return json.dumps(rows, ensure_ascii=False)


def scratch() -> Path:
    """**저장소 밖** 임시 디렉터리 (§24). 실제 panel_work/ 를 건드리지 않는다."""
    return Path(tempfile.mkdtemp(prefix="toto_pw_test_"))


def source_of(obj) -> str:
    return Path(obj.__file__).read_text(encoding="utf-8")


def fn_node(module, name):
    tree = ast.parse(source_of(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} 을 찾지 못했다")


def calls_in(node) -> set[str]:
    return {ast.unparse(c.func) for c in ast.walk(node)
            if isinstance(c, ast.Call)}


# ==========================================================================
# A. 클로드를 부르지 않는다 — 이 Phase 의 최우선 제약
# ==========================================================================
def test_a1_module_never_imports_the_api_layer():
    """`llm`·`anthropic` 이 이 모듈에 없다.

    **낱말 검색이 아니라 import 문을 본다** — 이 모듈의 docstring 은 "부르지
    않는다" 를 적으려고 그 이름들을 언급하고, 낱말로 재면 그 설명이 스스로
    걸린다. 지키려는 것은 문서가 아니라 의존성이다.
    """
    tree = ast.parse(source_of(panelwork))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported |= {a.name for a in node.names}
            if node.module:
                imported.add(node.module.split(".")[0])
    for bad in ("llm", "anthropic"):
        assert bad not in imported, f"{bad} 를 import 한다"


def test_a2_module_never_calls_the_api_executors():
    """`--panel` 의 실행기를 부르지 않는다 (§26).

    여기도 **호출 노드**로 본다 — docstring 이 금지 목록을 적고 있어 낱말
    검색으로는 잴 수 없다 (a1 과 같은 이유).
    """
    tree = ast.parse(source_of(panelwork))
    calls = {ast.unparse(c.func) for c in ast.walk(tree)
             if isinstance(c, ast.Call)}
    for bad in ("run_match", "run_panel_role", "attach_panels",
                "run_moderator", "complete"):
        hit = [c for c in calls if c.split(".")[-1] == bad]
        assert not hit, f"API 실행 경로를 부른다: {hit}"


def test_a3_cli_branch_never_calls_the_api_executors():
    """CLI 진입점도 마찬가지다."""
    from toto import cli
    calls = calls_in(fn_node(cli, "_panel_work"))
    for bad in ("run_match", "run_panel_role", "attach_panels",
                "run_moderator", "complete"):
        hit = [c for c in calls if c.split(".")[-1] == bad]
        assert not hit, f"{hit} 를 부른다"


def test_a5_cli_branch_returns_before_collection():
    """수집 구간 앞에서 갈라진다 — 소스도 부르지 않는다.

    **docstring 은 제외한다** — 이 함수의 설명이 "`toto.sources` 도 import
    되지 않는다" 를 적고 있어서, 본문과 함께 재면 그 설명이 스스로 걸린다
    (a1·a2 와 같은 교정). docstring 은 분기를 만들 수 없다.
    """
    from toto import cli
    node = fn_node(cli, "_panel_work")
    calls = calls_in(node)
    for bad in ("read_league", "read_round", "read_odds", "enrich"):
        assert not [c for c in calls if c.split(".")[-1] == bad], bad
    body = [n for n in node.body
            if not (isinstance(n, ast.Expr)
                    and isinstance(n.value, ast.Constant)
                    and isinstance(n.value.value, str))]
    src = "\n".join(ast.unparse(n) for n in body)
    assert "sources" not in src, src


def test_a4_reused_helpers_are_pure():
    """재사용하는 것들이 API 를 타지 않는다 — 우회 호출 방지."""
    for module, names in ((panel, ("parse_opinion", "build_panel_payload")),
                          (moderator, ("build_input", "serialize_input")),
                          (panelexport, ("moderator_data_sheet",))):
        for name in names:
            calls = calls_in(fn_node(module, name))
            bad = [c for c in calls
                   if "complete" in c or "client" in c
                   or (c.startswith("llm.") and "strip_fence" not in c)]
            assert not bad, f"{module.__name__}.{name}: {bad}"


# ==========================================================================
# B. A/B 저장 (§22 A·B)
# ==========================================================================
def test_b1_valid_analyst_a_is_saved():
    rep, base = demo_report(), scratch()
    out = panelwork.save_stage(stage_array(rep, "A"),
                               panel.DATA_ANALYST, rep, base=base)
    assert out.success, [str(i) for i in out.issues]
    assert out.saved_matches == 14, out.saved_matches
    assert out.path.name == "analyst_a.json", out.path
    assert out.path.is_file()
    assert out.status_line().startswith("ok ("), out.status_line()


def test_b2_valid_analyst_b_is_saved():
    rep, base = demo_report(), scratch()
    out = panelwork.save_stage(stage_array(rep, "B"),
                               panel.MATCHUP_ANALYST, rep, base=base)
    assert out.success and out.path.name == "analyst_b.json", out.path


def test_b3_saved_file_keeps_the_model_json_as_returned():
    """§6 — 프로그램이 재구성한 판을 저장하지 않는다."""
    rep, base = demo_report(), scratch()
    text = stage_array(rep, "A")
    panelwork.save_stage(text, panel.DATA_ANALYST, rep, base=base)
    saved = json.loads(
        panelwork.path_for("DEMO", panel.DATA_ANALYST, base)
        .read_text(encoding="utf-8"))
    assert saved == json.loads(text), "원본과 다르다"


def test_b4_two_roles_land_in_separate_files():
    rep, base = demo_report(), scratch()
    panelwork.save_stage(stage_array(rep, "A"), panel.DATA_ANALYST,
                         rep, base=base)
    panelwork.save_stage(stage_array(rep, "B"), panel.MATCHUP_ANALYST,
                         rep, base=base)
    a = panelwork.path_for("DEMO", panel.DATA_ANALYST, base)
    b = panelwork.path_for("DEMO", panel.MATCHUP_ANALYST, base)
    assert a != b and a.is_file() and b.is_file()
    assert a.read_text(encoding="utf-8") != b.read_text(encoding="utf-8")


def test_b5_work_dir_is_per_round():
    base = scratch()
    assert panelwork.work_dir("260054", base).name == "260054"
    assert panelwork.work_dir("260052", base) != panelwork.work_dir(
        "260054", base)


# ==========================================================================
# C~F. 잘못된 입력은 저장되지 않는다 (§5 · §22 C~F)
# ==========================================================================
def _rejects(text, *, role=panel.DATA_ANALYST, code=None):
    rep, base = demo_report(), scratch()
    out = panelwork.save_stage(text, role, rep, base=base)
    assert not out.success, "저장되면 안 된다"
    assert out.path is None
    assert not panelwork.path_for("DEMO", role, base).exists(), "파일이 생겼다"
    if code:
        codes = [i.code for i in out.issues]
        assert code in codes, codes
    return out


def test_c1_broken_json_is_rejected():
    _rejects("{이건 JSON 이 아니다", code="STAGE_NOT_JSON")


def test_c2_prose_is_rejected():
    _rejects("1번 경기는 2-1 예상입니다.", code="STAGE_NOT_JSON")


def test_c3_single_object_is_rejected():
    _rejects('{"match_no": 1}', code="STAGE_NOT_A_LIST")


def test_c4_empty_array_is_rejected():
    _rejects("[]", code="STAGE_EMPTY")


def test_d1_partial_round_is_rejected():
    """13경기만 → 저장하지 않는다 (§22 D)."""
    rep = demo_report()
    out = _rejects(stage_array(rep, "A", numbers=range(1, 14)),
                   code="STAGE_INCOMPLETE_ROUND")
    assert "14번" in str(out.errors[0]), str(out.errors[0])


def test_e1_duplicate_match_no_is_rejected():
    rep = demo_report()
    rows = json.loads(stage_array(rep, "A"))
    rows.append(dict(rows[0]))
    _rejects(json.dumps(rows, ensure_ascii=False),
             code="STAGE_DUPLICATE_MATCH_NO")


def test_e2_unknown_match_no_is_rejected():
    rep = demo_report()
    rows = json.loads(stage_array(rep, "A"))
    rows[0]["match_no"] = 99
    _rejects(json.dumps(rows, ensure_ascii=False),
             code="STAGE_UNKNOWN_MATCH_NO")


def test_e3_non_integer_match_no_is_rejected():
    rep = demo_report()
    for bad in ("1", 1.0, True, 0, -1, None):
        rows = json.loads(stage_array(rep, "A"))
        rows[0]["match_no"] = bad
        out = panelwork.save_stage(
            json.dumps(rows, ensure_ascii=False), panel.DATA_ANALYST,
            rep, base=scratch())
        assert not out.success, f"{bad!r} 가 통과했다"


def test_f1_unknown_evidence_id_is_rejected():
    """E999 → 저장하지 않는다 (§22 F). 기존 검증기가 잡는다."""
    rep = demo_report()
    rows = json.loads(stage_array(rep, "A"))
    rows[0]["evidence_ids"] = ["E999"]
    out = _rejects(json.dumps(rows, ensure_ascii=False),
                   code="STAGE_OPINION_INVALID")
    assert "E999" in str(out.errors[0]), str(out.errors[0])


def test_f2_evidence_id_from_another_match_is_rejected():
    """근거 ID 는 **그 경기의** 것이어야 한다 (§1-15)."""
    rep = demo_report()
    ids = {m.no: allowed_ids(m) for m in rep.matches}
    donor = next((n for n in ids if ids[n]
                  and any(set(ids[n]) - set(ids[o])
                          for o in ids if o != n)), None)
    if donor is None:
        return                       # 근거가 없는 픽스처면 볼 것이 없다
    other = next(o for o in ids if o != donor
                 and set(ids[donor]) - set(ids[o]))
    rows = json.loads(stage_array(rep, "A"))
    for row in rows:
        if row["match_no"] == other:
            row["evidence_ids"] = sorted(set(ids[donor]) - set(ids[other]))
    _rejects(json.dumps(rows, ensure_ascii=False),
             code="STAGE_OPINION_INVALID")


def test_f3_bad_score_is_not_silently_fixed():
    """`"2-1"`·`1.5` 를 고쳐 주지 않는다 (§5-9)."""
    rep = demo_report()
    for bad in ("2-1", 1.5, -1, True):
        rows = json.loads(stage_array(rep, "A"))
        rows[0]["predicted_home"] = bad
        out = panelwork.save_stage(
            json.dumps(rows, ensure_ascii=False), panel.DATA_ANALYST,
            rep, base=scratch())
        assert not out.success, f"{bad!r} 가 통과했다"


def test_f4_missing_summary_is_rejected():
    rep = demo_report()
    rows = json.loads(stage_array(rep, "A"))
    rows[0]["summary"] = ""
    _rejects(json.dumps(rows, ensure_ascii=False),
             code="STAGE_OPINION_INVALID")


def test_f5_forbidden_fields_are_dropped_not_stored_as_opinion():
    """승무패 칸은 `PanelOpinion` 에 자리가 없다 (불변조건 4)."""
    rep, base = demo_report(), scratch()
    text = stage_array(rep, "A", extra={"winner": "home",
                                        "confidence": 0.9})
    out = panelwork.save_stage(text, panel.DATA_ANALYST, rep, base=base)
    assert out.success, [str(i) for i in out.issues]
    ops, _ = panelwork.load_stage("DEMO", panel.DATA_ANALYST, rep, base)
    for op in ops.values():
        assert not hasattr(op, "winner") and not hasattr(op, "confidence")


def test_f6_code_fence_is_tolerated():
    """채팅에서 복사하면 ```json 이 함께 온다 — 기존 관용 그대로."""
    rep, base = demo_report(), scratch()
    text = "```json\n" + stage_array(rep, "A") + "\n```"
    assert panelwork.save_stage(text, panel.DATA_ANALYST, rep,
                                base=base).success


# ==========================================================================
# G~J. 조립 조건 (§19·§20 · §22 G~J)
# ==========================================================================
def _save_both(base, *, a_numbers=None, b_numbers=None):
    rep = demo_report()
    panelwork.save_stage(stage_array(rep, "A", numbers=a_numbers),
                         panel.DATA_ANALYST, rep, base=base)
    panelwork.save_stage(stage_array(rep, "B", numbers=b_numbers),
                         panel.MATCHUP_ANALYST, rep, base=base)
    return rep


def test_g1_both_present_builds_the_sheet():
    base = scratch()
    rep = _save_both(base)
    out = panelwork.build_completed_sheet(rep, base=base,
                                          outdir=base / "sheet")
    assert out.success, [str(i) for i in out.issues]
    assert out.path.name == panelwork.COMPLETED_SHEET, out.path
    assert out.matches == 14, out.matches


def test_h1_only_a_does_not_build():
    rep, base = demo_report(), scratch()
    panelwork.save_stage(stage_array(rep, "A"), panel.DATA_ANALYST,
                         rep, base=base)
    out = panelwork.build_completed_sheet(rep, base=base,
                                          outdir=base / "sheet")
    assert not out.success and out.path is None
    assert "MISSING_ANALYST" in [i.code for i in out.errors]
    assert not (base / "sheet" / panelwork.COMPLETED_SHEET).exists()


def test_i1_only_b_does_not_build():
    rep, base = demo_report(), scratch()
    panelwork.save_stage(stage_array(rep, "B"), panel.MATCHUP_ANALYST,
                         rep, base=base)
    out = panelwork.build_completed_sheet(rep, base=base,
                                          outdir=base / "sheet")
    assert not out.success
    assert "MISSING_ANALYST" in [i.code for i in out.errors]


def test_i2_neither_present_does_not_build():
    rep, base = demo_report(), scratch()
    out = panelwork.build_completed_sheet(rep, base=base,
                                          outdir=base / "sheet")
    assert not out.success
    assert len([i for i in out.errors if i.code == "MISSING_ANALYST"]) == 2


def test_j1_match_no_mismatch_does_not_build():
    """A=1~14, B=1~13 이면 만들지 않는다 (§20).

    보관 자체는 완전성 검사에 막히므로, **손으로 고쳐진 파일**을 흉내내
    조립 단계의 문을 직접 시험한다.
    """
    base = scratch()
    rep = _save_both(base)
    path = panelwork.path_for("DEMO", panel.MATCHUP_ANALYST, base)
    rows = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(rows[:-1], ensure_ascii=False),
                    encoding="utf-8")
    out = panelwork.build_completed_sheet(rep, base=base,
                                          outdir=base / "sheet")
    assert not out.success, "만들면 안 된다"
    assert not (base / "sheet" / panelwork.COMPLETED_SHEET).exists()


def test_j2_missing_match_is_never_filled_in():
    """빠진 경기를 채우거나 번호를 재정렬하지 않는다 (§20)."""
    src = source_of(panelwork)
    for bad in ("setdefault(no", "or []", "fillna", "sorted(rows)"):
        assert bad not in src.replace("opinions_by_no.get(p.match_no) or ()",
                                      ""), bad
    node = fn_node(panelwork, "collect_opinions")
    assert "MATCH_NO_MISMATCH" in ast.unparse(node)


# ==========================================================================
# K. 정확한 결합 — 이 Phase 의 본체
# ==========================================================================
def _blocks(text: str) -> dict:
    import re
    return {int(no): json.loads(js) for no, js in re.findall(
        r'<moderator_input no="(\d+)">\s*(\{.*?\})\s*</moderator_input>',
        text, re.S)}


def test_k1_each_match_gets_its_own_a_and_b():
    """경기 N 의 의견은 A_N 과 B_N 이다. 한 칸도 밀리지 않는다."""
    base = scratch()
    rep = _save_both(base)
    out = panelwork.build_completed_sheet(rep, base=base,
                                          outdir=base / "sheet")
    blocks = _blocks(out.path.read_text(encoding="utf-8"))
    assert len(blocks) == 14, len(blocks)
    for no, data in blocks.items():
        summaries = [o["summary"] for o in data["opinions"]]
        assert summaries == [f"A{no} 요약", f"B{no} 요약"], (no, summaries)


def test_k2_roles_are_in_order_and_named():
    base = scratch()
    rep = _save_both(base)
    out = panelwork.build_completed_sheet(rep, base=base,
                                          outdir=base / "sheet")
    for data in _blocks(out.path.read_text(encoding="utf-8")).values():
        assert [o["role"] for o in data["opinions"]] == list(panel.ROLES)


def test_k3_shuffled_input_still_pairs_by_match_no():
    """배열 순서에 기대지 않는다 (§9)."""
    rep, base = demo_report(), scratch()
    a_rows = json.loads(stage_array(rep, "A"))
    b_rows = json.loads(stage_array(rep, "B"))[::-1]     # 거꾸로
    panelwork.save_stage(json.dumps(a_rows, ensure_ascii=False),
                         panel.DATA_ANALYST, rep, base=base)
    panelwork.save_stage(json.dumps(b_rows, ensure_ascii=False),
                         panel.MATCHUP_ANALYST, rep, base=base)
    out = panelwork.build_completed_sheet(rep, base=base,
                                          outdir=base / "sheet")
    for no, data in _blocks(out.path.read_text(encoding="utf-8")).items():
        assert [o["summary"] for o in data["opinions"]] == [
            f"A{no} 요약", f"B{no} 요약"], no


def test_k4_moderator_input_keeps_five_fields():
    """조립이 사회자 입력 구조를 넓히지 않는다 (§1-10)."""
    base = scratch()
    rep = _save_both(base)
    out = panelwork.build_completed_sheet(rep, base=base,
                                          outdir=base / "sheet")
    text = out.path.read_text(encoding="utf-8")
    for data in _blocks(text).values():
        assert sorted(data) == ["conflicts", "evidence", "market_reference",
                                "match", "opinions"], sorted(data)
    assert "qualitative" not in text


def test_k5_opinion_rows_carry_only_the_agreed_fields():
    base = scratch()
    rep = _save_both(base)
    out = panelwork.build_completed_sheet(rep, base=base,
                                          outdir=base / "sheet")
    for data in _blocks(out.path.read_text(encoding="utf-8")).values():
        for op in data["opinions"]:
            assert sorted(op) == ["evidence_ids", "predicted_away",
                                  "predicted_home", "rationale", "role",
                                  "summary"], sorted(op)


def test_k6_completed_sheet_has_no_manual_slot():
    """`◀ … ▶` 수동 삽입이 사라진다 (§12)."""
    base = scratch()
    rep = _save_both(base)
    out = panelwork.build_completed_sheet(rep, base=base,
                                          outdir=base / "sheet")
    text = out.path.read_text(encoding="utf-8")
    assert "◀" not in text and "▶" not in text
    assert panelexport.OPINIONS_SLOT not in text
    assert '"opinions":[]' not in text


def test_k7_assembly_uses_build_input_not_string_surgery():
    """문자열 치환이 아니라 `build_input()` 을 쓴다 (§12).

    `os.replace` 는 원자적 파일 교체라 여기서 막는 대상이 아니다 — 막는
    것은 **자료 본문에 대한** `str.replace` 다.
    """
    assert "moderator.build_input" in calls_in(
        fn_node(panelexport, "moderator_data_sheet"))
    calls = calls_in(fn_node(panelwork, "build_completed_sheet"))
    surgery = [c for c in calls
               if c.endswith(".replace") and c != "os.replace"]
    assert not surgery, surgery


# ==========================================================================
# L. 기존 출력 회귀 (§21)
# ==========================================================================
def test_l1_default_moderator_sheet_is_byte_identical():
    """`opinions_by_no=None` 은 기존과 바이트까지 같다."""
    rep = demo_report()
    payloads = [panel.build_panel_payload(m) for m in rep.matches]
    a = panelexport.moderator_data_sheet("DEMO", payloads)
    b = panelexport.moderator_data_sheet("DEMO", payloads, None)
    c = panelexport.moderator_data_sheet("DEMO", payloads,
                                         opinions_by_no=None)
    assert a == b == c
    # 6-F-3 전에 잰 값 (같은 픽스처·같은 코드 경로)
    assert hashlib.sha256(a.encode()).hexdigest().startswith(
        "fbe7f6993f41c15f19312c12cac87bba"[:16]), \
        hashlib.sha256(a.encode()).hexdigest()
    assert len(a.encode()) == 6974, len(a.encode())


def test_l2_default_sheet_still_has_the_empty_opinions():
    rep = demo_report()
    text = panelexport.moderator_data_sheet(
        "DEMO", [panel.build_panel_payload(m) for m in rep.matches])
    assert '"opinions":[]' in text
    assert "1·2단계 의견이 이미 들어 있습니다" not in text


def test_l3_export_still_writes_the_plain_sheet():
    """`export()` 는 의견을 넣지 않는다 — 원본과 완성본이 나뉜다 (§11)."""
    node = fn_node(panelexport, "export")
    src = ast.unparse(node)
    assert "moderator_data_sheet(round_id, payloads)" in src, src
    assert "opinions_by_no" not in src


def test_l4_completed_sheet_does_not_overwrite_the_original():
    base = scratch()
    rep = _save_both(base)
    out = panelwork.build_completed_sheet(rep, base=base,
                                          outdir=base / "sheet")
    assert out.path.name != "03_사회자자료.md"
    assert out.path.name == "03_사회자자료_완성.md"


def test_l5_round_dir_is_unchanged():
    from toto.settings import ROOT
    assert panelexport.round_dir("260054") == (
        ROOT / "reports" / "panel_260054")


# ==========================================================================
# M. 되풀이해도 같다 · 복구 (§7 · §22 M)
# ==========================================================================
def test_m1_building_twice_is_deterministic():
    base = scratch()
    rep = _save_both(base)
    first = panelwork.build_completed_sheet(
        rep, base=base, outdir=base / "sheet").path.read_text(
            encoding="utf-8")
    second = panelwork.build_completed_sheet(
        rep, base=base, outdir=base / "sheet").path.read_text(
            encoding="utf-8")
    assert first == second


def test_m2_failed_save_keeps_the_previous_result():
    """검증 실패가 앞서 저장한 것을 지우지 않는다 (§7·§16)."""
    rep, base = demo_report(), scratch()
    good = stage_array(rep, "A")
    panelwork.save_stage(good, panel.DATA_ANALYST, rep, base=base)
    path = panelwork.path_for("DEMO", panel.DATA_ANALYST, base)
    before = path.read_text(encoding="utf-8")
    out = panelwork.save_stage("{깨진 입력", panel.DATA_ANALYST, rep,
                               base=base)
    assert not out.success
    assert path.read_text(encoding="utf-8") == before, "앞선 결과가 바뀌었다"


def test_m3_c_can_be_rebuilt_without_redoing_a_and_b():
    """C 실패 후 A/B 를 다시 넣지 않아도 된다 (§7)."""
    base = scratch()
    rep = _save_both(base)
    target = base / "sheet"
    panelwork.build_completed_sheet(rep, base=base, outdir=target)
    (target / panelwork.COMPLETED_SHEET).unlink()
    again = panelwork.build_completed_sheet(rep, base=base, outdir=target)
    assert again.success and again.path.is_file()


def test_m4_saving_b_again_does_not_touch_a():
    base = scratch()
    rep = _save_both(base)
    a_path = panelwork.path_for("DEMO", panel.DATA_ANALYST, base)
    before = a_path.read_text(encoding="utf-8")
    panelwork.save_stage(stage_array(rep, "B2"), panel.MATCHUP_ANALYST,
                         rep, base=base)
    assert a_path.read_text(encoding="utf-8") == before


def test_m5_save_is_atomic_no_tmp_left_behind():
    base = scratch()
    rep = _save_both(base)
    leftovers = list(panelwork.work_dir("DEMO", base).glob("*.tmp"))
    assert not leftovers, leftovers


# ==========================================================================
# N. A/B 독립성 (§18)
# ==========================================================================
def test_n1_saving_one_role_never_reads_the_other():
    """`save_stage`·`parse_stage` 가 보관본을 읽지 않는다."""
    for name in ("save_stage", "parse_stage"):
        calls = calls_in(fn_node(panelwork, name))
        for bad in ("load_stage", "collect_opinions", "path_for"):
            if name == "save_stage" and bad == "path_for":
                continue            # 자기 파일 자리를 구하는 것은 읽기가 아니다
            assert bad not in calls, f"{name} 가 {bad} 를 부른다"


def test_n2_parse_stage_does_not_take_the_other_role():
    """시그니처에 '상대 역할' 이 들어올 자리가 없다."""
    import inspect
    params = list(inspect.signature(panelwork.parse_stage).parameters)
    assert params == ["text", "role", "report"], params


def test_n3_the_two_roles_meet_only_in_collect_opinions():
    """`panel.ROLES` 를 도는 곳이 조립 함수뿐이다.

    **6-F-14 에서 범위를 옮겼다.** 최종 반영(`assemble_panel_result`)도 두
    역할을 함께 읽는다 — C 가 끝난 **뒤**에 세 보관본을 Panel Result 로
    옮기는 자리라 A·B 가 서로를 보는 경로가 아니다. 지키려던 것은 그대로다:
    한 단계를 **저장·검증하는** 함수는 다른 역할을 읽지 않는다.
    """
    tree = ast.parse(source_of(panelwork))
    users = [n.name for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef)
             and "panel.ROLES" in ast.unparse(n)]
    assert sorted(users) == ["assemble_panel_result", "collect_opinions",
                             "opinion_count"], users
    for name in ("save_stage", "parse_stage", "load_stage", "_read_stage"):
        body = ast.unparse(fn_node(panelwork, name))
        assert "panel.ROLES" not in body, f"{name} 가 두 역할을 함께 본다"


def test_n4_role_files_are_distinct_and_cover_both_roles():
    assert set(panelwork.ROLE_FILES) == set(panel.ROLES)
    assert len(set(panelwork.ROLE_FILES.values())) == 2


# ==========================================================================
# P. 계약을 넓히지 않았다 (§1 · §26)
# ==========================================================================
def test_p1_prompt_versions_are_untouched():
    """**6-F-11 에서 범위를 옮겼다.** 6-F-3 은 "보관·조립은 프롬프트를
    건드리지 않는다" 를 숫자로 적어 뒀는데, 6-F-11 이 B 역할 프롬프트를
    고치는 Phase 다 (§1-29 와 같은 교정).

    6-F-3 이 실제로 지키는 것은 **이 모듈이 프롬프트를 만지지 않는다**
    이므로 그쪽을 본다 — 사회자는 그대로이고, `panelwork` 에 프롬프트
    문자열이 없다.
    """
    assert moderator.MODERATOR_PROMPT_VERSION == "6"
    assert int(panel.PANEL_PROMPT_VERSION) >= 5
    src = inspect.getsource(panelwork)
    for text in (panel.SYSTEM_COMMON, *panel.ROLE_PROMPTS.values()):
        assert text not in src, "panelwork 가 프롬프트 사본을 들고 있다"


def test_p2_panel_result_schema_is_untouched():
    assert panelimport.SCHEMA_VERSION == "1.1"
    assert panelimport.SUPPORTED_VERSIONS == ("1.0", "1.1")


def test_p3_this_phase_did_not_touch_the_import_contract():
    """`[4]` 의 검증 경로에 이 모듈이 끼어들지 않는다."""
    from toto import panelaudit, panelpaste
    for mod in (panelimport, panelpaste, panelaudit):
        assert "panelwork" not in source_of(mod), mod.__name__


def test_p4_work_dir_is_not_the_inbox():
    """`panel_work/` 와 `panel_results/` 를 섞지 않는다."""
    assert panelwork.WORK_DIRNAME != panelimport.INBOX_DIRNAME
    base = scratch()
    assert panelwork.work_dir("R", base) != panelimport.inbox_dir(base)


def test_p5_gitignore_covers_the_work_dir():
    text = (Path(__file__).resolve().parent.parent
            / ".gitignore").read_text(encoding="utf-8")
    assert "panel_work/" in text, text[-400:]


def test_p6_role_aliases_resolve_both_ways():
    assert panelwork.resolve_role("a") == panel.DATA_ANALYST
    assert panelwork.resolve_role("B") == panel.MATCHUP_ANALYST
    assert panelwork.resolve_role("analyst_a") == panel.DATA_ANALYST
    assert panelwork.resolve_role(panel.MATCHUP_ANALYST) == \
        panel.MATCHUP_ANALYST
    assert panelwork.resolve_role("moderator") == ""
    assert panelwork.resolve_role("") == ""


def test_p7_menu_does_not_reimplement_validation():
    """검증·조립을 메뉴에서 다시 쓰지 않는다 (§1-20 과 같은 이유).

    메뉴는 CLI 인자를 만들어 같은 경로를 태울 뿐이다 — 두 곳에서 다른
    결과가 나오면 어느 쪽도 믿을 수 없다.
    """
    from toto import menu
    src = source_of(menu)
    for bad in ("parse_stage", "save_stage", "build_completed_sheet",
                "collect_opinions", "parse_opinion"):
        assert bad not in src, f"menu.py 가 {bad} 를 직접 부른다"
    assert "--save-panel-opinion" in src and "--build-moderator-input" in src


# ==========================================================================
# Q. 실물 형식 호환 (§25 — 재수집 없이 형식만 본다)
# ==========================================================================
def test_q1_real_artifact_payloads_accept_build_input():
    from toto import artifact
    path = Path(__file__).resolve().parent.parent / "data" / "artifacts"
    saved = sorted(path.glob("*.json")) if path.is_dir() else []
    if not saved:
        return
    report, why = artifact.load_path(saved[0])
    assert report is not None, why
    for match in report.matches[:3]:
        payload = panel.build_panel_payload(match)
        data = moderator.build_input(payload, [])
        assert sorted(data) == ["conflicts", "evidence", "market_reference",
                                "match", "opinions"]


def test_q2_real_artifact_round_has_numbered_matches():
    from toto import artifact
    path = Path(__file__).resolve().parent.parent / "data" / "artifacts"
    saved = sorted(path.glob("*.json")) if path.is_dir() else []
    if not saved:
        return
    report, _why = artifact.load_path(saved[0])
    numbers = [m.no for m in report.matches]
    assert numbers == sorted(numbers) and len(set(numbers)) == len(numbers)
    assert all(isinstance(n, int) and n > 0 for n in numbers)


def main() -> int:
    print("Phase 6-F-3 — 1·2단계 보관 + 3단계 조립")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 1 if _FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
