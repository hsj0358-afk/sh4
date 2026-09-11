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
from .ticket import TICKET_CSS, render_ticket


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
/* 표본 수(n=3). 값보다 한 단계 약하게 — 적은 표본이 충분해 보이면 안 된다 */
table.mini small{color:var(--text-muted);font-size:11px;font-weight:400}

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

/* 회차 승산 (지침 §5) */
.verdict{margin:16px 0 22px;padding:16px 18px;border-radius:12px;
  background:var(--surface-1);border:1px solid var(--border);
  border-left:4px solid var(--draw);box-shadow:var(--shadow)}
.verdict.bet{border-left-color:var(--st-good)}
.verdict.pass{border-left-color:var(--st-critical)}
.vhead{font-size:14px;font-weight:700;display:flex;align-items:center;gap:10px}
.vlab{font-size:12px;padding:2px 10px;border-radius:999px;
  border:1px solid var(--border);background:var(--page)}
.verdict.bet .vlab{color:var(--st-good)}
.verdict.pass .vlab{color:var(--st-critical)}
.vnums{display:flex;flex-wrap:wrap;gap:8px 22px;margin-top:10px;font-size:13px;
  color:var(--text-secondary);font-variant-numeric:tabular-nums}
.vnums b{color:var(--text-primary);font-size:15px}
.vex{color:var(--text-muted);font-size:12px}
.vnote{font-size:11.5px;color:var(--text-muted);margin:10px 0 0}
.vwarn{font-size:12.5px;color:var(--text-secondary);margin:8px 0 0;
  padding:8px 10px;border-radius:8px;background:var(--page)}

/* 통합표 (지침 §7) */
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table.picks{width:100%;min-width:760px;border-collapse:collapse;font-size:12.5px;
  background:var(--surface-1);border:1px solid var(--border);border-radius:10px}
table.picks th{text-align:left;font-weight:600;color:var(--text-muted);
  border-bottom:1px solid var(--grid);padding:8px 9px;font-size:11.5px;
  white-space:nowrap}
table.picks td{padding:7px 9px;border-bottom:1px solid var(--grid);
  color:var(--text-secondary);white-space:nowrap}
table.picks tr:last-child td{border-bottom:0}
table.picks .num{text-align:right;font-variant-numeric:tabular-nums}
table.picks .hi{color:var(--text-primary);font-weight:700}
table.picks .pk{color:var(--text-primary);font-weight:700}
.tossup{display:inline-block;font-size:10.5px;padding:1px 7px;border-radius:999px;
  background:var(--page);border:1px solid var(--st-warning);
  color:var(--text-secondary)}
.veto{display:inline-block;font-size:10.5px;padding:1px 7px;border-radius:999px;
  background:var(--page);border:1px solid var(--border);color:var(--text-muted)}
.pickline{margin-top:12px;font-size:13.5px;color:var(--text-secondary)}
.pickline .pk{font-size:16px;color:var(--text-primary)}

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


def _market_status(match: Match, report) -> str:
    """이 경기가 예정인가 종료인가. **4-A 의 판정을 그대로 쓴다** (§53).

    킥오프와 지금 시각을 비교해 추정하지 않는다 — 시즌 색인의 `finished`
    에서만 오고, 색인에서 못 가리면 '확인 불가' 다.
    """
    if report is None or not getattr(report, "season_matches", None):
        return ""
    from . import match_material

    try:
        return match_material._status_of(match, report)[0]
    except Exception:                                  # noqa: BLE001
        # 상태를 못 가려도 리포트는 나와야 한다 — 그때는 '확인 불가' 다.
        return ""


def _odds_block(match: Match, report=None) -> str:
    if not match.probs or not match.odds.available:
        # 왜 없는지를 셋으로 나눠 적는다 (§42). 문장은 경기자료 MD 와
        # **같은 함수**에서 온다 — 두 화면이 다른 이유를 말하면 안 된다.
        from . import match_material

        why = match_material.market_absence_reason(_market_status(match, report))
        return ('<div class="block"><h4>Pinnacle 시장 기준선</h4>'
                f'<p class="nodata">{esc(why)}</p></div>')

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
    extra.append(f'오버라운드 <b>{p.overround:.4f}</b> · '
                 f'옵션당 마진 <b>{p.margin_per_option * 100:.2f}%p</b>')
    if p.clamped:
        extra.append('<b>음수 확률 클램프 적용</b>')
    if p.veto_note:
        extra.append(f'Veto <b>{esc(p.veto_note)}</b>')
    if match.odds.source:
        extra.append(f'출처 <b>{esc(match.odds.source)}</b>')

    tag = ' <span class="tossup">백중세</span>' if p.toss_up else ""
    pickline = (f'<div class="pickline">픽(argmax) '
                f'<b class="pk">{esc(p.pick_ko)}</b> — 예상적중률 '
                f'<b>{p.p_pick * 100:.1f}%</b>{tag}</div>')
    return (f'<div class="block"><h4>Pinnacle 시장 기준선 · 보정 확률 (지침 §3-(b) 가산 마진 제거)</h4>'
            f'{bar}{pickline}'
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
    # 맞대결이 하나도 없으면 블록을 내지 않는다. 실물에서 제목만 있는 42바이트
    # 껍데기가 14경기에 전부 붙어 있었다 — 제목만 있는 자리는 '재 봤는데
    # 없다' 처럼 보이는데, 후스코어드 H2H 는 기본으로 꺼져 있어(§3-1) 실제로는
    # 찾아보지도 않은 것이다. 둘을 같은 모양으로 보이게 하지 않는다 (§1-6).
    if not h2h.entries:
        return ""
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


# --------------------------------------------------------------------------
# 경기력 분석 (Phase 2-A 시간축 · 2-B 기회의 질 · 2-C 수비의 질)
#
# 세 축은 진작 계산돼 있었지만 리포트에 나가는 길이 없었다 — `match.analysis`
# 를 읽는 블록이 장소(2-E) · 상대 강도(2-F) · 근거(2-G) 셋뿐이었고, 시즌 초에는
# 그 셋이 전부 표본에 걸려 비어 있다. 실제로 260050 실행에서 2-C 는 28/28팀
# 만들어졌는데 화면에는 한 줄도 나오지 않았다.
#
# **여기서 계산하지 않는다.** 축이 이미 담고 있는 값을 읽어서 놓을 뿐이다.
# 지표를 합치거나 점수로 바꾸지 않고, 승무패를 고르지 않는다 (§1-3).
_AXES_SECTIONS = (
    ("결과", "time_context",
     ("points", "goals", "goals_against", "goal_diff", "xg", "xga",
      "xgd", "npxgd")),
    ("공격 — 기회를 얼마나·어떤 질로 만드나", "chance_quality",
     ("shots", "shots_on_target", "shots_inside_box", "big_chances",
      "xg", "npxg", "xgot", "xg_per_shot", "npxg_per_shot",
      "on_target_rate", "box_shot_share",
      "goals", "goals_minus_xg", "goals_minus_npxg", "goals_minus_xgot")),
    ("수비 — 어떤 기회를 얼마나 허용하나", "defensive_quality",
     ("shots_against", "shots_on_target_against", "shots_inside_box_against",
      "xga", "npxga", "xgot_against", "npxga_per_shot_against",
      "goals_against", "goals_against_minus_npxga",
      "goals_against_minus_xgot_against")),
)

# 부호를 함께 보여 줄 지표. 차이·득실차는 방향(+/−)이 값의 일부다.
# **방향이 좋다/나쁘다는 뜻이 아니다** — 득점−xG 를 '결정력' 으로 읽으면
# 안 된다는 §1-1-8 의 규칙은 그대로다. 여기서는 표시만 한다.
# 트렌드 밴드의 표시 문구. **좋다/나쁘다가 아니라 방향이다** — 밴드를 점수로
# 바꾸거나 여러 지표를 합산하지 않는다는 §1-1-7 의 규칙은 그대로다.
_TREND_KO = {"higher": "높음", "lower": "낮음", "similar": "비슷"}

_AXES_SIGNED = frozenset((
    "goal_diff", "xgd", "npxgd",
    "goals_minus_xg", "goals_minus_npxg", "goals_minus_xgot",
    "goals_against_minus_npxga", "goals_against_minus_xgot_against"))


def _axis_label_fmt(name: str) -> tuple[str, str]:
    """지표 이름 → (표시 라벨, 숫자 서식). 둘 다 `SPECS` 에서 끌어온다.

    라벨과 단위를 render 에 다시 적지 않는다 — 두 곳에 두면 어긋난다.
    """
    from . import analysis

    spec = analysis.SPECS.get(name) or (name, "")
    label = spec[0]
    unit = spec[1] if len(spec) > 1 else ""
    if unit == "%":
        return f"{label} (%)", "{:.0f}"
    if unit == "per_shot":
        return label, "{:.3f}"
    return label, "{:.2f}"


def _axes_table(title: str, attr: str, names, home_team, away_team,
                home_label: str, away_label: str, want: str) -> str:
    """한 갈래(결과·공격·수비)를 홈/원정 나란히 놓은 표. `want` 기간만 낸다.

    값이 양쪽 네 칸 모두 없는 줄은 내지 않는다. 빈 줄을 남기면 '수집은 됐는데
    0 이다' 처럼 보인다 (§1-5).
    """
    def metric(team, period, name):
        axis = getattr(team, attr, None) if team else None
        if axis is None:
            return None
        return axis.metrics.get(f"{period}.{name}")

    def cell(m, fmt, signed, tail=""):
        if m is None or m.value is None:
            return '<td class="num"><span class="nodata">—</span></td>'
        text = fmt.format(m.value)
        if signed and m.value > 0:
            text = "+" + text
        n = "" if m.sample_count is None else f" n={m.sample_count}"
        return f'<td class="num">{esc(text)}<small>{esc(n)}</small>{tail}</td>'

    from . import analysis

    windows = []
    for team in (home_team, away_team):
        axis = getattr(team, attr, None) if team else None
        if axis is not None and axis.requested_matches:
            windows.append(int(axis.requested_matches))
    if not windows:
        return ""
    window = max(windows)

    # **기간마다 표를 따로 낸다.** 한 표에 시즌과 최근을 나란히 두면 두 가지
    # 문제가 생긴다.
    #   · 시즌에 없는 지표(npxG·xGOT·박스 안 슈팅 — §1-1-2)가 많아 실물에서
    #     경기당 42칸이 `—` 였다.
    #   · 나란히 놓는 배치 자체가 '빼서 비교하라' 고 말한다. 두 값은 다른
    #     피드에서 오므로 그 뺄셈은 성립하지 않는다 (§1-1-9).
    # 표 안에서 견주는 축은 **홈 ↔ 원정** 하나뿐이고, 그 비교는 성립한다.
    def trend(team, name, fmt):
        """최근 값 옆에 붙일 '시즌 대비' 꼬리표. 없으면 빈 문자열.

        **2-A 가 이미 계산해 둔 것을 읽을 뿐이다.** 여기서 빼지 않는다 —
        시즌과 최근은 대부분 다른 피드에서 오므로 그 뺄셈이 성립하는지는
        `trend_allowed()` 만 알고, 그 판정 결과가 이 지표의 유무다 (§1-1-9).
        """
        m = metric(team, f"trend{window}", name)
        if m is None or m.value is None:
            return ""
        band = _TREND_KO.get(analysis.parse_trend_band(m), "")
        text = fmt.format(m.value)
        if m.value > 0:
            text = "+" + text
        return f'<small> 시즌 대비 {esc(text)}{" " + band if band else ""}</small>'

    out = ""
    periods = ((analysis.SEASON, "시즌"),) if want == analysis.SEASON else (
        (analysis.period_name(window), f"최근 {window}경기"),)
    for period, span in periods:
        recent = period != analysis.SEASON
        rows = ""
        for name in names:
            cells = [metric(home_team, period, name),
                     metric(away_team, period, name)]
            if all(m is None or m.value is None for m in cells):
                continue
            label, fmt = _axis_label_fmt(name)
            signed = name in _AXES_SIGNED
            tails = ([trend(home_team, name, fmt), trend(away_team, name, fmt)]
                     if recent else ["", ""])
            rows += (f'<tr><td>{esc(label)}</td>'
                     + "".join(cell(m, fmt, signed, tail)
                               for m, tail in zip(cells, tails)) + '</tr>')
        if not rows:
            continue
        out += (f'<div class="tablewrap"><table class="mini"><thead><tr>'
                f'<th>{esc(title)} · {esc(span)}</th>'
                f'<th class="num">{esc(home_label)}</th>'
                f'<th class="num">{esc(away_label)}</th></tr></thead>'
                f'<tbody>{rows}</tbody></table></div>')
    return out


def _axis_notes(teams, attrs, limit: int = 8) -> str:
    """축이 남긴 사유를 한 번만 보여 준다.

    **값이 없으면 이유를 남긴다** 는 §1-1-9·§1-1-10 의 사유는 지금까지
    `AnalysisAxis.notes` 에만 있고 화면 어디에도 나오지 않았다. 그래서
    '시즌 대비' 와 '장소차' 가 왜 없는지 알 수 없었다.

    `_put()` 이 값이 없을 때 **지표를 아예 만들지 않으므로**(§1-1-10) 사유를
    지표의 `note` 에서 찾을 수 없다 — 여기가 유일한 자리다.

    패턴(`패턴 …`)은 다른 블록 소관이라 빼고, 팀 간 중복은 합친다.
    """
    seen, notes = set(), []
    for team in teams:
        for attr in attrs:
            axis = getattr(team, attr, None) if team else None
            for note in (axis.notes if axis else []):
                if note.startswith("패턴 ") or note in seen:
                    continue
                seen.add(note)
                notes.append(note)
    if not notes:
        return ""
    shown, rest = notes[:limit], notes[limit:]
    # 분석 축의 메모에는 강조용 `**…**` 가 섞여 있다. 화면에 처음 나오면서
    # 별표가 그대로 보였다. **해석하지 않고 표시만 걷어낸다** — markdown 을
    # 해석하기 시작하면 §1-11 의 '모델 문장을 해석하지 않는다' 와 어긋나는
    # 선례가 된다. 굵게 만들지 않고 별표만 지운다.
    items = "".join(f"<li>{esc(n.replace('**', ''))}</li>" for n in shown)
    more = f'<li>… 그 밖 {len(rest)}건</li>' if rest else ""
    # `.lbl` 은 `.traits` 안에서만 스타일이 잡혀 있어 여기서는 쓰지 않는다.
    # 제목은 '값이 없는 이유' 가 아니다 — 축의 notes 에는 표본 수 안내와
    # '합치지 마십시오' 같은 주의도 함께 들어 있다. 실물을 보고 고쳤다.
    return (f'<p class="meta">표본·수집 메모 (분석 축이 남긴 것)</p>'
            f'<ul class="mnotes">{items}{more}</ul>')


def _axes_blocks(match: Match) -> tuple[str, str]:
    """(시즌 블록, 최근 블록). **기간마다 따로 낸다.**

    카드가 이 둘을 각자의 차트 **바로 뒤에** 놓는다 — 시즌 표는 다이버징
    바 뒤, 최근 표는 슈팅·xG 프로필 뒤. 차트와 그 표가 떨어져 있으면 대조가
    안 되고, 같은 지표를 두 곳에서 따로 읽게 된다.

    표본 수(n)를 칸마다 적어 적은 표본이 충분해 보이지 않게 한다.
    승무패를 추천하지 않는다.
    """
    from . import analysis

    data = getattr(match, "analysis", None)
    if data is None:
        return "", ""
    home_team = getattr(data, "home", None)
    away_team = getattr(data, "away", None)
    if home_team is None and away_team is None:
        return "", ""

    home_label, away_label = match.home.display, match.away.display
    made = []
    for want, title, hint in (
            (analysis.SEASON, "경기력 분석 · 시즌",
             "순위표와 시즌 통계 피드에서 온 값입니다"),
            ("recent", "경기력 분석 · 최근 경기",
             "슛맵에서 온 값이라 시즌 값과 <b>다른 피드</b>입니다 — 뺄 수 있는 "
             "지표에만 <b>시즌 대비</b>가 붙습니다 · 표의 창은 설정값이고 "
             "실제 표본은 각 칸의 n 입니다")):
        tables = "".join(
            _axes_table(t, attr, names, home_team, away_team,
                        home_label, away_label, want)
            for t, attr, names in _AXES_SECTIONS)
        made.append((tables, title, hint))

    # 메모는 **마지막으로 나오는 블록 하나에만** 붙인다. 두 블록에 같은 목록을
    # 두 번 적으면 근거를 두 번 세는 꼴이 된다.
    notes = _axis_notes((home_team, away_team),
                        ("time_context", "chance_quality",
                         "defensive_quality"))
    last = max((i for i, (t, _, _) in enumerate(made) if t), default=None)

    out = []
    for i, (tables, title, hint) in enumerate(made):
        if not tables:
            out.append("")
            continue
        tail = notes if i == last else ""
        out.append(f'<div class="block"><h4>{esc(title)}</h4>'
                   f'<p class="meta">{hint} · n 은 그 지표의 실제 표본 수 · '
                   f'승무패를 추천하지 않습니다</p>{tables}{tail}</div>')
    return out[0], out[1]


# --------------------------------------------------------------------------
# 홈 ↔ 원정 직접 비교 (Phase 4-D)
#
# 축의 표는 값을 빠짐없이 보여주지만, 두 팀 중 어느 쪽이 큰지는 칸을 눈으로
# 오가며 읽어야 한다. 실물 260050 에서 경기당 그런 칸이 100개를 넘었다.
# 여기서는 **같은 기간·같은 지표**만 골라 마주보는 막대 하나로 놓는다.
#
# **새 값을 만들지 않는다.** 축이 이미 담고 있는 수를 그대로 옮기고,
# 지표를 합치거나 종합 점수로 바꾸지 않는다 (§1-3).
#
# 지표 이름은 여기에 한 번씩만 적는다 — 같은 지표가 두 축에 다 있어도
# (`goals_against` 는 시간축과 수비축에 다 있다) 화면에서 두 번 세면 안 된다.
# 후보를 여덟으로 줄였다 (Phase 4-E §26). 기간마다 값이 있는 것만 그려지므로
# 실제로는 시즌 6줄 · 최근 7줄쯤 나온다 — 상단 요약 계층은 훑을 수 있어야
# 하고, 나머지 지표는 아래 «경기력 분석» 표에 **하나도 빠짐없이** 남아 있다.
#
# 공격과 수비를 짝으로 둔다: 득점↔실점 · xG↔xGA/npxGA · 유효슈팅↔피슈팅.
# `npxg` 는 뺐다 — `xg` 와 거의 같은 이야기다(PK 차이뿐).
_DIRECT_ROWS = (
    ("time_context", "points"),
    ("time_context", "goals"),
    ("chance_quality", "xg"),
    ("chance_quality", "shots_on_target"),
    ("defensive_quality", "goals_against"),
    ("defensive_quality", "xga"),
    ("defensive_quality", "npxga"),
    ("defensive_quality", "shots_against"),
)


def _direct_compare_block(match: Match) -> str:
    """홈 ↔ 원정 직접 비교. 성립하는 비교 하나만 그린다.

    **양쪽 다 값이 있을 때만** 줄을 낸다. 한쪽만 그린 맞대결 막대는 없는
    쪽을 0 처럼 보이게 한다 (§1-5).

    **기간을 섞지 않는다.** 시즌과 최근은 대부분 다른 피드에서 오고, 축마다
    최근 창이 다를 수도 있다. 그래서 기간별로 그림을 나누고, 표본 수가 서로
    다른 지표는 아래에 그대로 적는다.
    """
    from . import analysis

    data = getattr(match, "analysis", None)
    if data is None:
        return ""
    home_team = getattr(data, "home", None)
    away_team = getattr(data, "away", None)
    if home_team is None or away_team is None:
        return ""

    def axis_of(team, attr):
        return getattr(team, attr, None) if team else None

    def window_of(attr: str) -> int:
        found = [int(a.requested_matches)
                 for a in (axis_of(home_team, attr), axis_of(away_team, attr))
                 if a is not None and a.requested_matches]
        return max(found) if found else 0

    rows_by_period: dict[str, list] = {}
    spans: dict[str, str] = {}
    # 표본이 어긋난 지표를 **같은 (기간, 홈 n, 원정 n) 끼리 묶는다.** 두 팀이
    # 치른 경기 수가 다르면 그 기간의 지표가 통째로 어긋나는데, 실물에서
    # 한 줄에 같은 "(홈 n=28 / 원정 n=25)" 가 여섯 번 반복돼 정작 표본이
    # 진짜로 좁은 지표가 묻혔다.
    mismatch: dict[tuple, list[str]] = {}

    for attr, name in _DIRECT_ROWS:
        label, fmt = _axis_label_fmt(name)
        # ↓ 는 레이더와 같은 표시다 — '낮을수록 좋은 지표'. 점의 위치 자체는
        # 좋고 나쁨을 담지 않으므로, 방향은 라벨로만 알린다.
        lower = analysis.SPECS.get(name, ("", "", ""))[2] == analysis.LOWER_BETTER
        window = window_of(attr)
        periods = [(analysis.SEASON, "시즌")]
        if window:
            periods.append((analysis.period_name(window), f"최근 {window}경기"))

        for period, span in periods:
            home_axis, away_axis = axis_of(home_team, attr), axis_of(away_team, attr)
            hm = home_axis.get(f"{period}.{name}") if home_axis else None
            am = away_axis.get(f"{period}.{name}") if away_axis else None
            if hm is None or am is None or hm.value is None or am.value is None:
                continue
            rows_by_period.setdefault(period, []).append(
                {"label": label, "home": hm.value, "away": am.value,
                 "fmt": fmt, "lower_better": lower})
            spans[period] = span
            if (hm.sample_count is not None and am.sample_count is not None
                    and hm.sample_count != am.sample_count):
                mismatch.setdefault(
                    (period, hm.sample_count, am.sample_count), []
                ).append(label + (" ↓" if lower else ""))

    if not rows_by_period:
        return ""

    body = ""
    for period in sorted(rows_by_period, key=analysis.period_sort_key):
        body += (f'<p class="meta">{esc(spans[period])}</p>'
                 + charts.dumbbell(rows_by_period[period],
                                   match.home.display,
                                   match.away.display, width=560))
    lines = []
    for key in sorted(mismatch, key=lambda k: (analysis.period_sort_key(k[0]),
                                               k[1], k[2])):
        period, home_n, away_n = key
        labels = mismatch[key]
        which = (f"지표 {len(labels)}개 전부"
                 if len(labels) == len(rows_by_period.get(period, ()))
                 else " · ".join(labels))
        lines.append(f"{spans[period]} — 홈 n={home_n} / 원정 n={away_n} "
                     f"({which})")
    note = ""
    if lines:
        note = ('<p class="meta">표본 크기가 다른 지표 — 그대로 견줄 때 '
                '주의하십시오: ' + esc(" · ".join(lines)) + '</p>')
    return ('<div class="block"><h4>홈 ↔ 원정 직접 비교</h4>'
            '<p class="meta">같은 기간·같은 지표를 <b>양쪽 다 값이 있을 때만</b> '
            '한 눈금 위에 놓습니다 · 눈금은 줄마다 따로라 다른 줄과 x 위치를 '
            '견줄 수 없습니다 · ↓ 는 낮을수록 좋은 지표 · 표본 수(n)는 아래 '
            '경기력 분석 표에 있고 여기 없는 지표도 거기 전부 남아 있습니다 · '
            '지표를 합쳐 종합 점수를 만들지 않고 승·무·패를 추천하지 '
            '않습니다</p>'
            f'{body}{note}</div>')


_VENUE_ROWS = (
    ("points", "{:.2f}"), ("goals", "{:.2f}"), ("goals_against", "{:.2f}"),
    ("xg", "{:.2f}"), ("npxg", "{:.2f}"), ("xgot", "{:.2f}"),
    ("shots", "{:.1f}"), ("shots_against", "{:.1f}"),
    ("shots_on_target_against", "{:.1f}"), ("npxga", "{:.2f}"),
    ("xgot_against", "{:.2f}"),
)


def _venue_table(axis, venue: str, window: int) -> str:
    """전체 · 장소 · 장소차를 한 표에. 표본 수를 함께 적는다 (2-E §24).

    값이 없으면 `데이터 없음` 으로 적는다 — 빈칸으로 두면 0 과 구별되지
    않는다. 장소차가 없는 줄은 사유를 그대로 보여 준다.
    """
    from . import analysis

    def cell(period, name):
        return axis.get(f"{period}.{name}")

    def num(metric, fmt, sign=False):
        if metric is None or metric.value is None:
            return '<span class="nodata">—</span>', ""
        text = fmt.format(metric.value)
        if sign and metric.value > 0:
            text = "+" + text
        n = "" if metric.sample_count is None else f"n={metric.sample_count}"
        return esc(text), n

    blocks = ((analysis.SEASON, analysis.venue_season_name(venue),
               "시즌"),
              (analysis.period_name(window),
               analysis.venue_period_name(venue, window),
               f"최근 {window}경기"))
    label = analysis.VENUE_LABELS.get(venue, venue)
    out = ""
    for overall_period, venue_period, span in blocks:
        # 장소차 열을 낼지 먼저 본다. 표본이 모자라면 `comparison_allowed`
        # 가 막고, 그때 `_put` 은 **지표를 아예 만들지 않는다** — 사유는
        # `axis.notes` 로 간다(§1-1-10). 그래서 이 열이 통째로 `—` 인 일이
        # 흔한데(실물 260050: 경기당 29칸), 사유 없는 `—` 만 늘어놓으면
        # '재 봤는데 없다' 처럼 보인다. 없으면 열을 빼고, 이유는 블록의
        # 메모 목록에서 한 번 보여 준다.
        gaps = [cell(venue_period, f"{n}{analysis.VENUE_GAP_SUFFIX}")
                for n, _ in _VENUE_ROWS]
        show_gap = any(g is not None and g.value is not None for g in gaps)
        rows = ""
        for name, fmt in _VENUE_ROWS:
            o = cell(overall_period, name)
            v = cell(venue_period, name)
            if o is None and v is None:
                continue
            o_txt, o_n = num(o, fmt)
            v_txt, v_n = num(v, fmt)
            gap_td = ""
            if show_gap:
                gap = cell(venue_period, f"{name}{analysis.VENUE_GAP_SUFFIX}")
                g_txt, _g_n = num(gap, fmt, sign=True)
                gap_td = f'<td class="num">{g_txt}</td>'
            spec = analysis.SPECS.get(name, (name,))
            rows += (f'<tr><td>{esc(spec[0])}</td>'
                     f'<td class="num">{o_txt}<small> {esc(o_n)}</small></td>'
                     f'<td class="num">{v_txt}<small> {esc(v_n)}</small></td>'
                     f'{gap_td}</tr>')
        if not rows:
            continue
        gap_th = '<th class="num">장소차</th>' if show_gap else ""
        out += (f'<table class="mini"><thead><tr>'
                f'<th>{esc(span)}</th><th class="num">전체</th>'
                f'<th class="num">{esc(label)}</th>'
                f'{gap_th}</tr></thead>'
                f'<tbody>{rows}</tbody></table>')
    return out


def _venue_block(match: Match) -> str:
    """홈팀의 홈 문맥 · 원정팀의 원정 문맥 (Phase 2-E).

    승무패를 추천하지 않는다. 같은 장소의 과거 표본을 전체와 나란히 놓을
    뿐이고, 표본 수를 함께 적어 적은 표본이 충분해 보이지 않게 한다.
    """
    from . import analysis

    analysis_data = getattr(match, "analysis", None)
    if analysis_data is None:
        return ""
    cols = ""
    for side, venue, color in (("home", analysis.HOME, charts.C_HOME),
                               ("away", analysis.AWAY, charts.C_AWAY)):
        team = getattr(analysis_data, side, None)
        axis = getattr(team, "venue_context", None) if team else None
        if axis is None or not axis.metrics:
            continue
        window = axis.requested_matches or 0
        table = _venue_table(axis, venue, window) if window else ""
        if not table:
            continue
        marks = [n for n in axis.notes if n.startswith("패턴 ")]
        notes = ("".join(f"<li>{esc(n)}</li>" for n in marks)
                 if marks else "")
        ref = getattr(match, side)
        cols += (f'<div><h5>{_swatch(color)}{esc(ref.display)} — '
                 f'{esc(analysis.VENUE_LABELS[venue])} 문맥</h5>{table}'
                 + (f'<ul>{notes}</ul>' if notes else "") + '</div>')
    if not cols:
        return ""
    # 장소차가 왜 없는지는 지표가 아니라 축의 notes 에 있다 (§1-1-10 —
    # `_put` 이 값 없는 지표를 만들지 않으므로 그것이 유일한 자리다).
    memo = _axis_notes((getattr(analysis_data, "home", None),
                        getattr(analysis_data, "away", None)),
                       ("venue_context",))
    return ('<div class="block"><h4>홈/원정 문맥 (같은 장소의 과거 표본)</h4>'
            '<p class="meta">장소차 = 장소 − 전체 · 같은 지표를 같은 방식으로 '
            '재고 표본만 좁힌 값입니다 · 표본이 모자라 장소차를 만들지 못하면 '
            '그 열이 아예 나오지 않습니다 · n 은 그 지표의 실제 표본 수 · '
            '승무패를 추천하지 않습니다</p>'
            f'<div class="traits">{cols}</div>{memo}</div>')


_SOS_ROWS = (("opponent_points", "{:.2f}"),
             ("opponent_goal_diff", "{:+.2f}"),
             ("opponent_resolved", "{:.0f}"))


def _sos_block(match: Match) -> str:
    """상대 강도 (Phase 2-F). 그 기간의 **상대 구성**만 적는다.

    성과를 보정하지 않고 일정이 유리했다·불리했다고 말하지 않는다. 표본이
    없으면 블록을 통째로 내지 않는다 — 빈 표는 오해를 만든다.
    """
    from . import analysis

    data = getattr(match, "analysis", None)
    if data is None:
        return ""
    cols = ""
    for side, color in (("home", charts.C_HOME), ("away", charts.C_AWAY)):
        team = getattr(data, side, None)
        axis = getattr(team, "schedule_strength", None) if team else None
        if axis is None or not axis.metrics:
            continue
        window = axis.requested_matches or 0
        periods = [(analysis.SEASON, "시즌")]
        if window:
            periods.append((analysis.period_name(window), f"최근 {window}경기"))
            venue = analysis.HOME if getattr(team, "is_home", None) else (
                analysis.AWAY if getattr(team, "is_home", None) is False
                else None)
            if venue:
                periods.append((analysis.venue_period_name(venue, window),
                                f"최근 {window}경기 중 "
                                f"{analysis.VENUE_LABELS[venue]}"))
        rows = ""
        for name, fmt in _SOS_ROWS:
            cells = ""
            found = False
            for period, _label in periods:
                m = axis.get(f"{period}.{name}")
                if m is None or m.value is None:
                    cells += ('<td class="num">'
                              '<span class="nodata">—</span></td>')
                    continue
                found = True
                n = "" if m.sample_count is None else f" n={m.sample_count}"
                cells += (f'<td class="num">{esc(fmt.format(m.value))}'
                          f'<small>{esc(n)}</small></td>')
            if found:
                label = analysis.SPECS.get(name, (name,))[0]
                rows += f'<tr><td>{esc(label)}</td>{cells}</tr>'
        if not rows:
            continue
        head = "".join(f'<th class="num">{esc(l)}</th>' for _p, l in periods)
        ref = getattr(match, side)
        cols += (f'<div><h5>{_swatch(color)}{esc(ref.display)}</h5>'
                 f'<table class="mini"><thead><tr><th>상대</th>{head}</tr>'
                 f'</thead><tbody>{rows}</tbody></table></div>')
    if not cols:
        return ""
    return ('<div class="block"><h4>상대 강도 (그 기간의 상대 구성)</h4>'
            '<p class="meta">상대의 <b>그 경기 이전</b> 성적입니다 · '
            '상대 성적에서 이 팀과의 경기는 뺐습니다 · '
            'n 은 그 지표의 실제 표본 수 · '
            '성과를 보정하거나 일정이 유리했다고 말하지 않습니다</p>'
            f'<div class="traits">{cols}</div></div>')


_CATEGORY_KO = {"attack": "공격", "defense": "수비",
                "sustainability_gap": "실제 ↔ 기대", "result": "결과",
                "schedule": "상대 구성"}
_CONTEXT_KO = {"overall": "시즌 전체", "recent": "최근", "venue": "장소",
               "schedule": "상대"}
# 지지 축은 '같은 사실을 다른 축도 들고 있었다'는 출처 표시다. 축 이름을
# 그대로 내보내면 화면에서 읽히지 않아 한국어 이름을 붙인다.
_AXIS_KO = {"time_context": "시간축", "chance_quality": "기회의 질",
            "defensive_quality": "수비의 질", "sustainability": "지속성",
            "venue_context": "장소 문맥", "schedule_strength": "상대 강도"}


def _evidence_block(match: Match) -> str:
    """근거 (Phase 2-G).

    **개수를 세기로 보여주지 않는다** — 막대·게이지·신뢰도 계기를 만들지
    않고, 지지 지표는 근거 안에 접어 넣는다. 근거가 하나도 없으면 블록을
    통째로 내지 않는다.
    """
    data = getattr(match, "analysis", None)
    items = list(getattr(data, "evidence", None) or []) if data else []
    if not items:
        return ""
    cols = ""
    for side, color in (("home", charts.C_HOME), ("away", charts.C_AWAY)):
        ref = getattr(match, side)
        team = getattr(getattr(data, side, None), "team", "")
        mine = [i for i in items if i.team == team] if team else []
        if not mine:
            continue
        rows = ""
        for item in mine:
            cat = _CATEGORY_KO.get(item.category, item.category)
            ctx = _CONTEXT_KO.get(item.context, item.context)
            n = "" if item.sample_count is None else f" · n={item.sample_count}"
            support = ", ".join(item.supporting_metrics)
            axes = ", ".join(_AXIS_KO.get(a, a)
                             for a in item.supporting_axes)
            axes = f" · 함께 관찰한 축: {esc(axes)}" if axes else ""
            rows += (f'<li><b>{esc(cat)} · {esc(ctx)}</b> {esc(item.claim)}'
                     f'<span class="vs">근거 지표 {esc(support)}{esc(n)}'
                     f'{axes}</span></li>')
        cols += (f'<div><h5>{_swatch(color)}{esc(ref.display)}</h5>'
                 f'<ul class="mnotes">{rows}</ul></div>')
    if not cols:
        return ""
    conflicts = ""
    for sig in (getattr(data, "conflicts", None) or []):
        conflicts += (f'<li>{esc(sig.basis)} — {esc(sig.note)}</li>')
    if conflicts:
        conflicts = (f'<p class="lbl">방향이 엇갈리는 관찰</p>'
                     f'<ul class="mnotes">{conflicts}</ul>')
    return ('<div class="block"><h4>근거 (관찰된 사실)</h4>'
            '<p class="meta">같은 사실은 하나로 묶고 그것을 지지한 지표를 '
            '함께 적었습니다 · <b>근거의 개수는 근거의 세기가 아닙니다</b> · '
            '승무패를 추천하지 않습니다</p>'
            f'<div class="traits">{cols}</div>{conflicts}</div>')


# --------------------------------------------------------------------------
# 패널 (Phase 3-D) — 이미 만들어진 해석을 읽어서 보여줄 뿐이다
# --------------------------------------------------------------------------
# 여기서 값을 계산하지 않는다. 평균·비교·승무패 변환을 하지 않고, 모델이 쓴
# 문장을 escape 해서 그대로 낸다. 문구의 의미를 강화하거나 약화시키지 않는다.
_ROLE_KO = {"data_analyst": "데이터 분석가",
            "matchup_tactical_analyst": "맞대결·전술 분석가"}

# 토론 라운드가 도달한 스코어의 출처. `compromise` 는 두 의견 어느 쪽도
# 처음에 내지 않았고 토론에서 나온 값이다.
_ORIGIN_KO = dict(_ROLE_KO, compromise="양쪽 절충")

# 패널이 실제로 있을 때만 내보낸다. 항상 실으면 `--panel` 없이 돌린 리포트의
# 바이트가 달라져 회귀 기준(데모 HTML sha256)이 깨진다 — 실측으로 확인했다
# (+310 bytes). 새 디자인 체계를 만들지 않고 `.traits`·`.mnotes` 를 그대로
# 쓰므로, 여기 있는 두 줄은 그것으로 안 되는 것만 채운다: 예상 스코어 한 줄과
# 모델이 만든 긴 문장의 줄바꿈.
PANEL_CSS = """
.pscore{font-size:13px;font-weight:700;margin:2px 0 8px;
  font-variant-numeric:tabular-nums}
.ptext{font-size:12.5px;line-height:1.65;margin:0 0 8px;overflow-wrap:anywhere}
.mscore{font-size:20px;font-weight:700;margin:2px 0 4px;
  font-variant-numeric:tabular-nums;letter-spacing:.5px}
"""


def panel_css_for(matches) -> str:
    """패널이 붙은 경기가 하나라도 있으면 그때만 스타일을 싣는다."""
    return PANEL_CSS if any(getattr(m, "panel", None) is not None
                            for m in matches) else ""


def _ptext(text) -> str:
    """모델이 쓴 문장 한 덩이. escape 하고 줄바꿈만 살린다.

    markdown 을 해석하지 않는다 — 모델 출력을 그대로 HTML 로 넣으면 안 된다.
    """
    return esc(text).replace("\n", "<br>")


def _score_line(opinion) -> str:
    """예상 스코어. **승무패로 바꾸지 않는다.**

    두 수를 나란히 적을 뿐이고, 어느 쪽이 크다는 판단을 만들지 않는다.
    한쪽이라도 없으면 줄을 내지 않는다 (0 은 실제 예측이라 다르다).
    """
    home, away = opinion.predicted_home, opinion.predicted_away
    if home is None or away is None:
        return '<p class="pscore"><span class="nodata">예상 스코어 없음</span></p>'
    return f'<p class="pscore">예상 스코어 {esc(home)} : {esc(away)}</p>'


def _opinion_card(opinion, evidence_ids: tuple) -> str:
    rationale = "".join(f'<li>{_ptext(r)}</li>' for r in opinion.rationale)
    cited = ", ".join(esc(e) for e in opinion.evidence_ids)
    # 근거는 **ID 나열**이다. 개수를 세기·별점·신뢰도로 그리지 않는다.
    cite = (f'<span class="vs">인용한 근거 {cited}</span>' if cited
            else '<span class="vs">인용한 근거 없음</span>')
    reasons = f'<ul class="mnotes">{rationale}</ul>' if rationale else ""
    return (f'<div><h5>{esc(_ROLE_KO.get(opinion.role, opinion.role))}</h5>'
            f'{_score_line(opinion)}'
            f'<p class="ptext">{_ptext(opinion.summary)}</p>'
            f'{reasons}'
            f'<p class="ptext">{cite}</p></div>')


def _market_table(market) -> str:
    """시장 기준선. **분석가가 아니다** — 별도 영역에 확률만 적는다."""
    if market is None:
        return ('<p class="lbl">Pinnacle 시장 기준선</p>'
                '<p class="nodata">배당을 가져오지 못해 시장 기준선이 '
                '없습니다.</p>')
    rows = ""
    for label, value in (("홈", market.home_probability),
                         ("무", market.draw_probability),
                         ("원정", market.away_probability)):
        cell = ('<span class="nodata">—</span>' if value is None
                else esc(f"{value * 100:.1f}%"))
        rows += f'<tr><td>{esc(label)}</td><td class="num">{cell}</td></tr>'
    if market.overround is not None:
        rows += (f'<tr><td>오버라운드</td><td class="num">'
                 f'{esc(f"{market.overround:.4f}")}</td></tr>')
    meta = " · ".join(x for x in (market.source, market.as_of) if x)
    return (f'<p class="lbl">Pinnacle 시장 기준선 (외부 참고값 · 분석가가 아닙니다)</p>'
            f'<table class="mini"><tbody>{rows}</tbody></table>'
            + (f'<p class="vs">{esc(meta)}</p>' if meta else ""))


_MODERATOR_ROWS = (("common_points", "공통점"),
                   ("differences", "차이"),
                   ("counterpoints", "반론·제약"),
                   ("uncertainty", "불확실성"))


def _tally_table(result) -> str:
    """토론 라운드가 도달한 스코어의 빈도.

    막대로 그리되 **확률로 읽히지 않게** 그린다 (Phase 4-D). 장치는 둘이고,
    둘 다 문구가 아니라 구조다.

    · 길이를 `simulations` 로 나누지 않는다. 기준은 그 경기 안의 **최댓값**
      이라 1등 막대가 언제나 꽉 찬다 — "30회 중 18회 = 60%" 로 읽을 수가
      없다. 전체 횟수는 `charts.count_bars()` 에 들어가지도 않는다.
    · 라벨은 언제나 횟수다. 백분율·게이지·별점을 만들지 않는다.
    """
    bars = charts.count_bars(
        [{"label": f"{t.home} : {t.away}", "count": t.count,
          "note": _ORIGIN_KO.get(t.origin, t.origin)}
         for t in result.distribution])
    if not bars:
        return ""
    return (f'<p class="lbl">토론 시뮬레이션 {esc(result.simulations)}회의 스코어 분포</p>'
            f'{bars}'
            f'<p class="vs">같은 자료를 서로 다른 축에서 읽었을 때 결론이 '
            f'모인 정도입니다 · 막대는 <b>이 경기에서 가장 많이 나온 스코어</b>를 '
            f'기준으로 한 상대 길이이고 전체 횟수로 나눈 값이 아닙니다 · '
            f'<b>확률이 아닙니다</b></p>')


def _adopted_block(result) -> str:
    """사회자가 정한 최종 예상 스코어.

    **읽어서 놓기만 한다.** 여기서 두 수를 견주지 않고 승/무/패로 바꾸지
    않는다 — 값은 토론 분포에 실제로 나타난 스코어 중 하나다.
    """
    home, away = result.adopted_home, result.adopted_away
    why = (f'<p class="ptext">{_ptext(result.conclusion)}</p>'
           if result.conclusion else "")
    tally = _tally_table(result)
    if home is None or away is None:
        # 0 은 실제 예측이라 다르다. 못 골랐으면 이유가 그 자리를 채운다.
        return ('<p class="lbl">Panel 종합 예상 스코어</p>'
                '<p class="nodata">토론 결과에서 하나를 고를 근거가 자료에 '
                '없었습니다.</p>' + why + tally)
    who = " · ".join(_ROLE_KO.get(r, r) for r in result.adopted_from)
    src = (f'<p class="vs">{esc(who)}의 예상 스코어입니다 '
           f'(평균내지 않습니다)</p>' if who else
           '<p class="vs">두 의견 어느 쪽도 처음에 내지 않은 <b>절충 '
           '스코어</b>입니다 (평균이 아니라 토론에서 나온 값)</p>')
    # §31 — 역할을 이름 옆에 붙여 둔다. '최종 판단'·'정답'·'추천' 이 아니다.
    role = ('<p class="vs">두 분석가의 의견을 <b>사회자가 종합한</b> 예상 '
            '스코어이며 승·무·패 추천이 아닙니다.</p>')
    return (f'<p class="lbl">Panel 종합 예상 스코어</p>'
            f'<p class="mscore">{esc(home)} : {esc(away)}</p>'
            f'{role}{src}{why}{tally}')


def _moderator_block(result) -> str:
    """사회자. 두 의견의 관계와 **채택한 종합 예상 스코어**를 적는다.

    스코어는 사회자가 고른 값을 **그대로** 옮길 뿐이다 — 여기서 평균내거나
    승/무/패로 바꾸지 않는다.
    """
    if result is None:
        return ""
    if not (result.common_points or result.differences):
        return ('<p class="lbl">사회자</p>'
                '<p class="nodata">종합 의견을 만들지 못했습니다. 개별 '
                '분석가 의견은 위에서 그대로 확인할 수 있습니다.</p>')
    seen = ", ".join(_ROLE_KO.get(r, r) for r in result.panels_seen)
    note = ""
    if len(result.panels_seen) < 2:
        note = (f'<p class="vs">분석가 한 명({esc(seen)})의 의견만으로 '
                f'정리한 것입니다.</p>')
    # 사용자가 3단계에서 얻으려는 답이므로 맨 앞에 놓는다.
    parts = _adopted_block(result)
    for field, label in _MODERATOR_ROWS:
        items = getattr(result, field, ()) or ()
        if not items:
            continue
        lis = "".join(f'<li>{_ptext(x)}</li>' for x in items)
        parts += (f'<p class="lbl">{esc(label)}</p>'
                  f'<ul class="mnotes">{lis}</ul>')
    for field, label in (("market_relation", "시장 기준선과의 관계"),):
        text = getattr(result, field, "") or ""
        if text:
            parts += (f'<p class="lbl">{esc(label)}</p>'
                      f'<p class="ptext">{_ptext(text)}</p>')
    shared = ", ".join(esc(e) for e in result.shared_evidence_ids)
    only_a = ", ".join(esc(e) for e in result.data_only_evidence_ids)
    only_b = ", ".join(esc(e) for e in result.matchup_only_evidence_ids)
    used = ""
    for label, ids in (("두 분석가가 함께 인용", shared),
                       ("데이터 분석가만 인용", only_a),
                       ("맞대결·전술 분석가만 인용", only_b)):
        if ids:
            used += f'<li><b>{esc(label)}</b> {ids}</li>'
    if used:
        # 관계만 보여준다 — 공통 근거가 많다고 강한 것이 아니다.
        parts += (f'<p class="lbl">근거 사용 관계</p>'
                  f'<ul class="mnotes">{used}</ul>')
    return f'<p class="lbl">사회자 (두 의견의 종합)</p>{note}{parts}'


def _panel_state(run) -> tuple[str, str]:
    """(상태 낱말, 사유). `PanelRun.status` 는 `"생략 (사유)"` 형식이다.

    **여기서 판정하지 않는다** — 4-B 가 정한 상태를 읽어 옮길 뿐이다
    (`panelimport.status_of`). 실행하지 않은 경기를 "못 골랐다" 로 적으면
    사회자가 하지도 않은 일을 화면이 말하게 된다.
    """
    from . import panelimport

    raw = getattr(run, "status", "") or ""
    reason = raw.split(" (", 1)[1].rstrip(")") if " (" in raw else ""
    state = panelimport.status_of(run)
    return state, (reason if state != panelimport.STATUS_OK else "")


def _score_flow(match: Match) -> str:
    """스코어 흐름 — 데이터 분석가 → 맞대결·전술 분석가 → 사회자 (Phase 4-D).

    **4-C 가 만든 감사 기록을 그대로 읽는다** (`panelaudit.match_audit`).
    화면이 결정 유형을 따로 계산하면 감사 보고서의 결정 유형과 갈라질 수
    있고, 그러면 둘 중 어느 쪽도 믿을 수 없게 된다 (§1-8).

    여기서 두 수를 견주지 않고, 누가 옳았는지 말하지 않는다. 적는 것은
    **무엇을 했는가** 하나뿐이다.
    """
    from . import panelaudit

    run = getattr(match, "panel", None)
    audit = panelaudit.match_audit(match, run)
    if audit is None:
        return ""
    decision_ko = {
        panelaudit.PANEL_SKIPPED: "패널을 실행하지 않았습니다",
        panelaudit.ADOPTED_DATA: "데이터 분석가의 원안을 그대로 채택",
        panelaudit.ADOPTED_MATCHUP: "맞대결·전술 분석가의 원안을 그대로 채택",
        panelaudit.ADOPTED_BOTH: "두 분석가가 같은 원안을 냈고 그것을 채택",
        panelaudit.MODIFIED: "어느 원안도 아닌 값 (수정·절충)",
        panelaudit.NOT_ADOPTED: "채택한 스코어가 없음",
    }
    relation_ko = {panelaudit.SAME_INITIAL: "같음",
                   panelaudit.DIFFERENT_INITIAL: "다름",
                   panelaudit.UNKNOWN_INITIAL: "알 수 없음"}

    _no, da, mu, adopted = audit.row
    rows = ""
    for label, cell in (("데이터 분석가", da),
                        ("맞대결·전술 분석가", mu),
                        ("사회자 채택", adopted)):
        # 없으면 0 으로 채우지 않는다 — 0 은 실제 예측이라 다르다 (§1-5).
        shown = ('<span class="nodata">—</span>' if cell == "—"
                 else esc(cell.replace("-", " : ")))
        rows += f'<tr><td>{esc(label)}</td><td class="num">{shown}</td></tr>'
    return (f'<p class="lbl">스코어 흐름</p>'
            f'<table class="mini"><thead><tr><th>누가</th>'
            f'<th class="num">예상 스코어</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
            f'<p class="vs">처음 두 의견: '
            f'<b>{esc(relation_ko.get(audit.initial_score_relation, ""))}</b> · '
            f'사회자가 한 일: '
            f'<b>{esc(decision_ko.get(audit.decision_type, ""))}</b> — '
            f'누가 옳은지가 아니라 <b>무엇을 했는지</b>입니다</p>')


def _panel_block(match: Match) -> str:
    """패널 분석 (Phase 3-B·3-C 결과).

    `--panel` 없이 돌린 실행에서는 `match.panel` 이 없고, 그때는 블록을
    통째로 내지 않는다 — 기존 리포트가 한 글자도 달라지지 않아야 한다.
    """
    run = getattr(match, "panel", None)
    if run is None:
        return ""

    head = ('<div class="block"><h4>패널 분석 (두 전문가의 해석)</h4>'
            '<p class="meta">두 분석가는 <b>같은 분석 자료</b>를 서로 다른 '
            '관점에서 해석합니다 · 시장 기준선은 분석가가 아니라 외부 '
            '참고값입니다 · <b>승/무/패를 추천하지 않습니다</b></p>')

    if not run.opinions and run.moderator is not None:
        # **사회자 결과만 들어온 경기** (Phase 4-F). 분석가 카드가 없는 것이
        # 사실이므로 빈 카드를 만들지 않고, 그 사실을 화면에 적는다 —
        # 없는 의견을 있었던 것처럼 보이게 하지 않는다.
        _state, reason = _panel_state(run)
        note = (f'<p class="nodata">사회자 결과만 반영했습니다 — 1·2단계 '
                f'분석가 원문은 이번 입력에 포함되지 않았습니다'
                f'{(" · " + esc(reason)) if reason else ""}. 아래 종합은 '
                f'사회자가 낸 것이고, 분석가 각자의 예상 스코어는 '
                f'<b>표시하지 않습니다</b>.</p>')
        return (f'{head}{note}{_market_table(run.market_reference)}'
                f'{_moderator_block(run.moderator)}'
                '<p class="lbl">최종 판단</p>'
                '<p class="ptext">패널 의견과 시장 기준선은 판단에 참고하는 '
                '정보입니다. 최종 승·무·패 선택은 사용자가 직접 합니다.</p>'
                '</div>')

    if not run.opinions:
        state, reason = _panel_state(run)
        # **돌리지 않은 것과 돌렸는데 안 된 것을 같은 말로 적지 않는다**
        # (§1-6). `생략` 은 애초에 실행하지 않은 것이고, `실패` 는 실행했는데
        # 의견이 만들어지지 않은 것이다.
        why = {"생략": "이 경기는 패널 분석을 하지 않았습니다",
               "부분": "패널을 일부만 실행했습니다",
               }.get(state, "분석가 의견을 만들지 못했습니다")
        tail = f" — {esc(reason)}" if reason else ""
        return (f'{head}<p class="nodata">{esc(why)}{tail}. 위의 데이터 분석 '
                f'결과는 그대로 확인할 수 있습니다.</p></div>')

    cards = "".join(_opinion_card(o, run.evidence_ids) for o in run.opinions)
    missing = ""
    for role in sorted(run.role_status):
        state = run.role_status.get(role, "")
        if state and state != "ok":
            # 사유는 사람이 읽을 한 줄만. traceback·프롬프트·키를 내지 않는다.
            missing += (f'<li>{esc(_ROLE_KO.get(role, role))}: '
                        f'{esc(state)}</li>')
    if missing:
        missing = (f'<p class="lbl">실행하지 못한 분석가</p>'
                   f'<ul class="mnotes">{missing}</ul>')

    return (f'{head}<div class="traits">{cards}</div>{_score_flow(match)}{missing}'
            f'{_market_table(run.market_reference)}'
            f'{_moderator_block(run.moderator)}'
            '<p class="lbl">최종 판단</p>'
            '<p class="ptext">패널 의견과 시장 기준선은 판단에 참고하는 '
            '정보입니다. 최종 승·무·패 선택은 사용자가 직접 합니다.</p>'
            '</div>')


def _radar_table(match: Match) -> str:
    """레이더와 **같은 값**을 글자로 (Phase 4-E §45).

    레이더는 값을 SVG `<title>` 로만 알려 주는데, 그건 마우스를 올려야 보이고
    **폰에서는 아예 볼 수 없다.** 색과 위치에만 기대지 않으려면 같은 값이
    글자로도 있어야 한다.

    **여기서 계산하지 않는다** — `Match.radar` 에 이미 들어 있는 값과 백분위를
    옮겨 적을 뿐이다. `상위 N%` 는 레이더 툴팁이 쓰는 것과 같은 표시 방식이다.
    """
    axes = (match.radar or {}).get("axes") or []
    if not axes:
        return '<p class="nodata">리그 백분위를 만들 자료가 없습니다.</p>'

    def cell(axis, side: str) -> str:
        value, pct = axis.get(f"{side}_value"), axis.get(f"{side}_pct")
        if value is None or pct is None:
            return '<td class="num"><span class="nodata">—</span></td>'
        return (f'<td class="num">{esc(charts._fmt(value))}'
                f'<small> 상위 {100 - pct:.0f}%</small></td>')

    rows = ""
    for axis in axes:
        label = esc(axis["label"]) + ("↓" if axis.get("invert") else "")
        # 장소 축은 두 팀이 다른 지표를 본다 — 그 사실을 줄에 적어 둔다.
        note = ""
        if axis.get("home_label") or axis.get("away_label"):
            note = (f'<small> ({esc(axis.get("home_label", ""))} / '
                    f'{esc(axis.get("away_label", ""))})</small>')
        rows += (f'<tr><td>{label}{note}</td>'
                 f'{cell(axis, "home")}{cell(axis, "away")}</tr>')
    return (f'<table class="mini"><thead><tr><th>지표</th>'
            f'<th class="num">{esc(match.home.display)}</th>'
            f'<th class="num">{esc(match.away.display)}</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>')


def _decision_summary(match: Match) -> str:
    """요약 — 이 경기에서 **이미 나온 것**을 한자리에 모은다 (Phase 4-D).

    새로 계산하지 않는다. 시장·패널·분석 축·근거는 각자 아래 블록에 그대로
    있고, 여기서는 그 **끝값만** 옮겨 적는다. 값을 합쳐 종합 점수를 만들지
    않고, 승·무·패를 고르지 않는다 (§1-3).

    자리가 위인 이유는 하나다 — 무엇이 있고 무엇이 **없는지**를 스무 개
    블록을 스크롤한 뒤가 아니라 먼저 알아야 한다. 시즌 초에는 축과 근거가
    통째로 비는 일이 흔한데, 예전에는 그 사실이 끝까지 내려가 봐야 보였다.

    없는 줄은 지우지 않고 **왜 없는지**를 그 자리에 적는다 (§1-5·§1-6).
    """
    rows = []

    p = match.probs
    if p is not None and match.odds.available:
        ph, pd, pa = p.pct()
        tag = ' <span class="tossup">백중세</span>' if p.toss_up else ""
        rows.append(("Pinnacle 시장 기준선",
                     f"승 {ph:.1f}% · 무 {pd:.1f}% · 패 {pa:.1f}%{tag}"))
    else:
        rows.append(("Pinnacle 시장 기준선",
                     '<span class="nodata">배당을 가져오지 못했습니다</span>'))

    # 패널은 `--panel` 없이 돌린 실행에 아예 없다. 그때는 줄을 만들지
    # 않는다 — 없는 단계를 '실패' 처럼 보이게 하면 안 된다 (§1-6).
    run = getattr(match, "panel", None)
    if run is not None:
        from . import panelaudit

        audit = panelaudit.match_audit(match, run)
        state, reason = _panel_state(run)
        _no, da, mu, adopted = audit.row
        if state != "ok":
            rows.append(("Panel 분석",
                         '<span class="nodata">하지 않았습니다 ('
                         + esc(state) + (f' — {esc(reason)}' if reason else "")
                         + ')</span>'))
        elif adopted == "—":
            rows.append(("Panel 종합 예상 스코어",
                         '<span class="nodata">토론 결과에서 하나를 고를 '
                         '근거가 자료에 없었습니다</span>'))
        else:
            who = " · ".join(_ROLE_KO.get(r, r) for r in audit.adopted_from)
            src = (f"{esc(who)}의 예상 스코어 (평균내지 않습니다)" if who
                   else "두 의견 어느 쪽도 처음에 내지 않은 절충 스코어 "
                        "(평균이 아닙니다)")
            rows.append(("Panel 종합 예상 스코어",
                         f"<b>{esc(adopted.replace('-', ' : '))}</b> — {src}"))
        both = " · ".join(
            f"{name} {cell.replace('-', ' : ')}"
            for name, cell in (("데이터", da), ("맞대결", mu))
            if cell != "—")
        if both:
            same = audit.initial_score_relation == panelaudit.SAME_INITIAL
            rows.append(("두 분석가의 처음 의견",
                         f"{esc(both)} — 처음 의견이 "
                         f"{'같았습니다' if same else '달랐습니다'}"))

    data = getattr(match, "analysis", None)
    if data is not None:
        counts = []
        for side, ref in (("home", match.home), ("away", match.away)):
            team = getattr(data, side, None)
            if team is None:
                continue
            counts.append(f"{esc(ref.display)} {len(team.computed_axes())}축")
        if counts:
            rows.append(("계산된 분석 축", " · ".join(counts)))

        items = list(getattr(data, "evidence", None) or [])
        if items:
            per = []
            for side, ref in (("home", match.home), ("away", match.away)):
                team = getattr(getattr(data, side, None), "team", "")
                if not team:
                    continue
                per.append(f"{esc(ref.display)} "
                           f"{len([i for i in items if i.team == team])}건")
            rows.append(("근거", " · ".join(per)
                         + " — 개수는 근거의 세기가 아닙니다"))
        else:
            rows.append(("근거", '<span class="nodata">0건 (근거 생성 게이트 '
                                 '미충족)</span>'))

    # §44 — 전술 정성 자료가 없으면 없다고 적는다. **포메이션·선발·부상·압박
    # 방식을 추정해 채우지 않는다** (§1-12 가 "구조가 막지 못한다" 고 적어 둔
    # 바로 그 항목들이라, 칸을 만들지 않는 것이 가장 확실한 방법이다).
    traits = [len(p.strengths) + len(p.weaknesses) + len(p.style_of_play)
              for p in (match.home_profile, match.away_profile) if p]
    if not traits or not any(traits):
        rows.append(("전술 정성 자료",
                     '<span class="nodata">없음 (WhoScored 강점·약점·스타일 '
                     '미수집) — 포메이션·선발·부상은 이 리포트 어디에도 '
                     '없습니다</span>'))

    body = "".join(f'<tr><td>{esc(label)}</td><td>{value}</td></tr>'
                   for label, value in rows)
    return ('<div class="block"><h4>요약 — 이 경기에서 지금까지 나온 것</h4>'
            '<p class="meta">아래 블록에 이미 있는 값을 한자리에 옮긴 것입니다 · '
            '여기서 새로 계산하거나 합치지 않습니다 · '
            '<b>승·무·패를 추천하지 않습니다</b></p>'
            f'<table class="mini"><tbody>{body}</tbody></table></div>')


def _match_card(match: Match, settings: Settings, report=None) -> str:
    meta = " · ".join(x for x in (match.league_ko or match.league,
                                  match.kickoff_kst) if x)
    notes = ""
    if match.notes:
        notes = ('<div class="notebox">'
                 + "<br>".join(esc(n) for n in match.notes) + "</div>")
    season_axes, recent_axes = _axes_blocks(match)

    return (f'<article class="match" id="m{match.no}">'
            f'<h3><span class="no">{match.no}</span>'
            f'{esc(match.home.display)} <span style="color:var(--text-muted)">vs</span> '
            f'{esc(match.away.display)}</h3>'
            f'<p class="meta">{esc(meta)}</p>'
            f'{_standing_row(match)}'
            f'{notes}'
            f'{_odds_block(match, report)}'
            # 위계는 요약 → 비교 → 패널 → 세부다 (Phase 4-D). 예전에는
            # 카드가 세부부터 시작해서, 무엇이 있고 무엇이 없는지 알려면
            # 열 몇 개 블록을 끝까지 내려가 봐야 했다.
            f'{_decision_summary(match)}'
            # 요약 계층의 두 그림은 **서로 다른 질문**에 답한다 (4-E §70):
            # 레이더는 "리그 안에서 어디쯤", 직접 비교는 "이번 두 팀이 실제
            # 수치로 어떻게 다른가". 예전에는 레이더 옆에 시즌 다이버징 바가
            # 함께 있었는데, 그 바는 직접 비교와 **같은 질문에 같은 수**로
            # 답해서 한 카드에 같은 지표가 세 번 그려졌다(실측 7종). 바는
            # 검증 계층으로 내렸다 — 자기 표(시즌) 바로 앞자리다.
            f'<div class="block"><h4>리그 내 위치 (리그 백분위)</h4>'
            f'<p class="meta">같은 리그 안에서만 줄 세운 값입니다 · '
            f'바깥쪽일수록 상위 · 옆 표에 같은 값을 글자로도 적었습니다 · '
            f'<b>여기서 종합 점수를 만들지 않습니다</b></p>'
            f'<div class="cols3">'
            f'{charts.radar((match.radar or {}).get("axes") or [], match.home.display, match.away.display)}'
            f'{_radar_table(match)}'
            f'</div></div>'
            f'{_direct_compare_block(match)}'
            f'{_panel_block(match)}'
            # ---- 검증 계층 (§62 LEVEL 4) ----
            # 차트와 그 표를 붙여 놓는다. 예전에는 다이버징 바(시즌)와
            # 슈팅·xG 프로필(최근)이 먼저 나오고 대응하는 표가 한참 뒤에
            # 따로 있어, 같은 지표를 두 곳에서 따로 읽어야 했다.
            f'<div class="block"><h4>시즌 지표 비교 (수집한 값 전부)</h4>'
            f'{_compare_inner(match, settings)}</div>'
            f'{season_axes}'
            f'{_recent_block(match, settings)}'
            f'{recent_axes}'
            # 정성(강점/약점·상성)을 정량 바로 뒤에 둔다. 예전에는 카드의
            # 맨 아래(10번째)였는데, 강점/약점이 처음 들어오면서 이 블록이
            # 실제로 값을 갖는 몇 안 되는 자리가 됐다.
            f'{_traits_block(match)}'
            f'{_venue_block(match)}'
            f'{_sos_block(match)}'
            f'{_evidence_block(match)}'
            f'{_form_block(match)}'
            f'{_h2h_block(match)}'
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


def _recent_block(match: Match, settings: Settings) -> str:
    """최근 N경기 표본에서만 나오는 지표 (npxG·xGOT·슈팅·박스 안팎).

    시즌 지표와 **표본이 다르므로** 위 비교표에 섞지 않고 블록을 따로 둔다.
    두 팀의 표본 크기가 다를 수 있어(연기·컵대회) 각 팀의 경기 수를 적는다.
    경기 상세를 건너뛴 실행에서는 값이 없어 블록 전체가 빠진다.
    """
    hp, ap = match.home_profile, match.away_profile
    if hp is None or ap is None:
        return ""
    rows = []
    for metric in settings.recent_metrics:
        hv = getattr(hp.stats, metric["key"], None)
        av = getattr(ap.stats, metric["key"], None)
        if hv is None and av is None:
            continue
        rows.append({"label": metric["label"], "home": hv, "away": av,
                     "fmt": metric.get("fmt", "{:.2f}")})
    if not rows:
        return ""

    hn, an = hp.stats.recent_matches, ap.stats.recent_matches
    if hn and an and hn == an:
        note = f"최근 {hn}경기 평균"
    else:
        note = (f"최근 {hn or 0}경기(홈팀) · {an or 0}경기(원정팀) 평균 "
                f"— 표본 크기가 달라 그대로 비교할 때 주의")
    return (f'<div class="block"><h4>최근 경기 슈팅·xG 프로필</h4>'
            f'<p class="meta">{esc(note)} · 시즌 누계가 아닙니다</p>'
            f'{charts.diverging_bar(rows, match.home.display, match.away.display, width=480)}'
            f'</div>')


def _verdict_box(report: Report) -> str:
    """회차 승산 요약 (지침 §5-(f), §7)."""
    v = report.verdict
    if v is None or not v.n:
        return ('<div class="warnbox">배당률이 없어 회차 승산을 계산할 수 없습니다.'
                '</div>')
    cls = "bet" if v.bet else "pass"
    label = "베팅" if v.bet else "패스"
    warn = ""
    if v.incomplete:
        miss = ", ".join(f"{n}번" for n in v.missing) or "일부"
        warn = (f'<p class="vwarn">⚠️ 배당을 가져오지 못한 경기({miss})가 있어 '
                f'{v.n}경기만으로 계산했습니다. 14경기가 모두 채워지기 전까지 '
                f'이 판정은 참고용입니다.</p>')
    return (f'<div class="verdict {cls}">'
            f'<div class="vhead">회차 승산 <span class="vlab">{label}</span></div>'
            f'<div class="vnums">'
            f'<span>E <b>{v.expected:.2f}</b></span>'
            f'<span>σ <b>{v.sigma:.2f}</b></span>'
            f'<span>z <b>{v.z:+.2f}</b></span>'
            f'<span>P(≥11) <b>{v.p_ge11 * 100:.0f}%</b></span>'
            f'<span class="vex">정확값 {v.p_ge11_exact * 100:.1f}%</span>'
            f'</div>'
            f'<p class="vnote">게이트: P(≥11) ≥ 15% 이면 베팅, 미만이면 패스. '
            f'P(≥11)은 지침 §5-(d)의 정규근사 Φ(z)이며, 괄호의 정확값은 '
            f'포아송 이항 분포로 직접 계산한 참고치입니다.</p>{warn}</div>')


def _tossup_list(matches: list[Match]) -> str:
    """직관 적용 후보 (지침 §7, §9-(1))."""
    items = [m for m in matches if m.probs is not None and m.probs.toss_up]
    if not items:
        return ('<p class="sub" style="color:var(--text-muted);font-size:12.5px">'
                '백중세 경기가 없습니다. 지침 §9 기준으로는 직관 개입의 근거가 '
                '있는 경기가 없다는 뜻입니다.</p>')
    lis = ""
    for m in items:
        p = m.probs
        ph, pd, pa = p.pct()
        lis += (f'<li><b>{m.no}. {esc(m.home.display)} vs {esc(m.away.display)}</b> '
                f'— {ph:.1f}% / {pd:.1f}% / {pa:.1f}% '
                f'(픽 {esc(p.pick_ko)}, 1·2순위 차 {p.gap * 100:.1f}%p)</li>')
    return (f'<ul class="mnotes">{lis}</ul>'
            f'<p class="sub" style="color:var(--text-muted);font-size:12.5px">'
            f'상위 두 결과가 4%p 이내로 붙어 있어, 1순위를 2순위로 바꿔도 '
            f'적중률 손실이 작습니다. 지침 §9 기준 직관을 넣어도 되는 유일한 '
            f'자리입니다. 명확한 정배를 무승부로 바꾸면 P(≥11)이 오히려 '
            f'낮아집니다(§9 함정).</p>')


def _summary_panel(match: Match) -> str:
    """회차 요약 카드의 Panel 줄 (Phase 4-E §39·§64).

    **스코어만 적고 승/무/패 라벨을 만들지 않는다** (§40). `2 : 0` 을 보고
    '홈승' 이라고 읽는 것은 사용자의 판단이고, 그 낱말을 프로그램이 먼저
    적어 주면 그 순간 추천이 된다.

    패널이 없는 실행에서는 줄 자체가 없다 — 없는 단계를 실패처럼 보이게
    하지 않는다 (§1-6).
    """
    run = getattr(match, "panel", None)
    if run is None:
        return ""
    state, _reason = _panel_state(run)
    if state != "ok":
        return f'<div class="pv"><span>Panel 분석 {esc(state)}</span></div>'
    mod = getattr(run, "moderator", None)
    home = getattr(mod, "adopted_home", None)
    away = getattr(mod, "adopted_away", None)
    if home is None or away is None:
        return '<div class="pv"><span>Panel 종합 스코어 없음</span></div>'
    return (f'<div class="pv"><span>Panel 종합 <b>{esc(home)} : '
            f'{esc(away)}</b></span></div>')


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
            f'{bar}{pv}{_summary_panel(m)}</a>')
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

    cards = "".join(_match_card(m, settings, report)
                     for m in report.matches)

    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}{TICKET_CSS}{panel_css_for(report.matches)}</style>
</head><body><div class="wrap" id="top">
<header class="top">
  <h1>⚽ {esc(title)}</h1>
  <p class="sub">경기별 상세 분석 데이터 · 생성 {esc(generated)}</p>
  <div class="badges">{badges}</div>
</header>
{warnings}
{_verdict_box(report)}
<p class="sub" style="color:var(--text-muted);font-size:12.5px;margin:0 0 12px">
  피나클 배당에서 <b>가산(균등) 마진</b>을 제거한 확률입니다(지침 §3-(b)).
  픽 기본값은 각 경기의 최댓값(argmax, §4)이며, 무승부 가중이나 리그 보정 같은
  임의 조정은 하지 않습니다.</p>
{render_ticket(report)}

<h2 class="sec">직관 적용 후보 (백중세)</h2>
{_tossup_list(report.matches)}

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
