"""3세션 자동화의 중단·재개와 A/B/C 출처 감사 (Phase 6-F-12 · §1-48).

6-F-6 이 자동 실행을 만들면서 재개 판정을 `panelwork.workflow()` 에
맡겼는데, 그 함수가 보는 것은 **파일이 있느냐** 하나였다. 사람이 화면에서
진행 상태를 볼 때는 그것으로 충분하지만, 같은 판정이 **다음 단계에 돈을
쓸지**를 정하기 시작하면 두 가지가 조용히 지나간다.

  · 손으로 고쳐졌거나 잘린 보관본이 '완료' 로 읽힌다. 뒤늦게 조립·반영
    단계에서 터지는데, 그때는 이미 다음 단계에 돈을 쓴 뒤다.
  · **출처가 다른** 보관본이 그대로 재사용된다. 회차를 다시 수집하면
    순위표·배당이 달라지는데(§1-1-7), 옛 A·B 를 그대로 두고 새 자료로
    만든 사회자 시트에 C 를 돌리면 한 회차 안에 두 시점이 섞인다.

이 스위트가 지키는 것 여섯이다.

  1. **다섯 문** — 있나 · 읽히나 · JSON 인가 · 기존 검증기를 지나나 ·
     출처가 맞나. `.tmp` 는 어느 문에도 닿지 않는다
  2. **`unverified` 는 어긋난 것이 아니다** — 기록이 없는 체크포인트(수동
     경로·옛 파일)는 그대로 쓴다. 그러지 않으면 멀쩡한 것이 전부 무효가
     된다 (§1-6 의 `unknown` ≠ `실패`)
  3. **의존성이 아래로 흐른다** — source → packet → A·B → 시트 → C → 반영
  4. **출처가 남는다** — A·B 가 같은 packet 을 받았고 프롬프트만 달랐다는
     사실이 파일로 확인된다
  5. **실패가 성공을 덮지 않는다** — 실패는 `last_attempt` 로 가고 앞서
     저장한 체크포인트는 그대로다
  6. **범위** — 세션 3회 · A·B 같은 stdin · 프롬프트 판 · schema 1.1 ·
     새 DB 없음 · LLM 재설명 단계 없음

**실제 모델을 부르지 않는다.** 시나리오는 전부 가짜 에이전트로 돌리고
(6-F-6 이 만든 harness 를 그대로 쓴다), 저장소의 `panel_work/` 는 한
글자도 건드리지 않는다 — 임시 폴더에서만 돈다 (§26·§27·§34).
"""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import moderator, panel, panelauto, panelimport   # noqa: E402
from toto import panelpacket, panelwork                     # noqa: E402

# **harness 를 두 벌 만들지 않는다** (§1-8). 6-F-6 이 만든 가짜 에이전트·
# 가짜 CLI·데모 회차를 그대로 쓴다 — 테스트가 같은 조건에서 돈다.
from test_panel_auto import (                               # noqa: E402
    FakeReport, code_of, fn_node, make_fake, module_code, moderator_array,
    patched, scratch, source_of, stage_array)

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
# 도구 — 저장소를 건드리지 않는 회차 하나
# ==========================================================================
class Round:
    """임시 폴더 위의 회차 하나. `panel_work/`·`reports/` 를 흉내낸다."""

    def __init__(self, n=3, round_id="RESUME"):
        self.report = FakeReport(n, round_id)
        self.base = scratch()
        self.sheet = self.base / "export"
        self.sheet.mkdir(parents=True, exist_ok=True)

    # ---- 씨앗 --------------------------------------------------------
    def seed_a(self):
        return panelwork.save_stage(stage_array(self.report),
                                    panel.DATA_ANALYST, self.report,
                                    self.base)

    def seed_b(self):
        return panelwork.save_stage(stage_array(self.report),
                                    panel.MATCHUP_ANALYST, self.report,
                                    self.base)

    def seed_sheet(self):
        return panelwork.build_completed_sheet(self.report, None, self.base,
                                               outdir=self.sheet)

    def seed_c(self):
        return panelwork.save_moderator_result(moderator_array(self.report),
                                               self.report, None, self.base)

    def seed_all(self):
        self.seed_a()
        self.seed_b()
        self.seed_sheet()
        self.seed_c()

    # ---- 읽기 --------------------------------------------------------
    def path(self, stage):
        return panelwork.checkpoint_path(self.report.round_id, stage,
                                         self.base, self.sheet)

    def cp(self, stage, expect=None):
        return panelwork.checkpoint_state(self.report.round_id, stage,
                                          self.report, self.base, self.sheet,
                                          expect)

    def plan(self, expect=None):
        return panelwork.resume_plan(self.report, self.report.round_id,
                                     self.base, self.sheet, expect)

    def manifest(self):
        return panelwork.read_manifest(self.report.round_id, self.base)

    def row(self, stage):
        return panelwork.stage_record(self.report.round_id, stage, self.base)


def fake_cli(rnd: Round):
    """`run_existing_cli` 대역. **검증기는 진짜**, 저장 자리만 임시 폴더."""
    report, base, sheet = rnd.report, rnd.base, rnd.sheet

    def run(argv):
        argv = list(argv)
        if "--save-panel-opinion" in argv:
            path = Path(argv[argv.index("--save-panel-opinion") + 1])
            role = argv[argv.index("--role") + 1]
            res = panelwork.save_stage(path.read_text(encoding="utf-8"),
                                       role, report, base)
            return 0 if res.success else 1
        if "--build-moderator-input" in argv:
            res = panelwork.build_completed_sheet(report, None, base,
                                                  outdir=sheet)
            return 0 if res.success else 1
        if "--save-moderator-result" in argv:
            path = Path(argv[argv.index("--save-moderator-result") + 1])
            saved, _res = panelwork.save_moderator_result(
                path.read_text(encoding="utf-8"), report, None, base)
            return 0 if saved is not None else 1
        if "--paste-panel-result" in argv:
            return 0
        raise AssertionError(f"모르는 CLI 호출: {argv}")
    return run


def breaking_fake(rnd: Round, stage_to_fail, status, record=None,
                  message="주입한 실패"):
    """한 단계만 실패시키는 가짜 에이전트. 나머지는 정상으로 돈다."""
    good = make_fake(rnd.report, record)

    def fake(prompt, system, workspace, **kw):
        run = good(prompt, system, workspace, **kw)
        is_mod = panelauto.MODERATOR_TAG in kw.get("stdin_text", "")
        stage = (panelauto.MODERATOR_DIR if is_mod
                 else (panel.MATCHUP_ANALYST if "맞대결" in system
                       else panel.DATA_ANALYST))
        if stage == stage_to_fail:
            return panelauto.AgentRun(status=status, message=message,
                                      session_id=run.session_id)
        return run
    return fake


def go(rnd: Round, agent=None, echo=None):
    """가짜로 끝까지 돌린다. **돈이 들지 않는다.** (결과, 호출목록)."""
    calls = []
    fake = agent(calls) if agent is not None else make_fake(rnd.report, calls)
    lines = [] if echo is None else echo
    os.environ[panelauto.AUTO_ENV] = str(rnd.base / "auto")
    try:
        with patched(run_agent=fake, cli="/bin/true",
                     existing_cli=fake_cli(rnd), sheet_dir=rnd.sheet):
            out = panelauto.run(rnd.report.round_id, rnd.report,
                                base=rnd.base, echo=lines.append)
    finally:
        os.environ.pop(panelauto.AUTO_ENV, None)
    return out, calls


def stages_called(calls):
    return [c["stage"] for c in calls]


# ==========================================================================
# A. 다섯 문 — 있다 ≠ 쓸 수 있다
# ==========================================================================
def test_a1_missing_checkpoint_is_missing():
    rnd = Round()
    cp = rnd.cp(panelwork.STAGE_A)
    assert cp.state == panelwork.CP_MISSING
    assert not cp.usable and not cp.exists
    assert rnd.plan().resume_from == panelwork.STAGE_A


def test_a2_valid_but_unrecorded_is_usable():
    """수동 경로·옛 파일은 **어긋난 것이 아니다** (§13)."""
    rnd = Round()
    rnd.seed_a()
    # 저장이 남긴 기록을 지워 '6-F-12 이전 파일' 을 만든다.
    panelwork.manifest_path(rnd.report.round_id, rnd.base).unlink()
    cp = rnd.cp(panelwork.STAGE_A)
    assert cp.state == panelwork.CP_UNVERIFIED, cp.reasons
    assert cp.usable, "기록이 없다고 멀쩡한 체크포인트를 버렸다"
    assert cp.matches == len(rnd.report.matches)
    assert any("출처 기록이 없습니다" in r for r in cp.reasons)


def test_a3_a_tmp_file_is_not_a_checkpoint():
    """쓰다 만 파일은 체크포인트가 아니다 (§5)."""
    rnd = Round()
    rnd.seed_a()
    real = rnd.path(panelwork.STAGE_A)
    body = real.read_text(encoding="utf-8")
    real.unlink()
    real.with_name(real.name + ".tmp").write_text(body, encoding="utf-8")
    cp = rnd.cp(panelwork.STAGE_A)
    assert cp.state == panelwork.CP_MISSING, cp.state
    # 경로 자체가 `.tmp` 를 가리키지 않는다.
    for stage in panelwork.STAGE_ORDER:
        assert not str(rnd.path(stage)).endswith(".tmp"), stage


def test_a4_broken_json_is_invalid():
    rnd = Round()
    rnd.seed_a()
    rnd.path(panelwork.STAGE_A).write_text("{ not json", encoding="utf-8")
    cp = rnd.cp(panelwork.STAGE_A)
    assert cp.state == panelwork.CP_INVALID, cp.state
    assert not cp.usable
    assert any("JSON" in r for r in cp.reasons), cp.reasons


def test_a5_partial_round_is_invalid():
    """경기가 모자라면 완료가 아니다 (§7)."""
    rnd = Round()
    rnd.seed_a()
    path = rnd.path(panelwork.STAGE_A)
    rows = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(rows[:1], ensure_ascii=False),
                    encoding="utf-8")
    cp = rnd.cp(panelwork.STAGE_A)
    assert cp.state == panelwork.CP_INVALID, cp.state
    assert any("경기" in r for r in cp.reasons), cp.reasons


def test_a6_unknown_match_no_is_invalid():
    rnd = Round()
    rnd.seed_a()
    path = rnd.path(panelwork.STAGE_A)
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows[0][panelwork.STAGE_NO] = 99
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    assert rnd.cp(panelwork.STAGE_A).state == panelwork.CP_INVALID


def test_a7_foreign_evidence_id_is_invalid():
    """근거 ID 는 **그 경기의 것**이어야 한다 — 새로 만들지 않는다 (§24)."""
    rnd = Round()
    rnd.seed_a()
    path = rnd.path(panelwork.STAGE_A)
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows[0]["evidence_ids"] = ["E999"]
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    cp = rnd.cp(panelwork.STAGE_A)
    assert cp.state == panelwork.CP_INVALID, cp.state


def test_a8_unreadable_file_is_not_complete():
    rnd = Round()
    rnd.seed_a()
    rnd.path(panelwork.STAGE_A).write_bytes(b"\xff\xfe\x00broken")
    cp = rnd.cp(panelwork.STAGE_A)
    assert cp.state in (panelwork.CP_UNREADABLE, panelwork.CP_INVALID)
    assert not cp.usable


def test_a9_five_checkpoint_paths_live_in_one_place():
    """다섯 자리를 한 함수가 정한다 (§1-8)."""
    rnd = Round()
    seen = {stage: rnd.path(stage) for stage in panelwork.STAGE_ORDER}
    assert len(set(map(str, seen.values()))) == 5, seen
    assert seen[panelwork.STAGE_A].name == "analyst_a.json"
    assert seen[panelwork.STAGE_B].name == "analyst_b.json"
    assert seen[panelwork.STAGE_RESULT].name == "moderator_result.json"
    assert seen[panelwork.STAGE_INPUT].name == panelwork.COMPLETED_SHEET
    assert seen[panelwork.STAGE_APPLY].name.endswith(panelimport.FILE_SUFFIX)


def test_a10_workflow_without_a_report_is_unchanged():
    """회차 자료 없이도 부를 수 있다 — 6-F-4 의 계약 그대로 (§1-41)."""
    rnd = Round()
    rnd.seed_a()
    wf = panelwork.workflow(rnd.report.round_id, rnd.base, rnd.sheet)
    a = wf.stage(panelwork.STAGE_A)
    assert a.done and a.state == panelwork.A_COMPLETE
    assert a.checkpoint is None, "report 없이 내용을 확인한 척했다"
    # 그 경로는 artifact 도 네트워크도 필요로 하지 않는다.
    body = code_of(fn_node(panelwork, "workflow"))
    assert "artifact" not in body


def test_a11_report_upgrades_workflow_to_verification():
    rnd = Round()
    rnd.seed_a()
    rnd.path(panelwork.STAGE_A).write_text("[]", encoding="utf-8")
    wf = panelwork.workflow(rnd.report.round_id, rnd.base, rnd.sheet,
                            report=rnd.report)
    a = wf.stage(panelwork.STAGE_A)
    assert not a.done, "깨진 파일이 완료로 남았다"
    assert a.state == panelwork.CHECKPOINT_INVALID, a.state
    assert a.detail, "사유를 적지 않았다"


# ==========================================================================
# B. 출처 — 무엇으로 만들어졌나
# ==========================================================================
def test_b1_manifest_records_what_was_saved():
    rnd = Round()
    rnd.seed_a()
    row = rnd.row(panelwork.STAGE_A)
    assert row["stage"] == panelwork.STAGE_A
    assert row["matches"] == len(rnd.report.matches)
    assert row["sha256"] == panelwork._file_sha(rnd.path(panelwork.STAGE_A))
    assert row["created_at"] and row["created_at"].endswith("+00:00")
    assert row["panel_prompt_version"] == panel.PANEL_PROMPT_VERSION
    assert row["status"] == panelwork.STAGE_COMPLETE
    data = rnd.manifest()
    assert data["manifest_version"] == panelwork.MANIFEST_VERSION
    assert data["round"] == rnd.report.round_id


def test_b2_auto_run_records_packet_and_session():
    """자동 경로가 **아는 것**을 합쳐 적는다 (§9·§10)."""
    rnd = Round()
    out, calls = go(rnd)
    assert out.ok, out.stopped_reason
    for stage in (panelwork.STAGE_A, panelwork.STAGE_B):
        row = rnd.row(stage)
        assert row["origin"] == "auto", row
        assert row["model"], "모델을 적지 않았다"
        assert row["session_id"], "세션을 적지 않았다"
        assert row["packet_sha256"], "packet 해시를 적지 않았다"
        assert row["packet_version"] == panelpacket.PACKET_VERSION
        assert row["source_sha256_16"], "source 해시를 적지 않았다"
        assert row["system_sha256"] and row["stdin_sha256"]


def test_b3_ab_shared_the_packet_and_differed_only_in_prompt():
    """§1-9 불변조건 2 가 **파일로** 확인된다 (§11)."""
    rnd = Round()
    out, calls = go(rnd)
    assert out.ok, out.stopped_reason
    a = rnd.row(panelwork.STAGE_A)
    b = rnd.row(panelwork.STAGE_B)
    assert a["packet_sha256"] == b["packet_sha256"], "packet 이 갈렸다"
    assert a["stdin_sha256"] == b["stdin_sha256"], "stdin 이 갈렸다"
    assert a["system_sha256"] != b["system_sha256"], "역할 프롬프트가 같다"
    assert a["session_id"] != b["session_id"], "세션이 같다"


def test_b4_moderator_records_its_inputs():
    """C 는 A·B·시트와 사회자 프롬프트 판을 기록한다 (§11)."""
    rnd = Round()
    out, _calls = go(rnd)
    assert out.ok, out.stopped_reason
    row = rnd.row(panelwork.STAGE_RESULT)
    dep = row["depends"]
    assert dep[panelwork.STAGE_A] == \
        panelwork._file_sha(rnd.path(panelwork.STAGE_A))
    assert dep[panelwork.STAGE_B] == \
        panelwork._file_sha(rnd.path(panelwork.STAGE_B))
    assert dep[panelwork.STAGE_INPUT] == \
        panelwork._file_sha(rnd.path(panelwork.STAGE_INPUT))
    assert row["moderator_prompt_version"] == \
        moderator.MODERATOR_PROMPT_VERSION


def test_b5_sheet_records_what_it_consumed():
    rnd = Round()
    rnd.seed_a()
    rnd.seed_b()
    rnd.seed_sheet()
    dep = rnd.row(panelwork.STAGE_INPUT)["depends"]
    for stage in (panelwork.STAGE_A, panelwork.STAGE_B):
        assert dep[stage] == panelwork._file_sha(rnd.path(stage)), stage
    assert rnd.row(panelwork.STAGE_INPUT)["sha256"] == \
        panelwork._file_sha(rnd.path(panelwork.STAGE_INPUT))


def test_b6_failure_goes_to_last_attempt_not_over_the_checkpoint():
    """실패가 **성공을 덮지 않는다** (§17·§20)."""
    rnd = Round()
    out, _ = go(rnd)
    assert out.ok
    before = rnd.row(panelwork.STAGE_A)
    kept = rnd.path(panelwork.STAGE_A).read_text(encoding="utf-8")

    # 같은 회차를 다시 돌리되 A 를 stale 로 만들어 재실행시키고 실패시킨다.
    panelwork.record_stage(rnd.report.round_id, panelwork.STAGE_A, rnd.base,
                           packet_sha256="달라진-packet")
    out2, calls = go(rnd, agent=lambda rec: breaking_fake(
        rnd, panel.DATA_ANALYST, panelauto.AGENT_FAILED, rec))
    assert not out2.ok
    after = rnd.row(panelwork.STAGE_A)
    assert after["sha256"] == before["sha256"], "실패가 해시를 덮었다"
    assert after["status"] == panelwork.STAGE_COMPLETE, "상태를 덮었다"
    assert after["last_attempt"]["status"] == panelwork.STAGE_FAILED
    assert rnd.path(panelwork.STAGE_A).read_text(encoding="utf-8") == kept


def test_b7_usage_limit_is_its_own_attempt_status():
    """한도는 그냥 실패가 아니다 — 할 일이 다르다 (§17)."""
    rnd = Round()
    out, _ = go(rnd, agent=lambda rec: breaking_fake(
        rnd, panel.DATA_ANALYST, panelauto.AGENT_USAGE_LIMIT, rec))
    assert not out.ok
    assert out.stopped_reason == panelauto.WORKFLOW_STOPPED_USAGE_LIMIT
    row = rnd.row(panelwork.STAGE_A)
    assert row["last_attempt"]["status"] == panelwork.STAGE_FAILED_LIMIT
    assert row["last_attempt"]["agent_status"] == panelauto.AGENT_USAGE_LIMIT


def test_b8_a_failed_attempt_alone_never_promotes_a_checkpoint():
    """실패 기록이 있다고 확인하지 않은 파일이 `complete` 가 되지 않는다."""
    rnd = Round()
    rnd.seed_a()
    panelwork.manifest_path(rnd.report.round_id, rnd.base).unlink()
    panelwork.record_stage(rnd.report.round_id, panelwork.STAGE_A, rnd.base,
                           last_attempt={"status": panelwork.STAGE_FAILED})
    cp = rnd.cp(panelwork.STAGE_A)
    assert cp.state == panelwork.CP_UNVERIFIED, cp.state
    assert cp.usable


def test_b9_manifest_version_mismatch_is_not_read():
    """판이 다르면 읽지 않는다 — 조용히 다르게 해석하지 않는다 (§1-16)."""
    rnd = Round()
    rnd.seed_a()
    path = panelwork.manifest_path(rnd.report.round_id, rnd.base)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["manifest_version"] = "999"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert panelwork.read_manifest(rnd.report.round_id, rnd.base) == {}
    assert rnd.cp(panelwork.STAGE_A).state == panelwork.CP_UNVERIFIED


def test_b10_broken_manifest_does_not_break_the_round():
    rnd = Round()
    rnd.seed_a()
    panelwork.manifest_path(rnd.report.round_id,
                            rnd.base).write_text("{ broken",
                                                 encoding="utf-8")
    assert panelwork.read_manifest(rnd.report.round_id, rnd.base) == {}
    assert rnd.cp(panelwork.STAGE_A).usable, "매니페스트가 깨져 회차가 죽었다"


def test_b11_checkpoint_files_carry_no_metadata():
    """보관본은 **모델이 돌려준 배열 그대로**다 — 메타를 섞지 않는다 (§8)."""
    rnd = Round()
    out, _ = go(rnd)
    assert out.ok
    for stage in (panelwork.STAGE_A, panelwork.STAGE_B,
                  panelwork.STAGE_RESULT):
        rows = json.loads(rnd.path(stage).read_text(encoding="utf-8"))
        assert isinstance(rows, list), stage
        for row in rows:
            for bad in ("packet_sha256", "source_sha256_16", "session_id",
                        "origin", "provenance", "manifest_version"):
                assert bad not in row, f"{stage} 보관본에 {bad}"


def test_b12_manifest_holds_data_not_interpretation():
    """출처이지 분석이 아니다 — 모델 문장을 담지 않는다 (§25)."""
    rnd = Round()
    out, _ = go(rnd)
    assert out.ok
    text = panelwork.manifest_path(rnd.report.round_id,
                                   rnd.base).read_text(encoding="utf-8")
    for bad in ("summary", "rationale", "conclusion", "distribution",
                "predicted_home", "adopted_home", "recommendation",
                "confidence"):
        assert bad not in text, f"매니페스트에 {bad} 가 있다"


# ==========================================================================
# C. 무효화 — 의존성이 아래로 흐른다
# ==========================================================================
def _expect(rnd: Round, **over):
    idx = panelpacket.build_panel_index(rnd.report)
    body = panelpacket.packet_text(panelpacket.build_compact_packet(idx))
    out = dict(panelpacket.source_manifest(idx))
    out["packet_sha256"] = panelpacket.packet_digest(body)
    out["packet_version"] = panelpacket.PACKET_VERSION
    out["moderator_prompt_version"] = moderator.MODERATOR_PROMPT_VERSION
    out.update(over)
    return out


def test_c1_a_changed_packet_makes_a_and_b_stale():
    rnd = Round()
    rnd.seed_all()
    for stage in (panelwork.STAGE_A, panelwork.STAGE_B):
        panelwork.record_stage(rnd.report.round_id, stage, rnd.base,
                               packet_sha256="옛-packet",
                               source_sha256_16="옛source",
                               packet_version=panelpacket.PACKET_VERSION)
    plan = rnd.plan(_expect(rnd))
    assert plan.resume_from == panelwork.STAGE_A
    for stage in (panelwork.STAGE_A, panelwork.STAGE_B):
        row = plan.plan(stage)
        assert not row.reuse and row.checkpoint.state == panelwork.CP_STALE
        assert "packet_sha256" in row.reason, row.reason


def test_c2_a_changed_source_makes_a_and_b_stale():
    rnd = Round()
    rnd.seed_all()
    exp = _expect(rnd)
    for stage in (panelwork.STAGE_A, panelwork.STAGE_B):
        panelwork.record_stage(rnd.report.round_id, stage, rnd.base,
                               packet_sha256=exp["packet_sha256"],
                               source_sha256_16="다른source")
    plan = rnd.plan(exp)
    assert not plan.reuse(panelwork.STAGE_A)
    assert "source_sha256_16" in plan.plan(panelwork.STAGE_A).reason


def test_c3_a_changed_panel_prompt_makes_a_and_b_stale():
    rnd = Round()
    rnd.seed_all()
    plan = rnd.plan(_expect(rnd, panel_prompt_version="999"))
    assert not plan.reuse(panelwork.STAGE_A)
    assert "panel_prompt_version" in plan.plan(panelwork.STAGE_A).reason


def test_c4_a_changed_moderator_prompt_makes_c_stale():
    rnd = Round()
    rnd.seed_all()
    plan = rnd.plan(_expect(rnd, moderator_prompt_version="999"))
    assert plan.reuse(panelwork.STAGE_A), "A 까지 낡았다고 했다"
    assert plan.reuse(panelwork.STAGE_B)
    assert not plan.reuse(panelwork.STAGE_RESULT)
    assert "moderator_prompt_version" in plan.plan(panelwork.STAGE_RESULT).reason


def test_c5_rebuilding_a_cascades_downstream():
    """source → packet → A·B → 시트 → C → 반영 (§14)."""
    rnd = Round()
    rnd.seed_all()
    rnd.path(panelwork.STAGE_A).write_text("[]", encoding="utf-8")
    plan = rnd.plan(_expect(rnd))
    assert plan.resume_from == panelwork.STAGE_A
    assert plan.reuse(panelwork.STAGE_B), "B 는 A 를 모른다"
    for stage in (panelwork.STAGE_INPUT, panelwork.STAGE_RESULT,
                  panelwork.STAGE_APPLY):
        row = plan.plan(stage)
        assert not row.reuse, stage
        assert "앞 단계" in row.reason, (stage, row.reason)


def test_c6_editing_a_after_the_sheet_makes_the_sheet_stale():
    """시트가 먹은 A 가 바뀌면 시트가 낡는다 — 해시로 드러난다."""
    rnd = Round()
    rnd.seed_a()
    rnd.seed_b()
    rnd.seed_sheet()
    # A 를 **여전히 검증을 지나는** 다른 내용으로 바꾼다.
    path = rnd.path(panelwork.STAGE_A)
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows[0]["summary"] = "사람이 고친 요약"
    panelwork._atomic_write(path, json.dumps(rows, ensure_ascii=False))
    a = rnd.cp(panelwork.STAGE_A)
    assert a.state == panelwork.CP_UNVERIFIED, a.state
    assert a.usable, "사람이 고쳤다고 돈 드는 재실행을 강요했다"
    assert any("바뀌었습니다" in r for r in a.reasons), a.reasons
    plan = rnd.plan(_expect(rnd))
    sheet = plan.plan(panelwork.STAGE_INPUT)
    assert not sheet.reuse, "시트가 옛 A 로 만들어졌는데 재사용했다"


def test_c7_missing_provenance_keys_are_not_questioned():
    """한쪽이 없으면 묻지 않는다 — 없는 것을 불일치로 세지 않는다."""
    rnd = Round()
    rnd.seed_all()
    # 저장 경로가 적은 기록에는 packet 해시가 없다 (수동 경로와 같다).
    row = rnd.row(panelwork.STAGE_A)
    assert "packet_sha256" not in row
    plan = rnd.plan(_expect(rnd))
    assert plan.reuse(panelwork.STAGE_A), plan.plan(panelwork.STAGE_A).reason


def test_c8_matching_provenance_reads_as_complete():
    rnd = Round()
    out, _ = go(rnd)
    assert out.ok
    plan = rnd.plan(_expect(rnd))
    for stage in (panelwork.STAGE_A, panelwork.STAGE_B,
                  panelwork.STAGE_RESULT):
        cp = plan.plan(stage).checkpoint
        assert cp.state == panelwork.CP_COMPLETE, (stage, cp.state, cp.reasons)
        assert cp.verified


def test_c9_upstream_order_is_a_dag_not_a_cycle():
    """A·B 는 서로를 모르고, 위로 거슬러 가지 않는다."""
    assert panelwork.STAGE_UPSTREAM[panelwork.STAGE_A] == ()
    assert panelwork.STAGE_UPSTREAM[panelwork.STAGE_B] == ()
    order = list(panelwork.STAGE_ORDER)
    for stage, ups in panelwork.STAGE_UPSTREAM.items():
        for up in ups:
            assert order.index(up) < order.index(stage), (stage, up)


# ==========================================================================
# D. 재개 시나리오 — 호출 수를 센다 (§33)
# ==========================================================================
def _scenario(seed, expected_stages):
    rnd = Round()
    seed(rnd)
    out, calls = go(rnd)
    assert out.ok, out.stopped_reason
    got = stages_called(calls)
    assert got == expected_stages, f"{got} != {expected_stages}"
    assert out.agent_calls == len(expected_stages), out.agent_calls
    return rnd, out


def test_d1_nothing_done_runs_three_sessions():
    _scenario(lambda r: None,
              [panel.DATA_ANALYST, panel.MATCHUP_ANALYST,
               panelauto.MODERATOR_DIR])


def test_d2_a_done_runs_two():
    _scenario(lambda r: r.seed_a(),
              [panel.MATCHUP_ANALYST, panelauto.MODERATOR_DIR])


def test_d3_a_and_b_done_runs_one():
    _scenario(lambda r: (r.seed_a(), r.seed_b()),
              [panelauto.MODERATOR_DIR])


def test_d4_everything_done_runs_none():
    rnd, out = _scenario(lambda r: r.seed_all(), [])
    assert out.reused_calls == 0, "재사용은 호출이 아니다"
    assert out.ok


def test_d5_a_broken_a_reruns_a_and_c_but_not_b():
    rnd = Round()
    rnd.seed_all()
    rnd.path(panelwork.STAGE_A).write_text("[]", encoding="utf-8")
    out, calls = go(rnd)
    assert out.ok, out.stopped_reason
    assert stages_called(calls) == [panel.DATA_ANALYST,
                                    panelauto.MODERATOR_DIR]


def test_d6_a_changed_packet_reruns_everything():
    rnd = Round()
    rnd.seed_all()
    for stage in (panelwork.STAGE_A, panelwork.STAGE_B):
        panelwork.record_stage(rnd.report.round_id, stage, rnd.base,
                               packet_sha256="옛-packet")
    out, calls = go(rnd)
    assert out.ok, out.stopped_reason
    assert stages_called(calls) == [panel.DATA_ANALYST,
                                    panel.MATCHUP_ANALYST,
                                    panelauto.MODERATOR_DIR]


def test_d7_resume_does_not_leak_a_into_b():
    """재개해도 B 의 stdin 에 A 결과가 들어가지 않는다 (§1-9)."""
    rnd = Round()
    rnd.seed_a()
    _out, calls = go(rnd)
    b = next(c for c in calls if c["stage"] == panel.MATCHUP_ANALYST)
    a_text = rnd.path(panelwork.STAGE_A).read_text(encoding="utf-8")
    rows = json.loads(a_text)
    assert rows[0]["summary"] not in b["stdin"], "A 의 요약이 B 에 샜다"
    assert panelauto.ANALYST_A_TAG not in b["stdin"]


def test_d8_resume_keeps_the_packet_identical_for_b():
    """A 를 재사용해도 B 가 받는 packet 은 A 가 받았던 그것이다."""
    rnd = Round()
    _out, first = go(rnd)
    a1 = next(c for c in first if c["stage"] == panel.DATA_ANALYST)
    b1 = next(c for c in first if c["stage"] == panel.MATCHUP_ANALYST)
    assert a1["stdin"] == b1["stdin"]
    rnd2 = Round()
    rnd2.seed_a()
    _out2, second = go(rnd2)
    b2 = next(c for c in second if c["stage"] == panel.MATCHUP_ANALYST)
    assert b2["stdin"] == b1["stdin"], "재개한 B 가 다른 자료를 받았다"


# ==========================================================================
# E. 실패 주입 (§15)
# ==========================================================================
def test_e1_a_failure_stops_before_b_and_c():
    """Case A — A 가 실패하면 뒤 단계에 돈을 쓰지 않는다."""
    rnd = Round()
    out, calls = go(rnd, agent=lambda rec: breaking_fake(
        rnd, panel.DATA_ANALYST, panelauto.AGENT_FAILED, rec))
    assert not out.ok
    assert stages_called(calls) == [panel.DATA_ANALYST]
    assert not rnd.path(panelwork.STAGE_A).is_file(), "실패가 보관됐다"


def test_e2_b_failure_keeps_a():
    """Case B — B 가 실패해도 A 체크포인트는 그대로다 (§20)."""
    rnd = Round()
    out, calls = go(rnd, agent=lambda rec: breaking_fake(
        rnd, panel.MATCHUP_ANALYST, panelauto.AGENT_FAILED, rec))
    assert not out.ok
    assert stages_called(calls) == [panel.DATA_ANALYST, panel.MATCHUP_ANALYST]
    assert rnd.path(panelwork.STAGE_A).is_file()
    assert rnd.cp(panelwork.STAGE_A).usable
    # 다시 돌리면 **B 부터** 이어간다.
    out2, calls2 = go(rnd)
    assert out2.ok, out2.stopped_reason
    assert stages_called(calls2) == [panel.MATCHUP_ANALYST,
                                     panelauto.MODERATOR_DIR]


def test_e3_c_failure_keeps_a_and_b():
    """Case C — C 가 실패해도 A·B 는 남고 재개는 C 부터다."""
    rnd = Round()
    out, _ = go(rnd, agent=lambda rec: breaking_fake(
        rnd, panelauto.MODERATOR_DIR, panelauto.AGENT_FAILED, rec))
    assert not out.ok
    assert not rnd.path(panelwork.STAGE_RESULT).is_file()
    out2, calls2 = go(rnd)
    assert out2.ok, out2.stopped_reason
    assert stages_called(calls2) == [panelauto.MODERATOR_DIR]


def test_e4_usage_limit_stops_and_never_switches_to_billing():
    """Case D — 한도에서 멈춘다. **과금으로 넘기지 않는다.**"""
    rnd = Round()
    lines = []
    out, calls = go(rnd, echo=lines, agent=lambda rec: breaking_fake(
        rnd, panel.MATCHUP_ANALYST, panelauto.AGENT_USAGE_LIMIT, rec))
    assert not out.ok
    assert out.stopped_reason == panelauto.WORKFLOW_STOPPED_USAGE_LIMIT
    assert stages_called(calls) == [panel.DATA_ANALYST, panel.MATCHUP_ANALYST]
    text = "\n".join(lines)
    assert "과금" in text and "보존" in text, text
    for bad in ("크레딧을 사용", "결제", "자동 충전", "API 키를 추가"):
        assert bad not in text, bad
    # 남은 것은 그대로 이어진다.
    out2, calls2 = go(rnd)
    assert out2.ok
    assert stages_called(calls2) == [panel.MATCHUP_ANALYST,
                                     panelauto.MODERATOR_DIR]


def test_e5_schema_failure_leaves_no_checkpoint():
    """Case E — 모델이 형식을 어기면 체크포인트가 생기지 않는다."""
    rnd = Round()

    def bad_agent(record):
        def fake(prompt, system, workspace, **kw):
            Path(workspace).mkdir(parents=True, exist_ok=True)
            record.append({"stage": panel.DATA_ANALYST, "stdin": "",
                           "system": system, "prompt": prompt})
            return panelauto.AgentRun(status=panelauto.AGENT_OK,
                                      session_id="sid", text='[{"x":1}]',
                                      turns=1, cost_usd=0.0)
        return fake

    out, _ = go(rnd, agent=bad_agent)
    assert not out.ok
    assert out.status == panelauto.AGENT_INVALID, out.status
    assert not rnd.path(panelwork.STAGE_A).is_file()
    row = rnd.row(panelwork.STAGE_A)
    assert row["last_attempt"]["status"] == panelwork.STAGE_FAILED


def test_e6_a_second_attempt_after_failure_is_recorded():
    rnd = Round()
    go(rnd, agent=lambda rec: breaking_fake(
        rnd, panel.DATA_ANALYST, panelauto.AGENT_FAILED, rec))
    first = rnd.row(panelwork.STAGE_A)["last_attempt"]["at"]
    out2, _ = go(rnd)
    assert out2.ok, out2.stopped_reason
    row = rnd.row(panelwork.STAGE_A)
    assert row["last_attempt"]["status"] == panelwork.STAGE_COMPLETE
    assert row["last_attempt"]["at"] >= first
    assert row["sha256"], "성공한 뒤에도 체크포인트 해시가 없다"


# ==========================================================================
# F. $0 점검 — 무엇을 다시 돌릴지 먼저 보여 준다 (§21·§22)
# ==========================================================================
def test_f1_check_reports_checkpoints_and_resume_point():
    rnd = Round()
    rnd.seed_a()
    lines = []
    with patched(cli="/bin/true", sheet_dir=rnd.sheet):
        ok = panelauto.check(rnd.report.round_id, rnd.report, base=rnd.base,
                             echo=lines.append)
    assert ok
    text = "\n".join(lines)
    assert "체크포인트" in text
    assert "시작 단계" in text
    for stage in panelwork.STAGE_ORDER:
        assert f"  {stage}: " in text, f"{stage} 줄이 없다"
    assert "Claude 호출 2회 예정" in text, text


def test_f2_check_calls_no_model():
    """점검은 **모델을 부르지 않는다** (§21). 기존 규칙 그대로."""
    body = code_of(fn_node(panelauto, "check"))
    for bad in ("run_agent", "agent_argv", "Popen", "run_stage_analyst",
                "run_stage_moderator", "_run_stages"):
        assert bad not in body, f"check() 가 {bad} 를 부른다"


def test_f3_run_echoes_the_resume_plan_before_spending():
    rnd = Round()
    rnd.seed_a()
    lines = []
    out, _ = go(rnd, echo=lines)
    assert out.ok
    text = "\n".join(lines)
    head = text.split("[1/3]")[0]
    assert "재개 계획" in head, head
    assert "시작 단계" in head, head


def test_f4_check_and_run_use_the_same_plan():
    """점검이 통과했는데 실행이 다르게 도는 일이 없다 (§1-8)."""
    check_body = code_of(fn_node(panelauto, "check"))
    run_body = code_of(fn_node(panelauto, "run"))
    assert "preflight(" in check_body and "preflight(" in run_body
    assert "pre.plan" in check_body and "pre.plan" in run_body


def test_f5_resume_planning_never_touches_the_network():
    """재개 판정은 수집도 모델 호출도 하지 않는다."""
    for name in ("resume_plan", "checkpoint_state", "read_manifest",
                 "record_stage", "checkpoint_path"):
        body = code_of(fn_node(panelwork, name))
        for bad in ("requests", "urlopen", "subprocess", "sources",
                    "anthropic", "llm."):
            assert bad not in body, f"{name} 이 {bad} 를 쓴다"
    assert "sources" not in module_code(panelwork)


# ==========================================================================
# G. 범위 — 바뀌지 않은 것
# ==========================================================================
def test_g1_still_exactly_three_sessions():
    assert panelauto.EXPECTED_SESSIONS == 3
    rnd = Round()
    out, calls = go(rnd)
    assert out.ok and len(calls) == 3


def test_g2_no_extra_explanation_pass():
    """LLM 에게 "왜 그렇게 판단했는지 설명해" 를 시키지 않는다 (§25)."""
    for mod in (panelauto, panelwork):
        code = module_code(mod)
        for bad in ("왜 그렇게", "다시 설명", "explain_yourself", "재설명",
                    "rationale_check", "self_critique"):
            assert bad not in code, f"{mod.__name__} 에 {bad}"
    # 단계는 여전히 셋뿐이다.
    assert set(panelauto.WORK_STAGE) == {panel.DATA_ANALYST,
                                         panel.MATCHUP_ANALYST,
                                         panelauto.MODERATOR_DIR}


def test_g3_no_database_and_one_new_file():
    """새 DB 를 만들지 않았고, 는 것은 매니페스트 한 장이다 (§30)."""
    for mod in (panelauto, panelwork):
        code = module_code(mod).lower()
        for bad in ("sqlite", "shelve", "pickle", "redis", "sqlalchemy"):
            assert bad not in code, f"{mod.__name__} 에 {bad}"
    rnd = Round()
    out, _ = go(rnd)
    assert out.ok
    folder = panelwork.work_dir(rnd.report.round_id, rnd.base)
    # `auto/` 는 에이전트 scratch 이고 `base` 를 준 테스트에서만 여기 생긴다
    # (운영에서는 저장소 밖이다 — `auto_root()`).
    got = sorted(p.name for p in folder.iterdir()
                 if p.name != panelauto.AUTO_DIRNAME)
    assert got == sorted(["analyst_a.json", "analyst_b.json",
                          "moderator_result.json",
                          panelwork.MANIFEST_FILE]), got
    assert panelwork.MANIFEST_FILE == "workflow_manifest.json"


def test_g4_no_auto_commit_of_panel_results():
    """`panel_results/` 를 자동으로 커밋하지 않는다 (§29)."""
    for mod in (panelauto, panelwork):
        code = module_code(mod)
        for bad in ("git ", "git.", "subprocess.*commit", "\"add\"", "push"):
            assert bad not in code, f"{mod.__name__} 에 {bad}"
    assert "panel_results" not in code_of(fn_node(panelwork, "record_stage"))


def test_g5_schema_and_prompt_versions_are_unchanged():
    assert panelimport.SCHEMA_VERSION == "1.1"
    assert panel.PANEL_PROMPT_VERSION == "5"
    assert moderator.MODERATOR_PROMPT_VERSION == "6"
    assert panelpacket.PACKET_VERSION == "6-F-10-common-v2"


def test_g6_packet_is_still_built_once_and_shared():
    """6-F-10 의 불변조건이 그대로다 — 재개가 그것을 깨지 않는다."""
    body = code_of(fn_node(panelauto, "_run_stages"))
    assert body.count("packet=packet") == 2
    made = []
    real = panelpacket.build_compact_packet

    def counting(index):
        made.append(1)
        return real(index)

    panelpacket.build_compact_packet = counting
    try:
        rnd = Round()
        out, calls = go(rnd)
    finally:
        panelpacket.build_compact_packet = real
    assert out.ok, out.stopped_reason
    assert len(made) == 1, f"packet 을 {len(made)}번 만들었다"
    a = next(c for c in calls if c["stage"] == panel.DATA_ANALYST)
    b = next(c for c in calls if c["stage"] == panel.MATCHUP_ANALYST)
    assert a["stdin"] == b["stdin"]


def test_g7_the_repository_checkpoints_are_never_touched():
    """이 스위트는 저장소의 `panel_work/` 를 건드리지 않는다 (§27)."""
    # 실물 회차 폴더를 이름으로 가리키는 상수가 이 파일에 없다.
    # 바늘을 쪼개 만든다 — 통째로 적으면 **이 검사 자신이** 걸린다.
    needle = panelwork.WORK_DIRNAME + "/" + "260052"
    tree = ast.parse(source_of(sys.modules[__name__]))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert needle not in node.value, node.value[:60]
    # 모든 경로가 임시 폴더 아래다.
    rnd = Round()
    for stage in (panelwork.STAGE_A, panelwork.STAGE_B,
                  panelwork.STAGE_RESULT):
        assert str(rnd.path(stage)).startswith(str(rnd.base)), stage


# ==========================================================================
# H. Resume 과 Rerun 은 다른 것이다 (§19)
# ==========================================================================
def test_h1_resume_is_the_default():
    """`[2]` 와 `--panel-auto` 는 **재개**다. 다시 돌리는 것은 선택이다."""
    import inspect
    sig = inspect.signature(panelauto.run)
    assert sig.parameters["rerun"].default is False


def test_h2_rerun_marks_every_stage_for_rerun():
    rnd = Round()
    rnd.seed_all()
    plan = rnd.plan(_expect(rnd))
    assert plan.resume_from == panelwork.STAGE_APPLY
    forced = panelwork.force_rerun(plan)
    assert forced.resume_from == panelwork.STAGE_A
    for row in forced.stages:
        assert not row.reuse, row.stage
        assert row.reason == "다시 실행하도록 요청했습니다"
    # 원래 계획을 고치지 않는다 — 둘을 견줄 수 있어야 한다.
    assert plan.reuse(panelwork.STAGE_A)


def test_h3_force_rerun_keeps_what_was_there():
    """무엇이 있었는지는 그대로 보인다 — 쓰지 않을 뿐이다."""
    rnd = Round()
    rnd.seed_all()
    forced = panelwork.force_rerun(rnd.plan(_expect(rnd)))
    cp = forced.plan(panelwork.STAGE_A).checkpoint
    assert cp is not None and cp.exists and cp.matches == 3


def test_h4_rerun_actually_calls_all_three():
    rnd = Round()
    rnd.seed_all()
    calls = []
    fake = make_fake(rnd.report, calls)
    lines = []
    os.environ[panelauto.AUTO_ENV] = str(rnd.base / "auto")
    try:
        with patched(run_agent=fake, cli="/bin/true",
                     existing_cli=fake_cli(rnd), sheet_dir=rnd.sheet):
            out = panelauto.run(rnd.report.round_id, rnd.report,
                                base=rnd.base, rerun=True,
                                echo=lines.append)
    finally:
        os.environ.pop(panelauto.AUTO_ENV, None)
    assert out.ok, out.stopped_reason
    assert stages_called(calls) == [panel.DATA_ANALYST,
                                    panel.MATCHUP_ANALYST,
                                    panelauto.MODERATOR_DIR]
    assert "다시 실행 (요청)" in "\n".join(lines)


def test_h5_the_menu_asks_and_defaults_to_no():
    """메뉴가 묻되 **기본이 아니오**다 (§19). 돈이 드는 쪽이 기본일 수 없다."""
    from toto import menu
    body = code_of(fn_node(menu, "_panel_auto_args"))
    assert "--panel-auto-rerun" in body
    assert "[y/N]" in body, "기본값을 예로 두었다"
    # 판정을 메뉴에서 다시 구현하지 않는다 — 인자를 만들어 CLI 에 넘긴다.
    for bad in ("resume_plan", "checkpoint_state", "force_rerun"):
        assert bad not in body, f"메뉴가 {bad} 를 직접 부른다"


def main() -> int:
    print("Phase 6-F-12 — stage resume · 체크포인트 · A/B/C provenance")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 1 if _FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
