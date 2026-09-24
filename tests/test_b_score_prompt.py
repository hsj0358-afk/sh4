"""B 예상 스코어 출력 회귀 (Phase 6-F-11 · CLAUDE.md §1-47).

6-F-10 실호출에서 B 가 14경기 **전부** `predicted_home`·`predicted_away`
를 `null` 로 냈다. 스키마 위반이 아니고(계약상 `null` 은 허용된다) 분석
내용도 정상이었지만, 그대로 3단계에 가면 **사회자의 제안 집합이 A 것뿐**이
되어 스코어 비교가 비대칭이 된다.

원인은 자료가 아니라 **프롬프트의 비대칭**이었다 — 데이터 분석가의 역할
프롬프트에는 예상 스코어 문단이 있는데(`당신의 예상 스코어는 지표와
근거에서 나와야 하며…`) 맞대결 분석가 쪽에는 **그것을 언급하는 줄이 한
줄도 없었다.** 공통 규칙은 반대로 "승무패를 도출하지 마라"·"자료가
부족하면 부족하다고 적어라" 만 말하므로, B 가 그 칸을 선택 사항으로 읽고
기본값을 `null` 로 잡을 이유만 있었다.

이 스위트가 지키는 것 다섯이다.

  1. **B 프롬프트가 예상 스코어 출력을 말한다** — 문장을 바이트로 박지 않고
     뜻을 이루는 요소(두 필드 이름 · `0 이상` 정수 · `null` 조건)를 본다
  2. **`null` 을 금지하지 않았다** — 강제 문구가 들어가면 자료가 실제로
     모자랄 때도 값을 지어내게 된다 (§1-5). 목표는 '불필요한 null 제거'
     이지 'null 제거' 가 아니다
  3. **승무패 금지가 그대로다** — 스코어를 승무패에서 역산하는 것도 막는다
  4. **새 통계를 만들지 않는다** — 스코어를 만들려고 공식·점수·확률을
     새로 계산하지 않는다
  5. **6-F-10 의 구조가 그대로다** — A·B 가 같은 packet 을 받고(같은 sha256)
     프롬프트만 다르며, A 프롬프트는 한 글자도 바뀌지 않았다
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import moderator, panel, panelauto, panelexport   # noqa: E402
from toto import panelimport, panelpacket, panelwork        # noqa: E402

_PASSED = _FAILED = 0


def check(name, fn):
    global _PASSED, _FAILED
    try:
        fn()
    except AssertionError as exc:
        _FAILED += 1
        print(f"  FAIL {name}: {exc}")
    except Exception as exc:                                # noqa: BLE001
        _FAILED += 1
        print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    else:
        _PASSED += 1
        print(f"  ok   {name}")


def b_prompt() -> str:
    return panel.ROLE_PROMPTS[panel.MATCHUP_ANALYST]


def a_prompt() -> str:
    return panel.ROLE_PROMPTS[panel.DATA_ANALYST]


def opinion(home, away, ids=("E001",)) -> str:
    return json.dumps({"predicted_home": home, "predicted_away": away,
                       "summary": "요약 문장.",
                       "rationale": ["공격 지표와 상대 수비 지표를 함께 보면 "
                                     "양 팀 득점 기대 수준에 차이가 있다"],
                       "evidence_ids": list(ids)}, ensure_ascii=False)


# ==========================================================================
# A. B 프롬프트가 예상 스코어를 말한다 (§4·§13)
# ==========================================================================
def test_b_prompt_mentions_score_output():
    """**뜻을 본다 — 문장을 바이트로 박지 않는다** (§13).

    문구는 다듬을 수 있어야 하므로 한글 한 문장을 통째로 고정하지 않고,
    그 규칙이 성립하려면 반드시 있어야 하는 요소만 본다.
    """
    text = b_prompt()
    for field in ("predicted_home", "predicted_away"):
        assert field in text, f"B 프롬프트가 {field} 를 말하지 않는다"
    assert "0 이상" in text, "정수 범위를 적지 않았다"
    assert "정수" in text
    assert "null" in text, "null 을 언제 쓰는지 적지 않았다"
    # 6-F-10 에서는 **한 줄도 없었다.** 그 상태로 돌아가면 여기서 깨진다.
    assert "예상 스코어" in text


def test_b_prompt_says_when_null_is_right():
    """`null` 의 조건이 **자료 부족**이라고 적혀 있다 (§5·§18)."""
    text = b_prompt()
    head = text[max(0, text.find("null") - 200):text.find("null") + 200]
    assert "자료" in head, head
    # '적어 보인다는 인상' 만으로 고르지 말라는 쪽도 함께 적혀 있다 (§4).
    assert "인상" in text or "먼저" in text


def test_b_prompt_does_not_force_non_null():
    """**강제하지 않는다** (§5).

    자료가 실제로 모자랄 때도 값을 지어내게 만드는 문구를 막는다 —
    이 프로젝트의 '없으면 없다고 적는다'(§1-5)와 정면으로 어긋난다.
    """
    text = b_prompt()
    for bad in ("무조건", "반드시 모든", "모든 경기에 스코어",
                "14경기 전부", "전부 채우", "null 을 쓰지 마",
                "null 금지", "빠짐없이 채"):
        assert bad not in text, f"강제 문구 '{bad}' 가 들어갔다"


def test_b_prompt_keeps_score_out_of_win_draw_loss():
    """스코어를 **승무패에서 역산하지 않는다** (§6)."""
    text = b_prompt()
    assert "역산" in text, "역산 금지를 적지 않았다"
    # 금지하는 방식 자체를 예로 들어 둔다 — 그래야 모델이 알아본다.
    assert "2-1" in text and "1-1" in text


def test_b_prompt_preserves_no_pick_rule():
    """승무패 추천 금지가 **그대로다** (§3·§13).

    공통 규칙에 있고, B 프롬프트의 새 문단도 그것과 어긋나지 않는다.
    """
    assert "승무패 추천" in panel.SYSTEM_COMMON
    assert "베팅" in panel.SYSTEM_COMMON
    assert "승/무/패를 도출하지 마십시오" in panel.SYSTEM_COMMON
    text = b_prompt()
    assert "승/무/패 선택이 아닙니다" in text, \
        "스코어가 승무패가 아니라는 것을 적지 않았다"
    for bad in ("홈승을 추천", "픽은", "베팅하십시오", "배팅"):
        assert bad not in text, bad


def test_b_prompt_forbids_new_numbers_for_the_score():
    """스코어를 만들려고 **새 수치를 계산하지 않는다** (§7)."""
    text = b_prompt()
    assert "계산하지 마십시오" in text
    for word in ("공격력 점수", "가중평균", "확률"):
        assert word in text, word


def test_b_prompt_links_score_to_rationale_and_evidence():
    """스코어를 적으면 `rationale`·`evidence_ids` 로 잇는다 (§8·§9)."""
    text = b_prompt()
    assert "rationale" in text
    assert "evidence_ids" in text
    assert "새 ID 를 만들지 않습니다" in text, "새 근거 ID 금지가 빠졌다"


# ==========================================================================
# B. 계약은 넓히지도 좁히지도 않았다 (§3·§15)
# ==========================================================================
def test_integer_score_passes_validation():
    """정수 스코어가 그대로 통과한다 (§15 정상 케이스)."""
    op = panel.parse_opinion(opinion(2, 1), panel.MATCHUP_ANALYST,
                             ("E001", "E002"))
    assert (op.predicted_home, op.predicted_away) == (2, 1)
    assert op.evidence_ids == ("E001",)


def test_null_score_still_passes_validation():
    """`null` 도 **그대로 통과한다** (§15 자료 부족 케이스).

    이 Phase 는 프롬프트만 바꿨다 — 검증기를 조이면 자료가 모자란 경기가
    통째로 실패한다.
    """
    op = panel.parse_opinion(opinion(None, None), panel.MATCHUP_ANALYST,
                             ("E001",))
    assert op.predicted_home is None and op.predicted_away is None


def test_validator_is_untouched():
    """스코어 규칙은 `panel._score()` 그대로다 — 새 규칙을 만들지 않았다."""
    for bad in ('"2"', "2.5", True, -1):
        try:
            panel.parse_opinion(opinion(bad, 1), panel.MATCHUP_ANALYST,
                                ("E001",))
        except panel.ValidationError:
            continue
        raise AssertionError(f"{bad!r} 가 통과했다")


def test_both_mock_shapes_survive_the_round_trip():
    """회차 배열로도 **두 모양이 섞여** 지난다 (§15).

    `panelwork.parse_stage()` 는 자동·수동·API 세 경로가 함께 쓰는 문이다.
    실물 회차로 배열을 만들어 일부는 정수, 일부는 `null` 로 보낸다 —
    운영에서 실제로 기대하는 모양이 이것이다 (§18).
    """
    from toto import artifact
    report, _why = artifact.load("260052")
    if report is None:
        return
    rows = []
    for i, m in enumerate(report.matches):
        ids = panel.build_panel_payload(m).evidence_ids
        body = json.loads(opinion(2, 1) if i % 2 == 0 else opinion(None, None))
        body["match_no"] = m.no
        body["evidence_ids"] = list(ids[:1])
        rows.append(body)
    opinions, _raw, res = panelwork.parse_stage(
        json.dumps(rows, ensure_ascii=False), panel.MATCHUP_ANALYST, report)
    errs = [i for i in res.issues if i.level == panelimport.ERROR]
    assert not errs, errs[:3]
    assert len(opinions) == len(report.matches)
    scored = [n for n, o in opinions.items() if o.predicted_home is not None]
    assert scored, "정수 스코어가 하나도 살아남지 않았다"
    assert len(scored) < len(opinions), "null 이 하나도 남지 않았다"


# ==========================================================================
# C. 6-F-10 의 구조가 그대로다 (§12·§20)
# ==========================================================================
def test_a_prompt_is_untouched():
    """**A 프롬프트를 건드리지 않았다** (§20)."""
    text = a_prompt()
    assert "당신의 역할은 **데이터 분석가**입니다." in text
    assert "관측된 수치만" in text or "관측된 수치" in text
    # 6-F-11 의 문단이 A 로 새지 않았다.
    assert "역산" not in text
    assert "predicted_home" not in text
    assert len(text) == 306, f"A 프롬프트 길이가 달라졌다: {len(text)}"


def test_ab_packet_identity():
    """**A stdin == B stdin** — 6-F-10 의 불변조건 (§12).

    프롬프트만 바꿨으므로 자료는 글자까지 같아야 한다.
    """
    from toto import artifact
    report, _why = artifact.load("260052")
    if report is None:                        # 저장본이 없는 환경
        return
    idx = panelpacket.build_panel_index(report)
    packet = panelpacket.packet_text(panelpacket.build_compact_packet(idx))
    a = panelauto.common_packet_text(report, None, idx)
    b = panelauto.common_packet_text(report, None, idx)
    assert a == b == packet
    assert panelpacket.packet_digest(a) == panelpacket.packet_digest(b)
    # packet 에는 역할이 실리지 않는다 (6-F-10).
    assert "predicted_home" not in packet or "role" not in packet


def test_only_the_b_system_text_changed():
    """바뀐 것은 **B system 문자열 하나**다 (§12).

    A·C 의 시스템 문자열은 그대로이고, B 만 새 문단을 갖는다.
    """
    marker = "예상 스코어(`predicted_home`·`predicted_away`)"
    assert marker in panel.SYSTEM_COMMON + "\n" \
        + panel.ROLE_PROMPTS[panel.MATCHUP_ANALYST]
    assert marker not in panel.SYSTEM_COMMON + "\n" \
        + panel.ROLE_PROMPTS[panel.DATA_ANALYST]
    assert marker not in moderator.system_prompt(30)


def test_prompt_version_was_raised():
    """프롬프트를 고쳤으면 **캐시가 무효화된다** (§1-4).

    특정 숫자가 아니라 '6-E-6 의 4 보다 높다' 를 본다 (§1-29 범위 이동).
    """
    assert int(panel.PANEL_PROMPT_VERSION) >= 5
    # 사회자는 건드리지 않았다 (§20).
    assert moderator.MODERATOR_PROMPT_VERSION == "6"
    assert panelimport.SCHEMA_VERSION == "1.1"


def test_instructions_fingerprint_changed():
    """지침 지문이 바뀐다 — **다시 붙여넣어야 한다** (§1-11-1)."""
    fp = panelexport.instructions_fingerprint()
    assert fp != "fe098456", "지문이 그대로면 지침이 낡은 줄 모른다"
    assert fp == "4a54e7ad", fp


def test_scope_untouched_modules():
    """이 Phase 가 손대지 않은 것 (§1·§20).

    `panelpacket`·`panelwork`·`moderator` 에 6-F-11 의 문구가 없다.
    """
    import inspect
    for mod in (panelpacket, panelwork, moderator, panelauto):
        src = inspect.getsource(mod)
        assert "역산" not in src, f"{mod.__name__} 에 프롬프트 문구가 샜다"
        assert "예상 득점수" not in src, mod.__name__


def test_b_prompt_change_is_additive():
    """기존 B 문장을 **지우지 않았다** (§11).

    6-E-4·6-E-6 이 넣은 문장이 그대로 있어야 한다 — 그 Phase 들의 테스트가
    따로 고정하고 있지만, 여기서도 한 번 더 본다.
    """
    text = b_prompt()
    for kept in ("당신의 역할은 **맞대결·전술 분석가**입니다.",
                 "qualitative", "style_of_play", "포메이션", "선발 명단",
                 "불확실성", "방향이 없습니다",
                 "그 밖에 당신이 볼 수 있는 것은 지표들의 상대 관계뿐입니다."):
        assert kept in text, f"기존 문장이 사라졌다: {kept}"


def test_score_block_sits_at_the_end():
    """새 문단이 **맨 끝**이다 (§10).

    시스템 문자열은 `SYSTEM_COMMON + 역할` 이라 출력 스키마가 위에 있고,
    역할 프롬프트가 마지막이다. 스코어 규칙을 그 끝에 두면 payload 바로
    앞에서 읽힌다.
    """
    text = b_prompt()
    assert text.index("예상 스코어(`predicted_home`") > text.index("qualitative")
    assert text.rstrip().endswith("그다음에 정하십시오.")


def main() -> int:
    print("Phase 6-F-11 — B 예상 스코어 출력")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 1 if _FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
