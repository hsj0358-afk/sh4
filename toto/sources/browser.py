"""여러 소스가 공유하는 Playwright 스텔스 세션.

후스코어드는 Incapsula, FotMob 은 API 게이트웨이 때문에 `requests` 만으로는
거의 통과하지 못한다(점검 도구에서 FotMob API 가 requests 로는 404, 실제
브라우저로는 200 이었다). 실제 브라우저를 띄우고 프로필을 유지해 통과 쿠키를
재사용하는 방식이 두 소스 모두에 필요해서, 세션 관리만 여기로 뺀다.

차단 판정은 소스마다 다르다(후스코어드는 짧은 응답이 곧 차단이지만 JSON API 는
원래 짧다). 그래서 기본값은 '차단 아님' 이고, 필요하면 `_is_blocked` 를
덮어쓴다.
"""
from __future__ import annotations

import html as _html
import json
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 자동화 탐지를 줄이는 초기 스크립트
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-GB', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = window.chrome || {runtime: {}};
"""


def unwrap_json(text: str) -> str:
    """브라우저로 JSON URL 을 열면 <pre> 로 감싼 HTML 이 온다. 알맹이만 꺼낸다."""
    if not text:
        return text
    if text.lstrip()[:1] in "{[":
        return text
    m = re.search(r"<pre[^>]*>(.*?)</pre>", text, re.S | re.I)
    return _html.unescape(m.group(1)) if m else text


class StealthBrowser:
    """Playwright 세션 래퍼 (with 문으로 사용).

    cfg 키: base / headless / delay_sec / timeout_ms / persistent_profile
    """

    def __init__(self, cfg: dict | None = None, cache=None,
                 name: str = "browser") -> None:
        self.cfg = cfg or {}
        self.name = name
        self.base = self.cfg.get("base", "")
        self.delay = float(self.cfg.get("delay_sec", 2.0))
        self.timeout = int(self.cfg.get("timeout_ms", 45000))
        self.cache = cache
        self._pw = None
        self._ctx = None
        self._browser = None
        self._page = None
        self.available = False
        self._last_load = 0.0

    # ---- 소스별로 덮어쓰는 훅 -------------------------------------------
    def _is_blocked(self, html: str) -> bool:
        return False

    # ---- 수명 주기 -------------------------------------------------------
    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            log.error("playwright 미설치 — %s 수집을 건너뜁니다. "
                      "`pip install -r requirements-toto.txt && "
                      "playwright install chromium`", self.name)
            return self

        args = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ]
        headless = bool(self.cfg.get("headless", True))
        try:
            self._pw = sync_playwright().start()
            if self.cfg.get("persistent_profile", True) and self.cache is not None:
                self._ctx = self._pw.chromium.launch_persistent_context(
                    str(self.cache.browser_profile), headless=headless, args=args,
                    user_agent=UA, locale="en-GB",
                    viewport={"width": 1440, "height": 900})
                self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
            else:
                self._browser = self._pw.chromium.launch(headless=headless, args=args)
                self._ctx = self._browser.new_context(
                    user_agent=UA, locale="en-GB",
                    viewport={"width": 1440, "height": 900})
                self._page = self._ctx.new_page()
            self._ctx.add_init_script(STEALTH_JS)
            self.available = True
        except Exception as exc:
            log.error("브라우저 기동 실패: %s", exc)
        return self

    def __exit__(self, *exc) -> None:
        # 컨텍스트 → 브라우저 → playwright 순으로 정리. 하나가 실패해도 나머지는 닫는다.
        for obj, method in ((self._ctx, "close"),
                            (self._browser, "close"),
                            (self._pw, "stop")):
            if obj is None:
                continue
            try:
                getattr(obj, method)()
            except Exception:
                pass

    # ---- 요청 -------------------------------------------------------------
    def _wait_turn(self) -> None:
        gap = time.time() - self._last_load
        if gap < self.delay:
            time.sleep(self.delay - gap)

    def get_html(self, url: str, wait_selector: str | None = None) -> str:
        """페이지를 열고 HTML 을 돌려준다. 실패하거나 차단이면 빈 문자열."""
        if not self.available:
            return ""
        self._wait_turn()
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
            if wait_selector:
                try:
                    self._page.wait_for_selector(wait_selector, timeout=15000)
                except Exception:
                    log.debug("셀렉터 대기 실패(%s) — 그래도 진행: %s", wait_selector, url)
            # 순위표·통계표는 스크롤해야 채워지는 경우가 있다.
            try:
                self._page.evaluate(
                    "window.scrollTo(0, document.body.scrollHeight / 2)")
                self._page.wait_for_timeout(800)
                self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except Exception:
                pass
            self._page.wait_for_timeout(2000)
            html = self._page.content()
            self._last_load = time.time()
            if self._is_blocked(html):
                log.warning("봇 차단 화면으로 보입니다: %s (headless: false 로 한 번 "
                            "실행하면 통과 쿠키가 저장됩니다)", url)
                return ""
            return html
        except Exception as exc:
            log.warning("페이지 로드 실패 %s: %s", url, exc)
            self._last_load = time.time()
            return ""

    def get_raw(self, url: str) -> tuple[int, str]:
        """차단 판정 없이 응답을 그대로 가져온다 (JSON API·점검 도구용).

        get_html() 은 짧은 응답을 '차단'으로 보는데, JSON API 는 원래 짧아서
        그 휴리스틱을 적용하면 안 된다.
        """
        if not self.available:
            return 0, ""
        self._wait_turn()
        try:
            resp = self._page.goto(url, wait_until="domcontentloaded",
                                   timeout=self.timeout)
            self._page.wait_for_timeout(1200)
            self._last_load = time.time()
            return (resp.status if resp else 0), self._page.content()
        except Exception as exc:
            log.warning("원본 로드 실패 %s: %s", url, exc)
            self._last_load = time.time()
            return 0, ""

    def get_json(self, url: str) -> Any | None:
        """JSON API 를 브라우저로 호출해 파싱한다. 실패하면 None."""
        status, text = self.get_raw(url)
        if status and status >= 400:
            log.warning("%s HTTP %s: %s", self.name, status, url)
            return None
        try:
            return json.loads(unwrap_json(text))
        except Exception:
            log.debug("%s JSON 파싱 실패 (%.0fKB): %s",
                      self.name, len(text) / 1024, url)
            return None

    def abs_url(self, path: str) -> str:
        return urljoin(self.base, path)
