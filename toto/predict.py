"""보정 확률 · argmax 픽 · 회차 승산 (Calibrated Single-Pick Engine v3.2).

'축구 승무패 예측' 프로젝트 지침 §3~§5 를 그대로 구현한다.

설계 원칙 (지침 §0):
  · 피나클 마감 배당 한 곳만 확률 소스로 쓴다.
  · 마진을 올바르게 제거한 확률이 곧 최선의 진실 추정치다. 휴리스틱 보정
    (리그 가중·무승부 가중·FLB 필터 등)은 하지 않는다.
  · 최대화 대상은 평균 적중 개수가 아니라 P(적중 ≥ 11) 이다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

HOME, DRAW, AWAY = "H", "D", "A"
RESULT_KO = {HOME: "승", DRAW: "무", AWAY: "패"}

# 지침 §5-(e): 이 확률 미만이면 회차 자체를 건너뛴다.
GATE_THRESHOLD = 0.15
# 지침 §7: 상위 두 픽이 이 폭 이내로 붙으면 [백중세] (직관 적용 후보)
TOSS_UP_GAP = 0.04
# 지침 §3-(b): 음수 확률이 나올 때 클램프할 값
CLAMP_FLOOR = 0.005
# 지침 §3-(d): 수동 Veto 의 최대 조정 폭
VETO_MAX = 0.05


@dataclass
class MatchProb:
    """한 경기의 보정 확률과 픽."""
    home: float = 0.0
    draw: float = 0.0
    away: float = 0.0

    overround: float = 0.0      # R = Σ(1/배당)
    margin_per_option: float = 0.0   # m = (R-1)/3
    clamped: bool = False       # 음수 확률이 나와 클램프했는지
    veto_note: str = ""         # Veto 적용 내역

    @property
    def as_tuple(self) -> tuple[float, float, float]:
        return (self.home, self.draw, self.away)

    @property
    def pick(self) -> str:
        """지침 §4: 가장 높은 결과를 픽한다(argmax). 그 외 규칙 없음."""
        return max(((self.home, HOME), (self.draw, DRAW), (self.away, AWAY)),
                   key=lambda x: x[0])[1]

    @property
    def pick_ko(self) -> str:
        return RESULT_KO[self.pick]

    @property
    def p_pick(self) -> float:
        """픽의 예상 적중률 = 그 결과의 보정 확률."""
        return {HOME: self.home, DRAW: self.draw, AWAY: self.away}[self.pick]

    def pct(self) -> tuple[float, float, float]:
        return (self.home * 100, self.draw * 100, self.away * 100)

    @property
    def margin(self) -> float:
        """북메이커 마진 (오버라운드 − 1)."""
        return max(0.0, self.overround - 1.0)

    @property
    def favorite(self) -> str:
        return self.pick

    @property
    def sorted_probs(self) -> list[float]:
        return sorted(self.as_tuple, reverse=True)

    @property
    def gap(self) -> float:
        """1순위와 2순위의 확률 차."""
        s = self.sorted_probs
        return s[0] - s[1]

    @property
    def toss_up(self) -> bool:
        """지침 §7: 상위 두 픽이 약 4%p 이내 → [백중세]."""
        return self.gap <= TOSS_UP_GAP


# --------------------------------------------------------------------------
# §3. 확률 도출 — 가산(균등) 마진 제거
# --------------------------------------------------------------------------
def additive_probabilities(odd_home: float, odd_draw: float,
                           odd_away: float) -> MatchProb:
    """피나클 배당 → 보정 확률 (지침 §3-(b) 가산 마진 제거, 필수 방법).

        q_i = 1 / 배당_i
        R   = Σ q_i                 (오버라운드, 1보다 큼)
        m   = (R − 1) / 3           (옵션당 균등 절대 마진)
        p_i = q_i − m               → 자동으로 Σ p_i = 1

    피나클은 모든 옵션에 거의 동일한 **절대** 마진을 부과하므로, 흔히 쓰는
    비례식(q_i / R)은 마진을 제대로 제거하지 못해 정배를 과소·역배를 과대
    추정한 채로 남긴다(Favorite-Longshot 편향). 지침은 비례식을 금지한다.

    >>> p = additive_probabilities(2.0, 3.5, 4.0)
    >>> round(p.home + p.draw + p.away, 12)
    1.0
    """
    for label, odd in (("승", odd_home), ("무", odd_draw), ("패", odd_away)):
        if not odd or odd <= 1.0:
            raise ValueError(f"유효하지 않은 배당({label}): {odd}")

    q = [1.0 / odd_home, 1.0 / odd_draw, 1.0 / odd_away]
    overround = sum(q)
    m = (overround - 1.0) / 3.0
    p = [x - m for x in q]

    clamped = False
    if any(x < 0 for x in p):
        # 지침 §3-(b) 예외 처리: 음수는 0 근방으로 클램프하고 나머지를
        # 합이 1이 되도록 재정규화한다.
        clamped = True
        fixed = [CLAMP_FLOOR if x < 0 else x for x in p]
        locked = sum(CLAMP_FLOOR for x in p if x < 0)
        free = [x for x, orig in zip(fixed, p) if orig >= 0]
        free_sum = sum(free)
        remaining = 1.0 - locked
        if free_sum > 0:
            scale = remaining / free_sum
            p = [CLAMP_FLOOR if orig < 0 else x * scale
                 for x, orig in zip(fixed, p)]
        else:
            p = [1.0 / 3] * 3

    return MatchProb(home=p[0], draw=p[1], away=p[2],
                     overround=overround, margin_per_option=m, clamped=clamped)


def apply_veto(prob: MatchProb, side: str, delta_pp: float,
               reason: str = "") -> MatchProb:
    """지침 §3-(d) 수동 Veto.

    마감 라인에 아직 반영되지 않은 **명확한 사실**(예: 직전 발표된 핵심 선수
    결장)에 한해 해당 결과 확률을 최대 5%p 조정하고 나머지를 재정규화한다.
    "느낌"이나 "추세"는 Veto 사유가 아니다.
    """
    if side not in (HOME, DRAW, AWAY):
        raise ValueError(f"side 는 H/D/A 중 하나여야 합니다: {side!r}")
    delta = max(-VETO_MAX, min(VETO_MAX, delta_pp))

    values = {HOME: prob.home, DRAW: prob.draw, AWAY: prob.away}
    target = max(0.0, min(1.0, values[side] + delta))
    others = [k for k in (HOME, DRAW, AWAY) if k != side]
    rest = sum(values[k] for k in others)
    remaining = 1.0 - target

    if rest > 0:
        for k in others:
            values[k] = values[k] / rest * remaining
    else:
        for k in others:
            values[k] = remaining / 2
    values[side] = target

    note = f"{RESULT_KO[side]} {delta:+.1%}"
    if reason:
        note += f" ({reason})"
    return MatchProb(home=values[HOME], draw=values[DRAW], away=values[AWAY],
                     overround=prob.overround,
                     margin_per_option=prob.margin_per_option,
                     clamped=prob.clamped, veto_note=note)


# --------------------------------------------------------------------------
# §5. 회차 승산
# --------------------------------------------------------------------------
def _phi(z: float) -> float:
    """표준정규 누적분포 Φ(z)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def poisson_binomial_ge(k: int, probs: list[float]) -> float:
    """서로 다른 성공확률을 가진 독립 시행에서 P(성공 ≥ k). 정확 계산.

    경기가 14개뿐이라 동적계획법으로 정확히 구할 수 있다. 지침 §5-(d)는
    정규근사를 쓰는데, 이는 손계산 제약 때문이다. 근사와 정확값을 함께
    제시하되 게이트 판정은 지침대로 정규근사를 따른다.
    """
    dp = [1.0]
    for p in probs:
        nxt = [0.0] * (len(dp) + 1)
        for i, acc in enumerate(dp):
            nxt[i] += acc * (1.0 - p)
            nxt[i + 1] += acc * p
        dp = nxt
    return sum(dp[k:]) if k <= len(probs) else 0.0


@dataclass
class RoundVerdict:
    """회차 단위 승산 평가 (지침 §5)."""
    n: int = 0
    expected: float = 0.0        # E = Σ p_pick
    sigma: float = 0.0           # σ = √Σ p(1-p)
    z: float = 0.0               # z = (E − 10.5) / σ
    p_ge11: float = 0.0          # Φ(z) — 지침 §5-(d), 게이트 기준
    p_ge11_exact: float = 0.0    # 포아송 이항 정확값 (참고)
    bet: bool = False
    incomplete: bool = False     # 배당 없는 경기가 있어 판정이 불완전한지
    missing: list[int] = field(default_factory=list)

    @property
    def verdict_ko(self) -> str:
        return "베팅" if self.bet else "패스"


def round_winnability(p_picks: list[float], total_matches: int = 14,
                      missing: list[int] | None = None,
                      threshold: int = 11) -> RoundVerdict:
    """argmax 단통표의 11개 이상 적중 확률을 추정한다 (지침 §5).

        E = Σ p_pick
        σ = √( Σ p_pick × (1 − p_pick) )
        z = (E − 10.5) / σ          ← 연속성 보정
        P(≥11) ≈ Φ(z)
        P(≥11) ≥ 15% → 베팅, 미만 → 패스
    """
    missing = missing or []
    v = RoundVerdict(n=len(p_picks), missing=list(missing),
                     incomplete=bool(missing) or len(p_picks) < total_matches)
    if not p_picks:
        return v

    v.expected = sum(p_picks)
    var = sum(p * (1.0 - p) for p in p_picks)
    v.sigma = math.sqrt(var)

    # 연속성 보정: 11개 이상 → 10.5 를 기준점으로
    cutoff = threshold - 0.5
    v.z = (v.expected - cutoff) / v.sigma if v.sigma > 0 else 0.0
    v.p_ge11 = _phi(v.z)
    v.p_ge11_exact = poisson_binomial_ge(threshold, p_picks)
    v.bet = v.p_ge11 >= GATE_THRESHOLD
    return v


# --------------------------------------------------------------------------
# §6. 사후 정산 진단
# --------------------------------------------------------------------------
def brier(prob: MatchProb, actual: str) -> float:
    """다항 Brier 점수 (지침 §6-(c)). 기준선 균등 1/3 = 0.667, 낮을수록 좋음."""
    if actual not in (HOME, DRAW, AWAY):
        raise ValueError(f"actual 은 H/D/A 중 하나여야 합니다: {actual!r}")
    ind = {HOME: 0.0, DRAW: 0.0, AWAY: 0.0}
    ind[actual] = 1.0
    return ((prob.home - ind[HOME]) ** 2
            + (prob.draw - ind[DRAW]) ** 2
            + (prob.away - ind[AWAY]) ** 2)


BRIER_BASELINE = 2.0 / 3.0      # 균등 1/3 예측의 Brier = 0.667
