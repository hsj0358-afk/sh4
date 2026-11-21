"""패널 파일의 canonical 바이트 — 윈도우에서도 LF (리팩터링 Phase 4 M17).

패널 단계의 파일을 쓰는 곳이 셋이다.

    panelpaste.write_canonical()   panel_results/<회차>_panel_result.json
    panelwork._atomic_write()      panel_work/<회차>/*.json · 매니페스트 ·
                                   03_사회자자료_완성.md
    panelpacket.write_cache()      panel_cache/<회차>/*.json

앞의 둘이 텍스트 모드 기본값(`newline=None`)으로 썼다. 그 기본값은 윈도우
에서 `\\n` 을 `\\r\\n` 으로 바꿔 쓰므로, 같은 자료가 OS 마다 다른 바이트가
됐다. 매니페스트의 sha256 은 LF 글자로 잰 값이라(`_sha(payload)`, 그리고
줄바꿈을 걷어 읽는 `_file_sha`) 윈도우 파일의 바이트와 어긋났다 — 윈도우
PC 의 `test_panel_apply.test_e2`·`test_j1` 실패가 이것이다.

이 스위트는 윈도우 텍스트 모드를 **흉내 내** 리눅스에서도 그 계약을 본다.
흉내는 `open` 이 `newline` 을 받지 않았을 때만 `\\r\\n` 을 쓰게 하는 것이고,
제품 코드는 바꾸지 않는다.

  A. 두 writer 의 바이트가 넘겨받은 글자의 UTF-8 그대로다 (흉내 안팎 모두).
  B. 매니페스트의 sha256 이 실제 파일 바이트의 sha256 과 같다.
  C. 원자적 교체·fsync·임시 파일 자리는 그대로다.
  D. `panelpacket` 캐시는 줄바꿈 바이트가 아예 없어 손대지 않았다 — 그
     전제가 맞는지 본다.

pytest 없이도 돈다:  python tests/test_canonical_bytes.py
"""
from __future__ import annotations

import builtins
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import panelpacket, panelpaste, panelwork               # noqa: E402

CR = b"\r"

# 넘겨줄 글자. 한글·여러 줄·끝 줄바꿈 없음 — 실제 보관본 모양이다.
DATA = {"schema_version": "1.1", "round": "M17",
        "matches": [{"match_number": 1, "summary": "첫 줄\n둘째 줄"},
                    {"match_number": 2, "summary": "한글 — ✓"}]}


def scratch() -> Path:
    return Path(tempfile.mkdtemp(prefix="toto_m17_"))


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@contextlib.contextmanager
def windows_text_mode():
    """윈도우 텍스트 모드 기본값을 흉내 낸다 — `newline` 을 안 주면 CRLF.

    `builtins.open`(panelwork 의 `open`)과 `io.open`(pathlib 의
    `write_text`)을 둘 다 바꾸고, 나가면 되돌린다.
    """
    real_builtin, real_io = builtins.open, io.open

    def fake(file, mode="r", buffering=-1, encoding=None, errors=None,
             newline=None, closefd=True, opener=None):
        if newline is None and "b" not in mode and any(c in mode for c in "wax+"):
            newline = "\r\n"
        return real_io(file, mode, buffering, encoding, errors, newline,
                       closefd, opener)

    builtins.open = io.open = fake
    try:
        yield
    finally:
        builtins.open, io.open = real_builtin, real_io


def test_a0_the_simulation_really_writes_crlf():
    """흉내가 실제로 CRLF 를 쓴다 — 아니면 아래 시험이 성립하지 않는다."""
    path = scratch() / "probe.txt"
    with windows_text_mode():
        path.write_text("a\nb\n", encoding="utf-8")
    assert path.read_bytes() == b"a\r\nb\r\n", path.read_bytes()


# ==========================================================================
# A. 바이트
# ==========================================================================
def test_a1_write_canonical_bytes_are_lf_everywhere():
    want = json.dumps(DATA, ensure_ascii=False, indent=1).encode("utf-8")
    assert b"\n" in want                     # 줄바꿈이 있는 글자다
    for simulate in (False, True):
        base = scratch()
        with (windows_text_mode() if simulate else contextlib.nullcontext()):
            path = panelpaste.write_canonical(DATA, "M17", base)
        raw = path.read_bytes()
        assert CR not in raw, ("CR 이 섞였다", simulate)
        assert raw == want, simulate
        assert path == panelpaste.canonical_path("M17", base)


def test_a2_atomic_write_keeps_the_payload_bytes():
    payloads = [
        json.dumps(DATA, ensure_ascii=False, indent=1),
        "# 사회자 자료\n\n| 경기 | 값 |\n|---|---|\n| 1 | 2-1 |\n",
        "끝 줄바꿈 없음",
        "",
    ]
    for simulate in (False, True):
        for payload in payloads:
            path = scratch() / "sub" / "x.json"
            with (windows_text_mode() if simulate
                  else contextlib.nullcontext()):
                panelwork._atomic_write(path, payload)
            assert path.read_bytes() == payload.encode("utf-8"), (
                simulate, payload[:20])


def test_a3_crlf_in_the_payload_is_not_doubled():
    """받은 글자에 이미 `\\r\\n` 이 있어도 `\\r\\r\\n` 이 되지 않는다."""
    payload = "윈도우에서 붙여넣은 줄\r\n다음 줄\r\n"
    path = scratch() / "x.json"
    with windows_text_mode():
        panelwork._atomic_write(path, payload)
    assert path.read_bytes() == payload.encode("utf-8")


def test_a4_no_bom():
    for simulate in (False, True):
        base = scratch()
        with (windows_text_mode() if simulate else contextlib.nullcontext()):
            canon = panelpaste.write_canonical(DATA, "M17", base)
            panelwork._atomic_write(base / "y.json", "{}")
        for path in (canon, base / "y.json"):
            assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


# ==========================================================================
# B. 매니페스트의 sha256 = 실제 파일 바이트의 sha256
# ==========================================================================
def test_b1_recorded_sha_matches_the_file_bytes():
    """`_sha(payload)` 로 적은 값과 파일 바이트의 해시가 같다.

    윈도우에서 어긋났던 자리다 — 기록은 LF 글자로 재고 파일은 CRLF 였다.
    """
    payload = json.dumps(DATA, ensure_ascii=False, indent=1)
    for simulate in (False, True):
        path = scratch() / "a.json"
        with (windows_text_mode() if simulate else contextlib.nullcontext()):
            panelwork._atomic_write(path, payload)
        raw = path.read_bytes()
        assert sha(raw) == panelwork._sha(payload), simulate
        assert sha(raw) == panelwork._file_sha(path), simulate


def test_b2_canonical_file_sha_matches_its_bytes():
    for simulate in (False, True):
        base = scratch()
        with (windows_text_mode() if simulate else contextlib.nullcontext()):
            path = panelpaste.write_canonical(DATA, "M17", base)
        assert sha(path.read_bytes()) == panelwork._file_sha(path), simulate


def test_b3_old_crlf_files_still_hash_the_same():
    """이미 CRLF 로 쓰인 옛 윈도우 파일도 기록과 맞는다 — `_file_sha` 는
    줄바꿈을 걷어 읽으므로 이 변경이 옛 매니페스트를 무효로 만들지 않는다."""
    payload = json.dumps(DATA, ensure_ascii=False, indent=1)
    old = scratch() / "old.json"
    old.write_bytes(payload.replace("\n", "\r\n").encode("utf-8"))
    new = scratch() / "new.json"
    panelwork._atomic_write(new, payload)
    assert panelwork._file_sha(old) == panelwork._file_sha(new) \
        == panelwork._sha(payload)


# ==========================================================================
# C. 원자적 교체 · fsync · 임시 파일
# ==========================================================================
def _replaces(fn):
    seen, real = [], os.replace

    def spy(src, dst):
        seen.append((Path(src), Path(dst)))
        return real(src, dst)

    os.replace = spy
    try:
        fn()
    finally:
        os.replace = real
    return seen


def test_c1_atomic_write_replaces_from_a_sibling_tmp_and_fsyncs():
    path = scratch() / "deep" / "x.json"
    synced, real_fsync = [], os.fsync
    os.fsync = lambda fd: synced.append(fd)
    try:
        seen = _replaces(lambda: panelwork._atomic_write(path, "{}"))
    finally:
        os.fsync = real_fsync
    assert seen == [(path.with_name("x.json.tmp"), path)], seen
    assert len(synced) == 1, "fsync 를 한 번 하지 않았다"
    assert not path.with_name("x.json.tmp").exists()


def test_c2_write_canonical_replaces_from_a_sibling_tmp():
    base = scratch()
    target = panelpaste.canonical_path("M17", base)
    seen = _replaces(lambda: panelpaste.write_canonical(DATA, "M17", base))
    assert seen == [(target.with_name(target.name + ".tmp"), target)], seen
    assert not target.with_name(target.name + ".tmp").exists()


def test_c3_failed_write_leaves_the_old_file():
    """쓰다 실패하면 바꿔 끼우지 않는다 — 앞서 있던 파일이 그대로다."""
    path = scratch() / "x.json"
    path.write_bytes(b'{"old":1}')
    try:
        panelwork._atomic_write(path, object())          # 글자가 아니다
    except TypeError:
        pass
    else:
        raise AssertionError("글자가 아닌 것을 썼다")
    assert path.read_bytes() == b'{"old":1}'


# ==========================================================================
# D. panelpacket — 손대지 않은 이유
# ==========================================================================
def test_d1_packet_cache_has_no_newline_bytes():
    """compact JSON 은 줄바꿈을 escape 한다 — 텍스트 모드가 바꿀 것이 없다."""
    import test_panel_auto as auto
    for simulate in (False, True):
        base = scratch()
        with (windows_text_mode() if simulate else contextlib.nullcontext()):
            out = panelpacket.write_cache(auto.demo_index(2), base)
        names = sorted(p.name for p in out.iterdir())
        assert names, "캐시를 쓰지 않았다"
        for p in out.iterdir():
            raw = p.read_bytes()
            assert b"\n" not in raw and CR not in raw, (simulate, p.name)


def main() -> int:
    # 직접 실행 러너는 `tests/_runner.py` 한 곳에 있다 (Phase 3 M13).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    sys.exit(main())
