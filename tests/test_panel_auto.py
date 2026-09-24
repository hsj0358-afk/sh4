"""패널 자동 실행 회귀 (Phase 6-F-6 → 6-F-9 · CLAUDE.md §1-42·§1-45).

지키려는 것 다섯이다.

  1. **비용을 프로그램이 결정하지 않는다** — API 키 차단 · `--bare` 없음 ·
     사용량 한도에서 과금 전환 없음
  2. **A/B 독립성** — 새 프로세스 · 새 세션 ID · 부모 세션 제거 · 폴더 분리
  3. **실패를 성공으로 취급하지 않는다** — 검증은 기존 검증기가 한다
  4. **끝난 단계는 건너뛴다** — 실패한 **단계**부터 재개
  5. **정상 실행의 Claude 세션은 정확히 셋** (6-F-9) — A 1 · B 1 · C 1

에이전트를 실제로 부르는 시험은 돈이 드므로, 여기서는 `run_agent` 를
가짜로 바꿔 **오케스트레이션**만 본다. 실제 `claude -p` 연동(stdin 입력 ·
`--tools ""` · `--append-system-prompt-file` · 봉투의 `result`)은 설치된
CLI 로 한 번 불러 확인했고 그 수치를 §1-45 에 적었다.
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
                  panelpacket, panelwork)

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
        self.season_matches = []
        self.source_status = {}


def opinion_obj(no=1, ids=()):
    return {"predicted_home": 2, "predicted_away": 1,
            "summary": f"{no}번 요약", "rationale": [f"{no}번 근거"],
            "evidence_ids": list(ids)}


def envelope(result: str, **extra) -> str:
    """`--output-format json` 봉투 한 장. **모델 출력은 `result` 한 칸**이다."""
    body = {"type": "result", "is_error": False, "result": result,
            "session_id": "sid", "num_turns": 1, "total_cost_usd": 0.1,
            "usage": {"input_tokens": 1, "output_tokens": 1}}
    body.update(extra)
    return json.dumps(body, ensure_ascii=False)


def stage_array(report, role=None) -> str:
    """회차 전체를 덮는 1·2단계 응답. 근거 ID 는 **그 경기의 것**을 쓴다."""
    rows = []
    for m in report.matches:
        ids = panel.build_panel_payload(m).evidence_ids
        row = opinion_obj(m.no, ids[:1])
        row[panelwork.STAGE_NO] = m.no
        rows.append(row)
    return json.dumps(rows, ensure_ascii=False)


def moderator_array(report) -> str:
    """회차 전체를 덮는 3단계 응답."""
    rows = []
    for m in report.matches:
        rows.append({
            panelwork.STAGE_NO: m.no, "simulations": 5,
            "distribution": [{"home": 1, "away": 1, "count": 5,
                              "origin": "compromise"}],
            "adopted_home": 1, "adopted_away": 1, "adopted_from": [],
            "conclusion": ("토론 결과 예상 스코어는 1-1 입니다. 표본이 "
                           "작습니다. 확정적이지 않습니다."),
            "common_points": ["표본이 작다"], "differences": [],
            "counterpoints": [], "uncertainty": ["표본 부족"],
            "evidence_ids": []})
    return json.dumps(rows, ensure_ascii=False)


def make_fake(report, record=None):
    """가짜 에이전트. **돈이 들지 않는다** — 단계에 맞는 배열을 돌려준다."""
    def fake(prompt, system, workspace, *, timeout=0, model="", cli="",
             env=None, stdin_text="", tools=panelauto.AGENT_TOOLS):
        is_mod = panelauto.MODERATOR_TAG in stdin_text
        stage = (panelauto.MODERATOR_DIR if is_mod
                 else (panel.MATCHUP_ANALYST
                       if "맞대결" in system else panel.DATA_ANALYST))
        body = moderator_array(report) if is_mod else stage_array(report)
        sid = f"sid-{len(record) + 1}" if record is not None else "sid"
        if record is not None:
            record.append({"stage": stage, "stdin": stdin_text,
                           "system": system, "prompt": prompt,
                           "tools": tools, "session": sid,
                           "ws": str(workspace)})
        Path(workspace).mkdir(parents=True, exist_ok=True)
        return panelauto.AgentRun(status=panelauto.AGENT_OK, session_id=sid,
                                  text=body, turns=1, cost_usd=0.1,
                                  usage={"input_tokens": 1,
                                         "output_tokens": 1})
    return fake


def fake_cli_runner(report, base: Path, sheet_dir: Path):
    """`run_existing_cli` 대역. **검증기는 진짜를 쓴다** — 저장 자리만 옮긴다.

    실제 CLI 를 부르면 저장소의 `panel_work/`·`reports/` 에 쓰므로 테스트가
    저장소를 더럽힌다. 그래서 인자를 읽어 같은 `panelwork` 함수를 부르되
    임시 폴더에 쓴다 — 실제 CLI 배선은 `test_l13` 이 AST 로 고정한다.
    """
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
                                                  outdir=sheet_dir)
            return 0 if res.success else 1
        if "--save-moderator-result" in argv:
            path = Path(argv[argv.index("--save-moderator-result") + 1])
            saved, res = panelwork.save_moderator_result(
                path.read_text(encoding="utf-8"), report, None, base)
            return 0 if saved is not None else 1
        if "--paste-panel-result" in argv:
            return 0
        raise AssertionError(f"모르는 CLI 호출: {argv}")
    return run


class patched:
    """`run_agent`·CLI 탐색·인증을 갈아 끼운다. **실제 모델을 부르지 않는다.**"""

    def __init__(self, run_agent=None, cli="/bin/true", existing_cli=None,
                 sheet_dir=None):
        self.run_agent, self.cli = run_agent, cli
        self.existing_cli, self.sheet_dir = existing_cli, sheet_dir
        self.saved = {}
        self.saved_round_dir = None

    def __enter__(self):
        from toto import panelexport
        for name in ("run_agent", "find_claude_cli", "cli_probe",
                     "auth_status", "run_existing_cli"):
            self.saved[name] = getattr(panelauto, name)
        if self.run_agent is not None:
            panelauto.run_agent = self.run_agent
        if self.existing_cli is not None:
            panelauto.run_existing_cli = self.existing_cli
        if self.sheet_dir is not None:
            self.saved_round_dir = panelexport.round_dir
            panelexport.round_dir = lambda round_id: self.sheet_dir
        if self.cli is not None:
            panelauto.find_claude_cli = lambda: self.cli
            panelauto.cli_probe = lambda exe, timeout=60: (True, "2.1.278", "")
            panelauto.auth_status = lambda exe, timeout=60: \
                panelauto.AuthStatus(state=panelauto.AUTH_OK, message="oauth")
        return self

    def __exit__(self, *exc):
        from toto import panelexport
        for name, value in self.saved.items():
            setattr(panelauto, name, value)
        if self.saved_round_dir is not None:
            panelexport.round_dir = self.saved_round_dir
        return False


def run_workflow(report, done=(), record=None, echo=None):
    """`run()` 을 가짜 에이전트로 끝까지 돌린다. **저장소를 건드리지 않는다.**"""
    base = scratch()
    sheet_dir = base / "export"
    sheet_dir.mkdir(parents=True, exist_ok=True)
    os.environ[panelauto.AUTO_ENV] = str(base / "auto")
    try:
        for key, role in ((panelwork.STAGE_A, panel.DATA_ANALYST),
                          (panelwork.STAGE_B, panel.MATCHUP_ANALYST)):
            if key in done:
                panelwork.save_stage(stage_array(report), role, report, base)
        with patched(run_agent=make_fake(report, record), cli="/bin/true",
                     existing_cli=fake_cli_runner(report, base, sheet_dir),
                     sheet_dir=sheet_dir):
            return panelauto.run(report.round_id, report, base=base,
                                 echo=echo or (lambda *a: None))
    finally:
        os.environ.pop(panelauto.AUTO_ENV, None)


def stage_calls(report, done=()):
    """가짜로 끝까지 돌린 뒤 **호출 목록**을 준다."""
    calls = []
    run_workflow(report, done=done, record=calls)
    return calls


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
    # **실물에서 온 문구 둘** (윈도우 260054). 같은 템플릿인데 가운데 낱말만
    # 다르다 — 낱말 하나씩 더하면 다음 표현에서 또 `failed` 로 떨어진다.
    for real in ("You've hit your session limit · resets 2:30am (Asia/Seoul)",
                 "You've hit your weekly limit · resets Sep 24, 9am (Asia/Seoul)"):
        assert panelauto._classify(real) == panelauto.AGENT_USAGE_LIMIT, real
    # 변하는 자리는 기간 낱말뿐이다 — 본 적 없는 낱말도 같은 모양이면 잡는다.
    for kind in ("daily", "monthly", "5-hour"):
        assert panelauto._classify(f"You've hit your {kind} limit") \
            == panelauto.AGENT_USAGE_LIMIT, kind
    # **모양이 아니면 잡지 않는다** — 낱말 둘이 따로 있는 것으로는 부족하다.
    for other in ("limit", "hit your head", "the limit of what you hit"):
        assert panelauto._classify(other) == panelauto.AGENT_FAILED, other
    assert panelauto.WORKFLOW_STOPPED_USAGE_LIMIT \
        == "WORKFLOW_STOPPED_USAGE_LIMIT"
    # 한도에서 멈출 때도 **보존·재개**를 말해 준다 — 재개가 가장 필요한
    # 자리인데 예전에는 실패 갈래에만 있었다.
    body = code_of(fn_node(panelauto, "_run_stages"))
    head, _, tail = body.partition("AGENT_USAGE_LIMIT")
    assert "보존" in tail.split("else")[0], "한도 갈래가 보존을 말하지 않는다"
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
    a = panelauto.stage_workspace("R", panel.DATA_ANALYST, base)
    b = panelauto.stage_workspace("R", panel.MATCHUP_ANALYST, base)
    c = panelauto.stage_workspace("R", panelauto.MODERATOR_DIR, base)
    assert len({a, b, c}) == 3
    assert not str(b).startswith(str(a))
    assert not str(a).startswith(str(b))


def test_b4_a_workspace_never_receives_b_output():
    """A 를 돌리면 B 폴더가 아예 생기지 않는다 (§9·§17)."""
    base, rep = scratch(), FakeReport(2)
    seen = []

    def fake(prompt, system, workspace, **kw):
        seen.append(Path(workspace))
        return panelauto.AgentRun(status=panelauto.AGENT_OK, session_id="s",
                                  text=stage_array(rep))

    with patched(run_agent=fake, cli=None,
                 existing_cli=fake_cli_runner(rep, base, base / "x")):
        panelauto.run_stage_analyst(rep, panel.DATA_ANALYST, base=base)
    a_root = panelauto.stage_workspace("TEST", panel.DATA_ANALYST, base)
    b_root = panelauto.stage_workspace("TEST", panel.MATCHUP_ANALYST, base)
    assert a_root.is_dir()
    assert not b_root.exists(), "A 를 돌렸는데 B 폴더가 생겼다"
    assert all(str(x).startswith(str(a_root)) for x in seen)


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
    """```json 울타리만 걷는다 — 설명문이 섞이면 검증기가 잡는다 (§17)."""
    rep = FakeReport(1)
    body = stage_array(rep)
    fenced, why = panelauto.parse_claude_result(
        envelope("```json\n" + body + "\n```"))
    assert fenced and not why, why
    # **울타리는 검증기가 걷는다** — 자동 경로가 따로 관대해지지 않는다.
    _ops, data, res = panelwork.parse_stage(fenced, panel.DATA_ANALYST, rep)
    assert data is not None, panelwork.report_lines(res)

    prose, why = panelauto.parse_claude_result(
        envelope("분석했습니다.\n" + body))
    assert prose.startswith("분석했습니다"), prose
    # 설명문은 고쳐 주지 않는다 — 그대로 검증기에 가서 떨어진다.
    _ops, data, res = panelwork.parse_stage(prose, panel.DATA_ANALYST, rep)
    assert data is None and res.errors


def test_c5_missing_output_is_its_own_state():
    """빈 응답·오류 봉투·읽을 수 없는 봉투가 **각각 사유를 남긴다** (§1-6-1)."""
    for raw, want in ((envelope(""), "빈 응답"),
                      ('{"is_error":true,"result":"boom"}', "boom"),
                      ("not json at all", "봉투")):
        text, why = panelauto.parse_claude_result(raw)
        assert not text and want in why, (raw[:30], why)


def test_c6_a_partial_round_is_not_success():
    """14경기 중 일부만 오면 **성공이 아니다** (§13)."""
    rep = FakeReport(3)
    rows = json.loads(stage_array(rep))[:2]
    _ops, data, res = panelwork.parse_stage(
        json.dumps(rows), panel.DATA_ANALYST, rep)
    assert data is None and res.errors
    assert any("STAGE_INCOMPLETE_ROUND" == i.code for i in res.errors)


def test_c7_failure_never_counts_as_success():
    """검증에 실패하면 그 단계는 실패다 — 다음 단계로 가지 않는다 (§17)."""
    base, rep = scratch(), FakeReport(2)
    bad = json.dumps([{"match_no": 1, "predicted_home": "둘"}])

    def fake(prompt, system, workspace, **kw):
        return panelauto.AgentRun(status=panelauto.AGENT_OK, text=bad)

    with patched(run_agent=fake, cli=None,
                 existing_cli=fake_cli_runner(rep, base, base / "x")):
        res = panelauto.run_stage_analyst(rep, panel.DATA_ANALYST, base=base)
    assert not res.ok
    assert res.status == panelauto.AGENT_INVALID
    assert res.matches == 0


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
# D. 재개 — **단계가 checkpoint 다** (6-F-9 §11)
#
#    6-F-8 까지는 경기 하나가 checkpoint 였다. 6-F-9 는 단계 하나가 호출
#    하나이므로 경기 단위 재개가 없다 — 지키려는 것(끝난 것을 다시 돌리지
#    않는다 · 깨진 것을 끝난 것으로 보지 않는다)은 그대로이고 단위만 옮겼다.
# ==========================================================================
def test_d1_completed_stage_is_skipped():
    """이미 보관된 단계는 **부르지 않는다**."""
    rep = FakeReport(2)
    calls = stage_calls(rep, done=(panelwork.STAGE_A,))
    assert [c["stage"] for c in calls] == [panel.MATCHUP_ANALYST,
                                           panelauto.MODERATOR_DIR], calls
    assert len(calls) == 2, "완료된 A 를 다시 불렀다"


def test_d2_per_match_checkpoints_are_gone():
    """경기 단위 재개 구조를 만들지 않는다 (§2·§11).

    `run_match_role`·`collect_stage`·`match_workspace` 가 없어야 하고,
    번호를 폴더 이름으로 쓰는 구조도 없어야 한다.
    """
    for gone in ("run_match_role", "collect_stage", "match_workspace",
                 "_completed", "_read_output"):
        assert not hasattr(panelauto, gone), f"{gone} 이 남아 있다"
    code = module_code(panelauto)
    for bad in ('f"{no:02d}"', "for match in report.matches",
                "for i, match in enumerate"):
        assert bad not in code, f"경기별 루프가 남아 있다: {bad}"


def test_d3_resume_starts_at_the_failed_stage():
    """앞 단계는 보존하고 실패한 **단계**부터 재개한다."""
    rep = FakeReport(2)
    calls = stage_calls(rep, done=(panelwork.STAGE_A, panelwork.STAGE_B))
    assert [c["stage"] for c in calls] == [panelauto.MODERATOR_DIR], calls


def test_d4_a_failed_stage_stops_the_workflow():
    """한 단계가 실패하면 뒤 단계를 시작하지 않는다 (§11)."""
    rep = FakeReport(2)

    calls = []

    def fake(prompt, system, workspace, **kw):
        calls.append(1)
        return panelauto.AgentRun(status=panelauto.AGENT_FAILED,
                                  message="일부러 실패")

    base = scratch()
    os.environ[panelauto.AUTO_ENV] = str(base / "auto")
    try:
        with patched(run_agent=fake, cli="/bin/true",
                     existing_cli=fake_cli_runner(rep, base, base / "x")):
            out = panelauto.run("TEST", rep, base=base,
                                echo=lambda *a: None)
    finally:
        os.environ.pop(panelauto.AUTO_ENV, None)
    assert not out.ok
    assert len(calls) == 1, "A 가 실패했는데 B·C 를 불렀다"


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
    """에이전트에게 **도구를 하나도 주지 않는다** (6-F-9 §15 금지 2·5·7).

    6-F-8 까지는 `--allowedTools "Read,Write"` 였는데 그것은 *자동승인*
    목록일 뿐이라 Bash 가 여전히 돌았다 — 실행 기록에서 실제로 `cat` 을
    실행했다. 실제 제한은 `--tools` 다.
    """
    assert panelauto.AGENT_TOOLS == ""
    argv = panelauto.agent_argv("claude", "p", "s", Path("/w"), "sid")
    assert "--allowedTools" not in argv, "자동승인 목록을 제한으로 착각한다"
    assert argv[argv.index("--tools") + 1] == ""


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
    node = fn_node(panelauto, "round_data_sheets")
    assert "panelexport.data_sheet" in calls_in(node)
    assert "panel.build_panel_payload" in calls_in(node)
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
    body = code_of(fn_node(panelauto, "pack_moderator_data"))
    assert "COMPLETED_SHEET" in body
    for bad in ("pack_round_data", "data_sheet", "build_panel_payload"):
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
    std = {"json", "os", "shutil", "signal", "subprocess", "tempfile", "uuid",
           "dataclasses", "pathlib", "__future__", "toto", "models",
           "moderator", "panel", "panelexport", "panelpacket", "panelwork",
           "artifact",
           "settings", "cli", "llm", "annotations", "dataclass", "field",
           "Path", "Report", "main", "load_settings", "ROOT"}
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
    for fn in ("run_stage_analyst", "run_stage_moderator", "_run_stage",
               "agent_argv"):
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
    """BOM 을 견디고, 깨진 인코딩은 **그 단계의 사유**가 된다 (§2-3).

    6-F-9 에서 자료는 stdin·stdout 으로 오가지만, `03_사회자자료_완성.md`
    는 여전히 파일이고 사용자가 윈도우 편집기로 열었다 저장하면 BOM 이
    붙는다. 봉투 파일도 마찬가지다.
    """
    tmp = scratch()
    env = tmp / panelauto.AGENT_ENVELOPE
    env.write_text(envelope('[{"match_no":1}]'), encoding="utf-8-sig")
    text, why = panelauto.parse_claude_result(
        env.read_text(encoding="utf-8-sig"))
    assert text and not why, why

    bad = scratch() / panelauto.AGENT_ENVELOPE
    bad.write_bytes('{"result":"한글"}'.encode("cp949"))
    # 예외가 아니라 사유여야 한다.
    raw = bad.read_text(encoding="utf-8", errors="replace")
    text, why = panelauto.parse_claude_result(raw)
    assert (text or why), "아무 말도 하지 않았다"


def test_h13_korean_and_spaced_paths_work():
    """`C:\\…\\축구토토 분석\\…` 같은 경로에서도 돈다 (§2-3).

    인자는 리스트로 넘기고 `shell=False` 라 공백이 쪼개지지 않는다.
    """
    root = scratch() / "축구토토 분석" / "panel work"
    ws = panelauto.stage_workspace("260052", panel.DATA_ANALYST, base=root)
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
    assert "✓" in code_of(fn_node(panelauto, "_run_stages"))


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
    for bad in ("run_agent", "run_stage_analyst", "run_stage_moderator",
                "run", "_run_stages", "_run_stage"):
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


# ==========================================================================
# K. 명령줄에 줄바꿈을 싣지 않는다 (6-F-7 후속 · 실물 윈도우 실패)
#
#    실물에서 `[2/5] 데이터 분석 A → 01/14 ✗ 종료코드 1` 로 멈췄다.
#    윈도우의 실제 계층은 `python → claude.CMD → cmd.exe → node.exe` 이고,
#    `cmd.exe` 는 명령줄을 **한 줄로** 읽는다. 그런데 이 명령줄에는 시스템
#    프롬프트 때문에 줄바꿈이 **54~93개** 실려 있었다 (실측).
# ==========================================================================
def _real_argv(role: str, ws: Path) -> list:
    """실물 프롬프트로 만든 명령줄. 합성 문자열로 재지 않는다."""
    prompt = (panelauto.analyst_prompt(14) if role != panelauto.MODERATOR_DIR
              else panelauto.moderator_prompt(14))
    return panelauto.agent_argv("claude.CMD", prompt,
                                ws / panelauto.AGENT_SYSTEM, ws, "sid",
                                "sonnet")


def test_k1_no_argument_carries_a_newline():
    """어떤 인자에도 줄바꿈이 없다 — `cmd.exe` 가 거기서 명령을 끊는다."""
    ws = Path("C:/Users/x/sh4/panel_work/260054/auto/a/01")
    for role in panel.ROLES:
        for arg in _real_argv(role, ws):
            assert "\n" not in arg and "\r" not in arg, \
                f"{role}: 줄바꿈이 실린 인자 {arg[:60]!r}"


def test_k2_the_system_prompt_goes_as_a_file():
    """시스템 프롬프트를 인자로 싣지 않는다 — 파일 경로로 넘긴다."""
    ws = Path("/w/a/01")
    argv = _real_argv(panel.DATA_ANALYST, ws)
    assert "--append-system-prompt" not in argv, "인라인으로 싣고 있다"
    assert "--append-system-prompt-file" in argv
    path = argv[argv.index("--append-system-prompt-file") + 1]
    assert path == str(ws / panelauto.AGENT_SYSTEM), path
    # 그 파일은 작업 폴더 안이라 `--add-dir` 범위를 넓히지 않는다 (§19).
    assert str(ws) in path


def test_k3_the_prompt_argument_is_cmd_safe():
    """`-p` 인자에 `cmd.exe` 가 해석하는 글자를 싣지 않는다.

    따옴표 안이어도 `%VAR%` 는 확장되고 줄바꿈은 명령을 끊는다.
    """
    argv = _real_argv(panel.DATA_ANALYST, Path("/w"))
    prompt = argv[argv.index("-p") + 1]
    for bad in ("\n", "\r", "%"):
        assert bad not in prompt, f"{bad!r} 가 실렸다"


def test_k4_one_line_keeps_every_word():
    """한 줄로 만들되 **낱말은 하나도 버리지 않는다.**"""
    src = "첫 줄\r\n\r\n  가운데 줄  \n끝 줄\n"
    got = panelauto.one_line(src)
    assert got == "첫 줄 가운데 줄 끝 줄", repr(got)
    for text in (panelauto.analyst_prompt(14),
                 panelauto.moderator_prompt(14),
                 panel.SYSTEM_COMMON):
        assert panelauto.one_line(text).split() == text.split()


def test_k5_the_system_text_itself_is_unchanged():
    """모델에게 가는 시스템 프롬프트 **글자는 그대로다.**

    자리를 인자에서 파일로 옮겼을 뿐이다 — 프롬프트 판이 바뀌지 않는다.
    """
    ws = scratch() / "a" / "01"
    ws.mkdir(parents=True)
    system = panel.SYSTEM_COMMON + "\n\n" \
        + panel.ROLE_PROMPTS[panel.MATCHUP_ANALYST]
    cli = fake_cli(scratch(), "printf '{\"result\":\"DONE\"}'\n")
    run = panelauto.run_agent("지시", system, ws, timeout=60, cli=str(cli))
    assert run.ok, (run.status, run.message)
    got = (ws / panelauto.AGENT_SYSTEM).read_text(encoding="utf-8")
    assert got == system, "시스템 프롬프트가 달라졌다"
    assert panel.PANEL_PROMPT_VERSION == "4"
    assert moderator.MODERATOR_PROMPT_VERSION == "6"


def test_k6_non_json_stdout_is_not_swallowed():
    """JSON 이 아닌 stdout 을 버리지 않는다 (§1-6-1).

    예전에는 `result` 칸만 읽고 나머지를 버려서, CLI 가 낸 오류가 화면에서
    `종료코드 1` 한 줄로 뭉개졌다 — 실물 윈도우에서 정확히 그랬다.
    """
    ws = scratch() / "a" / "01"
    ws.mkdir(parents=True)
    cli = fake_cli(scratch(),
                   "printf \"error: unknown option '--zzz'\\n\"; exit 1\n")
    run = panelauto.run_agent("지시", "시스템", ws, timeout=60, cli=str(cli))
    assert not run.ok
    assert "unknown option" in run.message, run.message
    assert (ws / panelauto.AGENT_ENVELOPE).read_text(
        encoding="utf-8").strip().startswith("error:")


def test_k7_empty_output_says_so_and_points_at_the_envelope():
    """정말 아무 출력도 없으면 **그렇다고 적고** 봉투 자리를 알려 준다."""
    ws = scratch() / "a" / "01"
    ws.mkdir(parents=True)
    cli = fake_cli(scratch(), "exit 1\n")
    run = panelauto.run_agent("지시", "시스템", ws, timeout=60, cli=str(cli))
    assert not run.ok
    assert "종료코드 1" in run.message
    assert "비었습니다" in run.message, run.message
    assert panelauto.AGENT_ENVELOPE in run.message, run.message


# ==========================================================================
# L. 3세션 배치 (Phase 6-F-9 · CLAUDE.md §1-45)
#
#    6-F-8 까지는 경기마다 세션을 열어 A 14 + B 14 + C 1 = 29회를 불렀다.
#    실측하면 경기 하나에 7턴 · 입력 487,563토큰이 들었고 그 79%가 같은
#    내용의 재전송이었으며, 작업 폴더가 저장소 안이라 호출마다 `CLAUDE.md`
#    197,275자(≈94,480토큰)가 함께 실렸다. 사람이 채팅에서 하는 것은
#    대화 셋이므로, 자동 경로도 셋으로 맞춘다.
# ==========================================================================
def test_l1_exactly_three_sessions():
    """정상 실행의 Claude 세션은 **정확히 셋**이다 (§0·§10·§22)."""
    rep = FakeReport(3)
    calls = stage_calls(rep)
    assert len(calls) == panelauto.EXPECTED_SESSIONS == 3, [
        c["stage"] for c in calls]
    assert [c["stage"] for c in calls] == [
        panel.DATA_ANALYST, panel.MATCHUP_ANALYST, panelauto.MODERATOR_DIR]
    # 세션 ID 가 호출마다 다르다 — 이어 붙이지 않는다 (§17).
    assert len({c["session"] for c in calls}) == 3


def test_l2_no_per_match_session():
    """경기 수가 늘어도 세션 수는 그대로다 (§2)."""
    for n in (2, 5, 9):
        calls = stage_calls(FakeReport(n))
        assert len(calls) == 3, f"{n}경기에 세션 {len(calls)}개"


def test_l3_analysts_compare_the_same_facts():
    """A·B 가 **같은 정량 사실**을 받는다 (3-B 불변조건 2).

    6-F-10 이 역할별 packet 을 넣으면서 이 단언의 범위를 옮겼다 — 예전에는
    "두 stdin 이 글자까지 같다" 였는데, 그 조항이 지키려는 것은
    "역할별 payload 를 만들면 두 의견이 **비교 불가능**해진다" 이고 비교되는
    것은 정량 사실이다. 그래서 **정량 본체가 바이트까지 같은지**를 본다
    (§1-29·§1-31·§1-42 와 같은 교정).
    """
    rep = FakeReport(3)
    calls = stage_calls(rep)
    a, b = json.loads(calls[0]["stdin"]), json.loads(calls[1]["stdin"])
    assert a["legend"] == b["legend"]
    core = [k for k in panelpacket.ROLE_VIEWS[panel.DATA_ANALYST]]
    for ra, rb in zip(a["data"], b["data"]):
        for key in core:
            assert ra.get(key) == rb.get(key), f"{key} 가 역할마다 다르다"
    # 자료를 고르는 규칙은 **한 곳**에 있다 — panelauto 가 칸을 더하지 않는다.
    body = code_of(fn_node(panelauto, "role_packet_text"))
    assert "panelpacket" in body
    for bad in ("evidence", "qualitative", "metrics"):
        assert bad not in body, f"role_packet_text 가 {bad} 를 직접 만진다"


def test_l4_b_never_sees_a_result():
    """B 의 입력에 A 결과가 **한 글자도** 없다 (§6·§15 금지 3)."""
    rep = FakeReport(3)
    calls = stage_calls(rep)
    a_result = calls[0]["stdin"]            # A 가 받은 것은 자료뿐이다
    b = calls[1]
    # A 가 **내놓은** 값이 B 의 stdin 에 없다.
    for row in json.loads(stage_array(rep)):
        assert row["summary"] not in b["stdin"], "B 가 A 의 요약을 봤다"
        for note in row["rationale"]:
            assert note not in b["stdin"], "B 가 A 의 근거를 봤다"
    for bad in (panelauto.ANALYST_A_TAG, "analyst_a", "analyst_b"):
        for where in ("stdin", "system", "prompt"):
            assert bad not in b[where], f"B 의 {where} 에 {bad} 가 있다"
    # 받은 정량 자료는 A 와 같다 (test_l3) — 다른 것은 역할 지침과
    # 정성 자료뿐이고, 어느 쪽도 A 의 **결과**가 아니다.
    assert json.loads(b["stdin"])["legend"] == json.loads(a_result)["legend"]
    assert b["system"] != calls[0]["system"]
    # 코드에도 경로가 없다.
    body = code_of(fn_node(panelauto, "run_stage_analyst"))
    assert "load_stage" not in body and "collect_opinions" not in body



def test_l5_moderator_gets_no_match_data():
    """C 는 경기자료 7개를 다시 받지 않는다 (§7·§15 금지 4)."""
    rep = FakeReport(3)
    calls = stage_calls(rep)
    c = calls[2]["stdin"]
    assert "<panel_payload" not in c, "C 에 경기자료가 들어갔다"
    assert panelauto.MODERATOR_TAG in c
    assert panelauto.ANALYST_A_TAG in c and panelauto.ANALYST_B_TAG in c
    # C 는 packet 도 받지 않는다 — A·B 의 **결과**와 사회자 자료뿐이다.
    assert "how_to_read" not in c and '"legend"' not in c


def test_l6_the_agent_never_reads_or_writes_files():
    """자료는 Python 이 읽고 결과는 Python 이 쓴다 (§4·§15 금지 5·7)."""
    rep = FakeReport(2)
    calls = stage_calls(rep)
    for c in calls:
        assert c["tools"] == "", f"{c['stage']} 에 도구를 줬다"
        assert c["stdin"], f"{c['stage']} 에 stdin 이 비었다"
        # 지시문이 파일을 읽거나 쓰라고 말하지 않는다.
        for bad in ("Read", "Write", "payload.md", "out.json", "작업 폴더의"):
            assert bad not in c["prompt"], f"{c['stage']} 지시문에 {bad}"
    code = module_code(panelauto)
    assert "AGENT_OUTPUT" not in code, "에이전트가 쓸 파일 이름이 남아 있다"


def test_l7_round_data_is_not_rewritten():
    """원문을 요약하거나 변형하지 않는다 (§16).

    붙는 것은 회차 표시와 파일 머리표뿐이고, 시트 본문은
    `panelexport.data_sheet()` 가 만든 것 그대로다.
    """
    rep = FakeReport(4)
    packed = panelauto.pack_round_data(rep)
    sheets = panelauto.round_data_sheets(rep)
    assert sheets, "시트가 하나도 없다"
    for sheet in sheets:
        assert sheet in packed, "시트 본문이 손대졌다"
    assert packed.count("<FILE:") == len(sheets)
    assert packed.startswith(panelauto.ROUND_TAG.format(round=rep.round_id))
    # 자료 전체가 payload 를 하나도 빠뜨리지 않는다.
    for m in rep.matches:
        pl = panel.build_panel_payload(m)
        assert panel.serialize_payload(pl) in packed, f"{m.no}번이 빠졌다"


def test_l8_packing_is_deterministic():
    """같은 회차면 같은 글자가 나온다 — 집합·사전 순서에 기대지 않는다."""
    rep = FakeReport(3)
    assert panelauto.pack_round_data(rep) == panelauto.pack_round_data(rep)


def test_l9_role_prompts_are_split_per_stage():
    """공통 규칙과 역할 규칙을 나누고 **그 단계에만** 싣는다 (§3·§8·§9·§15 금지 6)."""
    ws = scratch()
    a = panelauto.stage_system(ws, panel.DATA_ANALYST)
    b = panelauto.stage_system(ws, panel.MATCHUP_ANALYST)
    c = panelauto.stage_system(ws, panelauto.MODERATOR_DIR)
    names = {p.name for p in ws.iterdir()}
    assert panelauto.COMMON_FILE in names
    assert panelauto.ROLE_PROMPT_FILES[panel.DATA_ANALYST] in names
    assert panelauto.MODERATOR_PROMPT_FILE in names

    assert a == panel.SYSTEM_COMMON + "\n\n" + panel.ROLE_PROMPTS[
        panel.DATA_ANALYST]
    assert b == panel.SYSTEM_COMMON + "\n\n" + panel.ROLE_PROMPTS[
        panel.MATCHUP_ANALYST]
    # 남의 역할 지침이 섞이지 않는다.
    assert panel.ROLE_PROMPTS[panel.MATCHUP_ANALYST] not in a
    assert panel.ROLE_PROMPTS[panel.DATA_ANALYST] not in b
    assert panel.ROLE_PROMPTS[panel.DATA_ANALYST] not in c


def test_l10_role_files_are_generated_not_copied():
    """지침을 저장소에 베껴 두지 않는다 (§1-11-1 · §8).

    내용은 전부 코드 상수에서 온다 — 손으로 적은 사본이 있으면 채팅 판과
    자동 판이 조용히 갈라진다.
    """
    node = fn_node(panelauto, "write_prompt_files")
    names = calls_in(node)
    assert "moderator.system_prompt" in names
    body = code_of(node)
    assert "panel.SYSTEM_COMMON" in body and "panel.ROLE_PROMPTS" in body
    # 저장소에 사본 파일이 생기지 않는다.
    assert not Path("toto/../.claude/panel").exists()
    src = source_of(panelauto)
    for line in panel.SYSTEM_COMMON.splitlines():
        line = line.strip()
        if len(line) > 25:
            assert line not in src, f"프롬프트를 베꼈다: {line[:40]}"


def test_l11_workspace_lives_outside_the_repository():
    """작업 폴더가 저장소 밖이다 — `CLAUDE.md` 자동 주입을 끊는다 (§3)."""
    from toto.settings import ROOT
    got = panelauto.auto_dir("260052")
    assert ROOT not in got.parents and got != ROOT, got
    assert str(got).startswith(tempfile.gettempdir()), got
    # 탈출구가 있다.
    had = os.environ.get(panelauto.AUTO_ENV)
    os.environ[panelauto.AUTO_ENV] = "/elsewhere"
    try:
        assert str(panelauto.auto_dir("R")).startswith("/elsewhere")
    finally:
        os.environ.pop(panelauto.AUTO_ENV, None)
        if had is not None:
            os.environ[panelauto.AUTO_ENV] = had


def test_l12_data_goes_by_stdin_not_by_argv():
    """자료가 명령줄에 실리지 않는다 (§4 · 6-F-7 K절과 같은 이유)."""
    rep = FakeReport(3)
    packed = panelauto.pack_round_data(rep)
    argv = _real_argv(panel.DATA_ANALYST, Path("/w"))
    joined = " ".join(str(x) for x in argv)
    assert packed[:200] not in joined
    assert len(joined) < 2000, f"명령줄이 {len(joined)}자다"
    # `run_agent` 가 stdin 을 실제로 파이프로 넘긴다.
    body = code_of(fn_node(panelauto, "run_agent"))
    assert "stdin_text" in body and "subprocess.PIPE" in body
    assert "input=stdin_text" in body


def test_l13_validation_reuses_the_existing_path():
    """검증기를 새로 쓰지 않는다 (§13).

    1·2단계는 `--save-panel-opinion`(= `panelwork.save_stage`), 3단계는
    `--save-moderator-result` 를 지난다 — 수동 경로와 같은 문이다.
    """
    body = (code_of(fn_node(panelauto, "run_stage_analyst")) + "\n"
            + code_of(fn_node(panelauto, "run_stage_moderator")) + "\n"
            + code_of(fn_node(panelauto, "_run_stage")))
    assert "--save-panel-opinion" in body
    assert "--save-moderator-result" in body
    assert "run_existing_cli" in body
    # 스키마 검사를 여기서 다시 적지 않는다.
    for bad in ("parse_result", "panelimport.validate", "panelpaste.convert"):
        assert bad not in body, f"검증을 다시 구현한다: {bad}"


def test_l14_result_is_saved_atomically_and_only_when_valid():
    """깨진 결과가 정상 결과를 덮어쓰지 않는다 (§12).

    원자적 저장과 "통과한 것만 쓴다" 는 `panelwork` 가 이미 한다 —
    두 벌로 두지 않고 그것을 쓴다.
    """
    rep = FakeReport(2)
    good = stage_array(rep)
    base = scratch()
    res = panelwork.save_stage(good, panel.DATA_ANALYST, rep, base)
    assert res.success, panelwork.report_lines(res)
    path = panelwork.path_for(rep.round_id, panel.DATA_ANALYST, base)
    keep = path.read_text(encoding="utf-8")

    bad = panelwork.save_stage("[{\"match_no\":1}]", panel.DATA_ANALYST,
                               rep, base)
    assert not bad.success
    assert path.read_text(encoding="utf-8") == keep, "깨진 결과가 덮어썼다"
    body = code_of(fn_node(panelwork, "save_stage"))
    assert "os.replace" in body


def test_l15_stage_logs_are_stage_shaped():
    """로그가 **경기가 아니라 단계** 중심이다 (§21)."""
    rep = FakeReport(3)
    lines = []
    out = run_workflow(rep, echo=lines.append)
    assert out.ok, out.stopped_reason
    text = "\n".join(lines)
    for want in ("[1/3]", "[2/3]", "[3/3]", "Data Analyst",
                 "Matchup Analyst", "Moderator", "Claude session started",
                 "Claude session completed", "result validated: 3/3",
                 "Panel completed", "Claude sessions: 3"):
        assert want in text, f"로그에 {want!r} 이 없다"
    # 경기별 진행 줄이 없다.
    assert "01/3" not in text and "01/14" not in text


def test_l16_context_overflow_is_its_own_state():
    """문맥 초과를 한도·인증과 **다른 상태**로 적는다 (§1-6).

    둘은 사용자가 할 일이 정반대다 — 한도는 기다리는 것이고 문맥 초과는
    자료를 줄이거나 나누는 것이다.
    """
    assert panelauto._classify("prompt is too long: 900000 tokens") \
        == panelauto.AGENT_TOO_LARGE
    assert panelauto._classify("exceeds the maximum context window") \
        == panelauto.AGENT_TOO_LARGE
    # 한도·인증 판정은 그대로다.
    assert panelauto._classify("You've hit your weekly limit") \
        == panelauto.AGENT_USAGE_LIMIT
    assert panelauto._classify("not logged in") == panelauto.AGENT_AUTH
    assert panelauto._classify("무슨 일인지 모르겠다") == panelauto.AGENT_FAILED


def test_l17_preflight_reports_the_round_size():
    """회차 자료가 얼마나 큰지 **시작 전에** 적는다 (§1-6-1).

    14경기를 한 문맥에 넣으므로, 들어가는지를 돌려 보고 알게 하면 안 된다.
    """
    rep = FakeReport(3)
    with patched(cli="/bin/true"):
        pre = panelauto.preflight(rep, "TEST", scratch())
    assert pre.chars > 0 and pre.tokens > 0
    assert pre.chars == len(panelauto.pack_round_data(rep))
    assert any("토큰" in n and "회차 원본" in n for n in pre.notes), pre.notes
    # 6-F-10 부터는 **실제로 나갈 packet** 도 함께 잰다.
    assert any("packet" in n for n in pre.notes), pre.notes


def test_l18_the_safety_devices_survived():
    """6-F-6~8 의 안전장치를 그대로 유지한다 (§18·§19·§22)."""
    code = module_code(panelauto)
    for want in ("SCRUB_API", "SCRUB_SESSION", "_kill_tree", "_spawn_kwargs",
                 "AGENT_USAGE_LIMIT", "AUTH_API_KEY", "cli_probe",
                 "auth_status", "KeyboardInterrupt"):
        assert want in code, f"{want} 가 사라졌다"
    assert "--bare" not in code
    argv = panelauto.agent_argv("claude", "p", "s", Path("/w"), "sid")
    for bad in ("--bare", "--continue", "--resume", "--allow-dangerously-"
                "skip-permissions"):
        assert bad not in argv, f"{bad} 를 넘긴다"


# ==========================================================================
# M. 역할별 compact packet (Phase 6-F-10 · CLAUDE.md §1-46)
#
#    6-F-9 가 세션을 셋으로 줄였지만 A·B 는 회차 원본 전체(실측 1,746,547자
#    ≈ 836,470토큰)를 그대로 받았다. 이 절은 그 사이에 들어간 deterministic
#    전처리가 **자료를 한 칸도 잃지 않으면서** 반복을 걷어내는지 본다.
# ==========================================================================
def real_index():
    """실물 260052 저장본으로 색인을 만든다. 없으면 건너뛴다."""
    from toto import artifact
    report, _why = artifact.load("260052")
    if report is None:
        return None
    return panelpacket.build_panel_index(report)


def demo_index(n=3):
    return panelpacket.build_panel_index(FakeReport(n))


def test_m1_index_identifies_every_match():
    """색인이 경기 1~N 을 식별한다 (§5)."""
    rep = FakeReport(4)
    idx = panelpacket.build_panel_index(rep)
    assert idx.matches == 4
    assert [e.match_no for e in idx.entries] == [1, 2, 3, 4]
    for e in idx.entries:
        assert idx.by_no(e.match_no) is e
        assert e.home and e.away
        assert e.payload is not None
        assert any(p.endswith(".home") for p in e.source_paths)  # §20
    assert idx.by_no(99) is None
    # 축까지 있는 실물에서는 축 자리도 기록된다.
    real = real_index()
    if real is not None:
        first = real.entries[0]
        assert any(".home.time_context" in p for p in first.source_paths)
        assert first.evidence_ids


def test_m2_packet_carries_every_match():
    """packet 에 14경기가 전부 들어간다 — 나누지 않는다 (§15·§33)."""
    idx = demo_index(4)
    for role in panelpacket.ROLE_VIEWS:
        pk = panelpacket.build_analyst_packet(idx, role)
        assert pk["matches"] == 4
        assert [r["match_no"] for r in pk["data"]] == [1, 2, 3, 4]


def test_m3_folding_is_lossless():
    """legend 는 **버리는 것이 아니라 가리키는 것**이다 (§2 원칙 1).

    되풀면 원본과 글자까지 같아야 한다 — 실물로 확인한다.
    """
    idx = real_index() or demo_index(3)
    pk = panelpacket.build_analyst_b_packet(idx)
    legend, checked = pk["legend"], 0
    for entry, row in zip(idx.entries, pk["data"]):
        for key in ("home", "away", "data_quality"):
            if key not in row:
                continue
            back = panelpacket._restore(key, row[key], legend)
            assert back == entry.body[key], f"{entry.match_no}번 {key} 가 달라졌다"
            checked += 1
    assert checked >= 6, checked


def test_m4_every_evidence_id_survives():
    """근거는 **경기마다** 전부 보존된다 (§3).

    ID 만 모으면 14경기의 E001 이 한 건으로 뭉쳐 보존률이 부풀려지므로
    `(경기, ID)` 쌍으로 센다.
    """
    idx = real_index() or demo_index(3)
    for role in panelpacket.ROLE_VIEWS:
        rep = panelpacket.audit(idx, role)
        assert not rep["evidence_missing"], rep["evidence_missing"][:5]
        assert not rep["evidence_invented"], rep["evidence_invented"][:5]
        assert rep["evidence_packet"] == rep["evidence_source"]
    # 근거의 메타데이터도 그대로다.
    pk = panelpacket.build_analyst_a_packet(idx)
    for entry, row in zip(idx.entries, pk["data"]):
        assert list(row.get("evidence") or ()) == list(entry.body["evidence"])


def test_m5_nothing_is_invented():
    """packet 에 원본에 없던 자리가 생기지 않는다 (§21 · §2 원칙 2)."""
    idx = real_index() or demo_index(3)
    for role in panelpacket.ROLE_VIEWS:
        rep = panelpacket.audit(idx, role)
        assert not rep["added_paths"], rep["added_paths"][:5]


def test_m6_no_new_statistics():
    """고르고 다시 배열할 뿐 **계산하지 않는다** (§2 원칙 2 · §6).

    자료를 만지는 함수에 산술이 없어야 한다. 크기를 재는 함수(`measure`·
    `estimate_tokens`)는 자료가 아니라 문자 수를 다루므로 대상이 아니다.
    """
    for name in ("_pack_axis", "_pack_side", "_pack_quality",
                 "build_analyst_packet", "build_panel_index"):
        node = fn_node(panelpacket, name)
        for n in ast.walk(node):
            assert not isinstance(n, (ast.BinOp, ast.AugAssign)), \
                f"{name} 에 산술이 있다"
        names = calls_in(node)
        for bad in ("sum", "round", "mean", "sorted_by_value", "max", "min"):
            assert bad not in names, f"{name} 이 {bad} 를 쓴다"
    code = module_code(panelpacket)
    for bad in ("strength_score", "balance_index", "attack_defense",
                "_rating", "_ranking", "composite", "percentile"):
        assert bad not in code, f"{bad} 라는 파생값을 만든다"


def test_m7_the_quantitative_core_is_identical_for_both_roles():
    """**두 역할의 정량 본체가 바이트까지 같다** (§1-9 불변조건 2 의 실질).

    그 조항이 지키려는 것은 "두 의견이 비교 가능해야 한다" 이고, 비교되는
    것은 정량 사실이다. 그래서 축 지표·근거·data_quality·시장 기준선·
    legend 가 같은지를 직접 본다.
    """
    idx = real_index() or demo_index(3)
    a = panelpacket.build_analyst_a_packet(idx)
    b = panelpacket.build_analyst_b_packet(idx)
    assert a["legend"] == b["legend"], "legend 가 갈렸다"
    core = ("match_no", "league", "home_team", "away_team", "kickoff_kst",
            "as_of", "home", "away", "evidence", "conflicts",
            "data_quality", "market_reference")
    for ra, rb in zip(a["data"], b["data"]):
        for key in core:
            assert ra.get(key) == rb.get(key), f"{key} 가 역할마다 다르다"


def test_m8_the_only_role_difference_is_documented():
    """역할 차이는 **하나뿐이고 표에 적혀 있다** (§7·§8)."""
    va = set(panelpacket.ROLE_VIEWS[panel.DATA_ANALYST])
    vb = set(panelpacket.ROLE_VIEWS[panel.MATCHUP_ANALYST])
    assert vb - va == {"qualitative"}, vb - va
    assert not va - vb, va - vb
    # 맞대결 분석가의 프롬프트가 실제로 그 칸을 쓴다.
    assert "qualitative" in panel.ROLE_PROMPTS[panel.MATCHUP_ANALYST]
    assert "qualitative" not in panel.ROLE_PROMPTS[panel.DATA_ANALYST]
    # 실제 packet 에도 그대로 나타난다.
    idx = demo_index(2)
    a = panelpacket.build_analyst_a_packet(idx)
    b = panelpacket.build_analyst_b_packet(idx)
    assert all("qualitative" not in r for r in a["data"])
    assert any("qualitative" in r for r in b["data"])


def test_m9_measurement_has_no_hardcoded_target():
    """목표 토큰 수를 코드에 박지 않는다 (§4)."""
    idx = demo_index(3)
    stats = panelpacket.measure(idx)
    assert stats["source_chars"] > 0 and stats["matches"] == 3
    for role in panelpacket.ROLE_VIEWS:
        row = stats["roles"][role]
        assert row["chars"] > 0 and row["tokens"] > 0
        # 실제 문자 수에서 나온 값이다.
        text = panelpacket.packet_text(
            panelpacket.build_analyst_packet(idx, role))
        assert row["chars"] == len(text)
    code = module_code(panelpacket)
    for bad in ("150000", "150_000", "200000", "200_000", "target_tokens"):
        assert bad not in code, f"목표치 {bad} 를 박았다"
    # 어림이라는 것을 화면에 적는다 (§17).
    assert any("예상" in line for line in panelpacket.report_lines(stats))


def test_m10_suspiciously_small_packets_are_flagged():
    """토큰이 줄었다는 것 **자체를 성공으로 치지 않는다** (§32)."""
    idx = demo_index(2)
    ok = panelpacket.measure(idx)
    assert not panelpacket.too_small(ok), panelpacket.too_small(ok)
    tiny = {"round": "T", "matches": 2, "source_chars": 1_000_000,
            "source_tokens": 500_000,
            "roles": {panel.DATA_ANALYST: {"chars": 8_000, "tokens": 4_000,
                                           "reduction": 0.992}}}
    flags = panelpacket.too_small(tiny)
    assert flags and panelpacket.PACKET_TOO_SMALL in flags[0]
    # preflight 가 그것을 problems 로 올린다 — 시작하지 않는다.
    body = code_of(fn_node(panelauto, "preflight"))
    assert "too_small" in body


def test_m11_analysts_receive_packets_not_the_raw_round():
    """A·B 의 stdin 이 **원본 전체가 아니다** (§0·§28)."""
    rep = FakeReport(3)
    calls = stage_calls(rep)
    source = panelauto.pack_round_data(rep)
    for c in calls[:2]:
        assert c["stdin"] != source, "원본을 그대로 보냈다"
        body = json.loads(c["stdin"])
        assert body["matches"] == 3
        assert "legend" in body and "how_to_read" in body
        assert len(body["data"]) == 3
    # 지시문·시스템 프롬프트에도 원본을 싣지 않는다.
    assert "<panel_payload" not in calls[0]["stdin"]


def test_m12_still_exactly_three_sessions():
    """세션 구조는 6-F-9 그대로다 (§1·§33)."""
    calls = stage_calls(FakeReport(3))
    assert len(calls) == panelauto.EXPECTED_SESSIONS == 3
    assert [c["stage"] for c in calls] == [
        panel.DATA_ANALYST, panel.MATCHUP_ANALYST, panelauto.MODERATOR_DIR]


def test_m13_cache_holds_data_not_interpretation():
    """캐시는 속도·토큰용이고 **LLM 산출물을 담지 않는다** (§18·§19)."""
    base = scratch()
    idx = demo_index(2)
    out = panelpacket.write_cache(idx, base)
    names = {p.name for p in out.iterdir()}
    assert panelpacket.MANIFEST_FILE in names
    assert panelpacket.INDEX_FILE in names
    assert panelpacket.STATS_FILE in names
    for f in panelpacket.PACKET_FILES.values():
        assert f in names
    man = json.loads((out / panelpacket.MANIFEST_FILE).read_text("utf-8"))
    for key in ("round", "matches", "source_sha256_16", "parser_version"):
        assert key in man, key
    assert man["parser_version"] == panelpacket.PACKET_VERSION
    # 해석을 담지 않는다.
    body = module_code(panelpacket)
    for bad in ("llm", "anthropic", "summary_of", "interpret"):
        assert bad not in body.lower(), bad
    assert "llm" not in imported_names(panelpacket)


def test_m14_audit_reports_what_was_left_out():
    """빠진 것을 **정직하게** 센다 (§22).

    접힌 것을 빠진 것으로 세면 보고서가 거짓이 된다 — 첫 판에서 실제로
    `data_quality` 가 통째로 빠졌다고 나왔다.
    """
    idx = real_index() or demo_index(3)
    rep_a = panelpacket.audit(idx, panel.DATA_ANALYST)
    rep_b = panelpacket.audit(idx, panel.MATCHUP_ANALYST)
    assert "data_quality" not in rep_a["omitted_kinds"], rep_a["omitted_kinds"]
    assert "home" not in rep_a["omitted_kinds"]
    assert "evidence" not in rep_a["omitted_kinds"]
    # A 에서만 정성 자료가 빠진다.
    assert "qualitative" in rep_a["omitted_kinds"]
    assert "qualitative" not in rep_b["omitted_kinds"]
    lines = panelpacket.audit_lines(rep_a)
    assert any("evidence" in ln for ln in lines)


def test_m15_no_presentation_markup_in_the_packet():
    """HTML·CSS·SVG 는 분석 자료가 아니다 (§12)."""
    idx = real_index() or demo_index(3)
    text = panelpacket.packet_text(panelpacket.build_analyst_b_packet(idx))
    for bad in ("<table", "<div", "<svg", "<style", "</td>", "viewBox"):
        assert bad not in text, f"{bad} 가 실렸다"


def test_m16_the_format_explains_itself():
    """접은 형식을 **읽는 법이 packet 안에 있다** (§10).

    설명은 자료가 아니라 형식이라 짧게 적고, Evidence 검증에 필요한
    메타데이터(source·basis·표본 n)는 지우지 않는다.
    """
    idx = real_index() or demo_index(2)
    pk = panelpacket.build_analyst_a_packet(idx)
    how = pk["how_to_read"]
    assert "metric" in how and "legend" in how["metric"]
    meta = set(panelpacket.METRIC_META)
    assert meta == {"label", "unit", "source", "basis", "provenance"}
    for entry in pk["legend"]["metric"].values():
        assert set(entry) == meta
        break
    # 표본 수는 본문에 그대로 남는다.
    cell = None
    for row in pk["data"]:
        for axis in (row.get("home") or {}).values():
            if isinstance(axis, dict) and axis.get("metrics"):
                cell = next(iter(axis["metrics"].values()))
                break
        if cell:
            break
    if real_index() is not None:
        assert cell and len(cell) == 3, cell


def test_m17_the_original_is_not_touched():
    """원본을 버리거나 고치지 않는다 (§2 원칙 1)."""
    rep = FakeReport(3)
    before = [panel.serialize_payload(panel.build_panel_payload(m))
              for m in rep.matches]
    idx = panelpacket.build_panel_index(rep)
    panelpacket.build_analyst_a_packet(idx)
    panelpacket.build_analyst_b_packet(idx)
    after = [panel.serialize_payload(panel.build_panel_payload(m))
             for m in rep.matches]
    assert before == after, "원본 직렬화가 달라졌다"
    # 회차 자료 시트를 만드는 경로도 그대로 있다.
    assert panelauto.pack_round_data(rep)
    assert 'separators=(",", ":")' in source_of(panel)


def test_m18_packing_is_deterministic():
    """같은 자료면 같은 글자가 나온다 (§19 — deterministic preprocessing)."""
    rep = FakeReport(3)
    one = panelpacket.packet_text(
        panelpacket.build_analyst_a_packet(panelpacket.build_panel_index(rep)))
    two = panelpacket.packet_text(
        panelpacket.build_analyst_a_packet(panelpacket.build_panel_index(rep)))
    assert one == two
    body = module_code(panelpacket)
    for bad in ("random", "uuid", "time.time", "datetime.now"):
        assert bad not in body, f"{bad} 가 결과를 흔든다"


def test_m19_preflight_measures_before_spending():
    """시작 전에 packet 크기를 적는다 (§16·§26)."""
    rep = FakeReport(3)
    with patched(cli="/bin/true"):
        pre = panelauto.preflight(rep, "TEST", scratch())
    assert pre.packets and pre.index is not None
    assert pre.packets["source_chars"] > 0
    for role in panelpacket.ROLE_VIEWS:
        assert pre.packets["roles"][role]["chars"] > 0
    assert any("Retrieval" in n for n in pre.notes), pre.notes
    assert any("reduction" in n for n in pre.notes), pre.notes
    # 문맥 초과는 사용량 한도와 다른 상태로 남아 있다 (§16).
    assert panelauto._classify("prompt is too long") == panelauto.AGENT_TOO_LARGE


def test_m20_no_read_write_or_bash_is_needed():
    """Claude 는 여전히 도구가 필요 없다 (§23·§28)."""
    assert panelauto.AGENT_TOOLS == ""
    calls = stage_calls(FakeReport(2))
    for c in calls:
        assert c["tools"] == ""
        for bad in ("Read", "Write", "Bash", "파일을 읽"):
            assert bad not in c["prompt"], f"{c['stage']} 지시문에 {bad}"
    # MCP·embedding·vector DB 를 만들지 않았다 (§24·§25).
    code = module_code(panelpacket)
    for bad in ("embedding", "vector", "faiss", "chromadb", "mcp"):
        assert bad not in code.lower(), bad


def main() -> int:
    print("Phase 6-F-6~10 — 패널 자동 실행 (3세션 · 역할별 packet)")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 1 if _FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
