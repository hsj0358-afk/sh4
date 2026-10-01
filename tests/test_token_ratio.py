"""원본 자료의 자/토큰 비 `2.088` — 한 곳에서 정한다 (리팩터링 Phase 3-B M8).

`2.088` 은 6-F-8 에서 잰 **원본(접기 전) 한국어 JSON 자료**의 글자/토큰
비율이다. 두 곳이 같은 값을 따로 적고 있었다.

    panelpacket.CHARS_PER_TOKEN     packet 과 견줄 원본의 토큰 어림
    panelauto.EST_CHARS_PER_TOKEN   시작 전 점검의 "회차 원본 …토큰"

둘은 같은 실측, 같은 자료(원본), 같은 쓰임(시작 전에 크기만 어림 —
자르거나 요약하지 않는다)이고, **같은 점검 화면에 나란히** 찍힌다. 한쪽만
다시 재면 한 화면의 두 "원본" 줄이 서로 다른 비율로 계산된다.

`1.819`(compact packet 의 비율)는 **다른 글**에서 잰 다른 값이라 따로 둔다.

기대값은 제품 상수로 계산하지 않고 **숫자를 그대로 적었다** — 같은 상수로
기대값을 만들면 그 상수가 바뀌어도 통과한다.

pytest 없이도 돈다:  python tests/test_token_ratio.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import panelauto, panelpacket                          # noqa: E402

from test_panel_auto import FakeReport, patched, scratch         # noqa: E402

_PASSED = _FAILED = 0


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


class _Index:
    """`measure()` 가 읽는 칸만 가진 색인."""

    def __init__(self, source: str):
        self.round_id, self.matches, self._source = "T", 1, source

    def source_text(self) -> str:
        return self._source


# --------------------------------------------------------------------------
# A. 값과 계산이 그대로다
# --------------------------------------------------------------------------
def test_a1_values():
    assert panelpacket.CHARS_PER_TOKEN == 2.088
    assert panelauto.EST_CHARS_PER_TOKEN == 2.088
    assert panelpacket.PACKET_CHARS_PER_TOKEN == 1.819, "packet 비율은 다른 값"


def test_a2_estimate_tokens():
    assert panelpacket.estimate_tokens("가" * 2088) == 1000
    assert panelpacket.estimate_tokens("x" * 2089) == 1000          # 내림
    assert panelpacket.estimate_tokens("가" * 1819, 1.819) == 1000
    assert panelpacket.estimate_tokens("") == 0
    assert panelpacket.estimate_tokens(None) == 0
    # 비율을 비우면 원본 비율로 돌아간다.
    assert panelpacket.estimate_tokens("가" * 2088, 0) == 1000
    assert panelpacket.estimate_tokens("가" * 2088, None) == 1000


def test_a3_measure_uses_2088_for_source_and_1819_for_packet():
    stats = panelpacket.measure(_Index("가" * 20880), "나" * 18190)
    assert stats["source_chars"] == 20880
    assert stats["source_tokens"] == 10000
    assert stats["chars"] == 18190
    assert stats["tokens"] == 10000


def test_a4_preflight_note_prints_the_ratio():
    rep = FakeReport(3)
    with patched(cli="/bin/true"):
        pre = panelauto.preflight(rep, "TEST", scratch())
    assert pre.tokens == int(pre.chars / 2.088)
    want = (f"회차 원본 {pre.chars:,}자 ≈ {int(pre.chars / 2.088):,}토큰 "
            f"(실측 2.088자/토큰)")
    assert want in pre.notes, pre.notes


# --------------------------------------------------------------------------
# C. 한 곳에서 정한다
# --------------------------------------------------------------------------
def _float_literals(mod) -> list[float]:
    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, float)]


def test_c1_one_definition():
    assert panelauto.EST_CHARS_PER_TOKEN is panelpacket.CHARS_PER_TOKEN
    assert 2.088 not in _float_literals(panelauto), "panelauto 가 따로 적는다"
    assert _float_literals(panelpacket).count(2.088) == 1


def test_c2_packet_ratio_stays_its_own_value():
    assert panelpacket.PACKET_CHARS_PER_TOKEN is not panelpacket.CHARS_PER_TOKEN
    assert _float_literals(panelpacket).count(1.819) == 1


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
