"""3단계 결과 보관 + 기존 [4] 연결 + 워크플로 상태 (Phase 6-F-4).

6-F-3 이 1·2단계를 보관하고 3단계 입력을 조립했다. 남은 칸이 둘이었다.

  · 3단계 결과만 **보관되지 않았다** — 붙여넣으면 곧바로 `[4]` 로 흘러가
    클로드가 실제로 돌려준 배열이 사라졌다
  · 회차가 어디까지 왔는지 **파일로 읽을 방법이 없었다**

지키려는 것 넷이다.

  1. **클로드를 부르지 않는다** — 이 Phase 도 분석을 자동화하지 않는다
  2. **새 결과 포맷을 만들지 않는다** — 보관본을 기존 `--paste-panel-result`
     에 그대로 태운다. `[4]` 의 처리 계약이 한 줄도 바뀌지 않는다
  3. **검증기를 새로 쓰지 않는다** — `panelpaste.convert` + `panelimport.
     validate` 를 그대로 지난다 (그것이 다시 `moderator.parse_result` 를
     부른다)
  4. **상태 DB 를 만들지 않는다** — 다섯 단계가 전부 파일이 있느냐로 정해진다

그리고 6-F-3 의 산출물이 **한 바이트도 바뀌지 않는다** (D 절).
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import (fixtures, panel, panelexport, panelimport,  # noqa: E402
                  panelpaste, panelwork, settings as settings_mod)
from toto.analyze import run_all                              # noqa: E402
from toto.models import Report                                # noqa: E402

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
# 픽스처
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


def mod_row(match, **over) -> dict:
    """3단계 결과 한 경기. 기본은 **통과하는** 모양이다."""
    ids = allowed_ids(match)
    row = {
        "match_no": match.no,
        "simulations": 6,
        "distribution": [
            {"home": 2, "away": 1, "count": 4, "origin": "data_analyst"},
            {"home": 1, "away": 1, "count": 2,
             "origin": "matchup_tactical_analyst"},
        ],
        "adopted_home": 2, "adopted_away": 1,
        "adopted_from": ["data_analyst"],
        "conclusion": (f"{match.no}번 토론 결과 예상 스코어는 2-1 입니다. "
                       f"데이터 쪽 근거가 더 많이 인용됐습니다. 다만 표본이 "
                       f"얕습니다."),
        "common_points": [f"{match.no}번 공통점"],
        "differences": [],
        "counterpoints": [],
        "uncertainty": [f"{match.no}번 표본이 얕다"],
        "evidence_ids": ids,
    }
    row.update(over)
    return row


def mod_array(report: Report, *, numbers=None, over=None) -> str:
    rows = [mod_row(m, **(over or {})) for m in report.matches
            if numbers is None or m.no in numbers]
    return json.dumps(rows, ensure_ascii=False)


def stage_array(report: Report, tag: str) -> str:
    """1·2단계 응답 배열 (6-F-3 의 픽스처와 같은 모양)."""
    rows = [{"match_no": m.no, "predicted_home": 2, "predicted_away": 1,
             "summary": f"{tag}{m.no} 요약",
             "rationale": [f"{tag}{m.no} 근거"],
             "evidence_ids": allowed_ids(m)} for m in report.matches]
    return json.dumps(rows, ensure_ascii=False)


def scratch() -> Path:
    """**저장소 밖** 임시 디렉터리. 실제 panel_work/ 를 건드리지 않는다."""
    return Path(tempfile.mkdtemp(prefix="toto_wf_test_"))


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


def code_of(node) -> str:
    """docstring 을 뺀 본문.

    **낱말 검색이 문서에 걸리지 않게 한다** — 이 저장소의 함수들은 "무엇을
    하지 않는다" 를 docstring 에 적으므로, 그 설명이 스스로 검사에 걸린다
    (6-F-3 의 `test_a1` 이 같은 이유로 AST 로 바뀌었다). 지키려는 것은
    문서가 아니라 코드다.
    """
    body = [n for n in node.body
            if not (isinstance(n, ast.Expr)
                    and isinstance(n.value, ast.Constant)
                    and isinstance(n.value.value, str))]
    return "\n".join(ast.unparse(n) for n in body)


def literals_in(module) -> list[str]:
    """모듈의 문자열 상수. **docstring 은 뺀다** (위와 같은 이유)."""
    tree = ast.parse(source_of(module))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            for stmt in getattr(node, "body", [])[:1]:
                if (isinstance(stmt, ast.Expr)
                        and isinstance(stmt.value, ast.Constant)
                        and isinstance(stmt.value.value, str)):
                    docs.add(id(stmt.value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docs]


def imported_names(module) -> set[str]:
    tree = ast.parse(source_of(module))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            out |= {a.name for a in node.names}
            if node.module:
                out.add(node.module.split(".")[0])
    return out


# ==========================================================================
# A. 워크플로 상태 — **파일이 정한다. 상태 DB 가 없다**
# ==========================================================================
def test_a1_fresh_round_is_all_not_started():
    base = scratch()
    wf = panelwork.workflow("260099", base=base, outdir=base / "nope")
    states = [s.state for s in wf.stages]
    assert states == [panelwork.A_NOT_STARTED, panelwork.B_NOT_STARTED,
                      panelwork.MODERATOR_INPUT_NOT_BUILT,
                      panelwork.MODERATOR_RESULT_NOT_SAVED,
                      panelwork.PANEL_RESULT_NOT_APPLIED], states
    assert not wf.done
    assert wf.next_stage().key == panelwork.STAGE_A


def test_a2_each_stage_flips_when_its_file_appears():
    """상태는 **그 단계의 파일 하나**로 정해진다."""
    base, out = scratch(), scratch()
    rep = demo_report()
    rid = "260099"

    def state(key):
        return panelwork.workflow(rid, base=base, outdir=out).stage(key).state

    panelwork.path_for(rid, panel.DATA_ANALYST, base).parent.mkdir(
        parents=True, exist_ok=True)
    panelwork.path_for(rid, panel.DATA_ANALYST, base).write_text("[]")
    assert state(panelwork.STAGE_A) == panelwork.A_COMPLETE
    assert state(panelwork.STAGE_B) == panelwork.B_NOT_STARTED

    panelwork.path_for(rid, panel.MATCHUP_ANALYST, base).write_text("[]")
    assert state(panelwork.STAGE_B) == panelwork.B_COMPLETE

    (out / panelwork.COMPLETED_SHEET).write_text("x")
    assert state(panelwork.STAGE_INPUT) == panelwork.MODERATOR_INPUT_READY

    panelwork.moderator_result_path(rid, base).write_text("[]")
    assert state(panelwork.STAGE_RESULT) == panelwork.MODERATOR_RESULT_SAVED

    inbox = panelimport.inbox_dir(base)
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"{rid}{panelimport.FILE_SUFFIX}").write_text("{}")
    assert state(panelwork.STAGE_APPLY) == panelwork.PANEL_RESULT_COMPLETE
    assert panelwork.workflow(rid, base=base, outdir=out).done
    assert len(rep.matches) == 14


def test_a3_no_state_database_is_written():
    """상태를 **따로 저장하지 않는다.** `workflow()` 는 읽기만 한다."""
    node = fn_node(panelwork, "workflow")
    body = ast.unparse(node)
    for bad in ("write_text", "mkdir", "open(", "os.replace", "json.dump"):
        assert bad not in body, f"workflow() 가 {bad} 를 한다"
    base = scratch()
    before = sorted(p.name for p in base.iterdir())
    panelwork.workflow("260099", base=base, outdir=base / "nope")
    assert sorted(p.name for p in base.iterdir()) == before


def test_a4_status_needs_no_artifact_and_no_network():
    """회차 자료가 없어도 상태를 볼 수 있다 — 수집 전에도 부른다."""
    base = scratch()
    wf = panelwork.workflow("999999", base=base, outdir=base / "nope")
    assert wf.round_id == "999999"
    assert len(wf.stages) == 5
    body = code_of(fn_node(panelwork, "workflow"))
    for bad in ("artifact", "run_all", "requests", "read_league",
                "revive_report"):
        assert bad not in body, f"workflow() 가 {bad} 를 쓴다"
    assert "artifact" not in imported_names(panelwork)


def test_a5_attachment_names_are_read_from_the_folder():
    """첨부 파일 이름을 코드에 적어 두지 않는다 (§10).

    회차마다 `02_경기자료_3of7.md` 처럼 개수와 이름이 달라진다 — 적어 두면
    사용자에게 **없는 파일**을 첨부하라고 말하게 된다.
    """
    base, out = scratch(), scratch()
    out.mkdir(parents=True, exist_ok=True)
    for name in ("00_프로젝트_지침.md", "02_경기자료_1of3.md",
                 "02_경기자료_2of3.md", "02_경기자료_3of3.md",
                 "03_사회자자료.md", "04_PanelResult_JSON_규격.md"):
        (out / name).write_text("x")
    wf = panelwork.workflow("260099", base=base, outdir=out)
    a = wf.stage(panelwork.STAGE_A)
    names = [p.name for p in a.attachments]
    assert names.count("02_경기자료_1of3.md") == 1
    assert "02_경기자료_3of3.md" in names, names
    assert "1of3" in a.todo and "3of3" in a.todo

    # **코드의 문자열 상수**를 본다 (docstring 은 뺀다) — 설명은 바로 그
    # 이름을 예로 들어 "적어 두지 않는다" 를 말하므로 낱말로 재면 걸린다.
    for lit in literals_in(panelwork):
        for bad in ("1of", "경기자료", "사회자자료.md", "지침.md", "규격.md"):
            assert bad not in lit, f"panelwork.py 에 파일 이름 {lit!r} 이 박혀 있다"
    # 조립본 이름만 예외다 — 그건 이 모듈이 **직접 만드는** 파일이다.
    assert panelwork.COMPLETED_SHEET in literals_in(panelwork)


def test_a6_completed_sheet_supersedes_the_blank_one():
    """조립본이 있으면 **그것만** 첨부하라고 적는다 — 둘 다 내면 헷갈린다."""
    base, out = scratch(), scratch()
    out.mkdir(parents=True, exist_ok=True)
    (out / "03_사회자자료.md").write_text("x")
    (out / "04_PanelResult_JSON_규격.md").write_text("x")
    wf = panelwork.workflow("260099", base=base, outdir=out)
    names = [p.name for p in wf.stage(panelwork.STAGE_RESULT).attachments]
    assert names == ["03_사회자자료.md", "04_PanelResult_JSON_규격.md"], names

    (out / panelwork.COMPLETED_SHEET).write_text("x")
    wf = panelwork.workflow("260099", base=base, outdir=out)
    names = [p.name for p in wf.stage(panelwork.STAGE_RESULT).attachments]
    assert names == [panelwork.COMPLETED_SHEET,
                     "04_PanelResult_JSON_규격.md"], names


def test_a7_next_step_text_names_the_menu_item():
    """다음 할 일이 **어느 메뉴 번호인지** 말한다 (§9)."""
    base, out = scratch(), scratch()
    rid = "260099"
    wf = panelwork.workflow(rid, base=base, outdir=out)
    assert "[1]" in wf.next_stage().todo

    p = panelwork.path_for(rid, panel.DATA_ANALYST, base)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[]")
    assert "[2]" in panelwork.workflow(rid, base=base,
                                       outdir=out).next_stage().todo
    panelwork.path_for(rid, panel.MATCHUP_ANALYST, base).write_text("[]")
    assert "[3]" in panelwork.workflow(rid, base=base,
                                       outdir=out).next_stage().todo
    out.mkdir(parents=True, exist_ok=True)
    (out / panelwork.COMPLETED_SHEET).write_text("x")
    assert "[4]" in panelwork.workflow(rid, base=base,
                                       outdir=out).next_stage().todo
    panelwork.moderator_result_path(rid, base).write_text("[]")
    assert "[5]" in panelwork.workflow(rid, base=base,
                                       outdir=out).next_stage().todo


def test_a8_status_lines_do_not_judge():
    """상태는 **사실만** 적는다 — 품질·추천·확신도를 만들지 않는다."""
    base, out = scratch(), scratch()
    lines = "\n".join(panelwork.workflow_lines(
        panelwork.workflow("260099", base=base, outdir=out)))
    for bad in ("추천", "신뢰도", "확신도", "합의도", "유력", "%", "점수"):
        assert bad not in lines, f"상태 줄에 '{bad}' 가 있다"


def test_a9_counts_come_from_the_file_not_from_a_guess():
    base = scratch()
    rid = "260099"
    p = panelwork.moderator_result_path(rid, base)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([{"match_no": 1}, {"match_no": 2}]))
    st = panelwork.workflow(rid, base=base, outdir=base / "x").stage(
        panelwork.STAGE_RESULT)
    assert st.detail == "2경기", st.detail

    p.write_text("{ broken")
    st = panelwork.workflow(rid, base=base, outdir=base / "x").stage(
        panelwork.STAGE_RESULT)
    assert "읽지 못했습니다" in st.detail, st.detail
    # **지어내지 않는다** — 못 읽으면 0 이라고 적지 않는다.
    assert "0경기" not in st.detail


# ==========================================================================
# B. 3단계 결과 검증 — 기존 검증기를 그대로 지난다
# ==========================================================================
def test_b1_good_result_is_saved_as_the_raw_array():
    """보관하는 것은 **클로드가 돌려준 배열 그대로**다."""
    base, rep = scratch(), demo_report()
    text = mod_array(rep)
    path, out = panelwork.save_moderator_result(text, rep, base=base)
    assert path is not None, [str(i) for i in out.issues]
    assert out.success and not out.errors
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == json.loads(text)
    assert isinstance(saved, list) and len(saved) == 14
    # canonical Panel Result 로 옮겨 적지 않는다.
    assert "schema_version" not in str(saved[0])
    assert path.name == panelwork.MODERATOR_RESULT_FILE


def test_b2_partial_round_is_rejected():
    """13경기·15경기 — 둘 다 회차 결과가 아니다."""
    base, rep = scratch(), demo_report()
    short = [m.no for m in rep.matches][:13]
    path, out = panelwork.save_moderator_result(
        mod_array(rep, numbers=short), rep, base=base)
    assert path is None
    codes = {i.code for i in out.errors}
    assert "PASTE_INCOMPLETE_ROUND" in codes, codes

    rows = json.loads(mod_array(rep))
    rows.append(mod_row(rep.matches[0], match_no=99))
    path, out = panelwork.save_moderator_result(
        json.dumps(rows, ensure_ascii=False), rep, base=base)
    assert path is None
    assert "PASTE_UNKNOWN_MATCH_NO" in {i.code for i in out.errors}


def test_b3_duplicate_match_no_is_rejected():
    base, rep = scratch(), demo_report()
    rows = json.loads(mod_array(rep))
    rows.append(dict(rows[0]))
    path, out = panelwork.save_moderator_result(
        json.dumps(rows, ensure_ascii=False), rep, base=base)
    assert path is None
    assert "PASTE_DUPLICATE_MATCH_NO" in {i.code for i in out.errors}


def test_b4_unknown_evidence_id_is_rejected():
    base, rep = scratch(), demo_report()
    rows = json.loads(mod_array(rep))
    rows[0]["evidence_ids"] = ["E999"]
    path, out = panelwork.save_moderator_result(
        json.dumps(rows, ensure_ascii=False), rep, base=base)
    assert path is None, "없는 근거 ID 가 통과했다"
    assert out.errors


def test_b5_evidence_id_from_another_match_is_rejected():
    """근거 ID 는 **그 경기**의 것이어야 한다 (§1-15).

    경기마다 다시 매겨지므로 다른 경기의 ID 를 쓰면 다른 사실을 가리킨다.
    """
    base, rep = scratch(), demo_report()
    donor = next((m for m in rep.matches[1:]
                  if allowed_ids(m) and len(allowed_ids(m))
                  > len(allowed_ids(rep.matches[0]))), None)
    if donor is None:
        return                       # 픽스처에 그런 짝이 없으면 건너뛴다
    rows = json.loads(mod_array(rep))
    rows[0]["evidence_ids"] = [allowed_ids(donor)[-1]]
    path, out = panelwork.save_moderator_result(
        json.dumps(rows, ensure_ascii=False), rep, base=base)
    assert path is None, "다른 경기의 근거 ID 가 통과했다"


def test_b6_non_array_input_is_rejected():
    base, rep = scratch(), demo_report()
    for text, code in (
            ("{\"match_no\": 1}", "PASTE_NOT_A_LIST"),
            ("[]", "PASTE_EMPTY"),
            ("", "PASTE_EMPTY"),
            ("   ", "PASTE_EMPTY")):
        path, out = panelwork.save_moderator_result(text, rep, base=base)
        assert path is None, text
        assert code in {i.code for i in out.errors}, (text, out.errors)


def test_b7_prose_prefix_is_rejected_not_repaired():
    """앞에 설명 문장이 붙으면 **고쳐 주지 않는다** — 실패시킨다."""
    base, rep = scratch(), demo_report()
    text = "아래가 3단계 결과입니다.\n\n" + mod_array(rep)
    path, out = panelwork.save_moderator_result(text, rep, base=base)
    assert path is None
    assert "PASTE_NOT_JSON" in {i.code for i in out.errors}


def test_b8_code_fence_is_the_only_tolerance():
    """```json 울타리만 걷어낸다 — 채팅에서 복사하면 자주 함께 온다."""
    base, rep = scratch(), demo_report()
    text = "```json\n" + mod_array(rep) + "\n```"
    path, out = panelwork.save_moderator_result(text, rep, base=base)
    assert path is not None, [str(i) for i in out.issues]
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(
        mod_array(rep))


def test_b9_bad_scores_are_rejected_not_coerced():
    """`"2-1"` 을 2 와 1 로 읽지 않고 `1.5` 를 반올림하지 않는다 (§1-9)."""
    base, rep = scratch(), demo_report()
    cases = [
        {"adopted_home": "2", "adopted_away": "1"},
        {"adopted_home": 2.0, "adopted_away": 1.5},
        {"adopted_home": -1, "adopted_away": 1},
        {"adopted_home": True, "adopted_away": 1},
    ]
    for over in cases:
        rows = json.loads(mod_array(rep))
        rows[0].update(over)
        path, out = panelwork.save_moderator_result(
            json.dumps(rows, ensure_ascii=False), rep, base=base)
        assert path is None, f"{over} 가 통과했다"
        assert out.errors


def test_b10_distribution_count_must_match_simulations():
    base, rep = scratch(), demo_report()
    rows = json.loads(mod_array(rep))
    rows[0]["simulations"] = 7          # 분포 합은 6
    path, out = panelwork.save_moderator_result(
        json.dumps(rows, ensure_ascii=False), rep, base=base)
    assert path is None
    assert out.errors


def test_b11_adopted_score_must_appear_in_the_distribution():
    base, rep = scratch(), demo_report()
    rows = json.loads(mod_array(rep))
    rows[0]["adopted_home"] = 3         # 분포에 3-1 이 없다
    path, out = panelwork.save_moderator_result(
        json.dumps(rows, ensure_ascii=False), rep, base=base)
    assert path is None
    assert out.errors


def test_b12_forbidden_fields_are_rejected():
    """승무패·추천·확신도 칸은 자리가 없다 (§1-3)."""
    base, rep = scratch(), demo_report()
    for bad in ("winner", "confidence", "lean", "recommendation"):
        rows = json.loads(mod_array(rep))
        rows[0][bad] = "home"
        path, out = panelwork.save_moderator_result(
            json.dumps(rows, ensure_ascii=False), rep, base=base)
        assert path is None, f"{bad} 가 통과했다"
        assert "FORBIDDEN_FIELD" in {i.code for i in out.errors}


def test_b13_skipped_match_is_kept_as_skipped():
    """돌리지 않은 경기를 '토론 실패' 로 바꾸지 않는다 (§1-15-2)."""
    base, rep = scratch(), demo_report()
    rows = json.loads(mod_array(rep))
    rows[0] = {"match_no": rows[0]["match_no"], "simulations": 0,
               "distribution": [], "adopted_home": None, "adopted_away": None}
    path, out = panelwork.save_moderator_result(
        json.dumps(rows, ensure_ascii=False), rep, base=base)
    assert path is not None, [str(i) for i in out.issues]
    saved = json.loads(path.read_text(encoding="utf-8"))
    # **원문 그대로** 보관한다 — `panel_status` 를 여기서 적어 넣지 않는다.
    assert saved[0] == rows[0]
    assert "panel_status" not in saved[0]


def test_b14_null_adopted_with_reason_is_kept():
    """못 고른 경우를 `0 : 0` 으로 채우지 않는다 (§1-5)."""
    base, rep = scratch(), demo_report()
    rows = json.loads(mod_array(rep))
    rows[0]["adopted_home"] = None
    rows[0]["adopted_away"] = None
    rows[0]["adopted_from"] = []
    path, out = panelwork.save_moderator_result(
        json.dumps(rows, ensure_ascii=False), rep, base=base)
    saved = json.loads(path.read_text(encoding="utf-8")) if path else None
    if path is not None:
        assert saved[0]["adopted_home"] is None
    else:
        assert out.errors        # 사유가 없다고 막혔으면 그것도 정답이다


def test_b15_failure_leaves_the_previous_file_untouched():
    """실패해도 앞서 받아 둔 결과를 잃지 않는다 (§16)."""
    base, rep = scratch(), demo_report()
    good = mod_array(rep)
    path, _out = panelwork.save_moderator_result(good, rep, base=base)
    before = path.read_bytes()
    panelwork.save_moderator_result("이건 JSON 이 아니다", rep, base=base)
    assert path.read_bytes() == before


def test_b16_result_is_not_written_to_the_inbox():
    """`panel_results/` 는 `[4]` 의 자리다 — 이 모듈이 쓰지 않는다."""
    base, rep = scratch(), demo_report()
    panelwork.save_moderator_result(mod_array(rep), rep, base=base)
    assert not panelimport.inbox_dir(base).exists()
    node = fn_node(panelwork, "save_moderator_result")
    assert "inbox_dir" not in ast.unparse(node)
    assert "canonical_path" not in ast.unparse(node)


def test_b17_validation_is_not_reimplemented():
    """스코어·분포·근거를 여기서 다시 검사하지 않는다 (§6)."""
    node = fn_node(panelwork, "parse_moderator_result")
    calls = calls_in(node)
    assert "panelpaste.convert" in calls, calls
    assert "panelimport.validate" in calls, calls
    body = ast.unparse(node)
    for bad in ("adopted_home", "distribution", "simulations",
                "evidence_ids", "isinstance"):
        assert bad not in body, f"parse_moderator_result 가 {bad} 를 본다"


def test_b18_save_writes_atomically():
    """원자적 저장. 6-F-12 에서 **세 보관 함수가 한 헬퍼를 쓴다.**

    6-F-4 때는 이 함수 안에 `os.replace` 가 직접 있었다. 지키려는 것은
    '이 함수가 그 줄을 갖고 있다' 가 아니라 **쓰다 만 파일이 자리에 남지
    않는다** 이므로, 한 곳으로 모은 뒤에도 그대로 고정한다 — 오히려
    보관 함수가 하나 늘어도 같은 규칙을 지나게 된다.
    """
    body = ast.unparse(fn_node(panelwork, "save_moderator_result"))
    assert "_atomic_write" in body, "원자적 저장 경로를 거치지 않는다"
    helper = ast.unparse(fn_node(panelwork, "_atomic_write"))
    assert "os.replace" in helper and ".tmp" in helper
    # 1·2단계와 조립본도 같은 문을 지난다.
    for name in ("save_stage", "build_completed_sheet"):
        assert "_atomic_write" in ast.unparse(fn_node(panelwork, name)), name


# ==========================================================================
# C. 기존 [4] 와 연결 — 계약을 바꾸지 않는다
# ==========================================================================
def test_c1_saved_file_feeds_the_existing_paste_path():
    """보관본을 `panelpaste.apply()` 에 그대로 태울 수 있다.

    이것이 성립하므로 `[6]-5` 는 **새 반영 경로를 만들지 않는다** — 기존
    `--paste-panel-result` 인자를 그대로 쓴다.
    """
    base, rep = scratch(), demo_report()
    path, _out = panelwork.save_moderator_result(mod_array(rep), rep,
                                                 base=base)
    assert path is not None
    canon, result = panelpaste.apply(path.read_text(encoding="utf-8"), rep,
                                     base=base)
    assert canon is not None, [str(i) for i in result.issues]
    assert canon == panelpaste.canonical_path("DEMO", base)
    data = json.loads(canon.read_text(encoding="utf-8"))
    assert data["schema_version"] == panelimport.SCHEMA_VERSION
    assert len(data["matches"]) == 14


def test_c2_no_new_result_format():
    """Panel Result 규격을 건드리지 않는다 (§3)."""
    assert panelimport.SCHEMA_VERSION == "1.1"
    assert panelimport.SUPPORTED_VERSIONS == ("1.0", "1.1")
    src = source_of(panelwork)
    for bad in ("SCHEMA_VERSION =", "schema_version\":", "1.2"):
        assert bad not in src, f"panelwork.py 가 {bad} 를 정한다"


def test_c3_menu_item_5_reuses_the_existing_flag():
    """`[6]-5` 가 반영을 메뉴에서 다시 구현하지 않고 CLI 인자를 넘긴다.

    **6-F-14 범위 이동.** 6-F-4 는 이것을 "`--paste-panel-result` 를 쓴다"
    로 고정했는데, 3단계 보관본만 그 어댑터에 넘기면 1·2단계 원문이 최종
    결과에서 빠졌다 (6-F-13). 이제 `[6]-5` 는 자동 경로와 **같은 인자**
    `--apply-panel-work` 를 넘긴다. 지키려던 것은 그대로다 —

      · 메뉴는 인자만 만들고 검증·반영은 CLI 가 한다 (`test_c4`).
      · 번호가 밀리지 않는다 (여섯 개 그대로).
      · **`--paste-panel-result` 는 없어지지 않았다** — 3단계 응답만 가진
        경우의 입구로 `[4]` 하위(붙여넣기)에 그대로 남아 있다.
    """
    from toto import menu
    item5 = code_of(fn_node(menu, "_panel_work_for"))
    assert "--apply-panel-work" in item5, "[6]-5 가 세 보관본을 반영하지 않는다"
    assert "--paste-panel-result" not in item5, \
        "[6]-5 가 사회자 보관본만 붙여넣기 어댑터에 넘긴다"
    # 사회자 전용 입구는 제자리에 남는다 (6-F-14 금지: 제거하지 않는다).
    assert "--paste-panel-result" in code_of(fn_node(menu, "_paste_panel")), \
        "--paste-panel-result 입구가 메뉴에서 사라졌다"
    keys = {k for k, _t, _w in menu.PANEL_WORK}
    assert keys == {"1", "2", "3", "4", "5", "6"}, keys


def test_c4_menu_does_not_reimplement_validation():
    """검증을 메뉴에서 다시 쓰지 않는다 (§1-20 과 같은 이유)."""
    from toto import menu
    src = source_of(menu)
    for bad in ("save_moderator_result", "parse_moderator_result",
                "panelimport.validate", "panelpaste.apply", "parse_result"):
        assert bad not in src, f"menu.py 가 {bad} 를 직접 부른다"


def test_c5_paste_and_import_contracts_are_untouched():
    """`[4]` 의 처리 계약이 바뀌지 않았다 (§3).

    `panelpaste`·`panelimport`·`panelaudit` 어디에도 `panelwork` 라는
    낱말이 없다 — 연결은 **한 방향**이다.
    """
    from toto import panelaudit
    for mod in (panelpaste, panelimport, panelaudit):
        assert "panelwork" not in source_of(mod), mod.__name__


def test_c6_cli_still_routes_paste_through_one_handler():
    """붙여넣기가 지나는 문이 여전히 하나다."""
    from toto import cli
    body = code_of(fn_node(cli, "_handle_panel_file"))
    assert "_paste_to_canonical" in body, "붙여넣기가 그 문을 지나지 않는다"
    src = source_of(cli)
    assert src.count("_paste_to_canonical(") == 2   # 정의 1 + 호출 1
    # 변환·검증·저장은 `panelpaste.apply()` **한 곳**에서만 일어난다.
    assert src.count("panelpaste.apply(") == 1, "붙여넣기 문이 둘이다"
    assert "panelwork" not in code_of(fn_node(cli, "_handle_panel_file"))


def test_c7_panel_work_branch_is_before_collection():
    """상태·보관은 **수집 구간 앞**에서 갈라진다."""
    from toto import cli
    node = fn_node(cli, "main")
    body = ast.unparse(node)
    i_work = body.index("_panel_work(args, settings)")
    i_src = body.index("from .sources import betman")
    assert i_work < i_src, "수집 뒤에서 갈라진다"


# ==========================================================================
# D. 클로드를 부르지 않는다
# ==========================================================================
def test_d1_module_never_imports_the_api_layer():
    """`llm`·`anthropic` 이 이 모듈에 없다. **import 문을 본다.**"""
    names = imported_names(panelwork)
    assert "anthropic" not in names
    assert "llm" not in names, names


def test_d2_new_functions_never_call_the_api_executor():
    for fname in ("parse_moderator_result", "save_moderator_result",
                  "workflow", "workflow_lines", "export_files"):
        calls = calls_in(fn_node(panelwork, fname))
        for bad in ("panel.run_match", "panel.run_panel_role",
                    "panel.attach_panels", "moderator.run_moderator",
                    "llm.complete", "llm.ask"):
            assert bad not in calls, f"{fname} 이 {bad} 를 부른다"


def test_d3_cli_panel_work_never_touches_sources_or_llm():
    from toto import cli
    node = fn_node(cli, "_panel_work")
    body = "\n".join(ast.unparse(n) for n in node.body
                     if not (isinstance(n, ast.Expr)
                             and isinstance(n.value, ast.Constant)))
    for bad in ("sources", "anthropic", "run_match", "attach_panels",
                "run_moderator", "run_panel_role"):
        assert bad not in body, f"_panel_work 에 {bad} 가 있다"


def test_d4_menu_panel_work_never_calls_the_api_path():
    from toto import menu
    node = fn_node(menu, "_panel_work_args")
    body = ast.unparse(node)
    for bad in ("--panel\"", "anthropic", "run_match", "ANTHROPIC"):
        assert bad not in body, f"메뉴 [6] 이 {bad} 를 쓴다"


def test_d5_no_browser_automation_of_claude():
    """클로드를 브라우저로 자동 조작하지 않는다 (§21).

    **Playwright 자체를 금지하지 않는다** — `sources/browser.py` 가 FotMob·
    후스코어드를 받는 데 오래전부터 쓰고 있고 `cli.py` 는 그 선택 의존성을
    설명한다. 막으려는 것은 그 도구가 **이 Phase 의 경로**에 들어오는 것이다.
    """
    from toto import cli, menu
    tools = ("playwright", "selenium", "webdriver", "pyautogui",
             "pyperclip", "undetected_chromedriver")
    src = source_of(panelwork).lower()
    for bad in tools:
        assert bad not in src, f"panelwork.py 에 {bad} 가 있다"
    for mod, fname in ((cli, "_panel_work"), (cli, "_guide_next"),
                       (menu, "_panel_work_args"),
                       (menu, "_confirm_overwrite")):
        body = ast.unparse(fn_node(mod, fname)).lower()
        for bad in tools:
            assert bad not in body, f"{fname} 에 {bad} 가 있다"
    # 새 의존성을 들이지 않았다.
    req = (Path(__file__).resolve().parent.parent
           / "requirements-toto.txt").read_text(encoding="utf-8")
    assert "pyperclip" not in req and "pyautogui" not in req


# ==========================================================================
# E. 6-F-3 회귀 — 산출물이 한 바이트도 바뀌지 않는다
# ==========================================================================
def test_e1_moderator_sheet_without_opinions_is_unchanged():
    """`opinions_by_no=None` 인 기존 경로가 그대로다 (6-F-3 §21)."""
    rep = demo_report()
    payloads = [panel.build_panel_payload(m) for m in rep.matches]
    text = panelexport.moderator_data_sheet("DEMO", payloads)
    assert "1·2단계 의견이 이미 들어 있습니다" not in text
    assert "\"opinions\": []" in text or "\"opinions\":[]" in text
    again = panelexport.moderator_data_sheet("DEMO", payloads)
    assert hashlib.sha256(text.encode()).hexdigest() == \
        hashlib.sha256(again.encode()).hexdigest()


def test_e2_stage_save_and_build_still_work():
    """6-F-3 의 1·2단계 보관·조립이 그대로다."""
    base, out, rep = scratch(), scratch(), demo_report()
    a = panelwork.save_stage(stage_array(rep, "A"), panel.DATA_ANALYST, rep,
                             base=base)
    b = panelwork.save_stage(stage_array(rep, "B"), panel.MATCHUP_ANALYST,
                             rep, base=base)
    assert a.success and b.success
    built = panelwork.build_completed_sheet(rep, base=base, outdir=out)
    assert built.success, [str(i) for i in built.issues]
    text = built.path.read_text(encoding="utf-8")
    assert "◀" not in text and "▶" not in text
    assert "\"opinions\": []" not in text


def test_e3_existing_names_are_unchanged():
    """6-F-3 이 정한 이름·자리를 바꾸지 않았다."""
    assert panelwork.WORK_DIRNAME == "panel_work"
    assert panelwork.COMPLETED_SHEET == "03_사회자자료_완성.md"
    assert panelwork.ROLE_FILES == {
        panel.DATA_ANALYST: "analyst_a.json",
        panel.MATCHUP_ANALYST: "analyst_b.json"}
    assert panelwork.MODERATOR_RESULT_FILE == "moderator_result.json"
    # 같은 폴더에 나란히 둔다 — 셋이 한 회차의 작업물이다.
    base = scratch()
    paths = {panelwork.path_for("R", panel.DATA_ANALYST, base).parent,
             panelwork.path_for("R", panel.MATCHUP_ANALYST, base).parent,
             panelwork.moderator_result_path("R", base).parent}
    assert len(paths) == 1


def test_e4_cli_flags_from_6f3_still_exist():
    from toto import cli
    src = source_of(cli)
    for flag in ("--save-panel-opinion", "--role", "--build-moderator-input"):
        assert flag in src
    parser = cli.build_parser()
    args = parser.parse_args(["--round", "R", "--panel-workflow-status"])
    assert args.panel_workflow_status and args.round_id == "R"
    args = parser.parse_args(["--round", "R", "--save-moderator-result", "f"])
    assert str(args.save_moderator_result) == "f"
    # 기본값은 전부 꺼져 있다 — 아무것도 주지 않으면 6-F-3 이전과 같다.
    args = parser.parse_args(["--demo"])
    assert args.save_moderator_result is None
    assert args.panel_workflow_status is False


def test_e5_overwrite_prompt_lives_in_the_menu_only():
    """CLI 는 비대화형이라 묻지 않는다 — 6-F-3 의 CLI 동작이 그대로다."""
    from toto import cli, menu
    assert "교체하시겠습니까" in source_of(menu)
    assert "교체하시겠습니까" not in source_of(cli)
    node = fn_node(menu, "_confirm_overwrite")
    body = ast.unparse(node)
    assert "y" in body and "N]" in body


def test_e6_overwrite_default_is_no():
    """기본이 **아니오**다 — 실수로 Enter 를 눌러 잃지 않는다 (§13)."""
    from toto import menu
    base = scratch()
    p = base / "x.json"
    p.write_text("[]")
    answers = iter(["", "n", "아니오", "y", "Y", "yes"])
    orig = menu._ask
    menu._ask = lambda _prompt: next(answers)
    try:
        assert menu._confirm_overwrite(p, "테스트") is False   # 그냥 Enter
        assert menu._confirm_overwrite(p, "테스트") is False
        assert menu._confirm_overwrite(p, "테스트") is False
        assert menu._confirm_overwrite(p, "테스트") is True
        assert menu._confirm_overwrite(p, "테스트") is True
        assert menu._confirm_overwrite(p, "테스트") is True
        # 파일이 없으면 묻지 않는다.
        assert menu._confirm_overwrite(base / "none.json", "테스트") is True
    finally:
        menu._ask = orig


def test_e7_manual_workflow_is_still_reachable():
    """6-F-4 의 수동 기능에 여전히 닿을 수 있다.

    **범위를 옮겼다** — 6-F-6 이 메뉴를 일하는 순서로 다시 짜면서 단계별
    항목을 `[4] 패널 수동 진행·복구` 아래로 모았다(§35). 지키려는 것은
    번호가 아니라 **기능에 닿을 수 있다는 것**이다.
    """
    from toto import menu
    by_key = {k: a for k, _t, _d, a in menu.ITEMS}
    assert by_key["4"] == "panel-manual"
    src = Path(menu.__file__).read_text(encoding="utf-8")
    for flag in ("--save-moderator-result", "--paste-panel-result",
                 "--panel-workflow-status", "--import-panel-result"):
        assert flag in src, f"{flag} 에 닿을 수 없다"


# ==========================================================================
# F. 상태 이름과 어휘
# ==========================================================================
def test_f1_state_names_are_exactly_the_five_pairs():
    names = [panelwork.A_NOT_STARTED, panelwork.A_COMPLETE,
             panelwork.B_NOT_STARTED, panelwork.B_COMPLETE,
             panelwork.MODERATOR_INPUT_NOT_BUILT,
             panelwork.MODERATOR_INPUT_READY,
             panelwork.MODERATOR_RESULT_NOT_SAVED,
             panelwork.MODERATOR_RESULT_SAVED,
             panelwork.PANEL_RESULT_NOT_APPLIED,
             panelwork.PANEL_RESULT_COMPLETE]
    assert names == [
        "A_NOT_STARTED", "A_COMPLETE", "B_NOT_STARTED", "B_COMPLETE",
        "MODERATOR_INPUT_NOT_BUILT", "MODERATOR_INPUT_READY",
        "MODERATOR_RESULT_NOT_SAVED", "MODERATOR_RESULT_SAVED",
        "PANEL_RESULT_NOT_APPLIED", "PANEL_RESULT_COMPLETE"], names
    assert len(set(names)) == 10


def test_f2_status_uses_the_four_word_vocabulary():
    """보관 결과는 §1-6 의 어휘를 그대로 쓴다 — 새 낱말을 만들지 않는다.

    데모 픽스처는 시즌 색인이 없어 `LOCAL_MATCH_ID_MISSING` 경고가 붙는다.
    그때 `부분` 이 나오는 것이 **맞다** — '가져올 수는 있으나 확인이 필요'
    라는 뜻이고, `실패` 와 뭉뚱그리지 않는 것이 이 어휘의 요점이다.
    """
    base, rep = scratch(), demo_report()
    path, ok = panelwork.save_moderator_result(mod_array(rep), rep, base=base)
    assert path is not None and ok.success
    first = ok.status_line().split(" ")[0]
    assert first in {"ok", "부분"}, ok.status_line()
    assert first == ("ok" if not ok.warnings else "부분"), ok.status_line()

    path, bad = panelwork.save_moderator_result("nope", rep, base=base)
    assert path is None and not bad.success
    assert bad.status_line().startswith("실패 "), bad.status_line()
    # 사유가 괄호 안에 붙는다.
    assert "(" in bad.status_line() and ")" in bad.status_line()


def test_f3_reason_is_always_given():
    """조용히 비지 않는다 — 실패에는 언제나 사유가 붙는다 (§1-6-1)."""
    base, rep = scratch(), demo_report()
    for text in ("", "nope", "{}", "[]"):
        path, out = panelwork.save_moderator_result(text, rep, base=base)
        assert path is None
        assert out.errors, text
        assert all(i.message for i in out.errors), text


def main() -> int:
    print("Phase 6-F-4 — 3단계 결과 보관 · [4] 연결 · 워크플로 상태")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 1 if _FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
