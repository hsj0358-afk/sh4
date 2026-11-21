"""Anthropic API 경계 (Phase 3-B).

**이 모듈은 분석을 하지 않는다.** 클라이언트를 만들고, 호출하고, 실패를
분류하고, 원문을 돌려줄 뿐이다. xG·슈팅·근거·확률 계산이 여기 들어오면 안
된다 — 그런 것은 이미 Phase 2 가 만들어 두었다.

`briefing/` 의 구현을 **import 하지 않는다.** 두 프로젝트는 설정·의존성·
실행 경로가 완전히 분리돼 있고 `briefing/` 은 수정 금지다. import 하면 토토
실행이 저쪽 파일에 묶인다. 검증된 패턴(지연 import · 코드펜스 제거)만 옮겨
적었다.

## SDK 가 없어도 프로그램은 돈다

`anthropic` 을 **호출 시점에** import 한다. 설치돼 있지 않으면 패널만
`sdk_unavailable` 로 끝나고 나머지 리포트는 그대로 나온다.

## API 키

`ANTHROPIC_API_KEY` 를 **환경변수에서 호출 시점에** 읽는다. `Settings` 에
담지 않는 이유는 하나다 — 설정 객체는 로그·디버그 출력에 통째로 찍히기
쉬운데 키가 거기 섞이면 안 된다. `.env` 는 `settings.load_settings()` 가
이미 `os.environ` 으로 밀어 넣는다.
"""
from __future__ import annotations

import logging
import os
import re
import time

log = logging.getLogger(__name__)

# 실패 종류. 재시도할 수 있는 것과 없는 것을 나눈다.
NO_API_KEY = "no_api_key"
SDK_UNAVAILABLE = "sdk_unavailable"
RATE_LIMIT = "rate_limit"
SERVER_ERROR = "server_error"
TIMEOUT = "timeout"
NETWORK_ERROR = "network_error"
INVALID_RESPONSE = "invalid_response"

RETRYABLE = (RATE_LIMIT, SERVER_ERROR, TIMEOUT, NETWORK_ERROR)

REASON_KO = {
    NO_API_KEY: "ANTHROPIC_API_KEY 없음",
    SDK_UNAVAILABLE: "anthropic 미설치",
    RATE_LIMIT: "요청 한도",
    SERVER_ERROR: "서버 오류",
    TIMEOUT: "시간 초과",
    NETWORK_ERROR: "네트워크 오류",
    INVALID_RESPONSE: "응답 형식 오류",
}

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_TOKENS = 1200
DEFAULT_TIMEOUT_SEC = 60.0
API_KEY_ENV = "ANTHROPIC_API_KEY"
MODEL_ENV = "ANTHROPIC_MODEL"


class LLMError(Exception):
    """분류된 호출 실패. `kind` 로 재시도 여부를 정한다."""

    def __init__(self, kind: str, detail: str = "") -> None:
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE

    @property
    def korean(self) -> str:
        return REASON_KO.get(self.kind, self.kind)


def panel_config(settings) -> dict:
    """패널 설정 (`config_toto.yaml` 의 `panel:` 블록 + 환경변수)."""
    cfg = dict(getattr(settings, "panel", None) or {})
    # 환경변수가 설정 파일을 이긴다 — briefing 쪽 관례와 같고, 모델을 잠깐
    # 바꿔 보려고 설정 파일을 고치게 만들지 않기 위해서다.
    cfg["model"] = (os.environ.get(MODEL_ENV)
                    or cfg.get("model") or DEFAULT_MODEL)
    cfg.setdefault("max_tokens", DEFAULT_MAX_TOKENS)
    cfg.setdefault("timeout_sec", DEFAULT_TIMEOUT_SEC)
    return cfg


def unavailable_reason() -> str:
    """지금 호출할 수 있나. 못 하면 사유 종류, 할 수 있으면 빈 문자열.

    **키를 돌려주지 않는다** — 있는지만 본다.
    """
    try:
        import anthropic                                    # noqa: F401
    except Exception:
        return SDK_UNAVAILABLE
    if not os.environ.get(API_KEY_ENV):
        return NO_API_KEY
    return ""


def _client(timeout: float):
    try:
        import anthropic
    except Exception as exc:                                # noqa: BLE001
        raise LLMError(SDK_UNAVAILABLE, str(exc)) from exc
    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise LLMError(NO_API_KEY)
    return anthropic.Anthropic(api_key=key, timeout=timeout)


def _classify(exc: Exception) -> str:
    """SDK 예외를 종류로 나눈다.

    예외 클래스를 직접 import 해서 비교하지 않는다 — SDK 버전마다 이름과
    상속 구조가 달라서, 있는 것만 골라 잡으면 나머지가 조용히 미분류로
    떨어진다. 상태 코드와 클래스 이름으로 판정한다.
    """
    status = getattr(exc, "status_code", None)
    if status == 429:
        return RATE_LIMIT
    if isinstance(status, int) and 500 <= status < 600:
        return SERVER_ERROR
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return TIMEOUT
    if "ratelimit" in name:
        return RATE_LIMIT
    if "connection" in name or "network" in name:
        return NETWORK_ERROR
    if "apistatus" in name or "internalserver" in name:
        return SERVER_ERROR
    return NETWORK_ERROR


def extract_text(message) -> str:
    """응답에서 텍스트 블록만 이어 붙인다."""
    blocks = getattr(message, "content", None) or []
    return "".join(getattr(b, "text", "") for b in blocks
                   if getattr(b, "type", "") == "text")


_FENCE_OPEN = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)
_FENCE_CLOSE = re.compile(r"\s*```$")


def strip_fence(text: str) -> str:
    """코드펜스만 벗긴다. **내용을 고치지 않는다.**

    느슨한 복구는 하지 않는다 — `2-1` 같은 문자열을 스코어로 해석해 주는
    파서를 만들면 스키마를 어긴 응답이 조용히 통과한다.
    """
    text = (text or "").strip()
    text = _FENCE_OPEN.sub("", text)
    return _FENCE_CLOSE.sub("", text).strip()


def complete(system: str, user: str, *, settings, max_tokens: int | None = None,
             retries: int = 1, backoff: float = 2.0) -> str:
    """한 번 묻고 응답 원문을 돌려준다.

    전송 계층 재시도만 여기서 한다 (`429`·`5xx`·네트워크). 응답이 스키마를
    어긴 경우의 재요청은 **부르는 쪽**(panel)이 판단한다 — 프롬프트를 바꿔
    다시 물어야 하는데 그 판단은 여기 있으면 안 된다.
    """
    cfg = panel_config(settings)
    timeout = float(cfg.get("timeout_sec") or DEFAULT_TIMEOUT_SEC)
    model = str(cfg.get("model") or DEFAULT_MODEL)
    tokens = int(max_tokens or cfg.get("max_tokens") or DEFAULT_MAX_TOKENS)

    client = _client(timeout)
    attempt = 0
    while True:
        try:
            message = client.messages.create(
                model=model, max_tokens=tokens, temperature=0,
                system=system,
                messages=[{"role": "user", "content": user}])
        except LLMError:
            raise
        except Exception as exc:                            # noqa: BLE001
            kind = _classify(exc)
            if kind in RETRYABLE and attempt < retries:
                wait = backoff * (2 ** attempt)
                log.warning("LLM 호출 실패(%s) — %.0f초 뒤 재시도", kind, wait)
                time.sleep(wait)
                attempt += 1
                continue
            raise LLMError(kind, type(exc).__name__) from exc
        text = extract_text(message)
        if not text.strip():
            raise LLMError(INVALID_RESPONSE, "빈 응답")
        return text
