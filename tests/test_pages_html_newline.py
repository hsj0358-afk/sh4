"""게시용 최종 HTML 의 줄바꿈 — 윈도우에서도 LF.

`reports/toto_<회차>.html` 을 쓰는 곳은 `cli._write_report()` 하나다. 그 파일이
GitHub Pages 에 올라가는 최종 HTML 이고, `pagespublish.copy_final()` 은 바이트를
그대로 복사한다. 그런데 `pagespublish.check_final_html()` 은 파일 바이트를
그대로 풀어 패널 CSS(`render.PANEL_CSS`, LF 6개)를 찾는다.

writer 가 텍스트 모드 기본값으로 쓰던 동안, 윈도우는 `\\n` 을 `\\r\\n` 으로
바꿔 썼다. 그래서 패널이 붙은 리포트가 "패널이 붙지 않은 리포트입니다" 로
거부됐다. PC 에서 재현됐다: `CRLF 6` 과 그 메시지.

고친 자리는 writer 다 (`newline="\\n"`). 검사는 그대로다. 이 스위트는 윈도우
텍스트 모드를 흉내 내 리눅스에서도 그 계약을 본다. 흉내는 `open` 이
`newline` 을 받지 않았을 때만 `\\r\\n` 을 쓰게 하는 것이고, 제품 코드는
바꾸지 않는다.

  A. 실제 writer 가 쓴 바이트 = 렌더한 글자의 UTF-8 그대로 (CRLF 0, LF 있음)
  B. 그 파일이 `check_final_html` 을 통과하고, 게시 복사본도 같은 바이트다
  C. 검사는 약해지지 않았다 — 같은 리포트라도 CRLF 판은 여전히 거부하고,
     패널 없는 판은 줄바꿈과 무관하게 거부한다

pytest 없이도 돈다:  python tests/test_pages_html_newline.py
"""
from __future__ import annotations

import contextlib
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import cli, pagespublish, render                      # noqa: E402

import test_pages_publish as PP                                 # noqa: E402
import test_panel_apply as TA                                   # noqa: E402
from test_canonical_bytes import windows_text_mode               # noqa: E402

CRLF = b"\r\n"
RID = "990061"                   # 저장소에 없는 회차 번호


def scratch() -> Path:
    return Path(tempfile.mkdtemp(prefix="toto_pages_nl_"))


def modes():
    """(이름, 문맥) — 이 OS 그대로, 그리고 윈도우 텍스트 모드 흉내."""
    return (("native", contextlib.nullcontext),
            ("windows-text-mode", windows_text_mode))


def write_with_real_writer(report, dest: Path | None, settings=None) -> Path:
    """운영 writer 를 그대로 부른다. `dest` 가 없으면 기본 출력 경로다."""
    args = types.SimpleNamespace(output=dest)
    return cli._write_report(report, args, settings or TA.settings(), "test")


_ROUND = None


def panel_round() -> "PP.Round":
    global _ROUND
    if _ROUND is None:
        _ROUND = PP.Round(RID, scratch())
    return _ROUND


# ==========================================================================
# A. writer 의 바이트
# ==========================================================================
def test_a0_the_simulation_really_writes_crlf():
    """흉내가 실제로 CRLF 를 쓴다 — 아니면 아래 시험이 성립하지 않는다."""
    path = scratch() / "probe.html"
    with windows_text_mode():
        path.write_text("a\nb\n", encoding="utf-8")
    assert path.read_bytes() == b"a\r\nb\r\n"


def test_a1_writer_bytes_are_the_rendered_text_in_utf8():
    r = panel_round()
    want = render.render_report(r.with_panel, TA.settings()).encode("utf-8")
    assert b"\n" in want and CRLF not in want
    for name, ctx in modes():
        dest = scratch() / "reports" / f"toto_{RID}.html"
        with ctx():
            out = write_with_real_writer(r.with_panel, dest)
        raw = out.read_bytes()
        assert out == dest, (name, out)
        assert raw.count(CRLF) == 0, (name, raw.count(CRLF))
        assert raw.count(b"\n") > 0, name
        assert raw == want, name


def test_a2_default_output_path_is_lf_too():
    """`-o` 없이 쓰는 기본 경로(`settings.output_dir`)도 같은 계약이다."""
    r = panel_round()
    for name, ctx in modes():
        dev = scratch()
        settings = PP.dev_settings(dev)
        with ctx():
            out = write_with_real_writer(r.with_panel, None, settings)
        assert out == settings.output_dir / f"toto_{RID}.html", (name, out)
        assert out.read_bytes().count(CRLF) == 0, name


# ==========================================================================
# B. 검사 통과 · 게시 복사본
# ==========================================================================
def test_b1_real_writer_output_passes_the_panel_check():
    r = panel_round()
    for name, ctx in modes():
        dest = scratch() / "reports" / f"toto_{RID}.html"
        with ctx():
            out = write_with_real_writer(r.with_panel, dest)
        assert pagespublish.check_final_html(out, RID) == [], name


def test_b2_published_copy_keeps_the_lf_bytes():
    """`copy_final` 은 바이트를 그대로 옮긴다 — 게시 판도 LF 다."""
    r = panel_round()
    for name, ctx in modes():
        dest = scratch() / "reports" / f"toto_{RID}.html"
        pages = scratch() / "pages"
        with ctx():
            src = write_with_real_writer(r.with_panel, dest)
            copied = pagespublish.copy_final(src, pages, RID)
        assert copied.read_bytes() == src.read_bytes(), name
        assert copied.read_bytes().count(CRLF) == 0, name


# ==========================================================================
# C. 검사는 그대로 엄격하다
# ==========================================================================
def test_c1_crlf_copy_of_the_same_report_is_still_rejected():
    """canonical LF 검사를 유지했다 — CRLF 판은 지금도 거부된다.

    writer 가 LF 를 보장하므로 운영에서 이 판이 생기지 않는다. 그래도 누가
    다른 방법으로 CRLF 판을 그 자리에 두면 검사가 그것을 잡는다.
    """
    r = panel_round()
    dest = scratch() / "reports" / f"toto_{RID}.html"
    write_with_real_writer(r.with_panel, dest)
    dest.write_bytes(dest.read_bytes().replace(b"\n", CRLF))
    errors = pagespublish.check_final_html(dest, RID)
    assert any("패널이 붙지 않은 리포트" in e for e in errors), errors


def test_c2_panel_less_report_is_rejected_whatever_the_newlines():
    plain = render.render_report(TA.make_report(RID), TA.settings())
    assert render.PANEL_CSS not in plain
    for name, ctx in modes():
        dest = scratch() / "reports" / f"toto_{RID}.html"
        with ctx():
            write_with_real_writer(TA.make_report(RID), dest)
        errors = pagespublish.check_final_html(dest, RID)
        assert any("패널이 붙지 않은 리포트" in e for e in errors), (name, errors)


def test_c3_the_check_still_reads_raw_bytes():
    """검사가 바이트를 그대로 읽는다 — 줄바꿈을 걷는 읽기로 바뀌지 않았다."""
    import inspect
    body = inspect.getsource(pagespublish.check_final_html)
    assert "read_bytes()" in body and "read_text" not in body
    assert 'replace("\\r\\n"' not in body and "splitlines" not in body
    assert "render.PANEL_CSS not in text" in body


def main() -> int:
    # 직접 실행 러너는 `tests/_runner.py` 한 곳에 있다 (Phase 3 M13).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    sys.exit(main())
