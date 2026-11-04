"""통계 모델 백테스트 — 시즌 경기 색인으로, 미래를 섞지 않고 (읽기만 한다).

    python tools/backtest_statmodel.py                 # data/artifacts/*.json 전부
    python tools/backtest_statmodel.py --artifacts data/artifacts/260065.json
    python tools/backtest_statmodel.py --half-lives 0 60 30 --shrinks 3 5 10

무엇을 하나.

  1. 저장본들의 시즌 경기 색인을 모아(경기 ID 로 중복 제거) 국내리그 종료
     경기마다 **그 경기 킥오프 이전 경기만으로** 모델을 맞춰 예측한다
     (`statmodel.forecast` → `models.matches_before`). 시즌 색인은 최종
     스코어와 킥오프를 갖고 있어 과거 시점으로 잘린다 (§1-13 HISTORICAL_AS_OF).
  2. 안마다 승무패 방향 적중 · Brier · RPS · log loss 를 **같은 경기 집합**에서
     잰다.
  3. `data/round_matches.csv` 에 킥오프 전 시장 확률이 있는 경기는 시장과
     같은 경기에서 견준다 (경기 ID 로 잇는다).
  4. 같은 경기에서 **시장 확률과 모델 확률을 섞은 예측**이 시장만 쓴 것보다
     나은지 본다 — 모델이 시장에 **더할 정보**가 있는지를 묻는다. 섞는 비율은
     **회차 하나를 빼고 나머지 회차로 고른 뒤** 뺀 회차에 쓴다(교차검증).
     같은 경기로 고르고 같은 경기로 채점하면 언제나 좋아 보인다. 시장과의
     차이는 경기별 짝 차이의 평균 ± 표준오차로 적는다.

**운영 확률과 섞지 않는다.** 혼합은 이 도구 안의 비교일 뿐이고
`Match.probs`·리포트·패널 어디에도 가지 않는다 (§1-27).

**쓰지 않는다.** 저장본·CSV·캐시 어느 것도 바꾸지 않는다. `--json` 을 주면
그 경로에만 쓰고, 저장소 안이면 거부한다.

**검증된 기준이 아니다.** 안을 여럿 견주면 그중 하나는 운으로 좋아 보인다.
기준 안과 결과가 갈린 경기 수(맞힌 쪽 / 틀린 쪽)를 함께 적으니 그것을 본다.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from toto import artifact, marketeval, roundlog, statmodel   # noqa: E402
from toto.settings import load_settings                      # noqa: E402

OUTCOMES = statmodel.OUTCOMES
LOG_EPS = 1e-15
BLEND_WEIGHTS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)   # 모델 쪽 비중. 0 = 시장만


def normalized(probs: dict) -> dict:
    """합을 1 로 맞춘 승/무/패 (모델의 0~9골 절단분 · 시장의 반올림을 나눠 맞춘다)."""
    total = sum(probs[o] for o in OUTCOMES)
    return {o: probs[o] / total for o in OUTCOMES}


def brier_of(p: dict, actual: str) -> float:
    return sum((p[o] - (1.0 if o == actual else 0.0)) ** 2 for o in OUTCOMES)


def rps_of(p: dict, actual: str) -> float:
    """Ranked Probability Score (승→무→패 순서를 반영). 0~1, 낮을수록 좋음.

    `(1/(r−1)) Σ_{i<r} (누적 예측_i − 누적 실제_i)²`, r=3.
    """
    cum_p = cum_y = total = 0.0
    for o in OUTCOMES[:-1]:
        cum_p += p[o]
        cum_y += 1.0 if o == actual else 0.0
        total += (cum_p - cum_y) ** 2
    return total / (len(OUTCOMES) - 1)


def blend(market: dict, model: dict, w: float) -> dict:
    """선형 혼합 `(1−w)·시장 + w·모델`. 둘 다 합 1 로 맞춘 뒤 섞는다."""
    m, f = normalized(market), normalized(model)
    return {o: (1.0 - w) * m[o] + w * f[o] for o in OUTCOMES}


def actual_of(m) -> str:
    return ("H" if m.home_goals > m.away_goals
            else "D" if m.home_goals == m.away_goals else "A")


# --------------------------------------------------------------------------
# 입력
# --------------------------------------------------------------------------
def load_season(paths) -> tuple:
    """저장본들 → (시즌 경기 목록, 읽은 파일, 못 읽은 파일+사유). 경기 ID 로 중복 제거.

    같은 경기가 여러 저장본에 있으면 **종료된 판**을 남긴다 (나중 저장본일수록
    결과가 차 있다). 경기 ID 가 없는 경기는 색인에 들어오지 않는다(§1-1-4).
    """
    best: dict = {}
    read, failed = [], []
    for path in sorted(paths):
        report, why = artifact.load_path(Path(path))
        if report is None:
            failed.append((str(path), why))
            continue
        read.append(str(path))
        for m in report.season_matches or []:
            if not m.match_id:
                continue
            old = best.get(m.match_id)
            if old is None or (m.finished and not old.finished):
                best[m.match_id] = m
    season = sorted(best.values(), key=lambda m: m.sort_key)
    return season, read, failed


def market_by_match_id(path: Path | None = None) -> dict:
    """{경기 ID: (회차, 번호, 시장 확률 dict)} — 킥오프 전 확률만 (`marketeval.select`)."""
    raw = roundlog._read(path or roundlog.MATCH_FILE, roundlog.MATCH_FIELDS)
    ids = {(str(r.get("round") or "").strip(), str(r.get("no") or "").strip()):
           (r.get("match_id") or "").strip() for r in raw}
    picked, _ = marketeval.select(raw)
    out = {}
    for row in picked:
        mid = ids.get((row.round_id, str(row.no)))
        if mid:
            out[mid] = (row.round_id, row.no, dict(row.market))
    return out


# --------------------------------------------------------------------------
# 채점
# --------------------------------------------------------------------------
@dataclass
class Score:
    n: int = 0
    hits: int = 0
    brier: float = 0.0
    rps: float = 0.0
    logloss: float = 0.0
    fav: Counter = field(default_factory=Counter)
    fav_hits: Counter = field(default_factory=Counter)

    def add(self, probs: dict, actual: str) -> None:
        p = normalized(probs)                            # 0~9골 절단분을 나눠 맞춘다
        fav = max(OUTCOMES, key=lambda o: p[o])
        self.n += 1
        self.hits += int(fav == actual)
        self.fav[fav] += 1
        self.fav_hits[fav] += int(fav == actual)
        self.brier += brier_of(p, actual)
        self.rps += rps_of(p, actual)
        self.logloss -= math.log(max(p[actual], LOG_EPS))

    def line(self, name: str) -> str:
        if not self.n:
            return f"{name:<22}표본 없음"
        acc = self.hits / self.n
        se = math.sqrt(acc * (1 - acc) / self.n)
        favs = " ".join(f"{o}{self.fav[o]}({self.fav_hits[o]})" for o in OUTCOMES)
        return (f"{name:<22}{self.hits:>4}/{self.n:<4} {acc * 100:5.1f}% "
                f"±{se * 100:4.1f} · Brier {self.brier / self.n:.4f} · "
                f"RPS {self.rps / self.n:.4f} · "
                f"log {self.logloss / self.n:.4f} · 고른 결과 {favs}")


# --------------------------------------------------------------------------
# 시장 + 모델 혼합 — 모델이 시장에 더할 정보가 있나
# --------------------------------------------------------------------------
def paired(diffs: list) -> tuple:
    """경기별 짝 차이 → (평균, 표준오차, 경기 수). 경기가 2 미만이면 표준오차 None."""
    n = len(diffs)
    if not n:
        return None, None, 0
    mean = sum(diffs) / n
    if n < 2:
        return mean, None, n
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    return mean, math.sqrt(var / n), n


def verdict(mean, se) -> str:
    """짝 차이(혼합 − 시장)의 판정. 낮을수록 좋은 지표 기준. 2 표준오차로만 가른다."""
    if mean is None or not se:
        return "판정 불가 (표본 부족)"
    if mean + 2 * se < 0:
        return "시장보다 낮다 (2 표준오차 밖)"
    if mean - 2 * se > 0:
        return "시장보다 높다 (2 표준오차 밖)"
    return "시장과 구별되지 않는다"


def blend_study(rows: list, weights=BLEND_WEIGHTS) -> dict:
    """rows = [(회차, 시장 확률, 모델 확률, 실제)] → 혼합 비교.

      · in_sample — 비중마다 같은 경기에서 잰 평균 Brier·RPS. **고르는 데 쓴
        경기로 채점한 값이라 낙관적이다.** 곡선 모양만 본다.
      · cv — 회차 하나를 빼고 나머지 회차의 Brier 가 가장 낮은 비중을 골라
        뺀 회차에 쓴다(동점이면 작은 비중 = 시장 쪽). 회차가 둘 미만이면 없다.
      · vs_market — 교차검증 혼합 − 시장, 모델만 − 시장의 경기별 짝 차이.
    """
    out = {"n": len(rows), "weights": list(weights), "in_sample": {},
           "cv": None, "chosen": {}, "model_only": None}
    if not rows:
        return out
    for w in weights:
        b = [brier_of(blend(m, f, w), y) for _r, m, f, y in rows]
        r = [rps_of(blend(m, f, w), y) for _r, m, f, y in rows]
        out["in_sample"][w] = (sum(b) / len(b), sum(r) / len(r))
    base_b = [brier_of(normalized(m), y) for _r, m, f, y in rows]
    base_r = [rps_of(normalized(m), y) for _r, m, f, y in rows]
    only_b = [brier_of(normalized(f), y) for _r, m, f, y in rows]
    only_r = [rps_of(normalized(f), y) for _r, m, f, y in rows]
    out["model_only"] = {
        "brier": paired([a - b for a, b in zip(only_b, base_b)]),
        "rps": paired([a - b for a, b in zip(only_r, base_r)])}
    rounds = sorted({r for r, *_ in rows})
    if len(rounds) < 2:
        return out
    cv_b, cv_r = [0.0] * len(rows), [0.0] * len(rows)
    for held in rounds:
        train = [row for row in rows if row[0] != held]

        def train_brier(w, train=train):
            return sum(brier_of(blend(m, f, w), y)
                       for _r, m, f, y in train) / len(train)
        best = min(weights, key=lambda w: (train_brier(w), w))
        out["chosen"][held] = best
        for i, (r, m, f, y) in enumerate(rows):
            if r == held:
                p = blend(m, f, best)
                cv_b[i], cv_r[i] = brier_of(p, y), rps_of(p, y)
    out["cv"] = {
        "brier": sum(cv_b) / len(cv_b), "rps": sum(cv_r) / len(cv_r),
        "market_brier": sum(base_b) / len(base_b),
        "market_rps": sum(base_r) / len(base_r),
        "diff_brier": paired([a - b for a, b in zip(cv_b, base_b)]),
        "diff_rps": paired([a - b for a, b in zip(cv_r, base_r)])}
    return out


def _diff_text(d) -> str:
    mean, se, _n = d
    if mean is None:
        return "—"
    return f"{mean:+.4f}" + (f" ±{se:.4f}" if se else "")


def configs(half_lives, shrinks, venue: str) -> list:
    splits = {"both": (False, True), "on": (True,), "off": (False,)}[venue]
    out = []
    for split in splits:
        for hl in half_lives:
            for k in shrinks:
                out.append(statmodel.ModelConfig(
                    venue_split=split, half_life_days=hl or None,
                    shrink_matches=k))
    return out


def run(season, settings, cfgs, market: dict | None = None,
        weights=BLEND_WEIGHTS) -> dict:
    domestic = sorted({m.competition for m in season
                       if m.competition and settings.owns_team_league(m.competition)})
    targets = [m for m in season if m.competition in domestic
               and statmodel._usable(m) and m.kickoff is not None]
    preds: dict = {c.name: {} for c in cfgs}
    reasons: Counter = Counter()
    base_rates: dict = {}
    for m in targets:
        past, _ = statmodel.history(season, m.competition, m.kickoff)
        if past:
            cnt = Counter(actual_of(p) for p in past)
            base_rates[m.match_id] = {o: (cnt[o] + 1) / (len(past) + 3)
                                      for o in OUTCOMES}
        for cfg in cfgs:
            f, why = statmodel.forecast_from(past, m.home_team, m.away_team,
                                             m.kickoff, cfg)
            if f is None:
                reasons[f"{cfg.name}: {why.split(' (')[0]}"] += 1
                continue
            preds[cfg.name][m.match_id] = f
    common = set.intersection(*(set(p) for p in preds.values())) if preds else set()
    by_id = {m.match_id: m for m in targets}

    def scored(ids, probs_of) -> Score:
        s = Score()
        for mid in sorted(ids):
            probs = probs_of(mid)
            if probs is not None:
                s.add(probs, actual_of(by_id[mid]))
        return s

    table = {name: scored(common, lambda mid, p=p: p[mid].probs)
             for name, p in preds.items()}
    table["(기저율)"] = scored(common, base_rates.get)
    table["(언제나 홈)"] = scored(common, lambda mid: {"H": 1.0, "D": 0.0, "A": 0.0})

    # 기준 안과 고른 결과가 갈린 경기 — 차이가 운인지 볼 재료
    first = cfgs[0].name if cfgs else ""
    diffs = {}
    for name, p in preds.items():
        if name == first:
            continue
        only_base = only_this = both_wrong = 0
        for mid in common:
            a, b = preds[first][mid].favorite, p[mid].favorite
            if a == b:
                continue
            real = actual_of(by_id[mid])
            only_base += int(a == real)
            only_this += int(b == real)
            both_wrong += int(a != real and b != real)
        diffs[name] = (only_base, only_this, both_wrong)

    per_comp = {}
    for comp in domestic:
        ids = {mid for mid in common if by_id[mid].competition == comp}
        per_comp[comp] = {name: scored(ids, lambda mid, p=p: p[mid].probs)
                          for name, p in preds.items()}

    vs_market = {}
    if market:
        ids = {mid for mid in common if mid in market}
        rnds = Counter(market[mid][0] for mid in ids)
        vs_market = {"ids": len(ids), "rounds": dict(sorted(rnds.items())),
                     "market": scored(ids, lambda mid: market[mid][2])}
        for name, p in preds.items():
            vs_market[name] = scored(ids, lambda mid, p=p: p[mid].probs)
        unmatched = sorted({market[mid][0] for mid in market if mid not in by_id})
        vs_market["not_in_index_rounds"] = unmatched
        vs_market["blend"] = {
            name: blend_study([(market[mid][0], market[mid][2], p[mid].probs,
                                actual_of(by_id[mid])) for mid in sorted(ids)],
                              weights)
            for name, p in preds.items()}
    return {"domestic": domestic, "targets": len(targets), "common": len(common),
            "table": table, "diffs": diffs, "first": first,
            "per_comp": per_comp, "vs_market": vs_market,
            "skipped": dict(reasons.most_common())}


def lines(result: dict, read, failed, season) -> list:
    out = [f"저장본 {len(read)}개 · 시즌 색인 {len(season)}경기 "
           f"(국내리그 {', '.join(result['domestic']) or '없음'})"]
    for path, why in failed:
        out.append(f"  못 읽은 저장본: {path} — {why}")
    out.append(f"예측 대상 종료 경기 {result['targets']} · 모든 안이 예측한 경기 "
               f"{result['common']} (아래 표는 이 경기들만)")
    out.append("")
    out.append("승무패 방향 적중 · 확률 품질 — 적중/경기 · ±표준오차 · "
               "Brier(낮을수록 좋음, 0~2) · log loss · 고른 결과(적중)")
    for name, s in result["table"].items():
        out.append("  " + s.line(name))
    if result["diffs"]:
        out.append("")
        out.append(f"기준 안({result['first']})과 고른 결과가 갈린 경기 — "
                   "기준만 맞음 / 이 안만 맞음 / 둘 다 틀림")
        for name, (a, b, c) in result["diffs"].items():
            out.append(f"  {name:<22}{a:>4} / {b:<4} / {c}")
    for comp, table in result["per_comp"].items():
        out.append("")
        out.append(f"[{comp}]")
        for name, s in table.items():
            out.append("  " + s.line(name))
    vm = result["vs_market"]
    if vm:
        out.append("")
        out.append(f"시장과 같은 경기 — {vm['ids']}경기 · 회차 {vm['rounds']}")
        if vm["ids"]:
            out.append("  " + vm["market"].line("시장(킥오프 전)"))
            for name, s in vm.items():
                if isinstance(s, Score) and name != "market":
                    out.append("  " + s.line(name))
        if vm.get("not_in_index_rounds"):
            out.append(f"  색인에서 경기 ID 를 못 찾은 시장 회차: "
                       f"{', '.join(vm['not_in_index_rounds'])}")
        out.extend(blend_lines(vm.get("blend") or {}))
    if result["skipped"]:
        out.append("")
        out.append("예측하지 못한 경기 (안별 사유)")
        for why, n in result["skipped"].items():
            out.append(f"  {why}: {n}")
    out.append("")
    out.append("안을 여럿 견주면 그중 하나는 운으로 좋아 보입니다 — 표준오차와 "
               "갈린 경기 수를 함께 보십시오. 이 결과는 운영용 기준을 정하는 "
               "재료이지 검증이 아닙니다.")
    return out


def blend_lines(blends: dict) -> list:
    """혼합 비교의 출력. 판정은 교차검증 값으로만 한다."""
    if not blends or not any(b["n"] for b in blends.values()):
        return []
    n = next(b["n"] for b in blends.values())
    out = ["", f"시장 + 모델 혼합 — 모델이 시장에 더할 정보가 있나 (같은 {n}경기 · "
               "혼합 = (1−w)·시장 + w·모델)",
           "  ① 같은 경기에서 잰 Brier (w 를 고른 경기로 채점 → 낙관적, 모양만 본다)"]
    for name, b in blends.items():
        cells = " · ".join(f"{w:.1f} {v[0]:.4f}" for w, v in b["in_sample"].items())
        out.append(f"    {name:<20}{cells}")
    out.append("  ② 회차 하나를 빼고 고른 w 를 뺀 회차에 씀 (교차검증) — "
               "혼합 − 시장의 경기별 짝 차이 평균 ±표준오차 (음수 = 혼합이 나음)")
    any_cv = False
    for name, b in blends.items():
        cv = b["cv"]
        if cv is None:
            continue
        any_cv = True
        chosen = ", ".join(f"{r}:{w:.1f}" for r, w in b["chosen"].items())
        out.append(f"    {name:<20}Brier {cv['brier']:.4f} (시장 "
                   f"{cv['market_brier']:.4f}) {_diff_text(cv['diff_brier'])} → "
                   f"{verdict(*cv['diff_brier'][:2])}")
        out.append(f"    {'':<20}RPS   {cv['rps']:.4f} (시장 "
                   f"{cv['market_rps']:.4f}) {_diff_text(cv['diff_rps'])} → "
                   f"{verdict(*cv['diff_rps'][:2])} · 고른 w {chosen}")
    if not any_cv:
        out.append("    회차가 둘 이상이어야 교차검증을 합니다")
    out.append("  ③ 모델만 − 시장 (짝 차이)")
    for name, b in blends.items():
        mo = b["model_only"]
        if mo:
            out.append(f"    {name:<20}Brier {_diff_text(mo['brier'])} · "
                       f"RPS {_diff_text(mo['rps'])}")
    out.append("  고른 w 가 대부분 0 이거나 ②가 '구별되지 않는다' 면 모델은 시장에 "
               "더할 정보를 보여 주지 못한 것입니다. 이 비교는 도구 안에서만 "
               "하고 운영 확률에 섞지 않습니다.")
    return out


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="통계 모델 백테스트 (읽기만)")
    p.add_argument("--artifacts", nargs="*", default=None,
                   help="저장본 경로 (기본 data/artifacts/*.json)")
    p.add_argument("--half-lives", nargs="*", type=float, default=[0, 60, 30],
                   help="반감기(일). 0 은 가중치 없음")
    p.add_argument("--shrinks", nargs="*", type=float, default=[5],
                   help="리그 평균 쪽으로 당기는 가상 경기 수")
    p.add_argument("--venue", choices=("both", "on", "off"), default="both")
    p.add_argument("--min-team", type=int, default=3)
    p.add_argument("--matches-csv", default=None,
                   help="시장 확률 CSV (기본 data/round_matches.csv)")
    p.add_argument("--blend-weights", nargs="*", type=float,
                   default=list(BLEND_WEIGHTS),
                   help="시장+모델 혼합에서 모델 쪽 비중 후보 (0~1)")
    p.add_argument("--json", default=None, help="요약 JSON 을 쓸 경로 (저장소 밖)")
    return p


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    paths = args.artifacts
    if paths is None:
        paths = sorted(artifact.ARTIFACT_DIR.glob("*.json"))
    if not paths:
        print("저장본이 없습니다 — data/artifacts/*.json")
        return 2
    if args.json:
        target = Path(args.json).resolve()
        if ROOT.resolve() in (target, *target.parents):
            print(f"--json 은 저장소 밖이어야 합니다: {target}")
            return 2
    season, read, failed = load_season(paths)
    if not season:
        print("시즌 경기 색인이 비었습니다")
        return 2
    cfgs = [statmodel.ModelConfig(venue_split=c.venue_split,
                                  half_life_days=c.half_life_days,
                                  shrink_matches=c.shrink_matches,
                                  min_team_matches=args.min_team)
            for c in configs(args.half_lives, args.shrinks, args.venue)]
    market = market_by_match_id(Path(args.matches_csv) if args.matches_csv else None)
    weights = tuple(sorted({min(max(w, 0.0), 1.0) for w in args.blend_weights}
                           | {0.0}))
    result = run(season, load_settings(), cfgs, market, weights)
    text = lines(result, read, failed, season)
    print("\n".join(text))
    if args.json:
        Path(args.json).write_text(json.dumps(
            {"lines": text, "skipped": result["skipped"]},
            ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
