"""운영 학습 파일이 **테스트 실행 중에** 생기거나 바뀌지 않았는지 본다.

`data/teams.learned.yaml`·`data/teams.league.yaml` 은 실제 수집이 쌓는 운영
자료다(§1-6-1 · §3-5, gitignore 대상). 예전 세 테스트는 파일이 **있는지**만
봤다. 그래서 그 파일을 정상적으로 가진 PC 의 원본 저장소에서는 테스트가
아무것도 만들지 않았는데도 FAIL 이 됐고, 깨끗한 작업 트리에서는 통과했다.
지키려던 것은 '테스트가 운영 파일을 만들지 않는다' 이므로 실행 전후를 견준다.

**기준 시점은 이 모듈이 처음 import 될 때다.** pytest 는 테스트를 돌리기
전에 모든 테스트 모듈을 먼저 import 하고, 스크립트 실행도 `main()` 앞에서
import 하므로, 이 시점은 어느 테스트보다 앞선다.

  · 처음에 없던 파일은 끝까지 없어야 한다 — 예전 검사와 같다.
  · 처음에 있던 파일은 내용과 수정 시각이 그대로여야 한다. 테스트가 같은
    내용을 다시 써도 운영 파일을 건드린 것이므로 잡는다.
  · 파일을 지우거나 고치지 않는다. 읽기만 한다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = ("teams.learned.yaml", "teams.league.yaml")


def _state(path: Path):
    if not path.exists():
        return None
    st = path.stat()
    return (hashlib.sha256(path.read_bytes()).hexdigest(), st.st_mtime_ns)


def snapshot(root: Path = ROOT) -> dict[str, tuple | None]:
    return {name: _state(root / "data" / name) for name in NAMES}


BEFORE = snapshot()


def changed(before: dict | None = None, root: Path = ROOT) -> list[str]:
    """기준 시점 이후 생기거나 바뀐 파일 이름. 없으면 빈 목록."""
    before = BEFORE if before is None else before
    now = snapshot(root)
    out = []
    for name in NAMES:
        if now[name] == before[name]:
            continue
        if before[name] is None:
            out.append(f"data/{name} 이 생겼다")
        elif now[name] is None:
            out.append(f"data/{name} 이 사라졌다")
        else:
            out.append(f"data/{name} 이 바뀌었다")
    return out
