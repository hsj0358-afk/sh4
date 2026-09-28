"""패널·사회자 응답 검증의 공통 조각 (리팩터링 Phase 3 M1).

`panel`(두 분석가)과 `moderator`(사회자)가 **글자까지 같은** 세 가지를 따로
들고 있었다 — 형식 오류 예외 · 문자열 목록 검사 · 재요청 문구. 한 곳만
고쳐지면 두 역할의 검증이 조용히 갈라진다 (§1-8).

**`moderator` 는 `panel` 을 import 할 수 없다** — `panel` 이 `moderator` 를
부르므로 순환이 된다 (§1-10). 그래서 둘 다 부르는 제3의 자리에 두고, 이
모듈은 아무것도 import 하지 않는다.

여기 있는 것은 **규칙이 같은 것뿐이다.** 역할마다 다른 검증 — 분포 · 채택 ·
사유를 붙이는 사회자의 재요청(`moderator.retry_hint`) — 은 각 모듈에 그대로
있다. 역할의 실행·프롬프트·입출력은 합치지 않는다.

스코어 칸(`panel._score` · `moderator._goals`)은 **판정 규칙만** 여기 있고
오류 문구는 각 모듈이 정한다 (Phase 3 M2). 두 문구가 서로 다르고 둘 다 이미
밖으로 나가기 때문이다 — `panelimport` 오류 메시지와 사회자 재요청.
"""
from __future__ import annotations


class ValidationError(Exception):
    """응답이 형식에 맞지 않는다. **느슨하게 고쳐 주지 않는다** (§1-12).

    `panel.ValidationError` 와 `moderator.ValidationError` 는 이 한 클래스다.
    부르는 쪽은 저마다 자기 모듈의 이름으로 잡는다.
    """


# 형식 오류 뒤 재요청에 붙이는 문구. 모델에게 가는 글이다.
RETRY_HINT = ("\n\n앞선 응답이 형식에 맞지 않았습니다. 설명 없이 "
              "JSON 객체 하나만 출력하십시오.")


def strings(value, name: str) -> tuple[str, ...]:
    """문자열 목록 → 앞뒤 공백을 걷은 튜플. 빈 항목은 버린다.

    목록(또는 튜플)이 아니면 거부한다 — 문자열 하나를 글자 목록으로 풀지
    않는다. 문자열이 아닌 항목이 하나라도 있으면 거부한다 — 숫자를 문자열로
    바꿔 주지 않는다. 순서와 중복은 그대로 둔다.
    """
    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"{name}: 문자열 목록이어야 합니다")
    out = []
    for item in value:
        if not isinstance(item, str):
            raise ValidationError(f"{name}: 문자열이 아닌 항목이 있습니다")
        text = item.strip()
        if text:
            out.append(text)
    return tuple(out)


def nonnegative_int(value, name: str, *, not_int: str,
                    negative: str) -> int | None:
    """`None` 또는 0 이상 정수만. 받은 값을 **그대로** 돌려준다.

    `"2"` 를 2 로 읽거나 `1.5`·`2.0` 을 정수로 바꾸지 않는다. `True` 는
    `int` 의 하위형이라 그냥 두면 1 로 통과하므로 따로 막는다 (§1-12).

    오류 문구(`not_int` · `negative`)는 **부르는 쪽이 정한다** — 이 함수는
    `"{name}: {문구}"` 로 이어 붙일 뿐이다. `None` 이 무슨 뜻인지(스코어를
    내지 않음 · 칸이 빠짐)도 부르는 쪽이 정한다.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{name}: {not_int}")
    if value < 0:
        raise ValidationError(f"{name}: {negative}")
    return value
