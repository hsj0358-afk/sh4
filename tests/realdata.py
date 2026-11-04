"""실물 저장본이 필요한 테스트를 **보이게** 건너뛴다 (리팩터링 Phase 1).

`data/artifacts/` 는 gitignore 대상이라(§1-16) 새로 클론한 PC 나 CI 에는
실물 저장본이 없다. 그때 여섯 스위트가 테스트 함수 안에서 `return` 해 버려
**통과로 세어졌다** — 실물 회귀가 한 건도 돌지 않았는데 결과는 전부 초록이었다.

이제 두 가지를 가른다.

  · 파일이 **없으면** SKIP 이다 — 그 환경에서는 확인할 수 없다는 사실을 센다.
  · 파일이 **있는데 못 읽으면** FAIL 이다 — 그건 확인할 수 없는 것이 아니라
    회귀다. 예전에는 이것도 조용히 지나갔다(`report is None` → `return`).

pytest 는 `unittest.SkipTest` 를 skip 으로 센다(`-rs` 로 사유가 보인다).
스크립트 실행은 각 파일의 `main()` 이 `SkipTest` 를 받아 SKIP 줄을 찍고
따로 센다. pytest 가 없어도 돈다 — 표준 라이브러리만 쓴다.
"""
from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_260052 = ROOT / "data" / "artifacts" / "260052.json"

# 실물 내용을 상수로 고정한 테스트들(경기 수·다이제스트)이 기대값을 잰
# 260052 저장본. `tests/golden/real.json` 의 260052 입력 sha 와 같은 파일이다.
# 라싱 산탄데르 등록 **전** 수집본이라 라리가가 342경기다(§1-26). 그 뒤
# 다시 수집한 저장본(라리가 380경기, §3-10)은 다른 자료이므로 그 값과
# 견주지 않고 SKIP 한다 — 옛 자료로 되돌려 맞추는 것이 답이 아니다.
ARTIFACT_260052_SHA256 = (
    "92139c1eb98e60b1f54e61e6f1196de08dc41b4db01b1455ceb00b99c37f51fe")

SkipTest = unittest.SkipTest


def _shown(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def require(path: Path = ARTIFACT_260052) -> Path:
    """없으면 SKIP. 있으면 경로를 그대로 돌려준다."""
    path = Path(path)
    if not path.exists():
        raise SkipTest(f"실물 저장본 없음 — {_shown(path)} (gitignore 대상, "
                       f"이 환경에서는 확인하지 않았다)")
    return path


def require_sha256(path: Path, expected: str) -> Path:
    """없거나 **내용이 기준과 다르면** SKIP. 같으면 경로를 돌려준다.

    실물 내용을 상수로 고정한 테스트는 그 상수를 잰 파일에서만 의미가 있다.
    `require()` 는 있는지만 보므로, 다른 PC 에서 다시 수집한 같은 이름의
    저장본에서 그런 테스트가 FAIL 이 됐다(회귀가 아니라 입력이 다른 것).
    `tests/test_golden_real.py` 가 입력 sha 로 가르는 것과 같은 규칙이다.
    """
    path = require(path)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise SkipTest(f"입력 내용이 기준과 다르다 — {_shown(path)} "
                       f"sha256 {actual[:12]} (기준 {expected[:12]})")
    return path


def load_artifact(path: Path = ARTIFACT_260052, sha256: str | None = None):
    """없으면 SKIP, 못 읽으면 FAIL, 읽히면 Report.

    `sha256` 을 주면 내용이 그 파일과 다를 때도 SKIP 이다.
    """
    from toto import artifact
    path = require_sha256(path, sha256) if sha256 else require(path)
    report, why = artifact.load_path(path)
    assert report is not None, (f"실물 저장본을 읽지 못했습니다 — "
                                f"{_shown(Path(path))}: {why}")
    return report
