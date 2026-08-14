"""데이터 소스 점검 — 파서를 쓰기 전에 실물 구조를 확인한다.

이 도구는 **아무것도 파싱하지 않는다.** 각 소스에 실제로 접속해서
"응답이 오는가 / 우리가 필요한 리그가 있는가 / 필요한 지표가 실제 테이블·
JSON 에 들어 있는가"만 관찰해 출력한다.

지금까지 실물을 못 본 채 셀렉터를 추측해 쓰다가 여러 번 왕복했다. 이 출력만
있으면 파서를 한 번에 맞출 수 있다.

    python tools/probe_sources.py              # requests 로 점검
    python tools/probe_sources.py --browser    # 차단되면 실제 브라우저로 재시도
    python tools/probe_sources.py --only fbref

출력을 그대로 복사해서 전달하면 된다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DUMP = ROOT / "cache" / "probe"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 이번 회차(260043)가 전부 J리그·K리그였다. 아시아 커버리지가 최우선이다.
FBREF = {
    "comps 색인": "https://fbref.com/en/comps/",
    "K리그1": "https://fbref.com/en/comps/55/K-League-1-Stats",
    "J1리그": "https://fbref.com/en/comps/25/J1-League-Stats",
    "프리미어리그(대조군)": "https://fbref.com/en/comps/9/Premier-League-Stats",
}

# FBref 에서 확보하려는 지표 (제안서의 '못 구하는 절반')
WANT_COLS = {
    "피슈팅": ("sh_against", "shots against", "sot_against"),
    "xG": ("xg", "expected goals"),
    "xGA": ("xga", "xg_against", "expected goals against"),
    "SCA(슈팅창출)": ("sca",),
    "전진패스 PrgP": ("prgp", "progressive"),
    "최종3분의1 진입": ("final_third", "1/3"),
    "키패스": ("kp", "key pass"),
}

# 경로가 바뀌었을 수 있어 후보를 여러 개 시도한다.
FOTMOB = {
    # 1차 점검에서 200/500KB 로 살아 있음을 확인한 경로
    "api/data/leagues?id=9080 (K1)": "https://www.fotmob.com/api/data/leagues?id=9080",
    # 전체 리그 목록 — K리그2·J1 의 id 를 여기서 찾는다
    "api/data/allLeagues": "https://www.fotmob.com/api/data/allLeagues",
    "웹페이지(K리그1)": "https://www.fotmob.com/leagues/9080/overview/k-league-1",
}

SOFASCORE = {
    "api 검색(K League)": "https://api.sofascore.com/api/v1/search/all?q=K%20League",
    "api 검색(J1)": "https://api.sofascore.com/api/v1/search/all?q=J1%20League",
}

UNDERSTAT = {
    "K리그(있을까)": "https://understat.com/league/K_League",
    "EPL(대조군)": "https://understat.com/league/EPL",
}


# --------------------------------------------------------------------------
def _session():
    import requests
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
        "Accept": "text/html,application/json,*/*",
    })
    return s


def fetch(url: str, browser=None, timeout: int = 25) -> tuple[int, str, str]:
    """(status, text, note) — 실패해도 예외를 던지지 않는다."""
    if browser is not None:
        try:
            code, html = browser.get_raw(url)
            return code, html, "browser"
        except Exception as exc:
            return 0, "", f"browser 오류: {exc}"
    try:
        r = _session().get(url, timeout=timeout)
        return r.status_code, r.text, ""
    except Exception as exc:
        return 0, "", _short_error(exc)


def _short_error(exc: Exception) -> str:
    """연결 오류 메시지를 한 줄로 줄인다 (원문은 매우 길다)."""
    text = str(exc)
    if "Max retries exceeded" in text or "ConnectionPool" in text:
        if "403" in text or "Tunnel connection failed" in text:
            return "연결 차단됨 (프록시/방화벽 403)"
        if "NameResolution" in text or "getaddrinfo" in text:
            return "DNS 조회 실패"
        if "timed out" in text.lower():
            return "시간 초과"
        return "연결 실패 (차단 또는 네트워크)"
    return text.split("(Caused by")[0].strip()[:90]


def save(name: str, text: str) -> None:
    try:
        DUMP.mkdir(parents=True, exist_ok=True)
        (DUMP / f"{re.sub(r'[^0-9A-Za-z가-힣._-]+', '_', name)[:60]}.txt").write_text(
            text[:400000], encoding="utf-8")
    except Exception:
        pass


def head(title: str) -> None:
    print()
    print("=" * 74)
    print(title)
    print("=" * 74)


def _why_blocked(text: str) -> str:
    """응답 본문에서 차단 사유 단서를 뽑는다."""
    if not text:
        return ""
    low = text[:6000].lower()
    for sig, why in (
            ("cloudflare", "Cloudflare"),
            ("just a moment", "Cloudflare 챌린지"),
            ("captcha", "CAPTCHA"),
            ("incapsula", "Incapsula"),
            ("access denied", "접근 거부"),
            ("rate limit", "요청 과다"),
            ("429", "요청 과다(429)"),
            ("forbidden", "Forbidden"),
            ("__next_data__", "Next.js SPA (내장 JSON 있음)"),
            ("<!doctype html", "HTML 문서 (API 아님)")):
        if sig in low:
            return why
    return ""


def _excerpt(text: str, n: int = 150) -> str:
    """본문에서 태그를 걷어낸 앞부분."""
    if not text:
        return ""
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text[:20000],
                  flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    return body[:n]


def status_line(label: str, code: int, text: str, note: str) -> bool:
    ok = code == 200 and len(text) > 500
    mark = "OK " if ok else "실패"
    size = f"{len(text) / 1024:.0f}KB" if text else "0KB"
    extra = f"  {note}" if note else ""
    print(f"  [{mark}] {label:<26} HTTP {code or '---'}  {size:>7}{extra}")
    if not ok and text:
        why = _why_blocked(text)
        if why:
            print(f"         단서: {why}")
        ex = _excerpt(text)
        if ex:
            print(f"         본문: {ex}")
    return ok


# --------------------------------------------------------------------------
# FBref
# --------------------------------------------------------------------------
def unwrap_json(text: str) -> str:
    """브라우저로 JSON URL 을 열면 <pre> 로 감싼 HTML 이 돌아온다. 알맹이만 꺼낸다."""
    if not text:
        return text
    stripped = text.lstrip()
    if stripped[:1] in "{[":
        return text
    m = re.search(r"<pre[^>]*>(.*?)</pre>", text, re.S | re.I)
    if m:
        import html as _h
        return _h.unescape(m.group(1))
    return text


def _soup(html: str):
    from bs4 import BeautifulSoup
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _fbref_tables(html: str):
    """FBref 는 상당수 표를 HTML 주석 안에 넣어둔다. 주석까지 펼쳐서 찾는다."""
    from bs4 import Comment
    soup = _soup(html)
    tables = list(soup.find_all("table"))
    commented = 0
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        if "<table" not in c:
            continue
        try:
            inner = _soup(str(c))
        except Exception:
            continue
        found = inner.find_all("table")
        tables.extend(found)
        commented += len(found)
    return tables, commented


def probe_fbref(browser=None) -> None:
    head("① FBref — 정량 지표 (피슈팅 · xG · xGA · SCA · 전진패스)")
    print("  ※ FBref 는 표 상당수를 HTML 주석 안에 넣어둔다. 주석까지 펼쳐 센다.")
    print("  ※ 연속 요청 시 429 가 나므로 요청 사이에 4초 쉰다.")
    if browser is not None:
        print("  ※ Cloudflare 챌린지(Just a moment)는 몇 초 뒤 자동 해제된다.")
        print("    브라우저 모드에서는 해제를 기다렸다가 다시 읽는다.")

    for i, (label, url) in enumerate(FBREF.items()):
        if i:
            time.sleep(4)
        code, text, note = fetch(url, browser)
        # Cloudflare 인터스티셜이면 해제를 기다렸다가 한 번 더 읽는다
        if browser is not None and "just a moment" in (text or "")[:4000].lower():
            print(f"      Cloudflare 챌린지 감지 — 12초 대기 후 재시도")
            time.sleep(12)
            code2, text2, _ = fetch(url, browser)
            if code2 == 200 and "just a moment" not in (text2 or "")[:4000].lower():
                code, text = code2, text2
        ok = status_line(label, code, text, note)
        if not ok:
            continue
        save(f"fbref_{label}", text)

        if label == "comps 색인":
            soup = _soup(text)
            hits = []
            for a in soup.find_all("a", href=True):
                t = a.get_text(" ", strip=True)
                if re.search(r"K.?League|J\d?.?League|Korea|Japan", t, re.I):
                    hits.append(f"{t} → {a['href']}")
            print(f"      한국/일본 대회 링크 {len(hits)}개:")
            for h in sorted(set(hits))[:14]:
                print(f"        {h}")
            continue

        tables, commented = _fbref_tables(text)
        print(f"      표 {len(tables)}개 (그중 주석 안 {commented}개)")
        cols_all = set()
        for t in tables[:14]:
            tid = t.get("id") or "(id없음)"
            hdr = t.find("thead")
            names = []
            if hdr:
                names = [th.get("data-stat") or th.get_text(" ", strip=True)
                         for th in hdr.find_all("th")]
            cols_all.update(n.lower() for n in names if n)
            rows = len(t.find_all("tr"))
            print(f"        · {tid:<34} {rows:>3}행  컬럼 {len(names)}개")
            if names:
                print(f"          {', '.join(names[:18])}")
        print("      필요한 지표가 실제로 있는지:")
        for want, keys in WANT_COLS.items():
            hit = [c for c in cols_all if any(k in c for k in keys)]
            mark = "있음" if hit else "없음"
            sample = f"  ({', '.join(sorted(hit)[:4])})" if hit else ""
            print(f"        {want:<16} {mark}{sample}")


# --------------------------------------------------------------------------
# JSON API (FotMob / Sofascore)
# --------------------------------------------------------------------------
def _walk_keys(obj, prefix="", depth=0, out=None, maxd=3):
    if out is None:
        out = []
    if depth > maxd:
        return out
    if isinstance(obj, dict):
        for k, v in list(obj.items())[:24]:
            p = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                out.append(f"{p} ({type(v).__name__}"
                           + (f", {len(v)}" if isinstance(v, list) else "") + ")")
                _walk_keys(v, p, depth + 1, out, maxd)
            else:
                out.append(f"{p} = {str(v)[:40]}")
    elif isinstance(obj, list) and obj:
        _walk_keys(obj[0], f"{prefix}[0]", depth + 1, out, maxd)
    return out


def probe_json(title: str, urls: dict, browser=None,
               hint_keys: tuple = ()) -> None:
    head(title)
    for i, (label, url) in enumerate(urls.items()):
        if i:
            time.sleep(1.5)
        code, text, note = fetch(url, browser)
        ok = status_line(label, code, text, note)
        if not ok:
            continue
        save(f"{title[:6]}_{label}", text)
        text = unwrap_json(text)
        try:
            data = json.loads(text)
        except Exception:
            # SPA 페이지라면 내장 JSON(__NEXT_DATA__)에 데이터가 들어 있다.
            m = re.search(
                r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.S)
            if m:
                print("      JSON 이 아니라 SPA 페이지 — __NEXT_DATA__ 발견")
                try:
                    data = json.loads(m.group(1))
                    print(f"      내장 JSON 크기 {len(m.group(1)) / 1024:.0f}KB")
                except Exception as exc:
                    print(f"      내장 JSON 파싱 실패: {exc}")
                    continue
            else:
                print("      JSON 파싱 실패, 내장 JSON 도 없음 (차단 가능성)")
                continue
        keys = _walk_keys(data)
        print(f"      최상위 구조 ({len(keys)}개 경로 중 앞부분):")
        for k in keys[:20]:
            print(f"        {k}")

        # 순위표·팀 지표가 들어 있을 만한 경로를 더 깊이 펼친다
        for path in ("props.pageProps.table", "table", "details", "overview",
                     "leagues", "stats"):
            node = data
            try:
                for part in path.split("."):
                    node = node[part]
            except Exception:
                continue
            deep = _walk_keys(node, path, maxd=5)
            if deep:
                print(f"      ▼ {path} 상세 ({len(deep)}개 중 앞부분):")
                for k in deep[:30]:
                    print(f"        {k}")
                break
        low = text.lower()
        for hk in hint_keys:
            print(f"        · '{hk}' 포함: {'예' if hk.lower() in low else '아니오'}")


# --------------------------------------------------------------------------
def probe_understat(browser=None) -> None:
    head("④ Understat — xG 전문 (유럽 5대 리그 한정으로 알려져 있음)")
    for i, (label, url) in enumerate(UNDERSTAT.items()):
        if i:
            time.sleep(1.5)
        code, text, note = fetch(url, browser)
        ok = status_line(label, code, text, note)
        if ok:
            has = "teamsData" in text or "datesData" in text
            print(f"      내장 JSON(teamsData) 존재: {'예' if has else '아니오'}")


# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="데이터 소스 접속·구조 점검")
    ap.add_argument("--browser", action="store_true",
                    help="requests 가 막히면 실제 브라우저로 시도")
    ap.add_argument("--only", default="",
                    help="fbref / fotmob / sofascore / understat 중 하나만")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    try:
        import requests  # noqa: F401
        import bs4       # noqa: F401
    except Exception as exc:
        print(f"필수 패키지가 없습니다: {exc}")
        print("pip install -r requirements-toto.txt 를 먼저 실행하세요.")
        return 1

    print("데이터 소스 점검 — 파싱하지 않고 구조만 관찰합니다.")
    print(f"원본 응답은 {DUMP} 에 저장됩니다.")

    browser = None
    ctx = None
    if args.browser:
        try:
            sys.path.insert(0, str(ROOT))
            from toto.cache import Cache
            from toto.settings import load_settings
            from toto.sources.whoscored import WhoScoredBrowser
            s = load_settings()
            s.whoscored = dict(s.whoscored, delay_sec=2.0)
            ctx = WhoScoredBrowser(s, cache=Cache(enabled=True))
            browser = ctx.__enter__()
            if not browser.available:
                print("브라우저를 띄우지 못해 requests 로 진행합니다.")
                browser = None
        except Exception as exc:
            print(f"브라우저 준비 실패({exc}) — requests 로 진행합니다.")
            browser = None

    try:
        only = args.only.lower()
        if not only or only == "fbref":
            probe_fbref(browser)
        if not only or only == "fotmob":
            probe_json("② FotMob — 아시아 리그 + 결장자/평점", FOTMOB, browser,
                       hint_keys=("kleague", "j1", "shotsOnTarget", "rating"))
        if not only or only == "sofascore":
            probe_json("③ Sofascore — 아시아 리그 보조", SOFASCORE, browser,
                       hint_keys=("k league", "j1 league", "uniqueTournament"))
        if not only or only == "understat":
            probe_understat(browser)
    finally:
        if ctx is not None:
            try:
                ctx.__exit__(None, None, None)
            except Exception:
                pass

    print()
    print("=" * 74)
    print("점검 끝. 위 출력을 그대로 복사해서 전달해 주세요.")
    if browser is None:
        print("실패가 많다면 메뉴 [7] 에서 브라우저 사용에 'y' 로 다시 실행해 보세요.")
        print("(requests 는 UA 만 바꾸므로 Cloudflare 계열 차단을 통과하지 못합니다)")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
