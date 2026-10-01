"""회차 분석 결과 저장·복원 (Phase 4-C).

**왜 필요한가.** 4-B 까지는 패널 결과를 붙이려면 그 회차를 **다시 돌려야**
했다. `Report` 가 메모리에만 있었기 때문이다. 그런데 실제 운영 흐름은
이렇다.

    ① 회차 분석 → ② 경기자료 MD → ③ 클로드 채팅에서 패널 →
    ④ Panel JSON 저장 → ⑤ 나중에 JSON 만 가져오기 → ⑥ 감사 → ⑦ 리포트

③ 이 몇 시간, 며칠 걸릴 수 있다. 그 사이에 ① 을 다시 돌리면 **자료가
달라진다** — 순위표는 수집 시점 스냅샷이고(§1-1-7) 배당도 움직인다. 그러면
경기자료 MD 를 만든 그 분석과 패널 결과를 붙이는 분석이 서로 다른 것이 된다.

그래서 ① 이 끝날 때 그 결과를 그대로 저장한다.

    data/artifacts/260050.json

## 저장하는 것과 하지 않는 것

**새로 계산하지 않는다.** `Report.to_dict()`(=`asdict`)를 그대로 쓰고,
되살릴 때도 `models.revive_report()` 가 되감기만 한다.

**슛 계층은 저장하지 않는다.** `TeamProfile.shot_aggregates` ·
`shot_matches` · `opponent_matches` 는 Phase 2 분석의 **입력**이고, 분석은
이미 끝나 `Match.analysis` 에 들어 있다. 리포트 렌더링도 쓰지 않는다
(테스트로 확인). 지우면 파일이 크게 줄고, 되살릴 수 없는 것을 되살린 척하지
않게 된다.

**소스 캐시를 대신하지 않는다.** `cache/` 는 원본 응답 저장소이고 이쪽은
**분석 결과** 저장소다. 둘은 목적이 다르고 서로를 대체하지 않는다.

## `--demo` 는 저장하지 않는다

난수 표본이라 축적할 값이 아니다 (`roundlog` 와 같은 이유).
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .models import Report, as_of_from_match, revive_report
from .settings import ROOT

log = logging.getLogger("toto")

ARTIFACT_DIR = ROOT / "data" / "artifacts"
FILENAME = "{round}.json"

# 저장 형식 판. 되살리는 규칙이 바뀌면 올린다 — 옛 파일을 읽어 조용히 다른
# 것이 나오는 편보다 못 읽는 편이 낫다.
ARTIFACT_VERSION = 1

# 분석의 **입력**이라 저장하지 않는 칸 (위 설명 참고).
DROPPED = ("shot_aggregates", "shot_matches", "opponent_matches")


def path_for(round_id: str, outdir: Path | None = None) -> Path:
    base = Path(outdir) if outdir is not None else ARTIFACT_DIR
    return base / FILENAME.format(round=round_id or "unknown")


def _earliest_kickoff(report: Report) -> datetime | None:
    """이 회차에서 **가장 먼저 시작하는** 경기의 kickoff (KST aware).

    시각을 새로 파싱하지 않는다 — 분석이 `as_of` 를 만들 때 쓰는 것과
    **같은 함수**다 (`models.as_of_from_match`, §1-8). 두 곳에 두면 한쪽만
    고쳐져 "분석은 사전인데 저장은 사후" 처럼 어긋난다.

    `analysis` 를 import 하지 않는다 — 저장본이 분석을 다시 만들지 않는다는
    보증이 그 import 금지로 지켜지고 있다(`test_j8`). 그래서 규칙을
    `models` 로 옮겼다.
    """
    times = [t for t in (as_of_from_match(m) for m in report.matches) if t]
    return min(times) if times else None


def is_prematch(report: Report, now: datetime | None = None) -> bool:
    """이 회차가 아직 **한 경기도 시작하지 않았나** (Phase 6-B).

    **시각을 모르면 사전이라고 단정하지 않는다.** 모르는 채로 사전 스냅샷을
    갈아 끼우는 것보다 보존하는 편이 안전하다 (§1-5 와 같은 태도).
    """
    first = _earliest_kickoff(report)
    if first is None:
        return False
    now = now or datetime.now(first.tzinfo)
    if now.tzinfo is None:                      # naive 는 같은 시간대로 읽는다
        now = now.replace(tzinfo=first.tzinfo)
    return now < first


def _prune(node):
    """저장 전에 슛 계층을 걷어낸다. **값을 바꾸지 않는다** — 빼기만 한다."""
    if isinstance(node, dict):
        return {k: _prune(v) for k, v in node.items() if k not in DROPPED}
    if isinstance(node, list):
        return [_prune(v) for v in node]
    if isinstance(node, datetime):
        # 시간대를 지어내지 않는다 — naive 는 naive 로, aware 는 aware 로.
        return node.isoformat()
    return node


def to_dict(report: Report) -> dict:
    """저장할 모양. `Report.to_dict()` 위에 봉투만 씌운다."""
    return {"artifact_version": ARTIFACT_VERSION,
            "round": report.round_id or "",
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "report": _prune(asdict(report))}


def save(report: Report, outdir: Path | None = None,
         now: datetime | None = None) -> str:
    """회차 분석 결과를 파일로. 상태 문자열을 돌려준다 (§1-6).

    **경기가 시작한 뒤에는 기존 저장본을 덮어쓰지 않는다** (Phase 6-B).
    예전에는 무조건 덮어써서, 결과가 나온 뒤 같은 회차를 다시 돌리면
    **킥오프 전 스냅샷이 사후 스냅샷으로 조용히 교체**됐다 — 그러면 그 회차는
    시장 캘리브레이션 표본에서 영구히 사라진다.

    아직 한 경기도 시작하지 않았으면 그대로 덮어쓴다. 그때는 옛것도 새것도
    사전 스냅샷이고, 수집이 반쯤 실패한 뒤 다시 돌리는 것이 정상 흐름이다.
    """
    if not report.matches:
        return "생략 (경기 없음)"
    if (report.round_id or "").upper() == "DEMO":
        return "생략 (데모는 저장하지 않습니다)"
    path = path_for(report.round_id, outdir)
    if path.exists() and not is_prematch(report, now):
        return ("생략 (사전 스냅샷 보존 — 이미 시작한 회차입니다. "
                f"다시 저장하려면 {path} 를 지우십시오)")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(to_dict(report), ensure_ascii=False, indent=1)
        path.write_text(text, encoding="utf-8")
    except (OSError, TypeError, ValueError) as exc:
        return f"실패 ({exc})"
    return (f"ok ({len(report.matches)}경기 → {path}, "
            f"{len(text.encode('utf-8')) / 1024:.0f}KB)")


def load(round_id: str, outdir: Path | None = None
         ) -> tuple[Report | None, str]:
    """저장된 회차 분석 결과를 되살린다. (Report, 사유)."""
    return load_path(path_for(round_id, outdir))


def load_path(path: Path) -> tuple[Report | None, str]:
    """**파일 경로로** 되살린다 (Phase 5-E3a). (Report, 사유).

    `load()` 는 회차 번호로 경로를 만들어 읽는데, 저장본을 손에 들고
    "이 파일을 다시 렌더하라" 고 말하려면 경로로 부를 자리가 필요하다.
    **읽는 규칙은 하나다** — `load()` 가 이 함수로 들어오므로 회차 경로든
    임의 경로든 같은 판 검사와 같은 `revive_report()` 를 지난다. 새 파서를
    만들지 않는다 (§1-8).
    """
    path = Path(path)
    if not path.exists():
        return None, f"저장된 분석 결과가 없습니다 ({path})"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"읽지 못했습니다: {exc}"
    if not isinstance(data, dict):
        return None, "형식이 다릅니다 (최상위가 객체가 아님)"
    version = data.get("artifact_version")
    if version != ARTIFACT_VERSION:
        # 조용히 다른 것을 되살리느니 못 읽는 편이 낫다.
        return None, (f"저장 형식이 다릅니다 (파일 v{version} / "
                      f"현재 v{ARTIFACT_VERSION}) — 회차를 다시 돌리십시오")
    report = revive_report(data.get("report"))
    if report is None or not report.matches:
        return None, "되살릴 경기가 없습니다"
    return report, ""


def exists(round_id: str, outdir: Path | None = None) -> bool:
    return path_for(round_id, outdir).exists()
