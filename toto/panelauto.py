"""패널 자동 실행 (Phase 6-F-6) — Claude Code headless 오케스트레이터.

6-F-4 까지 사람이 하던 일은 **분석이 아니라 운반**이었다. 6-F-5 조사가
`claude -p`(Claude Code headless)로 그 운반을 없앨 수 있다는 것을 실측으로
확인했고, 이 모듈이 그것을 실제 경로로 만든다.

    [3] 회차 자료  →  A 14경기  →  B 14경기  →  조립  →  C  →  기존 [4]

## 이 모듈이 쓰지 않는 것

**Anthropic API 를 직접 부르지 않는다.** `anthropic`·`llm` 을 import 하지
않고, `[2] --panel` 의 API 실행 경로(`panel.run_match`·`run_panel_role`·
`attach_panels`·`moderator.run_moderator`)를 부르지 않는다 (AST 테스트).
모델을 부르는 유일한 방법은 `claude` 실행 파일을 **subprocess 로 띄우는
것**이고, 인증은 사용자의 Claude 구독 로그인을 그대로 쓴다.

브라우저 자동화·GUI 좌표 클릭·Cowork deep link 도 쓰지 않는다.

## 책임 분리

    Claude   ─ 분석만 한다 (Read·Write 권한뿐, Bash 없음)
    Python   ─ 검증·조립·[4] 실행을 전부 맡는다

그래서 에이전트가 실패해도 잘못된 값이 다음 단계로 넘어갈 수 없다.

## 검증기를 새로 만들지 않는다

경기 하나의 내용은 `panel.parse_opinion()` 이 본다 — 수동 경로(6-F-3)와
API 경로가 쓰는 바로 그 함수다. 조립된 회차 결과는 기존 CLI 인자
(`--save-panel-opinion`·`--build-moderator-input`·`--save-moderator-result`·
`--paste-panel-result`)를 그대로 태운다. 규칙을 두 벌 두면 자동 경로와
수동 경로가 조용히 갈라진다 (§1-8).

## 프롬프트를 베끼지 않는다

`panel.SYSTEM_COMMON`·`panel.ROLE_PROMPTS`·`moderator.system_prompt()` 를
그대로 실어 보낸다. 이 파일에 분석 지시문을 복사하면 채팅 판과 자동 판이
갈라지고, 그 뒤로는 "왜 결과가 다르지" 를 영원히 묻게 된다 (§1-11-1 과 같은
이유). 여기 있는 문장은 **파일 입출력 계약**뿐이다.

## A 와 B 는 구조로 격리한다

프롬프트로 "보지 마십시오" 라고 적는 것으로는 부족하다 (6-F-5 §9). 셋을
모두 건다.

    새 OS 프로세스  +  호출마다 새 세션 ID  +  부모 세션 ID 제거

그리고 작업 폴더 자체를 나눈다 — A 의 workspace 에 B 의 산출물이 **없다.**

## 비용은 프로그램이 결정하지 않는다

구독 한도를 넘었을 때 API 과금으로 넘어갈지는 **사람이 정할 일**이다.
이 모듈은 한도에 닿으면 `WORKFLOW_STOPPED_USAGE_LIMIT` 로 멈추고, 결제·
크레딧 전환·Console 자격증명 추가를 하지 않는다. `--bare` 도 쓰지 않는다 —
그 모드는 구독 로그인을 읽지 않고 `ANTHROPIC_API_KEY` 를 요구한다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import moderator, panel, panelexport, panelwork
from .models import Report

# ==========================================================================
# 상수
# ==========================================================================
# 경기별 작업 폴더. `panel_work/<회차>/auto/<역할>/<번호>/` 로 내려간다 —
# 보관본(analyst_a.json)과 같은 회차 폴더 아래 두어 함께 지워지게 한다.
AUTO_DIRNAME = "auto"

# 역할 → 폴더 이름. `panelwork.ROLE_FILES` 와 같은 표기(a·b)를 쓴다.
ROLE_DIRS = {panel.DATA_ANALYST: "a", panel.MATCHUP_ANALYST: "b"}
MODERATOR_DIR = "c"

AGENT_INPUT = "payload.md"          # 에이전트가 읽을 자료
AGENT_OUTPUT = "out.json"           # 에이전트가 쓸 결과
AGENT_ENVELOPE = "run.json"         # claude -p 가 돌려준 실행 봉투
AGENT_FAIL = "fail.txt"             # 실패 사유 (있으면 그 경기는 실패다)

# 한 경기가 멈춰도 회차 전체가 무한 대기하지 않게 한다. 실측 기준(6-F-5)
# 에서 경기 하나가 수 분이라 넉넉히 잡되, 상수로 두어 바꿀 수 있게 한다.
PANEL_AGENT_TIMEOUT = 900           # 경기 하나 (A·B)
MODERATOR_AGENT_TIMEOUT = 2400      # 사회자 (회차 전체를 한 번에)

# **자식 환경에서 반드시 지우는 것.**
#   · API 인증  — 있으면 구독이 아니라 API 로 과금된다 (공식 문서 경고)
#   · 세션 식별 — 물려주면 자식이 **부모와 같은 세션 ID** 를 쓴다
#                 (6-F-5 POC-B 에서 실제로 그랬다)
SCRUB_API = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
SCRUB_SESSION = ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID",
                 "CLAUDE_CODE_CHILD_SESSION", "CLAUDECODE",
                 "CLAUDE_CODE_ENTRYPOINT")

# 에이전트에게 주는 권한. **Bash 를 주지 않는다** — 분석가는 읽고 쓰기만
# 하면 되고, [4] 실행은 Python 이 한다 (§13).
AGENT_TOOLS = "Read,Write"

# 실행 결과 분류. `실패` 를 한 낱말로 뭉뚱그리지 않는다 (§1-6).
AGENT_OK = "ok"
AGENT_INVALID = "invalid"           # 형식·스키마 위반
AGENT_TIMEOUT = "timeout"
AGENT_USAGE_LIMIT = "usage_limit"   # 구독 한도 — 과금으로 넘기지 않는다
AGENT_AUTH = "auth"                 # 로그인이 없다
AGENT_NO_OUTPUT = "no_output"       # 파일을 안 썼다
AGENT_FAILED = "failed"             # 그 밖의 실패

# 워크플로 중단 사유. §26 이 이름을 정해 두었다.
WORKFLOW_STOPPED_USAGE_LIMIT = "WORKFLOW_STOPPED_USAGE_LIMIT"

# 구독 한도·인증 실패를 알아보는 표식. **문구가 바뀌면 못 알아볼 수 있으므로
# 못 알아본 것은 `failed` 로 남기고 과금 전환은 어느 경우에도 하지 않는다.**
_USAGE_MARKERS = ("usage limit", "rate limit", "rate_limit",
                  "사용량", "한도", "quota", "upgrade to", "limit reached")
_AUTH_MARKERS = ("authentication_failed", "invalid api key", "not logged in",
                 "please run /login", "unauthorized", "oauth")


# ==========================================================================
# 결과 그릇 — `panelimport` 의 어휘를 그대로 쓴다
# ==========================================================================
@dataclass
class AgentRun:
    """`claude -p` 한 번의 결과."""
    status: str = AGENT_FAILED
    session_id: str = ""
    requested_session_id: str = ""
    returncode: int | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == AGENT_OK


@dataclass
class MatchResult:
    """경기 하나의 자동 분석 결과."""
    no: int = 0
    role: str = ""
    status: str = AGENT_FAILED
    reused: bool = False            # 이미 있어 건너뛴 경기
    session_id: str = ""
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == AGENT_OK


@dataclass
class StageResult:
    """한 단계(A·B·C)의 결과."""
    role: str = ""
    matches: list = field(default_factory=list)
    status: str = AGENT_FAILED
    message: str = ""
    session_ids: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == AGENT_OK

    @property
    def failed(self) -> list:
        return [m for m in self.matches if not m.ok]


@dataclass
class AutoResult:
    """회차 하나의 자동 워크플로 결과."""
    round_id: str = ""
    status: str = AGENT_FAILED
    stopped_reason: str = ""
    stages: dict = field(default_factory=dict)
    agent_calls: int = 0
    reused_calls: int = 0
    message: str = ""
    report_path: Path | None = None
    lines: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == AGENT_OK


@dataclass
class Preflight:
    """시작 전 점검 결과. **하나라도 막히면 시작하지 않는다.**"""
    ok: bool = False
    cli: str = ""
    version: str = ""
    round_id: str = ""
    matches: int = 0
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)


# ==========================================================================
# 환경 — 비용 안전장치가 여기에 있다
# ==========================================================================
def find_claude_cli() -> str:
    """`claude` 실행 파일 경로. 없으면 빈 문자열.

    이름을 코드에 박지 않고 `shutil.which` 로 찾는다 — 윈도우에서는
    `claude.cmd` 처럼 확장자가 붙어 있어도 이것이 찾아 준다.
    """
    return shutil.which("claude") or ""


def build_agent_env(env: dict | None = None) -> dict:
    """자식 프로세스 환경. **API 인증과 부모 세션 식별을 지운다.**

    구독 로그인 정보(OAuth·키체인·호스트 관리 provider 설정)는 **그대로
    둔다** — 그것까지 지우면 인증이 통째로 사라진다. 지우는 것은 API 키와
    세션 식별자뿐이다.
    """
    out = dict(os.environ if env is None else env)
    for key in SCRUB_API + SCRUB_SESSION:
        out.pop(key, None)
    return out


def _classify(text: str) -> str:
    """실행 실패 문구를 분류한다. 모르는 것은 `failed` 로 둔다."""
    low = (text or "").lower()
    if any(m in low for m in _USAGE_MARKERS):
        return AGENT_USAGE_LIMIT
    if any(m in low for m in _AUTH_MARKERS):
        return AGENT_AUTH
    return AGENT_FAILED


# ==========================================================================
# Preflight
# ==========================================================================
def preflight(report: Report | None, round_id: str,
              base: Path | None = None) -> Preflight:
    """시작해도 되는지 본다. **API 키가 있으면 시작하지 않는다.**

    `report` 가 `None` 이면 저장본을 읽지 못한 것이다 — 그것도 막는다.
    """
    out = Preflight(round_id=str(round_id or ""))

    # ① 비용 — 가장 먼저 본다. 여기서 막히면 아무것도 실행하지 않는다.
    present = [k for k in SCRUB_API if os.environ.get(k)]
    if present:
        out.problems.append(
            f"{' · '.join(present)} 가 설정되어 있습니다 — 패널 자동 분석은 "
            f"Claude 구독 인증으로만 실행합니다. API 키를 쓴 자동 실행은 "
            f"시작하지 않습니다 (지우고 다시 실행하십시오)")

    # ② Claude CLI
    cli = find_claude_cli()
    if not cli:
        out.problems.append(
            "claude 실행 파일을 찾지 못했습니다 — Claude Code 를 설치하고 "
            "로그인한 뒤 다시 실행하십시오")
    else:
        out.cli = cli
        try:
            p = subprocess.run([cli, "--version"], capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=60)
            out.version = (p.stdout or "").strip().splitlines()[0][:60] \
                if p.stdout else ""
        except (OSError, subprocess.SubprocessError) as exc:
            out.problems.append(f"claude --version 실패: {exc}")

    # ③ 회차 자료
    if not out.round_id:
        out.problems.append("회차를 알 수 없습니다")
    if report is None:
        out.problems.append(
            "저장된 회차 분석 결과가 없습니다 — 먼저 회차 분석을 "
            "돌리십시오")
    else:
        out.matches = len(report.matches)
        if not report.matches:
            out.problems.append("회차에 경기가 없습니다")
        without = [m.no for m in report.matches
                   if not panel.build_panel_payload(m).evidence_ids]
        if without:
            out.notes.append(
                f"근거 0건인 경기 {len(without)}개 "
                f"({', '.join(str(n) for n in without)}번) — 축 지표만으로 "
                f"분석합니다")

    # ④ 작업 폴더
    try:
        auto_dir(out.round_id or "unknown", base).mkdir(parents=True,
                                                        exist_ok=True)
    except OSError as exc:
        out.problems.append(f"작업 폴더를 만들지 못했습니다: {exc}")

    # ⑤ 프롬프트 판 — 수동 경로와 같은 것을 쓴다는 기록
    out.notes.append(f"프롬프트 판 PANEL {panel.PANEL_PROMPT_VERSION} · "
                     f"MODERATOR {moderator.MODERATOR_PROMPT_VERSION}")

    out.ok = not out.problems
    return out


# ==========================================================================
# 작업 폴더
# ==========================================================================
def auto_dir(round_id: str, base: Path | None = None) -> Path:
    return panelwork.work_dir(round_id, base).joinpath(AUTO_DIRNAME)


def match_workspace(round_id: str, role: str, no: int,
                    base: Path | None = None) -> Path:
    """경기 하나의 작업 폴더. **역할마다 다른 가지에 둔다** (§9·§10)."""
    return auto_dir(round_id, base).joinpath(ROLE_DIRS[role], f"{no:02d}")


def moderator_workspace(round_id: str, base: Path | None = None) -> Path:
    return auto_dir(round_id, base).joinpath(MODERATOR_DIR)


# ==========================================================================
# 에이전트 실행
# ==========================================================================
def agent_argv(exe: str, prompt: str, system: str, workspace: Path,
               session_id: str, model: str = "") -> list:
    """`claude -p` 명령줄. **실행하지 않고 만들기만 한다** (테스트 가능).

    `--bare` 를 넣지 않는다 — 그 모드는 구독 로그인을 읽지 않고
    `ANTHROPIC_API_KEY` 를 요구해서, 이 워크플로의 비용 전제를 깬다.
    """
    argv = [exe, "-p", prompt,
            "--output-format", "json",
            "--session-id", session_id,      # 호출마다 새 세션 (§8)
            "--append-system-prompt", system,
            "--add-dir", str(workspace),     # 작업 폴더 바깥은 보지 않는다
            "--permission-mode", "acceptEdits",
            "--permission-prompts", "none",  # 물어야 하는 것은 거부된다
            "--allowedTools", AGENT_TOOLS]   # Bash 없음 (§13)
    if model:
        argv += ["--model", model]
    return argv


def run_agent(prompt: str, system: str, workspace: Path, *,
              timeout: int, model: str = "", cli: str = "",
              env: dict | None = None) -> AgentRun:
    """`claude -p` 한 번. **API 를 직접 부르지 않고 CLI 를 띄운다.**

    `--bare` 를 쓰지 않는다 — 그 모드는 구독 로그인을 읽지 않는다.
    `--permission-prompts none` 이라 사람에게 물어야 하는 것은 승인되지
    않고 거부되며, 그래서 무인 실행이 조용히 멈추지 않는다.
    """
    exe = cli or find_claude_cli()
    out = AgentRun()
    if not exe:
        out.message = "claude 실행 파일을 찾지 못했습니다"
        return out

    wanted = str(uuid.uuid4())          # 호출마다 **새 세션** (§8)
    out.requested_session_id = wanted
    argv = agent_argv(exe, prompt, system, workspace, wanted, model)

    try:
        proc = subprocess.run(
            argv, cwd=str(workspace), env=build_agent_env(env),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, shell=False,
            stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        out.status = AGENT_TIMEOUT
        out.message = f"{timeout}초 안에 끝나지 않았습니다"
        return out
    except OSError as exc:
        out.message = f"실행하지 못했습니다: {exc}"
        return out

    out.returncode = proc.returncode
    raw = (proc.stdout or "").strip()
    # 실행 봉투를 남긴다 — 실패했을 때 "모델이 무엇을 답했나" 를 되짚을
    # 유일한 자료다 (§29). 조용히 버리면 사유를 알 수 없다 (§1-6-1).
    try:
        (workspace / AGENT_ENVELOPE).write_text(
            raw or (proc.stderr or ""), encoding="utf-8")
    except OSError:
        pass
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    if isinstance(data, dict):
        out.session_id = str(data.get("session_id") or "")
        out.cost_usd = data.get("total_cost_usd")
        out.duration_ms = data.get("duration_ms")
        text = str(data.get("result") or "")
    else:
        text = raw

    if proc.returncode == 0 and isinstance(data, dict) \
            and not data.get("is_error"):
        out.status = AGENT_OK
        out.message = text[:200]
        return out

    blob = f"{text}\n{proc.stderr or ''}"
    out.status = _classify(blob)
    out.message = (text or (proc.stderr or "")).strip()[:300] \
        or f"종료코드 {proc.returncode}"
    return out


# ==========================================================================
# A · B — 경기 단위
# ==========================================================================
def payload_text(payload) -> str:
    """에이전트가 읽을 자료. **자료는 canonical 직렬화 그대로다.**

    `panel.serialize_payload()` 는 캐시 키의 근거라 minified 한 줄로 나온다
    (실측 134,536자 · 줄바꿈 0개). 그것을 그대로 파일에 쓰면 Read 도구가
    긴 줄을 잘라 읽어서 모델이 **부분 읽기를 15회** 반복했다 — 실측으로 한
    경기에 $1.55 가 들었다.

    그래서 **같은 자료를 줄바꿈만 넣어** 쓴다. `json.loads` → `json.dumps`
    라 키 순서(`sort_keys`)와 값이 보존되고, A·B 가 받는 문자열은 여전히
    서로 **똑같다** (3-B 불변조건 2). `serialize_payload()` 자체는 한 글자도
    바뀌지 않으므로 수동 경로·캐시 키도 그대로다.
    """
    return json.dumps(json.loads(panel.serialize_payload(payload)),
                      ensure_ascii=False, indent=1, sort_keys=True)


def _io_contract(keys: str) -> str:
    """파일 입출력 계약. **분석 지시는 한 줄도 여기에 없다.**

    분석 규칙은 전부 `panel.SYSTEM_COMMON` 과 역할 프롬프트에서 온다
    (§11). 이 문장은 "무엇을 읽고 무엇을 쓰라" 만 말한다.
    """
    return (f"작업 폴더의 `{AGENT_INPUT}` 를 읽고, 분석 결과를 "
            f"`{AGENT_OUTPUT}` 에 **JSON 객체 하나**로 쓰십시오.\n\n"
            f"필수 키: {keys}\n\n"
            f"`{AGENT_OUTPUT}` 외의 파일을 만들지 말고, 코드펜스나 설명 "
            f"문장을 파일에 넣지 마십시오. 다 쓰면 DONE 만 답하십시오.")


# `panel.parse_opinion()` 이 요구하는 칸. 이름이 갈라지지 않도록 한 곳에
# 적고 테스트가 그 함수와 대조한다.
OPINION_KEYS = ("predicted_home(0 이상 정수 또는 null)",
                "predicted_away(0 이상 정수 또는 null)",
                "summary(문자열)", "rationale(문자열 배열)",
                "evidence_ids(이 경기의 근거 ID 배열)")


def _read_output(workspace: Path):
    """에이전트가 쓴 결과를 읽는다. (obj, 사유)."""
    path = workspace / AGENT_OUTPUT
    if not path.is_file():
        return None, f"{AGENT_OUTPUT} 를 만들지 않았습니다"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"읽지 못했습니다: {exc}"
    from .llm import strip_fence      # 코드펜스만 걷는다 (기존 함수 재사용)
    try:
        data = json.loads(strip_fence(raw.strip()))
    except ValueError as exc:
        return None, f"JSON 이 아닙니다: {exc}"
    if not isinstance(data, dict):
        return None, f"객체가 아닙니다 ({type(data).__name__})"
    return data, ""


def verify_match(data: dict, match, role: str):
    """경기 하나의 결과를 **기존 검증기**로 본다. (의견, 사유).

    `panel.parse_opinion()` — 수동 경로·API 경로가 쓰는 그 함수다.
    """
    allowed = panel.build_panel_payload(match).evidence_ids
    body = dict(data)
    body.pop(panelwork.STAGE_NO, None)      # 번호는 오케스트레이터가 안다
    try:
        opinion = panel.parse_opinion(
            json.dumps(body, ensure_ascii=False), role, allowed)
    except panel.ValidationError as exc:
        return None, str(exc)
    return opinion, ""


def _completed(workspace: Path, match, role: str) -> bool:
    """이미 끝난 경기인가. **검증까지 통과해야 끝난 것으로 본다** (§16)."""
    data, why = _read_output(workspace)
    if data is None:
        return False
    opinion, why = verify_match(data, match, role)
    return opinion is not None


def run_match_role(match, role: str, round_id: str, *, model: str = "",
                   cli: str = "", base: Path | None = None,
                   timeout: int = PANEL_AGENT_TIMEOUT) -> MatchResult:
    """경기 하나를 한 역할로 분석한다. **이미 끝났으면 건너뛴다.**"""
    out = MatchResult(no=match.no, role=role)
    ws = match_workspace(round_id, role, match.no, base)
    ws.mkdir(parents=True, exist_ok=True)

    if _completed(ws, match, role):
        out.status, out.reused = AGENT_OK, True
        return out
    (ws / AGENT_FAIL).unlink(missing_ok=True)

    # 자료는 **두 역할에 같은 문자열**로 간다 (3-B 불변조건 2).
    payload = panel.build_panel_payload(match)
    (ws / AGENT_INPUT).write_text(payload_text(payload), encoding="utf-8")

    system = panel.SYSTEM_COMMON + "\n\n" + panel.ROLE_PROMPTS[role]
    run = run_agent(_io_contract(" · ".join(OPINION_KEYS)), system, ws,
                    timeout=timeout, model=model, cli=cli)
    out.session_id = run.session_id or run.requested_session_id

    if not run.ok:
        out.status, out.message = run.status, run.message
        (ws / AGENT_FAIL).write_text(f"{run.status}: {run.message}",
                                     encoding="utf-8")
        return out

    data, why = _read_output(ws)
    if data is None:
        out.status = AGENT_NO_OUTPUT if AGENT_OUTPUT in why else AGENT_INVALID
        out.message = why
        (ws / AGENT_FAIL).write_text(why, encoding="utf-8")
        return out

    opinion, why = verify_match(data, match, role)
    if opinion is None:
        out.status, out.message = AGENT_INVALID, why
        (ws / AGENT_FAIL).write_text(why, encoding="utf-8")
        return out

    out.status = AGENT_OK
    return out


def collect_stage(report: Report, role: str,
                  base: Path | None = None) -> tuple[list, list]:
    """경기별 결과를 배열로 모은다. (배열, 빠진 번호)."""
    rows, missing = [], []
    for match in report.matches:
        ws = match_workspace(report.round_id or "", role, match.no, base)
        data, _why = _read_output(ws)
        if data is None:
            missing.append(match.no)
            continue
        body = dict(data)
        body[panelwork.STAGE_NO] = match.no     # 번호는 프로그램이 정한다
        rows.append(body)
    return rows, missing


# ==========================================================================
# 기존 CLI 재호출 — **검증·조립·[4] 를 다시 구현하지 않는다**
# ==========================================================================
def run_existing_cli(argv: list) -> int:
    """기존 CLI 를 그대로 부른다 (메뉴가 쓰는 방식과 같다, §1-20).

    별도 프로세스로 띄우지 않는 이유는 윈도우에서 파이썬 경로·콘솔
    인코딩이 얽히기 때문이다 (§1-7). 같은 프로세스에서 부르면 그 문제가
    아예 생기지 않고, 이미 메뉴가 그렇게 하고 있다.
    """
    from .cli import main as cli_main
    return cli_main(list(argv))


def _save_stage(round_id: str, role: str, rows: list,
                base: Path | None = None) -> int:
    """조립한 배열을 **기존 `--save-panel-opinion`** 에 태운다."""
    path = auto_dir(round_id, base) / f"{ROLE_DIRS[role]}_stage.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return run_existing_cli(["--round", round_id,
                             "--save-panel-opinion", str(path),
                             "--role", role])


# ==========================================================================
# 단계 — A · B · C
# ==========================================================================
def run_stage_ab(report: Report, role: str, *, model: str = "",
                 cli: str = "", base: Path | None = None,
                 timeout: int = PANEL_AGENT_TIMEOUT,
                 progress=None) -> StageResult:
    """한 역할로 14경기를 **순차** 실행한다 (§15).

    동시에 띄우지 않는 이유는 실패 위치를 분명히 하고 사용량이 한꺼번에
    빠져나가지 않게 하기 위해서다. 한 경기가 실패하면 **거기서 멈춘다** —
    잘못된 결과로 다음 단계에 가지 않는다 (§17).
    """
    out = StageResult(role=role)
    total = len(report.matches)
    for i, match in enumerate(report.matches, start=1):
        res = run_match_role(match, role, report.round_id or "", model=model,
                             cli=cli, base=base, timeout=timeout)
        out.matches.append(res)
        if res.session_id:
            out.session_ids.append(res.session_id)
        if progress:
            progress(role, i, total, res)
        if not res.ok:
            out.status = res.status
            out.message = f"{res.no}번 경기: {res.message}"
            return out

    rows, missing = collect_stage(report, role, base)
    if missing:
        out.status = AGENT_INVALID
        out.message = f"결과가 없는 경기: {missing}"
        return out
    if _save_stage(report.round_id or "", role, rows, base) != 0:
        out.status = AGENT_INVALID
        out.message = "회차 결과 검증에 실패했습니다 (위 로그 참고)"
        return out
    out.status = AGENT_OK
    return out


def run_stage_c(report: Report, settings=None, *, model: str = "",
                cli: str = "", base: Path | None = None,
                timeout: int = MODERATOR_AGENT_TIMEOUT) -> StageResult:
    """사회자를 **1회** 실행한다 (§20).

    C 는 A·B 원본을 읽지 않는다 — 기존 경로가 만든 `03_사회자자료_완성.md`
    하나만 본다. 그래서 수동 경로와 자료가 같다.
    """
    out = StageResult(role="moderator")
    round_id = report.round_id or ""
    sheet = panelexport.round_dir(round_id) / panelwork.COMPLETED_SHEET
    if not sheet.is_file():
        out.status = AGENT_INVALID
        out.message = f"{panelwork.COMPLETED_SHEET} 이 없습니다"
        return out

    ws = moderator_workspace(round_id, base)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / AGENT_INPUT).write_text(sheet.read_text(encoding="utf-8"),
                                  encoding="utf-8")
    (ws / AGENT_FAIL).unlink(missing_ok=True)

    sims = moderator.simulations_of(settings) if settings is not None \
        else moderator.DEBATE_SIMULATIONS
    keys = ("match_no(정수) · simulations · distribution · adopted_home · "
            "adopted_away · adopted_from · conclusion · common_points · "
            "differences · counterpoints · uncertainty · evidence_ids")
    prompt = (f"작업 폴더의 `{AGENT_INPUT}` 를 읽으십시오. 그 안에 이 회차의 "
              f"경기별 사회자 입력이 들어 있습니다.\n\n"
              f"경기마다 규칙대로 토론을 진행하고, 결과를 `{AGENT_OUTPUT}` 에 "
              f"**JSON 배열**로 쓰십시오 (경기 하나가 객체 하나).\n\n"
              f"각 객체의 칸: {keys}\n\n"
              f"`{AGENT_OUTPUT}` 외의 파일을 만들지 말고, 코드펜스나 설명 "
              f"문장을 파일에 넣지 마십시오. 다 쓰면 DONE 만 답하십시오.")

    run = run_agent(prompt, moderator.system_prompt(sims), ws,
                    timeout=timeout, model=model, cli=cli)
    if run.session_id:
        out.session_ids.append(run.session_id)
    if not run.ok:
        out.status, out.message = run.status, run.message
        (ws / AGENT_FAIL).write_text(f"{run.status}: {run.message}",
                                     encoding="utf-8")
        return out

    path = ws / AGENT_OUTPUT
    if not path.is_file():
        out.status = AGENT_NO_OUTPUT
        out.message = f"{AGENT_OUTPUT} 를 만들지 않았습니다"
        return out

    # 내용 검증은 **기존 경로**가 한다 — `panelpaste.convert` +
    # `panelimport.validate` + `moderator.parse_result` (§21).
    if run_existing_cli(["--round", round_id,
                         "--save-moderator-result", str(path)]) != 0:
        out.status = AGENT_INVALID
        out.message = "사회자 결과 검증에 실패했습니다 (위 로그 참고)"
        (ws / AGENT_FAIL).write_text(out.message, encoding="utf-8")
        return out
    out.status = AGENT_OK
    return out


# ==========================================================================
# 전체 워크플로 — 상태를 읽고 **끝난 단계는 건너뛴다** (§23)
# ==========================================================================
_BAR = "━" * 44


def _default_progress(role, i, total, res):
    mark = "✓" if res.ok else "✗"
    tail = " (보존됨)" if res.reused else ""
    print(f"      {i:02d}/{total} {mark}{tail}")
    if not res.ok:
        print(f"      └ {res.status}: {res.message[:150]}")


def run(round_id: str, report: Report | None = None, settings=None, *,
        model: str = "", base: Path | None = None,
        progress=_default_progress, echo=print) -> AutoResult:
    """`[패널 자동 분석]` 의 본체. 한 번 부르면 [4] 까지 간다.

    사람에게 확인을 묻지 않는다 (§36). 다만 안전·오류 조건 — API 키 감지,
    인증 없음, 사용량 한도, 스키마 실패, 자료 손상, CLI 없음 — 에서는
    **즉시 멈춘다.**
    """
    out = AutoResult(round_id=str(round_id or ""))
    echo(_BAR)
    echo(f"Panel Auto Workflow — {out.round_id}")
    echo(_BAR)
    echo("")

    if report is None:
        from . import artifact
        report, why = artifact.load(out.round_id)
        if report is None:
            echo(f"[1/5] 자료 확인          ✗  {why}")
            out.status, out.message = AGENT_FAILED, why
            return out

    pre = preflight(report, out.round_id, base)
    for note in pre.notes:
        out.lines.append(note)
    if not pre.ok:
        echo("[1/5] 자료 확인          ✗")
        for p in pre.problems:
            echo(f"      └ {p}")
        out.status = AGENT_FAILED
        out.stopped_reason = "; ".join(pre.problems)
        return out
    echo(f"[1/5] 자료 확인          ✓  {pre.matches}경기 · {pre.version}")

    state = panelwork.workflow(out.round_id, base=base)
    done = {s.key: s.done for s in state.stages}

    def _stop(stage_name: str, res: StageResult) -> AutoResult:
        echo(f"      └ {res.status}: {res.message}")
        out.status = res.status
        if res.status == AGENT_USAGE_LIMIT:
            out.stopped_reason = WORKFLOW_STOPPED_USAGE_LIMIT
            echo("")
            echo("Claude 사용량 한도에 도달했습니다.")
            echo("  자동으로 API 과금으로 전환하지 않습니다 — 한도가 "
                 "회복된 뒤 다시 실행하면 이어서 진행합니다.")
        else:
            out.stopped_reason = f"{stage_name}: {res.message}"
            echo("")
            echo("  완료된 경기 결과는 보존되었습니다. 다시 실행하면 "
                 "실패한 지점부터 재개합니다.")
        return out

    # ---- [2/5] A ---------------------------------------------------------
    if done.get(panelwork.STAGE_A):
        echo("[2/5] 데이터 분석 A      ✓  (이미 완료 — 건너뜁니다)")
    else:
        echo("[2/5] 데이터 분석 A")
        res = run_stage_ab(report, panel.DATA_ANALYST, model=model, cli=pre.cli,
                           base=base, progress=progress)
        out.stages["a"] = res
        out.agent_calls += sum(1 for m in res.matches if not m.reused)
        out.reused_calls += sum(1 for m in res.matches if m.reused)
        if not res.ok:
            return _stop("A", res)

    # ---- [3/5] B — A 가 끝난 뒤에만 시작한다 (§18) -----------------------
    if done.get(panelwork.STAGE_B):
        echo("[3/5] 맞대결 분석 B      ✓  (이미 완료 — 건너뜁니다)")
    else:
        echo("[3/5] 맞대결 분석 B")
        res = run_stage_ab(report, panel.MATCHUP_ANALYST, model=model,
                           cli=pre.cli, base=base, progress=progress)
        out.stages["b"] = res
        out.agent_calls += sum(1 for m in res.matches if not m.reused)
        out.reused_calls += sum(1 for m in res.matches if m.reused)
        if not res.ok:
            return _stop("B", res)

    # ---- [4/5] 조립 + C --------------------------------------------------
    if not done.get(panelwork.STAGE_INPUT):
        if run_existing_cli(["--round", out.round_id,
                             "--build-moderator-input"]) != 0:
            out.status = AGENT_FAILED
            out.stopped_reason = "사회자 자료 조립 실패"
            echo("[4/5] 사회자 C           ✗  자료 조립 실패")
            return out

    if done.get(panelwork.STAGE_RESULT):
        echo("[4/5] 사회자 C           ✓  (이미 완료 — 건너뜁니다)")
    else:
        res = run_stage_c(report, settings, model=model, cli=pre.cli, base=base)
        out.stages["c"] = res
        out.agent_calls += 1
        if not res.ok:
            echo("[4/5] 사회자 C           ✗")
            return _stop("C", res)
        echo("[4/5] 사회자 C           ✓")

    # ---- [5/5] 기존 [4] 반영 ---------------------------------------------
    saved = panelwork.moderator_result_path(out.round_id, base)
    if run_existing_cli(["--round", out.round_id,
                         "--paste-panel-result", str(saved)]) != 0:
        out.status = AGENT_FAILED
        out.stopped_reason = "[4] 반영 실패"
        echo("[5/5] [4] 반영           ✗")
        echo("")
        echo("  사회자 결과는 보존되었습니다. 다시 실행하면 반영부터 "
             "재개합니다.")
        return out
    echo("[5/5] [4] 반영           ✓")

    out.status = AGENT_OK
    from .settings import load_settings
    st = settings if settings is not None else load_settings()
    name = st.output.get("filename", "toto_{round}.html").format(
        round=out.round_id)
    out.report_path = st.output_dir / name
    echo("")
    echo(_BAR)
    echo("패널 분석 완료")
    echo(f"결과: {out.report_path}")
    echo(_BAR)
    return out


__all__ = [
    "AUTO_DIRNAME", "ROLE_DIRS", "MODERATOR_DIR",
    "AGENT_INPUT", "AGENT_OUTPUT", "AGENT_ENVELOPE", "AGENT_FAIL",
    "PANEL_AGENT_TIMEOUT", "MODERATOR_AGENT_TIMEOUT",
    "SCRUB_API", "SCRUB_SESSION", "AGENT_TOOLS", "OPINION_KEYS",
    "AGENT_OK", "AGENT_INVALID", "AGENT_TIMEOUT", "AGENT_USAGE_LIMIT",
    "AGENT_AUTH", "AGENT_NO_OUTPUT", "AGENT_FAILED",
    "WORKFLOW_STOPPED_USAGE_LIMIT",
    "AgentRun", "MatchResult", "StageResult", "AutoResult", "Preflight",
    "find_claude_cli", "build_agent_env", "preflight",
    "auto_dir", "match_workspace", "moderator_workspace",
    "agent_argv", "run_agent", "payload_text", "run_match_role", "verify_match", "collect_stage",
    "run_existing_cli", "run_stage_ab", "run_stage_c", "run",
]
