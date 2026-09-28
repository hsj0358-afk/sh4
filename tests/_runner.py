"""테스트 파일의 **직접 실행** 러너 — `python tests/test_xxx.py` (Phase 3 M13).

pytest 는 이 파일을 쓰지 않는다 (`test_*.py` 가 아니다). 직접 실행할 때만
각 파일의 `main()` 이 이것을 부른다.

52개 파일이 글자까지 같은 출력을 내는 러너를 저마다 들고 있었다. 그 출력이
직접 실행의 계약이므로 **한 글자도 바꾸지 않고** 여기로 옮겼다.

    ok   <이름>                 통과
    SKIP <이름>: <사유>          실물 자료가 없다 — 실패도 통과도 아니다
    FAIL <이름>: <사유>          단언이 틀렸다
    ERR  <이름>: <종류>: <사유>   예상 밖 예외

    <통과>/<건너뛴 것을 뺀 수> 통과[ · 건너뜀 N]
    종료코드: 실패·오류가 있으면 1, 아니면 0 (SKIP 만 있으면 0)

`SKIP` 은 `unittest.SkipTest` 다 — `realdata.SkipTest` 가 바로 그것이다
(§1-55: 저장본이 없으면 SKIP, 있는데 못 읽으면 FAIL). 이 모듈은 `realdata`
를 import 하지 않는다 — 러너가 자료 모듈을 끌어오면 직접 실행할 때만
불러오는 모듈이 늘어난다.

**출력 형식이 다른 러너는 여기로 옮기지 않았다** — `✓`/`✗` 형식, 모든 예외를
`FAIL` 로 적는 형식, 머리글을 찍는 형식, 테스트마다 임시 폴더를 지우는 Pages
러너, 골든·모바일처럼 전용 흐름을 가진 러너는 각 파일에 그대로 있다.
"""
from __future__ import annotations

import unittest


def run_tests(namespace: dict) -> int:
    """`namespace`(보통 `globals()`)의 `test_*` 함수를 이름순으로 돌린다."""
    tests = [(n, f) for n, f in sorted(namespace.items())
             if n.startswith("test_") and callable(f)]
    failed = skipped = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except unittest.SkipTest as exc:
            skipped += 1
            print(f"  SKIP {name}: {exc}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {name}: {exc}")
        except Exception as exc:                        # noqa: BLE001
            failed += 1
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed - skipped}/{len(tests) - skipped} 통과"
          + (f" · 건너뜀 {skipped}" if skipped else ""))
    return 1 if failed else 0
