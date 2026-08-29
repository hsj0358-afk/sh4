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

# §9 가 직접 방향을 지정한 지표.
SPEC_DIRECTIONS = frozenset((
    "goals", "xg", "npxg", "xgot", "shots_on_target", "shots_inside_box",
    "big_chances", "points", "xgd",
    "goals_against", "npxga", "xgot_against", "shots_against",
    "shots_on_target_against"))
# 명세에 없지만 방향이 자명해 붙인 것. 어디까지가 명세인지 구분해 둔다.
EXTRA_DIRECTIONS = frozenset(("goal_diff", "npxgd", "wins", "losses"))
# 방향을 정하지 않은 지표 (많고 적음이 곧 좋고 나쁨이 아니다).
UNDIRECTED = frozenset(("shots", "draws"))

ATTACK = tuple(k for k, v in SPECS.items() if v[3] == "attack")
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
    """트렌드 지표의 밴드를 되읽는다 (note 앞에 토큰으로 적어 둔다)."""
    if metric is None or not metric.note:
        return ""
    head = metric.note.split(" ", 1)[0]
    return head if head in TREND_BANDS else ""


# --------------------------------------------------------------------------
# 6. 축 만들기
# --------------------------------------------------------------------------
def _metric(name: str, period: str, value: float, sample: int | None,
            provenance: str = OBSERVED, note: str = "") -> Metric:
    label, unit, direction, _group = SPECS[name]
    return Metric(name=name, label=label, value=value, provenance=provenance,
                  period=period, sample_count=sample, unit=unit, note=note,
                  direction=direction)


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
                       quality: DataQuality | None = None) -> AnalysisAxis:
    """시즌 · 최근 N경기 · 그 차이를 한 축에 담는다.

    키는 `기간.지표` 다 (`season.xg`, `recent6.xg`, `trend6.xg`). 기간을
    키에 넣어 두면 시즌 값과 최근 값이 **구조적으로 섞일 수 없다.**
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
        for name, (value, sample, _note) in values.items():
            base = season_values.get(name)
            if base is None:
                continue
            delta = value - base[0]
            band, limit = trend_band(name, delta, thresholds)
            key = metric_key(f"trend{window}", name)
            axis.metrics[key] = Metric(
                name=name, label=f"{SPECS[name][0]} (시즌 대비)", value=delta,
                provenance=DERIVED, period=f"trend{window}",
                sample_count=sample, unit=SPECS[name][1],
                direction=SPECS[name][2],
                note=f"{band} 시즌 {base[0]:.2f} → 최근 {window}경기 "
                     f"{value:.2f} (차이 {delta:+.2f}, 표시 기준 {limit:g})")

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

    out.time_context = build_time_context(
        profile, team, season_matches, as_of,
        windows=periods_from(settings), thresholds=thresholds_from(settings),
        detail_window=detail_window_of(settings), quality=quality)
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
        log.info("시간축 분석(2-A): %d경기 · 창 %s · 시즌 색인 %d경기",
                 built, windows, len(season))
