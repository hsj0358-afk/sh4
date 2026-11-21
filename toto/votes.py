"""베트맨 투표 현황에서 파생한 값 (§1-68).

투표율은 **다른 구매자들이 무엇을 찍었나**다. 확률이 아니고, 승무패는 같은
등수에 맞힌 사람끼리 상금을 나누므로 '얼마나 겹치나' 를 알려 준다. 시장
배당은 이것을 알려 주지 못한다.

여기서 하는 일은 셋뿐이다.

  · 경기마다 투표 비중과 시장 확률의 차이 (%p)
  · 회차 전체 — 투표 1위 결과로만 채운 조합이 얼마나 흔한가, 그 조합이 시장
    기준으로 모두 맞을 확률, 투표 1위와 시장 1위가 다른 경기
  · 그 밖에는 아무것도 하지 않는다

**고르지 않는다** (§1-3). '역배'·'가치 픽'·추천 같은 낱말을 만들지 않고,
조합을 제안하지 않는다. **패널에 주지 않는다** — 시장 확률을 주지 않는 것과
같은 이유다 (§1-19). 그래서 `panel`·`panelpacket`·`panelexport`·`moderator`·
`match_material`·`evidence`·`analysis` 는 이 모듈을 import 하지 않는다(테스트).

조합의 흔함은 **경기 간 독립을 가정한 곱**이다. 실제 사람들의 표는 서로
닮아 있어(인기 조합에 몰린다) 같은 조합은 이 곱보다 더 많이 겹친다 — 화면에
그렇게 적는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

OUTCOMES = ("H", "D", "A")


def shares(match) -> tuple[float, float, float] | None:
    votes = getattr(match, "votes", None)
    return votes.shares() if votes is not None else None


def diff_pp(match) -> tuple[float, float, float] | None:
    """투표 비중 − 시장 확률 (%p). 둘 중 하나라도 없으면 None."""
    s = shares(match)
    p = getattr(match, "probs", None)
    if s is None or p is None:
        return None
    return tuple((a - b) * 100 for a, b in zip(s, (p.home, p.draw, p.away)))


def _top(values) -> int | None:
    """가장 큰 값의 자리. 같은 값이 둘 이상이면 None — 고르지 않는다."""
    best = max(values)
    idx = [i for i, v in enumerate(values) if v == best]
    return idx[0] if len(idx) == 1 else None


@dataclass
class RoundVotes:
    """회차 전체 요약. 값이 없으면 None 이다 — 0 으로 채우지 않는다."""
    matches: int = 0                  # 회차 경기 수
    with_votes: int = 0               # 투표율을 읽은 경기
    total: int | None = None          # 경기마다 같은 투표 합 (다르면 None)
    captured_at: str = ""
    top_share: float | None = None    # 투표 1위 결과만으로 채운 조합의 비중 (곱)
    top_copies: float | None = None   # total × top_share — 같은 조합 예상 수
    top_market: float | None = None   # 그 조합이 시장 기준으로 모두 맞을 확률
    differ: list[int] = field(default_factory=list)   # 투표 1위 ≠ 시장 1위 경기 번호
    ties: list[int] = field(default_factory=list)     # 투표 1위가 동률인 경기


def round_votes(matches) -> RoundVotes:
    out = RoundVotes(matches=len(matches))
    have = [m for m in matches if shares(m) is not None]
    out.with_votes = len(have)
    if not have:
        return out
    totals = {m.votes.total for m in have}
    out.total = totals.pop() if len(totals) == 1 else None
    stamps = sorted({m.votes.captured_at for m in have if m.votes.captured_at})
    out.captured_at = stamps[-1] if stamps else ""

    tops: list[tuple[object, int]] = []
    for m in have:
        top = _top(shares(m))
        if top is None:
            out.ties.append(m.no)
            continue
        tops.append((m, top))
        p = m.probs
        if p is not None and p.pick in OUTCOMES and OUTCOMES.index(p.pick) != top:
            out.differ.append(m.no)

    # 조합 값은 **회차 전 경기**가 투표 1위를 가질 때만 만든다. 한 경기라도
    # 빠지면 14경기 조합이 아니다.
    if len(tops) != len(matches):
        return out
    share = 1.0
    for m, top in tops:
        share *= shares(m)[top]
    out.top_share = share
    if out.total:
        out.top_copies = out.total * share
    if all(m.probs is not None for m, _ in tops):
        market = 1.0
        for m, top in tops:
            market *= (m.probs.home, m.probs.draw, m.probs.away)[top]
        out.top_market = market
    return out
