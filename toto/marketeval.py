"""시장 기준선 캘리브레이션 (Phase 6-B) — **측정만 한다.**

## 무엇을 재는가

이 프로젝트에는 대상 경기의 **독립적인 W/D/L 모델 확률이 없다** (Phase 6-A).
`Match.probs` 는 피나클 배당에서 가산 마진만 뺀 값이고(`predict.
additive_probabilities`, §1-2), 리포트의 `Pinnacle 시장 기준선` 도 같은 수다.
`apply_veto` 는 어디에서도 호출되지 않고, xPTS 는 2-D 의 과거 집계에만 쓰인다.

그래서 지금 잴 수 있는 것은 **하나뿐**이다.

    Market baseline  ↔  Actual result

**`model_probability` 라는 칸을 만들지 않는다.** 없는 것을 있는 것처럼 두면
다음 사람이 "우리 분석이 시장보다 낫다" 를 이 표로 말하게 된다 — 그 비교는
지금 성립하지 않는다(두 열이 같은 수다). 나중에 진짜 모델 확률이 생기면
`ROWS` 에 열을 더하고 같은 지표 함수를 한 번 더 부르면 된다.

## 어디서 읽는가

**새 CSV 를 만들지 않는다.** `roundlog` 가 이미 쌓고 있는
`data/round_matches.csv` 를 그대로 읽는다 — 그 스키마가 필요한 칸을 전부
갖고 있다.

    round · no · league · kickoff_kst · home · away
    odds_home/draw/away        배당 (그 시점 관측)
    p_home/p_draw/p_away       ← **시장 확률**이다. 모델 확률이 아니다
    recorded_at                사전 스냅샷을 남긴 시각
    home_goals · away_goals · result · settled_at   ← 경기 뒤에 채워진다

`p_*` 를 시장 확률로 읽는다는 것이 이 모듈의 전제이고, 그 근거는 위의
`additive_probabilities` 한 줄이다.

## 보정하지 않는다

여기서 나온 수를 `predict.py` 나 `Match.probs` 에 되돌려 넣지 않는다.
이 모듈은 `predict`·`models` 의 확률을 **읽지도 않는다** — CSV 행만 본다.
승·무·패를 추천하지 않는다 (§1-3).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger("toto")

# 결과 어휘는 `predict.HOME/DRAW/AWAY` 와 `SeasonMatch.result` 가 쓰는 것과
# 같다. 여기서 새로 정하지 않고 같은 글자를 쓴다.
OUTCOMES = ("H", "D", "A")
OUTCOME_KO = {"H": "승", "D": "무", "A": "패"}

# 로그 손실에서 0 을 만나면 무한대가 된다. 자르는 값을 **밝혀 둔다** —
# 조용히 자르면 그 수가 어디서 왔는지 알 수 없다.
LOG_EPS = 1e-15

# 캘리브레이션 구간. 0.0~1.0 을 10등분한다.
BINS = tuple(round(0.1 * i, 1) for i in range(11))


# --------------------------------------------------------------------------
# 평가 대상 고르기 — 하나라도 모자라면 빼고, 왜 뺐는지 적는다 (§1-6)
# --------------------------------------------------------------------------
@dataclass
class EvalRow:
    """평가 한 건. **없는 값은 None 이다** (0 이 아니다)."""
    round_id: str = ""
    no: int | None = None
    league: str = ""
    kickoff_kst: str = ""
    home: str = ""
    away: str = ""
    recorded_at: str = ""
    market: dict[str, float] = field(default_factory=dict)   # H/D/A → 확률
    actual: str = ""                                         # H/D/A
    home_goals: int | None = None
    away_goals: int | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.round_id, str(self.no))

    @property
    def favorite(self) -> str:
        """시장 확률이 가장 높은 결과.

        **추천이 아니다.** 시장이 어디에 값을 매겼는지를 읽은 것뿐이고,
        이 프로그램은 승·무·패를 추천하지 않는다 (§1-3).
        """
        return max(OUTCOMES, key=lambda o: self.market[o])


@dataclass
class Excluded:
    round_id: str = ""
    no: str = ""
    reason: str = ""


def _num(text: str) -> float | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _stamp(text: str) -> datetime | None:
    """'2026-09-12 00:11' → datetime. 못 읽으면 None (지어내지 않는다)."""
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def select(rows: list[dict]) -> tuple[list[EvalRow], list[Excluded]]:
    """CSV 행 → 평가 대상. (뽑힌 것, 뺀 것+사유).

    다섯 조건을 전부 만족해야 들어온다 (§6).

      1. 시장 확률 3개가 다 있고 합이 1 근처다
      2. 실제 결과가 있다
      3. **그 확률이 경기 시작 전에 기록됐다** (`recorded_at < kickoff`)
      4. 같은 경기가 두 번 들어오지 않는다
      5. 회차·경기 번호로 식별된다

    **모자라면 0 으로 채우지 않고 뺀다.** 왜 뺐는지는 전부 남긴다.
    """
    out: list[EvalRow] = []
    dropped: list[Excluded] = []
    seen: set[tuple[str, str]] = set()

    for raw in rows:
        rnd = (raw.get("round") or "").strip()
        no = (raw.get("no") or "").strip()

        def skip(reason: str) -> None:
            dropped.append(Excluded(rnd, no, reason))

        if not rnd or not no:
            skip("회차·경기 번호가 없습니다")
            continue
        if (rnd, no) in seen:
            skip("같은 경기가 두 번 들어왔습니다")
            continue

        probs = {o: _num(raw.get(f"p_{k}")) for o, k
                 in zip(OUTCOMES, ("home", "draw", "away"))}
        if any(v is None for v in probs.values()):
            skip("시장 확률이 없습니다")
            seen.add((rnd, no))
            continue
        total = sum(probs.values())
        if abs(total - 1.0) > 0.01:
            skip(f"시장 확률 합이 1이 아닙니다 ({total:.4f})")
            seen.add((rnd, no))
            continue

        actual = (raw.get("result") or "").strip()
        if actual not in OUTCOMES:
            skip("실제 결과가 없습니다")
            seen.add((rnd, no))
            continue

        recorded = _stamp(raw.get("recorded_at", ""))
        kickoff = _stamp(raw.get("kickoff_kst", ""))
        if recorded is None or kickoff is None:
            skip("기록 시각이나 킥오프를 읽지 못했습니다")
            seen.add((rnd, no))
            continue
        if recorded >= kickoff:
            # 경기가 시작한 뒤에 남은 확률은 사전 스냅샷이 아니다.
            skip(f"확률이 킥오프 이후에 기록됐습니다 ({recorded} ≥ {kickoff})")
            seen.add((rnd, no))
            continue

        seen.add((rnd, no))
        hg, ag = _num(raw.get("home_goals")), _num(raw.get("away_goals"))
        out.append(EvalRow(
            round_id=rnd, no=int(no) if no.isdigit() else None,
            league=(raw.get("league") or "").strip(),
            kickoff_kst=(raw.get("kickoff_kst") or "").strip(),
            home=(raw.get("home") or "").strip(),
            away=(raw.get("away") or "").strip(),
            recorded_at=(raw.get("recorded_at") or "").strip(),
            market=probs, actual=actual,
            home_goals=int(hg) if hg is not None else None,
            away_goals=int(ag) if ag is not None else None))
    return out, dropped


# --------------------------------------------------------------------------
# 지표 — 표본이 없으면 None 이다 (0 이 아니다)
# --------------------------------------------------------------------------
def market_favorite_accuracy(rows: list[EvalRow]) -> float | None:
    """시장 확률이 가장 높았던 결과가 실제와 같았던 비율.

    **적중률이라고 부르지 않는다** — 이 프로그램은 픽을 추천하지 않으므로
    맞히려고 한 적이 없다. 시장의 최빈 결과와 실제가 얼마나 겹치는지다.
    """
    if not rows:
        return None
    return sum(1 for r in rows if r.favorite == r.actual) / len(rows)


def brier_score(rows: list[EvalRow]) -> float | None:
    """다중분류 Brier. `(1/N) Σ_경기 Σ_결과 (p − y)²` — 0~2, 낮을수록 좋다.

    /2 로 나누는 관례도 있는데 쓰지 않았다. **어느 정의인지 적어 두는 것**이
    수를 비교 가능하게 만든다.
    """
    if not rows:
        return None
    total = 0.0
    for r in rows:
        for o in OUTCOMES:
            y = 1.0 if o == r.actual else 0.0
            total += (r.market[o] - y) ** 2
    return total / len(rows)


def log_loss(rows: list[EvalRow]) -> float | None:
    """다중분류 로그 손실. `−(1/N) Σ ln p(실제 결과)` — 낮을수록 좋다.

    확률이 0 이면 무한대가 되므로 `LOG_EPS` 로 자른다. 자른다는 사실을
    숨기지 않는다.
    """
    if not rows:
        return None
    total = 0.0
    for r in rows:
        total += -math.log(max(r.market[r.actual], LOG_EPS))
    return total / len(rows)


@dataclass
class Bin:
    low: float
    high: float
    count: int = 0
    mean_predicted: float | None = None
    actual_frequency: float | None = None


def calibration_table(rows: list[EvalRow]) -> list[Bin]:
    """확률 구간별 (표본 수 · 평균 예측확률 · 실제 빈도).

    경기 하나가 **세 쌍**을 낸다 — 승·무·패 각각의 예측확률과 그 결과가
    실제로 일어났는지. §5-D 가 "결과별 예측확률을 구간화" 라고 적은 그대로다.

    **표본이 적은 구간을 해석하지 않는다.** 그래서 `count` 를 언제나 함께
    돌려주고, 빈 구간은 값 대신 `None` 을 둔다.
    """
    buckets: list[list[tuple[float, float]]] = [[] for _ in range(len(BINS) - 1)]
    for r in rows:
        for o in OUTCOMES:
            p = r.market[o]
            y = 1.0 if o == r.actual else 0.0
            idx = min(int(p * 10), len(buckets) - 1)
            buckets[max(idx, 0)].append((p, y))

    out = []
    for i, pairs in enumerate(buckets):
        b = Bin(low=BINS[i], high=BINS[i + 1], count=len(pairs))
        if pairs:
            b.mean_predicted = sum(p for p, _ in pairs) / len(pairs)
            b.actual_frequency = sum(y for _, y in pairs) / len(pairs)
        out.append(b)
    return out


# --------------------------------------------------------------------------
# 요약
# --------------------------------------------------------------------------
@dataclass
class Summary:
    rounds: int = 0
    matches_seen: int = 0
    evaluated: int = 0
    excluded: list[Excluded] = field(default_factory=list)
    favorite_accuracy: float | None = None
    brier: float | None = None
    logloss: float | None = None
    bins: list[Bin] = field(default_factory=list)
    rows: list[EvalRow] = field(default_factory=list)

    @property
    def exclusion_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.excluded:
            out[e.reason] = out.get(e.reason, 0) + 1
        return out


def evaluate(rows: list[dict]) -> Summary:
    """CSV 행 → 요약. **행을 고치지 않는다** (읽기만 한다)."""
    picked, dropped = select(rows)
    return Summary(
        rounds=len({(r.get("round") or "").strip() for r in rows
                    if (r.get("round") or "").strip()}),
        matches_seen=len(rows), evaluated=len(picked), excluded=dropped,
        favorite_accuracy=market_favorite_accuracy(picked),
        brier=brier_score(picked), logloss=log_loss(picked),
        bins=calibration_table(picked), rows=picked)


def load_rows(path: Path | None = None) -> list[dict]:
    """`roundlog` 가 쌓아 둔 경기 기록을 읽는다. 없으면 빈 목록.

    읽는 규칙을 새로 만들지 않는다 — `roundlog._read()` 를 그대로 쓴다
    (§1-8). BOM·열 추가 처리가 이미 거기 있다.
    """
    from . import roundlog
    return roundlog._read(path or roundlog.MATCH_FILE, roundlog.MATCH_FIELDS)


def format_summary(s: Summary) -> str:
    """사람이 읽을 여러 줄. **표본이 없으면 없다고 적는다.**"""
    lines = [
        "시장 기준선 캘리브레이션 (Pinnacle 배당에서 마진을 뺀 확률 ↔ 실제 결과)",
        "  이 표는 **시장**을 잰 것이다. 이 프로젝트의 분석을 잰 것이 아니고,",
        "  독립적인 모델 확률이 아직 없어 둘을 견줄 수 없다 (Phase 6-A).",
        "",
        f"  기록된 경기   {s.matches_seen}  ({s.rounds}회차)",
        f"  평가 대상     {s.evaluated}",
    ]
    for reason, n in sorted(s.exclusion_counts.items(), key=lambda x: -x[1]):
        lines.append(f"    제외 {n:4d}  {reason}")
    if not s.evaluated:
        lines.append("")
        lines.append("  평가할 표본이 없습니다 — 지표를 내지 않습니다.")
        return "\n".join(lines)

    lines += [
        "",
        f"  시장 최빈 결과 일치   {s.favorite_accuracy:.4f}"
        f"  ({round(s.favorite_accuracy * s.evaluated)}/{s.evaluated})",
        f"  Brier (다중분류 0~2)  {s.brier:.4f}",
        f"  로그 손실             {s.logloss:.4f}",
        "",
        "  캘리브레이션 (경기당 승·무·패 세 쌍)",
        "    구간          표본   평균 예측   실제 빈도",
    ]
    for b in s.bins:
        if not b.count:
            continue
        lines.append(f"    {b.low:.1f}~{b.high:.1f}   {b.count:6d}   "
                     f"{b.mean_predicted:9.4f}   {b.actual_frequency:9.4f}")
    lines.append("  표본이 적은 구간은 해석하지 않는다.")
    return "\n".join(lines)
