"""예측 모델 경기장 — 후보를 과거 시즌에 다시 돌려 겨루고, 이긴 것만 남긴다 (§1-67).

알파고 제로의 학습 고리를 축구 예측에 옮긴 것이다. 바둑처럼 스스로 대국할
수는 없으므로, **지나간 시즌을 처음부터 다시 재생**하는 것이 대국이다.

    1. 지식 없이 시작   모든 팀이 리그 평균에서 출발한다 (`toto/ratings.py`)
    2. 재생(대국)        경기마다 '보기 전' 에 예측하고, 본 뒤에 배운다
    3. 탐색              엔진 설정 · 특징 조합 · 출력층을 넓게 찾고(무작위)
                         가장 좋은 것 주변을 다시 찾는다(국소 개선)
    4. 챔피언 게이팅      도전자는 **본 적 없는 시즌**에서 현 챔피언을
                         통계적으로 이겨야만 자리를 넘겨받는다

## 시간을 셋으로 나눈다

| 구간 | 시즌 | 쓰임 |
|---|---|---|
| 예열 | 2000/01 ~ 2001/02 | 평점만 쌓는다. 채점하지 않는다 |
| 개발 | 2005/06 ~ 2018/19 | 탐색이 고르는 기준. 여기 점수로만 고른다 |
| 검증 | 2019/20 ~ 지금 | 최종 후보끼리 **한 번** 겨룬다. 여기서 고르지 않는다 |

출력층(로지스틱)은 **시즌(7월~6월) 단위로** 그 시즌 이전 경기만으로 다시
맞춘다 — 걸어가며 검증(walk-forward)이다. 평점 엔진의 특징값은 원래부터
'경기 전' 값이라, 어느 시점의 예측에도 미래가 들어가지 않는다.

## 채점

- **log loss** (주 지표 · 게이팅 기준) · **RPS** (승<무<패 순서를 보는 축구
  표준) · Brier · **적중률**(확률이 가장 높은 결과가 맞았나).
- 적중률은 사람이 보기 쉽지만 분산이 커서(1천 경기에 ±1.6%p) 고르는 기준으로
  쓰지 않는다. 잘 맞춘 확률의 최빈값이 적중률도 가장 높게 만든다.
- 둘을 견줄 때는 **같은 경기**에서 경기별 차이를 날짜 단위로 다시 뽑아
  (부트스트랩) 95% 구간을 낸다.

## 두 트랙

- **독립 트랙** — 경기 결과·슈팅만 본다. 리포트에 나가는 챔피언은 여기서만
  나온다 (`Match.probs`(시장)와 합치지 않는다는 §1-27·§1-66 을 지킨다).
- **시장 트랙** — 피나클 배당(킥오프 전)을 기준선으로, 그리고 모델과 섞은
  후보를 함께 잰다. 시장이 얼마나 강한지, 모델이 시장에 더할 것이 있는지를
  보이려는 것이다. 이 트랙의 후보는 리포트에 나가지 않는다.

이 모듈은 numpy 가 필요하다 (모델 경기장 전용). 리포트 경로는
`toto/champion.py` 이고 numpy 없이 돈다.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from datetime import date

from . import ratings, stacker

OUTCOMES = ("H", "D", "A")
TRAIN_FROM = 2002                 # 출력층 학습 자료의 첫 시즌 (그 앞은 예열)
DEV_YEARS = tuple(range(2005, 2019))
HOLDOUT_FROM = 2019
EPS = 1e-15


def fyear(d: date) -> int:
    """축구 연도 — 7월 1일에 바뀐다. 2025-08-01 → 2025 · 2026-03-01 → 2025."""
    return d.year if d.month >= 7 else d.year - 1


def holdout_years(rows) -> tuple:
    last = max((fyear(m.date) for m in rows), default=HOLDOUT_FROM)
    return tuple(range(HOLDOUT_FROM, last + 1))


# --------------------------------------------------------------------------
# 후보
# --------------------------------------------------------------------------
@dataclass
class Candidate:
    name: str
    kind: str                       # stack · gbm · mlp · poisson · base · market · statmodel · blend
    engines: list = field(default_factory=list)       # 엔진 spec (dict)
    features: list = field(default_factory=list)
    l2: float = 1.0
    per_league: bool = True
    window: int = 0                 # 출력층 학습 기간(시즌). 0 = 처음부터
    track: str = "independent"      # independent · market
    options: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "engines": self.engines,
                "features": self.features, "l2": self.l2,
                "per_league": self.per_league, "window": self.window,
                "track": self.track, "options": self.options}

    @classmethod
    def from_dict(cls, d: dict) -> "Candidate":
        return cls(**{k: d[k] for k in ("name", "kind", "engines", "features",
                                         "l2", "per_league", "window", "track",
                                         "options") if k in d})


# --------------------------------------------------------------------------
# 특징 저장소 — 같은 엔진 설정은 한 번만 돌린다
# --------------------------------------------------------------------------
def spec_key(spec: dict) -> str:
    return json.dumps(spec, sort_keys=True)


class FeatureStore:
    def __init__(self, rows):
        self.rows = rows
        self._memo = {}
        self._market = None

    def engine(self, spec: dict) -> list:
        key = spec_key(spec)
        if key not in self._memo:
            eng = ratings.make(spec)
            self._memo[key] = [f for _, f in ratings.replay(self.rows, [eng])]
        return self._memo[key]

    def drop(self, keep_specs) -> None:
        keep = {spec_key(s) for s in keep_specs}
        for k in list(self._memo):
            if k not in keep:
                del self._memo[k]

    def market(self) -> list:
        """피나클 킥오프 전 배당 → 가산 마진 제거 확률(지침 §3-(b)) → 로그 오즈."""
        if self._market is None:
            self._market = [market_features(m) for m in self.rows]
        return self._market

    def merged(self, specs, with_market: bool = False) -> list:
        parts = [self.engine(s) for s in specs]
        if with_market:
            parts.append(self.market())
        out = []
        for i in range(len(self.rows)):
            d = {}
            for p in parts:
                d.update(p[i])
            out.append(d)
        return out


def market_probs(odds) -> tuple | None:
    if not odds:
        return None
    from .predict import additive_probabilities   # 시장 트랙 전용 — 독립 엔진은 쓰지 않는다
    try:
        p = additive_probabilities(*odds)
    except ValueError:
        return None
    return (p.home, p.draw, p.away)


def market_features(m) -> dict:
    p = market_probs(m.odds_open)
    if p is None or min(p) <= 0:
        return {}
    return {"mkt_h": math.log(p[0] / p[1]), "mkt_a": math.log(p[2] / p[1]),
            "mkt_ph": p[0], "mkt_pd": p[1], "mkt_pa": p[2]}


# --------------------------------------------------------------------------
# 예측 — 후보 하나 → 경기마다 (pH, pD, pA) 또는 None
# --------------------------------------------------------------------------
def _years_of(rows):
    return [fyear(m.date) for m in rows]


def _train_years(year: int, window: int) -> tuple:
    lo = TRAIN_FROM if not window else max(TRAIN_FROM, year - window)
    return lo, year


def predict(cand: Candidate, store: FeatureStore, years) -> list:
    rows = store.rows
    if cand.kind == "base":
        return _predict_base(rows, years)
    if cand.kind == "market":
        which = cand.options.get("odds", "open")
        return [market_probs(getattr(m, f"odds_{which}"))
                if fyear(m.date) in years else None for m in rows]
    if cand.kind == "statmodel":
        return _predict_statmodel(rows, years, cand.options)
    if cand.kind == "poisson":
        return _predict_poisson(cand, store, years)
    if cand.kind == "blend":
        return _predict_blend(cand, store, years)
    feats = store.merged(cand.engines, with_market=cand.track == "market")
    X = [stacker.derive(f, cand.features) for f in feats]
    if cand.kind == "stack":
        return _walk_stack(rows, X, cand, years)
    if cand.kind in ("gbm", "mlp"):
        return _walk_sklearn(rows, X, cand, years)
    raise ValueError(f"모르는 후보 종류: {cand.kind}")


def _walk_stack(rows, X, cand, years, keep_models=None) -> list:
    yrs = _years_of(rows)
    out = [None] * len(rows)
    for year in sorted(set(years)):
        lo, hi = _train_years(year, cand.window)
        tr = [i for i, y in enumerate(yrs) if lo <= y < hi and X[i] is not None]
        if len(tr) < 200:
            continue
        model = stacker.fit([X[i] for i in tr], [rows[i].result for i in tr],
                            [rows[i].league for i in tr], cand.features,
                            l2=cand.l2, per_league=cand.per_league)
        if keep_models is not None:
            keep_models[year] = model
        for i, y in enumerate(yrs):
            if y == year and X[i] is not None:
                out[i] = model.predict(X[i], rows[i].league)
    return out


def _onehot(rows, idx, leagues):
    return [[1.0 if rows[i].league == lg else 0.0 for lg in leagues] for i in idx]


def _walk_sklearn(rows, X, cand, years) -> list:
    import numpy as np
    try:
        if cand.kind == "gbm":
            from sklearn.ensemble import HistGradientBoostingClassifier as Model
        else:
            from sklearn.neural_network import MLPClassifier as Model
    except ImportError:
        return [None] * len(rows)
    yrs = _years_of(rows)
    leagues = sorted({m.league for m in rows})
    out = [None] * len(rows)
    for year in sorted(set(years)):
        lo, hi = _train_years(year, cand.window)
        tr = [i for i, y in enumerate(yrs) if lo <= y < hi and X[i] is not None]
        te = [i for i, y in enumerate(yrs) if y == year and X[i] is not None]
        if len(tr) < 200 or not te:
            continue
        def mat(idx):
            return np.hstack([np.array([X[i] for i in idx], dtype=float),
                              np.array(_onehot(rows, idx, leagues))])
        A, B = mat(tr), mat(te)
        if cand.kind == "mlp":
            mu, sd = A.mean(axis=0), A.std(axis=0)
            sd[sd < 1e-12] = 1.0
            A, B = (A - mu) / sd, (B - mu) / sd
            model = Model(hidden_layer_sizes=tuple(cand.options.get("hidden", (16,))),
                          alpha=cand.options.get("alpha", 1.0), max_iter=400,
                          early_stopping=True, random_state=0)
        else:
            model = Model(max_iter=cand.options.get("iters", 200),
                          learning_rate=cand.options.get("lr", 0.05),
                          max_leaf_nodes=cand.options.get("leaves", 15),
                          l2_regularization=cand.options.get("l2", 1.0),
                          min_samples_leaf=cand.options.get("min_leaf", 200),
                          early_stopping=False, random_state=0)
        model.fit(A, [rows[i].result for i in tr])
        cls = list(model.classes_)
        P = model.predict_proba(B)
        for k, i in enumerate(te):
            out[i] = tuple(float(P[k][cls.index(o)]) for o in OUTCOMES)
    return out


def _predict_base(rows, years) -> list:
    """리그별 과거 빈도 — 그 시즌 이전 경기만."""
    yrs = _years_of(rows)
    out = [None] * len(rows)
    for year in sorted(set(years)):
        counts = {}
        for i, y in enumerate(yrs):
            if TRAIN_FROM <= y < year:
                c = counts.setdefault(rows[i].league, [0, 0, 0])
                c[OUTCOMES.index(rows[i].result)] += 1
        for i, y in enumerate(yrs):
            c = counts.get(rows[i].league)
            if y == year and c and sum(c):
                out[i] = tuple(v / sum(c) for v in c)
    return out


def dc_probs(lh: float, la: float, rho: float = 0.0, max_goals: int = 10) -> tuple:
    """독립 포아송(+ Dixon-Coles 저득점 보정) → (pH, pD, pA). 합이 1 이 되게 나눈다."""
    ph = [math.exp(-lh)]
    pa = [math.exp(-la)]
    for k in range(1, max_goals):
        ph.append(ph[-1] * lh / k)
        pa.append(pa[-1] * la / k)
    h = d = a = 0.0
    for i in range(max_goals):
        for j in range(max_goals):
            p = ph[i] * pa[j]
            if rho:
                if i == 0 and j == 0:
                    p *= 1.0 - lh * la * rho
                elif i == 0 and j == 1:
                    p *= 1.0 + lh * rho
                elif i == 1 and j == 0:
                    p *= 1.0 + la * rho
                elif i == 1 and j == 1:
                    p *= 1.0 - rho
            if i > j:
                h += p
            elif i == j:
                d += p
            else:
                a += p
    tot = h + d + a
    return h / tot, d / tot, a / tot


def _predict_poisson(cand, store, years) -> list:
    """엔진의 기대 득점으로 바로 확률을 낸다 (출력층 없음). rho 는 학습 시즌으로 고른다."""
    rows = store.rows
    feats = store.merged(cand.engines)
    stat = cand.options.get("stat", "goals")
    lams = [(math.exp(f[f"{stat}_lh"]), math.exp(f[f"{stat}_la"]))
            if f"{stat}_lh" in f else None for f in feats]
    yrs = _years_of(rows)
    out = [None] * len(rows)
    grid = [r / 100.0 for r in range(-20, 11, 2)] if cand.options.get("dc") else [0.0]
    for year in sorted(set(years)):
        rho = 0.0
        if len(grid) > 1:
            tr = [i for i, y in enumerate(yrs) if TRAIN_FROM <= y < year and lams[i]]
            tr = tr[-6000:]
            best = None
            for r in grid:
                ll = -sum(math.log(max(dc_probs(*lams[i], r)[OUTCOMES.index(rows[i].result)], EPS))
                          for i in tr)
                if best is None or ll < best[0]:
                    best = (ll, r)
            rho = best[1]
        for i, y in enumerate(yrs):
            if y == year and lams[i]:
                out[i] = dc_probs(*lams[i], rho)
    return out


def _predict_statmodel(rows, years, options) -> list:
    """현 운영 모델(`toto/statmodel.py`) — 그 시즌, 그 날짜 이전 경기만으로."""
    from datetime import datetime
    from types import SimpleNamespace

    from . import statmodel

    cfg = statmodel.ModelConfig(**options) if options else statmodel.ModelConfig()
    out = [None] * len(rows)
    season_rows = {}
    for i, m in enumerate(rows):
        season_rows.setdefault((m.league, m.season), []).append(i)
    for (league, season), idx in season_rows.items():
        past = []
        day, pending = None, []
        for i in idx:
            m = rows[i]
            if m.date != day:
                past.extend(pending)
                day, pending = m.date, []
            if fyear(m.date) in years:
                as_of = datetime(m.date.year, m.date.month, m.date.day)
                f, _ = statmodel.forecast_from(past, m.home, m.away, as_of, cfg)
                if f is not None:
                    tot = f.p_home + f.p_draw + f.p_away
                    out[i] = (f.p_home / tot, f.p_draw / tot, f.p_away / tot)
            pending.append(SimpleNamespace(
                home_team=m.home, away_team=m.away, home_goals=m.hg,
                away_goals=m.ag, kickoff=datetime(m.date.year, m.date.month, m.date.day)))
    return out


def _predict_blend(cand, store, years) -> list:
    """두 후보의 확률을 섞는다 — 무게는 그 시즌 이전 경기의 log loss 로 고른다."""
    members = [Candidate.from_dict(d) for d in cand.options["members"]]
    preds = [predict(c, store, years=set(range(TRAIN_FROM, max(years) + 1)))
             for c in members]
    rows = store.rows
    yrs = _years_of(rows)
    out = [None] * len(rows)
    grid = [w / 20.0 for w in range(21)]
    for year in sorted(set(years)):
        tr = [i for i, y in enumerate(yrs)
              if TRAIN_FROM <= y < year and preds[0][i] and preds[1][i]]
        if cand.window:
            tr = [i for i in tr if yrs[i] >= year - cand.window]
        if not tr:
            continue
        best = None
        for w in grid:
            ll = 0.0
            for i in tr:
                k = OUTCOMES.index(rows[i].result)
                ll -= math.log(max(w * preds[0][i][k] + (1 - w) * preds[1][i][k], EPS))
            if best is None or ll < best[0]:
                best = (ll, w)
        w = best[1]
        for i, y in enumerate(yrs):
            if y == year and preds[0][i] and preds[1][i]:
                out[i] = tuple(w * a + (1 - w) * b
                               for a, b in zip(preds[0][i], preds[1][i]))
    return out


# --------------------------------------------------------------------------
# 채점
# --------------------------------------------------------------------------
def losses(probs, result: str) -> tuple:
    """(log loss, RPS, Brier, 적중) — 한 경기."""
    k = OUTCOMES.index(result)
    o = [1.0 if i == k else 0.0 for i in range(3)]
    ll = -math.log(max(probs[k], EPS))
    c1 = probs[0] - o[0]
    c2 = probs[0] + probs[1] - o[0] - o[1]
    rps = 0.5 * (c1 * c1 + c2 * c2)
    brier = sum((p - y) ** 2 for p, y in zip(probs, o))
    hit = 1.0 if max(range(3), key=lambda i: probs[i]) == k else 0.0
    return ll, rps, brier, hit


def score(rows, probs, idx) -> dict:
    idx = [i for i in idx if probs[i] is not None]
    if not idx:
        return {"n": 0}
    tot = [0.0, 0.0, 0.0, 0.0]
    picks = {o: 0 for o in OUTCOMES}
    for i in idx:
        for j, v in enumerate(losses(probs[i], rows[i].result)):
            tot[j] += v
        picks[OUTCOMES[max(range(3), key=lambda k: probs[i][k])]] += 1
    n = len(idx)
    return {"n": n, "logloss": tot[0] / n, "rps": tot[1] / n,
            "brier": tot[2] / n, "accuracy": tot[3] / n,
            "picks": picks}


def index_of(rows, years, leagues=None) -> list:
    ys = set(years)
    return [i for i, m in enumerate(rows) if fyear(m.date) in ys
            and (leagues is None or m.league in leagues)]


def compare(rows, pa, pb, idx, resamples: int = 2000, seed: int = 0) -> dict:
    """A − B (낮을수록 좋은 지표는 B 가 나으면 양수). 같은 경기에서만.

    날짜 단위로 다시 뽑는다 — 같은 날 경기는 서로 독립이 아닐 수 있다.
    """
    import numpy as np

    common = [i for i in idx if pa[i] is not None and pb[i] is not None]
    if not common:
        return {"n": 0}
    by_day = {}
    for i in common:
        la, ra, _, ha = losses(pa[i], rows[i].result)
        lb, rb, _, hb = losses(pb[i], rows[i].result)
        d = by_day.setdefault(rows[i].date, [0.0, 0.0, 0.0, 0])
        d[0] += la - lb
        d[1] += ra - rb
        d[2] += hb - ha
        d[3] += 1
    days = list(by_day.values())
    arr = np.array(days, dtype=float)
    n = arr[:, 3].sum()
    mean = arr[:, :3].sum(axis=0) / n
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(days), size=(resamples, len(days)))
    sums = arr[pick].sum(axis=1)                      # resamples × 4
    boot = sums[:, :3] / sums[:, 3:4]
    lo = np.percentile(boot, 2.5, axis=0)
    hi = np.percentile(boot, 97.5, axis=0)
    p_better = (boot[:, 0] > 0).mean()                # B 의 log loss 가 더 낮을 확률
    return {"n": int(n), "days": len(days),
            "d_logloss": float(mean[0]), "d_logloss_ci": [float(lo[0]), float(hi[0])],
            "d_rps": float(mean[1]), "d_rps_ci": [float(lo[1]), float(hi[1])],
            "d_accuracy": float(mean[2]), "d_accuracy_ci": [float(lo[2]), float(hi[2])],
            "p_b_better": float(p_better)}


def gate(result: dict, level: float = 0.95) -> bool:
    """도전자(B)가 이겼나 — log loss 개선의 한쪽 95% 확신 (부트스트랩)."""
    return bool(result.get("n")) and result["p_b_better"] >= level


# --------------------------------------------------------------------------
# 탐색
# --------------------------------------------------------------------------
SPACE = {
    "elo": {"k": [8, 12, 16, 20, 25, 30, 40], "hfa": [0, 30, 50, 70, 90, 110],
            "carry": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0], "gd": ["none", "log", "wfe"]},
    "pi": {"lam": [0.015, 0.025, 0.035, 0.045, 0.06, 0.08, 0.1],
           "gamma": [0.3, 0.5, 0.7, 0.9, 1.0], "carry": [0.6, 0.8, 0.9, 1.0]},
    "goals": {"eta": [0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.07],
              "eta_g": [0.0, 0.001, 0.002, 0.005, 0.01],
              "carry": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]},
    "sot": {"eta": [0.02, 0.03, 0.05, 0.07, 0.1, 0.14, 0.2],
            "eta_g": [0.0, 0.001, 0.002, 0.005, 0.01],
            "carry": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]},
    "shots": {"eta": [0.02, 0.03, 0.05, 0.07, 0.1, 0.14, 0.2],
              "eta_g": [0.0, 0.001, 0.002, 0.005, 0.01],
              "carry": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]},
}

# 엔진 하나만으로 잴 때 쓰는 특징.
SOLO_FEATURES = {
    "elo": ["elo_diff", "abs:elo_diff"],
    "pi": ["pi_gd", "abs:pi_gd"],
    "goals": ["goals_diff", "goals_sum", "abs:goals_diff"],
    "sot": ["sot_diff", "sot_sum", "abs:sot_diff"],
    "shots": ["shots_diff", "shots_sum", "abs:shots_diff"],
}


def make_spec(family: str, params: dict) -> dict:
    if family in ("goals", "sot", "shots"):
        return {"kind": "dp", "stat": family, **params}
    return {"kind": family, **params}


def family_of(spec: dict) -> str:
    return spec["stat"] if spec["kind"] == "dp" else spec["kind"]


def solo(spec: dict, name: str = "") -> Candidate:
    fam = family_of(spec)
    return Candidate(name=name or f"{fam}-solo", kind="stack", engines=[spec],
                     features=SOLO_FEATURES[fam])


def dev_logloss(cand: Candidate, store: FeatureStore, years=DEV_YEARS) -> float:
    probs = predict(cand, store, years)
    s = score(store.rows, probs, index_of(store.rows, years))
    return s.get("logloss", float("inf"))


def search_engine(family: str, store: FeatureStore, n_random: int = 24,
                  seed: int = 0, log=print) -> tuple:
    """무작위 탐색 → 국소 개선. (최고 spec, 개발 log loss, 시도 기록)."""
    space = SPACE[family]
    rng = random.Random(f"{family}-{seed}")
    tried = {}

    def trial(params):
        spec = make_spec(family, params)
        key = spec_key(spec)
        if key not in tried:
            tried[key] = (dev_logloss(solo(spec), store), spec)
            store.drop([v[1] for v in sorted(tried.values(), key=lambda t: t[0])[:1]])
        return tried[key][0]

    default = make_spec(family, {})
    base = {k: v for k, v in ratings.make(default).params.items() if k in space}
    trial(base)
    for _ in range(n_random):
        trial({k: rng.choice(v) for k, v in space.items()})
    best_ll, best_spec = min(tried.values(), key=lambda t: t[0])
    log(f"  {family}: 무작위 {len(tried)}개 → 최고 {best_ll:.5f}")
    improved = True
    rounds = 0
    while improved and rounds < 6:
        improved, rounds = False, rounds + 1
        current = {k: best_spec[k] for k in space}
        for k, values in space.items():
            pos = values.index(current[k]) if current[k] in values else 0
            for nb in (pos - 1, pos + 1):
                if 0 <= nb < len(values):
                    cand = dict(current, **{k: values[nb]})
                    ll = trial(cand)
                    if ll < best_ll - 1e-6:
                        best_ll, best_spec = ll, make_spec(family, cand)
                        improved = True
        log(f"  {family}: 국소 개선 {rounds}회차 → {best_ll:.5f}")
    return best_spec, best_ll, sorted(((v[0], v[1]) for v in tried.values()),
                                      key=lambda t: t[0])


def combos(specs: dict) -> list:
    """엔진 이름 → spec. 공집합을 뺀 모든 조합."""
    names = sorted(specs)
    out = []
    for mask in range(1, 2 ** len(names)):
        out.append([names[i] for i in range(len(names)) if mask >> i & 1])
    return out


def stack_of(names, specs, name=None, **kw) -> Candidate:
    feats = []
    for n in names:
        feats.extend(SOLO_FEATURES[n])
    return Candidate(name=name or "stack:" + "+".join(names), kind="stack",
                     engines=[specs[n] for n in names], features=feats, **kw)
