"""GitHub Pages 자동 배포 (`toto/pagesdeploy.py` · cli 의 `_pages_deploy`).

리포트를 쓴 직후 `reports/toto_<회차>.html` 을 gh-pages worktree 로 복사하고
**그 회차의 게시 파일만** add·commit·push 한다. 검사·복사·index 는
`pagespublish` 를 그대로 쓴다.

이 스위트가 지키는 것.

  1. 정상 배포 — 복사 → commit(`Publish toto <회차> report`) → push
  2. 파일 없음 — 명확한 오류, 게시 폴더에 아무것도 쓰지 않는다
  3. 변경사항 없음 — commit 도 push 도 하지 않는다
  4. push 실패 — 크게 알리고, 리포트·복사본·커밋을 지우지 않는다. 다시
     돌리면 밀린 커밋을 push 한다
  5. 사용자의 다른 변경사항을 commit 하지 않는다 (`git add .` 없음)
  6. 인증 정보를 다루지 않는다
  7. 리포트를 **다 쓴 뒤** 자동으로 불린다 — 패널 반영 전 판·DEMO·`-o` 는
     배포하지 않는다

**실제 GitHub 에 닿지 않는다.** 원격은 전부 임시 폴더의 bare 저장소이고,
GitHub 주소가 필요한 검사는 `remote get-url` 응답만 바꿔 끼운다. 저장소의
`reports/`·`panel_work/`·`panel_results/`·`data/` 도 건드리지 않는다.

    python tests/test_pages_deploy.py
"""
from __future__ import annotations

import ast
import contextlib
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import (artifact, cli, pagesdeploy as D, pagespublish as P,  # noqa: E402
                  panelexport, panelwork, render)
from toto import settings as settings_mod                  # noqa: E402

import test_pages_publish as PP                            # noqa: E402
import test_panel_apply as TA                              # noqa: E402

REPO = Path(__file__).resolve().parent.parent
HAS_GIT = shutil.which("git") is not None
GITHUB = "https://github.com/hsj0358-afk/sh4.git"


def teardown_function(function):   # pytest 가 테스트마다 부른다 (실패해도)
    PP.cleanup_tmpdirs()


# ==========================================================================
# 픽스처
# ==========================================================================
def git(repo: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True)


def make_repo(remote=True) -> tuple[Path, Path | None]:
    """gh-pages worktree 흉내 + **로컬** bare 원격. GitHub 에 닿지 않는다.

    전역 설정(서명·사용자)에 기대지 않도록 저장소마다 적어 둔다.
    """
    pages = PP.make_pages()
    for key, value in (("user.name", "toto test"),
                       ("user.email", "toto@example.invalid"),
                       ("commit.gpgsign", "false")):
        git(pages, "config", key, value)
    bare = None
    if remote is True:
        bare = PP.tmpdir("toto_pages_remote_")
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        git(pages, "remote", "add", "origin", str(bare))
    elif remote:
        git(pages, "remote", "add", "origin", str(remote))
    return pages, bare


def recorder(calls: list, *, url: str | None = None, push=None):
    """`run_git` 를 감싸 호출을 기록한다. 응답 몇 개만 바꿔 끼울 수 있다."""
    def run(args, cwd, *, timeout=D.GIT_TIMEOUT):
        calls.append(list(args))
        if url is not None and args[:2] == ["remote", "get-url"]:
            return D.GitCall(list(args), 0, url + "\n")
        if push is not None and args[:1] == ["push"]:
            return push(args)
        return D.run_git(args, cwd, timeout=timeout)
    return run


def deploy(r, dev: Path, pages: Path, **kw):
    lines: list = []
    res = D.deploy_round(r.rid, PP.dev_settings(dev), pages, report=r.report,
                         base=r.base, outdir=r.outdir, echo=lines.append, **kw)
    return res, lines


def remote_log(bare: Path) -> list[str]:
    out = git(bare, "log", "--format=%s", P.PAGES_BRANCH)
    return out.stdout.split("\n")[:-1] if out.returncode == 0 else []


def remote_files(bare: Path) -> list[str]:
    return sorted(git(bare, "ls-tree", "-r", "--name-only",
                      P.PAGES_BRANCH).stdout.split())


def commit_files(repo: Path, rev="HEAD") -> list[str]:
    out = git(repo, "show", "--name-only", "--format=", rev)
    return sorted(out.stdout.split())


@contextlib.contextmanager
def env(**values):
    saved = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def said(lines, needle) -> bool:
    return any(needle in line for line in lines)


# ==========================================================================
# 1. 정상 배포
# ==========================================================================
def test_a1_copies_commits_and_pushes_the_round():
    base, dev = PP.tmpdir(), PP.tmpdir()
    pages, bare = make_repo()
    r = PP.Round("990052", base)
    src = r.write(dev)
    res, lines = deploy(r, dev, pages)
    assert res.status == D.DEPLOYED and res.ok and res.pushed, res.reasons
    assert res.dest == pages / "reports" / "toto_990052.html"
    assert remote_log(bare) == ["Publish toto 990052 report"]
    assert remote_files(bare) == [".nojekyll", "index.html",
                                  "reports/toto_990052.html"]
    blob = subprocess.run(["git", "-C", str(bare), "show",
                           f"{P.PAGES_BRANCH}:reports/toto_990052.html"],
                          capture_output=True).stdout
    assert blob == src.read_bytes(), "원격의 파일이 PC 원본과 다르다"
    for needle in ("[Pages] 리포트 복사 완료:", "[Pages] Git commit:",
                   "Publish toto 990052 report", "[Pages] GitHub Pages push:",
                   "origin/gh-pages"):
        assert said(lines, needle), needle


def test_a2_summary_block_has_the_requested_fields():
    base, dev = PP.tmpdir(), PP.tmpdir()
    pages, _bare = make_repo()
    r = PP.Round("990052", base)
    r.write(dev)
    res, lines = deploy(r, dev, pages, git=recorder([], url=GITHUB))
    block = lines + D.report_lines(res, auto=True)
    for needle in ("GitHub Pages 자동 배포", "회차: 990052", "원본:", "복사:",
                   "commit: Publish toto 990052 report", "branch: gh-pages",
                   "push: 성공", "GitHub Pages:",
                   "https://hsj0358-afk.github.io/sh4/reports/toto_990052.html",
                   "배포 완료"):
        assert said(block, needle), needle
    assert block[0] == D.BAR and block[-1] == D.BAR


def test_a3_next_round_commits_its_report_and_the_index_only():
    base, dev = PP.tmpdir(), PP.tmpdir()
    pages, bare = make_repo()
    r1, r2 = PP.Round("990052", base), PP.Round("990054", base)
    r1.write(dev)
    r2.write(dev)
    assert deploy(r1, dev, pages)[0].status == D.DEPLOYED
    res, _ = deploy(r2, dev, pages)
    assert res.status == D.DEPLOYED, res.reasons
    assert res.committed == ["reports/toto_990054.html", "index.html"]
    assert commit_files(pages) == ["index.html", "reports/toto_990054.html"]
    assert remote_log(bare) == ["Publish toto 990054 report",
                                "Publish toto 990052 report"]
    assert "reports/toto_990052.html" in remote_files(bare), "이전 회차가 사라졌다"


# ==========================================================================
# 2. 파일 없음
# ==========================================================================
def test_b1_missing_report_fails_clearly_and_writes_nothing():
    dev = PP.tmpdir()
    pages, bare = make_repo()
    calls: list = []
    lines: list = []
    res = D.deploy_round("999999", PP.dev_settings(dev), pages,
                         git=recorder(calls), echo=lines.append)
    assert res.status == D.BLOCKED and not res.ok
    assert any("최종 리포트가 없습니다" in e and "toto_999999.html" in e
               for e in res.reasons), res.reasons
    assert PP.tree(pages) == [], "게시 폴더에 무언가를 썼다"
    assert calls == [], f"git 을 불렀다: {calls}"
    assert remote_log(bare) == []
    text = "\n".join(D.report_lines(res))
    assert "[Pages] GitHub Pages 배포 실패" in text and "원인:" in text


def test_b2_manual_command_exits_nonzero_with_the_reason():
    pages, _bare = make_repo()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = D.main(["999999", "--pages-dir", str(pages)])
    out = buf.getvalue()
    assert rc == 1
    assert "[Pages] GitHub Pages 배포 실패" in out and "toto_999999.html" in out
    assert PP.tree(pages) == []


def test_b3_missing_pages_folder_is_skipped_with_guidance():
    base, dev = PP.tmpdir(), PP.tmpdir()
    r = PP.Round("990052", base)
    r.write(dev)
    missing = dev.parent / "toto_no_such_pages_dir"
    res, _ = deploy(r, dev, missing)
    assert res.status == D.SKIPPED and not res.ok
    text = "\n".join(res.reasons)
    assert str(missing) in text and D.ENV_PAGES_DIR in text
    assert "worktree" in text


# ==========================================================================
# 3. 변경사항 없음
# ==========================================================================
def test_c1_same_html_again_makes_no_commit_and_no_push():
    base, dev = PP.tmpdir(), PP.tmpdir()
    pages, bare = make_repo()
    r = PP.Round("990052", base)
    r.write(dev)
    assert deploy(r, dev, pages)[0].status == D.DEPLOYED
    calls: list = []
    res, lines = deploy(r, dev, pages, git=recorder(calls))
    assert res.status == D.UNCHANGED and res.ok and not res.pushed
    assert "[Pages] 변경사항 없음 — push 생략" in lines
    assert not [c for c in calls if c[0] in ("add", "commit", "push")], calls
    assert remote_log(bare) == ["Publish toto 990052 report"]
    assert git(pages, "status", "--porcelain").stdout == "", \
        "index.html 을 다시 쓰고 변경으로 남겼다"
    block = "\n".join(D.report_lines(res))
    assert "push: 생략" in block and "배포 완료" not in block


# ==========================================================================
# 4. push 실패
# ==========================================================================
def test_d1_push_failure_is_loud_and_keeps_everything():
    base, dev = PP.tmpdir(), PP.tmpdir()
    nowhere = PP.tmpdir().joinpath("no-such-remote.git")
    pages, _ = make_repo(remote=str(nowhere))
    r = PP.Round("990052", base)
    src = r.write(dev)
    before = P.sha256_of(src)
    res, lines = deploy(r, dev, pages)
    assert res.status == D.FAILED and not res.ok and not res.pushed
    assert res.reasons[0].startswith("git push 실패"), res.reasons
    text = "\n".join(D.report_lines(res, auto=True))
    assert "[Pages] GitHub Pages 배포 실패" in text and "원인: git push 실패" in text
    assert "python -m toto.pagesdeploy 990052" in text
    assert P.sha256_of(src) == before, "분석 리포트가 바뀌었다"
    assert (pages / "reports" / "toto_990052.html").is_file()
    assert git(pages, "log", "--format=%s").stdout.strip() == \
        "Publish toto 990052 report", "커밋을 되돌렸다"


def test_d2_rerun_pushes_the_commit_left_behind():
    base, dev = PP.tmpdir(), PP.tmpdir()
    nowhere = PP.tmpdir().joinpath("no-such-remote.git")
    pages, _ = make_repo(remote=str(nowhere))
    r = PP.Round("990052", base)
    r.write(dev)
    assert deploy(r, dev, pages)[0].status == D.FAILED
    bare = PP.tmpdir("toto_pages_remote_")
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(pages, "remote", "set-url", "origin", str(bare))
    calls: list = []
    res, lines = deploy(r, dev, pages, git=recorder(calls))
    assert res.status == D.DEPLOYED and res.pushed and res.pending == 1
    assert said(lines, "앞서 push 하지 못한 커밋 1개")
    assert not [c for c in calls if c[0] in ("add", "commit")], "빈 커밋을 만들었다"
    assert remote_log(bare) == ["Publish toto 990052 report"]


def test_d3_rejected_push_suggests_pull_and_never_forces():
    base, dev = PP.tmpdir(), PP.tmpdir()
    pages, bare = make_repo()
    r = PP.Round("990052", base)
    r.write(dev)
    calls: list = []

    def rejected(args):
        return D.GitCall(list(args), 1, "",
                         "To https://user:secret@github.com/o/r.git\n"
                         " ! [rejected]  gh-pages -> gh-pages (fetch first)")
    res, lines = deploy(r, dev, pages, git=recorder(calls, push=rejected))
    assert res.status == D.FAILED
    text = "\n".join(res.reasons + lines)
    assert "pull --rebase origin gh-pages" in text
    assert "secret" not in text, "인증 정보를 화면에 냈다"
    pushes = [c for c in calls if c[0] == "push"]
    assert pushes == [["push", "origin", "gh-pages"]], pushes
    assert remote_log(bare) == []


# ==========================================================================
# 5. 다른 변경사항을 건드리지 않는다
# ==========================================================================
def test_e1_user_work_in_the_pages_folder_is_not_committed():
    base, dev = PP.tmpdir(), PP.tmpdir()
    pages, bare = make_repo()
    r = PP.Round("990052", base)
    r.write(dev)
    pages.joinpath("notes.txt").write_text("작업 중", encoding="utf-8")
    git(pages, "add", "notes.txt")                        # 사용자가 staging
    pages.joinpath("draft.html").write_text("초안", encoding="utf-8")
    pages.joinpath("reports").mkdir()
    pages.joinpath("reports", "scratch.txt").write_text("x", encoding="utf-8")
    res, _ = deploy(r, dev, pages)
    assert res.status == D.DEPLOYED, res.reasons
    assert commit_files(pages) == [".nojekyll", "index.html",
                                   "reports/toto_990052.html"]
    assert remote_files(bare) == [".nojekyll", "index.html",
                                  "reports/toto_990052.html"]
    status = git(pages, "status", "--porcelain").stdout.splitlines()
    assert "A  notes.txt" in status, status               # 여전히 staging 만
    assert "?? draft.html" in status, status
    assert "?? reports/scratch.txt" in status, status


def _git_arg_lists() -> list[list]:
    """`pagesdeploy` 가 `git(...)` 에 넘기는 인자 목록의 문자열 상수들."""
    tree = ast.parse(Path(D.__file__).read_text(encoding="utf-8"))
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id == "git" and n.args \
                and isinstance(n.args[0], ast.List):
            out.append([e.value if isinstance(e, ast.Constant) else
                        ast.unparse(e) for e in n.args[0].elts])
    return out


def test_e2_never_adds_everything_and_never_forces():
    lists = _git_arg_lists()
    assert lists, "git 호출을 찾지 못했다"
    banned = {".", "-A", "--all", "-u", "--update", "--force", "-f",
              "--force-with-lease", "--mirror", "--amend", "--no-verify"}
    for args in lists:
        assert not banned & set(args), args
    adds = [a for a in lists if a[0] == "add"]
    commits = [a for a in lists if a[0] == "commit"]
    pushes = [a for a in lists if a[0] == "push"]
    assert adds == [["add", "--", "*changed"]], adds
    assert commits and all(a[-2:] == ["--", "*changed"] for a in commits), commits
    assert pushes == [["push", "REMOTE", "PAGES_BRANCH"]], pushes
    assert D.REMOTE == "origin" and D.PAGES_BRANCH == "gh-pages"


def test_e3_only_the_three_publish_files_can_be_staged():
    assert D.managed_paths("260055") == ["reports/toto_260055.html",
                                         "index.html", ".nojekyll"]
    porcelain = ("?? reports/toto_260055.html\n M index.html\nA  notes.txt\n"
                 "?? reports/toto_260054.html\n")
    assert D.changed_paths(porcelain, D.managed_paths("260055")) == [
        "reports/toto_260055.html", "index.html"]


def test_e4_pagespublish_stays_read_only():
    """git 쓰기는 이 모듈에만 있다 — `pagespublish` 는 그대로 읽기 전용."""
    PP.test_g1_no_git_write_commands_are_run()
    assert "pagesdeploy" not in Path(P.__file__).read_text(encoding="utf-8")


# ==========================================================================
# 6. 인증 정보
# ==========================================================================
def test_f1_no_credentials_in_code_or_config():
    text = Path(D.__file__).read_text(encoding="utf-8").lower()
    for bad in ("ghp_", "github_pat", "x-access-token", "authorization",
                "password=", "token="):
        assert bad not in text, bad
    # 주소·경로를 코드에 박지 않는다 — 원격은 git 에, 폴더는 설정에 묻는다.
    for bad in ("hsj0358", "sh4-pages", "c:\\users", "github.com/"):
        assert bad not in text, bad
    conf = REPO.joinpath("config_toto.yaml").read_text(encoding="utf-8").lower()
    for bad in ("sh4-pages", "ghp_", "github_pat", "access_token",
                "github_token", "password"):
        assert bad not in conf, bad


def test_f2_git_output_is_redacted():
    assert D.redact("To https://u:ghp_x@github.com/o/r.git") == \
        "To https://***@github.com/o/r.git"
    assert D.redact("To https://github.com/o/r.git") == \
        "To https://github.com/o/r.git"


def test_f3_pages_url_from_origin():
    want = "https://hsj0358-afk.github.io/sh4/reports/toto_260055.html"
    for url in (GITHUB, "https://github.com/hsj0358-afk/sh4",
                "git@github.com:hsj0358-afk/sh4.git",
                "ssh://git@github.com/hsj0358-afk/sh4.git",
                "https://someone:tok@github.com/hsj0358-afk/sh4.git"):
        assert D.pages_url(url, "260055") == want, url
    assert D.pages_url("https://github.com/o/o.github.io.git", "1") == \
        "https://o.github.io/reports/toto_1.html"
    assert D.pages_url("/tmp/bare.git", "1") == ""
    assert D.pages_url("https://gitlab.com/o/r.git", "1") == ""


def test_f4_terminal_prompt_is_disabled():
    """출력을 잡고 있어 물어도 보이지 않는다 — 묻지 말고 실패하게 한다."""
    src = ast.unparse(next(
        n for n in ast.parse(Path(D.__file__).read_text(encoding="utf-8")).body
        if isinstance(n, ast.FunctionDef) and n.name == "run_git"))
    assert 'GIT_TERMINAL_PROMPT="0"' in src or "GIT_TERMINAL_PROMPT='0'" in src
    assert "stdin=subprocess.DEVNULL" in src


# ==========================================================================
# 7. 자동 호출 — 리포트를 다 쓴 뒤
# ==========================================================================
def _fn(name):
    tree = ast.parse(Path(cli.__file__).read_text(encoding="utf-8"))
    return next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == name)


def _call_lines(fn, name) -> list[int]:
    return [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == name]


def test_g1_hooked_right_after_every_report_write():
    for name in ("_panel_only", "_rerender", "main"):
        fn = _fn(name)
        writes, deploys = _call_lines(fn, "_write_report"), \
            _call_lines(fn, "_pages_deploy")
        assert len(writes) == 1 and len(deploys) == 1, (name, writes, deploys)
        assert deploys[0] > writes[0], f"{name}: 리포트를 쓰기 전에 배포한다"
    main = _fn("main")
    saves = [n.lineno for n in ast.walk(main) if isinstance(n, ast.Call)
             and ast.unparse(n.func) in ("artifact.save", "roundlog.record")]
    assert saves and max(saves) < _call_lines(main, "_pages_deploy")[0], \
        "저장본을 남기기 전에 배포한다 — 게시 판정이 옛 저장본을 읽는다"
    assert not _call_lines(_fn("_write_report"), "_pages_deploy"), \
        "_write_report 가 직접 배포한다 (-o 비교본·테스트까지 배포 대상이 된다)"
    assert not _call_lines(_fn("_publish_round"), "_pages_deploy"), \
        "--publish-round 의 동작이 바뀌었다"


def test_g2_deploy_errors_never_change_the_cli_result():
    real = D.auto_deploy

    def boom(*a, **kw):
        raise RuntimeError("주입한 오류")
    D.auto_deploy = boom
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            cli._pages_deploy(Path("x.html"), TA.make_report("990052"),
                              cli.build_parser().parse_args([]), TA.settings())
    finally:
        D.auto_deploy = real
    out = buf.getvalue()
    assert "[Pages] GitHub Pages 배포 실패" in out and "주입한 오류" in out


def _auto(r, dev, pages, out_path=None, text=None, **kw):
    s = PP.dev_settings(dev)
    path = r.write(dev, text) if out_path is None else out_path
    lines: list = []
    res = D.auto_deploy(path, r.rid, s, pages, echo=lines.append, **kw)
    return res, lines


def test_g3_non_candidates_are_left_alone():
    base, dev = PP.tmpdir(), PP.tmpdir()
    pages, bare = make_repo()
    r = PP.Round("990052", base)
    # DEMO
    lines: list = []
    assert D.auto_deploy(dev / "reports" / "toto_DEMO.html", "DEMO",
                         PP.dev_settings(dev), pages,
                         echo=lines.append) is None and lines == []
    # -o 비교본
    other = dev / "compare.html"
    other.write_text(r.html(), encoding="utf-8")
    res, lines = _auto(r, dev, pages, out_path=other)
    assert res is None and lines == []
    # 패널 반영 전 ([1] 직후)
    plain = render.render_report(TA.make_report(r.rid), TA.settings())
    res, lines = _auto(r, dev, pages, text=plain)
    assert res is None and said(lines, "패널 반영 전 리포트")
    # 사용자가 끈 경우
    with env(**{D.ENV_AUTO: "0"}):
        res, lines = _auto(r, dev, pages)
    assert res is None and said(lines, "자동 배포 꺼짐")
    assert said(lines, "python -m toto.pagesdeploy 990052")
    assert PP.tree(pages) == [] and remote_log(bare) == []


def test_g4_final_report_is_deployed_automatically():
    base, dev = PP.tmpdir(), PP.tmpdir()
    pages, bare = make_repo()
    r = PP.Round("990052", base)
    s = PP.dev_settings(dev)
    path = r.write(dev)
    lines: list = []
    # auto_deploy 는 저장본을 스스로 읽는다 — 이 픽스처의 보관 자리를 넘기려고
    # deploy_round 를 감싼다 (판정은 그대로 pagespublish 가 한다).
    real = D.deploy_round

    def wired(rid, settings, pages_dir=None, **kw):
        return real(rid, settings, pages_dir, report=r.report, base=r.base,
                    outdir=r.outdir, **kw)
    D.deploy_round = wired
    try:
        res = D.auto_deploy(path, r.rid, s, pages, echo=lines.append)
    finally:
        D.deploy_round = real
    assert res is not None and res.status == D.DEPLOYED, res and res.reasons
    assert said(lines, "배포 완료") and said(lines, "GitHub Pages 자동 배포")
    assert remote_log(bare) == ["Publish toto 990052 report"]


def test_g5_pages_dir_comes_from_arg_then_env_then_sibling():
    s = PP.dev_settings(PP.tmpdir())
    with env(**{D.ENV_PAGES_DIR: "/tmp/from-env"}):
        assert D.resolve_pages_dir(s, Path("/tmp/from-arg"))[0] == \
            Path("/tmp/from-arg")
        assert D.resolve_pages_dir(s)[0] == Path("/tmp/from-env")
    with env(**{D.ENV_PAGES_DIR: None}):
        path, how = D.resolve_pages_dir(PP.dev_settings(REPO))
    assert path == P.default_pages_dir(REPO) and "기본값" in how
    assert path.name == REPO.resolve().name + "-pages"


# ==========================================================================
# 8. 끝까지 — `--apply-panel-work` 가 리포트를 쓰고 곧바로 배포한다
# ==========================================================================
@contextlib.contextmanager
def sandbox(root: Path):
    """기본 자리(ROOT·저장본·자료 폴더)를 임시 폴더로. 저장소를 건드리지 않는다."""
    saved = (settings_mod.ROOT, artifact.ARTIFACT_DIR, panelexport.ROOT)
    settings_mod.ROOT = root
    artifact.ARTIFACT_DIR = root / "data" / "artifacts"
    panelexport.ROOT = root
    try:
        yield root
    finally:
        settings_mod.ROOT, artifact.ARTIFACT_DIR, panelexport.ROOT = saved


def _seed_round(rid: str, root: Path):
    report = TA.make_report(rid)
    TA.seed(report, root, c=False)
    assert panelwork.build_completed_sheet(report, TA.settings()).success
    TA.seed(report, root, a=False, b=False, c=True)
    artifact.save(report)
    return report


def _repo_snapshot():
    dirs = [REPO / d for d in ("panel_results", "panel_work", "reports",
                               "data/artifacts")]
    return {str(p): p.stat().st_mtime_ns
            for d in dirs if d.is_dir() for p in d.rglob("*")}


def _apply(rid: str, pages: Path):
    root = PP.tmpdir("toto_deploy_root_")
    before = _repo_snapshot()
    buf = io.StringIO()
    with sandbox(root), env(**{D.ENV_PAGES_DIR: str(pages), D.ENV_AUTO: None}):
        report = _seed_round(rid, root)
        args = cli.build_parser().parse_args(["--round", rid,
                                              "--apply-panel-work"])
        with contextlib.redirect_stdout(buf):
            rc = cli._panel_only(report, args, PP.dev_settings(root), None)
    assert _repo_snapshot() == before, "저장소의 파일이 바뀌었다"
    return rc, root, buf.getvalue()


def test_h1_apply_panel_work_writes_the_report_then_deploys_it():
    pages, bare = make_repo()
    rc, root, out = _apply("990060", pages)
    assert rc == 0, out
    src = root / "reports" / "toto_990060.html"
    assert src.is_file() and render.PANEL_CSS in src.read_text(encoding="utf-8")
    assert "배포 완료" in out, out
    assert remote_log(bare) == ["Publish toto 990060 report"]
    blob = subprocess.run(["git", "-C", str(bare), "show",
                           f"{P.PAGES_BRANCH}:reports/toto_990060.html"],
                          capture_output=True).stdout
    assert blob == src.read_bytes()


def test_h2_push_failure_keeps_the_cli_result_and_the_report():
    nowhere = PP.tmpdir().joinpath("no-such-remote.git")
    pages, _ = make_repo(remote=str(nowhere))
    rc, root, out = _apply("990062", pages)
    assert rc == 0, "배포 실패가 분석 실행의 결과를 바꿨다"
    assert "[Pages] GitHub Pages 배포 실패" in out and "원인: git push 실패" in out
    assert (root / "reports" / "toto_990062.html").is_file()
    assert (pages / "reports" / "toto_990062.html").is_file()


# --------------------------------------------------------------------------
def main() -> int:
    if not HAS_GIT:
        print("git 이 없어 건너뜁니다.")
        return 0
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
                PP.cleanup_tmpdirs()
    finally:
        PP.cleanup_tmpdirs()
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
