"""분석 파이프라인이 주고받는 데이터 구조.

수집(sources) → 정규화(normalize) → 분석(analyze) → 렌더링(render) 전 구간에서
이 데이터클래스들만 오간다. 어떤 소스가 실패해도 해당 필드만 None/빈값으로 남고
나머지는 그대로 흐르도록 모든 선택 필드에 기본값을 준다.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from .predict import MatchProb, RoundVerdict
from typing import Any

# --------------------------------------------------------------------------
# 결과 코드
# --------------------------------------------------------------------------
HOME, DRAW, AWAY = "H", "D", "A"
RESULT_KO = {HOME: "승", DRAW: "무", AWAY: "패"}


# --------------------------------------------------------------------------
# 팀
# --------------------------------------------------------------------------
@dataclass
class TeamRef:
    """경기에 등장하는 한 팀의 식별 정보.

    베트맨은 한글, 피나클/후스코어드는 영문 팀명을 쓰기 때문에
    `name_ko`(베트맨 표기)와 `canonical`(영문 정규명)을 함께 들고 다닌다.
    """
    name_ko: str = ""
    canonical: str = ""          # 영문 정규 팀명 (매칭 키)
    display: str = ""            # 리포트에 표시할 이름
    whoscored_url: str = ""
    matched: bool = True         # 별칭 매칭 성공 여부

    def __post_init__(self) -> None:
        if not self.display:
            self.display = self.name_ko or self.canonical


@dataclass
class FormEntry:
    """최근 경기 1건."""
    date: str = ""
    opponent: str = ""
    home: bool = True            # 이 팀이 홈이었는지
    goals_for: int = 0
    goals_against: int = 0
    result: str = DRAW           # W/D/L 을 HOME/DRAW/AWAY 가 아닌 자체 코드로

    @property
    def points(self) -> int:
        return {"W": 3, "D": 1, "L": 0}.get(self.result, 0)

    @property
    def score(self) -> str:
        return f"{self.goals_for}-{self.goals_against}"


@dataclass
class TeamStats:
    """리그 순위표 + 후스코어드 팀 통계.

    값이 없는 항목은 None 으로 둔다. 백분위 계산과 레이더 차트는
    None 인 항목을 건너뛴다.
    """
    # 순위표
    rank: int | None = None
    played: int | None = None
    wins: int | None = None
    draws: int | None = None
    losses: int | None = None
    goals_for: int | None = None
    goals_against: int | None = None
    points: int | None = None

    # 홈/원정 분리 성적
    home_played: int | None = None
    home_points: int | None = None
    away_played: int | None = None
    away_points: int | None = None

    # 후스코어드 팀 통계 (경기당 평균)
    shots_pg: float | None = None
    shots_on_target_pg: float | None = None
    possession: float | None = None
    pass_success: float | None = None
    aerials_won_pg: float | None = None
    tackles_pg: float | None = None
    interceptions_pg: float | None = None
    dribbles_pg: float | None = None
    fouls_pg: float | None = None
    rating: float | None = None

    # 기대득점 (제공되는 경우)
    xg_pg: float | None = None
    xga_pg: float | None = None

    # ---- 파생 지표 ----
    @property
    def goals_for_pg(self) -> float | None:
        if self.goals_for is None or not self.played:
            return None
        return self.goals_for / self.played

    @property
    def goals_against_pg(self) -> float | None:
        if self.goals_against is None or not self.played:
            return None
        return self.goals_against / self.played

    @property
    def goal_diff(self) -> int | None:
        if self.goals_for is None or self.goals_against is None:
            return None
        return self.goals_for - self.goals_against

    @property
    def points_pg(self) -> float | None:
        if self.points is None or not self.played:
            return None
        return self.points / self.played

    @property
    def home_points_pg(self) -> float | None:
        if self.home_points is None or not self.home_played:
            return None
        return self.home_points / self.home_played

    @property
    def away_points_pg(self) -> float | None:
        if self.away_points is None or not self.away_played:
            return None
        return self.away_points / self.away_played

    @property
    def shot_accuracy(self) -> float | None:
        if not self.shots_pg or self.shots_on_target_pg is None:
            return None
        return self.shots_on_target_pg / self.shots_pg * 100

    @property
    def defensive_actions_pg(self) -> float | None:
        if self.tackles_pg is None and self.interceptions_pg is None:
            return None
        return (self.tackles_pg or 0.0) + (self.interceptions_pg or 0.0)


@dataclass
class TeamProfile:
    """한 팀에 대해 수집한 모든 것."""
    team: TeamRef
    league: str = ""
    stats: TeamStats = field(default_factory=TeamStats)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    style_of_play: list[str] = field(default_factory=list)
    form: list[FormEntry] = field(default_factory=list)     # 최신순
    missing_players: list[dict] = field(default_factory=list)
    rest_days: int | None = None
    source_ok: bool = False       # 후스코어드 수집 성공 여부

    @property
    def form_points(self) -> int:
        return sum(f.points for f in self.form)


# --------------------------------------------------------------------------
# 배당률
# --------------------------------------------------------------------------
@dataclass
class Odds:
    """피나클 배당률 스냅샷 (decimal odds)."""
    home: float | None = None
    draw: float | None = None
    away: float | None = None

    # 아시안 핸디캡 (홈 기준 라인)
    ah_line: float | None = None
    ah_home: float | None = None
    ah_away: float | None = None

    # 오버/언더
    ou_line: float | None = None
    ou_over: float | None = None
    ou_under: float | None = None

    fetched_at: str = ""
    source: str = ""              # "arcadia-api" / "playwright" / ""

    @property
    def available(self) -> bool:
        return None not in (self.home, self.draw, self.away)


# --------------------------------------------------------------------------
# 상대전적
# --------------------------------------------------------------------------
@dataclass
class H2HEntry:
    date: str = ""
    home_team: str = ""
    away_team: str = ""
    home_goals: int = 0
    away_goals: int = 0
    competition: str = ""

    def result_for(self, canonical: str) -> str:
        """주어진 팀 기준 W/D/L."""
        if self.home_goals == self.away_goals:
            return "D"
        winner = self.home_team if self.home_goals > self.away_goals else self.away_team
        return "W" if winner == canonical else "L"


@dataclass
class H2H:
    entries: list[H2HEntry] = field(default_factory=list)   # 최신순
    home_wins: int = 0
    draws: int = 0
    away_wins: int = 0
    source_ok: bool = False

    @property
    def total(self) -> int:
        return self.home_wins + self.draws + self.away_wins


# --------------------------------------------------------------------------
# 경기
# --------------------------------------------------------------------------
@dataclass
class Match:
    """승무패 14경기 중 한 경기."""
    no: int                       # 1~14
    league: str = ""              # config_toto.yaml 의 리그 키
    league_ko: str = ""
    home: TeamRef = field(default_factory=TeamRef)
    away: TeamRef = field(default_factory=TeamRef)
    kickoff_kst: str = ""         # "2026-08-09 20:00"

    # 수집물
    odds: Odds = field(default_factory=Odds)
    probs: MatchProb | None = None       # 보정 확률 + argmax 픽
    home_profile: TeamProfile | None = None
    away_profile: TeamProfile | None = None
    h2h: H2H = field(default_factory=H2H)

    # 분석 산출물
    radar: dict[str, Any] = field(default_factory=dict)
    matchup_notes: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)   # 경고/누락 안내

    @property
    def title(self) -> str:
        return f"{self.home.display} vs {self.away.display}"


@dataclass
class Report:
    """리포트 한 부."""
    round_id: str = ""            # 회차
    generated_at: str = ""
    matches: list[Match] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_status: dict[str, str] = field(default_factory=dict)
    verdict: RoundVerdict | None = None   # 회차 승산 (지침 §5)

    def to_dict(self) -> dict:
        return asdict(self)
