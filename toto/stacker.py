"""특징값 → 승/무/패 확률 — 다항 로지스틱 (예측 모델 경기장 · §1-67).

    z_H = b_H(리그) + w_H · x       z_D = 0       z_A = b_A(리그) + w_A · x
    p = softmax(z)

평점 엔진이 내는 값(평점 차 · 기대 득점 …)은 그 자체로 확률이 아니다. 이
층이 그것을 확률로 옮긴다. 무승부의 기준을 0 에 두고 홈승·원정승을 그 대비
로그 오즈로 맞추므로, '두 팀이 비슷하면 무승부가 늘어난다' 는 관계를
|차이| 같은 특징으로 배울 수 있다.

- **맞추기(`fit`)는 numpy 가 필요하다** — 모델 경기장에서만 부른다.
- **예측(`Stacker.predict`)은 순수 파이썬이다** — 리포트 경로에서 돈다.
- 특징은 맞춘 데이터의 평균·표준편차로 표준화해 계수와 함께 저장한다.
- 리그마다 절편을 따로 둘 수 있다 (`per_league`). 리그마다 홈 이점·무승부
  비율이 다르다. 모르는 리그는 공통 절편을 쓴다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

OUTCOMES = ("H", "D", "A")


# --------------------------------------------------------------------------
# 특징 만들기 — 엔진 출력에서 파생값을 만든다 (산술은 여기 한 곳)
# --------------------------------------------------------------------------
def derive(raw: dict, names) -> list | None:
    """엔진 특징 dict → 이름 순서대로의 값 목록. 하나라도 없으면 None.

    파생 이름 규칙:
      `<stat>_diff` · `<stat>_sum`  = lh − la · lh + la (로그 척도)
      `abs:<이름>`                   = 절댓값
    """
    out = []
    for name in names:
        v = _value(raw, name)
        if v is None:
            return None
        out.append(v)
    return out


def _value(raw, name):
    if name.startswith("abs:"):
        v = _value(raw, name[4:])
        return None if v is None else abs(v)
    if name in raw:
        return raw[name]
    for suffix, sign in (("_diff", -1.0), ("_sum", 1.0)):
        if name.endswith(suffix):
            stat = name[: -len(suffix)]
            lh, la = raw.get(f"{stat}_lh"), raw.get(f"{stat}_la")
            if lh is None or la is None:
                return None
            return lh + sign * la
    return None


# --------------------------------------------------------------------------
# 예측 (순수 파이썬)
# --------------------------------------------------------------------------
@dataclass
class Stacker:
    features: list
    mean: list
    std: list
    w_home: list
    w_away: list
    b_home: dict                     # 리그 → 절편 ("" = 공통)
    b_away: dict
    meta: dict = field(default_factory=dict)

    def predict(self, x, league: str = "") -> tuple:
        """표준화 전 특징값 → (p_H, p_D, p_A)."""
        z = [(v - m) / s for v, m, s in zip(x, self.mean, self.std)]
        zh = self.b_home.get(league, self.b_home[""]) + sum(
            w * v for w, v in zip(self.w_home, z))
        za = self.b_away.get(league, self.b_away[""]) + sum(
            w * v for w, v in zip(self.w_away, z))
        top = max(zh, 0.0, za)
        eh, ed, ea = math.exp(zh - top), math.exp(-top), math.exp(za - top)
        tot = eh + ed + ea
        return eh / tot, ed / tot, ea / tot

    def to_dict(self) -> dict:
        return {"features": list(self.features), "mean": self.mean,
                "std": self.std, "w_home": self.w_home, "w_away": self.w_away,
                "b_home": self.b_home, "b_away": self.b_away, "meta": self.meta}

    @classmethod
    def from_dict(cls, d: dict) -> "Stacker":
        return cls(features=list(d["features"]), mean=list(d["mean"]),
                   std=list(d["std"]), w_home=list(d["w_home"]),
                   w_away=list(d["w_away"]), b_home=dict(d["b_home"]),
                   b_away=dict(d["b_away"]), meta=dict(d.get("meta") or {}))


# --------------------------------------------------------------------------
# 맞추기 (numpy)
# --------------------------------------------------------------------------
def fit(X, y, leagues, features, l2: float = 1.0, per_league: bool = True,
        iterations: int = 30) -> Stacker:
    """뉴턴법으로 L2 벌점 다항 로지스틱을 맞춘다.

    X: n×p 특징 · y: 'H'/'D'/'A' 목록 · leagues: 리그 키 목록.
    절편에는 벌점을 주지 않는다. 결정적이다 (난수 없음).
    """
    import numpy as np

    X = np.asarray(X, dtype=float)
    n, p = X.shape if X.size else (0, len(features))
    mean = X.mean(axis=0) if n else np.zeros(p)
    std = X.std(axis=0) if n else np.ones(p)
    std = np.where(std > 1e-12, std, 1.0)
    Z = (X - mean) / std
    names = sorted(set(leagues)) if per_league else []
    # 설계 행렬: [공통 절편, 리그 절편(첫 리그 제외) …, 특징 …]
    cols = [np.ones(n)]
    for lg in names[1:]:
        cols.append(np.array([1.0 if l == lg else 0.0 for l in leagues]))
    B = np.column_stack(cols + [Z[:, j] for j in range(p)]) if n else np.zeros((0, 1 + max(0, len(names) - 1) + p))
    q = B.shape[1]
    n_int = q - p
    yh = np.array([1.0 if v == "H" else 0.0 for v in y])
    ya = np.array([1.0 if v == "A" else 0.0 for v in y])
    theta = np.zeros(2 * q)
    pen = np.zeros(2 * q)
    pen[n_int:q] = l2
    pen[q + n_int:] = l2
    for _ in range(iterations):
        th, ta = theta[:q], theta[q:]
        zh, za = B @ th, B @ ta
        top = np.maximum(np.maximum(zh, za), 0.0)
        eh, ea, ed = np.exp(zh - top), np.exp(za - top), np.exp(-top)
        tot = eh + ea + ed
        ph, pa = eh / tot, ea / tot
        grad = np.concatenate([B.T @ (yh - ph), B.T @ (ya - pa)]) - pen * theta
        whh, waa, wha = ph * (1 - ph), pa * (1 - pa), -ph * pa
        H = np.block([[B.T @ (B * whh[:, None]), B.T @ (B * wha[:, None])],
                      [B.T @ (B * wha[:, None]), B.T @ (B * waa[:, None])]])
        H += np.diag(pen) + 1e-9 * np.eye(2 * q)
        step = np.linalg.solve(H, grad)
        theta = theta + step
        if float(np.max(np.abs(step))) < 1e-8:
            break
    th, ta = theta[:q], theta[q:]
    b_home = {"": float(th[0])}
    b_away = {"": float(ta[0])}
    for i, lg in enumerate(names):
        b_home[lg] = float(th[0] + (th[i] if i else 0.0))
        b_away[lg] = float(ta[0] + (ta[i] if i else 0.0))
    if names:
        # 모르는 리그는 아는 리그 절편의 평균을 쓴다.
        b_home[""] = sum(b_home[lg] for lg in names) / len(names)
        b_away[""] = sum(b_away[lg] for lg in names) / len(names)
    return Stacker(features=list(features), mean=[float(v) for v in mean],
                   std=[float(v) for v in std],
                   w_home=[float(v) for v in th[n_int:]],
                   w_away=[float(v) for v in ta[n_int:]],
                   b_home=b_home, b_away=b_away,
                   meta={"n": int(n), "l2": l2, "per_league": per_league})
