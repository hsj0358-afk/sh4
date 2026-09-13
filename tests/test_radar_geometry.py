"""레이더 기하 회귀 테스트 (Phase 5-D1).

5-D 보고에 **레이더 라벨이 7.7px 잘린다**고 적었다. 그건 사실이 아니었고,
**측정 스크립트의 버그**였다.

```
viewBox = "-52 0 484 380"        ← min-x 가 0 이 아니라 -52 다
상대 박스 터치  x ∈ [-7.7, 62.0]
잘못된 판정   bb.x < 0        → −7.7 이 왼쪽 밖으로 보였다
올바른 판정   bb.x < vb.x     → −7.7 > −52 · 44.3 단위 여유
```

Chromium 으로 다시 쟀다 — 데모(현재 코드)와 첨부된 260052 원본 양쪽에서
1200×760 · 768×1024 · 400×900 세 크기 전부 **viewBox 밖 0 · 화면 잘림 0**
이다. 4-E 의 `VB_PAD` 는 제 일을 하고 있었다.

그래서 **기하를 한 줄도 바꾸지 않았다.** 고칠 것이 없는데 여백을 넓히면
모든 레이더의 절대 좌표가 이유 없이 움직인다. 대신 **같은 착각이 다시
일어나지 않도록** 그 불변조건을 여기에 고정한다.

고정하는 것 다섯 (§7 A~E).

  A. **어떤 라벨도 viewBox 밖으로 나가지 않는다** — 글자마다 1em 을 물리는
     **상한**으로 재므로 글꼴이 달라도 참이다. 브라우저가 필요 없다.
  B. 축 순서 8개가 4-E 구성 그대로다.
  C. 폴리곤 수가 팀당 하나씩이다.
  D. 라벨 좌표가 기준선 그대로다 — 중심·반경·각도가 움직이면 깨진다.
  E. 특정 라벨을 위한 예외 처리가 없다.

pytest 없이도 돈다:  python tests/test_radar_geometry.py
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import charts, fixtures, render                          # noqa: E402
from toto.analyze import run_all                                   # noqa: E402
from toto.settings import Settings                                 # noqa: E402

SIZE = 380.0                 # charts.radar 의 기본 size
FONT = 10.5                  # 축 라벨 font-size
LABEL_R = SIZE / 2 - 78 + 16        # radius + 16

# 4-E 가 정한 8축 (§1-19). 순서까지 계약이다.
AXES = ["big_chances_pg", "shots_on_target_pg", "goals_for_pg",
        "xga_pg", "goals_against_pg", "possession",
        "touches_opp_box_pg", "venue_points_pg"]


def _demo():
    matches = fixtures.build_demo_matches()
    s = Settings()
    run_all(matches, s, season_matches=[])
    return matches, s


def _svg(match=None) -> str:
    if match is None:
        match = _demo()[0][0]
    return charts.radar((match.radar or {}).get("axes") or [], "홈팀", "원정팀")


def _viewbox(svg: str) -> tuple[float, float, float, float]:
    m = re.search(r'viewBox="(-?[\d.]+) (-?[\d.]+) ([\d.]+) ([\d.]+)"', svg)
    assert m, svg[:200]
    return tuple(float(g) for g in m.groups())        # type: ignore[return-value]


def _texts(svg: str) -> list[dict]:
    """축 라벨 `<text>` 만. 폴리곤·점은 `<title>` 이라 걸리지 않는다."""
    out = []
    for x, y, anchor, label in re.findall(
            r'<text x="(-?[\d.]+)" y="(-?[\d.]+)" text-anchor="(\w+)"[^>]*>'
            r"(.*?)</text>", svg):
        out.append({"x": float(x), "y": float(y),
                    "anchor": anchor, "label": label})
    return out


def _extent(item: dict, font: float = FONT) -> tuple[float, float]:
    """라벨이 차지하는 x 구간의 **상한**.

    글자마다 1em 을 물린다 — 한글·화살표는 실제로 약 1em 이고 라틴 문자와
    공백은 그보다 좁으므로, 어떤 글꼴에서도 실제 폭이 이 값을 넘지 않는다.
    (실측: `상대 박스 터치` 8글자가 상한 84.0 에 실제 69.7.)
    """
    width = len(item["label"]) * font
    if item["anchor"] == "end":
        left = item["x"] - width
    elif item["anchor"] == "start":
        left = item["x"]
    else:
        left = item["x"] - width / 2
    return left, left + width


# --------------------------------------------------------------------------
# A. viewBox clipping — 라벨이 판 밖으로 나가지 않는다
# --------------------------------------------------------------------------
def test_a1_every_label_fits_inside_the_viewbox():
    """§7-A — 글자마다 1em 을 물린 **상한**으로도 전부 들어온다."""
    svg = _svg()
    vx, vy, vw, vh = _viewbox(svg)
    items = _texts(svg)
    assert len(items) == len(AXES), len(items)
    for item in items:
        left, right = _extent(item)
        assert left >= vx, (item["label"], left, vx)
        assert right <= vx + vw, (item["label"], right, vx + vw)
        # 세로도 본다 — 위아래 라벨은 판 경계에 가장 가깝다.
        assert vy <= item["y"] - FONT <= item["y"] + FONT <= vy + vh, item


def test_a2_the_longest_label_is_the_binding_case():
    """가장 긴 라벨이 가장 좁은 여유를 갖는지 — 그래야 A1 이 의미가 있다."""
    svg = _svg()
    vx, _vy, vw, _vh = _viewbox(svg)
    slack = {}
    for item in _texts(svg):
        left, right = _extent(item)
        slack[item["label"]] = min(left - vx, (vx + vw) - right)
    tightest = min(slack, key=lambda k: slack[k])
    assert tightest == "상대 박스 터치", slack
    assert slack[tightest] > 0, slack


def test_a3_there_is_real_headroom_left():
    """여유가 **얼마나** 남았는지 고정한다.

    5-D 의 오측정이 나온 자리라, "겨우 들어온다" 와 "넉넉히 들어온다" 를
    구분해 둔다. 라벨을 더 길게 만들면 이 테스트가 먼저 알려 준다.
    """
    svg = _svg()
    vx, _vy, vw, _vh = _viewbox(svg)
    worst = min(min(l - vx, (vx + vw) - r)
                for l, r in (_extent(i) for i in _texts(svg)))
    assert worst >= 2 * FONT, f"여유가 두 글자 미만이다 ({worst:.1f})"


def test_a4_a_much_longer_label_would_be_caught():
    """A1 이 통과만 하는 테스트가 아니라는 것 — 음성 대조."""
    axes = (_demo()[0][0].radar or {})["axes"]
    long_axes = [dict(a) for a in axes]
    long_axes[6]["label"] = "상대 박스 터치 횟수 평균값"     # 13글자
    svg = charts.radar(long_axes, "홈팀", "원정팀")
    vx, _vy, vw, _vh = _viewbox(svg)
    over = [i["label"] for i in _texts(svg)
            if _extent(i)[0] < vx or _extent(i)[1] > vx + vw]
    assert over, "길어진 라벨을 잡아내지 못한다"


def test_a5_the_padding_constant_is_what_makes_it_fit():
    """`VB_PAD` 가 여백의 근거다 — 0 이면 실제로 넘친다."""
    assert charts.VB_PAD == 52.0, charts.VB_PAD
    svg = _svg()
    items = _texts(svg)
    lefts = [_extent(i)[0] for i in items]
    assert min(lefts) < 0, "왼쪽 라벨이 원래 판(0~380) 안에 있다면 여백이 불필요하다"


# --------------------------------------------------------------------------
# B. 축 순서 — 4-E 구성 그대로
# --------------------------------------------------------------------------
def test_b1_axis_order_is_unchanged():
    """§7-B — 순서가 바뀌면 두 팀의 모양 비교가 통째로 달라진다."""
    matches, _s = _demo()
    for m in matches:
        keys = [a["key"] for a in (m.radar or {}).get("axes") or []]
        assert keys == AXES, (m.no, keys)


def test_b2_label_order_follows_axis_order():
    """그린 순서가 축 순서다 — 라벨이 엉뚱한 각도에 붙지 않는다."""
    match = _demo()[0][0]
    axes = (match.radar or {})["axes"]
    drawn = [i["label"] for i in _texts(_svg(match))]
    expect = [a["label"] + ("↓" if a.get("invert") else "") for a in axes]
    assert drawn == expect, list(zip(drawn, expect))


# --------------------------------------------------------------------------
# C. 폴리곤 — 팀당 하나
# --------------------------------------------------------------------------
def test_c1_two_polygons_per_radar():
    """§7-C — 홈·원정 하나씩. 축이 비어도 폴리곤은 그려진다."""
    assert _svg().count("<polygon") == 2


def test_c2_polygon_point_count_matches_axis_count():
    svg = _svg()
    for pts in re.findall(r'<polygon points="([^"]+)"', svg):
        assert len(pts.split()) == len(AXES), pts


def test_c3_round_report_has_one_radar_per_match():
    """§7-C — 14경기 = 레이더 14개 = 폴리곤 28개."""
    matches, s = _demo()
    from toto.models import Report
    html = render.render_report(
        Report(round_id="DEMO", generated_at="fixed", matches=matches), s)
    assert html.count('aria-label="리그 내 위치 레이더 차트"') == len(matches)
    assert html.count("<polygon") == len(matches) * 2


def test_c4_every_radar_svg_is_well_formed():
    matches, _s = _demo()
    for m in matches:
        ElementTree.fromstring(
            re.search(r"<svg.*?</svg>", _svg(m), re.S).group(0))


# --------------------------------------------------------------------------
# D. 라벨 좌표 — 중심·반경·각도가 움직이면 깨진다
# --------------------------------------------------------------------------
def test_d1_label_positions_match_the_documented_geometry():
    """§7-D — 좌표를 코드와 독립적으로 다시 계산해 대조한다."""
    svg = _svg()
    items = _texts(svg)
    cx = cy = SIZE / 2
    for i, item in enumerate(items):
        angle = -math.pi / 2 + 2 * math.pi * i / len(items)
        want_x = cx + LABEL_R * math.cos(angle)
        want_y = cy + LABEL_R * math.sin(angle)
        assert abs(item["x"] - want_x) < 0.06, (i, item, want_x)
        assert abs(item["y"] - want_y) < 0.06, (i, item, want_y)


def test_d2_anchors_follow_the_angle_not_the_text():
    """정렬은 **각도**가 정한다 — 라벨 길이나 이름을 보지 않는다."""
    items = _texts(_svg())
    for i, item in enumerate(items):
        cos = math.cos(-math.pi / 2 + 2 * math.pi * i / len(items))
        want = "middle" if abs(cos) < 0.25 else ("start" if cos > 0 else "end")
        assert item["anchor"] == want, (i, item, want)


def test_d3_the_viewbox_is_the_baseline():
    """판 자체가 기준선이다 — 여기가 움직이면 모든 절대 좌표가 움직인다."""
    assert _viewbox(_svg()) == (-52.0, 0.0, 484.0, 380.0)


def test_d4_center_and_radius_are_unchanged():
    """§6 — 중심점과 반경은 5-D1 에서 건드리지 않았다."""
    svg = _svg()
    rings = re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)" '
                       r'fill="none"', svg)
    assert len(rings) == 4, rings
    radius = SIZE / 2 - 78
    assert [r for _x, _y, r in rings] == [
        f"{radius * lv / 100:.1f}" for lv in (25, 50, 75, 100)], rings
    for x, y, _r in rings:
        assert (float(x), float(y)) == (SIZE / 2, SIZE / 2)


# --------------------------------------------------------------------------
# E. 지표별 예외 처리 금지
# --------------------------------------------------------------------------
def test_e1_no_label_specific_handling():
    """§4·§7-E — 특정 라벨만 따로 미는 코드가 없다."""
    src = Path(charts.__file__).read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith("#"))
    for banned in ('"상대 박스 터치"', "'상대 박스 터치'", '== "점유율"',
                   "len(label) >", "len(label) <", 'label ==',
                   "touches_opp_box"):
        assert banned not in code, banned


def test_e2_padding_is_one_constant_not_per_axis():
    """여백은 상수 하나다 — 축마다 다른 값을 주지 않는다."""
    src = Path(charts.__file__).read_text(encoding="utf-8")
    assert src.count("VB_PAD = ") == 1
    fn = src[src.index("def radar("):src.index("# 2) 배당 내재확률")]
    # viewBox 의 min-x · viewBox 의 width · max-width 셋뿐이다. 축을 그리는
    # 자리(`point`·라벨 좌표)에는 나타나지 않는다 — 여백은 판에만 준다.
    assert fn.count("VB_PAD") == 3, fn.count("VB_PAD")
    body = fn[:fn.index("svg = (")]
    assert "VB_PAD" not in body, "기하 계산에 여백이 섞였다"


def test_e3_radar_does_not_read_the_direct_compare_direction():
    """§1 — 5-D 의 방향 메타데이터는 레이더에 닿지 않는다."""
    src = Path(charts.__file__).read_text(encoding="utf-8")
    fn = src[src.index("def radar("):src.index("# 2) 배당 내재확률")]
    for banned in ("lower_better", "LOWER_BETTER", "SPECS"):
        assert banned not in fn, banned
    assert 'ax.get("invert")' in fn, "레이더의 ↓ 는 invert 에서 나온다"


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
