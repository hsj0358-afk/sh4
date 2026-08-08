"""후스코어드 파싱 실패 원인 진단.

cache/<날짜>/whoscored/FAILED_*.html 을 읽어, 파서를 고치는 데 필요한
정보만 짧게 출력한다. 출력 결과를 그대로 복사해서 전달하면 된다.
(HTML 원본 자체를 주고받지 않아도 되도록 요약만 뽑는다.)

    python tools/diagnose_whoscored.py
    python tools/diagnose_whoscored.py cache/2026-08-08/whoscored
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BLOCK_SIGNS = ("incapsula", "_incap_", "request unsuccessful", "access denied",
               "captcha", "just a moment", "cf-browser-verification")


def find_dir(arg: str | None) -> Path | None:
    if arg:
        p = Path(arg)
        return p if p.exists() else None
    cache = ROOT / "cache"
    if not cache.exists():
        return None
    days = sorted([d for d in cache.iterdir() if d.is_dir() and d.name[:2] == "20"])
    for day in reversed(days):
        ws = day / "whoscored"
        if ws.exists():
            return ws
    return None


def summarize(path: Path) -> None:
    raw = path.read_text(encoding="utf-8", errors="replace")
    print("=" * 72)
    print(f"파일: {path.name}   ({len(raw) / 1024:.0f} KB)")

    title = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    print(f"  <title>: {title.group(1).strip()[:110] if title else '(없음)'}")

    low = raw[:6000].lower()
    hits = [s for s in BLOCK_SIGNS if s in low]
    print(f"  봇 차단 흔적: {hits if hits else '없음'}")

    # 최종 URL 힌트 (리다이렉트되면 canonical 이 바뀐다)
    for pat, label in ((r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', "canonical"),
                       (r'<meta[^>]+property="og:url"[^>]+content="([^"]+)"', "og:url")):
        m = re.search(pat, raw, re.I)
        if m:
            print(f"  {label}: {m.group(1)[:110]}")

    try:
        from bs4 import BeautifulSoup
    except Exception:
        print("  ! beautifulsoup4 없음 — 표 분석 생략")
        return
    try:
        soup = BeautifulSoup(raw, "lxml")
    except Exception:
        soup = BeautifulSoup(raw, "html.parser")

    # 팀 링크
    links = [(a.get("href", ""), a.get_text(" ", strip=True))
             for a in soup.find_all("a", href=True) if "/Teams/" in a.get("href", "")]
    print(f"  /Teams/ 링크: {len(links)}개")
    for href, text in links[:6]:
        print(f"      {text[:28]:<30} {href[:70]}")

    # 표
    tables = soup.find_all("table")
    print(f"  <table>: {len(tables)}개")
    for i, t in enumerate(tables[:8]):
        rows = t.find_all("tr")
        header = []
        if rows:
            header = [c.get_text(" ", strip=True)
                      for c in rows[0].find_all(["th", "td"])][:12]
        tid = t.get("id") or ""
        cls = " ".join(t.get("class") or [])[:34]
        print(f"      [{i}] {len(rows):>3}행  id={tid[:26]:<28} class={cls}")
        if header:
            print(f"           헤더: {header}")
        if len(rows) > 1:
            first = [c.get_text(" ", strip=True)
                     for c in rows[1].find_all(["th", "td"])][:12]
            print(f"           1행 : {first}")

    # 표가 없다면 어떤 컨테이너가 있는지
    if not tables:
        ids = [d.get("id") for d in soup.find_all(id=True)][:25]
        print(f"  id 가진 요소 예시: {ids}")


def main() -> int:
    target = find_dir(sys.argv[1] if len(sys.argv) > 1 else None)
    if target is None:
        print("cache 안에서 whoscored 폴더를 찾지 못했습니다. "
              "경로를 인자로 넘겨주세요.")
        return 1

    files = sorted(target.glob("FAILED_*.html"))
    if not files:
        files = sorted(target.glob("*.html"))
    if not files:
        print(f"{target} 안에 html 파일이 없습니다.")
        return 1

    print(f"대상 폴더: {target}")
    for f in files[:4]:
        summarize(f)
    print("=" * 72)
    print("위 출력을 그대로 복사해서 전달해 주세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
