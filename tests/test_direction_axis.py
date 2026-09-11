"""지표 방향 메타데이터와 직접 비교 축 (Phase 5-D).

실물 260052 리포트를 보고 고친 셋이다. **값은 한 자리도 바뀌지 않는다** —
바뀐 것은 어디에 무엇을 그리느냐뿐이다.

1. **카드 안의 요약 사본을 걷었다.** `요약 — 이 경기에서 지금까지 나온 것`
   은 아래 블록의 끝값을 옮겨 적던 자리라, 같은 수가 한 카드에서 두 번
   읽혔다. 사본만 지웠고 원본 네 자리는 그대로다.
2. **백분위 칸의 `상위` 를 걷었다.** 한 화면에 열여섯 번 반복되면서 정작
   숫자가 안 보였다. 무엇을 재는 값인지는 블록 설명이 한 번 말한다.
3. **낮을수록 좋은 지표는 직접 비교 축을 뒤집는다.** 예전에는 실점 1.67 인
   팀이 1.00 인 팀보다 **오른쪽**에 찍혔다 — 화면은 "오른쪽이 크다" 만
   말하는데 사람은 그것을 "오른쪽이 낫다" 로 읽는다.

이 파일이 고정하려는 것은 다섯이다.

  · **방향은 지표 카탈로그가 정한다.** `analysis.SPECS` 의 방향 칸 하나가
    근거이고, 라벨의 `↓` 는 거기서 **파생된 표시**다. 이름으로 분기하거나
    (`if metric == "실점"`) `↓` 를 되읽어 방향을 정하지 않는다.
  · **뒤집는 것은 x 좌표 하나뿐이다.** `1/x`·`max−v` 같은 변환값을 만들거나
    보여 주지 않는다.
  · **마커·연결선·값 라벨·툴팁이 함께 움직인다.** 한 줄을 뒤집으면 그 줄의
    좌표 전부가 거울처럼 뒤집힌다 — 마커만 반전시키고 선을 두면 어긋난다.
  · **레이더는 그대로다.** 이 방향 메타데이터는 직접 비교에만 닿는다.
  · **지운 것은 사본이고 원본은 제자리에 있다.**

pytest 없이도 돈다:  python tests/test_direction_axis.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import analysis, charts, fixtures, render                # noqa: E402
from toto.analyze import run_all                                   # noqa: E402
from toto.models import Report                                     # noqa: E402
from toto.settings import Settings                                 # noqa: E402
from test_axes_render import _match                                # noqa: E402
from test_panel_render import full_run                             # noqa: E402

GONE = "요약 — 이 경기에서 지금까지 나온 것"


def _demo():
    matches = fixtures.build_demo_matches()
    s = Settings()
    run_all(matches, s, season_matches=[])
    return matches, s


def _report_html(with_panel: bool = True) -> str:
    matches, s = _demo()
    if with_panel:
        for m in matches:
            m.panel = full_run()
    return render.render_report(
        Report(round_id="DEMO", generated_at="fixed", matches=matches), s)


def _text(html: str) -> str:
    """화면에 실제로 보이는 글자만 (태그 속성값을 검사에서 뺀다)."""
    return re.sub(r"<[^>]+>", " ", html)


def _row(label: str, home: float, away: float, lower: bool) -> dict:
    return {"label": label, "home": home, "away": away,
            "fmt": "{:.2f}", "lower_better": lower}


def _circles(svg: str) -> dict[str, float]:
    """홈(채운 점) · 원정(속 빈 점)의 cx. 색으로 가른다."""
    out = {}
    for cx, fill in re.findall(r'<circle cx="([\d.]+)"[^>]*?fill="([^"]+)"',
                               svg):
        out["home" if fill == charts.C_HOME else "away"] = float(cx)
    return out


# --------------------------------------------------------------------------
# A. 요약 블록 제거 — 사본만 지웠다
# --------------------------------------------------------------------------
def test_a1_the_summary_copy_is_gone_from_the_report():
    """§20-A — 회차 전체 리포트 어디에도 그 제목이 없다."""
    assert GONE not in _report_html()
    assert GONE not in _report_html(with_panel=False)


def test_a2_the_originals_are_still_in_the_card():
    """§20-A — 사라진 것은 사본이고 원본은 제자리에 있다.

    요약이 옮겨 적던 것은 넷이었다 — 시장 확률 · 패널 스코어 · 축 지표 ·
    근거 개수. 네 자리가 전부 살아 있는지 본다.
    """
    m = _match()
    m.panel = full_run()
    card = render._match_card(m, Settings(), None)
    assert GONE not in card
    for must in ("Pinnacle 시장 기준선",       # 시장 원본
                 "패널 분석",                  # 패널 원본
                 "경기력 분석",                # 축 원본
                 "홈 ↔ 원정 직접 비교"):
        assert must in card, must


def test_a3_render_has_no_summary_function_left_behind():
    """죽은 함수를 남겨 두지 않는다 — 다음 사람이 다시 부른다."""
    src = Path(render.__file__).read_text(encoding="utf-8")
    assert "def _decision_summary" not in src
    assert "_decision_summary(" not in src


def test_a4_no_orphan_css_for_the_removed_block():
    """전용 CSS 가 남아 있으면 블록이 아직 있는 것처럼 읽힌다."""
    src = Path(render.__file__).read_text(encoding="utf-8")
    for banned in (".dsum", ".decision-summary", ".sumline"):
        assert banned not in src, banned


# --------------------------------------------------------------------------
# B. 백분위 표기 — 값 칸의 `상위` 만 걷는다
# --------------------------------------------------------------------------
def test_b1_percentile_cells_have_no_prefix():
    """§20-B — `상위 97%` 같은 **개별 값**이 남지 않는다."""
    html = _report_html()
    hits = re.findall(r"상위\s*\d+\s*%", html)
    assert not hits, hits[:5]


def test_b2_the_numbers_themselves_are_still_there():
    """§20-B — 걷은 것은 접두사뿐이고 값은 그대로다."""
    matches, _s = _demo()
    table = render._radar_table(matches[0])
    assert re.search(r"\d+%", table), "백분위 값이 사라졌다"
    assert "상위" not in table, "값 칸에 접두사가 남았다"


def test_b3_the_section_explains_what_the_number_means():
    """§20-B — 값 칸에서 뺀 대신 **블록 설명이 한 번** 말해야 한다.

    숫자만 남기고 뜻을 아무 데도 안 적으면 `97%` 가 무엇의 97 인지 알 수
    없다. 걷은 것은 반복이지 의미가 아니다.
    """
    m = _match()
    card = render._match_card(m, Settings(), None)
    assert "리그 내 위치 (리그 백분위)" in card
    assert card.count("상위") >= 1, "값 칸에서 뺀 설명을 어디에도 적지 않았다"


def test_b4_the_prefix_is_gone_from_the_svg_tooltips_too():
    """툴팁에도 같은 반복이 있었다 — 한쪽만 고치면 두 표기가 갈린다."""
    matches, _s = _demo()
    axes = (matches[0].radar or {}).get("axes") or []
    svg = charts.radar(axes, "홈", "원정")
    titles = re.findall(r"<title>(.*?)</title>", svg)
    assert titles, "툴팁이 사라졌다"
    assert not any(re.search(r"상위\s*\d+\s*%", t) for t in titles), titles[:3]
    assert any(re.search(r"\d+%", t) for t in titles), titles[:3]


def test_b5_percentile_values_are_untouched():
    """§23 — 표기만 바꿨다. 계산된 백분위 값은 그대로다."""
    matches, _s = _demo()
    m = matches[0]
    for axis in (m.radar or {}).get("axes") or []:
        for side in ("home_pct", "away_pct"):
            pct = axis.get(side)
            if pct is None:
                continue
            assert 0.0 <= pct <= 100.0, (axis["key"], side, pct)
            assert f"{100 - pct:.0f}%" in render._radar_table(m)


# --------------------------------------------------------------------------
# C. 방향 메타데이터 — 카탈로그 하나가 근거다
# --------------------------------------------------------------------------
def test_c1_every_direct_row_has_an_explicit_direction():
    """§17 — 방향이 불명확한 지표는 임의로 정하지 않는다.

    지금 직접 비교에 올라간 여덟 지표는 전부 카탈로그에 방향이 적혀 있다.
    새 지표를 넣었는데 방향이 비면 이 테스트가 먼저 깨진다.
    """
    for _attr, name in render._DIRECT_ROWS:
        spec = analysis.SPECS.get(name)
        assert spec is not None, name
        assert spec[2] in (analysis.HIGHER_BETTER, analysis.LOWER_BETTER), \
            (name, spec[2])


def test_c2_the_defensive_metrics_are_lower_better():
    """§20-C — 실점·xGA 계열이 `lower_better` 로 등록돼 있다."""
    for name in ("goals_against", "xga", "npxga", "shots_against"):
        assert analysis.SPECS[name][2] == analysis.LOWER_BETTER, name


def test_c3_the_attacking_metrics_stay_higher_better():
    """§20-C — 기존 방향을 뒤집지 않았다."""
    for name in ("points", "goals", "xg", "shots_on_target"):
        assert analysis.SPECS[name][2] == analysis.HIGHER_BETTER, name


def test_c4_the_renderer_reads_the_catalog_not_the_label():
    """§18 — `↓` 는 방향에서 파생된 표시이지 근거가 아니다."""
    src = Path(render.__file__).read_text(encoding="utf-8")
    block = src[src.index("def _direct_compare_block"):
                src.index("_VENUE_ROWS = (")]
    assert "analysis.SPECS.get(name" in block, "카탈로그를 읽지 않는다"
    assert "LOWER_BETTER" in block
    assert '"↓" in' not in block and "'↓' in" not in block


def test_c5_the_arrow_is_derived_from_the_flag():
    """라벨의 `↓` 가 플래그에서 나온다 — 반대가 아니다."""
    on = charts.dumbbell([_row("실점", 1.67, 1.00, True)], "홈", "원정")
    off = charts.dumbbell([_row("실점", 1.67, 1.00, False)], "홈", "원정")
    assert "실점 ↓" in on
    assert "실점 ↓" not in off


# --------------------------------------------------------------------------
# D. 좌표 방향 — 어느 줄이든 오른쪽이 더 좋은 값
# --------------------------------------------------------------------------
def test_d1_higher_better_puts_the_big_value_on_the_right():
    """§20-D — 보통 지표는 왼쪽 0 → 오른쪽 큰 값."""
    svg = charts.dumbbell([_row("득점", 1.67, 1.00, False)], "홈", "원정")
    c = _circles(svg)
    assert c["home"] > c["away"], c


def test_d2_lower_better_puts_the_small_value_on_the_right():
    """§20-D · §11 — 뒤집힌 줄은 작은 값이 오른쪽이다.

    실점 1.00 인 팀이 1.67 인 팀보다 오른쪽에 찍혀야 한다.
    """
    svg = charts.dumbbell([_row("실점", 1.67, 1.00, True)], "홈", "원정")
    c = _circles(svg)
    assert c["away"] > c["home"], c


def test_d3_the_two_directions_are_mirror_images():
    """§13·§14 — 마커만 반전시키고 선·라벨을 두는 구현을 막는다.

    같은 값의 두 줄을 그리면 **모든 x 좌표**가 눈금 한가운데를 기준으로
    서로 거울이어야 한다. 하나라도 따로 계산하면 여기서 깨진다.
    """
    up = charts.dumbbell([_row("실점", 1.67, 1.00, False)], "홈", "원정")
    dn = charts.dumbbell([_row("실점", 1.67, 1.00, True)], "홈", "원정")

    def xs(svg: str) -> list[float]:
        return [float(v) for v in re.findall(r'(?:cx|x1|x2)="([\d.]+)"', svg)]

    a, b = xs(up), xs(dn)
    assert len(a) == len(b) and a, (len(a), len(b))
    total = [x + y for x, y in zip(sorted(a), sorted(b, reverse=True))]
    assert max(total) - min(total) < 0.2, total


def test_d4_a_flat_row_does_not_move():
    """두 값이 같으면 방향과 무관하게 같은 자리에 찍힌다."""
    up = _circles(charts.dumbbell([_row("실점", 1.2, 1.2, False)], "홈", "원"))
    dn = _circles(charts.dumbbell([_row("실점", 1.2, 1.2, True)], "홈", "원"))
    assert abs(up["home"] - up["away"]) < 0.2
    assert abs(dn["home"] - dn["away"]) < 0.2


def test_d5_rows_are_independent():
    """눈금은 줄마다 따로다 — 한 줄을 뒤집어도 다른 줄이 움직이지 않는다."""
    rows = [_row("득점", 2.0, 1.0, False), _row("실점", 1.67, 1.00, True)]
    svg = charts.dumbbell(rows, "홈", "원정")
    cx = [float(v) for v in re.findall(r'<circle cx="([\d.]+)"', svg)]
    # 원정·홈 순으로 그린다 (같은 값일 때 홈이 위로 오게).
    away0, home0, away1, home1 = cx
    assert home0 > away0, "득점 줄이 뒤집혔다"
    assert away1 > home1, "실점 줄이 뒤집히지 않았다"


def test_d6_the_caption_states_both_orientations():
    """§12 — 설명이 한 방향만 말하면 뒤집힌 줄이 오류처럼 보인다."""
    svg = charts.dumbbell([_row("실점", 1.67, 1.00, True)], "홈", "원정")
    assert "축을 반대로" in svg
    assert "오른쪽이 그 지표에서 더 좋은 값" in svg


def test_d7_the_block_header_says_it_too():
    """직접 비교 블록 설명도 같은 말을 한다."""
    html = render._direct_compare_block(_match())
    assert "축을 반대로" in html


# --------------------------------------------------------------------------
# E. 값 보존 — 뒤집은 것은 좌표뿐이다
# --------------------------------------------------------------------------
def test_e1_raw_values_survive_the_reversal():
    """§20-E · §10 — 화면에 적히는 숫자는 그대로다."""
    for lower in (False, True):
        svg = charts.dumbbell([_row("실점", 1.67, 1.00, lower)], "홈", "원정")
        text = _text(svg)
        assert "1.67" in text and "1.00" in text, (lower, text)


def test_e2_no_transformed_number_is_shown():
    """§16 — `1/x`·`max−v` 같은 변환값을 사용자에게 보여 주지 않는다."""
    svg = charts.dumbbell([_row("실점", 1.67, 1.00, True)], "홈", "원정")
    shown = set(re.findall(r"\d+\.\d+", _text(svg)))
    assert shown == {"1.67", "1.00"}, shown


def test_e3_tooltips_carry_the_value_only():
    """§15 — 툴팁에 좌우 방향이나 내부 정규화 점수를 내지 않는다."""
    svg = charts.dumbbell([_row("실점", 1.67, 1.00, True)], "홈", "원정")
    titles = re.findall(r"<title>(.*?)</title>", svg)
    assert titles == ["원정 실점 ↓ 1.00", "홈 실점 ↓ 1.67"], titles
    for banned in ("왼쪽", "오른쪽", "normalized", "score", "frac", "%"):
        assert not any(banned in t for t in titles), banned


def test_e4_the_value_label_sits_next_to_its_own_point():
    """§14 — 라벨이 마커를 따라간다. 고정 칸에 두면 서로 뒤바뀐다."""
    svg = charts.dumbbell([_row("실점", 1.67, 1.00, True)], "홈", "원정")
    labels = {t: float(x) for x, t in
              re.findall(r'<text x="([\d.-]+)"[^>]*font-weight="600"[^>]*>'
                         r"([\d.]+)</text>", svg)}
    c = _circles(svg)
    # 1.67 은 홈 점 곁에, 1.00 은 원정 점 곁에 (9px 바깥으로 민다).
    assert abs(labels["1.67"] - c["home"]) <= 9.5, (labels, c)
    assert abs(labels["1.00"] - c["away"]) <= 9.5, (labels, c)


def test_e5_the_axis_values_in_the_report_are_unchanged():
    """§23 — 축이 담고 있는 수는 한 칸도 바뀌지 않았다."""
    m = _match()
    html = render._direct_compare_block(m)
    data = m.analysis
    seen = 0
    for attr, name in render._DIRECT_ROWS:
        for side in (data.home, data.away):
            axis = getattr(side, attr, None)
            if axis is None:
                continue
            for key, metric in axis.metrics.items():
                if not key.endswith(f".{name}") or metric.value is None:
                    continue
                _label, fmt = render._axis_label_fmt(name)
                if fmt.format(metric.value) in html:
                    seen += 1
    assert seen > 0, "직접 비교에 축의 값이 하나도 안 실렸다"


# --------------------------------------------------------------------------
# F. 레이더 회귀 — 이 방향 메타데이터는 레이더에 닿지 않는다
# --------------------------------------------------------------------------
def test_f1_axis_order_and_percentiles_are_unchanged():
    """§9·§20-F — 축 순서도 백분위도 건드리지 않았다.

    4-E 가 정한 8축(§1-19)이 그대로인지 본다 — 순서까지 고정한다.
    """
    matches, _s = _demo()
    want = ["big_chances_pg", "shots_on_target_pg", "goals_for_pg",
            "xga_pg", "goals_against_pg", "possession",
            "touches_opp_box_pg", "venue_points_pg"]
    for m in matches:
        keys = [a["key"] for a in (m.radar or {}).get("axes") or []]
        assert keys == want, (m.no, keys)


def test_f2_radar_does_not_read_the_direction_flag():
    """§9 — 방향 메타데이터가 레이더 좌표에 흘러들지 않는다."""
    src = Path(charts.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "radar")
    body = ast.get_source_segment(src, fn) or ""
    assert "lower_better" not in body
    assert "LOWER_BETTER" not in body


def test_f3_radar_geometry_is_stable():
    """§20-F — 같은 입력이 같은 좌표를 준다 (baseline 유지)."""
    matches, _s = _demo()
    axes = (matches[0].radar or {}).get("axes") or []
    one = charts.radar(axes, "홈", "원정")
    assert one == charts.radar(axes, "홈", "원정")
    ElementTree.fromstring(re.search(r"<svg.*?</svg>", one, re.S).group(0))
    assert "<polygon" in one, "폴리곤이 사라졌다"


def test_f4_radar_keeps_its_own_arrows():
    """§19 — 레이더의 `↓` 는 `invert` 에서 나온다. 그 표기를 그대로 둔다."""
    matches, _s = _demo()
    axes = (matches[0].radar or {}).get("axes") or []
    inverted = [a["label"] for a in axes if a.get("invert")]
    assert inverted, [a["key"] for a in axes]
    svg = charts.radar(axes, "홈", "원정")
    table = render._radar_table(matches[0])
    for label in inverted:
        assert f"{label}↓" in svg, label
        assert f"{label}↓" in table, label


# --------------------------------------------------------------------------
# G. 지표별 특수 처리 금지
# --------------------------------------------------------------------------
_SOURCES = ("render.py", "charts.py")


def test_g1_no_metric_name_special_cases():
    """§20-G · §25 — 지표 이름으로 분기하지 않는다."""
    root = Path(render.__file__).parent
    for fname in _SOURCES:
        src = (root / fname).read_text(encoding="utf-8")
        for banned in ('== "실점"', "== '실점'", '== "xGA"', "== 'xGA'",
                       '== "goals_against"', '== "xga"', '== "npxga"'):
            assert banned not in src, f"{fname}: {banned}"


def test_g2_no_arrow_parsing_decides_direction():
    """§18 — `↓` 를 되읽어 방향을 정하지 않는다."""
    root = Path(render.__file__).parent
    for fname in _SOURCES:
        src = (root / fname).read_text(encoding="utf-8")
        for banned in ('"↓" in ', "'↓' in ", "endswith(\"↓\")",
                       "startswith(\"↓\")"):
            assert banned not in src, f"{fname}: {banned}"


def test_g3_direction_is_read_in_exactly_one_place():
    """카탈로그를 두 곳에서 읽으면 조용히 갈라진다.

    주석은 세지 않는다 — 세는 것은 **실제로 방향을 판정하는 코드**다.
    """
    src = Path(render.__file__).read_text(encoding="utf-8")
    code = [ln for ln in src.splitlines()
            if "LOWER_BETTER" in ln and not ln.lstrip().startswith("#")]
    assert len(code) == 1, code


def test_g4_the_chart_never_recomputes_a_direction():
    """차트는 플래그를 받을 뿐 스스로 정하지 않는다.

    문서 문자열은 방향의 뜻을 설명해도 되지만, **코드**가 카탈로그를
    들여다보면 판정이 두 곳으로 갈린다.
    """
    src = Path(charts.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "dumbbell")
    code = ast.unparse(ast.Module(body=fn.body[1:], type_ignores=[]))
    for banned in ("SPECS", "analysis", "LOWER_BETTER", "import"):
        assert banned not in code, banned
    assert "lower_better" in code


def test_g5_no_score_is_built_from_the_direction():
    """§25 — 방향을 부호로 써서 합산하거나 우열을 만들지 않는다."""
    src = Path(render.__file__).read_text(encoding="utf-8")
    for banned in ("direction_score", "advantage_score", "edge_score",
                   "better_count", "wins_row"):
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
