"""베트맨 투표율 셀 점검 — 파서를 쓰기 전에 실물을 본다 (§1-4).

## 왜 이 도구가 필요한가

베트맨 경기 행에 투표율이 있다는 것은 실측 셀(260054·260055)로 알고 있지만,
**그 칸이 어떤 글자로 오는지**(세 값이 한 칸에 줄바꿈으로 오나, 칸마다 하나씩
오나, 승·무·패 순서인가, 라벨이 붙나)는 파서를 쓸 만큼 확인되지 않았다.
`tests/test_match_contract.py` 의 픽스처(`"투표율\\n41.2%\\n27.5%\\n31.3%"`)는
행 구조를 옮긴 것이지 투표율 칸을 검증한 값이 아니다.

또 하나 — 상금 계산에 필요한 **총 발매량·참여 수** 같은 값이 페이지 어디에
있는지 모른다. 표 행(`<tr>`)만 저장한 셀 파일에는 표 밖의 글자가 없다.

## 하는 일

    python tools/probe_betman_votes.py                       # cache/debug/betman_cells_*.json 분석
    python tools/probe_betman_votes.py 파일.json ...          # 지정 파일 분석
    python tools/probe_betman_votes.py --live 260066          # 게임슬립을 열어 행 + 프레임 본문 글자 저장 후 분석

  · 기본 모드는 **읽기만 한다.** 네트워크도 쓰지 않는다.
  · `--live` 는 수집기와 **같은 주소·같은 행 수집 함수**(`betman._scrape_rows`)를
    쓰고, 그에 더해 프레임마다 `document.body.innerText` 를 남긴다. 결과는
    `cache/probe/betman_votes_<회차>_<시각>.json` 에만 쓴다. `data/` · 저장본 ·
    회차 기록 · 리포트를 건드리지 않고, 회차 자동 탐지(`data/last_round.txt`
    를 읽는다)를 쓰지 않으려고 회차를 반드시 받는다.

파싱하지 않는다. 투표율 칸으로 보이는 글자를 **원문 그대로(repr)** 보여 주고,
숫자를 9 로 바꾼 모양을 세어 줄 뿐이다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto.settings import ROOT  # noqa: E402

DEBUG_DIR = ROOT / "cache" / "debug"
PROBE_DIR = ROOT / "cache" / "probe"

_PCT_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
_MATCH_NO_RE = re.compile(r"^\s*(\d{1,2})\s*경기\s*$")

# 표 밖에 있을 수 있는 회차 단위 값의 낱말. 찾기만 하고 해석하지 않는다.
KEYWORDS = ("투표", "발매", "판매", "금액", "참여", "적중", "상금", "이월",
            "총", "구매", "배분", "등")


def find_rows(obj) -> list[list[str]]:
    """셀 파일에서 행(문자열 목록)들을 찾는다. 모양으로만 찾는다."""
    if isinstance(obj, dict):
        if isinstance(obj.get("cells"), list):
            return [[str(c) for c in obj["cells"]]]
        out: list[list[str]] = []
        for v in obj.values():
            out.extend(find_rows(v))
        return out
    if isinstance(obj, list):
        if obj and all(isinstance(c, str) for c in obj):
            return [list(obj)]
        out = []
        for v in obj:
            out.extend(find_rows(v))
        return out
    return []


def find_texts(obj) -> list[str]:
    """`--live` 가 남긴 프레임 본문 글자."""
    if isinstance(obj, dict) and isinstance(obj.get("frames"), list):
        return [str(f.get("text") or "") for f in obj["frames"]
                if isinstance(f, dict)]
    return []


def match_no(cells: list[str]) -> int | None:
    for cell in cells:
        m = _MATCH_NO_RE.match(cell or "")
        if m:
            return int(m.group(1))
    return None


def shape(text: str) -> str:
    """숫자를 9 로 바꾼 모양 — 칸의 형식만 남긴다."""
    return re.sub(r"\d", "9", text)


def analyze(rows: list[list[str]], texts: list[str]) -> list[str]:
    lines: list[str] = []
    match_rows = [(match_no(r), r) for r in rows]
    numbered = [(n, r) for n, r in match_rows if n is not None]
    lines.append(f"행 {len(rows)}개 · 경기 번호가 있는 행 {len(numbered)}개 "
                 f"(번호 {sorted({n for n, _ in numbered})})")

    lines.append("")
    lines.append("== 경기 행 전체 셀 (처음 두 행 · 원문 repr) ==")
    for n, r in numbered[:2]:
        lines.append(f"-- {n}경기 · 셀 {len(r)}개")
        for i, c in enumerate(r):
            lines.append(f"  [{i}] {c!r}")

    lines.append("")
    lines.append("== 경기 행마다 '%' 가 든 칸 ==")
    shapes: Counter[str] = Counter()
    for n, r in numbered:
        hits = [(i, c) for i, c in enumerate(r) if "%" in (c or "")]
        if not hits:
            lines.append(f"  {n:>2}경기: % 가 든 칸 없음")
            continue
        for i, c in hits:
            vals = _PCT_RE.findall(c)
            shapes[(i, shape(c))] += 1
            lines.append(f"  {n:>2}경기 [{i}] 값 {vals} · 합 "
                         f"{sum(float(v.rstrip('% ')) for v in vals):.1f} · {c!r}")

    lines.append("")
    lines.append("== % 칸의 모양 (칸 번호, 숫자→9) ==")
    for (i, s), k in shapes.most_common():
        lines.append(f"  {k:>2}행  [{i}] {s!r}")

    others = [r for n, r in match_rows if n is None and any(c.strip() for c in r)]
    lines.append("")
    lines.append(f"== 경기 번호가 없는 행 {len(others)}개 (원문 repr) ==")
    for r in others:
        lines.append(f"  {r!r}")

    lines.append("")
    lines.append("== 낱말 검색 (표 행 + 프레임 본문) ==")
    blobs = ["\n".join(r) for r in rows] + list(texts)
    for word in KEYWORDS:
        found = []
        for blob in blobs:
            for m in re.finditer(re.escape(word), blob):
                a, b = max(0, m.start() - 30), min(len(blob), m.end() + 40)
                found.append(blob[a:b].replace("\n", " ⏎ "))
        uniq = list(dict.fromkeys(found))
        lines.append(f"  '{word}' {len(found)}회")
        for s in uniq[:6]:
            lines.append(f"      …{s}…")
        if len(uniq) > 6:
            lines.append(f"      (그 밖에 {len(uniq) - 6}곳)")

    if texts:
        lines.append("")
        lines.append(f"== 프레임 본문 {len(texts)}개 ==")
        for i, t in enumerate(texts):
            lines.append(f"  프레임 {i}: {len(t)}자")
    return lines


def live(round_id: str) -> Path:
    """게임슬립을 열어 행과 프레임 본문을 cache/probe/ 에 저장한다."""
    from playwright.sync_api import sync_playwright

    from toto.settings import load_settings
    from toto.sources import betman

    settings = load_settings()
    cfg = settings.betman
    url = cfg["slip_url"].format(
        game_id=cfg.get("game_id", betman.DEFAULT_GAME_ID), round=round_id)
    frames: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = browser.new_page(user_agent=betman.UA, locale="ko-KR")
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_selector("tr", timeout=20000)
            except Exception:
                pass
            page.wait_for_timeout(2500)
            rows = betman._scrape_rows(page)
            for frame in page.frames:
                try:
                    text = frame.evaluate(
                        "() => document.body ? document.body.innerText : ''")
                except Exception as exc:
                    text = f"(읽지 못함: {exc})"
                frames.append({"name": frame.name, "url": frame.url, "text": text})
        finally:
            browser.close()
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = PROBE_DIR / f"betman_votes_{round_id}_{stamp}.json"
    out.write_text(json.dumps({"round": round_id, "captured_at": stamp,
                               "url": url, "rows": rows, "frames": frames},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main(argv=None) -> int:
    from toto.cli import safe_console
    safe_console()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", help="셀 JSON 파일 (생략하면 cache/debug/betman_cells_*.json)")
    ap.add_argument("--live", metavar="ROUND", help="게임슬립을 열어 저장한 뒤 분석 (회차 필수)")
    args = ap.parse_args(argv)

    paths = [Path(f) for f in args.files]
    if args.live:
        if not args.live.isdigit():
            print(f"회차는 숫자여야 합니다: {args.live!r}")
            return 2
        saved = live(args.live)
        print(f"저장 → {saved}")
        paths = [saved]
    if not paths:
        paths = sorted(DEBUG_DIR.glob("betman_cells_*.json"))
    if not paths:
        print(f"셀 파일이 없습니다 — {DEBUG_DIR}")
        return 2

    for path in paths:
        print("=" * 72)
        print(f"{path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"  읽지 못함: {exc}")
            continue
        print(f"  최상위: {type(data).__name__}"
              + (f" · 키 {list(data)[:10]}" if isinstance(data, dict) else
                 f" · {len(data)}개" if isinstance(data, list) else ""))
        for line in analyze(find_rows(data), find_texts(data)):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
