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
import re
import time
from datetime import datetime, timedelta, timezone

from ..models import Odds
from ..normalize import TeamResolver
from ..settings import Settings


def _norm_league(text: str) -> str:
    """리그명 비교용 정규화. 공백·하이픈·구두점을 지우고 소문자로.

    비교는 이 값의 **완전일치**로만 한다. 부분일치를 쓰면
    "England - Premier League" 가 "England - Premier League 2 U21" 에
    걸린다(실측 확인).
    """
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())

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

        cfg = self.settings.leagues.get(league_key) or {}
        want = cfg.get("pinnacle_name", "")
        if not want:
            return None

        payload = self._all_leagues()
        if payload is None:
            return None

        # 부분일치는 쓰지 않는다. 피나클 리그명은 국가를 포함하는데
        # ("England - Premier League"), 정답 이름이 다른 리그명의 **접두사**라
        # 부분일치가 성립해 버린다 — 실측에서 EPL 요청이
        # "England - Premier League 2 U21" 에 걸려 배당이 통째로 어긋났다.
        # 완전일치 → 설정 별칭 → 실패 순으로만 간다.
        targets = {_norm_league(w)
                   for w in [want, *(cfg.get("pinnacle_aliases") or [])] if w}

        for item in payload or []:
            name = str(item.get("name", ""))
            full = f"{item.get('sport', {}).get('name', '')} {name}"
            if _norm_league(name) in targets or _norm_league(full) in targets:
                self._league_ids[league_key] = int(item["id"])
                log.info("피나클 리그 매칭: %s → id=%s (%s)",
                         league_key, item["id"], name)
                return self._league_ids[league_key]

        # 실패 — 이름이 비슷한 후보를 남겨 둔다. 사람이 보고
        # pinnacle_aliases 에 정확한 이름을 넣으면 다음 실행부터 해결된다.
        near = [str(i.get("name", "")) for i in payload or []
                if any(t in _norm_league(i.get("name", "")) for t in targets)]
        if near:
            log.warning("피나클에서 리그명이 정확히 일치하지 않습니다: %s (%s). "
                        "비슷한 후보 %s — 맞는 이름을 config_toto.yaml 의 "
                        "leagues.%s.pinnacle_aliases 에 넣어 주세요.",
                        league_key, want, near[:5], league_key)
        else:
            log.warning("피나클에서 리그를 찾지 못함: %s (%s)", league_key, want)
        return None

    # ---- 경기 + 마켓 ----
    def league_payload(self, league_key: str) -> tuple[list, list]:
        """(matchups, markets) 를 캐시와 함께 가져온다."""
        lid = self.league_id(league_key)
        if lid is None:
            return [], []
        return self.payload_by_id(lid)

    def payload_by_id(self, lid) -> tuple[list, list]:
        """피나클 리그 ID 로 (matchups, markets) 를 가져온다."""
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
            log.error("피나클 리그 %s 수집 실패: %s", lid, exc)
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
        # 같은 나라의 다른 대회까지 훑을 때는 K3·아마추어 팀이 잔뜩 섞여
        # 들어온다. 그건 못 찾는 게 정상이라 경고로 남기지 않는다.
        rh = resolver.resolve(h, learn=False, quiet=True)
        ra = resolver.resolve(a, learn=False, quiet=True)
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

    # 1차: 각 경기의 소속 리그에서 찾는다
    for league_key, group in by_league.items():
        matchups, markets = client.league_payload(league_key)
        if not matchups:
            continue
        for match in group:
            if _apply_odds(match, matchups, markets, resolver, now):
                filled += 1

    # 2차: 못 찾은 경기는 같은 나라의 다른 대회에서 찾는다.
    # 승무패에는 컵대회(르방컵·코리아컵 등)가 섞여 나오는데, 그런 경기는
    # 리그 피드에 없다. 나라 단위로 범위를 넓혀 한 번 더 훑는다.
    missing = [m for m in matches
               if not m.odds.available and m.home.canonical and m.away.canonical]
    if missing:
        log.info("리그 피드에서 못 찾은 %d경기 — 같은 나라의 다른 대회를 탐색합니다.",
                 len(missing))
        filled += _search_country_wide(client, missing, settings, resolver, now)

    for match in matches:
        if not match.odds.available:
            log.warning("피나클에서 배당을 찾지 못함: %s", match.title)

    if filled:
        return f"ok ({filled}/{len(matches)}경기)"
    if client.ok:
        return "연결됨 · 경기 매칭 실패"
    return "실패"


def _apply_odds(match, matchups: list, markets: list, resolver: TeamResolver,
                now: str) -> bool:
    """matchups 에서 경기를 찾아 배당을 채운다. 채웠으면 True."""
    if not (match.home.canonical and match.away.canonical):
        return False
    mu = _find_matchup(matchups, resolver, match.home.canonical, match.away.canonical)
    if not mu:
        return False
    rows = _markets_for(markets, mu.get("id"))
    ml, sp, tot = _moneyline(rows), _spread(rows), _total(rows)
    if not ml or ml.get("home") is None or ml.get("away") is None:
        return False
    match.odds = Odds(
        home=ml.get("home"), draw=ml.get("draw"), away=ml.get("away"),
        ah_line=sp.get("line"), ah_home=sp.get("home"), ah_away=sp.get("away"),
        ou_line=tot.get("line"), ou_over=tot.get("over"), ou_under=tot.get("under"),
        fetched_at=now, source="arcadia-api",
    )
    # 베트맨에서 킥오프를 못 읽었으면 피나클 startTime(UTC)으로 채운다
    if not match.kickoff_kst and mu.get("startTime"):
        match.kickoff_kst = _to_kst(str(mu["startTime"]))
    return True


def _country_of(settings: Settings, league_key: str) -> str:
    """설정된 리그명에서 나라 부분을 뽑는다. 'Japan - J League' → 'Japan'."""
    name = (settings.leagues.get(league_key) or {}).get("pinnacle_name", "")
    return name.split("-")[0].strip()


def _search_country_wide(client: "PinnacleClient", missing: list,
                         settings: Settings, resolver: TeamResolver,
                         now: str, max_leagues: int = 15) -> int:
    """같은 나라에 속한 모든 대회를 훑어 남은 경기의 배당을 찾는다."""
    payload = client._all_leagues()
    if not payload:
        return 0

    by_country: dict[str, list] = {}
    for match in missing:
        country = _country_of(settings, match.league)
        if country:
            by_country.setdefault(country, []).append(match)

    filled = 0
    for country, group in by_country.items():
        prefix = country.lower()
        candidates = []
        for item in payload:
            full = f"{(item.get('sport') or {}).get('name', '')} {item.get('name', '')}"
            if full.strip().lower().startswith(prefix) or \
                    str(item.get("name", "")).lower().startswith(prefix):
                candidates.append(item)
        if not candidates:
            continue
        log.info("%s: 대회 %d개 탐색", country, min(len(candidates), max_leagues))

        for item in candidates[:max_leagues]:
            remaining = [m for m in group if not m.odds.available]
            if not remaining:
                break
            lid = item.get("id")
            matchups, markets = client.payload_by_id(lid)
            if not matchups:
                continue
            for match in remaining:
                if _apply_odds(match, matchups, markets, resolver, now):
                    log.info("  %s → %s 에서 발견", match.title, item.get("name"))
                    filled += 1
    return filled
