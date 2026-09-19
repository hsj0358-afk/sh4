"""패널 자동 실행 회귀 (Phase 6-F-6 · CLAUDE.md §1-42).

지키려는 것 넷이다.

  1. **비용을 프로그램이 결정하지 않는다** — API 키 차단 · `--bare` 없음 ·
     사용량 한도에서 과금 전환 없음
  2. **A/B 독립성** — 새 프로세스 · 새 세션 ID · 부모 세션 제거 · 폴더 분리
  3. **실패를 성공으로 취급하지 않는다** — 검증은 기존 검증기가 한다
  4. **끝난 단계는 건너뛴다** — 실패 지점부터 재개

에이전트를 실제로 부르는 시험은 돈이 드므로, 여기서는 `run_agent` 를
가짜로 바꿔 **오케스트레이션**만 본다. 실제 `claude -p` 연동은 6-F-6 구현
중 실물로 확인했고 보고서에 수치를 적었다.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import (moderator, panel, panelauto, panelimport,  # noqa: E402
                  panelwork)

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
# 도구
# ==========================================================================
def source_of(obj) -> str:
    return Path(obj.__file__).read_text(encoding="utf-8")


def fn_node(module, name):
    tree = ast.parse(source_of(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} 을 찾지 못했다")


def code_of(node) -> str:
    """docstring 을 뺀 본문.

    이 저장소의 함수들은 "무엇을 하지 않는다" 를 docstring 에 적으므로,
    낱말로 재면 그 설명이 스스로 걸린다 (6-F-3·6-F-4 가 같은 이유로 AST 로
    옮겼다). 지키려는 것은 문서가 아니라 코드다.
    """
    body = [n for n in node.body
            if not (isinstance(n, ast.Expr)
                    and isinstance(n.value, ast.Constant)
                    and isinstance(n.value.value, str))]
    return "\n".join(ast.unparse(n) for n in body)


def module_code(module) -> str:
    """모듈 전체에서 docstring 만 뺀 코드."""
    tree = ast.parse(source_of(module))
    out = []
    for node in tree.body:
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            continue
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            out.append(node.name + "\n" + code_of(node))
        else:
            out.append(ast.unparse(node))
    return "\n".join(out)


def calls_in(node) -> set:
    return {ast.unparse(c.func) for c in ast.walk(node)
            if isinstance(c, ast.Call)}


def imported_names(module) -> set:
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


def scratch() -> Path:
    """**저장소 밖** 임시 디렉터리. 실제 panel_work/ 를 건드리지 않는다."""
    return Path(tempfile.mkdtemp(prefix="toto_auto_test_"))


_DEMO = None


def demo_matches(n):
    """**진짜 `Match` 객체**를 쓴다.

    `build_panel_payload()` 가 경기 객체의 여러 칸을 읽으므로 얇은 가짜로는
    검증기를 실제로 지나는지 확인할 수 없다 — 검증을 통과하는지가 이 절의
    요점이다.
    """
    global _DEMO
    if _DEMO is None:
        from toto import fixtures
        _DEMO = fixtures.build_demo_matches()
    picked = _DEMO[:n]
    for i, m in enumerate(picked, start=1):
        m.no = i
    return picked


class FakeReport:
    def __init__(self, n=3, round_id="TEST"):
        self.round_id = round_id
        self.matches = demo_matches(n)


def opinion_obj(no=1, ids=()):
    return {"predicted_home": 2, "predicted_away": 1,
            "summary": f"{no}번 요약", "rationale": [f"{no}번 근거"],
            "evidence_ids": list(ids)}


# ==========================================================================
# A. 비용 안전장치 — 이 Phase 의 최우선 제약
# ==========================================================================
def test_a1_api_key_blocks_preflight():
    """`ANTHROPIC_API_KEY` 가 있으면 **시작하지 않는다** (§25)."""
    rep = FakeReport()
    had = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
    try:
        pre = panelauto.preflight(rep, "TEST", scratch())
        assert not pre.ok, "API 키가 있는데 통과했다"
        joined = " ".join(pre.problems)
        assert "ANTHROPIC_API_KEY" in joined
        assert "구독" in joined, joined
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        if had is not None:
            os.environ["ANTHROPIC_API_KEY"] = had


def test_a2_child_env_drops_api_credentials():
    """자식 환경에서 API 인증을 지운다 (§4-A)."""
    base = {"ANTHROPIC_API_KEY": "k", "ANTHROPIC_AUTH_TOKEN": "t",
            "PATH": "/usr/bin"}
    env = panelauto.build_agent_env(base)
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["PATH"] == "/usr/bin", "무관한 환경까지 지웠다"


def test_a3_child_env_keeps_subscription_login():
    """구독 로그인 정보까지 지우면 안 된다 (§4-A).

    지우는 것은 `SCRUB_API` + `SCRUB_SESSION` 에 적힌 것뿐이고, 그 밖의
    `CLAUDE_*` 는 남아야 한다 — 인증이 통째로 사라지면 자동화가 돌지 않는다.
    """
    base = {"CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST": "1",
            "CLAUDE_CONFIG_DIR": "/home/u/.claude",
            "CLAUDE_CODE_SESSION_ID": "부모", "HOME": "/home/u"}
    env = panelauto.build_agent_env(base)
    assert env.get("CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST") == "1"
    assert env.get("CLAUDE_CONFIG_DIR") == "/home/u/.claude"
    assert env.get("HOME") == "/home/u"
    assert "CLAUDE_CODE_SESSION_ID" not in env


def test_a4_bare_is_never_passed():
    """`--bare` 를 쓰지 않는다 (§4-B).

    그 모드는 구독 로그인을 읽지 않고 `ANTHROPIC_API_KEY` 를 요구한다 —
    쓰는 순간 이 워크플로의 비용 전제가 깨진다.
    """
    argv = panelauto.agent_argv("claude", "p", "s", Path("/w"), "sid", "haiku")
    assert "--bare" not in argv, argv
    # 코드 어디에서도 만들지 않는다 (docstring 의 설명은 제외).
    assert "--bare" not in module_code(panelauto)


def test_a5_no_billing_switch_is_performed():
    """과금 전환·결제·크레딧 승인을 코드가 하지 않는다 (§26)."""
    code = module_code(panelauto)
    for bad in ("usage_credits", "enable_credits", "auto_reload",
                "billing", "purchase", "--dangerously-skip-permissions"):
        assert bad not in code, f"{bad} 가 코드에 있다"


def test_a6_usage_limit_stops_the_workflow():
    """한도에 닿으면 `WORKFLOW_STOPPED_USAGE_LIMIT` 로 멈춘다 (§26)."""
    assert panelauto._classify("Claude usage limit reached") \
        == panelauto.AGENT_USAGE_LIMIT
    assert panelauto._classify("rate_limit") == panelauto.AGENT_USAGE_LIMIT
    assert panelauto.WORKFLOW_STOPPED_USAGE_LIMIT \
        == "WORKFLOW_STOPPED_USAGE_LIMIT"
    # 모르는 오류를 한도로 오해하지 않는다 — 그 반대도 마찬가지다.
    assert panelauto._classify("무슨 소린지 모를 오류") \
        == panelauto.AGENT_FAILED


def test_a7_auth_failure_is_its_own_state():
    """로그인이 없는 것과 한도를 넘은 것은 다른 상태다 (§1-6)."""
    assert panelauto._classify("authentication_failed") \
        == panelauto.AGENT_AUTH
    assert panelauto.AGENT_AUTH != panelauto.AGENT_USAGE_LIMIT


def test_a8_never_calls_the_anthropic_api_directly():
    """`anthropic`·`llm` 을 import 하지 않는다 (§1).

    **import 문을 본다** — 이 모듈의 docstring 은 "부르지 않는다" 를 적으려고
    그 이름들을 언급하므로 낱말로 재면 설명이 스스로 걸린다.
    """
    names = imported_names(panelauto)
    assert "anthropic" not in names, names
    # `llm.strip_fence` 는 순수 정규식이라 함수 안에서만 쓴다 — 모델을
    # 부르는 함수(`complete`·`ask`)는 쓰지 않는다.
    code = module_code(panelauto)
    for bad in ("llm.complete", "llm.ask", "Anthropic("):
        assert bad not in code, bad


def test_a9_never_uses_the_legacy_api_executor():
    """`[2] --panel` 의 실행 경로를 부르지 않는다 (§1)."""
    node = ast.parse(module_code(panelauto))
    called = {ast.unparse(c.func) for c in ast.walk(node)
              if isinstance(c, ast.Call)}
    for bad in ("panel.run_match", "panel.run_panel_role",
                "panel.attach_panels", "moderator.run_moderator",
                "run_match", "run_panel_role", "attach_panels",
                "run_moderator"):
        assert bad not in called, f"{bad} 를 부른다"
    # 레거시 인자를 만들지도 않는다.
    assert '"--panel"' not in module_code(panelauto)


def test_a10_no_browser_or_gui_automation():
    for bad in ("playwright", "selenium", "webdriver", "pyautogui",
                "pyperclip", "claude://"):
        assert bad not in module_code(panelauto).lower(), bad


# ==========================================================================
# B. A/B 독립성
# ==========================================================================
def test_b1_every_call_gets_a_fresh_session_id():
    """호출마다 새 세션 ID (§8)."""
    seen = set()
    for _ in range(20):
        node = fn_node(panelauto, "run_agent")
        assert "uuid.uuid4" in code_of(node), "세션 ID 를 새로 만들지 않는다"
        break
    # 실제로 인자에 실리는지 본다.
    argv = panelauto.agent_argv("claude", "p", "s", Path("/w"), "SID")
    assert "--session-id" in argv and argv[argv.index("--session-id") + 1] \
        == "SID"


def test_b2_parent_session_is_scrubbed():
    """부모 세션 ID 를 물려주지 않는다 (§8).

    6-F-5 POC 에서 물려주면 자식이 **부모와 같은 세션 ID** 를 썼다.
    """
    assert "CLAUDE_CODE_SESSION_ID" in panelauto.SCRUB_SESSION
    env = panelauto.build_agent_env({"CLAUDE_CODE_SESSION_ID": "부모",
                                     "CLAUDECODE": "1"})
    assert "CLAUDE_CODE_SESSION_ID" not in env
    assert "CLAUDECODE" not in env


def test_b3_roles_use_different_workspaces():
    """A 와 B 의 작업 폴더가 다르다 (§9·§10)."""
    base = scratch()
    a = panelauto.match_workspace("R", panel.DATA_ANALYST, 1, base)
    b = panelauto.match_workspace("R", panel.MATCHUP_ANALYST, 1, base)
    assert a != b
    assert not str(b).startswith(str(a))
    assert not str(a).startswith(str(b))


def test_b4_a_workspace_never_receives_b_output():
    """A 의 workspace 에 B 산출물을 넣지 않는다 (§9)."""
    base, rep = scratch(), FakeReport(2)
    calls = []

    def fake(prompt, system, workspace, **kw):
        # 그 역할의 폴더에만 쓴다.
        (Path(workspace) / panelauto.AGENT_OUTPUT).write_text(
            json.dumps(opinion_obj()), encoding="utf-8")
        calls.append(Path(workspace))
        return panelauto.AgentRun(status=panelauto.AGENT_OK, session_id="s")

    orig = panelauto.run_agent
    panelauto.run_agent = fake
    try:
        for m in rep.matches:
            panelauto.run_match_role(m, panel.DATA_ANALYST, "R", base=base)
    finally:
        panelauto.run_agent = orig
    a_root = panelauto.auto_dir("R", base) / panelauto.ROLE_DIRS[
        panel.DATA_ANALYST]
    b_root = panelauto.auto_dir("R", base) / panelauto.ROLE_DIRS[
        panel.MATCHUP_ANALYST]
    assert a_root.is_dir()
    assert not b_root.exists(), "A 를 돌렸는데 B 폴더가 생겼다"
    assert all(str(c).startswith(str(a_root)) for c in calls)


def test_b5_isolation_is_structural_not_a_prompt():
    """격리를 프롬프트 문구에 기대지 않는다 (§8).

    세 장치가 코드에 있어야 한다 — 새 프로세스(subprocess) · 새 세션 ID ·
    부모 세션 제거.
    """
    code = module_code(panelauto)
    assert "subprocess.run" in code
    assert "uuid.uuid4" in code
    assert "SCRUB_SESSION" in code


# ==========================================================================
# C. 검증 — 실패를 성공으로 취급하지 않는다
# ==========================================================================
def test_c1_verification_reuses_the_existing_validator():
    """경기 하나의 내용은 `panel.parse_opinion()` 이 본다 (§40)."""
    node = fn_node(panelauto, "verify_match")
    assert "panel.parse_opinion" in calls_in(node), calls_in(node)
    # 스키마를 다시 적지 않는다.
    body = code_of(node)
    for bad in ("isinstance", "predicted_home", "int)"):
        assert bad not in body, f"verify_match 가 {bad} 를 직접 본다"


def test_c2_bad_scores_are_rejected():
    rep = FakeReport(1)
    ids = []
    for bad in ({"predicted_home": "2"}, {"predicted_home": 1.5},
                {"predicted_home": -1}, {"predicted_home": True}):
        obj = opinion_obj(1, ids)
        obj.update(bad)
        got, why = panelauto.verify_match(obj, rep.matches[0],
                                          panel.DATA_ANALYST)
        assert got is None, f"{bad} 가 통과했다"
        assert why


def test_c3_unknown_evidence_id_is_rejected():
    rep = FakeReport(1)
    obj = opinion_obj(1, ["E999"])
    got, why = panelauto.verify_match(obj, rep.matches[0], panel.DATA_ANALYST)
    assert got is None and why


def test_c4_code_fence_is_stripped_but_prose_is_not_repaired():
    """```json 울타리만 걷는다 — 설명문이 섞이면 실패다 (§17)."""
    ws = scratch()
    (ws / panelauto.AGENT_OUTPUT).write_text(
        "```json\n" + json.dumps(opinion_obj()) + "\n```", encoding="utf-8")
    data, why = panelauto._read_output(ws)
    assert data is not None, why

    (ws / panelauto.AGENT_OUTPUT).write_text(
        "분석했습니다.\n" + json.dumps(opinion_obj()), encoding="utf-8")
    data, why = panelauto._read_output(ws)
    assert data is None and "JSON" in why


def test_c5_missing_output_is_its_own_state():
    ws = scratch()
    data, why = panelauto._read_output(ws)
    assert data is None
    assert panelauto.AGENT_OUTPUT in why


def test_c6_array_instead_of_object_is_rejected():
    ws = scratch()
    (ws / panelauto.AGENT_OUTPUT).write_text("[]", encoding="utf-8")
    data, why = panelauto._read_output(ws)
    assert data is None and "객체" in why


def test_c7_failure_never_counts_as_success():
    """검증에 실패하면 그 경기는 실패다 — 다음 단계로 가지 않는다 (§17)."""
    base, rep = scratch(), FakeReport(2)

    def fake(prompt, system, workspace, **kw):
        (Path(workspace) / panelauto.AGENT_OUTPUT).write_text(
            json.dumps({"predicted_home": "둘"}), encoding="utf-8")
        return panelauto.AgentRun(status=panelauto.AGENT_OK)

    orig = panelauto.run_agent
    panelauto.run_agent = fake
    try:
        res = panelauto.run_stage_ab(rep, panel.DATA_ANALYST, base=base)
    finally:
        panelauto.run_agent = orig
    assert not res.ok
    assert res.status == panelauto.AGENT_INVALID
    # **첫 실패에서 멈춘다** — 2번 경기를 시도하지 않는다.
    assert len(res.matches) == 1, [m.no for m in res.matches]


def test_c8_opinion_keys_match_the_real_validator():
    """안내하는 칸이 `parse_opinion` 이 요구하는 것과 어긋나지 않는다.

    이름이 갈라지면 에이전트가 문서대로 만들고 검증기에서 거부당한다.
    """
    joined = " ".join(panelauto.OPINION_KEYS)
    src = source_of(panel)
    for key in ("predicted_home", "predicted_away", "summary", "rationale",
                "evidence_ids"):
        assert key in joined, f"{key} 를 안내하지 않는다"
        assert key in src, f"{key} 가 panel.py 에 없다"


# ==========================================================================
# D. 재개 — 끝난 것은 다시 돌리지 않는다
# ==========================================================================
def test_d1_completed_match_is_skipped():
    """이미 검증을 통과한 경기는 건너뛴다 (§16)."""
    base, rep = scratch(), FakeReport(1)
    ws = panelauto.match_workspace("R", panel.DATA_ANALYST, 1, base)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / panelauto.AGENT_OUTPUT).write_text(
        json.dumps(opinion_obj()), encoding="utf-8")

    called = []
    orig = panelauto.run_agent
    panelauto.run_agent = lambda *a, **k: called.append(1)
    try:
        res = panelauto.run_match_role(rep.matches[0], panel.DATA_ANALYST,
                                       "R", base=base)
    finally:
        panelauto.run_agent = orig
    assert res.ok and res.reused
    assert not called, "이미 끝난 경기를 다시 불렀다"


def test_d2_invalid_saved_output_is_not_treated_as_done():
    """깨진 결과가 남아 있으면 **끝난 것으로 보지 않는다** (§16·§17)."""
    base, rep = scratch(), FakeReport(1)
    ws = panelauto.match_workspace("R", panel.DATA_ANALYST, 1, base)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / panelauto.AGENT_OUTPUT).write_text("{깨짐", encoding="utf-8")

    called = []

    def fake(prompt, system, workspace, **kw):
        called.append(1)
        (Path(workspace) / panelauto.AGENT_OUTPUT).write_text(
            json.dumps(opinion_obj()), encoding="utf-8")
        return panelauto.AgentRun(status=panelauto.AGENT_OK)

    orig = panelauto.run_agent
    panelauto.run_agent = fake
    try:
        res = panelauto.run_match_role(rep.matches[0], panel.DATA_ANALYST,
                                       "R", base=base)
    finally:
        panelauto.run_agent = orig
    assert res.ok and not res.reused
    assert called, "깨진 결과를 완료로 보고 건너뛰었다"


def test_d3_resume_only_reruns_the_failed_match():
    """앞의 성공은 보존하고 실패한 경기부터 재개한다 (§16)."""
    base, rep = scratch(), FakeReport(4)
    attempts = []

    def make(fail_on):
        def fake(prompt, system, workspace, **kw):
            no = int(Path(workspace).name)
            attempts.append(no)
            if no == fail_on:
                return panelauto.AgentRun(status=panelauto.AGENT_FAILED,
                                          message="일부러 실패")
            (Path(workspace) / panelauto.AGENT_OUTPUT).write_text(
                json.dumps(opinion_obj(no)), encoding="utf-8")
            return panelauto.AgentRun(status=panelauto.AGENT_OK)
        return fake

    orig = panelauto.run_agent
    try:
        panelauto.run_agent = make(3)
        res = panelauto.run_stage_ab(rep, panel.DATA_ANALYST, base=base)
        assert not res.ok
        assert attempts == [1, 2, 3], attempts

        attempts.clear()
        panelauto.run_agent = make(0)       # 이번에는 아무것도 실패하지 않는다
        res = panelauto.run_stage_ab(rep, panel.DATA_ANALYST, base=base)
    finally:
        panelauto.run_agent = orig
    # 1·2 는 보존돼 다시 부르지 않고, 3·4 만 새로 부른다.
    assert attempts == [3, 4], attempts
    assert [m.reused for m in res.matches] == [True, True, False, False]


def test_d4_collect_reports_missing_matches():
    base, rep = scratch(), FakeReport(3)
    ws = panelauto.match_workspace("TEST", panel.DATA_ANALYST, 1, base)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / panelauto.AGENT_OUTPUT).write_text(json.dumps(opinion_obj(1)),
                                             encoding="utf-8")
    rows, missing = panelauto.collect_stage(rep, panel.DATA_ANALYST, base)
    assert len(rows) == 1 and missing == [2, 3]
    # 번호는 **프로그램이** 붙인다 — 모델이 적은 값을 믿지 않는다.
    assert rows[0][panelwork.STAGE_NO] == 1


# ==========================================================================
# E. 기존 계약을 바꾸지 않는다
# ==========================================================================
def test_e1_prompts_are_not_copied():
    """프롬프트 문장을 이 모듈에 복사하지 않는다 (§11)."""
    src = source_of(panelauto)
    for text in (panel.SYSTEM_COMMON, panel.ROLE_PROMPTS[panel.DATA_ANALYST],
                 panel.ROLE_PROMPTS[panel.MATCHUP_ANALYST]):
        for line in [x.strip() for x in text.splitlines() if len(x.strip()) > 25]:
            assert line not in src, f"프롬프트를 베꼈다: {line[:50]}"
    # 대신 상수를 그대로 쓴다.
    code = module_code(panelauto)
    assert "panel.SYSTEM_COMMON" in code
    assert "panel.ROLE_PROMPTS" in code
    assert "moderator.system_prompt" in code


def test_e2_existing_cli_paths_are_reused():
    """조립·검증·[4] 를 다시 구현하지 않는다 (§14·§19·§21·§22)."""
    code = module_code(panelauto)
    for flag in ("--save-panel-opinion", "--build-moderator-input",
                 "--save-moderator-result", "--paste-panel-result"):
        assert flag in code, f"{flag} 를 쓰지 않는다"
    # 회차 결과 파일을 직접 만들지 않는다 — `[4]` 의 자리다.
    assert "panel_results" not in code
    assert "panelimport.validate" not in code
    assert "panelpaste" not in code


def test_e3_agent_gets_no_bash():
    """에이전트에게 Bash 를 주지 않는다 (§13)."""
    assert "Bash" not in panelauto.AGENT_TOOLS
    assert panelauto.AGENT_TOOLS == "Read,Write"
    argv = panelauto.agent_argv("claude", "p", "s", Path("/w"), "sid")
    tools = argv[argv.index("--allowedTools") + 1]
    assert "Bash" not in tools


def test_e4_workspace_is_confined():
    """작업 폴더 밖을 보지 않게 한다 (§19 보안)."""
    argv = panelauto.agent_argv("claude", "p", "s", Path("/w/x"), "sid")
    assert "--add-dir" in argv
    assert argv[argv.index("--add-dir") + 1] == str(Path("/w/x"))


def test_e5_downstream_modules_do_not_know_panelauto():
    """연결은 **한 방향**이다 — 기존 모듈이 자동화를 참조하지 않는다."""
    from toto import panelaudit, panelpaste
    for mod in (panelimport, panelpaste, panelaudit, panel, moderator,
                panelwork):
        assert "panelauto" not in source_of(mod), mod.__name__


def test_e6_canonical_serialization_is_untouched():
    """자료는 canonical 직렬화 그대로다 — 줄바꿈만 넣는다.

    `serialize_payload()` 는 캐시 키의 근거라 한 글자도 바뀌면 안 된다.
    파일에 쓰는 것은 같은 자료를 다시 들여쓴 것이고, A·B 가 **같은
    문자열**을 받는다는 불변조건도 그대로다.
    """
    node = fn_node(panelauto, "payload_text")
    assert "panel.serialize_payload" in calls_in(node)
    src = source_of(panel)
    assert 'separators=(",", ":")' in src, "canonical 직렬화가 바뀌었다"


def test_e7_prompt_versions_are_unchanged():
    assert panel.PANEL_PROMPT_VERSION == "4"
    assert moderator.MODERATOR_PROMPT_VERSION == "6"
    assert panelimport.SCHEMA_VERSION == "1.1"


# ==========================================================================
# F. 메뉴 재구성
# ==========================================================================
def test_f1_menu_follows_the_work_order():
    """메뉴가 **일하는 순서**로 보인다 (§31·§42)."""
    from toto import menu
    keys = [k for k, *_ in menu.ITEMS]
    assert keys == ["1", "2", "3", "4", "5", "9"], keys
    titles = {k: t for k, t, *_ in menu.ITEMS}
    assert "회차 분석" in titles["1"]
    assert "패널 자동 분석" == titles["2"]
    assert "리포트" in titles["3"]


def test_f2_auto_panel_is_the_normal_entry_point():
    """`[2]` 가 자동 워크플로로 간다 (§34)."""
    from toto import menu
    by_key = {k: a for k, _t, _d, a in menu.ITEMS}
    assert by_key["2"] == "panel-auto"
    src = source_of(menu)
    assert "--panel-auto" in src


def test_f3_legacy_api_panel_is_isolated():
    """레거시 `--panel` 은 정상 workflow 에 없다 (§33)."""
    from toto import menu
    top = [a for _k, _t, _d, a in menu.ITEMS]
    for args in top:
        assert not (isinstance(args, tuple) and "--panel" in list(args[1])), \
            f"정상 메뉴에 --panel 이 있다: {args}"
    # 지우지는 않았다 — 개발 도구 아래 그대로 있다.
    tools = [a for _k, _t, _d, a in menu.TOOLS]
    assert any(isinstance(a, tuple) and "--panel" in list(a[1])
               for a in tools), "레거시 경로를 지웠다"


def test_f4_manual_recovery_is_still_reachable():
    """6-F-3/6-F-4 의 수동 기능에 전부 닿을 수 있다 (§35)."""
    from toto import menu
    by_key = {k: a for k, _t, _d, a in menu.ITEMS}
    assert by_key["4"] == "panel-manual"
    keys = [k for k, *_ in menu.PANEL_MANUAL]
    assert keys == ["1", "2", "3", "4", "5", "6", "7", "8"], keys
    # 옮긴 것이지 새로 만든 것이 아니다 — 기존 함수를 부른다.
    src = source_of(menu)
    assert "_panel_work_for" in src and "_pick_panel_file" in src


def test_f5_cli_contract_is_unchanged():
    """메뉴를 바꿔도 CLI 인자는 그대로다 (§32)."""
    from toto import cli
    parser = cli.build_parser()
    src = source_of(cli)
    for flag in ("--panel", "--panel-export", "--save-panel-opinion",
                 "--build-moderator-input", "--save-moderator-result",
                 "--paste-panel-result", "--import-panel-result",
                 "--panel-workflow-status", "--rerender-artifact",
                 "--settle-round", "--market-eval"):
        assert flag in src, f"{flag} 가 사라졌다"
    args = parser.parse_args(["--round", "R", "--panel-auto"])
    assert args.panel_auto and args.round_id == "R"
    # 기본값은 꺼져 있다 — 아무것도 주지 않으면 예전과 같다.
    assert parser.parse_args(["--demo"]).panel_auto is False
    assert parser.parse_args(["--demo"]).auto_model is None


def test_f6_menu_does_not_reimplement_the_workflow():
    """메뉴가 오케스트레이션을 다시 쓰지 않는다 (§1-20 과 같은 이유)."""
    from toto import menu
    src = source_of(menu)
    for bad in ("run_stage_ab", "run_stage_c", "panelauto.run",
                "run_match_role", "subprocess"):
        assert bad not in src, f"menu.py 가 {bad} 를 직접 쓴다"


# ==========================================================================
# G. 전체 워크플로 (가짜 에이전트로 — 돈이 들지 않는다)
# ==========================================================================
def workflow_code() -> str:
    """워크플로 본체. **함수 하나에 묶어 두지 않는다 (6-F-7 범위 이동).**

    6-F-6 은 A→B→C→[4] 가 `run()` 한 함수 안에 있다는 것을 전제로 낱말을
    셌는데, 6-F-7 이 Ctrl+C 정리를 붙이면서 단계 부분을 `_run_stages()` 로
    갈랐다. 지키려는 것은 **코드가 어느 함수에 있느냐가 아니라 순서·경로**
    이므로 둘을 이어 붙여 본다 (§1-29·§1-31 과 같은 교정).
    """
    return (code_of(fn_node(panelauto, "run")) + "\n"
            + code_of(fn_node(panelauto, "_run_stages")))


def test_g1_stage_order_a_then_b():
    """A 가 끝나야 B 를 시작한다 (§18)."""
    body = workflow_code()
    assert body.index("DATA_ANALYST") < body.index("MATCHUP_ANALYST")


def test_g2_c_reads_only_the_assembled_sheet():
    """C 는 A·B 원본을 읽지 않는다 (§20)."""
    node = fn_node(panelauto, "run_stage_c")
    body = code_of(node)
    assert "COMPLETED_SHEET" in body
    for bad in ("analyst_a", "analyst_b", "ROLE_DIRS", "match_workspace"):
        assert bad not in body, f"C 가 {bad} 를 본다"


def test_g3_apply_uses_the_existing_paste_path():
    """[4] 반영은 기존 경로다 (§22)."""
    body = workflow_code()
    assert "--paste-panel-result" in body
    assert "moderator_result_path" in body


def test_g4_completed_stages_are_skipped():
    """상태를 먼저 읽고 끝난 단계는 건너뛴다 (§23)."""
    body = workflow_code()
    assert "panelwork.workflow" in body
    for key in ("STAGE_A", "STAGE_B", "STAGE_INPUT", "STAGE_RESULT"):
        assert key in body, f"{key} 를 보지 않는다"


def test_g5_sequential_not_parallel():
    """순차 실행이다 (§15)."""
    code = module_code(panelauto)
    for bad in ("ThreadPool", "ProcessPool", "asyncio", "concurrent.futures",
                "threading"):
        assert bad not in code, f"{bad} 로 병렬 실행한다"


def test_g6_no_new_third_party_dependency():
    """표준 라이브러리만 쓴다 (§43)."""
    std = {"json", "os", "shutil", "signal", "subprocess", "uuid", "dataclasses",
           "pathlib", "__future__", "toto", "models", "moderator", "panel",
           "panelexport", "panelwork", "artifact", "settings", "cli", "llm",
           "annotations", "dataclass", "field", "Path", "Report",
           "strip_fence", "main", "load_settings"}
    unknown = imported_names(panelauto) - std
    assert not unknown, f"새 의존성: {unknown}"


# ==========================================================================
# H. 윈도우 안전성 (Phase 6-F-7 §2)
#
# **이 세션은 리눅스다.** 실제 윈도우 PC 에서 돌려 본 것이 아니라, 윈도우
# 에서 갈라지는 자리를 **코드로 고정**한 것이다 — 어느 분기가 어느 OS 의
# 것인지, 그리고 OS 와 무관한 부분(인증·모델·인코딩·파일 읽기)이 실제로
# 도는지를 본다. 실물 검증 여부는 보고서 §22 에 그대로 적었다.
# ==========================================================================
def fake_cli(dir_: Path, body: str, name: str = "claude") -> Path:
    """가짜 `claude` 실행 파일. **모델을 부르지 않는다.**"""
    path = dir_ / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_h1_cli_discovery_has_fallbacks_and_an_escape_hatch():
    """`shutil.which` 하나에 매달리지 않는다 (§2-1)."""
    had = os.environ.get(panelauto.CLI_ENV)
    os.environ[panelauto.CLI_ENV] = "/nowhere/claude.cmd"
    try:
        cands = panelauto.cli_candidates()
        assert cands[0] == "/nowhere/claude.cmd", "환경변수가 최우선이 아니다"
    finally:
        os.environ.pop(panelauto.CLI_ENV, None)
        if had is not None:
            os.environ[panelauto.CLI_ENV] = had
    cands = panelauto.cli_candidates()
    assert cands, "후보가 하나도 없다"
    # 이름을 코드에 박지 않는다 — PATH 조회가 후보에 들어 있어야 한다.
    assert "shutil.which" in module_code(panelauto)


def test_h2_finding_is_not_running():
    """`find_claude_cli()` 는 **실행하지 않는다** (§2-1).

    찾는 것과 도는 것은 다른 질문이라 preflight 가 따로 묻는다. 여기서
    subprocess 를 띄우면 메뉴를 그릴 때마다 CLI 가 돈다.
    """
    body = code_of(fn_node(panelauto, "find_claude_cli"))
    for bad in ("subprocess", "Popen", "run("):
        assert bad not in body, f"find_claude_cli 가 {bad} 를 쓴다"


def test_h3_broken_cli_is_caught_before_the_round_starts():
    """찾아졌는데 돌지 않는 상태를 시작 전에 잡는다 (§2-1).

    윈도우의 `claude.cmd` 는 npm 셸 심이라 Node 가 없으면 **찾아지지만
    돌지 않는다.** 14경기를 시작한 뒤에 알면 안 된다.
    """
    tmp = scratch()
    broken = fake_cli(tmp, "echo 'not installed' >&2\nexit 1\n")
    ok, version, why = panelauto.cli_probe(str(broken))
    assert not ok and why, (ok, why)
    good = fake_cli(tmp, "echo '2.1.277 (Claude Code)'\n", name="claude2")
    ok, version, why = panelauto.cli_probe(str(good))
    assert ok and version.startswith("2.1.277"), (ok, version, why)
    # 없는 파일도 조용히 통과하지 않는다.
    assert not panelauto.cli_probe("")[0]


def test_h4_auth_status_reads_the_local_check():
    """`claude auth status --json` 을 읽는다. **모델을 부르지 않는다** (§2-2)."""
    tmp = scratch()
    cases = {
        '{"loggedIn":true,"authMethod":"oauth_token","apiProvider":"firstParty"}':
            panelauto.AUTH_OK,
        '{"loggedIn":false}': panelauto.AUTH_MISSING,
        '{"loggedIn":true,"authMethod":"api_key"}': panelauto.AUTH_API_KEY,
        'not json at all': panelauto.AUTH_UNKNOWN,
    }
    for i, (payload, want) in enumerate(cases.items()):
        cli = fake_cli(tmp, f"cat <<'EOF'\n{payload}\nEOF\n", name=f"c{i}")
        got = panelauto.auth_status(str(cli))
        assert got.state == want, (payload, got.state, want)
        assert got.message, "사유를 적지 않았다"
    # **로컬 점검만 한다** — 어떤 인자를 넘기는지 직접 잡아 본다.
    seen = {}
    real = panelauto._probe

    def spy(argv, timeout):
        seen["argv"] = list(argv)
        return real(argv, timeout)

    panelauto._probe = spy
    try:
        panelauto.auth_status(str(fake_cli(tmp, "echo '{}'\n", name="spy")))
    finally:
        panelauto._probe = real
    assert seen["argv"][1:] == ["auth", "status", "--json"], seen["argv"]
    assert "-p" not in seen["argv"], "모델을 부르는 인자가 섞였다"


def test_h5_missing_login_stops_but_unknown_does_not():
    """로그인 없음은 중단, **확인 못 함은 중단이 아니다** (§1-6)."""
    tmp = scratch()
    rep = FakeReport()

    def run_with(payload):
        cli = fake_cli(tmp, f"case \"$1\" in --version) echo 9.9.9 ;; *) "
                            f"cat <<'EOF'\n{payload}\nEOF\n;; esac\n",
                       name=f"claude_{abs(hash(payload)) % 10000}")
        had = os.environ.get(panelauto.CLI_ENV)
        os.environ[panelauto.CLI_ENV] = str(cli)
        try:
            return panelauto.preflight(rep, "TEST", scratch())
        finally:
            os.environ.pop(panelauto.CLI_ENV, None)
            if had is not None:
                os.environ[panelauto.CLI_ENV] = had

    out = run_with('{"loggedIn":false}')
    assert not out.ok, "로그인이 없는데 시작한다"
    assert any("로그인" in p for p in out.problems), out.problems

    out = run_with('{"loggedIn":true,"authMethod":"api_key"}')
    assert not out.ok, "API 키 인증인데 시작한다"
    assert any("구독" in p for p in out.problems), out.problems

    out = run_with("아무 말")
    assert out.ok, f"확인 못 했다고 막았다: {out.problems}"
    assert any("확인 못 함" in n for n in out.notes), out.notes

    out = run_with('{"loggedIn":true,"authMethod":"oauth_token"}')
    assert out.ok, out.problems


def test_h6_default_model_is_the_measured_one():
    """`--auto-model` 없이도 검증된 모델로 돈다 (§5).

    6-F-6 실측에서 haiku 는 파일을 쓰지 않아 실패했고 sonnet 은 A·B·C 가
    전부 돌았다. 인자를 빼먹으면 그때그때의 CLI 기본 모델을 타게 된다.
    """
    assert panelauto.DEFAULT_AUTO_MODEL == "sonnet"
    assert panelauto.resolve_model(None) == "sonnet"
    assert panelauto.resolve_model("") == "sonnet"
    assert panelauto.resolve_model("  ") == "sonnet"
    assert panelauto.resolve_model("opus") == "opus"
    # 일부러 CLI 기본을 쓰려면 낱말로 고른다 — 그때만 `--model` 이 빠진다.
    for word in ("cli", "CLI", "default", "기본"):
        assert panelauto.resolve_model(word) == "", word
    argv = panelauto.agent_argv("claude", "p", "s", Path("/w"), "sid", "")
    assert "--model" not in argv
    argv = panelauto.agent_argv("claude", "p", "s", Path("/w"), "sid", "sonnet")
    assert argv[argv.index("--model") + 1] == "sonnet"


def test_h7_the_workflow_resolves_the_model_once():
    """모델 정책은 **한 곳**에 있다 (§1-8)."""
    assert "resolve_model" in code_of(fn_node(panelauto, "run"))
    # 하위 함수는 받은 값을 넘기기만 한다 — 각자 기본값을 정하지 않는다.
    for fn in ("run_stage_ab", "run_stage_c", "run_match_role", "agent_argv"):
        body = code_of(fn_node(panelauto, fn))
        assert "DEFAULT_AUTO_MODEL" not in body, f"{fn} 이 기본을 다시 정한다"


def test_h8_child_runs_in_its_own_process_group():
    """자식을 자기 그룹으로 띄운다 (§2-4)."""
    kwargs = panelauto._spawn_kwargs()
    if os.name == "nt":
        assert "creationflags" in kwargs
    else:
        assert kwargs.get("start_new_session") is True
    # 두 OS 의 분기가 코드에 다 있다.
    body = code_of(fn_node(panelauto, "_spawn_kwargs"))
    assert "CREATE_NEW_PROCESS_GROUP" in body and "start_new_session" in body


def test_h9_kill_covers_grandchildren_on_both_systems():
    """손자까지 끝낸다 (§2-4).

    윈도우에서 `claude.cmd` 의 실제 계층은 `cmd.exe → node.exe` 라, 직접
    자식만 죽이면 node 가 살아남아 사용량이 계속 나간다.
    """
    body = code_of(fn_node(panelauto, "_kill_tree"))
    assert "taskkill" in body and "/T" in body, "윈도우 트리 종료가 없다"
    assert "killpg" in body, "POSIX 그룹 종료가 없다"
    # `subprocess.run(timeout=)` 으로 돌아가지 않는다 — 그건 직접 자식만
    # 죽인다. `communicate` 를 쓰고 우리가 정리한다.
    run_body = code_of(fn_node(panelauto, "run_agent"))
    assert "communicate" in run_body and "_kill_tree" in run_body
    assert "subprocess.run(" not in run_body


def test_h10_timeout_really_kills_the_whole_tree():
    """**실제로** 손자가 사라진다 (POSIX 에서 실행해 확인한다)."""
    if os.name == "nt":                     # 윈도우에서는 taskkill 경로다
        return
    tmp = scratch()
    pidfile = tmp / "grandchild.pid"
    cli = fake_cli(tmp, f"sleep 300 & echo $! > '{pidfile}'\nsleep 300\n")
    run = panelauto.run_agent("p", "s", tmp, timeout=2, cli=str(cli))
    assert run.status == panelauto.AGENT_TIMEOUT, run.status
    assert pidfile.is_file(), "손자를 만들지 못했다 — 시험이 성립하지 않는다"
    pid = int(pidfile.read_text().strip())
    import time
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return                          # 사라졌다
        time.sleep(0.1)
    try:
        os.kill(pid, 9)
    finally:
        raise AssertionError(f"손자 {pid} 가 살아남았다")


def test_h11_interrupt_kills_the_child_and_propagates():
    """Ctrl+C 를 삼키지 않고, 자식을 남기지 않는다 (§2-4).

    삼키면 사용자가 멈췄는데도 모델이 계속 돈다. 종료코드 정책은
    `main()` 것이므로(§1-7-1) 예외는 그대로 올라가야 한다.
    """
    if os.name == "nt":
        return
    import subprocess as sp
    tmp = scratch()
    cli = fake_cli(tmp, "sleep 300\n")
    seen = {}
    real = sp.Popen

    class Interrupting(real):
        def communicate(self, *a, **k):
            seen["pid"] = self.pid
            raise KeyboardInterrupt

    sp.Popen = Interrupting
    try:
        raised = False
        try:
            panelauto.run_agent("p", "s", tmp, timeout=30, cli=str(cli))
        except KeyboardInterrupt:
            raised = True
        assert raised, "KeyboardInterrupt 를 삼켰다"
    finally:
        sp.Popen = real
    import time
    for _ in range(50):
        try:
            os.kill(seen["pid"], 0)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(0.1)
    raise AssertionError(f"자식 {seen['pid']} 이 살아남았다")


def test_h12_output_reading_survives_bom_and_bad_encoding():
    """BOM 을 견디고, 깨진 인코딩은 **그 경기의 사유**가 된다 (§2-3).

    예전에는 `UnicodeDecodeError` 가 그대로 올라가 회차 전체가 죽었다 —
    한 경기의 결과가 깨진 것은 그 경기의 실패이지 회차의 실패가 아니다.
    """
    tmp = scratch()
    (tmp / panelauto.AGENT_OUTPUT).write_text(
        json.dumps(opinion_obj(), ensure_ascii=False), encoding="utf-8-sig")
    data, why = panelauto._read_output(tmp)
    assert data is not None, f"BOM 붙은 결과를 읽지 못했다: {why}"
    assert data["summary"] == "1번 요약"

    bad = scratch()
    (bad / panelauto.AGENT_OUTPUT).write_bytes(
        '{"summary":"한글"}'.encode("cp949"))
    data, why = panelauto._read_output(bad)     # 예외가 아니라 사유여야 한다
    assert data is None and why, why


def test_h13_korean_and_spaced_paths_work():
    """`C:\\…\\축구토토 분석\\…` 같은 경로에서도 돈다 (§2-3).

    인자는 리스트로 넘기고 `shell=False` 라 공백이 쪼개지지 않는다.
    """
    root = scratch() / "축구토토 분석" / "panel work"
    ws = panelauto.match_workspace("260052", panel.DATA_ANALYST, 4,
                                   base=root)
    ws.mkdir(parents=True, exist_ok=True)
    assert "축구토토 분석" in str(ws) and ws.is_dir()
    argv = panelauto.agent_argv("claude", "프롬프트", "시스템", ws, "sid")
    assert str(ws) in argv, "작업 폴더가 인자에 통째로 들어가지 않았다"
    cli = fake_cli(scratch(), "printf '{\"result\":\"DONE\"}'\n")
    run = panelauto.run_agent("프롬프트", "시스템", ws, timeout=60, cli=str(cli))
    assert run.ok, (run.status, run.message)
    assert (ws / panelauto.AGENT_ENVELOPE).is_file(), "봉투를 남기지 않았다"


def test_h14_console_encoding_is_fixed_where_it_is_broken():
    """cp949 로 출력을 돌려도 죽지 않는다 (§2-3).

    한국어 윈도우에서 `> log.txt` 로 돌리면 파이썬이 로캘 인코딩으로 쓰는데,
    이 프로그램의 메시지에는 cp949 에 없는 글자가 있다(`—`·`✓`·`═`·`⚽`).
    **글자를 지워서 고치지 않는다** — 출력 계층에서 한 번 고친다.
    """
    import io
    from toto.cli import safe_console
    real_out, real_err = sys.stdout, sys.stderr
    try:
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        assert safe_console() == [], "멀쩡한 스트림을 건드렸다"

        buf = io.BytesIO()
        sys.stdout = io.TextIOWrapper(buf, encoding="cp949")
        sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding="cp949")
        assert "stdout" in safe_console(), "cp949 스트림을 고치지 않았다"
        print(panelauto._BAR)
        print("01/14 ✓ — 보존됨")
        sys.stdout.flush()
        text = buf.getvalue().decode("utf-8")
        assert "✓" in text and "—" in text, text[:40]
    finally:
        sys.stdout, sys.stderr = real_out, real_err
    # 없앤 것이 아니라 고친 것이다 — 진행 표시는 그대로다.
    assert "✓" in code_of(fn_node(panelauto, "_default_progress"))


def test_h15_preflight_reports_what_it_checked():
    """무엇을 보고 통과시켰는지 남긴다 (§1-6-1)."""
    tmp = scratch()
    cli = fake_cli(tmp, "case \"$1\" in --version) echo 9.9.9 ;; *) "
                        "printf '{\"loggedIn\":true,\"authMethod\":"
                        "\"oauth_token\",\"apiProvider\":\"firstParty\"}' "
                        ";; esac\n")
    had = os.environ.get(panelauto.CLI_ENV)
    os.environ[panelauto.CLI_ENV] = str(cli)
    try:
        pre = panelauto.preflight(FakeReport(), "TEST", scratch())
    finally:
        os.environ.pop(panelauto.CLI_ENV, None)
        if had is not None:
            os.environ[panelauto.CLI_ENV] = had
    assert pre.ok, pre.problems
    assert pre.version.startswith("9.9.9"), pre.version
    joined = " ".join(pre.notes)
    assert str(cli) in joined, "어느 실행 파일을 쓰는지 안 적었다"
    # 경로만으로는 '찾았다' 까지다. 이 줄이 뜬 근거는 실제로 띄워
    # `--version` 을 받은 것이므로 그 버전도 적는다.
    assert "9.9.9" in joined, f"버전을 안 적었다: {joined}"
    assert "인증" in joined, joined
    assert pre.auth is not None and pre.auth.ok


# ==========================================================================
# I. CLI 를 못 찾았을 때 (실물 윈도우 실행 후속)
#
# 6-F-7 의 hardening 이 실물 윈도우에서 **정확히 이 자리에서 멈췄다.**
# 메시지는 맞았지만 `못 찾았습니다` 한 줄만으로는 **설치가 안 된 것**인지
# **다른 자리에 있는 것**인지 가릴 수 없었다 — 둘은 할 일이 정반대다.
# ==========================================================================
def as_windows(fn):
    """윈도우 분기를 리눅스에서 그대로 태운다.

    `Path.home()` 이 리눅스에서 `WindowsPath` 를 못 만들어서 시험용
    Path 를 끼운다. 바꾸는 것은 **시험 환경**이고 코드가 아니다.
    """
    import pathlib

    class FakePath(pathlib.PurePosixPath):
        @classmethod
        def home(cls):
            return cls("C:/Users/tester")

        def is_file(self):
            return False

    real_os, real_path = os.name, panelauto.Path
    saved = {k: os.environ.get(k) for k in ("PATHEXT", "APPDATA",
                                            "LOCALAPPDATA")}
    os.name = "nt"
    panelauto.Path = FakePath
    os.environ["PATHEXT"] = ".COM;.EXE;.BAT;.CMD"
    os.environ["APPDATA"] = "C:/Users/tester/AppData/Roaming"
    os.environ["LOCALAPPDATA"] = "C:/Users/tester/AppData/Local"
    try:
        return fn()
    finally:
        os.name, panelauto.Path = real_os, real_path
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_i1_windows_candidates_cover_the_real_installers():
    """npm 의 `.cmd` 와 네이티브의 `.exe` 를 둘 다 본다.

    설치 방법마다 만드는 파일이 달라서 이름을 하나만 박으면 다른 설치가
    조용히 안 보인다. 폴더 × PATHEXT 로 훑는다.
    """
    cands = as_windows(panelauto.cli_candidates)
    lower = [c.lower() for c in cands]
    assert any(c.endswith("/npm/claude.cmd") for c in lower), "npm 심을 안 본다"
    assert any("programs/claude/claude.exe" in c for c in lower), \
        "네이티브 설치를 안 본다"
    assert any(".local/bin/claude.exe" in c for c in lower), lower[:5]
    assert any(".claude/local/claude.cmd" in c for c in lower), lower[:5]


def test_i2_pathext_is_split_on_semicolons():
    """`PATHEXT` 는 `;` 구분이다 — `os.pathsep` 이 아니다.

    `os.pathsep` 으로 나누면 이 분기를 다른 OS 에서 시험할 때 통째로
    안 갈린다 (실제로 그래서 못 갈렸다).
    """
    suffixes = as_windows(panelauto._exe_suffixes)
    assert ".CMD" in suffixes and ".EXE" in suffixes, suffixes
    assert ".PS1" in suffixes, "ps1 설치를 못 본다"
    assert not any(";" in s for s in suffixes), suffixes
    body = code_of(fn_node(panelauto, "_exe_suffixes"))
    assert "os.pathsep" not in body, "PATHEXT 를 os.pathsep 으로 나눈다"
    # POSIX 에서는 확장자가 없다.
    assert panelauto._exe_suffixes() == [""] or os.name == "nt"


def test_i3_search_folders_are_not_listed_twice():
    """같은 폴더를 두 번 적지 않는다 — 진단에 그대로 찍힌다."""
    dirs = [str(d) for d in as_windows(panelauto.cli_search_dirs)]
    assert len(dirs) == len(set(dirs)), dirs
    dirs = [str(d) for d in panelauto.cli_search_dirs()]
    assert len(dirs) == len(set(dirs)), dirs


def test_i4_diagnosis_reports_what_was_checked():
    """**무엇을 찾아봤는지** 그대로 낸다 (§1-6-1)."""
    diag = panelauto.cli_diagnosis()
    for key in ("os", "env_var", "which", "checked", "found", "path_entries"):
        assert key in diag, key
    assert diag["env_var"] == panelauto.CLI_ENV
    assert diag["checked"], "찾아본 자리를 안 적는다"
    for row in diag["checked"]:
        assert "path" in row and "exists" in row, row
    # **고쳐 주지 않는다** — 진단은 읽기만 한다.
    body = code_of(fn_node(panelauto, "cli_diagnosis"))
    for bad in ("mkdir", "write_text", "os.environ[", "subprocess"):
        assert bad not in body, f"진단이 {bad} 를 한다"


def test_i5_not_found_tells_the_user_what_to_do():
    """설치 여부와 경로 지정 둘 다 안내한다."""
    lines = " ".join(panelauto.cli_help_lines())
    assert panelauto.CLI_ENV in lines, "경로 지정 방법을 안 적는다"
    assert "claude --version" in lines or "which claude" in lines
    win = " ".join(as_windows(panelauto.cli_help_lines))
    assert "setx" in win and "Get-Command" in win, win
    assert "WSL" in win, "WSL 설치를 안 짚는다"
    assert "@anthropic-ai/claude-code" in win, "설치 방법을 안 적는다"
    # 추천·확신도 같은 말을 여기 적지 않는다.
    for bad in ("%", "추천", "확신"):
        assert bad not in win, bad


def test_i6_preflight_failure_surfaces_the_diagnosis():
    """막혔을 때 **찾아본 자리**가 화면에 나온다.

    실물 윈도우 실행에서 사유 한 줄만 나와 설치가 안 된 것인지 다른
    자리인지 가릴 수 없었다. 그 상태를 재현해 고정한다.
    """
    tmp = scratch()
    saved_path = os.environ.get("PATH")
    saved_env = os.environ.get(panelauto.CLI_ENV)
    os.environ["PATH"] = str(tmp)          # claude 가 없는 PATH
    os.environ.pop(panelauto.CLI_ENV, None)
    try:
        pre = panelauto.preflight(FakeReport(), "TEST", scratch())
    finally:
        if saved_path is not None:
            os.environ["PATH"] = saved_path
        if saved_env is not None:
            os.environ[panelauto.CLI_ENV] = saved_env
    assert not pre.ok
    problems = " ".join(pre.problems)
    assert "찾지 못했습니다" in problems
    notes = " ".join(pre.notes)
    assert "찾아본 자리" in notes, notes
    assert panelauto.CLI_ENV in notes, notes
    # 실행 경로를 지어내지 않는다 — 없으면 '없음' 이라고 적는다 (§1-5).
    assert "없음" in notes or "미설정" in notes, notes


def test_i7_failure_path_echoes_the_notes():
    """`run()` 이 막혔을 때 notes 를 삼키지 않는다."""
    body = workflow_code()
    idx = body.index("pre.problems")
    tail = body[idx:idx + 400]
    assert "pre.notes" in tail, "실패 경로에서 진단을 감춘다"


# ==========================================================================
# J. 준비 점검 — 비용 0 (실물 윈도우 실행 후속)
#
# 회차 전체는 29회 호출이다. "내 PC 가 준비됐나" 를 **그 29회를 시작해서**
# 알아내면 안 된다.
# ==========================================================================
def test_j1_check_never_calls_the_model():
    """`check()` 는 에이전트를 부르지 않는다 (비용 0)."""
    node = fn_node(panelauto, "check")
    names = calls_in(node)
    for bad in ("run_agent", "run_stage_ab", "run_stage_c",
                "run_match_role", "run", "_run_stages"):
        assert bad not in names, f"check 가 {bad} 를 부른다"
    body = code_of(node)
    for bad in ("Popen", "agent_argv", "subprocess"):
        assert bad not in body, f"check 가 {bad} 를 쓴다"


def test_j2_check_reuses_the_same_preflight():
    """판정을 두 벌 만들지 않는다 (§1-8).

    점검이 통과했는데 실행이 막히면(또는 그 반대면) 둘 중 어느 쪽도
    믿을 수 없다.
    """
    assert "preflight" in calls_in(fn_node(panelauto, "check"))
    assert "preflight" in calls_in(fn_node(panelauto, "run"))


def test_j3_check_passes_when_the_cli_is_ready():
    """CLI 가 돌고 로그인돼 있으면 통과한다."""
    tmp = scratch()
    cli = fake_cli(tmp, "case \"$1\" in --version) echo 9.9.9 ;; *) "
                        "printf '{\"loggedIn\":true,\"authMethod\":"
                        "\"oauth_token\"}' ;; esac\n")
    lines = []
    had = os.environ.get(panelauto.CLI_ENV)
    os.environ[panelauto.CLI_ENV] = str(cli)
    try:
        ok = panelauto.check("TEST", FakeReport(), base=scratch(),
                             echo=lines.append)
    finally:
        os.environ.pop(panelauto.CLI_ENV, None)
        if had is not None:
            os.environ[panelauto.CLI_ENV] = had
    assert ok, lines
    text = " ".join(lines)
    assert "준비됐습니다" in text, text
    # 무엇으로 돌지 밝힌다 — 모델과 인증을 적는다.
    assert panelauto.DEFAULT_AUTO_MODEL in text, text
    assert "인증" in text, text
    assert "모델 호출 0회" in text, text


def test_j4_check_fails_and_says_why():
    """막히면 사유를 적고 `False` 다 — 조용히 통과시키지 않는다."""
    tmp = scratch()
    cli = fake_cli(tmp, "case \"$1\" in --version) echo 9.9.9 ;; *) "
                        "printf '{\"loggedIn\":false}' ;; esac\n")
    lines = []
    had = os.environ.get(panelauto.CLI_ENV)
    os.environ[panelauto.CLI_ENV] = str(cli)
    try:
        ok = panelauto.check("TEST", FakeReport(), base=scratch(),
                             echo=lines.append)
    finally:
        os.environ.pop(panelauto.CLI_ENV, None)
        if had is not None:
            os.environ[panelauto.CLI_ENV] = had
    assert ok is False
    text = " ".join(lines)
    assert "로그인" in text, text
    assert "준비됐습니다" not in text, "막혔는데 통과처럼 적는다"


def test_j5_check_has_its_own_cli_flag_and_stops_there():
    """`--panel-auto-check` 가 점검만 하고 멈춘다."""
    import toto.cli as cli_mod
    src = source_of(cli_mod)
    assert "--panel-auto-check" in src
    body = code_of(fn_node(cli_mod, "_panel_auto"))
    # 점검 분기가 `run()` **앞에** 있고 거기서 돌려준다.
    assert body.index("panel_auto_check") < body.index("panelauto.run"), \
        "점검이 실행 뒤에 있다"
    assert "panelauto.check" in body


def test_j6_check_is_reachable_from_the_menu():
    """도구 메뉴에서 부를 수 있고 **기존 번호를 밀지 않았다**."""
    from toto.menu import TOOLS
    numbers = [t[0] for t in TOOLS]
    assert len(numbers) == len(set(numbers)), f"번호 중복 {numbers}"
    entry = [t for t in TOOLS if "--panel-auto-check" in str(t[-1])]
    assert entry, "메뉴에 준비 점검이 없다"
    assert "비용 0" in entry[0][1], entry[0][1]
    # 레거시 API 패널은 [7] 그대로다 (6-F-6 §33).
    legacy = [t for t in TOOLS if "--panel" in str(t[-1])
              and "--panel-auto-check" not in str(t[-1])]
    assert legacy and legacy[0][0] == "7", legacy


def main() -> int:
    print("Phase 6-F-6 — 패널 자동 실행 (claude -p)")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 1 if _FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
