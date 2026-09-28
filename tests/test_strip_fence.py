"""코드펜스 벗기기 — 한 구현, 여러 입구 (리팩터링 Phase 3 M9).

구현은 `llm.strip_fence` **하나**다. 부르는 길은 둘이다.

    llm.strip_fence            panel.parse_opinion · moderator.parse_result
    panelpaste._strip_fence    panelpaste.convert · panelwork.parse_stage ·
      (위 함수에 위임)          panelwork.parse_moderator_result

`panelpaste._strip_fence` 는 계약이 같은 위임 함수다. `panelwork` 는 API
클라이언트 모듈(`llm`)을 import 하지 않는다는 경계가 테스트로 걸려 있어
(`test_panel_work.test_a1`·`test_panel_workflow.test_d1`), 붙여넣기·자동
경로는 이 위임 함수를 거쳐 같은 규칙에 닿는다. M9 은 합칠 두 번째 구현이
없어 코드를 바꾸지 않았다.

기존 스위트는 ```` ```json ```` 울타리 하나만 본다. 이 스위트는 그 밖의
경계를 **측정한 값 그대로** 고정한다 — 기대값은 M9 조사 때 두 입구에서 잰
출력이다. 규칙의 요지는 §1-12 의 "느슨하게 고쳐 주지 않는다" 다: 울타리
한 겹만 떼고, 설명문·다른 언어 표시·안쪽 울타리는 건드리지 않는다.

pytest 없이도 돈다:  python tests/test_strip_fence.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import llm, panel, panelpaste                          # noqa: E402

from test_panel import GOOD                                      # noqa: E402

_PASSED = _FAILED = 0

ENTRIES = (llm.strip_fence, panelpaste._strip_fence)

# (입력, 측정한 출력)
CASES = [
    ("hello", "hello"),
    ('{"a": 1}', '{"a": 1}'),
    ('```json\n{"a": 1}\n```', '{"a": 1}'),
    ('```\n{"a": 1}\n```', '{"a": 1}'),                  # 언어 표시 없음
    ('```JSON\n{"a": 1}\n```', '{"a": 1}'),              # 대소문자 무시
    ('  \n ```json\n{"a": 1}\n```  \n', '{"a": 1}'),     # 앞뒤 공백
    ("", ""),
    (None, ""),
    ("   \n  ", ""),
    ('```json\n{"a": 1}', '{"a": 1}'),                   # 여는 울타리만
    ('{"a": 1}\n```', '{"a": 1}'),                       # 닫는 울타리만
    ('```json {"a": 1} ```', '{"a": 1}'),                # 한 줄
    ('```json\n[\n  {"요약": "홈 우세"},\n  {"요약": "무"}\n]\n```',
     '[\n  {"요약": "홈 우세"},\n  {"요약": "무"}\n]'),      # 여러 줄 · 한국어
    # --- 고치지 않는 것 ---
    ('```python\n{"a": 1}\n```', 'python\n{"a": 1}'),    # 다른 언어 표시
    ('{"t": "```json x ```"}', '{"t": "```json x ```"}'),  # 안쪽 울타리
    ('분석했습니다.\n```json\n{"a": 1}\n```',
     '분석했습니다.\n```json\n{"a": 1}'),                  # 앞에 설명문
    ('```json\n```json\n{"a": 1}\n```\n```',
     '```json\n{"a": 1}\n```'),                           # 한 겹만
    ('~~~json\n{"a": 1}\n~~~', '~~~json\n{"a": 1}\n~~~'),  # ~~~ 는 모른다
]


def check(name, fn):
    global _PASSED, _FAILED
    try:
        fn()
    except Exception as exc:                                 # noqa: BLE001
        _FAILED += 1
        print(f"  ✗ {name}: {type(exc).__name__}: {exc}")
    else:
        _PASSED += 1
        print(f"  ✓ {name}")


# --------------------------------------------------------------------------
# A. 함수 — 두 입구가 같은 글자를 돌려준다
# --------------------------------------------------------------------------
def test_a1_measured_outputs():
    for fn in ENTRIES:
        for text, want in CASES:
            got = fn(text)
            assert got == want, (fn.__module__, text, got)
            assert type(got) is str


def test_a2_two_entries_agree():
    for text, _want in CASES:
        assert llm.strip_fence(text) == panelpaste._strip_fence(text), text


def test_a3_non_text_is_not_coerced():
    """문자열이 아니면 고쳐 주지 않고 그대로 실패한다 (지금의 동작)."""
    for fn in ENTRIES:
        try:
            fn(123)
        except AttributeError:
            continue
        raise AssertionError(fn.__module__)


# --------------------------------------------------------------------------
# B. 부르는 쪽 — 같은 규칙으로 읽거나 거부한다
# --------------------------------------------------------------------------
def _parsed(text):
    return panel.parse_opinion(text, panel.DATA_ANALYST, ["E001"])


def test_b1_analyst_parser_reads_every_plain_fence_form():
    for wrap in ("```json\n{}\n```", "```\n{}\n```", "```JSON\n{}\n```",
                 "  ```json {}```  ", "{}"):
        op = _parsed(wrap.replace("{}", GOOD))
        assert op.predicted_home == 2, wrap


def test_b2_analyst_parser_refuses_what_it_does_not_repair():
    for bad in ("```python\n" + GOOD + "\n```",
                "분석했습니다.\n```json\n" + GOOD + "\n```",
                "~~~json\n" + GOOD + "\n~~~"):
        try:
            _parsed(bad)
        except panel.ValidationError as exc:
            assert str(exc).startswith("JSON 파싱 실패"), exc
            continue
        raise AssertionError(f"고쳐서 통과시켰다: {bad[:20]!r}")


def test_b3_paste_path_reads_the_same_forms():
    """붙여넣기 경로는 위임 함수로 같은 규칙에 닿는다."""
    body = json.dumps([{"match_no": 1}], ensure_ascii=False)
    for wrap in ("```json\n{}\n```", "```\n{}\n```", "\n\n{}\n"):
        text = wrap.replace("{}", body)
        assert json.loads(panelpaste._strip_fence(text.strip())) == \
            [{"match_no": 1}], wrap


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
