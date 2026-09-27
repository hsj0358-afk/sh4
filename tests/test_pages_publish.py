"""GitHub Pages 게시 계층 (`--publish-round` · `toto/pagespublish.py`).

분석 작업 영역(`reports/`)과 공개 영역(gh-pages worktree)을 나눈다.
`--publish-round R` 은 **패널까지 끝난 최종 리포트 한 장**만 게시 영역의
`reports/` 로 복사하고 index.html 을 다시 만든다. git 쓰기 명령은 하지 않는다.

이 스위트가 지키는 것.

  1. 최종 HTML **하나만** 복사된다 — DEMO · 비교본 · 패널 자료 · md 제외
  2. index 는 게시 영역의 `toto_<숫자>.html` 만 싣는다
  3. 회차는 내림차순
  4. 이전 회차를 지우지 않고, 같은 회차는 그 파일만 바꾼다
  5. 없는 회차는 안전하게 실패한다 (아무것도 쓰지 않는다)
  6. 패널이 끝나지 않았으면 막는다 — **기존 판정**(`panelwork.workflow` ·
     반영 단계 `complete`)을 그대로 쓴다
  7. 기존 `publish()`(클라우드 복사)는 그대로다

그리고 경로 안전성 · 기본 경로 규칙 · git 쓰기 금지 · 수집 구간 앞 분기.

**저장소의 `reports/`·`panel_work/`·`panel_results/` 를 건드리지 않는다** —
임시 폴더에서만 돈다. 실제 모델도 네트워크도 쓰지 않는다.

    python tests/test_pages_publish.py
"""
from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import (cli, pagespublish as P, panelimport, panelpaste,  # noqa: E402
                  panelwork, publish, render)
from toto import settings as settings_mod                  # noqa: E402

import test_panel_apply as TA                              # noqa: E402

REPO = Path(__file__).resolve().parent.parent
HAS_GIT = shutil.which("git") is not None


# ==========================================================================
# 픽스처
# ==========================================================================
def tmpdir(prefix="toto_pages_test_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def make_pages(branch=P.PAGES_BRANCH) -> Path:
    """gh-pages 브랜치에 있는 **빈 git 저장소** (게시 worktree 흉내)."""
    pages = tmpdir("toto_pages_wt_")
    subprocess.run(["git", "init", "-q", "-b", branch, str(pages)], check=True)
    return pages


def dev_settings(dev: Path):
    s = settings_mod.load_settings()
    s.root = dev                     # output_dir = dev/reports
    return s


class Round:
    """한 회차의 **완료된** 패널 상태 — 실제 저장·조립·기록 함수로 만든다.

    순서는 운영과 같다: A → B → 3단계 자료 → C → 반영 기록. 회차 번호는
    저장소에 없는 99xxxx 를 쓴다 (`save_moderator_result` 는 자료 조립본의
    해시를 기본 자리 `reports/panel_<회차>/` 에서 읽는다).
    """

    def __init__(self, rid: str, base: Path, *, record=True, panel=True):
        self.rid, self.base = rid, base
        self.outdir = base.joinpath("export", rid)
        self.report = TA.make_report(rid)
        TA.seed(self.report, base, c=False)
        built = panelwork.build_completed_sheet(self.report, TA.settings(),
                                                base, self.outdir)
        assert built.success
        TA.seed(self.report, base, a=False, b=False, c=True)
        data, res = panelwork.assemble_panel_result(self.report, None, base)
        assert data is not None, res.issues
        self.panel_path = panelpaste.write_canonical(data, rid, base)
        if record:
            panelwork.record_applied(rid, self.panel_path,
                                     len(data["matches"]), base)
        self.with_panel = TA.make_report(rid)
        if panel:
            outcome = panelimport.run(self.panel_path, self.with_panel, None)
            assert panelimport.attach(outcome, self.with_panel)

    def html(self) -> str:
        return render.render_report(self.with_panel, TA.settings())

    def write(self, dev: Path, text: str | None = None) -> Path:
        path = dev.joinpath("reports", f"toto_{self.rid}.html")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.html() if text is None else text, encoding="utf-8")
        return path

    def publish(self, dev: Path, pages: Path, settings=None):
        return P.publish_round(self.rid, settings or dev_settings(dev), pages,
                               report=self.report, base=self.base,
                               outdir=self.outdir)


def tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)).replace(os.sep, "/")
                  for p in root.rglob("*") if ".git" not in p.parts)


# ==========================================================================
# 1. 최종 HTML 하나만
# ==========================================================================
def test_1_only_the_final_html_is_copied():
    base, dev, pages = tmpdir(), tmpdir(), make_pages()
    r = Round("990052", base)
    src = r.write(dev)
    rep = dev.joinpath("reports")
    rep.joinpath("toto_DEMO.html").write_text(r.html(), encoding="utf-8")
    rep.joinpath("toto_990052_5E3b.html").write_text(r.html(), encoding="utf-8")
    rep.joinpath("sample.md").write_text("# 내부", encoding="utf-8")
    rep.joinpath("panel_990052").mkdir()
    rep.joinpath("panel_990052", "03_사회자자료_완성.md").write_text(
        "x", encoding="utf-8")
    res = r.publish(dev, pages)
    assert res.ok, res.errors
    assert tree(pages) == [".nojekyll", "index.html", "reports",
                           "reports/toto_990052.html"], tree(pages)
    assert P.sha256_of(pages / "reports/toto_990052.html") == P.sha256_of(src)
    assert res.sha256 == P.sha256_of(src)


def test_1b_dev_reports_are_not_modified():
    base, dev, pages = tmpdir(), tmpdir(), make_pages()
    r = Round("990052", base)
    r.write(dev)
    before = {p: (p.stat().st_mtime_ns, P.sha256_of(p))
              for p in dev.rglob("*") if p.is_file()}
    assert r.publish(dev, pages).ok
    after = {p: (p.stat().st_mtime_ns, P.sha256_of(p))
             for p in dev.rglob("*") if p.is_file()}
    assert before == after


# ==========================================================================
# 2·3. index — 필터와 정렬
# ==========================================================================
def _index_with(names) -> tuple[list, str]:
    pages = tmpdir()
    pages.joinpath("reports").mkdir()
    for n in names:
        pages.joinpath("reports", n).write_text("<html></html>", encoding="utf-8")
    rounds, _ = P.write_index(pages)
    return rounds, pages.joinpath("index.html").read_text(encoding="utf-8")


def test_2_index_lists_only_numeric_rounds():
    rounds, html = _index_with(["toto_260052.html", "toto_260054.html",
                                "toto_DEMO.html", "toto_260054_ABC.html",
                                "toto_latest.html", "toto_manual.html"])
    assert rounds == ["260054", "260052"], rounds
    for bad in ("DEMO", "ABC", "latest", "manual"):
        assert bad not in html, bad
    assert html.count('class="round"') == 2


def test_2b_index_ignores_subfolders_and_other_files():
    pages = tmpdir()
    pages.joinpath("reports", "panel_260054").mkdir(parents=True)
    pages.joinpath("reports", "panel_260054", "toto_260054.html").write_text(
        "x", encoding="utf-8")
    pages.joinpath("reports", "toto_260050.html.tmp").write_text("x",
                                                                encoding="utf-8")
    pages.joinpath("reports", "260052_경기자료.md").write_text("x",
                                                             encoding="utf-8")
    assert P.published_rounds(pages) == []


def test_3_rounds_are_descending():
    rounds, html = _index_with(["toto_260050.html", "toto_260054.html",
                                "toto_260052.html"])
    assert rounds == ["260054", "260052", "260050"]
    pos = [html.index(f"reports/toto_{r}.html") for r in rounds]
    assert pos == sorted(pos)


def test_3b_numeric_not_lexical_order():
    rounds, _ = _index_with(["toto_99999.html", "toto_100000.html"])
    assert rounds == ["100000", "99999"]


def test_3c_index_is_static_and_mobile_ready():
    _, html = _index_with(["toto_260052.html"])
    low = html.lower()
    assert low.startswith("<!doctype html")
    assert '<meta name="viewport" content="width=device-width' in html
    assert f"<title>{P.INDEX_TITLE}</title>" in html
    for bad in ("<script", "http://", "https://", "<link", "@import", "url("):
        assert bad not in low, bad
    assert 'href="reports/toto_260052.html"' in html
    assert "260052회차" in html


def test_3d_empty_state():
    rounds, html = _index_with([])
    assert rounds == []
    assert "아직 게시된 리포트가 없습니다" in html
    assert 'class="round"' not in html


# ==========================================================================
# 4. 이전 회차 보존 · 같은 회차 교체
# ==========================================================================
def test_4_previous_rounds_are_kept():
    base, dev, pages = tmpdir(), tmpdir(), make_pages()
    r1, r2 = Round("990052", base), Round("990054", base)
    r1.write(dev)
    assert r1.publish(dev, pages).ok
    r2.write(dev)
    res = r2.publish(dev, pages)
    assert res.ok, res.errors
    assert res.rounds == ["990054", "990052"]
    assert tree(pages) == [".nojekyll", "index.html", "reports",
                           "reports/toto_990052.html",
                           "reports/toto_990054.html"]


def test_4b_republish_replaces_only_that_round():
    base, dev, pages = tmpdir(), tmpdir(), make_pages()
    r1, r2 = Round("990052", base), Round("990054", base)
    r1.write(dev)
    r2.write(dev)
    assert r1.publish(dev, pages).ok and r2.publish(dev, pages).ok
    keep = P.sha256_of(pages / "reports/toto_990054.html")
    new = r1.html().replace("</body>", "<!-- 다시 렌더 --></body>")
    src = r1.write(dev, new)
    assert r1.publish(dev, pages).ok
    assert P.sha256_of(pages / "reports/toto_990052.html") == P.sha256_of(src)
    assert P.sha256_of(pages / "reports/toto_990054.html") == keep


# ==========================================================================
# 5. 없는 회차 · 잘못된 회차
# ==========================================================================
def test_5_missing_report_fails_and_writes_nothing():
    base, dev, pages = tmpdir(), tmpdir(), make_pages()
    r = Round("990052", base)                   # 패널은 끝났지만 HTML 이 없다
    res = r.publish(dev, pages)
    assert not res.ok
    assert any("최종 리포트가 없습니다" in e for e in res.errors), res.errors
    assert tree(pages) == []


def test_5b_cli_unknown_round_exits_nonzero():
    pages = make_pages()
    rc = cli.main(["--publish-round", "999999", "--pages-dir", str(pages)])
    assert rc == 1
    assert tree(pages) == []


def test_5c_non_numeric_round_is_rejected_before_any_path():
    s = dev_settings(tmpdir())
    for bad in ("DEMO", "latest", "manual", "../260052", "260052/../x",
                "260052_5E3b", ""):
        res = P.publish_round(bad, s, make_pages())
        assert not res.ok and res.source is None, bad
        assert "숫자" in res.errors[0]


# ==========================================================================
# 6. 패널 미완료 차단 — 기존 판정 그대로
# ==========================================================================
def _blocked(res, needle):
    assert not res.ok
    assert any(needle in e for e in res.errors), res.errors


def test_6_moderator_only_apply_is_blocked():
    """반영 기록이 없는 Panel Result(사회자 전용 붙여넣기·옛 파일)는 막는다.
    `workflow().done` 은 참이다 — 그래서 반영 단계의 `complete` 를 본다."""
    base, dev, pages = tmpdir(), tmpdir(), make_pages()
    r = Round("990052", base, record=False)
    r.write(dev)
    wf = panelwork.workflow(r.rid, base=base, outdir=r.outdir, report=r.report,
                            settings=TA.settings())
    assert wf.done                               # 기존 판정은 '끝났다'
    _blocked(r.publish(dev, pages), "기록이 없습니다")
    assert tree(pages) == []


def test_6b_missing_analyst_checkpoint_is_blocked():
    base, dev, pages = tmpdir(), tmpdir(), make_pages()
    r = Round("990052", base)
    r.write(dev)
    panelwork.path_for(r.rid, TA.DA, base).unlink()
    _blocked(r.publish(dev, pages), "1단계")
    assert tree(pages) == []


def test_6c_changed_checkpoint_after_apply_is_blocked():
    """반영 뒤에 B 가 바뀌면 반영 기록이 낡는다 (6-F-12 의존성 전파)."""
    base, dev, pages = tmpdir(), tmpdir(), make_pages()
    r = Round("990052", base)
    r.write(dev)
    rows = TA.b_rows(r.report)
    rows[0]["summary"] = "바뀐 요약"
    assert panelwork.save_stage(TA.dump(rows), TA.MU, r.report, base).success
    res = r.publish(dev, pages)
    assert not res.ok, "낡은 반영을 게시했다"
    assert tree(pages) == []


def test_6d_panel_less_render_is_blocked():
    """[1] 재수집·재렌더가 최종판을 패널 없는 판으로 덮어쓴 경우."""
    base, dev, pages = tmpdir(), tmpdir(), make_pages()
    r = Round("990052", base)
    plain = render.render_report(TA.make_report(r.rid), TA.settings())
    assert render.PANEL_CSS not in plain
    r.write(dev, plain)
    _blocked(r.publish(dev, pages), "패널이 붙지 않은 리포트")
    assert tree(pages) == []


def test_6e_report_older_than_panel_result_is_blocked():
    base, dev, pages = tmpdir(), tmpdir(), make_pages()
    r = Round("990052", base)
    src = r.write(dev)
    old = r.panel_path.stat().st_mtime - 60
    os.utime(src, (old, old))
    _blocked(r.publish(dev, pages), "오래됐습니다")


def test_6f_empty_or_non_html_is_blocked():
    base = tmpdir()
    r = Round("990052", base)
    for text, needle in (("", "비어"), ("hello", "doctype"),
                         ("<!doctype html><html><body></body></html>", "제목")):
        dev, pages = tmpdir(), make_pages()
        r.write(dev, text)
        _blocked(r.publish(dev, pages), needle)
        assert tree(pages) == []


def test_6g_missing_artifact_blocks_through_real_loader():
    """회차 저장본이 없으면 패널을 확인할 수 없다 — 게시하지 않는다."""
    dev, pages = tmpdir(), make_pages()
    res = P.publish_round("999999", dev_settings(dev), pages)
    _blocked(res, "회차 저장본을 읽지 못해")


# ==========================================================================
# 7. 기존 publish() 는 그대로
# ==========================================================================
def test_7_existing_cloud_publish_unchanged():
    dev, target = tmpdir(), tmpdir()
    src = dev.joinpath("toto_260052.html")
    src.write_text("<!doctype html><html></html>", encoding="utf-8")
    s = settings_mod.load_settings()
    s.output = dict(s.output, copy_to=[str(target)], latest_name="최신.html")
    done = publish.publish(src, s)
    assert done == [target / "toto_260052.html"]
    assert sorted(p.name for p in target.iterdir()) == ["toto_260052.html",
                                                        "최신.html"]


def test_7b_cloud_publish_still_called_only_after_collection():
    tree_ = ast.parse(REPO.joinpath("toto/cli.py").read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree_) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "publish"]
    assert len(calls) == 1
    fn = next(n for n in tree_.body if isinstance(n, ast.FunctionDef)
              and n.name == "_publish_round")
    imported = {a.name for n in ast.walk(fn)
                if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    assert imported == {"pagespublish"}, imported


def _imports(text: str) -> set:
    out = set()
    for n in ast.walk(ast.parse(text)):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            out |= {n.module or ""} | {a.name for a in n.names}
    return out


def test_7c_modules_do_not_know_each_other():
    text = REPO.joinpath("toto/pagespublish.py").read_text(encoding="utf-8")
    assert "publish" not in _imports(text)
    assert "pagespublish" not in REPO.joinpath("toto/publish.py").read_text(
        encoding="utf-8")


# ==========================================================================
# 경로 안전성
# ==========================================================================
def test_p1_missing_worktree_is_explained():
    dev = tmpdir()
    errs = P.check_pages_dir(dev.parent / "nope-pages-xyz", dev)
    assert errs and "gh-pages worktree 가 없습니다" in errs[0]
    assert "--orphan" in errs[0]


def test_p2_pages_inside_or_equal_dev_is_refused():
    dev = tmpdir()
    inner = dev.joinpath("site")
    inner.mkdir()
    subprocess.run(["git", "init", "-q", "-b", P.PAGES_BRANCH, str(inner)],
                   check=True)
    assert "겹칩니다" in P.check_pages_dir(inner, dev)[0]
    assert "겹칩니다" in P.check_pages_dir(dev, dev)[0]
    outer = make_pages()
    nested_dev = outer.joinpath("sh4")
    nested_dev.mkdir()
    assert "겹칩니다" in P.check_pages_dir(outer, nested_dev)[0]


def test_p3_wrong_branch_or_not_a_repo_is_refused():
    dev = tmpdir()
    err = P.check_pages_dir(make_pages("main"), dev)[0]
    assert "브랜치가 gh-pages 가 아닙니다" in err and "(main)" in err, err
    plain = tmpdir()
    assert "최상위 폴더가 아닙니다" in P.check_pages_dir(plain, dev)[0]
    sub = make_pages().joinpath("sub")
    sub.mkdir()
    assert "최상위 폴더가 아닙니다" in P.check_pages_dir(sub, dev)[0]


def test_p4_reports_symlink_outside_is_refused():
    pages, outside = make_pages(), tmpdir()
    try:
        pages.joinpath("reports").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        return                                   # 심볼릭 링크를 못 만드는 OS
    assert "밖을 가리킵니다" in P.check_pages_dir(pages, tmpdir())[0]


def test_p5_default_pages_dir_is_sibling_named_by_git():
    top = P.repo_toplevel(REPO)
    assert top.resolve() == REPO.resolve()
    assert P.default_pages_dir(REPO) == REPO.resolve().parent / (
        REPO.resolve().name + "-pages")


# ==========================================================================
# 기본 경로 규칙 · git · 분기
# ==========================================================================
def test_r1_final_path_matches_write_report():
    """게시 대상 자리는 `_write_report()` 가 쓰는 자리 그대로다."""
    dev = tmpdir()
    s = dev_settings(dev)
    rep = TA.make_report("990052")
    args = cli.build_parser().parse_args(["--round", "990052"])
    saved = cli.render_report
    cli.render_report = lambda report, settings: "<html></html>"
    try:
        out = cli._write_report(rep, args, s, "생성 완료")
    finally:
        cli.render_report = saved
    assert out == P.final_report_path(s, "990052")


def test_g1_no_git_write_commands_are_run():
    text = REPO.joinpath("toto/pagespublish.py").read_text(encoding="utf-8")
    tree_ = ast.parse(text)
    firsts = set()
    for n in ast.walk(tree_):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id == "_git":
            arg = n.args[0]
            assert isinstance(arg, ast.List), ast.dump(arg)
            firsts.add(arg.elts[0].value)
    assert firsts <= {"rev-parse", "symbolic-ref", "show-ref"}, firsts
    runs = [n for n in ast.walk(tree_) if isinstance(n, ast.Attribute)
            and n.attr in ("run", "Popen", "call", "check_call", "check_output")]
    assert len(runs) == 1                        # `_git` 안의 하나뿐


def test_g2_no_bulk_copy():
    text = REPO.joinpath("toto/pagespublish.py").read_text(encoding="utf-8")
    for bad in ("rglob(", "copytree(", ".glob(", "walk("):
        assert bad not in text, bad


def test_g3_git_commands_are_printed_not_run():
    base, dev, pages = tmpdir(), tmpdir(), make_pages()
    r = Round("990052", base)
    r.write(dev)
    res = r.publish(dev, pages)
    q = f'"{pages}"'
    assert res.git_commands == [
        f"git -C {q} status --short",
        f"git -C {q} add index.html .nojekyll reports/toto_990052.html",
        f'git -C {q} commit -m "publish: 990052 report"',
        f"git -C {q} push -u origin gh-pages"]
    log = subprocess.run(["git", "-C", str(pages), "log", "--oneline"],
                         capture_output=True, text=True)
    assert log.returncode != 0 or not log.stdout.strip()   # 커밋이 없다


def test_c1_cli_args_and_branch_before_collection():
    args = cli.build_parser().parse_args(["--publish-round", "260054",
                                          "--pages-dir", "x"])
    assert args.publish_round == "260054" and args.pages_dir == Path("x")
    assert cli.build_parser().parse_args(["--demo"]).publish_round is None
    code = (f"import sys; sys.path.insert(0, {str(REPO)!r});"
            "from toto import cli;"
            "rc = cli.main(['--publish-round', '999999', '--pages-dir', "
            f"{str(tmpdir())!r}]);"
            "print(rc, sorted(m for m in sys.modules if m.startswith('toto.sources')))")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    assert proc.stdout.strip().splitlines()[-1] == "1 []", proc.stdout + proc.stderr


# --------------------------------------------------------------------------
def main() -> int:
    if not HAS_GIT:
        print("git 이 없어 건너뜁니다.")
        return 0
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
