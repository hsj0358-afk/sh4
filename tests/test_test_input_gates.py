"""환경에 따라 FAIL 하던 테스트 여섯의 문 (Phase 6-C 후속).

PC 원본 저장소의 전체 실행이 6건 FAIL 이었는데, 깨끗한 작업 트리에서는
그중 셋이 통과했고 기준(e0380fc)·현재(62eed5f) 두 트리가 같은 값으로
실패했다. 코드 회귀가 아니라 **테스트가 입력·환경을 가리지 않은 것**이었다.

  · 실물 저장본 세 건 — 경기 수·다이제스트 상수를 특정 수집본에서 쟀는데
    파일이 **있는지만** 봤다. 다시 수집한 같은 이름의 저장본(라리가
    380경기)에서 FAIL 이 됐다. 이제 입력 sha 가 다르면 SKIP 이다
    (`realdata.require_sha256`) — `test_golden_real.py` 와 같은 규칙이다.
  · 학습 파일 세 건 — 테스트가 운영 파일을 **만들지 않는지**를 보려 했는데
    파일이 **있는지**를 봤다. 실제 수집이 쌓은 정상 파일이 있는 저장소에서
    FAIL 이 됐다. 이제 실행 전후를 견준다 (`prodfiles.changed`).

pytest 없이도 돈다:  python tests/test_test_input_gates.py
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))

import prodfiles                                                 # noqa: E402
import realdata                                                  # noqa: E402

ARTIFACT_TESTS = (
    ("test_continental_collection.py", "test_i2_existing_artifact_still_reads"),
    ("test_qualitative_characteristics.py",
     "test_f3_stored_artifact_keeps_the_notes_it_was_saved_with"),
    ("test_qualitative_characteristics.py",
     "test_f6_real_round_six_axes_are_unchanged"),
)
LEARNED_TESTS = (
    ("test_continental_collection.py", "test_g2_no_learned_files_are_created"),
    ("test_index_isolation.py", "test_j3_learned_files_are_not_created"),
    ("test_strict_resolution.py", "test_f3_production_learned_files_absent"),
)


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="toto-gates-"))


def _skips(fn) -> str:
    try:
        fn()
    except unittest.SkipTest as exc:
        return str(exc)
    raise AssertionError("SKIP 하지 않았다")


def _function(file: str, name: str) -> ast.FunctionDef:
    tree = ast.parse((TESTS / file).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{file}::{name} 가 없다")


def _src(file: str, name: str) -> str:
    return ast.unparse(_function(file, name))


# ==========================================================================
# A. 실물 저장본 — 입력 sha 가 다르면 SKIP
# ==========================================================================
def test_a1_missing_file_still_skips():
    path = _tmp() / "260052.json"
    assert "실물 저장본 없음" in _skips(
        lambda: realdata.require_sha256(path, "0" * 64))


def test_a2_different_content_skips_and_says_why():
    path = _tmp() / "260052.json"
    path.write_bytes(b'{"other": "collection"}')
    why = _skips(lambda: realdata.require_sha256(path, "0" * 64))
    assert "입력 내용이 기준과 다르다" in why, why
    assert hashlib.sha256(path.read_bytes()).hexdigest()[:12] in why, why


def test_a3_same_content_passes_through():
    path = _tmp() / "260052.json"
    path.write_bytes(b"measured")
    sha = hashlib.sha256(b"measured").hexdigest()
    assert realdata.require_sha256(path, sha) == path


def test_a4_load_artifact_does_not_parse_a_different_input():
    """다른 입력이면 읽기 전에 SKIP 이다 — 깨진 JSON 이어도 FAIL 이 아니다."""
    path = _tmp() / "260052.json"
    path.write_bytes(b"not json")
    assert "입력 내용이 기준과 다르다" in _skips(
        lambda: realdata.load_artifact(path, sha256="0" * 64))


def test_a5_load_artifact_without_sha_keeps_old_behaviour():
    """sha 를 주지 않으면 예전 그대로다 — 있는데 못 읽으면 FAIL."""
    path = _tmp() / "260052.json"
    path.write_bytes(b"not json")
    try:
        realdata.load_artifact(path)
    except unittest.SkipTest:
        raise AssertionError("sha 없이 SKIP 했다")
    except AssertionError:
        return
    raise AssertionError("못 읽는 저장본이 통과했다")


def test_a6_measured_sha_matches_the_real_golden_input():
    """기대값을 잰 파일과 실물 골든의 입력이 같은 파일이다 (기준이 둘이 아니다)."""
    golden = json.loads((TESTS / "golden" / "real.json").read_text("utf-8"))
    inputs = golden["rounds"]["260052"]["artifact"]["inputs"]
    assert inputs["data/artifacts/260052.json"] == realdata.ARTIFACT_260052_SHA256


def test_a7_the_three_artifact_tests_are_bound_to_the_measured_input():
    for file, name in ARTIFACT_TESTS:
        src = _src(file, name)
        bound = ("ARTIFACT_260052_SHA256" in src
                 or "_measured_artifact()" in src)
        assert bound, f"{file}::{name} 가 입력 sha 를 보지 않는다"
    helper = _src("test_qualitative_characteristics.py", "_measured_artifact")
    assert "ARTIFACT_260052_SHA256" in helper


# ==========================================================================
# B. 학습 파일 — 실행 중에 생기거나 바뀌었나
# ==========================================================================
def _learned(root: Path) -> Path:
    (root / "data").mkdir(parents=True, exist_ok=True)
    return root / "data" / "teams.learned.yaml"


def test_b1_absent_stays_absent():
    root = _tmp()
    before = prodfiles.snapshot(root)
    assert prodfiles.changed(before, root) == []


def test_b2_created_during_the_run_is_caught():
    root = _tmp()
    before = prodfiles.snapshot(root)
    _learned(root).write_text("aliases: {}\n", encoding="utf-8")
    assert prodfiles.changed(before, root) == [
        "data/teams.learned.yaml 이 생겼다"]


def test_b3_existing_operational_file_is_not_a_failure():
    """PC 원본 저장소의 상태 — 운영 중에 쌓인 파일이 처음부터 있다."""
    root = _tmp()
    _learned(root).write_text("aliases: {x: y}\n", encoding="utf-8")
    before = prodfiles.snapshot(root)
    assert prodfiles.changed(before, root) == []


def test_b4_rewriting_an_existing_file_is_caught():
    root = _tmp()
    path = _learned(root)
    path.write_text("aliases: {x: y}\n", encoding="utf-8")
    before = prodfiles.snapshot(root)
    path.write_text("aliases: {x: z}\n", encoding="utf-8")
    assert prodfiles.changed(before, root) == [
        "data/teams.learned.yaml 이 바뀌었다"]


def test_b5_touching_with_the_same_content_is_caught():
    """같은 내용을 다시 써도 운영 파일을 건드린 것이다."""
    root = _tmp()
    path = _learned(root)
    path.write_text("aliases: {x: y}\n", encoding="utf-8")
    before = prodfiles.snapshot(root)
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert prodfiles.changed(before, root) == [
        "data/teams.learned.yaml 이 바뀌었다"]


def test_b6_deleting_is_caught():
    root = _tmp()
    path = _learned(root)
    path.write_text("aliases: {}\n", encoding="utf-8")
    before = prodfiles.snapshot(root)
    path.unlink()
    assert prodfiles.changed(before, root) == [
        "data/teams.learned.yaml 이 사라졌다"]


def test_b7_the_three_learned_tests_compare_before_and_after():
    for file, name in LEARNED_TESTS:
        src = _src(file, name)
        assert "prodfiles.changed()" in src, f"{file}::{name}"
        assert ".exists()" not in src, f"{file}::{name} 가 아직 존재만 본다"


def test_b8_snapshot_only_reads():
    """기준 시점 기록은 파일을 만들거나 고치지 않는다."""
    tree = ast.parse((TESTS / "prodfiles.py").read_text(encoding="utf-8"))
    calls = {n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    for banned in ("write_text", "write_bytes", "unlink", "mkdir", "touch",
                   "rename", "replace", "rmdir"):
        assert banned not in calls, banned


def main() -> int:
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    sys.exit(main())
