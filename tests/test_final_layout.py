"""최종 정보 구조 — 레이더 · 직접 비교 · 시장 · 회차 카드 (Phase 4-E).

4-E 도 **새 분석이 아니다.** 4-D 가 위계를 세웠다면 여기서는 각 시각화가
**서로 다른 질문**에 답하도록 자리와 모양을 정한다.

    레이더        이 팀은 자기 리그에서 어디쯤인가?
    직접 비교      이번 두 팀은 같은 조건의 실제 수치로 어떻게 다른가?
    시장 기준선    외부 시장은 이 경기를 어떤 가격 구조로 보는가?
    패널          같은 자료를 본 두 분석가는 어떻게 해석했는가?

고정하려는 것.

1. **레이더는 리그 상대 위치다.** 합성 점수를 만들지 않고 기존
   `analyze.percentile()` 을 그대로 쓴다.
2. **장소 축은 이 경기의 장소를 본다.** 홈팀은 홈 성적, 원정팀은 원정 성적.
3. **직접 비교는 위치이지 길이가 아니다.** 줄마다 눈금이 따로다.
4. **시장은 Pinnacle 이라고 이름을 밝히고, 어느 방향으로도 편향을 만들지
   않는다** — 추종도 반시장도 금지다.
5. **회차 카드는 스코어만 적고 승/무/패 라벨을 만들지 않는다.**

pytest 없이도 돈다:  python tests/test_final_layout.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import (analyze, charts, fixtures, match_material,       # noqa: E402
                  moderator, panel, render)
from toto.analyze import run_all                                   # noqa: E402
from toto.models import Report                                     # noqa: E402
from toto.settings import Settings                                 # noqa: E402
from test_panel_render import MARKET, full_run, mod                # noqa: E402

VENUE = "venue_points_pg"


def _demo():
    matches = fixtures.build_demo_matches()
    s = Settings()
    run_all(matches, s, season_matches=[])
    return matches, s


def _text(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def _axis(match, key):
    return next((a for a in (match.radar or {}).get("axes") or []
                 if a["key"] == key), None)


# --------------------------------------------------------------------------
# A. 레이더 — 리그 안에서 어디쯤인가
# --------------------------------------------------------------------------
def test_a1_axis_count_is_within_the_readable_range():
    """§16 — 6~8축. 너무 많으면 못 읽고 너무 적으면 프로필이 안 된다."""
    matches, _s = _demo()
    for m in matches:
        n = len((m.radar or {}).get("axes") or [])
        assert 6 <= n <= 8, f"{m.no}번 축 {n}개"


def test_a2_every_axis_has_both_teams_in_the_demo():
    """빈 축을 '실제 시즌에는 채워질 것' 이라며 남겨 두지 않는다 (§58)."""
    matches, _s = _demo()
    for m in matches:
        for ax in m.radar["axes"]:
            assert ax["home_pct"] is not None and ax["away_pct"] is not None, \
                f"{m.no}번 {ax['label']}"


def test_a3_venue_axis_reads_each_team_where_it_actually_plays():
    """§17 — 예전에는 `홈 승점`·`원정 승점` 축 각각의 절반이 이 경기와
    무관했다. 레이더는 두 팀을 같은 축에 겹치므로, 원정팀의 홈 성적과
    홈팀의 원정 성적은 이 경기에서 쓸 자리가 없다.
    """
    matches, _s = _demo()
    m = matches[0]
    ax = _axis(m, VENUE)
    assert ax is not None, "장소 축이 없다"
    assert ax["home_value"] == m.home_profile.stats.home_points_pg
    assert ax["away_value"] == m.away_profile.stats.away_points_pg
    # 없어진 두 축이 되살아나지 않았는지.
    for gone in ("home_points_pg", "away_points_pg"):
        assert _axis(m, gone) is None, gone


def test_a4_each_side_is_ranked_against_its_own_population():
    """홈 성적은 리그의 **홈 성적 분포**에서, 원정은 원정 분포에서 잰다.

    두 분포를 한 모집단에 섞으면 홈 성적이 통째로 위로, 원정이 아래로
    쏠린다 (홈 이점이 분포에 들어 있다).
    """
    matches, _s = _demo()
    m = matches[0]
    ax = _axis(m, VENUE)
    same_league = [p for mm in matches if mm.league == m.league
                   for p in (mm.home_profile, mm.away_profile) if p]
    home_pool = [p.stats.home_points_pg for p in same_league
                 if p.stats.home_points_pg is not None]
    away_pool = [p.stats.away_points_pg for p in same_league
                 if p.stats.away_points_pg is not None]
    assert ax["home_pct"] == analyze.percentile(ax["home_value"], home_pool)
    assert ax["away_pct"] == analyze.percentile(ax["away_value"], away_pool)
    # 섞은 모집단으로 재면 다른 값이 나온다 — 그게 이 테스트의 요점이다.
    assert ax["home_pct"] != analyze.percentile(ax["home_value"],
                                                home_pool + away_pool)


def test_a5_normal_axes_use_one_key_for_both_sides():
    for metric in Settings().radar_metrics:
        home_key, away_key = analyze._radar_keys(metric)
        if metric.get("key") == VENUE:
            assert home_key != away_key, "장소 축은 쪽마다 달라야 한다"
        else:
            assert home_key == away_key == metric["key"], metric


def test_a6_defence_axes_are_inverted_so_higher_is_better():
    """§18 — 시각적 방향을 통일한다. 피xG·실점은 적을수록 바깥쪽."""
    matches, _s = _demo()
    for m in matches:
        for key in ("xga_pg", "goals_against_pg"):
            ax = _axis(m, key)
            assert ax is not None and ax["invert"] is True, key
            # 값이 작은 쪽이 백분위가 높아야 한다.
            if ax["home_value"] != ax["away_value"]:
                low_is_home = ax["home_value"] < ax["away_value"]
                assert (ax["home_pct"] > ax["away_pct"]) == low_is_home, key


def test_a7_attack_defence_balance():
    """§17 — 결과 계열 셋 · 수비 하나였던 균형을 다시 맞춘다."""
    keys = [m.get("key") for m in Settings().radar_metrics]
    defence = [k for k in keys if k in ("xga_pg", "goals_against_pg")]
    assert len(defence) >= 2, f"수비 축이 모자란다: {keys}"
    assert keys.count("home_points_pg") == 0 and keys.count("away_points_pg") == 0


def test_a8_missing_metric_drops_the_axis_instead_of_scoring_zero():
    matches, s = _demo()
    for m in matches:
        for p in (m.home_profile, m.away_profile):
            p.stats.possession = None
    analyze.build_radar(matches, s)
    for m in matches:
        assert _axis(m, "possession") is None, "빈 축을 0 으로 그렸다"
        assert len(m.radar["axes"]) >= 6


def test_a9_radar_makes_no_composite_score():
    """§13 — overall_strength · team_rating 같은 값을 만들지 않는다."""
    src = Path(analyze.__file__).read_text(encoding="utf-8")
    for banned in ("overall_strength", "attack_score", "defense_score",
                   "team_rating", "strength_score", "composite"):
        assert banned not in src, banned


def test_a10_tooltip_names_the_metric_each_side_actually_shows():
    """§60 — 장소 축은 두 팀이 다른 지표를 본다. 축 이름만 적으면 같은
    값을 견준 것처럼 보인다.
    """
    matches, _s = _demo()
    svg = charts.radar(matches[0].radar["axes"], "홈팀", "원정팀")
    assert "홈 경기 승점" in svg and "원정 경기 승점" in svg, svg[:400]


# --------------------------------------------------------------------------
# B. 직접 비교 — 위치이지 길이가 아니다
# --------------------------------------------------------------------------
ROWS = [{"label": "승점", "home": 1.82, "away": 0.72, "fmt": "{:.2f}"},
        {"label": "실점", "home": 0.93, "away": 1.40, "fmt": "{:.2f}",
         "lower_better": True}]


def test_b1_actual_values_are_printed_not_only_drawn():
    svg = charts.dumbbell(ROWS, "홈팀", "원정팀")
    for v in ("1.82", "0.72", "0.93", "1.40"):
        assert v in svg, v


def test_b2_each_row_has_its_own_scale():
    """§23 — 단위가 다른 지표를 한 눈금에 올리면 줄끼리 견줄 수 있는
    것처럼 보인다. 줄마다 큰 값이 오른쪽 끝에 온다.
    """
    svg = charts.dumbbell(
        [{"label": "슈팅", "home": 18.0, "away": 4.0, "fmt": "{:.1f}"},
         {"label": "xG", "home": 0.4, "away": 1.9, "fmt": "{:.2f}"}],
        "홈팀", "원정팀")
    xs = [float(x) for x in re.findall(r'<circle cx="([\d.]+)"', svg)]
    # 줄마다 (원정, 홈) 두 점. 각 줄의 큰 값이 같은 x 에 놓인다.
    assert max(xs[0], xs[1]) == max(xs[2], xs[3]), xs


def test_b3_zero_is_the_left_edge_so_the_gap_is_readable():
    svg = charts.dumbbell(
        [{"label": "승점", "home": 2.0, "away": 1.0, "fmt": "{:.1f}"}],
        "홈팀", "원정팀")
    xs = [float(x) for x in re.findall(r'<circle cx="([\d.]+)"', svg)]
    away_x, home_x = xs           # 원정 점을 먼저 그린다
    track = re.search(r'<line x1="([\d.]+)"[^/]*?x2="([\d.]+)"', svg)
    left, right = float(track.group(1)), float(track.group(2))
    # 1.0 은 0 과 2.0 의 한가운데다.
    assert abs(away_x - (left + right) / 2) < 0.6, (away_x, left, right)
    assert abs(home_x - right) < 0.6, (home_x, right)


def test_b3b_each_value_is_printed_beside_its_own_point():
    """처음에는 값을 왼쪽·오른쪽 **고정 칸**에 적었다. 점은 값에 따라
    움직이므로 큰 값의 숫자가 작은 값의 점 옆에 놓였고, 화면에서 두 숫자가
    서로 뒤바뀐 것처럼 보였다 — 스크린샷을 보고 잡았다.
    """
    svg = charts.dumbbell(
        [{"label": "승점", "home": 1.82, "away": 0.82, "fmt": "{:.2f}"}],
        "홈팀", "원정팀")
    home_x = float(re.search(r'<circle cx="([\d.]+)"[^>]*fill="var\(--home\)"',
                             svg).group(1))
    away_x = float(re.search(r'<circle cx="([\d.]+)"[^>]*stroke="var\(--away\)"',
                             svg).group(1))
    spots = {t: float(x) for x, t in
             re.findall(r'<text x="([\d.-]+)"[^>]*>([\d.]+)</text>', svg)}
    assert abs(spots["1.82"] - home_x) < 14, (spots, home_x)
    assert abs(spots["0.82"] - away_x) < 14, (spots, away_x)
    # 큰 값이 오른쪽 점이므로 그 숫자도 오른쪽에 있어야 한다.
    assert spots["1.82"] > spots["0.82"]


def test_b4_two_teams_are_distinguishable_without_colour():
    """§45 — 색에만 기대지 않는다. 홈은 채운 점, 원정은 속 빈 점."""
    svg = charts.dumbbell(ROWS, "홈팀", "원정팀")
    assert 'fill="var(--home)"' in svg
    assert 'stroke="var(--away)"' in svg and 'fill="var(--surface-1)"' in svg
    assert "채운 점" in svg and "속 빈 점" in svg


def test_b5_one_sided_rows_are_dropped():
    svg = charts.dumbbell(
        [{"label": "승점", "home": 1.8, "away": None, "fmt": "{:.1f}"}],
        "홈팀", "원정팀")
    assert "<svg" not in svg, "한쪽만 있는 줄을 그렸다"
    assert "직접 견줄 수 있는 지표가 없습니다" in svg


def test_b6_direction_is_a_label_not_a_verdict():
    svg = charts.dumbbell(ROWS, "홈팀", "원정팀")
    assert "실점 ↓" in svg
    text = _text(svg)
    for banned in ("우위", "우세", "낫다", "유리"):
        assert banned not in text, banned


def test_b7_equal_values_still_show_both_points():
    svg = charts.dumbbell(
        [{"label": "승점", "home": 1.5, "away": 1.5, "fmt": "{:.1f}"}],
        "홈팀", "원정팀")
    assert len(re.findall(r"<circle", svg)) == 2, "두 점이 겹쳐 하나가 됐다"


def test_b8_dumbbell_is_well_formed():
    svg = charts.dumbbell(ROWS, "홈<팀>", "원정&팀")
    ElementTree.fromstring(re.search(r"<svg.*</svg>", svg, re.S).group(0))
    assert "<팀>" not in svg, "팀 이름을 escape 하지 않았다"


# --------------------------------------------------------------------------
# C. Pinnacle 시장 기준선
# --------------------------------------------------------------------------
def test_c1_market_is_named_in_the_ui():
    """§6 — '시장' 이 아니라 어느 시장인지 밝힌다."""
    assert "Pinnacle 시장 기준선" in render._market_table(MARKET)
    assert "Pinnacle 시장 기준선" in render._market_table(None)


def test_c2_market_is_not_called_a_strong_or_authoritative_baseline():
    """§6 — '강한 기준선'·'가장 신뢰할 수 있는'·'정답' 같은 말을 쓰지 않는다."""
    html = render._market_table(MARKET)
    for banned in ("강한 기준", "가장 신뢰", "정답", "시장 우선",
                   "가장 정확", "우선합니다"):
        assert banned not in html, banned
    assert "분석가가 아닙니다" in html


def test_c3_market_reference_carries_no_selection():
    """불변조건 1 — 시장의 '선택' 을 실으면 세 번째 분석가가 된다."""
    fields = set(MARKET.__dataclass_fields__)
    for banned in ("pick", "p_pick", "favorite", "toss_up", "lean",
                   "weight", "confidence"):
        assert banned not in fields, banned


def test_c4_analysts_are_told_market_bias_runs_both_ways():
    """§5-3 — 예전에는 **시장 추종만** 막혀 있었다. '시장과 달라야 의미가
    있다' 는 반대쪽 편향은 열려 있었고, 그쪽이 더 그럴듯해 보인다.
    """
    src = panel.SYSTEM_COMMON
    assert "그쪽으로 해석하지 마십시오" in src, "시장 추종 금지가 없다"
    assert "반대쪽으로 해석하지도 마십시오" in src, "반시장 편향 금지가 없다"
    assert "우위에 있지 않고" in src and "열위에 있지도 않습니다" in src


def test_c5_moderator_is_told_the_same():
    src = moderator.SYSTEM
    assert "시장 확률이 어느 쪽에 가깝다는 이유로 고르지 마십시오" in src
    assert "시장에서 먼 쪽을 고르지 마십시오" in src, "반시장 편향 금지가 없다"


def test_c6_both_analysts_receive_the_market():
    """§5-2 — 두 분석가 모두 참고할 수 있어야 한다. 같은 자료이므로
    역할별로 골라 주지 않는다 (3-B 불변조건 2).
    """
    assert "market_reference" in panel.PanelPayload.__dataclass_fields__
    src = panel.ROLE_PROMPTS[panel.DATA_ANALYST]
    assert "참고할 수는 있지만" in src, "데이터 분석가에게 시장을 막아 두었다"


def test_c7_market_is_in_the_chat_material():
    """§F-1 — 채팅 경로(경기자료 MD)에도 실려 있어야 한다."""
    src = Path(match_material.__file__).read_text(encoding="utf-8")
    assert "def _market(" in src
    assert "내재확률 (마진 제거)" in src
    assert "추천이나 favorite 를 만들지 마십시오" in src


def test_c8_no_market_derived_score_anywhere_in_render():
    src = Path(render.__file__).read_text(encoding="utf-8")
    for banned in ("market_confidence", "market_weight", "market_adjusted",
                   "market_score", "market_strength", "market_accuracy"):
        assert banned not in src, banned


# --------------------------------------------------------------------------
# D. 회차 요약 카드
# --------------------------------------------------------------------------
def test_c9_missing_tactical_data_is_stated_not_invented():
    """§44 — 없으면 없다고 적고, 포메이션·선발·부상을 추정해 채우지 않는다."""
    matches, _s = _demo()
    m = matches[0]
    for p in (m.home_profile, m.away_profile):
        p.strengths, p.weaknesses, p.style_of_play = [], [], []
    html = render._decision_summary(m)
    assert "전술 정성 자료" in html and "미수집" in html
    for banned in ("포메이션 4-", "선발 명단", "부상자 명단", "압박 방식"):
        assert banned not in html, banned


def test_d1_panel_score_appears_on_the_round_card():
    matches, _s = _demo()
    matches[0].panel = full_run()
    html = render._summary_grid(matches)
    # Phase 4-G 에서 카드의 중심이 시장 확률 → 종합 예상 스코어로 바뀌었다.
    # 묻는 것은 그대로다: 사회자가 채택한 스코어가 카드에 나오는가.
    assert "종합 예상 스코어" in html and "2 - 1" in html


def test_d2_no_panel_no_panel_line():
    matches, _s = _demo()
    assert "Panel 종합" not in render._summary_grid(matches)


def test_d3_round_card_never_labels_a_result():
    """§40 — `2 : 0` 을 보고 '홈승' 이라 읽는 것은 사용자의 판단이다.
    프로그램이 그 낱말을 먼저 적으면 그 순간 추천이 된다.
    """
    matches, _s = _demo()
    for m in matches:
        m.panel = full_run()
    text = _text(render._summary_grid(matches))
    for banned in ("홈승", "원정승", "무승부 예상", "추천", "유력",
                   "confidence", "strength"):
        assert banned not in text, banned


def test_d4_panel_without_adopted_score_says_so():
    matches, _s = _demo()
    matches[0].panel = full_run(moderator=mod(
        adopted_home=None, adopted_away=None, adopted_from=()))
    html = render._summary_grid(matches)
    assert "예상 스코어 없음" in html
    assert "0 : 0" not in html and "0 - 0" not in html


# --------------------------------------------------------------------------
# E. 전체 리포트
# --------------------------------------------------------------------------
def _report_html(with_panel: bool = False) -> str:
    matches, s = _demo()
    if with_panel:
        for m in matches:
            m.panel = full_run()
    return render.render_report(
        Report(round_id="DEMO", generated_at="fixed", matches=matches), s)


def test_e1_section_order_is_summary_compare_panel_detail():
    html = _report_html(with_panel=True)
    card = html[html.index('id="m1"'):html.index('id="m2"')]
    order = [card.index(x) for x in
             ("Pinnacle 시장 기준선", "요약 — 이 경기에서 지금까지 나온 것",
              "리그 내 위치", "홈 ↔ 원정 직접 비교", "패널 분석",
              "토론 시뮬레이션", "최근 경기 슈팅", "상대전적")]
    assert order == sorted(order), order


def test_e2_report_is_self_contained():
    html = _report_html(with_panel=True)
    for bad in ("http://", "https://", "<script src", "<iframe", "url("):
        assert bad not in html, bad


def test_e3_every_svg_is_well_formed():
    html = _report_html(with_panel=True)
    svgs = re.findall(r"<svg.*?</svg>", html, re.S)
    assert len(svgs) > 100, len(svgs)
    for svg in svgs:
        ElementTree.fromstring(svg)


def test_e4_no_wdl_verdict_anywhere_in_the_summary_layers():
    html = _report_html(with_panel=True)
    card = html[html.index('id="m1"'):html.index('id="m2"')]
    text = _text(card[:card.index("패널 분석")])
    for banned in ("홈승", "원정승", "승리 예상", "AI Pick", "consensus",
                   "strength score", "panel confidence"):
        assert banned not in text, banned


def test_e5_detail_sections_are_not_deleted():
    """§61 — 상단을 요약 계층으로 만들되 검증 계층을 지우지 않는다."""
    html = _report_html()
    for token in ("경기력 분석 · 시즌", "최근 경기 슈팅·xG 프로필",
                  "전략적 상성", "최근 5경기 폼"):
        assert token in html, token


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
