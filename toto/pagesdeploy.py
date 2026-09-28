"""GitHub Pages 자동 배포 — 최종 리포트 한 장을 gh-pages 에 commit·push 한다.

    reports/toto_<회차>.html                  분석 작업 영역 — 건드리지 않는다
        ↓ pagespublish.publish_round()       검사 · 복사 · index 재생성 (§1-52)
    <저장소>-pages/reports/toto_<회차>.html   gh-pages worktree
        ↓ 이 모듈                              그 회차의 게시 파일만 add·commit·push
    origin/gh-pages → GitHub Pages

**검사·복사·index 를 다시 만들지 않는다.** `pagespublish` 의 판정(패널 완료 ·
패널이 붙은 렌더 · 반영 뒤 렌더)과 복사를 그대로 부르고, 여기서 하는 일은 그
뒤의 git 쓰기뿐이다. `pagespublish` 는 읽기 전용 git 만 쓰는 모듈로 남는다 —
git 쓰기는 이 모듈에만 있다.

**게시 파일만 staging 한다.** `git add .`·`-A` 를 쓰지 않는다. 대상은 이번
회차 리포트와 index.html·.nojekyll 셋뿐이고, 그중 `git status` 가 바뀌었다고
말한 것만 add·commit 한다. index 는 회차 목록이 달라질 때만 내용이 바뀌므로
같은 회차를 다시 배포하면 commit 되지 않는다. commit 에도 pathspec 을 붙인다
— 게시 폴더에 사용자가 따로 staging 해 둔 파일이 있어도 함께 commit 되지
않는다.

**인증 정보를 다루지 않는다.** PC 에 이미 설정된 git 인증을 그대로 쓴다.
토큰·비밀번호를 받지도 저장하지도 않고, git 출력에 URL 속 인증 정보가 보이면
가린다. 터미널에서 묻는 대신 실패하도록 `GIT_TERMINAL_PROMPT=0` 을 준다 —
출력을 잡고 있어 물어도 사용자에게 보이지 않기 때문이다.

**배포는 분석이 아니다.** 실패해도 리포트를 지우거나 되돌리지 않고 사유만
크게 알린다. 다시 배포: `python -m toto.pagesdeploy <회차>`.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import pagespublish, render
from .pagespublish import (INDEX_FILE, NOJEKYLL_FILE, PAGES_BRANCH,
                           REPORTS_DIRNAME)

log = logging.getLogger(__name__)

ENV_PAGES_DIR = "SH4_PAGES_DIR"      # 게시 폴더 (없으면 저장소 옆 <이름>-pages)
ENV_AUTO = "TOTO_PAGES_DEPLOY"       # 0 · false · off · no → 자동 배포를 끈다
_OFF = ("0", "false", "off", "no")

REMOTE = "origin"
COMMIT_MESSAGE = "Publish toto {round} report"
GIT_TIMEOUT = 60
PUSH_TIMEOUT = 300
BAR = "=" * 50

DEPLOYED = "deployed"        # commit(또는 밀린 커밋) push 까지 끝났다
UNCHANGED = "unchanged"      # 바뀐 것이 없어 commit·push 를 하지 않았다
SKIPPED = "skipped"          # 게시 폴더가 없다 — 아무것도 쓰지 않았다
BLOCKED = "blocked"          # 게시 조건 미충족 — 아무것도 쓰지 않았다
FAILED = "failed"            # 복사 뒤 git 단계가 실패했다


@dataclass
class GitCall:
    args: list
    code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def output(self) -> str:
        return "\n".join(t for t in (self.stdout.strip(), self.stderr.strip())
                         if t)


@dataclass
class DeployResult:
    round_id: str = ""
    status: str = ""
    source: Path | None = None
    dest: Path | None = None
    pages_dir: Path | None = None
    pages_dir_from: str = ""
    commit_message: str = ""
    committed: list = field(default_factory=list)   # 이번에 commit 한 경로
    pending: int = 0                                 # push 한 커밋 수
    pushed: bool = False
    url: str = ""
    reasons: list = field(default_factory=list)
    calls: list = field(default_factory=list)        # 실행한 GitCall

    @property
    def ok(self) -> bool:
        return self.status in (DEPLOYED, UNCHANGED)


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------
def run_git(args: list, cwd: Path, *, timeout: int = GIT_TIMEOUT) -> GitCall:
    """git 명령 하나. 예외를 올리지 않고 종료코드와 출력으로 돌려준다."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        proc = subprocess.run(["git", "-C", str(cwd), *args],
                              capture_output=True, encoding="utf-8",
                              errors="replace", timeout=timeout,
                              stdin=subprocess.DEVNULL, env=env)
    except subprocess.TimeoutExpired:
        return GitCall(list(args), 124, "",
                       f"git {args[0]} 이 {timeout}초 안에 끝나지 않았습니다")
    except (OSError, subprocess.SubprocessError) as exc:
        return GitCall(list(args), 1, "", str(exc))
    return GitCall(list(args), proc.returncode, proc.stdout or "",
                   proc.stderr or "")


_USERINFO = re.compile(r"(\b[a-z][a-z0-9+.-]*://)[^/\s@]+@", re.I)


def redact(text: str) -> str:
    """URL 에 붙은 인증 정보(`https://user:token@…`)를 가린다."""
    return _USERINFO.sub(r"\1***@", text or "")


_GITHUB = re.compile(r"^(?:[a-z][a-z0-9+.-]*://)?(?:[^@/\s]+@)?github\.com"
                     r"[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", re.I)


def pages_url(remote_url: str, round_id: str) -> str:
    """origin 주소로 GitHub Pages 주소를 만든다. github.com 이 아니면 ""."""
    m = _GITHUB.match((remote_url or "").strip())
    if not m:
        return ""
    owner, repo = m.group(1).lower(), m.group(2)
    site = f"https://{owner}.github.io/"
    if repo.lower() != f"{owner}.github.io":
        site += f"{repo}/"
    return f"{site}{REPORTS_DIRNAME}/toto_{round_id}.html"


def managed_paths(round_id: str) -> list[str]:
    """이 회차 배포가 staging 할 수 있는 경로 — **이것뿐이다.**"""
    return [f"{REPORTS_DIRNAME}/toto_{round_id}.html", INDEX_FILE,
            NOJEKYLL_FILE]


def changed_paths(porcelain: str, paths: list[str]) -> list[str]:
    """`git status --porcelain` 에서 `paths` 중 바뀐 것만, `paths` 순서로."""
    seen = set()
    for line in (porcelain or "").splitlines():
        if len(line) < 4:
            continue
        name = line[3:].split(" -> ")[-1].strip().strip('"')
        seen.add(name)
    return [p for p in paths if p in seen]


def _ahead(pages: Path, git) -> tuple[int, list]:
    """원격 gh-pages 에 아직 없는 커밋 수. 원격 기록이 없으면 전부."""
    calls = []
    ref = f"refs/remotes/{REMOTE}/{PAGES_BRANCH}"
    has = git(["rev-parse", "--verify", "--quiet", ref], pages)
    calls.append(has)
    span = f"{ref}..HEAD" if has.code == 0 else "HEAD"
    head = git(["rev-parse", "--verify", "--quiet", "HEAD"], pages)
    calls.append(head)
    if head.code != 0:
        return 0, calls                      # 커밋이 하나도 없다
    cnt = git(["rev-list", "--count", span], pages)
    calls.append(cnt)
    text = cnt.stdout.strip()
    return (int(text) if cnt.code == 0 and text.isdigit() else 0), calls


# --------------------------------------------------------------------------
# 경로 · 켜짐
# --------------------------------------------------------------------------
def resolve_pages_dir(settings, explicit: Path | None = None
                      ) -> tuple[Path, str]:
    """게시 폴더와 그 출처. `--pages-dir` → `SH4_PAGES_DIR` → 저장소 옆."""
    if explicit:
        return Path(explicit), "--pages-dir"
    env = os.environ.get(ENV_PAGES_DIR, "").strip()
    if env:
        return Path(os.path.expandvars(os.path.expanduser(env))), ENV_PAGES_DIR
    return (pagespublish.default_pages_dir(Path(settings.root)),
            "기본값 — 저장소 옆 <저장소 이름>-pages")


def auto_enabled() -> bool:
    return os.environ.get(ENV_AUTO, "").strip().lower() not in _OFF


# --------------------------------------------------------------------------
# 배포
# --------------------------------------------------------------------------
def _show(call: GitCall, echo) -> None:
    for line in redact(call.output).splitlines():
        echo(f"  │ {line}")


def _fail(out: DeployResult, what: str, call: GitCall) -> DeployResult:
    out.status = FAILED
    detail = redact(call.output) or f"종료코드 {call.code}"
    out.reasons.append(f"{what} — {detail}")
    low = detail.lower()
    if call.args[:1] == ["push"] and ("rejected" in low or "fetch first" in low
                                       or "non-fast-forward" in low):
        out.reasons.append(
            f"원격 {PAGES_BRANCH} 가 앞서 있습니다. 게시 폴더에서 "
            f"`git pull --rebase {REMOTE} {PAGES_BRANCH}` 로 맞춘 뒤 다시 "
            f"배포하십시오 (강제 push 는 하지 않습니다).")
    return out


def deploy_round(round_id: str, settings, pages_dir: Path | None = None, *,
                 report=None, base: Path | None = None,
                 outdir: Path | None = None, git=run_git,
                 echo=print) -> DeployResult:
    """검사·복사(`pagespublish`) → 바뀐 게시 파일만 commit → push."""
    rid = str(round_id or "").strip()
    out = DeployResult(round_id=rid)
    echo(BAR)
    echo("GitHub Pages 자동 배포")
    echo(BAR)
    echo(f"회차: {rid or '(미상)'}")

    pages, how = resolve_pages_dir(settings, pages_dir)
    out.pages_dir, out.pages_dir_from = pages, how
    if not pages.is_dir():
        out.status = SKIPPED
        out.reasons += [
            f"게시 폴더가 없습니다: {pages} ({how})",
            f"다른 곳에 있으면 환경변수 {ENV_PAGES_DIR} 로 경로를 지정하십시오.",
            "없으면 gh-pages worktree 를 만드십시오: "
            + pagespublish.worktree_hint(Path(settings.root), pages)]
        return out

    pub = pagespublish.publish_round(rid, settings, pages, report=report,
                                     base=base, outdir=outdir)
    out.source = pub.source
    if not pub.ok:
        out.status = BLOCKED
        out.reasons += pub.errors
        return out
    out.dest = pub.dest
    echo("[Pages] 리포트 복사 완료:")
    echo(f"  {pub.dest}")

    paths = managed_paths(rid)
    st = git(["status", "--porcelain", "--untracked-files=all", "--", *paths],
             pages)
    out.calls.append(st)
    if st.code != 0:
        return _fail(out, "git status 실패", st)
    changed = changed_paths(st.stdout, paths)

    if changed:
        add = git(["add", "--", *changed], pages)
        out.calls.append(add)
        if add.code != 0:
            return _fail(out, "git add 실패", add)
        message = COMMIT_MESSAGE.format(round=rid)
        com = git(["commit", "-m", message, "--", *changed], pages)
        out.calls.append(com)
        echo("[Pages] Git commit:")
        echo(f"  {message}")
        _show(com, echo)
        if com.code != 0:
            return _fail(out, "git commit 실패", com)
        out.commit_message, out.committed = message, changed

    ahead, calls = _ahead(pages, git)
    out.calls += calls
    if not changed and ahead == 0:
        out.status = UNCHANGED
        echo("[Pages] 변경사항 없음 — push 생략")
    else:
        if not changed:
            echo(f"[Pages] 변경사항 없음 — 앞서 push 하지 못한 커밋 {ahead}개를 "
                 f"push 합니다")
        push = git(["push", REMOTE, PAGES_BRANCH], pages, timeout=PUSH_TIMEOUT)
        out.calls.append(push)
        echo("[Pages] GitHub Pages push:")
        echo(f"  {REMOTE}/{PAGES_BRANCH}")
        _show(push, echo)
        if push.code != 0:
            return _fail(out, "git push 실패", push)
        out.pushed, out.pending, out.status = True, ahead, DEPLOYED

    remote = git(["remote", "get-url", REMOTE], pages)
    out.calls.append(remote)
    if remote.code == 0:
        out.url = pages_url(remote.stdout, rid)
    return out


def report_lines(result: DeployResult, *, auto: bool = False) -> list[str]:
    """배포 뒤 요약. 머리글(회차)은 `deploy_round` 가 이미 냈다."""
    rid = result.round_id or "<회차>"
    retry = f"다시 배포: python -m toto.pagesdeploy {rid}"
    if result.status in (SKIPPED, BLOCKED):
        head = ("[Pages] 자동 배포하지 않았습니다" if auto
                else "[Pages] GitHub Pages 배포 실패")
        lines = [head]
        lines += [f"원인: {r}" if i == 0 else f"      {r}"
                  for i, r in enumerate(result.reasons)]
        lines += ["", "게시 폴더에는 아무것도 쓰지 않았습니다. 분석 리포트는 "
                      "그대로 있습니다.", BAR]
        return lines
    if result.status == FAILED:
        lines = ["[Pages] GitHub Pages 배포 실패"]
        lines += [f"원인: {r}" if i == 0 else f"      {r}"
                  for i, r in enumerate(result.reasons)]
        lines += ["", f"원본: {result.source}"]
        if result.dest:
            lines.append(f"복사: {result.dest}")
        lines += ["분석 리포트는 그대로 있습니다. 문제를 고친 뒤 " + retry, BAR]
        return lines

    if result.committed:
        commit = result.commit_message
    elif result.pending:
        commit = f"없음 (앞서 만든 커밋 {result.pending}개를 push)"
    else:
        commit = "없음 — 변경사항 없음"
    lines = ["", "원본:", str(result.source), "", "복사:", str(result.dest), "",
             "Git:", f"commit: {commit}", f"branch: {PAGES_BRANCH}",
             "push: " + ("성공" if result.pushed else "생략 (변경사항 없음)"),
             "", "GitHub Pages:",
             result.url or f"주소를 알 수 없습니다 ({REMOTE} 주소가 github.com "
                           "이 아닙니다)",
             "",
             "배포 완료" if result.pushed
             else "변경사항 없음 — 이미 배포된 판과 같습니다",
             BAR]
    return lines


def auto_deploy(out_path: Path, round_id: str, settings,
                pages_dir: Path | None = None, *, git=run_git,
                echo=print) -> DeployResult | None:
    """리포트를 **다 쓴 뒤** 부른다 (cli). 배포 대상이 아니면 None.

    대상은 기본 경로(`reports/toto_<숫자>.html`)에 쓴, 패널이 붙은 리포트다.
    DEMO · `-o` 비교본은 조용히 넘기고, 패널 반영 전 리포트([1] 직후)는
    한 줄로 알리고 넘긴다 — 패널이 반영되는 순간([2]·[4]) 다시 불린다.
    """
    rid = str(round_id or "").strip()
    if not pagespublish.ROUND_ID.match(rid):
        log.debug("[Pages] 자동 배포 대상 아님 — 회차가 숫자가 아닙니다 (%s)",
                  rid or "미상")
        return None
    out_path = Path(out_path)
    try:
        canonical = (out_path.resolve()
                     == pagespublish.final_report_path(settings, rid).resolve())
    except OSError:
        canonical = False
    if not canonical:
        log.debug("[Pages] 자동 배포 대상 아님 — 기본 경로가 아닌 출력: %s",
                  out_path)
        return None
    if not auto_enabled():
        echo(f"[Pages] 자동 배포 꺼짐 ({ENV_AUTO}="
             f"{os.environ.get(ENV_AUTO, '')}) — 수동: "
             f"python -m toto.pagesdeploy {rid}")
        return None
    try:
        text = out_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        text = ""
    if render.PANEL_CSS not in text:
        echo(f"[Pages] 자동 배포 생략 — 패널 반영 전 리포트입니다 "
             f"({out_path.name}). 패널이 반영되면([2] 패널 자동 분석 · "
             f"[4] 반영) 그때 자동으로 배포됩니다.")
        return None

    result = deploy_round(rid, settings, pages_dir, git=git, echo=echo)
    for line in report_lines(result, auto=True):
        echo(line)
    return result


def main(argv: list | None = None) -> int:
    """`python -m toto.pagesdeploy <회차>` — 수동 (재)배포."""
    import argparse

    from .cli import _setup_logging, safe_console
    from .settings import load_settings

    safe_console()
    p = argparse.ArgumentParser(
        prog="python -m toto.pagesdeploy",
        description="패널까지 끝난 회차의 최종 리포트를 gh-pages 에 복사하고 "
                    "그 파일만 commit·push 한다.")
    p.add_argument("round_id", metavar="ROUND", help="회차 (예: 260055)")
    p.add_argument("--pages-dir", type=Path, default=None, metavar="DIR",
                   help=f"게시 폴더 (기본: 환경변수 {ENV_PAGES_DIR} → "
                        "저장소 옆 <저장소 이름>-pages)")
    args = p.parse_args(argv)
    _setup_logging(False)
    result = deploy_round(args.round_id, load_settings(), args.pages_dir)
    for line in report_lines(result):
        print(line)
    return 0 if result.ok else 1


__all__ = [
    "ENV_PAGES_DIR", "ENV_AUTO", "REMOTE", "COMMIT_MESSAGE",
    "DEPLOYED", "UNCHANGED", "SKIPPED", "BLOCKED", "FAILED",
    "GitCall", "DeployResult", "run_git", "redact", "pages_url",
    "managed_paths", "changed_paths", "resolve_pages_dir", "auto_enabled",
    "deploy_round", "report_lines", "auto_deploy", "main",
]


if __name__ == "__main__":
    sys.exit(main())
