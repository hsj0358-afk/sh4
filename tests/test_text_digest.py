"""글자의 sha256 — `panelpacket.packet_digest` ↔ `panelwork._sha` (리팩터링 Phase 4 M14).

두 모듈이 **글자까지 같은** 한 줄을 따로 들고 있었다.

    hashlib.sha256((text or "").encode("utf-8")).hexdigest()

둘이 재는 값은 같은 매니페스트(`workflow_manifest.json`)에 나란히 적힌다 —
packet 해시(`packet_sha256`, `packet_digest`)와 보관본 해시(`sha256`·
`depends`, `_sha`). 재개 판정은 둘 다 '그때 잰 값 ↔ 지금 잰 값' 으로
견주므로, 같은 규칙이 두 벌이면 한쪽만 바뀌어도 조용히 어긋난다. 그래서
정의를 하나로 모았다. 의존 방향은 `panelwork → panelpacket` 이다 (`panelpacket` 은 `panel`
과 `models` 만 부르는 아래층이라, 거꾸로 부르면 아래층이 작업 흐름 모듈을
끌어온다).

이 스위트가 지키는 것은 셋이다.

  A. 글자 → 해시가 그대로다. 기대값은 제품 함수로 만들지 않고 `sha256sum`
     으로 따로 계산해 **그대로 적었다** — 같은 함수로 기대값을 만들면 무엇이
     바뀌어도 통과한다. 자르지 않은 64자이고 `None` 은 빈 글자다.
  B. 정의가 한 곳이다 (`panelpacket.packet_digest`). `panelwork._sha` 는
     같은 함수다.
  C. **합치지 않은 해시는 그대로 따로다** — 계약이 다르다.
       `panelwork._file_sha`        파일을 BOM·줄바꿈을 걷어 읽고 잰다
       `pagespublish.sha256_of`     파일 바이트를 그대로 잰다
       `panelexport.instructions_fingerprint`  8자로 자른 지문

A·C 는 통합 전 코드에서도 똑같이 통과해야 한다.

pytest 없이도 돈다:  python tests/test_text_digest.py
"""
from __future__ import annotations

import ast
import inspect
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import pagespublish, panelexport, panelpacket, panelwork  # noqa: E402

FUNCS = (panelpacket.packet_digest, panelwork._sha)

# (입력, 기대 출력). `printf '…' | sha256sum` 으로 따로 계산했다.
CASES = [
    ("", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    ("abc",
     "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
    ("한글 — ✓\n둘째 줄",
     "a4641c12eb03b27a21c9281fffae8077df245ab053d54bf0677f8babeafe9d3c"),
    ("{}", "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"),
]
EMPTY = CASES[0][1]


# ==========================================================================
# A. 값
# ==========================================================================
def test_a1_known_answers():
    for fn in FUNCS:
        for text, want in CASES:
            assert fn(text) == want, (fn.__qualname__, text)


def test_a2_none_is_the_empty_text():
    for fn in FUNCS:
        assert fn(None) == EMPTY, fn.__qualname__


def test_a3_full_length_lowercase_hex():
    for fn in FUNCS:
        got = fn("abc")
        assert len(got) == 64 and got == got.lower(), got


def test_a4_newlines_are_hashed_as_given():
    """글자를 재는 함수다 — `\\r\\n` 과 `\\n` 은 다른 글자다."""
    for fn in FUNCS:
        assert fn("a\r\nb") != fn("a\nb"), fn.__qualname__


# ==========================================================================
# B. 정의는 한 곳
# ==========================================================================
def test_b1_panelwork_uses_the_same_function():
    assert panelwork._sha is panelpacket.packet_digest


def test_b2_panelwork_has_no_second_definition():
    tree = ast.parse(inspect.getsource(panelwork))
    defs = [n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert "_sha" not in defs, "panelwork 가 해시를 다시 정의한다"
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
    assert "hashlib" not in imported, "panelwork 가 hashlib 을 직접 쓴다"


def test_b3_lower_layer_does_not_import_the_workflow_module():
    """`panelpacket` 은 `panelwork` 를 모른다 — 의존은 한 방향이다."""
    tree = ast.parse(inspect.getsource(panelpacket))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names |= {a.name for a in node.names}
            if node.module:
                names.add(node.module.split(".")[-1])
        elif isinstance(node, ast.Import):
            names |= {a.name.split(".")[-1] for a in node.names}
    assert "panelwork" not in names, names


# ==========================================================================
# C. 합치지 않은 해시 — 계약이 다르다
# ==========================================================================
def _scratch() -> Path:
    return Path(tempfile.mkdtemp(prefix="toto_m14_"))


def test_c1_file_sha_reads_text_without_bom_and_crlf():
    path = _scratch() / "x.json"
    path.write_bytes(b"\xef\xbb\xbf{\r\n}")
    assert panelwork._file_sha(path) == panelwork._sha("{\n}")
    assert panelwork._file_sha is not panelpacket.packet_digest


def test_c2_file_sha_of_a_missing_file_is_empty():
    assert panelwork._file_sha(_scratch() / "none.json") == ""


def test_c3_pages_sha_hashes_raw_bytes():
    path = _scratch() / "x.html"
    path.write_bytes(b"\xef\xbb\xbf{}")
    assert pagespublish.sha256_of(path) == (
        "aa25e978046d680ef8740d837e6de5bc1e2a2dc6089dbda1012544b538d53f65")
    assert pagespublish.sha256_of(path) != panelpacket.packet_digest("{}")


def test_c4_instruction_fingerprint_stays_short():
    assert len(panelexport.instructions_fingerprint()) == 8


def main() -> int:
    # 직접 실행 러너는 `tests/_runner.py` 한 곳에 있다 (Phase 3 M13).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    sys.exit(main())
