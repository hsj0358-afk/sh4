"""GitHub Pages 의 git 실행 함수 둘 — 계약 고정 (리팩터링 Phase 3 M6).

`pagespublish._git`(게시 판정용 **읽기**)과 `pagesdeploy.run_git`(배포용
**쓰기**)은 명령 모양(`git -C <폴더> …`)과 출력 해독(UTF-8 · 깨진 바이트는
대체)만 같고 나머지는 **일부러** 다르다.

    |              | pagespublish._git          | pagesdeploy.run_git              |
    |--------------|----------------------------|----------------------------------|
    | 쓰는 명령     | rev-parse · symbolic-ref · show-ref | status · add · commit · rev-parse · rev-list · push · remote |
    | 시간 제한     | 20초 고정                   | 60초 (push 300초)                 |
    | 표준입력      | 물려받는다                  | DEVNULL                          |
    | 환경변수      | 그대로                      | + GIT_TERMINAL_PROMPT=0          |
    | 시간 초과     | (1, 파이썬 예외 문장)        | 종료코드 124 · 한국어 사유         |
    | 돌려주는 것   | (코드, stdout 없으면 stderr, strip) | GitCall (stdout·stderr 따로, 그대로) |
    | 바꿔 끼우기   | 없음                        | `deploy_round(git=…)`            |

두 함수를 하나로 묶으면 위 표의 차이가 전부 매개변수가 되고, `pagespublish`
의 유일한 실행 자리가 모듈 밖으로 나간다 — `test_pages_publish.test_g1`
("실행은 `_git` 안의 한 곳뿐") 이 지키는 읽기 전용 경계가 그 자리다. 그래서
M6 은 **합치지 않았다.** 이 스위트는 지금의 두 계약을 따로 고정한다.

pytest 없이도 돈다:  python tests/test_pages_git_wrappers.py
"""
from __future__ import annotations

import ast
import inspect
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import pagesdeploy as D                                # noqa: E402
from toto import pagespublish as P                               # noqa: E402

HAS_GIT = shutil.which("git") is not None
_PASSED = _FAILED = 0


def check(name, fn):
    global _PASSED, _FAILED
    try:
        fn()
    except Exception as exc:                                 # noqa: BLE001
        _FAILED += 1
        print(f"  ✗ {name}: {type(exc).__name__}: {exc}")
    else:
        _PASSED += 1
        print(f"  ✓ {name}")


class _FakeRun:
    """`subprocess.run` 자리에 끼워 인자를 기록한다. 실제 git 을 부르지 않는다."""

    def __init__(self, *, result=None, raises=None):
        self.result, self.raises = result, raises
        self.calls: list[tuple[list, dict]] = []

    def __call__(self, argv, **kw):
        self.calls.append((list(argv), dict(kw)))
        if self.raises is not None:
            raise self.raises
        return self.result


def _with_fake(fake, fn):
    saved = subprocess.run
    subprocess.run = fake
    try:
        return fn()
    finally:
        subprocess.run = saved


def _done(code=0, out="", err=""):
    return subprocess.CompletedProcess(["git"], code, out, err)


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="m6git-"))


# --------------------------------------------------------------------------
# A. pagespublish._git — 읽기 전용
# --------------------------------------------------------------------------
def test_a1_publish_git_command_and_options():
    fake = _FakeRun(result=_done(0, "x\n"))
    cwd = Path("/게시 폴더")
    _with_fake(fake, lambda: P._git(["rev-parse", "--show-toplevel"], cwd))
    [(argv, kw)] = fake.calls
    assert argv == ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"]
    fixed = {k: kw.pop(k, "(없음)") for k in
             ("capture_output", "encoding", "errors", "timeout")}
    assert fixed == {"capture_output": True, "encoding": "utf-8",
                     "errors": "replace", "timeout": 20}, fixed
    # 표준입력·환경변수는 **물려받는다** (안 주거나 None — `subprocess.run`
    # 에서 둘은 같다). shell·check 는 쓰지 않는다.
    for key in ("stdin", "env"):
        assert kw.pop(key, None) is None, (key, kw)
    assert not kw.pop("shell", False) and not kw.pop("check", False)
    assert not kw, f"모르는 인자: {kw}"


def test_a2_publish_git_returns_code_and_one_stripped_text():
    cases = [
        (_done(0, "  gh-pages\n", "경고\n"), (0, "gh-pages")),   # stdout 우선
        (_done(128, "", "fatal: 없음\n"), (128, "fatal: 없음")),  # 없으면 stderr
        (_done(1, None, None), (1, "")),
        (_done(0, "", ""), (0, "")),
    ]
    for proc, want in cases:
        got = _with_fake(_FakeRun(result=proc),
                         lambda: P._git(["show-ref"], Path(".")))
        assert got == want, (proc, got)


def test_a3_publish_git_turns_errors_into_code_1():
    for exc in (subprocess.TimeoutExpired(["git"], 20),
                FileNotFoundError(2, "git 없음"),
                PermissionError(13, "권한 없음")):
        got = _with_fake(_FakeRun(raises=exc),
                         lambda: P._git(["rev-parse"], Path(".")))
        assert got == (1, str(exc)), (exc, got)


def test_a4_publish_git_real_repo_and_non_repo():
    if not HAS_GIT:
        return
    repo = _tmp()
    subprocess.run(["git", "init", "-q", "-b", P.PAGES_BRANCH, str(repo)],
                   check=True)
    code, top = P._git(["rev-parse", "--show-toplevel"], repo)
    assert code == 0 and Path(top).resolve() == repo.resolve(), (code, top)
    code, branch = P._git(["symbolic-ref", "--short", "HEAD"], repo)
    assert (code, branch) == (0, P.PAGES_BRANCH)
    code, text = P._git(["rev-parse", "--show-toplevel"], _tmp())
    assert code != 0 and text.startswith("fatal:"), (code, text)


# --------------------------------------------------------------------------
# B. pagesdeploy.run_git — 쓰기
# --------------------------------------------------------------------------
def test_b1_deploy_git_command_and_options():
    fake = _FakeRun(result=_done(0))
    cwd = Path("/게시 폴더")
    _with_fake(fake, lambda: D.run_git(["status", "--porcelain"], cwd))
    _with_fake(fake, lambda: D.run_git(["push", "origin", "gh-pages"], cwd,
                                       timeout=D.PUSH_TIMEOUT))
    (argv, kw), (argv2, kw2) = fake.calls
    assert argv == ["git", "-C", str(cwd), "status", "--porcelain"]
    assert argv2 == ["git", "-C", str(cwd), "push", "origin", "gh-pages"]
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    want = {"capture_output": True, "encoding": "utf-8", "errors": "replace",
            "timeout": 60, "stdin": subprocess.DEVNULL, "env": env}
    assert kw == want, kw
    assert kw2 == dict(want, timeout=300), kw2
    assert (D.GIT_TIMEOUT, D.PUSH_TIMEOUT) == (60, 300)


def test_b2_deploy_git_keeps_both_streams_as_they_are():
    args = ["commit", "-m", "m"]
    got = _with_fake(_FakeRun(result=_done(1, " out \n", " err \n")),
                     lambda: D.run_git(args, Path(".")))
    assert got == D.GitCall(args, 1, " out \n", " err \n"), got
    assert got.args is not args, "인자 목록을 그대로 들고 있다"
    assert got.output == "out\nerr"
    none = _with_fake(_FakeRun(result=_done(0, None, None)),
                      lambda: D.run_git(["status"], Path(".")))
    assert (none.stdout, none.stderr, none.output) == ("", "", "")


def test_b3_deploy_git_turns_errors_into_codes():
    got = _with_fake(_FakeRun(raises=subprocess.TimeoutExpired(["git"], 300)),
                     lambda: D.run_git(["push", "origin"], Path("."),
                                       timeout=300))
    assert got == D.GitCall(["push", "origin"], 124, "",
                            "git push 이 300초 안에 끝나지 않았습니다"), got
    exc = FileNotFoundError(2, "git 없음")
    got = _with_fake(_FakeRun(raises=exc),
                     lambda: D.run_git(["add", "--", "a"], Path(".")))
    assert got == D.GitCall(["add", "--", "a"], 1, "", str(exc)), got


def test_b4_deploy_git_real_non_repo():
    if not HAS_GIT:
        return
    got = D.run_git(["status", "--porcelain"], _tmp())
    assert got.code != 0 and got.stdout == "", got
    assert got.stderr.startswith("fatal:"), got


# --------------------------------------------------------------------------
# C. 경계 — 실행 자리와 쓰기 책임
# --------------------------------------------------------------------------
_LAUNCH = ("run", "Popen", "call", "check_call", "check_output")


def _launch_sites(mod) -> list[str]:
    """subprocess 를 띄우는 호출이 **어느 함수 안에** 있는가."""
    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        for n in ast.walk(fn):
            if isinstance(n, ast.Attribute) and n.attr in _LAUNCH \
                    and isinstance(n.value, ast.Name) \
                    and n.value.id == "subprocess":
                out.append(fn.name)
    return out


def test_c1_each_module_launches_git_in_exactly_one_function():
    assert _launch_sites(P) == ["_git"], _launch_sites(P)
    assert _launch_sites(D) == ["run_git"], _launch_sites(D)


def test_c2_writes_go_through_the_injectable_deploy_runner():
    for fn in (D.deploy_round, D.auto_deploy):
        assert inspect.signature(fn).parameters["git"].default is D.run_git
    src = Path(D.__file__).read_text(encoding="utf-8")
    assert "pagespublish._git" not in src, "배포가 게시 모듈의 읽기 함수를 쓴다"
    assert "import pagesdeploy" not in Path(P.__file__).read_text(
        encoding="utf-8").replace("\n", " ")


def test_c3_publish_git_is_never_given_a_write_verb():
    """`pagespublish` 의 `_git(...)` 첫 인자는 읽기 명령뿐이다."""
    tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
    verbs = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id == "_git":
            verbs.add(n.args[0].elts[0].value)
    assert verbs == {"rev-parse", "symbolic-ref", "show-ref"}, verbs


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
