"""브리핑 JSON → 마크다운 / 이메일용 HTML 렌더링."""
from __future__ import annotations

import html

from .analyzer import CATEGORY_ORDER, CATEGORY_TITLES

PRESS_LINE = "조선·중앙·동아·매일경제·한국경제·전자신문"
IMP_BADGE = {"high": "🔴 중요", "med": "🟡 참고", "low": "⚪ 일반"}
IMP_COLOR = {"high": "#d93025", "med": "#f29900", "low": "#9aa0a6"}


def _items(briefing: dict, key: str) -> list:
    return briefing.get("categories", {}).get(key, []) or []


def count_items(briefing: dict) -> int:
    return sum(len(_items(briefing, k)) for k in CATEGORY_ORDER)


# --------------------------------------------------------------------------
# 마크다운
# --------------------------------------------------------------------------
def to_markdown(briefing: dict) -> str:
    date = briefing.get("date", "")
    out = [f"# 📰 아침 신문 브리핑 — {date}",
           f"> 대상: {PRESS_LINE}", ""]

    summary = briefing.get("headline_summary") or []
    if summary:
        out.append("## 🔑 오늘의 핵심")
        out += [f"- {s}" for s in summary]
        out.append("")

    for ci, key in enumerate(CATEGORY_ORDER, start=1):
        items = _items(briefing, key)
        title = CATEGORY_TITLES[key]
        out.append(f"## {ci}. {title}")
        if not items:
            out.append("_해당 기사 없음_\n")
            continue
        for it in items:
            imp = it.get("importance", "low")
            badge = IMP_BADGE.get(imp, "")
            press = it.get("press", "")
            head = it.get("headline", "(제목 없음)")
            out.append(f"### {head}  `[{press}]` {badge}")
            if it.get("summary"):
                out.append(it["summary"])
            if key == "HRD" and it.get("detail"):
                out.append("")
                out.append(f"> {it['detail']}")
            if it.get("talking_point"):
                out.append(f"- 💬 **부서장 언급 포인트:** {it['talking_point']}")
            if it.get("url"):
                out.append(f"- 🔗 [기사 링크]({it['url']})")
            out.append("")
    out.append("---")
    out.append("_본 브리핑은 네이버뉴스 지면보기 기사를 자동 수집·요약한 것입니다._")
    return "\n".join(out)


# --------------------------------------------------------------------------
# HTML (이메일용, 인라인 스타일)
# --------------------------------------------------------------------------
def _esc(s: str) -> str:
    return html.escape(s or "")


def to_html(briefing: dict) -> str:
    date = briefing.get("date", "")
    parts = [f"""<div style="font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
max-width:760px;margin:0 auto;color:#202124;line-height:1.6">
<h1 style="font-size:22px;border-bottom:3px solid #1a73e8;padding-bottom:8px">
📰 아침 신문 브리핑 <span style="color:#5f6368;font-size:16px">— {_esc(date)}</span></h1>
<p style="color:#5f6368;font-size:13px;margin-top:-4px">대상: {PRESS_LINE}</p>"""]

    summary = briefing.get("headline_summary") or []
    if summary:
        lis = "".join(f"<li>{_esc(s)}</li>" for s in summary)
        parts.append(f"""<div style="background:#f1f3f4;border-radius:8px;padding:12px 18px;margin:16px 0">
<div style="font-weight:700;margin-bottom:6px">🔑 오늘의 핵심</div>
<ul style="margin:0;padding-left:20px">{lis}</ul></div>""")

    for ci, key in enumerate(CATEGORY_ORDER, start=1):
        items = _items(briefing, key)
        title = CATEGORY_TITLES[key]
        parts.append(f'<h2 style="font-size:18px;margin-top:26px;color:#1a73e8">'
                     f'{ci}. {_esc(title)}</h2>')
        if not items:
            parts.append('<p style="color:#9aa0a6;font-size:14px">해당 기사 없음</p>')
            continue
        for it in items:
            imp = it.get("importance", "low")
            color = IMP_COLOR.get(imp, "#9aa0a6")
            badge = IMP_BADGE.get(imp, "")
            press = _esc(it.get("press", ""))
            head = _esc(it.get("headline", "(제목 없음)"))
            block = [f'<div style="border-left:4px solid {color};padding:6px 0 6px 14px;margin:14px 0">',
                     f'<div style="font-weight:700;font-size:15px">{head} '
                     f'<span style="color:#5f6368;font-weight:400;font-size:13px">[{press}]</span> '
                     f'<span style="font-size:12px;color:{color}">{badge}</span></div>']
            if it.get("summary"):
                block.append(f'<div style="font-size:14px;margin-top:4px">{_esc(it["summary"])}</div>')
            if key == "HRD" and it.get("detail"):
                block.append(f'<div style="font-size:13px;color:#3c4043;background:#f8f9fa;'
                             f'border-radius:6px;padding:8px 12px;margin-top:6px">'
                             f'{_esc(it["detail"])}</div>')
            if it.get("talking_point"):
                block.append(f'<div style="font-size:13px;margin-top:6px">'
                             f'💬 <b>부서장 언급 포인트:</b> {_esc(it["talking_point"])}</div>')
            if it.get("url"):
                block.append(f'<div style="font-size:13px;margin-top:4px">'
                             f'🔗 <a href="{_esc(it["url"])}" style="color:#1a73e8">기사 링크</a></div>')
            block.append("</div>")
            parts.append("".join(block))

    parts.append('<hr style="margin-top:28px;border:none;border-top:1px solid #e0e0e0">')
    parts.append('<p style="color:#9aa0a6;font-size:12px">본 브리핑은 네이버뉴스 '
                 '지면보기 기사를 자동 수집·요약한 것입니다.</p></div>')
    return "\n".join(parts)
