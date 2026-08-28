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
    fotmob_id: str = ""          # FotMob 팀 ID (팀 상세 조회용)
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

    # 홈/원정 분리 성적 ('장소 특화도' 축은 승점만이 아니라 득실차도 본다)
    home_played: int | None = None
    home_points: int | None = None
    home_goals_for: int | None = None
    home_goals_against: int | None = None
    away_played: int | None = None
    away_points: int | None = None
    away_goals_for: int | None = None
    away_goals_against: int | None = None

    # 팀 통계 (경기당 평균)
    shots_pg: float | None = None
    shots_on_target_pg: float | None = None
    shots_against_pg: float | None = None      # 피슈팅 — 경기별 슛맵에서만 나온다
    shots_on_target_against_pg: float | None = None
    key_passes_pg: float | None = None
    # FotMob 시즌 통계 피드에서 오는 항목 (리그 카탈로그 29종 중 쓰는 것)
    big_chances_pg: float | None = None        # 결정적 기회 — '공격 창출력'
    big_chances_missed_pg: float | None = None
    touches_opp_box_pg: float | None = None    # 상대 박스 터치 — '경기 지배력'
    accurate_passes_pg: float | None = None
    poss_won_att_3rd_pg: float | None = None   # 상대 진영 볼 탈취
    saves_pg: float | None = None
    clearances_pg: float | None = None
    corners_pg: float | None = None
    clean_sheets: float | None = None
    possession: float | None = None
    pass_success: float | None = None
    pass_success_opp_half: float | None = None  # 상대 진영 패스 성공률
    aerials_won_pg: float | None = None
    tackles_pg: float | None = None
    interceptions_pg: float | None = None
    dribbles_pg: float | None = None
    fouls_pg: float | None = None
    rating: float | None = None

    # 기대득점 — 시즌 누계와 그 표본 경기수를 함께 둔다. FotMob 의 xG 표는
    # 순위표와 경기수가 다를 수 있어(집계 시점 차이) 따로 나눠야 정확하다.
    xg_total: float | None = None
    xga_total: float | None = None
    xg_played: int | None = None
    # 소스가 경기당 값을 직접 주는 경우 (후스코어드 등)
    xg_pg_raw: float | None = None
    xga_pg_raw: float | None = None

    # ---- 시즌 통계 피드 (FotMob stats.teams[]) ----------------------------
    # 전부 그 소스가 주는 단위 그대로다. 이름 끝의 _pg 는 '경기당', 없으면 누계.
    set_piece_goals: float | None = None            # 누계
    set_piece_goals_conceded: float | None = None   # 누계
    penalties_won: float | None = None              # 누계
    penalties_conceded: float | None = None         # 누계
    yellow_cards: float | None = None               # 누계
    red_cards: float | None = None                  # 누계
    accurate_crosses_pg: float | None = None
    accurate_long_balls_pg: float | None = None

    # ---- 경기 상세 집계 (최근 N경기) --------------------------------------
    # 시즌 누계가 아니라 **최근 N경기 표본의 합계**다. 시즌 지표와 의미가
    # 다르므로 이름에 _recent 를 붙여 섞이지 않게 한다. 경기당 값이 필요하면
    # 아래 _recent_pg 속성을 쓴다 (recent_matches 로 나눈 값).
    recent_matches: int | None = None               # 받아 온 경기 수
    # 지표마다 표본이 다를 수 있다 — 어떤 경기에는 npxG 가 없고 슈팅만 있다.
    # 그런 지표를 recent_matches 로 나누면 빠진 경기를 0 으로 친 것과 같아져
    # 값이 조용히 낮아진다. 그래서 {필드 이름: 그 지표가 실제로 있던 경기 수}
    # 를 따로 들고 다니며 그것으로 나눈다. None 이면 정보가 없다는 뜻이라
    # recent_matches 로 되돌아간다 (fill_stats 가 다른 필드와 똑같이 다루도록
    # 기본값을 빈 dict 가 아니라 None 으로 뒀다).
    recent_counts: dict | None = None
    npxg_recent: float | None = None
    npxga_recent: float | None = None
    xgot_recent: float | None = None
    xgot_against_recent: float | None = None
    xg_open_play_recent: float | None = None
    xg_set_play_recent: float | None = None
    shots_recent: float | None = None
    shots_against_recent: float | None = None
    shots_on_target_recent: float | None = None
    shots_on_target_against_recent: float | None = None
    shots_inside_box_recent: float | None = None
    shots_outside_box_recent: float | None = None

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

    # ---- 6축 레이더용 파생 지표 ------------------------------------------
    # 각 축은 재료가 하나라도 없으면 None 을 돌려준다. 반쪽짜리 값으로
    # 축을 채우면 리그 백분위가 왜곡돼서, 차라리 축을 빼는 편이 낫다.
    @property
    def home_goal_diff_pg(self) -> float | None:
        if self.home_goals_for is None or self.home_goals_against is None \
                or not self.home_played:
            return None
        return (self.home_goals_for - self.home_goals_against) / self.home_played

    @property
    def away_goal_diff_pg(self) -> float | None:
        if self.away_goals_for is None or self.away_goals_against is None \
                or not self.away_played:
            return None
        return (self.away_goals_for - self.away_goals_against) / self.away_played

    @property
    def conversion_rate(self) -> float | None:
        """슈팅 대비 득점 전환율(%) — '공격 효율성' 축의 재료."""
        if not self.shots_pg or self.goals_for_pg is None:
            return None
        return self.goals_for_pg / self.shots_pg * 100

    @property
    def xg_pg(self) -> float | None:
        if self.xg_pg_raw is not None:
            return self.xg_pg_raw
        if self.xg_total is None or not self.xg_played:
            return None
        return self.xg_total / self.xg_played

    @property
    def xga_pg(self) -> float | None:
        if self.xga_pg_raw is not None:
            return self.xga_pg_raw
        if self.xga_total is None or not self.xg_played:
            return None
        return self.xga_total / self.xg_played

    @property
    def finishing_delta(self) -> float | None:
        """실제 득점 − xG. 양수면 기대 이상으로 넣고 있다는 뜻.

        FotMob 도 xgDiff 를 주지만 부호 규칙이 문서화돼 있지 않아 쓰지 않는다.
        득점은 순위표에서 이미 확보했으므로 직접 뺀다.
        """
        if self.goals_for is None or self.xg_total is None:
            return None
        return self.goals_for - self.xg_total

    @property
    def defending_delta(self) -> float | None:
        """실제 실점 − 피xG. 음수면 기대보다 덜 실점하고 있다는 뜻."""
        if self.goals_against is None or self.xga_total is None:
            return None
        return self.goals_against - self.xga_total

    # ---- 최근 N경기 표본의 경기당 값 --------------------------------------
    # 전부 `_recent` 합계를 `recent_matches` 로 나눈 파생값이다. 시즌 지표
    # (xg_pg 등)와 표본이 다르므로 이름으로 구분해 둔다. 표본이 없으면 None —
    # 0 으로 채우면 '0개를 기록했다'는 실제 값과 구분되지 않는다.
    def _per_recent(self, name: str) -> float | None:
        total = getattr(self, name)
        if total is None:
            return None
        n = (self.recent_counts or {}).get(name) or self.recent_matches
        if not n:
            return None
        return total / n

    @property
    def npxg_recent_pg(self) -> float | None:
        return self._per_recent("npxg_recent")

    @property
    def npxga_recent_pg(self) -> float | None:
        return self._per_recent("npxga_recent")

    @property
    def xgot_recent_pg(self) -> float | None:
        return self._per_recent("xgot_recent")

    @property
    def xgot_against_recent_pg(self) -> float | None:
        return self._per_recent("xgot_against_recent")

    @property
    def xg_open_play_recent_pg(self) -> float | None:
        return self._per_recent("xg_open_play_recent")

    @property
    def xg_set_play_recent_pg(self) -> float | None:
        return self._per_recent("xg_set_play_recent")

    @property
    def shots_recent_pg(self) -> float | None:
        return self._per_recent("shots_recent")

    @property
    def shots_against_recent_pg(self) -> float | None:
        return self._per_recent("shots_against_recent")

    @property
    def shots_on_target_recent_pg(self) -> float | None:
        return self._per_recent("shots_on_target_recent")

    @property
    def shots_on_target_against_recent_pg(self) -> float | None:
        return self._per_recent("shots_on_target_against_recent")

    @property
    def shots_inside_box_recent_pg(self) -> float | None:
        return self._per_recent("shots_inside_box_recent")

    @property
    def shots_outside_box_recent_pg(self) -> float | None:
        return self._per_recent("shots_outside_box_recent")

    @property
    def inside_box_shot_share(self) -> float | None:
        """박스 안 슈팅 비율(%). 슈팅의 '질' 을 거칠게 가늠한다."""
        inside, outside = self.shots_inside_box_recent, self.shots_outside_box_recent
        if inside is None or outside is None:
            return None
        total = inside + outside
        return None if total <= 0 else inside / total * 100.0

    @property
    def xgot_delta_recent(self) -> float | None:
        """xGOT − npxG. 양수면 기대보다 좋은 코스로 때리고 있다는 뜻."""
        if self.xgot_recent is None or self.npxg_recent is None:
            return None
        return self.xgot_recent - self.npxg_recent

    # ---- 시즌 누계를 경기당으로 -------------------------------------------
    # 피드가 누계로 주는 항목들. 리그 안에서도 팀마다 소화 경기수가 달라서
    # (연기·스플릿) 누계를 그대로 나란히 두면 경기를 더 치른 팀이 부풀려진다.
    def _per_played(self, name: str) -> float | None:
        total = getattr(self, name)
        if total is None or not self.played:
            return None
        return total / self.played

    @property
    def set_piece_goals_pg(self) -> float | None:
        return self._per_played("set_piece_goals")

    @property
    def set_piece_goals_conceded_pg(self) -> float | None:
        return self._per_played("set_piece_goals_conceded")

    @property
    def penalties_won_pg(self) -> float | None:
        return self._per_played("penalties_won")

    @property
    def penalties_conceded_pg(self) -> float | None:
        return self._per_played("penalties_conceded")

    @property
    def yellow_cards_pg(self) -> float | None:
        return self._per_played("yellow_cards")

    @property
    def red_cards_pg(self) -> float | None:
        return self._per_played("red_cards")

    @property
    def set_piece_goal_share(self) -> float | None:
        """득점 중 세트피스 비중(%). 어떻게 넣는 팀인지 가늠한다."""
        if self.set_piece_goals is None or not self.goals_for:
            return None
        return self.set_piece_goals / self.goals_for * 100.0

    @property
    def defensive_solidity(self) -> float | None:
        """피슈팅의 역수 — 적게 맞을수록 높다. '수비 견고함' 축.

        역수를 그대로 쓰지 않고 백분위 단계에서 invert 로 뒤집는 방법도 있지만,
        제안대로 '역수'를 값으로 두면 지표 비교표에도 그대로 쓸 수 있다.
        """
        if not self.shots_against_pg:
            return None
        return 1.0 / self.shots_against_pg


def fill_stats(dst: TeamStats, src: TeamStats, overwrite: bool = False) -> int:
    """src 의 값으로 dst 의 빈 칸을 채운다. 채운 항목 수를 돌려준다.

    한 팀의 지표를 두 소스가 나눠서 들고 있다 — 순위표·홈원정 승점은 FotMob,
    점유율·패스성공률·평점은 후스코어드다. 나중에 붙는 소스가 앞서 채운 값을
    None 으로 덮어쓰면 안 되므로, 기본은 '비어 있을 때만' 채운다.
    """
    filled = 0
    for name in src.__dataclass_fields__:
        value = getattr(src, name)
        if value is None:
            continue
        if overwrite or getattr(dst, name) is None:
            setattr(dst, name, value)
            filled += 1
    return filled


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
