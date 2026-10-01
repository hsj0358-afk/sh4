"""Pages 수동 진입점 둘 — 게시 폴더를 정하는 규칙 (리팩터링 Phase 3-B M11).

    python -m toto --publish-round R      검사·복사·index 까지. git 은 **안내만** 한다
    python -m toto.pagesdeploy R          같은 검사·복사·index 뒤 **commit·push**

두 진입점은 같은 사용자 작업이 아니다 — 앞은 사람이 올라갈 파일을 보고
직접 git 을 치는 경로이고(§1-52), 뒤는 배포까지 하는 경로다(§1-54). 검사·
복사·index 는 이미 `pagespublish.publish_round()` 하나를 함께 쓴다.

게시 폴더를 정하는 규칙이 다르다. M11 에서 **그대로 두기로 판정한 계약**이다.

    --publish-round    --pages-dir → 저장소 옆 <이름>-pages
    pagesdeploy        --pages-dir → SH4_PAGES_DIR → 저장소 옆 <이름>-pages

`SH4_PAGES_DIR` 를 둔 PC 에서 두 명령은 **다른 폴더**를 볼 수 있다. 이 차이를
바꾸려면 이 테스트를 의도적으로 고쳐야 한다. 기존 스위트가 이미 지키는 것
(`pagesdeploy` 의 우선순위 · 폴더 없음 · 변경 없음 · 무관한 변경 · push 실패
· `--publish-round` 의 폴더 검사)은 여기서 다시 적지 않는다.

실제 GitHub 에도, 저장소의 `reports/`·`panel_work/` 에도 쓰지 않는다 —
임시 폴더와 로컬 bare 원격만 쓴다.

    python tests/test_pages_entrypoints.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import cli, pagesdeploy as D, pagespublish as P      # noqa: E402

import test_pages_deploy as PD                                 # noqa: E402
import test_pages_publish as PP                                # noqa: E402

HAS_GIT = shutil.which("git") is not None


def teardown_function(function):   # pytest 가 테스트마다 부른다 (실패해도)
    PP.cleanup_tmpdirs()


def _sibling_pages(dev: Path) -> Path:
    """`dev` 옆 기본 게시 폴더를 **실제 gh-pages 저장소로** 만든다."""
    sibling = P.default_pages_dir(dev)
    assert sibling == dev.parent / (dev.name + P.PAGES_SUFFIX), sibling
    subprocess.run(["git", "init", "-q", "-b", P.PAGES_BRANCH, str(sibling)],
                   check=True)
    PP._CREATED.append(sibling)
    return sibling


def _round(dev: Path):
    r = PP.Round("990071", PP.tmpdir())
    r.write(dev)
    return r


def _publish(r, dev: Path, pages_dir):
    return P.publish_round(r.rid, PP.dev_settings(dev), pages_dir,
                           report=r.report, base=r.base, outdir=r.outdir)


def _deploy(r, dev: Path, pages_dir):
    lines: list = []
    res = D.deploy_round(r.rid, PP.dev_settings(dev), pages_dir,
                         report=r.report, base=r.base, outdir=r.outdir,
                         echo=lines.append)
    return res


# --------------------------------------------------------------------------
# 시나리오 B — SH4_PAGES_DIR 만 있다
# --------------------------------------------------------------------------
def test_b1_publish_round_ignores_the_env_folder():
    if not HAS_GIT:
        return
    dev = PP.tmpdir()
    sibling = _sibling_pages(dev)
    env_pages, _bare = PD.make_repo()
    r = _round(dev)
    with PD.env(**{D.ENV_PAGES_DIR: str(env_pages)}):
        res = _publish(r, dev, None)
    assert res.ok, res.errors
    assert res.pages_dir == sibling, res.pages_dir
    assert "reports/toto_990071.html" in PP.tree(sibling)
    assert PP.tree(env_pages) == [], "환경변수 폴더에 썼다"


def test_b2_pagesdeploy_uses_the_env_folder():
    if not HAS_GIT:
        return
    dev = PP.tmpdir()
    sibling = _sibling_pages(dev)
    env_pages, bare = PD.make_repo()
    r = _round(dev)
    with PD.env(**{D.ENV_PAGES_DIR: str(env_pages)}):
        res = _deploy(r, dev, None)
    assert res.status == D.DEPLOYED, res.reasons
    assert (res.pages_dir, res.pages_dir_from) == (env_pages, D.ENV_PAGES_DIR)
    assert PD.remote_files(bare) == [".nojekyll", "index.html",
                                     "reports/toto_990071.html"]
    assert PP.tree(sibling) == [], "기본 폴더에 썼다"


# --------------------------------------------------------------------------
# 시나리오 D — --pages-dir 와 SH4_PAGES_DIR 가 함께 있다: 둘 다 인자가 이긴다
# --------------------------------------------------------------------------
def test_d1_explicit_folder_wins_for_both():
    if not HAS_GIT:
        return
    dev = PP.tmpdir()
    env_pages = PP.make_pages()
    arg_pages, _bare = PD.make_repo()
    r = _round(dev)
    with PD.env(**{D.ENV_PAGES_DIR: str(env_pages)}):
        pub = _publish(r, dev, arg_pages)
        dep = _deploy(r, dev, arg_pages)
    assert pub.ok and pub.pages_dir == arg_pages, pub.errors
    assert dep.status == D.DEPLOYED, dep.reasons
    assert (dep.pages_dir, dep.pages_dir_from) == (arg_pages, "--pages-dir")
    assert PP.tree(env_pages) == [], "환경변수 폴더에 썼다"


# --------------------------------------------------------------------------
# CLI — 인자를 그대로 넘기고 환경변수를 끼워 넣지 않는다
# --------------------------------------------------------------------------
def test_c1_publish_round_cli_passes_only_the_argument():
    seen: list = []
    real = P.publish_round

    def fake(round_id, settings, pages_dir=None, **kw):
        seen.append((round_id, pages_dir))
        return P.PublishResult(round_id=round_id, errors=["가짜"])

    P.publish_round = fake
    try:
        with PD.env(**{D.ENV_PAGES_DIR: "/somewhere/else"}):
            for argv, want in ((["--publish-round", "990071"], None),
                               (["--publish-round", "990071", "--pages-dir",
                                 "x"], Path("x"))):
                args = cli.build_parser().parse_args(argv)
                assert cli._publish_round(args, PP.dev_settings(
                    PP.tmpdir())) == 1
                assert seen[-1] == ("990071", want), seen[-1]
    finally:
        P.publish_round = real


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
            print(f"  FAIL {fn.__name__}: {type(exc).__name__}: {exc}")
        finally:
            PP.cleanup_tmpdirs()
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
