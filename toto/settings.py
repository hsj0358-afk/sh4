"""설정 로딩: config_toto.yaml + .env + 내장 기본값.

briefing/settings.py 의 로더 패턴을 그대로 따른다 — PyYAML 이나 설정 파일이
없어도 내장 기본값으로 동작해야 한다(오프라인/샘플 실행 시 의존성 최소화).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent

# config_toto.yaml 이 없을 때 쓰는 최소 기본값 --------------------------------
DEFAULT_LEAGUES: dict[str, dict] = {
    "epl": {
        "ko": "프리미어리그", "aliases": ["프리미어", "EPL", "잉글랜드"],
        "pinnacle_url": "https://www.pinnacle.com/en/soccer/england-premier-league/matchups/#all",
        "pinnacle_name": "England - Premier League",
        "country": "England",
        "fotmob_name": "Premier League",
        "fotmob_id": 47,
        "whoscored": "/Regions/252/Tournaments/2/England-Premier-League",
    },
    "laliga": {
        "ko": "라리가", "aliases": ["라리가", "프리메라", "스페인"],
        "pinnacle_url": "https://www.pinnacle.com/en/soccer/spain-la-liga/matchups/#all",
        "pinnacle_name": "Spain - La Liga",
        "country": "Spain",
        "fotmob_name": "LaLiga",
        "whoscored": "/Regions/206/Tournaments/4/Spain-LaLiga",
    },
    "bundesliga": {
        "ko": "분데스리가", "aliases": ["분데스", "독일"],
        "pinnacle_url": "https://www.pinnacle.com/en/soccer/germany-bundesliga/matchups/#all",
        "pinnacle_name": "Germany - Bundesliga",
        "country": "Germany",
        "fotmob_name": "Bundesliga",
        "whoscored": "/Regions/81/Tournaments/3/Germany-Bundesliga",
    },
    "seriea": {
        "ko": "세리에A", "aliases": ["세리에", "이탈리아"],
        "pinnacle_url": "https://www.pinnacle.com/en/soccer/italy-serie-a/matchups/#all",
        "pinnacle_name": "Italy - Serie A",
        "country": "Italy",
        "fotmob_name": "Serie A",
        "fotmob_id": 55,
        "whoscored": "/Regions/108/Tournaments/5/Italy-Serie-A",
    },
    "ligue1": {
        "ko": "리그앙", "aliases": ["리그앙", "리그 1", "프랑스"],
        "pinnacle_url": "https://www.pinnacle.com/en/soccer/france-ligue-1/matchups/#all",
        "pinnacle_name": "France - Ligue 1",
        "country": "France",
        "fotmob_name": "Ligue 1",
        "whoscored": "/Regions/74/Tournaments/22/France-Ligue-1",
    },
    "kleague1": {
        "ko": "K리그1", "aliases": ["K리그1", "K리그 1", "케이리그1"],
        "pinnacle_url": "https://www.pinnacle.com/en/soccer/korea-republic-k-league-1/matchups/#all",
        "pinnacle_name": "Korea Republic - K League 1",
        "country": "South Korea",
        "fotmob_name": "K League 1",
        "fotmob_id": 9080,
        "whoscored": "/Regions/260/Tournaments/387/South-Korea-K-League-1",
        "whoscored_slug": ["south-korea", "k-league-1"],
    },
    "kleague2": {
        "ko": "K리그2", "aliases": ["K리그2", "K리그 2", "케이리그2"],
        "pinnacle_url": "https://www.pinnacle.com/en/soccer/korea-republic-k-league-2/matchups/#all",
        "pinnacle_name": "Korea Republic - K League 2",
        "country": "South Korea",
        "fotmob_name": "K League 2",
        "fotmob_id": 9116,
        "whoscored": "/Regions/260/Tournaments/418/South-Korea-K-League-2",
        "whoscored_slug": ["south-korea", "k-league-2"],
    },
    "jleague": {
        "ko": "J리그", "aliases": ["J리그", "제이리그", "일본"],
        "pinnacle_url": "https://www.pinnacle.com/en/soccer/japan-j-league/matchups/#all",
        "pinnacle_name": "Japan - J League",
        "country": "Japan",
        "fotmob_name": "J1 League",
        "whoscored": "/Regions/110/Tournaments/150/Japan-J-League",
        "whoscored_slug": ["japan", "j-league"],
    },
}

DEFAULT_RADAR_METRICS = [
    {"key": "big_chances_pg", "label": "결정적 기회", "invert": False},
    {"key": "shots_on_target_pg", "label": "유효슈팅", "invert": False},
    {"key": "goals_for_pg", "label": "경기당 득점", "invert": False},
    {"key": "xga_pg", "label": "피xG", "invert": True},
    {"key": "possession", "label": "점유율", "invert": False},
    {"key": "touches_opp_box_pg", "label": "상대 박스 터치", "invert": False},
    {"key": "home_points_pg", "label": "홈 승점", "invert": False},
    {"key": "away_points_pg", "label": "원정 승점", "invert": False},
]

DEFAULT_COMPARE_METRICS = [
    {"key": "points_pg", "label": "경기당 승점", "fmt": "{:.2f}"},
    {"key": "goals_for_pg", "label": "경기당 득점", "fmt": "{:.2f}"},
    {"key": "goals_against_pg", "label": "경기당 실점", "fmt": "{:.2f}"},
    {"key": "xg_pg", "label": "경기당 xG", "fmt": "{:.2f}"},
    {"key": "xga_pg", "label": "경기당 피xG", "fmt": "{:.2f}"},
    {"key": "finishing_delta", "label": "결정력(득점−xG)", "fmt": "{:+.1f}"},
    {"key": "possession", "label": "점유율(%)", "fmt": "{:.1f}"},
    {"key": "shots_on_target_pg", "label": "유효슈팅", "fmt": "{:.1f}"},
    {"key": "big_chances_pg", "label": "결정적 기회", "fmt": "{:.1f}"},
    {"key": "rating", "label": "평점", "fmt": "{:.2f}"},
    {"key": "set_piece_goals_pg", "label": "세트피스 득점", "fmt": "{:.2f}"},
    {"key": "set_piece_goals_conceded_pg", "label": "세트피스 실점", "fmt": "{:.2f}"},
    {"key": "yellow_cards_pg", "label": "경고", "fmt": "{:.2f}"},
    {"key": "accurate_crosses_pg", "label": "정확한 크로스", "fmt": "{:.1f}"},
    {"key": "accurate_long_balls_pg", "label": "정확한 롱볼", "fmt": "{:.1f}"},
]

# 최근 N경기 표본(경기 상세)에서만 나오는 지표. 시즌 지표와 표본이 다르므로
# compare_metrics 와 섞지 않고 리포트에서도 블록을 따로 둔다.
DEFAULT_RECENT_METRICS = [
    {"key": "npxg_recent_pg", "label": "npxG(PK 제외)", "fmt": "{:.2f}"},
    {"key": "npxga_recent_pg", "label": "피npxG", "fmt": "{:.2f}"},
    {"key": "xgot_recent_pg", "label": "xGOT", "fmt": "{:.2f}"},
    {"key": "xgot_against_recent_pg", "label": "피xGOT", "fmt": "{:.2f}"},
    {"key": "xgot_delta_recent", "label": "xGOT−npxG(합계)", "fmt": "{:+.2f}"},
    {"key": "xg_open_play_recent_pg", "label": "오픈플레이 xG", "fmt": "{:.2f}"},
    {"key": "xg_set_play_recent_pg", "label": "세트피스 xG", "fmt": "{:.2f}"},
    {"key": "shots_recent_pg", "label": "슈팅", "fmt": "{:.1f}"},
    {"key": "shots_against_recent_pg", "label": "피슈팅", "fmt": "{:.1f}"},
    {"key": "shots_on_target_recent_pg", "label": "유효슈팅", "fmt": "{:.1f}"},
    {"key": "shots_on_target_against_recent_pg", "label": "피유효슈팅",
     "fmt": "{:.1f}"},
    {"key": "inside_box_shot_share", "label": "박스 안 슈팅 비율(%)",
     "fmt": "{:.0f}"},
]


def _load_dotenv(path: Path) -> None:
    """python-dotenv 가 있으면 사용, 없으면 간단 파서로 .env 를 환경변수에 주입."""
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(path, override=False)
        return
    except Exception:
        pass
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def load_yaml(path: Path) -> dict:
    """YAML 로드. PyYAML 이 없거나 파일이 깨져도 빈 dict 를 돌려준다.

    **빈 dict 를 돌려주더라도 왜 비었는지는 반드시 남긴다.** 예전에는 네 가지
    실패(파일 없음·PyYAML 없음·인코딩·파싱)를 전부 조용히 삼켰다. 그러면
    `data/teams.yaml` 이 안 읽혀도 아무도 말하지 않고, 결과는 저 아래에서
    '팀명 매칭 실패' 28줄로만 나타나 원인을 찾을 수 없다 (§1-6).

    파일이 없는 것은 정상일 수 있어(학습 별칭·승강 반영분) DEBUG 로 남기고,
    **깨진 파일은 언제나 WARNING** 이다 — 그건 정상인 적이 없다.
    """
    if not path.exists():
        log.debug("YAML 없음: %s", path)
        return {}
    try:
        import yaml  # type: ignore
    except Exception:
        log.warning("PyYAML 이 없어 %s 를 읽지 못했습니다 "
                    "(pip install -r requirements-toto.txt)", path.name)
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        log.warning("%s 를 UTF-8 로 읽지 못했습니다 — 파일 인코딩을 확인하세요: %s",
                    path, exc)
        return {}
    except OSError as exc:
        log.warning("%s 를 열지 못했습니다: %s", path, exc)
        return {}
    try:
        return yaml.safe_load(text) or {}
    except Exception as exc:                            # noqa: BLE001
        log.warning("%s 를 파싱하지 못했습니다: %s", path, exc)
        return {}


@dataclass
class Settings:
    betman: dict = field(default_factory=dict)
    pinnacle: dict = field(default_factory=dict)
    whoscored: dict = field(default_factory=dict)
    fotmob: dict = field(default_factory=dict)
    leagues: dict = field(default_factory=lambda: dict(DEFAULT_LEAGUES))
    radar_metrics: list = field(default_factory=lambda: list(DEFAULT_RADAR_METRICS))
    compare_metrics: list = field(default_factory=lambda: list(DEFAULT_COMPARE_METRICS))
    recent_metrics: list = field(default_factory=lambda: list(DEFAULT_RECENT_METRICS))
    # 시간축 분석(Phase 2-A) 설정: periods · trend_thresholds.
    # 비어 있으면 toto/analysis.py 의 기본값을 쓴다.
    analysis: dict = field(default_factory=dict)
    # 패널(Phase 3-B) 설정: model · max_tokens · timeout_sec.
    # **API 키는 여기 담지 않는다** — 설정 객체는 로그·디버그에 통째로 찍히기
    # 쉬운데 키가 섞이면 안 된다. `llm.py` 가 호출 시점에 환경변수에서 읽는다
    # (`_load_dotenv` 가 이미 `.env` 를 `os.environ` 으로 밀어 넣는다).
    panel: dict = field(default_factory=dict)
    output: dict = field(default_factory=dict)

    root: Path = ROOT

    # ---- 편의 접근자 ----
    def league_of(self, text: str) -> str | None:
        """베트맨 리그 표기 문자열에서 내부 리그 키를 찾는다."""
        if not text:
            return None
        squished = text.replace(" ", "")
        for key, cfg in self.leagues.items():
            candidates = [cfg.get("ko", ""), key, *(cfg.get("aliases") or [])]
            for cand in candidates:
                if cand and cand.replace(" ", "") in squished:
                    return key
        return None

    def league_ko(self, key: str) -> str:
        return (self.leagues.get(key) or {}).get("ko", key)

    @property
    def ws_delay(self) -> float:
        return float(self.whoscored.get("delay_sec", 4.0))

    @property
    def output_dir(self) -> Path:
        return self.root / self.output.get("dir", "reports")


def load_settings(config_path: Path | None = None, env_path: Path | None = None) -> Settings:
    config_path = config_path or (ROOT / "config_toto.yaml")
    _load_dotenv(env_path or (ROOT / ".env"))

    cfg = load_yaml(config_path)
    s = Settings()
    s.betman = cfg.get("betman") or {
        "game_id": "G011",
        "slip_url": ("https://www.betman.co.kr/main/mainPage/gamebuy/gameSlip.do"
                     "?frameType=typeA&gmId={game_id}&gmTs={round}"),
        "buy_url": "https://www.betman.co.kr/main/mainPage/gamebuy/gameBuyList.do",
        "expected_matches": 14,
    }
    s.pinnacle = cfg.get("pinnacle") or {
        "api_base": "https://guest.api.arcadia.pinnacle.com/0.1",
        "api_key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
        "soccer_sport_id": 29,
        "timeout_sec": 20,
        "fallback_to_browser": True,
    }
    s.whoscored = cfg.get("whoscored") or {
        "base": "https://www.whoscored.com",
        "headless": True,
        "delay_sec": 4.0,
        "timeout_ms": 45000,
        "persistent_profile": True,
        "recent_form_count": 6,
        "h2h_count": 10,
    }
    s.fotmob = cfg.get("fotmob") or {
        "base": "https://www.fotmob.com",
        "headless": True,
        "delay_sec": 1.5,
        "timeout_ms": 45000,
        "persistent_profile": True,
        "match_detail_matches": 6,
        "shot_recent_windows": [3, 5, 6, 10],
    }
    if cfg.get("leagues"):
        s.leagues = cfg["leagues"]
    if cfg.get("radar_metrics"):
        s.radar_metrics = cfg["radar_metrics"]
    if cfg.get("compare_metrics"):
        s.compare_metrics = cfg["compare_metrics"]
    if cfg.get("recent_metrics"):
        s.recent_metrics = cfg["recent_metrics"]
    s.analysis = cfg.get("analysis") or {}
    s.panel = cfg.get("panel") or {}
    s.output = cfg.get("output") or {
        "dir": "reports", "filename": "toto_{round}.html",
        "copy_to": [], "copy_to_exclude": ["OneDrive"],
        "cloud_folder": "축구토토",
        "latest_name": "최신리포트.html",
    }
    return s
