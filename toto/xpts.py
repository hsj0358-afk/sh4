"""독립 포아송 기대승점 (xPTS) — **모델 산출값**.

경기별 xG 두 개(홈·원정)를 넣으면 승/무/패 확률과 기대승점이 나온다.

## 이것이 무엇이 아닌지부터

- **피나클 배당 확률과 다른 것이다.** 저쪽은 시장이 매긴 값(`toto/predict.py`,
  provenance=observed)이고 이쪽은 경기내용에서 만든 모델값이다. 두 확률을
  합치거나 서로 보정하지 않는다. 이 모듈은 `predict` 를 import 하지 않고
  `predict` 도 이 모듈을 import 하지 않는다 — 테스트로 고정한다.
- **Dixon-Coles 가 아니다.** 무승부 보정계수도, 두 팀 득점의 상관항도 없다.
  홈 득점과 원정 득점을 **독립**으로 본다. 실제 축구에서는 완전히 독립이
  아니라 저득점 스코어라인이 과소평가되는 것으로 알려져 있는데, 그 보정을
  넣지 않았다는 뜻이다.
- **추천이 아니다.** 확률과 기대승점만 만들고 픽을 고르지 않는다.

## 계산

    P(X=k) = exp(-λ) · λ^k / k!        (λ = 그 팀의 xG)
    P(i,j) = P_home(i) · P_away(j)     (독립)

    i > j → 홈승,  i = j → 무,  i < j → 원정승

    xPTS_home = 3·P(홈승) + 1·P(무)
    xPTS_away = 3·P(원정승) + 1·P(무)

**두 팀 xPTS 의 합은 3 이 아니다.** 절단 오차가 없더라도 그렇다 —
무승부 확률이 양쪽에 1점씩 들어가므로 합은 `3 − P(무) · 1` 만큼 작다.
(λ 둘 다 1.0 이면 합이 약 2.69 다.)

## 절단과 tail_mass

득점을 0~9 로 끊는다. 그래서 확률 합이 1보다 조금 작고, 그 부족분을
`tail_mass` 로 남긴다. **자동으로 정규화하지 않는다** — 재분배하면 모델이
얼마나 어긋났는지가 보이지 않게 된다. λ 가 커질수록 tail 이 커진다
(λ 둘 다 4.0 이면 약 1.6%).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from .models import AnalysisAxis, Metric, MODEL

log = logging.getLogger(__name__)

# 득점 절단. 0..MAX_GOALS 까지만 센다.
MAX_GOALS = 9
# 이보다 많이 새면 로그로 알린다. 값을 고치지는 않는다.
TAIL_WARN = 0.01
# math.exp(-λ) 가 0 으로 언더플로하는 지점(약 745) 훨씬 앞에서 막는다.
# 축구 한 경기 xG 가 이 값을 넘을 일은 없고, 넘었다면 입력이 잘못된 것이다.
MAX_LAMBDA = 50.0


def poisson_pmf(lam: float, max_goals: int = MAX_GOALS) -> list[float]:
    """[P(0), P(1), …, P(max_goals)].

    `λ^k / k!` 를 직접 계산하지 않고 점화식으로 만든다 —
    `p(0) = exp(-λ)`, `p(k) = p(k-1) · λ / k`.
    큰 λ 에서 `λ^k` 가 넘치거나 `k!` 가 커지는 문제를 피하고 곱셈 k번으로 끝난다.
    """
    if lam < 0:
        raise ValueError(f"λ 는 0 이상이어야 합니다: {lam}")
    if not math.isfinite(lam):
        raise ValueError(f"λ 가 유한하지 않습니다: {lam}")
    if lam > MAX_LAMBDA:
        raise ValueError(f"λ 가 비정상적으로 큽니다: {lam} (> {MAX_LAMBDA})")

    out = [math.exp(-lam)]
    for k in range(1, max_goals + 1):
        out.append(out[-1] * lam / k)
    return out


@dataclass
class XPTSResult:
    """한 경기의 모델 산출값. 전부 `provenance = "model"` 이다."""
    home_xg: float | None = None            # 입력 (observed)
    away_xg: float | None = None            # 입력 (observed)
    home_win_probability: float | None = None
    draw_probability: float | None = None
    away_win_probability: float | None = None
    home_xpts: float | None = None
    away_xpts: float | None = None
    probability_sum: float | None = None    # 절단 때문에 1보다 조금 작다
    tail_mass: float | None = None          # 1 − probability_sum
    max_goals: int = MAX_GOALS
    provenance: str = MODEL
    reason: str = ""                        # 계산하지 못한 이유

    @property
    def available(self) -> bool:
        return self.home_xpts is not None

    def as_axis(self, name: str = "xpts") -> AnalysisAxis:
        """`MatchAnalysis` 에 넣을 축으로 바꾼다.

        입력 xG 는 원본이지만 여기서는 **모델의 입력**으로 함께 보여주는
        것이므로, 확률·기대승점만 model 로 표시하고 xG 는 넣지 않는다 —
        xG 자체는 기회의 질(2-B) 축이 observed 로 들고 있다.
        """
        axis = AnalysisAxis(name=name)
        if not self.available:
            if self.reason:
                axis.notes.append(self.reason)
            return axis
        for key, label, value in (
                ("home_win_probability", "홈승 확률(모델)",
                 self.home_win_probability),
                ("draw_probability", "무승부 확률(모델)", self.draw_probability),
                ("away_win_probability", "원정승 확률(모델)",
                 self.away_win_probability),
                ("home_xpts", "홈 기대승점", self.home_xpts),
                ("away_xpts", "원정 기대승점", self.away_xpts)):
            axis.metrics[key] = Metric(
                name=key, label=label, value=value, provenance=MODEL,
                period="match", sample_count=1)
        axis.notes.append(
            f"독립 포아송 · 득점 0~{self.max_goals} 절단 · "
            f"확률합 {self.probability_sum:.6f} (누락 {self.tail_mass:.2e})")
        return axis


def match_xpts(home_xg: float | None, away_xg: float | None,
               max_goals: int = MAX_GOALS) -> XPTSResult:
    """경기 1건의 승/무/패 확률과 기대승점.

    **어느 한쪽 xG 라도 None 이면 전부 None 이다** — 데이터가 없는 것이지
    0 이 아니다. 반대로 `0.0` 은 실제 값이라 그대로 계산한다(무득점 기대).
    """
    if home_xg is None or away_xg is None:
        which = "홈" if home_xg is None else "원정"
        return XPTSResult(home_xg=home_xg, away_xg=away_xg,
                          reason=f"{which} xG 없음")
    try:
        home = poisson_pmf(float(home_xg), max_goals)
        away = poisson_pmf(float(away_xg), max_goals)
    except (ValueError, TypeError) as exc:
        return XPTSResult(home_xg=home_xg, away_xg=away_xg,
                          reason=f"계산 불가: {exc}")

    p_home = p_draw = p_away = 0.0
    for i, ph in enumerate(home):
        for j, pa in enumerate(away):
            joint = ph * pa
            if i > j:
                p_home += joint
            elif i == j:
                p_draw += joint
            else:
                p_away += joint

    total = p_home + p_draw + p_away
    tail = 1.0 - total
    if tail > TAIL_WARN:
        log.info("xPTS 절단 누락이 큽니다: %.4f (xG %.2f/%.2f, 득점 0~%d). "
                 "확률을 재분배하지 않고 그대로 둡니다.",
                 tail, home_xg, away_xg, max_goals)

    return XPTSResult(
        home_xg=float(home_xg), away_xg=float(away_xg),
        home_win_probability=p_home, draw_probability=p_draw,
        away_win_probability=p_away,
        # 기대승점은 **절단된 확률 그대로** 계산한다. 정규화한 확률을 쓰면
        # 절단 오차가 기대승점에 숨어 버린다.
        home_xpts=3.0 * p_home + 1.0 * p_draw,
        away_xpts=3.0 * p_away + 1.0 * p_draw,
        probability_sum=total, tail_mass=tail, max_goals=max_goals)


# --------------------------------------------------------------------------
# 팀 단위 집계 (시즌 / 최근 N경기)
# --------------------------------------------------------------------------
@dataclass
class TeamXPTS:
    """한 팀의 기대승점 합계와 **표본**.

    `requested_matches` 와 `available_matches` 는 다른 개념이다 —
    앞은 넘겨받은 경기 수, 뒤는 그중 xG 가 있어 실제로 계산된 경기 수다.
    시즌 전체 경기의 xG 가 확보돼 있지 않으므로(경기 상세는 팀당 최근
    N경기만 받는다) 이 둘은 자주 다르다. **커버리지를 감추지 않는다.**
    """
    team: str = ""
    xpts_sum: float | None = None
    requested_matches: int = 0
    available_matches: int = 0
    match_ids: list[str] = field(default_factory=list)

    @property
    def sample_count(self) -> int:
        """xPTS 를 실제로 계산한 경기 수 (available_matches 와 같다)."""
        return self.available_matches

    @property
    def xpts_per_match(self) -> float | None:
        """경기당 기대승점. **있는 경기 수로만** 나눈다."""
        if self.xpts_sum is None or not self.available_matches:
            return None
        return self.xpts_sum / self.available_matches

    @property
    def coverage(self) -> float | None:
        """xG 가 있던 경기 비율. 1.0 미만이면 부분 표본이다."""
        if not self.requested_matches:
            return None
        return self.available_matches / self.requested_matches

    def as_axis(self, name: str = "xpts_team") -> AnalysisAxis:
        axis = AnalysisAxis(name=name,
                            requested_matches=self.requested_matches,
                            available_matches=self.available_matches)
        if self.xpts_sum is None:
            axis.notes.append(
                f"표본 부족 ({self.available_matches}/{self.requested_matches}경기)")
            return axis
        axis.metrics["xpts_sum"] = Metric(
            name="xpts_sum", label="기대승점 합계", value=self.xpts_sum,
            provenance=MODEL, sample_count=self.available_matches)
        axis.metrics["xpts_per_match"] = Metric(
            name="xpts_per_match", label="경기당 기대승점",
            value=self.xpts_per_match, provenance=MODEL,
            sample_count=self.available_matches, unit="per_match")
        axis.notes.append(
            f"xG 가 있던 경기 {self.available_matches}/{self.requested_matches}")
        return axis


def aggregate_team_xpts(matches, xg_by_match: dict, team: str,
                        max_goals: int = MAX_GOALS) -> TeamXPTS:
    """여러 과거 경기에서 한 팀의 기대승점을 모은다.

    - `matches` — `SeasonMatch` 목록. **호출부가 이미 시점으로 걸러서** 넘긴다
      (`Report.matches_before(as_of)`). 이 함수는 시점을 다시 보지 않는다 —
      누수 방지를 한 곳에만 두기 위해서다.
    - `xg_by_match` — `{match_id: (home_xg, away_xg)}`. 경기 상세를 받은
      경기에만 있다. **없는 경기는 세지 않는다**(0 으로 치지 않는다).
    - `team` — 정규명. `SeasonMatch.home_team`/`away_team` 과 맞춘다.

    같은 경기를 두 번 세지 않는다.
    """
    out = TeamXPTS(team=team)
    seen: set[str] = set()
    total = 0.0
    for m in matches:
        home_team = getattr(m, "home_team", None)
        away_team = getattr(m, "away_team", None)
        if team not in (home_team, away_team):
            continue
        mid = str(getattr(m, "match_id", "") or "")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.requested_matches += 1

        pair = xg_by_match.get(mid)
        if not pair:
            continue
        home_xg, away_xg = pair
        result = match_xpts(home_xg, away_xg, max_goals)
        if not result.available:
            continue
        out.available_matches += 1
        out.match_ids.append(mid)
        total += (result.home_xpts if team == home_team else result.away_xpts)

    out.xpts_sum = total if out.available_matches else None
    return out
