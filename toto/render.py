"""분석 결과 → 자체 완결형 HTML 리포트.

외부 참조(CDN 스크립트/폰트/이미지)를 일절 넣지 않는다. 파일 하나만 있으면
어느 브라우저에서든 열리고, 그대로 전달·공유할 수 있어야 한다.

색 토큰은 :root 에 라이트 값을 정의하고, 다크 값을 두 스코프
(prefers-color-scheme 미디어쿼리 + [data-theme="dark"])에 각각 선언한다.
"""
from __future__ import annotations

import html
from datetime import datetime

from . import charts
from .models import Match, Report
from .settings import Settings


def esc(text) -> str:
    return html.escape(str(text), quote=True)


# --------------------------------------------------------------------------
# 스타일
# --------------------------------------------------------------------------
CSS = """
:root{
  color-scheme:light;
  --surface-1:#fcfcfb; --page:#f9f9f7;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10);
  --home:#2a78d6; --away:#eb6834; --draw:#898781;
  --st-good:#0ca30c; --st-critical:#d03b3b; --st-warning:#fab219;
  --shadow:0 1px 2px rgba(11,11,11,.06),0 8px 24px rgba(11,11,11,.05);
}
@media (prefers-color-scheme:dark){
  :root:where(:not([data-theme="light"])){
    color-scheme:dark;
    --surface-1:#1a1a19; --page:#0d0d0d;
    --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
    --home:#3987e5; --away:#d95926; --draw:#898781;
    --st-good:#0ca30c; --st-critical:#d03b3b; --st-warning:#fab219;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --surface-1:#1a1a19; --page:#0d0d0d;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
  --home:#3987e5; --away:#d95926; --draw:#898781;
  --st-good:#0ca30c; --st-critical:#d03b3b; --st-warning:#fab219;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);
}

*{box-sizing:border-box}
body{
  margin:0;padding:0 16px 80px;background:var(--page);color:var(--text-primary);
  font-family:system-ui,-apple-system,"Segoe UI","Apple SD Gothic Neo",
    "Malgun Gothic",sans-serif;
  line-height:1.55;-webkit-text-size-adjust:100%;
}
.wrap{max-width:1080px;margin:0 auto}

header.top{padding:32px 0 8px}
header.top h1{font-size:26px;margin:0 0 6px;letter-spacing:-.01em}
header.top .sub{color:var(--text-secondary);font-size:14px;margin:0}
.badges{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0 0}
.badge{font-size:12px;padding:3px 9px;border-radius:999px;border:1px solid var(--border);
  background:var(--surface-1);color:var(--text-secondary)}
.badge.ok{color:var(--st-good)} .badge.bad{color:var(--st-critical)}

.warnbox{margin:16px 0;padding:12px 14px;border-radius:10px;
  border:1px solid var(--border);border-left:3px solid var(--st-warning);
  background:var(--surface-1);font-size:13.5px;color:var(--text-secondary)}
.warnbox ul{margin:6px 0 0;padding-left:18px}

h2.sec{font-size:18px;margin:36px 0 12px;letter-spacing:-.01em}

/* 요약 그리드 */
.summary{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}
.sumcard{display:block;text-decoration:none;color:inherit;background:var(--surface-1);
  border:1px solid var(--border);border-radius:12px;padding:11px 13px;box-shadow:var(--shadow)}
.sumcard:hover{border-color:var(--axis)}
.sumcard .hd{display:flex;justify-content:space-between;gap:8px;font-size:11.5px;
  color:var(--text-muted);margin-bottom:4px}
.sumcard .tm{font-size:14px;font-weight:600;margin-bottom:7px;
  overflow-wrap:anywhere}
.sumcard .pv{display:flex;gap:10px;font-size:11.5px;color:var(--text-secondary);
  margin-top:5px;font-variant-numeric:tabular-nums}

/* 경기 카드 */
.match{background:var(--surface-1);border:1px solid var(--border);border-radius:14px;
  padding:20px;margin:0 0 18px;box-shadow:var(--shadow);scroll-margin-top:16px}
.match > h3{margin:0;font-size:20px;letter-spacing:-.01em;overflow-wrap:anywhere}
.match .meta{color:var(--text-muted);font-size:12.5px;margin:4px 0 16px}
.no{display:inline-block;min-width:26px;height:26px;line-height:26px;text-align:center;
  border-radius:7px;background:var(--page);border:1px solid var(--border);
  font-size:12.5px;font-weight:700;margin-right:8px;color:var(--text-secondary)}

.block{margin:22px 0 0;padding-top:18px;border-top:1px solid var(--grid)}
.block:first-of-type{border-top:0;padding-top:0}
.block > h4{margin:0 0 10px;font-size:13px;font-weight:700;letter-spacing:.02em;
  color:var(--text-secondary);text-transform:uppercase}

.cols{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.cols3{display:grid;grid-template-columns:1.1fr 1fr;gap:22px;align-items:start}
@media (max-width:760px){.cols,.cols3{grid-template-columns:1fr}}

/* 차트 공통 */
figure.chart{margin:0}
figure.chart figcaption{font-size:11.5px;color:var(--text-muted);margin-top:8px}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:12px;
  color:var(--text-secondary)}
.lg{display:inline-flex;align-items:center;gap:6px}
.sw{width:10px;height:10px;border-radius:3px;display:inline-block;flex:none}
.nodata{font-size:12.5px;color:var(--text-muted);margin:6px 0;font-style:italic}

table.mini{width:100%;border-collapse:collapse;margin-top:10px;font-size:12.5px}
table.mini th{text-align:left;font-weight:600;color:var(--text-muted);
  border-bottom:1px solid var(--grid);padding:5px 6px;font-size:11.5px}
table.mini td{padding:5px 6px;border-bottom:1px solid var(--grid);
  color:var(--text-secondary)}
table.mini td:first-child{color:var(--text-primary)}
table.mini .num{text-align:right;font-variant-numeric:tabular-nums}
table.mini tr:last-child td{border-bottom:0}

/* 폼 */
.form .chips{list-style:none;display:flex;flex-wrap:wrap;gap:6px;margin:0;padding:0}
.chip{display:flex;flex-direction:column;align-items:center;gap:1px;min-width:60px;
  padding:6px 7px;border-radius:9px;background:var(--page);
  border:1px solid var(--border);font-size:11px;color:var(--text-secondary)}
.chip .dot{width:8px;height:8px;border-radius:50%;display:block}
.chip b{font-size:12px;color:var(--text-primary)}
.chip .sc{font-variant-numeric:tabular-nums}
.chip .op{font-size:10px;color:var(--text-muted);max-width:74px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.form-sum{margin-top:9px;font-size:12.5px;color:var(--text-secondary);
  display:flex;align-items:center;gap:8px}
.spark{flex:none}
.teamform{margin-bottom:16px}
.teamform > .tt{font-size:13px;font-weight:600;margin-bottom:7px;display:flex;
  align-items:center;gap:7px}

/* 특성 */
.traits{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media (max-width:760px){.traits{grid-template-columns:1fr}}
.traits h5{margin:0 0 6px;font-size:12.5px;display:flex;align-items:center;gap:7px}
.traits ul{margin:0 0 12px;padding-left:17px;font-size:12.5px;
  color:var(--text-secondary)}
.traits li{margin-bottom:3px}
.traits .lbl{font-size:11px;color:var(--text-muted);text-transform:uppercase;
  letter-spacing:.03em;margin:0 0 4px}

.mnotes{list-style:none;margin:10px 0 0;padding:0}
.mnotes li{padding:9px 11px;border-radius:9px;background:var(--page);
  border:1px solid var(--border);margin-bottom:6px;font-size:12.5px}
.mnotes .tp{font-weight:700;margin-right:6px}
.mnotes .vs{color:var(--text-muted);font-size:11.5px;display:block;margin-top:2px}

.missing{font-size:12.5px;color:var(--text-secondary)}
.missing ul{margin:4px 0 0;padding-left:17px}

.kv{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:12.5px;
  color:var(--text-secondary);margin-top:8px}
.kv b{color:var(--text-primary);font-variant-numeric:tabular-nums}

.notebox{margin-top:12px;padding:9px 11px;border-radius:9px;font-size:12.5px;
  background:var(--page);border:1px solid var(--border);
  border-left:3px solid var(--st-warning);color:var(--text-secondary)}

footer.bot{margin-top:44px;padding-top:18px;border-top:1px solid var(--grid);
  font-size:12px;color:var(--text-muted)}
a.top-link{color:var(--text-muted);font-size:12px;text-decoration:none}
a.top-link:hover{color:var(--text-secondary)}
"""


# --------------------------------------------------------------------------
# 조각 렌더러
# --------------------------------------------------------------------------
def _swatch(color: str) -> str:
    return f'<span class="sw" style="background:{color}"></span>'


def _odds_block(match: Match) -> str:
    if not match.probs or not match.odds.available:
        return ('<div class="block"><h4>배당률 · 내재확률</h4>'
                '<p class="nodata">피나클 배당률을 가져오지 못했습니다.</p></div>')

    p = match.probs
    bar = charts.prob_bar(p.home, p.draw, p.away,
                          match.odds.home, match.odds.draw, match.odds.away)
    extra = []
    if match.odds.ah_line is not None:
        extra.append(f'아시안 핸디캡 <b>{match.odds.ah_line:+.2f}</b> '
                     f'(홈 {charts._fmt(match.odds.ah_home)} / '
                     f'원정 {charts._fmt(match.odds.ah_away)})')
    if match.odds.ou_line is not None:
        extra.append(f'오버/언더 <b>{match.odds.ou_line:.1f}</b> '
                     f'(오버 {charts._fmt(match.odds.ou_over)} / '
                     f'언더 {charts._fmt(match.odds.ou_under)})')
    extra.append(f'북메이커 마진 <b>{p.margin * 100:.2f}%</b>')
    if match.odds.source:
        extra.append(f'출처 <b>{esc(match.odds.source)}</b>')

    return (f'<div class="block"><h4>배당률 · 내재확률 (마진 제거)</h4>{bar}'
            f'<div class="kv">{"".join(f"<span>{e}</span>" for e in extra)}</div></div>')


def _standing_row(match: Match) -> str:
    """순위표 요약 한 줄."""
    cells = []
    for side, color in ((match.home_profile, charts.C_HOME),
                        (match.away_profile, charts.C_AWAY)):
        if side is None:
            continue
        st = side.stats
        bits = []
        if st.rank is not None:
            bits.append(f"{st.rank}위")
        if st.played:
            bits.append(f"{st.played}경기")
        if None not in (st.wins, st.draws, st.losses):
            bits.append(f"{st.wins}승 {st.draws}무 {st.losses}패")
        if st.points is not None:
            bits.append(f"승점 {st.points}")
        if st.goal_diff is not None:
            bits.append(f"골득실 {st.goal_diff:+d}")
        if side.rest_days is not None:
            bits.append(f"휴식 {side.rest_days}일")
        if bits:
            cells.append(f'<span>{_swatch(color)}<b>{esc(side.team.display)}</b> '
                         f'{esc(" · ".join(bits))}</span>')
    if not cells:
        return ""
    return f'<div class="kv">{"".join(cells)}</div>'


def _form_block(match: Match) -> str:
    parts = []
    for profile, color in ((match.home_profile, charts.C_HOME),
                           (match.away_profile, charts.C_AWAY)):
        if profile is None:
            continue
        parts.append(
            f'<div class="teamform"><div class="tt">{_swatch(color)}'
            f'{esc(profile.team.display)}</div>'
            f'{charts.form_timeline(profile.form, profile.team.display)}</div>')
    if not parts:
        return ""
    return (f'<div class="block"><h4>최근 5경기 폼</h4>'
            f'<div class="cols">{"".join(parts)}</div></div>')


def _h2h_block(match: Match) -> str:
    h2h = match.h2h
    bar = charts.h2h_bar(h2h.home_wins, h2h.draws, h2h.away_wins,
                         match.home.display, match.away.display)
    rows = ""
    for e in h2h.entries[:10]:
        rows += (f'<tr><td>{esc(e.date)}</td>'
                 f'<td>{esc(e.home_team)} {e.home_goals}-{e.away_goals} '
                 f'{esc(e.away_team)}</td></tr>')
    table = (f'<table class="mini"><thead><tr><th>날짜</th><th>결과</th></tr></thead>'
             f'<tbody>{rows}</tbody></table>') if rows else ""
    return f'<div class="block"><h4>상대전적</h4>{bar}{table}</div>'


def _traits_block(match: Match) -> str:
    hp, ap = match.home_profile, match.away_profile
    if hp is None or ap is None:
        return ""

    def col(profile, color) -> str:
        def lst(title, items):
            if not items:
                return f'<p class="lbl">{title}</p><p class="nodata">데이터 없음</p>'
            body = "".join(f"<li>{esc(i)}</li>" for i in items)
            return f'<p class="lbl">{title}</p><ul>{body}</ul>'
        return (f'<div><h5>{_swatch(color)}{esc(profile.team.display)}</h5>'
                f'{lst("강점 Strengths", profile.strengths)}'
                f'{lst("약점 Weaknesses", profile.weaknesses)}'
                f'{lst("스타일 Style of play", profile.style_of_play)}</div>')

    notes = ""
    if match.matchup_notes:
        items = ""
        for note in match.matchup_notes:
            color = charts.C_HOME if note["side"] == "home" else charts.C_AWAY
            items += (f'<li>{_swatch(color)}<span class="tp">{esc(note["topic"])}</span>'
                      f'{esc(note["text"])}'
                      f'<span class="vs">강점: {esc(note["strength"])} ↔ '
                      f'약점: {esc(note["weakness"])}</span></li>')
        notes = f'<ul class="mnotes">{items}</ul>'

    missing = ""
    for profile, color in ((hp, charts.C_HOME), (ap, charts.C_AWAY)):
        if profile.missing_players:
            lis = "".join(
                f'<li>{esc(m.get("player", ""))}'
                + (f' — {esc(m.get("reason"))}' if m.get("reason") else "")
                + "</li>" for m in profile.missing_players)
            missing += (f'<div class="missing">{_swatch(color)}'
                        f'<b>{esc(profile.team.display)}</b> 결장 예상<ul>{lis}</ul></div>')

    return (f'<div class="block"><h4>전략적 상성 (WhoScored 팀 특성)</h4>'
            f'<div class="traits">{col(hp, charts.C_HOME)}{col(ap, charts.C_AWAY)}</div>'
            f'{notes}'
            + (f'<div class="block" style="border-top:0;padding-top:14px">'
               f'<h4>결장 예상</h4>{missing}</div>' if missing else "")
            + '</div>')


def _match_card(match: Match, settings: Settings) -> str:
    meta = " · ".join(x for x in (match.league_ko or match.league,
                                  match.kickoff_kst) if x)
    notes = ""
    if match.notes:
        notes = ('<div class="notebox">'
                 + "<br>".join(esc(n) for n in match.notes) + "</div>")

    return (f'<article class="match" id="m{match.no}">'
            f'<h3><span class="no">{match.no}</span>'
            f'{esc(match.home.display)} <span style="color:var(--text-muted)">vs</span> '
            f'{esc(match.away.display)}</h3>'
            f'<p class="meta">{esc(meta)}</p>'
            f'{_standing_row(match)}'
            f'{notes}'
            f'{_odds_block(match)}'
            f'<div class="block"><h4>리그 내 위치 · 지표 비교</h4>'
            f'<div class="cols3">'
            f'{charts.radar((match.radar or {}).get("axes") or [], match.home.display, match.away.display)}'
            f'{_compare_inner(match, settings)}'
            f'</div></div>'
            f'{_form_block(match)}'
            f'{_h2h_block(match)}'
            f'{_traits_block(match)}'
            f'<p style="margin:18px 0 0"><a class="top-link" href="#top">↑ 목록으로</a></p>'
            f'</article>')


def _compare_inner(match: Match, settings: Settings) -> str:
    hp, ap = match.home_profile, match.away_profile
    if hp is None or ap is None:
        return '<p class="nodata">비교할 팀 데이터가 없습니다.</p>'
    rows = []
    for metric in settings.compare_metrics:
        hv = getattr(hp.stats, metric["key"], None)
        av = getattr(ap.stats, metric["key"], None)
        if hv is None and av is None:
            continue
        rows.append({"label": metric["label"], "home": hv, "away": av,
                     "fmt": metric.get("fmt", "{:.2f}")})
    if not rows:
        return '<p class="nodata">비교할 지표가 없습니다.</p>'
    return charts.diverging_bar(rows, match.home.display, match.away.display, width=480)


def _summary_grid(matches: list[Match]) -> str:
    cards = []
    for m in matches:
        if m.probs:
            bar = charts.mini_prob_bar(m.probs.home, m.probs.draw, m.probs.away)
            ph, pd, pa = m.probs.pct()
            pv = (f'<div class="pv"><span>승 {ph:.0f}%</span>'
                  f'<span>무 {pd:.0f}%</span><span>패 {pa:.0f}%</span></div>')
        else:
            bar, pv = "", '<div class="pv"><span>배당 없음</span></div>'
        cards.append(
            f'<a class="sumcard" href="#m{m.no}">'
            f'<div class="hd"><span>{m.no}. {esc(m.league_ko or m.league)}</span>'
            f'<span>{esc(m.kickoff_kst)}</span></div>'
            f'<div class="tm">{esc(m.home.display)} vs {esc(m.away.display)}</div>'
            f'{bar}{pv}</a>')
    return f'<div class="summary">{"".join(cards)}</div>'


# --------------------------------------------------------------------------
# 리포트 전체
# --------------------------------------------------------------------------
def render_report(report: Report, settings: Settings) -> str:
    generated = report.generated_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"축구토토 승무패 {report.round_id or ''}회차 분석".replace("  ", " ")

    badges = "".join(
        f'<span class="badge {"ok" if str(v).startswith("ok") else "bad"}">'
        f'{esc(k)}: {esc(v)}</span>'
        for k, v in (report.source_status or {}).items())

    warnings = ""
    if report.warnings:
        items = "".join(f"<li>{esc(w)}</li>" for w in report.warnings)
        warnings = (f'<div class="warnbox"><b>확인이 필요한 항목</b>'
                    f'<ul>{items}</ul></div>')

    cards = "".join(_match_card(m, settings) for m in report.matches)

    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}</style>
</head><body><div class="wrap" id="top">
<header class="top">
  <h1>⚽ {esc(title)}</h1>
  <p class="sub">경기별 상세 분석 데이터 · 생성 {esc(generated)}</p>
  <div class="badges">{badges}</div>
</header>
{warnings}
<h2 class="sec">14경기 한눈에 보기</h2>
<p class="sub" style="color:var(--text-muted);font-size:12.5px;margin:0 0 12px">
  막대는 배당률에서 마진을 제거한 내재확률입니다
  (<span class="lg">{_swatch(charts.C_HOME)}승</span>
   <span class="lg">{_swatch(charts.C_DRAW)}무</span>
   <span class="lg">{_swatch(charts.C_AWAY)}패</span>). 카드를 누르면 상세로 이동합니다.</p>
{_summary_grid(report.matches)}

<h2 class="sec">경기별 상세 분석</h2>
{cards}

<footer class="bot">
  이 리포트는 판단에 필요한 데이터를 모아 보여줄 뿐, 승/무/패를 추천하지 않습니다.
  배당률·통계는 수집 시점 기준이며 경기 직전까지 변동될 수 있습니다.<br>
  출처: 베트맨(경기 목록) · Pinnacle(배당률) · WhoScored(팀 통계 및 특성).
</footer>
</div></body></html>"""
