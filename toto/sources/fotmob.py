"""FotMob 수집 — 순위표(홈/원정 분리) + 최근 폼 + 상대전적.

## 왜 FotMob 인가

점검 도구(tools/probe_sources.py) 실행 결과가 근거다.

  · FBref     — Cloudflare 가 브라우저로도 403 (12초 대기 재시도까지 실패)
  · Understat — 아시아 리그 미수록 (K리그 404, EPL 만 200)
  · Sofascore — 브라우저로 200. 다만 대회/시즌 ID 를 두 번 타고 들어가야 한다
  · **FotMob  — 브라우저로 200, 리그 1회 요청에 필요한 것이 거의 다 들어 있다**

이번 회차가 전부 K리그·J리그였는데 아시아를 제대로 덮는 건 FotMob 뿐이었다.

## 무엇을 가져오는가

리그당 **요청 1회**로 아래를 한꺼번에 얻는다(후스코어드는 팀마다 페이지를
열어야 했고 그마저 자주 막혔다):

  · 순위표 all/home/away  → 경기수·승·무·패·득실·승점, **홈/원정 승점**
  · 시즌 전체 경기 목록    → 팀별 최근 5경기 폼, 두 팀 간 상대전적

홈/원정 승점은 레이더 축에 넣어두고도 후스코어드에서 한 번도 못 채운 항목이다.

## 구조를 이름이 아니라 모양으로 찾는 이유

FotMob 응답은 리그마다 형태가 조금씩 다르다. 정규 리그는
`table[0].data.table.all`, 스플릿·조별 리그는 `...data.tables[i].table.all`,
`composite` 가 끼기도 한다. 경로를 박아두면 K리그 스플릿이 시작되는 순간
조용히 빈 값이 된다. 그래서 **"all 이 팀 행들의 리스트인 dict"** 처럼
모양으로 찾는다.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict
from typing import Any, Iterator

from ..models import FormEntry, H2H, H2HEntry, TeamProfile, TeamRef, TeamStats
from ..models import fill_stats
from ..normalize import TeamResolver
from ..settings import Settings
from .browser import StealthBrowser

log = logging.getLogger(__name__)

DEFAULT_BASE = "https://www.fotmob.com"
LEAGUE_PATH = "/api/data/leagues?id={id}"
ALL_LEAGUES_PATH = "/api/data/allLeagues"

# 캐시 형식이나 파싱 로직이 바뀌면 올린다. 옛 캐시는 자동으로 버려진다.
_CACHE_VERSION = 1

_SCORE_RE = re.compile(r"(\d+)\s*[-:]\s*(\d+)")


class FotMobBrowser(StealthBrowser):
    def __init__(self, settings: Settings, cache=None) -> None:
        cfg = dict(getattr(settings, "fotmob", None) or {})
        cfg.setdefault("base", DEFAULT_BASE)
        cfg.setdefault("delay_sec", 1.5)
        super().__init__(cfg, cache=cache, name="FotMob")


# --------------------------------------------------------------------------
# JSON 구조 탐색 (경로가 아니라 모양으로)
# --------------------------------------------------------------------------
def _walk(node: Any, max_nodes: int = 400_000) -> Iterator[dict]:
    """JSON 트리의 모든 dict 를 훑는다 (재귀 한도를 피해 스택으로)."""
    stack = [node]
    seen = 0
    while stack and seen < max_nodes:
        cur = stack.pop()
        seen += 1
        if isinstance(cur, dict):
            yield cur
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def _is_team_row(item: Any) -> bool:
    return (isinstance(item, dict) and isinstance(item.get("name"), str)
            and ("pts" in item or "played" in item))


def _standings_blocks(data: Any) -> list[dict]:
    """{"all": [팀행...], "home": [...], "away": [...]} 모양의 dict 들."""
    out = []
    for node in _walk(data):
        rows = node.get("all")
        if isinstance(rows, list) and rows and all(_is_team_row(r) for r in rows):
            out.append(node)
    return out


def _is_match(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    home, away = item.get("home"), item.get("away")
    return (isinstance(home, dict) and isinstance(away, dict)
            and isinstance(home.get("name"), str)
            and isinstance(away.get("name"), str))


def _match_list(data: Any) -> list[dict]:
    """시즌 경기 목록. id 로 중복을 제거한다(여러 섹션에 같은 경기가 실린다)."""
    out: dict[str, dict] = {}
    for node in _walk(data):
        if not _is_match(node):
            continue
        key = str(node.get("id") or
                  f"{node['home'].get('name')}|{node['away'].get('name')}|"
                  f"{_utc_time(node)}")
        out.setdefault(key, node)
    return list(out.values())


def _utc_time(match: dict) -> str:
    status = match.get("status")
    if isinstance(status, dict) and status.get("utcTime"):
        return str(status["utcTime"])
    return str(match.get("utcTime") or match.get("time") or "")


def _finished(match: dict) -> bool:
    status = match.get("status")
    if isinstance(status, dict):
        if status.get("finished") is True:
            return True
        if status.get("cancelled") or status.get("started") is False:
            return False
    return _goals(match) != (None, None)


def _goals(match: dict) -> tuple[int | None, int | None]:
    """(홈 득점, 원정 득점). 아직 안 끝난 경기면 (None, None)."""
    home, away = match.get("home") or {}, match.get("away") or {}
    hs, as_ = home.get("score"), away.get("score")
    if isinstance(hs, int) and isinstance(as_, int):
        return hs, as_
    status = match.get("status") or {}
    text = status.get("scoreStr") if isinstance(status, dict) else None
    m = _SCORE_RE.search(str(text or ""))
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


# --------------------------------------------------------------------------
# 리그 ID
# --------------------------------------------------------------------------
def resolve_league_id(browser: FotMobBrowser, settings: Settings,
                      league_key: str, cache=None) -> int | None:
    """설정의 fotmob_id 를 쓰되, 없으면 전체 리그 목록에서 이름으로 찾는다.

    ID 를 설정에 박아두면 시즌이 바뀔 때 조용히 어긋난다. 그래서 못 찾은
    리그는 allLeagues 에서 이름으로 탐색하고, 알아낸 값은 캐시에 남긴다.
    """
    cfg = settings.leagues.get(league_key) or {}
    fixed = cfg.get("fotmob_id")
    if fixed:
        return int(fixed)

    cached = cache.get("fotmob", f"leagueid_{league_key}") if cache else None
    if isinstance(cached, int):
        return cached

    want = str(cfg.get("fotmob_name") or "").strip().lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", want) if t]
    if not tokens:
        log.warning("[%s] FotMob 리그명이 설정에 없어 ID 를 찾을 수 없습니다 "
                    "(config_toto.yaml 의 leagues.%s.fotmob_name)",
                    league_key, league_key)
        return None
    # "K League 2" 의 'k'·'2' 같은 한 글자 토큰은 아무 이름에나 걸린다.
    # 그래서 '긴 토큰이 반드시 들어 있을 것'을 통과 조건으로 두고,
    # 짧은 토큰은 1 · 2부 리그를 가르는 가점으로만 쓴다.
    anchor = max(tokens, key=len)

    data = browser.get_json(browser.abs_url(ALL_LEAGUES_PATH))
    if data is None:
        log.warning("[%s] FotMob 리그 목록을 받지 못했습니다.", league_key)
        return None

    best: tuple[int, int, str] | None = None      # (일치 토큰 수, id, 이름)
    for node in _walk(data):
        name, lid = node.get("name"), node.get("id")
        if not isinstance(name, str) or not isinstance(lid, int):
            continue
        low = name.strip().lower()
        if low == want:
            best = (len(tokens) + 1, lid, name)
            break
        if len(anchor) > 2 and anchor not in low:
            continue
        hits = sum(1 for t in tokens if t in low)
        if best is None or hits > best[0]:
            best = (hits, lid, name)

    if best is None:
        log.warning("[%s] FotMob 리그 목록에서 '%s' 를 찾지 못했습니다.",
                    league_key, want)
        return None
    log.info("[%s] FotMob 리그 탐색: '%s' → id=%d", league_key, best[2], best[1])
    if cache:
        cache.set("fotmob", f"leagueid_{league_key}", best[1])
    return best[1]


# --------------------------------------------------------------------------
# 리그 1회 요청 → 순위표 + 폼 + 경기 목록
# --------------------------------------------------------------------------
def read_league(browser: FotMobBrowser, settings: Settings, league_key: str,
                resolver: TeamResolver, cache=None) -> dict:
    """Returns: {"teams": {정규명: {...}}, "matches": [정규화된 경기...]}"""
    cached = cache.get("fotmob", f"league_{league_key}") if cache else None
    revived = _revive(cached)
    if revived is not None:
        log.info("[%s] FotMob 캐시 사용 (팀 %d개). 새로 받으려면 캐시 비우기를 쓰세요.",
                 league_key, len(revived["teams"]))
        return revived

    league_id = resolve_league_id(browser, settings, league_key, cache=cache)
    if league_id is None:
        return {"teams": {}, "matches": []}

    url = browser.abs_url(LEAGUE_PATH.format(id=league_id))
    data = browser.get_json(url)
    if data is None:
        log.error("[%s] FotMob 리그 응답을 받지 못했습니다 (id=%d).",
                  league_key, league_id)
        return {"teams": {}, "matches": []}

    teams = _parse_standings(data, resolver, league_key)
    matches = _parse_matches(data, resolver)
    _attach_form(teams, matches, int(settings.whoscored.get("recent_form_count", 5)))

    if not teams:
        log.error("[%s] FotMob 순위표를 해석하지 못했습니다 (id=%d). "
                  "응답에 표 블록이 %d개 있었습니다.", league_key, league_id,
                  len(_standings_blocks(data)))
        return {"teams": {}, "matches": matches}

    log.info("[%s] FotMob — 팀 %d개, 종료 경기 %d개 수집 (id=%d)",
             league_key, len(teams), sum(1 for m in matches if m["finished"]),
             league_id)

    result = {"teams": teams, "matches": matches}
    if cache:
        cache.set("fotmob", f"league_{league_key}", _freeze(result))
    return result


def _parse_standings(data: Any, resolver: TeamResolver,
                     league_key: str) -> dict[str, dict]:
    """순위표 블록들을 정규명 → {stats, fotmob_id, page_url} 로 접는다."""
    out: dict[str, dict] = {}
    unmatched: list[str] = []

    for block in _standings_blocks(data):
        # xg 는 all/home/away 와 나란히 있는 또 하나의 표다. 리그 응답 한 번에
        # 이미 들어 있으므로 추가 요청 없이 xG·피xG 축을 채울 수 있다.
        for section in ("all", "home", "away", "xg"):
            rows = block.get(section)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not _is_team_row(row):
                    continue
                canon = resolver.resolve(str(row.get("name")), learn=False)
                if not canon:
                    unmatched.append(str(row.get("name")))
                    continue
                entry = out.setdefault(
                    canon, {"stats": TeamStats(), "fotmob_id": "", "page_url": ""})
                if row.get("id") and not entry["fotmob_id"]:
                    entry["fotmob_id"] = str(row["id"])
                if row.get("pageUrl") and not entry["page_url"]:
                    entry["page_url"] = str(row["pageUrl"])
                _apply_row(entry["stats"], row, section)

    if unmatched:
        # 리그 전체가 안 맞는지, 한두 팀만 안 맞는지 구분되게 남긴다.
        log.debug("[%s] FotMob 팀명 미매칭 %d건: %s", league_key,
                  len(set(unmatched)), sorted(set(unmatched))[:6])
    return out


def _apply_row(stats: TeamStats, row: dict, section: str) -> None:
    played = _int(row.get("played"))
    pts = _int(row.get("pts"))

    if section == "xg":
        # FotMob 이 함께 주는 xgDiff 는 쓰지 않는다. 부호 규칙(득점-xG 인지
        # xG-득점 인지)이 문서화돼 있지 않아서, 득점은 all 표에서 이미
        # 확보했으니 차이는 우리가 직접 계산한다.
        if played is None or (stats.xg_played or 0) > played:
            return
        stats.xg_played = played
        stats.xg_total = _float(row.get("xg"))
        stats.xga_total = _float(row.get("xgConceded"))
        return

    if section in ("home", "away"):
        # 스플릿 리그는 같은 팀이 여러 블록에 나온다. 경기수가 더 많은 쪽
        # (= 전체 시즌 표)을 남긴다.
        if played is None or (getattr(stats, f"{section}_played") or 0) > played:
            return
        setattr(stats, f"{section}_played", played)
        setattr(stats, f"{section}_points", pts)
        # 승점만 쓰고 버렸던 득실을 함께 남긴다 — '장소 특화도' 축은
        # 홈/원정 승점과 득실차를 같이 본다.
        gf, ga = _parse_scores(row)
        if gf is not None:
            setattr(stats, f"{section}_goals_for", gf)
            setattr(stats, f"{section}_goals_against", ga)
        return

    if played is None:
        if stats.played is not None:
            return                              # 값 없는 표로 덮어쓰지 않는다
    elif (stats.played or 0) > played:
        return                                  # 더 정보가 많은 표를 이미 읽었다

    stats.played = played
    stats.points = pts
    stats.wins = _int(row.get("wins"))
    stats.draws = _int(row.get("draws"))
    stats.losses = _int(row.get("losses"))
    rank = _int(row.get("idx"))
    if rank is not None:
        stats.rank = rank

    gf, ga = _parse_scores(row)
    if gf is not None:
        stats.goals_for, stats.goals_against = gf, ga


def _parse_scores(row: dict) -> tuple[int | None, int | None]:
    """"35-17" → (35, 17). 형식이 바뀌면 득실차로라도 복원한다."""
    m = _SCORE_RE.search(str(row.get("scoresStr") or ""))
    if m:
        return int(m.group(1)), int(m.group(2))
    gf = _int(row.get("goalsScored") or row.get("scored"))
    ga = _int(row.get("goalsConceded") or row.get("conceded"))
    if gf is not None and ga is not None:
        return gf, ga
    diff = _int(row.get("goalConDiff"))
    if gf is not None and diff is not None:
        return gf, gf - diff
    return None, None


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_matches(data: Any, resolver: TeamResolver) -> list[dict]:
    """경기 목록을 정규명 기준으로 평평하게 만든다."""
    out = []
    for raw in _match_list(data):
        home = resolver.resolve(str(raw["home"].get("name")), learn=False)
        away = resolver.resolve(str(raw["away"].get("name")), learn=False)
        if not home or not away or home == away:
            continue
        hg, ag = _goals(raw)
        out.append({
            "date": _utc_time(raw)[:10],
            "utc": _utc_time(raw),
            "home": home,
            "away": away,
            "home_goals": hg,
            "away_goals": ag,
            "finished": _finished(raw) and hg is not None,
        })
    out.sort(key=lambda m: m["utc"], reverse=True)
    return out


def _attach_form(teams: dict[str, dict], matches: list[dict], count: int) -> None:
    """종료된 경기에서 팀별 최근 N경기 폼을 만든다 (최신순)."""
    for canon, entry in teams.items():
        form: list[FormEntry] = []
        for m in matches:                       # 이미 최신순 정렬
            if not m["finished"] or canon not in (m["home"], m["away"]):
                continue
            at_home = m["home"] == canon
            gf = m["home_goals"] if at_home else m["away_goals"]
            ga = m["away_goals"] if at_home else m["home_goals"]
            form.append(FormEntry(
                date=m["date"],
                opponent=m["away"] if at_home else m["home"],
                home=at_home, goals_for=gf, goals_against=ga,
                result="D" if gf == ga else ("W" if gf > ga else "L")))
            if len(form) >= count:
                break
        entry["form"] = form


def build_h2h(matches: list[dict], home_canon: str, away_canon: str,
              limit: int = 10) -> H2H:
    """같은 리그 시즌 경기 목록에서 두 팀 간 맞대결만 뽑는다.

    한 시즌 안에서만 찾으므로 보통 1~2경기다. 후스코어드 프리뷰의 다년치
    상대전적과는 성격이 다르니, 렌더링 쪽에서 건수를 함께 보여준다.
    """
    h2h = H2H()
    pair = {home_canon, away_canon}
    for m in matches:
        if not m["finished"] or {m["home"], m["away"]} != pair:
            continue
        h2h.entries.append(H2HEntry(
            date=m["date"], home_team=m["home"], away_team=m["away"],
            home_goals=m["home_goals"], away_goals=m["away_goals"]))
        if m["home_goals"] == m["away_goals"]:
            h2h.draws += 1
        elif (m["home"] == home_canon) == (m["home_goals"] > m["away_goals"]):
            h2h.home_wins += 1
        else:
            h2h.away_wins += 1
        if len(h2h.entries) >= limit:
            break
    h2h.source_ok = bool(h2h.entries)
    return h2h


# --------------------------------------------------------------------------
# 캐시 직렬화
# --------------------------------------------------------------------------
def _freeze(result: dict) -> dict:
    return {
        "_v": _CACHE_VERSION,
        "matches": result["matches"],
        "teams": {
            canon: {
                "stats": asdict(entry["stats"]),
                "form": [asdict(f) for f in entry.get("form") or []],
                "fotmob_id": entry.get("fotmob_id", ""),
                "page_url": entry.get("page_url", ""),
            }
            for canon, entry in result["teams"].items()
        },
    }


def _revive(data: Any) -> dict | None:
    if not isinstance(data, dict) or data.get("_v") != _CACHE_VERSION:
        return None
    try:
        teams = {
            canon: {
                "stats": TeamStats(**entry["stats"]),
                "form": [FormEntry(**f) for f in entry.get("form") or []],
                "fotmob_id": entry.get("fotmob_id", ""),
                "page_url": entry.get("page_url", ""),
            }
            for canon, entry in (data.get("teams") or {}).items()
        }
    except Exception as exc:
        log.debug("FotMob 캐시 복원 실패 — 새로 받습니다: %s", exc)
        return None
    return {"teams": teams, "matches": data.get("matches") or []}


# --------------------------------------------------------------------------
# 진입점
# --------------------------------------------------------------------------
def enrich(matches, settings: Settings, resolver: TeamResolver, cache=None) -> str:
    """모든 경기에 FotMob 데이터를 붙인다. 반환값은 상태 문자열.

    이미 프로필이 있으면(다른 소스가 먼저 채웠으면) 빈 칸만 메운다.
    """
    leagues = sorted({m.league for m in matches if m.league})
    if not leagues:
        return "생략 (리그 미상)"

    stats_done = 0
    form_done = 0
    h2h_done = 0

    with FotMobBrowser(settings, cache=cache) as browser:
        if not browser.available:
            return "실패 (브라우저 기동 불가)"

        data = {key: read_league(browser, settings, key, resolver, cache=cache)
                for key in leagues}

    for match in matches:
        league = data.get(match.league) or {"teams": {}, "matches": []}
        for side in ("home", "away"):
            ref: TeamRef = getattr(match, side)
            profile = getattr(match, f"{side}_profile") or TeamProfile(
                team=ref, league=match.league)
            entry = league["teams"].get(ref.canonical) if ref.canonical else None
            if entry:
                fill_stats(profile.stats, entry["stats"])
                profile.source_ok = True
                stats_done += 1
                if entry.get("form") and not profile.form:
                    profile.form = list(entry["form"])
                    form_done += 1
                if entry.get("fotmob_id"):
                    ref.fotmob_id = entry["fotmob_id"]
            setattr(match, f"{side}_profile", profile)

        if match.home.canonical and match.away.canonical and not match.h2h.entries:
            h2h = build_h2h(league["matches"], match.home.canonical,
                            match.away.canonical,
                            limit=int(settings.whoscored.get("h2h_count", 10)))
            if h2h.entries:
                match.h2h = h2h
                h2h_done += 1

    total = len(matches) * 2
    if stats_done == 0:
        return "실패 (수집 0팀)"
    detail = f"{stats_done}/{total}팀 지표, {form_done}팀 폼, {h2h_done}경기 상대전적"
    return (f"ok ({detail})" if stats_done == total else f"부분 ({detail})")
