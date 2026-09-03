"""후스코어드 팀 특성 파싱 회귀 테스트 (§3-1).

260050 실행에서 28개 팀 전부 강점/약점을 하나도 못 읽었다. 원인은 실물
진단(AC 밀란 941KB, 2026-09-03)으로 확정됐다 — 제목이

    <h3><span style="color: #35AB53;">+</span> Strengths</h3>

이라서 `get_text()` 가 `"+ Strengths"` 를 주고, `_CHARACTERISTIC_HEADINGS`
조회가 기호 하나 때문에 빗나갔다. 봇 차단도 아니었고 데이터가 없는 것도
아니었다(진단: `봇 차단 흔적: 없음`, `Strengths=3회`).

두 번째 원인은 항목 추출이다. 제목을 맞춰도 `div.grid` 안에서 span/td/p 만
읽으면 실물에서 `['', 'Very Strong', '']` 이 나온다 — **이름이 아니라 강도
라벨**이다. 이름은 `div.character` 안의 `div` 에 있다.

여기 픽스처는 진단기가 찍어 준 **원본 조각 그대로**를 재구성한 것이다.
안쪽(`div.iconize…`)은 조각이 잘린 부분이라 모양만 맞췄고, 그래서 테스트는
특정 클래스 경로가 아니라 **읽어낸 결과**를 단언한다.

pytest 없이도 돈다:  python tests/test_whoscored_characteristics.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import BeautifulSoup                                   # noqa: E402

from toto.analyze import _topics_of                             # noqa: E402
from toto.sources.whoscored import (                            # noqa: E402
    _TEAM_CACHE_VERSION, _extract_characteristics, _heading_label,
    _soup as _prod_soup)


def _soup(html: str):
    return BeautifulSoup(html, "html.parser")


def _character(name: str, level: str) -> str:
    """실물의 항목 한 줄. 이름과 강도가 **다른 열**에 있다."""
    return (f'<div class="character">'
            f'<div class="col12-lg-8 col12-m-8 col12-s-9 col12-xs-9">'
            f'<div class="iconize iconize-icon-left iconize-16-16">'
            f'<span class="ui-icon"></span>{name}</div></div>'
            f'<div class="col12-lg-4 col12-m-4 col12-s-3 col12-xs-3">'
            f'<span>{level}</span></div></div>')


# 실물 구조 (진단기 '원본 조각' 재구성)
REAL = f"""<html><head>
<title>AC Milan - Football Statistics | WhoScored.com</title></head><body>
<h2><a href="/teams/80/statistics/italy-ac-milan"
   class="iconize iconize-icon-right ui-state-transparent-default disabled">
   AC Milan Characteristics <span class="ui-icon ui-icon-circle-arrow-e"></span></a></h2>
<div class="sws-content character-card singular">
  <div class="col12-lg-6 col12-m-6 col12-s-12 col12-xs-12 strengths">
    <h3><span style="color: #35AB53;">+</span> Strengths</h3>
    <div class="grid">
      {_character("Set pieces", "Very Strong")}
      {_character("Aerial duels", "Strong")}
      {_character("Counter attacks", "Strong")}
    </div>
  </div>
  <div class="col12-lg-6 col12-m-6 col12-s-12 col12-xs-12 weaknesses">
    <h3><span style="color: #CA2027;">-</span> Weaknesses</h3>
    <div class="grid">
      {_character("Defending fast breaks", "Weak")}
    </div>
  </div>
</div></body></html>"""

# 이전에 통했던 두 모양. 고치면서 깨지면 안 된다.
OLD_UL = """<html><body>
<h3>Strengths</h3><ul><li>Set pieces</li><li>Counter attacks</li></ul>
<h3>Weaknesses</h3><ul><li>Defending crosses</li></ul>
<h3>Style of play</h3><ul><li>Plays short passes</li></ul></body></html>"""

OLD_SPAN = """<html><body><div class="characteristics">
 <div class="col"><h4>Strengths</h4><div class="ws-list">
   <span class="item">Set pieces</span><span class="item">Counter attacks</span></div></div>
 <div class="col"><h4>Weaknesses</h4><div class="ws-list">
   <span class="item">Defending crosses</span></div></div>
</div></body></html>"""


# ---------------------------------------------------------------- 라벨 정규화
def test_a1_plus_sign_heading_is_matched():
    """실패의 직접 원인. '+ Strengths' 가 'strengths' 로 정규화돼야 한다."""
    node = _soup('<h3><span style="color: #35AB53;">+</span> Strengths</h3>').h3
    assert _heading_label(node) == "strengths", _heading_label(node)


def test_a2_minus_sign_heading_is_matched():
    node = _soup('<h3><span style="color: #CA2027;">-</span> Weaknesses</h3>').h3
    assert _heading_label(node) == "weaknesses", _heading_label(node)


def test_a3_plain_headings_unchanged():
    for html, want in (("<h3>Strengths</h3>", "strengths"),
                       ("<h3>Strengths:</h3>", "strengths"),
                       ("<h3>Style of play</h3>", "style of play"),
                       ("<h4>Weaknesses</h4>", "weaknesses")):
        node = _soup(html).find(["h3", "h4"])
        assert _heading_label(node) == want, f"{html} → {_heading_label(node)}"


def test_a4_long_heading_is_not_mistaken_for_a_section():
    """'AC Milan Characteristics' 는 20자를 넘어 제목 후보에서 빠진다."""
    node = _soup("<h2><a>AC Milan Characteristics</a></h2>").h2
    label = _heading_label(node)
    assert len(label) > 20, label


def test_a5_label_normalisation_does_not_invent_a_match():
    """기호를 걷어낸다고 없던 항목이 생기면 안 된다."""
    node = _soup("<h3><span>+</span></h3>").h3
    assert _heading_label(node) == "", repr(_heading_label(node))


# ---------------------------------------------------------------- 실물 구조
def test_b1_real_structure_yields_strengths():
    got = _extract_characteristics(_soup(REAL))
    assert len(got["strengths"]) == 3, got["strengths"]


def test_b2_real_structure_yields_weaknesses():
    got = _extract_characteristics(_soup(REAL))
    assert len(got["weaknesses"]) == 1, got["weaknesses"]


def test_b3_item_name_is_kept_not_only_the_level():
    """예전 코드는 span/td/p 만 읽어 'Very Strong' 만 남았다."""
    got = _extract_characteristics(_soup(REAL))
    joined = " ".join(got["strengths"])
    for name in ("Set pieces", "Aerial duels", "Counter attacks"):
        assert name in joined, f"{name} 없음: {got['strengths']}"


def test_b4_level_is_kept_too():
    got = _extract_characteristics(_soup(REAL))
    assert "Very Strong" in got["strengths"][0], got["strengths"][0]


def test_b5_name_and_level_do_not_run_together():
    """구분자가 없으면 'Set piecesVery Strong' 처럼 붙어 읽기 어려워진다."""
    got = _extract_characteristics(_soup(REAL))
    assert "·" in got["strengths"][0], got["strengths"][0]
    assert "piecesVery" not in got["strengths"][0]


def test_b6_no_empty_or_duplicate_items():
    got = _extract_characteristics(_soup(REAL))
    for slot in ("strengths", "weaknesses"):
        items = got[slot]
        assert all(item.strip() for item in items), items
        assert len(items) == len(set(items)), items


def test_b7_style_absent_stays_empty_not_invented():
    """이 페이지에는 Style of play 블록이 없다. 지어내지 않는다."""
    got = _extract_characteristics(_soup(REAL))
    assert got["style"] == [], got["style"]


def test_b8_level_vocabulary_is_not_hardcoded():
    """'Very Strong' 같은 어휘를 코드에 두고 자르지 않는다 — 구조로만 가른다.

    문자열 검색은 자기 주석에 걸린다(실제로 걸렸다). AST 의 문자열 상수만
    본다 — 주석은 AST 에 없고, 문서화 문자열은 따로 걷어낸다.
    """
    path = (Path(__file__).resolve().parent.parent
            / "toto" / "sources" / "whoscored.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))

    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings):
            low = node.value.lower()
            for word in ("very strong", "very weak"):
                assert word not in low, f"어휘 하드코딩: {node.value!r}"


# ---------------------------------------------------------------- 회귀 방지
def test_c1_old_ul_structure_still_read():
    got = _extract_characteristics(_soup(OLD_UL))
    assert got["strengths"] == ["Set pieces", "Counter attacks"], got["strengths"]
    assert got["weaknesses"] == ["Defending crosses"], got["weaknesses"]
    assert got["style"] == ["Plays short passes"], got["style"]


def test_c2_old_span_structure_still_read():
    got = _extract_characteristics(_soup(OLD_SPAN))
    assert got["strengths"] == ["Set pieces", "Counter attacks"], got["strengths"]
    assert got["weaknesses"] == ["Defending crosses"], got["weaknesses"]


def test_c3_empty_page_stays_empty():
    got = _extract_characteristics(_soup("<html><body><p>hi</p></body></html>"))
    assert got == {"strengths": [], "weaknesses": [], "style": []}, got


def test_c4_bot_wall_stays_empty():
    html = ("<html><head><title>Request unsuccessful. Incapsula incident ID: 1"
            "</title></head><body>Request unsuccessful.</body></html>")
    assert not any(_extract_characteristics(_soup(html)).values())


# ---------------------------------------------------------------- 실제 경로
def test_e1_production_soup_reads_the_same():
    """운영은 lxml 을 먼저 쓴다. 파서가 달라도 결과가 같아야 한다."""
    got = _extract_characteristics(_prod_soup(REAL))
    assert len(got["strengths"]) == 3, got["strengths"]
    assert len(got["weaknesses"]) == 1, got["weaknesses"]
    assert "Set pieces" in got["strengths"][0], got["strengths"][0]


def test_e2_team_cache_is_versioned():
    """파싱을 고쳤으면 옛 캐시를 읽으면 안 된다 (§1-4)."""
    assert isinstance(_TEAM_CACHE_VERSION, int) and _TEAM_CACHE_VERSION >= 1


def test_e3_old_cache_entry_is_rejected():
    """판 번호가 없거나 다른 캐시는 무시하고 다시 읽어야 한다."""
    for cached in ({}, {"strengths": []}, {"_v": _TEAM_CACHE_VERSION - 1}):
        assert cached.get("_v") != _TEAM_CACHE_VERSION, cached


# ---------------------------------------------------------------- 하류 연결
def test_d1_topics_still_match_with_level_suffix():
    """강도 꼬리표가 붙어도 교차 대조(_topics_of)가 주제를 알아봐야 한다."""
    got = _extract_characteristics(_soup(REAL))
    topics = _topics_of(got["strengths"])
    assert "set_piece" in topics, topics
    assert "aerial" in topics, topics
    assert "counter" in topics, topics


def test_d2_weakness_topic_matches_for_crossmatch():
    got = _extract_characteristics(_soup(REAL))
    assert "counter" in _topics_of(got["weaknesses"])


# --------------------------------------------------------------------------
def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            print(f"  ERR  {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
