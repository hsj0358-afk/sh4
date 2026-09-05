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
        # 파일명을 손으로 적다 틀리기 쉽다(팀명은 한글이 아니라 정규 영문명이다).
        # 같은 폴더에 실제로 무엇이 있는지 보여 준다.
        if p.parent.is_dir():
            names = sorted(f.name for f in p.parent.glob("FAILED_*.html"))
            if names:
                print(f"  그 폴더에 있는 파일 {len(names)}개:")
                for name in names[:30]:
                    print(f"      {name}")
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


# 팀 페이지에서 찾는 정성 데이터 제목. 파서(`_CHARACTERISTIC_HEADINGS`)가
# 쓰는 세 개에 더해, 문구가 바뀌었을 가능성을 보려고 주변 낱말도 함께 센다.
CHAR_MARKS = ("Strengths", "Weaknesses", "Style of play", "Characteristics",
              "Team Characteristics", "Strength", "Weakness")


def _head(path: Path, raw: str) -> str:
    """파일 공통 머리말. 크기·제목·차단 흔적·최종 URL."""
    print("=" * 72)
    print(f"파일: {path.name}   ({len(raw) / 1024:.0f} KB)")
    title = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    text = title.group(1).strip()[:110] if title else "(없음)"
    print(f"  <title>: {text}")
    hits = [s for s in BLOCK_SIGNS if s in raw[:6000].lower()]
    print(f"  봇 차단 흔적: {hits if hits else '없음'}")
    for pat, label in (
            (r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', "canonical"),
            (r'<meta[^>]+property="og:url"[^>]+content="([^"]+)"', "og:url")):
        m = re.search(pat, raw, re.I)
        if m:
            print(f"  {label}: {m.group(1)[:110]}")
    return text


def _in_script(raw: str, pos: int) -> bool:
    """raw[pos] 가 <script> 안인가. 조각을 찍을 때 자리를 밝히려고 쓴다."""
    opened = raw.rfind("<script", 0, pos)
    if opened < 0:
        return False
    closed = raw.find("</script", opened)
    return closed < 0 or closed > pos


def summarize_team(path: Path) -> None:
    """팀 페이지 전용 진단 — 정성 데이터(강점/약점/스타일)가 왜 안 나오나.

    리그 페이지 진단과 묻는 것이 다르다. 저쪽은 "팀 링크가 있나" 이고
    이쪽은 **"그 문구가 문서에 있기는 한가, 있다면 어떤 구조인가"** 다.
    파서는 제목 텍스트를 찾아 `find_next(["ul","ol","dd","table","div"])`
    로 뒤따르는 목록을 읽는데, 실제 구조가 그와 다르면 조용히 빈다.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    _head(path, raw)

    # 1. 문구가 문서 어디에 있나 — DOM 과 <script> 를 나눠 센다.
    scripts = "".join(re.findall(r"<script[^>]*>(.*?)</script>", raw, re.S | re.I))
    dom = re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=re.S | re.I)
    print("  정성 문구 (DOM / script):")
    any_dom = any_script = 0
    for name in CHAR_MARKS:
        d, s = dom.lower().count(name.lower()), scripts.lower().count(name.lower())
        if d or s:
            print(f"      {name:<20} DOM {d:>3}회 · script {s:>3}회")
            any_dom += d
            any_script += s
    if not (any_dom or any_script):
        print("      (하나도 없음)")

    # 1-b. 원본 조각 — 가설을 더 세우지 말고 마크업을 그대로 본다.
    #      DOM 이든 script 든 "어떤 태그·어떤 키로 싸여 있나" 가 여기서 끝난다.
    if any_dom or any_script:
        print("  원본 조각 (앞뒤 그대로):")
        shown = 0
        # 셀 때 쓴 낱말과 같은 것을 찾아야 한다. 'strengths' 만 찾으면
        # 키가 positiveCharacteristics 인 경우에 조각이 하나도 안 나온다.
        frag_pat = re.compile(
            r"strengths?|weaknesses?|style ?of ?play|characteristics?|playing ?style",
            re.I)
        for m in frag_pat.finditer(raw):
            lo, hi = max(0, m.start() - 150), min(len(raw), m.end() + 260)
            frag = re.sub(r"\s+", " ", raw[lo:hi]).strip()
            where = "script" if _in_script(raw, m.start()) else "DOM"
            print(f"      [{where}] …{frag}…")
            shown += 1
            if shown >= 5:
                break

    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:
        print("  ! beautifulsoup4 없음 — 구조 분석 생략")
        return
    soup = BeautifulSoup(raw, "html.parser")

    # 2. DOM 에 있으면 어떤 구조인지 — 파서가 헛짚는 자리를 그대로 보여준다.
    if any_dom:
        print("  DOM 에서 찾은 자리:")
        seen = 0
        for node in soup.find_all(string=re.compile(
                r"^\s*(strengths?|weaknesses?|style of play)\s*:?\s*$", re.I)):
            parent = node.parent
            if parent is None:
                continue
            chain = []
            cur = parent
            for _ in range(3):
                if cur is None or not getattr(cur, "name", None):
                    break
                cls = ".".join((cur.get("class") or [])[:2])
                chain.append(cur.name + (f".{cls}" if cls else ""))
                cur = cur.parent
            nxt = parent.find_next(["ul", "ol", "dd", "table", "div"])
            kind = "(뒤에 아무것도 없음)"
            if nxt is not None:
                li = len(nxt.find_all("li"))
                sp = len(nxt.find_all(["span", "td", "p"]))
                cls = ".".join((nxt.get("class") or [])[:2])
                kind = (f"{nxt.name}{'.' + cls if cls else ''} "
                        f"· li {li}개 · span/td/p {sp}개")
                sample = [x.get_text(" ", strip=True)
                          for x in (nxt.find_all("li") or
                                    nxt.find_all(["span", "td", "p"]))[:3]]
                kind += f" · 예: {sample}"
            print(f"      '{node.strip()[:24]}' 위치 {' < '.join(chain)}")
            print(f"          다음 컨테이너 → {kind}")
            # 제목이 든 블록을 통째로 찍는다. 항목 이름이 어느 태그에 있는지
            # 조각으로는 잘려서 안 보인다 — 여기서 한 번에 끝낸다.
            block = parent.parent if parent.parent is not None else parent
            dump = re.sub(r"\s+", " ", str(block))
            print(f"          블록 원본({len(dump)}자 중 앞 2200자):")
            print(f"            {dump[:2200]}")
            seen += 1
            if seen >= 2:
                break
        if seen == 0:
            print("      제목처럼 단독으로 있는 노드는 없음 "
                  "(문장 안에 섞여 있을 가능성)")

    # 3. script 에만 있으면 어떤 키로 들어 있나 — 폴백이 찾는 키와 대조.
    if any_script and not any_dom:
        print("  script 안의 키 이름 (파서 폴백은 "
              '"strengths"/"weaknesses"/"style" 을 찾는다):')
        keys = set()
        for m in re.finditer(r'"([A-Za-z_]{3,30})"\s*:\s*\[', scripts):
            key = m.group(1)
            if any(w in key.lower() for w in ("streng", "weak", "style",
                                              "charact", "trait")):
                keys.add(key)
        print(f"      {sorted(keys) if keys else '(배열 형태의 관련 키 없음)'}")

    # 4. 문구가 아예 없으면 — 이 페이지에 무슨 섹션이 있는지 그대로 보여준다.
    if not (any_dom or any_script):
        heads = []
        for h in soup.find_all(["h1", "h2", "h3", "h4"]):
            t = h.get_text(" ", strip=True)
            if 1 < len(t) < 40:
                heads.append(t)
        print(f"  이 페이지의 제목들 (상위 20): {heads[:20]}")
        print(f"  <table> {len(soup.find_all('table'))}개 · "
              f"<ul> {len(soup.find_all('ul'))}개")

    # 5. 최근 경기(form) 단서 — 로그상 특성과 폼이 함께 실패했다.
    rows = 0
    for t in soup.find_all("table"):
        rows = max(rows, len(t.find_all("tr")))
    print(f"  가장 큰 표의 행 수: {rows}행 "
          f"(폼을 읽으려면 최근 경기 표가 있어야 한다)")


def summarize(path: Path) -> None:
    if path.name.startswith("FAILED_team_"):
        summarize_team(path)
        return
    raw = path.read_text(encoding="utf-8", errors="replace")
    _head(path, raw)   # 최종 URL 힌트(canonical·og:url)도 여기서 함께 찍는다

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
    # 실제 경로는 소문자 `/teams/` 다. 대소문자를 가려 세면 링크가 멀쩡히
    # 있는데도 0개로 보고해, 파서(대소문자 무시)와 진단이 어긋난다.
    links = [(a.get("href", ""), a.get_text(" ", strip=True))
             for a in soup.find_all("a", href=True)
             if "/teams/" in a.get("href", "").lower()]
    print(f"  팀 링크(/teams/, 대소문자 무시): {len(links)}개")
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

    # 파일 하나를 직접 지목할 수 있다 — 특정 팀만 보고 싶을 때.
    if argv and not argv[0].startswith("-") and Path(argv[0]).is_file():
        summarize(Path(argv[0]))
        print("=" * 72)
        print("위 출력을 그대로 복사해서 전달해 주세요.")
        return 0

    target = find_dir(argv[0] if argv else None)
    if target is None:
        print()
        print("후스코어드 실패 원본을 찾지 못했습니다.")
        print(f"  찾아본 위치: {ROOT / 'cache'}/<날짜>/whoscored/")
        print()
        print("먼저 후스코어드 수집을 한 번 실행해야 파일이 생깁니다.")
        print("  메뉴 [1] 전체 수집  또는  [3] 회차 지정해서 수집")
        return 1

    # 리그 페이지와 팀 페이지는 **묻는 것이 다르다** — 리그는 "팀 링크가 있나",
    # 팀은 "강점/약점 문구가 있나". 앞에서부터 잘라 내면 리그 파일만 3개
    # 나오고 정작 정성 데이터 질문에는 답이 안 나온다. 종류별로 골라 담는다.
    league = sorted(target.glob("FAILED_page_league_*.html"))
    team = sorted(target.glob("FAILED_team_*.html"))
    rest = [f for f in sorted(target.glob("FAILED_*.html"))
            if f not in league and f not in team]
    files = league[:2] + team[:2] + rest[:2]
    if not files:
        files = sorted(target.glob("*.html"))[:3]
    if not files:
        print(f"{target} 안에 html 파일이 없습니다.")
        return 1

    print(f"대상 폴더: {target}")
    print(f"  리그 원본 {len(league)}개 · 팀 원본 {len(team)}개 · 그 밖 {len(rest)}개"
          f"  →  {len(files)}개를 봅니다")
    for f in files:
        summarize(f)
    print("=" * 72)
    print("위 출력을 그대로 복사해서 전달해 주세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
