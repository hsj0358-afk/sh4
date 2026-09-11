"""저장본 재렌더 진입점 회귀 테스트 (Phase 5-E3a).

**왜 필요했나.** 4-C 가 회차 분석을 `data/artifacts/<회차>.json` 으로 저장해
두는데, 그것을 읽는 입구가 `_panel_only` **하나뿐**이었고 그 입구는 패널 파일
인자에 묶여 있었다 (`cli.py` 의 `panel_file is not None`). 그래서 "자료는
그대로 두고 화면만 지금 코드로 다시 그린다" 를 할 방법이 없었다.

리포트 표현이 바뀔 때마다(4-G · 5-D) 그것을 실물 회차에서 확인하려면
재수집밖에 없었는데, **재수집은 다른 자료가 된다** — 순위표는 수집 시점
스냅샷이고 배당도 움직인다 (§1-1-7). 그러면 "화면만 바뀌었나" 를 물을 수가
없다.

고정하려는 것은 다섯이다.

  A. **저장본 하나로 렌더까지 간다.** JSON → `revive_report()` → 지금
     renderer → HTML.
  B. **수집하지 않는다.** `toto.sources` 가 import 조차 되지 않는다 —
     네 수집기가 전부 수집 구간 안에서 지연 import 되므로, 그 구간에 닿지
     않았다는 것이 곧 네트워크 0회의 증거다.
  C. **없는 것을 되살린 척하지 않는다.** 파일 없음 · 깨진 JSON · 최상위가
     객체가 아님 · 판 불일치 · 경기 0 — 다섯 다 사유와 함께 실패한다.
  D. **기존 실행 경로가 그대로다.** 수집 경로와 패널 전용 경로가 같은
     출력 규칙을 쓰고, 재렌더가 세 번째 사본을 만들지 않았다.
  E. **5-D 의 화면이 그대로 나온다.** 여기서 UI 를 다시 만들지 않는다.

pytest 없이도 돈다:  python tests/test_rerender.py
"""
from __future__ import annotations

import ast
import json
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import artifact, cli, fixtures                          # noqa: E402
from toto.analyze import run_all                                  # noqa: E402
from toto.models import Report                                    # noqa: E402
from toto.settings import Settings                                # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 수집 구간 안에서만 지연 import 되는 네 모듈. 재렌더가 여기 닿으면 안 된다.
COLLECTORS = ("betman", "fotmob", "pinnacle", "whoscored")


def _artifact(tmp: Path, round_id: str = "TESTRD") -> Path:
    """작은 저장본 하나. **실물 회차인 척하지 않는다** — 데모 픽스처다."""
    matches = fixtures.build_demo_matches()
    s = Settings()
    run_all(matches, s, season_matches=[])
    report = Report(round_id=round_id, generated_at="fixed", matches=matches)
    report.source_status = {"경기목록": "ok (샘플 · 실제 배당/성적 아님)"}
    status = artifact.save(report, outdir=tmp)
    assert status.startswith("ok"), status
    return tmp / f"{round_id}.json"


def _run(*argv: str) -> int:
    """CLI 를 부르되 그 로그는 삼킨다.

    루트 레벨만 올리는 것으로는 **안 된다** — `cli.main()` 이 맨 처음
    `_setup_logging()` 을 불러 레벨을 INFO 로 되돌리기 때문이다(§1-7-1 이
    "여러 번 불려도 레벨이 반영돼야 한다" 고 적어 둔 그 동작이다). 그래서
    그 호출만 잠깐 비우고 돌린다.

    **전역 `logging.disable` 을 쓰지 않는다** — `test_alias_table_loading.py`
    가 로그 문구를 검사하므로, 한 프로세스에서 함께 돌면 그 테스트가 조용히
    깨진다.
    """
    root, real = logging.getLogger(), cli._setup_logging
    before = root.level
    cli._setup_logging = lambda _verbose: None
    root.setLevel(logging.CRITICAL)
    try:
        return cli.main(list(argv))
    finally:
        cli._setup_logging = real
        root.setLevel(before)


# --------------------------------------------------------------------------
# A. 저장본 하나로 렌더까지
# --------------------------------------------------------------------------
def test_a1_artifact_renders_to_html():
    tmp = Path(tempfile.mkdtemp())
    src = _artifact(tmp)
    out = tmp / "out.html"
    assert _run("--rerender-artifact", str(src), "-o", str(out)) == 0
    html = out.read_text(encoding="utf-8")
    assert "<!doctype html>" in html.lower()
    assert html.count('<h3><span class="no">') == 14


def test_a2_the_saved_values_come_through():
    """분석값을 다시 만들지 않는다 — 저장된 것이 그대로 화면에 온다."""
    tmp = Path(tempfile.mkdtemp())
    src = _artifact(tmp)
    out = tmp / "out.html"
    _run("--rerender-artifact", str(src), "-o", str(out))
    html = out.read_text(encoding="utf-8")
    saved = json.loads(src.read_text(encoding="utf-8"))["report"]
    for match in saved["matches"]:
        assert match["home"]["display"] in html, match["no"]
        assert match["away"]["display"] in html, match["no"]
    assert saved["round_id"] in html


def test_a3_source_status_is_replayed_not_rebuilt():
    """상태 문자열은 **그때 적힌 것**이다. 지금 다시 판정하지 않는다."""
    tmp = Path(tempfile.mkdtemp())
    src = _artifact(tmp)
    out = tmp / "out.html"
    _run("--rerender-artifact", str(src), "-o", str(out))
    assert "ok (샘플 · 실제 배당/성적 아님)" in out.read_text(encoding="utf-8")


def test_a4_default_output_follows_the_report_convention():
    """출력 이름은 기존 규칙 그대로다 — 새 관례를 만들지 않는다."""
    tmp = Path(tempfile.mkdtemp())
    src = _artifact(tmp)
    s = Settings()
    name = s.output.get("filename", "toto_{round}.html").format(round="TESTRD")
    assert name == "toto_TESTRD.html", name


def test_a5_round_id_and_path_loaders_are_one_rule():
    """`load()` 가 `load_path()` 로 들어간다 — 읽는 규칙이 둘이 아니다."""
    tmp = Path(tempfile.mkdtemp())
    _artifact(tmp)
    by_round, _w1 = artifact.load("TESTRD", outdir=tmp)
    by_path, _w2 = artifact.load_path(tmp / "TESTRD.json")
    assert by_round is not None and by_path is not None
    assert [m.no for m in by_round.matches] == [m.no for m in by_path.matches]
    src = Path(artifact.__file__).read_text(encoding="utf-8")
    assert "return load_path(path_for(round_id, outdir))" in src


# --------------------------------------------------------------------------
# B. 수집하지 않는다
# --------------------------------------------------------------------------
def test_b1_no_collector_module_is_imported():
    """§B — 별도 프로세스에서 재렌더를 돌리고 `sys.modules` 를 본다.

    네 수집기는 전부 `cli.py` 의 수집 구간 안에서 지연 import 된다. 그
    구간에 닿지 않았다면 모듈이 로드될 수 없고, 로드되지 않았다면 네트워크
    요청도 있을 수 없다 — 이것이 "네트워크 0회" 의 직접 증거다.
    """
    tmp = Path(tempfile.mkdtemp())
    src = _artifact(tmp)
    out = tmp / "out.html"
    code = (
        "import sys, json\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from toto import cli\n"
        f"rc = cli.main(['--rerender-artifact', {str(src)!r}, '-o', {str(out)!r}])\n"
        "loaded = sorted(m for m in sys.modules if m.startswith('toto.sources'))\n"
        "print(json.dumps({'rc': rc, 'loaded': loaded}))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-800:]
    got = json.loads(proc.stdout.strip().splitlines()[-1])
    assert got["rc"] == 0, got
    assert got["loaded"] == [], got["loaded"]
    assert out.exists()


def test_b2_rerender_never_names_a_collector():
    """소스 코드에도 수집기가 나오지 않는다."""
    src = Path(cli.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_rerender")
    body = ast.unparse(ast.Module(body=fn.body[1:], type_ignores=[]))
    for name in COLLECTORS:
        assert name not in body, name
    for banned in ("sources", "Cache", "TeamResolver", "run_all", "requests"):
        assert banned not in body, banned


def test_b3_the_branch_sits_before_the_collection():
    """수집 구간 **앞에서** 갈라진다 — 한 줄이라도 뒤면 의미가 없다."""
    src = Path(cli.__file__).read_text(encoding="utf-8")
    branch = src.index("if args.rerender_artifact is not None:")
    for name in COLLECTORS:
        assert branch < src.index(f"from .sources import {name}"), name


def test_b4_no_cache_or_resolver_is_built():
    """캐시·팀 해석기도 만들지 않는다 — 저장본은 이미 해석이 끝난 값이다."""
    src = Path(cli.__file__).read_text(encoding="utf-8")
    branch = src.index("if args.rerender_artifact is not None:")
    assert branch < src.index("resolver = TeamResolver()")
    assert branch < src.index("cache = Cache(")


# --------------------------------------------------------------------------
# C. 없는 것을 되살린 척하지 않는다
# --------------------------------------------------------------------------
def _fails(text: str | None, name: str = "bad.json") -> str:
    """저장본을 만들어 재렌더를 돌리고 (종료코드, 사유) 를 본다."""
    tmp = Path(tempfile.mkdtemp())
    path = tmp / name
    if text is not None:
        path.write_text(text, encoding="utf-8")
    report, why = artifact.load_path(path)
    assert report is None, "되살리면 안 되는 것을 되살렸다"
    assert _run("--rerender-artifact", str(path)) == 1
    return why


def test_c1_missing_file():
    why = _fails(None, "없는파일.json")
    assert "없습니다" in why, why


def test_c2_malformed_json():
    why = _fails('{"artifact_version": 1, "rep')
    assert "읽지 못했습니다" in why, why


def test_c3_top_level_is_not_an_object():
    why = _fails("[1, 2, 3]")
    assert "최상위가 객체가 아님" in why, why


def test_c4_version_mismatch_is_not_guessed():
    """판이 다르면 **읽지 않는다** — 조용히 다른 것을 되살리지 않는다."""
    why = _fails('{"artifact_version": 99, "report": {"matches": []}}')
    assert "저장 형식이 다릅니다" in why, why


def test_c5_no_matches():
    why = _fails('{"artifact_version": 1, '
                 '"report": {"round_id": "X", "matches": []}}')
    assert "되살릴 경기가 없습니다" in why, why


def test_c6_a_failure_writes_no_html():
    """실패했는데 빈 리포트를 남기지 않는다."""
    tmp = Path(tempfile.mkdtemp())
    bad = tmp / "bad.json"
    bad.write_text("[1,2,3]", encoding="utf-8")
    out = tmp / "out.html"
    assert _run("--rerender-artifact", str(bad), "-o", str(out)) == 1
    assert not out.exists()


# --------------------------------------------------------------------------
# D. 기존 실행 경로가 그대로다
# --------------------------------------------------------------------------
def test_d1_one_write_path_for_all_three():
    """§1-8 — 세 경로가 같은 출력 규칙을 쓴다. 사본을 만들지 않았다."""
    src = Path(cli.__file__).read_text(encoding="utf-8")
    assert src.count("def _write_report(") == 1
    assert src.count('settings.output.get("filename"') == 1
    assert src.count("_write_report(report, args, settings") == 3


def test_d2_the_renderer_is_the_existing_one():
    """새 renderer 를 만들지 않았다 — `render_report` 하나뿐이다."""
    src = Path(cli.__file__).read_text(encoding="utf-8")
    assert src.count("render_report(report, settings)") == 1
    assert "from .render import render_report" in src


def test_d3_the_normal_run_is_untouched():
    """`--rerender-artifact` 없이는 이 분기에 들어가지 않는다."""
    args = cli.build_parser().parse_args(["--demo"])
    assert args.rerender_artifact is None
    args = cli.build_parser().parse_args(["--round", "260052"])
    assert args.rerender_artifact is None


def test_d4_the_flag_stands_alone():
    """회차 번호·패널 파일을 함께 주지 않아도 된다."""
    args = cli.build_parser().parse_args(["--rerender-artifact", "x.json"])
    assert args.round_id is None
    assert args.import_panel_result is None
    assert args.rerender_artifact == Path("x.json")


def test_d5_artifact_schema_is_untouched():
    """저장 형식을 건드리지 않았다 — 판도 버리는 칸도 그대로다."""
    assert artifact.ARTIFACT_VERSION == 1
    assert artifact.DROPPED == ("shot_aggregates", "shot_matches",
                                "opponent_matches")
    assert artifact.FILENAME == "{round}.json"


# --------------------------------------------------------------------------
# E. 5-D 의 화면이 그대로 나온다
# --------------------------------------------------------------------------
def _rendered() -> str:
    tmp = Path(tempfile.mkdtemp())
    src = _artifact(tmp)
    out = tmp / "out.html"
    _run("--rerender-artifact", str(src), "-o", str(out))
    return out.read_text(encoding="utf-8")


def test_e1_summary_block_stays_removed():
    assert "요약 — 이 경기에서 지금까지 나온 것" not in _rendered()


def test_e2_percentile_cells_have_no_prefix():
    html = _rendered()
    assert not re.findall(r"상위\s*\d+\s*%", html)
    assert re.search(r"<small> \d+%</small>", html), "백분위 값이 사라졌다"


def test_e3_lower_is_better_axis_is_reversed():
    """5-D 의 축 반전이 이 경로에서도 그대로다."""
    html = _rendered()
    assert "축을 반대로" in html
    assert "오른쪽이 그 지표에서 더 좋은 값" in html
    assert "오른쪽 끝이 그 줄의 큰 값" not in html


def test_e4_radar_keeps_its_meaning():
    html = _rendered()
    assert html.count('aria-label="리그 내 위치 레이더 차트"') == 14
    assert html.count("<polygon") == 28
    assert "바깥쪽일수록 상위" in html


def test_e5_the_report_is_still_self_contained():
    html = _rendered()
    for bad in ("http://", "https://", "<script src", "<iframe", "url("):
        assert bad not in html, bad


def test_e6_rerender_does_not_touch_the_renderer():
    """이 Phase 에서 UI 를 다시 만들지 않았다."""
    src = Path(cli.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_rerender")
    body = ast.unparse(ast.Module(body=fn.body[1:], type_ignores=[]))
    for banned in ("<div", "<p ", "상위", "요약", "charts", "esc("):
        assert banned not in body, banned


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
