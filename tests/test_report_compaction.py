"""리포트 문구 압축 회귀 테스트 (Phase 5-E2).

실물 260052 리포트에서 **같은 설명이 한 카드 안에 여러 번** 나왔다. 세는
방법을 바꾼 것도, 값을 줄인 것도 아니고, 되풀이를 걷었을 뿐이다.

| 자리 | 실물 반복 | 지금 |
|---|---|---|
| 직접 비교 축 설명 | 블록 1 + 그림 2 = 경기당 3번 | 블록 맨 위 **한 번** |
| 분포 "확률이 아닙니다" | 패널마다 1번 | 구조가 막는다 (문구 없음) |
| Moderator-only 안내 | 제목 + 설명 + 최초 스코어 주석 = 3겹 | 제목 하나 |
| 사회자 세부 다섯 절 | 전부 펼침 | 접이식 **하나** |

**지우는 것이 아니라 접는 것이다** (§1-15-3). 펼치면 전과 같은 항목이
같은 순서로 있고, 이 파일이 그것을 글자 단위로 대조한다.

pytest 없이도 돈다:  python tests/test_report_compaction.py
"""
from __future__ import annotations

import ast
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import charts, panelimport, panelpaste, render        # noqa: E402
from toto.settings import Settings                              # noqa: E402

import test_panel_paste as P                                    # noqa: E402
from test_axes_render import _match                             # noqa: E402
from test_panel_render import full_run                          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _text(html: str) -> str:
    """화면에 보이는 글자만 — 속성값을 검사에서 뺀다."""
    return re.sub(r"<[^>]+>", " ", html)


def _moderator_only_report():
    """실물 260052 모양 — 11경기 Moderator-only · 3경기 생략."""
    report = P._report()
    base = Path(tempfile.mkdtemp())
    path, res = panelpaste.apply(P.FIXTURE.read_text(encoding="utf-8"),
                                 report, P.S, base=base)
    assert path is not None, [str(i) for i in res.issues]
    panelimport.attach(res, report)
    return report


def _full_card() -> str:
    """축·패널이 다 들어 있는 카드."""
    m = _match()
    m.panel = full_run()
    return render._match_card(m, Settings(), None)


def _src(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# A. 직접 비교 — 설명은 블록 맨 위 한 번
# --------------------------------------------------------------------------
def test_a1_axis_rule_is_stated_once_per_block():
    """실물에서 같은 축 설명이 블록 1 + 그림 2 로 경기당 세 번 나왔다."""
    block = render._direct_compare_block(_match())
    assert block, "직접 비교 블록이 비었다 — 픽스처를 확인하라"
    assert block.count("눈금") <= 2, block.count("눈금")
    assert "<figcaption>" not in block, "그림에 설명이 다시 붙었다"


def test_a2_the_rule_itself_is_unchanged():
    """**규칙은 그대로다.** ↓ 줄은 축을 반대로 그린다는 말이 남아 있어야
    한다 — 그림만 보고는 알 수 없는 정보라 지우면 오해가 생긴다 (§1-23)."""
    t = _text(render._direct_compare_block(_match()))
    for word in ("↓", "축을", "반대로", "오른쪽"):
        assert word in t, (word, t[:200])


def test_a3_dropped_sentences_are_really_gone():
    block = render._direct_compare_block(_match())
    for gone in ("표본 수(n)는 아래 경기력 분석 표에",
                 "지표를 합쳐 종합 점수를 만들지 않고",
                 "각 줄은 <b>그 줄만의 눈금</b>입니다"):
        assert gone not in block, gone


def test_a4_sample_size_is_still_on_screen_where_it_belongs():
    """'표본 수는 아래 표에 있다' 는 문장을 뺐다 — 그 표가 실제로 있고
    거기에 표본 수가 적혀 있어야 문장을 뺄 수 있다."""
    card = _full_card()
    assert "경기력 분석" in card
    assert "n=" in card


# --------------------------------------------------------------------------
# B. 덤벨 — 범례는 남고 설명만 걷혔다
# --------------------------------------------------------------------------
ROWS = [{"label": "경기당 승점", "home": 1.80, "away": 1.20},
        {"label": "경기당 실점", "home": 1.00, "away": 1.60,
         "lower_better": True}]


def test_b1_dumbbell_has_no_caption():
    svg = charts.dumbbell(ROWS, "홈", "원정")
    assert "<figcaption>" not in svg, svg[-200:]


def test_b2_dumbbell_keeps_its_legend():
    """범례는 설명이 아니라 **그림을 읽는 데 필요한 정보**다."""
    svg = charts.dumbbell(ROWS, "홈팀", "원정팀")
    assert "채운 점" in svg and "속 빈 점" in svg
    assert "홈팀" in svg and "원정팀" in svg


def test_b3_geometry_is_untouched():
    """좌표는 한 칸도 바뀌지 않는다 — 5-D 의 축 반전이 그대로다.

    한 줄에 원정 점을 먼저, 홈 점을 나중에 그린다 (값이 같을 때 홈이 위로).
    """
    svg = charts.dumbbell(ROWS, "홈", "원정")
    xs = [float(x) for x in re.findall(r'<circle[^>]+cx="([\d.]+)"', svg)]
    assert len(xs) == 4, xs
    away0, home0, away1, home1 = xs
    assert home0 > away0, ("승점 1.80 > 1.20 이므로 홈이 오른쪽", xs)
    assert home1 > away1, ("실점 ↓ 1.00 < 1.60 인데 홈이 오른쪽이어야 한다", xs)


def test_b4_direction_never_comes_from_the_label():
    """방향을 라벨 문자열(`↓`)로 되읽지 않는다 (§1-23).

    `↓` 는 방향에서 **파생된 표시**다. 그것을 근거로 삼으면 출처가 두 곳이
    된다 — 비교식의 피연산자로 쓰이지 않았는지 본다.
    """
    tree = ast.parse(_src("toto/charts.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for part in [node.left] + list(node.comparators):
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    assert "↓" not in part.value, ast.dump(node)[:120]


# --------------------------------------------------------------------------
# C. 패널 — 안내 문구 셋이 사라지고 상태는 그대로
# --------------------------------------------------------------------------
GONE = ("1·2단계 분석가 원문은 이번 입력에 포함되지",
        "각 분석가가 <b>처음</b> 낸 스코어만",
        "예상 스코어는 <b>표시하지 않습니다</b>",
        "같은 자료를 서로 다른 축에서 읽었을 때 결론이")


def test_c1_three_panel_notes_are_gone():
    html = render.render_report(_moderator_only_report(), Settings())
    for gone in GONE:
        assert gone not in html, gone


def test_c2_the_title_still_says_what_state_this_is():
    """설명을 뺄 수 있는 이유는 **제목이 이미 상태를 말하기 때문**이다."""
    html = render.render_report(_moderator_only_report(), Settings())
    assert "패널 분석 (사회자 결과만 반영)" in html
    assert "사회자 종합" in html


def test_c3_skipped_matches_still_say_they_did_not_run():
    """생략과 Moderator-only 를 같은 말로 적지 않는다 (§1-20)."""
    html = render.render_report(_moderator_only_report(), Settings())
    assert "이 경기는 패널 분석을 하지 않았습니다" in html


def test_c4_initial_scores_keep_their_label():
    """최초 스코어의 주석은 걷었지만 **라벨은 남는다** — 라벨이 없으면
    그 두 수가 무엇인지 알 수 없다."""
    report = _moderator_only_report()
    html = render.render_report(report, Settings())
    if "1·2단계 최초 예상 스코어" in html:        # 픽스처에 있을 때만
        assert "데이터 분석가" in html


def test_c5_distribution_is_still_counts_not_percent():
    """문구를 뺐어도 **확률이 되지 않는 장치는 구조 그대로**다 (§1-11).

    길이 기준이 전체 횟수가 아니라 최댓값이라는 것은 `count_bars` 의
    시그니처가 말한다 — 전체 횟수를 **받지도 않는다.**
    """
    import inspect
    params = list(inspect.signature(charts.count_bars).parameters)
    assert "simulations" not in params, params
    assert "total" not in params, params


def _moderator_html(report) -> str:
    run = next(m.panel for m in report.matches if m.panel and m.panel.moderator)
    return render._moderator_block(run.moderator)


def test_c6_no_percent_in_the_moderator_block():
    """확률은 시장 기준선 표에만 나온다 (§1-11). 분포는 **횟수**다.

    화면에 보이는 글자만 본다 — `width="100%"` 는 SVG 속성이지 값이 아니다.
    """
    assert "%" not in _text(_moderator_html(_moderator_only_report()))


# --------------------------------------------------------------------------
# D. 세부 다섯 절 → 접이식 하나 (내용 보존)
# --------------------------------------------------------------------------
SUBSECTIONS = ("공통점", "차이", "반론·제약", "불확실성", "시장 기준선과의 관계")


def _panel_details(html: str) -> str:
    """'패널 세부 의견' 접이식 하나를 그대로 떼어낸다."""
    i = html.index("패널 세부 의견")
    start = html.rindex("<details", 0, i)
    return html[start:html.index("</details>", i) + len("</details>")]


def test_d1_the_five_sections_live_in_one_details():
    html = render.render_report(_moderator_only_report(), Settings())
    body = _panel_details(html)
    for label in SUBSECTIONS:
        assert f'<p class="lbl">{label}</p>' in body, label


def test_d2_order_is_unchanged():
    html = render.render_report(_moderator_only_report(), Settings())
    body = _panel_details(html)
    pos = [body.index(f'<p class="lbl">{x}</p>') for x in SUBSECTIONS]
    assert pos == sorted(pos), list(zip(SUBSECTIONS, pos))


def test_d3_every_item_survives_verbatim():
    """**내용은 한 글자도 줄이지 않았다.** 사회자 결과의 항목을 그대로
    들고 와 화면의 `<li>` 와 대조한다."""
    report = _moderator_only_report()
    html = render.render_report(report, Settings())
    body = _panel_details(html)
    shown = [re.sub(r"<[^>]+>", "", x)
             for x in re.findall(r"<li>(.*?)</li>", body, re.S)]
    run = next(m.panel for m in report.matches
               if m.panel and m.panel.moderator)
    want = []
    for field, _lbl in render._MODERATOR_ROWS:
        want += list(getattr(run.moderator, field, ()) or ())
    assert want, "픽스처에 세부 항목이 없다"
    for item in want:
        assert item in shown, (item, shown)


def test_d4_market_relation_text_survives():
    report = _moderator_only_report()
    html = render.render_report(report, Settings())
    run = next(m.panel for m in report.matches if m.panel and m.panel.moderator)
    text = getattr(run.moderator, "market_relation", "") or ""
    if text:
        assert text in _panel_details(html)


def test_d5_the_conclusion_stays_outside_the_collapse():
    """접는 것은 세부다. **결론(최종 스코어)은 펼쳐진 채로** 있어야 한다 —
    그것이 사용자가 3단계에서 얻으려는 답이다 (§1-11)."""
    html = render.render_report(_moderator_only_report(), Settings())
    i = html.index("Panel 종합 예상 스코어")
    j = html.index("패널 세부 의견")
    assert i < j, (i, j)


def test_d6_one_more_collapse_per_card_at_most():
    """카드당 접이식은 셋까지다 — 창마다 접으면 클릭이 일곱 번이 된다
    (§1-15-3). 5-E2 에서 패널 세부가 하나 늘어 2 → 3 이 됐다."""
    card = _full_card()
    assert card.count("<details") <= 3, card.count("<details")


def test_d7_the_collapse_is_browser_native():
    """JS 를 새로 들이지 않는다 — 외부 참조 0 이 이 프로젝트의 조건이다
    (§1-8)."""
    html = render.render_report(_moderator_only_report(), Settings())
    assert "<script src" not in html
    assert 'src="http' not in html and 'href="http' not in html
    assert "<summary" in html


def test_d8_summary_names_what_is_inside():
    """접힌 것이 무엇인지 열어 보지 않고도 알 수 있어야 한다."""
    html = render.render_report(_moderator_only_report(), Settings())
    i = html.index("패널 세부 의견")
    head = html[i:i + 200]
    for label in SUBSECTIONS:
        assert label in head, (label, head)


def test_d9_empty_details_are_not_rendered():
    """세부가 하나도 없으면 빈 껍데기를 내지 않는다 (§1-1-15)."""
    assert render._details("제목", "왜", "") == ""


# --------------------------------------------------------------------------
# E. 값은 한 칸도 바뀌지 않았다
# --------------------------------------------------------------------------
def test_e1_no_arithmetic_entered_the_touched_functions():
    """문구를 걷는 변경이었다 — 셈이 들어오면 그건 다른 일이다.

    문자열 이어붙이기(`+`)는 셈이 아니므로 나눗셈·곱셈·뺄셈만 본다.
    """
    tree = ast.parse(_src("toto/render.py"))
    names = {"_direct_compare_block", "_tally_table", "_moderator_block"}
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in names:
            seen.add(node.name)
            for sub in ast.walk(node):
                if isinstance(sub, ast.BinOp):
                    assert not isinstance(sub.op, (ast.Div, ast.Mult, ast.Sub,
                                                   ast.FloorDiv, ast.Pow)), \
                        (node.name, ast.dump(sub)[:90])
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                    assert sub.func.id not in ("sum", "round", "mean"), \
                        (node.name, sub.func.id)
    assert seen == names, seen


def test_e2_no_verdict_words_were_introduced():
    """문구를 줄인 자리에 판정을 넣지 않았다. '추천' 은 **부정문으로만**
    나온다 (§1-17 이 '확률' 에 쓴 것과 같은 기준)."""
    t = _text(_moderator_html(_moderator_only_report()))
    for banned in ("확신도", "신뢰도", "유력", "추천합니다", "추천드립니다"):
        assert banned not in t, banned
    for i in (m.start() for m in re.finditer("추천", t)):
        tail = t[i:i + 20]
        assert "아닙니다" in tail or "않습니다" in tail, tail


def test_e3_footer_rule_is_still_there():
    """§1-3 의 문장은 그대로다 — 문구를 뺀 것이지 원칙을 뺀 것이 아니다."""
    html = render.render_report(_moderator_only_report(), Settings())
    assert "승/무/패를 추천하지 않습니다" in html


def test_e4_no_new_css_class():
    """새 CSS 를 만들지 않았다 — 접이식은 §1-15-3 이 만든 `_details` 를
    그대로 쓰고, 안쪽은 사회자 블록이 원래 쓰던 클래스 그대로다."""
    html = render.render_report(_moderator_only_report(), Settings())
    body = _panel_details(html)
    used = set(re.findall(r'class="([^"]+)"', body))
    assert used <= {"more", "morebody", "meta", "lbl", "mnotes", "ptext"}, used


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
