"""팀 단위 시간축 분석 (Phase 2-A · Time Context).

**시즌 전체 경기력과 최근 경기력을 나란히 놓고 차이를 보여 주는 것**이
이 모듈의 전부다. 픽을 고르지 않고, 전력 점수를 만들지 않고, 두 기간을
하나의 평균으로 합치지도 않는다.

## 기간

`season` 과 `recent{N}` 을 각각 **독립적으로** 계산한다. N 은 코드에 박지
않고 설정에서 온다 (`analysis.periods`, 없으면 `fotmob.shot_recent_windows`).

    season    순위표·시즌 통계 피드 (팀이 치른 전 경기)
    recent10  최근 10경기
    recent6   최근 6경기
    recent5   최근 5경기
    recent3   최근 3경기

**시즌 값과 최근 값을 섞어 하나의 평균으로 만들지 않는다.** 표본이 다르고
(§CLAUDE.md 1-1-2) 의미도 다르다. 리포트는 두 값을 나란히 보여 주고,
그 차이(`trend`)는 파생값으로 따로 표시한다.

## 지표가 기간마다 다른 이유 — 없는 것을 만들지 않는다

| 지표 | 시즌 | 최근 N |
|---|---|---|
| 득점·실점·승점·득실차·승무패 | 순위표 | 시즌 경기 색인 (`SeasonMatch`) |
| xG | 시즌 xG 표 | 슛 계층 (`RecentShotAggregate`) |
| 슈팅·유효슈팅 | 시즌 통계 피드 | 슛 계층 |
| **npxG · xGOT · 박스 안 슈팅** | **없다** | 슛 계층 |
| **결정적 기회** | 시즌 통계 피드 | **없다** (경기별 값이 수집되지 않는다) |
| **피npxG · 피xGOT · 피슈팅 · 피유효슈팅** | 없다 | **경기 상세 창 1개에서만** |

빈칸을 추정으로 채우지 않는다. 없는 칸은 아예 지표를 만들지 않고, 왜
없는지를 `AnalysisAxis.notes` 에 남긴다.

수비 지표가 창 하나에서만 나오는 이유: 상대 팀의 경기별 슛 집계가 저장되지
않아(현재는 `opponent_id` 만 남는다) 창별로 다시 합산할 수 없다. 지금
쓸 수 있는 것은 `TeamStats` 의 `*_against_recent` 합계뿐이고, 그 표본은
`fotmob.match_detail_matches` 로 정한 창 하나다. 창별 수비 지표는 2-C 에서
상대 집계를 확보한 뒤에 만든다.

## 표본 세 가지를 구분한다

    requested_matches    요청한 창 (recent6 이면 6)
    available_matches    실제로 확보한 경기
    metric sample_count  **그 지표에** 값이 있던 경기

셋은 다를 수 있고 실제로 다르다. 평균은 언제나 **그 지표의 표본 수**로
나눈다 (Phase 1-B 에서 6으로 나눠 값이 절반이 된 사고가 있었다).
커버리지(`available/requested`)는 `DataQuality` 에 기간별로 남기는데,
**이것을 신뢰도 점수로 바꾸지 않는다.** 몇 경기로 계산했는지를 그대로
보여 줄 뿐이다.

시즌 초라 `1/6 경기` 인 것은 오류가 아니다. 그렇게 적고 넘어간다.

## 시점 (§11)

과거 경기는 `models.matches_before(as_of)` 로만 고른다 — 엄격한 `< as_of`
이고, 같은 시각에 시작하는 경기는 **쓰지 않는다**. 이 모듈은 자체 cutoff
로직을 두지 않는다.

슛 계층의 창은 수집 시점에 만들어져 있어 `as_of` 로 다시 자를 수 없다.
대신 창에 들어간 `match_ids` 를 시즌 경기 색인과 대조해,

  · `as_of` 이후 경기가 섞였으면 → 그 창의 슛 기반 지표를 **만들지 않는다**
  · 색인에 없어 시점을 확인할 수 없으면 → 값은 내되 그 사실을 notes 에 적는다

## 하지 않는 것

- 최근 값이 높다고 "상승세"·"전력 상승"·"강팀" 이라고 적지 않는다.
  `trend` 는 "최근이 시즌보다 +0.22" 까지가 전부다.
- 승/무/패로 폼 점수 같은 단일 숫자를 만들지 않는다.
- xPTS 를 여기서 다시 계산하지 않는다 (P1 의 `toto/xpts.py`, 연결은 2-D).
- 홈/원정 분리는 여기서 하지 않는다 (2-E). 다만 슛 계층에 `home{N}` ·
  `away{N}` 창이 이미 있어 그대로 이어 붙일 수 있다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .models import (DERIVED, OBSERVED, AnalysisAxis, DataQuality, Match,
                     MatchAnalysis, Metric, SeasonMatch, TeamAnalysis,
                     TeamProfile, matches_before)
from .settings import Settings

log = logging.getLogger(__name__)

SEASON = "season"
HIGHER_BETTER = "higher_better"
LOWER_BETTER = "lower_better"

# 베트맨 경기 시각(`Match.kickoff_kst`)은 한국시간 표기다. 시즌 경기 색인의
# kickoff 은 FotMob 이 UTC 로 주므로, 비교하려면 한쪽에 시간대를 붙여야 한다.
# **임의로 정하는 것이 아니라** 필드 이름이 이미 KST 라고 밝히고 있다.
KST = timezone(timedelta(hours=9))

# 트렌드 밴드. 값이 아니라 라벨이다 — 점수로 바꾸지 않는다.
HIGHER, LOWER, SIMILAR = "higher", "lower", "similar"
TREND_BANDS = (HIGHER, LOWER, SIMILAR)
# 두 값을 뺄 수 없어 추세로 읽으면 안 되는 경우. 값은 None 이고 사유가 붙는다.
NOT_MEANINGFUL = "not_meaningful"
TREND_STATES = TREND_BANDS + (NOT_MEANINGFUL,)


# --------------------------------------------------------------------------
# 0. 값의 출처와 산출 방식 (2-B 교정)
# --------------------------------------------------------------------------
# 실물에서 겪은 사고: 풀럼의 시즌 xG 는 1.33(경기 스탯), 최근 xG 는 1.39
# (슛맵 합산)이었다. **같은 한 경기**인데 0.06 이 달랐다. 슛맵은 슛마다 xG 를
# 반올림해 주므로 합치면 누적되기 때문이다(§1-1-3, 실측 최대 +0.09).
# 그 차이를 빼서 "+0.06" 이라고 적으면 측정 방식의 차이가 경기력 변화로
# 둔갑한다. 그래서 빼기 전에 **원천(source)과 산출 방식(basis)** 을 본다.
#
# source — 어느 피드에서 왔나
STANDINGS = "standings"                  # 리그 순위표
SEASON_STATS_FEED = "season_stats_feed"  # FotMob 시즌 통계 피드 (stats.teams[])
SEASON_XG_TABLE = "season_xg_table"      # FotMob 시즌 xG 표
SEASON_MATCH_INDEX = "season_match_index"  # 시즌 경기 색인 (SeasonMatch)
SHOTMAP = "shotmap"                      # matchDetails 의 슛맵 이벤트
MATCH_STATS = "match_stats"              # matchDetails 의 경기 스탯 표
DERIVED_SOURCE = "derived"               # 위 값들에서 계산한 파생값

# measurement_basis — 그 피드에서 어떻게 만들어졌나
FINAL_SCORE = "final_score"    # 최종 스코어를 센 값 (득점·승점·승무패…)
MATCH_STAT = "match_stat"      # 소스가 계산해 준 경기 스탯 값
SHOT_EVENTS = "shot_events"    # 슛 이벤트를 하나씩 합산한 값
MIXED_BASIS = "mixed"          # 서로 다른 방식이 섞였다

# **직접 비교 가능한 원천 묶음.** 서로 다른 피드지만 같은 것을 세고 있어
# 값이 일치하는 쌍만 넣는다. 순위표의 득점·승점 누계는 정의상 최종 스코어의
# 합이고, 260048 실물에서도 두 경로가 정확히 같았다(첼시 3.00 = 3.00).
# **추측으로 늘리지 않는다.**
COMPARABLE_SOURCES: tuple[frozenset[str], ...] = (
    frozenset({STANDINGS, SEASON_MATCH_INDEX}),
)

# (기간 종류, 지표) → (source, basis).
# 시즌과 최근이 **다른 피드에서 온다는 사실 자체**가 여기 적혀 있다.
_SEASON_ORIGIN: dict[str, tuple[str, str]] = {
    "goals": (STANDINGS, FINAL_SCORE),
    "goals_against": (STANDINGS, FINAL_SCORE),
    "points": (STANDINGS, FINAL_SCORE),
    "goal_diff": (STANDINGS, FINAL_SCORE),
    "wins": (STANDINGS, FINAL_SCORE),
    "draws": (STANDINGS, FINAL_SCORE),
    "losses": (STANDINGS, FINAL_SCORE),
    "xg": (SEASON_XG_TABLE, MATCH_STAT),
    "xgd": (SEASON_XG_TABLE, MATCH_STAT),
    "shots": (SEASON_STATS_FEED, MATCH_STAT),
    "shots_on_target": (SEASON_STATS_FEED, MATCH_STAT),
    "shots_against": (SEASON_STATS_FEED, MATCH_STAT),
    "shots_on_target_against": (SEASON_STATS_FEED, MATCH_STAT),
    "big_chances": (SEASON_STATS_FEED, MATCH_STAT),
    "xg_per_shot": (DERIVED_SOURCE, MATCH_STAT),
    "on_target_rate": (DERIVED_SOURCE, MATCH_STAT),
    "goals_minus_xg": (DERIVED_SOURCE, MIXED_BASIS),
}
_RECENT_ORIGIN: dict[str, tuple[str, str]] = {
    "goals": (SEASON_MATCH_INDEX, FINAL_SCORE),
    "goals_against": (SEASON_MATCH_INDEX, FINAL_SCORE),
    "points": (SEASON_MATCH_INDEX, FINAL_SCORE),
    "goal_diff": (SEASON_MATCH_INDEX, FINAL_SCORE),
    "wins": (SEASON_MATCH_INDEX, FINAL_SCORE),
    "draws": (SEASON_MATCH_INDEX, FINAL_SCORE),
    "losses": (SEASON_MATCH_INDEX, FINAL_SCORE),
    "xg": (SHOTMAP, SHOT_EVENTS),
    "npxg": (SHOTMAP, SHOT_EVENTS),
    "xgot": (SHOTMAP, SHOT_EVENTS),
    "shots": (SHOTMAP, SHOT_EVENTS),
    "shots_on_target": (SHOTMAP, SHOT_EVENTS),
    "shots_inside_box": (SHOTMAP, SHOT_EVENTS),
    "shots_outside_box": (SHOTMAP, SHOT_EVENTS),
    "npxga": (MATCH_STATS, MATCH_STAT),
    "xgot_against": (MATCH_STATS, MATCH_STAT),
    "shots_against": (MATCH_STATS, MATCH_STAT),
    "shots_on_target_against": (MATCH_STATS, MATCH_STAT),
    "npxgd": (DERIVED_SOURCE, MIXED_BASIS),
    "xg_per_shot": (DERIVED_SOURCE, SHOT_EVENTS),
    "npxg_per_shot": (DERIVED_SOURCE, SHOT_EVENTS),
    "box_shot_share": (DERIVED_SOURCE, SHOT_EVENTS),
    "on_target_rate": (DERIVED_SOURCE, SHOT_EVENTS),
    "goals_minus_xg": (DERIVED_SOURCE, MIXED_BASIS),
    "goals_minus_npxg": (DERIVED_SOURCE, MIXED_BASIS),
    "goals_minus_xgot": (DERIVED_SOURCE, MIXED_BASIS),
}


def metric_origin(period: str, name: str) -> tuple[str, str]:
    """(source, measurement_basis). 모르면 빈 문자열 — 지어내지 않는다."""
    table = _SEASON_ORIGIN if period == SEASON else _RECENT_ORIGIN
    return table.get(name, ("", ""))


def sources_comparable(a: str, b: str) -> bool:
    """두 원천의 값을 직접 빼도 되나.

    같은 원천이면 당연히 되고, 아니면 **명시적으로 등록된 쌍**만 된다.
    "아마 비슷할 것" 으로 통과시키지 않는다.
    """
    if not a or not b:
        return False
    if a == b:
        return True
    return any({a, b} <= group for group in COMPARABLE_SOURCES)


# --------------------------------------------------------------------------
# 1. 지표 카탈로그
# --------------------------------------------------------------------------
# {키: (라벨, 단위, 방향, 묶음)}
#
# 방향은 §9 의 목록을 그대로 옮긴 것이다. **목록에 없는 지표는 비워 둔다** —
# 슈팅 수는 많다고 반드시 좋은 것이 아니고(역습 팀은 적게 쏜다), 무승부 수도
# 좋고 나쁨을 말할 수 없다. 아래 EXTRA_DIRECTIONS 만 명세 밖의 판단이다.
SPECS: dict[str, tuple[str, str, str, str]] = {
    # ---- 공격 ----
    "goals":                   ("득점", "per_match", HIGHER_BETTER, "attack"),
    "xg":                      ("xG", "per_match", HIGHER_BETTER, "attack"),
    "npxg":                    ("npxG", "per_match", HIGHER_BETTER, "attack"),
    "xgot":                    ("xGOT", "per_match", HIGHER_BETTER, "attack"),
    "shots":                   ("슈팅", "per_match", "", "attack"),
    "shots_on_target":         ("유효슈팅", "per_match", HIGHER_BETTER, "attack"),
    "shots_inside_box":        ("박스 안 슈팅", "per_match", HIGHER_BETTER, "attack"),
    "shots_outside_box":       ("박스 밖 슈팅", "per_match", "", "attack"),
    "big_chances":             ("결정적 기회", "per_match", HIGHER_BETTER, "attack"),
    # ---- 수비 ----
    "goals_against":           ("실점", "per_match", LOWER_BETTER, "defense"),
    "npxga":                   ("피npxG", "per_match", LOWER_BETTER, "defense"),
    "xgot_against":            ("피xGOT", "per_match", LOWER_BETTER, "defense"),
    "shots_against":           ("피슈팅", "per_match", LOWER_BETTER, "defense"),
    "shots_on_target_against": ("피유효슈팅", "per_match", LOWER_BETTER, "defense"),
    # ---- 결과 ----
    "points":                  ("승점", "per_match", HIGHER_BETTER, "result"),
    "goal_diff":               ("득실차", "per_match", HIGHER_BETTER, "result"),
    "xgd":                     ("xGD", "per_match", HIGHER_BETTER, "result"),
    "npxgd":                   ("npxGD", "per_match", HIGHER_BETTER, "result"),
    "wins":                    ("승", "count", HIGHER_BETTER, "result"),
    "draws":                   ("무", "count", "", "result"),
    "losses":                  ("패", "count", LOWER_BETTER, "result"),
}

# ---- 2-B 파생지표 --------------------------------------------------------
# 원재료(shots·xG·npxG·xGOT·goals)는 위 SPECS 에 이미 있다. 여기에는
# **비율·차이만** 더한다. 이름을 그대로 쓴다 — "결정력"·"전환율"·
# "finishing" 같은 해석적 이름을 붙이지 않는다 (§5-6, §5-7).
DERIVED_SPECS: dict[str, tuple[str, str, str, str]] = {
    "xg_per_shot":       ("슛당 xG", "per_shot", HIGHER_BETTER, "attack"),
    "npxg_per_shot":     ("슛당 npxG", "per_shot", HIGHER_BETTER, "attack"),
    "box_shot_share":    ("박스 안 슈팅 비율", "%", HIGHER_BETTER, "attack"),
    "on_target_rate":    ("유효슈팅 비율", "%", HIGHER_BETTER, "attack"),
    # 아래 셋은 **방향을 정하지 않는다.** 득점이 xG 보다 많다고 좋은 것도,
    # 적다고 나쁜 것도 아니다 — 표본이 작을수록 크게 흔들리는 차이값이다.
    "goals_minus_xg":    ("득점 − xG", "per_match", "", "attack"),
    "goals_minus_npxg":  ("득점 − npxG", "per_match", "", "attack"),
    "goals_minus_xgot":  ("득점 − xGOT", "per_match", "", "attack"),
}
SPECS.update(DERIVED_SPECS)

# 지표 묶음 (2-B §15). **점수 계산용이 아니다** — 2-I 가 같은 사실을 여러 번
# 세지 않도록 붙이는 메타데이터다. xG·npxG·슛당 xG 는 같은 이야기의 세 얼굴이다.
VOLUME = "volume"
CHANCE_CREATION = "chance_quality"
EXECUTION = "execution"
GAP = "sustainability_gap"
OUTCOME = "outcome"
DEFENSE_GROUP = "defense"
RESULT_GROUP = "result"

GROUPS: dict[str, str] = {
    "shots": VOLUME, "shots_on_target": VOLUME, "shots_inside_box": VOLUME,
    "shots_outside_box": VOLUME,
    "xg": CHANCE_CREATION, "npxg": CHANCE_CREATION,
    "big_chances": CHANCE_CREATION, "xg_per_shot": CHANCE_CREATION,
    "npxg_per_shot": CHANCE_CREATION, "box_shot_share": CHANCE_CREATION,
    "xgot": EXECUTION, "on_target_rate": EXECUTION,
    "goals_minus_xg": GAP, "goals_minus_npxg": GAP, "goals_minus_xgot": GAP,
    "goals": OUTCOME,
    "goals_against": DEFENSE_GROUP, "npxga": DEFENSE_GROUP,
    "xgot_against": DEFENSE_GROUP, "shots_against": DEFENSE_GROUP,
    "shots_on_target_against": DEFENSE_GROUP,
    "points": RESULT_GROUP, "goal_diff": RESULT_GROUP, "xgd": RESULT_GROUP,
    "npxgd": RESULT_GROUP, "wins": RESULT_GROUP, "draws": RESULT_GROUP,
    "losses": RESULT_GROUP,
}

# §9 가 직접 방향을 지정한 지표.
SPEC_DIRECTIONS = frozenset((
    "goals", "xg", "npxg", "xgot", "shots_on_target", "shots_inside_box",
    "big_chances", "points", "xgd",
    "goals_against", "npxga", "xgot_against", "shots_against",
    "shots_on_target_against"))
# 명세에 없지만 방향이 자명해 붙인 것. 어디까지가 명세인지 구분해 둔다.
EXTRA_DIRECTIONS = frozenset((
    "goal_diff", "npxgd", "wins", "losses",
    # 2-B 파생 비율. 명세가 방향을 지정하지는 않았지만 자명하다.
    "xg_per_shot", "npxg_per_shot", "box_shot_share", "on_target_rate"))
# 방향을 정하지 않은 지표 (많고 적음이 곧 좋고 나쁨이 아니다).
# 득점−xG 계열이 여기 있는 이유: 양수를 "결정력이 좋다" 로 읽으면 안 된다.
UNDIRECTED = frozenset((
    "shots", "draws", "shots_outside_box",
    "goals_minus_xg", "goals_minus_npxg", "goals_minus_xgot"))

ATTACK = tuple(k for k, v in SPECS.items()
               if v[3] == "attack" and k not in DERIVED_SPECS)
DEFENSE = tuple(k for k, v in SPECS.items() if v[3] == "defense")
RESULT = tuple(k for k, v in SPECS.items() if v[3] == "result")

# 슛 계층(`RecentShotAggregate`)이 창별로 주는 지표 → 이 모듈의 지표 이름.
_FROM_SHOTS = {
    "xg": "xg", "npxg": "npxg", "xgot": "xgot", "shots": "shots",
    "shots_on_target": "shots_on_target",
    "shots_inside_box": "shots_inside_box",
}
# `TeamStats` 의 최근 N경기 피지표 → 이 모듈의 지표 이름.
# 창이 하나뿐이라(`fotmob.match_detail_matches`) 그 창에서만 쓴다.
_FROM_STATS_AGAINST = {
    "npxga": "npxga_recent",
    "xgot_against": "xgot_against_recent",
    "shots_against": "shots_against_recent",
    "shots_on_target_against": "shots_on_target_against_recent",
}

# 기본 트렌드 문턱. 설정에 없을 때만 쓰는 값이고, 설정 파일 쪽에 같은 값과
# 함께 "운영용 기준이며 통계적으로 검증된 기준이 아님" 이라고 적어 두었다.
DEFAULT_TREND_THRESHOLDS: dict[str, float] = {
    "default": 0.20,
    "goals": 0.30, "goals_against": 0.30, "goal_diff": 0.40,
    "xg": 0.25, "npxg": 0.25, "xgot": 0.25, "npxga": 0.25,
    "xgot_against": 0.25, "xgd": 0.35, "npxgd": 0.35,
    "shots": 2.0, "shots_against": 2.0,
    "shots_on_target": 1.0, "shots_on_target_against": 1.0,
    "shots_inside_box": 1.5,
    "points": 0.40,
    "wins": 1.0, "draws": 1.0, "losses": 1.0,
    "big_chances": 0.8,
}
# 트렌드를 만들 최소 표본. 양쪽 기간 모두 이 수를 넘어야 한다.
DEFAULT_TREND_MIN_SAMPLE = 3


def period_name(window: int) -> str:
    return f"recent{int(window)}"


def period_label(period: str) -> str:
    if period == SEASON:
        return "시즌"
    if period.startswith("recent"):
        return f"최근 {period[6:]}경기"
    if period.startswith("trend"):
        return f"시즌 대비 최근 {period[5:]}경기"
    return period


def metric_key(period: str, name: str) -> str:
    """축 안에서 지표를 가리키는 키. `기간.지표` 로 고정한다."""
    return f"{period}.{name}"


# --------------------------------------------------------------------------
# 2. 설정 읽기
# --------------------------------------------------------------------------
def periods_from(settings: Settings) -> list[int]:
    """분석할 최근 N 목록. 큰 창부터 내려온다.

    `analysis.periods` 가 있으면 그것을, 없으면 슛 계층이 실제로 만들어 둔
    창(`fotmob.shot_recent_windows`)을 쓴다. **N 을 코드에 박지 않는다.**
    """
    raw = (getattr(settings, "analysis", None) or {}).get("periods")
    if not raw:
        raw = (settings.fotmob or {}).get("shot_recent_windows") or [3, 5, 6, 10]
    out = []
    for v in raw:
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n > 0 and n not in out:
            out.append(n)
    return sorted(out, reverse=True)


def thresholds_from(settings: Settings) -> dict[str, float]:
    cfg = (getattr(settings, "analysis", None) or {}).get("trend_thresholds")
    out = dict(DEFAULT_TREND_THRESHOLDS)
    if isinstance(cfg, dict):
        for k, v in cfg.items():
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if f >= 0:                      # 음수 문턱은 의미가 없다
                out[str(k)] = f
    return out


def detail_window_of(settings: Settings) -> int:
    """경기 상세를 받은 경기 수. 수비 최근 지표가 이 창에서만 나온다."""
    try:
        return int((settings.fotmob or {}).get("match_detail_matches", 6))
    except (TypeError, ValueError):
        return 6


# --------------------------------------------------------------------------
# 3. 시점
# --------------------------------------------------------------------------
def as_of_from_match(match: Match) -> datetime | None:
    """`Match.kickoff_kst` → 시간대가 붙은 datetime.

    필드 이름이 KST 라고 밝히고 있으므로 UTC+9 를 붙인다. 시즌 경기 색인의
    kickoff 은 UTC 라서 시간대가 없으면 비교 자체가 되지 않는다
    (`matches_before` 가 TypeError 를 삼키고 전부 버린다).
    파싱하지 못하면 None — 그러면 과거 경기 구간이 비고, 그 사실이 notes 에
    남는다. 없는 시각을 지어내지 않는다.
    """
    text = (getattr(match, "kickoff_kst", "") or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)


def team_history(season: list[SeasonMatch], team: str,
                 as_of: datetime | None) -> list[SeasonMatch]:
    """`as_of` 이전에 끝난 그 팀의 경기 (오래된 것부터).

    cutoff 는 `models.matches_before` 하나만 쓴다 — 여기서 다시 날짜를
    비교하지 않는다.
    """
    if not team:
        return []
    return [m for m in matches_before(season, as_of)
            if team in (m.home_team, m.away_team)]


# --------------------------------------------------------------------------
# 4. 기간별 값 만들기
# --------------------------------------------------------------------------
def _num(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None          # NaN 제외


def _put(out: dict, name: str, value, sample: int | None,
         note: str = "") -> None:
    """값이 있을 때만 넣는다. **None 은 넣지 않는다** — 0 과 구분하기 위해서다.

    `value=0.0` 은 실제 값이라 그대로 들어간다.
    """
    v = _num(value)
    if v is None:
        return
    out[name] = (v, sample, note)


def _season_values(stats) -> dict[str, tuple[float, int | None, str]]:
    """시즌 지표 {이름: (값, 표본, 비고)}.

    표본은 그 값이 나온 경기 수다. xG 계열은 순위표와 집계 시점이 달라
    `xg_played` 를 쓴다 (`TeamStats` 주석 참고).
    """
    out: dict[str, tuple[float, int | None, str]] = {}
    if stats is None:
        return out
    played = stats.played
    xg_played = stats.xg_played or played

    _put(out, "goals", stats.goals_for_pg, played)
    _put(out, "goals_against", stats.goals_against_pg, played)
    _put(out, "points", stats.points_pg, played)
    if stats.goal_diff is not None and played:
        _put(out, "goal_diff", stats.goal_diff / played, played)
    _put(out, "wins", stats.wins, played)
    _put(out, "draws", stats.draws, played)
    _put(out, "losses", stats.losses, played)

    _put(out, "xg", stats.xg_pg, xg_played)
    xg, xga = stats.xg_pg, stats.xga_pg
    if xg is not None and xga is not None:
        _put(out, "xgd", xg - xga, xg_played)

    _put(out, "shots", stats.shots_pg, played)
    _put(out, "shots_on_target", stats.shots_on_target_pg, played)
    _put(out, "big_chances", stats.big_chances_pg, played)
    # 시즌 피지표는 소스가 주는 경우에만 있다 (보통 비어 있다).
    _put(out, "shots_against", stats.shots_against_pg, played)
    _put(out, "shots_on_target_against", stats.shots_on_target_against_pg,
         played)
    return out


def _result_values(history: list[SeasonMatch], team: str, window: int
                   ) -> tuple[dict[str, tuple[float, int | None, str]], int]:
    """최근 `window` 경기의 결과 지표. 실제 스코어에서 직접 센다.

    슛맵의 득점을 쓰지 않는 이유: 슛맵은 상대 자책골을 우리 득점으로 세지
    않는다. 승점·득실차의 기준이 되는 것은 최종 스코어다.
    """
    recent = history[-window:] if window > 0 else []
    n = len(recent)
    out: dict[str, tuple[float, int | None, str]] = {}
    if not n:
        return out, 0

    gf = ga = pts = w = d = ls = 0
    counted = 0
    for m in recent:
        home = m.home_team == team
        mine = m.home_goals if home else m.away_goals
        theirs = m.away_goals if home else m.home_goals
        if mine is None or theirs is None:
            continue                       # 점수가 없는 경기는 세지 않는다
        counted += 1
        gf += mine
        ga += theirs
        if mine > theirs:
            pts += 3
            w += 1
        elif mine == theirs:
            pts += 1
            d += 1
        else:
            ls += 1
    if not counted:
        return out, n

    _put(out, "goals", gf / counted, counted)
    _put(out, "goals_against", ga / counted, counted)
    _put(out, "points", pts / counted, counted)
    _put(out, "goal_diff", (gf - ga) / counted, counted)
    _put(out, "wins", w, counted)
    _put(out, "draws", d, counted)
    _put(out, "losses", ls, counted)
    return out, n


def _agg_field(agg, name: str):
    """`RecentShotAggregate` 든 그것을 풀어 놓은 dict 든 같은 방식으로 읽는다."""
    if agg is None:
        return None
    if isinstance(agg, dict):
        return agg.get(name)
    return getattr(agg, name, None)


def _agg_avg(agg, metric: str) -> tuple[float | None, int]:
    """(경기당 값, 그 지표의 표본 수). **표본 수로 나눈다.**"""
    sums = _agg_field(agg, "sums") or {}
    counts = _agg_field(agg, "counts") or {}
    n = int(counts.get(metric, 0) or 0)
    if not n or metric not in sums:
        return None, n
    return float(sums[metric]) / n, n


def _shot_values(agg) -> dict[str, tuple[float, int | None, str]]:
    out: dict[str, tuple[float, int | None, str]] = {}
    if agg is None:
        return out
    for name, source in _FROM_SHOTS.items():
        value, n = _agg_avg(agg, source)
        _put(out, name, value, n)
    return out


def _defense_recent_values(stats) -> dict[str, tuple[float, int | None, str]]:
    """경기 상세 창의 피지표. 창이 하나뿐이라 그 창에서만 부른다."""
    out: dict[str, tuple[float, int | None, str]] = {}
    if stats is None:
        return out
    counts = stats.recent_counts or {}
    for name, field_name in _FROM_STATS_AGAINST.items():
        total = getattr(stats, field_name, None)
        if total is None:
            continue
        n = counts.get(field_name) or stats.recent_matches
        if not n:
            continue
        _put(out, name, float(total) / n, int(n))
    return out


# --------------------------------------------------------------------------
# 5. 트렌드
# --------------------------------------------------------------------------
def trend_band(name: str, delta: float,
               thresholds: dict[str, float]) -> tuple[str, float]:
    """(밴드, 쓰인 문턱). 밴드는 라벨이지 점수가 아니다.

    문턱 미만이면 `similar` 다. 이 문턱은 **운영용 표시 기준이며 통계적으로
    검증된 기준이 아니다** — 설정 파일에 같은 문구를 적어 두었다.
    """
    limit = thresholds.get(name, thresholds.get("default", 0.2))
    try:
        limit = abs(float(limit))
    except (TypeError, ValueError):
        limit = 0.2
    if abs(delta) < limit:
        return SIMILAR, limit
    return (HIGHER if delta > 0 else LOWER), limit


def parse_trend_band(metric: Metric | None) -> str:
    """트렌드 지표의 상태를 되읽는다 (note 앞에 토큰으로 적어 둔다).

    `higher`/`lower`/`similar` 또는 `not_meaningful` 을 돌려준다.
    """
    if metric is None or not metric.note:
        return ""
    head = metric.note.split(" ", 1)[0]
    return head if head in TREND_STATES else ""


# 트렌드를 만들지 못한 사유 코드.
BLOCK_MISSING = "missing"
BLOCK_METRIC = "metric_mismatch"
BLOCK_SOURCE = "source"
BLOCK_BASIS = "basis"
BLOCK_COUNT_UNIT = "count_unit"
BLOCK_SAME_SET = "same_match_set"
BLOCK_SAMPLE = "sample"
# 창 길이와 무관한 사유 — 지표의 성질에서 온다. 창마다 반복해 적지 않는다.
STRUCTURAL_BLOCKS = frozenset({BLOCK_METRIC, BLOCK_SOURCE, BLOCK_BASIS,
                               BLOCK_COUNT_UNIT})


def trend_allowed(name: str, season_metric: Metric | None,
                  recent_metric: Metric | None, *, same_match_set: bool,
                  min_sample: int) -> tuple[bool, str, str]:
    """시즌 값과 최근 값을 빼도 되나. `(가능한가, 사유 코드, 사유 문구)`.

    하나라도 어긋나면 트렌드를 **만들지 않는다** — 값의 차이는 있어도 그것을
    추세로 읽을 수 없기 때문이다. 검사 순서는 '더 근본적인 이유' 순이다.
    """
    if season_metric is None or recent_metric is None:
        return False, BLOCK_MISSING, "한쪽 기간에 값이 없음"
    if season_metric.name != recent_metric.name:
        return False, BLOCK_METRIC, "서로 다른 지표"
    if not sources_comparable(season_metric.source, recent_metric.source):
        return False, BLOCK_SOURCE, (
            f"측정 원천이 다름 (시즌 {season_metric.source or '미상'}"
            f" ↔ 최근 {recent_metric.source or '미상'})")
    if (not season_metric.measurement_basis
            or season_metric.measurement_basis
            != recent_metric.measurement_basis):
        return False, BLOCK_BASIS, (
            f"산출 방식이 다름 (시즌 "
            f"{season_metric.measurement_basis or '미상'} ↔ 최근 "
            f"{recent_metric.measurement_basis or '미상'})")
    if season_metric.unit == "count":
        # 승/무/패는 **누계**다. "시즌 5승" 과 "최근 3경기 3승" 을 빼면 −2 가
        # 나오는데 이건 경기 수가 달라서 생긴 숫자이지 추세가 아니다.
        # 경기당으로 환산한 승점(points)이 이미 같은 이야기를 하고 있다.
        return False, BLOCK_COUNT_UNIT, "누적 개수라 기간 길이가 다르면 뺄 수 없음"
    if same_match_set:
        return False, BLOCK_SAME_SET, "동일 경기 표본 (최근 구간이 시즌 전체와 같음)"
    s_n, r_n = season_metric.sample_count, recent_metric.sample_count
    if not isinstance(s_n, int) or not isinstance(r_n, int) \
            or s_n <= 0 or r_n <= 0:
        return False, BLOCK_SAMPLE, "표본 수를 알 수 없음"
    if s_n < min_sample or r_n < min_sample:
        return False, BLOCK_SAMPLE, (
            f"표본 부족 (시즌 {s_n} · 최근 {r_n}, 최소 {min_sample})")
    return True, "", ""


def trend_min_sample(settings: Settings) -> int:
    cfg = (getattr(settings, "analysis", None) or {}).get("trend_min_sample")
    try:
        return max(1, int(cfg))
    except (TypeError, ValueError):
        return DEFAULT_TREND_MIN_SAMPLE


# --------------------------------------------------------------------------
# 6. 축 만들기
# --------------------------------------------------------------------------
def _metric(name: str, period: str, value: float, sample: int | None,
            provenance: str = OBSERVED, note: str = "") -> Metric:
    label, unit, direction, _family = SPECS[name]
    source, basis = metric_origin(period, name)
    return Metric(name=name, label=label, value=value, provenance=provenance,
                  period=period, sample_count=sample, unit=unit, note=note,
                  direction=direction, group=GROUPS.get(name, ""),
                  source=source, measurement_basis=basis)


def _window_time_check(agg, allowed_ids: set[str], known_ids: set[str]
                       ) -> tuple[list[str], list[str]]:
    """창에 들어간 경기를 시즌 색인과 대조한다.

    돌려주는 것: (`as_of` 이후로 확인된 경기, 시점을 확인할 수 없는 경기).
    슛 계층의 창은 수집 시점에 이미 만들어져 있어 다시 자를 수 없으므로,
    자르는 대신 **오염됐는지 확인**한다.
    """
    ids = [str(x) for x in (_agg_field(agg, "match_ids") or [])]
    future = [i for i in ids if i in known_ids and i not in allowed_ids]
    unknown = [i for i in ids if i not in known_ids]
    return future, unknown


def build_time_context(profile: TeamProfile | None, team: str,
                       season_matches: list[SeasonMatch] | None,
                       as_of: datetime | None,
                       windows: list[int],
                       thresholds: dict[str, float],
                       detail_window: int = 6,
                       quality: DataQuality | None = None,
                       min_sample: int = DEFAULT_TREND_MIN_SAMPLE
                       ) -> AnalysisAxis:
    """시즌 · 최근 N경기 · 그 차이를 한 축에 담는다.

    키는 `기간.지표` 다 (`season.xg`, `recent6.xg`, `trend6.xg`). 기간을
    키에 넣어 두면 시즌 값과 최근 값이 **구조적으로 섞일 수 없다.**

    트렌드는 **뺄 수 있을 때만** 만든다 (`trend_allowed`). 못 만들면 값이
    None 인 지표를 사유와 함께 남긴다 — 지우면 왜 없는지 알 수 없고,
    숫자를 남기면 측정 방식의 차이가 추세로 읽힌다.
    """
    axis = AnalysisAxis(name="time_context")
    stats = getattr(profile, "stats", None) if profile else None
    aggregates = getattr(profile, "shot_aggregates", None) or {}
    season = list(season_matches or [])

    history = team_history(season, team, as_of)
    known_ids = {str(m.match_id) for m in season if m.match_id}
    allowed_ids = {str(m.match_id) for m in matches_before(season, as_of)
                   if m.match_id}

    windows = sorted({int(w) for w in windows if int(w) > 0}, reverse=True)
    axis.requested_matches = windows[0] if windows else None
    axis.available_matches = len(history)

    # ---- 시즌 --------------------------------------------------------------
    season_values = _season_values(stats)
    for name, (value, sample, note) in season_values.items():
        axis.metrics[metric_key(SEASON, name)] = _metric(
            name, SEASON, value, sample, note=note)
    played = getattr(stats, "played", None) if stats else None
    if season_values:
        axis.notes.append(f"시즌: {played if played is not None else '?'}경기 "
                          "(순위표·시즌 통계 피드 기준)")
    else:
        axis.notes.append("시즌: 값 없음 (순위표를 받지 못했습니다)")
    if quality is not None:
        quality.mark("time_context.season", bool(season_values),
                     requested=played, available_matches=played,
                     reason="" if season_values else "시즌 지표 없음")

    # 시즌 스냅샷은 수집 시점 기준이라 `as_of` 로 자를 수 없다. 과거 경기
    # 수와 어긋나면 그 사실을 밝힌다 — 조용히 지나가면 과거 경기를 분석할 때
    # 미래가 섞인 줄 모르게 된다.
    if played is not None and as_of is not None and history \
            and played > len(history):
        axis.notes.append(
            f"시즌 지표는 수집 시점 스냅샷입니다 — 순위표 {played}경기 vs "
            f"기준시각 이전 {len(history)}경기. 기준시각으로 잘리지 않습니다")

    # ---- 최근 N경기 ---------------------------------------------------------
    blocked: dict[str, set[str]] = {}     # 창마다 다른 사유 (표본·경기집합)
    structural: dict[str, set[str]] = {}  # 창과 무관한 사유 (원천·방식·단위)
    for window in windows:
        period = period_name(window)
        values: dict[str, tuple[float, int | None, str]] = {}

        result_values, available = _result_values(history, team, window)
        values.update(result_values)

        agg = aggregates.get(f"all{window}")
        future, unknown = _window_time_check(agg, allowed_ids, known_ids)
        shot_available = _agg_field(agg, "available_matches")
        if agg is not None and future:
            axis.notes.append(
                f"{period_label(period)}: 슛 지표 제외 — 기준시각 이후 경기 "
                f"{len(future)}건이 창에 들어 있습니다")
        elif agg is not None:
            values.update(_shot_values(agg))
            if int(shot_available or 0) > available:
                available = int(shot_available or 0)
            if unknown:
                axis.notes.append(
                    f"{period_label(period)}: 시즌 색인에 없어 시점을 확인하지 "
                    f"못한 경기 {len(unknown)}건이 슛 지표에 들어 있습니다")
            # 수비 지표는 경기 상세 창 하나에서만 나온다.
            if window == detail_window:
                values.update(_defense_recent_values(stats))
                npxg = values.get("npxg")
                npxga = values.get("npxga")
                if npxg and npxga and npxg[1] == npxga[1]:
                    _put(values, "npxgd", npxg[0] - npxga[0], npxg[1])
                elif npxg and npxga:
                    axis.notes.append(
                        f"{period_label(period)}: npxG 표본 {npxg[1]} · "
                        f"피npxG 표본 {npxga[1]} 이 달라 npxGD 를 만들지 "
                        "않았습니다")

        for name, (value, sample, note) in values.items():
            axis.metrics[metric_key(period, name)] = _metric(
                name, period, value, sample, note=note)

        axis.notes.append(f"{period_label(period)}: {available}/{window}경기")
        if quality is not None:
            quality.mark(f"time_context.{period}", bool(values),
                         requested=window, available_matches=available,
                         reason="" if values else "표본 없음")

        # ---- 트렌드 (시즌 대비) --------------------------------------------
        # **빼기 전에 뺄 수 있는지 먼저 본다.** 원천이나 산출 방식이 다르면
        # 두 값의 차이는 경기력 변화가 아니라 측정 방식의 차이다.
        # 최근 구간이 시즌 전체와 같은 경기면 비교 자체가 성립하지 않는다.
        same_set = (played is not None and available >= played)
        for name, (value, sample, _note) in values.items():
            base = season_values.get(name)
            if base is None:
                continue
            season_metric = axis.get(metric_key(SEASON, name))
            recent_metric = axis.get(metric_key(period, name))
            ok, code, reason = trend_allowed(
                name, season_metric, recent_metric,
                same_match_set=same_set, min_sample=min_sample)
            key = metric_key(f"trend{window}", name)
            label = f"{SPECS[name][0]} (시즌 대비)"
            if not ok:
                # 값을 None 으로 두고 **사유를 함께 남긴다.** 지워 버리면
                # 왜 없는지 알 수 없고, 숫자를 남기면 추세로 읽힌다.
                axis.metrics[key] = Metric(
                    name=name, label=label, value=None, provenance=DERIVED,
                    period=f"trend{window}", sample_count=sample,
                    unit=SPECS[name][1], direction=SPECS[name][2],
                    group=GROUPS.get(name, ""), source=DERIVED_SOURCE,
                    measurement_basis=MIXED_BASIS,
                    note=f"{NOT_MEANINGFUL} {reason}")
                target = structural if code in STRUCTURAL_BLOCKS else blocked
                target.setdefault(reason, set()).add(name)
                continue
            delta = value - base[0]
            band, limit = trend_band(name, delta, thresholds)
            axis.metrics[key] = Metric(
                name=name, label=label, value=delta,
                provenance=DERIVED, period=f"trend{window}",
                sample_count=sample, unit=SPECS[name][1],
                direction=SPECS[name][2], group=GROUPS.get(name, ""),
                source=DERIVED_SOURCE,
                measurement_basis=season_metric.measurement_basis,
                note=f"{band} 시즌 {base[0]:.2f} → 최근 {window}경기 "
                     f"{value:.2f} (차이 {delta:+.2f}, 표시 기준 {limit:g})")
        for reason, names in sorted(blocked.items()):
            axis.notes.append(
                f"{period_label(period)} trend 미생성: {reason} — "
                + ", ".join(SPECS[n][0] for n in sorted(names)))
        blocked.clear()

    # 창 길이와 무관한 사유는 창마다 반복하지 않고 한 번만 적는다.
    for reason, names in sorted(structural.items()):
        axis.notes.append("trend 미생성(모든 기간): " + reason + " — "
                          + ", ".join(SPECS[n][0] for n in sorted(names)))

    if not aggregates:
        axis.notes.append(
            "슛 계층 창이 없습니다 — npxG·xGOT·박스 안 슈팅은 경기 상세에서만 "
            "나옵니다 (--skip-match-details 로 돌렸거나 수집 실패)")
    if as_of is None:
        axis.notes.append(
            "기준시각을 알 수 없어 과거 경기 구간이 비었습니다 "
            "(득점·승점·승무패는 최근 창에서 빠집니다)")
    axis.notes.append(
        "시즌 값과 최근 값은 표본이 다릅니다. 하나의 평균으로 합치지 마십시오")
    return axis


# ==========================================================================
# Phase 2-B — 기회의 질 / 공격 실행 (chance_quality)
# ==========================================================================
# 흐름 하나를 구조로 만든다:
#
#     슈팅  →  xG · npxG  →  xGOT  →  득점
#     (양)     (기회의 질)    (실행)    (결과)
#
# 왜 2-A 와 따로 두나: 2-A 는 **같은 지표를 기간별로** 늘어놓는 축이고,
# 여기는 **지표들 사이의 관계**(비율·차이)를 만드는 축이다. 원재료가 겹치는
# 것은 의도된 것이고, `Metric.group` 이 2-I 에서 같은 사실을 두 번 세지
# 않게 막는다.
#
# ## 비율은 '평균의 평균' 이 아니다
#
# 경기별 xG/슛 을 구해 다시 평균 내지 않는다 — 슛이 적은 경기가 과대
# 대표된다. **기간 합계끼리 나눈다**: `Σ xG / Σ 슛`.
#
# ## 분자와 분모의 표본이 같아야 한다
#
# 창의 합계(`RecentShotAggregate.sums`)만으로는 이걸 보장할 수 없다.
# 6경기 창에서 슛은 6경기 전부에 있고 xG 는 4경기에만 있으면, `Σxg/Σshots`
# 는 4경기치 xG 를 6경기치 슛으로 나눈 값이 된다 — 조용히 낮아진다.
# 그래서 **경기별 원재료**(`TeamProfile.shot_matches`)에서 둘 다 있는 경기만
# 골라 합산한다. 원재료가 없으면(옛 캐시·데모) 창의 표본 수가 완전히 일치할
# 때만 계산하고, 아니면 만들지 않는다.
#
# ## 만들지 않는 것
#
# **`xGOT − npxG` 를 만들지 않는다.** xGOT 은 PK 를 포함하고 npxG 는
# 제외하므로 기준이 다르다. 이 차이를 "결정력"·"슈팅 효율" 로 부르면 PK 를
# 많이 얻은 팀이 자동으로 좋아 보인다. xG·npxG·xGOT 세 원값을 따로 둔다.
# (리포트의 `recent_metrics` 에 Phase 1-B 때 넣은 `xgot_delta_recent` 행이
#  아직 남아 있다 — 이번 단계는 UI 를 건드리지 않으므로 그대로 두고
#  Known Limitations 에 적는다.)
#
# 득점−xG 계열을 "결정력"·"finishing" 으로 부르지 않고 방향도 정하지 않는다.

# 비율 지표: (지표 이름, 분자 필드, 분모 필드, 배수)
_RATES: tuple[tuple[str, str, str, float], ...] = (
    ("xg_per_shot", "xg", "shots", 1.0),
    ("npxg_per_shot", "npxg", "shots", 1.0),
    ("box_shot_share", "shots_inside_box", "shots", 100.0),
    ("on_target_rate", "shots_on_target", "shots", 100.0),
)
# 차이 지표: (지표 이름, 빼는 값의 필드)
_GAPS: tuple[tuple[str, str], ...] = (
    ("goals_minus_xg", "xg"),
    ("goals_minus_npxg", "npxg"),
    ("goals_minus_xgot", "xgot"),
)
# 경기별 원재료에서 그대로 평균 내는 관측값.
_OBSERVED_FIELDS = ("shots", "shots_on_target", "shots_inside_box",
                    "shots_outside_box", "xg", "npxg", "xgot")

DEFAULT_CHANCE_QUALITY: dict = {
    "min_sample": 3,
    "thresholds": {
        "shots_high": 14.0, "shots_low": 10.0,
        "xg_per_shot_high": 0.12, "xg_per_shot_low": 0.09,
        "xg_high": 1.60, "xgot_high": 1.40,
        "goals_gap_low": -0.30,
    },
}

PATTERN_LABELS = {
    "A": "슈팅량에 비해 평균 기회 질이 낮음",
    "B": "슈팅량은 적지만 평균 기회 질이 높음",
    "C": "기회 창출 대비 실제 득점이 낮음",
    "D": "기회 창출과 유효슈팅 실행 수준이 모두 높음",
}


def chance_quality_config(settings: Settings) -> dict:
    cfg = (getattr(settings, "analysis", None) or {}).get("chance_quality")
    out = {"min_sample": DEFAULT_CHANCE_QUALITY["min_sample"],
           "thresholds": dict(DEFAULT_CHANCE_QUALITY["thresholds"])}
    if isinstance(cfg, dict):
        try:
            out["min_sample"] = max(1, int(cfg.get("min_sample",
                                                   out["min_sample"])))
        except (TypeError, ValueError):
            pass
        for k, v in (cfg.get("thresholds") or {}).items():
            try:
                out["thresholds"][str(k)] = float(v)
            except (TypeError, ValueError):
                continue
    return out


def _field(row, name: str):
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name, None)


def _match_rows(profile: TeamProfile | None, agg) -> list:
    """창에 들어간 경기의 **경기별** 슛 집계.

    `RecentShotAggregate.match_ids` 로 고른다 — 창이 이미 정한 경기 집합을
    그대로 쓰므로 여기서 다시 자르지 않는다(시점 판단은 2-A 의
    `_window_time_check` 가 이미 했다).
    """
    rows = getattr(profile, "shot_matches", None) or []
    wanted = [str(x) for x in (_agg_field(agg, "match_ids") or [])]
    if not rows or not wanted:
        return []
    index = {str(_field(r, "match_id")): r for r in rows}
    return [index[m] for m in wanted if m in index]


def _mean(rows: list, field_name: str) -> tuple[float | None, int]:
    """(경기당 평균, 표본 수). 값이 없는 경기는 **세지 않는다**."""
    vals = [_num(_field(r, field_name)) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None, 0
    return sum(vals) / len(vals), len(vals)


def _ratio(rows: list, num: str, den: str, scale: float = 1.0
           ) -> tuple[float | None, int, str]:
    """(비율, 표본 수, 비고). **분자·분모가 둘 다 있는 경기만** 쓴다.

    합계끼리 나눈다 — 경기별 비율을 다시 평균 내지 않는다.
    분모 합이 0 이면 None 이다 (0 으로 나눌 수 없다. 0 이 답인 게 아니다).
    """
    pairs = []
    for r in rows:
        a, b = _num(_field(r, num)), _num(_field(r, den))
        if a is None or b is None:
            continue
        pairs.append((a, b))
    if not pairs:
        return None, 0, ""
    bottom = sum(b for _a, b in pairs)
    if bottom <= 0:
        return None, len(pairs), f"분모({SPECS.get(den, (den,))[0]}) 합계 0"
    return sum(a for a, _b in pairs) / bottom * scale, len(pairs), ""


def _gap(rows: list, goals_by_match: dict, field_name: str
         ) -> tuple[float | None, int, str]:
    """(경기당 득점 − 지표, 표본 수, 비고).

    득점은 슛맵이 아니라 **시즌 경기 색인의 최종 스코어**에서 온다 — 슛맵은
    상대 자책골을 우리 득점으로 세지 않는다. 스코어를 모르는 경기는 표본에서
    빠진다(0 으로 치지 않는다).
    """
    pairs = []
    unknown = 0
    for r in rows:
        value = _num(_field(r, field_name))
        if value is None:
            continue
        mid = str(_field(r, "match_id"))
        if mid not in goals_by_match:
            unknown += 1
            continue
        pairs.append((goals_by_match[mid], value))
    if not pairs:
        note = f"스코어를 모르는 경기 {unknown}건" if unknown else ""
        return None, 0, note
    n = len(pairs)
    note = f"스코어 미상 {unknown}경기 제외" if unknown else ""
    return (sum(g for g, _v in pairs) - sum(v for _g, v in pairs)) / n, n, note


def _rates_from_window(agg, available: int) -> dict:
    """경기별 원재료가 없을 때의 대비책.

    창의 합계만 있을 때는 분자·분모가 **같은 경기 집합**인지 증명할 수 없다.
    두 표본 수가 창의 확보 경기 수와 모두 같을 때만(=모든 경기에 둘 다 있음)
    계산하고, 아니면 만들지 않는다.
    """
    out: dict[str, tuple[float, int, str]] = {}
    sums = _agg_field(agg, "sums") or {}
    counts = _agg_field(agg, "counts") or {}
    for name, num, den, scale in _RATES:
        n_num, n_den = counts.get(num, 0), counts.get(den, 0)
        if not available or n_num != available or n_den != available:
            continue
        bottom = sums.get(den)
        if not bottom:
            continue
        top = sums.get(num)
        if top is None:
            continue
        out[name] = (top / bottom * scale, available,
                     "창 합계 기준 (경기별 원재료 없음)")
    return out


def _season_chance_values(stats) -> tuple[dict, list[str]]:
    """시즌 기회의 질. **표본이 어긋나면 만들지 않는다.**

    순위표(`played`)와 xG 표(`xg_played`)는 집계 시점이 달라 경기 수가 다를
    수 있다. 다르면 비율·차이를 계산하지 않고 그 사실을 적는다.
    """
    out: dict[str, tuple[float, int | None, str]] = {}
    notes: list[str] = []
    if stats is None:
        return out, notes
    played, xg_played = stats.played, stats.xg_played

    _put(out, "shots", stats.shots_pg, played)
    _put(out, "shots_on_target", stats.shots_on_target_pg, played)
    _put(out, "big_chances", stats.big_chances_pg, played)
    _put(out, "goals", stats.goals_for_pg, played)
    _put(out, "xg", stats.xg_pg, xg_played or played)

    shots_pg, xg_pg = stats.shots_pg, stats.xg_pg
    sot_pg, goals_pg = stats.shots_on_target_pg, stats.goals_for_pg
    if shots_pg and sot_pg is not None:
        _put(out, "on_target_rate", sot_pg / shots_pg * 100.0, played)

    same_sample = (played is not None and xg_played is not None
                   and played == xg_played)
    if xg_pg is not None and not same_sample and played is not None:
        notes.append(
            f"시즌 xG 표본({xg_played})과 순위표 경기 수({played})가 달라 "
            "슛당 xG·득점−xG 를 만들지 않았습니다")
    elif same_sample:
        if shots_pg and xg_pg is not None:
            _put(out, "xg_per_shot", xg_pg / shots_pg, played)
        if goals_pg is not None and xg_pg is not None:
            _put(out, "goals_minus_xg", goals_pg - xg_pg, played)
    return out, notes


def detect_patterns(values: dict, config: dict) -> list[tuple[str, str, str]]:
    """[(코드, 라벨, 근거)]. **추천이 아니다** — 상태 설명이다.

    표본이 `min_sample` 에 못 미치면 아무 패턴도 만들지 않는다. 문턱은
    설정에서 오고 **운영용이며 통계적으로 검증된 기준이 아니다.**
    """
    th = config.get("thresholds") or {}
    floor = int(config.get("min_sample") or 1)

    def get(name):
        row = values.get(name)
        if row is None or row[1] is None or int(row[1]) < floor:
            return None
        return row[0]

    shots, xgps = get("shots"), get("xg_per_shot")
    xg, xgot, gap = get("xg"), get("xgot"), get("goals_minus_xg")
    out: list[tuple[str, str, str]] = []

    if shots is not None and xgps is not None:
        if (shots >= th.get("shots_high", 1e9)
                and xgps <= th.get("xg_per_shot_low", -1)):
            out.append(("A", PATTERN_LABELS["A"],
                        f"슈팅 {shots:.1f} · 슛당 xG {xgps:.3f}"))
        elif (shots <= th.get("shots_low", -1)
                and xgps >= th.get("xg_per_shot_high", 1e9)):
            out.append(("B", PATTERN_LABELS["B"],
                        f"슈팅 {shots:.1f} · 슛당 xG {xgps:.3f}"))
    high_xg = xg is not None and xg >= th.get("xg_high", 1e9)
    if high_xg and gap is not None and gap <= th.get("goals_gap_low", -1e9):
        out.append(("C", PATTERN_LABELS["C"],
                    f"xG {xg:.2f} · 득점−xG {gap:+.2f}"))
    if high_xg and xgot is not None and xgot >= th.get("xgot_high", 1e9):
        out.append(("D", PATTERN_LABELS["D"],
                    f"xG {xg:.2f} · xGOT {xgot:.2f}"))
    return out


def build_chance_quality(profile: TeamProfile | None, team: str,
                         season_matches: list[SeasonMatch] | None,
                         as_of: datetime | None,
                         windows: list[int],
                         config: dict,
                         quality: DataQuality | None = None) -> AnalysisAxis:
    """슈팅 → xG/npxG → xGOT → 득점 을 기간별로 담는다 (Phase 2-B).

    키는 2-A 와 같은 `기간.지표` 다. 기간 구조를 새로 만들지 않는다.
    """
    axis = AnalysisAxis(name="chance_quality")
    stats = getattr(profile, "stats", None) if profile else None
    aggregates = getattr(profile, "shot_aggregates", None) or {}
    season = list(season_matches or [])

    history = team_history(season, team, as_of)
    known_ids = {str(m.match_id) for m in season if m.match_id}
    allowed_ids = {str(m.match_id) for m in matches_before(season, as_of)
                   if m.match_id}
    # {경기 id: 그 경기에서 이 팀이 넣은 골} — 최종 스코어 기준.
    goals_by_match: dict[str, int] = {}
    for m in history:
        mine = m.home_goals if m.home_team == team else m.away_goals
        if mine is not None:
            goals_by_match[str(m.match_id)] = int(mine)

    windows = sorted({int(w) for w in windows if int(w) > 0}, reverse=True)
    axis.requested_matches = windows[0] if windows else None
    axis.available_matches = len(history)

    # ---- 시즌 --------------------------------------------------------------
    season_values, season_notes = _season_chance_values(stats)
    for name, (value, sample, note) in season_values.items():
        axis.metrics[metric_key(SEASON, name)] = _metric(
            name, SEASON, value, sample,
            provenance=(DERIVED if name in DERIVED_SPECS else OBSERVED),
            note=note)
    axis.notes.extend(season_notes)
    played = getattr(stats, "played", None) if stats else None
    axis.notes.append(
        "시즌: npxG·xGOT·박스 안 슈팅이 없어 슛당 npxG·박스 안 비율·"
        "득점−npxG·득점−xGOT 는 시즌 값이 없습니다")
    if quality is not None:
        quality.mark("chance_quality.season", bool(season_values),
                     requested=played, available_matches=played,
                     reason="" if season_values else "시즌 지표 없음")
    for code, label, basis in detect_patterns(season_values, config):
        axis.notes.append(f"패턴 {code} · 시즌 · {label} ({basis})")

    # ---- 최근 N경기 ---------------------------------------------------------
    for window in windows:
        period = period_name(window)
        agg = aggregates.get(f"all{window}")
        if agg is None:
            if quality is not None:
                quality.mark(f"chance_quality.{period}", False,
                             requested=window, available_matches=0,
                             reason="슛 계층 창 없음")
            continue

        future, unknown = _window_time_check(agg, allowed_ids, known_ids)
        if future:
            axis.notes.append(
                f"{period_label(period)}: 기준시각 이후 경기 {len(future)}건이 "
                "창에 들어 있어 이 기간을 만들지 않았습니다")
            if quality is not None:
                quality.mark(f"chance_quality.{period}", False,
                             requested=window, available_matches=0,
                             reason="기준시각 이후 경기 혼입")
            continue

        available = int(_agg_field(agg, "available_matches") or 0)
        rows = _match_rows(profile, agg)
        values: dict[str, tuple[float, int | None, str]] = {}

        if rows:
            for field_name in _OBSERVED_FIELDS:
                value, n = _mean(rows, field_name)
                _put(values, field_name, value, n)
            for name, num, den, scale in _RATES:
                value, n, note = _ratio(rows, num, den, scale)
                _put(values, name, value, n, note)
            for name, field_name in _GAPS:
                value, n, note = _gap(rows, goals_by_match, field_name)
                _put(values, name, value, n, note)
            # 득점은 **슛맵이 아니라 최종 스코어**에서 온다. 슛맵의 `goals`
            # 는 상대 자책골을 우리 득점으로 세지 않아 결과 지표가 될 수 없다.
            team_goals = [goals_by_match[str(_field(r, "match_id"))]
                          for r in rows
                          if str(_field(r, "match_id")) in goals_by_match]
            if team_goals:
                _put(values, "goals", sum(team_goals) / len(team_goals),
                     len(team_goals))
            inside = sum(int(_field(r, "shots_inside_box") or 0) for r in rows)
            outside = sum(int(_field(r, "shots_outside_box") or 0)
                          for r in rows)
            total = sum(int(_field(r, "shots") or 0) for r in rows)
            if total and inside + outside != total:
                axis.notes.append(
                    f"{period_label(period)}: 위치를 알 수 없는 슛 "
                    f"{total - inside - outside}개가 있어 박스 안 비율의 "
                    "분모(총슈팅)에 포함돼 있습니다")
        else:
            for name, source in _FROM_SHOTS.items():
                value, n = _agg_avg(agg, source)
                _put(values, name, value, n)
            for name, (value, n, note) in _rates_from_window(
                    agg, available).items():
                _put(values, name, value, n, note)
            axis.notes.append(
                f"{period_label(period)}: 경기별 슛 원재료가 없어 비율 지표를 "
                "표본이 완전히 일치할 때만 만들었고 득점 차이는 만들지 "
                "않았습니다")

        for name, (value, sample, note) in values.items():
            axis.metrics[metric_key(period, name)] = _metric(
                name, period, value, sample,
                provenance=(DERIVED if name in DERIVED_SPECS else OBSERVED),
                note=note)

        if unknown:
            axis.notes.append(
                f"{period_label(period)}: 시즌 색인에 없어 시점을 확인하지 "
                f"못한 경기 {len(unknown)}건이 들어 있습니다")
        if quality is not None:
            quality.mark(f"chance_quality.{period}", bool(values),
                         requested=window, available_matches=available,
                         reason="" if values else "표본 없음")
        for code, label, basis in detect_patterns(values, config):
            axis.notes.append(
                f"패턴 {code} · {period_label(period)} · {label} ({basis})")

    axis.notes.append(
        "비율은 기간 합계끼리 나눈 값입니다 (경기별 비율의 평균이 아닙니다). "
        "분자와 분모가 모두 있는 경기만 씁니다")
    axis.notes.append(
        "득점−xG · 득점−npxG · 득점−xGOT 는 실제 득점과 기대값의 차이일 뿐이며 "
        "결정력을 뜻하지 않습니다. 하나의 점수로 합치지 마십시오")
    return axis


def patterns_in(axis: AnalysisAxis | None) -> list[str]:
    """축 notes 에 적힌 패턴 줄만 뽑는다."""
    if axis is None:
        return []
    return [n for n in axis.notes if n.startswith("패턴 ")]


# --------------------------------------------------------------------------
# 7. TeamAnalysis / Match 연결
# --------------------------------------------------------------------------
def build_team_analysis(profile: TeamProfile | None, team: str,
                        season_matches: list[SeasonMatch] | None,
                        as_of: datetime | None, settings: Settings,
                        is_home: bool | None = None) -> TeamAnalysis:
    quality = DataQuality()
    out = TeamAnalysis(team=team, is_home=is_home, data_quality=quality)
    ref = getattr(profile, "team", None) if profile else None
    raw_id = getattr(ref, "fotmob_id", "") if ref else ""
    try:
        out.fotmob_id = int(raw_id) if raw_id else None
    except (TypeError, ValueError):
        out.fotmob_id = None

    windows = periods_from(settings)
    out.time_context = build_time_context(
        profile, team, season_matches, as_of,
        windows=windows, thresholds=thresholds_from(settings),
        detail_window=detail_window_of(settings), quality=quality,
        min_sample=trend_min_sample(settings))
    out.chance_quality = build_chance_quality(
        profile, team, season_matches, as_of, windows=windows,
        config=chance_quality_config(settings), quality=quality)
    return out


def attach_time_context(matches: list[Match], settings: Settings,
                        season_matches: list[SeasonMatch] | None = None
                        ) -> None:
    """14경기 각각에 Phase 2-A 결과를 붙인다.

    `Match.probs`(피나클 배당 확률)는 건드리지 않는다. 리포트 렌더링도
    아직 이 값을 읽지 않으므로 화면은 그대로다 (시각화는 Phase 3).
    """
    season = list(season_matches or [])
    built = 0
    for match in matches:
        as_of = as_of_from_match(match)
        analysis = match.analysis or MatchAnalysis()
        analysis.as_of = as_of
        for side in ("home", "away"):
            ref = getattr(match, side)
            profile = getattr(match, f"{side}_profile")
            team = getattr(ref, "canonical", "") or getattr(ref, "display", "")
            if not team:
                continue
            setattr(analysis, side, build_team_analysis(
                profile, team, season, as_of, settings,
                is_home=(side == "home")))
        if analysis.home or analysis.away:
            match.analysis = analysis
            built += 1

    if built:
        windows = "/".join(str(w) for w in periods_from(settings))
        patterns = sum(len(patterns_in(getattr(m.analysis, side).chance_quality
                                       if getattr(m.analysis, side) else None))
                       for m in matches if m.analysis
                       for side in ("home", "away"))
        log.info("팀 분석(2-A 시간축 · 2-B 기회의 질): %d경기 · 창 %s · "
                 "시즌 색인 %d경기 · 패턴 %d건",
                 built, windows, len(season), patterns)
