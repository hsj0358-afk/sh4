"""패널·사회자 응답 검증의 공통 조각 (리팩터링 Phase 3 M1).

`panel` 과 `moderator` 가 **글자까지 같은** 세 가지를 따로 들고 있었다 —
형식 오류 예외(`ValidationError`) · 문자열 목록 검사(`_strings`) · 재요청
문구(`RETRY_HINT`). 이 스위트가 지키는 것은 둘이다.

  A. **동작이 그대로다.** 통합 전 코드에서도 똑같이 통과해야 하는 절이다 —
     반환값·예외 문구·재요청 문구가 글자까지 같고, 두 역할의 재요청 방식이
     그대로 다르다 (분석가는 일반 문구, 사회자는 사유를 붙인 문구).
  B. **정의가 한 곳이다.** 공통 조각은 `toto/panelcheck.py` 에만 있고,
     `moderator` 는 여전히 `panel` 을 import 하지 않는다 (순환 금지, §1-10).

역할마다 다른 검증(스코어 칸 문구 · 분포 · 채택)은 여기서 다루지 않는다.

**실제 모델을 부르지 않는다.** 가짜 클라이언트는 기존 스위트의 것을 쓴다.

pytest 없이도 돈다:  python tests/test_response_validation.py
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import moderator, panel                               # noqa: E402

from test_moderator import opinion, payload_of                  # noqa: E402
from test_panel import FakeClient, S, make_match                # noqa: E402

_PASSED = _FAILED = 0

# 재요청 문구 원문. 모델에게 가는 글이라 한 글자도 바뀌면 안 된다.
HINT = ("\n\n앞선 응답이 형식에 맞지 않았습니다. 설명 없이 "
        "JSON 객체 하나만 출력하십시오.")

MODULES = (panel, moderator)


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


def _raises(fn, exc_type) -> str:
    try:
        fn()
    except exc_type as exc:
        return str(exc)
    raise AssertionError(f"{exc_type.__name__} 가 나지 않았다")


# --------------------------------------------------------------------------
# A. 동작이 그대로다
# --------------------------------------------------------------------------
_ACCEPT = [
    ([], ()),
    ((), ()),
    (["a"], ("a",)),
    (("a", "b"), ("a", "b")),
    (["  앞뒤  ", "\t탭\n"], ("앞뒤", "탭")),
    (["", "   ", "남김"], ("남김",)),                # 빈 항목은 버린다
    (["중복", "중복"], ("중복", "중복")),          # 중복을 합치지 않는다
    (["E002", "E001"], ("E002", "E001")),        # 순서를 바꾸지 않는다
]


def test_a1_strings_accepts_lists_and_tuples():
    for mod in MODULES:
        for value, want in _ACCEPT:
            got = mod._strings(value, "f")
            assert got == want, (mod.__name__, value, got)
            assert type(got) is tuple, (mod.__name__, type(got))


def test_a2_strings_rejects_non_list_with_exact_message():
    """문자열 하나를 글자 목록으로 풀지 않는다 — 목록이 아니면 거부한다."""
    for mod in MODULES:
        for value in ("abc", "", None, 1, 1.5, True, {"a": 1}, {"a"}):
            msg = _raises(lambda: mod._strings(value, "rationale"),
                          mod.ValidationError)
            assert msg == "rationale: 문자열 목록이어야 합니다", (value, msg)


def test_a3_strings_rejects_non_str_items_with_exact_message():
    """숫자를 문자열로 바꿔 주지 않는다 — 느슨하게 고치지 않는다 (§1-12)."""
    for mod in MODULES:
        for value in ([1], ["a", None], [["a"]], ["a", 2.5], [True]):
            msg = _raises(lambda: mod._strings(value, "evidence_ids"),
                          mod.ValidationError)
            assert msg == "evidence_ids: 문자열이 아닌 항목이 있습니다", \
                (value, msg)


def test_a4_strings_does_not_touch_the_input():
    for mod in MODULES:
        value = ["  a ", "", "b"]
        mod._strings(value, "f")
        assert value == ["  a ", "", "b"]


def test_a5_retry_hint_text_is_unchanged():
    assert panel.RETRY_HINT == HINT
    assert moderator.RETRY_HINT == HINT


def test_a6_moderator_retry_hint_carries_the_reason():
    assert moderator.retry_hint("사유") == HINT + "\n오류: 사유"
    assert moderator.retry_hint("  사유  ") == HINT + "\n오류: 사유"
    assert moderator.retry_hint("") == HINT
    assert moderator.retry_hint("   ") == HINT
    assert moderator.retry_hint(None) == HINT


def test_a7_analyst_retry_adds_the_plain_hint_only():
    """분석가 재요청은 **일반 문구만** 붙인다 — 사회자의 사유 문구와 합치지
    않는다. 두 역할의 재요청 방식이 달라지면 안 되는 것도, 같아지면 안 되는
    것도 아니다 — 지금 그대로여야 한다."""
    client = FakeClient(["형식이 틀린 응답", "또 틀림"])
    payload = panel.build_panel_payload(make_match())
    msg = _raises(lambda: panel.run_panel_role(
        panel.DATA_ANALYST, payload, "{}", settings=S, client=client),
        panel.ValidationError)
    assert msg.startswith("JSON 파싱 실패"), msg
    assert len(client.calls) == 2
    first, second = client.calls[0][1], client.calls[1][1]
    assert second == first + HINT, "분석가 재요청 문구가 달라졌다"


def test_a8_moderator_retry_adds_the_reason():
    client = FakeClient(moderator_reply="틀린 응답")
    msg = _raises(lambda: moderator.run_moderator(
        payload_of(), [opinion(moderator.DATA_ROLE)], settings=S,
        client=client), moderator.ValidationError)
    assert msg.startswith("JSON 파싱 실패"), msg
    assert len(client.moderator_calls) == 2
    first = client.moderator_calls[0][1]
    second = client.moderator_calls[1][1]
    assert second.startswith(first + HINT + "\n오류: JSON 파싱 실패"), second


def test_a9_parse_opinion_uses_the_list_check():
    body = {"predicted_home": 1, "predicted_away": 0, "summary": "요약",
            "rationale": "문장 하나", "evidence_ids": []}
    msg = _raises(lambda: panel.parse_opinion(
        json.dumps(body, ensure_ascii=False), panel.DATA_ANALYST, ()),
        panel.ValidationError)
    assert msg == "rationale: 문자열 목록이어야 합니다", msg
    body["rationale"] = [" 앞뒤 ", ""]
    op = panel.parse_opinion(json.dumps(body, ensure_ascii=False),
                             panel.DATA_ANALYST, ())
    assert op.rationale == ("앞뒤",)


def test_a10_parse_result_uses_the_list_check():
    body = {"common_points": ["공통"], "differences": [],
            "counterpoints": [1], "uncertainty": [], "evidence_ids": []}
    msg = _raises(lambda: moderator.parse_result(
        json.dumps(body, ensure_ascii=False), panels_seen=(),
        shared=(), data_only=(), matchup_only=(), allowed_ids=()),
        moderator.ValidationError)
    assert msg == "counterpoints: 문자열이 아닌 항목이 있습니다", msg


def test_a11_each_module_catches_its_own_errors():
    """부르는 쪽은 저마다 **자기 모듈 이름**으로 잡는다 (panelimport ·
    panelwork · panelauto · panel.run_match). 그 이름이 계속 잡아야 한다."""
    for mod in MODULES:
        try:
            mod._strings("x", "f")
        except mod.ValidationError:
            pass
        else:
            raise AssertionError(mod.__name__)
    assert issubclass(panel.ValidationError, Exception)
    assert issubclass(moderator.ValidationError, Exception)


# --------------------------------------------------------------------------
# B. 정의가 한 곳이다
# --------------------------------------------------------------------------
def _module_source(mod) -> ast.Module:
    return ast.parse(inspect.getsource(mod))


def test_b1_shared_pieces_are_one_object():
    from toto import panelcheck
    assert panel.ValidationError is panelcheck.ValidationError
    assert moderator.ValidationError is panelcheck.ValidationError
    assert panel._strings is panelcheck.strings
    assert moderator._strings is panelcheck.strings
    assert panel.RETRY_HINT is panelcheck.RETRY_HINT
    assert moderator.RETRY_HINT is panelcheck.RETRY_HINT


def test_b2_no_second_definition_in_panel_or_moderator():
    for mod in MODULES:
        tree = _module_source(mod)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                assert node.name != "ValidationError", mod.__name__
            if isinstance(node, ast.FunctionDef):
                assert node.name != "_strings", mod.__name__
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets
                         if isinstance(t, ast.Name)]
                assert "RETRY_HINT" not in names, mod.__name__


def test_b3_shared_module_imports_nothing_from_toto():
    """순환이 생길 자리를 만들지 않는다 — 공통 조각은 아무것도 부르지 않는다."""
    from toto import panelcheck
    tree = _module_source(panelcheck)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module == "__future__" and not node.level, \
                ast.dump(node)
        assert not isinstance(node, ast.Import), ast.dump(node)


def test_b4_moderator_still_does_not_import_panel():
    """`panel` 이 `moderator` 를 부르므로 거꾸로 부르면 순환이다 (§1-10)."""
    tree = _module_source(moderator)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names]
            assert node.module != "panel" and "panel" not in names, \
                ast.dump(node)
            assert not (node.module or "").endswith(".panel"), ast.dump(node)
        if isinstance(node, ast.Import):
            for a in node.names:
                assert not a.name.endswith("panel"), a.name


def test_b5_role_specific_checks_stay_in_their_module():
    """공통 조각만 옮겼다. 역할마다 다른 것은 제자리에 있다."""
    from toto import panelcheck
    assert callable(moderator.retry_hint)          # 사회자만 사유를 붙인다
    assert not hasattr(panel, "retry_hint")
    assert not hasattr(panelcheck, "retry_hint")
    for name in ("_score", "_goals", "_text"):
        assert not hasattr(panelcheck, name), name


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
