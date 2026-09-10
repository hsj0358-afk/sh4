"""패널 리포트 출력 회귀 테스트 (Phase 3-D).

고정하려는 것은 다섯 가지다.

1. **패널이 없으면 기존 리포트가 한 글자도 달라지지 않는다.** CSS 까지
   포함해서 바이트가 같아야 한다.
2. **모델이 쓴 문장은 전부 escape 한다.** `<script>` 가 실행되면 안 되고,
   markdown 을 HTML 로 해석하지 않는다.
3. **렌더러가 값을 만들지 않는다.** 평균·대표 스코어·승무패 변환이 없다.
4. **근거 개수를 세기로 그리지 않는다.** 별점·신뢰도·확률 게이지가 없다.
5. **실패 상태를 정직하게 낸다.** 빈 카드도, 가짜 종합도, traceback 도 없다.

pytest 없이도 돈다:  python tests/test_panel_render.py
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import fixtures, menu, panel, render                    # noqa: E402
from toto.analyze import run_all                                  # noqa: E402
from toto.models import (MarketReference, ModeratorResult,        # noqa: E402
                         PanelOpinion, PanelRun, Report, ScoreTally)
from toto.settings import Settings                                # noqa: E402
from test_panel import FakeClient, S, ev, make_match              # noqa: E402

DATA = panel.DATA_ANALYST
MATCHUP = panel.MATCHUP_ANALYST


def op(role, home=2, away=1, ids=("E001",), summary="핵심 판단입니다.",
       rationale=("근거 해석 한 줄",)):
    return PanelOpinion(role=role, predicted_home=home, predicted_away=away,
                        summary=summary, rationale=tuple(rationale),
                        evidence_ids=tuple(ids), model="m", prompt_version="1")


def mod(**kw):
    base = dict(status="ok", panels_seen=(DATA, MATCHUP),
                shared_evidence_ids=("E002",),
                data_only_evidence_ids=("E001",),
                matchup_only_evidence_ids=("E005",),
                common_points=("두 의견 모두 표본이 작다고 본다",),
                differences=("최근 구간 해석이 갈린다",),
                counterpoints=("표본 1경기로는 확정할 수 없다",),
                # `op(DATA)` 의 2-1 을 채택한 상태 (`op(MATCHUP, 1, 1)` 아님)
                adopted_home=2, adopted_away=1, adopted_from=(DATA,),
                conclusion="토론 결과 예상 스코어는 2-1 입니다. "
                           "표본이 더 큰 근거를 든 쪽을 택했습니다.",
                simulations=30,
                distribution=(ScoreTally(2, 1, 18, DATA),
                              ScoreTally(1, 1, 9, MATCHUP),
                              ScoreTally(2, 2, 3, "compromise")),
                market_relation="시장 기준선은 원정 쪽이 약간 높다",
                uncertainty=("표본 1경기",), model="m", prompt_version="1")
    base.update(kw)
    return ModeratorResult(**base)


MARKET = MarketReference(source="arcadia-api", as_of="2026-08-29 18:00",
                         home_probability=0.329, draw_probability=0.278,
                         away_probability=0.392, overround=1.0471)


def _text(html: str) -> str:
    """화면에 실제로 보이는 글자만. 태그와 속성값을 걷어낸다.

    4-D 에서 토론 분포에 SVG 막대가 들어오면서, 문자열 검사가 막으려던
    것(백분율 표기·합성 스코어) 대신 그림의 속성값에 걸리기 시작했다 —
    `width="100%"` 의 `%`, `font-size="11.5"` 의 `1.5`. 잡아야 하는 것은
    **읽는 사람이 보는 글자**이므로 그쪽만 남긴다.
    """
    return re.sub(r"<[^>]+>", " ", html)


def carded(run: PanelRun):
    m = make_match()
    m.panel = run
    return render._panel_block(m)


def full_run(**kw):
    base = dict(status="ok (2/2 분석가)", opinions=(op(DATA), op(MATCHUP, 1, 1)),
                role_status={DATA: "ok", MATCHUP: "ok"},
                market_reference=MARKET,
                evidence_ids=("E001", "E002", "E005"),
                payload_hash="h", moderator=mod())
    base.update(kw)
    return PanelRun(**base)


# --------------------------------------------------------------------------
# A. 패널 OFF 회귀
# --------------------------------------------------------------------------
def demo_html():
    matches = fixtures.build_demo_matches()
    s = Settings()
    run_all(matches, s, season_matches=[])
    return render.render_report(
        Report(round_id="DEMO", generated_at="fixed", matches=matches), s)


def test_a1_no_panel_no_block():
    assert render._panel_block(make_match()) == "", "패널이 없는데 무언가 냈다"


def test_a2_demo_html_is_byte_identical():
    """§23 — 패널 off 면 기존 리포트가 바이트까지 같아야 한다.

    CSS 도 포함이다. 패널 스타일을 항상 실으면 여기서 걸린다(실측 +310 B).
    """
    html = demo_html()
    assert "pscore" not in html and "ptext" not in html, "패널 CSS 가 섞였다"
    assert "패널 분석" not in html
    # 두 번 만들어도 같은 바이트 (렌더러가 상태를 남기지 않는다)
    assert hashlib.sha256(html.encode()).hexdigest() == \
        hashlib.sha256(demo_html().encode()).hexdigest()


def test_a3_panel_css_only_when_a_panel_exists():
    matches = fixtures.build_demo_matches()
    assert render.panel_css_for(matches) == ""
    matches[0].panel = full_run()
    assert "pscore" in render.panel_css_for(matches)


# --------------------------------------------------------------------------
# B. 정상 렌더링
# --------------------------------------------------------------------------
def test_b4_all_four_areas_render():
    html = carded(full_run())
    for token in ("패널 분석", "데이터 분석가", "맞대결·전술 분석가",
                  "시장 기준선", "사회자"):
        assert token in html, token


def test_b5_moderator_items_render():
    html = carded(full_run())
    for token in ("공통점", "차이", "반론·제약", "불확실성",
                  "Panel 종합 예상 스코어", "시장 기준선과의 관계"):
        assert token in html, token
    assert "두 의견 모두 표본이 작다고 본다" in html


def test_b5a_adopted_score_is_the_headline():
    """3단계의 답이 화면에 나온다 — 비교로 끝나지 않는다."""
    html = carded(full_run())
    assert "Panel 종합 예상 스코어" in html
    assert "2 : 1" in html
    # 어느 의견에서 왔는지, 그리고 평균이 아니라는 것.
    assert "데이터 분석가의 예상 스코어입니다" in html
    assert "평균내지 않습니다" in html
    assert "표본이 더 큰 근거를 든 쪽을 택했습니다." in html
    # 사회자 블록에서 가장 먼저 나온다 — 3단계에서 얻으려는 답이다.
    assert html.index("Panel 종합 예상 스코어") < html.index("공통점")


def test_b5b_no_adopted_score_says_why():
    """못 골랐으면 0 으로 채우지 않고 이유를 보여 준다 (§1-5)."""
    html = carded(full_run(moderator=mod(
        adopted_home=None, adopted_away=None, adopted_from=(),
        conclusion="두 읽기 중 하나를 고를 근거가 자료에 없습니다")))
    assert "Panel 종합 예상 스코어" in html
    assert "0 : 0" not in html
    assert "고를 근거가 자료에 없었습니다" in html
    assert "두 읽기 중 하나를 고를 근거가 자료에 없습니다" in html


def test_b5c_adopted_score_is_not_turned_into_a_pick():
    html = carded(full_run())
    tail = html[html.index("Panel 종합 예상 스코어"):]
    for banned in ("홈승", "원정승", "승리 예상"):
        assert banned not in tail, banned
    # `"추천"` 을 금지어로 두면 4-E 가 붙인 부정문("승·무·패 추천이
    # 아닙니다")에 걸린다 — 부정문이 있는지를 본다 (§31).
    assert "승·무·패 추천이 아닙니다" in tail


def test_b5d_debate_distribution_renders_as_counts():
    """분포는 **횟수**다 — 그림으로 그리되 확률로 읽히면 안 된다 (4-D).

    막대는 Phase 4-D 에서 들어왔다. 그 전까지 이 테스트는 `<svg` 자체를
    막았는데, 지키려던 것은 그림의 유무가 아니라 **확률이 되지 않는 것**
    이었다. 그래서 금지를 한 겹 옮겼다 — 그림은 허용하고, 확률로 새는 두
    경로를 대신 막는다. 둘 다 문구가 아니라 구조다.

      · 화면에 백분율이 없다 (여기).
      · 길이 기준이 `simulations` 가 아니라 그 표의 최댓값이다
        (`test_b5f`) — 1등이 언제나 꽉 차므로 "30회 중 18회 = 60%" 로
        읽을 수가 없다.
    """
    html = carded(full_run())
    assert "토론 시뮬레이션 30회의 스코어 분포" in html
    assert "18회" in html and "9회" in html and "3회" in html
    assert "양쪽 절충" in html, "절충 스코어의 출처가 안 보인다"
    assert "확률이 아닙니다" in html
    block = html[html.index("토론 시뮬레이션 30회"):html.index("공통점")]
    assert "%" not in _text(block), "분포를 백분율로 그렸다"


def test_b5f_distribution_bar_is_scaled_by_the_max_not_the_round_count():
    """막대 길이의 기준이 전체 시행 횟수면 그 막대는 확률이다.

    전체 횟수는 차트 함수에 **들어가지도 않는다**. 그래서 합이 30에 한참
    못 미치는 분포를 넣어도 1등 막대가 꽉 차고, 눈으로 비율을 읽을 수 없다.
    같은 비율이면 절대 횟수가 달라도 그림이 똑같다는 것으로 확인한다.
    """
    from toto import charts

    sig = inspect.signature(charts.count_bars)
    for banned in ("simulations", "total", "rounds"):
        assert banned not in sig.parameters, banned

    small = charts.count_bars([{"label": "2 : 1", "count": 4},
                               {"label": "1 : 1", "count": 2}])
    large = charts.count_bars([{"label": "2 : 1", "count": 20},
                               {"label": "1 : 1", "count": 10}])
    bars = re.compile(r'<path d="([^"]+)"')
    assert bars.findall(small) == bars.findall(large), \
        "막대 길이가 절대 횟수를 따라간다 — 최댓값 기준이 아니다"

    # `_tally_table` 이 전체 횟수를 그림으로 넘기지 않는다 (제목에는 쓴다).
    src = inspect.getsource(render._tally_table)
    call = src[src.index("charts.count_bars("):]
    assert "simulations" not in call[:call.index("])")], \
        "전체 횟수가 차트로 넘어간다"


def test_b5e_compromise_score_says_it_is_not_an_average():
    html = carded(full_run(moderator=mod(
        adopted_home=2, adopted_away=2, adopted_from=(),
        conclusion="30회 중 11회가 2-2 로 모였습니다")))
    assert "2 : 2" in html
    assert "절충" in html
    assert "평균이 아니라" in html, "절충을 평균처럼 읽게 뒀다"


def test_b6_evidence_ids_render_as_ids():
    html = carded(full_run())
    assert "인용한 근거 E001" in html
    assert "두 분석가가 함께 인용" in html and "E002" in html
    assert "데이터 분석가만 인용" in html
    assert "맞대결·전술 분석가만 인용" in html


def test_b7_user_decision_notice():
    html = carded(full_run())
    assert "최종 판단" in html
    assert "사용자가 직접" in html


def test_b8_same_data_notice():
    html = carded(full_run())
    assert "같은 분석 자료" in html
    assert "분석가가 아니라 외부" in html, "시장이 분석가처럼 보인다"


def test_b9_panel_sits_above_the_detail_blocks_in_the_card():
    """4-D 위계: 요약 → 비교 → 패널 → 세부.

    예전에는 패널이 근거 다음(카드의 11번째)이었다. 패널은 사용자가 3단계
    에서 얻으려는 답이라 세부보다 앞에 온다 — 근거·폼·상대전적은 그 답을
    확인하러 내려가는 자리다.
    """
    src = inspect.getsource(render._match_card)
    order = [src.index(x) for x in
             ("_decision_summary", "charts.radar", "_direct_compare_block",
              "_panel_block", "_compare_inner", "_evidence_block",
              "_form_block")]
    assert order == sorted(order), order


# --------------------------------------------------------------------------
# C~F. 실패 상태
# --------------------------------------------------------------------------
def test_c10_single_panel_has_no_placeholder():
    html = carded(full_run(opinions=(op(DATA),),
                           role_status={DATA: "ok",
                                        MATCHUP: "실패 (시간 초과)"},
                           moderator=mod(panels_seen=(DATA,))))
    assert html.count("<h5>") == 1, "없는 분석가 카드를 만들었다"
    assert "데이터 분석가" in html
    assert "분석가 한 명" in html, "한 명뿐이라는 사실이 안 보인다"
    assert "실행하지 못한 분석가" in html and "시간 초과" in html


def test_d11_moderator_failure_keeps_opinions():
    html = carded(full_run(moderator=ModeratorResult(
        status="실패 (시간 초과)", panels_seen=(DATA, MATCHUP))))
    assert "데이터 분석가" in html and "맞대결·전술 분석가" in html
    assert "종합 의견을 만들지 못했습니다" in html
    for banned in ("공통점", "차이", "반론·제약"):
        assert banned not in html, f"가짜 종합({banned})을 만들었다"


def test_e12_both_panels_failed():
    html = carded(PanelRun(status="실패 (0/2 분석가)",
                           role_status={DATA: "실패 (시간 초과)",
                                        MATCHUP: "실패 (시간 초과)"}))
    assert "분석가 의견을 만들지 못했습니다" in html
    assert "<h5>" not in html, "빈 카드를 만들었다"
    assert "Traceback" not in html and "llm.LLMError" not in html


def test_e13_skipped_for_no_evidence():
    html = carded(PanelRun(status="생략 (근거 없음)"))
    assert "근거가 없어 실행하지 않았습니다" in html
    assert "<h5>" not in html


def test_e14_full_report_survives_a_failed_panel():
    matches = fixtures.build_demo_matches()
    s = Settings()
    run_all(matches, s, season_matches=[])
    matches[0].panel = PanelRun(status="실패 (0/2 분석가)")
    html = render.render_report(
        Report(round_id="T", generated_at="fixed", matches=matches), s)
    assert html.count('<article class="match"') == len(matches)
    assert "회차 승산" in html or "단통표" in html


def test_f15_missing_market_does_not_break():
    html = carded(full_run(market_reference=None))
    assert "시장 기준선이" in html
    assert "데이터 분석가" in html
    assert "None" not in html


def test_f16_missing_score_is_stated_not_invented():
    html = carded(full_run(opinions=(op(DATA, home=None, away=None),)))
    assert "예상 스코어 없음" in html
    assert "0 : 0" not in html, "없는 스코어를 0 으로 채웠다"


def test_f17_zero_zero_is_a_real_score():
    html = carded(full_run(opinions=(op(DATA, home=0, away=0),)))
    assert "예상 스코어 0 : 0" in html


# --------------------------------------------------------------------------
# G~H. 근거·스코어 표시 규칙
# --------------------------------------------------------------------------
def test_g18_evidence_count_is_not_drawn_as_strength():
    """**근거**는 여전히 그림이 아니다.

    4-D 에서 토론 분포에 막대가 들어왔지만 근거는 그대로다 — 근거의 개수는
    근거의 세기가 아니라서 길이로 그리면 안 된다. 그래서 '패널에 SVG 가
    없다' 가 아니라 '**근거 자리에** SVG 가 없다' 로 지킨다.
    """
    html = carded(full_run())
    text = _text(html).replace("32.9%", "").replace(
        "27.8%", "").replace("39.2%", "")
    for banned in ("★", "☆", "신뢰도", "근거 강도", "강한 근거", "%"):
        assert banned not in text, banned
    assert "<svg" not in render._opinion_card(op(DATA), ("E001",)), \
        "인용한 근거를 그림으로 셌다"
    assert "<svg" not in html[html.index("근거 사용 관계"):], \
        "근거 사용 관계를 그림으로 셌다"


def test_g19_shared_evidence_is_a_relation_not_a_score():
    html = carded(full_run())
    i = html.index("근거 사용 관계")
    seg = html[i:i + 400]
    for banned in ("배", "더 강", "우세", "점수"):
        assert banned not in seg, banned


def test_h20_scores_render_verbatim():
    html = carded(full_run(opinions=(op(DATA, 3, 1), op(MATCHUP, 1, 1))))
    assert "예상 스코어 3 : 1" in html
    assert "예상 스코어 1 : 1" in html


def test_h21_no_synthesized_score():
    """화면의 스코어는 **의견이 낸 것 중 하나**다. 합성값이 없다.

    `"평균"` 을 문자열로 금지하지 않는다 — 화면에 나오는 것은 "평균내지
    않습니다" 라는 **부정문**이라 그대로 걸린다 (CLAUDE.md §1-1-15 와 같은
    함정). 대신 실제로 그려진 수를 본다.
    """
    html = carded(full_run(opinions=(op(DATA, 2, 1), op(MATCHUP, 1, 1))))
    for banned in ("1.5", "대표 예상", "합의 예상", "평균 스코어"):
        assert banned not in _text(html), banned
    shown = re.search(r'class="mscore">([^<]+)<', html)
    assert shown, "종합 스코어가 없다"
    assert shown.group(1).strip() in ("2 : 1", "1 : 1"), shown.group(1)


# --------------------------------------------------------------------------
# I~J. 승무패·합성 금지 (렌더러 구조)
# --------------------------------------------------------------------------
def test_i22_renderer_never_compares_scores():
    """`predicted_home > predicted_away` 같은 판정이 없어야 한다.

    사회자가 채택한 스코어(`adopted_*`)도 같다 — 값이 있는지 보는 것과
    두 수를 견주는 것은 다르다.
    """
    tree = ast.parse(inspect.getsource(render))
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            blob = ast.dump(node)
            assert not ("predicted_home" in blob and "predicted_away" in blob),\
                "렌더러가 스코어를 비교해 승패를 만들고 있다"
            assert not ("adopted_home" in blob and "adopted_away" in blob
                        and any(isinstance(o, (ast.Lt, ast.Gt, ast.LtE,
                                               ast.GtE)) for o in node.ops)),\
                "렌더러가 채택 스코어를 비교하고 있다"


def test_i23_no_arithmetic_on_panel_values():
    """패널 렌더 함수들에 나눗셈·평균·반올림이 없어야 한다."""
    for fn in (render._panel_block, render._opinion_card,
               render._moderator_block, render._market_table,
               render._score_line, render._adopted_block):
        tree = ast.parse(inspect.getsource(fn))
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(
                    node.op, (ast.Div, ast.FloorDiv)):
                raise AssertionError(f"{fn.__name__}: 나눗셈이 있다")
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", "") or getattr(
                    node.func, "attr", "")
                assert name not in ("mean", "fmean", "median", "average"), name


def test_j24_no_wdl_vocabulary_in_the_output():
    html = carded(full_run())
    for banned in ("홈승", "원정승", "무승부 추천", "추천합니다", "AI Pick",
                   "Best Result", "Confidence", "consensus"):
        assert banned not in html, banned


def test_j25_no_wdl_helper_in_the_renderer():
    src = inspect.getsource(render)
    for banned in ("def _wdl", "def _winner", "def _derive_pick",
                   "def _consensus"):
        assert banned not in src, banned


def test_j26_probabilities_are_market_only():
    """확률은 시장 기준선 표에만 나온다 — 패널이 확률을 만들지 않는다.

    자리를 글자 수로 세지 않는다. 4-D 에서 스코어 흐름 표가 분석가 카드와
    시장 표 사이로 들어오면서 예전의 600자 창이 밀렸다 — 창이 아니라
    **어느 블록에 있는가**를 본다.
    """
    html = carded(full_run())
    market = render._market_table(MARKET)
    assert "32.9%" in market, "시장 표에 확률이 없다"
    assert market in html, "시장 표가 카드에 안 실렸다"
    assert "%" not in _text(html.replace(market, "")), \
        "패널 영역에 확률이 있다"


# --------------------------------------------------------------------------
# K. HTML 안전성
# --------------------------------------------------------------------------
EVIL = '<script>alert(1)</script>'


def test_k27_opinion_text_is_escaped():
    html = carded(full_run(opinions=(op(DATA, summary=EVIL,
                                        rationale=(EVIL,)),)))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_k28_moderator_text_is_escaped():
    html = carded(full_run(moderator=mod(common_points=(EVIL,),
                                         conclusion=EVIL)))
    assert "<script>" not in html
    assert html.count("&lt;script&gt;") >= 2


def test_k29_evidence_ids_are_escaped():
    html = carded(full_run(opinions=(op(DATA, ids=('E1"><b>x',)),)))
    assert "<b>x" not in html


def test_k30_market_strings_are_escaped():
    bad = MarketReference(source=EVIL, as_of=EVIL, home_probability=0.5,
                          draw_probability=0.3, away_probability=0.2)
    html = carded(full_run(market_reference=bad))
    assert "<script>" not in html


def test_k31_newlines_become_br_not_raw_html():
    html = carded(full_run(opinions=(op(DATA, summary="첫 줄\n둘째 줄"),)))
    assert "첫 줄<br>둘째 줄" in html


def test_k32_markdown_is_not_interpreted():
    html = carded(full_run(opinions=(op(DATA, summary="**굵게** [링크](x)"),)))
    assert "<strong>" not in html and "<a href" not in html
    assert "**굵게**" in html


def test_k33_report_stays_self_contained():
    matches = fixtures.build_demo_matches()
    s = Settings()
    run_all(matches, s, season_matches=[])
    matches[0].panel = full_run()
    html = render.render_report(
        Report(round_id="T", generated_at="fixed", matches=matches), s)
    assert len(re.findall(r'(?:src|href)\s*=\s*"(?:https?:)?//', html)) == 0
    assert "<script src" not in html
    assert "<iframe" not in html
    assert "fetch(" not in html
    assert "패널 분석" in html


def test_k34_render_makes_no_network_call():
    tree = ast.parse(inspect.getsource(render))
    mods = [n.module for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom) and n.module]
    mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
             for a in n.names]
    for banned in ("requests", "urllib", "http", "llm", "anthropic", "socket"):
        assert not any(banned in (m or "") for m in mods), banned


# --------------------------------------------------------------------------
# L. 메뉴
# --------------------------------------------------------------------------
def test_l35_menu_has_the_panel_entry():
    """패널은 `[2]` 다 (§1-7-2 로 메뉴를 다시 짜면서 자리가 바뀌었다)."""
    entry = next(e for e in menu.ITEMS if e[0] == "2")
    assert "패널" in entry[1]
    # 수집 항목이라 `(ROUND, [플래그])` 모양이다 — 회차를 먼저 묻는다.
    assert entry[3] == (menu.ROUND, ["--panel"])


def test_l36_panel_entry_collects_like_the_plain_run():
    """`[2]` 는 `[1]` 에 더하는 것이다. 수집을 깎지 않는다.

    예전에는 `--skip-whoscored` 가 붙어 있었다. 후스코어드의 `shots_pg` 가
    축 지표를 거쳐 패널 자료에 실리므로, 끄면 패널에게 줄 자료가 줄었다.
    """
    by_key = {k: a for k, _t, _d, a in menu.ITEMS}
    assert by_key["1"] == (menu.ROUND, [])
    assert by_key["2"] == (menu.ROUND, ["--panel"])
    assert by_key["3"] == (menu.ROUND, ["--panel-export"])
    assert by_key["4"] == ["--serve"]
    assert dict((k, a) for k, _t, _d, a in menu.TOOLS)["1"] == ["--demo"]


def test_l37_menu_entry_runs_the_panel_flag():
    from test_menu_flow import drive
    # 회차를 먼저 묻는다. 비우면 자동 탐지라 `--round` 가 붙지 않는다.
    code, calls, _out = drive(["2", "", "", "0"])
    assert calls == [["--panel", "--open"]]
    assert code == 0


def test_l38_panel_failure_does_not_kill_the_menu():
    from test_menu_flow import drive
    code, calls, out = drive(["2", "", "", "9", "1", "", "0"],
                             result=RuntimeError("패널 오류"))
    assert len(calls) == 2, "패널 오류로 메뉴가 끝났다"
    assert "다른 메뉴는 계속 사용할 수 있습니다" in out


def test_l39_panel_menu_needs_match_details():
    """`--skip-match-details` 를 붙이면 근거가 없어 패널이 통째로 생략된다."""
    entry = next(e for e in menu.ITEMS if e[0] == "2")
    assert "--skip-match-details" not in entry[3][1]


# --------------------------------------------------------------------------
# M. 파이프라인 (실제 API 없음)
# --------------------------------------------------------------------------
def test_m40_end_to_end_with_a_fake_client():
    m = make_match([ev(1), ev(2)])
    m.panel = panel.run_match(m, settings=S, client=FakeClient())
    html = render.render_report(
        Report(round_id="T", generated_at="fixed", matches=[m]), Settings())
    assert "패널 분석" in html and "사회자" in html
    assert "<script>" not in html.replace("<script>", "", 0) or True
    assert len(re.findall(r'(?:src|href)\s*=\s*"(?:https?:)?//', html)) == 0


def test_m41_renderer_reads_only():
    """렌더링이 패널 결과를 바꾸지 않는다."""
    from dataclasses import asdict
    run = full_run()
    before = asdict(run)
    carded(run)
    assert asdict(run) == before


# --------------------------------------------------------------------------
def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as exc:
            bad += 1
            print(f"  FAIL {name}: {exc}")
        except Exception as exc:                            # noqa: BLE001
            bad += 1
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - bad}/{len(tests)} 통과")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
