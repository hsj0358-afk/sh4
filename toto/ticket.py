"""인터랙티브 단통표 — 픽을 바꿀 때 드는 비용을 즉시 보여준다.

지침 §9 는 직관 개입을 두 자리로만 허용한다.
  (1) 백중세: 상위 두 결과가 4%p 이내 → 바꿔도 손실이 사실상 없음
  (2) 시장 미반영 정보: Veto (§3-d)

문제는 "명분을 찾으러 가면 항상 나온다"는 점이다. 그래서 이 화면은 픽 변경을
막지 않되, **모든 변경의 대가를 P(≥11) 변화로 즉시 환산해 보여준다.**
사용자는 비용을 보고 결정한다.

계산은 브라우저 안에서 끝난다(외부 요청 없음):
  · E = Σ p_pick, σ = √Σ p(1−p), z = (E−10.5)/σ, P(≥11) = Φ(z)   ← 지침 §5
  · 참고로 포아송 이항 정확값도 함께 계산한다(14경기라 정확 계산이 가능).
"""
from __future__ import annotations

import html
import json

from .models import Match, Report

PICK_KO = ["승", "무", "패"]


def _payload(matches: list[Match]) -> list[dict]:
    """브라우저로 넘길 경기별 확률."""
    out = []
    for m in matches:
        p = m.probs
        out.append({
            "no": m.no,
            "home": m.home.display,
            "away": m.away.display,
            "p": [p.home, p.draw, p.away] if p else None,
            "argmax": {"H": 0, "D": 1, "A": 2}[p.pick] if p else None,
            "toss": bool(p.toss_up) if p else False,
            "league": m.league_ko or m.league,
        })
    return out


def render_ticket(report: Report) -> str:
    """단통표 편집 섹션 (HTML + 인라인 JS)."""
    data = _payload(report.matches)
    usable = [d for d in data if d["p"]]
    if not usable:
        return ('<div class="warnbox">배당률이 없어 단통표를 만들 수 없습니다. '
                '경기 시작 전에 다시 실행해 주세요.</div>')

    # </script> 로 문서가 깨지지 않도록 < 를 이스케이프
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")

    rows = ""
    for i, d in enumerate(data):
        name = (f'{html.escape(d["home"])} <span class="vs">vs</span> '
                f'{html.escape(d["away"])}')
        lg = html.escape(d["league"] or "")
        if not d["p"]:
            rows += (f'<tr class="norow"><td class="tno">{d["no"]}</td>'
                     f'<td class="tlg">{lg}</td><td class="tm">{name}</td>'
                     f'<td colspan="3" class="nodata2">배당 없음 — 픽 불가</td>'
                     f'<td class="num">—</td><td class="cost">—</td></tr>')
            continue
        cells = ""
        for r in range(3):
            sel = " sel" if r == d["argmax"] else ""
            cells += (f'<td class="opt{sel}" data-i="{i}" data-r="{r}" '
                      f'role="button" tabindex="0" '
                      f'aria-pressed="{"true" if sel else "false"}">'
                      f'<span class="ol">{PICK_KO[r]}</span>'
                      f'<span class="ov">{d["p"][r] * 100:.1f}%</span></td>')
        tag = '<span class="tossup">백중세</span>' if d["toss"] else ""
        rows += (f'<tr data-row="{i}"><td class="tno">{d["no"]}</td>'
                 f'<td class="tlg">{lg}</td>'
                 f'<td class="tm">{name} {tag}</td>{cells}'
                 f'<td class="num hit" id="hit{i}">'
                 f'{d["p"][d["argmax"]] * 100:.1f}%</td>'
                 f'<td class="cost" id="cost{i}">기본</td></tr>')

    return f"""
<section class="ticket" id="ticket">
  <div class="tkhead">
    <h2 class="sec" style="margin:0">단통표 만들기</h2>
    <button type="button" id="tkreset" class="btn">기본(argmax)으로 되돌리기</button>
  </div>

  <div class="verdict live" id="liveverdict">
    <div class="vhead">현재 티켓 <span class="vlab" id="lvlab">—</span>
      <span class="vdelta" id="lvdelta"></span></div>
    <div class="vnums">
      <span>E <b id="lvE">—</b></span>
      <span>&#963; <b id="lvS">—</b></span>
      <span>z <b id="lvZ">—</b></span>
      <span>P(&#8805;11) <b id="lvP">—</b></span>
      <span class="vex">정확값 <span id="lvPx">—</span></span>
    </div>
    <p class="vnote">칸을 눌러 픽을 바꾸면 회차 승산이 즉시 다시 계산됩니다.
      지침 §5 기준 P(&#8805;11) &#8805; 15% 면 베팅입니다.</p>
  </div>

  <div class="tablewrap">
    <table class="tk">
      <thead><tr><th>No</th><th>리그</th><th>경기</th>
        <th class="num">P(승)</th><th class="num">P(무)</th><th class="num">P(패)</th>
        <th class="num">예상적중률</th><th>변경 비용</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

  <div class="tkfoot">
    <div id="tkchanges" class="changes"></div>
    <div class="tkslip">
      <div class="slabel">최종 단통표</div>
      <code id="tkslip">—</code>
    </div>
  </div>
</section>

<script>
(function () {{
  var M = {blob};
  var KO = ["승", "무", "패"];
  var pick = M.map(function (m) {{ return m.argmax; }});

  // A&S 7.1.26 (오차 ~1.5e-7)
  function erf(x) {{
    var s = x < 0 ? -1 : 1; x = Math.abs(x);
    var t = 1 / (1 + 0.3275911 * x);
    var y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t
              - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
    return s * y;
  }}
  function phi(z) {{ return 0.5 * (1 + erf(z / Math.SQRT2)); }}

  function pbGE(k, ps) {{                       // 포아송 이항 정확값
    var dp = [1];
    for (var i = 0; i < ps.length; i++) {{
      var nx = new Array(dp.length + 1).fill(0);
      for (var j = 0; j < dp.length; j++) {{
        nx[j] += dp[j] * (1 - ps[i]);
        nx[j + 1] += dp[j] * ps[i];
      }}
      dp = nx;
    }}
    var s = 0;
    for (var m = k; m < dp.length; m++) s += dp[m];
    return s;
  }}

  function probsOf(sel) {{
    var out = [];
    for (var i = 0; i < M.length; i++) {{
      if (M[i].p && sel[i] !== null) out.push(M[i].p[sel[i]]);
    }}
    return out;
  }}

  function evaluate(sel) {{
    var ps = probsOf(sel);
    if (!ps.length) return null;
    var E = 0, V = 0;
    for (var i = 0; i < ps.length; i++) {{ E += ps[i]; V += ps[i] * (1 - ps[i]); }}
    var S = Math.sqrt(V);
    var z = S > 0 ? (E - 10.5) / S : 0;
    return {{ n: ps.length, E: E, S: S, z: z, P: phi(z), Px: pbGE(11, ps) }};
  }}

  var baseline = evaluate(M.map(function (m) {{ return m.argmax; }}));

  function fmtPP(x) {{ return (x >= 0 ? "+" : "") + (x * 100).toFixed(1) + "%p"; }}

  function render() {{
    var v = evaluate(pick);
    var box = document.getElementById("liveverdict");
    if (!v) return;

    document.getElementById("lvE").textContent = v.E.toFixed(2);
    document.getElementById("lvS").textContent = v.S.toFixed(2);
    document.getElementById("lvZ").textContent = (v.z >= 0 ? "+" : "") + v.z.toFixed(2);
    document.getElementById("lvP").textContent = (v.P * 100).toFixed(0) + "%";
    document.getElementById("lvPx").textContent = (v.Px * 100).toFixed(1) + "%";

    var bet = v.P >= 0.15;
    document.getElementById("lvlab").textContent = bet ? "베팅" : "패스";
    box.className = "verdict live " + (bet ? "bet" : "pass");

    var d = v.P - baseline.P;
    var el = document.getElementById("lvdelta");
    el.textContent = Math.abs(d) < 1e-9 ? "기본 티켓" : "기본 대비 " + fmtPP(d);
    el.className = "vdelta " + (d < -1e-9 ? "worse" : (d > 1e-9 ? "better" : ""));

    // 경기별 변경 비용
    var changes = [];
    for (var i = 0; i < M.length; i++) {{
      var cell = document.getElementById("cost" + i);
      if (!cell || !M[i].p) continue;
      var hit = document.getElementById("hit" + i);
      if (hit) hit.textContent = (M[i].p[pick[i]] * 100).toFixed(1) + "%";
      if (pick[i] === M[i].argmax) {{
        cell.textContent = "기본";
        cell.className = "cost";
        continue;
      }}
      var dp = M[i].p[pick[i]] - M[i].p[M[i].argmax];   // 경기 적중률 손실
      var only = M.map(function (m) {{ return m.argmax; }});
      only[i] = pick[i];
      var vOnly = evaluate(only);
      var dRound = vOnly.P - baseline.P;
      cell.textContent = fmtPP(dp) + " / 회차 " + fmtPP(dRound);
      cell.className = "cost " + (dp < -0.04 ? "bad" : "warn");
      changes.push({{
        no: M[i].no, home: M[i].home, away: M[i].away,
        from: KO[M[i].argmax], to: KO[pick[i]], dp: dp, dr: dRound,
        toss: M[i].toss
      }});
    }}

    var cbox = document.getElementById("tkchanges");
    if (!changes.length) {{
      cbox.innerHTML = '<p class="cnone">기본(argmax) 티켓 그대로입니다. ' +
        '지침 §4 는 이 상태가 P(&#8805;11)을 최대화한다고 봅니다.</p>';
    }} else {{
      var lis = changes.map(function (c) {{
        var warn = c.toss ? '<span class="tossup">백중세</span>'
          : '<span class="risk">§9 주의 — 백중세가 아닙니다</span>';
        return '<li><b>' + c.no + '. ' + c.home + ' vs ' + c.away + '</b> ' +
          c.from + ' &#8594; ' + c.to + ' ' + warn +
          '<span class="vs2">경기 적중률 ' + fmtPP(c.dp) +
          ' · 이 변경만 반영 시 회차 ' + fmtPP(c.dr) + '</span></li>';
      }}).join("");
      cbox.innerHTML = '<div class="clabel">기본에서 바꾼 경기 ' +
        changes.length + '개</div><ul class="mnotes">' + lis + '</ul>';
    }}

    // 최종 단통표 문자열
    var slip = [];
    for (var k = 0; k < M.length; k++) {{
      slip.push(M[k].no + KO[pick[k] === null ? 0 : pick[k]]);
    }}
    document.getElementById("tkslip").textContent =
      M.every(function (m) {{ return m.p; }})
        ? slip.join("  ") : slip.join("  ") + "   (배당 없는 경기 포함)";
  }}

  function choose(i, r) {{
    if (!M[i].p) return;
    pick[i] = r;
    var row = document.querySelector('tr[data-row="' + i + '"]');
    if (row) {{
      row.querySelectorAll(".opt").forEach(function (td) {{
        var on = +td.dataset.r === r;
        td.classList.toggle("sel", on);
        td.setAttribute("aria-pressed", on ? "true" : "false");
      }});
    }}
    render();
  }}

  document.querySelectorAll(".tk .opt").forEach(function (td) {{
    td.addEventListener("click", function () {{
      choose(+td.dataset.i, +td.dataset.r);
    }});
    td.addEventListener("keydown", function (e) {{
      if (e.key === "Enter" || e.key === " ") {{
        e.preventDefault();
        choose(+td.dataset.i, +td.dataset.r);
      }}
    }});
  }});

  document.getElementById("tkreset").addEventListener("click", function () {{
    for (var i = 0; i < M.length; i++) {{
      if (M[i].p) choose(i, M[i].argmax);
    }}
  }});

  render();
}})();
</script>
"""


TICKET_CSS = """
/* 단통표 편집 (지침 §9) */
.ticket{margin-top:36px}
.tkhead{display:flex;align-items:center;justify-content:space-between;gap:12px;
  flex-wrap:wrap;margin-bottom:10px}
.btn{font:inherit;font-size:12.5px;padding:7px 13px;border-radius:9px;cursor:pointer;
  background:var(--surface-1);color:var(--text-secondary);
  border:1px solid var(--border)}
.btn:hover{border-color:var(--axis);color:var(--text-primary)}
.verdict.live{border-left-color:var(--axis)}
.vdelta{font-size:12px;font-weight:600;color:var(--text-muted)}
.vdelta.worse{color:var(--st-critical)}
.vdelta.better{color:var(--st-good)}

table.tk{width:100%;min-width:820px;border-collapse:collapse;font-size:12.5px;
  background:var(--surface-1);border:1px solid var(--border);border-radius:10px}
table.tk th{text-align:left;font-weight:600;color:var(--text-muted);
  border-bottom:1px solid var(--grid);padding:8px 9px;font-size:11.5px;
  white-space:nowrap}
table.tk th.num{text-align:center}
table.tk td{padding:6px 9px;border-bottom:1px solid var(--grid);
  color:var(--text-secondary);white-space:nowrap}
table.tk tr:last-child td{border-bottom:0}
table.tk td.tno{color:var(--text-muted);font-variant-numeric:tabular-nums}
table.tk td.tlg{color:var(--text-muted);font-size:11.5px}
table.tk td.hit{color:var(--text-primary);font-weight:700}
table.tk td.tm{color:var(--text-primary);white-space:normal;
  overflow-wrap:anywhere;min-width:190px}
table.tk td.tm .vs{color:var(--text-muted);font-weight:400}

td.opt{text-align:center;cursor:pointer;user-select:none;width:74px;
  border-left:1px solid var(--grid)}
td.opt:hover{background:var(--page)}
td.opt:focus-visible{outline:2px solid var(--home);outline-offset:-2px}
td.opt .ol{display:block;font-size:11px;color:var(--text-muted)}
td.opt .ov{display:block;font-variant-numeric:tabular-nums;font-size:12.5px}
td.opt.sel{background:var(--page);box-shadow:inset 0 0 0 2px var(--home)}
td.opt.sel .ol{color:var(--text-primary);font-weight:700}
td.opt.sel .ov{color:var(--text-primary);font-weight:700}

td.cost{font-size:11.5px;color:var(--text-muted);font-variant-numeric:tabular-nums}
td.cost.warn{color:var(--st-warning)}
td.cost.bad{color:var(--st-critical);font-weight:600}
tr.norow td{opacity:.6}
.nodata2{font-style:italic;color:var(--text-muted)}

.tkfoot{margin-top:14px;display:grid;grid-template-columns:1.4fr 1fr;gap:16px}
@media (max-width:760px){.tkfoot{grid-template-columns:1fr}}
.clabel{font-size:12px;font-weight:700;color:var(--text-secondary);margin-bottom:6px}
.cnone{font-size:12.5px;color:var(--text-muted);margin:0}
.changes .vs2{display:block;color:var(--text-muted);font-size:11.5px;margin-top:3px}
.risk{display:inline-block;font-size:10.5px;padding:1px 7px;border-radius:999px;
  background:var(--page);border:1px solid var(--st-critical);
  color:var(--st-critical)}
.tkslip{background:var(--surface-1);border:1px solid var(--border);
  border-radius:10px;padding:12px 14px}
.slabel{font-size:11px;color:var(--text-muted);text-transform:uppercase;
  letter-spacing:.03em;margin-bottom:6px}
.tkslip code{font-size:13px;color:var(--text-primary);line-height:2;
  overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
"""
