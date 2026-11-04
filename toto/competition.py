"""경기의 대회(competition)를 정한다 (Phase 6-C).

파서(`sources/betman.py`)는 경기 자체 — 번호·팀·시각 — 만 읽고 대회를 정하지
않는다. 베트맨 경기 행에는 **대회 칸이 없다** (260054·260055 실측). 대회는
여기서 정하고, 무엇으로 정했는지를 `Match.league_basis` 에 남긴다.

## 근거

| 근거 | 뜻 | 확정 |
|---|---|---|
| `matches_file` | 사람이 matches.yaml 에 적은 대회 | 예 |
| `team_league`  | 팀 소속 리그로 추론 (홈 → 원정) | 아니오 |
| `none`         | 정하지 못함 | — |
| `""`           | 기록 없음 (옛 저장본·데모·직접 만든 Match) | 아니오 |

**행 전체 문자열로 추정하지 않는다.** `settings.league_of()` 는 리그 *표기*
를 읽는 함수인데, 베트맨 행 전체에 걸면 국가대표 경기의 국가명이 국내리그
별칭에 걸린다 — `이탈리아 vs 벨기에` → 세리에A, `튀르키예 vs 프랑스` →
리그앙, `잉글랜드 vs 스페인` → EPL (260055 실측). 별칭은 지우지 않는다 —
matches.yaml 의 리그 표기를 읽는 데 그대로 쓰이므로, **쓰는 자리**를
바로잡았다.

## 확정된 대회는 팀 추론이 덮지 않는다

`fotmob.enrich()` 는 순위표로 팀 소속을 정정한 뒤 경기의 대회를 홈팀 소속으로
다시 맞춘다 — 승강을 반영하려는 것이고 팀 추론에는 옳다(§3-5). 그런데 사람이
적은 대회까지 덮으면 안 된다. `adopt_team_league()` 가 그 판정을 한 곳에서
한다.

## 대회 상태 (`state`)

| 상태 | 뜻 |
|---|---|
| `supported`    | 등록됐고 국내리그 (`type` 미지정 또는 `league`) — 회차 분석이 지원 |
| `unsupported`  | 등록됐지만 국내리그가 아니다 (대륙대회·컵) — 식별은 했지만 미지원 |
| `unregistered` | 이름은 있지만 설정에 없는 대회 |
| `unknown`      | 대회를 정하지 못했다 |

국가대표·컵·UCL/UEL 지원은 이 Phase 가 구현하지 않는다. 지원하지 않는 대회를
**국내리그로 오인하지 않는 것**까지가 범위다.
"""
from __future__ import annotations

from .settings import LEAGUE

MATCHES_FILE = "matches_file"
TEAM_LEAGUE = "team_league"
NONE = "none"
UNRECORDED = ""
BASES = (MATCHES_FILE, TEAM_LEAGUE, NONE)

SUPPORTED = "supported"
UNSUPPORTED = "unsupported"
UNREGISTERED = "unregistered"
UNKNOWN = "unknown"
STATES = (SUPPORTED, UNSUPPORTED, UNREGISTERED, UNKNOWN)


def is_confirmed(match) -> bool:
    """사람이 적은 대회인가 — 팀 추론이 덮으면 안 되는 대회."""
    return bool(match.league) and match.league_basis == MATCHES_FILE


def from_teams(match, resolver) -> str | None:
    """팀 소속 리그 (홈 우선, 없으면 원정). 정규명이 없으면 볼 수 없다."""
    for ref in (match.home, match.away):
        key = resolver.league_of(ref.canonical) if ref.canonical else None
        if key:
            return key
    return None


def resolve(match, resolver, settings) -> str:
    """경기의 대회를 정하고 근거를 돌려준다.

    이미 대회가 있으면 손대지 않는다 — matches.yaml 에 적힌 대회이거나
    (`matches_file`), 근거 기록 없이 들어온 값이다(예전 동작 그대로).
    없으면 팀 소속으로 추론하고, 그것도 없으면 `none` 이다. **추측으로
    채우지 않는다.**
    """
    if match.league:
        return match.league_basis
    key = from_teams(match, resolver)
    if key:
        match.league = key
        match.league_ko = settings.league_ko(key)
        match.league_basis = TEAM_LEAGUE
    else:
        match.league_basis = NONE
    return match.league_basis


def adopt_team_league(match, key: str | None, settings) -> bool:
    """팀 소속이 정정됐을 때 **확정되지 않은** 대회만 그 소속으로 고친다.

    고쳤으면 True. 근거 기록이 없던 경기(옛 동작)는 근거 칸을 지어내지 않고
    대회만 고친다.
    """
    if not key or key == match.league or is_confirmed(match):
        return False
    match.league = key
    match.league_ko = settings.league_ko(key)
    if match.league_basis:
        match.league_basis = TEAM_LEAGUE
    return True


def state(key: str, settings) -> str:
    """대회 키 → `supported` / `unsupported` / `unregistered` / `unknown`."""
    if not key:
        return UNKNOWN
    if key not in settings.leagues:
        return UNREGISTERED
    return SUPPORTED if settings.league_type(key) == LEAGUE else UNSUPPORTED
