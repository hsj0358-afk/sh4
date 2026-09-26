"""후스코어드 차단 감지 회귀 테스트.

2026-09-25 GitHub Actions 실측에서 후스코어드가 첫 요청부터 **HTTP 403** 과
`Attention Required! | Cloudflare` 제목의 4KB 화면을 돌려줬다. 그런데

  · `_looks_blocked()` 는 Incapsula 표지와 `just a moment` 만 알아서 이
    화면(800B 이상)을 정상 페이지로 봤고,
  · `get_html()` 은 `page.goto()` 의 응답(=HTTP 상태)을 버리고 있었다.

그래서 차단 화면이 파서로 넘어가 `팀 링크가 없습니다 — 리그 경로가
틀렸거나 JS 렌더링 대기가 부족` 이라는 **엉뚱한 사유**가 기록됐다.

고친 뒤의 규칙:

  · `get_html()` 이 응답 상태를 `last_status` 에 남긴다. 모르면 None 이다.
  · 후스코어드는 HTTP 403 · Cloudflare 제목/오류 화면 · 예전 표지를
    차단으로 보고, 그 페이지를 **파싱하지 않는다.**
  · 로그에 `[whoscored] 차단 감지 | status=… | type=… | url=… | title=…`.
  · 공용 기본값(`StealthBrowser._block_reason`)은 예전 `_is_blocked(html)`
    그대로다 — 다른 소스는 상태를 보지 않는다.

**우회를 시험하지 않는다.** 이 파일은 막힌 것을 정확히 알아보는지만 본다.
외부 사이트에 접속하지 않는다 — Playwright 페이지를 흉내 낸다.

    python tests/test_whoscored_block_detection.py
"""
from __future__ import annotations

import ast
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto.normalize import TeamResolver                         # noqa: E402
from toto.settings import load_settings                         # noqa: E402
from toto.sources import browser as B                           # noqa: E402
from toto.sources import whoscored as W                         # noqa: E402
from toto.sources.fotmob import FotMobBrowser                   # noqa: E402

import tests.test_league_stat_table as LS                       # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# 픽스처
# --------------------------------------------------------------------------
# Actions 실측에서 확인된 것은 **상태 403 · 제목 · 크기(약 4.2KB)** 뿐이다.
# 본문은 받아 보지 못했다(아티팩트를 열 수 없었다). 아래 본문은 Cloudflare
# 차단 화면의 일반적인 모양을 옮긴 **대표 픽스처**이고, 테스트는 본문의
# 세부가 아니라 제목·상태로 판정되는지를 본다.
_CF_BODY = """
<div id="cf-wrapper">
  <div id="cf-error-details" class="cf-error-details-wrapper">
    <div class="cf-wrapper cf-header cf-error-overview">
      <h1 data-translate="block_headline">Sorry, you have been blocked</h1>
      <h2 class="cf-subheadline">You are unable to access whoscored.com</h2>
    </div>
    <div class="cf-section cf-wrapper">
      <h2 data-translate="blocked_why_headline">Why have I been blocked?</h2>
      <p>This website is using a security service to protect itself from
      online attacks.</p>
    </div>
    <div class="cf-error-footer">Cloudflare Ray ID: 0000000000000000</div>
  </div>
</div>"""

CF_BLOCK_PAGE = (
    "<!DOCTYPE html><html lang=\"en-US\"><head>"
    "<title>Attention Required! | Cloudflare</title>"
    "<meta charset=\"UTF-8\" />"
    "<link rel=\"stylesheet\" href=\"/cdn-cgi/styles/cf.errors.css\" />"
    "</head><body>" + _CF_BODY + ("<!-- pad -->" * 280) + "</body></html>")

# 제목이 Cloudflare 가 아니어도 오류 화면 구조가 있으면 Cloudflare 다.
CF_BODY_ONLY = ("<html><head><title>whoscored.com</title></head><body>"
                + _CF_BODY + ("<!-- pad -->" * 280) + "</body></html>")

JUST_A_MOMENT = ("<html><head><title>Just a moment...</title></head><body>"
                 + ("<p>Checking your browser</p>" * 60) + "</body></html>")

INCAPSULA = ("<html><head><META NAME=\"robots\" CONTENT=\"noindex,nofollow\">"
             "<script src=\"/_Incapsula_Resource?SWJIYLWA=5074a74\"></script>"
             "</head><body>" + ("<p>Request unsuccessful.</p>" * 60)
             + "</body></html>")

# 정상 페이지 — Cloudflare 뒤에 있는 사이트는 정상 화면에도 cdnjs 스크립트나
# /cdn-cgi/ 경로가 실릴 수 있다. 이런 페이지를 차단으로 보면 안 된다.
NORMAL_PAGE = LS._page(
    "<script src=\"https://cdnjs.cloudflare.com/ajax/libs/jquery/3.7.1/jquery.min.js\">"
    "</script>"
    + LS.STANDINGS + LS.TABS
    + "<script src=\"/cdn-cgi/challenge-platform/scripts/jsd/main.js\"></script>")
TEAM_PAGE = ("<html><head><title>AC Milan - Football Statistics | WhoScored.com"
             "</title></head><body>" + ("<p>stats</p>" * 200) + "</body></html>")


class FakeResponse:
    def __init__(self, status):
        self.status = status


class FakePage:
    """`get_html` 이 부르는 Playwright 메서드만 흉내낸다. 네트워크 없음."""

    def __init__(self, routes, status_none=False):
        self.routes = routes              # [(주소 조각, (상태, html))]
        self.status_none = status_none
        self.gotos = []

    def _find(self, url):
        for frag, reply in self.routes:
            if frag in url:
                return reply
        return 200, ""

    def goto(self, url, wait_until=None, timeout=None):
        self.gotos.append((url, wait_until))
        self._cur = self._find(url)
        return None if self.status_none else FakeResponse(self._cur[0])

    def wait_for_selector(self, sel, timeout=None):
        return None

    def evaluate(self, js):
        return None

    def wait_for_timeout(self, ms):
        return None

    def content(self):
        return self._cur[1]


def _browser(routes, status_none=False):
    b = W.WhoScoredBrowser(load_settings(), cache=None)   # 브라우저를 띄우지 않는다
    b.available, b.delay = True, 0.0
    b._page = FakePage(routes, status_none=status_none)
    return b


class _Cache:
    def __init__(self):
        self.debug, self.saved = [], {}

    def get(self, ns, key):
        return None

    def set(self, ns, key, value):
        self.saved[(ns, key)] = value

    def save_debug(self, ns, key, body, failed=True):
        self.debug.append((ns, key, failed, body))


class _Logs(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def _capture():
    h = _Logs()
    for name in ("toto.sources.browser", "toto.sources.whoscored"):
        lg = logging.getLogger(name)
        lg.addHandler(h)
        lg.setLevel(logging.DEBUG)
    return h


def _release(h):
    for name in ("toto.sources.browser", "toto.sources.whoscored"):
        logging.getLogger(name).removeHandler(h)


# ==========================================================================
# A. 판정 — 요청된 다섯 경우
# ==========================================================================
def test_a1_403_attention_required_is_blocked():
    assert W._looks_blocked(CF_BLOCK_PAGE, 403) is True
    assert W._block_kind(CF_BLOCK_PAGE, 403) == "cloudflare"


def test_a2_403_cloudflare_body_is_blocked():
    assert W._looks_blocked(CF_BODY_ONLY, 403) is True
    assert W._block_kind(CF_BODY_ONLY, 403) == "cloudflare"


def test_a2b_cloudflare_page_is_blocked_even_without_status():
    """상태를 모르는 경우(응답 없음·옛 호출부)에도 화면만으로 알아본다."""
    assert W._block_kind(CF_BLOCK_PAGE) == "cloudflare"
    assert W._block_kind(CF_BODY_ONLY) == "cloudflare"


def test_a3_just_a_moment_still_blocked():
    for status in (None, 200, 403, 503):
        assert W._block_kind(JUST_A_MOMENT, status) == "cloudflare", status


def test_a4_incapsula_still_blocked():
    assert W._looks_blocked(INCAPSULA) is True
    assert W._block_kind(INCAPSULA) == "incapsula"


def test_a5_normal_page_not_blocked():
    for html in (NORMAL_PAGE, LS.LEAGUE_PAGE, TEAM_PAGE):
        for status in (None, 200):
            assert W._block_kind(html, status) == "", (status, html[:80])


def test_a5b_cloudflare_asset_urls_do_not_trigger():
    """맨 문자열 'cloudflare' 는 본문에서 찾지 않는다 (오탐 방지)."""
    assert "cloudflare" in NORMAL_PAGE[:4000].lower()
    assert W._block_kind(NORMAL_PAGE, 200) == ""


def test_a6_plain_403_is_blocked():
    """표지가 없어도 403 자체가 차단 신호다."""
    assert W._block_kind(TEAM_PAGE, 403) == "http_403"


def test_a7_short_page_rule_unchanged():
    assert W._block_kind("", None) == "short_page"
    assert W._block_kind("<html>tiny</html>", 200) == "short_page"


def test_a8_single_arg_compat_matches_old_rule():
    """상태를 모를 때 예전 `_looks_blocked(html)` 가 막던 것은 전부 막는다."""
    def old(html):
        if not html or len(html) < 800:
            return True
        low = html[:4000].lower()
        return any(s in low for s in ("incapsula", "_incap_", "request unsuccessful",
                                      "access denied", "captcha-delivery",
                                      "just a moment"))
    access = "<html><body>Access Denied" + "x" * 900 + "</body></html>"
    dd = "<html><body><script src='https://captcha-delivery.com/x'></script>" \
         + "x" * 900 + "</body></html>"
    corpus = [NORMAL_PAGE, LS.LEAGUE_PAGE, TEAM_PAGE, JUST_A_MOMENT, INCAPSULA,
              access, dd, "", "<p>short</p>"]
    for html in corpus:
        if old(html):
            assert W._looks_blocked(html), html[:60]
    for html in (NORMAL_PAGE, LS.LEAGUE_PAGE, TEAM_PAGE):
        assert old(html) is False and W._looks_blocked(html) is False


# ==========================================================================
# B. get_html — 상태를 보존하고, 차단 화면을 돌려주지 않는다
# ==========================================================================
def test_b1_blocked_page_returns_empty_and_records_status():
    b = _browser([("England", (403, CF_BLOCK_PAGE))])
    h = _capture()
    try:
        got = b.get_html("https://www.whoscored.com/Regions/252/Tournaments/2/"
                         "England-Premier-League", wait_selector="table")
    finally:
        _release(h)
    assert got == ""
    assert b.last_status == 403
    assert b.last_block == "cloudflare"
    assert b.last_block_html == CF_BLOCK_PAGE


def test_b2_block_log_line_has_source_status_type_url_title():
    b = _browser([("England", (403, CF_BLOCK_PAGE))])
    h = _capture()
    try:
        b.get_html("https://www.whoscored.com/Regions/252/Tournaments/2/"
                   "England-Premier-League")
    finally:
        _release(h)
    lines = [ln for ln in h.lines if "차단 감지" in ln]
    assert len(lines) == 1, h.lines
    ln = lines[0]
    assert ln.startswith("[whoscored] 차단 감지"), ln
    for part in ("status=403", "type=cloudflare",
                 "url=https://www.whoscored.com/Regions/252",
                 "title=Attention Required! | Cloudflare"):
        assert part in ln, (part, ln)


def test_b3_normal_page_returned_unchanged():
    b = _browser([("England", (200, NORMAL_PAGE))])
    got = b.get_html("https://www.whoscored.com/Regions/252/Tournaments/2/"
                     "England-Premier-League", wait_selector="table")
    assert got == NORMAL_PAGE
    assert b.last_status == 200 and b.last_block == "" and b.last_block_html == ""


def test_b4_unknown_status_keeps_old_behaviour():
    """`goto()` 가 응답을 주지 않으면(None) 상태 없이 예전처럼 판정한다."""
    b = _browser([("x", (403, NORMAL_PAGE))], status_none=True)
    assert b.get_html("https://www.whoscored.com/x") == NORMAL_PAGE
    assert b.last_status is None
    b = _browser([("x", (403, INCAPSULA))], status_none=True)
    assert b.get_html("https://www.whoscored.com/x") == ""
    assert b.last_block == "incapsula"


def test_b5_state_resets_between_calls():
    b = _browser([("blocked", (403, CF_BLOCK_PAGE)), ("ok", (200, TEAM_PAGE))])
    h = _capture()
    try:
        assert b.get_html("https://www.whoscored.com/blocked") == ""
        assert b.get_html("https://www.whoscored.com/ok") == TEAM_PAGE
    finally:
        _release(h)
    assert b.last_status == 200 and b.last_block == "" and b.last_block_html == ""


def test_b6_goto_arguments_unchanged():
    """요청 방식은 그대로다 — 같은 주소, 같은 대기 조건."""
    b = _browser([("x", (200, TEAM_PAGE))])
    b.get_html("https://www.whoscored.com/x")
    assert b._page.gotos == [("https://www.whoscored.com/x", "domcontentloaded")]


def test_b7_get_raw_unchanged():
    """`get_raw` 는 판정 없이 상태와 본문을 그대로 준다 (점검 도구·FotMob)."""
    b = _browser([("x", (403, CF_BLOCK_PAGE))])
    assert b.get_raw("https://www.whoscored.com/x") == (403, CF_BLOCK_PAGE)


# ==========================================================================
# C. 다른 소스는 영향을 받지 않는다
# ==========================================================================
def test_c1_base_hook_ignores_status():
    """공용 기본값은 예전 `_is_blocked(html)` 그대로다 — 403 을 보지 않는다."""
    base = B.StealthBrowser({}, cache=None)
    assert base._block_reason(NORMAL_PAGE, 403) == ""
    assert base._block_reason(CF_BLOCK_PAGE, 403) == ""   # 기본 `_is_blocked` 는 False


def test_c2_fotmob_does_not_override_block_hooks():
    assert FotMobBrowser._block_reason is B.StealthBrowser._block_reason
    assert FotMobBrowser._is_blocked is B.StealthBrowser._is_blocked


def test_c3_base_page_passes_through_on_403():
    """다른 소스의 `get_html` 은 403 이어도 예전처럼 본문을 돌려준다."""
    base = B.StealthBrowser({}, cache=None)
    base.available, base.delay = True, 0.0
    base._page = FakePage([("x", (403, NORMAL_PAGE))])
    assert base.get_html("https://example.invalid/x") == NORMAL_PAGE
    assert base.last_status == 403 and base.last_block == ""


# ==========================================================================
# D. read_league — 차단 화면을 파싱하지 않고, 사유를 정확히 남긴다
# ==========================================================================
def _read_league(routes, cache=None):
    b = _browser(routes)
    h = _capture()
    try:
        out = W.read_league(b, load_settings(), "epl", TeamResolver(), cache=cache)
    finally:
        _release(h)
    return out, b, h.lines


def test_d1_blocked_league_is_not_parsed():
    cache = _Cache()
    out, b, lines = _read_league([("England", (403, CF_BLOCK_PAGE))], cache=cache)
    assert out == {}
    # 파서가 돌았다면 이 줄들이 나온다 — 예전의 오진이다
    for wrong in ("팀을 하나도 파싱하지 못함", "팀 링크가 없습니다", "JS 렌더링",
                  "팀 통계 탭 링크가"):
        assert not any(wrong in ln for ln in lines), (wrong, lines)
    # 팀 통계 탭을 찾으러 가지 않는다 — 요청은 리그 페이지 한 번뿐이다
    assert len(b._page.gotos) == 1, b._page.gotos


def test_d2_blocked_league_error_names_the_block():
    _, _, lines = _read_league([("England", (403, CF_BLOCK_PAGE))])
    err = [ln for ln in lines if ln.startswith("리그 페이지 수집 실패")]
    assert len(err) == 1, lines
    assert "epl" in err[0] and "type=cloudflare" in err[0] and "status=403" in err[0]


def test_d3_blocked_raw_page_kept_for_diagnosis():
    """차단 화면은 파싱하지 않지만 원본은 남긴다 (경고가 아니라 보관으로)."""
    cache = _Cache()
    _read_league([("England", (403, CF_BLOCK_PAGE))], cache=cache)
    assert cache.debug == [("whoscored", "blocked_league_epl", False, CF_BLOCK_PAGE)]
    assert cache.saved == {}                   # 빈 결과를 캐시에 넣지 않는다


def test_d4_blocked_stat_tab_is_not_parsed():
    """리그 페이지는 정상이고 팀 통계 탭만 막혀도 그 화면을 읽지 않는다."""
    out, _, lines = _read_league([("/teamstatistics/", (403, CF_BLOCK_PAGE)),
                                  ("England", (200, LS.LEAGUE_PAGE))])
    assert any("차단 감지" in ln and "type=cloudflare" in ln for ln in lines)
    assert any("팀 통계 탭을 받지 못했습니다" in ln for ln in lines)
    # 순위표는 그대로 살아 있다
    assert (LS._stats(out, "Manchester City").played, LS._stats(out, "Arsenal").points) \
        == (3, 9)
    assert LS._stats(out, "Arsenal").shots_pg is None


def test_d5_normal_collection_matches_existing_fixture():
    """정상 경로: 실제 `get_html` 을 거쳐도 기존 픽스처와 결과가 같다.

    기존 픽스처의 팀 통계 페이지는 800B 가 안 된다. 실제 `get_html` 은 예전부터
    그런 문서를 차단으로 봤으므로(짧은 문서 규칙 — 바꾸지 않았다) 주석으로
    실물 크기에 가깝게 채운다. 표 내용은 한 글자도 바꾸지 않는다.
    """
    league = LS.LEAGUE_PAGE
    stat = LS._page(LS.STAT_TABLE + "<!-- pad -->" * 80)
    assert len(league) >= 800 and len(stat) >= 800
    expected, _ = LS._run(league, stat)          # 기존 테스트의 흉내 브라우저
    for status_none in (False, True):
        b = _browser([("/teamstatistics/", (200, stat)), ("England", (200, league))],
                     status_none=status_none)
        got = W.read_league(b, load_settings(), "epl", TeamResolver(), cache=None)
        assert got == expected, status_none
    assert LS._stats(expected, "Arsenal").shots_pg == 13.7


def test_d6_team_page_block_returns_empty():
    b = _browser([("/teams/", (403, CF_BLOCK_PAGE))])
    h = _capture()
    try:
        got = W.read_team(b, load_settings(), "/teams/80/show/italy-ac-milan",
                          "AC Milan", TeamResolver(), cache=None)
    finally:
        _release(h)
    assert got == {}
    assert not any("아무것도 파싱하지 못함" in ln for ln in h.lines), h.lines


# ==========================================================================
# E. 우회를 만들지 않았다
# ==========================================================================
def test_e1_no_bypass_code():
    """차단을 알아보기만 한다 — 재시도·대기·다른 전송 방식이 늘지 않았다."""
    for rel in ("toto/sources/browser.py", "toto/sources/whoscored.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                for a in n.names}
        mods |= {n.module or "" for n in ast.walk(tree)
                 if isinstance(n, ast.ImportFrom)}
        for bad in ("requests", "urllib.request", "httpx", "cloudscraper",
                    "undetected_chromedriver", "playwright_stealth"):
            assert bad not in mods, (rel, bad)


def test_e2_block_detection_is_whoscored_specific():
    """상태를 판정에 쓰는 것은 후스코어드 하나뿐이다."""
    assert W.WhoScoredBrowser._block_reason is not B.StealthBrowser._block_reason
    assert W.WhoScoredBrowser.source == "whoscored"


# --------------------------------------------------------------------------
def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            print(f"  ERR  {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
