"""최종 리포트 한 장을 GitHub Pages 게시 영역으로 옮긴다 (`--publish-round`).

분석 시스템과 모바일 공개 리포트를 **나눈다.** 이 모듈은 그 사이의 얇은
게시 계층이다.

    reports/toto_<회차>.html            분석 작업 영역 — 건드리지 않는다
        ↓ 패널 완료 확인 · 게시 대상이 그 파일 하나인지 확인
    <저장소>-pages/reports/toto_<회차>.html   gh-pages worktree
        ↓ index.html 재생성 (게시 영역의 실제 파일 목록 기준)
    사람이 git add · commit · push          ← 이 모듈은 하지 않는다

**기존 `publish.py` 와 다르다.** 그쪽은 수집 직후(`cli.py` 의 수집 경로)
불려 패널 반영 **전** 판을 클라우드 폴더로 복사할 수 있다. 여기는 사용자가
명시적으로 부르고, 패널이 끝난 최종판만 받는다. 두 기능은 서로를 모른다.

**패널 완료 판정을 새로 만들지 않는다.** `panelwork.workflow(report=…)`
(6-F-4·6-F-12) 가 다섯 단계를 검증하고, 그중 `리포트 반영` 단계는
`--apply-panel-work` 가 1·2·3단계 보관본으로 Panel Result 를 만들며 남긴
기록(6-F-14 `record_applied`)과 대조돼야 `complete` 가 된다. 그 두 상태를
그대로 읽는다.

  · `workflow().done` 만으로는 모자란다 — 3단계 응답만 붙여 넣은 회차
    (사회자 전용 · `source: moderator-paste`)도 모든 단계가 `unverified`
    로 '끝났다' 가 된다(실물 260052 가 그 상태다). 1·2·3단계 원문이 최종
    결과에 실렸다는 것을 말해 주는 기존 상태는 반영 단계의 `complete`
    하나뿐이다.
  · 그리고 게시하려는 HTML 이 **패널이 붙은 렌더**인지 본다. `render.
    panel_css_for()` 는 패널이 붙은 경기가 있을 때만 `PANEL_CSS` 를 싣는다
    (§1-11). `[1]` 재수집이나 저장본 재렌더가 같은 파일을 패널 없는 판으로
    덮어쓴 경우가 여기서 걸린다.

**git 쓰기 명령을 실행하지 않는다.** add·commit·push 는 사람이 한다 —
인증·충돌을 분석 실행과 떼어 놓고, 올라갈 파일을 사람이 한 번 보게 한다.
읽기 전용 git 명령(`rev-parse` 등)만 쓴다.
"""
from __future__ import annotations

import hashlib
import html as _html
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import panelwork, render

PAGES_BRANCH = "gh-pages"
PAGES_SUFFIX = "-pages"
REPORTS_DIRNAME = "reports"
INDEX_FILE = "index.html"
NOJEKYLL_FILE = ".nojekyll"
INDEX_TITLE = "축구토토 승무패 분석 리포트"

# 게시 대상은 이 이름뿐이다. DEMO · manual · latest · `-o` 비교본
# (`toto_260052_5E3b.html`)이 전부 여기서 빠진다.
PUBLISH_NAME = re.compile(r"^toto_(\d+)\.html$")
ROUND_ID = re.compile(r"^\d+$")

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


@dataclass
class PublishResult:
    round_id: str = ""
    ok: bool = False
    source: Path | None = None
    dest: Path | None = None
    pages_dir: Path | None = None
    sha256: str = ""
    rounds: list = field(default_factory=list)     # index 에 실린 회차 (내림차순)
    created: list = field(default_factory=list)    # 이번에 새로 생긴 파일
    errors: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    git_commands: list = field(default_factory=list)


# --------------------------------------------------------------------------
# 경로
# --------------------------------------------------------------------------
def final_report_path(settings, round_id: str) -> Path:
    """그 회차의 최종 리포트 자리 — `cli._write_report()` 의 기본 경로 규칙
    그대로다 (`output.dir` + `output.filename`). `-o` 로 쓴 파일은 여기에
    오지 않으므로 게시 대상이 될 수 없다."""
    name = (settings.output or {}).get("filename", "toto_{round}.html").format(
        round=round_id)
    return Path(settings.output_dir).joinpath(name)


def _git(args: list, cwd: Path) -> tuple[int, str]:
    """**읽기 전용** git 명령 하나. 실패하면 (코드, 사유)."""
    try:
        proc = subprocess.run(["git", "-C", str(cwd), *args],
                              capture_output=True, encoding="utf-8",
                              errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return proc.returncode, (proc.stdout or proc.stderr or "").strip()


def repo_toplevel(dev_root: Path) -> Path:
    """개발 저장소의 최상위 폴더 — 이름을 적어 두지 않고 git 에 묻는다."""
    code, out = _git(["rev-parse", "--show-toplevel"], dev_root)
    return Path(out) if code == 0 and out else Path(dev_root)


def default_pages_dir(dev_root: Path) -> Path:
    """`<저장소 부모>/<저장소 이름>-pages` (예: sh4 → sh4-pages)."""
    top = repo_toplevel(dev_root).resolve()
    return top.parent.joinpath(top.name + PAGES_SUFFIX)


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def worktree_hint(dev_root: Path, pages_dir: Path) -> str:
    """gh-pages worktree 를 만드는 명령. **개발 브랜치 파일을 싣지 않는
    orphan 브랜치**여야 한다 — `-b gh-pages` 만 주면 지금 HEAD 에서 갈라져
    저장소 전체가 게시 브랜치에 실린다."""
    top = repo_toplevel(dev_root)
    code, _ = _git(["show-ref", "--verify", "--quiet",
                    f"refs/heads/{PAGES_BRANCH}"], top)
    if code == 0:
        return f'git -C "{top}" worktree add "{pages_dir}" {PAGES_BRANCH}'
    code, _ = _git(["show-ref", "--verify", "--quiet",
                    f"refs/remotes/origin/{PAGES_BRANCH}"], top)
    if code == 0:
        return (f'git -C "{top}" worktree add -b {PAGES_BRANCH} "{pages_dir}" '
                f"origin/{PAGES_BRANCH}")
    return (f'git -C "{top}" worktree add --orphan -b {PAGES_BRANCH} '
            f'"{pages_dir}"   (Git 2.42 이상)')


def check_pages_dir(pages_dir: Path, dev_root: Path) -> list[str]:
    """게시 영역이 **개발 작업 트리 밖의 gh-pages worktree** 인지."""
    pages = Path(pages_dir)
    if not pages.is_dir():
        return [f"gh-pages worktree 가 없습니다: {pages} — 먼저 만드십시오: "
                f"{worktree_hint(dev_root, pages)}"]
    rp = pages.resolve()
    rd = repo_toplevel(dev_root).resolve()
    if rp == rd or _inside(rp, rd) or _inside(rd, rp):
        return [f"게시 경로가 개발 저장소와 겹칩니다: {rp} — 게시 파일을 "
                f"개발 작업 트리에 섞지 않습니다."]
    code, top = _git(["rev-parse", "--show-toplevel"], rp)
    if code != 0 or Path(top).resolve() != rp:
        return [f"git worktree 의 최상위 폴더가 아닙니다: {rp} — "
                f"{worktree_hint(dev_root, rp)}"]
    code, branch = _git(["symbolic-ref", "--short", "HEAD"], rp)
    if code != 0 or branch != PAGES_BRANCH:
        return [f"게시 폴더의 브랜치가 {PAGES_BRANCH} 가 아닙니다 "
                f"({branch or '확인 불가'}): {rp}"]
    reports = rp.joinpath(REPORTS_DIRNAME)
    if reports.exists() and not _inside(reports.resolve(), rp):
        return [f"{REPORTS_DIRNAME}/ 가 게시 폴더 밖을 가리킵니다: "
                f"{reports.resolve()}"]
    return []


# --------------------------------------------------------------------------
# 게시 조건
# --------------------------------------------------------------------------
def check_panel_complete(round_id: str, report, *, base: Path | None = None,
                         outdir: Path | None = None, settings=None
                         ) -> tuple[list[str], Path | None]:
    """패널 A·B·C 가 최종 결과에 반영된 상태인가. (오류, Panel Result 경로).

    기존 판정만 읽는다 — `workflow(report=…)` 의 다섯 단계와, 반영 단계의
    체크포인트가 `complete`(1·2·3단계 보관본으로 만든 기록과 일치)인지.
    """
    wf = panelwork.workflow(round_id, base=base, outdir=outdir, report=report,
                            settings=settings)
    errors = [f"{st.title}: {st.state}" + (f" — {st.detail}" if st.detail else "")
              for st in wf.stages if not st.done]
    applied = wf.stage(panelwork.STAGE_APPLY)
    cp = applied.checkpoint if applied is not None else None
    if applied is not None and applied.done and (
            cp is None or cp.state != panelwork.CP_COMPLETE):
        why = "; ".join(cp.reasons) if cp is not None and cp.reasons else \
            "출처 기록이 없습니다"
        errors.append(
            f"{applied.title}: Panel Result 가 1·2·3단계 보관본으로 만들어졌다는 "
            f"기록이 없습니다 ({why}). 사회자 결과만 붙인 반영이거나 옛 파일입니다 — "
            f"`python -m toto --round {round_id} --apply-panel-work` 로 다시 "
            f"반영하십시오.")
    return errors, (applied.path if applied is not None else None)


def check_final_html(path: Path, round_id: str) -> list[str]:
    """정상 HTML 문서이고, 이 회차의 **패널이 붙은** 렌더인가."""
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        return [f"리포트를 읽지 못했습니다: {exc}"]
    if not data.strip():
        return [f"리포트가 비어 있습니다: {path}"]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [f"리포트가 UTF-8 이 아닙니다: {path}"]
    low = text.lstrip("﻿").lstrip().lower()
    errors = []
    if not low.startswith("<!doctype html"):
        errors.append("<!doctype html> 로 시작하지 않습니다")
    missing = [t for t in ("<html", "</html>", "<body", "</body>") if t not in low]
    if missing:
        errors.append("HTML 문서 구조가 아닙니다 (없음: " + ", ".join(missing) + ")")
    m = _TITLE.search(text)
    title = _html.unescape(m.group(1)).strip() if m else ""
    if round_id not in title:
        errors.append(f"제목에 회차 {round_id} 가 없습니다 ({title or '제목 없음'})")
    if render.PANEL_CSS not in text:
        errors.append("패널이 붙지 않은 리포트입니다 — [1] 재수집이나 저장본 "
                      "재렌더가 최종판을 덮어썼을 수 있습니다. "
                      f"`python -m toto --round {round_id} --apply-panel-work` "
                      f"로 다시 반영하십시오.")
    return [f"리포트 검사: {e}" for e in errors]


def check_order(html_path: Path, panel_path: Path | None) -> list[str]:
    """리포트가 Panel Result 보다 **나중에** 만들어졌나 — 반영 뒤 렌더인가."""
    if panel_path is None:
        return []
    try:
        if Path(html_path).stat().st_mtime_ns < Path(panel_path).stat().st_mtime_ns:
            return ["리포트가 Panel Result 보다 오래됐습니다 — 반영 뒤에 리포트가 "
                    "다시 만들어지지 않았습니다."]
    except OSError:
        return []
    return []


# --------------------------------------------------------------------------
# 게시 영역
# --------------------------------------------------------------------------
def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def published_rounds(pages_dir: Path) -> list[str]:
    """게시 영역 `reports/` 바로 아래의 `toto_<숫자>.html` — 내림차순.

    **하위 폴더를 훑지 않는다.** 게시 대상 규칙에 맞는 이름만 센다.
    """
    folder = Path(pages_dir).joinpath(REPORTS_DIRNAME)
    if not folder.is_dir():
        return []
    rounds = [m.group(1) for p in folder.iterdir()
              if (m := PUBLISH_NAME.match(p.name)) and p.is_file()]
    return sorted(rounds, key=lambda r: (int(r), r), reverse=True)


_INDEX_CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1f2328;--muted:#6b6f76;--line:#e3e3df;
  --accent:#2f6fde}
@media (prefers-color-scheme:dark){:root{--bg:#16181b;--card:#1f2226;
  --ink:#e8e8e6;--muted:#9aa0a6;--line:#30343a;--accent:#7aa7ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI","Apple SD Gothic Neo",
  "Malgun Gothic",sans-serif;line-height:1.5}
main{max-width:560px;margin:0 auto;padding:24px 16px 40px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--muted);font-size:14px;margin:0 0 20px}
ul{list-style:none;margin:0;padding:0}
li{margin:0 0 10px}
a.round{display:block;padding:16px 18px;background:var(--card);
  border:1px solid var(--line);border-radius:12px;color:var(--ink);
  text-decoration:none;font-size:18px;font-weight:600;
  font-variant-numeric:tabular-nums}
a.round:active,a.round:hover{border-color:var(--accent);color:var(--accent)}
.empty{padding:18px;border:1px dashed var(--line);border-radius:12px;
  color:var(--muted);text-align:center}
footer{margin-top:28px;color:var(--muted);font-size:12.5px}
"""


def render_index(rounds: list[str]) -> str:
    """회차 목록 페이지. 인라인 CSS 만 — 외부 참조·JavaScript 가 없다."""
    if rounds:
        items = "\n".join(
            f'<li><a class="round" href="{REPORTS_DIRNAME}/toto_{_html.escape(r)}'
            f'.html">{_html.escape(r)}회차</a></li>' for r in rounds)
        body = (f'<p class="sub">게시된 회차 {len(rounds)}개 · 최신 회차가 '
                f'위에 있습니다</p>\n<ul>\n{items}\n</ul>')
    else:
        body = ('<p class="sub">게시된 회차 0개</p>\n'
                '<p class="empty">아직 게시된 리포트가 없습니다.</p>')
    return (
        "<!doctype html>\n"
        '<html lang="ko"><head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{INDEX_TITLE}</title>\n"
        f"<style>{_INDEX_CSS}</style>\n"
        "</head><body><main>\n"
        f"<h1>{INDEX_TITLE}</h1>\n"
        f"{body}\n"
        "<footer>PC 에서 분석을 마친 뒤 게시한 최종 리포트입니다. "
        "판단에 필요한 자료를 모아 보여줄 뿐, 승/무/패를 추천하지 않습니다."
        "</footer>\n"
        "</main></body></html>\n")


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def write_index(pages_dir: Path) -> tuple[list[str], list[str]]:
    """게시 영역의 **실제 파일 목록**으로 index.html 을 다시 만든다.
    (회차 목록, 새로 생긴 파일)."""
    pages = Path(pages_dir)
    created = []
    nojekyll = pages.joinpath(NOJEKYLL_FILE)
    if not nojekyll.exists():
        nojekyll.write_text("", encoding="utf-8")
        created.append(NOJEKYLL_FILE)
    index = pages.joinpath(INDEX_FILE)
    if not index.exists():
        created.append(INDEX_FILE)
    rounds = published_rounds(pages)
    _atomic_write(index, render_index(rounds))
    return rounds, created


def copy_final(src: Path, pages_dir: Path, round_id: str) -> Path:
    """최종 HTML **한 장만** 복사한다. 같은 회차면 그 파일만 바꿔 끼운다."""
    reports = Path(pages_dir).joinpath(REPORTS_DIRNAME)
    reports.mkdir(parents=True, exist_ok=True)
    dest = reports.joinpath(f"toto_{round_id}.html")
    if dest.resolve().parent != reports.resolve():
        raise ValueError(f"게시 경로가 {REPORTS_DIRNAME}/ 밖입니다: {dest}")
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()
    return dest


def git_commands(pages_dir: Path, round_id: str) -> list[str]:
    """사람이 실행할 명령. `git -C` 형태라 cmd · PowerShell 어디서나 같다."""
    q = f'"{Path(pages_dir)}"'
    code, _ = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name",
                    "@{u}"], Path(pages_dir))
    push = (f"git -C {q} push" if code == 0
            else f"git -C {q} push -u origin {PAGES_BRANCH}")
    return [f"git -C {q} status --short",
            f"git -C {q} add {INDEX_FILE} {NOJEKYLL_FILE} "
            f"{REPORTS_DIRNAME}/toto_{round_id}.html",
            f'git -C {q} commit -m "publish: {round_id} report"',
            push]


# --------------------------------------------------------------------------
# 게시
# --------------------------------------------------------------------------
def publish_round(round_id: str, settings, pages_dir: Path | None = None, *,
                  report=None, base: Path | None = None,
                  outdir: Path | None = None) -> PublishResult:
    """검사를 **전부** 통과해야 복사한다. 하나라도 걸리면 아무것도 쓰지 않는다."""
    out = PublishResult(round_id=str(round_id or "").strip())
    rid = out.round_id
    if not ROUND_ID.match(rid):
        out.errors.append(f"회차는 숫자여야 합니다: {rid!r} (DEMO·manual·latest 는 "
                          f"게시 대상이 아닙니다)")
        return out

    dev_root = Path(settings.root)
    src = final_report_path(settings, rid)
    out.source = src
    if not PUBLISH_NAME.match(src.name):
        out.errors.append(f"리포트 이름이 게시 규칙(toto_<회차>.html)과 다릅니다: "
                          f"{src.name} — config_toto.yaml 의 output.filename 확인")
    if not src.is_file():
        out.errors.append(f"최종 리포트가 없습니다: {src} — 먼저 회차 분석과 "
                          f"패널 반영을 끝내십시오.")

    pages = Path(pages_dir) if pages_dir else default_pages_dir(dev_root)
    out.pages_dir = pages
    out.errors += check_pages_dir(pages, dev_root)

    if report is None:
        from . import artifact
        report, why = artifact.load(rid)
        if report is None:
            out.errors.append(f"회차 저장본을 읽지 못해 패널 결과를 확인할 수 "
                              f"없습니다 — {why}")
    panel_path = None
    if report is not None:
        perr, panel_path = check_panel_complete(rid, report, base=base,
                                                outdir=outdir, settings=settings)
        out.errors += perr
    if src.is_file():
        out.errors += check_final_html(src, rid)
        out.errors += check_order(src, panel_path)
    if out.errors:
        return out

    try:
        out.dest = copy_final(src, pages, rid)
    except (OSError, ValueError) as exc:
        out.errors.append(f"복사하지 못했습니다: {exc}")
        return out
    out.sha256 = sha256_of(src)
    if sha256_of(out.dest) != out.sha256:
        out.errors.append("복사본의 SHA-256 이 원본과 다릅니다")
        return out
    out.rounds, out.created = write_index(pages)
    out.git_commands = git_commands(pages, rid)
    out.ok = True
    return out


def report_lines(result: PublishResult) -> list[str]:
    """화면에 낼 줄들."""
    if not result.ok:
        lines = [f"게시하지 않았습니다 — 회차 {result.round_id or '(미상)'}"]
        lines += [f"  ✗ {e}" for e in result.errors]
        lines.append("  gh-pages 게시 영역에는 아무것도 쓰지 않았습니다.")
        return lines
    lines = [f"게시 준비 완료 — 회차 {result.round_id}",
             f"  원본   {result.source}",
             f"  게시본 {result.dest}",
             f"  SHA-256 {result.sha256} (원본과 같음)",
             f"  index.html 재생성 — 게시된 회차 {len(result.rounds)}개: "
             + ", ".join(result.rounds)]
    if result.created:
        lines.append("  새로 만든 파일: " + ", ".join(result.created))
    lines.append("")
    lines.append("git 명령은 실행하지 않았습니다. 확인한 뒤 직접 실행하십시오:")
    lines += [f"  {c}" for c in result.git_commands]
    return lines


__all__ = [
    "PAGES_BRANCH", "REPORTS_DIRNAME", "INDEX_FILE", "NOJEKYLL_FILE",
    "INDEX_TITLE", "PUBLISH_NAME", "PublishResult", "final_report_path",
    "repo_toplevel", "default_pages_dir", "worktree_hint", "check_pages_dir",
    "check_panel_complete", "check_final_html", "check_order",
    "published_rounds", "render_index", "write_index", "copy_final",
    "git_commands", "publish_round", "report_lines", "sha256_of",
]
