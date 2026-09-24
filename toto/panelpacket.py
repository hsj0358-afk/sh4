"""역할별 compact packet (Phase 6-F-10) — **Python 이 고르고 Claude 는 분석만 한다.**

6-F-9 가 세션을 셋으로 줄였지만 A·B 는 여전히 회차 원본 전체를 받았다 —
실측 **1,746,547자 ≈ 836,470토큰**을 두 번. 이 모듈이 그 사이에 결정적
전처리 계층을 넣는다.

    PanelPayload 14개  →  build_panel_index()  →  PanelIndex
                       →  build_analyst_packet(role)  →  compact packet
                       →  packet_text()  →  stdin 한 번

## 새 통계를 만들지 않는다

**고르고 다시 배열할 뿐이다.** 값을 더하거나 나누거나 순위를 매기지 않고,
`strength_score`·`balance_index` 같은 파생값을 만들지 않는다 (AST 테스트).
packet 에 들어가는 모든 수는 `PanelPayload` 에 이미 있던 그 수이고, 모든
문자열은 이미 있던 그 문자열이다.

## 줄어드는 이유는 **버려서가 아니라 반복을 걷어내서**다

실측이 설계를 정했다 (260052 · 14경기).

| | |
|---|---|
| 지표 칸 | 8,910개 |
| 고유 지표 키 | 252개 |
| 고유 메타(label·unit·source·basis·provenance) | **57개** — 평균 156회 반복 |
| 고유 `degraded_reason` | **4개** (1,092칸에) |
| 고유 축 notes 문장 | 411개 (99,030자) |

그래서 **반복되는 문자열을 legend 로 올리고 본문은 그것을 가리킨다.**
`json.loads` 로 되돌리면 같은 사실이 그대로 나온다 — 한 칸도 버리지 않는다.

    "season.goals": {"label":"득점","value":1.5,"n":3,"unit":"per_match",
                     "source":"standings","basis":"final_score",
                     "provenance":"observed"}        ← 170자

    "season.goals": [1.5, 3, 12]                     ← 27자
                     └ legend.metric["12"] 이 나머지를 들고 있다

**지표 키는 본문에 그대로 남긴다.** 분석가가 실제로 추론하는 것은
`recent10.xg` 같은 키이고, legend 로 올리는 것은 **표시·출처 메타데이터**
뿐이다 — 근거를 인용할 때 필요하지만 추론에는 쓰이지 않는다.

## 원본을 버리지 않는다

`PanelPayload` 도 회차 자료 시트(`panelexport.data_sheet()`)도 그대로
있다. 이 모듈은 읽기만 하고, packet 은 **파생물**이라 artifact 에 저장되지
않는다.

## Evidence 는 통째로 보존한다

근거는 ID·claim·metric·value·n·source·basis·supporting_* 가 **전부** 간다.
줄이지 않는 이유는 그것이 분석가가 인용해야 하는 계약이기 때문이다
(§1-9 불변조건 3). `panel.parse_opinion()` 이 packet 에 없는 ID 를 거부하므로,
여기서 한 건이라도 빠뜨리면 그 경기가 통째로 실패한다.

## 역할별 view

`ROLE_VIEWS` 가 역할마다 실을 칸을 정한다. **오늘 다른 것은 하나뿐이다** —
`qualitative`(정성 특성·관계)는 맞대결 분석가에게만 간다. 데이터 분석가의
역할 프롬프트는 그 칸을 한 번도 언급하지 않고("관측된 **수치**만"), 맞대결
분석가의 프롬프트는 그것을 중심으로 쓰여 있다.

**§1-9 불변조건 2 가 지키려는 것은 그대로다.** 그 조항이 말하는 것은
"역할별 payload 를 만들면 두 의견이 **비교 불가능**해진다" 이고, 비교되는
것은 정량 사실이다. 그래서 **정량 본체(축 지표·근거·data_quality·시장
기준선·legend)가 두 역할에서 바이트까지 같다**는 것을 테스트로 고정한다 —
조항의 실질을 더 좁고 검사 가능한 형태로 옮긴 것이다.

바꾸려면 `ROLE_VIEWS` 한 줄이다. 실측 기여가 0.9% 라 크기 때문에 나눈 것이
아니라 역할 분리 때문에 나눴다.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import panel
from .models import Report

# ==========================================================================
# 상수
# ==========================================================================
# 파서 판. **바뀌면 캐시를 버린다** (§18) — 같은 원본에서 다른 packet 이
# 나오는데 옛 packet 을 읽으면 조용히 낡은 자료를 보낸다 (§1-4 와 같은 이유).
PACKET_VERSION = "1"

# 캐시 자리. 저장소 안이지만 **에이전트 작업 폴더가 아니다** — 여기는
# Python 만 읽고 쓰고, Claude 는 이 경로를 모른다.
CACHE_DIRNAME = "panel_cache"
MANIFEST_FILE = "source_manifest.json"
INDEX_FILE = "index.json"
STATS_FILE = "stats.json"
PACKET_FILES = {panel.DATA_ANALYST: "analyst_a_packet.json",
                panel.MATCHUP_ANALYST: "analyst_b_packet.json"}

# 실측 자/토큰 비. **어림에만 쓴다** — 이 값으로 자료를 자르거나 요약하지
# 않는다.
#
#   원본 payload   2.088 자/토큰   (6-F-8 분석 · 한국어 JSON)
#   역할별 packet  1.819 자/토큰   (6-F-10 실호출 · 597,146자 → 328,326토큰)
#
# **packet 이 더 조밀하다.** legend 로 접으면 한국어 문장이 빠지고 숫자·
# 괄호·짧은 키가 남기 때문이다. 원본 비율(2.088)을 그대로 쓰면 packet 을
# **15% 적게** 잡아 문맥 여유를 실제보다 넉넉히 보고하게 된다 — 한 번의
# 실호출로 잰 값을 그대로 쓴다.
CHARS_PER_TOKEN = 2.088
PACKET_CHARS_PER_TOKEN = 1.819

# 축 본문의 칸 이름. `PanelPayload` 의 `_axis_summary()` 가 만드는 모양이다.
AXIS_METRICS = "metrics"
AXIS_NOTES = "notes"

# 지표 메타의 칸. **이 다섯이 legend 로 올라간다.**
METRIC_META = ("label", "unit", "source", "basis", "provenance")

# 역할별로 실을 최상위 칸. **정량 본체는 두 역할에 같다** (모듈 설명 참고).
_CORE = ("match_no", "league", "home_team", "away_team", "kickoff_kst",
         "as_of", "home", "away", "evidence", "conflicts", "data_quality",
         "market_reference")
ROLE_VIEWS = {
    panel.DATA_ANALYST: _CORE,
    panel.MATCHUP_ANALYST: _CORE + ("qualitative",),
}

# **의심스럽게 작으면 멈춘다** (§32). 토큰이 줄었다는 것 자체를 성공으로
# 치지 않는다 — 자료를 잘못 잘라 분석이 불가능해진 것과 구분이 안 된다.
MIN_PACKET_RATIO = 0.05             # 원본의 5% 미만이면 의심한다
PACKET_TOO_SMALL = "PACKET_SUSPICIOUSLY_SMALL"

_JSON = dict(ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _dump(obj) -> str:
    return json.dumps(obj, **_JSON)


def estimate_tokens(text: str, ratio: float = CHARS_PER_TOKEN) -> int:
    """**예상값**이다. 실제 토큰은 실행 봉투의 `usage` 에만 있다 (§17)."""
    return int(len(text or "") / (ratio or CHARS_PER_TOKEN))


# ==========================================================================
# 색인 — **분석 결과가 아니라 위치·필드 view 다** (§6)
# ==========================================================================
@dataclass
class MatchEntry:
    """경기 하나. `payload` 는 원본 `PanelPayload` 를 그대로 들고 있다."""
    match_no: int = 0
    home: str = ""
    away: str = ""
    kickoff_kst: str = ""
    payload: "panel.PanelPayload | None" = None
    body: dict = field(default_factory=dict)        # 직렬화된 원본
    evidence_ids: tuple = ()
    sections: dict = field(default_factory=dict)    # 칸 이름 → source path

    @property
    def source_paths(self) -> tuple:
        return tuple(sorted(self.sections))


@dataclass
class PanelIndex:
    """회차 하나의 색인. **원본을 복사해 들고 있을 뿐 고치지 않는다.**"""
    round_id: str = ""
    entries: list = field(default_factory=list)

    @property
    def matches(self) -> int:
        return len(self.entries)

    def by_no(self, no: int):
        for e in self.entries:
            if e.match_no == no:
                return e
        return None

    def source_text(self) -> str:
        """원본 payload 를 canonical 직렬화로 이어 붙인 것. **기준선**이다.

        `panelexport.data_sheet()` 의 채팅용 머리글은 빼고 잰다 — 그것은
        분석 자료가 아니라 첨부 안내문이다 (§10).
        """
        return "\n".join(_dump(e.body) for e in self.entries)


def build_panel_index(report: Report) -> PanelIndex:
    """회차 → 색인. **새 파서를 만들지 않는다.**

    `panel.build_panel_payload()` 와 `panel.serialize_payload()` 를 그대로
    쓴다 — 채팅 경로·API 경로가 쓰는 바로 그 함수다 (§1-8). 회차 자료 시트의
    `<panel_payload no="N">` 를 다시 파싱하지 않는 이유가 이것이다: 그 시트도
    같은 함수에서 만들어지므로, 텍스트로 되읽으면 같은 값을 두 번 해석하는
    경로가 생긴다.
    """
    out = PanelIndex(round_id=str(report.round_id or ""))
    for match in report.matches:
        payload = panel.build_panel_payload(match)
        body = json.loads(panel.serialize_payload(payload))
        sections = {}
        for key in sorted(body):
            sections[f"payload[{payload.match_no}].{key}"] = key
            if key in ("home", "away") and isinstance(body[key], dict):
                for axis in sorted(body[key]):
                    sections[f"payload[{payload.match_no}].{key}.{axis}"] = \
                        f"{key}.{axis}"
        out.entries.append(MatchEntry(
            match_no=payload.match_no,
            home=payload.home_team, away=payload.away_team,
            kickoff_kst=payload.kickoff_kst,
            payload=payload, body=body,
            evidence_ids=tuple(payload.evidence_ids),
            sections=sections))
    return out


# ==========================================================================
# legend — **반복되는 문자열을 한 번만 싣는다.** 버리는 것이 아니다
# ==========================================================================
class _Legend:
    """같은 문자열·같은 메타 묶음에 번호를 매긴다. 순서는 **처음 만난 순**."""

    def __init__(self):
        self.metric: dict = {}
        self.note: dict = {}
        self.reason: dict = {}

    @staticmethod
    def _id(table: dict, key):
        if key not in table:
            table[key] = len(table)
        return table[key]

    def metric_id(self, meta: tuple) -> int:
        return self._id(self.metric, meta)

    def note_id(self, text: str) -> int:
        return self._id(self.note, text)

    def reason_id(self, text: str) -> int:
        return self._id(self.reason, text)

    def to_dict(self) -> dict:
        return {
            "metric": {str(i): dict(zip(METRIC_META, t))
                       for t, i in sorted(self.metric.items(),
                                          key=lambda kv: kv[1])},
            "note": {str(i): t for t, i in sorted(self.note.items(),
                                                  key=lambda kv: kv[1])},
            "reason": {str(i): t for t, i in sorted(self.reason.items(),
                                                    key=lambda kv: kv[1])},
        }


# 읽는 법. **자료가 아니라 형식 설명이라 짧게 적는다** (§10).
HOW_TO_READ = {
    "metric": "지표는 [값, 표본수(n), legend.metric 번호] 입니다. "
              "n 이 null 이면 표본 수가 기록되지 않은 값입니다.",
    "notes": "축의 notes 는 legend.note 번호 목록입니다.",
    "data_quality": "[사용 가능 여부, 확보 경기, 요청한 창, "
                    "legend.reason 번호 또는 null] 입니다.",
    "evidence": "근거는 원본 그대로입니다. evidence_ids 에는 여기 있는 "
                "id 만 적으십시오.",
}


def _pack_axis(body: dict, legend: _Legend) -> dict:
    """축 하나. 지표는 배열로, notes 는 번호로 — **값은 그대로다.**"""
    metrics = {}
    for key in sorted(body.get(AXIS_METRICS) or {}):
        m = body[AXIS_METRICS][key]
        meta = tuple(m.get(name) for name in METRIC_META)
        metrics[key] = [m.get("value"), m.get("n"), legend.metric_id(meta)]
    out = {AXIS_METRICS: metrics}
    notes = [legend.note_id(t) for t in (body.get(AXIS_NOTES) or [])]
    if notes:
        out[AXIS_NOTES] = notes
    return out


def _pack_side(side: dict, legend: _Legend) -> dict:
    out = {}
    for name in sorted(side):
        body = side[name]
        if isinstance(body, dict) and AXIS_METRICS in body:
            out[name] = _pack_axis(body, legend)
        else:
            out[name] = body
    return out


def _pack_quality(quality: dict, legend: _Legend) -> dict:
    """`data_quality` — 네 칸을 배열로 접는다. 사유 문자열은 legend 로."""
    out = {}
    for team in sorted(quality):
        axes = quality[team] or {}
        rows = {}
        for key in sorted(axes):
            cell = axes[key] or {}
            reason = cell.get("degraded_reason") or ""
            rows[key] = [cell.get("available"),
                         cell.get("available_matches"),
                         cell.get("requested"),
                         legend.reason_id(reason) if reason else None]
        out[team] = rows
    return out


# ==========================================================================
# 역할별 packet
# ==========================================================================
def build_analyst_packet(index: PanelIndex, role: str) -> dict:
    """역할 하나의 compact packet. **14경기 전부가 들어간다** (§15).

    경기를 나누지 않는다 — 나누면 세션이 늘어나고 그것은 6-F-9 가 없앤
    구조다 (§33).
    """
    if role not in ROLE_VIEWS:
        raise ValueError(f"모르는 역할: {role}")
    fields = ROLE_VIEWS[role]
    legend = _Legend()
    rows = []
    for entry in index.entries:
        body = entry.body
        row = {}
        for key in fields:
            if key not in body:
                continue
            value = body[key]
            if key in ("home", "away"):
                row[key] = _pack_side(value or {}, legend)
            elif key == "data_quality":
                row[key] = _pack_quality(value or {}, legend)
            elif value or value == 0:
                row[key] = value
        rows.append(row)
    return {
        "round": index.round_id,
        "matches": len(rows),
        "packet_version": PACKET_VERSION,
        "how_to_read": HOW_TO_READ,
        "legend": legend.to_dict(),
        "data": rows,
    }


def build_analyst_a_packet(index: PanelIndex) -> dict:
    """데이터 분석가용 (§7)."""
    return build_analyst_packet(index, panel.DATA_ANALYST)


def build_analyst_b_packet(index: PanelIndex) -> dict:
    """맞대결·전술 분석가용 (§8)."""
    return build_analyst_packet(index, panel.MATCHUP_ANALYST)


def packet_text(packet: dict) -> str:
    """stdin 으로 나갈 문자열. compact JSON 이다 (§9 — 실측으로 골랐다)."""
    return _dump(packet)


# ==========================================================================
# 되읽기 — **legend 를 풀면 원본이 나온다**는 것을 검사할 수 있어야 한다
# ==========================================================================
def expand_metric(cell, legend: dict) -> dict:
    """packet 의 지표 한 칸 → 원본 모양. 테스트와 감사가 쓴다."""
    value, n, mid = cell
    meta = (legend.get("metric") or {}).get(str(mid)) or {}
    out = {"value": value, "n": n}
    out.update(meta)
    return out


# ==========================================================================
# 측정 (§4) — **목표 토큰 수를 코드에 박지 않는다**
# ==========================================================================
def measure(index: PanelIndex) -> dict:
    """원본과 역할별 packet 의 크기. 전부 **실측**이고 목표값이 없다."""
    source = index.source_text()
    out = {"round": index.round_id, "matches": index.matches,
           "source_chars": len(source),
           "source_tokens": estimate_tokens(source), "roles": {}}
    for role in ROLE_VIEWS:
        text = packet_text(build_analyst_packet(index, role))
        chars = len(text)
        out["roles"][role] = {
            "chars": chars,
            "tokens": estimate_tokens(text, PACKET_CHARS_PER_TOKEN),
            "reduction": (1 - chars / len(source)) if source else 0.0,
        }
    return out


def report_lines(stats: dict) -> list:
    """사람이 읽을 요약 (§26·§34). 없는 값을 지어내지 않는다."""
    lines = [f"[Retrieval] {stats['round']} · {stats['matches']}경기",
             f"  source: {stats['source_chars']:,} chars / "
             f"~{stats['source_tokens']:,} tokens (예상)"]
    for role in ROLE_VIEWS:
        row = stats["roles"].get(role) or {}
        if not row:
            continue
        ko = panel.ROLE_KO.get(role, role)
        lines.append(f"  {ko} packet: {row['chars']:,} chars / "
                     f"~{row['tokens']:,} tokens (예상) · "
                     f"reduction {100 * row['reduction']:.1f}%")
    return lines


def too_small(stats: dict) -> list:
    """**줄어든 것 자체를 성공으로 치지 않는다** (§32). 사유 목록을 준다."""
    out = []
    for role, row in (stats.get("roles") or {}).items():
        if not stats.get("source_chars"):
            continue
        ratio = row["chars"] / stats["source_chars"]
        if ratio < MIN_PACKET_RATIO:
            out.append(
                f"{PACKET_TOO_SMALL}: {panel.ROLE_KO.get(role, role)} packet 이 "
                f"원본의 {100 * ratio:.1f}% 입니다 (최소 "
                f"{100 * MIN_PACKET_RATIO:.0f}%) — 자료가 잘렸는지 "
                f"확인하십시오")
    return out


# ==========================================================================
# 감사 (§20·§21·§22) — **무엇이 빠졌는지 추적할 수 있어야 한다**
# ==========================================================================
def _paths(obj, prefix: str, out: set) -> None:
    if isinstance(obj, dict):
        for k in obj:
            _paths(obj[k], f"{prefix}.{k}" if prefix else str(k), out)
    elif isinstance(obj, list):
        out.add(prefix)
    else:
        out.add(prefix)


def _restore(key: str, value, legend: dict):
    """packet 의 한 칸을 **원본 모양으로 되푼다.** 감사가 쓴다.

    접힌 것을 빠진 것으로 세면 보고서가 거짓이 된다 — 실제로 첫 판에서
    `data_quality` 가 통째로 '빠졌다' 고 나왔다.
    """
    if key in ("home", "away"):
        out = {}
        for axis, body in (value or {}).items():
            if isinstance(body, dict) and AXIS_METRICS in body:
                out[axis] = {
                    AXIS_METRICS: {k: expand_metric(c, legend)
                                   for k, c in body[AXIS_METRICS].items()},
                    AXIS_NOTES: [legend["note"][str(i)]
                                 for i in body.get(AXIS_NOTES, [])]}
            else:
                out[axis] = body
        return out
    if key == "data_quality":
        out = {}
        for team, rows in (value or {}).items():
            out[team] = {}
            for name, cell in rows.items():
                available, got, requested, rid = cell
                out[team][name] = {
                    "available": available, "available_matches": got,
                    "requested": requested,
                    "degraded_reason": ("" if rid is None
                                        else legend["reason"][str(rid)])}
        return out
    return value


def audit(index: PanelIndex, role: str) -> dict:
    """원본과 packet 을 견준다. (§22 의 '삭제된 필드 보고서')

    packet 이 legend 로 접혀 있으므로 **되풀어서** 비교한다 — 접힌 것을
    빠진 것으로 세면 보고서가 거짓이 된다.
    """
    packet = build_analyst_packet(index, role)
    legend = packet["legend"]
    fields = ROLE_VIEWS[role]

    src_paths, out_paths = set(), set()
    ev_src, ev_out = set(), set()
    for entry, row in zip(index.entries, packet["data"]):
        no = entry.match_no
        for key in sorted(entry.body):
            _paths(entry.body[key], f"[{no}].{key}", src_paths)
        # 근거는 **경기마다 다시 매겨지므로**(§1-15) 경기 번호와 함께 센다 —
        # ID 만 모으면 14경기의 E001 이 한 건으로 뭉쳐 보존률이 부풀려진다.
        ev_src.update((no, i) for i in entry.evidence_ids)
        for key in sorted(row):
            _paths(_restore(key, row[key], legend), f"[{no}].{key}", out_paths)
        ev_out.update((no, e["id"]) for e in (row.get("evidence") or ()))

    omitted = sorted(p for p in src_paths - out_paths)
    kinds = sorted({p.split(".")[1] for p in omitted if "." in p})
    return {
        "role": role,
        "fields": list(fields),
        "source_paths": len(src_paths),
        "packet_paths": len(out_paths),
        "omitted_paths": len(omitted),
        "omitted_kinds": kinds,
        "omitted_sample": omitted[:20],
        "added_paths": sorted(out_paths - src_paths)[:20],
        "evidence_source": len(ev_src),
        "evidence_packet": len(ev_out),
        "evidence_missing": sorted(ev_src - ev_out),
        "evidence_invented": sorted(ev_out - ev_src),
    }


def audit_lines(report: dict) -> list:
    ko = panel.ROLE_KO.get(report["role"], report["role"])
    lines = [f"[Retrieval audit] {ko}",
             f"  source fields: {report['source_paths']:,}",
             f"  packet fields: {report['packet_paths']:,}",
             f"  omitted: {report['omitted_paths']:,}"
             + (f" ({', '.join(report['omitted_kinds'])})"
                if report["omitted_kinds"] else ""),
             f"  evidence: {report['evidence_packet']}/"
             f"{report['evidence_source']} 보존"]
    if report["evidence_missing"]:
        lines.append(f"  ⚠ 빠진 근거 {report['evidence_missing'][:5]}")
    if report["evidence_invented"]:
        lines.append(f"  ⚠ 원본에 없는 근거 {report['evidence_invented'][:5]}")
    return lines


# ==========================================================================
# 캐시 (§18·§19) — **속도와 토큰을 위한 것이지 의미를 바꾸지 않는다**
# ==========================================================================
def cache_dir(round_id: str, base: Path | None = None) -> Path:
    from .settings import ROOT
    root = Path(base) if base is not None else ROOT
    return root.joinpath(CACHE_DIRNAME, str(round_id or "unknown"))


def source_manifest(index: PanelIndex) -> dict:
    """무엇으로 만들어졌나. **판이 다르면 다시 만든다.**"""
    digest = hashlib.sha256(
        index.source_text().encode("utf-8")).hexdigest()[:16]
    return {"round": index.round_id, "matches": index.matches,
            "source_sha256_16": digest,
            "source_chars": len(index.source_text()),
            "parser_version": PACKET_VERSION,
            "panel_prompt_version": panel.PANEL_PROMPT_VERSION}


def write_cache(index: PanelIndex, base: Path | None = None) -> Path:
    """색인·packet·측정값을 남긴다. **LLM 산출물은 담지 않는다** (§19)."""
    out = cache_dir(index.round_id, base)
    out.mkdir(parents=True, exist_ok=True)
    stats = measure(index)

    def _write(name: str, obj) -> None:
        path = out / name
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(_dump(obj), encoding="utf-8")
        os.replace(tmp, path)

    _write(MANIFEST_FILE, source_manifest(index))
    _write(INDEX_FILE, {"round": index.round_id, "matches": [
        {"match_no": e.match_no, "home": e.home, "away": e.away,
         "kickoff_kst": e.kickoff_kst, "evidence_ids": list(e.evidence_ids),
         "source_sections": list(e.source_paths)} for e in index.entries]})
    for role, name in PACKET_FILES.items():
        _write(name, build_analyst_packet(index, role))
    _write(STATS_FILE, stats)
    return out


__all__ = [
    "PACKET_VERSION", "CACHE_DIRNAME", "MANIFEST_FILE", "INDEX_FILE",
    "STATS_FILE", "PACKET_FILES", "CHARS_PER_TOKEN",
    "PACKET_CHARS_PER_TOKEN",
    "METRIC_META", "ROLE_VIEWS", "HOW_TO_READ",
    "MIN_PACKET_RATIO", "PACKET_TOO_SMALL",
    "MatchEntry", "PanelIndex",
    "build_panel_index", "build_analyst_packet",
    "build_analyst_a_packet", "build_analyst_b_packet",
    "packet_text", "expand_metric", "estimate_tokens",
    "measure", "report_lines", "too_small",
    "audit", "audit_lines",
    "cache_dir", "source_manifest", "write_cache",
]
