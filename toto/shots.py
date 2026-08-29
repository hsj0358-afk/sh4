"""슛 이벤트 데이터 계층 (Phase 1-C).

FotMob `matchDetails` 의 `content.shotmap.shots[]` 를 재사용 가능한 계층으로
만든다. Phase 2 의 경기력 분석과 Phase 3 의 슈팅맵이 이 위에 올라간다.

    Raw JSON
      ↓  parse_shot_events()      슛 1개 = ShotEvent 1개 (원본 id 보존)
    ShotEvent
      ↓  aggregate_match()        경기 × 팀 단위 합계
    MatchShotAggregate
      ↓  aggregate_recent()       최근 N경기 (전체 / 홈 / 원정)
    RecentShotAggregate

## 왜 별도 모듈인가

`toto/sources/fotmob.py` 의 `_shot_totals()` 는 경기 스탯과 대조하려고 만든
5개 값짜리 합산이다. 그건 그대로 두고(대조 로그가 그 값을 쓴다), 여기서는
슛 1개를 잃지 않는 완전한 계층을 만든다. 집계 로직 자체는 소스와 무관하므로
분리해 두면 Phase 2·3 에서 그대로 쓸 수 있다.

## 지키는 규칙 (CLAUDE.md)

- **None 과 0 을 구분한다.** 한 슛도 xG 를 갖지 않은 경기의 xG 는 `0.0` 이
  아니라 `None` 이다. 0 으로 두면 '기록이 없다' 와 '정말 0 이다' 가 같아진다.
- **지표마다 표본이 다르다.** `RecentShotAggregate` 는 합계와 **지표별 경기
  수**를 따로 들고 다니고, 평균은 그 지표의 경기 수로 나눈다.
- **추측하지 않는다.** 실물에서 확인된 필드만 읽는다. 없으면 None 이다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

log = logging.getLogger(__name__)

# 집계 대상 지표. sums/counts 의 키이자 RecentShotAggregate 의 지표 이름이다.
METRICS = ("shots", "shots_on_target", "shots_off_target", "shots_blocked",
           "shots_inside_box", "shots_outside_box",
           "xg", "npxg", "xgot", "goals", "own_goals")

# 실물에서 관찰된 situation 값. 목록에 없는 값이 와도 버리지 않고 그대로
# 집계한다 — 새 분류가 생겼을 때 조용히 사라지면 안 된다. 실제로 260048
# 실물에서 ThrowInSetPiece · IndividualPlay 두 개가 새로 나왔고, 그대로
# 집계됐다(목록은 참고용이지 필터가 아니다).
KNOWN_SITUATIONS = ("RegularPlay", "SetPiece", "FastBreak", "FromCorner",
                    "FreeKick", "Penalty", "ThrowInSetPiece", "IndividualPlay")


def _f(value: Any) -> float | None:
    """숫자만 통과. bool 은 숫자가 아니다 (True 가 1.0 이 되면 안 된다)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _i(value: Any) -> int | None:
    f = _f(value)
    return int(f) if f is not None else None


def _b(value: Any) -> bool | None:
    """세 상태를 유지한다 — True / False / 모름(None)."""
    return value if isinstance(value, bool) else None


# --------------------------------------------------------------------------
# 1. ShotEvent — 슛 1개
# --------------------------------------------------------------------------
@dataclass
class ShotEvent:
    """슛 1개. 필드는 전부 FotMob 실물에서 확인된 것만 담는다.

    | 필드 | 원본 필드 | 타입 | 없을 수 있나 |
    |---|---|---|---|
    | `match_id` | (호출부가 넘김) | str | 아니오 |
    | `event_id` | `id` | str | 예 ("") |
    | `team_id` | `teamId` | int | 아니오 (없으면 슛을 버린다) |
    | `player_id` | `playerId` | int·None | 예 |
    | `player_name` | `playerName` | str | 예 ("") |
    | `x` / `y` | `x` / `y` | float·None | 예 |
    | `minute` | `min` | int·None | 예 |
    | `minute_added` | `minAdded` | int·None | 예 |
    | `period` | `period` | str | 예 ("") |
    | `expected_goals` | `expectedGoals` | float·None | 예 |
    | `expected_goals_on_target` | `expectedGoalsOnTarget` | float·None | 예 |
    | `is_on_target` | `isOnTarget` | bool·None | 예 |
    | `is_blocked` | `isBlocked` | bool·None | 예 |
    | `is_own_goal` | `isOwnGoal` | bool·None | 예 |
    | `is_inside_box` | `isFromInsideBox` | bool·None | 예 |
    | `shot_type` | `shotType` | str | 예 ("") |
    | `situation` | `situation` | str | 예 ("") |
    | `event_type` | `eventType` | str | 예 ("") |

    bool 세 개는 `False` 와 `None` 을 구분한다. `is_inside_box=None` 은
    '박스 밖' 이 아니라 '어디였는지 모른다' 이므로 안팎 어느 쪽으로도 세지
    않는다.
    """
    match_id: str
    team_id: int
    event_id: str = ""
    player_id: int | None = None
    player_name: str = ""
    x: float | None = None
    y: float | None = None
    minute: int | None = None
    minute_added: int | None = None
    period: str = ""
    expected_goals: float | None = None
    expected_goals_on_target: float | None = None
    is_on_target: bool | None = None
    is_blocked: bool | None = None
    is_own_goal: bool | None = None
    is_inside_box: bool | None = None
    shot_type: str = ""
    situation: str = ""
    event_type: str = ""

    @property
    def is_penalty(self) -> bool:
        return self.situation.strip().lower() == "penalty"

    @property
    def is_goal(self) -> bool:
        """자책골은 제외한다.

        FotMob 이 자책골을 넣은 팀과 실점한 팀 중 어느 쪽 `teamId` 로 다는지
        실물로 확인하지 못했다. 그래서 득점에 섞지 않고 `own_goals` 로 따로
        센다 — 섞으면 어느 쪽이든 한쪽이 조용히 틀린다.
        """
        return (self.event_type.strip().lower() == "goal"
                and not self.is_own_goal)

    @property
    def key(self) -> tuple:
        """중복 판정용. event id 가 유일하다고 가정하지 않는다.

        id 가 있으면 (경기, id) 로 보고, 없으면 슛을 특정하는 값들을 묶는다.
        """
        if self.event_id:
            return (self.match_id, self.event_id)
        return (self.match_id, self.team_id, self.player_id, self.minute,
                self.minute_added, self.x, self.y, self.expected_goals)


def parse_shot_events(shots: Iterable[Any], match_id: str) -> list[ShotEvent]:
    """슛맵 배열 → ShotEvent 목록. teamId 가 없는 항목은 버린다.

    팀을 특정할 수 없는 슛은 어느 팀에도 넣을 수 없다. 조용히 한쪽에 몰아
    넣는 것보다 세지 않는 편이 낫다(버린 개수는 호출부가 로그로 남긴다).
    """
    out: list[ShotEvent] = []
    for raw in shots or []:
        if not isinstance(raw, dict):
            continue
        team_id = _i(raw.get("teamId"))
        if team_id is None:
            continue
        eid = raw.get("id")
        out.append(ShotEvent(
            match_id=str(match_id),
            team_id=team_id,
            event_id="" if eid is None else str(eid),
            player_id=_i(raw.get("playerId")),
            player_name=str(raw.get("playerName") or ""),
            x=_f(raw.get("x")), y=_f(raw.get("y")),
            minute=_i(raw.get("min")), minute_added=_i(raw.get("minAdded")),
            period=str(raw.get("period") or ""),
            expected_goals=_f(raw.get("expectedGoals")),
            expected_goals_on_target=_f(raw.get("expectedGoalsOnTarget")),
            is_on_target=_b(raw.get("isOnTarget")),
            is_blocked=_b(raw.get("isBlocked")),
            is_own_goal=_b(raw.get("isOwnGoal")),
            is_inside_box=_b(raw.get("isFromInsideBox")),
            shot_type=str(raw.get("shotType") or ""),
            situation=str(raw.get("situation") or ""),
            event_type=str(raw.get("eventType") or ""),
        ))
    return out


def dedupe(events: Iterable[ShotEvent]) -> tuple[list[ShotEvent], int]:
    """(중복 제거된 목록, 버린 개수). 순서는 유지한다."""
    seen: set[tuple] = set()
    out: list[ShotEvent] = []
    dropped = 0
    for e in events:
        if e.key in seen:
            dropped += 1
            continue
        seen.add(e.key)
        out.append(e)
    return out, dropped


# --------------------------------------------------------------------------
# 2. MatchShotAggregate — 경기 × 팀
# --------------------------------------------------------------------------
@dataclass
class MatchShotAggregate:
    """한 경기에서 한 팀의 슛 집계.

    개수(shots·on_target…)는 int 로 **0 이 실제 0**이다 — 슛맵을 받았는데
    슛이 없었다면 0 이 맞다. 반면 xg·npxg·xgot 은 `float | None` 이고,
    그 경기 어느 슛에도 값이 없으면 None 이다.
    """
    match_id: str
    team_id: int
    is_home: bool | None = None          # teamId 로 판정. 모르면 None
    shots: int = 0
    shots_on_target: int = 0
    shots_off_target: int = 0
    shots_blocked: int = 0
    shots_inside_box: int = 0
    shots_outside_box: int = 0
    xg: float | None = None
    npxg: float | None = None
    xgot: float | None = None
    goals: int = 0
    own_goals: int = 0
    penalties: int = 0
    # {situation: {"count": int, "xg": float|None}}
    situations: dict[str, dict] = field(default_factory=dict)

    def value(self, metric: str) -> float | None:
        return getattr(self, metric, None)


def aggregate_match(events: Iterable[ShotEvent],
                    home_id: int | None = None,
                    away_id: int | None = None) -> dict[int, MatchShotAggregate]:
    """{team_id: MatchShotAggregate}. 홈/원정은 **teamId 로만** 정한다.

    경기 스탯의 `[0], [1]` 배열 순서는 여기서 쓰지 않는다 (CLAUDE.md — 배열
    순서를 믿는 구조를 새로 만들지 않는다). home_id/away_id 를 못 받으면
    `is_home` 은 None 으로 남고, 홈/원정 분리 집계에서 그 경기가 빠진다.
    """
    out: dict[int, MatchShotAggregate] = {}
    # 지표별로 '값이 있는 슛이 하나라도 있었나'. 없으면 합계가 아니라 None.
    seen: dict[int, set[str]] = {}
    for e in events:
        agg = out.get(e.team_id)
        if agg is None:
            is_home = None
            if home_id is not None and e.team_id == home_id:
                is_home = True
            elif away_id is not None and e.team_id == away_id:
                is_home = False
            agg = out[e.team_id] = MatchShotAggregate(
                match_id=e.match_id, team_id=e.team_id, is_home=is_home)
            seen[e.team_id] = set()

        agg.shots += 1
        # **막힌 슛은 유효슈팅이 아니다.** FotMob 의 `isOnTarget` 은 블록된
        # 슛에도 true 로 온다 — 골문으로 가던 슛이었다는 뜻이라 그 자체로
        # 틀린 값은 아니지만, 통상적인 '유효슈팅'(과 FotMob 자신의 경기 스탯
        # `ShotsOnTarget`)은 블록을 제외한다.
        # 260048 실물 6개 팀-경기 전부에서, 블록을 빼야 경기 스탯과 정확히
        # 일치했다 (빼기 전 차이 최대 +8, 뺀 뒤 0).
        blocked = e.is_blocked is True
        if blocked:
            agg.shots_blocked += 1
        elif e.is_on_target is True:
            agg.shots_on_target += 1
        elif e.is_on_target is False:
            agg.shots_off_target += 1
        if e.is_inside_box is True:
            agg.shots_inside_box += 1
        elif e.is_inside_box is False:
            agg.shots_outside_box += 1
        if e.is_goal:
            agg.goals += 1
        if e.is_own_goal is True:
            agg.own_goals += 1
        if e.is_penalty:
            agg.penalties += 1

        xg = e.expected_goals
        if xg is not None:
            agg.xg = (agg.xg or 0.0) + xg
            seen[e.team_id].add("xg")
            # npxG = PK 를 뺀 xG. 상수 차감이 아니라 실제 분류를 쓴다.
            if not e.is_penalty:
                agg.npxg = (agg.npxg or 0.0) + xg
            elif agg.npxg is None:
                agg.npxg = 0.0      # PK 만 있던 팀도 npxG 는 0 이 맞다
            seen[e.team_id].add("npxg")
        xgot = e.expected_goals_on_target
        if xgot is not None:
            agg.xgot = (agg.xgot or 0.0) + xgot
            seen[e.team_id].add("xgot")

        # 상황별 — 이름을 고치지 않고 원본 그대로 센다
        name = e.situation or "Unknown"
        slot = agg.situations.setdefault(name, {"count": 0, "xg": None})
        slot["count"] += 1
        if xg is not None:
            slot["xg"] = (slot["xg"] or 0.0) + xg
    return out


# --------------------------------------------------------------------------
# 3. RecentShotAggregate — 최근 N경기
# --------------------------------------------------------------------------
@dataclass
class RecentShotAggregate:
    """최근 N경기 합계 + 지표별 표본 수.

    합계(`sums`)·표본 수(`counts`)·평균(`avg()`)을 분리해 둔다. Phase 1-B 에서
    실제로 겪은 사고가 여기서 반복되면 안 되기 때문이다 — 6경기를 받았어도
    npxG 가 4경기에만 있으면 **4로 나눠야** 하고, 6으로 나누면 빠진 2경기를
    0 으로 친 셈이 돼 값이 조용히 낮아진다.
    """
    team_id: int
    window: int                    # 요청한 N
    venue: str = "all"             # "all" | "home" | "away"
    requested_matches: int = 0
    available_matches: int = 0     # 실제로 집계에 들어간 경기 수
    match_ids: list[str] = field(default_factory=list)
    sums: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def total(self, metric: str) -> float | None:
        return self.sums.get(metric)

    def sample(self, metric: str) -> int:
        return self.counts.get(metric, 0)

    def avg(self, metric: str) -> float | None:
        """경기당 값. **그 지표의 표본 수**로 나눈다."""
        n = self.counts.get(metric, 0)
        if not n or metric not in self.sums:
            return None
        return self.sums[metric] / n


def aggregate_recent(aggregates: Iterable[MatchShotAggregate], team_id: int,
                     window: int, venue: str = "all") -> RecentShotAggregate:
    """한 팀의 최근 `window` 경기를 합산한다.

    `aggregates` 는 **최신순**으로 들어와야 한다 (호출부가 정렬 책임).
    같은 match_id 는 한 번만 센다.
    """
    out = RecentShotAggregate(team_id=team_id, window=window, venue=venue,
                              requested_matches=window)
    used: set[str] = set()
    for agg in aggregates:
        if agg.team_id != team_id or agg.match_id in used:
            continue
        if venue == "home" and agg.is_home is not True:
            continue
        if venue == "away" and agg.is_home is not False:
            continue
        if len(used) >= window:
            break
        used.add(agg.match_id)
        out.match_ids.append(agg.match_id)
        out.available_matches += 1
        for m in METRICS:
            v = agg.value(m)
            if v is None:            # 그 경기에 그 지표가 없었다 → 세지 않는다
                continue
            out.sums[m] = out.sums.get(m, 0.0) + float(v)
            out.counts[m] = out.counts.get(m, 0) + 1
    return out


def aggregate_windows(aggregates: list[MatchShotAggregate], team_id: int,
                      windows: Iterable[int],
                      venues: Iterable[str] = ("all", "home", "away"),
                      ) -> dict[str, RecentShotAggregate]:
    """{"all6": ..., "home3": ...} 형태로 여러 창을 한 번에 만든다."""
    out: dict[str, RecentShotAggregate] = {}
    for w in windows:
        for v in venues:
            out[f"{v}{w}"] = aggregate_recent(aggregates, team_id, w, v)
    return out


# --------------------------------------------------------------------------
# 4. 검증 — 물리적·논리적 불변조건
# --------------------------------------------------------------------------
def validate(agg: MatchShotAggregate) -> list[str]:
    """깨진 불변조건을 문자열로 돌려준다 (빈 목록이면 정상).

    억지 단언은 넣지 않는다. 특히 `안 + 밖 == 전체` 는 **검사하지 않는다** —
    `isFromInsideBox` 가 없는 슛이 있으면 어느 쪽으로도 세지 않으므로 합이
    모자라는 게 정상이다. 확실한 것만 본다.
    """
    bad: list[str] = []
    for name in ("shots", "shots_on_target", "shots_off_target",
                 "shots_blocked", "shots_inside_box", "shots_outside_box",
                 "goals", "own_goals", "penalties"):
        v = getattr(agg, name)
        if v < 0:
            bad.append(f"{name} 음수 ({v})")
    for name in ("xg", "npxg", "xgot"):
        v = getattr(agg, name)
        if v is not None and v < 0:
            bad.append(f"{name} 음수 ({v})")
    if agg.shots_on_target > agg.shots:
        bad.append(f"유효슈팅 {agg.shots_on_target} > 총슈팅 {agg.shots}")
    if agg.shots_blocked > agg.shots:
        bad.append(f"블록 {agg.shots_blocked} > 총슈팅 {agg.shots}")
    if agg.shots_inside_box + agg.shots_outside_box > agg.shots:
        bad.append("박스 안+밖이 총슈팅보다 많다")
    if agg.npxg is not None and agg.xg is not None and agg.npxg > agg.xg + 1e-9:
        bad.append(f"npxG {agg.npxg:.3f} > xG {agg.xg:.3f}")
    if agg.goals > agg.shots:
        bad.append(f"득점 {agg.goals} > 총슈팅 {agg.shots}")
    return bad


# --------------------------------------------------------------------------
# 5. 경기 스탯과 대조
# --------------------------------------------------------------------------
# 슛맵 집계 지표 → 경기 스탯 키. 이름이 서로 달라서 표로 둔다.
RECONCILE = {
    "xg": "expected_goals",
    "npxg": "expected_goals_non_penalty",
    "xgot": "expected_goals_on_target",
    "shots": "total_shots",
    "shots_on_target": "ShotsOnTarget",
    "shots_inside_box": "shots_inside_box",
    "shots_outside_box": "shots_outside_box",
}


def reconcile(agg: MatchShotAggregate,
              stat_values: dict[str, float]) -> dict[str, float]:
    """{지표: 슛맵 − 경기스탯}. 둘 다 있는 지표만.

    **값을 맞추지 않는다.** 차이를 그대로 돌려주고, 판단은 호출부가 한다.
    """
    out: dict[str, float] = {}
    for metric, _key in RECONCILE.items():
        mine = agg.value(metric)
        theirs = stat_values.get(metric)
        if mine is None or theirs is None:
            continue
        out[metric] = float(mine) - float(theirs)
    return out
