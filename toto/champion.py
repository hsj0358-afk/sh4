"""챔피언 예측 모델 — 경기장에서 이긴 모델을 리포트에서 돌린다 (§1-67).

모델 경기장(`toto/arena.py` · `tools/model_arena.py`)이 과거 시즌을 다시 재생해
후보를 겨루고, 검증 구간에서 현 챔피언을 통계적으로 이긴 도전자만 챔피언이
된다. 이 모듈은 그 챔피언을 **리포트 경로에서** 돌린다.

    data/model/champion.json        누가 챔피언인가 · 검증 점수 · 교체 이력 (커밋)
    data/model/champion_state.json  출력층 계수 + 평점 엔진 상태 (커밋)
    cache/model/champion_state.json 최신 기록으로 다시 굴린 엔진 상태 (`--model-update`)

## 리포트 경로는 순수 파이썬이다

numpy 를 쓰지 않는다. 출력층 계수는 경기장에서 맞춰 상태 파일에 실어 두고,
여기서는 엔진 상태를 불러 경기 전 특징값을 만들고 계수를 곱할 뿐이다.

## 미래를 쓰지 않는다 — 두 겹

1. **상태가 그 경기 이후까지 배웠으면 쓰지 않는다.** 엔진 상태의 자료 끝
   날짜(`data_through`)가 킥오프 날짜(UTC)와 같거나 늦으면 거부한다. 옛
   저장본을 다시 렌더할 때 지금 상태로 지난 경기를 '예측' 하면 결과를 아는
   채로 맞히는 것이다 (§1-13).
2. 상태 이후의 결과는 **시즌 경기 색인에서 그 경기 이전 것만** 덧붙여 배운다
   (`models.matches_before` · §1-1-4). 이미 상태에 든 경기는 다시 배우지 않는다.

## 이것이 무엇이 아닌지

- **시장 확률과 합치지 않는다.** 배당을 읽지 않고 `predict` 를 import 하지
  않는다 (테스트). 시장을 섞은 후보는 경기장의 '시장 트랙' 에서만 잰다.
- **패널에 주지 않는다** (§1-66 과 같은 단계).
- **추천이 아니다.** 확률을 낼 뿐이다 (§1-3). `favorite` 은 채점용이다.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from . import ratings, stacker
from .models import MODEL
from .settings import ROOT

log = logging.getLogger(__name__)

MODEL_DIR = ROOT / "data" / "model"
CHAMPION_FILE = MODEL_DIR / "champion.json"
STATE_FILE = MODEL_DIR / "champion_state.json"
FRESH_STATE_FILE = ROOT / "cache" / "model" / "champion_state.json"
STATE_VERSION = 1

OUTCOMES = ("H", "D", "A")

# football-data.co.uk 표기 → 이 프로젝트의 정규명. **정확일치로 해석되지 않는
# 것만** 적는다 (TeamResolver(strict) 가 먼저다). 목표 정규명이 teams.yaml 에
# 실제로 있는지 테스트가 확인한다. teams.yaml 에 넣지 않는 이유: 이 표기는
# 예측 모델만 쓰고, 다른 소스의 해석에 끼어들면 안 된다 (§1-22).
FD_NAMES = {
    "Ath Bilbao": "Athletic Club",
    "Ath Madrid": "Atletico Madrid",
    "Espanol": "Espanyol",
    "La Coruna": "Deportivo La Coruna",
    "Santander": "Racing Santander",
    "Vallecano": "Rayo Vallecano",
    "Ein Frankfurt": "Eintracht Frankfurt",
    "M'gladbach": "Borussia M.Gladbach",
    "Chiba": "JEF United Chiba",
}

REASON_NO_STATE = "예측 모델 상태 파일 없음"
REASON_LEAGUE = "예측 모델이 다루지 않는 리그"
REASON_TEAM = "예측 모델 기록에 없는 팀"
REASON_FUTURE = "모델 자료가 이 경기 이후까지 학습돼 있어 쓰지 않습니다 (사후 정보)"
REASON_ASOF = "킥오프 시각 없음"


@dataclass(frozen=True)
class ModelForecast:
    p_home: float
    p_draw: float
    p_away: float
    model: str
    data_through: str                # 엔진 상태의 자료 끝 날짜
    replayed: int                    # 상태 이후 시즌 색인에서 덧붙여 배운 경기 수
    holdout: dict                    # 경기장 검증 점수 (log loss · 적중률 …)
    provenance: str = MODEL

    @property
    def probs(self) -> dict:
        return {"H": self.p_home, "D": self.p_draw, "A": self.p_away}

    @property
    def favorite(self) -> str:
        """확률이 가장 높은 결과. **채점용이다 — 추천이 아니다** (§1-3)."""
        return max(OUTCOMES, key=lambda o: self.probs[o])


# --------------------------------------------------------------------------
# 챔피언 기록
# --------------------------------------------------------------------------
def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    tmp.replace(path)


def load_champion(path: Path | None = None) -> dict | None:
    return _read_json(path or CHAMPION_FILE)


def champion_id(candidate: dict) -> str:
    import hashlib
    raw = json.dumps({k: candidate.get(k) for k in
                      ("kind", "engines", "features", "l2", "per_league", "window")},
                     sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def save_champion(cand, holdout: dict, gate: dict, against: str,
                  previous: dict | None = None, path: Path | None = None) -> dict:
    record = {
        "candidate": cand.to_dict(),
        "id": champion_id(cand.to_dict()),
        "promoted_at": datetime.now().isoformat(timespec="seconds"),
        "holdout": holdout,
        "gate": {"against": against, **gate},
        "history": list((previous or {}).get("history") or []),
    }
    if previous is not None:
        record["history"].append({k: previous.get(k) for k in
                                  ("id", "promoted_at", "holdout")}
                                 | {"name": previous["candidate"]["name"]})
    _write_json(path or CHAMPION_FILE, record)
    return record


# --------------------------------------------------------------------------
# 상태 만들기 (경기장 · 모델 갱신)
# --------------------------------------------------------------------------
def team_map(rows, resolver=None) -> tuple:
    """(리그 → {football-data 표기: 정규명}, 못 이은 표기 목록). 최근 두 시즌의 팀만."""
    if resolver is None:
        from .normalize import TeamResolver
        resolver = TeamResolver()
    by_league = {}
    for m in rows:
        seasons = by_league.setdefault(m.league, {})
        seasons.setdefault(m.season, set()).update((m.home, m.away))
    out, missing = {}, []
    for league, seasons in sorted(by_league.items()):
        last_dates = {}
        for m in rows:
            if m.league == league:
                last_dates[m.season] = m.date
        recent = sorted(seasons, key=lambda s: last_dates[s])[-2:]
        names = sorted(set().union(*(seasons[s] for s in recent)))
        mapping = {}
        for name in names:
            canon = FD_NAMES.get(name) or resolver.resolve(
                name, learn=False, quiet=True, strict=True)
            if canon:
                mapping[name] = canon
            else:
                missing.append(f"{league}:{name}")
        out[league] = mapping
    return out, missing


def replay_engines(cand_engines, rows) -> list:
    engines = [ratings.make(s) for s in cand_engines]
    feats = ratings.replay(rows, engines)
    return engines, feats


def build_state(cand, rows, stack: stacker.Stacker | None = None) -> tuple:
    """(상태 dict, 메모). `stack` 이 없으면 경기장의 규칙대로 새로 맞춘다 (numpy)."""
    from . import arena

    if cand.kind != "stack":
        raise ValueError(f"리포트 경로가 돌릴 수 없는 종류: {cand.kind}")
    engines, feats = replay_engines(cand.engines, rows)
    notes = []
    if stack is None:
        lo = arena.TRAIN_FROM
        if cand.window:
            lo = max(lo, arena.fyear(rows[-1].date) - cand.window)
        X, y, lg = [], [], []
        for m, f in feats:
            if arena.fyear(m.date) < lo:
                continue
            x = stacker.derive(f, cand.features)
            if x is None:
                continue
            X.append(x)
            y.append(m.result)
            lg.append(m.league)
        stack = stacker.fit(X, y, lg, cand.features, l2=cand.l2,
                            per_league=cand.per_league)
        notes.append(f"출력층 학습 {len(X):,}경기")
    mapping, missing = team_map(rows)
    if missing:
        notes.append(f"정규명으로 잇지 못한 팀 {len(missing)}: {', '.join(missing)}")
    last = rows[-1].date
    league_last = {}
    for m in rows:
        league_last[m.league] = m.date
    state = {
        "version": STATE_VERSION,
        "champion": champion_id(cand.to_dict()),
        "name": cand.name,
        "data_through": last.isoformat(),
        "league_last": {k: v.isoformat() for k, v in sorted(league_last.items())},
        "engines": [e.state() for e in engines],
        "stacker": stack.to_dict(),
        "teams": mapping,
    }
    return state, notes


def save_state(state: dict, path: Path | None = None) -> None:
    _write_json(path or STATE_FILE, state)


def refresh_state(rows, base: dict | None = None,
                  out_path: Path | None = None) -> tuple:
    """출력층은 그대로 두고 엔진만 최신 기록으로 다시 굴린다 (numpy 없이)."""
    base = base or _read_json(STATE_FILE)
    if not base:
        return None, REASON_NO_STATE
    champ = load_champion()
    if champ is None:
        return None, "챔피언 기록 없음"
    from .arena import Candidate

    cand = Candidate.from_dict(champ["candidate"])
    stack = stacker.Stacker.from_dict(base["stacker"])
    state, notes = build_state(cand, rows, stack=stack)
    save_state(state, out_path or FRESH_STATE_FILE)
    return state, "; ".join(notes)


_CACHE = {}


def load_state(paths=None) -> dict | None:
    """가장 최근 자료의 상태. 챔피언이 바뀌었으면 옛 상태는 쓰지 않는다."""
    champ = load_champion()
    best = None
    for p in paths or (FRESH_STATE_FILE, STATE_FILE):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        key = (str(p), mtime)
        st = _CACHE.get(key)
        if st is None:
            st = _read_json(p)
            if not isinstance(st, dict) or st.get("version") != STATE_VERSION:
                continue
            _CACHE[key] = st
        if champ is not None and st.get("champion") != champ.get("id"):
            continue
        if best is None or st["data_through"] > best["data_through"]:
            best = st
    return best


# --------------------------------------------------------------------------
# 리포트 경로
# --------------------------------------------------------------------------
def _fyear(d: date) -> int:
    return d.year if d.month >= 7 else d.year - 1


def _utc_date(dt) -> date | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.date()


def _season_for(state, league, d: date, engines) -> str:
    last = date.fromisoformat(state["league_last"].get(league, state["data_through"]))
    for e in engines:
        lg = e.leagues.get(league)
        if lg is not None and lg.season is not None:
            if _fyear(d) == _fyear(last):
                return lg.season
            break
    return f"rt{_fyear(d)}"


def forecast_from_state(state, league: str, home: str, away: str, kickoff,
                        season=None, holdout: dict | None = None) -> tuple:
    """정규명 두 팀 · 킥오프(aware 또는 naive KST) → (ModelForecast | None, 사유)."""
    if not state:
        return None, REASON_NO_STATE
    mapping = state["teams"].get(league)
    if mapping is None:
        return None, f"{REASON_LEAGUE} ({league or '리그 미상'})"
    to_fd = {c: f for f, c in mapping.items()}
    fh, fa = to_fd.get(home), to_fd.get(away)
    if not fh or not fa:
        miss = [t for t, f in ((home, fh), (away, fa)) if not f]
        return None, f"{REASON_TEAM}: {', '.join(miss)}"
    kd = _utc_date(kickoff)
    if kd is None:
        return None, REASON_ASOF
    through = date.fromisoformat(state["data_through"])
    if kd <= through:
        return None, f"{REASON_FUTURE} (자료 {state['data_through']} · 경기 {kd})"
    engines = [ratings.Engine.from_state(s) for s in state["engines"]]
    replayed = _replay_season(state, engines, league, to_fd, season, kickoff)
    target = SimpleNamespace(league=league, season=_season_for(state, league, kd, engines),
                             home=fh, away=fa, date=kd)
    feats = {}
    for e in engines:
        feats.update(e.features(target))
    st = stacker.Stacker.from_dict(state["stacker"])
    x = stacker.derive(feats, st.features)
    if x is None:
        return None, "특징값을 만들지 못했습니다"
    ph, pd, pa = st.predict(x, league)
    return ModelForecast(p_home=ph, p_draw=pd, p_away=pa, model=state.get("name", ""),
                         data_through=state["data_through"], replayed=replayed,
                         holdout=holdout or {}), ""


def _replay_season(state, engines, league, to_fd, season, kickoff) -> int:
    """상태 이후 · 킥오프 이전의 그 리그 종료 경기를 배운다. 배운 경기 수."""
    if not season:
        return 0
    from . import models

    scoped, why = models.scope_to_competition(list(season), league)
    if why:
        return 0
    through = date.fromisoformat(state["data_through"])
    todo = []
    for m in models.matches_before(scoped, kickoff):
        if not (m.finished and m.home_goals is not None and m.away_goals is not None):
            continue
        d = _utc_date(m.kickoff)
        # 상태에 든 날짜까지는 football-data 가 이미 담았다. 그 뒤만 배운다.
        if d is None or d <= through:
            continue
        fh, fa = to_fd.get(m.home_team), to_fd.get(m.away_team)
        if not fh or not fa:
            continue
        todo.append(SimpleNamespace(league=league, season=_season_for(state, league, d, engines),
                                    date=d, home=fh, away=fa, hg=m.home_goals,
                                    ag=m.away_goals, hst=None, ast=None, hs=None, as_=None))
    todo.sort(key=lambda r: (r.date, r.home))
    ratings.replay(todo, engines)
    return len(todo)


def for_match(match, report=None) -> tuple:
    """회차 경기 → (ModelForecast | None, 사유)."""
    from . import models

    home = getattr(match.home, "canonical", "") or ""
    away = getattr(match.away, "canonical", "") or ""
    if not home or not away:
        return None, "팀 정규명 없음"
    state = load_state()
    champ = load_champion() or {}
    return forecast_from_state(
        state, getattr(match, "league", "") or "", home, away,
        models.as_of_from_match(match),
        season=getattr(report, "season_matches", None) if report is not None else None,
        holdout=champ.get("holdout"))


def update(refresh: bool = True) -> str:
    """과거 기록의 진행 중 시즌을 다시 받고 엔진 상태를 굴린다 → 상태 문자열 (§1-6).

    출력층은 그대로 쓴다(numpy 없이 돈다). 실패해도 리포트는 커밋된 상태와
    시즌 색인으로 그대로 돈다 — 이 단계가 실행을 죽이지 않는다.
    """
    if load_champion() is None:
        return "생략 (챔피언 없음)"
    if _read_json(STATE_FILE) is None:
        return f"생략 ({REASON_NO_STATE})"
    from . import history

    got = history.fetch(refresh=refresh)
    rows, _missing = history.load()
    if not rows:
        return "실패 (과거 기록을 읽지 못함)"
    state, why = refresh_state(rows)
    if state is None:
        return f"실패 ({why})"
    fails = len(got["failed"])
    tail = f" · 받기 실패 {fails}" if fails else ""
    return f"ok (자료 {state['data_through']}까지 · 받음 {got['ok']}{tail})"
