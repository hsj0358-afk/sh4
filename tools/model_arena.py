"""예측 모델 경기장 실행기 (§1-67).

    python tools/model_arena.py fetch [--refresh]      # 과거 기록 받기 (football-data.co.uk)
    python tools/model_arena.py run                    # 탐색 → 검증 → 게이팅 → 보고서
    python tools/model_arena.py run --promote          # 게이팅을 통과하면 챔피언을 바꾼다
    python tools/model_arena.py promote                # 마지막 run 의 결과로 바꾼다 (다시 탐색하지 않는다)
    python tools/model_arena.py export                 # 챔피언 상태를 최신 기록으로 다시 만든다

`run` 이 하는 일 (알파고 제로의 학습 고리를 옮긴 것 — `toto/arena.py`):

  1. 엔진마다 무작위 탐색 + 국소 개선 (개발 구간 2005/06~2018/19 의 log loss)
  2. 엔진 조합 31가지 · 출력층 설정 · GBM · MLP · 직접 포아송을 같은 기준으로
  3. 개발 구간 1위(리포트에서 돌 수 있는 종류 중)가 **도전자**가 된다
  4. 도전자와 현 챔피언·현 운영 모델·기준선을 **검증 구간**(2019/20~)에서
     같은 경기로 견준다 — 여기서는 고르지 않는다
  5. 도전자가 log loss 개선 한쪽 95% 확신을 넘으면 `--promote` 로 챔피언 교체

출력: `data/model/arena_result.json` · `docs/model_arena.md` ·
(`--promote` 통과 시) `data/model/champion.json` + `data/model/champion_state.json`.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from toto import arena as A          # noqa: E402
from toto import champion as C       # noqa: E402
from toto import history as H        # noqa: E402

RESULT_FILE = ROOT / "data" / "model" / "arena_result.json"
REPORT_FILE = ROOT / "docs" / "model_arena.md"
RUNTIME_KINDS = ("stack",)            # 리포트 경로(순수 파이썬)에서 돌 수 있는 종류


def log(*a):
    print(*a, flush=True)


# --------------------------------------------------------------------------
def cmd_fetch(args) -> int:
    out = H.fetch(refresh=args.refresh)
    log(f"받음 {out['ok']} · 캐시 {out['cached']} · 실패 {len(out['failed'])}")
    for url, why in out["failed"]:
        log(f"  ✗ {url} — {why}")
    return 0 if not out["failed"] else 1


def _fmt(s: dict) -> str:
    if not s.get("n"):
        return "—"
    return (f"logloss {s['logloss']:.4f} · RPS {s['rps']:.4f} · "
            f"Brier {s['brier']:.4f} · 적중 {s['accuracy'] * 100:.2f}% (n={s['n']})")


def cmd_run(args) -> int:
    t0 = time.time()
    rows, missing = H.load()
    if not rows:
        log("기록이 없습니다 — 먼저 fetch 를 돌리십시오")
        return 2
    log(f"경기 {len(rows):,} · 리그 {sorted({m.league for m in rows})} · "
        f"{rows[0].date} ~ {rows[-1].date}")
    store = A.FeatureStore(rows)
    hold = A.holdout_years(rows)
    dev = A.DEV_YEARS
    board = []                         # (이름, 종류, 트랙, 개발 점수, 후보)

    def enter(cand, years=dev, idx=None):
        probs = A.predict(cand, store, years)
        s = A.score(rows, probs, idx if idx is not None else A.index_of(rows, years))
        board.append({"candidate": cand.to_dict(), "dev": s})
        log(f"  {cand.name:<44} {_fmt(s)}")
        return s

    # 1. 엔진 탐색 ----------------------------------------------------------
    log("\n[1] 엔진 탐색 (무작위 + 국소 개선)")
    best = {}
    trials = {}
    for fam in ("elo", "pi", "goals", "sot", "shots"):
        spec, ll, tried = A.search_engine(fam, store, n_random=args.n_random, log=log)
        best[fam] = spec
        trials[fam] = [{"dev_logloss": v, "spec": s} for v, s in tried]
        log(f"  → {fam}: {spec}")
    store.drop(list(best.values()))

    # 2. 기준선 · 단독 엔진 -------------------------------------------------
    log("\n[2] 기준선 · 단독 엔진 (개발 구간)")
    enter(A.Candidate("base", "base"))
    for fam, spec in best.items():
        enter(A.solo(spec, name=f"{fam}-solo"))
    enter(A.Candidate("poisson", "poisson", engines=[best["goals"]]))
    enter(A.Candidate("poisson-dc", "poisson", engines=[best["goals"]],
                      options={"dc": True}))

    # 3. 엔진 조합 ----------------------------------------------------------
    log("\n[3] 엔진 조합 (출력층 = 다항 로지스틱)")
    combo_scores = []
    for names in A.combos(best):
        if len(names) < 2:
            continue
        cand = A.stack_of(names, best)
        s = enter(cand)
        combo_scores.append((s["logloss"], names))
    combo_scores.sort()
    top_names = combo_scores[0][1]
    log(f"  → 최고 조합: {top_names}")

    # 4. 출력층 설정 --------------------------------------------------------
    log("\n[4] 출력층 설정")
    stack_best = None
    for l2 in (0.1, 1.0, 10.0, 100.0):
        for per_league in (True, False):
            for window in (0, 6, 10):
                cand = A.stack_of(top_names, best, l2=l2, per_league=per_league,
                                  window=window,
                                  name=f"stack[l2={l2:g},lg={int(per_league)},w={window}]")
                probs = A.predict(cand, store, dev)
                s = A.score(rows, probs, A.index_of(rows, dev))
                if stack_best is None or s["logloss"] < stack_best[0]:
                    stack_best = (s["logloss"], cand)
    enter(stack_best[1])

    # 5. 기계학습 출력층 ----------------------------------------------------
    log("\n[5] 기계학습 출력층 (같은 특징)")
    feats = stack_best[1].features
    engs = stack_best[1].engines
    for opts in ({"lr": 0.05, "iters": 150, "leaves": 15, "min_leaf": 300},
                 {"lr": 0.03, "iters": 300, "leaves": 7, "min_leaf": 500}):
        enter(A.Candidate(f"gbm[{opts['lr']},{opts['iters']},{opts['leaves']}]",
                          "gbm", engines=engs, features=feats, options=opts))
    for opts in ({"hidden": [16], "alpha": 1.0}, {"hidden": [32, 16], "alpha": 3.0}):
        enter(A.Candidate(f"mlp{opts['hidden']}", "mlp", engines=engs,
                          features=feats, options=opts))

    # 6. 도전자 고르기 (개발 구간 · 리포트에서 돌 수 있는 종류) ----------------
    indep = [b for b in board if b["candidate"]["track"] == "independent"
             and b["dev"].get("n")]
    indep.sort(key=lambda b: b["dev"]["logloss"])
    runnable = [b for b in indep if b["candidate"]["kind"] in RUNTIME_KINDS]
    challenger = A.Candidate.from_dict(runnable[0]["candidate"])
    challenger.name = "challenger:" + challenger.name
    log(f"\n도전자: {challenger.name} (개발 log loss {runnable[0]['dev']['logloss']:.5f})")
    if indep[0] is not runnable[0]:
        log(f"  (개발 1위는 {indep[0]['candidate']['name']} — 리포트에서 돌 수 없는 종류라 제외)")

    # 7. 시장 트랙 (개발: 배당이 있는 2012/13~) -------------------------------
    log("\n[7] 시장 트랙 (피나클 킥오프 전 배당)")
    mdev = tuple(y for y in dev if y >= 2012)
    market = A.Candidate("market-pinnacle", "market", track="market",
                         options={"odds": "open"})
    mstack = A.Candidate("market+model-stack", "stack", engines=challenger.engines,
                         features=["mkt_h", "mkt_a"] + challenger.features,
                         l2=challenger.l2, per_league=challenger.per_league,
                         window=0, track="market")
    mblend = A.Candidate("market+model-blend", "blend", track="market",
                         options={"members": [challenger.to_dict(), market.to_dict()]})
    midx = [i for i in A.index_of(rows, mdev) if rows[i].odds_open]
    for c in (market, mstack, mblend):
        enter(c, years=mdev, idx=midx)

    # 8. 검증 구간 (고르지 않는다) --------------------------------------------
    log(f"\n[8] 검증 구간 {hold[0]}/{hold[0] + 1 - 2000:02d} ~ — 같은 경기에서 견준다")
    incumbent = C.load_champion()
    finalists = {
        "challenger": challenger,
        "production-statmodel": A.Candidate("production-statmodel", "statmodel"),
        "base": A.Candidate("base", "base"),
        "poisson-dc": A.Candidate("poisson-dc", "poisson", engines=[best["goals"]],
                                  options={"dc": True}),
    }
    for fam, spec in best.items():
        finalists[f"{fam}-solo"] = A.solo(spec, name=f"{fam}-solo")
    for b in board:
        if b["candidate"]["kind"] in ("gbm", "mlp"):
            finalists[b["candidate"]["name"]] = A.Candidate.from_dict(b["candidate"])
    if incumbent is not None:
        finalists["incumbent"] = A.Candidate.from_dict(incumbent["candidate"])
    finalists.update({"market-pinnacle": market, "market+model-stack": mstack,
                      "market+model-blend": mblend})
    hidx = A.index_of(rows, hold)
    hprobs, hold_scores = {}, {}
    for key, cand in finalists.items():
        hprobs[key] = A.predict(cand, store, hold)
        hold_scores[key] = A.score(rows, hprobs[key], hidx)
        log(f"  {key:<28} {_fmt(hold_scores[key])}")
    per_league = {}
    for lg in sorted({m.league for m in rows}):
        li = A.index_of(rows, hold, leagues={lg})
        per_league[lg] = {k: A.score(rows, hprobs[k], li)
                          for k in ("challenger", "production-statmodel",
                                    "market-pinnacle", "base")}

    # 9. 짝 비교 · 게이팅 ----------------------------------------------------
    log("\n[9] 짝 비교 (A − B · 양수면 B 가 낫다 · 날짜 부트스트랩)")
    pairs = [("production-statmodel", "challenger"), ("base", "challenger"),
             ("market-pinnacle", "challenger"),
             ("market-pinnacle", "market+model-stack"),
             ("market-pinnacle", "market+model-blend")]
    pairs += [(f"{fam}-solo", "challenger") for fam in best]
    if incumbent is not None:
        pairs.insert(0, ("incumbent", "challenger"))
    comps = {}
    for a, b in pairs:
        r = A.compare(rows, hprobs[a], hprobs[b], hidx)
        comps[f"{a} → {b}"] = r
        if r.get("n"):
            log(f"  {a:>22} → {b:<20} n={r['n']:>5}  Δlogloss {r['d_logloss']:+.4f} "
                f"[{r['d_logloss_ci'][0]:+.4f}, {r['d_logloss_ci'][1]:+.4f}]  "
                f"Δ적중 {r['d_accuracy'] * 100:+.2f}%p  P(B 우위) {r['p_b_better']:.3f}")
    gate_vs = "incumbent" if incumbent is not None else "production-statmodel"
    gate_result = comps[f"{gate_vs} → challenger"]
    passed = A.gate(gate_result)
    log(f"\n게이팅 ({gate_vs} → 도전자): {'통과' if passed else '실패'} "
        f"(P {gate_result.get('p_b_better', 0):.3f}, 기준 0.95)")

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data": {"matches": len(rows), "first": str(rows[0].date),
                 "last": str(rows[-1].date),
                 "leagues": sorted({m.league for m in rows}),
                 "dev_years": [dev[0], dev[-1]], "holdout_years": [hold[0], hold[-1]]},
        "engine_search": {k: v[:10] for k, v in trials.items()},
        "best_engines": best,
        "combos": [{"dev_logloss": s, "engines": n} for s, n in combo_scores],
        "dev_board": board,
        "challenger": challenger.to_dict(),
        "holdout": hold_scores,
        "holdout_per_league": per_league,
        "comparisons": comps,
        "gate": {"against": gate_vs, "passed": passed, **gate_result},
        "incumbent_id": incumbent.get("id") if incumbent else None,
        "seconds": round(time.time() - t0, 1),
    }
    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                           encoding="utf-8", newline="\n")
    REPORT_FILE.write_text(render_report(result), encoding="utf-8", newline="\n")
    log(f"\n결과 → {RESULT_FILE.relative_to(ROOT)} · {REPORT_FILE.relative_to(ROOT)}")

    log(f"총 {time.time() - t0:.0f}초")
    if args.promote:
        return cmd_promote(args, rows=rows)
    return 0


def cmd_promote(args, rows=None) -> int:
    """마지막 `run` 의 결과로 챔피언을 바꾼다 — 다시 탐색하지 않는다.

    게이팅을 통과했고, 그 `run` 이 견준 현 챔피언이 **지금도** 같을 때만.
    그 사이에 챔피언이 바뀌었으면 결과가 낡았으므로 거부한다.
    """
    result = C._read_json(RESULT_FILE)
    if not result:
        log("경기장 결과가 없습니다 — 먼저 run 을 돌리십시오")
        return 2
    gate = result.get("gate") or {}
    if not gate.get("passed"):
        log(f"게이팅을 통과하지 못했습니다 (P {gate.get('p_b_better', 0):.3f}) — 바꾸지 않습니다")
        return 1
    incumbent = C.load_champion()
    now_id = incumbent.get("id") if incumbent else None
    if now_id != result.get("incumbent_id"):
        log("결과를 만든 뒤 챔피언이 바뀌었습니다 — run 을 다시 돌리십시오")
        return 1
    challenger = A.Candidate.from_dict(result["challenger"])
    if challenger.kind not in RUNTIME_KINDS:
        log(f"리포트에서 돌 수 없는 종류입니다: {challenger.kind}")
        return 1
    record = C.save_champion(challenger, result["holdout"]["challenger"], gate,
                             against=gate.get("against", ""), previous=incumbent)
    log(f"챔피언 교체 → {C.CHAMPION_FILE.relative_to(ROOT)} (id {record['id']})")
    return cmd_export(args, rows=rows)


def cmd_export(args, rows=None) -> int:
    champ = C.load_champion()
    if champ is None:
        log("챔피언이 없습니다 — run --promote 를 먼저 돌리십시오")
        return 2
    if rows is None:
        rows, _ = H.load()
    state, notes = C.build_state(A.Candidate.from_dict(champ["candidate"]), rows)
    C.save_state(state)
    for n in notes:
        log(f"  · {n}")
    log(f"챔피언 상태 → {C.STATE_FILE.relative_to(ROOT)} (자료 {state['data_through']}까지)")
    return 0


# --------------------------------------------------------------------------
def _row(name, s):
    if not s.get("n"):
        return f"| {name} | — | — | — | — | 0 |"
    return (f"| {name} | {s['logloss']:.4f} | {s['rps']:.4f} | {s['brier']:.4f} | "
            f"{s['accuracy'] * 100:.2f}% | {s['n']:,} |")


LEAGUE_KO = {"epl": "EPL", "laliga": "라리가", "bundesliga": "분데스리가",
             "seriea": "세리에A", "ligue1": "리그앙", "jleague": "J리그"}


def render_report(r: dict) -> str:
    d = r["data"]
    lines = [
        "# 예측 모델 경기장 결과",
        "",
        f"생성 {r['generated_at']} · 경기 {d['matches']:,} ({d['first']} ~ {d['last']}) · "
        f"리그 {', '.join(LEAGUE_KO.get(x, x) for x in d['leagues'])}",
        "",
        f"개발 구간 {d['dev_years'][0]}/{d['dev_years'][0] + 1 - 2000:02d} ~ "
        f"{d['dev_years'][1]}/{d['dev_years'][1] + 1 - 2000:02d} 에서 고르고, "
        f"검증 구간 {d['holdout_years'][0]}/{d['holdout_years'][0] + 1 - 2000:02d} ~ "
        "에서 **한 번** 견준다. 모든 예측은 그 경기를 보기 전의 값이다.",
        "",
        "## 검증 구간 순위",
        "",
        "낮을수록 좋다 (log loss · RPS · Brier). 적중률은 확률이 가장 높은 결과가 맞은 비율.",
        "시장 트랙은 피나클 배당이 있는 경기만이라 n 이 다르다 — 같은 경기 비교는 아래 짝 비교를 본다.",
        "",
        "| 후보 | log loss | RPS | Brier | 적중률 | n |",
        "|---|---|---|---|---|---|",
    ]
    order = sorted(r["holdout"].items(),
                   key=lambda kv: kv[1].get("logloss", 9.0))
    for k, s in order:
        lines.append(_row(k, s))
    lines += ["", "## 짝 비교 (같은 경기)", "",
              "Δ 는 A − B. log loss 가 양수면 B 가 낫다. 적중은 B − A. 구간은 날짜 단위 부트스트랩 95%.",
              "",
              "| A → B | n | Δ log loss [95%] | Δ 적중률 [95%] | P(B 우위) |",
              "|---|---|---|---|---|"]
    for k, c in r["comparisons"].items():
        if not c.get("n"):
            continue
        lines.append(
            f"| {k} | {c['n']:,} | {c['d_logloss']:+.4f} "
            f"[{c['d_logloss_ci'][0]:+.4f}, {c['d_logloss_ci'][1]:+.4f}] | "
            f"{c['d_accuracy'] * 100:+.2f}%p "
            f"[{c['d_accuracy_ci'][0] * 100:+.2f}, {c['d_accuracy_ci'][1] * 100:+.2f}] | "
            f"{c['p_b_better']:.3f} |")
    g = r["gate"]
    lines += ["", "## 게이팅", "",
              f"도전자 `{r['challenger']['name']}` vs `{g['against']}` — "
              f"{'**통과**' if g['passed'] else '**실패**'} "
              f"(P(도전자 우위) {g.get('p_b_better', 0):.3f}, 기준 0.95)", "",
              "## 리그별 (검증 구간)", "",
              "| 리그 | 도전자 | 운영 statmodel | 피나클 | 기준선 |",
              "|---|---|---|---|---|"]
    for lg, s in r["holdout_per_league"].items():
        cells = []
        for k in ("challenger", "production-statmodel", "market-pinnacle", "base"):
            v = s.get(k, {})
            cells.append(f"{v['logloss']:.4f} · {v['accuracy'] * 100:.1f}%"
                         if v.get("n") else "—")
        lines.append(f"| {LEAGUE_KO.get(lg, lg)} | " + " | ".join(cells) + " |")
    lines += ["", "## 엔진 탐색 최고값 (개발 구간)", ""]
    for fam, spec in r["best_engines"].items():
        lines.append(f"- `{fam}` — `{json.dumps(spec, ensure_ascii=False)}`")
    lines += ["", "## 개발 구간 순위 (상위 15)", "",
              "| 후보 | log loss | 적중률 | n |", "|---|---|---|---|"]
    dev = [b for b in r["dev_board"] if b["dev"].get("n")
           and b["candidate"]["track"] == "independent"]
    for b in sorted(dev, key=lambda b: b["dev"]["logloss"])[:15]:
        s = b["dev"]
        lines.append(f"| {b['candidate']['name']} | {s['logloss']:.4f} | "
                     f"{s['accuracy'] * 100:.2f}% | {s['n']:,} |")
    lines += ["", f"실행 {r['seconds']:.0f}초.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--refresh", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--n-random", type=int, default=24)
    r.add_argument("--promote", action="store_true")
    sub.add_parser("promote")
    sub.add_parser("export")
    args = p.parse_args(argv)
    if args.cmd == "fetch":
        return cmd_fetch(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "promote":
        return cmd_promote(args)
    return cmd_export(args)


if __name__ == "__main__":
    sys.exit(main())
