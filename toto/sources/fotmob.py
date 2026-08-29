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

  · 순위표 all/home/away  → 경기수·승·무·패·득실·승점, **홈/원정 승점·득실**
  · xG 표                 → 시즌 xG·피xG (같은 응답 안에 들어 있다)
  · 시즌 전체 경기 목록    → 팀별 최근 N경기 폼, 두 팀 간 상대전적
  · stats.teams[]         → 이 리그에서 받을 수 있는 팀 통계 29종의 URL

홈/원정 승점은 레이더 축에 넣어두고도 후스코어드에서 한 번도 못 채운 항목이다.
통계 29종은 리그당 지표 1개씩 추가 요청이 들지만, 한 번에 그 리그 전 팀
값을 받으므로 팀별로 페이지를 여는 것보다 훨씬 싸다.

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
from datetime import datetime
from typing import Any, Iterator

from ..models import FormEntry, H2H, H2HEntry, SeasonMatch
from ..models import TeamProfile, TeamRef, TeamStats
from ..models import fill_stats
from ..normalize import TeamResolver
from .. import shots
from ..settings import Settings
from .browser import StealthBrowser

log = logging.getLogger(__name__)

DEFAULT_BASE = "https://www.fotmob.com"
LEAGUE_PATH = "/api/data/leagues?id={id}"
ALL_LEAGUES_PATH = "/api/data/allLeagues"

# 캐시 형식이나 파싱 로직이 바뀌면 올린다. 옛 캐시는 자동으로 버려진다.
_CACHE_VERSION = 9

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
# 동명 후보가 여럿일 때 순위표를 받아 확인할 최대 개수. 응답이 크므로
# 무한정 받지 않는다. 실측에서 'Premier League' 동명 리그가 16개였고 4개만
# 확인해서는 잉글랜드가 걸리지 않았다 — 국가 힌트로 순서를 잡은 뒤 이만큼 본다.
_MAX_VERIFY_CANDIDATES = 8
# 순위표에서 '우리가 그 리그 소속으로 아는 팀'이 이만큼은 나와야 채택한다.
_MIN_ROSTER_HITS = 3


def _country_hints(data: Any) -> dict[int, set[str]]:
    """리그 id → 그 리그를 감싼 dict 의 문자열 값들 (국가명·코드 등).

    allLeagues 의 내부 구조는 아직 실물로 확인하지 못했다. 그래서
    `countries[].name` 같은 경로를 단정하지 않고, **'리그 목록을 들고 있는
    dict' 의 문자열 필드를 그대로 힌트로 쓴다.** 그 dict 가 국가든 대륙이든
    이름이 무엇이든, 담긴 리그를 가리키는 상위 정보인 건 분명하다.
    """
    hints: dict[int, set[str]] = {}
    for node in _walk(data):
        words: set[str] | None = None
        for value in node.values():
            if not isinstance(value, list):
                continue
            ids = [v["id"] for v in value
                   if isinstance(v, dict) and isinstance(v.get("id"), int)
                   and isinstance(v.get("name"), str)]
            if not ids:
                continue
            if words is None:
                words = {v.strip().lower() for v in node.values()
                         if isinstance(v, str) and v.strip()}
            for lid in ids:
                hints.setdefault(lid, set()).update(words)
    return hints


def _name_candidates(data: Any, want: str) -> list[tuple[int, int, str]]:
    """(점수, id, 이름) 후보 목록. 점수가 높을수록 이름이 잘 맞는다.

    이름이 정확히 같은 리그가 **여러 나라에 존재**한다. FotMob allLeagues 는
    94개국을 담고 있고 'Premier League' 는 잉글랜드 말고도 여럿이다. 그래서
    처음 만난 하나에서 멈추면 안 되고, 동점 후보를 전부 남겨 뒤에서 가린다.
    """
    tokens = [t for t in re.split(r"[^a-z0-9]+", want) if t]
    if not tokens:
        return []
    # "K League 2" 의 'k'·'2' 같은 한 글자 토큰은 아무 이름에나 걸린다.
    # 긴 토큰이 반드시 들어 있을 것을 통과 조건으로 두고, 짧은 토큰은
    # 1 · 2부를 가르는 가점으로만 쓴다.
    anchor = max(tokens, key=len)

    out: dict[int, tuple[int, int, str]] = {}
    for node in _walk(data):
        name, lid = node.get("name"), node.get("id")
        if not isinstance(name, str) or not isinstance(lid, int) or lid in out:
            continue
        low = name.strip().lower()
        if low == want:
            out[lid] = (len(tokens) + 1, lid, name)      # 완전일치
            continue
        if len(anchor) > 2 and anchor not in low:
            continue
        hits = sum(1 for t in tokens if t in low)
        if hits:
            out[lid] = (hits, lid, name)
    return sorted(out.values(), key=lambda x: -x[0])


def _roster_hits(browser: FotMobBrowser, league_id: int, league_key: str,
                 resolver: TeamResolver) -> int:
    """이 리그 순위표에 '우리가 그 리그 소속으로 아는 팀'이 몇 팀 있는지.

    동명 리그를 가르는 기준으로 국가 코드를 쓰려면 allLeagues 의 내부 구조를
    알아야 하는데 그건 아직 실물로 확인하지 못했다. 반면 순위표의
    `table.all[].name` 은 이미 확인된 구조이고, 소속 리그는 data/teams.yaml
    이 들고 있다. 그래서 '아는 팀이 실제로 들어 있는가'로 판별한다.
    """
    data = browser.get_json(browser.abs_url(LEAGUE_PATH.format(id=league_id)))
    if data is None:
        return -1
    for block in _standings_blocks(data):
        hits = 0
        for row in block.get("all") or []:
            canon = resolver.resolve(str(row.get("name")), learn=False, quiet=True)
            if canon and resolver.league_of(canon) == league_key:
                hits += 1
        return hits
    return 0


def resolve_league_id(browser: FotMobBrowser, settings: Settings,
                      league_key: str, cache=None,
                      resolver: TeamResolver | None = None) -> int | None:
    """설정의 fotmob_id 를 쓰되, 없으면 전체 리그 목록에서 찾는다.

    ID 를 설정에 박아두면 시즌이 바뀔 때 조용히 어긋나므로 탐색도 남겨 둔다.
    다만 **이름만으로는 리그를 특정할 수 없다** — 같은 이름의 리그가 여러
    나라에 있어서, 처음 만난 후보를 채택하면 엉뚱한 리그를 잡는다(실측:
    EPL 요청에 id=441 이 선택돼 순위표 해석이 통째로 실패했다).

    그래서 동명 후보가 여럿이면 임의로 고르지 않고 순위표의 팀 구성으로
    가린다. 그래도 못 가리면 **실패로 끝내고** 설정에 ID 를 넣도록 안내한다.
    """
    cfg = settings.leagues.get(league_key) or {}
    fixed = cfg.get("fotmob_id")
    if fixed:
        return int(fixed)

    cached = cache.get("fotmob", f"leagueid_{league_key}") if cache else None
    if isinstance(cached, int):
        return cached

    want = str(cfg.get("fotmob_name") or "").strip().lower()
    if not want:
        log.warning("[%s] FotMob 리그명이 설정에 없어 ID 를 찾을 수 없습니다 "
                    "(config_toto.yaml 의 leagues.%s.fotmob_name)",
                    league_key, league_key)
        return None

    data = browser.get_json(browser.abs_url(ALL_LEAGUES_PATH))
    if data is None:
        log.warning("[%s] FotMob 리그 목록을 받지 못했습니다.", league_key)
        return None

    cands = _name_candidates(data, want)
    if not cands:
        log.warning("[%s] FotMob 리그 목록에서 '%s' 를 찾지 못했습니다.",
                    league_key, want)
        return None

    top = [c for c in cands if c[0] == cands[0][0]]

    # 국가로 후보를 좁힌다. 이름만으로는 못 가른다 — 실측에서
    # 'Premier League' 동명 리그가 16개였다.
    country = str(cfg.get("country") or "").strip().lower()
    if country and len(top) > 1:
        hints = _country_hints(data)
        same = [c for c in top if country in hints.get(c[1], set())]
        if same:
            log.info("[%s] 국가 '%s' 로 후보를 %d개 → %d개로 좁혔습니다.",
                     league_key, cfg.get("country"), len(top), len(same))
            top = same
        else:
            # 국가 힌트가 하나도 안 맞으면 순서만 뒤로 미룬다(버리지 않는다).
            log.debug("[%s] 국가 '%s' 로 좁히지 못했습니다.", league_key, country)

    if len(top) == 1:
        chosen = top[0]
        log.info("[%s] FotMob 리그 탐색: '%s' → id=%d",
                 league_key, chosen[2], chosen[1])
        if cache:
            cache.set("fotmob", f"leagueid_{league_key}", chosen[1])
        return chosen[1]

    # 동명 후보가 여럿 — 순위표의 팀 구성으로 가린다
    log.info("[%s] 이름이 같은 리그가 %d개입니다. 순위표로 확인합니다: %s",
             league_key, len(top), ", ".join(f"{c[2]}(id={c[1]})" for c in top[:6]))
    if resolver is None:
        log.warning("[%s] 후보를 가릴 수단이 없어 중단합니다. "
                    "config_toto.yaml 의 leagues.%s.fotmob_id 에 ID 를 적어 주세요.",
                    league_key, league_key)
        return None

    best_id, best_hits, best_name = None, 0, ""
    for _, lid, name in top[:_MAX_VERIFY_CANDIDATES]:
        hits = _roster_hits(browser, lid, league_key, resolver)
        log.info("[%s]   id=%d '%s' → 아는 팀 %d개", league_key, lid, name, hits)
        if hits > best_hits:
            best_id, best_hits, best_name = lid, hits, name

    if best_id is None or best_hits < _MIN_ROSTER_HITS:
        log.error("[%s] 동명 리그 %d개 중 어느 것인지 가리지 못했습니다 "
                  "(최다 일치 %d팀 < 기준 %d팀). 엉뚱한 리그를 쓰지 않도록 "
                  "건너뜁니다 — config_toto.yaml 의 leagues.%s.fotmob_id 에 "
                  "ID 를 적어 주세요.",
                  league_key, len(top), best_hits, _MIN_ROSTER_HITS, league_key)
        return None

    log.info("[%s] FotMob 리그 확정: '%s' → id=%d (아는 팀 %d개)",
             league_key, best_name, best_id, best_hits)
    if cache:
        cache.set("fotmob", f"leagueid_{league_key}", best_id)
    return best_id


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

    league_id = resolve_league_id(browser, settings, league_key,
                                  cache=cache, resolver=resolver)
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
    _attach_form(teams, matches, int(settings.whoscored.get("recent_form_count", 6)))

    feeds = settings.fotmob.get("team_stats") or DEFAULT_TEAM_STAT_FEEDS
    if teams and feeds:
        read_team_stats(browser, data, teams, resolver, feeds, league_key)

    # 시즌 통계에 없는 지표(npxG·xGOT·총슈팅·피슈팅·박스 안팎)는 경기 상세에만
    # 있다. 0 으로 두면 이 단계를 통째로 건너뛴다.
    detail_count = int(settings.fotmob.get("match_detail_matches", 0) or 0)
    if teams and detail_count > 0:
        attach_match_details(browser, teams, matches, detail_count,
                             league_key, cache=cache,
                             windows=_shot_windows(settings))

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
                canon = resolver.resolve(str(row.get("name")), learn=False, quiet=True)
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


# --------------------------------------------------------------------------
# 시즌 팀 통계 피드
# --------------------------------------------------------------------------
# 리그 응답의 stats.teams[] 에 이 리그에서 받을 수 있는 팀 통계 목록(29종)과
# 각각의 fetchAllUrl 이 들어 있다. URL 을 우리가 조립하지 않고 응답이 준
# 그대로 쓰므로, 시즌 ID 가 바뀌어도 따라간다.
#
# feed  : stats.teams[].name (URL 조각)
# field : TeamStats 속성명
DEFAULT_TEAM_STAT_FEEDS = [
    {"feed": "possession_percentage_team", "field": "possession"},
    {"feed": "ontarget_scoring_att_team", "field": "shots_on_target_pg"},
    {"feed": "big_chance_team", "field": "big_chances_pg"},
    {"feed": "big_chance_missed_team", "field": "big_chances_missed_pg"},
    {"feed": "touches_in_opp_box_team", "field": "touches_opp_box_pg"},
    {"feed": "accurate_pass_team", "field": "accurate_passes_pg"},
    {"feed": "poss_won_att_3rd_team", "field": "poss_won_att_3rd_pg"},
    {"feed": "saves_team", "field": "saves_pg"},
    {"feed": "interception_team", "field": "interceptions_pg"},
    {"feed": "total_tackle_team", "field": "tackles_pg"},
    {"feed": "effective_clearance_team", "field": "clearances_pg"},
    {"feed": "corner_taken_team", "field": "corners_pg"},
    {"feed": "clean_sheet_team", "field": "clean_sheets"},
    {"feed": "fk_foul_lost_team", "field": "fouls_pg"},
    {"feed": "rating_team", "field": "rating"},
    # --- Phase 1-B: 세트피스 · PK · 카드 · 전개 (전부 시즌 누계/경기당) ---
    {"feed": "_set_piece_goals_team", "field": "set_piece_goals"},
    {"feed": "_set_piece_goals_conceded_team", "field": "set_piece_goals_conceded"},
    {"feed": "penalty_won_team", "field": "penalties_won"},
    {"feed": "penalty_conceded_team", "field": "penalties_conceded"},
    {"feed": "total_yel_card_team", "field": "yellow_cards"},
    {"feed": "total_red_card_team", "field": "red_cards"},
    {"feed": "accurate_cross_team", "field": "accurate_crosses_pg"},
    {"feed": "accurate_long_balls_team", "field": "accurate_long_balls_pg"},
]

# 값으로 쓸 숫자 필드 이름 (앞에 있을수록 우선)
_VALUE_KEY_HINTS = ("statvalue", "value", "statcount", "stat")
# 숫자지만 지표가 아닌 것들
_NOT_VALUE = ("id", "rank", "index", "idx", "order", "position", "minutes",
              "matches", "played", "count")


def _stat_feeds(data: Any) -> dict[str, str]:
    """{피드이름: fetchAllUrl}. 응답이 알려준 URL 을 그대로 쓴다."""
    out: dict[str, str] = {}
    for node in _walk(data):
        name, url = node.get("name"), node.get("fetchAllUrl")
        if isinstance(name, str) and isinstance(url, str) and url.startswith("http"):
            out.setdefault(name, url)
    return out


def _pick_value(node: dict) -> float | None:
    """지표로 보이는 숫자 필드 하나를 고른다."""
    best: tuple[int, float] | None = None
    for key, value in node.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        low = str(key).lower()
        if any(bad in low for bad in _NOT_VALUE):
            continue
        rank = next((i for i, hint in enumerate(_VALUE_KEY_HINTS) if hint in low),
                    len(_VALUE_KEY_HINTS))
        if best is None or rank < best[0]:
            best = (rank, float(value))
    return best[1] if best else None


def _parse_stat_feed(data: Any, resolver: TeamResolver) -> dict[str, float]:
    """통계 피드 → {정규명: 값}.

    피드의 정확한 스키마를 본 적이 없어서 경로를 박지 않는다. '팀 이름으로
    해석되는 문자열 + 지표로 보이는 숫자'를 함께 가진 dict 를 찾는 방식이라
    StatList/TopLists 같은 껍데기 이름이 무엇이든 통과한다.
    """
    out: dict[str, float] = {}
    for node in _walk(data):
        canon = _find_team_name(node, resolver)
        if not canon or canon in out:
            continue
        value = _pick_value(node)
        if value is not None:
            out[canon] = value
    return out


def _find_team_name(node: dict, resolver: TeamResolver) -> str | None:
    """이 dict 가 가리키는 팀. 자기 필드에 없으면 한 단계 아래까지 본다.

    피드에 따라 이름이 같은 층에 있기도 하고
    (`{"ParticiantName": "FC Seoul", "StatValue": 54.2}`),
    한 겹 안에 들어 있기도 하다
    (`{"participant": {"name": "FC Seoul"}, "statValue": 54.2}`).
    """
    for depth, target in ((0, node), *((1, v) for v in node.values()
                                       if isinstance(v, dict))):
        for key, value in target.items():
            if not isinstance(value, str) or len(value) < 2:
                continue
            low = str(key).lower()
            if "name" not in low and "team" not in low and "participant" not in low:
                continue
            # 지표 이름("possession_percentage_team")이 팀명 매칭을 타지 않게 한다
            if "_" in value and " " not in value:
                continue
            canon = resolver.resolve(value, learn=False, quiet=True)
            if canon:
                return canon
        if depth == 0 and _pick_value(node) is None:
            break                       # 값이 없는 껍데기면 더 파고들 이유가 없다
    return None


def read_team_stats(browser: FotMobBrowser, league_data: Any,
                    teams: dict[str, dict], resolver: TeamResolver,
                    feeds: list[dict], league_key: str) -> int:
    """시즌 팀 통계 피드를 받아 teams 의 TeamStats 를 채운다. 채운 지표 수."""
    available = _stat_feeds(league_data)
    if not available:
        log.warning("[%s] FotMob 통계 피드 목록(stats.teams[])이 없습니다.",
                    league_key)
        return 0

    filled = 0
    for spec in feeds:
        feed, field = spec.get("feed"), spec.get("field")
        url = available.get(feed)
        if not url:
            log.debug("[%s] 통계 피드 '%s' 는 이 리그에 없습니다.", league_key, feed)
            continue
        data = browser.get_json(url)
        if data is None:
            log.warning("[%s] 통계 피드 '%s' 를 받지 못했습니다.", league_key, feed)
            continue
        values = _parse_stat_feed(data, resolver)
        if not values:
            log.warning("[%s] 통계 피드 '%s' 에서 팀·값을 찾지 못했습니다 "
                        "(구조가 예상과 다릅니다).", league_key, feed)
            continue
        hit = 0
        for canon, value in values.items():
            entry = teams.get(canon)
            if entry is None:
                continue
            setattr(entry["stats"], field, value)
            hit += 1
        filled += hit
        log.info("[%s] %s → %d팀", league_key, feed, hit)
    return filled


def _parse_matches(data: Any, resolver: TeamResolver) -> list[dict]:
    """경기 목록을 정규명 기준으로 평평하게 만든다."""
    out = []
    for raw in _match_list(data):
        home = resolver.resolve(str(raw["home"].get("name")), learn=False, quiet=True)
        away = resolver.resolve(str(raw["away"].get("name")), learn=False, quiet=True)
        if not home or not away or home == away:
            continue
        hg, ag = _goals(raw)
        out.append({
            # 경기 ID 는 경기 상세(matchDetails)를 부를 때 쓴다
            "id": raw.get("id"),
            "date": _utc_time(raw)[:10],
            "utc": _utc_time(raw),
            "home": home,
            "away": away,
            # 숫자 teamId. 정규명(home/away)과 **다른 식별 체계**라 함께 남긴다 —
            # 슛 계층과 순위표는 이 숫자로 돌고, 팀명으로는 이어지지 않는다.
            "home_id": _int((raw.get("home") or {}).get("id")),
            "away_id": _int((raw.get("away") or {}).get("id")),
            "home_goals": hg,
            "away_goals": ag,
            "finished": _finished(raw) and hg is not None,
        })
    out.sort(key=lambda m: m["utc"], reverse=True)
    return out


def _parse_kickoff(text: str) -> tuple[Any, bool]:
    """(datetime | None, timezone 정보가 있었나).

    FotMob 은 `status.utcTime` 을 ISO 로 준다 — 관찰된 형태는 `...Z` 다.
    파이썬 `fromisoformat` 은 버전에 따라 `Z` 를 못 읽으므로 `+00:00` 으로
    바꿔 준다. **시간대 표시가 없으면 붙이지 않는다** — 임의로 UTC 라고
    단정하면 시점 비교가 조용히 어긋난다. naive 로 두고 그렇다고 표시한다.
    """
    raw = (text or "").strip()
    if not raw:
        return None, False
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None, False
    return dt, dt.tzinfo is not None


def season_matches_from(matches: list[dict], competition: str) -> list[SeasonMatch]:
    """`_parse_matches` 결과 → `SeasonMatch` 목록.

    새로 수집하지 않는다. 이미 받아 둔 리그 응답을 옮겨 담을 뿐이다.
    """
    out = []
    for m in matches:
        mid = m.get("id")
        if not mid:
            # 경기 ID 가 없으면 담지 않는다. 팀명+날짜를 임의의 키로 만들면
            # 나중에 같은 경기가 두 벌로 들어온다.
            continue
        kickoff, aware = _parse_kickoff(m.get("utc", ""))
        out.append(SeasonMatch(
            match_id=str(mid),
            competition=competition,
            kickoff=kickoff, kickoff_raw=str(m.get("utc") or ""),
            kickoff_aware=aware,
            home_team=m.get("home", ""), away_team=m.get("away", ""),
            home_fotmob_id=m.get("home_id"), away_fotmob_id=m.get("away_id"),
            home_goals=m.get("home_goals"), away_goals=m.get("away_goals"),
            finished=bool(m.get("finished")),
        ))
    return out


# --------------------------------------------------------------------------
# 경기 상세 (matchDetails) — 시즌 통계에 없는 지표는 여기에만 있다
# --------------------------------------------------------------------------
MATCH_PATH = "/api/data/matchDetails?matchId={id}"

# FotMob 경기 스탯 키 → (우리 필드 접미사, 상대편 값도 쓰는가)
# Phase 0 [8] 출력에서 실물로 확인한 키만 적는다. 값은 [홈, 원정] 2원소다.
_MATCH_STAT_KEYS = {
    "expected_goals_non_penalty": ("npxg", True),      # npxG / npxGA
    "expected_goals_on_target": ("xgot", True),        # xGOT / xGOT against
    "expected_goals_open_play": ("xg_open_play", False),
    "expected_goals_set_play": ("xg_set_play", False),
    "total_shots": ("shots", True),                    # 슈팅 / 피슈팅
    "ShotsOnTarget": ("shots_on_target", True),
    "shots_inside_box": ("shots_inside_box", False),
    "shots_outside_box": ("shots_outside_box", False),
}
# 상대편 값을 담는 필드 이름 (…_against_recent)
_AGAINST_FIELD = {"npxg": "npxga", "xgot": "xgot_against",
                  "shots": "shots_against",
                  "shots_on_target": "shots_on_target_against"}

_PCT_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _stat_number(value: Any) -> float | None:
    """경기 스탯 한 칸을 숫자로. '57%' · '12 (30%)' 같은 표기도 받는다."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _PCT_RE.search(str(value))
    return float(m.group()) if m else None


def _all_period(data: Any) -> Any:
    """기간별 표가 여럿이면 '전체 경기' 표만 돌려준다.

    경로 이름이 `content.stats.Periods.All` — **Periods 는 복수형이고**
    전·후반 표가 함께 온다. 전체를 훑으면 `_walk` 가 스택(LIFO)이라 순회
    순서가 문서 순서와 달라, `setdefault` 가 하프 값을 먼저 잡을 수 있다.
    그러면 npxG·슈팅이 한 하프치만 담겨 조용히 절반이 된다 — 260048 실행에서
    'npxG 대조 최대 차이 3.03' 으로 드러난 증상이 이것이다.

    'All' 을 찾지 못하면 None 을 돌려주고 호출부가 전체를 훑는다. 기간 구분이
    없는 응답에서도 그대로 동작해야 하기 때문이다.
    """
    for node in _walk(data):
        periods = node.get("Periods")
        if not isinstance(periods, dict) or not periods:
            continue
        whole = periods.get("All")
        if isinstance(whole, dict):
            return whole
        if len(periods) == 1:                       # 이름이 달라도 하나뿐이면 그것
            only = next(iter(periods.values()))
            if isinstance(only, dict):
                return only
    return None


def _match_stat_pairs(data: Any) -> dict[str, tuple[float | None, float | None]]:
    """{FotMob 키: (홈 값, 원정 값)}.

    경로가 아니라 모양으로 찾는다 — `key` 가 문자열이고 `stats` 가 **스칼라
    2개**인 dict 가 지표 한 줄이다. 그룹 dict 도 `key`/`stats` 를 갖지만
    그쪽 `stats` 는 dict 목록이라 걸러진다.

    단, 기간(Periods)만은 모양으로 가리지 못한다 — 전반 표와 전체 표가
    똑같이 생겼기 때문이다. 그래서 '전체' 표를 먼저 골라내고 그 안에서만 찾는다.
    """
    out: dict[str, tuple[float | None, float | None]] = {}
    scope = _all_period(data)
    for node in _walk(data if scope is None else scope):
        key, vals = node.get("key"), node.get("stats")
        if not isinstance(key, str) or not isinstance(vals, list) or len(vals) != 2:
            continue
        if any(isinstance(v, (dict, list)) for v in vals):
            continue                                   # 그룹 dict
        home, away = _stat_number(vals[0]), _stat_number(vals[1])
        if home is None and away is None:
            continue
        out.setdefault(key, (home, away))
    return out


def _shotmap(data: Any) -> list:
    """경기 전체 슛맵 배열. 후보가 여럿이면 가장 긴 것.

    `_walk` 는 스택이라 순서를 보장하지 않는다. 선수별로 쪼개진 부분 목록을
    먼저 잡으면 합계가 조용히 모자라므로, 가장 긴 목록 하나만 쓴다.
    """
    best: list = []
    for node in _walk(data):
        shots = node.get("shots")
        if not isinstance(shots, list) or len(shots) <= len(best):
            continue
        if not (isinstance(shots[0], dict) and "teamId" in shots[0]):
            continue
        best = shots
    return best


def _home_away_ids(data: Any) -> tuple[int | None, int | None]:
    """응답 안에서 홈·원정 팀 ID 를 찾는다. 없으면 (None, None).

    경로를 박지 않고 모양으로 찾는다 — `homeTeam`/`awayTeam` 을 **둘 다**
    dict 로 갖고 각각 `id` 가 있는 노드. 못 찾으면 호출부가 순위표 쪽
    매핑으로 넘어간다. 배열 순서([0]/[1])는 여기서 쓰지 않는다.
    """
    for node in _walk(data):
        home, away = node.get("homeTeam"), node.get("awayTeam")
        if not (isinstance(home, dict) and isinstance(away, dict)):
            continue
        hid, aid = _int(home.get("id")), _int(away.get("id"))
        if hid is not None and aid is not None and hid != aid:
            return hid, aid
    return None, None


def _shot_totals(data: Any) -> dict[int, dict[str, float]]:
    """슛맵을 팀 ID 별로 합산한다 (경기 스탯과 대조할 검증용).

    `situation == "Penalty"` 를 빼면 npxG 가 된다 — PK 를 상수(0.76)로
    빼는 추정이 아니라 실제 슛 단위 분류를 쓴다.
    """
    out: dict[int, dict[str, float]] = {}
    for shot in _shotmap(data):
        if not isinstance(shot, dict):
            continue
        tid = shot.get("teamId")
        if not isinstance(tid, int):
            continue
        acc = out.setdefault(tid, {"shots": 0.0, "on_target": 0.0,
                                   "xg": 0.0, "npxg": 0.0, "xgot": 0.0})
        acc["shots"] += 1
        # 블록된 슛은 유효슈팅에서 뺀다. FotMob 의 isOnTarget 은 블록에도
        # true 로 오는데, 경기 스탯의 ShotsOnTarget 은 블록을 제외한다
        # (260048 실물 6쌍에서 확인 — 빼야 정확히 일치).
        if shot.get("isOnTarget") and not shot.get("isBlocked"):
            acc["on_target"] += 1
        xg = _float(shot.get("expectedGoals")) or 0.0
        acc["xg"] += xg
        if str(shot.get("situation") or "").lower() != "penalty":
            acc["npxg"] += xg
        acc["xgot"] += _float(shot.get("expectedGoalsOnTarget")) or 0.0
    return out


def read_match_details(browser: FotMobBrowser, match: dict, cache=None) -> dict | None:
    """경기 1건의 팀별 지표. {"home": {...}, "away": {...}, "check": {...}}

    `check` 는 슛맵 합산값이다. 경기 스탯과 다를 수 있으므로 **억지로 맞추지
    않고** 차이를 기록만 한다.
    """
    mid = match.get("id")
    if not mid:
        return None
    cached = cache.get("fotmob", f"match_{mid}") if cache else None
    if cached is not None:
        return cached or None

    data = browser.get_json(browser.abs_url(MATCH_PATH.format(id=mid)))
    if data is None:
        return None

    pairs = _match_stat_pairs(data)
    events = shots.parse_shot_events(_shotmap(data), str(mid))
    if not pairs and not events:
        log.debug("경기 %s: 스탯 표도 슛맵도 찾지 못했습니다.", mid)
        if cache:
            cache.set("fotmob", f"match_{mid}", {})    # 재요청 방지
        return None

    sides: dict[str, dict[str, float]] = {"home": {}, "away": {}}
    for key, (suffix, has_against) in _MATCH_STAT_KEYS.items():
        pair = pairs.get(key)
        if pair is None:
            continue
        home, away = pair
        if home is not None:
            sides["home"][suffix] = home
        if away is not None:
            sides["away"][suffix] = away
        if has_against:
            against = _AGAINST_FIELD[suffix]
            if away is not None:
                sides["home"][against] = away          # 홈의 피지표 = 원정 값
            if home is not None:
                sides["away"][against] = home

    deduped, dropped = shots.dedupe(events)
    if dropped:
        log.debug("경기 %s: 중복 슛 %d개를 걸렀습니다.", mid, dropped)
    hid, aid = _home_away_ids(data)
    payload = {
        "home": sides["home"], "away": sides["away"],
        "check": _shot_totals(data),
        # Phase 1-C: 슛 이벤트 원본을 정규화해 그대로 보관한다. 집계는 뒤에서
        # 하고, 여기서는 잃지 않는 것이 목적이다 (Phase 2·3 이 이걸 쓴다).
        "shots": [asdict(e) for e in deduped],
        "team_ids": {"home": hid, "away": aid},
        "stat_values": {m: pairs[k][0] if k in pairs else None
                        for m, k in shots.RECONCILE.items()},
        "stat_values_away": {m: pairs[k][1] if k in pairs else None
                             for m, k in shots.RECONCILE.items()},
    }
    if cache:
        cache.set("fotmob", f"match_{mid}", payload)
    return payload


def _check_for(check: Any, fotmob_id: Any) -> dict | None:
    """슛맵 합산에서 이 팀의 칸을 꺼낸다.

    `_shot_totals` 는 teamId 를 **int** 키로 담지만, 캐시를 거치면 JSON 이
    키를 문자열로 바꿔 놓는다. 둘 다 받는다.
    """
    if not isinstance(check, dict) or fotmob_id in (None, ""):
        return None
    found = check.get(str(fotmob_id))
    if found is None:
        try:
            found = check.get(int(fotmob_id))
        except (TypeError, ValueError):
            return None
    return found if isinstance(found, dict) else None


def _recent_finished(matches: list[dict], canon: str, count: int) -> list[dict]:
    """이 팀의 최근 종료 경기 N건 (최신순). id 가 있는 것만."""
    out = []
    for m in matches:
        if not m.get("finished") or not m.get("id"):
            continue
        if canon not in (m["home"], m["away"]):
            continue
        out.append(m)
        if len(out) >= count:
            break
    return out


def attach_match_details(browser: FotMobBrowser, teams: dict[str, dict],
                         matches: list[dict], count: int,
                         league_key: str, cache=None,
                         windows: list[int] | None = None) -> tuple[int, int]:
    """최근 N경기 상세를 받아 팀별로 합산한다. (채운 팀 수, 받은 경기 수).

    시즌 통계 29종에 없는 지표(npxG·xGOT·총슈팅·피슈팅·박스 안팎)는 경기
    상세에만 있다. 경기당 요청 1회가 들지만 같은 경기를 두 팀이 공유하므로
    캐시로 중복을 없앤다.
    """
    if count <= 0 or not teams:
        return 0, 0

    wanted: dict[str, list[dict]] = {
        canon: _recent_finished(matches, canon, count) for canon in teams}
    unique = {m["id"]: m for ms in wanted.values() for m in ms}
    if not unique:
        log.info("[%s] 종료된 경기가 없어 경기 상세를 건너뜁니다.", league_key)
        return 0, 0

    log.info("[%s] 경기 상세 %d경기 수집 (팀당 최근 %d경기)",
             league_key, len(unique), count)
    details: dict[Any, dict] = {}
    for mid, match in unique.items():
        payload = read_match_details(browser, match, cache=cache)
        if payload is not None:
            details[mid] = payload

    filled = 0
    # (차이, 팀, 경기id). 슛맵 합산과 경기 스탯을 대조하는 진단용이며 저장하는
    # 값에는 영향을 주지 않는다.
    diffs: list[tuple[float, str, Any]] = []
    xgot_diffs: list[tuple[float, str, Any]] = []
    for canon, entry in teams.items():
        stats, sampled = entry["stats"], 0
        acc: dict[str, float] = {}
        # 지표별로 '실제로 값이 있던 경기 수' 를 따로 센다. 어떤 경기에 npxG 가
        # 빠져 있으면 그 지표만 표본이 작아지는데, 전부 sampled 로 나누면
        # 빠진 경기를 0 으로 친 셈이 돼 값이 조용히 낮아진다.
        seen: dict[str, int] = {}
        for match in wanted.get(canon, []):
            payload = details.get(match["id"])
            if payload is None:
                continue
            side = "home" if match["home"] == canon else "away"
            values = payload.get(side) or {}
            if not values:
                continue
            sampled += 1
            for name, value in values.items():
                acc[name] = acc.get(name, 0.0) + value
                seen[name] = seen.get(name, 0) + 1
            # 슛맵 합산과 경기 스탯의 차이를 기록 (맞추지 않는다)
            check = _check_for(payload.get("check"), entry.get("fotmob_id"))
            if check:
                # 부호를 살려 둔다. 전부 한쪽으로 쏠리면 계통 오차(예: 하프
                # 표를 읽음)이고, 부호가 섞이면 개별 경기 편차다.
                for metric, store in (("npxg", diffs), ("xgot", xgot_diffs)):
                    if values.get(metric) is None:
                        continue
                    store.append((check.get(metric, 0.0) - values[metric],
                                  canon, match["id"]))
        if not sampled:
            continue
        stats.recent_matches = sampled
        stats.recent_counts = {f"{n}_recent": c for n, c in seen.items()}
        for name, total in acc.items():
            setattr(stats, f"{name}_recent", total)
        filled += 1
        short = {n: c for n, c in seen.items() if c < sampled}
        if short:
            log.info("[%s] %s: 일부 지표가 경기 수보다 적은 표본입니다 "
                     "(경기 %d개 중 %s) — 그 지표는 있는 경기 수로만 나눕니다.",
                     league_key, canon, sampled,
                     ", ".join(f"{n} {c}" for n, c in sorted(short.items())))

    _log_reconciliation(league_key, "npxG", diffs)
    _log_reconciliation(league_key, "xGOT", xgot_diffs)
    _attach_shot_aggregates(details, teams, wanted, league_key,
                            windows or [3, 5, 6, 10])
    return filled, len(details)


def _shot_windows(settings: Settings) -> list[int]:
    """집계할 최근 N 목록. 하드코딩하지 않고 설정에서 읽는다."""
    raw = (settings.fotmob or {}).get("shot_recent_windows") or [3, 5, 6, 10]
    out = sorted({int(w) for w in raw if int(w) > 0})
    return out or [6]


def _resolve_sides(payload: dict, match: dict,
                   teams: dict[str, dict]) -> tuple[int | None, int | None]:
    """(홈 팀ID, 원정 팀ID). 배열 순서는 쓰지 않는다.

    1) 경기 상세 응답이 직접 알려 준 값 (`homeTeam`/`awayTeam` 의 id)
    2) 없으면 순위표에서 얻은 팀ID 를 경기 목록의 홈/원정 이름으로 찾는다

    둘 다 없으면 (None, None) — 그 경기는 홈/원정 분리 집계에서 빠지고,
    전체 집계에는 그대로 들어간다.
    """
    ids = payload.get("team_ids") or {}
    hid, aid = _int(ids.get("home")), _int(ids.get("away"))
    if hid is not None and aid is not None:
        return hid, aid
    hid = _int((teams.get(match.get("home")) or {}).get("fotmob_id"))
    aid = _int((teams.get(match.get("away")) or {}).get("fotmob_id"))
    return hid, aid


def _attach_shot_aggregates(details: dict, teams: dict[str, dict],
                            wanted: dict[str, list[dict]], league_key: str,
                            windows: list[int]) -> None:
    """슛 이벤트를 경기별 → 팀별 → 최근 N경기로 집계해 팀에 붙인다 (Phase 1-C).

    결과는 `entry["shot_aggregates"]` 에 들어간다. 리포트는 아직 쓰지 않고,
    Phase 2·3 이 쓸 데이터 기반이다. 여기서 TeamStats 를 건드리지 않으므로
    기존 지표와 리포트에는 영향이 없다.
    """
    # 1) 경기별 × 팀별 집계
    per_match: dict[Any, dict[int, shots.MatchShotAggregate]] = {}
    broken: list[str] = []
    recon: dict[str, list[float]] = {}
    for canon, ms in wanted.items():
        for match in ms:
            mid = match["id"]
            if mid in per_match:
                continue                          # 같은 경기를 두 번 집계하지 않는다
            payload = details.get(mid)
            if not payload or not payload.get("shots"):
                continue
            events = [shots.ShotEvent(**d) for d in payload["shots"]]
            hid, aid = _resolve_sides(payload, match, teams)
            aggs = shots.aggregate_match(events, hid, aid)
            per_match[mid] = aggs
            for tid, agg in aggs.items():
                bad = shots.validate(agg)
                if bad:
                    broken.append(f"경기 {mid} 팀 {tid}: {'; '.join(bad)}")
                side = ("stat_values" if agg.is_home is True
                        else "stat_values_away" if agg.is_home is False else None)
                if side:
                    vals = {k: v for k, v in (payload.get(side) or {}).items()
                            if v is not None}
                    for metric, diff in shots.reconcile(agg, vals).items():
                        recon.setdefault(metric, []).append(diff)
    if not per_match:
        return

    # 2) 팀별 최근 N경기 (전체 / 홈 / 원정)
    filled = 0
    empty_sides = 0       # 상대가 0슛이라 슛맵에 없던 경기 수
    for canon, entry in teams.items():
        tid = _int(entry.get("fotmob_id"))
        if tid is None:
            continue
        ordered = [per_match[m["id"]][tid]
                   for m in wanted.get(canon, [])
                   if m["id"] in per_match and tid in per_match[m["id"]]]
        if not ordered:
            continue
        entry["shot_aggregates"] = shots.aggregate_windows(ordered, tid, windows)
        entry["shot_matches"] = ordered
        # Phase 2-C: **상대 팀의 같은 경기 집계**. `per_match[mid]` 는 양 팀을
        # 다 갖고 있는데 지금까지 자기 것만 꺼내 쓰고 버렸다. 상대가 그 경기에
        # 몇 슛을 쳤는지 없이는 피슛·npxGA·피xGOT 를 만들 수 없다.
        # 상대 팀 ID 는 `opponent_id`(P0-1)가 들고 있다 — 팀명으로 찾지 않는다.
        opponents = []
        for agg in ordered:
            opp_id = agg.opponent_id
            if opp_id is None:
                continue                      # 상대를 모르면 담지 않는다
            side = per_match.get(agg.match_id) or {}
            opp = side.get(opp_id)
            if opp is None:
                # 상대가 **0슛**이면 슛맵에 나타나지 않는다. 그 경기를 버리면
                # 가장 잘 막은 경기가 표본에서 사라져 피슛이 위로 치우친다.
                opp = shots.empty_aggregate(
                    agg.match_id, opp_id,
                    is_home=(None if agg.is_home is None else not agg.is_home),
                    opponent_id=tid)
                empty_sides += 1
            opponents.append(opp)
        entry["opponent_matches"] = opponents
        filled += 1

    log.info("[%s] 슛 이벤트 계층: 경기 %d개 · 팀 %d개 · 창 %s",
             league_key, len(per_match), filled,
             "/".join(str(w) for w in windows))
    if empty_sides:
        log.info("[%s] 상대가 0슛이라 슛맵에 없던 팀-경기 %d건 — "
                 "0으로 채워 수비 표본에 넣었습니다", league_key, empty_sides)
    if broken:
        log.warning("[%s] 슛 집계 불변조건 위반 %d건: %s", league_key,
                    len(broken), " | ".join(broken[:3]))
    # 3) 경기 스탯과의 대조 — 위의 npxG·xGOT 줄이 다루지 않는 지표만
    extra = [m for m in ("xg", "shots", "shots_on_target",
                         "shots_inside_box", "shots_outside_box") if m in recon]
    if extra:
        parts = []
        for m in extra:
            v = recon[m]
            parts.append(f"{m} 평균 {sum(v)/len(v):+.2f}/최대 "
                         f"{max(v, key=abs):+.2f}")
        log.info("[%s] 슛맵−경기스탯 대조 (표본 %d): %s — 값은 맞추지 않습니다.",
                 league_key, len(recon[extra[0]]), " · ".join(parts))


def _log_reconciliation(league_key: str, label: str,
                        diffs: list[tuple[float, str, Any]]) -> None:
    """슛맵 합산과 경기 스탯의 차이를 요약해 남긴다 (진단용).

    최대값만 적으면 '한 경기가 튀는 것'과 '전부 어긋나는 것'을 구분할 수
    없다. 260048 실행에서 최대 3.03 만 보고는 원인을 좁히지 못했다. 부호를
    살린 평균·중앙값이 있어야 계통 오차인지 개별 편차인지 갈린다.
    """
    if not diffs:
        return
    vals = sorted(d for d, _, _ in diffs)
    n = len(vals)
    mean = sum(vals) / n
    median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    worst = max(diffs, key=lambda x: abs(x[0]))
    positive = sum(1 for d in vals if d > 0.05)
    log.info("[%s] %s 대조 (슛맵 합산 − 경기스탯, 표본 %d): "
             "평균 %+.2f · 중앙값 %+.2f · 최대 %+.2f (%s, 경기 %s) · "
             "슛맵이 더 큰 경우 %d/%d — 값은 경기스탯을 그대로 씁니다.",
             league_key, label, n, mean, median, worst[0], worst[1], worst[2],
             positive, n)
    if abs(mean) > 0.30:
        log.warning("[%s] %s 대조 차이가 한쪽으로 쏠려 있습니다 (평균 %+.2f). "
                    "개별 경기 편차가 아니라 계통 오차일 수 있습니다 — "
                    "경기 스탯에서 전체(All) 표가 아니라 하프 표를 읽고 "
                    "있는지부터 확인하세요.", league_key, label, mean)


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
    # 여러 리그 목록을 합쳐 넘길 수 있어(컵대회) 여기서 다시 최신순으로
    # 정렬하고, 같은 경기가 두 리그 응답에 실린 경우를 걸러낸다.
    seen: set[tuple] = set()
    for m in sorted(matches, key=lambda x: x.get("utc", ""), reverse=True):
        if not m["finished"] or {m["home"], m["away"]} != pair:
            continue
        key = (m["home"], m["away"], m.get("utc", ""))
        if key in seen:
            continue
        seen.add(key)
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
                # Phase 1-C 슛 계층. 캐시에 남기지 않으면 같은 날 재실행에서
                # 통째로 사라진다 (경기 상세를 다시 받지 않으므로).
                "shot_aggregates": {k: asdict(v) for k, v
                                    in (entry.get("shot_aggregates") or {}).items()},
                "shot_matches": [asdict(m) for m
                                 in (entry.get("shot_matches") or [])],
                # Phase 2-C: 상대 팀의 같은 경기 집계. 캐시에 안 남기면
                # 같은 날 재실행에서 수비 지표가 통째로 사라진다.
                "opponent_matches": [asdict(m) for m
                                     in (entry.get("opponent_matches") or [])],
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
                "shot_aggregates": {
                    k: shots.RecentShotAggregate(**v)
                    for k, v in (entry.get("shot_aggregates") or {}).items()},
                "shot_matches": [shots.MatchShotAggregate(**m)
                                 for m in (entry.get("shot_matches") or [])],
                "opponent_matches": [
                    shots.MatchShotAggregate(**m)
                    for m in (entry.get("opponent_matches") or [])],
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
def enrich(matches, settings: Settings, resolver: TeamResolver, cache=None,
           season_out: list | None = None) -> str:
    """모든 경기에 FotMob 데이터를 붙인다. 반환값은 상태 문자열.

    이미 프로필이 있으면(다른 소스가 먼저 채웠으면) 빈 칸만 메운다.

    `season_out` 을 주면 받아 온 리그의 **시즌 경기 목록**을 거기에 담는다
    (Phase 2 의 시점별 분석용). 반환형을 바꾸지 않으려고 out-파라미터로 뒀다 —
    whoscored.enrich 와 시그니처를 맞춰 두는 편이 호출부가 단순하다.
    새로 수집하지 않고 이미 받은 응답을 옮겨 담을 뿐이다.
    """
    # 경기의 리그만 받으면 컵대회에서 구멍이 난다. 부천(K2) vs 전북(K1) 같은
    # 경기는 match.league 가 홈팀 기준으로 하나만 정해지는데, 그러면 원정팀은
    # 그 리그 순위표에 없어서 통째로 빈칸이 된다. 그래서 **등장하는 모든 팀의
    # 소속 리그**를 함께 받는다.
    leagues = {m.league for m in matches if m.league}
    for match in matches:
        for ref in (match.home, match.away):
            own = resolver.league_of(ref.canonical) if ref.canonical else None
            if own:
                leagues.add(own)
    leagues = sorted(k for k in leagues if k in settings.leagues)
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

    # 시즌 경기 색인 (Phase 2). 같은 경기가 두 리그 피드에 겹쳐 실릴 수 있어
    # match_id 로 한 번만 담고, kickoff 오름차순으로 정렬해 둔다.
    if season_out is not None:
        seen_ids = {sm.match_id for sm in season_out}
        for league_key in leagues:
            for sm in season_matches_from(
                    (data.get(league_key) or {}).get("matches", []), league_key):
                if sm.match_id in seen_ids:
                    continue
                seen_ids.add(sm.match_id)
                season_out.append(sm)
        season_out.sort(key=lambda x: x.sort_key)
        no_time = sum(1 for sm in season_out if sm.kickoff is None)
        log.info("시즌 경기 색인 %d경기 (종료 %d) — Phase 2 시점 분석용%s",
                 len(season_out), sum(1 for sm in season_out if sm.finished),
                 f", 시각 해석 실패 {no_time}건" if no_time else "")

    # 팀 → 항목 통합 색인. 어느 리그에서 왔든 팀만 알면 찾을 수 있게 한다.
    index: dict[str, dict] = {}
    for league_key in leagues:
        for canon, entry in (data.get(league_key) or {}).get("teams", {}).items():
            index.setdefault(canon, entry)

    # 순위표에 실제로 올라 있는 리그로 소속을 정정한다. 승강이 반영되지 않은
    # 표는 배당 조회를 통째로 엉뚱한 리그로 보낸다(2026 시즌 대구·수원FC·
    # 인천·부천이 그랬다).
    moved = 0
    for league_key in leagues:
        for canon in (data.get(league_key) or {}).get("teams", {}):
            if resolver.set_league(canon, league_key):
                moved += 1
    if moved:
        for match in matches:
            own = (resolver.league_of(match.home.canonical)
                   if match.home.canonical else None)
            if own and own != match.league:
                match.league = own
                match.league_ko = settings.league_ko(own)
            # 승강 반영 전에 붙은 '컵대회로 보인다' 경고는 근거가 사라졌다.
            # (부천 vs 전북은 둘 다 K리그1 이라 컵대회가 아니었다.)
            match.notes = [n for n in match.notes
                           if not n.startswith("두 팀의 소속 리그가 다릅니다")]
            lh = (resolver.league_of(match.home.canonical)
                  if match.home.canonical else None)
            la = (resolver.league_of(match.away.canonical)
                  if match.away.canonical else None)
            if lh and la and lh != la:
                match.notes.append(
                    f"두 팀의 소속 리그가 다릅니다 ({settings.league_ko(lh)} vs "
                    f"{settings.league_ko(la)}) — 컵대회 경기로 보이며, "
                    f"배당률·순위 데이터가 없을 수 있습니다.")
        log.info("소속 리그 %d팀을 순위표 기준으로 정정했습니다.", moved)

    for match in matches:
        league = data.get(match.league) or {"teams": {}, "matches": []}
        for side in ("home", "away"):
            ref: TeamRef = getattr(match, side)
            profile = getattr(match, f"{side}_profile") or TeamProfile(
                team=ref, league=match.league)
            entry = index.get(ref.canonical) if ref.canonical else None
            if entry:
                fill_stats(profile.stats, entry["stats"])
                profile.source_ok = True
                stats_done += 1
                if entry.get("form") and not profile.form:
                    profile.form = list(entry["form"])
                    form_done += 1
                if entry.get("fotmob_id"):
                    ref.fotmob_id = entry["fotmob_id"]
                if entry.get("shot_aggregates") and not profile.shot_aggregates:
                    profile.shot_aggregates = entry["shot_aggregates"]
                if entry.get("shot_matches") and not profile.shot_matches:
                    # 경기별 원재료. 2-B 의 비율 지표가 지표를 가로질러 표본을
                    # 맞추려면 창의 합계만으로는 안 되고 이게 있어야 한다.
                    profile.shot_matches = list(entry["shot_matches"])
                if entry.get("opponent_matches") and not profile.opponent_matches:
                    # 2-C 수비 지표의 원재료 — 상대가 그 경기에 무엇을 했나.
                    profile.opponent_matches = list(entry["opponent_matches"])
            setattr(match, f"{side}_profile", profile)

        if match.home.canonical and match.away.canonical and not match.h2h.entries:
            # 컵대회는 두 팀의 리그가 달라, 어느 쪽 경기 목록에 실려 있을지
            # 모른다. 받아 둔 리그를 전부 뒤진다.
            pool = list(league["matches"])
            for other in leagues:
                if other != match.league:
                    pool.extend((data.get(other) or {}).get("matches", []))
            h2h = build_h2h(pool, match.home.canonical, match.away.canonical,
                            limit=int(settings.whoscored.get("h2h_count", 10)))
            if h2h.entries:
                match.h2h = h2h
                h2h_done += 1

    total = len(matches) * 2
    if stats_done == 0:
        return "실패 (수집 0팀)"
    detail = f"{stats_done}/{total}팀 지표, {form_done}팀 폼, {h2h_done}경기 상대전적"
    return (f"ok ({detail})" if stats_done == total else f"부분 ({detail})")
