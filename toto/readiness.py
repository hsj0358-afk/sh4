"""수집 결과 → 분석·저장본 준비 상태 (Phase 6-C).

한 줄짜리 성공/실패로 뭉개지 않고 단계마다 따로 적는다.

    Betman 수집 · 경기 파싱 · 대회 식별 · FotMob · Pinnacle · WhoScored
        → 분석 준비 · 저장본 준비

## 무엇을 막고 무엇을 기록만 하나 — 지금의 계약

| 상황 | 동작 | 근거 |
|---|---|---|
| 베트맨 경기 목록이 14경기 계약 위반 | **멈춘다** (분석·저장본 없음) | C1 — `betman.MatchListError` |
| 대회를 정하지 못함 · 지원하지 않는 대회 | 경고하고 진행, 저장본도 만든다 | §1-6 · §1-16 |
| 소스 하나가 실패·부분·생략 | 경고하고 진행, 저장본도 만든다 | §1-6 · §1-16 |

두 번째·세 번째 줄을 막을지(전체 중단 / 분석은 하되 저장본 차단 / 분석축별
차단)는 **정책 결정이 필요하고 아직 정해지지 않았다.** 여기서 고르지 않는다 —
상태를 정확히 적어 두는 것까지가 이 모듈의 일이다. `ARTIFACT_POLICY` 가 그
사실을 코드에 남긴다.

**새로 수집하지 않고 판정을 다시 하지 않는다.** 소스 상태는 각 소스가 이미
적은 문자열(§1-6 의 네 낱말)을 읽고, 경기 수·배당·프로필은 이미 채워진 값을
센다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import competition

PASS = "PASS"
PARTIAL = "PARTIAL"
FAIL = "FAIL"
SKIP = "SKIP"
UNKNOWN = "UNKNOWN"

READY = "READY"
DEGRADED = "DEGRADED"
NOT_READY = "NOT_READY"

# 저장본 준비 상태가 저장을 막는가. **막지 않는다** — §1-6(한 소스 실패가
# 실행을 죽이지 않는다)·§1-16(매 실행이 저장한다)의 기존 계약이고, 바꿀지는
# 정책 결정이 필요하다. 막는 것은 베트맨 14경기 계약(C1)뿐이고 그건 이 판정
# 앞에서 실행을 멈춘다.
ARTIFACT_POLICY = "record_only"

# §1-6 의 상태 낱말. 소스가 적은 문자열의 첫 낱말을 이것으로 읽는다.
_WORDS = {"ok": PASS, "부분": PARTIAL, "실패": FAIL, "생략": SKIP}

# (표시 이름, `report.source_status` 키)
SOURCES = (("FotMob", "순위·폼"), ("Pinnacle", "배당률"),
           ("WhoScored", "상세데이터"))


@dataclass(frozen=True)
class Check:
    name: str
    state: str
    detail: str = ""


@dataclass
class Readiness:
    checks: list[Check] = field(default_factory=list)
    analysis: str = NOT_READY
    artifact: str = NOT_READY
    reasons: list[str] = field(default_factory=list)
    artifact_policy: str = ARTIFACT_POLICY

    def get(self, name: str) -> Check | None:
        return next((c for c in self.checks if c.name == name), None)

    def lines(self) -> list[str]:
        out = ["준비 상태"]
        width = max(len(c.name) for c in self.checks) if self.checks else 0
        for c in self.checks:
            out.append(f"  {c.name:<{width}}  {c.state:<7} {c.detail}".rstrip())
        why = " — " + "; ".join(self.reasons) if self.reasons else ""
        out.append(f"  분석    {self.analysis}{why}")
        out.append(f"  저장본  {self.artifact} (저장을 막지 않는다 · "
                   f"정책 {self.artifact_policy})")
        return out


def word_state(status: str | None) -> str:
    """상태 문자열 → PASS/PARTIAL/FAIL/SKIP. 첫 낱말이 어휘에 없으면 '실패' 가
    들어 있을 때 FAIL, 아니면 UNKNOWN 이다 — 모르는 것을 통과로 치지 않는다."""
    text = (status or "").strip()
    if not text:
        return UNKNOWN
    head = text.split(" ", 1)[0].split("(", 1)[0].strip()
    if head in _WORDS:
        return _WORDS[head]
    return FAIL if "실패" in text else UNKNOWN


def _numbering(matches, expected: int) -> Check:
    nos = sorted(m.no for m in matches)
    if nos == list(range(1, expected + 1)):
        return Check("경기 파싱", PASS, f"{len(nos)}/{expected} · 번호 1~{expected}")
    return Check("경기 파싱", FAIL,
                 f"{len(nos)}경기 · 번호 {nos} (기대 1~{expected} 한 번씩)")


def _competitions(matches, settings) -> Check:
    states = [competition.state(m.league, settings) for m in matches]
    total = len(states)
    ok = states.count(competition.SUPPORTED)
    parts = [f"{competition.SUPPORTED} {ok}/{total}"]
    for kind in competition.STATES[1:]:
        n = states.count(kind)
        if n:
            parts.append(f"{kind} {n}")
    bases = {}
    for m in matches:
        key = m.league_basis or "기록 없음"
        bases[key] = bases.get(key, 0) + 1
    parts.append("근거 " + " · ".join(f"{k} {v}" for k, v in sorted(bases.items())))
    state = PASS if total and ok == total else (FAIL if ok == 0 else PARTIAL)
    return Check("대회 식별", state, " · ".join(parts))


def _coverage(state: str, have: int, total: int) -> str:
    """상태 낱말이 ok 여도 실제로 빈 경기가 있으면 PARTIAL 이다."""
    if state == PASS and total and have < total:
        return PARTIAL
    return state


def assess(matches, source_status: dict, settings,
           expected: int = 14) -> Readiness:
    """수집이 끝난 경기와 소스 상태를 읽어 준비 상태를 만든다.

    아무것도 바꾸지 않는다 — 경기·상태 문자열·저장본 어느 것도 고치지 않는다.
    """
    matches = list(matches)
    status = source_status
    checks = [Check("Betman", word_state(status.get("경기목록")),
                    status.get("경기목록", "")),
              _numbering(matches, expected),
              _competitions(matches, settings)]

    n = len(matches)
    covered = {
        "FotMob": (sum(1 for m in matches for p in (m.home_profile, m.away_profile)
                       if p is not None and p.source_ok), 2 * n),
        "Pinnacle": (sum(1 for m in matches if m.odds.available), n),
    }
    for name, key in SOURCES:
        text = status.get(key, "")
        state = word_state(text)
        if name in covered:
            have, total = covered[name]
            state = _coverage(state, have, total)
            text = f"{text} [채움 {have}/{total}]" if text else f"[채움 {have}/{total}]"
        checks.append(Check(name, state, text))

    out = Readiness(checks=checks)
    parse = out.get("경기 파싱")
    comp = out.get("대회 식별")
    if parse.state == FAIL or comp.state == FAIL:
        out.analysis = NOT_READY
    elif any(c.state != PASS for c in checks):
        out.analysis = DEGRADED
    else:
        out.analysis = READY
    out.reasons = [f"{c.name} {c.state}" for c in checks if c.state != PASS]
    # 저장본은 분석이 만든 것을 그대로 담으므로 같은 판정이다. 저장을
    # 막지는 않는다 (`ARTIFACT_POLICY`).
    out.artifact = out.analysis
    return out
