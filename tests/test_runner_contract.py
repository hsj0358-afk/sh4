"""직접 실행 러너(`tests/_runner.py`)의 계약 (리팩터링 Phase 3 M13).

테스트 파일은 pytest 로도, `python tests/test_xxx.py` 로도 돈다. 52개 파일이
같은 출력을 내는 러너를 저마다 들고 있다가 `_runner.run_tests()` 하나를
부르게 됐다. 이 스위트가 지키는 것은 **사람이 보는 결과**다.

  A. 출력 글자와 종료코드 — ok · SKIP · FAIL · ERR 네 줄과 요약
  B. SKIP 은 PASS 도 FAIL 도 아니다 (`realdata.SkipTest` = `unittest.SkipTest`)
  C. 직접 실행 — 저장소 루트 · 저장소 밖(절대 경로) · `python -m tests.…`
  D. 다른 테스트가 import 해도 아무것도 실행되지 않는다

기대 출력은 M13 이전 러너가 같은 입력에 낸 글자다 (조사 때 대조했다).

pytest 없이도 돈다:  python tests/test_runner_contract.py
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import realdata                                                 # noqa: E402
from _runner import run_tests                                   # noqa: E402

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
SAMPLE = TESTS / "test_xpts.py"          # 공통 러너를 쓰는 빠른 파일 하나
_SUMMARY = re.compile(r"^(\d+)/\1 통과$")


def _fn(name: str, kind: str = "ok"):
    def f():
        if kind == "skip":
            realdata.require(Path("/no/such/artifact.json"))
        if kind == "fail":
            # `assert` 문을 쓰지 않는다 — pytest 가 이 모듈의 assert 를 다시
            # 써서 메시지에 식을 덧붙이므로 두 실행 방식의 글자가 달라진다.
            raise AssertionError("틀림")
        if kind == "err":
            raise ValueError("터짐")
    f.__name__ = name
    return f


def _run(**kinds) -> tuple[int, str]:
    ns = {n: _fn(n, k) for n, k in kinds.items()}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run_tests(ns)
    return rc, buf.getvalue()


def _direct(argv: list, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, *argv], cwd=cwd, capture_output=True,
                          text=True, env=env, timeout=300)


# --------------------------------------------------------------------------
# A. 출력과 종료코드
# --------------------------------------------------------------------------
def test_a1_all_pass():
    assert _run(test_a="ok", test_b="ok") == (
        0, "  ok   test_a\n  ok   test_b\n\n2/2 통과\n")


def test_a2_failure_and_error_are_separate_lines():
    rc, out = _run(test_a="ok", test_b="fail", test_c="err")
    assert rc == 1
    assert out == ("  ok   test_a\n  FAIL test_b: 틀림\n"
                   "  ERR  test_c: ValueError: 터짐\n\n1/3 통과\n"), out


def test_a3_only_test_functions_in_name_order():
    ns = {"test_b": _fn("test_b"), "test_a": _fn("test_a"),
          "helper": _fn("helper", "fail"), "test_value": 3}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert run_tests(ns) == 0
    assert buf.getvalue() == "  ok   test_a\n  ok   test_b\n\n2/2 통과\n"


# --------------------------------------------------------------------------
# B. SKIP 은 PASS 도 FAIL 도 아니다
# --------------------------------------------------------------------------
def test_b1_skip_is_counted_apart():
    rc, out = _run(test_a="ok", test_b="skip", test_c="fail", test_d="err")
    assert rc == 1, "실패가 있으면 1"
    lines = out.splitlines()
    assert lines[1].startswith("  SKIP test_b: 실물 저장본 없음"), lines[1]
    assert lines[-1] == "1/3 통과 · 건너뜀 1", lines[-1]


def test_b2_only_skips_is_not_a_failure():
    rc, out = _run(test_b="skip")
    assert rc == 0
    assert out.splitlines()[-1] == "0/0 통과 · 건너뜀 1"


def test_b3_realdata_skip_is_unittest_skip():
    assert realdata.SkipTest is unittest.SkipTest


# --------------------------------------------------------------------------
# C. 직접 실행
# --------------------------------------------------------------------------
def test_c1_direct_run_from_repo_root():
    r = _direct([str(SAMPLE.relative_to(REPO))], REPO)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _SUMMARY.match(r.stdout.splitlines()[-1]), r.stdout[-200:]


def test_c2_direct_run_from_outside_with_absolute_path():
    inside = _direct([str(SAMPLE)], REPO)
    outside = _direct([str(SAMPLE)], Path(tempfile.mkdtemp()))
    assert outside.returncode == 0, outside.stdout + outside.stderr
    assert outside.stdout == inside.stdout


def test_c3_module_mode_still_runs():
    r = _direct(["-m", f"tests.{SAMPLE.stem}"], REPO)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _SUMMARY.match(r.stdout.splitlines()[-1]), r.stdout[-200:]


# --------------------------------------------------------------------------
# D. import 는 아무것도 실행하지 않는다
# --------------------------------------------------------------------------
def test_d1_importing_a_test_module_runs_nothing():
    code = (f"import sys; sys.path[:0] = [{str(REPO)!r}, {str(TESTS)!r}]; "
            f"import {SAMPLE.stem}")
    r = _direct(["-c", code], REPO)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "", r.stdout


def test_d2_runner_module_is_not_collected():
    """`_runner.py` 는 `test_*.py` 가 아니고 테스트 함수도 없다."""
    import _runner
    assert not [n for n in vars(_runner) if n.startswith("test_")]


def main() -> int:
    # 직접 실행 러너는 `tests/_runner.py` 한 곳에 있다 (Phase 3 M13).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _runner import run_tests as _run_tests
    return _run_tests(globals())


if __name__ == "__main__":
    sys.exit(main())
