"""리포트 HTML 의 escape — `render.esc` ↔ `charts.esc` (리팩터링 Phase 3 M7).

두 모듈이 **글자까지 같은** 한 줄을 따로 들고 있었다.

    def esc(text) -> str:
        return html.escape(str(text), quote=True)

리포트에 들어가는 팀명·수치·라벨·모델 문장이 전부 이것을 지난다 (§1-11 —
"모델 문장은 전부 escape 한다"). 이 스위트가 지키는 것은 셋이다.

  A. 입력 → 출력이 글자까지 그대로다. 기대값은 `html.escape` 로 계산하지
     않고 **손으로 적었다** — 같은 함수로 기대값을 만들면 무엇이 바뀌어도
     통과한다.
  B. 부르는 쪽에서도 그대로다 — 모델 문장(`_ptext`) · 폼 칩 툴팁
     (`charts.form_timeline`) · 경기 카드의 팀명(`render._match_card`).
  C. 정의가 한 곳이다 (`charts.esc`). `render.esc` 는 같은 함수다.

A·B 는 통합 전 코드에서도 똑같이 통과해야 한다.

pytest 없이도 돈다:  python tests/test_html_escape.py
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import charts, render                                  # noqa: E402
from toto.models import FormEntry                                # noqa: E402

_PASSED = _FAILED = 0

FUNCS = (render.esc, charts.esc)

# (입력, 기대 출력). 손으로 적었다.
CASES = [
    ("abc", "abc"),
    ("", ""),
    ("한글", "한글"),
    ("⚽ ↓ — ·", "⚽ ↓ — ·"),
    ("줄1\n줄2", "줄1\n줄2"),                        # 줄바꿈은 그대로 둔다
    ("\t 앞뒤 공백 ", "\t 앞뒤 공백 "),              # 공백을 걷지 않는다
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
    ("'", "&#x27;"),                                 # 작은따옴표도 바꾼다
    ("<tag>", "&lt;tag&gt;"),
    ("a & b", "a &amp; b"),
    ('"quoted"', "&quot;quoted&quot;"),
    ("'quoted'", "&#x27;quoted&#x27;"),
    ("<script>alert(1)</script>",
     "&lt;script&gt;alert(1)&lt;/script&gt;"),
    ('<a href="x?a=1&b=2">Tom & Jerry</a>',
     "&lt;a href=&quot;x?a=1&amp;b=2&quot;&gt;Tom &amp; Jerry&lt;/a&gt;"),
    # 이미 escape 된 문자열도 **다시** 바꾼다 — 한 번 더 넣으면 두 번 걸린다.
    ("&amp;", "&amp;amp;"),
    ("&lt;", "&amp;lt;"),
    ("&gt;", "&amp;gt;"),
    ("&quot;", "&amp;quot;"),
    ("&#x27;", "&amp;#x27;"),
    ("이미 &amp; 처리된 값", "이미 &amp;amp; 처리된 값"),
    ("**굵게**", "**굵게**"),                        # markdown 을 해석하지 않는다
    # 문자열이 아니면 `str()` 한 뒤 escape 한다 — 거부하지 않는다.
    (None, "None"),
    (123, "123"),
    (0, "0"),
    (-1.5, "-1.5"),
    (True, "True"),
    (False, "False"),
    ([1, "a"], "[1, &#x27;a&#x27;]"),
    ({"a": "<b>"}, "{&#x27;a&#x27;: &#x27;&lt;b&gt;&#x27;}"),
    (("x",), "(&#x27;x&#x27;,)"),
]


class _Str(str):
    """`str` 의 하위형."""


class _Bad:
    def __str__(self):
        raise ValueError("str 실패")


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
# A. 입력 → 출력
# --------------------------------------------------------------------------
def test_a1_every_case_matches_the_handwritten_output():
    for fn in FUNCS:
        for value, want in CASES:
            got = fn(value)
            assert got == want, (fn.__module__, value, got)


def test_a2_always_returns_a_plain_str():
    for fn in FUNCS:
        for value, _ in CASES:
            assert type(fn(value)) is str, (fn.__module__, value)
        got = fn(_Str("<x>"))
        assert got == "&lt;x&gt;" and type(got) is str


def test_a3_the_two_agree_on_every_case():
    for value, _ in CASES:
        assert render.esc(value) == charts.esc(value), value


def test_a4_not_idempotent():
    """두 번 부르면 두 번 escape 된다 — 이미 HTML 인 것을 넘기면 안 된다."""
    for fn in FUNCS:
        once = fn("a & <b>")
        assert fn(once) == "a &amp;amp; &amp;lt;b&amp;gt;", fn(once)


def test_a5_only_str_can_raise():
    """escape 자체는 예외를 내지 않는다. `str()` 이 실패하면 그대로 올라간다."""
    for fn in FUNCS:
        try:
            fn(_Bad())
        except ValueError as exc:
            assert str(exc) == "str 실패"
        else:
            raise AssertionError(fn.__module__)


def test_a6_one_positional_argument():
    for fn in FUNCS:
        params = list(inspect.signature(fn).parameters)
        assert params == ["text"], (fn.__module__, params)


# --------------------------------------------------------------------------
# B. 부르는 쪽에서
# --------------------------------------------------------------------------
def test_b1_model_sentences_are_escaped_then_line_broken():
    """§1-11 — escape 한 **뒤** 줄바꿈만 `<br>` 로 바꾼다."""
    got = render._ptext('<script>x</script>\n**b** & "q" \'s\'')
    assert got == ("&lt;script&gt;x&lt;/script&gt;<br>**b** &amp; "
                   "&quot;q&quot; &#x27;s&#x27;"), got


def test_b2_form_chip_tooltip_is_escaped():
    entry = FormEntry(date="2026-09-01", opponent='<b>A&B "C"</b>',
                      home=False, goals_for=1, goals_against=0, result="W")
    out = charts.form_timeline([entry], "팀")
    safe = "&lt;b&gt;A&amp;B &quot;C&quot;&lt;/b&gt;"
    assert f'title="2026-09-01 원정 vs {safe} ' in out, out
    assert f'<span class="op">원정 · {safe}</span>' in out, out
    assert '<b>A&B' not in out


def test_b3_team_names_in_the_card_are_escaped():
    from test_axes_render import _match
    from toto.settings import Settings

    m = _match()
    m.home.display = '<i>홈&"</i>'
    m.away.display = "원정'<"
    out = render._match_card(m, Settings(), None)
    assert "&lt;i&gt;홈&amp;&quot;&lt;/i&gt;" in out
    assert "원정&#x27;&lt;" in out
    assert '<i>홈&"' not in out and "원정'<" not in out


# --------------------------------------------------------------------------
# C. 정의가 한 곳이다
# --------------------------------------------------------------------------
def _defines_esc(mod) -> bool:
    tree = ast.parse(inspect.getsource(mod))
    return any(isinstance(n, ast.FunctionDef) and n.name == "esc"
               for n in tree.body)


def test_c1_one_definition():
    assert render.esc is charts.esc
    assert _defines_esc(charts)
    assert not _defines_esc(render), "render 가 esc 를 따로 들고 있다"


def test_c2_charts_does_not_import_render():
    """`render` 가 `charts` 를 부르므로 거꾸로 부르면 순환이다."""
    tree = ast.parse(inspect.getsource(charts))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module in ("__future__",) and not node.level, \
                ast.dump(node)
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name in ("html", "math"), a.name


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
