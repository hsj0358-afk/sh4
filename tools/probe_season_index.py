"""시즌 경기 색인이 시즌 전체를 담는가 — 실측 도구 (Phase 2-F 착수 조건).

## 왜 이 도구가 필요한가

`Report.season_matches` 는 FotMob 리그 응답(`api/data/leagues?id=`) 안에 있는
경기 노드를 전부 모아 만든다. 그런데 **그 응답이 시즌 전체 일정을 담는지,
최근 몇 라운드만 담는지 실물로 확인된 적이 없다.**

이 답에 따라 상대 강도(SoS)의 운명이 갈린다.

  · 시즌 전체를 담는다  → 회차마다 그 리그를 한 번 받으면 과거가 전부 온다.
                          누적 저장 없이 as-of 상대 강도를 만들 수 있다.
  · 최근 몇 라운드만    → 시즌 초 상대 기록이 영영 없다. SoS 를 만들 수 없다.

## 어떻게 판정하나 — 추측하지 않는다

**순위표의 `played` 와 색인에서 센 종료 경기 수를 대조한다.** 순위표는
리그가 직접 준 "이 팀이 몇 경기를 했나" 이고, 색인은 우리가 응답에서 주워
담은 경기다. 두 수가 같으면 그 팀의 경기가 빠짐없이 들어 있다는 뜻이다.

    순위표 played 12  ==  색인 종료 12   → 완전
    순위표 played 12  vs  색인 종료  5   → 최근 5경기만 (SoS 불가)

## 쓰는 법

    python tools/probe_season_index.py                 # 오늘 캐시 → 없으면 수집
    python tools/probe_season_index.py --day 2026-08-29  # 그 날짜 캐시로
    python tools/probe_season_index.py --leagues epl,seriea
    python tools/probe_season_index.py --no-cache      # 캐시 무시하고 새로 수집

출력을 그대로 복사해 전달하면 된다. 값을 저장하거나 분석 파이프라인을
건드리지 않는다 — **읽고 세기만 한다.**
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto.cache import Cache                                   # noqa: E402
from toto.models import matches_before                         # noqa: E402
from toto.normalize import TeamResolver                        # noqa: E402
from toto.settings import load_settings                        # noqa: E402
from toto.sources import fotmob                                # noqa: E402


def collect(settings, resolver, keys, cache, use_cache):
    """{리그: read_league 결과}. 캐시가 있으면 그것을 쓴다."""
    out = {}
    missing = []
    for key in keys:
        cached = fotmob._revive(cache.get("fotmob", f"league_{key}")) \
            if use_cache else None
        if cached is not None:
            out[key] = cached
            print(f"  [{key}] 캐시 사용 — 팀 {len(cached['teams'])}개")
        else:
            missing.append(key)
    if missing:
        print(f"  캐시 없음: {', '.join(missing)} → FotMob 에서 받습니다")
        with fotmob.FotMobBrowser(settings, cache=cache) as browser:
            if not browser.available:
                print("  ! 브라우저를 띄우지 못했습니다 "
                      "(playwright install chromium 이 필요할 수 있습니다)")
                return out
            for key in missing:
                out[key] = fotmob.read_league(browser, settings, key,
                                              resolver, cache=cache)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="시즌 경기 색인 실측")
    ap.add_argument("--day", help="캐시 날짜 (기본: 오늘)")
    ap.add_argument("--leagues", help="쉼표로 구분 (기본: 설정의 전부)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args(argv)

    settings = load_settings()
    resolver = TeamResolver()
    cache = Cache(enabled=True, day=args.day)
    keys = ([k.strip() for k in args.leagues.split(",") if k.strip()]
            if args.leagues else sorted(settings.leagues))

    print("=" * 78)
    print(f"시즌 경기 색인 실측 · 캐시 {cache.root}")
    print("=" * 78)
    data = collect(settings, resolver, keys, cache, not args.no_cache)
    if not data:
        print("\n리그 데이터를 하나도 얻지 못했습니다.")
        return 1

    grand = []
    for key in keys:
        entry = data.get(key)
        if not entry or not entry.get("teams"):
            print(f"\n[{key}] 데이터 없음 — 건너뜁니다")
            continue
        matches = entry["matches"]
        index = fotmob.season_matches_from(matches, key)
        grand.extend(index)
        done = [m for m in index if m.finished]
        dates = sorted(m.kickoff for m in index if m.kickoff)

        print(f"\n{'=' * 78}\n[{key}] 팀 {len(entry['teams'])}개")
        print(f"  색인 {len(index)}경기 (종료 {len(done)} · 예정 "
              f"{len(index) - len(done)})")
        if dates:
            print(f"  기간 {dates[0].date()} ~ {dates[-1].date()}")
        no_time = sum(1 for m in index if m.kickoff is None)
        no_id = sum(1 for m in matches if not m.get("id"))
        if no_time:
            print(f"  ! 킥오프 해석 실패 {no_time}건")
        if no_id:
            print(f"  ! 경기 ID 가 없어 담지 못한 경기 {no_id}건")

        # ---- 핵심 판정: 순위표 played vs 색인 종료 경기 수 -----------------
        counted: dict[str, int] = defaultdict(int)
        for m in done:
            counted[m.home_team] += 1
            counted[m.away_team] += 1

        print(f"\n  {'팀':<22}{'순위표':>7}{'색인':>7}{'차이':>7}   판정")
        print("  " + "-" * 60)
        exact = short = over = unknown = 0
        for canon, team in sorted(entry["teams"].items()):
            played = getattr(team["stats"], "played", None)
            got = counted.get(canon, 0)
            if played is None:
                unknown += 1
                print(f"  {canon[:22]:<22}{'?':>7}{got:>7}{'':>7}   순위표 없음")
                continue
            diff = got - played
            if diff == 0:
                exact += 1
                mark = "완전"
            elif diff < 0:
                short += 1
                mark = "★ 색인에 빠진 경기"
            else:
                over += 1
                mark = "★ 색인이 더 많음"
            print(f"  {canon[:22]:<22}{played:>7}{got:>7}{diff:>+7}   {mark}")

        total = exact + short + over + unknown
        print(f"\n  → 완전 {exact}/{total} · 모자람 {short} · 초과 {over} · "
              f"순위표 없음 {unknown}")
        if total and exact == total:
            print("  → 이 리그의 색인은 **시즌 전체를 담고 있다.**")
        elif short:
            print("  → 색인이 시즌 일부만 담는다. as-of 상대 강도를 "
                  "만들 수 없다.")

        # ---- SoS 표본 시뮬레이션 -------------------------------------------
        # 각 팀의 가장 최근 종료 경기에서, 상대가 그 이전에 치른 경기 수.
        # 우리와의 경기는 뺀다(self-exclusion) — 순환을 끊기 위해서다.
        print(f"\n  ---- 상대 강도 표본 (가장 최근 경기 기준) ----")
        rows = []
        for canon in sorted(entry["teams"]):
            mine = [m for m in done if canon in (m.home_team, m.away_team)]
            if not mine:
                rows.append((canon, None, None))
                continue
            last = max(mine, key=lambda m: m.sort_key)
            opp = (last.away_team if last.home_team == canon
                   else last.home_team)
            prior = [m for m in matches_before(index, last.kickoff)
                     if opp in (m.home_team, m.away_team)
                     and canon not in (m.home_team, m.away_team)]
            rows.append((canon, opp, len(prior)))
        usable = [n for _c, _o, n in rows if n is not None and n >= 3]
        print(f"  상대의 이전 경기 3경기 이상: {len(usable)}/{len(rows)}팀")
        for canon, opp, n in rows[:6]:
            if n is None:
                print(f"    {canon[:20]:<20} 종료 경기 없음")
            else:
                print(f"    {canon[:20]:<20} 최근 상대 {opp[:18]:<18} "
                      f"그 이전 {n}경기")
        if len(rows) > 6:
            print(f"    … 외 {len(rows) - 6}팀")

    # ---- 전체 요약 ---------------------------------------------------------
    print(f"\n{'=' * 78}")
    seen = {m.match_id for m in grand}
    fin = sum(1 for m in grand if m.finished)
    print(f"전체 색인 {len(seen)}경기 (종료 {fin}) · 리그 {len(data)}개")
    print("이 출력을 그대로 전달하면 SoS 착수 여부를 판단할 수 있습니다.")
    print(f"실행 시각 {datetime.now():%Y-%m-%d %H:%M}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
