"""FotMob 과거 시즌 요청이 production path 에서 통하는가 — 진단 전용 (6-D-6A).

## 왜 이 도구가 필요한가

6-D-6(Historical Season Acquisition)이 **네트워크 계층에서 막혀 BLOCKED** 다.
원격 세션에서는 fotmob.com 이 차단돼 있어(CLAUDE.md §2-1) 답할 수 없는 질문이
정확히 하나 남았다.

    page.goto() 로 `&season=2025/2026` 을 요청하면
    **과거 시즌이 오는가, 최신 시즌이 조용히 오는가, 실패하는가**

이 질문이 중요한 이유는 셋째 갈래가 **조용하기 때문**이다. 최신 시즌 응답을
과거 시즌 데이터로 쓰면 틀린 값이 사실처럼 리포트에 실린다 — 없는 값보다
나쁘다 (§1-5).

## 왜 HAR 로는 답이 안 되나

브라우저 SPA 가 보낸 요청은 XHR 이고 **`x-mas` 서명 헤더를 달고 있다.**
이 프로젝트의 production 경로는 `page.goto()`(최상위 내비게이션)라 그 헤더가
생성되지 않는다. 그래서 "브라우저에서는 됐다" 가 "우리 코드에서도 된다" 를
뜻하지 않는다. **관측(HAR) ≠ production 보증**이다.

그래서 이 도구는 **production `FotMobBrowser` 를 그대로 쓴다.** 새 HTTP
클라이언트를 만들지 않고(`requests`·`curl`·`httpx` 없음), `x-mas` 를 지어내지
않는다. 요청 자체가 production 과 같아야 답이 의미가 있다.

## 무엇을 하지 않는가

**읽고 찍기만 한다.** 수집 로직·파서·캐시·설정을 한 줄도 건드리지 않고,
받은 응답을 저장하지도 않는다. 판정도 하드코딩하지 않는다 — 응답이 실제로
무엇을 말하는지 그대로 출력하고, 그 위에서 기준 하나만 적용한다.

## 쓰는 법

    python tools/probe_fotmob_season.py                 # UEL(73) · 2025/2026
    python tools/probe_fotmob_season.py --id 42         # UCL
    python tools/probe_fotmob_season.py --id 10216      # Conference
    python tools/probe_fotmob_season.py --season 2024/2025
    python tools/probe_fotmob_season.py --headful       # 통과 쿠키를 만들 때

출력을 그대로 복사해 전달하면 6-D-6 을 이어서 끝낼 수 있다.

## 판정 기준

    details.selectedSeason == 요청한 시즌        → PASS
    details.selectedSeason == latestSeason       → FAIL (최신 시즌이 왔다)
    파싱 불가                                     → FAIL
    HTTP 응답 자체를 못 받음                       → BLOCKED

**`overview.season` 으로 판정하지 않는다.** 관측된 과거 시즌 응답에서 그
필드는 `2026/2027`(최신)을 말하고 있었다 — 그것을 믿으면 과거 시즌 요청이
성공했는지 영원히 알 수 없다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto.cache import Cache                                   # noqa: E402
from toto.settings import load_settings                        # noqa: E402
from toto.sources.browser import unwrap_json                   # noqa: E402
from toto.sources.fotmob import FotMobBrowser                  # noqa: E402

MISSING = object()          # '그 경로가 없다' — None(값이 실제로 없다)과 다르다


# --------------------------------------------------------------------------
# JSON 경로 읽기 — 없으면 어디서 끊겼는지 말한다
# --------------------------------------------------------------------------
def dig(node, path: str):
    """`a.b.c` 를 따라간다. `(값, 끊긴 경로)` — 끝까지 가면 끊긴 경로가 "" 다.

    예외를 삼키지 않는 것이 이 함수의 요점이다. 없으면 **어느 마디에서**
    없는지 돌려주므로, 응답 구조가 예상과 다를 때 그 사실이 그대로 화면에
    나온다 (구조를 추측하지 않기 위해서다 — §1-4).
    """
    cur, walked = node, []
    for part in path.split("."):
        walked.append(part)
        if not isinstance(cur, dict) or part not in cur:
            return MISSING, ".".join(walked)
        cur = cur[part]
    return cur, ""


def dig_list(node, list_path: str, leaf: str):
    """`table[].data.selectedSeason` 처럼 리스트를 건너뛰는 경로.

    `(값 목록, 사유)` — 목록이 비면 사유에 왜 비었는지가 들어간다.
    """
    seq, broke = dig(node, list_path)
    if seq is MISSING:
        return [], f"{broke} 없음"
    if not isinstance(seq, list):
        return [], f"{list_path} 가 리스트가 아님 ({type(seq).__name__})"
    if not seq:
        return [], f"{list_path} 가 빈 리스트"
    out, misses = [], []
    for i, item in enumerate(seq):
        value, broke = dig(item, leaf)
        if value is MISSING:
            misses.append(f"[{i}]{broke}")
        else:
            out.append(value)
    return out, ("; ".join(misses) if misses else "")


def season_fields(node, prefix: str = "", found=None, depth: int = 0):
    """이름에 `season` 이 든 스칼라 필드를 전부 모은다.

    예상한 경로가 없을 때를 위한 안전망이다. **authoritative 필드를 우리가
    정하지 않고** 응답이 실제로 무엇을 들고 있는지 보여 준다.
    """
    found = {} if found is None else found
    if depth > 6 or len(found) > 60:
        return found
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            if "season" in key.lower() and not isinstance(value, (dict, list)):
                found.setdefault(path, value)
            elif ("season" in key.lower() and isinstance(value, list)
                  and value and not isinstance(value[0], (dict, list))):
                found.setdefault(path, value[:5])
            season_fields(value, path, found, depth + 1)
    elif isinstance(node, list):
        for item in node[:3]:           # 리스트는 앞쪽만 — 경로 모양만 보면 된다
            season_fields(item, f"{prefix}[]", found, depth + 1)
    return found


def show(label: str, value) -> None:
    if value is MISSING:
        print(f"    {label:<34} (경로 없음)")
    else:
        print(f"    {label:<34} {value!r}")


# --------------------------------------------------------------------------
# 요청 하나
# --------------------------------------------------------------------------
def probe(browser: FotMobBrowser, label: str, params: dict,
          want_season: str) -> dict:
    """production `get_raw()` 로 한 번 부르고 시즌 필드를 찍는다.

    파싱은 production `get_json()` 의 본문과 **같은 두 줄**이다
    (`json.loads(unwrap_json(text))`). `get_json()` 을 따로 부르면 같은
    요청이 두 번 나가므로, status·bytes 를 함께 보려고 이렇게 나눴다.
    """
    url = browser.abs_url("/api/data/leagues?" + urlencode(params))
    print(f"\n{'-' * 74}\n{label}\n  URL    {url}")

    status, text = browser.get_raw(url)          # ← production 경로 그대로
    print(f"  status {status}    bytes {len(text)}")

    if not status:
        print("  판정   BLOCKED — HTTP 응답을 받지 못했습니다 "
              "(네트워크·프록시·타임아웃).")
        return {"label": label, "url": url, "status": status,
                "bytes": len(text), "verdict": "BLOCKED",
                "reason": "HTTP 응답 없음"}
    if status >= 400:
        print(f"  판정   FAIL — HTTP {status}")
        return {"label": label, "url": url, "status": status,
                "bytes": len(text), "verdict": "FAIL",
                "reason": f"HTTP {status}"}

    try:
        data = json.loads(unwrap_json(text))
    except Exception as exc:               # noqa: BLE001 — 사유를 그대로 보여 준다
        print(f"  판정   FAIL — JSON 파싱 실패: {type(exc).__name__}: {exc}")
        print(f"  앞 200자: {text[:200]!r}")
        return {"label": label, "url": url, "status": status,
                "bytes": len(text), "verdict": "FAIL",
                "reason": f"JSON 파싱 실패 ({type(exc).__name__})"}

    if not isinstance(data, dict):
        print(f"  판정   FAIL — 최상위가 dict 가 아닙니다 "
              f"({type(data).__name__})")
        return {"label": label, "url": url, "status": status,
                "bytes": len(text), "verdict": "FAIL",
                "reason": "최상위가 객체가 아님"}

    print(f"  최상위 키 {sorted(data)}")

    selected, _ = dig(data, "details.selectedSeason")
    latest, _ = dig(data, "details.latestSeason")
    overview, _ = dig(data, "overview.season")
    tbl_season, tbl_why = dig_list(data, "table", "data.selectedSeason")
    tbl_cur, cur_why = dig_list(data, "table", "data.isCurrentSeason")

    print("\n  요청한 필드")
    show("details.selectedSeason", selected)
    show("details.latestSeason", latest)
    show("overview.season", overview)
    print(f"    {'table[].data.selectedSeason':<34} "
          f"{tbl_season if tbl_season else '(없음)'}"
          f"{'  ← ' + tbl_why if tbl_why else ''}")
    print(f"    {'table[].data.isCurrentSeason':<34} "
          f"{tbl_cur if tbl_cur else '(없음)'}"
          f"{'  ← ' + cur_why if cur_why else ''}")

    others = {k: v for k, v in season_fields(data).items()
              if k not in ("details.selectedSeason", "details.latestSeason",
                           "overview.season")}
    if others:
        print("\n  그 밖에 응답이 들고 있는 season 필드 "
              "(authoritative 후보를 우리가 정하지 않는다)")
        for path, value in sorted(others.items())[:14]:
            print(f"    {path:<52} {value!r}"[:118])

    # ---- 판정 ------------------------------------------------------------
    if selected is MISSING:
        verdict, reason = "FAIL", "details.selectedSeason 경로가 없음"
        if tbl_season:
            reason += f" (table[].data.selectedSeason = {tbl_season})"
    elif str(selected) == want_season:
        verdict, reason = "PASS", f"selectedSeason == 요청한 {want_season}"
    elif latest is not MISSING and str(selected) == str(latest):
        verdict, reason = "FAIL", (f"최신 시즌이 왔다 (selected={selected!r} "
                                   f"== latest={latest!r})")
    else:
        verdict, reason = "FAIL", (f"요청 {want_season} ≠ "
                                   f"selected {selected!r}")
    print(f"\n  판정   {verdict} — {reason}")
    return {"label": label, "url": url, "status": status, "bytes": len(text),
            "selected": selected, "latest": latest, "overview": overview,
            "verdict": verdict, "reason": reason}


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="FotMob 과거 시즌 요청 진단 (production path · 읽기만 한다)")
    ap.add_argument("--id", type=int, default=73,
                    help="FotMob 리그 id (기본 73=UEL · 42=UCL · 10216=Conference)")
    ap.add_argument("--season", default="2025/2026", help="요청할 시즌")
    ap.add_argument("--ccode3", default="KOR",
                    help="3번째 요청에 붙일 ccode3 (관측된 값은 KOR)")
    ap.add_argument("--headful", action="store_true",
                    help="브라우저 창을 띄운다 (통과 쿠키 저장용)")
    args = ap.parse_args(argv)

    print("=" * 74)
    print("FotMob 과거 시즌 요청 진단 (6-D-6A)")
    print(f"리그 id {args.id} · 요청 시즌 {args.season} · "
          f"{datetime.now():%Y-%m-%d %H:%M}")
    print("production FotMobBrowser.get_raw() 를 그대로 씁니다 — "
          "x-mas 를 만들지 않고, 다른 HTTP 클라이언트를 쓰지 않습니다.")
    print("=" * 74)

    settings = load_settings()
    if args.headful:
        settings.fotmob = {**(settings.fotmob or {}), "headless": False}
    cache = Cache(enabled=True)

    cases = [
        ("1) 현재 방식 (season 없음)",
         {"id": args.id}),
        ("2) season 파라미터",
         {"id": args.id, "season": args.season}),
        ("3) season + ccode3",
         {"id": args.id, "season": args.season, "ccode3": args.ccode3}),
    ]

    results = []
    with FotMobBrowser(settings, cache=cache) as browser:
        if not browser.available:
            print("\n! 브라우저를 띄우지 못했습니다.")
            print("  pip install -r requirements-toto.txt && "
                  "playwright install chromium")
            print("\n판정 BLOCKED — 브라우저 기동 실패 (네트워크 판정 불가)")
            return 2
        for label, params in cases:
            results.append(probe(browser, label, params, args.season))

    # ---- 요약 --------------------------------------------------------------
    print(f"\n{'=' * 74}\n요약")
    for r in results:
        print(f"  {r['label']:<28} {r['verdict']:<8} "
              f"HTTP {r['status']} · {r['bytes']} bytes · {r['reason']}")

    hist = [r for r in results if "season" in r["url"]]
    if all(r["verdict"] == "BLOCKED" for r in results):
        final = ("BLOCKED — production path 가 HTTP 응답을 받지 못했습니다. "
                 "네트워크 계층 문제이며 FotMob 의 거부가 아닙니다.")
        code = 2
    elif any(r["verdict"] == "PASS" for r in hist):
        ok = [r["label"] for r in hist if r["verdict"] == "PASS"]
        final = (f"PASS — season 파라미터가 production path 에서 실제로 "
                 f"과거 시즌을 돌려줍니다 ({', '.join(ok)}). "
                 f"x-mas 없이 동작합니다.")
        code = 0
    else:
        final = ("FAIL — season 파라미터를 붙여도 과거 시즌이 오지 않습니다. "
                 "이 상태로 historical acquisition 을 구현하면 최신 시즌을 "
                 "과거 시즌으로 쓰게 됩니다.")
        code = 1
    print(f"\n최종 판정: {final}")
    print("\n이 출력을 그대로 전달하면 6-D-6 을 이어서 끝낼 수 있습니다.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
