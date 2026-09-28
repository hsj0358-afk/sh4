"""PC 원본 ↔ 웹 리포트 일치 검증 도구 (`tools/verify_web_report.py`).

이 스위트가 지키는 것.

  1. 바이트가 같으면 PASS
  2. 줄바꿈(CRLF↔LF)·BOM 만 다르면 SHA 가 달라도 PASS — B 로 보고한다
  3. 숫자 표기만 다르면("4.00"/"4.0") PASS — 값으로 비교한다
  4. 배포용 head·본문 덧붙임(meta·style·script·안내 줄)은 PASS — A/B 로 보고한다
  5. 수·팀·스코어·분석가 문장·사회자 문장·Evidence ID·경기 수·순서가
     바뀌면 FAIL — 경기 번호와 원본/웹 값을 함께 적는다
  6. 접힌 영역(<details>) 안의 값도 비교한다
  7. 원본 자료(Panel Result)와 HTML 이 어긋나면 FAIL
  8. 입력 파일을 바꾸지 않고, 분석 모듈을 import 하지 않는다

픽스처는 실제 렌더러로 만든 패널 리포트 한 장(`test_pages_publish.Round`)이다.
임시 폴더는 테스트가 끝나면 지운다.

    python tests/test_verify_web_report.py
"""
from __future__ import annotations

import ast
import atexit
import contextlib
import io
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import verify_web_report as V                               # noqa: E402

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "verify_web_report.py"
ROUND = "990052"

_CREATED: list[Path] = []
_FIXTURE: dict = {}


def tmpdir() -> Path:
    path = Path(tempfile.mkdtemp(prefix="toto_verify_test_"))
    _CREATED.append(path)
    return path


def cleanup_tmpdirs() -> None:
    while _CREATED:
        shutil.rmtree(_CREATED.pop(), ignore_errors=True)


def _cleanup_all() -> None:
    cleanup_tmpdirs()
    base = _FIXTURE.pop("base", None)
    if base is not None:
        shutil.rmtree(base, ignore_errors=True)


def teardown_function(function):
    cleanup_tmpdirs()


atexit.register(_cleanup_all)


def fixture() -> tuple[str, Path]:
    """(패널이 붙은 실제 렌더 HTML, Panel Result 가 있는 base). 한 번만 만든다."""
    if "html" not in _FIXTURE:
        import test_pages_publish as T
        base = Path(tempfile.mkdtemp(prefix="toto_verify_base_"))
        _FIXTURE["base"] = base
        _FIXTURE["html"] = T.Round(ROUND, base).html()
        T.cleanup_tmpdirs()
    return _FIXTURE["html"], _FIXTURE["base"]


def run_tool(original: str | bytes, web: str | bytes, *extra) -> tuple[int, str]:
    d = tmpdir()
    po, pw = d / f"toto_{ROUND}.html", d / "web.html"
    po.write_bytes(original.encode("utf-8") if isinstance(original, str) else original)
    pw.write_bytes(web.encode("utf-8") if isinstance(web, str) else web)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = V.run(V.build_parser().parse_args(
            [ROUND, "--original", str(po), "--web", str(pw), "--no-browser",
             "--no-source", *extra]))
    return rc, buf.getvalue()


def line(out: str, name: str) -> str:
    return next(l for l in out.splitlines() if l.startswith(name + ":"))


def once(text: str, old: str, new: str) -> str:
    assert old in text, old
    return text.replace(old, new, 1)


def card(html: str, no: int) -> tuple[int, int]:
    a = html.index(f'id="match-{no:02d}"')
    nxt = html.find(f'id="match-{no + 1:02d}"', a)
    return a, (nxt if nxt != -1 else len(html))


# ==========================================================================
# 1~4. 같다고 봐야 하는 것
# ==========================================================================
def test_1_identical_is_pass():
    html, _ = fixture()
    rc, out = run_tool(html, html)
    assert rc == 0, out
    assert "SHA256: 일치" in out and "최종 결과: PASS" in out
    assert "[차이]\n없음" in out
    for n in range(1, 15):
        assert f"{n}경기: PASS" in out


def test_2_newline_and_bom_only_is_pass_but_reported():
    html, _ = fixture()
    web = html.encode("utf-8")
    original = b"\xef\xbb\xbf" + web.replace(b"\n", b"\r\n")
    rc, out = run_tool(original, web)
    assert rc == 0, out
    assert "SHA256: 다름" in out
    assert "줄바꿈·BOM 을 걷은 뒤: 일치" in out
    assert "B. 배포용 HTML 구조 차이: 줄바꿈(CRLF↔LF)·BOM 만 다름" in out
    assert "A. 표현/레이아웃" not in out, out     # <style> 해시가 줄바꿈에 흔들리지 않는다


def test_3_number_format_only_is_pass():
    html, _ = fixture()
    m = re.search(r'<td class="num">(\d+)\.(\d)%</td>', html)
    web = once(html, m.group(0), f'<td class="num">{m.group(1)}.{m.group(2)}0%</td>')
    rc, out = run_tool(html, web)
    assert rc == 0, out
    assert "숫자 표기만 다른 곳: 1개" in out


def test_4_deploy_wrapper_is_pass():
    html, _ = fixture()
    web = once(html, "<title>", '<meta name="robots" content="noindex">'
               "<style>@media(max-width:400px){body{font-size:14px}}</style>"
               "<script>/* analytics */</script><title>")
    web = once(web, "<body>", '<body><nav class="deploy">목록으로</nav>')
    rc, out = run_tool(html, web)
    assert rc == 0, out
    assert "B. 배포용 HTML 구조 차이: <meta> 가 다름" in out
    assert "B. 배포용 HTML 구조 차이: <script> 가 다름" in out
    assert "A. 표현/레이아웃 차이: <style> 가 다름" in out
    assert "B. 배포용 HTML 구조 차이: 웹에만 있음" in out and "목록으로" in out


# ==========================================================================
# 5. 달라진 내용 — FAIL 과 위치
# ==========================================================================
def test_5a_market_value_change_fails_with_values():
    html, _ = fixture()
    a, b = card(html, 3)
    m = re.search(r'<td class="num">(\d+\.\d)%</td>', html[a:b])
    old = m.group(1)
    new = f"{float(old) + 0.2:.1f}"
    web = html[:a] + html[a:b].replace(m.group(0), f'<td class="num">{new}%</td>', 1) \
        + html[b:]
    rc, out = run_tool(html, web)
    assert rc == 1, out
    assert line(out, "시장 기준값") == "시장 기준값: FAIL"
    assert "3경기: FAIL" in out and "1경기: PASS" in out
    assert f"PC 원본: {old}" in out and f"웹 리포트: {new}" in out
    assert "분류: C. 실제 데이터 차이" in out
    assert "판단: 웹 리포트가 PC 원본과 일치하지 않음" in out


def test_5b_analyst_sentence_change_is_analysis_difference():
    html, _ = fixture()
    m = re.search(r'<div class="traits"><div><h5>[^<]+</h5><p class="pscore">[^<]*</p>'
                  r'<p class="ptext">([^<]{8,})</p>', html)
    web = once(html, m.group(1), m.group(1) + " 그리고 다른 결론")
    rc, out = run_tool(html, web)
    assert rc == 1, out
    assert line(out, "분석가 의견") == "분석가 의견: FAIL"
    assert "분류: D. 실제 분석 내용 차이" in out


def test_5c_score_change_fails():
    html, _ = fixture()
    m = re.search(r'<p class="mscore">(\d+) : (\d+)</p>', html)
    web = once(html, m.group(0), f'<p class="mscore">{m.group(1)} : {int(m.group(2)) + 1}</p>')
    rc, out = run_tool(html, web)
    assert rc == 1, out
    assert line(out, "예측 스코어") == "예측 스코어: FAIL"
    assert f"PC 원본: {m.group(1)} : {m.group(2)}" in out


def test_5d_team_name_change_fails():
    html, _ = fixture()
    a, b = card(html, 5)
    h3 = re.search(r"<h3>.*?</h3>", html[a:b]).group(0)
    team = re.search(r"</span>([^<]+?) <span", h3).group(1)
    new_h3 = h3.replace(team, team + "FC", 1)
    web = html[:a] + html[a:b].replace(h3, new_h3, 1) + html[b:]
    rc, out = run_tool(html, web)
    assert rc == 1, out
    assert line(out, "홈팀/원정팀") == "홈팀/원정팀: FAIL"
    assert "5경기: FAIL" in out and f"{team}FC" in out


def test_5e_moderator_sentence_change_is_analysis_difference():
    html, base = fixture()
    import json
    pr = json.loads((base / "panel_results" / f"{ROUND}_panel_result.json")
                    .read_text(encoding="utf-8"))
    conclusion = next(m["moderator"]["conclusion"] for m in pr["matches"]
                      if isinstance(m.get("moderator"), dict)
                      and m["moderator"].get("conclusion"))
    import html as H
    esc = H.escape(conclusion, quote=True)
    web = once(html, esc, esc + " 추가된 문장")
    rc, out = run_tool(html, web)
    assert rc == 1, out
    assert line(out, "사회자 종합") == "사회자 종합: FAIL"
    assert "분류: D. 실제 분석 내용 차이" in out


def test_5f_evidence_id_change_fails():
    html, _ = fixture()
    m = re.search(r"인용한 근거 (E\d+)", html)
    new = "E" + str(int(m.group(1)[1:]) + 90).zfill(3)
    web = once(html, m.group(0), f"인용한 근거 {new}")
    rc, out = run_tool(html, web)
    assert rc == 1, out
    assert line(out, "Evidence ID") == "Evidence ID: FAIL"


def test_5g_missing_card_fails():
    html, _ = fixture()
    a = html.index('<article class="match" id="match-14"')
    b = html.index("</article>", a) + len("</article>")
    rc, out = run_tool(html, html[:a] + html[b:])
    assert rc == 1, out
    assert line(out, "경기 수") == "경기 수: FAIL"
    assert "상세 14 · 요약 14" in out and "상세 13 · 요약 14" in out
    assert "14경기: FAIL" in out


def test_5h_swapped_order_fails():
    html, _ = fixture()
    a1, b1 = card(html, 1)
    a2, b2 = card(html, 2)
    s1 = html.rfind("<article", 0, a1)
    s2 = html.rfind("<article", 0, a2)
    e2 = html.rfind("<article", 0, b2) if b2 < len(html) else html.index("</article>", a2) + 10
    web = html[:s1] + html[s2:e2] + html[s1:s2] + html[e2:]
    rc, out = run_tool(html, web)
    assert rc == 1, out
    assert line(out, "경기 순서") == "경기 순서: FAIL"


def test_5i_number_value_is_compared_by_value_not_string():
    toks = V.tokenize("1.20 1.2 −0.35 -0.35 E001 E1 2-1 1,234 18.7%")
    nums = [t.value for t in toks if t.kind == "n"]
    assert nums[0] == nums[1]                            # 1.20 = 1.2
    assert nums[2] == nums[3]                            # 유니코드 마이너스
    ids = [t.value for t in toks if t.kind == "t" and t.value.startswith("E")]
    assert ids == ["E001", "E1"]                         # 식별자는 수로 읽지 않는다
    assert [t.raw for t in toks[6:9]] == ["2", "-", "1"]  # 스코어의 - 는 부호가 아니다
    assert 1234 in nums


# ==========================================================================
# 6. 접힌 영역
# ==========================================================================
def test_6_value_inside_collapsed_details_is_compared():
    html, _ = fixture()
    a, b = card(html, 2)
    d = html.index("<details", a)
    assert d < b
    m = re.search(r'<td class="num">(\d+\.\d+)', html[d:b])
    old = m.group(1)
    web = html[:d] + html[d:b].replace(m.group(0), f'<td class="num">{old}9', 1) + html[b:]
    rc, out = run_tool(html, web)
    assert rc == 1, out
    assert "2경기: FAIL" in out and f"PC 원본: {old}" in out


# ==========================================================================
# 7. 원본 자료 ↔ HTML
# ==========================================================================
def _source(html_text: str) -> dict:
    _, base = fixture()
    docs = [V.load_doc("PC 원본", html_text.encode("utf-8"))]
    return V.source_stage(ROUND, docs, base=base)


def test_7a_source_data_matches_rendered_html():
    html, _ = fixture()
    res = _source(html)
    assert res["status"] == "PASS", [vars(f) for f in res["findings"]]
    assert any("Panel Result" in c for c in res["checked"])


def test_7b_html_that_disagrees_with_panel_result_fails():
    html, _ = fixture()
    m = re.search(r'<p class="pscore">예상 스코어 (\d+) : (\d+)</p>', html)
    bad = once(html, m.group(0),
               f'<p class="pscore">예상 스코어 {m.group(1)} : {int(m.group(2)) + 1}</p>')
    res = _source(bad)
    assert res["status"] == "FAIL"
    assert any(f.what.startswith("분석가 예상 스코어") for f in res["findings"])


def test_7c_no_source_files_is_skip_not_fail():
    html, _ = fixture()
    res = V.source_stage(ROUND, [V.load_doc("x", html.encode("utf-8"))],
                         base=tmpdir())
    assert res["status"] == "SKIP"


# ==========================================================================
# 8. 읽기만 한다 · 독립 도구다
# ==========================================================================
def test_8a_inputs_are_not_modified():
    html, _ = fixture()
    d = tmpdir()
    po, pw = d / f"toto_{ROUND}.html", d / "web.html"
    po.write_text(html, encoding="utf-8")
    pw.write_text(html, encoding="utf-8")
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in (po, pw)}
    with contextlib.redirect_stdout(io.StringIO()):
        V.run(V.build_parser().parse_args(
            [ROUND, "--original", str(po), "--web", str(pw), "--no-browser",
             "--no-source"]))
    assert {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in (po, pw)} == before
    assert sorted(x.name for x in d.iterdir()) == ["toto_990052.html", "web.html"]


def test_8b_tool_does_not_import_analysis_logic():
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            names |= {n.module} | {f"{n.module}.{a.name}" for a in n.names}
        elif isinstance(n, ast.Import):
            names |= {a.name for a in n.names}
    toto = {x for x in names if x.startswith("toto")}
    assert toto <= {"toto", "toto.pagespublish", "toto.settings", "toto.panel",
                    "toto.panel.ROLE_KO", "toto.artifact", "toto.cli",
                    "toto.cli.safe_console"}, toto
    for bad in ("render", "analysis", "analyze", "predict", "evidence", "xpts"):
        assert not any(bad in x for x in toto), bad


def test_8c_git_is_read_only():
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    firsts = {n.args[0].elts[0].value for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "_git" and isinstance(n.args[0], ast.List)}
    assert firsts == {"show", "ls-tree"}, firsts


def test_8d_missing_web_file_exits_2():
    html, _ = fixture()
    d = tmpdir()
    po = d / f"toto_{ROUND}.html"
    po.write_text(html, encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        rc = V.run(V.build_parser().parse_args(
            [ROUND, "--original", str(po), "--web", str(d / "none.html")]))
    assert rc == 2


def test_8e_latest_round_is_picked_from_both_sides():
    d = tmpdir()
    rep, pages = d / "reports", d / "pages" / "reports"
    rep.mkdir()
    pages.mkdir(parents=True)
    for n in ("toto_260050.html", "toto_260052.html", "toto_260054.html",
              "toto_DEMO.html", "toto_260052_5E3b.html"):
        rep.joinpath(n).write_text("x", encoding="utf-8")
    for n in ("toto_260050.html", "toto_260052.html"):
        pages.joinpath(n).write_text("x", encoding="utf-8")
    assert V.dir_rounds(rep) & V.dir_rounds(pages) == {"260050", "260052"}
    assert max(V.dir_rounds(rep) & V.dir_rounds(pages), key=int) == "260052"


# ==========================================================================
# 브라우저 (Playwright 가 있을 때만)
# ==========================================================================
def test_9_browser_stage_sees_collapsed_change():
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return
    html, _ = fixture()
    a, b = card(html, 2)
    d = html.index("<details", a)
    m = re.search(r'<td class="num">(\d+\.\d+)', html[d:b])
    web = html[:d] + html[d:b].replace(m.group(0), f'<td class="num">{m.group(1)}9', 1) \
        + html[b:]
    res = V.browser_stage(html.encode("utf-8"), web.encode("utf-8"), widths=(400,))
    if res["status"] == "SKIP":
        return
    assert res["status"] == "FAIL"
    assert any(f.match == 2 for f in res["findings"])
    same = V.browser_stage(html.encode("utf-8"), html.encode("utf-8"), widths=(400,))
    assert same["status"] == "PASS"


# --------------------------------------------------------------------------
def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    try:
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
            finally:
                cleanup_tmpdirs()
    finally:
        _cleanup_all()
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
