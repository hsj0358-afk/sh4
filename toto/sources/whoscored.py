"""후스코어드(whoscored.com) 상세 데이터 수집.

후스코어드는 Incapsula 봇 차단이 강해서 requests 로는 거의 통과하지 못한다.
Playwright 로 실제 브라우저를 띄우고, 브라우저 프로필을 유지해 한 번 통과한
쿠키를 재사용하는 방식이 가장 현실적이다.

수집 구조 (페이지 로드를 최소화한다):
  · 리그 페이지 1회      → 그 리그 **모든 팀**의 순위표 + 팀 통계
  · 팀 페이지 1회/팀     → Strengths / Weaknesses / Style of Play, 최근 폼, 결장자
  · 경기 프리뷰 1회/경기 → 상대전적(H2H)

셀렉터는 언제든 바뀔 수 있으므로, 클래스명에 의존하는 대신
**제목 텍스트("Strengths", "Weaknesses", "Style of play")를 찾아 그 뒤의
목록을 읽는 휴리스틱**을 우선한다. 실패하면 원본 HTML 을 cache 에 남긴다.
"""
from __future__ import annotations

import json
import logging
import re
import time
from urllib.parse import urljoin

from ..models import FormEntry, H2H, H2HEntry, TeamProfile, TeamRef, TeamStats
from ..normalize import TeamResolver
from ..settings import Settings

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 자동화 탐지를 줄이는 초기 스크립트
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-GB', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = window.chrome || {runtime: {}};
"""

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
_SCORE_RE = re.compile(r"(\d+)\s*[-:]\s*(\d+)")
_DATE_RE = re.compile(r"(\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}|\d{4}-\d{2}-\d{2})")


def _num(text: str) -> float | None:
    if not text:
        return None
    m = _NUM_RE.search(str(text).replace(",", ""))
    return float(m.group()) if m else None


# --------------------------------------------------------------------------
# 브라우저 세션
# --------------------------------------------------------------------------
class WhoScoredBrowser:
    """Playwright 세션 래퍼 (with 문으로 사용)."""

    def __init__(self, settings: Settings, cache=None) -> None:
        self.cfg = settings.whoscored
        self.base = self.cfg.get("base", "https://www.whoscored.com")
        self.delay = float(self.cfg.get("delay_sec", 4.0))
        self.timeout = int(self.cfg.get("timeout_ms", 45000))
        self.cache = cache
        self._pw = None
        self._ctx = None
        self._browser = None
        self._page = None
        self.available = False
        self._last_load = 0.0

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            log.error("playwright 미설치 — 후스코어드 수집을 건너뜁니다. "
                      "`pip install -r requirements-toto.txt && playwright install chromium`")
            return self

        args = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ]
        headless = bool(self.cfg.get("headless", True))
        try:
            self._pw = sync_playwright().start()
            if self.cfg.get("persistent_profile", True) and self.cache is not None:
                self._ctx = self._pw.chromium.launch_persistent_context(
                    str(self.cache.browser_profile), headless=headless, args=args,
                    user_agent=UA, locale="en-GB",
                    viewport={"width": 1440, "height": 900})
                self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
            else:
                self._browser = self._pw.chromium.launch(headless=headless, args=args)
                self._ctx = self._browser.new_context(
                    user_agent=UA, locale="en-GB",
                    viewport={"width": 1440, "height": 900})
                self._page = self._ctx.new_page()
            self._ctx.add_init_script(STEALTH_JS)
            self.available = True
        except Exception as exc:
            log.error("브라우저 기동 실패: %s", exc)
        return self

    def __exit__(self, *exc) -> None:
        # 컨텍스트 → 브라우저 → playwright 순으로 정리. 하나가 실패해도 나머지는 닫는다.
        for obj, method in ((self._ctx, "close"),
                            (self._browser, "close"),
                            (self._pw, "stop")):
            if obj is None:
                continue
            try:
                getattr(obj, method)()
            except Exception:
                pass

    def get_html(self, url: str, wait_selector: str | None = None) -> str:
        """페이지를 열고 HTML 을 돌려준다. 실패하면 빈 문자열."""
        if not self.available:
            return ""
        # 요청 간격 유지 (차단 방지)
        gap = time.time() - self._last_load
        if gap < self.delay:
            time.sleep(self.delay - gap)
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
            if wait_selector:
                try:
                    self._page.wait_for_selector(wait_selector, timeout=15000)
                except Exception:
                    log.debug("셀렉터 대기 실패(%s) — 그래도 진행: %s", wait_selector, url)
            # 순위표·통계표는 스크롤해야 채워지는 경우가 있다.
            try:
                self._page.evaluate(
                    "window.scrollTo(0, document.body.scrollHeight / 2)")
                self._page.wait_for_timeout(800)
                self._page.evaluate(
                    "window.scrollTo(0, document.body.scrollHeight)")
            except Exception:
                pass
            self._page.wait_for_timeout(2000)
            html = self._page.content()
            self._last_load = time.time()
            if _looks_blocked(html):
                log.warning("봇 차단 화면으로 보입니다: %s "
                            "(headless: false 로 한 번 실행하면 통과 쿠키가 저장됩니다)", url)
                return ""
            return html
        except Exception as exc:
            log.warning("페이지 로드 실패 %s: %s", url, exc)
            self._last_load = time.time()
            return ""

    def abs_url(self, path: str) -> str:
        return urljoin(self.base, path)


def _looks_blocked(html: str) -> bool:
    if not html or len(html) < 800:
        return True
    lowered = html[:4000].lower()
    return any(sig in lowered for sig in
               ("incapsula", "_incap_", "request unsuccessful", "access denied",
                "captcha-delivery", "just a moment"))


# --------------------------------------------------------------------------
# HTML 파싱 유틸
# --------------------------------------------------------------------------
def _soup(html: str):
    from bs4 import BeautifulSoup
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _table_rows(table) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)
    return rows


def _header_index(rows: list[list[str]], *names: str) -> int | None:
    """헤더 행에서 주어진 이름 중 하나와 맞는 컬럼 인덱스를 찾는다."""
    if not rows:
        return None
    header = [h.lower() for h in rows[0]]
    for want in names:
        w = want.lower()
        for i, h in enumerate(header):
            if h == w or h.replace(" ", "") == w.replace(" ", ""):
                return i
    for want in names:                      # 부분 일치로 한 번 더
        w = want.lower()
        for i, h in enumerate(header):
            if w in h:
                return i
    return None


# --------------------------------------------------------------------------
# 리그 페이지 → 팀별 순위표 + 통계
# --------------------------------------------------------------------------
def read_league(browser: WhoScoredBrowser, settings: Settings,
                league_key: str, resolver: TeamResolver,
                cache=None) -> dict[str, dict]:
    """리그 페이지 1회 로드로 그 리그 모든 팀의 지표를 수집한다.

    Returns: {정규명: {"stats": TeamStats, "url": 팀페이지 경로}}
    """
    cached = cache.get("whoscored", f"league_{league_key}") if cache else None
    if cached is not None:
        return _revive_league(cached)

    path = (settings.leagues.get(league_key) or {}).get("whoscored", "")
    if not path:
        log.warning("후스코어드 리그 경로가 설정에 없음: %s", league_key)
        return {}

    url = browser.abs_url(path)
    html = browser.get_html(url, wait_selector="table")
    if not html:
        log.error("리그 페이지 수집 실패: %s", league_key)
        return {}

    # 잘못된 리그 경로면 후스코어드가 홈으로 리다이렉트해 버린다.
    # 제목을 남겨 두면 '차단'인지 '엉뚱한 페이지'인지 바로 구분된다.
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    log.info("[%s] 페이지 제목: %s", league_key,
             re.sub(r"\s+", " ", title.group(1)).strip()[:90] if title else "(없음)")

    soup = _soup(html)
    out: dict[str, dict] = {}

    # 1) 팀 페이지 링크 수집 (/Teams/{id}/Show/... 또는 /Teams/{id})
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/Teams/" not in href:
            continue
        name = a.get_text(" ", strip=True)
        canon = resolver.resolve(name, learn=False) if name else None
        if not canon:
            continue
        entry = out.setdefault(canon, {"stats": TeamStats(), "url": ""})
        if not entry["url"]:
            entry["url"] = href

    # 2) 순위표 (Team / Pl / W / D / L / GF / GA / Pts)
    for table in soup.find_all("table"):
        rows = _table_rows(table)
        if len(rows) < 3:
            continue
        i_team = _header_index(rows, "team", "")
        i_pl = _header_index(rows, "pl", "p", "played", "mp")
        i_pts = _header_index(rows, "pts", "points")
        if i_pl is None or i_pts is None:
            continue
        idx = {
            "w": _header_index(rows, "w", "won"),
            "d": _header_index(rows, "d", "drawn"),
            "l": _header_index(rows, "l", "lost"),
            "gf": _header_index(rows, "gf", "f", "goals for"),
            "ga": _header_index(rows, "ga", "a", "goals against"),
        }
        for row in rows[1:]:
            canon = _row_team(row, resolver, i_team)
            if not canon:
                continue
            st = out.setdefault(canon, {"stats": TeamStats(), "url": ""})["stats"]
            rank = _num(row[0])
            if rank is not None and st.rank is None:
                st.rank = int(rank)
            st.played = _int(row, i_pl)
            st.points = _int(row, i_pts)
            st.wins = _int(row, idx["w"])
            st.draws = _int(row, idx["d"])
            st.losses = _int(row, idx["l"])
            st.goals_for = _int(row, idx["gf"])
            st.goals_against = _int(row, idx["ga"])

    # 3) 팀 통계 (Shots pg / Possession% / Pass% / AerialsWon / Rating)
    for table in soup.find_all("table"):
        rows = _table_rows(table)
        if len(rows) < 3:
            continue
        i_team = _header_index(rows, "team", "")
        i_shots = _header_index(rows, "shots pg", "shotspg")
        i_poss = _header_index(rows, "possession%", "possession")
        i_pass = _header_index(rows, "pass%", "passsuccess", "pass success")
        i_aerial = _header_index(rows, "aerialswon", "aerials won")
        i_rating = _header_index(rows, "rating")
        if not any(x is not None for x in (i_shots, i_poss, i_pass, i_rating)):
            continue
        for row in rows[1:]:
            canon = _row_team(row, resolver, i_team)
            if not canon:
                continue
            st = out.setdefault(canon, {"stats": TeamStats(), "url": ""})["stats"]
            st.shots_pg = _f(row, i_shots) or st.shots_pg
            st.possession = _f(row, i_poss) or st.possession
            st.pass_success = _f(row, i_pass) or st.pass_success
            st.aerials_won_pg = _f(row, i_aerial) or st.aerials_won_pg
            st.rating = _f(row, i_rating) or st.rating

    if not out:
        # 왜 실패했는지 구분되도록 구조 정보를 남긴다.
        team_links = [a["href"] for a in soup.find_all("a", href=True)
                      if "/Teams/" in a["href"]]
        tables = soup.find_all("table")
        log.error("리그 페이지에서 팀을 하나도 파싱하지 못함: %s "
                  "(/Teams/ 링크 %d개, <table> %d개, 문서 %.0fKB)",
                  league_key, len(team_links), len(tables), len(html) / 1024)
        if team_links:
            log.error("  링크는 있는데 팀명이 안 맞습니다. 예: %s", team_links[:3])
        else:
            log.error("  팀 링크가 없습니다 — 리그 경로(config_toto.yaml 의 "
                      "leagues.%s.whoscored)가 틀렸거나 JS 렌더링 대기가 "
                      "부족한 것으로 보입니다.", league_key)
        if cache:
            cache.save_debug("whoscored", f"league_{league_key}", html)
        return {}

    log.info("후스코어드 %s — 팀 %d개 수집", league_key, len(out))
    if cache:
        cache.set("whoscored", f"league_{league_key}", _freeze_league(out))
    return out


def _row_team(row: list[str], resolver: TeamResolver, i_team: int | None) -> str | None:
    """행에서 팀명을 찾아 정규명으로 바꾼다."""
    candidates = []
    if i_team is not None and i_team < len(row):
        candidates.append(row[i_team])
    candidates.extend(row[:3])
    for cand in candidates:
        cand = re.sub(r"^\d+\s*", "", cand or "").strip()
        if len(cand) < 2 or _NUM_RE.fullmatch(cand or ""):
            continue
        canon = resolver.resolve(cand, learn=False)
        if canon:
            return canon
    return None


def _int(row: list[str], i: int | None) -> int | None:
    v = _f(row, i)
    return int(v) if v is not None else None


def _f(row: list[str], i: int | None) -> float | None:
    if i is None or i >= len(row):
        return None
    return _num(row[i])


def _freeze_league(data: dict) -> dict:
    from dataclasses import asdict
    return {k: {"stats": asdict(v["stats"]), "url": v["url"]} for k, v in data.items()}


def _revive_league(data: dict) -> dict:
    out = {}
    for k, v in (data or {}).items():
        st = TeamStats(**(v.get("stats") or {}))
        out[k] = {"stats": st, "url": v.get("url", "")}
    return out


# --------------------------------------------------------------------------
# 팀 페이지 → 특성 / 최근 폼 / 결장자
# --------------------------------------------------------------------------
_CHARACTERISTIC_HEADINGS = {
    "strengths": "strengths",
    "strength": "strengths",
    "weaknesses": "weaknesses",
    "weakness": "weaknesses",
    "style of play": "style",
    "styleofplay": "style",
}


def _extract_characteristics(soup) -> dict[str, list[str]]:
    """Strengths / Weaknesses / Style of Play 추출.

    클래스명 대신 **제목 텍스트**를 기준으로 찾는다 — 마크업이 바뀌어도
    제목 문구는 잘 바뀌지 않기 때문이다.
    """
    found: dict[str, list[str]] = {"strengths": [], "weaknesses": [], "style": []}

    # 제목이 될 만한 태그만 훑는다. div/span 전체를 get_text 하면 큰 페이지에서
    # 매우 느려지므로, 자식이 거의 없는 잎 노드로 제한한다.
    for node in soup.find_all(["h1", "h2", "h3", "h4", "h5", "dt", "th",
                               "strong", "b", "label", "span", "div"]):
        if node.name in ("span", "div") and len(node.find_all(True, recursive=False)) > 1:
            continue
        label = node.get_text(" ", strip=True).lower().rstrip(":")
        if len(label) > 20:            # "Style of play" 보다 긴 제목은 없다
            continue
        slot = _CHARACTERISTIC_HEADINGS.get(label) or _CHARACTERISTIC_HEADINGS.get(
            label.replace(" ", ""))
        if not slot or found[slot]:
            continue
        # 제목 뒤에 오는 첫 목록을 읽는다
        holder = node.find_next(["ul", "ol", "dd", "table", "div"])
        if holder is None:
            continue
        items = [li.get_text(" ", strip=True) for li in holder.find_all("li")]
        if not items:
            items = [x.get_text(" ", strip=True)
                     for x in holder.find_all(["span", "td", "p"])]
        items = [re.sub(r"\s+", " ", i) for i in items if 2 < len(i) < 120]
        # 중복 제거(순서 유지)
        seen, cleaned = set(), []
        for item in items:
            if item.lower() not in seen:
                seen.add(item.lower())
                cleaned.append(item)
        found[slot] = cleaned[:8]

    # 임베드 JSON 폴백
    if not any(found.values()):
        for script in soup.find_all("script"):
            text = script.string or ""
            if "trength" not in text and "haracteristic" not in text:
                continue
            for key, slot in (("strengths", "strengths"), ("weaknesses", "weaknesses"),
                              ("style", "style")):
                m = re.search(rf'"{key}"\s*:\s*(\[[^\]]*\])', text, re.I)
                if m and not found[slot]:
                    try:
                        vals = json.loads(m.group(1))
                        found[slot] = [str(v) for v in vals if isinstance(v, (str, int))][:8]
                    except Exception:
                        pass
    return found


def _extract_form(soup, resolver: TeamResolver, canonical: str,
                  limit: int) -> list[FormEntry]:
    """최근 경기 결과 추출 (최신순)."""
    entries: list[FormEntry] = []
    for table in soup.find_all("table"):
        rows = _table_rows(table)
        if len(rows) < 2:
            continue
        blob = " ".join(rows[0]).lower()
        if not any(k in blob for k in ("result", "score", "opponent", "date")):
            continue
        for row in rows[1:]:
            line = " ".join(row)
            sm = _SCORE_RE.search(line)
            if not sm:
                continue
            names = [c for c in row
                     if len(c) > 2 and not _SCORE_RE.search(c) and not _DATE_RE.search(c)]
            teams = []
            for cand in names:
                canon = resolver.resolve(cand, learn=False)
                if canon and canon not in teams:
                    teams.append(canon)
            if canonical not in teams or len(teams) < 2:
                continue
            opponent = next(t for t in teams if t != canonical)
            is_home = teams.index(canonical) < teams.index(opponent)
            g1, g2 = int(sm.group(1)), int(sm.group(2))
            gf, ga = (g1, g2) if is_home else (g2, g1)
            dm = _DATE_RE.search(line)
            entries.append(FormEntry(
                date=dm.group(1) if dm else "",
                opponent=opponent, home=is_home,
                goals_for=gf, goals_against=ga,
                result="W" if gf > ga else ("D" if gf == ga else "L"),
            ))
        if entries:
            break
    return entries[:limit]


def _extract_missing(soup) -> list[dict]:
    """결장자(부상/징계) 목록."""
    out: list[dict] = []
    for node in soup.find_all(["h2", "h3", "h4", "div", "span"]):
        label = node.get_text(" ", strip=True).lower()
        if not any(k in label for k in ("injur", "suspend", "missing", "unavailable")):
            continue
        if len(label) > 40:
            continue
        holder = node.find_next(["ul", "table", "div"])
        if holder is None:
            continue
        for row in holder.find_all(["li", "tr"]):
            cells = [c.get_text(" ", strip=True)
                     for c in row.find_all(["td", "span"])] or [row.get_text(" ", strip=True)]
            cells = [c for c in cells if c]
            if not cells:
                continue
            out.append({"player": cells[0],
                        "reason": " · ".join(cells[1:3]) if len(cells) > 1 else ""})
        if out:
            break
    return out[:10]


def read_team(browser: WhoScoredBrowser, settings: Settings, team_url: str,
              canonical: str, resolver: TeamResolver, cache=None) -> dict:
    """팀 페이지에서 특성/폼/결장자를 수집한다."""
    cached = cache.get("whoscored", f"team_{canonical}") if cache else None
    if cached is not None:
        return cached

    if not team_url:
        return {}
    html = browser.get_html(browser.abs_url(team_url), wait_selector="table, ul")
    if not html:
        return {}

    soup = _soup(html)
    chars = _extract_characteristics(soup)
    limit = int(settings.whoscored.get("recent_form_count", 5))
    form = _extract_form(soup, resolver, canonical, limit)

    payload = {
        "strengths": chars["strengths"],
        "weaknesses": chars["weaknesses"],
        "style": chars["style"],
        "form": [f.__dict__ for f in form],
        "missing": _extract_missing(soup),
    }
    if not any(chars.values()) and not form:
        log.warning("팀 페이지에서 아무것도 파싱하지 못함: %s", canonical)
        if cache:
            cache.save_debug("whoscored", f"team_{canonical}", html)
        return {}

    if cache:
        cache.set("whoscored", f"team_{canonical}", payload)
    return payload


# --------------------------------------------------------------------------
# 상대전적
# --------------------------------------------------------------------------
def read_h2h(browser: WhoScoredBrowser, settings: Settings,
             home_canon: str, away_canon: str, resolver: TeamResolver,
             league_key: str, cache=None) -> H2H:
    """리그 일정에서 해당 경기를 찾아 프리뷰 페이지의 상대전적을 읽는다."""
    key = f"h2h_{home_canon}__{away_canon}"
    cached = cache.get("whoscored", key) if cache else None
    if cached is not None:
        return _revive_h2h(cached)

    path = (settings.leagues.get(league_key) or {}).get("whoscored", "")
    if not path:
        return H2H()

    fixtures_html = browser.get_html(browser.abs_url(path + "/Fixtures"),
                                     wait_selector="a[href*='/Matches/']")
    match_id = _find_match_id(fixtures_html, resolver, home_canon, away_canon)
    if not match_id:
        log.info("H2H: 일정에서 경기를 찾지 못함 (%s vs %s)", home_canon, away_canon)
        return H2H()

    preview = browser.get_html(browser.abs_url(f"/Matches/{match_id}/Preview"),
                               wait_selector="table")
    if not preview:
        return H2H()

    h2h = _parse_h2h(preview, resolver, home_canon, away_canon,
                     int(settings.whoscored.get("h2h_count", 10)))
    if cache and h2h.source_ok:
        from dataclasses import asdict
        cache.set("whoscored", key, asdict(h2h))
    return h2h


def _find_match_id(html: str, resolver: TeamResolver,
                   home_canon: str, away_canon: str) -> str | None:
    if not html:
        return None
    soup = _soup(html)
    for row in soup.find_all(["tr", "div"]):
        text = row.get_text(" ", strip=True)
        if len(text) > 200:
            continue
        link = row.find("a", href=re.compile(r"/Matches/\d+"))
        if not link:
            continue
        teams = []
        for a in row.find_all("a"):
            canon = resolver.resolve(a.get_text(" ", strip=True), learn=False)
            if canon and canon not in teams:
                teams.append(canon)
        if home_canon in teams and away_canon in teams:
            m = re.search(r"/Matches/(\d+)", link["href"])
            if m:
                return m.group(1)
    return None


def _parse_h2h(html: str, resolver: TeamResolver, home_canon: str,
               away_canon: str, limit: int) -> H2H:
    soup = _soup(html)
    entries: list[H2HEntry] = []
    for table in soup.find_all("table"):
        for row in _table_rows(table):
            line = " ".join(row)
            sm = _SCORE_RE.search(line)
            if not sm:
                continue
            teams = []
            for cell in row:
                canon = resolver.resolve(cell, learn=False)
                if canon and canon not in teams:
                    teams.append(canon)
            if home_canon not in teams or away_canon not in teams:
                continue
            first = teams[0]
            g1, g2 = int(sm.group(1)), int(sm.group(2))
            dm = _DATE_RE.search(line)
            entries.append(H2HEntry(
                date=dm.group(1) if dm else "",
                home_team=first,
                away_team=away_canon if first == home_canon else home_canon,
                home_goals=g1, away_goals=g2,
            ))
        if entries:
            break

    entries = entries[:limit]
    h2h = H2H(entries=entries, source_ok=bool(entries))
    for e in entries:
        if e.home_goals == e.away_goals:
            h2h.draws += 1
        else:
            winner = e.home_team if e.home_goals > e.away_goals else e.away_team
            if winner == home_canon:
                h2h.home_wins += 1
            else:
                h2h.away_wins += 1
    return h2h


def _revive_h2h(data: dict) -> H2H:
    entries = [H2HEntry(**e) for e in (data.get("entries") or [])]
    return H2H(entries=entries, home_wins=data.get("home_wins", 0),
               draws=data.get("draws", 0), away_wins=data.get("away_wins", 0),
               source_ok=data.get("source_ok", False))


# --------------------------------------------------------------------------
# 오케스트레이션
# --------------------------------------------------------------------------
def enrich(matches, settings: Settings, resolver: TeamResolver, cache=None) -> str:
    """모든 경기에 후스코어드 데이터를 붙인다. 반환값은 상태 문자열."""
    try:
        import bs4  # noqa: F401
    except Exception:
        log.error("beautifulsoup4 미설치 — 후스코어드 수집을 건너뜁니다.")
        return "실패 (bs4 미설치)"

    leagues = sorted({m.league for m in matches if m.league})
    teams_done = 0

    with WhoScoredBrowser(settings, cache=cache) as browser:
        if not browser.available:
            return "실패 (브라우저 기동 불가)"

        league_data: dict[str, dict] = {}
        for key in leagues:
            league_data[key] = read_league(browser, settings, key, resolver, cache=cache)

        for match in matches:
            table = league_data.get(match.league) or {}
            for side in ("home", "away"):
                ref: TeamRef = getattr(match, side)
                profile = TeamProfile(team=ref, league=match.league)
                entry = table.get(ref.canonical) if ref.canonical else None
                if entry:
                    profile.stats = entry["stats"]
                    ref.whoscored_url = entry.get("url", "")
                    payload = read_team(browser, settings, ref.whoscored_url,
                                        ref.canonical, resolver, cache=cache)
                    if payload:
                        profile.strengths = payload.get("strengths") or []
                        profile.weaknesses = payload.get("weaknesses") or []
                        profile.style_of_play = payload.get("style") or []
                        profile.form = [FormEntry(**f) for f in (payload.get("form") or [])]
                        profile.missing_players = payload.get("missing") or []
                        profile.source_ok = True
                        teams_done += 1
                else:
                    match.notes.append(
                        f"{ref.display}: 후스코어드에서 팀을 찾지 못했습니다.")
                setattr(match, f"{side}_profile", profile)

            if match.home.canonical and match.away.canonical:
                match.h2h = read_h2h(browser, settings, match.home.canonical,
                                     match.away.canonical, resolver,
                                     match.league, cache=cache)

    total = len(matches) * 2
    if teams_done == 0:
        return "실패 (수집 0팀)"
    return f"ok ({teams_done}/{total}팀)"
