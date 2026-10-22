"""시장 기준 가장 그럴듯한 스코어 — 피나클 승/무/패 확률을 스코어로 옮긴다.

**새 모델이 아니라 시장 확률의 파생값이다.** 경기마다 킥오프 전 피나클
보정 확률(`Match.probs`)에 맞는 독립 포아송 두 개(양 팀 기대 득점)를 찾고,
그 분포에서 가장 확률이 높은 스코어 하나를 읽는다. 출처는 언제나 시장이다
(§1-27 — 이 시스템에 독립 모델 확률은 없다. 이 값도 그것이 아니다).

    승/무/패 확률 → (홈 기대 득점, 원정 기대 득점) → 스코어 확률 → 최빈

왜 두나 (§1-63): 정확 스코어만 보면 시장 최빈 스코어가 패널보다 좋다 —
오프라인 재생 42경기에서 기대 적중 5.25 대 4.95, 실제 적중 8 대 4. 그래서
리포트에 **별도 참고값**으로 놓는다.

지키는 것.

  · **패널에 주지 않는다.** 분석가가 이 값을 보면 시장을 따라간다 (§1-19 의
    시장 추종 금지). `panel`·`panelpacket`·`panelexport`·`moderator`·
    `match_material` 은 이 모듈을 import 하지 않는다(테스트로 고정).
  · **승/무/패 라벨을 붙이지 않는다** (§1-3). 스코어와 그 확률만 낸다.
  · 포아송 계산은 `xpts` 를 그대로 쓴다 (§1-8). `predict` 를 import 하지
    않는다 — 확률은 이미 계산된 `Match.probs` 를 읽기만 한다.
  · 독립 포아송이라 무승부 보정(Dixon-Coles)이 없다. 그래서 승/무/패를
    정확히 재현하지 못할 수 있고, 맞춤 오차를 함께 돌려준다.
  · 같은 입력이면 같은 답이다 (난수 없음).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import xpts

FIT_LAMBDA_MAX = 5.0
FIT_COARSE_STEP = 0.1
FIT_REFINE_ROUNDS = 6
# 승/무/패 합이 이만큼 1 에서 벗어나면 맞추지 않는다 (보정 확률은 합이 1 이다).
PROB_SUM_TOLERANCE = 0.01


@dataclass(frozen=True)
class MarketScore:
    home: int
    away: int
    probability: float          # 그 스코어가 나올 확률 (독립 포아송 · 0~9 절단)
    home_goals: float           # 홈 기대 득점
    away_goals: float           # 원정 기대 득점
    fit_error: float            # 승/무/패 확률 재현의 최대 절대 오차

    @property
    def label(self) -> str:
        return f"{self.home} - {self.away}"


def _outcome_probs(lh: float, la: float) -> tuple:
    """(홈승, 무, 원정승) 확률. `xpts.match_xpts()` 와 같은 수를 같은 순서로 더한다.

    `match_xpts` 를 부르지 않는 이유: 맞춤은 기대 득점을 5.0 까지 훑는데,
    그 함수는 0~9골 절단 밖으로 1% 넘게 새면 INFO 를 남긴다. 시도값마다
    찍혀 회차 하나에 로그가 만 줄을 넘었다(실측 260061 · 12,250줄). 값은
    바이트까지 같다(테스트로 고정).
    """
    ph, pa = xpts.poisson_pmf(lh), xpts.poisson_pmf(la)
    p_home = p_draw = p_away = 0.0
    for i, h in enumerate(ph):
        for j, a in enumerate(pa):
            joint = h * a
            if i > j:
                p_home += joint
            elif i == j:
                p_draw += joint
            else:
                p_away += joint
    return p_home, p_draw, p_away


def _fit_error(lh: float, la: float, target: tuple) -> float:
    got = _outcome_probs(lh, la)
    return sum((g - t) ** 2 for g, t in zip(got, target))


def fit_market(p_home: float, p_draw: float, p_away: float) -> tuple:
    """시장 승/무/패 확률 → (홈 기대 득점, 원정 기대 득점, 최대 절대 오차).

    격자에서 시작해 간격을 줄여 가며 오차 제곱합이 가장 작은 점을 찾는다.
    """
    target = (p_home, p_draw, p_away)
    step = FIT_COARSE_STEP
    grid = [step * i for i in range(1, int(FIT_LAMBDA_MAX / step) + 1)]
    best = min((_fit_error(h, a, target), h, a) for h in grid for a in grid)
    _, lh, la = best
    for _ in range(FIT_REFINE_ROUNDS):
        step /= 4
        cands = [(lh + dh * step, la + da * step)
                 for dh in range(-4, 5) for da in range(-4, 5)]
        best = min((_fit_error(h, a, target), h, a) for h, a in cands
                   if 0 < h <= FIT_LAMBDA_MAX and 0 < a <= FIT_LAMBDA_MAX)
        _, lh, la = best
    got = _outcome_probs(lh, la)
    err = max(abs(g - t) for g, t in zip(got, target))
    return lh, la, err


def score_probability(lh: float, la: float, home: int, away: int) -> float:
    """독립 포아송에서 정확히 `home`-`away` 가 나올 확률 (0~9 절단)."""
    ph, pa = xpts.poisson_pmf(lh), xpts.poisson_pmf(la)
    if not (0 <= home < len(ph) and 0 <= away < len(pa)):
        return 0.0
    return ph[home] * pa[away]


def market_mode(lh: float, la: float) -> tuple:
    """가장 그럴듯한 스코어와 그 확률. ((홈, 원정), 확률).

    동률이면 득점 합이 적은 쪽, 그다음 홈 득점이 적은 쪽.
    """
    ph, pa = xpts.poisson_pmf(lh), xpts.poisson_pmf(la)
    p, neg_total, neg_home = max(
        (ph[i] * pa[j], -(i + j), -i)
        for i in range(len(ph)) for j in range(len(pa)))
    return (-neg_home, -neg_total + neg_home), p


def most_likely(probs) -> MarketScore | None:
    """`Match.probs`(home/draw/away 를 가진 객체) → `MarketScore`.

    확률이 없거나 0 이하이거나 합이 1 근처가 아니면 `None` 이다 —
    억지로 맞추지 않는다 (§1-5).
    """
    if probs is None:
        return None
    try:
        values = tuple(float(getattr(probs, k)) for k in ("home", "draw", "away"))
    except (AttributeError, TypeError, ValueError):
        return None
    if any(v <= 0 for v in values) or \
            abs(sum(values) - 1.0) > PROB_SUM_TOLERANCE:
        return None
    lh, la, err = fit_market(*values)
    (home, away), p = market_mode(lh, la)
    return MarketScore(home=home, away=away, probability=p,
                       home_goals=lh, away_goals=la, fit_error=err)
