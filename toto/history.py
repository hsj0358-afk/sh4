"""과거 경기 기록 — football-data.co.uk 의 시즌 CSV (예측 모델 경기장 · §1-67).

예측 모델을 겨루려면 **여러 시즌**의 결과가 있어야 한다. 이 프로젝트의 수집
소스(FotMob 시즌 색인)는 지금 시즌만 담으므로(§1-1-4), 모델 훈련·검증용
과거 기록은 football-data.co.uk 의 공개 CSV 를 쓴다. 2000/01 시즌부터의
최종 스코어·슈팅·유효슈팅과 2012/13 시즌부터의 피나클 배당이 들어 있다.

    https://football-data.co.uk/mmz4281/{시즌}/{디비전}.csv   (5대 리그)
    https://football-data.co.uk/new/JPN.csv                   (J리그 · 한 파일)

## 이것이 무엇이 아닌지

- **회차 수집 경로가 아니다.** 베트맨·FotMob·피나클·후스코어드의 순서와
  역할(§1-1)을 바꾸지 않는다. 이 모듈은 모델 경기장(`toto/arena.py`)과
  모델 상태 갱신(`toto/champion.py`)만 부른다.
- **팀명을 해석하지 않는다.** 소스가 적은 이름 그대로 둔다 (`Man City`).
  리포트의 정규명으로 잇는 것은 `champion.py` 의 일이다.
- **없는 값을 0 으로 채우지 않는다.** 슈팅·배당이 없는 시즌은 `None` 이다.

## 캐시

`cache/history/footballdata/<시즌>/<디비전>.csv` (`.gitignore` 의 `cache/`).
지난 시즌 파일은 바뀌지 않으므로 한 번 받으면 다시 받지 않는다. **진행 중인
시즌만** `refresh=True` 일 때 다시 받는다 — 소스가 주 2회 갱신한다.
"""
from __future__ import annotations

import csv
import io
import logging
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .settings import ROOT

log = logging.getLogger(__name__)

BASE_URL = "https://football-data.co.uk"
CACHE_DIR = ROOT / "cache" / "history" / "footballdata"

# 리그 키(config_toto.yaml) → football-data 디비전 코드. 한국 리그는 소스에 없다.
DIVISIONS = {
    "epl": "E0",
    "laliga": "SP1",
    "bundesliga": "D1",
    "seriea": "I1",
    "ligue1": "F1",
}
# 한 파일에 전 시즌이 들어 있는 '추가 리그' 형식.
EXTRA = {
    "jleague": "JPN",
}
LEAGUES = tuple(DIVISIONS) + tuple(EXTRA)

FIRST_SEASON = 2000          # 2000/01 — 그 이전에는 슈팅 칸이 없다


def season_code(start_year: int) -> str:
    """2025 → '2526'."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def current_season_start(today: date | None = None) -> int:
    """유럽 시즌의 시작 연도 — 7월부터 새 시즌으로 본다."""
    d = today or date.today()
    return d.year if d.month >= 7 else d.year - 1


def season_codes(first: int = FIRST_SEASON, last: int | None = None) -> list:
    last = current_season_start() if last is None else last
    return [season_code(y) for y in range(first, last + 1)]


@dataclass(frozen=True)
class HistMatch:
    league: str
    season: str                  # '2526' (유럽) · '2026' (J리그 · 달력 연도)
    date: date
    time: str                    # 'HH:MM' 또는 ''
    home: str
    away: str
    hg: int
    ag: int
    hs: int | None = None        # 슈팅
    as_: int | None = None
    hst: int | None = None       # 유효슈팅
    ast: int | None = None
    hxg: float | None = None     # 2026/27 부터 일부
    axg: float | None = None
    odds_open: tuple | None = None    # 피나클 (집계 시점 · 킥오프 전)
    odds_close: tuple | None = None   # 피나클 마감
    odds_avg: tuple | None = None     # 시장 평균

    @property
    def result(self) -> str:
        return "H" if self.hg > self.ag else "D" if self.hg == self.ag else "A"

    @property
    def key(self) -> tuple:
        return (self.date, self.league, self.home, self.away)


# --------------------------------------------------------------------------
# 받기
# --------------------------------------------------------------------------
def _url(league: str, season: str) -> str:
    if league in EXTRA:
        return f"{BASE_URL}/new/{EXTRA[league]}.csv"
    return f"{BASE_URL}/mmz4281/{season}/{DIVISIONS[league]}.csv"


def _path(league: str, season: str, cache_dir: Path) -> Path:
    if league in EXTRA:
        return cache_dir / "new" / f"{EXTRA[league]}.csv"
    return cache_dir / season / f"{DIVISIONS[league]}.csv"


def _download(url: str, path: Path, timeout: float = 30.0) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "toto-arena/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if not data.strip():
        raise ValueError("빈 응답")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def fetch(leagues=LEAGUES, seasons=None, cache_dir: Path = CACHE_DIR,
          refresh: bool = False) -> dict:
    """빠진 파일을 받는다. {'ok': n, 'cached': n, 'failed': [(url, 사유)]}.

    `refresh` 면 진행 중인 시즌(목록의 마지막)과 '추가 리그' 파일을 다시 받는다.
    실패해도 멈추지 않는다 — 받은 것만으로 돈다 (§1-6).
    """
    seasons = list(seasons or season_codes())
    out = {"ok": 0, "cached": 0, "failed": []}
    latest = seasons[-1] if seasons else ""
    done_extra = set()
    for league in leagues:
        for season in seasons:
            if league in EXTRA:
                if league in done_extra:
                    continue
                done_extra.add(league)
            path = _path(league, season, cache_dir)
            stale = refresh and (league in EXTRA or season == latest)
            if path.is_file() and path.stat().st_size > 0 and not stale:
                out["cached"] += 1
                continue
            url = _url(league, season)
            try:
                _download(url, path)
                out["ok"] += 1
            except Exception as e:                      # noqa: BLE001
                out["failed"].append((url, f"{type(e).__name__}: {e}"))
    return out


# --------------------------------------------------------------------------
# 읽기
# --------------------------------------------------------------------------
def _text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _date(raw: str) -> date | None:
    raw = (raw or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _int(row, key) -> int | None:
    v = (row.get(key) or "").strip()
    if not v:
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def _float(row, key) -> float | None:
    v = (row.get(key) or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _odds(row, *names) -> tuple | None:
    """세 칸 이름 묶음을 차례로 보고 처음으로 셋 다 1 보다 큰 묶음을 쓴다."""
    for h, d, a in names:
        vals = (_float(row, h), _float(row, d), _float(row, a))
        if all(v is not None and v > 1.0 for v in vals):
            return vals
    return None


def parse(text: str, league: str, season: str) -> list:
    """CSV 본문 → [HistMatch]. 스코어가 없는 줄은 담지 않는다."""
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        if league in EXTRA:
            home, away = (row.get("Home") or "").strip(), (row.get("Away") or "").strip()
            hg, ag = _int(row, "HG"), _int(row, "AG")
            szn = (row.get("Season") or "").strip()
        else:
            home = (row.get("HomeTeam") or row.get("HT") or "").strip()
            away = (row.get("AwayTeam") or row.get("AT") or "").strip()
            hg, ag = _int(row, "FTHG"), _int(row, "FTAG")
            szn = season
        d = _date(row.get("Date", ""))
        if not home or not away or hg is None or ag is None or d is None:
            continue
        out.append(HistMatch(
            league=league, season=szn, date=d,
            time=(row.get("Time") or "").strip(),
            home=home, away=away, hg=hg, ag=ag,
            hs=_int(row, "HS"), as_=_int(row, "AS"),
            hst=_int(row, "HST"), ast=_int(row, "AST"),
            hxg=_float(row, "HxG"), axg=_float(row, "AxG"),
            odds_open=_odds(row, ("PSH", "PSD", "PSA")),
            odds_close=_odds(row, ("PSCH", "PSCD", "PSCA")),
            odds_avg=_odds(row, ("AvgH", "AvgD", "AvgA"),
                           ("BbAvH", "BbAvD", "BbAvA"),
                           ("AvgCH", "AvgCD", "AvgCA")),
        ))
    return out


def load(leagues=LEAGUES, seasons=None, cache_dir: Path = CACHE_DIR) -> tuple:
    """(경기 목록, 못 읽은 파일 목록). 날짜 → 리그 → 홈팀 순으로 정렬한다.

    같은 경기(날짜·리그·홈·원정)가 두 번 오면 하나만 남긴다.
    """
    seasons = list(seasons or season_codes())
    first_year = 2000 + int(seasons[0][:2]) if seasons else FIRST_SEASON
    rows, missing, seen = [], [], set()
    done_extra = set()
    for league in leagues:
        for season in seasons:
            if league in EXTRA:
                if league in done_extra:
                    continue
                done_extra.add(league)
            path = _path(league, season, cache_dir)
            if not path.is_file():
                missing.append(str(path))
                continue
            for m in parse(_text(path), league, season):
                if league in EXTRA and m.date.year < first_year:
                    continue
                if m.key in seen:
                    continue
                seen.add(m.key)
                rows.append(m)
    rows.sort(key=lambda m: (m.date, m.league, m.home, m.away))
    return rows, missing
