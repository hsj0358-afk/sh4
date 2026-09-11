"""3단계 Moderator 결과 붙여넣기 (Phase 4-F).

4-B 는 **파일**을 받는다. 그런데 사용자가 실제로 손에 쥐는 것은 클로드
채팅의 3단계 응답 한 덩어리이고, 그것을 Panel Result JSON 으로 옮겨 적는
단계가 매 회차 손으로 반복됐다.

    클로드 3단계 결과  →  [이 모듈]  →  Panel Result 1.1  →  기존 4-B 경로

## 계약을 바꾸지 않는다

이 모듈은 **어댑터일 뿐이다.** Panel Result 1.1 규격도, `panelimport` 의
검증도, `panelaudit`·`artifact`·`render` 도 그대로다. 여기서 하는 일은
셋뿐이다.

  · 붙여넣은 텍스트를 JSON 배열로 읽는다
  · `match_no` 를 **이 회차의 공식 경기목록**에 맞춰 경기를 확정한다
    (`match_id` 는 프로그램이 구한다 — §1-15-1)
  · 그 결과를 Panel Result 1.1 **dict** 로 옮긴다

**내용 검증을 여기서 다시 쓰지 않는다.** 스코어·분포·근거·금지 칸은
`panelimport.validate()` 가 보고, 그것은 다시 `moderator.parse_result()` 를
부른다 — 세 경로(API·파일·붙여넣기)가 같은 문을 지난다.

## 없는 것을 만들지 않는다

3단계 결과에는 **두 분석가의 원문이 없다.** 그래서:

  · `distribution.origin` 으로 분석가의 예상 스코어를 만들지 않는다
  · `adopted_from` 으로도 만들지 않는다
  · `conclusion` 문장을 읽어 추정하지도 않는다

결과는 `panel_status = "부분"` 이고 — §1-6 의 어휘 그대로다 — 분석가 자리에는
`panelimport.MODERATOR_ONLY` 사유만 남는다. 리포트도 그렇게 적는다.

## 3단계 결과를 고치지 않는다

`origin`·`adopted_from`·`distribution`·`conclusion`·`market_relation`·
`evidence_ids` 는 **원문 그대로** 옮긴다. 허용하는 정규화는 넷뿐이다.

  · `match_no` → `match_number`
  · 회차 경기목록에서 `home_team`·`away_team` 보강
  · 돌리지 않은 경기를 `panel_status` 로 옮김
  · 그 외 칸은 사회자 블록 안으로 그대로 이동

기존 검증기가 이미 오류로 잡는 것은 그대로 오류로 나간다 — 이 Phase 는
입력 경로 개선이지 3단계 내용 교정이 아니다.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from . import panelimport
from .models import Report

log = logging.getLogger("toto")

# 붙여넣기 입력의 경기 번호 키. 1·2·3단계 출력이 전부 이 이름을 쓴다.
PASTE_NO = "match_no"

# 사회자 블록으로 옮기지 않는 칸 — 경기 식별자는 바깥에 자리가 따로 있다.
_IDENTITY_KEYS = (PASTE_NO, "match_number", "match_id",
                  "home_team", "away_team",
                  "panel_status", "panel_status_reason")

# 돌리지 않은 경기의 사유. **문장을 지어내지 않는다** — 입력이 말해 준
# 사실(시뮬레이션 0회·분포 없음·채택 없음)을 그대로 적는다.
SKIPPED_REASON = ("3단계 결과에 토론이 없습니다 "
                  "(simulations 0 · distribution 비어 있음 · 채택 없음)")

# 사회자 결과만 받았다는 사유. 분석가 원문이 없다는 사실 그대로다.
PARTIAL_REASON = "3단계 Moderator 결과만 붙여넣었습니다 (1·2단계 원문 없음)"


def _int_no(value) -> int | None:
    """양의 정수만. `True` 는 `int` 의 하위형이라 따로 막는다 (§1-9)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _is_skipped(body: dict) -> bool:
    """돌리지 않은 경기인가 (260052 의 9·13·14번 모양).

    셋이 **모두** 맞아야 한다 — 하나라도 내용이 있으면 토론이 있었던 것이고,
    그것을 '생략' 으로 적으면 사회자가 한 일을 지우는 셈이 된다.
    """
    sims = body.get("simulations")
    return (not body.get("distribution")
            and body.get("adopted_home") is None
            and body.get("adopted_away") is None
            and (sims is None or sims == 0))


def convert(text: str, report: Report) -> tuple[dict | None, list]:
    """붙여넣은 텍스트 → Panel Result 1.1 dict. (dict, 문제 목록).

    여기서 보는 것은 **구조와 경기 연결**뿐이다. 내용은 돌려준 dict 를
    `panelimport.validate()` 에 태워서 본다 — 검증을 두 벌 만들지 않는다.
    """
    out = panelimport.PanelImportResult(
        round_id=str(report.round_id or ""),
        expected_matches=len(report.matches))

    def fail(code: str, why: str, **kw):
        out.add(panelimport.ERROR, code, why, **kw)

    raw = (text or "").strip()
    if not raw:
        fail("PASTE_EMPTY", "붙여넣은 내용이 없습니다")
        return None, out.issues
    try:
        data = json.loads(_strip_fence(raw))
    except Exception as exc:                                # noqa: BLE001
        fail("PASTE_NOT_JSON", f"JSON 으로 읽지 못했습니다: {exc}")
        return None, out.issues
    if not isinstance(data, list):
        fail("PASTE_NOT_A_LIST",
             f"최상위가 배열이 아닙니다 ({type(data).__name__}) — 3단계 결과는 "
             f"경기 객체의 배열입니다")
        return None, out.issues
    if not data:
        fail("PASTE_EMPTY", "배열이 비어 있습니다")
        return None, out.issues

    by_no = {m.no: m for m in report.matches}
    blocks, seen = [], {}
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            fail("PASTE_ITEM_NOT_AN_OBJECT",
                 f"{i + 1}번째 항목이 객체가 아닙니다 ({type(item).__name__})",
                 field=f"[{i}]")
            continue
        no = _int_no(item.get(PASTE_NO))
        if no is None:
            fail("PASTE_MATCH_NO_INVALID",
                 f"{i + 1}번째 항목의 {PASTE_NO} 가 양의 정수가 아닙니다 "
                 f"({item.get(PASTE_NO)!r})", field=f"[{i}].{PASTE_NO}")
            continue
        if no in seen:
            fail("PASTE_DUPLICATE_MATCH_NO",
                 f"{PASTE_NO} {no} 이 두 번 나옵니다 (앞서 {seen[no]}번째)",
                 match_no=no, field=f"[{i}].{PASTE_NO}")
            continue
        seen[no] = i + 1
        match = by_no.get(no)
        if match is None:
            fail("PASTE_UNKNOWN_MATCH_NO",
                 f"{no}번 경기가 이 회차({report.round_id})에 없습니다",
                 match_no=no, field=f"[{i}].{PASTE_NO}")
            continue
        blocks.append(_block(item, match))

    # **일부만 붙여넣은 것을 완전한 회차 결과로 치지 않는다.** 빠진 경기는
    # `MATCH_MISSING` 으로 다시 잡히지만, 여기서 먼저 알려 주어야 사용자가
    # 무엇을 더 붙여야 하는지 안다.
    missing = [m.no for m in report.matches if m.no not in seen]
    if missing:
        fail("PASTE_INCOMPLETE_ROUND",
             f"회차 {len(report.matches)}경기 중 {len(seen)}경기만 있습니다 — "
             f"빠진 경기: {', '.join(str(n) for n in missing)}번. 3단계 결과 "
             f"전체를 붙여넣으십시오")

    if out.errors:
        return None, out.issues
    return {"schema_version": panelimport.SCHEMA_VERSION,
            "round": report.round_id or "",
            "source": "moderator-paste",
            "matches": blocks}, out.issues


def _strip_fence(text: str) -> str:
    """```json 울타리를 걷어낸다. 채팅에서 복사하면 자주 함께 온다."""
    from .llm import strip_fence
    return strip_fence(text)


def _block(item: dict, match) -> dict:
    """경기 하나를 Panel Result 1.1 모양으로. **값을 고치지 않는다.**"""
    body = {k: v for k, v in item.items() if k not in _IDENTITY_KEYS}
    block = {
        "match_number": match.no,
        # 팀 이름은 **회차 공식 경기목록**에서 온다. 사용자가 적지 않은 것을
        # 추론하는 것이 아니라 프로그램이 이미 아는 값을 채우는 것이다.
        "home_team": match.home.display or match.home.canonical,
        "away_team": match.away.display or match.away.canonical,
    }
    if _is_skipped(body):
        block["panel_status"] = panelimport.STATUS_SKIPPED
        block["panel_status_reason"] = SKIPPED_REASON
        return block
    block["panel_status"] = panelimport.STATUS_PARTIAL
    block["panel_status_reason"] = PARTIAL_REASON
    block[panelimport.MODERATOR_ROLE] = body
    return block


def canonical_path(round_id: str, base: Path | None = None) -> Path:
    """프로그램이 만들어 두는 Panel Result 파일 자리."""
    return panelimport.inbox_dir(base).joinpath(
        f"{round_id}{panelimport.FILE_SUFFIX}")


def apply(text: str, report: Report, settings=None,
          base: Path | None = None) -> tuple[Path | None, object]:
    """붙여넣기 → 검증 → (통과하면) 파일 저장. (경로, 검증 결과).

    **검증을 통과한 경우에만 파일을 만든다** (§12). 중간에 깨진 붙여넣기가
    `panel_results/` 에 남으면 다음 실행이 그것을 집어 든다.

    저장한 파일은 사용자가 손으로 만든 것이 아니라 **프로그램이 만든
    canonical 출력**이고, 그대로 기존 파일 경로(`--import-panel-result`)에
    다시 태울 수 있다.
    """
    data, issues = convert(text, report)
    if data is None:
        out = panelimport.PanelImportResult(
            round_id=str(report.round_id or ""),
            expected_matches=len(report.matches))
        out.issues = list(issues)
        return None, out

    result = panelimport.validate(data, report, settings)
    result.issues = list(issues) + list(result.issues)
    if not result.success:
        return None, result

    path = canonical_path(report.round_id or "unknown", base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path, result


def report_lines(result) -> list[str]:
    """사람이 읽을 요약. `panelimport` 의 어휘를 그대로 쓴다."""
    lines = [result.status_line()]
    for issue in result.issues:
        lines.append(str(issue))
    return lines
