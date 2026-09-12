"""경기력 분석 블록 렌더링 회귀 테스트 (2-A · 2-B · 2-C → 리포트).

세 축은 진작 계산되고 있었지만 리포트에 나가는 길이 없었다. `match.analysis`
를 읽는 블록이 장소(2-E) · 상대 강도(2-F) · 근거(2-G) 셋뿐이었고, 시즌 초에는
그 셋이 전부 표본에 걸려 빈다. 260050 실행에서 2-C 는 28/28팀 만들어졌는데
화면에는 한 줄도 나오지 않았다.

이 블록은 **읽어서 놓기만 한다** — 값을 다시 계산하지 않고, 지표를 합치거나
점수로 바꾸지 않으며, 승무패를 고르지 않는다.

pytest 없이도 돈다:  python tests/test_axes_render.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import render                                        # noqa: E402
from toto.models import (                                      # noqa: E402
    AnalysisAxis, Match, MatchAnalysis, Metric, TeamAnalysis, TeamRef)

SEASON = "season"
RECENT = "recent6"


def _metric(name, value, period, n=None, **kw) -> Metric:
    return Metric(name=name, label=name, value=value, provenance="observed",
                  period=period, sample_count=n, **kw)


def _axis(name: str, values: dict) -> AnalysisAxis:
    """values: {(기간, 지표): (값, 표본)}"""
    axis = AnalysisAxis(name=name, requested_matches=6, available_matches=5)
    for (period, metric), (value, n) in values.items():
        axis.metrics[f"{period}.{metric}"] = _metric(metric, value, period, n)
    return axis


def _team(name: str, *, season_only: bool = False) -> TeamAnalysis:
    def both(metric, s, r):
        out = {(SEASON, metric): s}
        if not season_only:
            out[(RECENT, metric)] = r
        return out

    tc, cq, dq = {}, {}, {}
    tc.update(both("points", (1.80, 20), (2.00, 6)))
    tc.update(both("goals", (2.10, 20), (2.50, 6)))
    tc.update(both("goal_diff", (1.20, 20), (-0.50, 6)))
    if not season_only:
        # 2-A 가 만든 트렌드. 뺄 수 있는 지표에만 붙는다 (§1-1-9) — 여기서는
        # 득점·승점처럼 실제로 붙는 경우와, 축이 남긴 사유를 함께 재현한다.
        tc[("trend6", "points")] = (0.20, 6)
        tc[("trend6", "goals")] = (-0.35, 6)
    cq.update(both("shots", (16.0, 20), (14.0, 6)))
    cq.update(both("xg", (2.05, 20), (1.70, 4)))
    cq.update(both("on_target_rate", (41.5, 20), (38.0, 4)))
    cq.update(both("goals_minus_xg", (0.31, 20), (-0.22, 4)))
    dq.update(both("shots_against", (9.5, 20), (11.0, 6)))
    dq.update(both("goals_against", (0.90, 20), (1.30, 6)))
    if not season_only:
        # 시즌에는 없고 최근 창에만 있는 지표 (§1-1-2). season_only 픽스처는
        # '최근이 통째로 비는' 경우를 재현하는 것이므로 여기도 넣지 않는다.
        cq[(RECENT, "npxg")] = (1.55, 4)
        cq[(RECENT, "xg_per_shot")] = (0.121, 4)
        dq[(RECENT, "npxga")] = (1.12, 5)
        dq[(RECENT, "npxga_per_shot_against")] = (0.102, 5)
    tc_axis = _axis("time_context", tc)
    if not season_only:
        # 밴드는 note 앞의 토큰으로 실려 온다 (analysis.parse_trend_band).
        tc_axis.metrics["trend6.points"].note = "higher 문턱 0.40"
        tc_axis.metrics["trend6.goals"].note = "lower 문턱 0.30"
        tc_axis.notes.append("xg: 시즌과 최근의 산출 방식이 달라 뺄 수 없음")
        tc_axis.notes.append("패턴 A — 이 줄은 다른 블록 소관이라 빼야 한다")
    return TeamAnalysis(team=name, is_home=None,
                        time_context=tc_axis,
                        chance_quality=_axis("chance_quality", cq),
                        defensive_quality=_axis("defensive_quality", dq))


def _match(*, season_only: bool = False, analysis: bool = True) -> Match:
    m = Match(no=1,
              home=TeamRef(display="홈팀", canonical="Home"),
              away=TeamRef(display="원정팀", canonical="Away"))
    if analysis:
        away = _team("Away", season_only=season_only)
        # 한쪽만 값이 있는 경우를 만든다 — 상대 슛맵을 못 이은 팀이 실제로
        # 이렇게 된다. 그 칸은 0 이 아니라 `—` 여야 한다 (§1-5).
        away.time_context.metrics.pop(f"{SEASON}.goal_diff", None)
        m.analysis = MatchAnalysis(home=_team("Home", season_only=season_only),
                                   away=away)
    return m


def _html(**kw) -> str:
    """두 블록(시즌·최근)을 이어 붙인 것. 카드에서는 각자의 차트 뒤에 놓인다."""
    season, recent = render._axes_blocks(_match(**kw))
    return season + recent


def _season_html(**kw) -> str:
    return render._axes_blocks(_match(**kw))[0]


def _recent_html(**kw) -> str:
    return render._axes_blocks(_match(**kw))[1]


# ---------------------------------------------------------------- 기본 동작
def test_a1_block_is_rendered_when_axes_exist():
    html = _html()
    assert "경기력 분석" in html, html[:200]


def test_a2_no_analysis_means_no_block():
    """--demo 이전 · 수집 실패 시 빈 블록을 만들지 않는다."""
    assert render._axes_blocks(_match(analysis=False)) == ("", "")


def test_a3_all_three_axes_appear():
    html = _html()
    for title in ("결과", "공격", "수비"):
        assert title in html, title


def test_a4_defensive_axis_is_present():
    """2-C 는 28/28팀 만들어지고도 화면에 없었다. 그것이 이 작업의 이유다."""
    html = _html()
    assert "피슈팅" in html, html
    assert "피npxG" in html, html


def test_a5_both_team_names_in_header():
    html = _html()
    assert "홈팀" in html and "원정팀" in html


# ---------------------------------------------------------------- 표본 표기
def test_b1_sample_counts_are_shown():
    html = _html()
    assert "n=20" in html, "시즌 표본이 안 보인다"
    assert "n=4" in html, "지표별 표본이 안 보인다"


def test_b2_sample_count_is_per_metric_not_per_window():
    """같은 창 안에서도 지표마다 표본이 다르다 (§1-1-2)."""
    html = _html()
    assert "n=6" in html and "n=4" in html and "n=5" in html, html


def test_b3_missing_value_shows_dash_not_zero():
    html = _html()
    assert "nodata" in html
    assert re.search(r'class="nodata">—<', html), "빈 값이 — 로 표시되지 않는다"


# ---------------------------------------------------------------- 기간 처리
def test_c1_two_periods_give_two_columns_each():
    html = _html()
    assert "최근 6" in html, html
    assert html.count("시즌") >= 3


def test_c2_empty_period_column_is_dropped():
    """`—` 만 채운 열은 자리만 차지하고 '재 봤는데 없다' 처럼 보인다."""
    html = _html(season_only=True)
    # 블록 제목·설명에도 '최근' 이 들어 있으므로 표 머리글만 본다.
    heads = re.findall(r"<thead>.*?</thead>", html, re.S)
    assert heads, html
    for head in heads:
        assert "최근" not in head, head
        assert "nodata" not in head, head


def test_c3_period_is_named_in_the_table_head():
    """표마다 어느 기간인지 머리글에 적는다 — 표를 나눴으므로 필수다."""
    html = _html()
    heads = re.findall(r"<thead>.*?</thead>", html, re.S)
    assert heads, html
    for head in heads:
        assert ("시즌" in head) or ("최근" in head), head
    assert 'rowspan' not in html, html


def test_c3b_periods_are_separate_tables():
    """한 표에 시즌과 최근을 나란히 두지 않는다 (§1-1-9 — 빼면 안 되는 값이다)."""
    html = _html()
    heads = re.findall(r"<thead>.*?</thead>", html, re.S)
    for head in heads:
        assert not ("시즌" in head and "최근" in head), head


def test_c4_season_only_metric_still_shows():
    html = _html(season_only=True)
    assert "승점" in html and "슈팅" in html


def test_c5_recent_only_metric_shows_in_two_period_table():
    """시즌에 없는 지표(npxG)도 최근 열이 있으면 나온다."""
    html = _html()
    assert "npxG" in html, html


# ------------------------------------------------------- 시즌 대비 (트렌드)
def test_t1_trend_is_shown_next_to_the_recent_value():
    """2-A 가 계산한 트렌드가 지금까지 화면에 없었다."""
    html = _html()
    assert "시즌 대비" in html, html


def test_t2_trend_band_is_worded_not_scored():
    html = _html()
    assert "높음" in html and "낮음" in html, html
    for word in ("상승세", "전력", "우세", "점수"):
        assert word not in html, word


def test_t3_trend_keeps_its_sign():
    html = _html()
    assert "+0.20" in html, html
    assert "-0.35" in html, html


def test_t4_trend_only_on_the_recent_table():
    """시즌 표에는 붙지 않는다 — 시즌 대비의 기준이 시즌 자신이 된다."""
    html = _html()
    for tm in re.finditer(r"<table class=\"mini\">(.*?)</table>", html, re.S):
        t = tm.group(1)
        if "· 시즌" in t.split("</thead>")[0]:
            assert "시즌 대비" not in t, t


def test_t5_metric_without_trend_gets_no_tail():
    """뺄 수 없는 지표(xG 등)에는 붙지 않는다 (§1-1-9)."""
    html = _html()
    row = re.search(r"<tr><td>xG</td>(.*?)</tr>", html, re.S)
    assert row and "시즌 대비" not in row.group(1), row


def test_t6_reasons_are_shown_once():
    html = _html()
    assert "표본·수집 메모" in html, html
    assert html.count("산출 방식이 달라 뺄 수 없음") == 1, "팀마다 반복되면 안 된다"


def test_t7_pattern_notes_belong_to_another_block():
    html = _html()
    assert "패턴 A" not in html, html


def test_t8_no_reasons_no_section():
    html = _html(season_only=True)
    assert "표본·수집 메모" not in html, html


# ---------------------------------------------------------------- 표시 규칙
def test_d1_signed_metrics_keep_their_sign():
    html = _html()
    assert "+1.20" in html, "양수 득실차에 부호가 없다"
    assert "-0.50" in html, "음수 득실차가 사라졌다"


def test_d2_percent_metric_is_labelled():
    assert "유효슈팅 비율 (%)" in _html()


def test_d3_per_shot_metric_keeps_three_decimals():
    html = _html()
    assert "0.121" in html, html


def test_d4_labels_come_from_specs_not_retyped():
    """라벨을 render 에 다시 적으면 analysis 와 어긋난다."""
    from toto import analysis as A
    src = Path(render.__file__).read_text(encoding="utf-8")
    block = src[src.index("_AXES_SECTIONS"):src.index("_VENUE_ROWS")]
    for name in ("npxga_per_shot_against", "on_target_rate", "goals_minus_xg"):
        assert A.SPECS[name][0] not in block, f"{name} 라벨이 render 에 박혔다"


# ---------------------------------------------------------------- 금지 사항
def test_e1_no_pick_wording():
    html = _html()
    for word in ("추천", "유력", "우세", "승리 예상"):
        if word == "추천":
            assert "추천하지 않습니다" in html or word not in html
            continue
        assert word not in html, word


def test_e2_block_does_not_compute():
    """읽어서 놓기만 한다 — 산술 연산도 합산도 없다."""
    src = Path(render.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    targets = {"_axes_blocks", "_axes_table", "_axis_label_fmt",
               "_axes_notes"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in targets:
            for n in ast.walk(node):
                assert not isinstance(n, ast.BinOp) or isinstance(
                    n.op, (ast.Mod, ast.Add, ast.Mult)), \
                    f"{node.name} 에 산술 연산이 있다"
                if isinstance(n, ast.Call) and getattr(n.func, "id", "") in (
                        "sum", "mean", "round", "abs"):
                    raise AssertionError(f"{node.name} 에 {n.func.id}() 가 있다")


def test_e3_no_new_external_reference():
    html = _html()
    for bad in ("http://", "https://", "<script", "<iframe", "url("):
        assert bad not in html, bad


def test_e4_no_new_css_class():
    """기존 CSS 만 쓴다 — .tablewrap · table.mini · .num · .nodata · .meta."""
    html = _html()
    classes = set(re.findall(r'class="([^"]+)"', html))
    allowed = {"block", "meta", "tablewrap", "mini", "num", "nodata", "mnotes"}
    for c in classes:
        for token in c.split():
            assert token in allowed, f"새 CSS 클래스: {token}"


# ------------------------------------------------- 메모 (2-E 와 공용 헬퍼)
def test_n1_notes_helper_is_shared_with_the_venue_block():
    """§1-8 — 같은 일을 하는 코드를 두 벌 만들지 않는다."""
    src = Path(render.__file__).read_text(encoding="utf-8")
    assert src.count("def _axis_notes(") == 1, "메모 헬퍼가 둘이다"
    venue = src[src.index("def _venue_block"):]
    venue = venue[:venue.index("\n_SOS_ROWS")]
    assert "_axis_notes(" in venue, "장소 블록이 메모를 보여 주지 않는다"


def test_n2_markdown_markers_are_stripped_not_interpreted():
    """축 메모의 `**…**` 가 별표로 새어 나오면 안 된다.

    그렇다고 굵게 만들지도 않는다 — markdown 을 해석하기 시작하면 §1-11 의
    '모델 문장을 해석하지 않는다' 와 어긋나는 선례가 된다.
    """
    m = _match()
    axis = m.analysis.home.time_context
    axis.notes.append("이것은 **강조** 문구입니다")
    html = render._axis_notes((m.analysis.home,), ("time_context",))
    assert "**" not in html, html
    assert "<b>" not in html, html
    assert "이것은 강조 문구입니다" in html, html


def test_n3_pattern_notes_stay_out_of_the_memo():
    m = _match()
    m.analysis.home.time_context.notes.append("패턴 B — 다른 블록 소관")
    html = render._axis_notes((m.analysis.home,), ("time_context",))
    assert "패턴 B" not in html, html


# ---------------------------------------------------------------- 구조
def test_f1_html_is_well_formed():
    # 두 블록을 이어 붙였으므로 뿌리가 둘이다. 감싸서 검사한다.
    ElementTree.fromstring(f"<div>{_html()}</div>")
    for part in (_season_html(), _recent_html()):
        if part:
            ElementTree.fromstring(part)


def test_f2_wide_table_can_scroll():
    """폰에서 가로 스크롤이 되어야 한다 (§1-8)."""
    assert 'class="tablewrap"' in _html()


def test_f3_each_table_sits_next_to_its_chart():
    """차트와 그 표가 떨어져 있으면 같은 지표를 두 곳에서 따로 읽게 된다.

    시즌 표는 다이버징 바 뒤, 최근 표는 슈팅·xG 프로필 뒤여야 한다.
    """
    src = Path(render.__file__).read_text(encoding="utf-8")
    card = src[src.index("def _match_card"):]
    card = card[:card.index("\ndef ", 10)]
    for name in ("season_axes", "recent_axes"):
        assert name in card, f"카드에 {name} 가 없다"
    # 대입문이 아니라 카드에 **끼워 넣은 자리**를 본다.
    order = [card.index(x) for x in ("_compare_inner", "{season_axes}",
                                     "_recent_block(match, settings)",
                                     "{recent_axes}",
                                     "_traits_block", "_venue_block")]
    assert order == sorted(order), order


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
