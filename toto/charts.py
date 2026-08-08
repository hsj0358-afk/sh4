"""인라인 SVG 차트 생성.

외부 차트 라이브러리를 쓰지 않는다 — 리포트가 CDN 없이 단일 HTML 파일로
완결되어야 하기 때문이다. 색은 전부 CSS 변수(var(--...))로 넣어서
라이트/다크 테마 전환이 한 곳에서 이뤄지도록 한다.

시각화 규칙 (dataviz 가이드 준수):
  · 홈=파랑, 원정=주황 — 리포트 전체에서 팀 정체성에 색을 고정한다.
    이 두 색은 색각이상 시뮬레이션에서 분리도 검증을 통과한 조합이다.
  · 무승부는 중립 회색. 승↔무↔패 는 "홈 우세 ← 중립 → 원정 우세" 극성 축이라
    가운데를 무채색으로 두는 diverging 배색이 맞다.
  · 쌓인 막대 사이에는 2px 표면색 간격을 둔다(테두리를 그리지 않는다).
  · 격자/축은 hairline 1px 실선, 배경으로 물러나게.
  · 계열이 2개 이상이면 범례를 항상 넣고, 텍스트에는 계열색을 쓰지 않는다.
  · 각 마크에 <title> 을 달아 마우스오버 시 원값이 보이게 한다(JS 불필요).
"""
from __future__ import annotations

import html
import math

# 색 역할 (실제 값은 render.py 의 CSS 토큰에서 정의)
C_HOME = "var(--home)"
C_AWAY = "var(--away)"
C_DRAW = "var(--draw)"
C_SURFACE = "var(--surface-1)"
C_GRID = "var(--grid)"
C_AXIS = "var(--axis)"
C_MUTED = "var(--text-muted)"
C_SECOND = "var(--text-secondary)"
C_PRIMARY = "var(--text-primary)"
C_WIN = "var(--st-good)"
C_LOSS = "var(--st-critical)"

GAP = 2.0          # 표면색 간격 (px)
BAR_MAX = 24.0     # 막대 최대 두께


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


# --------------------------------------------------------------------------
# 1) 레이더 — 리그 내 위치
# --------------------------------------------------------------------------
def radar(axes: list[dict], home_name: str, away_name: str,
          size: int = 380) -> str:
    """두 팀의 리그 백분위를 겹쳐 그린다.

    axes: [{label, home_pct, away_pct, home_value, away_value, invert}, ...]
    50% 링이 리그 평균선 역할을 한다.
    """
    axes = [a for a in axes if a.get("home_pct") is not None
            or a.get("away_pct") is not None]
    n = len(axes)
    if n < 3:
        return _empty_note("레이더를 그릴 지표가 부족합니다 (3개 이상 필요)")

    cx = cy = size / 2
    radius = size / 2 - 78          # 축 라벨 자리를 남긴다
    parts: list[str] = []

    # --- 격자 링 ---
    for level in (25, 50, 75, 100):
        r = radius * level / 100
        emphasis = level == 50      # 리그 평균선은 파선으로 강조
        stroke = C_AXIS if emphasis else C_GRID
        dash = ' stroke-dasharray="3 3"' if emphasis else ""
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" '
            f'stroke="{stroke}" stroke-width="1"{dash} />')

    # --- 축선 + 라벨 ---
    def point(i: int, pct: float) -> tuple[float, float]:
        angle = -math.pi / 2 + 2 * math.pi * i / n
        r = radius * max(0.0, min(100.0, pct)) / 100
        return cx + r * math.cos(angle), cy + r * math.sin(angle)

    for i, ax in enumerate(axes):
        angle = -math.pi / 2 + 2 * math.pi * i / n
        ex, ey = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
        parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
                     f'stroke="{C_GRID}" stroke-width="1" />')

        lx, ly = cx + (radius + 16) * math.cos(angle), cy + (radius + 16) * math.sin(angle)
        cos = math.cos(angle)
        anchor = "middle" if abs(cos) < 0.25 else ("start" if cos > 0 else "end")
        label = ax["label"] + ("↓" if ax.get("invert") else "")
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
            f'dominant-baseline="middle" font-size="10.5" fill="{C_SECOND}">'
            f'{esc(label)}</text>')

    # --- 데이터 다각형 ---
    def polygon(key: str, color: str, name: str) -> str:
        pts, titles = [], []
        for i, ax in enumerate(axes):
            pct = ax.get(key)
            if pct is None:
                pct = 0.0
            x, y = point(i, pct)
            pts.append(f"{x:.1f},{y:.1f}")
            titles.append(f"{ax['label']}: {_fmt(ax.get(key.replace('_pct','_value')))} "
                          f"(상위 {100 - pct:.0f}%)")
        body = (f'<polygon points="{" ".join(pts)}" fill="{color}" fill-opacity="0.10" '
                f'stroke="{color}" stroke-width="2" stroke-linejoin="round">'
                f'<title>{esc(name)}</title></polygon>')
        dots = ""
        for i, ax in enumerate(axes):
            pct = ax.get(key)
            if pct is None:
                continue
            x, y = point(i, pct)
            dots += (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}" '
                     f'stroke="{C_SURFACE}" stroke-width="2">'
                     f'<title>{esc(name)} · {esc(titles[i])}</title></circle>')
        return body + dots

    parts.append(polygon("home_pct", C_HOME, home_name))
    parts.append(polygon("away_pct", C_AWAY, away_name))

    svg = (f'<svg viewBox="0 0 {size} {size}" width="100%" height="auto" '
           f'role="img" aria-label="리그 내 위치 레이더 차트" '
           f'style="max-width:{size}px">{"".join(parts)}</svg>')
    return (f'<figure class="chart">{svg}'
            f'{legend([(C_HOME, home_name), (C_AWAY, away_name)])}'
            f'<figcaption>바깥쪽일수록 해당 리그에서 상위. '
            f'점선은 리그 중간(50%), ↓ 표시는 낮을수록 좋은 지표입니다.</figcaption>'
            f'</figure>')


# --------------------------------------------------------------------------
# 2) 배당 내재확률 — 100% 스택 바
# --------------------------------------------------------------------------
def prob_bar(p_home: float, p_draw: float, p_away: float,
             o_home: float | None, o_draw: float | None, o_away: float | None,
             width: int = 640, height: int = 46) -> str:
    """승/무/패 내재확률을 100% 가로 스택으로."""
    segs = [
        ("승", p_home, o_home, C_HOME),
        ("무", p_draw, o_draw, C_DRAW),
        ("패", p_away, o_away, C_AWAY),
    ]
    parts: list[str] = []
    x = 0.0
    total = sum(s[1] for s in segs) or 1.0

    for idx, (label, prob, odd, color) in enumerate(segs):
        raw_w = width * prob / total
        # 마지막을 제외하고 오른쪽에 2px 표면 간격을 둔다
        w = max(0.0, raw_w - (GAP if idx < len(segs) - 1 else 0.0))
        pct = prob * 100
        radius = 4 if idx in (0, len(segs) - 1) else 0
        parts.append(
            f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="{height}" '
            f'rx="{radius}" fill="{color}">'
            f'<title>{esc(label)} {pct:.1f}% · 배당 {_fmt(odd)}</title></rect>')

        # 라벨은 들어갈 자리가 있을 때만 안쪽에 (없으면 표 값으로 대체)
        text = f"{label} {pct:.0f}%"
        if w >= len(text) * 8.0:
            parts.append(
                f'<text x="{x + w / 2:.1f}" y="{height / 2:.1f}" text-anchor="middle" '
                f'dominant-baseline="central" font-size="13" font-weight="600" '
                f'fill="#ffffff">{esc(text)}</text>')
        x += raw_w

    svg = (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
           f'preserveAspectRatio="none" role="img" '
           f'aria-label="승무패 내재확률 {p_home*100:.0f}/{p_draw*100:.0f}/{p_away*100:.0f}퍼센트" '
           f'>{"".join(parts)}</svg>')

    rows = "".join(
        f'<tr><td><span class="sw" style="background:{c}"></span>{esc(l)}</td>'
        f'<td class="num">{_fmt(o)}</td><td class="num">{p*100:.1f}%</td></tr>'
        for l, p, o, c in segs)
    table = (f'<table class="mini"><thead><tr><th>결과</th><th class="num">배당</th>'
             f'<th class="num">내재확률</th></tr></thead><tbody>{rows}</tbody></table>')
    return f'<figure class="chart">{svg}{table}</figure>'


# --------------------------------------------------------------------------
# 3) 최근 폼 — W/D/L 칩 + 누적 승점 스파크라인
# --------------------------------------------------------------------------
_RESULT_COLOR = {"W": C_WIN, "D": C_DRAW, "L": C_LOSS}
_RESULT_KO = {"W": "승", "D": "무", "L": "패"}


def form_timeline(form: list, team_name: str) -> str:
    """최근 경기 결과를 오래된 → 최근 순으로 칩 나열."""
    if not form:
        return _empty_note(f"{team_name}: 최근 경기 데이터가 없습니다")

    ordered = list(reversed(form))       # form 은 최신순으로 들어온다
    chips = []
    for entry in ordered:
        color = _RESULT_COLOR.get(entry.result, C_DRAW)
        venue = "홈" if entry.home else "원정"
        chips.append(
            f'<li class="chip" title="{esc(entry.date)} {esc(venue)} vs '
            f'{esc(entry.opponent)} {esc(entry.score)}">'
            f'<span class="dot" style="background:{color}"></span>'
            f'<b>{esc(_RESULT_KO.get(entry.result, entry.result))}</b>'
            f'<span class="sc">{esc(entry.score)}</span>'
            f'<span class="op">{esc(venue)} · {esc(entry.opponent)}</span></li>')

    points = sum(e.points for e in ordered)
    spark = _sparkline([e.points for e in ordered])
    return (f'<div class="form">'
            f'<ul class="chips">{"".join(chips)}</ul>'
            f'<div class="form-sum">최근 {len(ordered)}경기 <b>{points}점</b> '
            f'/ {len(ordered) * 3}점 {spark}</div></div>')


def _sparkline(points: list[int], width: int = 90, height: int = 22) -> str:
    """누적 승점 추이 미니 라인."""
    if not points:
        return ""
    cum, total = [], 0
    for p in points:
        total += p
        cum.append(total)
    top = max(cum) or 1
    step = width / max(1, len(cum) - 1) if len(cum) > 1 else width
    pts = " ".join(f"{i * step:.1f},{height - (v / top) * (height - 4) - 2:.1f}"
                   for i, v in enumerate(cum))
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" '
            f'height="{height}" role="img" aria-label="누적 승점 추이">'
            f'<polyline points="{pts}" fill="none" stroke="{C_AXIS}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')


# --------------------------------------------------------------------------
# 4) 상대전적 — 스택 바
# --------------------------------------------------------------------------
def h2h_bar(home_wins: int, draws: int, away_wins: int,
            home_name: str, away_name: str,
            width: int = 640, height: int = 34) -> str:
    total = home_wins + draws + away_wins
    if total == 0:
        return _empty_note("상대전적 데이터가 없습니다")

    segs = [(f"{home_name} 승", home_wins, C_HOME),
            ("무", draws, C_DRAW),
            (f"{away_name} 승", away_wins, C_AWAY)]
    parts, x = [], 0.0
    for idx, (label, count, color) in enumerate(segs):
        raw_w = width * count / total
        if raw_w <= 0:
            continue
        w = max(0.0, raw_w - (GAP if idx < len(segs) - 1 else 0.0))
        radius = 4 if idx in (0, len(segs) - 1) else 0
        parts.append(f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="{height}" '
                     f'rx="{radius}" fill="{color}">'
                     f'<title>{esc(label)} {count}회</title></rect>')
        if w >= 34:
            parts.append(
                f'<text x="{x + w / 2:.1f}" y="{height / 2:.1f}" text-anchor="middle" '
                f'dominant-baseline="central" font-size="13" font-weight="600" '
                f'fill="#ffffff">{count}</text>')
        x += raw_w

    svg = (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
           f'preserveAspectRatio="none" role="img" '
           f'aria-label="상대전적 {home_wins}승 {draws}무 {away_wins}패">'
           f'{"".join(parts)}</svg>')
    return (f'<figure class="chart">{svg}'
            f'{legend([(C_HOME, f"{home_name} {home_wins}승"), (C_DRAW, f"무 {draws}"), (C_AWAY, f"{away_name} {away_wins}승")])}'
            f'</figure>')


# --------------------------------------------------------------------------
# 5) 직접 비교 — 다이버징(마주보기) 바
# --------------------------------------------------------------------------
def diverging_bar(rows: list[dict], home_name: str, away_name: str,
                  width: int = 640) -> str:
    """rows: [{label, home, away, fmt}] — 두 팀 값을 중앙 기준 좌우로."""
    rows = [r for r in rows if r.get("home") is not None or r.get("away") is not None]
    if not rows:
        return _empty_note("비교할 지표가 없습니다")

    # 가로 배치: [값][홈 막대] [지표명] [원정 막대][값]
    # 가운데 라벨 칸과 바깥 값 칸을 먼저 떼어 놓고, 남는 폭을 막대에 준다.
    # (이 폭 계산을 건너뛰면 라벨이 막대에 덮이고 값이 잘린다.)
    row_h, gap_y = 30, 8
    label_w, value_w, pad = 124.0, 42.0, 6.0
    half = max(20.0, (width - label_w) / 2 - value_w - pad)
    height = len(rows) * (row_h + gap_y)
    bar_h = min(BAR_MAX, row_h - 10)
    cx = width / 2
    left_edge = cx - label_w / 2 - pad      # 왼쪽 막대의 오른쪽 끝(기준선)
    right_edge = cx + label_w / 2 + pad     # 오른쪽 막대의 왼쪽 끝(기준선)
    parts: list[str] = []

    for i, row in enumerate(rows):
        y = i * (row_h + gap_y)
        mid_y = y + row_h / 2
        hv, av = row.get("home"), row.get("away")
        fmt = row.get("fmt", "{:.2f}")
        top = max(abs(hv or 0), abs(av or 0)) or 1.0

        parts.append(
            f'<text x="{cx:.1f}" y="{mid_y:.1f}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="10.5" fill="{C_MUTED}">'
            f'{esc(row["label"])}</text>')

        if hv is not None:
            w = half * abs(hv) / top
            # 왼쪽 막대: 바깥쪽(데이터) 끝만 둥글게, 기준선 쪽은 각지게
            parts.append(_rounded_bar(left_edge - w, mid_y - bar_h / 2, w, bar_h,
                                      C_HOME, left=True,
                                      title=f"{home_name} {fmt.format(hv)}"))
            parts.append(
                f'<text x="{left_edge - w - 5:.1f}" y="{mid_y:.1f}" text-anchor="end" '
                f'dominant-baseline="central" font-size="11.5" font-weight="600" '
                f'fill="{C_PRIMARY}">{esc(fmt.format(hv))}</text>')
        if av is not None:
            w = half * abs(av) / top
            parts.append(_rounded_bar(right_edge, mid_y - bar_h / 2, w, bar_h,
                                      C_AWAY, left=False,
                                      title=f"{away_name} {fmt.format(av)}"))
            parts.append(
                f'<text x="{right_edge + w + 5:.1f}" y="{mid_y:.1f}" text-anchor="start" '
                f'dominant-baseline="central" font-size="11.5" font-weight="600" '
                f'fill="{C_PRIMARY}">{esc(fmt.format(av))}</text>')

    svg = (f'<svg viewBox="0 0 {width} {height}" width="100%" height="auto" '
           f'role="img" aria-label="두 팀 지표 직접 비교" '
           f'style="max-width:{width}px">{"".join(parts)}</svg>')
    return (f'<figure class="chart">{svg}'
            f'{legend([(C_HOME, home_name), (C_AWAY, away_name)])}'
            f'<figcaption>각 줄에서 막대 길이는 두 팀 중 큰 값을 기준으로 한 상대 길이입니다.'
            f'</figcaption></figure>')


def _rounded_bar(x: float, y: float, w: float, h: float, color: str,
                 left: bool, title: str) -> str:
    """한쪽 끝만 4px 둥근 막대 (데이터 끝은 둥글게, 기준선 쪽은 각지게)."""
    r = min(4.0, w, h / 2)
    if w <= 0:
        return ""
    if r <= 0.5:
        path = f"M{x:.1f},{y:.1f} h{w:.1f} v{h:.1f} h-{w:.1f} Z"
    elif left:
        path = (f"M{x + w:.1f},{y:.1f} H{x + r:.1f} A{r:.1f},{r:.1f} 0 0 0 {x:.1f},{y + r:.1f} "
                f"V{y + h - r:.1f} A{r:.1f},{r:.1f} 0 0 0 {x + r:.1f},{y + h:.1f} "
                f"H{x + w:.1f} Z")
    else:
        path = (f"M{x:.1f},{y:.1f} H{x + w - r:.1f} A{r:.1f},{r:.1f} 0 0 1 {x + w:.1f},{y + r:.1f} "
                f"V{y + h - r:.1f} A{r:.1f},{r:.1f} 0 0 1 {x + w - r:.1f},{y + h:.1f} "
                f"H{x:.1f} Z")
    return f'<path d="{path}" fill="{color}"><title>{esc(title)}</title></path>'


# --------------------------------------------------------------------------
# 공통
# --------------------------------------------------------------------------
def legend(items: list[tuple[str, str]]) -> str:
    """계열 범례. 텍스트는 항상 잉크색, 정체성은 옆의 색 스와치가 담당한다."""
    chips = "".join(
        f'<span class="lg"><span class="sw" style="background:{color}"></span>'
        f'{esc(label)}</span>' for color, label in items)
    return f'<div class="legend">{chips}</div>'


def _empty_note(text: str) -> str:
    return f'<p class="nodata">{esc(text)}</p>'


def mini_prob_bar(p_home: float, p_draw: float, p_away: float,
                  width: int = 150, height: int = 12) -> str:
    """요약 그리드용 초소형 확률 바 (라벨 없음 — 옆에 수치를 함께 적는다)."""
    parts, x = [], 0.0
    total = (p_home + p_draw + p_away) or 1.0
    for idx, (prob, color) in enumerate(((p_home, C_HOME), (p_draw, C_DRAW),
                                         (p_away, C_AWAY))):
        raw_w = width * prob / total
        w = max(0.0, raw_w - (GAP if idx < 2 else 0.0))
        radius = 3 if idx in (0, 2) else 0
        parts.append(f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="{height}" '
                     f'rx="{radius}" fill="{color}"/>')
        x += raw_w
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
            f'preserveAspectRatio="none" aria-hidden="true">{"".join(parts)}</svg>')
