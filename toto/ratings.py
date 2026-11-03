"""온라인 평점 엔진 — 경기 결과만 보고 배우는 팀 평점 (예측 모델 경기장 · §1-67).

엔진은 **지식 없이 시작한다** — 모든 팀이 리그 평균에서 출발하고, 경기를
하나씩 보며 평점을 고친다. 경기 전에는 그 시점까지 배운 평점으로 특징값을
내고, 경기 뒤에 결과로 배운다. 그래서 특징값은 언제나 **그 경기를 보기 전의
값**이다 — 미래가 섞일 자리가 구조적으로 없다.

    features(경기)  →  예측에 쓰는 값   (경기 전)
    update(경기)    →  결과로 배운다    (경기 뒤)

엔진 넷.

| 이름 | 무엇을 배우나 | 특징값 |
|---|---|---|
| `elo` | 승패(+득실차 배수) | 두 팀 평점 차 |
| `pi` | 득실차 · 홈/원정 평점을 따로 (Constantinou & Fenton 2013) | 예상 득실차 |
| `dp` | 득점(또는 유효슈팅·슈팅) 의 공격·수비 — 온라인 포아송 | 양 팀 기대값(로그) |

이 모듈은 **순수 파이썬**이다 (numpy 없음). 사용자 PC 의 리포트 경로에서
그대로 돈다. 같은 입력이면 같은 출력이다 (난수 없음).

## 시즌 경계

리그의 시즌이 바뀌면 (1) 지난 시즌에 뛴 팀의 평점을 리그 평균 쪽으로
`carry` 만큼 당기고, (2) 지난 시즌에 없던 팀(승격·복귀)은 **지난 시즌 하위
`PROMOTED_K` 팀의 평균**에서 시작한다. 승격팀은 강등팀과 비슷하다는 관측에
기댄 것이고, 리그 평균에서 시작하면 승격팀을 과대평가한다.

## 시장 확률과 무관하다

배당을 읽지 않는다. `predict`·`Match.probs` 를 참조하지 않는다 (테스트).
"""
from __future__ import annotations

import math

PROMOTED_K = 3


def _mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


class _League:
    """한 리그의 시즌 기록 — 어느 팀이 어느 시즌에 뛰었나."""

    __slots__ = ("season", "prev", "played", "prior")

    def __init__(self):
        self.season = None          # 지금 시즌
        self.prev = None            # 바로 전 시즌
        self.played = {}            # 팀 → 마지막으로 뛴 시즌
        self.prior = None           # 승격팀 시작값 (엔진마다 모양이 다르다)


class Engine:
    """엔진 공통 뼈대. 하위 클래스가 `_vec`·`_set_vec`·`_init_vec`·
    `_features`·`_learn` 을 채운다. 팀 상태는 숫자 튜플 하나다."""

    kind = ""

    def __init__(self, **params):
        self.params = dict(params)
        self.teams = {}             # (리그, 팀) → 튜플
        self.leagues = {}           # 리그 → _League
        self.globals = {}           # 리그 → 리그 전체 값 (엔진마다)

    # ---- 이름 ----------------------------------------------------------
    @property
    def name(self) -> str:
        bits = [f"{k}{self.params[k]:g}" if isinstance(self.params[k], (int, float))
                else f"{k}{self.params[k]}" for k in sorted(self.params)]
        return f"{self.kind}[{','.join(bits)}]"

    # ---- 시즌 ----------------------------------------------------------
    def _league(self, league) -> _League:
        lg = self.leagues.get(league)
        if lg is None:
            lg = self.leagues[league] = _League()
        return lg

    def see_season(self, league: str, season: str) -> None:
        """경기마다 부른다. 시즌이 바뀌었으면 평점을 당기고 승격팀 시작값을 정한다."""
        lg = self._league(league)
        if lg.season == season:
            return
        if lg.season is not None:
            lg.prev = lg.season
            last = [t for t, s in lg.played.items() if s == lg.prev]
            self._regress(league, last)
            vecs = sorted((self.teams[(league, t)] for t in last),
                          key=self._strength)
            bottom = vecs[:PROMOTED_K]
            lg.prior = (tuple(_mean(v[i] for v in bottom)
                              for i in range(len(bottom[0])))
                        if bottom else None)
        lg.season = season

    def _regress(self, league, teams) -> None:
        carry = float(self.params.get("carry", 1.0))
        if not teams or carry >= 1.0:
            return
        vecs = [self.teams[(league, t)] for t in teams]
        means = [_mean(v[i] for v in vecs) for i in range(len(vecs[0]))]
        for t in teams:
            v = self.teams[(league, t)]
            self.teams[(league, t)] = tuple(m + carry * (x - m)
                                            for x, m in zip(v, means))

    def _team(self, league: str, team: str) -> tuple:
        """그 팀의 상태. 처음 보거나(승격) 쉬었다 돌아온 팀은 시작값으로 연다."""
        lg = self._league(league)
        key = (league, team)
        last = lg.played.get(team)
        if key not in self.teams or (last is not None and last not in
                                     (lg.season, lg.prev)):
            self.teams[key] = (lg.prior if lg.prior is not None
                               else self._init_vec(league))
        return self.teams[key]

    def _mark(self, league, *teams) -> None:
        lg = self._league(league)
        for t in teams:
            lg.played[t] = lg.season

    # ---- 바깥에서 부르는 것 --------------------------------------------
    def features(self, m) -> dict:
        self.see_season(m.league, m.season)
        return self._features(m.league, self._team(m.league, m.home),
                              self._team(m.league, m.away))

    def update(self, m) -> None:
        self.see_season(m.league, m.season)
        h = self._team(m.league, m.home)
        a = self._team(m.league, m.away)
        out = self._learn(m, h, a)
        if out is None:              # 배울 값이 없는 경기 (슈팅 칸이 비었다)
            return
        self.teams[(m.league, m.home)], self.teams[(m.league, m.away)] = out
        self._mark(m.league, m.home, m.away)

    # ---- 저장 ----------------------------------------------------------
    def state(self) -> dict:
        return {
            "kind": self.kind, "params": self.params,
            "teams": [[lg, t, list(v)] for (lg, t), v in sorted(self.teams.items())],
            "leagues": {k: {"season": v.season, "prev": v.prev,
                            "played": dict(sorted(v.played.items())),
                            "prior": list(v.prior) if v.prior else None}
                        for k, v in sorted(self.leagues.items())},
            "globals": {k: list(v) for k, v in sorted(self.globals.items())},
        }

    @classmethod
    def from_state(cls, data: dict) -> "Engine":
        target = ENGINES[data["kind"]]
        if cls is Engine and target.from_state.__func__ is not Engine.from_state.__func__:
            return target.from_state(data)      # 선수·명단을 따로 들고 있는 엔진
        eng = target(**data["params"])
        eng.teams = {(lg, t): tuple(v) for lg, t, v in data["teams"]}
        for k, v in data["leagues"].items():
            lg = eng._league(k)
            lg.season, lg.prev = v["season"], v["prev"]
            lg.played = dict(v["played"])
            lg.prior = tuple(v["prior"]) if v.get("prior") else None
        eng.globals = {k: tuple(v) for k, v in data["globals"].items()}
        return eng

    # ---- 하위 클래스 ----------------------------------------------------
    def _init_vec(self, league) -> tuple:
        raise NotImplementedError

    def _strength(self, vec) -> float:
        raise NotImplementedError

    def _features(self, league, h, a) -> dict:
        raise NotImplementedError

    def _learn(self, m, h, a):
        raise NotImplementedError


# --------------------------------------------------------------------------
# Elo
# --------------------------------------------------------------------------
class Elo(Engine):
    """승/무/패 Elo. `gd` 가 득실차 배수를 정한다 (none · log · wfe)."""

    kind = "elo"

    def __init__(self, k: float = 20.0, hfa: float = 60.0, carry: float = 0.8,
                 gd: str = "log"):
        super().__init__(k=k, hfa=hfa, carry=carry, gd=gd)

    def _init_vec(self, league):
        return (0.0,)

    def _strength(self, vec):
        return vec[0]

    def _features(self, league, h, a):
        return {"elo_diff": (h[0] - a[0]) / 100.0}

    def _mult(self, gd: int) -> float:
        mode, n = self.params["gd"], abs(gd)
        if mode == "none" or n <= 1:
            return 1.0
        if mode == "log":
            return 1.0 + math.log(n)
        # World Football Elo
        return 1.5 if n == 2 else (11.0 + n) / 8.0

    def _learn(self, m, h, a):
        exp = 1.0 / (1.0 + 10.0 ** (-(h[0] - a[0] + self.params["hfa"]) / 400.0))
        s = 1.0 if m.hg > m.ag else 0.5 if m.hg == m.ag else 0.0
        delta = self.params["k"] * self._mult(m.hg - m.ag) * (s - exp)
        return (h[0] + delta,), (a[0] - delta,)


# --------------------------------------------------------------------------
# pi-rating
# --------------------------------------------------------------------------
PI_C = 3.0


def _pi_goals(r: float) -> float:
    return math.copysign(10.0 ** (abs(r) / PI_C) - 1.0, r)


class Pi(Engine):
    """pi-rating — 팀마다 홈 평점·원정 평점 (Constantinou & Fenton 2013)."""

    kind = "pi"

    def __init__(self, lam: float = 0.035, gamma: float = 0.7, carry: float = 1.0,
                 mix: float = 0.0):
        # mix > 0 이면 xG 가 있는 경기에서 득실차 대신 (1−mix)·득실차 + mix·xG 차를
        # 배운다 (§1-68). 없으면 params 에 남기지 않아 옛 spec·id 가 그대로다.
        params = dict(lam=lam, gamma=gamma, carry=carry)
        if mix:
            params["mix"] = mix
        super().__init__(**params)

    def _init_vec(self, league):
        return (0.0, 0.0)              # (홈 평점, 원정 평점)

    def _strength(self, vec):
        return vec[0] + vec[1]

    def _features(self, league, h, a):
        return {"pi_gd": _pi_goals(h[0]) - _pi_goals(a[1])}

    def _learn(self, m, h, a):
        lam, gamma = self.params["lam"], self.params["gamma"]
        margin = m.hg - m.ag
        mix = self.params.get("mix", 0.0)
        xh, xa = getattr(m, "hxg", None), getattr(m, "axg", None)
        if mix and xh is not None and xa is not None:
            margin = (1 - mix) * margin + mix * (xh - xa)
        err = margin - (_pi_goals(h[0]) - _pi_goals(a[1]))
        psi = math.copysign(PI_C * math.log10(1.0 + abs(err)), err)
        dh = psi * lam
        da = -psi * lam
        return ((h[0] + dh, h[1] + dh * gamma),
                (a[0] + da * gamma, a[1] + da))


# --------------------------------------------------------------------------
# 온라인 포아송 (득점 · 유효슈팅 · 슈팅)
# --------------------------------------------------------------------------
STAT_COLUMNS = {
    "goals": ("hg", "ag", 1.35),
    "sot": ("hst", "ast", 4.4),
    "shots": ("hs", "as_", 12.5),
    # FotMob 경기 상세 (§1-68) — 2020/21 부터. 값이 없는 경기는 배우지 않는다.
    "xg": ("hxg", "axg", 1.35),
    "npxg": ("hnpxg", "anpxg", 1.25),
    "xgot": ("hxgot", "axgot", 1.3),
    "bigch": ("hbc", "abc", 2.0),
    "touch": ("htb", "atb", 25.0),
}


class DynPoisson(Engine):
    """log λ_홈 = μ + 홈 + 공격_홈 − 수비_원정 · log λ_원정 = μ + 공격_원정 − 수비_홈.

    경기 뒤에 포아송 우도의 기울기로 한 걸음 간다 (`eta`). 리그 평균 μ 와
    홈 이점은 `eta_g` 로 천천히 배운다 — 무관중 시즌처럼 홈 이점이 바뀌어도
    따라간다.
    """

    kind = "dp"

    def __init__(self, stat: str = "goals", eta: float = 0.03,
                 eta_g: float = 0.002, carry: float = 0.8, mix: float = 0.0,
                 tag: str = ""):
        # mix > 0 이면 '득점' 엔진이 xG 가 있는 경기에서 (1−mix)·득점 + mix·xG 를
        # 배운다 (§1-68). 특징 이름은 그대로라 xG 이전 시즌과 같은 출력층을 쓴다.
        # tag 가 있으면 특징 이름의 머리를 바꾼다 — 같은 지표를 다른 속도로 도는
        # 엔진 둘을 함께 쓸 때 이름이 겹치지 않게 한다.
        params = dict(stat=stat, eta=eta, eta_g=eta_g, carry=carry)
        if mix:
            params["mix"] = mix
        if tag:
            params["tag"] = tag
        super().__init__(**params)

    def _cols(self):
        return STAT_COLUMNS[self.params["stat"]]

    def _glob(self, league) -> tuple:
        g = self.globals.get(league)
        if g is None:
            g = self.globals[league] = (math.log(self._cols()[2]), 0.25)
        return g

    def _init_vec(self, league):
        return (0.0, 0.0)              # (공격, 수비) — 로그 척도, 0 = 리그 평균

    def _strength(self, vec):
        return vec[0] + vec[1]

    def rates(self, league, h, a) -> tuple:
        mu, home = self._glob(league)
        return (math.exp(mu + home + h[0] - a[1]), math.exp(mu + a[0] - h[1]))

    def _features(self, league, h, a):
        lh, la = self.rates(league, h, a)
        p = self.params.get("tag") or self.params["stat"]
        return {f"{p}_lh": math.log(lh), f"{p}_la": math.log(la)}

    def _learn(self, m, h, a):
        ch, ca, _ = self._cols()
        yh, ya = getattr(m, ch, None), getattr(m, ca, None)
        if yh is None or ya is None:
            return None
        mix = self.params.get("mix", 0.0)
        if mix:
            xh, xa = getattr(m, "hxg", None), getattr(m, "axg", None)
            if xh is not None and xa is not None:
                yh, ya = (1 - mix) * yh + mix * xh, (1 - mix) * ya + mix * xa
        lh, la = self.rates(m.league, h, a)
        rh, ra = yh - lh, ya - la
        # 큰 값의 지표(슈팅)일수록 잔차가 커진다 — 기대값으로 나눠 걸음 크기를 맞춘다.
        scale = self._cols()[2]
        eta = self.params["eta"] / scale
        mu, home = self._glob(m.league)
        g = self.params["eta_g"] / scale
        self.globals[m.league] = (mu + g * (rh + ra) / 2.0, home + g * (rh - ra) / 2.0)
        return ((h[0] + eta * rh, h[1] - eta * ra),
                (a[0] + eta * ra, a[1] - eta * rh))

    def _regress(self, league, teams) -> None:
        # 평균으로 당기기 전에 공격·수비의 평균을 μ 로 옮긴다 (식별 표류를 막는다).
        if teams:
            vecs = [self.teams[(league, t)] for t in teams]
            ma, md = _mean(v[0] for v in vecs), _mean(v[1] for v in vecs)
            mu, home = self._glob(league)
            self.globals[league] = (mu + ma - md, home)
            for t in teams:
                v = self.teams[(league, t)]
                self.teams[(league, t)] = (v[0] - ma, v[1] - md)
        super()._regress(league, teams)


# --------------------------------------------------------------------------
# 선형 평점 — 경기별 차이(득실차·xG 차·팀 평점 차)를 직접 배운다
# --------------------------------------------------------------------------
LIN_COLUMNS = {
    "gd": ("hg", "ag"),
    "xgd": ("hxg", "axg"),
    "rating": ("hrat", "arat"),     # FotMob 팀 평점 (§1-68)
}


class LinRating(Engine):
    """r_홈 − r_원정 + 홈이점 ≈ 관측된 차이. 오차만큼 `k` 로 고친다 (Massey 의 온라인판)."""

    kind = "lin"

    def __init__(self, stat: str = "xgd", k: float = 0.05, carry: float = 0.8,
                 hfa_lr: float = 0.002):
        super().__init__(stat=stat, k=k, carry=carry, hfa_lr=hfa_lr)

    def _glob(self, league) -> tuple:
        g = self.globals.get(league)
        if g is None:
            g = self.globals[league] = (0.0,)
        return g

    def _init_vec(self, league):
        return (0.0,)

    def _strength(self, vec):
        return vec[0]

    def _features(self, league, h, a):
        return {f"{self.params['stat']}_m": h[0] - a[0] + self._glob(league)[0]}

    def _learn(self, m, h, a):
        ch, ca = LIN_COLUMNS[self.params["stat"]]
        yh, ya = getattr(m, ch, None), getattr(m, ca, None)
        if yh is None or ya is None:
            return None
        hfa = self._glob(m.league)[0]
        err = (yh - ya) - (h[0] - a[0] + hfa)
        self.globals[m.league] = (hfa + self.params["hfa_lr"] * err,)
        k = self.params["k"]
        return (h[0] + k * err,), (a[0] - k * err,)


# --------------------------------------------------------------------------
# 순위표 — 그 경기에 걸린 것이 있나 (§1-68)
# --------------------------------------------------------------------------
def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


class Table(Engine):
    """이번 시즌 순위표를 결과만으로 쌓고, 경기 전에 '걸린 것' 을 잰다.

    우승·유럽대회권·강등권 세 경계마다 그 팀이 경계에서 몇 점 떨어져 있는지를
    남은 경기로 딸 수 있는 승점(3 × 남은 경기 + slack)에 견준다. 경계에 붙어
    있으면 1, 남은 경기를 다 이기거나 져도 닿지 않으면 0 이다. 시즌 초에는
    누구나 1 이고, 시즌 끝으로 갈수록 '아무것도 걸리지 않은 팀' 이 0 이 된다.

    시즌 길이는 지난 시즌 한 팀의 최대 경기 수로 정한다 (처음 시즌은
    2 × (팀 수 − 1)). 강등·유럽대회 자리 수는 리그마다 다르지만 매개변수
    하나로 근사한다 — 경계의 정확한 위치보다 '경계 근처인가' 를 본다.
    팀 상태 = (승점, 경기 수, 득실차) — 이번 시즌 값이다.
    """

    kind = "tbl"

    def __init__(self, rel: int = 3, eur: int = 4, slack: float = 3.0):
        super().__init__(rel=rel, eur=eur, slack=slack)

    def _init_vec(self, league):
        return (0.0, 0.0, 0.0)

    def _strength(self, vec):
        return vec[0]

    def _regress(self, league, teams) -> None:
        return None

    def see_season(self, league: str, season: str) -> None:
        lg = self._league(league)
        if lg.season == season:
            return
        if lg.season is not None:
            mine = [k for k in self.teams if k[0] == league]
            longest = max((self.teams[k][1] for k in mine), default=0.0)
            if longest > 0:
                self.globals[league] = (float(longest), float(len(mine)))
            for k in mine:
                del self.teams[k]
        lg.prev, lg.season = lg.season, season

    def _team(self, league: str, team: str) -> tuple:
        return self.teams.get((league, team), (0.0, 0.0, 0.0))

    def _stakes(self, league, team, ranked, length) -> tuple:
        pts, played, _ = self._team(league, team)
        n = len(ranked)
        rank = next((i + 1 for i, (t, _v) in enumerate(ranked) if t == team), n + 1)
        # 딸 수 있는 승점 + 여유. 마지막 경기(남은 경기 0 · slack 0)에서도 1점은 둔다.
        cap = max(1.0, 3.0 * max(0.0, length - played) + float(self.params["slack"]))

        def pts_at(pos):
            if 1 <= pos <= n:
                return ranked[pos - 1][1][0]
            return 0.0

        def alive(boundary):            # boundary = 경계 위쪽 마지막 자리
            if boundary < 1 or boundary >= n:
                return 0.0
            other = boundary + 1 if rank <= boundary else boundary
            return _clip01(1.0 - abs(pts - pts_at(other)) / cap)

        top = alive(1)
        eur = alive(int(self.params["eur"]))
        rel = alive(n - int(self.params["rel"]))
        return top, eur, rel, max(top, eur, rel), (played / length if length else 0.0)

    def features(self, m) -> dict:
        self.see_season(m.league, m.season)
        mine = [(k[1], v) for k, v in self.teams.items() if k[0] == m.league]
        for t in (m.home, m.away):
            if all(t != x for x, _ in mine):
                mine.append((t, (0.0, 0.0, 0.0)))
        g = self.globals.get(m.league)
        n = max(len(mine), int(g[1]) if g else 0)
        length = g[0] if g else 2.0 * (n - 1)
        ranked = sorted(mine, key=lambda kv: (-kv[1][0], -kv[1][2], kv[0]))
        th, eh, rh, sh, lh = self._stakes(m.league, m.home, ranked, length)
        ta, ea, ra, sa, la = self._stakes(m.league, m.away, ranked, length)
        late = 0.5 * (lh + la)
        return {"tbl_st_h": sh, "tbl_st_a": sa, "tbl_st_diff": sh - sa,
                "tbl_top_diff": th - ta, "tbl_eur_diff": eh - ea,
                "tbl_rel_diff": rh - ra, "tbl_late": late,
                "tbl_dead_sum": late * ((1.0 - sh) + (1.0 - sa)),
                "tbl_lst_diff": late * (sh - sa)}

    def update(self, m) -> None:
        self.see_season(m.league, m.season)
        for team, gf, ga in ((m.home, m.hg, m.ag), (m.away, m.ag, m.hg)):
            pts, played, gd = self._team(m.league, team)
            win = 3.0 if gf > ga else 1.0 if gf == ga else 0.0
            self.teams[(m.league, team)] = (pts + win, played + 1.0, gd + gf - ga)
        self._mark(m.league, m.home, m.away)


# --------------------------------------------------------------------------
# 선수 — 직전 리그 경기 선발 11명의 힘 (§1-68)
# --------------------------------------------------------------------------
class Player(Engine):
    """선수마다 경기 차이(기본 xG 차)에 대한 기여 r 를 온라인으로 배운다.

        예측 = Σ(홈 출전 선수 w·r) − Σ(원정 출전 선수 w·r) + 홈이점
        오차만큼 그 경기에 뛴 선수 각자를 w(출전 분 / 90)에 비례해 고친다.

    선수 값은 **팀이 아니라 선수에** 붙어 이적해도 따라간다. 경기 전 특징값은
    그 팀의 **직전 리그 경기 선발 11명**의 r 합이다. FotMob 경기 평점의
    지수평균도 함께 낸다. 선발 명단이 없는 경기는 배우지 않는다.

    결장 명단(`unavailable`)은 쓰지 않는다 — 과거 기록의 명단은 경기 **뒤**에
    정리된 것(실제로 빠진 선수)이라 킥오프 전 명단('Doubtful' 포함)과 다르다.
    그것으로 맞추면 경기 전에 알 수 없던 정보가 섞인다.
    """

    kind = "ply"

    def __init__(self, k: float = 0.006, alpha: float = 0.1, prior: float = 0.0,
                 rk: float = 3.0, target: str = "xgd"):
        super().__init__(k=k, alpha=alpha, prior=prior, rk=rk, target=target)
        self.players = {}          # 선수 → [r, 경기 수, 평점 평균]
        self.lastxi = {}           # (리그, 팀) → [선수]

    def _init_vec(self, league):
        return (0.0,)

    def _strength(self, vec):
        return 0.0

    def _regress(self, league, teams) -> None:
        return None

    def see_season(self, league: str, season: str) -> None:
        lg = self._league(league)
        if lg.season != season:
            lg.prev, lg.season = lg.season, season

    def _side(self, m, team) -> tuple:
        xi = self.lastxi.get((m.league, team))
        if not xi:
            return 0.0, 0.0
        prior, rk = float(self.params["prior"]), float(self.params["rk"])
        s = q = 0.0
        for pid in xi:
            st = self.players.get(pid)
            r, n, ema = st if st else (prior, 0, 6.7)
            s += r
            q += (n * ema + rk * 6.7) / (n + rk)
        return s, q / len(xi)

    def features(self, m) -> dict:
        self.see_season(m.league, m.season)
        sh, qh = self._side(m, m.home)
        sa, qa = self._side(m, m.away)
        both = 1.0 if (self.lastxi.get((m.league, m.home))
                       and self.lastxi.get((m.league, m.away))) else 0.0
        return {"ply_diff": both * (sh - sa), "plyq_diff": both * (qh - qa),
                "ply_has": both}

    @staticmethod
    def _played(lu) -> dict:
        out = {}
        for pid, rating, off, _pos in lu.get("starters") or []:
            out[str(pid)] = ((off if off else 90) / 90.0, rating)
        for pid, rating, on, _pos in lu.get("subs") or []:
            w = max(0.0, 90 - (on if on is not None else 90)) / 90.0
            if w > 0:
                out[str(pid)] = (w, rating)
        return out

    def update(self, m) -> None:
        self.see_season(m.league, m.season)
        lineup = getattr(m, "lineup", None) or {}
        lh, la = lineup.get("home") or {}, lineup.get("away") or {}
        ph, pa = self._played(lh), self._played(la)
        if not ph or not pa:
            return
        if self.params["target"] == "xgd" and m.hxg is not None and m.axg is not None:
            y = m.hxg - m.axg
        else:
            y = float(m.hg - m.ag)
        prior = float(self.params["prior"])
        g = self.globals.get(m.league, (0.0,))[0]
        def r_of(pid):
            st = self.players.get(pid)
            return st[0] if st else prior
        pred = (sum(w * r_of(p) for p, (w, _) in ph.items())
                - sum(w * r_of(p) for p, (w, _) in pa.items()) + g)
        err = y - pred
        self.globals[m.league] = (g + 0.002 * err,)
        k, a = float(self.params["k"]), float(self.params["alpha"])
        for sign, played in ((1.0, ph), (-1.0, pa)):
            for pid, (w, rating) in played.items():
                st = self.players.get(pid)
                if st is None:
                    st = self.players[pid] = [prior, 0, 6.7]
                st[0] += k * err * w * sign
                if isinstance(rating, (int, float)) and rating > 0:
                    st[2] = rating if st[1] == 0 else (1 - a) * st[2] + a * rating
                    st[1] += 1
        for side, team, lu in (("home", m.home, lh), ("away", m.away, la)):
            xi = [str(r[0]) for r in lu.get("starters") or []]
            if xi:
                self.lastxi[(m.league, team)] = xi
        self._mark(m.league, m.home, m.away)

    def state(self) -> dict:
        out = super().state()
        out["players"] = {p: [round(v[0], 5), v[1], round(v[2], 3)]
                          for p, v in sorted(self.players.items())}
        out["lastxi"] = [[lg, t, xi] for (lg, t), xi in sorted(self.lastxi.items())]
        return out

    @classmethod
    def from_state(cls, data: dict) -> "Engine":
        eng = Engine.from_state.__func__(cls, data)
        eng.players = {p: list(v) for p, v in data.get("players", {}).items()}
        eng.lastxi = {(lg, t): list(xi) for lg, t, xi in data.get("lastxi", [])}
        return eng


ENGINES = {cls.kind: cls for cls in (Elo, Pi, DynPoisson, LinRating, Table, Player)}


def make(spec: dict) -> Engine:
    """{'kind': 'elo', 'k': 20, ...} → 엔진."""
    spec = dict(spec)
    return ENGINES[spec.pop("kind")](**spec)


def spec_of(engine: Engine) -> dict:
    return {"kind": engine.kind, **engine.params}


# --------------------------------------------------------------------------
# 여러 엔진을 한 번에 돌린다
# --------------------------------------------------------------------------
def replay(matches, engines, on_features=None) -> list:
    """경기를 날짜순으로 보며 특징값을 모은다. [(경기, {특징})].

    같은 날짜의 경기는 **모두 예측한 뒤** 결과로 배운다 — 같은 날 먼저 끝난
    경기의 결과를 뒤 경기 예측에 쓰지 않는다 (보수적). `matches` 는 날짜순으로
    정렬돼 있어야 한다 (`history.load` 가 그렇게 준다).
    """
    out = []
    day, batch = None, []

    def flush():
        for m in batch:
            for e in engines:
                e.update(m)

    for m in matches:
        if m.date != day:
            flush()
            day, batch = m.date, []
        feats = {}
        for e in engines:
            feats.update(e.features(m))
        if on_features is not None:
            on_features(m, feats)
        out.append((m, feats))
        batch.append(m)
    flush()
    return out
