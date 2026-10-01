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

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_260052 = ROOT / "data" / "artifacts" / "260052.json"

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


def load_artifact(path: Path = ARTIFACT_260052):
    """없으면 SKIP, 못 읽으면 FAIL, 읽히면 Report."""
    from toto import artifact
    report, why = artifact.load_path(require(path))
    assert report is not None, (f"실물 저장본을 읽지 못했습니다 — "
                                f"{_shown(Path(path))}: {why}")
    return report
