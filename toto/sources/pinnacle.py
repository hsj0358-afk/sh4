"""피나클 배당률 수집.

사용자가 지정한 /matchups/#all 페이지는 SPA 라 HTML 만 받아서는 배당이 안 나온다.
그 페이지가 실제로 읽는 공개 guest API(Arcadia)를 직접 호출하는 편이 훨씬 안정적이다.

  GET {api_base}/sports/29/leagues?all=false        → 리그 ID
  GET {api_base}/leagues/{id}/matchups              → 경기(참가팀, 시작시각)
  GET {api_base}/leagues/{id}/markets/straight      → 배당(머니라인/핸디캡/O·U)

헤더에 웹앱 내장 공개 키(x-api-key)를 실어야 응답한다.
가격은 **아메리칸 배당**이므로 decimal 로 변환해서 돌려준다.

guest API 가 막히면 Playwright 로 리그 페이지를 열어 XHR 응답을 가로채는
폴백을 쓴다(config_toto.yaml 의 pinnacle.fallback_to_browser).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from ..models import Odds
from ..normalize import TeamResolver
from ..settings import Settings

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

KST = timezone(timedelta(hours=9))


def american_to_decimal(price: float | int | None) -> float | None:
    """아메리칸 배당 → 소수 배당.

    +150 → 2.50 , -200 → 1.50
    """
    if price is None:
        return None
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    if p > 0:
        return round(1.0 + p / 100.0, 4)
    return round(1.0 + 100.0 / abs(p), 4)


def decimal_to_american(dec: float | None) -> float | None:
    """소수 배당 → 아메리칸 배당 (왕복 검증용)."""
    if not dec or dec <= 1.0:
        return None
    if dec >= 2.0:
        return round((dec - 1.0) * 100.0, 2)
    return round(-100.0 / (dec - 1.0), 2)


# --------------------------------------------------------------------------
# guest API
# --------------------------------------------------------------------------
class PinnacleClient:
    def __init__(self, settings: Settings, cache=None) -> None:
        self.cfg = settings.pinnacle
        self.settings = settings
        self.cache = cache
        self.base = self.cfg.get("api_base", "https://guest.api.arcadia.pinnacle.com/0.1")
        self.timeout = int(self.cfg.get("timeout_sec", 20))
        self._league_ids: dict[str, int] = {}
        self._leagues_payload: list | None = None
        self._leagues_failed = False      # 실패 시 리그마다 재시도하지 않는다
        self.ok = False

    def _headers(self) -> dict:
        return {
            "x-api-key": self.cfg.get("api_key", ""),
            "accept": "application/json",
            "user-agent": UA,
            "referer": "https://www.pinnacle.com/",
        }

    def _get(self, path: str):
        import requests
        url = f"{self.base}{path}"
        resp = requests.get(url, headers=self._headers(), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ---- 리그 ----
    def _all_leagues(self) -> list | None:
        """축구 리그 목록. 한 번만 조회하고 결과(실패 포함)를 재사용한다."""
        if self._leagues_payload is not None:
            return self._leagues_payload
        if self._leagues_failed:
            return None

        payload = self.cache.get("pinnacle", "leagues") if self.cache else None
        if payload is None:
            try:
                sport = int(self.cfg.get("soccer_sport_id", 29))
                payload = self._get(f"/sports/{sport}/leagues?all=false")
                if self.cache:
                    self.cache.set("pinnacle", "leagues", payload)
            except Exception as exc:
                # 리그마다 같은 오류를 반복 출력하지 않도록 한 번만 남긴다
                log.error("피나클 리그 목록 조회 실패 (%s): %s",
                          type(exc).__name__, str(exc).split("(Caused by")[0].strip())
                self._leagues_failed = True
                return None
        self._leagues_payload = payload
        return payload

    def league_id(self, league_key: str) -> int | None:
        """내부 리그 키 → 피나클 리그 ID."""
        if league_key in self._league_ids:
            return self._league_ids[league_key]

        want = (self.settings.leagues.get(league_key) or {}).get("pinnacle_name", "")
        if not want:
            return None

        payload = self._all_leagues()
        if payload is None:
            return None

        target = want.replace(" ", "").replace("-", "").lower()
        for item in payload or []:
            name = str(item.get("name", ""))
            full = f"{item.get('sport', {}).get('name', '')}{name}"
            for cand in (name, full):
                if cand.replace(" ", "").replace("-", "").lower().endswith(target) \
                        or target in cand.replace(" ", "").replace("-", "").lower():
                    self._league_ids[league_key] = int(item["id"])
                    log.info("피나클 리그 매칭: %s → id=%s (%s)", league_key, item["id"], name)
                    return self._league_ids[league_key]
        log.warning("피나클에서 리그를 찾지 못함: %s (%s)", league_key, want)
        return None

    # ---- 경기 + 마켓 ----
    def league_payload(self, league_key: str) -> tuple[list, list]:
        """(matchups, markets) 를 캐시와 함께 가져온다."""
        lid = self.league_id(league_key)
        if lid is None:
            return [], []

        matchups = self.cache.get("pinnacle", f"matchups_{lid}") if self.cache else None
        markets = self.cache.get("pinnacle", f"markets_{lid}") if self.cache else None

        try:
            if matchups is None:
                matchups = self._get(f"/leagues/{lid}/matchups")
                if self.cache:
                    self.cache.set("pinnacle", f"matchups_{lid}", matchups)
                time.sleep(0.4)
            if markets is None:
                markets = self._get(f"/leagues/{lid}/markets/straight")
                if self.cache:
                    self.cache.set("pinnacle", f"markets_{lid}", markets)
            self.ok = True
        except Exception as exc:
            log.error("피나클 %s 수집 실패: %s", league_key, exc)
            return matchups or [], markets or []
        return matchups or [], markets or []


# --------------------------------------------------------------------------
# 파싱
# --------------------------------------------------------------------------
def _to_kst(iso_utc: str) -> str:
    """피나클의 UTC ISO 시각 → 한국시간 표기."""
    try:
        text = iso_utc.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _participants(matchup: dict) -> tuple[str, str]:
    """matchup 에서 (홈팀, 원정팀) 이름을 뽑는다."""
    home = away = ""
    for part in matchup.get("participants") or []:
        align = (part.get("alignment") or "").lower()
        name = str(part.get("name", ""))
        if align == "home":
            home = name
        elif align == "away":
            away = name
    if not home or not away:
        names = [str(p.get("name", "")) for p in (matchup.get("participants") or [])]
        if len(names) >= 2:
            home, away = names[0], names[1]
    return home, away


def _find_matchup(matchups: list, resolver: TeamResolver,
                  home_canon: str, away_canon: str) -> dict | None:
    """정규명 기준으로 해당 경기를 찾는다."""
    for mu in matchups or []:
        # 부모 경기만 사용 (파생 마켓/코너 등 제외)
        if mu.get("parentId"):
            continue
        if (mu.get("type") or "matchup") != "matchup":
            continue
        h, a = _participants(mu)
        if not h or not a:
            continue
        rh, ra = resolver.resolve(h, learn=False), resolver.resolve(a, learn=False)
        if rh == home_canon and ra == away_canon:
            return mu
    return None


def _markets_for(markets: list, matchup_id) -> list:
    return [m for m in markets or [] if str(m.get("matchupId")) == str(matchup_id)]


def _moneyline(rows: list) -> dict:
    for m in rows:
        if m.get("type") == "moneyline" and m.get("period") == 0:
            out = {}
            for price in m.get("prices") or []:
                desig = (price.get("designation") or "").lower()
                out[desig] = american_to_decimal(price.get("price"))
            return out
    return {}


def _spread(rows: list) -> dict:
    """가장 균형 잡힌(0에 가까운) 아시안 핸디캡 라인 하나."""
    best, best_gap = None, 1e9
    for m in rows:
        if m.get("type") != "spread" or m.get("period") != 0:
            continue
        prices = m.get("prices") or []
        if len(prices) < 2:
            continue
        line = prices[0].get("points")
        if line is None:
            continue
        gap = abs(float(line))
        if gap < best_gap:
            out = {"line": float(line)}
            for price in prices:
                desig = (price.get("designation") or "").lower()
                out[desig] = american_to_decimal(price.get("price"))
            best, best_gap = out, gap
    return best or {}


def _total(rows: list, prefer: float = 2.5) -> dict:
    best, best_gap = None, 1e9
    for m in rows:
        if m.get("type") != "total" or m.get("period") != 0:
            continue
        prices = m.get("prices") or []
        if len(prices) < 2:
            continue
        line = prices[0].get("points")
        if line is None:
            continue
        gap = abs(float(line) - prefer)
        if gap < best_gap:
            out = {"line": float(line)}
            for price in prices:
                desig = (price.get("designation") or "").lower()
                out[desig] = american_to_decimal(price.get("price"))
            best, best_gap = out, gap
    return best or {}


def fetch_odds(matches, settings: Settings, resolver: TeamResolver,
               cache=None) -> str:
    """경기 목록에 배당률을 채워 넣는다. 반환값은 소스 상태 문자열."""
    client = PinnacleClient(settings, cache=cache)
    by_league: dict[str, list] = {}
    for m in matches:
        if m.league:
            by_league.setdefault(m.league, []).append(m)

    filled = 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for league_key, group in by_league.items():
        matchups, markets = client.league_payload(league_key)
        if not matchups:
            continue
        for match in group:
            if not (match.home.canonical and match.away.canonical):
                continue
            mu = _find_matchup(matchups, resolver,
                               match.home.canonical, match.away.canonical)
            if not mu:
                log.warning("피나클에서 경기를 찾지 못함: %s", match.title)
                continue
            rows = _markets_for(markets, mu.get("id"))
            ml, sp, tot = _moneyline(rows), _spread(rows), _total(rows)
            if not ml:
                log.warning("머니라인 없음: %s", match.title)
                continue
            match.odds = Odds(
                home=ml.get("home"), draw=ml.get("draw"), away=ml.get("away"),
                ah_line=sp.get("line"), ah_home=sp.get("home"), ah_away=sp.get("away"),
                ou_line=tot.get("line"), ou_over=tot.get("over"), ou_under=tot.get("under"),
                fetched_at=now, source="arcadia-api",
            )
            # 베트맨에서 킥오프를 못 읽었으면 피나클 startTime(UTC)으로 채운다
            if not match.kickoff_kst and mu.get("startTime"):
                match.kickoff_kst = _to_kst(str(mu["startTime"]))
            filled += 1

    if filled:
        return f"ok ({filled}/{len(matches)}경기)"
    if client.ok:
        return "연결됨 · 경기 매칭 실패"
    return "실패"
