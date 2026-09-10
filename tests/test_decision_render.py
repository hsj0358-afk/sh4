"""요약 · 직접 비교 · 패널 시각화 회귀 테스트 (Phase 4-D).

4-D 는 **새 분석이 아니다.** 값은 전부 이미 계산돼 있었고, 문제는 그것이
카드의 스무 번째 블록까지 내려가야 보인다는 것이었다. 그래서 위계를 바꾼다.

    요약 → 비교 → 패널 → 세부

고정하려는 것은 여섯 가지다.

1. **새 값을 만들지 않는다.** 요약은 아래 블록의 끝값을 옮길 뿐이고,
   직접 비교는 축이 담고 있는 수를 그대로 놓는다. 종합 점수가 없다.
2. **승/무/패를 만들지 않는다.** 어느 블록도 두 수를 견주어 결과를 고르지
   않는다.
3. **없는 것은 없다고 적는다.** 0 으로 채우거나 줄을 지우지 않는다.
4. **분포는 확률이 아니다.** 막대는 그리되 전체 시행 횟수로 나누지 않는다.
5. **패널 판정을 두 벌 만들지 않는다.** 화면은 4-C 의 `PanelMatchAudit` 를
   그대로 읽는다.
6. **자체 완결형이다.** 외부 참조가 없고, 새 CSS 클래스를 만들지 않는다.

pytest 없이도 돈다:  python tests/test_decision_render.py
"""
from __future__ import annotations

import ast
import inspect
import re
import sys
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import charts, panelaudit, render                       # noqa: E402
from toto.models import Odds, ScoreTally                          # noqa: E402
from test_axes_render import RECENT, SEASON, _match               # noqa: E402
from test_panel_render import DATA, MATCHUP, full_run, mod, op    # noqa: E402


def _text(html: str) -> str:
    """화면에 실제로 보이는 글자만 (SVG 속성값을 검사에서 뺀다)."""
    return re.sub(r"<[^>]+>", " ", html)


def _panelled(**kw):
    """분석 축 + 패널이 둘 다 붙은 경기."""
    m = _match()
    m.panel = full_run(**kw)
    return m


# --------------------------------------------------------------------------
# A. 요약 — 이 경기에서 지금까지 나온 것
# --------------------------------------------------------------------------
def test_a1_market_row_shows_the_probabilities_it_already_has():
    m = _match()
    m.odds = Odds(home=2.0, draw=3.5, away=4.0, source="arcadia-api")
    from toto.predict import additive_probabilities

    m.probs = additive_probabilities(m.odds.home, m.odds.draw,
                                     m.odds.away)
    html = render._decision_summary(m)
    assert "시장 내재확률" in html
    ph, _pd, _pa = m.probs.pct()
    assert f"{ph:.1f}%" in html, html


def test_a2_no_odds_says_why_instead_of_zero():
    html = render._decision_summary(_match())
    assert "배당을 가져오지 못했습니다" in html
    assert "0.0%" not in html, "배당이 없는데 0% 로 채웠다"


def test_a3_panel_rows_appear_only_when_a_panel_exists():
    plain = render._decision_summary(_match())
    assert "패널 최종 예상 스코어" not in plain, \
        "패널 없이 돌린 실행에 패널 줄이 생겼다"
    assert "패널 최종 예상 스코어" in render._decision_summary(_panelled())


def test_a4_adopted_score_is_copied_verbatim_not_averaged():
    """2-1 과 1-1 에서 1.5 같은 값이 나오면 안 된다."""
    html = render._decision_summary(_panelled())
    assert "2 : 1" in html
    assert "평균내지 않습니다" in html
    for banned in ("1.5", "1 : 1.5", "대표 예상", "합의 예상"):
        assert banned not in _text(html), banned


def test_a5_compromise_says_it_is_not_an_average():
    html = render._decision_summary(_panelled(moderator=mod(
        adopted_home=2, adopted_away=2, adopted_from=())))
    assert "2 : 2" in html
    assert "절충" in html and "평균이 아닙니다" in html


def test_a6_no_adopted_score_says_why_and_never_prints_zero():
    html = render._decision_summary(_panelled(moderator=mod(
        adopted_home=None, adopted_away=None, adopted_from=())))
    assert "고를 근거가 자료에 없었습니다" in html
    assert "0 : 0" not in html


def test_a7_initial_opinions_are_shown_as_a_relation():
    """두 원안을 나란히 적되 **누가 옳은지 말하지 않는다.**"""
    html = render._decision_summary(_panelled())
    assert "두 분석가의 처음 의견" in html
    assert "데이터 2 : 1" in html and "맞대결 1 : 1" in html
    assert "달랐습니다" in html
    same = render._decision_summary(_panelled(
        opinions=(op(DATA, 2, 1), op(MATCHUP, 2, 1))))
    assert "같았습니다" in same


def test_a8_axis_and_evidence_counts_come_with_their_caveat():
    html = render._decision_summary(_match())
    assert "계산된 분석 축" in html
    assert "3축" in html, html          # 픽스처는 축 셋을 채운다
    assert "근거" in html
    # 근거가 없는 경기는 **왜 없는지**를 적는다 (§1-5).
    assert "0건" in html and "게이트" in html


def test_a9_summary_never_recommends():
    html = render._decision_summary(_panelled())
    text = _text(html)
    for banned in ("홈승", "원정승", "승리 예상", "유력", "우세", "추천합니다"):
        assert banned not in text, banned
    assert "추천하지 않습니다" in text


# --------------------------------------------------------------------------
# B. 홈 ↔ 원정 직접 비교
# --------------------------------------------------------------------------
def test_b1_no_analysis_no_block():
    assert render._direct_compare_block(_match(analysis=False)) == ""


def test_b2_only_rows_where_both_sides_have_a_value():
    """한쪽만 그린 맞대결 막대는 없는 쪽을 0 처럼 보이게 한다 (§1-5)."""
    m = _match()
    # 원정에서 시즌 xG 를 지운다 — 그 줄은 통째로 빠져야 한다.
    m.analysis.away.chance_quality.metrics.pop(f"{SEASON}.xg", None)
    html = render._direct_compare_block(m)
    season = html[:html.index("최근 6경기")]
    assert "xG" not in _text(season), "한쪽만 있는 지표를 그렸다"
    # 최근 구간에는 양쪽 다 있으므로 그대로 나온다.
    assert "xG" in _text(html[html.index("최근 6경기"):])


def test_b3_periods_are_not_mixed_into_one_picture():
    """시즌과 최근은 다른 피드다. 한 그림에 넣으면 그 비교가 성립하지 않는다."""
    html = render._direct_compare_block(_match())
    assert "시즌" in html and "최근 6경기" in html
    assert html.count("<figure") >= 2, "기간을 한 그림에 몰아넣었다"
    assert html.index("시즌") < html.index("최근 6경기")


def test_b4_lower_is_better_metrics_are_marked():
    html = render._direct_compare_block(_match())
    assert "실점 ↓" in html or "피슈팅 ↓" in html, html
    # 방향 표시는 라벨뿐이고, 막대가 좋고 나쁨을 담지 않는다는 말이 붙는다.
    assert "좋고 나쁨이 아닙니다" in html


def test_b5_unequal_sample_sizes_are_reported_not_hidden():
    m = _match()
    m.analysis.away.chance_quality.metrics[f"{RECENT}.xg"].sample_count = 2
    html = render._direct_compare_block(m)
    assert "표본 크기가 다른 지표" in html
    assert "홈 n=4" in html and "원정 n=2" in html, html


def test_b5b_uniform_sample_mismatch_collapses_into_one_line():
    """두 팀이 치른 경기 수가 다르면 그 기간의 지표가 통째로 어긋난다.

    실물에서 같은 "(홈 n=28 / 원정 n=25)" 가 한 줄에 여섯 번 반복돼, 정작
    표본이 진짜로 좁은 지표가 그 사이에 묻혔다. 같은 짝은 한 번만 적는다.
    """
    m = _match()
    for team, count in ((m.analysis.home, 28), (m.analysis.away, 25)):
        for attr in ("time_context", "chance_quality", "defensive_quality"):
            for key, metric in getattr(team, attr).metrics.items():
                if key.startswith(f"{SEASON}."):
                    metric.sample_count = count
    html = render._direct_compare_block(m)
    assert html.count("홈 n=28 / 원정 n=25") == 1, "같은 짝을 여러 번 적었다"
    assert "지표" in html and "개 전부" in html, html


def test_b6_equal_samples_produce_no_warning():
    assert "표본 크기가 다른 지표" not in render._direct_compare_block(_match())


def test_b7_each_metric_is_named_once():
    """같은 지표가 두 축에 다 있어도 화면에서 두 번 세면 안 된다."""
    names = [name for _attr, name in render._DIRECT_ROWS]
    assert len(names) == len(set(names)), names


def test_b8_values_are_copied_from_the_axis_verbatim():
    m = _match()
    m.analysis.home.time_context.metrics[f"{SEASON}.points"].value = 1.77
    html = render._direct_compare_block(m)
    assert "1.77" in html, "축의 값이 그대로 나오지 않았다"


def test_b9_direct_compare_never_recommends():
    text = _text(render._direct_compare_block(_match()))
    for banned in ("홈승", "원정승", "승리 예상", "유력"):
        assert banned not in text, banned
    # `"종합 점수"` 를 금지어로 두면 이 블록이 스스로 적은 부정문
    # ("종합 점수를 만들지 않고")에 걸린다 — 부정문이 있는지를 본다.
    assert "종합 점수를 만들지 않고" in text
    assert "승·무·패를 추천하지 않습니다" in text


# --------------------------------------------------------------------------
# C. 패널 시각화
# --------------------------------------------------------------------------
def test_c1_score_flow_reads_the_audit_record_not_its_own_maths():
    """§1-8 — 화면과 감사 보고서가 같은 함수를 쓴다."""
    m = _panelled()
    audit = panelaudit.match_audit(m, m.panel)
    _no, da, mu, adopted = audit.row
    html = render._score_flow(m)
    for cell in (da, mu, adopted):
        assert cell.replace("-", " : ") in html, cell
    assert "데이터 분석가의 원안을 그대로 채택" in html
    assert "다름" in html, "처음 의견의 관계가 안 보인다"


def test_c2_score_flow_says_what_happened_not_who_was_right():
    html = render._score_flow(_panelled())
    assert "무엇을 했는지" in html
    for banned in ("옳았", "정확", "신뢰할 만", "더 나은"):
        assert banned not in _text(html), banned


def test_c3_missing_analyst_is_a_dash_not_a_zero():
    html = render._score_flow(_panelled(opinions=(op(DATA),)))
    assert "맞대결·전술 분석가" in html
    assert "0 : 0" not in html
    assert "—" in html, "없는 의견을 빈칸으로 뒀다"


def test_c4_compromise_shows_as_modified_not_as_an_analyst_win():
    html = render._score_flow(_panelled(moderator=mod(
        adopted_home=3, adopted_away=3, adopted_from=())))
    assert "수정·절충" in html


def test_c5_no_panel_no_flow():
    assert render._score_flow(_match()) == ""


def test_c6_distribution_labels_are_counts():
    html = render._tally_table(mod())
    text = _text(html)
    assert "18회" in text and "9회" in text and "3회" in text
    assert "%" not in text, "분포를 백분율로 적었다"
    assert "확률이 아닙니다" in text


def test_c7_distribution_bar_ignores_the_round_count():
    """전체 횟수가 길이에 끼어들면 그 막대는 확률이다."""
    a = charts.count_bars([{"label": "2 : 1", "count": 6},
                           {"label": "1 : 1", "count": 3}])
    b = charts.count_bars([{"label": "2 : 1", "count": 24},
                           {"label": "1 : 1", "count": 12}])
    paths = re.compile(r'<path d="([^"]+)"')
    assert paths.findall(a) == paths.findall(b)


def test_c8_empty_distribution_draws_nothing():
    assert charts.count_bars([]) == ""
    assert charts.count_bars([{"label": "2 : 1", "count": 0}]) == ""
    assert render._tally_table(mod(distribution=())) == ""


def test_c9_distribution_keeps_the_origin_visible():
    html = render._tally_table(mod(distribution=(
        ScoreTally(2, 1, 5, DATA), ScoreTally(1, 1, 4, "compromise"))))
    assert "데이터 분석가" in html and "양쪽 절충" in html


# --------------------------------------------------------------------------
# D. 전체 규칙
# --------------------------------------------------------------------------
NEW_BLOCKS = ("_decision_summary", "_direct_compare_block", "_score_flow")


def test_d1_new_blocks_do_not_compute():
    """읽어서 놓기만 한다 — 나눗셈·평균·합산이 없다."""
    for name in NEW_BLOCKS:
        tree = ast.parse(inspect.getsource(getattr(render, name)))
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(
                    node.op, (ast.Div, ast.FloorDiv, ast.Sub)):
                raise AssertionError(f"{name}: 산술 연산이 있다")
            if isinstance(node, ast.Call):
                fn = getattr(node.func, "id", "") or getattr(
                    node.func, "attr", "")
                assert fn not in ("sum", "mean", "fmean", "median", "round",
                                  "average"), f"{name}: {fn}()"


def test_d2_new_blocks_never_compare_two_scores():
    for name in NEW_BLOCKS:
        tree = ast.parse(inspect.getsource(getattr(render, name)))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            dump = ast.dump(node)
            assert "predicted_" not in dump, f"{name}: 스코어를 견줬다"
            if any(isinstance(o, (ast.Lt, ast.Gt, ast.LtE, ast.GtE))
                   for o in node.ops):
                assert "adopted" not in dump, f"{name}: 채택 스코어를 견줬다"


def test_d3_no_wdl_helper_appears():
    src = inspect.getsource(render)
    for banned in ("def _wdl", "def _winner", "def _derive_pick",
                   "def _consensus", "def _confidence"):
        assert banned not in src, banned


def test_d4_model_text_is_escaped():
    evil = '<script>alert(1)</script>'
    m = _panelled(moderator=mod(conclusion=evil))
    for html in (render._decision_summary(m), render._panel_block(m)):
        assert "<script>" not in html, "모델 문장이 그대로 새어 나갔다"


def test_d5_no_external_reference():
    m = _panelled()
    for html in (render._decision_summary(m), render._direct_compare_block(m),
                 render._score_flow(m)):
        for bad in ("http://", "https://", "<script", "<iframe", "url("):
            assert bad not in html, bad


def test_d6_only_existing_css_classes():
    """새 디자인 체계를 만들지 않는다 — 있는 클래스만 쓴다."""
    allowed = {"block", "meta", "mini", "num", "nodata", "tossup", "chart",
               "legend", "lg", "sw", "lbl", "vs", "tablewrap"}
    m = _panelled()
    for html in (render._decision_summary(m), render._direct_compare_block(m),
                 render._score_flow(m)):
        for group in re.findall(r'class="([^"]+)"', html):
            for token in group.split():
                assert token in allowed, f"새 CSS 클래스: {token}"


def test_d7_blocks_are_well_formed():
    m = _panelled()
    for html in (render._decision_summary(m), render._direct_compare_block(m),
                 render._score_flow(m)):
        ElementTree.fromstring(f"<div>{html}</div>")


def test_d8_card_hierarchy_is_summary_compare_panel_detail():
    src = inspect.getsource(render._match_card)
    order = [src.index(x) for x in
             ("_odds_block", "_decision_summary", "_compare_inner",
              "{season_axes}", "_direct_compare_block", "_panel_block",
              "_recent_block(match, settings)", "{recent_axes}",
              "_traits_block", "_evidence_block", "_h2h_block")]
    assert order == sorted(order), order


def test_d9_panel_visualisation_is_shared_with_the_audit():
    """감사와 화면이 결정 유형을 따로 계산하면 둘이 갈라진다."""
    src = inspect.getsource(render._score_flow)
    assert "panelaudit.match_audit(" in src
    for banned in ("ADOPTED_DATA =", "def decision_type", "== da", "== mu"):
        assert banned not in src, banned


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
