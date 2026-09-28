"""스코어 칸 검증 — `panel._score` ↔ `moderator._goals` (리팩터링 Phase 3 M2).

두 함수는 **판정 규칙이 같다** — `None` 은 `None`, `bool`·정수가 아닌 값은
거부, 음수는 거부, 나머지는 받은 값 그대로. 다른 것은 **오류 문구뿐이다.**

  panel._score      "{칸}: 정수 또는 null 이어야 합니다" · "{칸}: 음수는 허용하지 않습니다"
  moderator._goals  "{칸}: 0 이상의 정수 또는 null 이어야 합니다" · "{칸}: 음수는 받지 않습니다"

그 문구는 밖으로 나간다 — `panelimport` 의 오류 메시지(사용자가 읽는다)와
사회자 재요청(`moderator.retry_hint`, 모델이 읽는다)이다. `panelimport` 는
메시지 **문자열로 오류 코드를 고르는데**, 고르는 낱말(`근거 ID` ·
`distribution` · `simulations` …)은 문구 꼬리가 아니라 **칸 이름**에서 온다.

이 스위트가 지키는 것.

  A. 함수 하나하나의 동작 — 반환값·예외 종류·예외 문구 (둘의 차이까지)
  B. 부르는 쪽의 계약 — `parse_opinion` · `parse_result` · `panelimport` 의
     오류 코드와 메시지 · 사회자 재요청 문구
  C. 판정 규칙이 한 곳이다 (`panelcheck.nonnegative_int`)

A·B 는 통합 전 코드에서도 똑같이 통과해야 한다.

pytest 없이도 돈다:  python tests/test_score_validation.py
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import moderator, panel, panelimport                  # noqa: E402

from test_moderator import _mod_json, opinion, payload_of       # noqa: E402
from test_panel import FakeClient, S                            # noqa: E402

_PASSED = _FAILED = 0

DA, MU = moderator.DATA_ROLE, moderator.MATCHUP_ROLE

# (함수, 형식 오류 꼬리, 음수 꼬리)
PANEL_TAILS = ("정수 또는 null 이어야 합니다", "음수는 허용하지 않습니다")
MOD_TAILS = ("0 이상의 정수 또는 null 이어야 합니다", "음수는 받지 않습니다")
CASES = ((panel._score, PANEL_TAILS), (moderator._goals, MOD_TAILS))


class _IntSub(int):
    """`int` 의 하위형. 받은 객체 그대로 돌려주는지 본다."""


def check(name, fn):
    global _PASSED, _FAILED
    try:
        fn()
    except Exception as exc:                                 # noqa: BLE001
        _FAILED += 1
        print(f"  ✗ {name}: {type(exc).__name__}: {exc}")
    else:
        _PASSED += 1
        print(f"  ✓ {name}")


def _raises(fn) -> str:
    try:
        fn()
    except panel.ValidationError as exc:
        return str(exc)
    raise AssertionError("ValidationError 가 나지 않았다")


# --------------------------------------------------------------------------
# A. 함수 하나하나
# --------------------------------------------------------------------------
def test_a1_none_is_none():
    for fn, _ in CASES:
        assert fn(None, "x") is None, fn.__name__


def test_a2_non_negative_ints_come_back_unchanged():
    for fn, _ in CASES:
        for value in (0, 1, 2, 9, 30, 10**6):
            got = fn(value, "x")
            assert got == value and type(got) is int, (fn.__name__, value)
        sub = _IntSub(3)
        assert fn(sub, "x") is sub, "받은 객체를 그대로 돌려주지 않았다"


def test_a3_negative_is_refused_with_its_own_message():
    for fn, (_, negative) in CASES:
        for value in (-1, -30, _IntSub(-2)):
            assert _raises(lambda: fn(value, "칸")) == f"칸: {negative}", \
                (fn.__name__, value)


def test_a4_non_int_is_refused_not_repaired():
    """`"2"` 를 2 로, `1.5`·`2.0` 을 정수로, `True` 를 1 로 읽지 않는다."""
    junk = ("2", "", "2-1", "-1", 1.5, 2.0, 0.0, -1.5, float("nan"),
            True, False, [1], [], (1,), {"home": 1}, {}, object())
    for fn, (not_int, _) in CASES:
        for value in junk:
            assert _raises(lambda: fn(value, "칸")) == f"칸: {not_int}", \
                (fn.__name__, value)


def test_a5_name_is_the_prefix_as_given():
    assert _raises(lambda: panel._score(-1, "predicted_home")) == \
        "predicted_home: 음수는 허용하지 않습니다"
    assert _raises(lambda: moderator._goals("3", "distribution[2].home")) == \
        "distribution[2].home: 0 이상의 정수 또는 null 이어야 합니다"
    assert _raises(lambda: moderator._goals(-1, "")) == ": 음수는 받지 않습니다"


def test_a6_the_two_messages_stay_different():
    """문구를 통일하지 않는다 — 둘 다 이미 밖으로 나간다."""
    assert _raises(lambda: panel._score(1.5, "n")) != \
        _raises(lambda: moderator._goals(1.5, "n"))
    assert _raises(lambda: panel._score(-1, "n")) != \
        _raises(lambda: moderator._goals(-1, "n"))


def test_a7_both_raise_the_one_validation_error():
    for fn, _ in CASES:
        for value in (-1, "2"):
            try:
                fn(value, "x")
            except panel.ValidationError as exc:
                assert type(exc) is panel.ValidationError
                assert isinstance(exc, moderator.ValidationError)
            else:
                raise AssertionError(fn.__name__)


# --------------------------------------------------------------------------
# B. 부르는 쪽의 계약
# --------------------------------------------------------------------------
def _opinion_json(**over) -> str:
    body = {"predicted_home": 2, "predicted_away": 1, "summary": "요약",
            "rationale": [], "evidence_ids": []}
    body.update(over)
    return json.dumps(body, ensure_ascii=False)


def test_b1_parse_opinion_missing_key_is_null():
    body = json.loads(_opinion_json())
    del body["predicted_home"]
    op = panel.parse_opinion(json.dumps(body), DA, ())
    assert op.predicted_home is None and op.predicted_away == 1


def test_b2_parse_opinion_messages():
    for over, want in (
            ({"predicted_home": -1}, "predicted_home: 음수는 허용하지 않습니다"),
            ({"predicted_away": "1"},
             "predicted_away: 정수 또는 null 이어야 합니다"),
            ({"predicted_home": True},
             "predicted_home: 정수 또는 null 이어야 합니다")):
        got = _raises(lambda: panel.parse_opinion(_opinion_json(**over),
                                                  DA, ()))
        assert got == want, (over, got)


def test_b3_panelimport_analyst_code_and_message():
    """분석가 스코어 오류는 `INVALID_ANALYST` 이고 메시지는 그대로 실린다."""
    res = panelimport.PanelImportResult()
    block = json.loads(_opinion_json(predicted_home=-1))
    assert panelimport._opinion(block, DA, (), res, {"match_no": 1}) is None
    [issue] = res.issues
    assert issue.code == "INVALID_ANALYST", issue
    assert issue.message == "predicted_home: 음수는 허용하지 않습니다"


def test_b4_panelimport_initial_scores_code_and_message():
    res = panelimport.PanelImportResult()
    block = {panelimport.INITIAL_SCORES: {DA: {"home": -1, "away": 1},
                                          MU: {"home": None, "away": 0}}}
    got = panelimport._initial_scores(block, res, {"match_no": 1})
    [issue] = res.issues
    assert issue.code == "INITIAL_SCORE_INVALID", issue
    assert issue.message == (f"{DA} 의 최초 스코어: home: 음수는 허용하지 "
                             f"않습니다"), issue.message
    [score] = got                  # `null` 은 0 으로 채우지 않고 그대로 둔다
    assert (score.role, score.home, score.away) == (MU, None, 0)


def _parse(**over):
    return moderator.parse_result(
        _mod_json(**over), panels_seen=(DA,), shared=(), data_only=(),
        matchup_only=(), allowed_ids=(), allowed_scores={DA: (2, 1)})


_DIST_OK = [{"home": 2, "away": 1, "count": 30, "origin": DA}]


def test_b5_parse_result_messages():
    cases = (
        ({"distribution": [{"home": "2", "away": 1, "count": 30}],
          "simulations": 30},
         "distribution[0].home: 0 이상의 정수 또는 null 이어야 합니다"),
        ({"distribution": [{"home": 2, "away": 1, "count": -3}],
          "simulations": 30},
         "distribution[0].count: 음수는 받지 않습니다"),
        ({"distribution": [{"home": 2, "away": 1}], "simulations": 30},
         "distribution[0]: home·away·count 가 필요합니다"),
        ({"distribution": _DIST_OK, "simulations": "30"},
         "simulations: 0 이상의 정수 또는 null 이어야 합니다"),
        ({"adopted_home": -1, "adopted_away": 1},
         "adopted_home: 음수는 받지 않습니다"),
        ({"adopted_home": 2, "adopted_away": 1.0},
         "adopted_away: 0 이상의 정수 또는 null 이어야 합니다"),
    )
    for over, want in cases:
        got = _raises(lambda: _parse(**over))
        assert got == want, (over, got)


def test_b6_parse_result_nulls_keep_their_caller_meaning():
    """`None` 의 뜻은 부르는 쪽이 정한다 — 함수는 `None` 만 돌려준다."""
    res = _parse(conclusion="고를 근거가 없었습니다.")   # 분포·채택 없음
    assert res.simulations == 0 and res.distribution == ()
    assert res.adopted_home is None and res.adopted_away is None
    res = _parse(distribution=_DIST_OK, simulations=30, adopted_home=2,
                 adopted_away=1, conclusion="토론 결과 2-1 입니다.")
    assert (res.adopted_home, res.adopted_away, res.simulations) == (2, 1, 30)
    msg = _raises(lambda: _parse(distribution=_DIST_OK, simulations=None))
    assert msg == "simulations(0) 와 distribution 합계(30)가 다릅니다", msg


def test_b7_panelimport_moderator_codes_follow_the_field_name():
    """오류 코드는 문구 꼬리가 아니라 **칸 이름**으로 갈린다."""
    ops = [opinion(DA, home=2, away=1)]
    cases = (
        ({"distribution": [{"home": "2", "away": 1, "count": 30}],
          "simulations": 30}, "INVALID_DISTRIBUTION",
         "distribution[0].home: 0 이상의 정수 또는 null 이어야 합니다"),
        ({"distribution": _DIST_OK, "simulations": -30},
         "INVALID_DISTRIBUTION", "simulations: 음수는 받지 않습니다"),
        ({"simulations": 0, "adopted_home": True, "adopted_away": 1},
         "INVALID_MODERATOR",
         "adopted_home: 0 이상의 정수 또는 null 이어야 합니다"),
    )
    for over, code, message in cases:
        res = panelimport.PanelImportResult()
        body = json.loads(_mod_json(**over))
        got = panelimport._moderator(body, ops, (), 30, res, {"match_no": 1})
        assert got is None
        [issue] = res.errors
        assert (issue.code, issue.message) == (code, message), issue


def test_b8_moderator_retry_carries_the_goal_message_to_the_model():
    """사회자 재요청은 오류 문구를 **모델에게 그대로** 보낸다."""
    bad = _mod_json(adopted_home=-1, adopted_away=1)
    client = FakeClient(moderator_reply=bad)
    _raises(lambda: moderator.run_moderator(
        payload_of(), [opinion(DA)], settings=S, client=client))
    assert len(client.moderator_calls) == 2
    first = client.moderator_calls[0][1]
    second = client.moderator_calls[1][1]
    assert second == first + moderator.retry_hint(
        "adopted_home: 음수는 받지 않습니다"), second[len(first):]


# --------------------------------------------------------------------------
# C. 판정 규칙이 한 곳이다
# --------------------------------------------------------------------------
def _bool_checks(fn) -> int:
    tree = ast.parse(inspect.getsource(fn).lstrip())
    return sum(1 for n in ast.walk(tree)
               if isinstance(n, ast.Name) and n.id == "bool")


def test_c1_rule_lives_in_panelcheck():
    from toto import panelcheck
    assert _bool_checks(panelcheck.nonnegative_int) == 1
    for fn in (panel._score, moderator._goals):
        assert _bool_checks(fn) == 0, f"{fn.__name__} 가 규칙을 따로 들고 있다"
        src = inspect.getsource(fn)
        assert "nonnegative_int(" in src, fn.__name__


def _str_constants(fn) -> set[str]:
    """함수 안의 문자열 상수 (docstring 포함). 부분 문자열로 견주지 않는다 —
    패널 문구가 사회자 문구의 꼬리와 겹친다."""
    tree = ast.parse(inspect.getsource(fn).lstrip())
    return {n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def test_c2_wrappers_keep_their_names_and_messages():
    """이름과 문구는 부르는 쪽의 계약이라 제자리에 있다."""
    from toto import panelcheck
    const_p = _str_constants(panel._score)
    const_m = _str_constants(moderator._goals)
    const_c = _str_constants(panelcheck.nonnegative_int)
    assert set(PANEL_TAILS) <= const_p, const_p
    assert set(MOD_TAILS) <= const_m, const_m
    assert not set(PANEL_TAILS) & const_m
    assert not set(MOD_TAILS) & const_p
    assert not set(PANEL_TAILS + MOD_TAILS) & const_c, \
        "공통 규칙이 문구를 정하고 있다"


def test_c3_shared_rule_is_pure():
    """공통 규칙은 부르는 쪽의 뜻을 모른다 — 기본값·칸 이름을 정하지 않는다."""
    from toto import panelcheck
    sig = inspect.signature(panelcheck.nonnegative_int)
    assert list(sig.parameters) == ["value", "name", "not_int", "negative"]
    for p in ("not_int", "negative"):
        assert sig.parameters[p].kind is inspect.Parameter.KEYWORD_ONLY, p
        assert sig.parameters[p].default is inspect.Parameter.empty, p


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
