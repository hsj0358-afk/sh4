"""패널 오프라인 재생 — tools/replay_panel.py (§1-63).

실제 모델을 부르지 않는다 — 가짜 에이전트로 A → B → C 를 끝까지 돌리고,
운영 자리(panel_work/·panel_results/·reports/)에 아무것도 생기지 않는지 본다.

    python tests/test_panel_replay.py
"""
from __future__ import annotations

import ast
import csv
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import replay_panel as R                                    # noqa: E402
from toto import artifact, panel, panelauto, panelwork, roundlog  # noqa: E402
from toto.models import Report                              # noqa: E402

import tests.test_panel_auto as PA                          # noqa: E402

A, B, C = R.A, R.B, R.C


def tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="toto_replay_test_"))


def demo_report(rid="990001", n=3) -> Report:
    report = Report(round_id=rid)
    report.matches = PA.demo_matches(n)
    return report


def repo_untouched(rid: str) -> bool:
    return not (ROOT / panelwork.WORK_DIRNAME / rid).exists() \
        and not (ROOT / "reports" / f"panel_{rid}").exists() \
        and not (ROOT / "panel_results" / f"{rid}_panel_result.json").exists()


# ==========================================================================
# A. 안 — 운영 프롬프트 위의 치환
# ==========================================================================
def test_a1_every_variant_fits_production_prompts():
    for name in R.VARIANTS:
        assert R.check_variant(name) == [], name


def test_a2_baseline_is_exactly_the_production_system():
    """baseline 은 운영이 실제로 넘기는 시스템 프롬프트와 글자까지 같다."""
    for stage in R.STAGES:
        ws = tmp()
        want = panelauto.stage_system(ws, stage)
        assert R.system_for(stage, "baseline") == want, stage
        shutil.rmtree(ws, ignore_errors=True)


def test_a3_v1_only_adds_text_and_touches_the_intended_stages():
    for stage in R.STAGES:
        base = R.system_for(stage, "baseline")
        v1 = R.system_for(stage, "v1")
        assert v1 != base, stage
    # 분석가 둘은 같은 공통 문단을 받는다 — 역할 차이는 역할 규칙뿐이다.
    a_common, a_role = R.prompt_parts(A, "v1")
    b_common, b_role = R.prompt_parts(B, "v1")
    assert a_common == b_common
    assert a_role == panel.ROLE_PROMPTS[A] and b_role == panel.ROLE_PROMPTS[B]
    # 공통 문단은 끼워 넣기만 한다 — 원래 글자가 그대로 남는다.
    base_common = panel.SYSTEM_COMMON
    assert a_common.replace(R._V1_SCORE_RULES, "") == base_common


def test_a4_missing_anchor_refuses_instead_of_silently_skipping():
    saved = dict(R.VARIANTS)
    try:
        R.VARIANTS["broken"] = (R.Edit((A,), "common", "없는 문구 ZZZ", "x"),)
        problems = R.check_variant("broken")
        assert problems and "1번이어야" in problems[0], problems
        R.VARIANTS["twice"] = (R.Edit((A,), "common", "\n", "x"),)
        assert R.check_variant("twice")
    finally:
        R.VARIANTS.clear()
        R.VARIANTS.update(saved)


def test_a5_moderator_has_no_separate_common_part():
    saved = dict(R.VARIANTS)
    try:
        R.VARIANTS["bad"] = (R.Edit((C,), "common", "payload", "x"),)
        assert R.check_variant("bad")
    finally:
        R.VARIANTS.clear()
        R.VARIANTS.update(saved)


def test_a6_unknown_variant_is_refused():
    assert R.check_variant("nope")


def test_a7_v1_does_not_invent_numbers_or_outcomes():
    """안이 새 확률·공식을 요구하거나 승무패를 말하지 않는다 (§1-3·§1-9)."""
    text = R._V1_SCORE_RULES + R._V1_ROUNDS_NEW + R._V1_CHOOSE_RULE
    for word in ("확률을 계산", "%", "홈승", "원정승", "추천", "베팅", "픽"):
        assert word not in text, word


def test_a8_production_prompts_and_versions_are_unchanged():
    """재생은 운영 프롬프트를 바꾸지 않는다 — 판 번호·지침 지문 그대로."""
    assert panel.PANEL_PROMPT_VERSION == "5"
    from toto import moderator, panelexport
    assert moderator.MODERATOR_PROMPT_VERSION == "6"
    assert R._V1_SCORE_RULES not in panel.SYSTEM_COMMON
    assert panelexport.instructions_fingerprint() == "71163a6f"


# ==========================================================================
# B. 운영 함수의 분리 — 동작이 그대로다
# ==========================================================================
def test_b1_stage_system_is_join_of_prompt_texts():
    for stage in R.STAGES:
        ws = tmp()
        common, role = panelauto.prompt_texts(stage)
        assert panelauto.stage_system(ws, stage) == \
            panelauto.join_system(stage, common, role)
        shutil.rmtree(ws, ignore_errors=True)


def test_b2_pack_moderator_data_default_sheet_dir_is_unchanged():
    src = ast.get_source_segment(
        Path(panelauto.__file__).read_text(encoding="utf-8"),
        next(n for n in ast.walk(ast.parse(
            Path(panelauto.__file__).read_text(encoding="utf-8")))
            if isinstance(n, ast.FunctionDef)
            and n.name == "pack_moderator_data"))
    assert "panelexport.round_dir(round_id)" in src


# ==========================================================================
# C. 자리 — 저장소 밖, 사후 스냅샷 거부
# ==========================================================================
def test_c1_out_inside_repo_is_refused():
    code = R.main(["run", "--rounds", "260054", "--variant", "baseline",
                   "--out", str(ROOT / "replay_here")])
    assert code == R.EXIT_REFUSED
    assert not (ROOT / "replay_here").exists()


def test_c2_default_root_is_outside_repo():
    old = os.environ.pop(R.REPLAY_ENV, None)
    try:
        assert not R.inside_repo(R.replay_root())
    finally:
        if old is not None:
            os.environ[R.REPLAY_ENV] = old


def _write_artifact(dir_: Path, report: Report, saved_at: str) -> None:
    data = artifact.to_dict(report)
    data["saved_at"] = saved_at
    path = artifact.path_for(report.round_id, dir_)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_c3_postmatch_snapshot_is_refused():
    d = tmp()
    report = demo_report("990002")
    first = min(m.kickoff_kst for m in report.matches)
    after = (datetime.strptime(first, "%Y-%m-%d %H:%M")
             .replace(year=2026)).strftime("%Y-%m-%d %H:%M")
    _write_artifact(d, report, after)          # 첫 킥오프와 같은 시각 = 사후
    got, why = R.load_round("990002", d)
    assert got is None and "킥오프 뒤" in why, why


def test_c4_prematch_snapshot_loads():
    d = tmp()
    report = demo_report("990003")
    _write_artifact(d, report, "2026-08-01 09:00")
    got, why = R.load_round("990003", d)
    assert got is not None and why == "", why
    assert len(got.matches) == len(report.matches)


def test_c5_missing_saved_at_is_refused():
    d = tmp()
    report = demo_report("990004")
    _write_artifact(d, report, "")
    got, why = R.load_round("990004", d)
    assert got is None and "saved_at" in why


# ==========================================================================
# D. 실행 — 가짜 에이전트로 끝까지
# ==========================================================================
def _run(report, variant="v1", root=None, record=None, fake=None):
    root = root or tmp()
    record = record if record is not None else []
    with PA.patched(run_agent=fake or PA.make_fake(report, record)):
        summary = R.run_round(report, variant, None, root=root, model="sonnet",
                              cli="", echo=lambda *_: None)
    return summary, root, record


def test_d1_full_round_writes_only_under_replay_root():
    report = demo_report("990010")
    summary, root, record = _run(report)
    assert [r["stage"] for r in record] == [A, B, C]
    assert summary["assembled_ok"], summary["assemble_issues"]
    assert (R.round_base(root, "v1", "990010") / R.RESULT_FILE).is_file()
    assert repo_untouched("990010")
    assert set(summary["scores"]) == {"1", "2", "3"}
    assert summary["scores"]["1"] == {"a": [2, 1], "b": [2, 1], "c": [1, 1]}


def test_d2_a_and_b_get_the_same_packet_c_gets_moderator_data():
    report = demo_report("990011")
    _s, _root, record = _run(report)
    a, b, c = record
    assert a["stdin"] == b["stdin"] and a["stdin"]
    assert panelauto.MODERATOR_TAG in c["stdin"]
    assert "<panel_payload" not in c["stdin"]


def test_d3_variant_system_is_what_the_agent_received():
    report = demo_report("990012")
    summary, _root, record = _run(report)
    for row in record:
        assert row["system"] == R.system_for(row["stage"], "v1")
    assert R._V1_SCORE_RULES.strip() in record[0]["system"]
    assert "번갈아" in record[2]["system"]
    assert summary["system_sha256"]["a"] != summary["system_sha256"]["c"]


def test_d4_second_run_reuses_finished_stages():
    report = demo_report("990013")
    _s, root, _rec = _run(report)
    record = []
    summary, _r, record = _run(report, root=root, record=record)
    assert record == []
    assert all(s.get("reused") for s in summary["stages"].values())


def test_d5_usage_limit_stops_and_resume_runs_only_the_rest():
    report = demo_report("990014")
    good = PA.make_fake(report, [])
    calls = []

    def limited(prompt, system, workspace, **kw):
        calls.append(system)
        if "맞대결" in system and "분석가" in system and \
                panelauto.MODERATOR_TAG not in kw.get("stdin_text", ""):
            return panelauto.AgentRun(status=panelauto.AGENT_USAGE_LIMIT,
                                      message="You've hit your weekly limit")
        return good(prompt, system, workspace, **kw)

    root = tmp()
    try:
        _run(report, root=root, fake=limited)
    except R.StopReplay as stop:
        assert stop.code == R.EXIT_LIMIT
    else:
        raise AssertionError("한도에서 멈추지 않았다")
    assert panelwork.path_for("990014", A, R.round_base(root, "v1",
                                                         "990014")).is_file()
    record = []
    _s, _r, record = _run(report, root=root, record=record)
    assert [r["stage"] for r in record] == [B, C]


def test_d6_invalid_output_is_not_saved():
    report = demo_report("990015")

    def bad(prompt, system, workspace, **kw):
        Path(workspace).mkdir(parents=True, exist_ok=True)
        return panelauto.AgentRun(status=panelauto.AGENT_OK, text="[]")

    root = tmp()
    try:
        _run(report, root=root, fake=bad)
    except R.StopReplay as stop:
        assert stop.code == R.EXIT_FAIL and "검증 실패" in str(stop)
    else:
        raise AssertionError("빈 배열을 통과시켰다")
    assert not panelwork.path_for("990015", A, R.round_base(
        root, "v1", "990015")).is_file()


def test_d7_tool_never_calls_production_writers():
    tree = ast.parse(Path(R.__file__).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    for bad in ("run_existing_cli", "write_canonical", "record_applied",
                "_run_stage", "run_stage_analyst", "run_stage_moderator",
                "anthropic"):
        assert bad not in names, bad


def test_d8_every_panelwork_writer_gets_a_base():
    """보관·조립 함수에는 언제나 재생 폴더(base)를 넘긴다 — 기본값은 운영 자리다."""
    tree = ast.parse(Path(R.__file__).read_text(encoding="utf-8"))
    need = {"save_stage": 4, "save_moderator_result": 4,
            "build_completed_sheet": 3, "assemble_panel_result": 3,
            "load_stage": 4}
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in need:
            seen.add(node.func.attr)
            assert len(node.args) >= need[node.func.attr], node.func.attr
    assert seen == set(need), seen


# ==========================================================================
# E. 점수 — 정확 스코어 적중
# ==========================================================================
def _write_actual(path: Path, rid: str, scores: dict) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=roundlog.MATCH_FIELDS)
        w.writeheader()
        for no, (h, a) in scores.items():
            w.writerow({"round": rid, "no": no, "home_goals": h,
                        "away_goals": a})


def _write_stage(base: Path, rid: str, role: str, rows) -> None:
    path = panelwork.path_for(rid, role, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows), encoding="utf-8")


def test_e1_counts_exact_hits_and_changes():
    rid = "990020"
    root, stored, d = tmp(), tmp(), tmp()
    actual = d / "round_matches.csv"
    _write_actual(actual, rid, {1: (1, 0), 2: (1, 1), 3: (2, 2)})
    _write_stage(stored, rid, A, [
        {"match_no": 1, "predicted_home": 2, "predicted_away": 1},
        {"match_no": 2, "predicted_home": 1, "predicted_away": 1},
        {"match_no": 3, "predicted_home": None, "predicted_away": None}])
    path = panelwork.moderator_result_path(rid, stored)
    path.write_text(json.dumps([
        {"match_no": 1, "adopted_home": 2, "adopted_away": 1},
        {"match_no": 2, "adopted_home": 1, "adopted_away": 1},
        {"match_no": 3, "adopted_home": 1, "adopted_away": 1}]),
        encoding="utf-8")
    rep = R.round_base(root, "v1", rid)
    rep.mkdir(parents=True)
    (rep / R.RESULT_FILE).write_text(json.dumps({"scores": {
        "1": {"a": [1, 0], "b": [1, 0], "c": [1, 0]},
        "2": {"a": [1, 1], "b": [0, 1], "c": [1, 1]},
        "3": {"a": [1, 1], "b": [1, 1], "c": [1, 1]}},
        "packet_sha256": "abc"}), encoding="utf-8")
    got = R.score([rid], ["v1"], root, actual_path=actual, stored_base=stored)
    s, v = got["table"]["stored"], got["table"]["v1"]
    assert s["n"] == 3 and s["hits"] == {"a": 1, "b": 0, "c": 1}
    assert s["missing"]["a"] == 1 and s["missing"]["b"] == 3
    assert v["hits"] == {"a": 2, "b": 1, "c": 2}
    assert v["changed_c_vs_stored"] == 1 and v["compared_c"] == 3
    lines = R.score_lines(got)
    assert any(line.startswith("v1") for line in lines)


def test_e2_unsettled_matches_are_not_counted():
    rid = "990021"
    root, d = tmp(), tmp()
    actual = d / "round_matches.csv"
    with actual.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=roundlog.MATCH_FIELDS)
        w.writeheader()
        w.writerow({"round": rid, "no": 1, "home_goals": "",
                    "away_goals": ""})
        w.writerow({"round": "other", "no": 1, "home_goals": 1,
                    "away_goals": 0})
    got = R.score([rid], [], root, actual_path=actual, stored_base=tmp())
    assert got["table"]["stored"]["n"] == 0


def test_e3_score_reads_only():
    """점수는 읽기만 한다 — 운영 자리를 만들지 않는다."""
    rid = "990022"
    R.score([rid], ["v1"], tmp(), actual_path=tmp() / "none.csv")
    assert repo_untouched(rid)


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    raise SystemExit(main())
