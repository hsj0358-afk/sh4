"""패널 자동 실행 (Phase 6-F-6 → **6-F-9 3세션 배치**) — Claude Code
headless 오케스트레이터.

6-F-4 까지 사람이 하던 일은 **분석이 아니라 운반**이었다. 6-F-5 조사가
`claude -p`(Claude Code headless)로 그 운반을 없앨 수 있다는 것을 실측으로
확인했고, 이 모듈이 그것을 실제 경로로 만든다.

    [1] 회차 분석  →  A 1회  →  B 1회  →  조립  →  C 1회  →  기존 [4]

## 6-F-9 — 사람이 채팅에서 하는 것과 **같은 모양**으로 부른다

사람은 채팅에서 대화 셋을 연다 — 1단계에 경기자료 7개를 붙이고 14경기를
한 번에, 2단계에 **같은** 7개를 붙이고 다시 14경기를 한 번에, 3단계에
사회자 자료와 1·2단계 결과를 붙이고 14경기를 한 번에. 그런데 6-F-6~8 의
자동 경로는 **경기마다 세션을 새로 열어** A 14 + B 14 + C 1 = 29회를 불렀다.
자동화는 사람의 수동 절차를 배치로 돌리는 것이어야 하므로, 이 판에서
호출 수를 셋으로 맞춘다.

    정상 실행 = Claude Code 세션 **정확히 3개** (A 1 · B 1 · C 1)

경기 단위 세션·경기 단위 checkpoint·경기 단위 재개는 **없다.** 체크포인트는
`panelwork` 의 단계 산출물 셋뿐이다 (`analyst_a.json` · `analyst_b.json` ·
`moderator_result.json`).

## 자료는 Python 이 읽어 stdin 으로 한 번 준다

6-F-8 까지는 자료를 파일로 써 두고 에이전트에게 `Read` 시켰다. 실측하면
그 Read 하나가 Claude Code 의 도구 스키마·스킬 목록까지 문맥에 끌고 들어와
경기 하나에 **7턴 · 입력 487,563토큰**이 들었고, 자료 자체는 그중 39%가
같은 내용의 재전송이었다. 이제 Python 이 파일을 읽어 **stdin 한 번**으로
넘기고 도구를 아예 끈다 (`--tools ""`).

    Python  ─ 자료 로드 · stdin 패킹 · 검증 · 조립 · [4] 실행
    Claude  ─ 분석만 한다 (**도구 없음**)

에이전트는 파일을 읽지도 쓰지도 않는다. 결과는 `--output-format json` 의
`result` 로 돌아오고 그것을 Python 이 파싱·검증·저장한다.

## 작업 폴더를 저장소 밖에 둔다

6-F-6 실행 기록을 뜯어 보니 작업 폴더가 `panel_work/…`(저장소 안)이라
Claude Code 가 이 저장소의 `CLAUDE.md` 를 자동 발견해 **호출마다 197,275자
≈ 94,480토큰**을 문맥에 실었다. 저장소의 `CLAUDE.md` 는 이 프로젝트의
개발 규칙서이지 패널 에이전트의 지침이 아니므로 **지우지 않고**, 작업
폴더를 저장소 밖(OS 임시 폴더)으로 옮겨 자동 발견을 끊는다.

패널의 공통 규칙은 `panel.SYSTEM_COMMON`, 역할별 규칙은
`panel.ROLE_PROMPTS` 와 `moderator.system_prompt()` 에 이미 나뉘어 있다.
그 넷을 작업 폴더에 `common.md`·`data_analyst.md`·`matchup_analyst.md`·
`moderator.md` 로 **코드에서 생성해** 시스템 프롬프트로만 주입한다 —
손으로 베낀 사본을 만들지 않는다 (§1-11-1).

## 이 모듈이 쓰지 않는 것

**Anthropic API 를 직접 부르지 않는다.** `anthropic`·`llm` 을 import 하지
않고, `[2] --panel` 의 API 실행 경로(`panel.run_match`·`run_panel_role`·
`attach_panels`·`moderator.run_moderator`)를 부르지 않는다 (AST 테스트).
모델을 부르는 유일한 방법은 `claude` 실행 파일을 **subprocess 로 띄우는
것**이고, 인증은 사용자의 Claude 구독 로그인을 그대로 쓴다.

브라우저 자동화·GUI 좌표 클릭·Cowork deep link 도 쓰지 않는다.

## 검증기를 새로 만들지 않는다

경기 하나의 내용은 `panel.parse_opinion()` 이 본다 — 수동 경로(6-F-3)와
API 경로가 쓰는 바로 그 함수다. 회차 배열은 기존 CLI 인자
(`--save-panel-opinion`·`--build-moderator-input`·`--save-moderator-result`·
`--paste-panel-result`)를 그대로 태운다. 규칙을 두 벌 두면 자동 경로와
수동 경로가 조용히 갈라진다 (§1-8).

## 프롬프트를 베끼지 않는다

`panel.SYSTEM_COMMON`·`panel.ROLE_PROMPTS`·`moderator.system_prompt()` 를
그대로 실어 보낸다. 이 파일에 분석 지시문을 복사하면 채팅 판과 자동 판이
갈라지고, 그 뒤로는 "왜 결과가 다르지" 를 영원히 묻게 된다 (§1-11-1 과 같은
이유). 여기 있는 문장은 **파일 입출력 계약**뿐이다.

## A 와 B 는 구조로 격리한다

프롬프트로 "보지 마십시오" 라고 적는 것으로는 부족하다 (6-F-5 §9). 넷을
모두 건다.

    새 OS 프로세스  +  호출마다 새 세션 ID  +  부모 세션 ID 제거
    +  `--continue`·`--resume` 를 쓰지 않는다

그리고 작업 폴더 자체를 나눈다 — A 의 workspace 에 B 의 산출물이 **없다.**
B 의 stdin 은 A 와 **글자까지 같은 자료**이고 A 의 결과는 한 글자도 들어
가지 않는다 (테스트로 고정). 사회자만 두 결과를 받는다.

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
import signal
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import moderator, panel, panelexport, panelpacket, panelwork
from .models import Report

# ==========================================================================
# 상수
# ==========================================================================
# 단계별 작업 폴더의 이름. `<auto_root>/<회차>/<a|b|c>/` 로 내려간다.
AUTO_DIRNAME = "auto"

# 역할 → 폴더 이름. `panelwork.ROLE_FILES` 와 같은 표기(a·b)를 쓴다.
ROLE_DIRS = {panel.DATA_ANALYST: "a", panel.MATCHUP_ANALYST: "b"}
MODERATOR_DIR = "c"

# 이 모듈의 단계 이름 → `panelwork` 의 체크포인트 단계 키 (6-F-12).
# 두 이름을 이어 두는 자리를 **한 곳**으로 둔다 (§1-8).
WORK_STAGE = {panel.DATA_ANALYST: panelwork.STAGE_A,
              panel.MATCHUP_ANALYST: panelwork.STAGE_B,
              MODERATOR_DIR: panelwork.STAGE_RESULT}

# **작업 폴더를 저장소 밖에 두는 이유는 토큰이다** (6-F-9). 저장소 안에서
# 돌리면 Claude Code 가 이 저장소의 `CLAUDE.md`(371KB ≈ 94,480토큰)를
# 자동 발견해 **호출마다** 문맥에 싣는다 — 6-F-6 실행 기록에서 실제로
# 그랬다. 저장소의 `CLAUDE.md` 는 개발 규칙서이지 패널 지침이 아니므로
# 지우지 않고, 작업 폴더를 옮겨 자동 발견을 끊는다.
AUTO_ENV = "TOTO_PANEL_AUTO_DIR"    # 자리를 직접 정하고 싶을 때의 탈출구
AUTO_SCRATCH = "toto_panel_auto"

# 작업 폴더 안의 파일. **에이전트는 이 중 어느 것도 읽거나 쓰지 않는다** —
# 자료는 stdin 으로 가고 결과는 stdout 으로 온다. 전부 진단용 사본이다.
AGENT_STDIN = "stdin.txt"           # 실제로 넘긴 사용자 입력 (사본)
AGENT_SYSTEM = "system.md"          # 시스템 프롬프트 (명령줄에 싣지 않는다)
AGENT_ENVELOPE = "run.json"         # claude -p 가 돌려준 실행 봉투
AGENT_RESULT = "result.json"        # 모델이 돌려준 배열 (Python 이 쓴다)
AGENT_FAIL = "fail.txt"             # 실패 사유 (있으면 그 단계는 실패다)

# 시스템 프롬프트의 원천 파일. **여기 적히는 글자는 전부 코드 상수에서
# 온다** — 손으로 베낀 사본을 만들면 채팅 판과 자동 판이 갈라진다
# (§1-11-1). 파일로 떨어뜨리는 것은 사람이 열어 볼 수 있게 하기 위해서다.
COMMON_FILE = "common.md"
ROLE_PROMPT_FILES = {panel.DATA_ANALYST: "data_analyst.md",
                     panel.MATCHUP_ANALYST: "matchup_analyst.md"}
MODERATOR_PROMPT_FILE = "moderator.md"

# 한 단계가 멈춰도 회차 전체가 무한 대기하지 않게 한다. **6-F-9 부터는
# 한 호출이 14경기를 통째로 다루므로** 경기 하나 기준(900초)으로는 모자란다.
ANALYST_AGENT_TIMEOUT = 3600        # A · B (회차 전체를 한 번에)
MODERATOR_AGENT_TIMEOUT = 3600      # 사회자 (회차 전체를 한 번에)

# **자식 환경에서 반드시 지우는 것.**
#   · API 인증  — 있으면 구독이 아니라 API 로 과금된다 (공식 문서 경고)
#   · 세션 식별 — 물려주면 자식이 **부모와 같은 세션 ID** 를 쓴다
#                 (6-F-5 POC-B 에서 실제로 그랬다)
SCRUB_API = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
SCRUB_SESSION = ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID",
                 "CLAUDE_CODE_CHILD_SESSION", "CLAUDECODE",
                 "CLAUDE_CODE_ENTRYPOINT")

# 에이전트에게 주는 도구. **하나도 주지 않는다** (6-F-9 §15 금지 2·5·7).
# 자료는 Python 이 읽어 stdin 으로 주고 결과는 stdout 으로 받으므로 분석가가
# 파일을 읽거나 쓸 일이 없다.
#
# **`--allowedTools` 가 아니라 `--tools` 다.** 앞의 것은 *자동승인* 목록일
# 뿐이라 거기 없는 도구도 여전히 쓸 수 있다 — 6-F-8 실행 기록에서 에이전트가
# `--allowedTools "Read,Write"` 아래서 Bash `cat` 을 실제로 실행했다. 실제
# 제한은 `--tools` 이고, 빈 문자열이 "도구 없음" 이다 (설치된 CLI 의
# `--help` 로 확인하고 실행으로 재확인했다 — `num_turns` 1).
AGENT_TOOLS = ""

# **기본 모델 (Phase 6-F-7 §5).** 6-F-6 실측이 이 값을 정했다 —
# sonnet 은 A·B·C 세 단계가 전부 정상 동작했고(A $1.08 · B $1.67 ·
# C $1.97 · client-side 추정), **haiku 는 파일을 쓰지 않아 실패했다.**
# 그래서 운영 경로가 `--auto-model` 을 **주지 않아도** 검증된 모델로 돈다 —
# 인자를 빼먹으면 Claude Code 의 그때그때 기본 모델을 타게 되고, 그것이
# haiku 로 바뀌는 날 자동 실행이 통째로 멈춘다. 바꾸는 것은 사용자 몫이고,
# 일부러 CLI 기본값을 쓰려면 `--auto-model cli` 다.
DEFAULT_AUTO_MODEL = "sonnet"

# `--auto-model` 에 이 낱말을 주면 `--model` 을 **넘기지 않는다** (Claude
# Code 자신의 기본 모델). 빈 문자열이 아니라 낱말로 둔 이유는, 빈 값을
# "지정 안 함" 으로 읽어 기본 모델을 건너뛰는 일이 없게 하려는 것이다.
CLI_DEFAULT_MODEL = ("cli", "default", "기본")

# `claude` 실행 파일을 직접 가리키고 싶을 때 쓰는 환경변수. PATH 에 없는
# 자리에 설치된 경우(윈도우 네이티브 설치·포터블)를 위한 탈출구다.
CLI_ENV = "TOTO_CLAUDE_CLI"

# 인증 상태. §1-6 의 어휘를 그대로 쓴다 — **'확인 못 함' 은 '실패' 가
# 아니다.** 옛 CLI 에는 `auth status` 가 없을 수 있고, 그때 멈추면 돌아갈
# 실행까지 막는다.
AUTH_OK = "ok"
AUTH_MISSING = "missing"            # 로그인이 없다 — 시작하지 않는다
AUTH_API_KEY = "api_key"            # 구독이 아니라 API 과금이다 — 멈춘다
AUTH_UNKNOWN = "unknown"            # 물어보지 못했다 — 기록만 남긴다

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

# **한국어 JSON 의 실측 자/토큰 비** (6-F-8 분석: 세 tool_result 에서
# 46,263자→22,347토큰 · 46,873→22,241 · 37,729→18,083, 평균 2.088).
# 회차 자료가 문맥에 들어가는지 **시작 전에** 어림하는 데만 쓴다 — 이 값으로
# 무엇을 자르거나 요약하지 않는다.
EST_CHARS_PER_TOKEN = 2.088

# 문맥을 넘겼을 때의 표식. 한도·인증과 **다른 상태**다 — 같은 `failed` 로
# 뭉뚱그리면 "자료가 너무 크다" 를 "왜인지 모르게 실패" 로 읽게 된다.
AGENT_TOO_LARGE = "too_large"
_TOO_LARGE_MARKERS = ("prompt is too long", "context window",
                      "context_length", "too many tokens",
                      "input is too long", "exceeds the maximum")

# 구독 한도·인증 실패를 알아보는 표식. **문구가 바뀌면 못 알아볼 수 있으므로
# 못 알아본 것은 `failed` 로 남기고 과금 전환은 어느 경우에도 하지 않는다.**
_USAGE_MARKERS = ("usage limit", "rate limit", "rate_limit", "session limit",
                  "사용량", "한도", "quota", "upgrade to", "limit reached")

# **실물에서 관측한 문구는 한 템플릿이고 가운데 낱말만 다르다** (윈도우 260054).
#
#     You've hit your session limit · resets 2:30am (Asia/Seoul)   2026-09-19
#     You've hit your weekly  limit · resets Sep 24, 9am           2026-09-20
#
# 낱말 하나씩 표에 더하면 다음 표현(daily·monthly…)에서 또 `failed` 로 떨어져
# 한도가 고장처럼 보인다 — 실제로 두 번 그랬다. 그래서 **관측한 두 건이
# 공유하는 모양**으로 잡는다. 없는 문구를 상상해 넣는 것이 아니라, 변하는
# 자리가 어디인지를 두 표본이 알려 준 것이다 (§1-1-1 의 태도와 같다).
_USAGE_SHAPE = ("hit your", "limit")


def _matches_usage_shape(low: str) -> bool:
    """`hit your <무엇> limit` 모양인가. 낱말이 **순서대로** 있어야 한다."""
    at = low.find(_USAGE_SHAPE[0])
    return at >= 0 and _USAGE_SHAPE[1] in low[at:]


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
    turns: int | None = None
    usage: dict = field(default_factory=dict)
    text: str = ""                  # 모델의 최종 출력 (봉투의 `result`)
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == AGENT_OK


@dataclass
class StageResult:
    """한 단계(A·B·C)의 결과. **경기 단위 결과를 담지 않는다** (6-F-9).

    단계 하나가 호출 하나이고 체크포인트 하나다. 경기별 상태를 여기에 두면
    "경기 7번부터 재개" 같은 구조가 다시 생긴다.
    """
    role: str = ""
    status: str = AGENT_FAILED
    message: str = ""
    session_id: str = ""
    matches: int = 0                # 검증을 통과한 경기 수
    expected: int = 0
    reused: bool = False            # 이미 끝나 있어 부르지 않았다
    cost_usd: float | None = None
    turns: int | None = None
    usage: dict = field(default_factory=dict)
    lines: list = field(default_factory=list)   # 검증기가 남긴 보고

    @property
    def ok(self) -> bool:
        return self.status == AGENT_OK

    @property
    def called(self) -> bool:
        """이 단계가 실제로 Claude 를 불렀나. 호출 수를 세는 자리다."""
        return not self.reused


@dataclass
class AutoResult:
    """회차 하나의 자동 워크플로 결과."""
    round_id: str = ""
    status: str = AGENT_FAILED
    stopped_reason: str = ""
    model: str = ""                 # 실제로 넘긴 모델 (빈 값 = CLI 기본)
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
    chars: int = 0                  # 회차 원본 자료 크기 (6-F-9 기준선)
    tokens: int = 0                 # 위를 실측 비율로 환산한 어림
    packet: dict = field(default_factory=dict)    # 공통 packet 실측 (6-F-10)
    # **여기서 한 번 만들고 A·B 가 이 문자열을 그대로 받는다** (§1-9
    # 불변조건 2). 두 번 만들면 같은 자료에서도 갈릴 여지가 생긴다.
    packet_text: str = ""
    index: "panelpacket.PanelIndex | None" = None
    # 체크포인트를 그대로 써도 되는지 가리는 기준 (6-F-12). packet 에서
    # 파생되므로 여기서 만든다 — 판정은 `panelwork` 가 한다 (§1-8).
    expect: dict = field(default_factory=dict)
    plan: "panelwork.ResumePlan | None" = None
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    auth: "AuthStatus | None" = None


# ==========================================================================
# 환경 — 비용 안전장치가 여기에 있다
# ==========================================================================
def cli_search_dirs() -> list:
    """`claude` 가 설치되는 **폴더**들. 파일 이름은 여기서 정하지 않는다.

    설치 방법마다 만들어 주는 파일이 다르다 — npm 은 `claude.cmd`,
    네이티브 설치는 `claude.exe`, 경우에 따라 `.ps1` 도 있다. 이름을 하나씩
    박으면 그중 하나만 다른 설치에서 조용히 못 찾는다. 그래서 **폴더만
    적고 확장자는 `PATHEXT` 에서 읽는다** — §1-4 의 "경로를 박지 말고
    모양으로 찾는다" 와 같은 태도다.
    """
    home = Path.home()
    if os.name == "nt":
        appdata = Path(os.environ.get("APPDATA")
                       or home / "AppData" / "Roaming")
        local = Path(os.environ.get("LOCALAPPDATA")
                     or home / "AppData" / "Local")
        dirs = [appdata / "npm",                     # npm -g
                local / "Programs" / "claude",       # 네이티브 설치
                home / ".local" / "bin",             # 네이티브 설치(사용자)
                home / ".claude" / "local"]          # migrate-installer
    else:
        dirs = [home / ".local" / "bin", home / ".claude" / "local",
                Path("/usr/local/bin"), Path("/opt/homebrew/bin")]

    # 같은 폴더를 두 번 적지 않는다 — 진단에 그대로 찍히므로 중복이 있으면
    # 두 자리를 본 것처럼 보인다 (`%LOCALAPPDATA%` 가 기본값과 같을 때 실제로
    # 그랬다).
    out, seen = [], set()
    for d in dirs:
        key = str(d)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def _exe_suffixes() -> list:
    """실행 파일로 인정되는 확장자. 윈도우는 `PATHEXT` 가 정한다.

    **`;` 로 나눈다 — `os.pathsep` 이 아니다.** `PATHEXT` 는 윈도우 전용
    변수라 언제나 `;` 구분이고, `os.pathsep` 으로 나누면 이 분기를 다른
    OS 에서 시험할 때 통째로 안 갈린다(실제로 그래서 못 갈렸다).
    """
    if os.name != "nt":
        return [""]
    raw = os.environ.get("PATHEXT") or ".COM;.EXE;.BAT;.CMD"
    out = [s.strip() for s in raw.split(";") if s.strip()]
    if ".PS1" not in [s.upper() for s in out]:
        out.append(".PS1")              # PATHEXT 에 없는 설치가 있다
    return out


def cli_candidates() -> list:
    """찾아볼 순서. **앞이 우선이다.**

    `shutil.which` 하나로는 모자란 경우가 실제로 있다 (Phase 6-F-7 §2-1).

      · 윈도우 npm 설치는 `%APPDATA%\\npm\\claude.cmd` 를 만드는데, 그
        폴더가 PATH 에 없는 계정이 있다.
      · 네이티브 설치는 `%LOCALAPPDATA%\\Programs` 나 `~/.local/bin` 아래다.
      · PowerShell 프로필의 alias 는 `which` 가 보지 못한다.

    그래서 PATH 를 먼저 보고, 못 찾으면 **알려진 설치 폴더 × PATHEXT** 를
    훑는다. 경로를 지어내지 않고 환경변수(`TOTO_CLAUDE_CLI`)라는 탈출구를
    둔다.
    """
    out, seen = [], set()

    def add(value):
        text = str(value or "").strip().strip('"')
        if text and text not in seen:
            seen.add(text)
            out.append(text)

    add(os.environ.get(CLI_ENV))
    add(shutil.which("claude"))
    for folder in cli_search_dirs():
        for suffix in _exe_suffixes():
            add(folder / f"claude{suffix.lower()}")
    return out


def cli_diagnosis() -> dict:
    """**무엇을 찾아봤는지** 그대로 돌려준다 (Phase 6-F-7 후속).

    실물 윈도우 실행에서 `찾지 못했습니다` 한 줄만 나왔는데, 그것만으로는
    **설치가 안 된 것**인지 **다른 자리에 설치된 것**인지 가릴 수 없다.
    둘은 할 일이 정반대다 — 하나는 설치, 하나는 `TOTO_CLAUDE_CLI` 다.
    사유를 남기라는 §1-6-1 이 여기에도 그대로 적용된다.

    **고쳐 주지 않는다.** 찾아본 자리와 그 결과만 적는다.
    """
    checked = [{"path": c, "exists": Path(c).is_file()}
               for c in cli_candidates()]
    return {
        "os": os.name,
        "env_var": CLI_ENV,
        "env_value": os.environ.get(CLI_ENV, ""),
        "which": shutil.which("claude") or "",
        "pathext": os.environ.get("PATHEXT", "") if os.name == "nt" else "",
        "path_entries": len([p for p in (os.environ.get("PATH") or "")
                             .split(os.pathsep) if p.strip()]),
        "checked": checked,
        "found": next((c["path"] for c in checked if c["exists"]), ""),
    }


def cli_help_lines() -> list:
    """못 찾았을 때 사람이 할 수 있는 일. **한 줄씩.**"""
    lines = ["claude 실행 파일을 찾지 못했습니다."]
    if os.name == "nt":
        lines += [
            "  ① Claude Code 가 이 PC 에 설치돼 있습니까?",
            "     PowerShell 에서 `claude --version` 이 도는지 보십시오.",
            "     안 되면 설치가 필요합니다 — npm 이 있으면",
            "     `npm install -g @anthropic-ai/claude-code`,",
            "     다른 방법은 https://code.claude.com/docs 를 보십시오.",
            "  ② 설치는 돼 있는데 여기서만 안 보이는 경우",
            "     PowerShell 에서 `(Get-Command claude).Source` 로 경로를",
            "     확인해 그 값을 환경변수에 넣으십시오:",
            f"     setx {CLI_ENV} \"C:\\전체\\경로\\claude.cmd\"",
            "     (새 창을 열어야 적용됩니다)",
            "  ③ WSL 안에만 설치돼 있으면 윈도우 파이썬에서는 보이지",
            "     않습니다 — 윈도우 쪽에 따로 설치하십시오.",
        ]
    else:
        lines += [
            f"  설치 뒤에도 못 찾으면 `which claude` 의 경로를 {CLI_ENV} 에 "
            f"넣으십시오.",
        ]
    return lines


def find_claude_cli() -> str:
    """`claude` 실행 파일 경로. 없으면 빈 문자열.

    이름을 코드에 박지 않고 `shutil.which` 로 먼저 찾는다 — 윈도우에서는
    `claude.cmd` 처럼 확장자가 붙어 있어도 `PATHEXT` 덕에 이것이 찾아 준다.
    PATH 에 없으면 `cli_candidates()` 의 관측된 설치 위치를 본다.

    **여기서는 실행해 보지 않는다** — 찾는 것과 도는 것은 다른 질문이라
    `cli_probe()` 가 따로 답한다 (§2-1).
    """
    for cand in cli_candidates():
        if Path(cand).is_file() or shutil.which(cand):
            return cand
    return ""


def _probe(argv: list, timeout: int):
    """짧은 CLI 호출 하나. (returncode, stdout, stderr) 또는 사유 문자열.

    **모델을 부르지 않는다** — `--version`·`auth status` 는 로컬 점검이다.
    """
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout, shell=False,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, f"{timeout}초 안에 답하지 않았습니다"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return proc, ""


def cli_probe(exe: str, timeout: int = 60):
    """**실제로 띄워 본다.** (ok, 버전, 사유).

    `shutil.which` 가 찾았다는 것과 그것이 돈다는 것은 다르다 — 윈도우의
    `claude.cmd` 는 npm 셸 심이라 Node 가 없거나 설치가 깨져 있으면
    **찾아지지만 돌지 않는다.** 그 차이를 14경기를 시작한 뒤가 아니라
    시작 전에 안다.
    """
    if not exe:
        return False, "", "실행 파일을 찾지 못했습니다"
    proc, why = _probe([exe, "--version"], timeout)
    if proc is None:
        return False, "", why
    text = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    line = text.splitlines()[0][:60] if text else ""
    if proc.returncode != 0:
        return False, line, f"종료코드 {proc.returncode}: {line or '출력 없음'}"
    if not line:
        return False, "", "버전을 답하지 않았습니다"
    return True, line, ""


@dataclass
class AuthStatus:
    """`claude auth status` 결과. **모델을 부르지 않는 로컬 점검이다.**"""
    state: str = AUTH_UNKNOWN
    method: str = ""
    provider: str = ""
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.state == AUTH_OK


def auth_status(exe: str, timeout: int = 60) -> AuthStatus:
    """로그인이 되어 있는가. **시작 전에 묻는다** (§2-2).

    묻지 않으면 14경기를 돌리기 시작한 뒤 첫 호출에서야 알게 되고, 그 사이
    작업 폴더와 자료 파일이 만들어진다.

    **인증 방식도 본다.** `authMethod` 가 API 키를 가리키면 구독이 아니라
    과금 경로라는 뜻이라 그 자리에서 멈춘다 — 환경변수를 지우는 것만으로는
    (호스트가 관리하는 설정처럼) 다 막히지 않는다.

    답을 얻지 못하면 `unknown` 이고 **멈추지 않는다** — 옛 CLI 에는 이
    하위 명령이 없을 수 있고, 없는 것을 실패로 치면 돌아갈 실행까지
    막는다 (§1-6: '확인 못 함' 은 '실패' 가 아니다).
    """
    out = AuthStatus()
    if not exe:
        out.message = "실행 파일을 찾지 못했습니다"
        return out
    proc, why = _probe([exe, "auth", "status", "--json"], timeout)
    if proc is None:
        out.message = why
        return out
    raw = (proc.stdout or "").strip()
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict) or "loggedIn" not in data:
        out.message = (f"인증 상태를 읽지 못했습니다 "
                       f"(종료코드 {proc.returncode})")
        return out

    out.method = str(data.get("authMethod") or "")
    out.provider = str(data.get("apiProvider") or "")
    low = out.method.lower()
    if not data.get("loggedIn"):
        out.state = AUTH_MISSING
        out.message = "로그인되어 있지 않습니다"
    elif "api_key" in low or "apikey" in low:
        out.state = AUTH_API_KEY
        out.message = f"인증 방식이 API 키입니다 ({out.method})"
    else:
        out.state = AUTH_OK
        out.message = f"{out.method or '로그인됨'} · {out.provider}".strip(" ·")
    return out


def resolve_model(choice: str | None) -> str:
    """`--auto-model` 해석. **주지 않으면 검증된 기본 모델이다** (§5).

    돌려주는 빈 문자열은 "`--model` 을 넘기지 않는다" 는 뜻이고, 그것은
    `--auto-model cli` 로 **일부러** 고를 때만 나온다.
    """
    value = (choice or "").strip()
    if not value:
        return DEFAULT_AUTO_MODEL
    if value.lower() in CLI_DEFAULT_MODEL or value in CLI_DEFAULT_MODEL:
        return ""
    return value


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
    # **문맥 초과를 먼저 본다.** 한도 표식과 낱말이 겹칠 수 있는데(`limit`),
    # 둘은 사용자가 할 일이 정반대다 — 한도는 기다리는 것이고 문맥 초과는
    # 자료를 줄이거나 나누는 것이다 (§1-6).
    if any(m in low for m in _TOO_LARGE_MARKERS):
        return AGENT_TOO_LARGE
    if any(m in low for m in _USAGE_MARKERS) or _matches_usage_shape(low):
        return AGENT_USAGE_LIMIT
    if any(m in low for m in _AUTH_MARKERS):
        return AGENT_AUTH
    return AGENT_FAILED


# ==========================================================================
# Preflight
# ==========================================================================
def preflight(report: Report | None, round_id: str,
              base: Path | None = None, index=None) -> Preflight:
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

    # ② Claude CLI — **찾는 것과 도는 것을 따로 본다** (§2-1).
    cli = find_claude_cli()
    if not cli:
        # **무엇을 찾아봤는지 적는다.** '못 찾았다' 한 줄만으로는 설치가
        # 안 된 것인지 다른 자리에 있는 것인지 가릴 수 없고, 둘은 할 일이
        # 정반대다 (§1-6-1).
        diag = cli_diagnosis()
        out.problems.extend(cli_help_lines())
        folders = []
        for row in diag["checked"]:
            folder = str(Path(row["path"]).parent)
            if folder not in folders:
                folders.append(folder)
        out.notes.append(
            f"찾아본 자리 {len(diag['checked'])}곳 (전부 없음) — "
            + " · ".join(folders[:6]))
        out.notes.append(
            f"PATH 항목 {diag['path_entries']}개 · which claude = "
            f"{diag['which'] or '없음'} · {CLI_ENV} = "
            f"{diag['env_value'] or '미설정'}")
    else:
        out.cli = cli
        ok, version, why = cli_probe(cli)
        out.version = version
        if not ok:
            # 찾아졌는데 돌지 않는 상태다 — 경로를 함께 적는다. 윈도우에서
            # `claude.cmd` 는 npm 셸 심이라 Node 가 없으면 이렇게 된다.
            out.problems.append(f"claude 를 실행하지 못했습니다 ({cli}): {why}")
        else:
            # **버전도 함께 적는다.** 경로만으로는 "찾았다" 까지만 알 수
            # 있고, 이 줄이 뜬 근거는 실제로 띄워 `--version` 을 받은
            # 것이다 (`cli_probe`). 무엇을 확인했는지 그대로 적는다.
            out.notes.append(
                f"claude {version} — {cli}" if version
                else f"claude 실행 파일 {cli}")

            # ②-b 인증 — 여기서 막히면 14경기를 시작하지 않는다.
            auth = auth_status(cli)
            out.auth = auth
            if auth.state == AUTH_MISSING:
                out.problems.append(
                    "Claude Code 에 로그인되어 있지 않습니다 — "
                    "`claude auth login` 으로 로그인한 뒤 다시 실행하십시오")
            elif auth.state == AUTH_API_KEY:
                out.problems.append(
                    f"{auth.message} — 패널 자동 분석은 Claude 구독 인증으로만 "
                    f"실행합니다. API 과금으로 도는 자동 실행은 시작하지 "
                    f"않습니다")
            elif auth.state == AUTH_UNKNOWN:
                # '확인 못 함' 은 '실패' 가 아니다 (§1-6). 기록만 남기고
                # 진행한다 — 실제로 로그인이 없으면 첫 호출이 `auth` 로
                # 멈추고, 그때도 과금으로 넘어가지 않는다.
                out.notes.append(f"인증 상태 확인 못 함 — {auth.message}")
            else:
                out.notes.append(f"인증 {auth.message}")

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
        # **회차 전체를 한 번에 보내므로 크기를 먼저 적는다** (6-F-9).
        # 6-F-10 부터는 원본이 아니라 **공통 packet** 이 나가므로 둘을
        # 함께 잰다 — 줄어든 것이 실측이라는 것을 시작 전에 보여 준다.
        #
        # **packet 을 여기서 만든다.** A·B 가 받는 문자열이 이 한 번의
        # 결과이고, 시작 전에 적는 크기도 그 문자열을 잰 값이다 — 보고와
        # 실제가 어긋날 자리가 없다.
        if report.matches:
            try:
                chars = len(pack_round_data(report))
                idx = index if index is not None \
                    else panelpacket.build_panel_index(report)
                body = panelpacket.packet_text(
                    panelpacket.build_compact_packet(idx))
                stats = panelpacket.measure(idx, body)
            except Exception as exc:                        # noqa: BLE001
                out.problems.append(f"회차 자료를 만들지 못했습니다: {exc}")
            else:
                out.chars = chars
                out.tokens = int(chars / EST_CHARS_PER_TOKEN)
                out.index, out.packet, out.packet_text = idx, stats, body
                # **출처 기준은 packet 에서 그대로 나온다** (6-F-12).
                # 여기서 새 해시 규칙을 만들지 않는다 — `source_manifest()`
                # 가 이미 쓰는 칸 이름을 그대로 쓴다 (§1-8).
                out.expect = dict(panelpacket.source_manifest(idx))
                out.expect["packet_sha256"] = panelpacket.packet_digest(body)
                out.expect["packet_version"] = panelpacket.PACKET_VERSION
                out.expect["moderator_prompt_version"] = \
                    moderator.MODERATOR_PROMPT_VERSION
                out.notes.append(
                    f"회차 원본 {chars:,}자 ≈ {out.tokens:,}토큰 "
                    f"(실측 {EST_CHARS_PER_TOKEN}자/토큰)")
                out.notes.extend(panelpacket.report_lines(stats))
                # **줄어든 것 자체를 성공으로 치지 않는다** (§32).
                out.problems.extend(panelpacket.too_small(stats))

    # ④ 작업 폴더
    try:
        auto_dir(out.round_id or "unknown", base).mkdir(parents=True,
                                                        exist_ok=True)
    except OSError as exc:
        out.problems.append(f"작업 폴더를 만들지 못했습니다: {exc}")

    # ⑤ 프롬프트 판 — 수동 경로와 같은 것을 쓴다는 기록
    out.notes.append(f"프롬프트 판 PANEL {panel.PANEL_PROMPT_VERSION} · "
                     f"MODERATOR {moderator.MODERATOR_PROMPT_VERSION}")

    # ⑥ 재개 — **어느 단계부터 도는지 시작 전에 정한다** (6-F-12 §19·§22).
    # 모델을 부르지 않으므로 `check()` 에서도 같은 값을 $0 로 볼 수 있다.
    if report is not None:
        try:
            out.plan = panelwork.resume_plan(report, out.round_id, base,
                                             expect=out.expect)
        except Exception as exc:                            # noqa: BLE001
            # 재개 판정이 안 되면 **전부 다시 돌리는 쪽**이 아니라 막는다 —
            # 모르는 채로 세 단계에 돈을 쓰지 않는다.
            out.problems.append(f"체크포인트를 확인하지 못했습니다: {exc}")

    out.ok = not out.problems
    return out


# ==========================================================================
# 작업 폴더
# ==========================================================================
def auto_root() -> Path:
    """작업 폴더의 뿌리. **저장소 밖이다** (`AUTO_ENV` 로 바꿀 수 있다).

    저장소 안에 두면 Claude Code 가 `CLAUDE.md` 를 자동 발견해 호출마다
    94,480토큰을 더 싣는다 — 상수 주석에 실측을 적어 두었다.
    """
    env = os.environ.get(AUTO_ENV, "").strip()
    if env:
        return Path(env)
    return Path(tempfile.gettempdir()).joinpath(AUTO_SCRATCH)


def auto_dir(round_id: str, base: Path | None = None) -> Path:
    """회차의 작업 폴더. `base` 를 주면 그 아래에 둔다 (테스트용)."""
    if base is not None:
        return panelwork.work_dir(round_id, base).joinpath(AUTO_DIRNAME)
    return auto_root().joinpath(str(round_id or "unknown"))


def stage_workspace(round_id: str, stage: str,
                    base: Path | None = None) -> Path:
    """단계 하나의 작업 폴더. **A·B·C 가 서로 다른 가지다** (§17).

    `stage` 는 역할 식별자이거나 `MODERATOR_DIR` 이다.
    """
    return auto_dir(round_id, base).joinpath(ROLE_DIRS.get(stage, stage))


# ==========================================================================
# 에이전트 실행
# ==========================================================================
def one_line(text: str) -> str:
    """명령줄에 실을 수 있게 **줄바꿈을 없앤다.** 낱말은 버리지 않는다.

    윈도우에서 `claude` 는 npm 셸 심(`claude.CMD`)이라 실제 계층이
    `python → claude.CMD → cmd.exe → node.exe` 다. `cmd.exe` 는 명령줄을
    **한 줄로** 읽으므로 인자 안의 줄바꿈이 거기서 명령을 끊는다 — 따옴표
    안이어도 마찬가지다. 리눅스에서는 무해해서 6-F-6 실측에서는 드러나지
    않았다.
    """
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    return " ".join(p.strip() for p in raw.split("\n") if p.strip())


def agent_argv(exe: str, prompt: str, system_file, workspace: Path,
               session_id: str, model: str = "",
               tools: str = AGENT_TOOLS) -> list:
    """`claude -p` 명령줄. **실행하지 않고 만들기만 한다** (테스트 가능).

    `--bare` 를 넣지 않는다 — 그 모드는 구독 로그인을 읽지 않고
    `ANTHROPIC_API_KEY` 를 요구해서, 이 워크플로의 비용 전제를 깬다.

    **어떤 인자에도 줄바꿈이 없다** (Phase 6-F-7 후속). 시스템 프롬프트는
    파일로 넘기고(`--append-system-prompt-file`) 지시문은 한 줄로 만든다 —
    실측으로 이 명령줄에 원래 줄바꿈이 54~93개 실려 있었다. 규칙을 여기
    한 곳에 두어 부르는 쪽이 저마다 다듬지 않게 한다 (§1-8).

    **모델에게 가는 시스템 프롬프트 글자는 바뀌지 않는다** — 같은 문자열을
    인자 대신 파일로 옮겼을 뿐이다 (`PANEL_PROMPT_VERSION` 무관).

    **자료는 여기 없다** (6-F-9). 경기자료는 stdin 으로 가므로 명령줄 길이가
    회차 크기와 무관해진다 — 윈도우 `cmd.exe` 의 8191자 한계와도 무관하다.

    `--continue`·`--resume` 를 넣지 않는다 (§17) — 넣는 순간 A·B 격리가
    깨진다. 테스트가 이 낱말들이 없는 것을 고정한다.
    """
    argv = [exe, "-p", one_line(prompt),
            "--output-format", "json",
            "--session-id", session_id,      # 호출마다 새 세션 (§8·§17)
            "--append-system-prompt-file", str(system_file),
            "--add-dir", str(workspace),     # 작업 폴더 바깥은 보지 않는다
            "--permission-mode", "acceptEdits",
            "--permission-prompts", "none",  # 물어야 하는 것은 거부된다
            "--tools", tools]                # 기본은 **도구 없음** (§15)
    if model:
        argv += ["--model", model]
    return argv


def _spawn_kwargs() -> dict:
    """자식을 **자기 프로세스 그룹**으로 띄운다 (Phase 6-F-7 §2-4).

    그래야 시간이 넘쳤을 때 손자까지 한 번에 끝낼 수 있고, Ctrl+C 가
    우리와 자식에게 동시에 날아들어 **누가 정리하는지 모르는 상태**가 되지
    않는다 — 정리는 우리가 한다.
    """
    if os.name == "nt":
        return {"creationflags": getattr(subprocess,
                                         "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _kill_tree(proc) -> None:
    """자식의 **자식까지** 끝낸다.

    윈도우에서 `claude.cmd` 는 npm 셸 심이라 실제 계층이
    `cmd.exe → node.exe` 다. 직접 자식(`cmd.exe`)만 죽이면 **node 가
    살아남아** 사용량이 계속 나가고 작업 폴더에 파일을 계속 쓴다 — 그러면
    재개할 때 '끝난 경기' 를 잘못 판정할 수 있다. `taskkill /T` 가 트리를
    통째로 끝낸다. POSIX 에서는 프로세스 그룹에 신호를 보낸다.

    실패해도 예외를 올리지 않는다 — 정리는 최선을 다하는 일이고, 그것
    때문에 회차가 죽으면 안 된다.
    """
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, timeout=30, shell=False)
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(os.getpgid(proc.pid), sig)
            except (OSError, ProcessLookupError):
                break
            try:
                proc.wait(timeout=10)
                return
            except subprocess.TimeoutExpired:
                continue
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def parse_envelope(raw: str) -> dict:
    """`--output-format json` 의 봉투. 읽지 못하면 **빈 dict** 다.

    봉투와 모델 출력을 헷갈리지 않으려고 자리를 나눈다 (§14) — 봉투는
    `session_id`·`usage`·`num_turns` 같은 실행 정보이고, 모델이 만든 것은
    그 안의 `result` 한 칸뿐이다.
    """
    try:
        data = json.loads((raw or "").strip()) if (raw or "").strip() else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def parse_claude_result(raw: str) -> tuple[str, str]:
    """봉투 → (모델 최종 출력, 사유). **꺼내 주기만 한다.**

    코드펜스 제거도 JSON 파싱도 여기서 하지 않는다 — 내용은 전부
    `panelwork` 가 보고, 그쪽이 이미 `panelpaste._strip_fence()` 를 거쳐
    붙여넣기·파일 경로와 **같은 문**을 지난다 (§1-8). 여기서 한 번 더
    손대면 자동 경로만 관대해진다.
    """
    data = parse_envelope(raw)
    if not data:
        return "", "실행 봉투를 JSON 으로 읽지 못했습니다"
    if data.get("is_error"):
        return "", str(data.get("result") or "실행이 오류로 끝났습니다")
    text = str(data.get("result") or "").strip()
    if not text:
        return "", "모델이 빈 응답을 돌려줬습니다"
    return text, ""


def run_agent(prompt: str, system: str, workspace: Path, *,
              timeout: int, model: str = "", cli: str = "",
              env: dict | None = None, stdin_text: str = "",
              tools: str = AGENT_TOOLS) -> AgentRun:
    """`claude -p` 한 번. **API 를 직접 부르지 않고 CLI 를 띄운다.**

    `--bare` 를 쓰지 않는다 — 그 모드는 구독 로그인을 읽지 않는다.
    `--permission-prompts none` 이라 사람에게 물어야 하는 것은 승인되지
    않고 거부되며, 그래서 무인 실행이 조용히 멈추지 않는다.

    **자료는 `stdin_text` 로 간다** (6-F-9). 명령줄에도 파일에도 싣지
    않으므로 회차 크기와 명령줄 길이가 무관해지고, 에이전트가 자료를
    `Read` 하느라 턴을 쓰지 않는다. 넘긴 것과 같은 글자를 작업 폴더에
    사본으로 남긴다 — 실패했을 때 "무엇을 보냈나" 를 되짚을 자료다.

    **시간이 넘치거나 Ctrl+C 가 오면 손자까지 끝낸다** (`_kill_tree`).
    `subprocess.run(timeout=)` 은 직접 자식만 죽이는데, 윈도우에서는 그
    자식이 `cmd.exe` 셸 심이라 정작 모델을 부르는 node 가 살아남는다.
    """
    exe = cli or find_claude_cli()
    out = AgentRun()
    if not exe:
        out.message = "claude 실행 파일을 찾지 못했습니다"
        return out

    wanted = str(uuid.uuid4())          # 호출마다 **새 세션** (§8·§17)
    out.requested_session_id = wanted
    # 시스템 프롬프트는 **명령줄이 아니라 파일**로 간다 (`one_line` 주석).
    sys_file = workspace / AGENT_SYSTEM
    try:
        sys_file.write_text(system, encoding="utf-8")
        if stdin_text:
            (workspace / AGENT_STDIN).write_text(stdin_text,
                                                 encoding="utf-8")
    except OSError as exc:
        out.message = f"작업 폴더에 쓰지 못했습니다: {exc}"
        return out
    argv = agent_argv(exe, prompt, sys_file, workspace, wanted, model,
                      tools=tools)

    try:
        proc = subprocess.Popen(
            argv, cwd=str(workspace), env=build_agent_env(env),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if stdin_text else subprocess.DEVNULL,
            text=True, encoding="utf-8",
            errors="replace", shell=False, **_spawn_kwargs())
    except OSError as exc:
        out.message = f"실행하지 못했습니다: {exc}"
        return out

    try:
        stdout, stderr = proc.communicate(input=stdin_text or None,
                                          timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        out.status = AGENT_TIMEOUT
        out.message = f"{timeout}초 안에 끝나지 않았습니다"
        return out
    except BaseException:
        # Ctrl+C 도 여기로 온다. **자식을 남기지 않고** 그대로 올려보낸다 —
        # 삼키면 사용자가 멈췄는데도 모델이 계속 돈다.
        _kill_tree(proc)
        raise

    out.returncode = proc.returncode
    raw = (stdout or "").strip()
    proc_stderr = stderr or ""
    # 실행 봉투를 남긴다 — 실패했을 때 "모델이 무엇을 답했나" 를 되짚을
    # 유일한 자료다 (§29). 조용히 버리면 사유를 알 수 없다 (§1-6-1).
    try:
        (workspace / AGENT_ENVELOPE).write_text(
            raw or proc_stderr, encoding="utf-8")
    except OSError:
        pass
    data = parse_envelope(raw)
    if data:
        out.session_id = str(data.get("session_id") or "")
        out.cost_usd = data.get("total_cost_usd")
        out.duration_ms = data.get("duration_ms")
        out.turns = data.get("num_turns")
        usage = data.get("usage")
        out.usage = usage if isinstance(usage, dict) else {}
        text = str(data.get("result") or "")
    else:
        text = raw

    if proc.returncode == 0 and data and not data.get("is_error"):
        out.status = AGENT_OK
        out.text = text
        out.message = text[:200]
        return out

    # 분류·사유 모두 **raw 까지 본다.** 예전에는 JSON 이 아닌 stdout 을
    # 통째로 버려서, 모델이 아니라 CLI 가 낸 오류(`unknown option …`)가
    # 화면에서 `종료코드 1` 한 줄로 뭉개졌다 (§1-6-1).
    out.status = _classify(f"{text}\n{raw}\n{proc_stderr}")
    detail = (text or raw or proc_stderr).strip()
    out.message = detail[:300] or (
        f"종료코드 {proc.returncode} · stdout·stderr 가 둘 다 비었습니다 "
        f"(실행 봉투: {workspace / AGENT_ENVELOPE})")
    return out


# ==========================================================================
# 자료 패킹 — **Python 이 읽어 stdin 으로 한 번 준다** (6-F-9 §4·§16)
# ==========================================================================
ROUND_TAG = "<ROUND: {round}>"
FILE_TAG = "<FILE: {no:02d}>"
MODERATOR_TAG = "=== MODERATOR_DATA ==="
ANALYST_A_TAG = "=== ANALYST_A ==="
ANALYST_B_TAG = "=== ANALYST_B ==="


def round_data_sheets(report: Report, settings=None) -> list:
    """회차 경기자료 시트들. **채팅에 첨부하는 것과 같은 함수**로 만든다.

    `panelexport._chunks()` 가 정한 부수·차례 그대로이고 본문도
    `panelexport.data_sheet()` 가 만든다 — 자동 경로가 자기 판을 따로
    만들면 "채팅에서 하는 것과 같은 것을 보낸다" 가 깨진다 (§25).

    `[3] 패널 자료 내보내기` 를 먼저 돌렸는지와 무관하게 **메모리에서**
    만든다. 디스크의 파일을 읽으면 그 파일이 낡았을 때 조용히 옛 자료를
    보내게 된다.
    """
    payloads = [panel.build_panel_payload(m) for m in report.matches]
    budget = panelexport.DEFAULT_MAX_BYTES
    if settings is not None:
        budget = int(getattr(settings, "panel", {}).get(
            "export_max_bytes", budget) or budget)
    groups = panelexport._chunks(payloads, budget)
    round_id = report.round_id or "unknown"
    return [panelexport.data_sheet(round_id, g, i + 1, len(groups))
            for i, g in enumerate(groups)]


def pack_round_data(report: Report, settings=None) -> str:
    """A·B 가 stdin 으로 받는 자료 한 덩어리.

    **원문을 요약하거나 변형하지 않는다** (§16) — 공백도 건드리지 않는다.
    붙는 것은 회차 표시와 파일 구분 머리표뿐이고, 그것이 없으면 모델이
    어디서 어디까지가 한 파일인지 알 수 없다.

    **A 와 B 가 이 함수의 같은 결과를 받는다** (3-B 불변조건 2). 역할을
    인자로 받지 않으므로 역할마다 다른 자료가 나갈 수 없다.
    """
    sheets = round_data_sheets(report, settings)
    parts = [ROUND_TAG.format(round=report.round_id or "unknown")]
    for i, sheet in enumerate(sheets, start=1):
        parts.append(FILE_TAG.format(no=i))
        parts.append(sheet)
    return "\n\n".join(parts)


def common_packet_text(report: Report, settings=None, index=None) -> str:
    """A·B 가 stdin 으로 받는 **공통 compact packet** (Phase 6-F-10).

    6-F-9 까지는 `pack_round_data()` 의 회차 원본 전체(실측 1,746,547자 ≈
    836,470토큰)가 두 역할에 그대로 갔다. 이제 `panelpacket` 이 반복되는
    메타데이터를 legend 로 올린 packet 을 만든다 — **값도 근거도 한 칸
    버리지 않고** 실측 −64% 다.

    **역할을 인자로 받지 않는다.** 두 분석가가 같은 문자열을 받는다는 것이
    시그니처로 표현된다 (§1-9 불변조건 2) — `pack_round_data()` 가 6-F-9
    에서 그랬던 것과 같은 방식이다.

    자료를 고르는 규칙은 전부 `panelpacket` 에 있다. 여기서 칸을 더하거나
    빼지 않는다 (§1-8).
    """
    idx = index if index is not None else panelpacket.build_panel_index(report)
    return panelpacket.packet_text(panelpacket.build_compact_packet(idx))


def pack_moderator_data(report: Report, base: Path | None = None) -> tuple:
    """C 가 stdin 으로 받는 자료. (본문, 사유).

    **경기자료 7개가 들어가지 않는다** (§7·§15 금지 4). 들어가는 것은 셋
    뿐이다 — 사회자 자료(축 지표가 빠진 판) · A 결과 배열 · B 결과 배열.

    사회자 자료는 `[--build-moderator-input]` 이 만들어 둔
    `03_사회자자료_완성.md` 를 그대로 쓴다. 그 안에 이미 경기별
    `"opinions"` 가 채워져 있으므로(6-F-3) A·B 배열은 **원문 보존용**으로
    따로 싣는다 — 사회자가 분석가가 실제로 적은 문장을 그대로 볼 수 있어야
    한다.
    """
    round_id = report.round_id or "unknown"
    sheet = panelexport.round_dir(round_id) / panelwork.COMPLETED_SHEET
    if not sheet.is_file():
        return "", f"{panelwork.COMPLETED_SHEET} 이 없습니다 ({sheet})"
    try:
        # 우리가 UTF-8 로 쓴 파일이지만 `-sig` 로 읽는다 — 사용자가 윈도우
        # 편집기로 열었다 저장하면 BOM 이 붙는다 (§1-7 과 같은 계열).
        body = sheet.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return "", f"{panelwork.COMPLETED_SHEET} 을 읽지 못했습니다: {exc}"

    blocks = [ROUND_TAG.format(round=round_id), MODERATOR_TAG, body]
    for tag, role in ((ANALYST_A_TAG, panel.DATA_ANALYST),
                      (ANALYST_B_TAG, panel.MATCHUP_ANALYST)):
        path = panelwork.path_for(round_id, role, base)
        if not path.is_file():
            return "", (f"{panel.ROLE_KO.get(role, role)} 결과가 없습니다 "
                        f"({path})")
        try:
            rows = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            return "", f"{path.name} 을 읽지 못했습니다: {exc}"
        blocks.append(tag)
        # compact 직렬화 — 공백을 줄인다 (§7). 내용은 그대로다.
        blocks.append(json.dumps(rows, ensure_ascii=False,
                                 separators=(",", ":")))
    return "\n\n".join(blocks), ""


# ==========================================================================
# 시스템 프롬프트 — **공통 규칙과 역할 규칙을 파일로 나눈다** (§3·§8·§9)
# ==========================================================================
def write_prompt_files(workspace: Path, stage: str,
                       settings=None) -> tuple:
    """공통·역할 지침을 작업 폴더에 쓰고 (공통 경로, 역할 경로) 를 준다.

    **내용은 전부 코드 상수에서 온다** — `panel.SYSTEM_COMMON` ·
    `panel.ROLE_PROMPTS` · `moderator.system_prompt()`. 손으로 베낀 사본을
    저장소에 두면 채팅 판과 자동 판이 조용히 갈라지고, 그 뒤로는 "왜 결과가
    다르지" 를 영원히 묻게 된다 (§1-11-1).

    파일로 떨어뜨리는 이유는 사람이 열어 볼 수 있게 하려는 것이고, 실제로
    `--append-system-prompt-file` 에 넘어가는 것은 둘을 이어 붙인
    `system.md` 다 (`run_agent` 가 쓴다).
    """
    workspace.mkdir(parents=True, exist_ok=True)
    common = workspace / COMMON_FILE
    common.write_text(panel.SYSTEM_COMMON, encoding="utf-8")
    if stage == MODERATOR_DIR:
        sims = moderator.simulations_of(settings) if settings is not None \
            else moderator.DEBATE_SIMULATIONS
        role_path = workspace / MODERATOR_PROMPT_FILE
        role_path.write_text(moderator.system_prompt(sims), encoding="utf-8")
    else:
        role_path = workspace / ROLE_PROMPT_FILES[stage]
        role_path.write_text(panel.ROLE_PROMPTS[stage], encoding="utf-8")
    return common, role_path


def stage_system(workspace: Path, stage: str, settings=None) -> str:
    """그 단계의 시스템 프롬프트. **역할 규칙은 그 단계에만 실린다** (§15 금지 6).

    사회자 지침은 `moderator.system_prompt()` 가 이미 공통 규칙을 포함하고
    있어 그것만 싣는다 — 두 번 실으면 같은 말이 두 벌 들어간다.
    """
    common, role_path = write_prompt_files(workspace, stage, settings)
    role_text = role_path.read_text(encoding="utf-8")
    if stage == MODERATOR_DIR:
        return role_text
    return common.read_text(encoding="utf-8") + "\n\n" + role_text


# ==========================================================================
# 지시문 — **분석 규칙은 한 줄도 여기에 없다** (전부 시스템 프롬프트에서 온다)
# ==========================================================================
# `panel.parse_opinion()` 이 요구하는 칸. 이름이 갈라지지 않도록 한 곳에
# 적고 테스트가 그 함수와 대조한다. 회차 배열이므로 `match_no` 가 붙는다.
OPINION_KEYS = ("match_no(정수)",
                "predicted_home(0 이상 정수 또는 null)",
                "predicted_away(0 이상 정수 또는 null)",
                "summary(문자열)", "rationale(문자열 배열)",
                "evidence_ids(이 경기의 근거 ID 배열)")

# `moderator.parse_result()` 가 요구하는 칸.
MODERATOR_KEYS = ("match_no(정수)", "simulations", "distribution",
                  "adopted_home", "adopted_away", "adopted_from",
                  "conclusion", "common_points", "differences",
                  "counterpoints", "uncertainty", "evidence_ids")


def _array_contract(count: int, keys) -> str:
    """"입력을 다 보고 배열로만 답하라" 한 문장. 장식을 붙이지 않는다 (§15 금지 8)."""
    return (f"표준입력에 이 회차 {count}경기 자료가 들어 있습니다. "
            f"{count}경기를 모두 분석하고 결과를 JSON 배열로만 출력하십시오 "
            f"(경기 하나가 객체 하나).\n\n"
            f"각 객체의 칸: {' · '.join(keys)}\n\n"
            f"코드펜스·머리말·설명 문장을 붙이지 말고 배열만 출력하십시오.")


def analyst_prompt(count: int) -> str:
    return _array_contract(count, OPINION_KEYS)


def moderator_prompt(count: int) -> str:
    return _array_contract(count, MODERATOR_KEYS)


# ==========================================================================
# 검증 — **기존 검증기를 그대로 쓴다** (§13)
# ==========================================================================
def verify_match(data: dict, match, role: str):
    """경기 하나의 결과를 **기존 검증기**로 본다. (의견, 사유).

    `panel.parse_opinion()` — 수동 경로·API 경로가 쓰는 그 함수다. 회차
    배열 전체는 `panelwork.parse_stage()` 가 같은 함수로 본다.
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


def _stage_file(round_id: str, stage: str, base: Path | None = None) -> Path:
    """모델이 돌려준 배열을 담을 자리. **Python 이 쓴다** (§15 금지 5)."""
    ws = stage_workspace(round_id, stage, base)
    ws.mkdir(parents=True, exist_ok=True)
    return ws / AGENT_RESULT


# ==========================================================================
# 단계 — A · B · C.  **한 단계가 Claude 호출 한 번이다** (6-F-9 §0)
# ==========================================================================
def _run_stage(report: Report, stage: str, prompt: str, stdin_text: str,
               save_argv: list, settings=None, *, model: str = "",
               cli: str = "", base: Path | None = None,
               timeout: int, expect: dict | None = None) -> StageResult:
    """한 단계를 **1회** 실행하고 결과를 기존 검증 경로에 태운다.

    A·B·C 가 이 함수 하나를 쓴다 — 다르게 두면 격리·검증·실패 처리가
    단계마다 갈라진다 (§1-8). 다른 것은 stdin 과 지시문과 저장 경로뿐이다.

    **검증을 통과한 뒤에만 출처를 적는다** (6-F-12). 순서가 반대면 실패한
    실행의 출처가 남아 다음 재개가 그것을 보고 '완료' 로 읽는다.
    """
    out = StageResult(role=stage, expected=len(report.matches))
    round_id = report.round_id or ""
    key = WORK_STAGE[stage]
    ws = stage_workspace(round_id, stage, base)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / AGENT_FAIL).unlink(missing_ok=True)

    def fail(status: str, why: str) -> StageResult:
        out.status, out.message = status, why
        try:
            (ws / AGENT_FAIL).write_text(f"{status}: {why}", encoding="utf-8")
        except OSError:
            pass
        # **시도를 적되 체크포인트를 건드리지 않는다.** `status`·`sha256`
        # 은 저장된 파일을 설명하는 칸이고, 실패는 `last_attempt` 로 간다
        # — 그래야 앞서 성공한 기록이 실패로 덮이지 않는다 (§17·§20).
        panelwork.record_stage(
            round_id, key, base,
            last_attempt={
                "status": (panelwork.STAGE_FAILED_LIMIT
                           if status == AGENT_USAGE_LIMIT
                           else panelwork.STAGE_FAILED),
                "agent_status": status, "reason": why,
                "session_id": out.session_id, "model": model,
                "at": panelwork.now_utc()})
        return out

    system = stage_system(ws, stage, settings)
    run = run_agent(prompt, system, ws, timeout=timeout, model=model, cli=cli,
                    stdin_text=stdin_text)
    out.session_id = run.session_id or run.requested_session_id
    out.cost_usd, out.turns, out.usage = run.cost_usd, run.turns, run.usage
    if not run.ok:
        return fail(run.status, run.message)

    text, why = parse_claude_result(
        (ws / AGENT_ENVELOPE).read_text(encoding="utf-8")
        if (ws / AGENT_ENVELOPE).is_file() else "")
    if not text:
        # 봉투를 못 읽었더라도 `run_agent` 가 이미 꺼내 둔 것이 있으면 쓴다.
        text = (run.text or "").strip()
        if text:
            why = ""
    if not text:
        return fail(AGENT_NO_OUTPUT, why or "모델이 빈 응답을 돌려줬습니다")

    path = _stage_file(round_id, stage, base)
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        return fail(AGENT_INVALID, f"결과를 쓰지 못했습니다: {exc}")

    # 내용 검증은 **기존 경로**가 한다 (§13) — 1·2단계는
    # `panelwork.save_stage()`, 3단계는 `panelpaste.convert()` +
    # `panelimport.validate()` + `moderator.parse_result()`.
    if run_existing_cli(save_argv + [str(path)]) != 0:
        return fail(AGENT_INVALID, "결과 검증에 실패했습니다 (위 로그 참고)")
    out.status = AGENT_OK
    out.matches = len(report.matches)
    # 통과했다. 저장 함수가 이미 적어 둔 행에 **자동 경로만 아는 것**을
    # 합친다 — 무엇으로 만들었나(packet·시스템 프롬프트)와 누가 만들었나
    # (모델·세션)다. 여기서 해시 규칙을 새로 만들지 않는다.
    extra = {k: v for k, v in (expect or {}).items()
             if k in panelwork.PACKET_KEYS
             or k == "moderator_prompt_version"}
    panelwork.record_stage(round_id, key, base, origin="auto", model=model,
                           session_id=out.session_id,
                           system_sha256=panelwork._sha(system),
                           stdin_sha256=panelwork._sha(stdin_text),
                           turns=run.turns, cost_usd=run.cost_usd,
                           last_attempt={"status": panelwork.STAGE_COMPLETE,
                                         "agent_status": AGENT_OK,
                                         "session_id": out.session_id,
                                         "model": model,
                                         "at": panelwork.now_utc()},
                           **extra)
    return out


def run_stage_analyst(report: Report, role: str, settings=None, *,
                      model: str = "", cli: str = "",
                      base: Path | None = None, index=None, packet: str = "",
                      expect: dict | None = None,
                      timeout: int = ANALYST_AGENT_TIMEOUT) -> StageResult:
    """한 역할로 회차 전체를 **1회** 분석한다 (6-F-9 §5·§6).

    **A 와 B 는 서로의 결과를 보지 않는다.** stdin 은
    `common_packet_text()` 하나에서 오고, 그 함수는 **결과가 아니라 회차
    자료만** 본다 — A 의 결과가 B 의 입력에 들어갈 경로가 코드에 없다
    (테스트로 고정).

    **두 역할이 받는 문자열은 같다** (6-F-10 · §1-9 불변조건 2).
    `packet` 을 주면 그 문자열을 그대로 쓴다 — 호출부가 한 번 만들어
    둘에 넘기므로 두 번 만들어 갈릴 자리가 없다. 주지 않으면 여기서
    만드는데, 그것도 역할을 보지 않으므로 결과는 같다.
    """
    return _run_stage(
        report, role, analyst_prompt(len(report.matches)),
        packet or common_packet_text(report, settings, index),
        ["--round", report.round_id or "", "--role", role,
         "--save-panel-opinion"],
        settings, model=model, cli=cli, base=base, timeout=timeout,
        expect=expect)


def run_stage_moderator(report: Report, settings=None, *, model: str = "",
                        cli: str = "", base: Path | None = None,
                        expect: dict | None = None,
                        timeout: int = MODERATOR_AGENT_TIMEOUT
                        ) -> StageResult:
    """사회자를 **1회** 실행한다 (6-F-9 §7).

    **경기자료 7개를 다시 주지 않는다** — stdin 은 사회자 자료와 A·B
    결과뿐이다 (`pack_moderator_data`).
    """
    out = StageResult(role=MODERATOR_DIR, expected=len(report.matches))
    stdin_text, why = pack_moderator_data(report, base)
    if not stdin_text:
        out.status, out.message = AGENT_INVALID, why
        return out
    return _run_stage(
        report, MODERATOR_DIR, moderator_prompt(len(report.matches)),
        stdin_text,
        ["--round", report.round_id or "", "--save-moderator-result"],
        settings, model=model, cli=cli, base=base, timeout=timeout,
        expect=expect)


# ==========================================================================
# 전체 워크플로 — 상태를 읽고 **끝난 단계는 건너뛴다** (§23)
# ==========================================================================
_BAR = "━" * 44

# 단계 → 화면 이름. 로그가 **경기가 아니라 단계** 중심이다 (§21).
STAGE_LABEL = {panel.DATA_ANALYST: "Data Analyst",
               panel.MATCHUP_ANALYST: "Matchup Analyst",
               MODERATOR_DIR: "Moderator"}

# 정상 실행의 Claude 세션 수. **이 수가 늘면 설계가 되돌아간 것이다** (§22).
EXPECTED_SESSIONS = 3


def _usage_line(res: StageResult) -> str:
    """단계 하나의 사용량. 없으면 빈 문자열이고 지어내지 않는다 (§1-5)."""
    u = res.usage or {}
    got = [(k, u.get(k)) for k in ("input_tokens",
                                   "cache_creation_input_tokens",
                                   "cache_read_input_tokens",
                                   "output_tokens")]
    total_in = sum(v for k, v in got if k != "output_tokens"
                   and isinstance(v, int))
    out_tok = u.get("output_tokens")
    bits = []
    if total_in:
        bits.append(f"입력 {total_in:,}")
    if isinstance(out_tok, int):
        bits.append(f"출력 {out_tok:,}")
    if res.turns is not None:
        bits.append(f"{res.turns}턴")
    if res.cost_usd is not None:
        bits.append(f"${res.cost_usd:.4f}")
    return " · ".join(bits)


def check(round_id: str, report: Report | None = None, *,
          model: str = "", base: Path | None = None, echo=print) -> bool:
    """**시작해도 되는지만 본다. 모델을 부르지 않는다.**

    회차 하나가 Claude 세션 셋이다(6-F-9). 그런데 지금까지는 "내 PC 가
    준비됐나" 를 묻는 방법이 **그것을 시작해 보는 것**뿐이었다 — 윈도우에서
    무언가 어긋나면 돈과 시간을 쓴 뒤에 알게 된다.

    이 경로는 `preflight()` 만 돌리고 멈춘다. 비용 0 이고, 그러면서도
    CLI 탐색 · 실행 · 인증 · 저장본 · 모델 결정을 **실제로** 확인한다.

    `run()` 을 복제하지 않는다 — 같은 `preflight()` 를 부른다 (§1-8).
    """
    if report is None:
        from . import artifact
        report, why = artifact.load(str(round_id or ""))
        if report is None:
            echo(f"✗ 저장된 회차 분석 결과가 없습니다 — {why}")
            return False

    pre = preflight(report, round_id, base)
    echo(_BAR)
    echo(f"패널 자동 분석 준비 점검 — {pre.round_id}  (모델 호출 0회)")
    echo(_BAR)
    for note in pre.notes:
        echo(f"  · {note}")
    echo(f"  · 모델 {resolve_model(model) or 'Claude Code 기본'}")
    echo(f"  · 작업 폴더 {auto_dir(pre.round_id, base)}")
    if pre.problems:
        echo("")
        for problem in pre.problems:
            echo(f"  ✗ {problem}")
        echo("")
        echo("  고친 뒤 다시 점검하십시오. 지금 [2] 를 돌리면 같은 자리에서 "
             "멈춥니다.")
        return False
    echo("")
    # **무엇을 다시 돌릴지 $0 에 보여 준다** (6-F-12 §21). 실행이 쓰는
    # 것과 같은 `preflight()` 의 계획이라 여기서 본 것이 그대로 돈다.
    if pre.plan is not None:
        echo("  체크포인트")
        for line in pre.plan.lines():
            echo(f"  {line}")
        start = pre.plan.resume_from
        todo = [s for s in pre.plan.stages
                if not s.reuse and s.stage in WORK_STAGE.values()]
        echo(f"  · 시작 단계 {start or '없음 (전부 재사용)'} · "
             f"Claude 호출 {len(todo)}회 예정")
        echo("")
    echo(f"  ✓ 준비됐습니다 — {pre.matches}경기")
    echo(f"    이제 [2] 패널 자동 분석 을 돌리면 됩니다. 회차 하나에 "
         f"A·B·C 합쳐 {EXPECTED_SESSIONS}회를 부릅니다.")
    return True


def run(round_id: str, report: Report | None = None, settings=None, *,
        model: str = "", base: Path | None = None, rerun: bool = False,
        progress=None, echo=print) -> AutoResult:
    """`[패널 자동 분석]` 의 본체. 한 번 부르면 [4] 까지 간다.

    사람에게 확인을 묻지 않는다 (§36). 다만 안전·오류 조건 — API 키 감지,
    인증 없음, 사용량 한도, 스키마 실패, 자료 손상, CLI 없음 — 에서는
    **즉시 멈춘다.**

    `progress` 는 6-F-8 까지 경기별 진행을 찍던 자리다. 6-F-9 는 단계가
    호출 하나라 경기별 진행이 없고, 인자는 부르는 쪽을 깨지 않으려고
    남겨 두었다 — 주면 단계마다 한 번 불린다.
    """
    out = AutoResult(round_id=str(round_id or ""))
    # **모델은 여기 한 곳에서 정한다** (§5). 아래 단계 함수들은 받은 값을
    # 그대로 넘기기만 하고, `agent_argv` 의 "빈 문자열이면 `--model` 을
    # 넘기지 않는다" 규칙도 그대로다 — 바뀐 것은 정책의 자리뿐이다.
    model = resolve_model(model)
    echo(_BAR)
    echo(f"Panel Auto Workflow — {out.round_id}")
    echo(_BAR)
    echo("")

    if report is None:
        from . import artifact
        report, why = artifact.load(out.round_id)
        if report is None:
            echo(f"[준비] 자료 확인        ✗  {why}")
            out.status, out.message = AGENT_FAILED, why
            return out

    pre = preflight(report, out.round_id, base)
    for note in pre.notes:
        out.lines.append(note)
    if not pre.ok:
        echo("[준비] 자료 확인        ✗")
        for p in pre.problems:
            echo(f"      └ {p}")
        # **막혔을 때야말로 진단이 필요하다.** 정상 경로에서는 notes 를
        # 조용히 두지만, 여기서 감추면 사용자가 무엇을 고쳐야 할지 모른다.
        for note in pre.notes:
            echo(f"      · {note}")
        out.status = AGENT_FAILED
        out.stopped_reason = pre.problems[0]
        return out
    echo(f"[준비] 자료 확인        ✓  {pre.matches}경기 · {pre.version}")
    echo(f"      └ 모델 {model or 'Claude Code 기본'} · 작업 폴더 "
         f"{auto_dir(out.round_id, base)}")
    out.model = model
    # **무엇을 얼마나 보내는지 먼저 보여 준다** (6-F-10 §26·§34).
    # 한 덩어리이고 A·B 가 그것을 그대로 받는다 — 역할마다 줄을 나누지
    # 않는다.
    if pre.packet:
        echo("")
        for line in panelpacket.report_lines(pre.packet):
            echo(line)
        echo("")
    # 색인·packet·측정값을 남긴다 (6-F-10 §18). 진단용이고 **실패해도
    # 실행을 죽이지 않는다** — 리포트는 이것과 무관하다 (§1-6).
    # **보낸 문자열 그대로** 남긴다 — 다시 만들면 캐시와 실제가 갈린다.
    if pre.index is not None:
        try:
            panelpacket.write_cache(pre.index, base, pre.packet_text)
        except OSError as exc:
            out.lines.append(f"packet 캐시를 쓰지 못했습니다: {exc}")

    # **재개 계획을 시작 전에 보여 준다** (6-F-12 §22). `preflight` 가
    # 이미 만들어 둔 것이라 `--panel-auto-check` 와 같은 값이다 — 점검이
    # 통과했는데 실행이 다르게 도는 일이 없다 (§1-8).
    plan = pre.plan if pre.plan is not None else panelwork.resume_plan(
        report, out.round_id, base, expect=pre.expect, settings=settings)
    # **Resume 이 기본이고 Rerun 은 명시할 때만이다** (6-F-12 §19).
    # 다시 돌리는 것은 세 단계에 돈을 쓰는 일이라 기본값이 될 수 없다.
    if rerun:
        plan = panelwork.force_rerun(plan)
        echo("다시 실행 (요청) — 끝난 단계도 처음부터 돌립니다")
    echo("재개 계획")
    for line in plan.lines():
        echo(line)
    echo(f"  시작 단계: {plan.resume_from or '없음 (전부 재사용)'}")
    echo("")

    # Ctrl+C 로 멈춰도 **자식을 남기지 않고**(`run_agent`) 끝난 단계는
    # 보존된다 — 재개는 `panelwork.resume_plan()` 이 파일을 읽고 정한다.
    # 예외를 삼키지 않는다: 종료코드 정책은 `main()` 것이다 (§1-7-1).
    try:
        return _run_stages(report, settings, out, pre, plan, model=model,
                           base=base, progress=progress, echo=echo,
                           index=pre.index)
    except KeyboardInterrupt:
        echo("")
        echo("  중단했습니다 — 끝난 단계 결과는 보존되었습니다. "
             "다시 실행하면 멈춘 단계부터 재개합니다.")
        raise


def _run_stages(report, settings, out: AutoResult, pre: Preflight,
                plan: "panelwork.ResumePlan", *, model: str, base, progress,
                echo, index=None) -> AutoResult:
    """A → B → 조립 → C → [4]. `run()` 이 준비한 것 위에서 돈다.

    **단계가 checkpoint 다** (§11). 경기 단위 재개가 없으므로, 한 단계가
    실패하면 그 단계 전체를 다시 돌린다 — 앞 단계 결과는 그대로 쓴다.

    건너뛸지는 **`plan` 이 정한다** (6-F-12). 파일이 있느냐가 아니라
    내용이 검증을 지나고 출처가 맞느냐다 — 6-F-6~11 까지는 존재만 봤다.
    """
    total = len(report.matches)

    def _stop(stage_name: str, res: StageResult) -> AutoResult:
        echo(f"      └ {res.status}: {res.message}")
        out.status = res.status
        if res.status == AGENT_USAGE_LIMIT:
            out.stopped_reason = WORKFLOW_STOPPED_USAGE_LIMIT
            echo("")
            echo("Claude 사용량 한도에 도달했습니다.")
            echo("  자동으로 API 과금으로 전환하지 않습니다 — 한도가 "
                 "회복된 뒤 다시 실행하면 이어서 진행합니다.")
            echo("  끝난 단계 결과는 보존되었습니다.")
        elif res.status == AGENT_TOO_LARGE:
            out.stopped_reason = f"{stage_name}: 문맥 초과"
            echo("")
            echo("회차 자료가 모델 문맥에 들어가지 않았습니다.")
            echo(f"  이 회차는 {total}경기 · 약 {pre.tokens:,}토큰입니다. "
                 f"문맥이 더 큰 모델로 다시 돌리십시오 "
                 f"(`--auto-model`) — 기본값은 "
                 f"{DEFAULT_AUTO_MODEL} 입니다.")
            echo("  끝난 단계 결과는 보존되었습니다.")
        else:
            out.stopped_reason = f"{stage_name}: {res.message}"
            echo("")
            echo("  끝난 단계 결과는 보존되었습니다. 다시 실행하면 "
                 "실패한 단계부터 재개합니다.")
        return out

    def _stage(order: int, key: str, stage: str, runner) -> StageResult | None:
        """단계 하나. 이미 끝나 있으면 **부르지 않는다** (§11)."""
        label = STAGE_LABEL[stage]
        head = f"[{order}/{EXPECTED_SESSIONS}] {label} — {total} matches"
        row = plan.plan(key)
        if row is not None and row.reuse:
            cp = row.checkpoint
            res = StageResult(role=stage, status=AGENT_OK, reused=True,
                              expected=total,
                              matches=(cp.matches if cp else total))
            note = f" · {row.reason}" if row.reason else ""
            echo(f"{head}  ✓  (이미 완료 — 건너뜁니다"
                 f"{'; ' + cp.state if cp else ''}{note})")
        else:
            echo(head)
            echo("      Claude session started")
            res = runner()
            if res.ok:
                echo("      Claude session completed")
                usage = _usage_line(res)
                if usage:
                    echo(f"      {usage}")
                echo(f"      {label} result validated: "
                     f"{res.matches}/{res.expected}")
            out.agent_calls += 1 if res.called else 0
            out.reused_calls += 0 if res.called else 1
        out.stages[stage] = res
        if progress:
            progress(stage, order, EXPECTED_SESSIONS, res)
        return res

    # **packet 은 preflight 가 만든 그 하나다** (6-F-10 · §1-9 불변조건 2).
    # 두 호출에 **같은 문자열 객체**를 넘긴다 — 여기서 다시 만들지 않는다.
    packet = pre.packet_text

    # ---- [1/3] A ---------------------------------------------------------
    res = _stage(1, panelwork.STAGE_A, panel.DATA_ANALYST,
                 lambda: run_stage_analyst(report, panel.DATA_ANALYST,
                                           settings, model=model,
                                           cli=pre.cli, base=base,
                                           index=index, packet=packet,
                                           expect=pre.expect))
    if not res.ok:
        return _stop("A", res)

    # ---- [2/3] B — A 가 끝난 뒤에만 시작한다. A 결과는 넘기지 않는다 (§6)
    res = _stage(2, panelwork.STAGE_B, panel.MATCHUP_ANALYST,
                 lambda: run_stage_analyst(report, panel.MATCHUP_ANALYST,
                                           settings, model=model,
                                           cli=pre.cli, base=base,
                                           index=index, packet=packet,
                                           expect=pre.expect))
    if not res.ok:
        return _stop("B", res)

    # ---- 조립 — A·B 가 **여기서 처음 만난다** ---------------------------
    if not plan.reuse(panelwork.STAGE_INPUT):
        if run_existing_cli(["--round", out.round_id,
                             "--build-moderator-input"]) != 0:
            out.status = AGENT_FAILED
            out.stopped_reason = "사회자 자료 조립 실패"
            echo("[3/3] Moderator          ✗  자료 조립 실패")
            return out

    # ---- [3/3] C ---------------------------------------------------------
    res = _stage(3, panelwork.STAGE_RESULT, MODERATOR_DIR,
                 lambda: run_stage_moderator(report, settings, model=model,
                                             cli=pre.cli, base=base,
                                             expect=pre.expect))
    if not res.ok:
        return _stop("C", res)

    # ---- 반영 ------------------------------------------------------------
    saved = panelwork.moderator_result_path(out.round_id, base)
    if run_existing_cli(["--round", out.round_id,
                         "--paste-panel-result", str(saved)]) != 0:
        out.status = AGENT_FAILED
        out.stopped_reason = "[4] 반영 실패"
        echo("[반영] 리포트            ✗")
        echo("")
        echo("  사회자 결과는 보존되었습니다. 다시 실행하면 반영부터 "
             "재개합니다.")
        return out
    echo("[반영] 리포트            ✓")

    out.status = AGENT_OK
    from .settings import load_settings
    st = settings if settings is not None else load_settings()
    name = st.output.get("filename", "toto_{round}.html").format(
        round=out.round_id)
    out.report_path = st.output_dir / name
    echo("")
    echo(_BAR)
    echo("Panel completed")
    echo(f"Claude sessions: {out.agent_calls}"
         + (f" (재사용 {out.reused_calls})" if out.reused_calls else ""))
    echo(f"결과: {out.report_path}")
    echo(_BAR)
    return out


__all__ = [
    "AUTO_DIRNAME", "AUTO_ENV", "AUTO_SCRATCH", "ROLE_DIRS", "MODERATOR_DIR",
    "WORK_STAGE",
    "AGENT_STDIN", "AGENT_SYSTEM", "AGENT_ENVELOPE", "AGENT_RESULT",
    "AGENT_FAIL",
    "COMMON_FILE", "ROLE_PROMPT_FILES", "MODERATOR_PROMPT_FILE",
    "ANALYST_AGENT_TIMEOUT", "MODERATOR_AGENT_TIMEOUT",
    "SCRUB_API", "SCRUB_SESSION", "AGENT_TOOLS",
    "OPINION_KEYS", "MODERATOR_KEYS", "EXPECTED_SESSIONS", "STAGE_LABEL",
    "AGENT_OK", "AGENT_INVALID", "AGENT_TIMEOUT", "AGENT_USAGE_LIMIT",
    "AGENT_AUTH", "AGENT_NO_OUTPUT", "AGENT_FAILED", "AGENT_TOO_LARGE",
    "WORKFLOW_STOPPED_USAGE_LIMIT", "EST_CHARS_PER_TOKEN",
    "DEFAULT_AUTO_MODEL", "CLI_DEFAULT_MODEL", "CLI_ENV",
    "AUTH_OK", "AUTH_MISSING", "AUTH_API_KEY", "AUTH_UNKNOWN",
    "AgentRun", "StageResult", "AutoResult", "Preflight", "AuthStatus",
    "cli_candidates", "cli_search_dirs", "cli_diagnosis", "cli_help_lines",
    "cli_probe", "auth_status", "resolve_model",
    "find_claude_cli", "build_agent_env", "preflight",
    "auto_root", "auto_dir", "stage_workspace",
    "one_line", "agent_argv", "run_agent",
    "parse_envelope", "parse_claude_result",
    "round_data_sheets", "pack_round_data", "common_packet_text",
    "pack_moderator_data",
    "write_prompt_files", "stage_system",
    "analyst_prompt", "moderator_prompt", "verify_match",
    "run_existing_cli", "run_stage_analyst", "run_stage_moderator",
    "run", "check",
]
