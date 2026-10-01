"""리포트 내비게이션 회귀 (Phase 6-F-7 · CLAUDE.md §1-43).

지키려는 것 넷이다.

  1. **앵커는 한 곳에서만 만들어진다** — `render.match_anchor()` 하나
  2. **링크가 끊기지 않는다** — 모든 `#…` 대상이 문서에 실제로 있고 중복이
     없으며, 4-G 때 공유한 옛 링크(`#m4`)도 계속 돈다
  3. **없는 방향은 만들지 않는다** — 1번에 이전 없음 · 14번에 다음 없음
  4. **자료가 바뀌지 않는다** — 표·항목·좌표·스코어가 변경 전과 같다

§18 이 적은 대로 **HTML 전체 바이트·해시가 달라지는 것은 정상이다** (UI
변경이다). 그래서 바이트가 아니라 **내용**을 대조한다.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import render                                        # noqa: E402
from toto.settings import Settings                             # noqa: E402

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
_HTML = None
_PANEL_HTML = None


def _report(with_panel: bool):
    """데모 회차. **기존 테스트와 같은 방식으로 만든다** (§1-8)."""
    from toto import fixtures
    from toto.analyze import run_all
    from toto.models import Report
    matches = fixtures.build_demo_matches()
    settings = Settings()
    run_all(matches, settings, season_matches=[])
    if with_panel:
        from test_panel_render import full_run
        for match in matches:
            match.panel = full_run()
    return Report(round_id="DEMO", generated_at="fixed", matches=matches), settings


def demo_html() -> str:
    """데모 회차의 리포트. 한 번만 만든다."""
    global _HTML
    if _HTML is None:
        report, settings = _report(with_panel=False)
        _HTML = render.render_report(report, settings)
    return _HTML


def panel_html() -> str:
    """패널이 붙은 리포트 — 요약 카드에 스코어가 있는 경로."""
    global _PANEL_HTML
    if _PANEL_HTML is None:
        report, settings = _report(with_panel=True)
        _PANEL_HTML = render.render_report(report, settings)
    return _PANEL_HTML


def ids_of(html: str) -> list:
    return re.findall(r'\sid="([^"]+)"', html)


def fragment_targets(html: str) -> list:
    return re.findall(r'href="#([^"]+)"', html)


def card_of(html: str, no: int) -> str:
    """경기 카드 하나의 HTML."""
    mark = f'<article class="match" id="{render.match_anchor(no)}">'
    assert mark in html, f"{no}번 카드가 없다"
    return html.split(mark)[1].split("</article>")[0]


def source_of(obj) -> str:
    return Path(obj.__file__).read_text(encoding="utf-8")


def fn_node(module, name):
    for node in ast.walk(ast.parse(source_of(module))):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} 을 찾지 못했다")


# ==========================================================================
# A. 앵커 형식 — 숫자 기반 · 한 곳에서만 만든다
# ==========================================================================
def test_a1_anchor_is_zero_padded_and_numeric():
    """`match-01` … `match-14` (§10·§17)."""
    assert render.match_anchor(1) == "match-01"
    assert render.match_anchor(4) == "match-04"
    assert render.match_anchor(14) == "match-14"
    assert render.OVERVIEW_ANCHOR == "match-overview"


def test_a2_anchor_never_contains_a_team_name():
    """경기명·한글 제목을 id 로 쓰지 않는다 (§10).

    fragment 에 한글·공백·`&` 가 들어가면 인코딩이 브라우저·메신저마다
    달라져 링크가 깨지고, 팀 이름은 회차마다 바뀌어 같은 자리를 가리키지도
    못한다.
    """
    html = demo_html()
    for value in ids_of(html) + fragment_targets(html):
        assert value.isascii(), f"비ASCII id/fragment: {value}"
        assert not re.search(r"[\s&#?/]", value), f"위험한 문자: {value}"


def test_a3_only_render_builds_the_anchor():
    """앵커 문자열이 **한 곳에서만** 만들어진다 (§16).

    14경기 markup 을 문자열로 복사해 끼워 넣으면 목록과 상세가 조용히
    갈라진다. `match-` 라는 접두사가 `match_anchor` 밖에 없어야 한다.
    """
    src = source_of(render)
    hits = [line for line in src.splitlines()
            if '"match-' in line or "'match-" in line]
    # `match_anchor` 의 두 return 과 `OVERVIEW_ANCHOR` 정의, 그리고 그것을
    # 그대로 쓰는 CSS 선택자(#match-overview)만 허용한다.
    for line in hits:
        ok = ("return f\"match-" in line
              or line.strip().startswith("OVERVIEW_ANCHOR")
              or line.strip().startswith("#match-overview{"))
        assert ok, f"앵커를 다른 데서 만든다: {line.strip()[:80]}"


def test_a4_cards_use_the_helper_not_a_literal():
    """카드·요약 카드가 헬퍼를 부른다."""
    for fn in ("_match_card", "_summary_grid", "_match_nav"):
        code = ast.unparse(fn_node(render, fn))
        assert "match_anchor" in code, f"{fn} 이 헬퍼를 쓰지 않는다"


# ==========================================================================
# B. 링크가 끊기지 않는다
# ==========================================================================
def test_b1_every_fragment_target_exists():
    """모든 `href="#…"` 의 대상이 문서에 있다 (§18)."""
    for label, html in (("데모", demo_html()), ("패널", panel_html())):
        have = set(ids_of(html))
        dead = sorted({t for t in fragment_targets(html) if t not in have})
        assert not dead, f"{label}: 끊긴 링크 {dead}"


def test_b2_no_duplicate_ids():
    """같은 id 가 두 번 나오지 않는다 (§18).

    중복이면 브라우저가 먼저 나온 것으로 가므로 뒤쪽 경기가 영영 안 열린다.
    """
    for label, html in (("데모", demo_html()), ("패널", panel_html())):
        ids = ids_of(html)
        dup = sorted({i for i in ids if ids.count(i) > 1})
        assert not dup, f"{label}: 중복 id {dup}"


def test_b3_overview_section_exists():
    """목록이 자기 앵커를 가진 구역이다 (§6)."""
    html = demo_html()
    assert f'<section id="{render.OVERVIEW_ANCHOR}">' in html
    assert "14경기 한눈에 보기" in html


def test_b4_every_summary_card_links_to_its_detail():
    """목록 → 상세 (§7·§8)."""
    html = demo_html()
    assert html.count('class="sumcard"') == 14
    for no in range(1, 15):
        target = render.match_anchor(no)
        assert f'<a class="sumcard" href="#{target}">' in html, no
        assert f'<article class="match" id="{target}">' in html, no


def test_b5_every_detail_links_back_to_the_overview():
    """상세 → 목록 (§11)."""
    html = demo_html()
    for no in range(1, 15):
        card = card_of(html, no)
        assert f'href="#{render.OVERVIEW_ANCHOR}"' in card, no


def test_b6_legacy_anchor_still_resolves():
    """4-G 때 공유한 `#m4` 가 계속 돈다.

    리포트는 같은 경로에 다시 쓰이므로(`reports/toto_<회차>.html`) 앵커만
    바꾸면 이미 공유·북마크한 링크가 **조용히** 맨 위로 떨어진다. 값이
    없는 것과 틀린 곳으로 가는 것은 다르다 (§1-5).
    """
    html = demo_html()
    for no in range(1, 15):
        alias = render.legacy_match_anchor(no)
        assert alias == f"m{no}"
        assert f'<span class="aka" id="{alias}"></span>' in html, no
        # 그 span 은 **그 경기 카드 안**에 있어야 한다 — 다른 카드로 가면
        # 옛 링크가 조용히 틀린 경기를 연다.
        assert f'id="{alias}"' in card_of(html, no), no


# ==========================================================================
# C. 이전·다음 — 없는 방향은 만들지 않는다
# ==========================================================================
def test_c1_first_match_has_no_previous():
    """1번에 '이전' 이 없다 (§12)."""
    card = card_of(demo_html(), 1)
    assert "mnav-prev" not in card, "1번에 이전 링크가 있다"
    assert "mnav-next" in card, "1번에 다음 링크가 없다"


def test_c2_last_match_has_no_next():
    """14번에 '다음' 이 없다 (§12)."""
    card = card_of(demo_html(), 14)
    assert "mnav-next" not in card, "14번에 다음 링크가 있다"
    assert "mnav-prev" in card, "14번에 이전 링크가 없다"


def test_c3_middle_matches_have_both():
    """2~13번은 둘 다 있고 **정확히 이웃**을 가리킨다 (§12)."""
    html = demo_html()
    for no in range(2, 14):
        card = card_of(html, no)
        assert f'href="#{render.match_anchor(no - 1)}"' in card, no
        assert f'href="#{render.match_anchor(no + 1)}"' in card, no
        assert f'class="mnav-prev" href="#{render.match_anchor(no - 1)}"' in card
        assert f'class="mnav-next" href="#{render.match_anchor(no + 1)}"' in card


def test_c4_no_link_points_at_itself():
    """자기 자신으로 가는 이동 링크를 만들지 않는다."""
    html = demo_html()
    for no in range(1, 15):
        card = card_of(html, no)
        me = render.match_anchor(no)
        for cls in ("mnav-prev", "mnav-next"):
            assert f'class="{cls}" href="#{me}"' not in card, (no, cls)


def test_c5_nav_markup_is_built_in_one_place():
    """위아래 두 줄을 **같은 함수**가 만든다 (§16)."""
    code = ast.unparse(fn_node(render, "_match_card"))
    assert code.count("_match_nav(") == 1, "nav 를 두 번 조립한다"
    assert code.count("nav") >= 2, "만든 줄을 한 번만 쓴다"
    html = demo_html()
    # 카드마다 두 줄이고 그 둘의 내용이 같다.
    for no in (1, 7, 14):
        bars = re.findall(r'<nav class="mnav".*?</nav>', card_of(html, no), re.S)
        assert len(bars) == 2, (no, len(bars))
        assert bars[0] == bars[1], f"{no}번 위아래 줄이 다르다"


def test_c6_navigation_needs_no_javascript():
    """순수 anchor 다 (§15).

    리포트는 외부 참조 0 의 자체 완결 HTML 이어야 한다 (§1-8). 이동에
    스크립트가 끼면 `file://`·폰·오프라인에서 깨질 여지가 생긴다.
    """
    code = ast.unparse(fn_node(render, "_match_nav"))
    for bad in ("script", "onclick", "addEventListener", "javascript:"):
        assert bad not in code, f"{bad} 를 쓴다"
    html = demo_html()
    block = html[html.index("<nav class=\"mnav\""):]
    block = block[:block.index("</nav>")]
    assert "<script" not in block and "onclick" not in block


def test_c7_no_new_css_class_family():
    """CSS 는 내비게이션에 필요한 것만 더했다 (§14).

    layout·spacing 밖으로 나가지 않는다 — 이번 범위는 navigation 뿐이다.
    """
    classes = set(re.findall(r"\.([a-zA-Z][\w-]*)\s*\{", render.CSS))
    added = {c for c in classes if c.startswith("mnav")} | {"aka"}
    assert "mnav" in added and "aka" in added
    # 지표·값·패널 쪽 클래스를 새로 만들지 않았다.
    for bad in ("score", "verdict", "pick", "recommend"):
        assert not any(c.startswith(bad) for c in added), bad


def test_c8_report_stays_self_contained():
    """외부 참조 0 (§1-8)."""
    html = demo_html()
    assert "<script src" not in html
    assert "@import" not in html
    assert not re.search(r'(src|href)="https?:', html)


# ==========================================================================
# D. 자료가 바뀌지 않는다 — §14 가 금지한 것들
# ==========================================================================
def _content(html: str) -> dict:
    return {
        "td": re.findall(r"<td[^>]*>(.*?)</td>", html, re.S),
        "th": re.findall(r"<th[^>]*>(.*?)</th>", html, re.S),
        "li": re.findall(r"<li[^>]*>(.*?)</li>", html, re.S),
        "svg": re.findall(r'\b(?:cx|cy|x1|y1|x2|y2|points|d)="([^"]+)"', html),
        "title": re.findall(r"<title[^>]*>(.*?)</title>", html, re.S),
        "h4": re.findall(r"<h4[^>]*>(.*?)</h4>", html, re.S),
        "score": re.findall(r'class="sumscore[^"]*">(.*?)</p>', html, re.S),
    }


def test_d1_navigation_does_not_touch_the_numbers():
    """nav 를 걷어낸 문서가 **내용에서** 전과 같다 (§14·§18).

    바이트는 달라진다(그게 이번 변경이다). 달라지면 **안 되는** 것은 표
    칸·항목·좌표·툴팁·예상 스코어다. nav 가 그중 어느 것도 만들지 않으므로,
    nav markup 을 지운 문서에는 그것들이 고스란히 남아야 한다.
    """
    html = panel_html()
    stripped = re.sub(r'<nav class="mnav".*?</nav>', "", html, flags=re.S)
    stripped = re.sub(r'<span class="aka" id="m\d+"></span>', "", stripped)
    a, b = _content(html), _content(stripped)
    for key in a:
        assert a[key] == b[key], f"{key} 가 nav 에 딸려 바뀐다"
    assert len(a["td"]) > 100 and len(a["svg"]) > 100, "대조 대상이 비었다"


def test_d2_nav_carries_no_numbers_but_the_match_number():
    """이동 줄에 **경기 번호 말고 다른 수가 없다** (§14).

    스코어·확률·지표를 여기 적기 시작하면 그 순간 이 줄이 요약이 되고,
    같은 수가 카드 안팎에서 두 번 읽힌다 (5-D 가 걷어낸 사본과 같다).
    """
    html = demo_html()
    for bar in re.findall(r'<nav class="mnav".*?</nav>', html, re.S):
        text = re.sub(r"<[^>]+>", " ", bar)
        nums = {int(n) for n in re.findall(r"\d+", text)}
        assert nums <= set(range(1, 15)), f"경기 번호 밖의 수: {nums}"
        for bad in ("%", "확률", "추천", "승", "무", "패"):
            assert bad not in text, f"이동 줄에 '{bad}' 가 있다"


def test_d3_card_order_and_count_are_unchanged():
    """경기 순서·개수가 그대로다."""
    html = demo_html()
    order = [int(m) for m in re.findall(
        r'<article class="match" id="match-(\d+)">', html)]
    assert order == list(range(1, 15)), order


def test_d4_footer_still_says_no_recommendation():
    """§1-3 의 문장은 그대로다 — 이동 줄이 그것을 흐리지 않는다."""
    assert "승/무/패를 추천하지 않습니다" in demo_html()


def main() -> int:
    print("Phase 6-F-7 — 리포트 내비게이션")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 1 if _FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
