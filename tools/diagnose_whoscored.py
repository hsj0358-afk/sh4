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
    # '-' 로 시작하면 경로가 아니라 옵션이다(메뉴에서 넘어온 --menu 등).
    if arg and not arg.startswith("-"):
        p = Path(arg)
        if p.exists():
            return p
        print(f"지정한 경로가 없습니다: {p}")
        return None
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

    # 팀 링크가 0개면 강점/약점을 가져올 팀 페이지 주소를 못 만든다.
    # 표기가 바뀐 건지(소문자·다른 경로) 아예 없는 건지 구분해야 고칠 수 있다.
    if not links:
        print("  ! 팀 링크가 없어 팀 페이지(강점/약점·스타일)를 열 수 없습니다.")
        variants: dict[str, int] = {}
        for m in re.finditer(r'href="([^"]{3,90})"', raw, re.I):
            href = m.group(1)
            if re.search(r"/teams?/\d+|/team/|player|squad", href, re.I):
                key = re.sub(r"\d+", "{id}", href)[:60]
                variants[key] = variants.get(key, 0) + 1
        if variants:
            print("  팀으로 보이는 링크 형태 (많은 순):")
            for key, n in sorted(variants.items(), key=lambda x: -x[1])[:8]:
                print(f"      {n:>4}회  {key}")
        else:
            print("  팀 비슷한 링크가 아예 없습니다 — 목록이 JS 로 그려지는 듯합니다.")

    # 정성 데이터가 이 페이지에 실려 있는지 (팀 페이지를 못 열더라도 확인)
    low = raw.lower()
    marks = [(name, low.count(name.lower()))
             for name in ("Strengths", "Weaknesses", "Style of play")]
    print("  정성 데이터 문구: "
          + ", ".join(f"{n}={c}회" for n, c in marks))

    # 표
    tables = soup.find_all("table")
    print(f"  <table>: {len(tables)}개")
    for i, t in enumerate(tables[:8]):
        rows = t.find_all("tr")
        tid = t.get("id") or ""
        cls = " ".join(t.get("class") or [])[:34]
        print(f"      [{i}] {len(rows):>3}행  id={tid[:26]:<28} class={cls}")
        # 머리글이 여러 줄일 수 있으므로 앞 3줄과 첫 데이터 2줄을 그대로 보여준다
        for j, r in enumerate(rows[:5]):
            cells = [c.get_text(" ", strip=True)
                     for c in r.find_all(["th", "td"])][:14]
            tag = "th" if r.find("th") else "td"
            print(f"           r{j} ({tag}): {cells}")

    # 표가 없다면 어떤 컨테이너가 있는지
    if not tables:
        ids = [d.get("id") for d in soup.find_all(id=True)][:25]
        print(f"  id 가진 요소 예시: {ids}")

    _tournament_links(raw)


# 저장된 페이지가 홈으로 리다이렉트된 것이라면, 그 안에 대회 메뉴가 들어 있다.
# 거기서 우리가 쓰는 리그의 실제 주소를 뽑아낸다.
_TOURNAMENT_HREF = re.compile(r"/Regions/\d+/Tournaments/\d+[^\"'\s>]*", re.I)

WANTED = {
    "K리그1": ("south-korea", "k-league-1"),
    "K리그2": ("south-korea", "k-league-2"),
    "J리그": ("japan", "j-league"),
    "프리미어리그": ("england", "premier-league"),
    "라리가": ("spain", "laliga"),
    "분데스리가": ("germany", "bundesliga"),
    "세리에A": ("italy", "serie-a"),
    "리그앙": ("france", "ligue-1"),
}


def _tournament_links(raw: str) -> None:
    hrefs = {}
    for href in _TOURNAMENT_HREF.findall(raw):
        tail = re.sub(r"^.*?/Tournaments/\d+/?", "", href, flags=re.I)
        slug = re.sub(r"[^a-z0-9]+", "-", tail.lower()).strip("-")
        if slug:
            hrefs.setdefault(slug, href)
    print(f"  대회(/Regions/../Tournaments/..) 링크: {len(hrefs)}개")
    if not hrefs:
        return
    for label, tokens in WANTED.items():
        hits = [(s, h) for s, h in hrefs.items() if all(t in s for t in tokens)]
        if hits:
            slug, href = min(hits, key=lambda x: len(x[0]))
            print(f"      {label:<8} → {href}")
        else:
            print(f"      {label:<8} → (없음)")


def main(argv: list[str] | None = None) -> int:
    # 메뉴에서 호출할 때는 argv=[] 로 넘어온다. sys.argv 를 그대로 읽으면
    # 부모 프로세스의 옵션(--menu 등)을 경로로 오인한다.
    argv = sys.argv[1:] if argv is None else argv
    target = find_dir(argv[0] if argv else None)
    if target is None:
        print()
        print("후스코어드 실패 원본을 찾지 못했습니다.")
        print(f"  찾아본 위치: {ROOT / 'cache'}/<날짜>/whoscored/")
        print()
        print("먼저 후스코어드 수집을 한 번 실행해야 파일이 생깁니다.")
        print("  메뉴 [1] 전체 수집  또는  [3] 회차 지정해서 수집")
        return 1

    # 리그 페이지 원본(page_league_*)을 우선 본다. 파싱이 '되긴 했는데
    # 값이 이상한' 경우는 이 파일에만 단서가 있다.
    files = sorted(target.glob("FAILED_page_league_*.html"))
    files += [f for f in sorted(target.glob("FAILED_*.html")) if f not in files]
    if not files:
        files = sorted(target.glob("*.html"))
    if not files:
        print(f"{target} 안에 html 파일이 없습니다.")
        return 1

    print(f"대상 폴더: {target}")
    for f in files[:3]:
        summarize(f)
    print("=" * 72)
    print("위 출력을 그대로 복사해서 전달해 주세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
