"""pytest 전용 — 테스트가 만든 임시 폴더를 세션 끝에 **한 번에** 지운다.

스위트 대부분이 `tempfile.mkdtemp()` 로 저장소 밖 폴더를 만들고 지우지 않는다.
한 파일씩 스크립트로 돌릴 때는 티가 나지 않지만 `python -m pytest -q` 한 번이
시스템 임시 폴더에 **456개 항목 · 34 MB** 를 남겼다 (실측). 테스트를 하나하나
고치면 65개 파일을 건드리게 되므로, 세션 동안 임시 폴더의 뿌리를 한 곳으로
모으고 끝나면 그 한 곳만 지운다.

  · 뿌리는 여전히 **저장소 밖**(시스템 임시 폴더 아래)이다. 패널 자동 실행의
    작업 폴더가 저장소 `CLAUDE.md` 를 피하려고 OS 임시 폴더를 쓰는데(§1-45),
    그 전제를 바꾸지 않는다.
  · 자식 프로세스(`python -m toto …`)도 같은 뿌리를 쓰도록 `TMPDIR`·`TEMP`·
    `TMP` 를 함께 맞추고, 끝나면 원래 값으로 되돌린다.
  · 스크립트 실행(`python tests/test_x.py`)에는 **아무 영향이 없다** — 이 파일은
    pytest 만 읽는다.
  · 테스트 코드도 제품 코드도 바꾸지 않는다.
"""
from __future__ import annotations

import os
import shutil
import tempfile

_ENV_KEYS = ("TMPDIR", "TEMP", "TMP")
_SAVED_ENV = {key: os.environ.get(key) for key in _ENV_KEYS}
_SAVED_TEMPDIR = tempfile.tempdir

# 테스트 모듈이 **import 되는 순간**에도 임시 폴더를 만드는 것이 있어
# 훅이 아니라 conftest 가 읽히는 시점에 바로 옮긴다 (이 파일이 먼저 읽힌다).
SESSION_TMP = tempfile.mkdtemp(prefix="toto-pytest-")
tempfile.tempdir = SESSION_TMP
for _key in _ENV_KEYS:
    os.environ[_key] = SESSION_TMP


def pytest_sessionfinish(session, exitstatus):          # noqa: ARG001
    """원래 임시 폴더 설정으로 되돌리고 세션 뿌리를 지운다."""
    tempfile.tempdir = _SAVED_TEMPDIR
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    # 지우지 못한 것(열린 파일 등)이 있어도 테스트 결과를 바꾸지 않는다.
    shutil.rmtree(SESSION_TMP, ignore_errors=True)
