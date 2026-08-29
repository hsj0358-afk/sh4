"""분석 파이프라인이 주고받는 데이터 구조.

수집(sources) → 정규화(normalize) → 분석(analyze) → 렌더링(render) 전 구간에서
이 데이터클래스들만 오간다. 어떤 소스가 실패해도 해당 필드만 None/빈값으로 남고
나머지는 그대로 흐르도록 모든 선택 필드에 기본값을 준다.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from datetime import datetime

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
    # Phase 1-C 슛 이벤트 계층. {"all6": RecentShotAggregate, "home3": ...}
    # TeamStats 가 아니라 여기 둔다 — 구조가 있는 값이라 fill_stats 의
    # 스칼라 병합 규칙에 맞지 않고, 기존 지표 계산에 끼어들면 안 된다.
    shot_aggregates: dict = field(default_factory=dict)
    # **경기별** 슛 집계 [MatchShotAggregate] (최신순). 창(`shot_aggregates`)은
    # 지표별 합계와 표본 수만 들고 있어서, "xG 와 슈팅이 **둘 다** 있는 경기"
    # 처럼 지표를 가로질러 표본을 맞춰야 하는 계산(2-B 의 비율 지표)을 할 수
    # 없다. 그래서 원재료를 함께 싣는다. 수집·캐시는 이미 하고 있었고
    # (`fotmob._attach_shot_aggregates`) 여기로 넘겨 주기만 하면 된다.
    shot_matches: list = field(default_factory=list)
    # **상대 팀**의 같은 경기 집계 [MatchShotAggregate] (`shot_matches` 와
    # 같은 경기, match_id 로 짝을 맞춘다). 상대가 그 경기에 몇 슛을 쳤고
    # npxG 가 얼마였는지가 곧 우리의 피슛·npxGA 다 (Phase 2-C).
    # 상대는 **숫자 teamId**(`opponent_id`, P0-1)로 잇는다 — 팀명이 아니다.
    opponent_matches: list = field(default_factory=list)

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
# Phase 2 분석 결과 (P0-3 — 그릇만 만든다. 계산은 P1 이후)
# --------------------------------------------------------------------------
# 값의 출처. `HOME/DRAW/AWAY` 처럼 모듈 상수로 둔다 (Enum 을 새로 들이지 않는다).
#   observed — 소스가 준 원본 그대로 (득점·xG·슈팅…)
#   derived  — 원본에서 계산 (npxG/슛, 박스 안 비율, 득점−npxG…)
#   model    — 모델 산출 (xPTS, 포아송 확률…)
OBSERVED, DERIVED, MODEL = "observed", "derived", "model"
PROVENANCE = (OBSERVED, DERIVED, MODEL)

# 신호가 가리키는 방향. 합산하지 않고 그대로 나열하기 위한 라벨이다.
NEUTRAL, UNKNOWN = "NEUTRAL", "UNKNOWN"
LEANS = (HOME, DRAW, AWAY, NEUTRAL, UNKNOWN)


@dataclass
class Metric:
    """분석 지표 한 칸.

    **모든 숫자를 이걸로 감싸지 않는다.** 리포트에 근거로 나가거나 출처·표본을
    함께 밝혀야 하는 값에만 쓴다. 중간 계산은 평범한 float 로 둔다.

    `value=None` 은 '계산하지 못했다'는 뜻이고 0 이 아니다 (CLAUDE.md §1-5).
    `sample_count` 는 **이 지표의** 표본 수다 — 축 전체의 경기 수와 다를 수
    있다(Phase 1-B 에서 실제로 겪은 사고).
    """
    name: str = ""                  # 내부 키 (예: "npxg_per_shot")
    label: str = ""                 # 사람이 읽을 이름 (예: "슛당 npxG")
    value: float | None = None
    provenance: str = OBSERVED      # OBSERVED / DERIVED / MODEL
    period: str = ""                # "season" · "recent6" · "home6" …
    sample_count: int | None = None  # 이 지표에 실제로 값이 있던 경기 수
    unit: str = ""                  # "" · "%" · "per_match" …
    note: str = ""
    # 값이 클수록 좋은가 (2-A §9). "higher_better" | "lower_better" | ""
    # **빈 문자열은 '방향을 정하지 않았다'는 뜻이지 중립이라는 뜻이 아니다.**
    # 슈팅처럼 많다고 좋은지 단정할 수 없는 지표는 비워 둔다. 이 값을 점수로
    # 바꾸거나 부호를 곱해 합산하지 않는다 — 표시용 메타데이터다.
    direction: str = ""
    # 같은 정보를 가리키는 지표 묶음 (2-B §15). "volume" · "chance_quality" ·
    # "execution" · "sustainability_gap" · "outcome" …
    # **점수 계산용이 아니다.** 2-I 근거 요약에서 같은 사실을 세 번 세지
    # 않으려고 붙이는 메타데이터다 (xG·npxG·xG/슛은 같은 이야기다).
    group: str = ""
    # 이 값이 **어느 피드에서** 왔나 (`standings` · `shotmap` · …).
    source: str = ""
    # 그 피드에서 **어떻게 만들어졌나** (`final_score` · `match_stat` ·
    # `shot_events` …).
    #
    # 이 둘이 필요한 이유는 실물에서 겪은 사고다. 풀럼의 시즌 xG 1.33 은
    # 경기 스탯 값이고 최근 xG 1.39 는 슛맵을 합산한 값이라, **같은 한 경기**
    # 인데도 0.06 이 달랐다. 그 차이를 빼서 "최근 xG 가 시즌보다 +0.06" 이라고
    # 적으면 측정 방식의 차이를 경기력 변화로 둔갑시킨 것이 된다. 그래서 두
    # 값을 빼기 전에 원천과 산출 방식이 같은지 먼저 본다.
    measurement_basis: str = ""

    @property
    def known(self) -> bool:
        return self.value is not None


@dataclass
class AnalysisAxis:
    """분석 축 하나 (기회의 질·수비·홈원정 …).

    축마다 전용 dataclass 를 7개 만들지 않는다 — 아직 각 축의 최종 필드
    구성이 확정되지 않았고, 확정되기 전에 모양을 박으면 P2~P6 에서 매번
    구조를 뜯어야 한다. 축은 **이름이 붙은 지표 묶음**이라는 공통점이
    있으므로 그 공통 그릇 하나로 둔다.

    `requested_matches` 는 요청한 창(예: 최근 6경기), `available_matches` 는
    실제로 쓸 수 있었던 경기 수다. 둘을 같은 수로 뭉뚱그리지 않는다.
    """
    name: str = ""
    metrics: dict[str, Metric] = field(default_factory=dict)
    requested_matches: int | None = None
    available_matches: int | None = None
    notes: list[str] = field(default_factory=list)

    def get(self, key: str) -> Metric | None:
        return self.metrics.get(key)

    def value(self, key: str) -> float | None:
        m = self.metrics.get(key)
        return m.value if m else None


@dataclass
class MatchupPair:
    """공격 지표 1개 ↔ 상대 수비 지표 1개 (2-G).

    곱하거나 더해서 하나의 점수로 만들지 않는다 — 두 값을 나란히 두고
    읽는 사람이 판단한다.
    """
    concept: str = ""               # "chance_volume" · "chance_quality" …
    label: str = ""
    attack: Metric | None = None
    defense: Metric | None = None
    direction: str = ""             # "home_attack" | "away_attack"
    note: str = ""


@dataclass
class Signal:
    """독립 신호 하나 (2-H). **합산하지 않는다.**

    `lean` 은 방향 라벨일 뿐 점수가 아니다. 신호 개수를 세어 최종 픽을
    만들지 않는다 — "5개가 홈을 가리킨다"까지가 결과다.
    """
    name: str = ""
    lean: str = UNKNOWN             # HOME/DRAW/AWAY/NEUTRAL/UNKNOWN
    strength: str = ""              # "low" | "medium" | "high" (표본 기반)
    basis: str = ""                 # 무엇을 보고 정했나
    sample_count: int | None = None
    provenance: str = OBSERVED
    note: str = ""


@dataclass
class EvidenceItem:
    """근거 한 줄 (2-I).

    같은 정보를 여러 번 세지 않도록 축별 대표만 만든다. `side` 는 이 근거가
    지지하는 쪽이고, `counter=True` 면 그 쪽을 **반박**하는 근거다.
    """
    claim: str = ""
    side: str = NEUTRAL             # HOME / DRAW / AWAY
    counter: bool = False
    metric: str = ""
    value: float | None = None
    comparison: str = ""            # 무엇과 견줬나 (상대·리그평균 …)
    period: str = ""
    sample_count: int | None = None
    provenance: str = OBSERVED
    axis: str = ""                  # 어느 분석 축에서 나왔나 (중복 방지용)


@dataclass
class DataQuality:
    """분석 축별 데이터 상태 (2-J).

    **종합 confidence 점수를 만들지 않는다.** 축별로 쓸 수 있었는지와 왜
    못 썼는지만 남긴다. 표본이 기준 미만이면 값을 만들지 않고 여기에
    `degraded_reason` 을 적는다.
    """
    # {축 이름: {"available": bool, "requested": int, "available_matches": int,
    #            "degraded_reason": str, "coverage": float|None}}
    axes: dict[str, dict] = field(default_factory=dict)
    source_status: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def mark(self, axis: str, available: bool, requested: int | None = None,
             available_matches: int | None = None, reason: str = "") -> None:
        self.axes[axis] = {"available": available, "requested": requested,
                           "available_matches": available_matches,
                           "degraded_reason": reason}

    def unavailable(self) -> list[str]:
        return [k for k, v in self.axes.items() if not v.get("available")]


@dataclass
class TeamAnalysis:
    """한 팀의 Phase 2 분석 결과 묶음.

    **축이 None 이면 '아직 계산하지 않았거나 표본이 모자라 만들지 않았다'는
    뜻이다.** 빈 축 객체를 넣어 분석이 끝난 것처럼 보이게 하지 않는다.
    """
    team: str = ""                  # 정규명 (프로젝트 canonical)
    fotmob_id: int | None = None    # 숫자 teamId (슛 계층과 잇는 열쇠)
    is_home: bool | None = None

    time_context: AnalysisAxis | None = None        # 2-A
    chance_quality: AnalysisAxis | None = None      # 2-B
    defensive_quality: AnalysisAxis | None = None   # 2-C
    sustainability: AnalysisAxis | None = None      # 2-D
    venue_context: AnalysisAxis | None = None       # 2-E
    schedule_strength: AnalysisAxis | None = None   # 2-F
    data_quality: DataQuality | None = None         # 2-J

    AXES = ("time_context", "chance_quality", "defensive_quality",
            "sustainability", "venue_context", "schedule_strength")

    def computed_axes(self) -> list[str]:
        """실제로 값이 들어간 축 이름."""
        return [a for a in self.AXES if getattr(self, a) is not None]


@dataclass
class MatchAnalysis:
    """한 경기의 Phase 2 분석 결과.

    `Match.probs`(피나클 배당 확률)와 **별개의 객체**다. 여기서 확률을
    다시 계산하거나 배당 확률과 합치지 않는다.

    최종 승무패를 담는 필드는 두지 않는다 — 구조적으로 추천을 표현할 수
    없어야 한다(CLAUDE.md §1-3).

    `as_of` 는 이 분석의 시점 기준이다. 과거 경기를 고를 때 이 시각보다
    앞선 것만 쓴다(`Report.matches_before`). `generated_at` 은 두지 않는다 —
    `Report.generated_at` 이 이미 있고, 리포트 한 부의 생성 시각은 하나면
    충분하다.
    """
    home: TeamAnalysis | None = None
    away: TeamAnalysis | None = None
    matchup: list[MatchupPair] = field(default_factory=list)
    conflicts: list[Signal] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    data_quality: DataQuality | None = None
    # 모델 산출값 전용 축 (xPTS·포아송 확률…). observed/derived 축과 섞지
    # 않으려고 자리를 따로 뒀다. `probs`(피나클 배당 확률)와는 무관하며
    # 서로 합치지 않는다.
    model: AnalysisAxis | None = None
    as_of: datetime | None = None   # 시점 기준

    def evidence_for(self, side: str, counter: bool = False
                     ) -> list[EvidenceItem]:
        return [e for e in self.evidence
                if e.side == side and e.counter is counter]

    def signals_by_lean(self) -> dict[str, int]:
        """방향별 신호 **개수**. 이것으로 픽을 만들지 않는다 —
        '몇 개가 어느 쪽을 가리키는지'를 그대로 보여주기 위한 집계다."""
        out: dict[str, int] = {}
        for s in self.conflicts:
            out[s.lean] = out.get(s.lean, 0) + 1
        return out

    @property
    def has_conflict(self) -> bool:
        leans = {s.lean for s in self.conflicts} - {NEUTRAL, UNKNOWN}
        return len(leans) > 1


def _revive_metric(d: Any) -> Metric | None:
    return Metric(**d) if isinstance(d, dict) else None


def _revive_axis(d: Any) -> AnalysisAxis | None:
    if not isinstance(d, dict):
        return None
    out = AnalysisAxis(**{k: v for k, v in d.items() if k != "metrics"})
    out.metrics = {k: m for k, m in
                   ((k, _revive_metric(v)) for k, v in
                    (d.get("metrics") or {}).items()) if m is not None}
    return out


def revive_team_analysis(d: Any) -> TeamAnalysis | None:
    """dict → TeamAnalysis. dataclass 중첩은 asdict 가 풀어 놓으므로 되감는다."""
    if not isinstance(d, dict):
        return None
    out = TeamAnalysis(team=d.get("team", ""), fotmob_id=d.get("fotmob_id"),
                       is_home=d.get("is_home"))
    for axis in TeamAnalysis.AXES:
        setattr(out, axis, _revive_axis(d.get(axis)))
    dq = d.get("data_quality")
    out.data_quality = DataQuality(**dq) if isinstance(dq, dict) else None
    return out


def revive_match_analysis(d: Any) -> MatchAnalysis | None:
    if not isinstance(d, dict):
        return None
    out = MatchAnalysis(as_of=d.get("as_of"))
    out.model = _revive_axis(d.get("model"))
    out.home = revive_team_analysis(d.get("home"))
    out.away = revive_team_analysis(d.get("away"))
    out.matchup = [MatchupPair(**{k: v for k, v in p.items()
                                  if k not in ("attack", "defense")},
                               attack=_revive_metric(p.get("attack")),
                               defense=_revive_metric(p.get("defense")))
                   for p in (d.get("matchup") or []) if isinstance(p, dict)]
    out.conflicts = [Signal(**s) for s in (d.get("conflicts") or [])
                     if isinstance(s, dict)]
    out.evidence = [EvidenceItem(**e) for e in (d.get("evidence") or [])
                    if isinstance(e, dict)]
    dq = d.get("data_quality")
    out.data_quality = DataQuality(**dq) if isinstance(dq, dict) else None
    return out


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
    # Phase 2 분석 결과. None = 아직 계산하지 않음.
    # `probs`(피나클 배당 확률)와 **별개**이며 서로 덮어쓰지 않는다.
    analysis: MatchAnalysis | None = None

    @property
    def title(self) -> str:
        return f"{self.home.display} vs {self.away.display}"


@dataclass
class SeasonMatch:
    """시즌에 이미 치러졌거나 예정된 경기 1건 (Phase 2 의 과거 경기 색인).

    회차 14경기를 담는 `Match` 와 목적이 다르다 — 이쪽은 배당·확률·프로필이
    없는 **기록**이고, 시점별 분석(2-F 상대 강도)이 "그 경기 이전에 무슨 일이
    있었나"를 묻기 위한 것이다.

    ## 팀 식별자가 두 벌인 이유

    이 프로젝트의 정규 식별자는 **팀명 문자열**(`TeamResolver` 가 만든
    canonical name)이고, 슛 계층은 **FotMob 숫자 teamId** 로 돈다. 둘은
    서로 다른 체계라서 하나로 합치면 한쪽이 조용히 끊긴다. 그래서 둘 다
    들고 다닌다.

      · `home_team` / `away_team`         정규명 (프로젝트 canonical)
      · `home_fotmob_id` / `away_fotmob_id` 숫자 (슛 계층·순위표와 연결)

    팀명만으로 과거 경기를 잇지 않는다.

    ## kickoff

    `kickoff` 는 정렬·시점 비교에 쓰는 datetime 이다. 원본 문자열이 UTC 표시
    (`...Z`)면 **timezone 을 가진** datetime 이 되고, 표시가 없으면 naive 로
    두고 `kickoff_aware=False` 로 남긴다. **임의의 시간대를 가정하지 않는다.**
    파싱에 실패하면 `kickoff=None` 이고 `kickoff_raw` 에 원본이 남는다.
    """
    match_id: str = ""
    competition: str = ""         # 내부 리그 키 (이 경기를 어느 리그 피드에서 얻었나)
    kickoff: datetime | None = None
    kickoff_raw: str = ""         # 원본 문자열 (파싱 실패해도 근거를 남긴다)
    kickoff_aware: bool = False   # timezone 정보가 있었나
    home_team: str = ""           # 정규명
    away_team: str = ""
    home_fotmob_id: int | None = None
    away_fotmob_id: int | None = None
    home_goals: int | None = None
    away_goals: int | None = None
    finished: bool = False

    @property
    def sort_key(self) -> tuple:
        """kickoff 오름차순, 같으면 match_id 로 안정 정렬.

        kickoff 가 없는 경기는 **뒤로** 보낸다 — 시점을 모르는 경기를 과거
        구간에 끼워 넣으면 시점 비교가 무너진다.
        """
        if self.kickoff is None:
            return (1, "", str(self.match_id))
        return (0, self.kickoff.isoformat(), str(self.match_id))

    @property
    def result(self) -> str | None:
        """홈 기준 H/D/A. 종료되지 않았거나 점수가 없으면 None."""
        if not self.finished or self.home_goals is None or self.away_goals is None:
            return None
        if self.home_goals > self.away_goals:
            return HOME
        return DRAW if self.home_goals == self.away_goals else AWAY


def matches_before(season: list[SeasonMatch], as_of: datetime | None,
                   finished_only: bool = True) -> list[SeasonMatch]:
    """`as_of` **이전에 시작한** 경기만. Phase 2-F 누수 방지의 기본 장치.

    - 기준은 **엄격한 부등호** `kickoff < as_of` 다. 같은 시각에 시작한 경기는
      **포함하지 않는다** — 그 경기 결과가 아직 나오지 않았기 때문이다.
      (같은 날 15:00 경기는 20:00 경기 분석에 쓸 수 있지만, 15:00 경기끼리는
      서로를 쓸 수 없다.)
    - `kickoff` 가 없는 경기는 시점을 알 수 없으므로 **항상 제외**한다.
    - `as_of` 가 None 이면 빈 목록. "기준이 없으니 전부"가 아니다 — 그렇게
      두면 실수로 미래가 섞인다.
    - 기본은 **종료된 경기만**. 예정 경기를 과거처럼 쓰면 안 된다.

    tz-aware 와 naive 를 섞어 비교하면 파이썬이 TypeError 를 낸다. 그런
    경기는 비교 자체를 하지 않고 제외하며, 호출부가 세어 볼 수 있도록
    조용히 빠뜨리기만 한다(추측해서 시간대를 붙이지 않는다).
    """
    if as_of is None:
        return []
    out = []
    for m in season:
        if m.kickoff is None:
            continue
        if finished_only and not m.finished:
            continue
        try:
            if m.kickoff < as_of:
                out.append(m)
        except TypeError:          # aware ↔ naive 혼용 — 비교 불가
            continue
    out.sort(key=lambda x: x.sort_key)
    return out


@dataclass
class Report:
    """리포트 한 부."""
    round_id: str = ""            # 회차
    generated_at: str = ""
    matches: list[Match] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_status: dict[str, str] = field(default_factory=dict)
    verdict: RoundVerdict | None = None   # 회차 승산 (지침 §5)
    # 시즌 경기 색인 (Phase 2). kickoff 오름차순으로 정렬해 둔다.
    season_matches: list[SeasonMatch] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def matches_before(self, as_of: datetime | None,
                       finished_only: bool = True) -> list[SeasonMatch]:
        """`as_of` 이전 경기만 (모듈 함수와 같은 규칙)."""
        return matches_before(self.season_matches, as_of, finished_only)
