"""경기자료 MD — 프로그램과 클로드 채팅 프로젝트 사이의 **공식 인터페이스**
(Phase 4-A).

회차 하나의 분석 결과를 Markdown 파일 **한 장**으로 옮긴다.

    reports/260050_경기자료.md

## 이 모듈이 하는 일과 하지 않는 일

**직렬화 계층이다.** 이미 계산된 값을 읽어 옮겨 적을 뿐, 새 분석값을 만들지
않는다 — 종합점수·percentile·strength score·confidence·승무패 판단·winner
어느 것도 만들지 않는다. 산술 연산이 이 모듈에 없는지 AST 로 검사한다.

`toto/render.py` 가 같은 자료를 HTML 로 옮기는 것과 대응한다. 다른 점은
**읽는 쪽이 사람이 아니라 모델**이라는 것이고, 그래서 두 가지가 다르다.

  · **줄이지 않는다.** HTML 리포트는 사람이 훑을 수 있게 지표를 골라 싣지만
    (`_AXES_SECTIONS` 의 큐레이션 목록), 이 파일은 축에 들어 있는 지표를
    **전부** 낸다. 모델이 필요한 관계를 스스로 고르게 하려면 재료를 줄이면
    안 된다.
  · **메타데이터를 함께 낸다.** 값만 남기면 그 수가 무엇인지 알 수 없다.
    표본 수 · 공통 표본 수 · source · measurement_basis · provenance ·
    방향 · 묶음 · 값이 없는 이유를 한 표 안에 싣는다.

## 왜 JSON 덤프가 아닌가

`panelexport` 가 내는 자료는 `PanelPayload` 를 그대로 직렬화한 JSON 이다.
그쪽은 API 판과 **문자열까지 같아야** 하기 때문에 그 형식을 쓴다(§1-11-1).
이 파일은 그 제약이 없고, 대신 사람도 열어 볼 수 있어야 하므로 의미 단위로
묶은 표로 낸다. 두 경로는 목적이 다르고 서로를 대체하지 않는다.

## 새 값을 만들지 않는다는 것의 구체적 의미

  · 백분위는 **이미 계산돼 있다** — `analyze.build_radar()` 가 리그 안에서
    구해 `Match.radar` 에 넣어 둔다. 여기서는 그것을 읽기만 한다.
  · 경기 상태(예정/종료)는 **시즌 색인의 `finished`** 를 읽는다. 킥오프와
    현재 시각을 비교해 추정하지 않는다.
  · 근거가 없으면 `근거 없음` 이라고 적는다. `E001` 을 지어내지 않는다.
  · 후스코어드 정성 자료가 없으면 없다고 적는다. 포메이션·부상·선발·압박
    방식을 만들어 내지 않는다 (§1-12 가 "구조가 막지 못한다" 고 적어 둔
    바로 그 항목들이다 — 여기서는 애초에 자리를 만들지 않는다).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from .models import (AWAY, DRAW, HOME, MatchAnalysis, Report, TeamAnalysis,
                     find_season_match)
from .settings import ROOT

log = logging.getLogger("toto")

# 시즌 색인에서 이 회차 경기를 찾을 때 허용하는 킥오프 오차.
# `roundlog._SETTLE_WINDOW` 와 같은 값이고 이유도 같다 — 같은 팀 짝이 시즌에
# 두 번 나오므로 날짜로 갈라야 하고, 못 가리면 비워 둔다.
MATCH_WINDOW = timedelta(days=4)

FILENAME = "{round}_경기자료.md"

_AXIS_KO = {
    "time_context": "시간축 (결과·기본 경기력)",
    "chance_quality": "공격 · 기회 창출",
    "defensive_quality": "수비 · 허용한 기회",
    "sustainability": "지속가능성 (실제 ↔ 기대)",
    "venue_context": "홈/원정 문맥",
    "schedule_strength": "상대 강도 (결과 기반)",
}

_PROVENANCE_KO = {"observed": "OBSERVED", "derived": "DERIVED",
                  "model": "MODEL"}

_DIRECTION_KO = {"higher_better": "높을수록",
                 "lower_better": "낮을수록", "": "—"}

_SIDE_KO = {HOME: "홈", DRAW: "무", AWAY: "원정", "NEUTRAL": "중립"}


# ==========================================================================
# 표시 (값을 바꾸지 않는다 — 자릿수만 정한다)
# ==========================================================================
def _num(value, unit: str = "") -> str:
    """숫자 한 칸. **반올림해 새 값을 만드는 것이 아니라 표시 자릿수다.**

    `per_shot` 은 셋째 자리까지 남긴다 — 0.102 와 0.121 이 구분돼야 한다
    (§1-1-15 가 리포트에서 정한 것과 같은 규칙).
    """
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, float):
        return str(value)
    if unit == "per_shot":
        return f"{value:.3f}"
    if unit == "%":
        return f"{value:.1f}"
    return f"{value:.2f}"


def _cell(metric, unit: str = "") -> str:
    """값 + 표본. 표본은 **그 지표의** 수이지 창의 크기가 아니다 (§1-1-2)."""
    if metric is None:
        return "—"
    text = _num(metric.value, unit or metric.unit)
    bits = []
    if metric.sample_count is not None:
        bits.append(f"n={metric.sample_count}")
    if metric.common_sample_count is not None:
        bits.append(f"공통={metric.common_sample_count}")
    return f"{text} ({', '.join(bits)})" if bits else text


def _esc(text) -> str:
    """표 칸에 들어갈 문자열. `|` 만 막으면 표가 깨지지 않는다."""
    return str(text if text is not None else "").replace("|", "\\|").strip()


def _table(header: list[str], rows: list[list[str]], align: str = "") -> str:
    if not rows:
        return ""
    sep = align or ("|" + "|".join("---" for _ in header) + "|")
    lines = ["| " + " | ".join(header) + " |", sep]
    lines += ["| " + " | ".join(_esc(c) for c in r) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def _bullets(items, empty: str = "") -> str:
    items = [x for x in (items or []) if str(x).strip()]
    if not items:
        return f"{empty}\n" if empty else ""
    return "\n".join(f"- {x}" for x in items) + "\n"


# ==========================================================================
# 축 — 지표를 **전부** 내고 메타데이터를 함께 싣는다
# ==========================================================================
def _period_of(key: str) -> tuple[str, str]:
    """`기간.지표` 를 나눈다. 점이 없으면 기간을 모르는 것으로 둔다."""
    return tuple(key.split(".", 1)) if "." in key else ("", key)


def _period_key(period: str) -> tuple:
    """기간 나열 순서. `analysis.period_sort_key` 를 그대로 쓴다.

    자체 정렬 규칙을 새로 만들지 않는다 — 두 곳이 어긋나면 리포트와 이
    파일의 기간 순서가 달라진다 (§1-1-10 이 겪은 사고와 같은 계열).
    """
    from .analysis import period_sort_key
    return period_sort_key(period) if period else (9, 0, "")


def _axis_rows(home_axis, away_axis) -> list[list[str]]:
    """한 축의 모든 지표를 `기간 × 지표` 행으로. **고르지 않는다.**"""
    keys = sorted(set(getattr(home_axis, "metrics", {}) or {})
                  | set(getattr(away_axis, "metrics", {}) or {}),
                  key=lambda k: (_period_key(_period_of(k)[0]),
                                 _period_of(k)[1]))
    rows = []
    for key in keys:
        period, name = _period_of(key)
        hm = (getattr(home_axis, "metrics", {}) or {}).get(key)
        am = (getattr(away_axis, "metrics", {}) or {}).get(key)
        ref = hm or am
        unit = ref.unit or ""
        # 두 팀의 메타데이터는 같은 축·같은 지표라 보통 일치한다. 어긋나면
        # 감추지 않고 둘 다 적는다 — 그 자체가 읽을거리다 (§1-1-9).
        def meta(field: str) -> str:
            hv = getattr(hm, field, "") or ""
            av = getattr(am, field, "") or ""
            if hv and av and hv != av:
                return f"홈 {hv} / 원정 {av}"
            return hv or av or "—"

        rows.append([
            period or "—", ref.label or name,
            _cell(hm, unit), _cell(am, unit),
            unit or "—",
            _DIRECTION_KO.get(ref.direction, ref.direction or "—"),
            ref.group or "—",
            meta("source"), meta("measurement_basis"),
            _PROVENANCE_KO.get(meta("provenance"), meta("provenance")),
        ])
    return rows


_AXIS_HEADER = ["기간", "지표", "홈", "원정", "단위", "방향", "묶음",
                "source", "measurement_basis", "provenance"]


def _axis_block(name: str, home: TeamAnalysis | None,
                away: TeamAnalysis | None) -> str:
    ha = getattr(home, name, None)
    aa = getattr(away, name, None)
    if ha is None and aa is None:
        return (f"#### {_AXIS_KO.get(name, name)}\n\n"
                f"이 축은 만들어지지 않았습니다 (표본 부족 또는 자료 없음). "
                f"자세한 사유는 아래 **데이터 품질** 절을 보십시오.\n\n")
    rows = _axis_rows(ha, aa)
    out = f"#### {_AXIS_KO.get(name, name)}\n\n"
    win = []
    for label, axis in (("홈", ha), ("원정", aa)):
        if axis is None:
            win.append(f"{label}: 축 없음")
            continue
        win.append(f"{label}: 요청 창 {axis.requested_matches if axis.requested_matches is not None else '—'}"
                   f" / 확보 경기 {axis.available_matches if axis.available_matches is not None else '—'}")
    out += " · ".join(win) + "\n\n"
    if rows:
        out += _table(_AXIS_HEADER, rows) + "\n"
    else:
        out += "값이 있는 지표가 없습니다.\n\n"
    notes = []
    for label, axis in (("홈", ha), ("원정", aa)):
        for note in (getattr(axis, "notes", None) or []):
            notes.append(f"[{label}] {note}")
    if notes:
        out += "축 메모 (값이 없는 이유·표본 안내):\n\n" + _bullets(notes) + "\n"
    return out


# ==========================================================================
# 경기 절
# ==========================================================================
def _status_of(match, report: Report) -> tuple[str, object]:
    """(상태 문자열, 시즌 색인 항목).

    상태는 **시즌 색인의 `finished`** 에서만 온다. 킥오프와 지금 시각을
    비교해 추정하지 않는다 — 색인에서 못 찾으면 '확인 불가' 다.
    """
    when = None
    raw = (getattr(match, "kickoff_kst", "") or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            when = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    sm = find_season_match(report.season_matches or [],
                           match.home.canonical, match.away.canonical,
                           when, MATCH_WINDOW)
    if sm is None:
        return "확인 불가 (시즌 색인에서 이 경기를 가리지 못했습니다)", None
    return ("종료" if sm.finished else "예정"), sm


def _basic(match, no: int, report: Report, status: str, sm) -> str:
    rows = [
        ["회차", report.round_id or "—"],
        ["경기 번호", f"{no:02d}"],
        ["match_id (FotMob)", getattr(sm, "match_id", "") or "확인 불가"],
        ["competition (내부 리그 키)", match.league or "—"],
        ["리그", match.league_ko or "—"],
        ["kickoff (KST)", match.kickoff_kst or "—"],
        ["kickoff_raw (시즌 색인)", getattr(sm, "kickoff_raw", "") or "—"],
        ["home_team", match.home.display or "—"],
        ["home_team (정규명)", match.home.canonical or "—"],
        ["home_team_id (FotMob)", match.home.fotmob_id or "—"],
        ["away_team", match.away.display or "—"],
        ["away_team (정규명)", match.away.canonical or "—"],
        ["away_team_id (FotMob)", match.away.fotmob_id or "—"],
        ["match_status", status],
    ]
    if sm is not None and sm.finished and sm.home_goals is not None:
        rows.append(["실제 결과", f"{sm.home_goals} : {sm.away_goals}"])
    if not match.home.matched or not match.away.matched:
        rows.append(["팀명 매칭", "실패한 팀이 있습니다 — 지표가 비어 있을 수 있습니다"])
    return _table(["항목", "값"], rows) + "\n"


def market_absence_reason(status: str) -> str:
    """배당이 없을 때 **왜 없는지**. 셋을 구분한다 (§1-6).

    HTML 리포트(`render._odds_block`)와 경기자료 MD 가 **같은 문장**을 쓴다
    (Phase 4-E §42·§53) — 두 곳에 따로 적으면 한쪽만 고쳐져 같은 경기가 두
    화면에서 다른 이유를 말하게 된다.
    """
    if status == "종료":
        return ("현재 배당 스냅샷 없음 — 경기가 이미 종료되어 시장이 "
                "닫혔습니다 (수집 실패가 아닙니다)")
    if status == "예정":
        return "예정 경기인데 배당을 가져오지 못했습니다 (수집 실패)"
    return ("배당 없음 — 경기 상태를 가리지 못해 수집 실패인지 "
            "시장이 닫힌 것인지 판별할 수 없습니다")


def _market(match, status: str) -> str:
    """시장 기준선. **여기서 favorite·픽을 만들지 않는다.**"""
    odds, probs = match.odds, match.probs
    out = ""
    if not odds.available:
        return f"{market_absence_reason(status)}\n\n"
    rows = [["source", odds.source or "—"],
            ["as_of (수집 시각)", odds.fetched_at or "—"],
            ["승 (decimal)", _num(odds.home)],
            ["무 (decimal)", _num(odds.draw)],
            ["패 (decimal)", _num(odds.away)]]
    for label, line, a, b in (("아시안 핸디캡", odds.ah_line, odds.ah_home,
                               odds.ah_away),
                              ("오버/언더", odds.ou_line, odds.ou_over,
                               odds.ou_under)):
        if line is not None:
            rows.append([f"{label} 라인", _num(line)])
            rows.append([f"{label} (홈/오버)", _num(a)])
            rows.append([f"{label} (원정/언더)", _num(b)])
    out += _table(["항목", "값"], rows) + "\n"
    if probs is not None:
        out += _table(
            ["내재확률 (마진 제거)", "값"],
            [["승", f"{probs.home * 100:.1f}%"],
             ["무", f"{probs.draw * 100:.1f}%"],
             ["패", f"{probs.away * 100:.1f}%"],
             ["오버라운드", _num(probs.overround)],
             ["옵션당 마진", _num(probs.margin_per_option)]])
        out += ("\n시장은 **외부 기준선**이며 분석가가 아닙니다. 이 확률에서 "
                "추천이나 favorite 를 만들지 마십시오.\n\n")
    return out


def _standings(match) -> str:
    """리그 내 위치. 순위표 원값 + 이미 계산된 리그 백분위."""
    out = ""
    rows = []
    fields = [("rank", "순위"), ("played", "경기"), ("wins", "승"),
              ("draws", "무"), ("losses", "패"), ("goals_for", "득점"),
              ("goals_against", "실점"), ("goal_diff", "득실차"),
              ("points", "승점"), ("home_played", "홈 경기"),
              ("home_points", "홈 승점"), ("home_goals_for", "홈 득점"),
              ("home_goals_against", "홈 실점"), ("away_played", "원정 경기"),
              ("away_points", "원정 승점"), ("away_goals_for", "원정 득점"),
              ("away_goals_against", "원정 실점"),
              ("xg_total", "시즌 xG 누계"), ("xga_total", "시즌 xGA 누계"),
              ("xg_played", "xG 표본 경기")]
    hs = getattr(match.home_profile, "stats", None)
    as_ = getattr(match.away_profile, "stats", None)
    for key, label in fields:
        hv = getattr(hs, key, None)
        av = getattr(as_, key, None)
        if hv is None and av is None:
            continue
        rows.append([label, _num(hv), _num(av)])
    if rows:
        out += _table(["순위표 항목", "홈", "원정"], rows) + "\n"
    else:
        out += "순위표 자료가 없습니다.\n\n"

    axes = (match.radar or {}).get("axes") or []
    if axes:
        out += ("리그 내 백분위 — `analyze.build_radar()` 가 **같은 리그 안에서** "
                "이미 계산해 둔 값입니다. 여기서 다시 계산하지 않았습니다.\n\n")
        out += _table(
            ["축", "홈 값", "홈 백분위", "원정 값", "원정 백분위", "방향"],
            [[a.get("label", a.get("key", "")),
              _num(a.get("home_value")),
              _num(a.get("home_pct")),
              _num(a.get("away_value")),
              _num(a.get("away_pct")),
              "낮을수록 좋음" if a.get("invert") else "높을수록 좋음"]
             for a in axes]) + "\n"
    else:
        out += "리그 내 백분위 자료가 없습니다.\n\n"
    return out


def _evidence(analysis: MatchAnalysis | None) -> str:
    """근거. **없으면 없다고 적는다 — ID 를 지어내지 않는다.**"""
    items = list(getattr(analysis, "evidence", None) or []) if analysis else []
    if not items:
        return ("근거 없음 (Evidence generation gate: not met).\n\n"
                "2-G 의 패턴 게이트가 표본 부족으로 성립하지 않았습니다. "
                "**근거 ID 를 지어내지 마십시오** — 이 경기에서 인용할 수 있는 "
                "ID 는 하나도 없습니다.\n\n")
    rows = []
    for i, e in enumerate(items, start=1):
        rows.append([
            f"E{i:03d}", e.team or "—", e.category or "—", e.context or "—",
            e.period or "—", e.finding_kind or "—", e.claim or "—",
            e.metric or "—", _num(e.value),
            "—" if e.sample_count is None else e.sample_count,
            e.source or "—", e.measurement_basis or "—",
            _PROVENANCE_KO.get(e.provenance, e.provenance or "—"),
            _SIDE_KO.get(e.side, e.side or "—"),
        ])
    out = _table(["id", "팀", "category", "context", "기간", "finding",
                  "claim", "지표", "값", "n", "source", "basis",
                  "provenance", "side"], rows) + "\n"
    extra = []
    for i, e in enumerate(items, start=1):
        if e.supporting_metrics or e.supporting_axes:
            extra.append(f"E{i:03d} — 지지 지표: "
                         f"{', '.join(e.supporting_metrics) or '—'} / 지지 축: "
                         f"{', '.join(e.supporting_axes) or '—'}")
    if extra:
        out += ("근거를 지지한 지표·축입니다. **개수가 근거의 세기가 "
                "아닙니다.**\n\n" + _bullets(extra) + "\n")
    return out


def _quality(analysis: MatchAnalysis | None) -> str:
    """데이터 품질. 축별 available / 사유를 그대로 옮긴다."""
    blocks = []
    for label, holder in (("경기 전체", getattr(analysis, "data_quality", None)),
                          ("홈", getattr(getattr(analysis, "home", None),
                                         "data_quality", None)),
                          ("원정", getattr(getattr(analysis, "away", None),
                                           "data_quality", None))):
        if holder is None or not holder.axes:
            continue
        rows = []
        for key in sorted(holder.axes):
            v = holder.axes[key] or {}
            rows.append([key,
                         "예" if v.get("available") else "아니오",
                         _num(v.get("requested")),
                         _num(v.get("available_matches")),
                         _num(v.get("coverage")),
                         v.get("degraded_reason") or "—"])
        blocks.append(f"**{label}**\n\n" + _table(
            ["축.기간", "available", "requested", "available_matches",
             "coverage", "degraded_reason"], rows))
        if holder.notes:
            blocks.append(_bullets(holder.notes))
    if not blocks:
        return "데이터 품질 기록이 없습니다.\n\n"
    return "\n".join(blocks) + "\n"


def _conflicts(analysis: MatchAnalysis | None) -> str:
    signals = list(getattr(analysis, "conflicts", None) or []) if analysis else []
    if not signals:
        return ""
    return ("방향이 엇갈린 신호입니다 (2-G 가 이미 찾아 둔 것). **개수를 세거나 "
            "상쇄하지 마십시오.**\n\n" + _table(
                ["지표", "lean", "표본", "provenance", "설명", "메모"],
                [[s.name or "—", s.lean or "—",
                  "—" if s.sample_count is None else s.sample_count,
                  _PROVENANCE_KO.get(s.provenance, s.provenance or "—"),
                  s.basis or "—", s.note or "—"] for s in signals]) + "\n")


def _h2h(match) -> str:
    h2h = match.h2h
    if not h2h.entries:
        return ("H2H: unavailable — 맞대결 자료가 없습니다. "
                "새로 계산하거나 추정하지 마십시오.\n\n")
    out = (f"홈 {h2h.home_wins}승 · 무 {h2h.draws} · 원정 "
           f"{h2h.away_wins}승 (총 {h2h.total}경기)\n\n")
    return out + _table(
        ["날짜", "홈", "원정", "스코어", "대회"],
        [[e.date or "—", e.home_team or "—", e.away_team or "—",
          f"{e.home_goals}-{e.away_goals}", e.competition or "—"]
         for e in h2h.entries]) + "\n"


def _tactical(match) -> str:
    """후스코어드 정성 자료. **없으면 없다고만 적는다.**

    포메이션·선발·부상·압박 방식·감독 성향은 이 프로그램이 수집하지 않는다.
    자리를 만들지 않는 것이 그것을 지어내지 않는 가장 확실한 방법이다.
    """
    out = ""
    have = False
    for label, profile in (("홈", match.home_profile),
                           ("원정", match.away_profile)):
        if profile is None:
            continue
        rows = []
        for name, items in (("강점", profile.strengths),
                            ("약점", profile.weaknesses),
                            ("플레이 스타일", profile.style_of_play)):
            if items:
                rows.append([name, " · ".join(items)])
                have = True
        if profile.rest_days is not None:
            rows.append(["직전 경기 이후 휴식일", str(profile.rest_days)])
            have = True
        if rows:
            out += f"**{label} — {profile.team.display}**\n\n" + _table(
                ["항목", "내용"], rows) + "\n"
    if match.matchup_notes:
        out += ("상성 노트 (한쪽 강점 ↔ 상대 약점 교차 대조):\n\n" + _table(
            ["주제", "쪽", "강점", "상대 약점", "설명"],
            [[n.get("topic", "—"),
              {"home": "홈", "away": "원정"}.get(n.get("side"), "—"),
              n.get("strength", "—"), n.get("weakness", "—"),
              n.get("text", "—")]
             for n in match.matchup_notes]) + "\n")
        have = True
    if not have:
        out = ("Tactical qualitative data: unavailable — 후스코어드 정성 자료가 "
               "없습니다.\n\n")
    out += ("이 프로그램은 **포메이션 · 선발 명단 · 선수 · 부상 · 압박 방식 · "
            "감독 성향을 수집하지 않습니다.** 자료에 없는 것을 아는 것처럼 "
            "쓰지 마십시오.\n\n")
    return out


def _match_section(match, no: int, report: Report) -> str:
    status, sm = _status_of(match, report)
    analysis = match.analysis
    home = getattr(analysis, "home", None)
    away = getattr(analysis, "away", None)

    axes = ("축마다 **기간 × 지표**로 폅니다. 홈과 원정이 한 행에 나란히 "
            "있는 것이 곧 직접 비교이고, 같은 기간·같은 지표·같은 산출 "
            "방식일 때만 한 행에 놓입니다.\n\n"
            "`n` 은 **그 지표에** 값이 있던 경기 수이고 창의 크기가 "
            "아닙니다. `공통` 은 두 값이 다 있던 경기 수로 차이 지표에만 "
            "붙습니다.\n\n")
    if analysis is None:
        axes += "분석 결과가 없습니다 (Phase 2 를 실행하지 않았습니다).\n\n"
    else:
        for name in TeamAnalysis.AXES:
            axes += _axis_block(name, home, away)
        model = getattr(analysis, "model", None)
        if model is not None:
            rows = _axis_rows(model, None)
            axes += ("#### 모델 산출 (xPTS · 독립 포아송)\n\n"
                     "**모델값입니다.** 시장 확률(위 시장 기준선)과 합치거나 "
                     "서로 보정하지 마십시오 — 저쪽은 시장이 매긴 값이고 "
                     "이쪽은 경기내용에서 만든 모델값입니다.\n\n")
            axes += (_table(_AXIS_HEADER, rows) if rows
                     else "값이 없습니다.\n") + "\n"

    # 절 번호는 **실제로 나가는 절만** 세어 붙인다. 없는 절의 번호를 건너뛰면
    # 읽는 쪽이 빠진 절을 찾게 된다.
    parts = [
        ("경기 기본정보", _basic(match, no, report, status, sm)),
        ("시장 기준선", _market(match, status)),
        ("리그 내 위치", _standings(match)),
        ("경기력 분석 (Phase 2 축)", axes),
        ("근거 (Evidence)", _evidence(analysis)),
    ]
    conflicts = _conflicts(analysis)
    if conflicts:
        parts.append(("방향이 엇갈린 신호", conflicts))
    parts += [("데이터 품질", _quality(analysis)),
              ("상대전적 (H2H)", _h2h(match)),
              ("정성 자료 (후스코어드)", _tactical(match))]
    if match.notes:
        parts.append(("경기 메모", _bullets(match.notes) + "\n"))

    out = f"## 경기 {no:02d}. {match.home.display} vs {match.away.display}\n\n"
    for i, (title, body) in enumerate(parts, start=1):
        out += f"### {no:02d}-{i}. {title}\n\n{body}"
    return out + "---\n\n"


# ==========================================================================
# 회차 머리말
# ==========================================================================
_HOWTO = """\
### 0-3. 이 문서를 읽는 법

이 파일은 프로그램이 **이미 계산한 값을 옮겨 적은 것**입니다. 새로 계산된
수는 하나도 없습니다.

숫자와 함께 붙는 메타데이터의 뜻:

| 칸 | 뜻 |
|---|---|
| `n` | **그 지표에** 값이 있던 경기 수. 창의 크기가 아닙니다 |
| `공통` | 두 값이 **다 있던** 경기 수. 차이 지표에만 붙습니다 |
| `기간` | `season` · `recent6` · `home5` 처럼 어느 구간인가 |
| `source` | 어느 피드에서 왔나 (`standings` · `shotmap` · `match_stats` …) |
| `measurement_basis` | 그 피드에서 **어떻게** 만들어졌나 |
| `provenance` | OBSERVED(관측) · DERIVED(계산) · MODEL(모델 산출) |
| `방향` | 값이 클수록 좋은가. `—` 는 **정하지 않았다**는 뜻입니다 |
| `묶음` | 같은 이야기를 하는 지표 무리. 같은 사실을 여러 번 세지 않기 위한 것 |

**`source` 와 `measurement_basis` 가 다르면 두 수를 직접 빼지 마십시오.**
실물에서 겪은 사고가 있습니다 — 어떤 팀의 시즌 xG 는 경기 스탯 값이고 최근
xG 는 슛맵을 합산한 값이라, **같은 한 경기**인데도 0.06 이 달랐습니다. 그
차이를 "최근이 시즌보다 높다" 고 읽으면 측정 방식의 차이를 경기력 변화로
둔갑시킨 것이 됩니다.

**값이 `—` 인 것은 0 이 아닙니다.** 계산하지 못했다는 뜻이고, 이유는 축
메모나 데이터 품질 절에 있습니다.

다음은 이 자료에 **들어 있지 않습니다.** 아는 것처럼 쓰지 마십시오.

- 포메이션 · 선발 명단 · 선수 개인 · 부상 · 출장 정지
- 압박 방식 · 감독 성향 · 전술 지시
- 날씨 · 경기장 상태 · 심판

"""


def _round_head(report: Report) -> str:
    matches = report.matches
    statuses = [_status_of(m, report)[0] for m in matches]
    counts = {s: statuses.count(s) for s in sorted(set(statuses))}
    with_odds = sum(1 for m in matches if m.odds.available)
    with_analysis = sum(1 for m in matches if m.analysis is not None)
    with_evidence = sum(1 for m in matches
                        if getattr(m.analysis, "evidence", None))

    out = (f"# 축구토토 승무패 {report.round_id or '(회차 미상)'}회차 경기자료\n\n"
           "이 파일은 프로그램의 분석 결과를 **한 장으로 직렬화한 것**입니다. "
           "여기에 새로 계산된 수는 없습니다.\n\n"
           "### 0-1. 회차 기본정보\n\n")
    out += _table(["항목", "값"], [
        ["회차", report.round_id or "—"],
        ["생성 시각", report.generated_at or "—"],
        ["경기 수", len(matches)],
        ["경기 상태", " · ".join(f"{k} {v}경기" for k, v in counts.items())
         or "—"],
        ["배당이 있는 경기", f"{with_odds}/{len(matches)}"],
        ["Phase 2 분석이 붙은 경기", f"{with_analysis}/{len(matches)}"],
        ["근거가 생성된 경기", f"{with_evidence}/{len(matches)}"],
        ["시즌 경기 색인", f"{len(report.season_matches or [])}경기"],
    ]) + "\n"

    out += "### 0-2. 데이터 수집 상태\n\n"
    if report.source_status:
        out += _table(["소스", "상태"],
                      [[k, v] for k, v in sorted(report.source_status.items())])
        out += ("\n상태 어휘는 넷입니다 — `ok`(정상) · `부분`(일부만) · "
                "`실패 (사유)`(수집 자체가 안 됨) · `생략`(조회하지 않음). "
                "**`실패` 와 `생략` 은 다릅니다.**\n\n")
    else:
        out += "수집 상태 기록이 없습니다.\n\n"
    if report.warnings:
        out += "회차 경고:\n\n" + _bullets(report.warnings) + "\n"
    if with_evidence == 0 and matches:
        out += ("> **이 회차에는 근거(Evidence)가 한 건도 없습니다.** 2-G 의 "
                "패턴 게이트가 표본 부족으로 성립하지 않았습니다(시즌 초에는 "
                "정상입니다). 근거 ID 를 지어내지 말고 축 지표를 표본 수와 "
                "함께 밝히십시오.\n\n")
    out += _HOWTO
    out += "---\n\n"
    return out


# ==========================================================================
# 실행
# ==========================================================================
def build(report: Report) -> str:
    """경기자료 MD 전문. 경기 순서는 **회차 순서 그대로**다."""
    out = _round_head(report)
    for i, match in enumerate(report.matches, start=1):
        # 회차 순서를 지킨다. `match.no` 가 있으면 그것이 공식 번호다.
        out += _match_section(match, match.no or i, report)
    return out


def export(report: Report, settings=None, outdir: Path | None = None) -> str:
    """파일로 낸다. 상태 문자열을 돌려준다 (§1-6)."""
    if not report.matches:
        return "생략 (경기 없음)"
    round_id = report.round_id or "unknown"
    base = Path(outdir) if outdir is not None else (
        settings.output_dir if settings is not None else ROOT / "reports")
    path = Path(base) / FILENAME.format(round=round_id)
    text = build(report)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 한국어 윈도우에서도 안전하게 열리도록 UTF-8 로 고정한다.
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        return f"실패 ({exc})"
    return (f"ok ({len(report.matches)}경기 → {path}, "
            f"{len(text.encode('utf-8')) / 1024:.0f}KB)")
