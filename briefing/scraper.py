"""네이버 '신문보기'(지면) 스크래퍼.

- 기사 목록: 지면 페이지가 JS 로 렌더링되므로 Playwright(헤드리스 크롬)로 수집한다.
  URL: https://media.naver.com/press/{oid}/newspaper?date=YYYYMMDD
- 기사 본문: 개별 기사 페이지(n.news.naver.com)는 서버 렌더링이라 requests 로 충분.

playwright / requests / bs4 는 함수 안에서 지연 import 한다.
(샘플/오프라인 테스트 시 이 모듈을 import 만 해도 깨지지 않도록)
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)

NEWSPAPER_URL = "https://media.naver.com/press/{oid}/newspaper"
ARTICLE_URL = "https://n.news.naver.com/article/{oid}/{aid}"
ARTICLE_HREF_RE = re.compile(r"/article/(?:mnews/)?(\d{3})/(\d+)")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


@dataclass
class Article:
    oid: str
    aid: str
    press: str
    title: str
    url: str
    page: str = ""        # 지면 면 정보(있으면)
    body: str = ""
    published: str = ""

    @property
    def key(self) -> str:
        return f"{self.oid}/{self.aid}"


def _clean(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------
# 기사 목록 (Playwright)
# --------------------------------------------------------------------------
def fetch_newspaper_list(oid: str, press: str, date: str | None = None,
                         timeout_ms: int = 30000) -> list[Article]:
    """한 언론사의 지면 기사 목록을 수집한다."""
    from playwright.sync_api import sync_playwright

    url = NEWSPAPER_URL.format(oid=oid)
    if date:
        url += f"?date={date}"

    anchors: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = browser.new_page(user_agent=UA, locale="ko-KR")
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_selector("a[href*='/article/']", timeout=timeout_ms)
            except Exception:
                log.warning("[%s] 기사 링크 selector 대기 실패 — 페이지 구조 확인 필요", press)
            # 지면이 면 단위 lazy-load 되므로 스크롤로 모두 로드
            for _ in range(8):
                page.mouse.wheel(0, 5000)
                page.wait_for_timeout(350)
            anchors = page.eval_on_selector_all(
                "a[href*='/article/']",
                "els => els.map(e => ({href: e.href, text: (e.innerText||'').trim()}))",
            )
        finally:
            browser.close()

    found: dict[str, Article] = {}
    for a in anchors:
        m = ARTICLE_HREF_RE.search(a.get("href", ""))
        if not m:
            continue
        a_oid, aid = m.group(1), m.group(2)
        if a_oid != oid:          # 다른 언론사 링크(추천 등) 제외
            continue
        title = _clean(a.get("text", ""))
        if not title or len(title) < 6:   # 썸네일/빈 링크 제외
            continue
        key = f"{a_oid}/{aid}"
        if key in found:
            # 같은 기사가 여러 링크로 잡히면 더 긴 제목 채택
            if len(title) > len(found[key].title):
                found[key].title = title
            continue
        found[key] = Article(
            oid=a_oid, aid=aid, press=press, title=title,
            url=ARTICLE_URL.format(oid=a_oid, aid=aid),
        )
    log.info("[%s] 기사 %d건 수집", press, len(found))
    return list(found.values())


def scrape_all(presses: dict, date: str | None = None) -> list[Article]:
    """설정된 모든 언론사의 지면 기사 목록을 수집한다."""
    articles: list[Article] = []
    for oid, press in presses.items():
        try:
            items = fetch_newspaper_list(str(oid), press, date=date)
            articles.extend(items)
        except Exception as e:  # 한 언론사 실패가 전체를 막지 않도록
            log.error("[%s] 목록 수집 실패: %s", press, e)
        time.sleep(1.0)  # 과도한 연속 요청 방지
    return articles


# --------------------------------------------------------------------------
# 기사 본문 (requests + BeautifulSoup)
# --------------------------------------------------------------------------
def _session():
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    return s


def fetch_article_body(article: Article, session=None, timeout: int = 15) -> Article:
    from bs4 import BeautifulSoup

    session = session or _session()
    try:
        r = session.get(article.url, timeout=timeout)
        r.raise_for_status()
    except Exception as e:
        log.warning("본문 수집 실패 %s: %s", article.url, e)
        return article

    soup = BeautifulSoup(r.text, "lxml")

    title_el = soup.select_one("#title_area") or soup.select_one("h2.media_end_head_headline")
    if title_el:
        t = _clean(title_el.get_text(" "))
        if t:
            article.title = t

    body_el = (soup.select_one("#dic_area")
               or soup.select_one("#newsct_article")
               or soup.select_one("article"))
    if body_el:
        for bad in body_el.select("script, style, .media_end_summary, .img_desc, "
                                  "em.img_desc, .end_photo_org, .vod_player_wrap"):
            bad.decompose()
        article.body = _clean(body_el.get_text("\n"))
    if not article.body:
        og = soup.select_one("meta[property='og:description']")
        if og:
            article.body = og.get("content", "")

    dt_el = soup.select_one(".media_end_head_info_datestamp_time")
    if dt_el:
        article.published = dt_el.get("data-date-time") or _clean(dt_el.get_text())

    return article


def fetch_bodies(articles: list[Article], delay: float = 0.3) -> list[Article]:
    """여러 기사 본문을 순차 수집(서버 부하/차단 방지를 위해 약간의 지연)."""
    session = _session()
    for a in articles:
        fetch_article_body(a, session=session)
        time.sleep(delay)
    return articles
