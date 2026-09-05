"""분석: 배당 → 내재확률, 리그 백분위, 전략적 상성.

여기서는 추천 픽을 만들지 않는다. 사용자가 직접 판단하도록
"가공된 사실"만 제공하는 것이 이 모듈의 역할이다.
"""
from __future__ import annotations

import logging
from datetime import datetime

from . import analysis
from .models import Match, TeamStats
from .predict import additive_probabilities, round_winnability
from .settings import Settings

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# 배당 → 확률
# --------------------------------------------------------------------------
def attach_probabilities(matches: list[Match]) -> None:
    """배당 → 보정 확률 (지침 §3-(b) 가산 마진 제거)."""
    for match in matches:
        if not match.odds.available:
            continue
        try:
            match.probs = additive_probabilities(
                match.odds.home, match.odds.draw, match.odds.away)
        except ValueError as exc:
            log.warning("%s 확률 계산 실패: %s", match.title, exc)


def evaluate_round(matches: list[Match], expected_total: int = 14):
    """argmax 단통표의 회차 승산을 평가한다 (지침 §5)."""
    picks, missing = [], []
    for m in matches:
        if m.probs is not None:
            picks.append(m.probs.p_pick)
        else:
            missing.append(m.no)
    return round_winnability(picks, total_matches=expected_total, missing=missing)


# --------------------------------------------------------------------------
# 리그 백분위 (레이더 차트용)
# --------------------------------------------------------------------------
def percentile(value: float, population: list[float], invert: bool = False) -> float:
    """population 안에서 value 의 백분위(0~100).

    동점자는 절반만 인정하는 표준 방식을 쓴다.
    invert=True 면 값이 낮을수록 좋은 지표(실점 등)라 백분위를 뒤집는다.
    """
    if not population:
        return 50.0
    below = sum(1 for v in population if v < value)
    equal = sum(1 for v in population if v == value)
    pct = (below + 0.5 * equal) / len(population) * 100.0
    if invert:
        pct = 100.0 - pct
    return max(0.0, min(100.0, pct))


def _metric_value(stats: TeamStats, key: str) -> float | None:
    value = getattr(stats, key, None)
    return float(value) if isinstance(value, (int, float)) else None


def build_radar(matches: list[Match], settings: Settings) -> None:
    """각 경기에 레이더 차트 데이터를 붙인다.

    백분위는 **같은 리그 안에서만** 계산한다 (K리그2 팀을 EPL 기준으로
    줄 세우면 의미가 없다).
    """
    # 리그별 모집단 수집
    pools: dict[str, dict[str, list[float]]] = {}
    for match in matches:
        for profile in (match.home_profile, match.away_profile):
            if profile is None:
                continue
            bucket = pools.setdefault(match.league, {})
            for metric in settings.radar_metrics:
                val = _metric_value(profile.stats, metric["key"])
                if val is not None:
                    bucket.setdefault(metric["key"], []).append(val)

    # 리그 전체 팀 데이터가 있으면 그걸로 모집단을 넓힌다
    for match in matches:
        pool = pools.get(match.league, {})
        axes = []
        for metric in settings.radar_metrics:
            key, label = metric["key"], metric["label"]
            invert = bool(metric.get("invert"))
            population = pool.get(key) or []
            hv = _metric_value(match.home_profile.stats, key) if match.home_profile else None
            av = _metric_value(match.away_profile.stats, key) if match.away_profile else None
            if hv is None and av is None:
                continue
            axes.append({
                "key": key,
                "label": label,
                "invert": invert,
                "home_value": hv,
                "away_value": av,
                "home_pct": percentile(hv, population, invert) if hv is not None else None,
                "away_pct": percentile(av, population, invert) if av is not None else None,
            })
        match.radar = {"axes": axes, "league_size": len(
            {v for vals in pool.values() for v in vals}) or 0}


# --------------------------------------------------------------------------
# 전략적 상성
# --------------------------------------------------------------------------
# 후스코어드 특성 문구를 주제어로 묶는다. 홈팀의 강점 주제가 원정팀의 약점
# 주제와 겹치면 "노려볼 지점"으로 표시한다.
_TOPICS = {
    "set_piece": ["set piece", "corner", "free kick", "free-kick", "dead ball"],
    "aerial": ["aerial", "header", "high ball", "tall"],
    "counter": ["counter", "break", "transition", "fast"],
    "possession": ["possession", "keeping the ball", "short pass", "build"],
    "wing": ["wing", "crossing", "cross", "flank", "wide"],
    "through_ball": ["through ball", "threaded", "defence-splitting"],
    "long_ball": ["long ball", "direct", "route one"],
    "dribbling": ["dribbl", "individual skill", "solo run"],
    "shooting_long": ["long shot", "outside the box", "distance"],
    "defending_box": ["defending the box", "clearance", "blocking", "concede"],
    "pressing": ["press", "high line", "win the ball high"],
    "discipline": ["foul", "card", "discipline", "aggressive"],
    "finishing": ["finish", "conversion", "clinical", "scoring"],
    "goalkeeping": ["keeper", "goalkeep", "save"],
}

_TOPIC_KO = {
    "set_piece": "세트피스", "aerial": "공중볼", "counter": "역습",
    "possession": "점유·빌드업", "wing": "측면·크로스", "through_ball": "스루패스",
    "long_ball": "롱볼·direct", "dribbling": "드리블 돌파",
    "shooting_long": "중거리 슛", "defending_box": "박스 수비",
    "pressing": "전방 압박", "discipline": "파울·카드", "finishing": "결정력",
    "goalkeeping": "골키핑",
}


def _topics_of(phrases: list[str]) -> dict[str, str]:
    """문구 목록 → {주제: 원문} (첫 매칭만)."""
    found: dict[str, str] = {}
    for phrase in phrases or []:
        low = phrase.lower()
        for topic, keys in _TOPICS.items():
            if topic in found:
                continue
            if any(k in low for k in keys):
                found[topic] = phrase
    return found


def build_matchup(matches: list[Match]) -> None:
    """홈 강점 ↔ 원정 약점 (및 그 반대) 교차 대조."""
    for match in matches:
        hp, ap = match.home_profile, match.away_profile
        if hp is None or ap is None:
            continue
        notes = []

        h_str, a_weak = _topics_of(hp.strengths), _topics_of(ap.weaknesses)
        for topic in h_str.keys() & a_weak.keys():
            notes.append({
                "side": "home",
                "topic": _TOPIC_KO.get(topic, topic),
                "strength": h_str[topic],
                "weakness": a_weak[topic],
                "text": f"{hp.team.display}의 강점이 {ap.team.display}의 약점과 맞물립니다.",
            })

        a_str, h_weak = _topics_of(ap.strengths), _topics_of(hp.weaknesses)
        for topic in a_str.keys() & h_weak.keys():
            notes.append({
                "side": "away",
                "topic": _TOPIC_KO.get(topic, topic),
                "strength": a_str[topic],
                "weakness": h_weak[topic],
                "text": f"{ap.team.display}의 강점이 {hp.team.display}의 약점과 맞물립니다.",
            })

        match.matchup_notes = notes


# --------------------------------------------------------------------------
# 휴식일
# --------------------------------------------------------------------------
_DATE_FORMATS = ("%Y-%m-%d", "%d-%b-%y", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y")


def _parse_date(text: str) -> datetime | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def build_rest_days(matches: list[Match]) -> None:
    """직전 경기 이후 휴식일 계산 (킥오프와 최근 경기 날짜가 모두 있을 때만)."""
    for match in matches:
        kickoff = _parse_date((match.kickoff_kst or "").split(" ")[0])
        if kickoff is None:
            continue
        for profile in (match.home_profile, match.away_profile):
            if profile is None or not profile.form:
                continue
            last = _parse_date(profile.form[0].date)
            if last is not None:
                delta = (kickoff - last).days
                if 0 <= delta <= 60:
                    profile.rest_days = delta


def run_all(matches: list[Match], settings: Settings,
            season_matches: list | None = None) -> None:
    """분석 파이프라인 전체 실행.

    `season_matches` 는 Phase 2 의 시즌 경기 색인(`Report.season_matches`)이다.
    없으면 시간축 분석의 결과 지표(득점·승점·승무패)가 비고, 슛 기반 지표만
    남는다 — 실행이 죽지는 않는다.
    """
    attach_probabilities(matches)
    build_radar(matches, settings)
    build_matchup(matches)
    build_rest_days(matches)
    # Phase 2-A. 기존 산출물(probs·radar·matchup)을 건드리지 않고
    # `Match.analysis` 에만 붙는다.
    analysis.attach_time_context(matches, settings, season_matches)
    # Phase 2-G. 이미 만들어진 분석을 읽어 근거로 압축할 뿐 — 소스를 다시
    # 부르지 않고 확률(`Match.probs`)도 읽지 않는다.
    from . import evidence
    evidence.attach_evidence(matches, settings)
