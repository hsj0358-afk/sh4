"""리포트 레이아웃 스모크 — 폰 폭에서 깨지지 않는가 (리팩터링 Phase 1).

리포트는 폰에서 열린다(§1-52 GitHub Pages · `--serve`). 지금까지 가로 넘침·
카드 밖 요소를 Phase 마다 사람이 Chromium 으로 재서 보고서에 적었다
(4-F · 4-E · 5-E2 · 6-F-7). 이 파일이 그 측정을 자동으로 한다.

리포트는 골든 테스트와 **같은 자식 프로세스**가 만든 것을 쓴다 — 여기서
따로 조립하면 골든이 고정한 것과 다른 HTML 을 재게 된다.

  데모 리포트 · 패널 fixture 리포트 (언제나)
  실물 재렌더 · 실물 패널 반영 리포트 (저장본·보관본이 있을 때만)

두 층이다.

  구조   14개 카드와 앵커 · 끊긴 `#` 링크 0 · 중복 id 0 · 외부 참조 0
         — 브라우저 없이 돈다
  브라우저  1200×760 · 768×1024 · 400×900, 접힘과 **전부 펼침** 두 상태에서
         가로 넘침 0 · 카드 밖으로 나간 요소 0 · JS 오류 0 · 외부 요청 0
         — Playwright·Chromium 이 없으면 SKIP (사유가 보인다)

값을 판단하지 않는다. 레이아웃만 본다.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import realdata                                                   # noqa: E402

VIEWPORTS = ((1200, 760), (768, 1024), (400, 900))
MATCHES = 14

_PASSED = _FAILED = _SKIPPED = 0
_TMP = tempfile.TemporaryDirectory(prefix="toto_mobile_")   # 종료 때 지워진다
_DOCS: dict = {}
_MEASURED: dict = {}


def check(name, fn):
    global _PASSED, _FAILED, _SKIPPED
    try:
        fn()
    except realdata.SkipTest as exc:
        _SKIPPED += 1
        print(f"  SKIP {name}: {exc}")
    except AssertionError as exc:
        _FAILED += 1
        print(f"  FAIL {name}: {exc}")
    except Exception as exc:                                # noqa: BLE001
        _FAILED += 1
        print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    else:
        _PASSED += 1
        print(f"  ok   {name}")


# ==========================================================================
# 리포트 — 골든 테스트의 emit 자식이 덤프한 것을 쓴다
# ==========================================================================
def _dump(script: str, *args: str) -> Path:
    out = Path(_TMP.name) / script
    env = dict(os.environ, PYTHONHASHSEED="0", TOTO_GOLDEN_DUMP=str(out))
    target = Path(_TMP.name) / f"{script}.json"
    proc = subprocess.run(
        [sys.executable, str(HERE / script), *args, str(target)],
        cwd=str(REPO), env=env, capture_output=True, timeout=900)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace")[-2000:]
        raise AssertionError(f"{script} 산출물 생성 실패:\n{tail}")
    return out


def docs() -> dict:
    """{이름: HTML 경로}."""
    if _DOCS:
        return _DOCS
    base = _dump("test_golden_regression.py", "--emit")
    _DOCS["demo"] = base / "demo" / "report.html"
    _DOCS["panel fixture"] = base / "panel" / "report.html"
    art = realdata.ARTIFACT_260052
    if art.exists():
        real = _dump("test_golden_real.py", "--emit-real", art.stem)
        root = real / "real" / art.stem
        _DOCS[f"real {art.stem}"] = root / "artifact" / "report.html"
        if (root / "panel" / "report.html").is_file():
            _DOCS[f"real {art.stem} panel"] = root / "panel" / "report.html"
    else:
        print(f"    · 실물 저장본 없음 — 데모·fixture 리포트만 잰다")
    return _DOCS


# ==========================================================================
# 구조 — 브라우저 없이
# ==========================================================================
_ID = re.compile(r'\sid="([^"]+)"')
_FRAG = re.compile(r'\shref="#([^"]*)"')
_EXTERNAL = re.compile(
    r'<(?:script|img|link|iframe|source|video|audio)\b[^>]*\s(?:src|href)='
    r'"(?:https?:)?//', re.I)


def test_s1_every_card_and_anchor_exists():
    from toto import render
    for name, path in docs().items():
        html = path.read_text(encoding="utf-8")
        ids = set(_ID.findall(html))
        cards = html.count('<article class="match"')
        assert cards == MATCHES, f"{name}: 카드 {cards}개"
        for no in range(1, MATCHES + 1):
            assert render.match_anchor(no) in ids, (name, no)
        assert render.OVERVIEW_ANCHOR in ids, name


def test_s2_no_broken_fragment_or_duplicate_id():
    for name, path in docs().items():
        html = path.read_text(encoding="utf-8")
        ids = _ID.findall(html)
        dup = sorted({i for i in ids if ids.count(i) > 1})
        assert not dup, f"{name}: 중복 id {dup[:5]}"
        broken = sorted({f for f in _FRAG.findall(html)
                         if f and f not in set(ids)})
        assert not broken, f"{name}: 끊긴 링크 {broken[:5]}"


def test_s3_no_external_reference():
    """자체 완결 HTML (§1-8). 폰·오프라인에서 여기에 달려 있다."""
    for name, path in docs().items():
        html = path.read_text(encoding="utf-8")
        hits = _EXTERNAL.findall(html)
        assert not hits, f"{name}: 외부 참조 {hits[:3]}"


# ==========================================================================
# 브라우저 — 폭 셋 × 접힘/펼침
# ==========================================================================
_JS = r"""
(openAll) => {
  if (openAll) document.querySelectorAll('details').forEach(d => d.open = true);
  const de = document.documentElement;
  const out = {overflow: de.scrollWidth - de.clientWidth, escapes: [],
               details: document.querySelectorAll('details').length};
  const clipped = (el, card) => {
    for (let p = el.parentElement; p && p !== card; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if (ox === 'auto' || ox === 'scroll' || ox === 'hidden') return true;
    }
    return false;
  };
  for (const card of document.querySelectorAll('article.match')) {
    const cr = card.getBoundingClientRect();
    for (const el of card.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      if (r.right <= cr.right + 1 && r.left >= cr.left - 1) continue;
      if (clipped(el, card)) continue;
      const cls = typeof el.className === 'string' && el.className
        ? '.' + el.className.split(' ')[0] : '';
      out.escapes.push(`${card.id} ${el.tagName.toLowerCase()}${cls} ` +
        `${Math.round(r.left - cr.left)}..${Math.round(r.right - cr.right)}`);
      if (out.escapes.length >= 10) return out;
    }
  }
  return out;
}
"""


def _launch(p):
    try:
        return p.chromium.launch()
    except Exception as first:                              # noqa: BLE001
        exe = Path("/opt/pw-browsers/chromium")
        if exe.exists():
            try:
                return p.chromium.launch(executable_path=str(exe))
            except Exception:                               # noqa: BLE001
                pass
        raise realdata.SkipTest(
            f"브라우저를 띄우지 못했습니다: {str(first).splitlines()[0]}")


def measured() -> dict:
    """{(문서, 폭, 펼침): {overflow, escapes, errors, external}}."""
    if _MEASURED:
        return _MEASURED
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise realdata.SkipTest("playwright 가 설치되어 있지 않습니다")
    targets = docs()
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            for name, path in targets.items():
                for width, height in VIEWPORTS:
                    page = browser.new_page(viewport={"width": width,
                                                      "height": height})
                    external, errors = [], []
                    page.on("pageerror", lambda e: errors.append(str(e)))

                    def route(r, ext=external):
                        if r.request.url.startswith(("file:", "data:",
                                                     "about:")):
                            r.continue_()
                        else:
                            ext.append(r.request.url)
                            r.abort()
                    page.route("**/*", route)
                    page.goto(path.as_uri(), wait_until="load")
                    for open_all in (False, True):
                        data = page.evaluate(_JS, open_all)
                        data["errors"] = list(errors)
                        data["external"] = list(external)
                        _MEASURED[(name, width, open_all)] = data
                    page.close()
        finally:
            browser.close()
    return _MEASURED


def _state(key) -> str:
    name, width, open_all = key
    return f"{name} @{width}px {'펼침' if open_all else '접힘'}"


def test_m1_no_horizontal_page_overflow():
    bad = [f"{_state(k)}: {v['overflow']}px"
           for k, v in measured().items() if v["overflow"] > 0]
    assert not bad, "가로 스크롤이 생겼다\n  " + "\n  ".join(bad)


def test_m2_nothing_escapes_its_card():
    """표는 자기 가로 스크롤(`.tablewrap`) 안에 있어야 하고 그 밖의 요소는
    카드 안에 있어야 한다 (4-F·4-E 실측 기준)."""
    bad = [f"{_state(k)}: {v['escapes'][:3]}"
           for k, v in measured().items() if v["escapes"]]
    assert not bad, "카드 밖으로 나간 요소\n  " + "\n  ".join(bad)


def test_m3_no_script_error_and_no_network():
    bad = [f"{_state(k)}: 오류 {v['errors'][:2]} · 외부 {v['external'][:2]}"
           for k, v in measured().items() if v["errors"] or v["external"]]
    assert not bad, "\n  ".join(bad)


def test_m4_details_actually_opened():
    """펼침 상태를 잰 것이 맞는지 — `<details>` 가 있는 문서에서 접힘/펼침
    측정이 둘 다 있다. 이것이 없으면 m1·m2 가 접힌 상태만 본 셈이다."""
    got = measured()
    for name in docs():
        for width, _h in VIEWPORTS:
            assert (name, width, False) in got and (name, width, True) in got
        assert got[(name, 400, True)]["details"] > 0, name


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과"
          + (f" · 건너뜀 {_SKIPPED}" if _SKIPPED else ""))
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
