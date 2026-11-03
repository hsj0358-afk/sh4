"""FotMob 경기별 기록 — 예측 모델 경기장의 xG·경기 내용 자료 (§1-68).

football-data.co.uk(§1-67)에는 슈팅까지만 있고 **경기별 xG 가 없다**(2026/27
부터만 있다). FotMob 경기 상세(`matchDetails`)에는 경기마다 xG·npxG·xGOT·
빅찬스·상대 박스 터치·점유율과 선발 명단(선수 평점)이 있다. 이 모듈이 그것을
**과거 시즌까지** 모아 작은 레코드로 남긴다.

실물로 확인한 범위 (2026-11-03):

| 리그 | FotMob id | 경기별 xG 가 있는 첫 시즌 |
|---|---|---|
| EPL · 라리가 · 분데스리가 · 세리에A · 리그앙 | 47 · 87 · 54 · 55 · 53 | 2020/2021 (그 전은 `coverageLevel` ratings/lower) |
| J리그 | 223 | 2022 |
| K리그1 | 9080 | 2022 |
| K리그2 | 9116 | 없음 (ratings 까지) |

- **파서를 새로 쓰지 않는다.** 경기 스탯은 운영 코드의
  `fotmob._match_stat_pairs()`(전체 기간 표만 읽는다, §1-1-2)를, 홈/원정
  팀 ID 는 `_home_away_ids()` 를 그대로 부른다.
- **원본을 쌓지 않는다.** 경기 하나가 200~300KB 라 수만 경기면 수 GB 다.
  필요한 칸만 뽑은 레코드(경기당 수 KB)를 `cache/history/fotmob/<리그>/
  <시즌>.jsonl.gz` 에 남긴다. 이미 받은 경기는 다시 받지 않는다(재개).
- **없는 값을 0 으로 채우지 않는다.** xG 가 없는 경기(`coverageLevel` 이
  xG 가 아닌 경기)는 그 칸이 `None` 이다.
- 회차 수집 경로가 아니다 (§1-1). 경기장과 모델 갱신만 쓴다.
"""
from __future__ import annotations

import gzip
import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .settings import ROOT

log = logging.getLogger(__name__)

BASE = "https://www.fotmob.com"
LEAGUE_PATH = "/api/data/leagues?id={id}"
MATCH_PATH = "/api/data/matchDetails?matchId={id}"
CACHE_DIR = ROOT / "cache" / "history" / "fotmob"

# 실물 응답의 details.name·country 로 확인한 값만 적는다 (§1-1-1).
LEAGUES = {
    "epl": (47, 2020),
    "laliga": (87, 2020),
    "bundesliga": (54, 2020),
    "seriea": (55, 2020),
    "ligue1": (53, 2020),
    "jleague": (223, 2022),
    "kleague1": (9080, 2022),
}

# 경기 스탯 키 → 레코드 칸. 값은 [홈, 원정].
STAT_KEYS = {
    "expected_goals": "xg",
    "expected_goals_non_penalty": "npxg",
    "expected_goals_on_target": "xgot",
    "expected_goals_open_play": "xg_op",
    "expected_goals_set_play": "xg_sp",
    "total_shots": "shots",
    "ShotsOnTarget": "sot",
    "shots_inside_box": "shots_box",
    "big_chance": "big_chances",
    "big_chance_missed_title": "big_missed",
    "touches_opp_box": "touches_box",
    "BallPossesion": "possession",
    "corners": "corners",
    "red_cards": "red_cards",
    "passes": "passes",
}


def season_start(season: str) -> int:
    """'2020/2021' → 2020 · '2022' → 2022."""
    try:
        return int(str(season)[:4])
    except ValueError:
        return 0


# --------------------------------------------------------------------------
# 받기
# --------------------------------------------------------------------------
class Fetcher:
    """평범한 HTTPS 로 받는다. 요청 사이에 간격을 둔다 (스레드 공용)."""

    def __init__(self, delay: float = 0.4, timeout: float = 30.0, retries: int = 2):
        self.delay, self.timeout, self.retries = delay, timeout, retries
        self._lock = threading.Lock()
        self._next = 0.0
        self.requests = 0

    def _wait(self):
        with self._lock:
            now = time.monotonic()
            at = max(now, self._next)
            self._next = at + self.delay
        if at > now:
            time.sleep(at - now)

    def get_json(self, path: str):
        url = BASE + path
        last = None
        for attempt in range(self.retries + 1):
            self._wait()
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; toto-history/1)",
                    "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    self.requests += 1
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:                       # noqa: BLE001
                last = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"{url}: {type(last).__name__}: {last}")


def league_seasons(fetcher: Fetcher, league_id: int) -> list:
    data = fetcher.get_json(LEAGUE_PATH.format(id=league_id))
    return list(data.get("allAvailableSeasons") or [])


def season_fixtures(fetcher: Fetcher, league_id: int, season: str) -> tuple:
    """(끝난 경기 목록, 받은 시즌 이름). 받은 시즌이 요청과 다르면 빈 목록이다 (§1-33)."""
    path = (LEAGUE_PATH.format(id=league_id) + "&season="
            + urllib.parse.quote(season, safe=""))
    data = fetcher.get_json(path)
    got = (data.get("details") or {}).get("selectedSeason") or ""
    if got != season:
        return [], got
    out = []
    for m in (data.get("fixtures") or {}).get("allMatches") or []:
        st = m.get("status") or {}
        if st.get("finished") and not st.get("cancelled") and not st.get("awarded"):
            out.append(m)
    return out, got


# --------------------------------------------------------------------------
# 레코드
# --------------------------------------------------------------------------
def _num(v):
    from .sources.fotmob import _stat_number
    return _stat_number(v)


def _players(team: dict) -> dict:
    """선발·교체로 뛴 선수의 (id, 평점, 들어온/나간 분)."""
    out = {"starters": [], "subs": []}
    for p in team.get("starters") or []:
        perf = p.get("performance") or {}
        off = next((e.get("time") for e in perf.get("substitutionEvents") or []
                    if e.get("type") == "subOut"), None)
        out["starters"].append([p.get("id"), perf.get("rating"), off,
                                p.get("usualPlayingPositionId")])
    for p in team.get("subs") or []:
        perf = p.get("performance") or {}
        on = next((e.get("time") for e in perf.get("substitutionEvents") or []
                   if e.get("type") == "subIn"), None)
        if on is not None:
            out["subs"].append([p.get("id"), perf.get("rating"), on,
                                p.get("usualPlayingPositionId")])
    return out


def compact(detail: dict, fixture: dict, league: str, season: str) -> dict:
    """경기 상세 → 작은 레코드. 운영 파서(`_match_stat_pairs`)를 그대로 쓴다."""
    from .sources import fotmob

    general = detail.get("general") or {}
    pairs = fotmob._match_stat_pairs(detail)
    stats = {}
    for key, name in STAT_KEYS.items():
        if key in pairs:
            stats[name] = list(pairs[key])
    hid, aid = fotmob._home_away_ids(detail)
    home = fixture.get("home") or {}
    away = fixture.get("away") or {}
    score = None
    teams = (detail.get("header") or {}).get("teams") or []
    if len(teams) == 2 and all(isinstance(t.get("score"), int) for t in teams):
        score = [teams[0]["score"], teams[1]["score"]]
    lineup = (detail.get("content") or {}).get("lineup") or {}
    lu = {}
    for side in ("homeTeam", "awayTeam"):
        t = lineup.get(side) or {}
        if not t:
            continue
        lu[side[:4]] = {
            "id": t.get("id"), "rating": t.get("rating"),
            "formation": t.get("formation"),
            "value": t.get("totalStarterMarketValue"),
            "age": t.get("averageStarterAge"),
            "coach": (t.get("coach") or {}).get("id"),
            "unavailable": [[u.get("id"), (u.get("unavailability") or {}).get("type")
                             if isinstance(u.get("unavailability"), dict) else None]
                            for u in t.get("unavailable") or []],
            **_players(t)}
    return {
        "id": str(fixture.get("id") or general.get("matchId")),
        "league": league, "season": season,
        "utc": (fixture.get("status") or {}).get("utcTime")
               or general.get("matchTimeUTCDate"),
        "home": {"id": home.get("id"), "name": home.get("name")},
        "away": {"id": away.get("id"), "name": away.get("name")},
        "detail_ids": [hid, aid],
        "score": score,
        "coverage": general.get("coverageLevel"),
        "stats": stats,
        "lineup": lu,
    }


# --------------------------------------------------------------------------
# 저장
# --------------------------------------------------------------------------
def _season_file(league: str, season: str, cache_dir: Path) -> Path:
    return cache_dir / league / (season.replace("/", "-") + ".jsonl.gz")


def read_season(league: str, season: str, cache_dir: Path = CACHE_DIR) -> list:
    path = _season_file(league, season, cache_dir)
    if not path.is_file():
        return []
    out = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue                  # 쓰다 끊긴 줄 — 다시 받는다
    return out


def fetch(leagues=None, cache_dir: Path = CACHE_DIR, workers: int = 2,
          delay: float = 0.4, limit: int | None = None, log_fn=print,
          latest_only: bool = False, fetcher=None, since=None) -> dict:
    """빠진 경기만 받아 시즌 파일에 덧붙인다. 진행 상황을 돌려준다.

    한 경기가 실패해도 멈추지 않는다 — 다음 실행이 그 경기만 다시 받는다.
    `since`(date) 를 주면 그날 이후(UTC 날짜) 경기만 받는다 — 리포트 경로의
    갱신이 모델 상태 이후 경기만 받게 한다.
    """
    fetcher = fetcher or Fetcher(delay=delay)
    summary = {"seasons": 0, "new": 0, "failed": 0, "skipped": 0}
    budget = [limit if limit is not None else 10 ** 9]
    for league in leagues or LEAGUES:
        league_id, first = LEAGUES[league]
        try:
            seasons = [s for s in league_seasons(fetcher, league_id)
                       if season_start(s) >= first]
            if latest_only and seasons:
                seasons = sorted(seasons, key=season_start)[-1:]
        except Exception as e:                         # noqa: BLE001
            log_fn(f"  ✗ {league}: 시즌 목록 실패 — {e}")
            continue
        for season in sorted(seasons, key=season_start):
            if budget[0] <= 0:
                return summary
            try:
                fixtures, got = season_fixtures(fetcher, league_id, season)
            except Exception as e:                     # noqa: BLE001
                log_fn(f"  ✗ {league} {season}: 경기 목록 실패 — {e}")
                continue
            if got != season:
                log_fn(f"  ✗ {league} {season}: 다른 시즌이 왔다 ({got})")
                continue
            have = {r["id"] for r in read_season(league, season, cache_dir)}
            todo = [m for m in fixtures if str(m.get("id")) not in have]
            if since is not None:
                cut = since.isoformat()
                fixtures = [m for m in fixtures
                            if ((m.get("status") or {}).get("utcTime") or "")[:10] >= cut]
                todo = [m for m in todo
                        if ((m.get("status") or {}).get("utcTime") or "")[:10] >= cut]
            summary["seasons"] += 1
            summary["skipped"] += len(fixtures) - len(todo)
            todo = todo[: budget[0]]
            if not todo:
                log_fn(f"  · {league} {season}: {len(fixtures)}경기 이미 있음")
                continue
            path = _season_file(league, season, cache_dir)
            path.parent.mkdir(parents=True, exist_ok=True)
            lock = threading.Lock()
            done = [0, 0]

            def one(fx):
                try:
                    detail = fetcher.get_json(MATCH_PATH.format(id=fx["id"]))
                    rec = compact(detail, fx, league, season)
                except Exception as e:                 # noqa: BLE001
                    with lock:
                        done[1] += 1
                    log.debug("경기 %s 실패: %s", fx.get("id"), e)
                    return
                line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
                with lock:
                    with gzip.open(path, "at", encoding="utf-8") as fh:
                        fh.write(line + "\n")
                    done[0] += 1

            with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
                list(pool.map(one, todo))
            budget[0] -= len(todo)
            summary["new"] += done[0]
            summary["failed"] += done[1]
            log_fn(f"  ✓ {league} {season}: +{done[0]} (실패 {done[1]}) · "
                   f"전체 {len(have) + done[0]}/{len(fixtures)}")
    summary["requests"] = fetcher.requests
    return summary


def load(leagues=None, cache_dir: Path = CACHE_DIR) -> list:
    """모든 시즌 레코드. 같은 경기 ID 는 하나만 남긴다."""
    out, seen = [], set()
    for league in leagues or LEAGUES:
        base = cache_dir / league
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.jsonl.gz")):
            season = path.name[: -len(".jsonl.gz")].replace("-", "/")
            for rec in read_season(league, season, cache_dir):
                if rec["id"] in seen:
                    continue
                seen.add(rec["id"])
                out.append(rec)
    out.sort(key=lambda r: (r.get("utc") or "", r["id"]))
    return out


# --------------------------------------------------------------------------
# football-data 기록에 붙이기
# --------------------------------------------------------------------------
_FIELDS = {"xg": ("hxg", "axg"), "npxg": ("hnpxg", "anpxg"),
           "xgot": ("hxgot", "axgot"), "big_chances": ("hbc", "abc"),
           "touches_box": ("htb", "atb")}


def _rec_date(rec):
    from datetime import date as _d
    utc = rec.get("utc") or ""
    try:
        return _d.fromisoformat(utc[:10])
    except ValueError:
        return None


def _oriented(rec) -> bool:
    """레코드의 홈/원정이 경기 상세와 맞는가 (배열 순서를 믿지 않는다, §1-1-3)."""
    ids = rec.get("detail_ids") or [None, None]
    try:
        return ids[0] is None or int(ids[0]) == int(rec["home"]["id"])
    except (TypeError, ValueError, KeyError):
        return False


def _values(rec) -> dict:
    out = {}
    stats = rec.get("stats") or {}
    for key, (hf, af) in _FIELDS.items():
        pair = stats.get(key)
        if isinstance(pair, list) and len(pair) == 2 and None not in pair:
            out[hf], out[af] = float(pair[0]), float(pair[1])
    lu = rec.get("lineup") or {}
    hr, ar = (lu.get("home") or {}).get("rating"), (lu.get("away") or {}).get("rating")
    if isinstance(hr, (int, float)) and isinstance(ar, (int, float)) and hr > 0 and ar > 0:
        out["hrat"], out["arat"] = float(hr), float(ar)
    return out


def attach(rows, recs, log_fn=None) -> tuple:
    """football-data 경기 → FotMob 값을 붙인 새 목록, 요약, 쓴 레코드 ID.

    잇는 규칙 (팀 이름을 추측하지 않는다):
      1. 같은 리그 · 날짜 ±1일 · **같은 스코어** 후보가 정확히 하나면 짝이다.
         그 짝들로 'football-data 표기 → FotMob 팀 ID' 표를 투표로 만든다
         (3표 이상 · 80% 이상일 때만 채택).
      2. 나머지는 그 표의 두 팀 ID 와 날짜 ±3일로 찾고, 스코어가 같을 때만 잇는다.
    어긋나는 것은 잇지 않고 센다 — 틀린 xG 를 붙이는 것보다 비어 있는 편이 낫다.
    """
    out, stats, used, _names = _attach(rows, recs, log_fn)
    return out, stats, used


def _attach(rows, recs, log_fn=None) -> tuple:
    """`attach` 의 본체. 네 번째 값은 표기 표 {(리그, football-data 표기): FotMob 팀 ID}."""
    from collections import Counter, defaultdict
    from dataclasses import replace
    from datetime import timedelta

    by_league = defaultdict(list)
    for r in recs:
        if r.get("score") and _oriented(r) and _values(r):
            by_league[r["league"]].append(r)
    index = {}
    for lg, rs in by_league.items():
        d = defaultdict(list)
        for r in rs:
            rd = _rec_date(r)
            if rd:
                d[rd].append(r)
        index[lg] = d

    def near(lg, day, span):
        d = index.get(lg) or {}
        for k in range(-span, span + 1):
            yield from d.get(day + timedelta(days=k), [])

    pairs, votes = {}, defaultdict(Counter)
    for i, m in enumerate(rows):
        if m.league not in index:
            continue
        cand = [r for r in near(m.league, m.date, 1)
                if r["score"] == [m.hg, m.ag]]
        if len(cand) == 1:
            r = cand[0]
            pairs[i] = r
            votes[(m.league, m.home)][str(r["home"]["id"])] += 1
            votes[(m.league, m.away)][str(r["away"]["id"])] += 1
    names = {}
    for key, c in votes.items():
        tid, n = c.most_common(1)[0]
        if n >= 3 and n >= 0.8 * sum(c.values()):
            names[key] = tid
    out, used = [], set()
    stats = Counter()
    for i, m in enumerate(rows):
        r = None
        hid, aid = names.get((m.league, m.home)), names.get((m.league, m.away))
        if hid and aid and m.league in index:
            cand = [x for x in near(m.league, m.date, 3)
                    if str(x["home"]["id"]) == hid and str(x["away"]["id"]) == aid]
            if len(cand) == 1:
                r = cand[0]
            elif len(cand) > 1:
                stats["ambiguous"] += 1
        if r is None and i in pairs:
            p = pairs[i]
            if (not hid or str(p["home"]["id"]) == hid) and \
               (not aid or str(p["away"]["id"]) == aid):
                r = p
        if r is not None and r["score"] != [m.hg, m.ag]:
            stats["score_mismatch"] += 1
            r = None
        if r is not None and r["id"] in used:
            stats["duplicate"] += 1
            r = None
        if r is None:
            out.append(m)
            continue
        used.add(r["id"])
        stats["joined"] += 1
        fill = {k: v for k, v in _values(r).items() if getattr(m, k) is None}
        out.append(replace(m, fm_id=r["id"], lineup=r.get("lineup"), **fill))
    stats["fotmob_records"] = sum(len(v) for v in by_league.values())
    stats["unused_records"] = stats["fotmob_records"] - len(used)
    if log_fn:
        log_fn(f"FotMob 연결: {dict(stats)}")
    return out, dict(stats), used, names


def to_hist(recs, leagues, used=(), rename=None) -> list:
    """football-data 에 없는 리그(K리그)의 FotMob 레코드 → HistMatch.

    팀 이름은 FotMob 표기 그대로 둔다 — `rename` {(리그, FotMob 팀 ID): 표기} 를
    주면 그 표기를 쓰고, 표에 없는 팀이 낀 경기는 담지 않는다(다른 이름의
    새 팀으로 평점이 갈라지면 안 된다). 시즌은 FotMob 시즌 이름이다.
    """
    from .history import HistMatch

    out = []
    for r in recs:
        if r["league"] not in leagues or r["id"] in used:
            continue
        if not r.get("score") or not _oriented(r):
            continue
        d = _rec_date(r)
        if d is None:
            continue
        home, away = r["home"]["name"], r["away"]["name"]
        if rename is not None:
            home = rename.get((r["league"], str(r["home"]["id"])))
            away = rename.get((r["league"], str(r["away"]["id"])))
            if not home or not away:
                continue
        sh = (r.get("stats") or {})
        shots, sot = sh.get("shots") or [None, None], sh.get("sot") or [None, None]
        out.append(HistMatch(
            league=r["league"], season=r["season"], date=d,
            time=(r.get("utc") or "")[11:16],
            home=home, away=away,
            hg=r["score"][0], ag=r["score"][1],
            hs=None if shots[0] is None else int(shots[0]),
            as_=None if shots[1] is None else int(shots[1]),
            hst=None if sot[0] is None else int(sot[0]),
            ast=None if sot[1] is None else int(sot[1]),
            fm_id=r["id"], lineup=r.get("lineup"), **_values(r)))
    out.sort(key=lambda m: (m.date, m.league, m.home, m.away))
    return out


def season_gaps(fd_rows, recs, used, names) -> list:
    """football-data 가 통째로 빠뜨린 시즌의 FotMob 레코드 → HistMatch.

    J리그의 2026 특별 시즌(2~6월, 200경기)이 football-data 에 없다. 그런 시즌은
    빠진 채로 두면 평점이 그 반년을 건너뛴다. 조건은 셋이다 — 그 (리그, 시즌)의
    레코드가 하나도 이어지지 않았고, 그 기간에 football-data 경기가 하나도 없고,
    두 팀 다 이름 투표로 football-data 표기를 안다.
    """
    from collections import defaultdict
    from datetime import timedelta

    rename = {(lg, tid): fd for (lg, fd), tid in names.items()}
    leagues = {m.league for m in fd_rows}
    groups = defaultdict(list)
    for r in recs:
        if r["league"] in leagues:
            groups[(r["league"], r["season"])].append(r)
    fd_days = defaultdict(list)
    for m in fd_rows:
        fd_days[m.league].append(m.date)
    out = []
    for (lg, _season), rs in sorted(groups.items()):
        if any(r["id"] in used for r in rs):
            continue
        days = [d for d in (_rec_date(r) for r in rs) if d]
        if not days:
            continue
        lo, hi = min(days) - timedelta(days=3), max(days) + timedelta(days=3)
        if any(lo <= d <= hi for d in fd_days[lg]):
            continue
        out.extend(to_hist(rs, leagues={lg}, used=used, rename=rename))
    return out


def combined(fd_rows, recs, extra_leagues=("kleague1",), log_fn=None) -> tuple:
    """football-data 기록에 FotMob 값을 붙이고, football-data 에 없는 리그·시즌을 더한다."""
    rows, stats, used, names = _attach(fd_rows, recs, log_fn=log_fn)
    extra = to_hist(recs, leagues=set(extra_leagues), used=used)
    gaps = season_gaps(fd_rows, recs, used, names)
    rows = sorted(rows + extra + gaps, key=lambda m: (m.date, m.league, m.home, m.away))
    stats["extra_rows"] = len(extra)
    stats["gap_rows"] = len(gaps)
    return rows, stats
