"""사회자 회귀 테스트 (Phase 3-C).

고정하려는 것은 다섯 가지다.

1. **사회자는 세 번째 분석가가 아니다.** 투표하지 않고, 시장을 의견으로
   세지 않으며, 누가 맞는지 고르지 않는다.
2. **같은 근거는 하나다.** 둘이 같은 ID 를 인용해도 공통 근거 하나이고,
   근거 개수를 세기로 쓰지 않는다.
3. **스코어는 채택이지 평균이 아니다.** 종합 예상 스코어 칸은 있지만
   **두 의견이 실제로 낸 조합**만 들어갈 수 있다 — 파서가 그 밖의 값을
   거부하므로 `1.5-1` 도 `2-2` 도 만들어질 수 없다.
4. **승무패를 만들지 않는다.** 관련 필드도 property 도 없다.
5. **읽기만 한다.** 자료와 의견을 바꾸지 않고, 축·근거·확률을 다시
   계산하지 않는다.

pytest 없이도 돈다:  python tests/test_moderator.py
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
from dataclasses import asdict, fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import llm, moderator, panel                            # noqa: E402
from toto.models import (MarketReference, ModeratorResult,        # noqa: E402
                         PanelOpinion, PanelRun, Report,
                         revive_moderator, revive_panel_run)
from toto.settings import Settings                                # noqa: E402
from test_panel import (FakeClient, GOOD, MODERATOR_OK, MemCache,  # noqa: E402
                        ev, make_match, S)


def opinion(role, ids=(), home=2, away=1):
    return PanelOpinion(role=role, predicted_home=home, predicted_away=away,
                        summary=f"{role} 의견", rationale=("근거 해석",),
                        evidence_ids=tuple(ids), model="test-model",
                        prompt_version="1")


def payload_of(n=8):
    return panel.build_panel_payload(make_match([ev(i) for i in range(1, n + 1)]))


def _mod_json(**over) -> str:
    """사회자 응답 한 벌. 스코어 칸만 바꿔 가며 파서를 시험한다."""
    body = {"common_points": ["표본이 작다"], "differences": ["스코어가 다르다"],
            "counterpoints": [], "score_comparison": "1골 차이",
            "market_relation": "", "uncertainty": [], "evidence_ids": []}
    body.update(over)
    return json.dumps(body, ensure_ascii=False)


DATA = moderator.DATA_ROLE
MATCHUP = moderator.MATCHUP_ROLE


# --------------------------------------------------------------------------
# A. 기본 동작
# --------------------------------------------------------------------------
def test_a1_two_panels_produce_a_result():
    res = moderator.run_moderator(
        payload_of(), [opinion(DATA, ["E001"]), opinion(MATCHUP, ["E002"])],
        settings=S, client=FakeClient())
    assert isinstance(res, ModeratorResult)
    assert res.status == "ok"
    assert res.panels_seen == (DATA, MATCHUP)
    assert res.common_points and res.differences


def test_a2_attached_to_the_panel_run():
    run = panel.run_match(make_match(), settings=S, client=FakeClient())
    assert isinstance(run, PanelRun)
    assert isinstance(run.moderator, ModeratorResult)
    assert run.moderator.panels_seen == (DATA, MATCHUP)


def test_a3_role_names_match_the_panel_module():
    """moderator 는 순환을 피하려고 역할 이름을 따로 들고 있다 — 어긋나면 안 된다."""
    assert moderator.DATA_ROLE == panel.DATA_ANALYST
    assert moderator.MATCHUP_ROLE == panel.MATCHUP_ANALYST


# --------------------------------------------------------------------------
# B. 근거 dedup
# --------------------------------------------------------------------------
def test_b4_shared_and_only_are_split():
    order = ("E001", "E002", "E003", "E004")
    shared, left, right = moderator.split_evidence(
        ["E001", "E002", "E003"], ["E002", "E003", "E004"], order)
    assert shared == ("E002", "E003")
    assert left == ("E001",)
    assert right == ("E004",)


def test_b5_same_id_is_counted_once():
    shared, left, right = moderator.split_evidence(
        ["E001"], ["E001"], ("E001", "E002"))
    assert shared == ("E001",), "같은 근거를 두 번 셌다"
    assert left == () and right == ()


def test_b6_split_is_computed_not_asked_of_the_model():
    """모델이 보낸 분류를 쓰지 않는다 — 집합 연산은 코드가 한다."""
    text = json.dumps({"common_points": ["a"], "differences": ["b"],
                       "counterpoints": [], "score_comparison": "",
                       "market_relation": "", "uncertainty": [],
                       "evidence_ids": [],
                       "shared_evidence_ids": ["E999"],       # 무시돼야 한다
                       "data_only_evidence_ids": ["E888"]})
    res = moderator.parse_result(
        text, panels_seen=(DATA,), shared=("E001",), data_only=("E002",),
        matchup_only=(), allowed_ids=("E001", "E002"))
    assert res.shared_evidence_ids == ("E001",)
    assert res.data_only_evidence_ids == ("E002",)


def test_b7_result_is_deterministic_regardless_of_input_order():
    order = ("E001", "E002", "E003", "E004", "E005")
    a = moderator.split_evidence(["E003", "E001"], ["E001", "E005"], order)
    b = moderator.split_evidence(["E001", "E003"], ["E005", "E001"], order)
    assert a == b
    assert a[1] == ("E003",) and a[2] == ("E005",)


def test_b8_order_follows_the_evidence_order_not_the_alphabet():
    order = ("E005", "E001", "E003")
    shared, _l, _r = moderator.split_evidence(
        ["E001", "E003", "E005"], ["E001", "E003", "E005"], order)
    assert shared == ("E005", "E001", "E003"), "근거 순서를 안 따랐다"


def test_b9_unknown_ids_go_last_but_stay_stable():
    shared, _l, _r = moderator.split_evidence(
        ["E002", "E777"], ["E002", "E777"], ("E001", "E002"))
    assert shared == ("E002", "E777")


# --------------------------------------------------------------------------
# C. 근거 개수는 세기가 아니다
# --------------------------------------------------------------------------
def test_c10_no_evidence_count_fields():
    names = {f.name for f in fields(ModeratorResult)}
    for banned in ("data_evidence_count", "matchup_evidence_count",
                   "evidence_advantage", "evidence_score", "score",
                   "strength", "confidence"):
        assert banned not in names, banned


def test_c11_more_citations_does_not_decide_anything():
    res = moderator.run_moderator(
        payload_of(),
        [opinion(DATA, ["E001", "E002", "E003", "E004", "E005"]),
         opinion(MATCHUP, ["E006"])],
        settings=S, client=FakeClient())
    blob = json.dumps(asdict(res), ensure_ascii=False)
    for banned in ("우세", "우위 판정", "winner", "더 강함"):
        assert banned not in blob, banned
    assert len(res.data_only_evidence_ids) == 5
    assert len(res.matchup_only_evidence_ids) == 1


def test_c12_no_count_based_comparison_in_the_code():
    src = inspect.getsource(moderator)
    for banned in ("len(data_ids) >", "len(matchup_ids) >",
                   "evidence_score", "advantage"):
        assert banned not in src, banned


# --------------------------------------------------------------------------
# D~E. Market Reference
# --------------------------------------------------------------------------
def test_d13_market_is_not_an_opinion():
    data = moderator.build_input(
        payload_of(), [opinion(DATA), opinion(MATCHUP)])
    assert len(data["opinions"]) == 2, "시장이 의견 목록에 들어갔다"
    assert "market_reference" in data
    assert all(o["role"] in (DATA, MATCHUP) for o in data["opinions"])


def test_d14_market_pick_fields_are_absent():
    data = moderator.build_input(payload_of(), [opinion(DATA)])
    blob = json.dumps(data, ensure_ascii=False)
    for banned in ("p_pick", "favorite", "toss_up", "pick"):
        assert banned not in blob, banned


def test_d15_prompt_forbids_treating_market_as_a_vote():
    for phrase in ("외부 기준선", "세 번째 전문가가 아닙니다", "3표 중 2표"):
        assert phrase in moderator.SYSTEM, phrase


def test_e16_missing_market_is_safe():
    m = make_match(with_odds=False)
    p = panel.build_panel_payload(m)
    assert p.market_reference is None
    res = moderator.run_moderator(p, [opinion(DATA), opinion(MATCHUP)],
                                  settings=S, client=FakeClient())
    assert res.status == "ok", "시장이 없다고 실패했다"
    data = moderator.build_input(p, [opinion(DATA)])
    assert data["market_reference"] is None


def test_e17_market_relation_is_prose_not_a_number():
    field_types = {f.name: f.type for f in fields(ModeratorResult)}
    assert field_types["market_relation"] == "str"


# --------------------------------------------------------------------------
# F~G. 패널 실패
# --------------------------------------------------------------------------
def test_f18_only_the_data_analyst():
    client = FakeClient([GOOD, llm.LLMError(llm.TIMEOUT)])
    run = panel.run_match(make_match(), settings=S, client=client)
    assert run.moderator is not None
    assert run.moderator.panels_seen == (DATA,), run.moderator.panels_seen
    assert len(client.moderator_calls) == 1


def test_f19_only_the_matchup_analyst():
    client = FakeClient([llm.LLMError(llm.SERVER_ERROR), GOOD])
    run = panel.run_match(make_match(), settings=S, client=client)
    assert run.moderator.panels_seen == (MATCHUP,)


def test_f20_one_panel_prompt_says_so():
    system, _u = moderator.build_prompt("{}", 1)
    assert moderator.ONE_PANEL_NOTE in system
    system2, _u2 = moderator.build_prompt("{}", 2)
    assert moderator.ONE_PANEL_NOTE not in system2


def test_g21_both_panels_failing_means_no_moderator_call():
    client = FakeClient([llm.LLMError(llm.TIMEOUT),
                         llm.LLMError(llm.TIMEOUT)])
    run = panel.run_match(make_match(), settings=S, client=client)
    assert run.opinions == ()
    assert run.moderator is None, "의견이 없는데 종합했다"
    assert client.moderator_calls == [], "의견이 없는데 API 를 불렀다"


def test_g22_no_evidence_means_no_moderator_call():
    client = FakeClient()
    run = panel.run_match(make_match([]), settings=S, client=client)
    assert run.moderator is None
    assert client.moderator_calls == []


def test_g23_moderator_failure_does_not_fake_a_result():
    client = FakeClient(moderator_reply=llm.LLMError(llm.TIMEOUT))
    run = panel.run_match(make_match(), settings=S, client=client)
    assert len(run.opinions) == 2, "사회자 실패가 패널을 죽였다"
    assert run.moderator.status.startswith("실패")
    assert run.moderator.common_points == ()
    assert run.moderator.panels_seen == (DATA, MATCHUP)


# --------------------------------------------------------------------------
# H. 가짜 근거 ID
# --------------------------------------------------------------------------
def test_h24_fake_evidence_id_is_rejected():
    text = json.dumps({"common_points": ["a"], "differences": ["b"],
                       "counterpoints": [], "score_comparison": "",
                       "market_relation": "", "uncertainty": [],
                       "evidence_ids": ["E999"]})
    try:
        moderator.parse_result(text, panels_seen=(DATA,), shared=(),
                               data_only=(), matchup_only=(),
                               allowed_ids=("E001",))
    except moderator.ValidationError as exc:
        assert "E999" in str(exc)
        return
    raise AssertionError("없는 근거 ID 가 통과했다")


def test_h25_empty_synthesis_is_rejected():
    text = json.dumps({"common_points": [], "differences": [],
                       "counterpoints": [], "score_comparison": "",
                       "market_relation": "", "uncertainty": [],
                       "evidence_ids": []})
    try:
        moderator.parse_result(text, panels_seen=(DATA,), shared=(),
                               data_only=(), matchup_only=(), allowed_ids=())
    except moderator.ValidationError:
        return
    raise AssertionError("빈 종합이 통과했다")


def test_h26_non_json_is_rejected():
    for junk in ("<html>", "그냥 문장", "[1,2]"):
        try:
            moderator.parse_result(junk, panels_seen=(), shared=(),
                                   data_only=(), matchup_only=(),
                                   allowed_ids=())
        except moderator.ValidationError:
            continue
        raise AssertionError(f"JSON 이 아닌데 통과했다: {junk}")


def test_h27_parse_failure_retries_once_then_gives_up():
    client = FakeClient(moderator_reply="틀린 응답")
    try:
        moderator.run_moderator(payload_of(), [opinion(DATA)],
                                settings=S, client=client)
    except moderator.ValidationError:
        assert len(client.moderator_calls) == 2
        assert moderator.RETRY_HINT in client.moderator_calls[1][1]
        return
    raise AssertionError("형식 오류인데 통과했다")


# --------------------------------------------------------------------------
# I~K. 스코어 / 승무패 / 평균
# --------------------------------------------------------------------------
def test_i28_no_wdl_fields():
    names = {f.name for f in fields(ModeratorResult)}
    attrs = set(dir(ModeratorResult))
    for banned in ("winner", "result", "wdl", "pick", "lean",
                   "recommendation", "confidence", "strength", "favorite",
                   "probability"):
        assert banned not in names, f"필드에 {banned} 가 있다"
        assert banned not in attrs, f"property 로 {banned} 가 있다"


def test_i29_the_adopted_score_is_one_of_the_proposals():
    """종합 스코어 칸은 있다. 다만 **제안 집합 안에서만** 채워진다.

    예전에는 칸 자체를 두지 않아 평균값을 막았는데, 그러면 사회자가 비교로
    끝나 "그래서 몇 대 몇인가" 에 닿지 못했다. 지금은 값의 출처를 제약해
    같은 결과를 얻는다 — 제안에 없는 조합은 파서가 거부한다.
    """
    res = moderator.run_moderator(
        payload_of(), [opinion(DATA, ["E001"]), opinion(MATCHUP, ["E002"])],
        settings=S, client=FakeClient())
    assert (res.adopted_home, res.adopted_away) == (2, 1)
    assert set(res.adopted_from) == {DATA, MATCHUP}
    assert res.score_rationale


def test_i29b_averaged_score_is_rejected():
    """`2-1` 과 `1-1` 에서 `1.5-1`·`2-2` 는 들어올 수 없다."""
    allowed = {DATA: (2, 1), MATCHUP: (1, 1)}
    for bad in (1.5, 2.0, "2", True, -1):
        with_score = _mod_json(adopted_home=bad, adopted_away=1)
        try:
            moderator.parse_result(with_score, panels_seen=(), shared=(),
                                   data_only=(), matchup_only=(),
                                   allowed_ids=(), allowed_scores=allowed)
        except moderator.ValidationError:
            continue
        raise AssertionError(f"{bad!r} 가 통과했다")
    # 정수이지만 아무도 제안하지 않은 조합
    try:
        moderator.parse_result(_mod_json(adopted_home=2, adopted_away=2),
                               panels_seen=(), shared=(), data_only=(),
                               matchup_only=(), allowed_ids=(),
                               allowed_scores=allowed)
    except moderator.ValidationError as exc:
        assert "낸 의견이 없습니다" in str(exc), exc
        return
    raise AssertionError("제안에 없는 2-2 가 통과했다")


def test_i29c_both_proposals_are_selectable():
    """갈렸을 때 **어느 쪽이든** 고를 수 있다 — 한쪽으로 몰지 않는다."""
    allowed = {DATA: (2, 1), MATCHUP: (1, 1)}
    for home, away, who in ((2, 1, DATA), (1, 1, MATCHUP)):
        res = moderator.parse_result(
            _mod_json(adopted_home=home, adopted_away=away,
                      adopted_from=[who], score_rationale="표본이 큰 쪽"),
            panels_seen=(), shared=(), data_only=(), matchup_only=(),
            allowed_ids=(), allowed_scores=allowed)
        assert (res.adopted_home, res.adopted_away) == (home, away)
        assert res.adopted_from == (who,)


def test_i29d_adopted_from_must_match_the_score():
    """"B 의 스코어를 채택했다" 면서 A 의 숫자를 적을 수 없다."""
    allowed = {DATA: (2, 1), MATCHUP: (1, 1)}
    try:
        moderator.parse_result(
            _mod_json(adopted_home=2, adopted_away=1, adopted_from=[MATCHUP]),
            panels_seen=(), shared=(), data_only=(), matchup_only=(),
            allowed_ids=(), allowed_scores=allowed)
    except moderator.ValidationError as exc:
        assert "내지 않았습니다" in str(exc), exc
        return
    raise AssertionError("출처가 어긋났는데 통과했다")


def test_i29e_missing_adopted_from_is_filled_from_the_proposals():
    """어디서 왔는지 빼먹으면 **제안 집합에서 채운다** (새로 만들지 않는다)."""
    res = moderator.parse_result(
        _mod_json(adopted_home=1, adopted_away=1),
        panels_seen=(), shared=(), data_only=(), matchup_only=(),
        allowed_ids=(), allowed_scores={DATA: (2, 1), MATCHUP: (1, 1)})
    assert res.adopted_from == (MATCHUP,)


def test_i29f_declining_needs_a_reason():
    """고르지 않는 것은 정직한 답이다 — 다만 이유를 적어야 한다."""
    kw = dict(panels_seen=(), shared=(), data_only=(), matchup_only=(),
              allowed_ids=(), allowed_scores={DATA: (2, 1), MATCHUP: (1, 1)})
    ok = moderator.parse_result(
        _mod_json(score_rationale="두 읽기 중 하나를 고를 근거가 없습니다"), **kw)
    assert ok.adopted_home is None and ok.adopted_away is None
    assert ok.adopted_from == ()
    try:
        moderator.parse_result(_mod_json(), **kw)
    except moderator.ValidationError as exc:
        assert "score_rationale" in str(exc), exc
        return
    raise AssertionError("이유 없이 비웠는데 통과했다")


def test_i29g_no_proposal_means_no_reason_needed():
    """두 의견 다 스코어가 없으면 빈 칸이 정답이고 변명을 요구하지 않는다."""
    res = moderator.parse_result(
        _mod_json(), panels_seen=(), shared=(), data_only=(),
        matchup_only=(), allowed_ids=(), allowed_scores={})
    assert res.adopted_home is None


def test_i29h_half_a_score_is_rejected():
    try:
        moderator.parse_result(
            _mod_json(adopted_home=2), panels_seen=(), shared=(),
            data_only=(), matchup_only=(), allowed_ids=(),
            allowed_scores={DATA: (2, 1)})
    except moderator.ValidationError as exc:
        assert "한쪽만" in str(exc), exc
        return
    raise AssertionError("홈 득점만 있는데 통과했다")


def test_i29i_proposed_scores_skips_opinions_without_one():
    got = moderator.proposed_scores(
        [opinion(DATA, home=2, away=1), opinion(MATCHUP, home=None, away=1)])
    assert got == {DATA: (2, 1)}


def test_i29j_no_representative_score_field():
    """평균·합의를 뜻하는 이름은 여전히 없다 — `adopted_*` 만 있다."""
    names = {f.name for f in fields(ModeratorResult)}
    for banned in ("predicted_home", "predicted_away", "final_home",
                   "final_away", "consensus_home", "consensus_away",
                   "average_home", "average_away"):
        assert banned not in names, banned
    assert {"adopted_home", "adopted_away", "adopted_from",
            "score_rationale"} <= names


def test_i29k_retry_tells_the_model_what_was_wrong():
    """고칠 수 있는 오류인데 같은 답을 되풀이하게 두지 않는다."""
    hint = moderator.retry_hint("채택한 스코어 2-2 를 낸 의견이 없습니다")
    assert moderator.RETRY_HINT in hint
    assert "2-2" in hint
    assert moderator.retry_hint("") == moderator.RETRY_HINT


def test_j30_differing_scores_produce_no_verdict():
    res = moderator.run_moderator(
        payload_of(),
        [opinion(DATA, ["E001"], home=2, away=1),
         opinion(MATCHUP, ["E001"], home=1, away=1)],
        settings=S, client=FakeClient())
    blob = json.dumps(asdict(res), ensure_ascii=False)
    for banned in ("홈승", "원정승", "무승부 추천", "추천", "베팅",
                   "winner", "pick"):
        assert banned not in blob, banned


def test_k31_no_averaging_in_the_code():
    """평균·다수결을 **구현**하지 않는다.

    문자열 검색은 쓰지 않는다 — 모듈 설명과 프롬프트에 "투표하지 않는다"·
    "평균내지 않는다" 라고 적혀 있어서 그 부정문에 그대로 걸린다(실제로
    걸렸다). 실행되는 코드만 본다: 주석과 문자열 상수를 걷어낸 뒤 나눗셈
    연산과 평균 함수 호출이 있는지 검사한다.
    """
    tree = ast.parse(inspect.getsource(moderator))
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(
                node.op, (ast.Div, ast.FloorDiv)):
            raise AssertionError("나눗셈이 있다 (평균을 만들고 있나)")
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", "") or getattr(
                node.func, "attr", "")
            assert name not in ("mean", "fmean", "median", "average",
                                "round"), f"{name}() 를 쓰고 있다"


def test_k32_no_score_comparison_operator():
    """스코어를 비교해 승패를 만드는 코드가 없어야 한다."""
    tree = ast.parse(inspect.getsource(moderator))
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            blob = ast.dump(node)
            assert "predicted_" not in blob, "예상 스코어를 비교하고 있다"


def test_k33_prompt_forbids_averaging_and_wdl():
    for phrase in ("평균내거나", "승/무/패를 도출하지",
                   "최종 판단은 사용자가", "근거 개수를 세기로"):
        assert phrase in moderator.SYSTEM, phrase


# --------------------------------------------------------------------------
# N~O. 입력 불변
# --------------------------------------------------------------------------
def test_n34_payload_is_unchanged():
    p = payload_of()
    before = (panel.serialize_payload(p), panel.payload_hash(p))
    moderator.run_moderator(p, [opinion(DATA), opinion(MATCHUP)],
                            settings=S, client=FakeClient())
    assert (panel.serialize_payload(p), panel.payload_hash(p)) == before


def test_o35_opinions_are_unchanged():
    ops = [opinion(DATA, ["E001"]), opinion(MATCHUP, ["E002"])]
    before = [asdict(o) for o in ops]
    moderator.run_moderator(payload_of(), ops, settings=S,
                            client=FakeClient())
    assert [asdict(o) for o in ops] == before


def test_o36_moderator_does_not_recompute_anything():
    tree = ast.parse(inspect.getsource(moderator))
    mods = [n.module for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom) and n.module]
    mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
             for a in n.names]
    for banned in ("analysis", "evidence", "predict", "xpts", "shots",
                   "sources", "requests", "cache", "render", "menu"):
        assert not any(banned in (m or "") for m in mods), banned


def test_o37_input_drops_the_axis_dumps():
    """자료를 통째로 다시 보내지 않는다 (§20).

    크기 비율로 재지 않는다 — 합성 픽스처에는 축 지표 덤프가 없어서 비율이
    실물과 전혀 다르다(실측 1,682 vs 2,610). 무엇이 빠졌는지를 **구조로**
    본다: 용량의 대부분을 차지하는 축 요약(실물 86%)과 notes 가 없어야 한다.
    """
    p = payload_of()
    data = moderator.build_input(p, [opinion(DATA), opinion(MATCHUP)])
    for dropped in ("home", "away", "data_quality"):
        assert dropped not in data, f"{dropped} 를 그대로 다시 보내고 있다"
    blob = moderator.serialize_input(data)
    for token in ('"metrics"', '"notes"', '"provenance"'):
        assert token not in blob, f"축 덤프({token})가 들어 있다"
    assert len(blob) < len(panel.serialize_payload(p))


def test_o37b_input_keeps_what_the_moderator_cannot_reconstruct():
    """축소 검증에서 **남기기로 정한 둘**이 실제로 실린다.

    빼면 사회자가 할 일을 못 한다:

      · `conflicts`             2-G 가 이미 찾은 방향 불일치 — "왜 갈렸나"
                                의 원재료이고 다른 칸으로 복원할 수 없다
      · `source`/`measurement_basis`  측정 방식이 다르면 직접 견줄 수 없다
                                (§1-1-9). `claim` 문장으로는 알 수 없다
    """
    p = payload_of()
    data = moderator.build_input(p, [opinion(DATA), opinion(MATCHUP)])
    assert "conflicts" in data, "2-G 방향 불일치가 사라졌다"
    for row in data["evidence"]:
        assert "source" in row and "measurement_basis" in row
    # 이름이 겹치면 안 된다 — conflicts 의 basis 는 신호 설명이라 뜻이 다르다
    assert all("basis" != k for row in data["evidence"] for k in row
               if k == "basis")


def test_o37c_conflicts_are_passed_through_not_recomputed():
    m = make_match()
    from toto.models import Signal
    m.analysis.conflicts = [Signal(name="goals_vs_xg 방향 불일치",
                                   basis="H: 최근 3경기 +0.55 ↔ 최근 6경기 -0.40",
                                   note="표본에 따라 방향이 다릅니다.")]
    data = moderator.build_input(panel.build_panel_payload(m),
                                 [opinion(DATA)])
    assert len(data["conflicts"]) == 1
    assert data["conflicts"][0]["basis"].startswith("H:")
    assert "goals_vs_xg" in data["conflicts"][0]["name"]


def test_o37d_prompt_explains_the_two_retained_fields():
    """모델이 알아서 이해할 것이라 가정하지 않는다 (§14)."""
    for phrase in ("measurement_basis", "conflicts",
                   "직접 견줄 수 없습니다", "이미 발견된"):
        assert phrase in moderator.SYSTEM, phrase


def test_o38_input_keeps_every_evidence_id():
    p = payload_of()
    data = moderator.build_input(p, [opinion(DATA)])
    assert [e["id"] for e in data["evidence"]] == list(p.evidence_ids)


# --------------------------------------------------------------------------
# 캐시
# --------------------------------------------------------------------------
def test_39_cache_hit_avoids_a_second_call():
    cache, p = MemCache(), payload_of()
    ops = [opinion(DATA), opinion(MATCHUP)]
    c1 = FakeClient()
    moderator.run_moderator(p, ops, settings=S, cache=cache, client=c1)
    c2 = FakeClient()
    moderator.run_moderator(p, ops, settings=S, cache=cache, client=c2)
    assert len(c1.moderator_calls) == 1 and c2.moderator_calls == []


def test_40_changed_opinion_invalidates():
    cache, p = MemCache(), payload_of()
    moderator.run_moderator(p, [opinion(DATA), opinion(MATCHUP)],
                            settings=S, cache=cache, client=FakeClient())
    c2 = FakeClient()
    moderator.run_moderator(p, [opinion(DATA, home=3), opinion(MATCHUP)],
                            settings=S, cache=cache, client=c2)
    assert len(c2.moderator_calls) == 1, "의견이 바뀌었는데 캐시를 썼다"


def test_40b_changed_market_invalidates():
    cache = MemCache()
    ops = [opinion(DATA)]
    with_odds = panel.build_panel_payload(make_match())
    moderator.run_moderator(with_odds, ops, settings=S, cache=cache,
                            client=FakeClient())
    c2 = FakeClient()
    moderator.run_moderator(panel.build_panel_payload(
        make_match(with_odds=False)), ops, settings=S, cache=cache, client=c2)
    assert len(c2.moderator_calls) == 1, "시장이 바뀌었는데 캐시를 썼다"


def test_40c_changed_evidence_content_invalidates():
    """입력에 **실린** 근거 정보가 바뀌면 미적중이어야 한다."""
    cache = MemCache()
    ops = [opinion(DATA, ["E001"])]
    moderator.run_moderator(panel.build_panel_payload(make_match([ev(1)])),
                            ops, settings=S, cache=cache, client=FakeClient())
    c2 = FakeClient()
    moderator.run_moderator(
        panel.build_panel_payload(make_match([ev(1, value=9.9)])),
        ops, settings=S, cache=cache, client=c2)
    assert len(c2.moderator_calls) == 1, "근거 값이 바뀌었는데 캐시를 썼다"


def test_40d_irrelevant_payload_change_may_hit():
    """입력에 **안 실리는** 자료가 바뀌면 적중해도 된다 (§11).

    사회자 캐시는 **사회자가 실제로 받은 것**을 추적한다. 축 지표 덤프는
    입력에 없으므로 그것만 달라진 경우 다시 물을 이유가 없다 — 같은 질문에
    같은 자료를 준 것이기 때문이다.
    """
    from toto.models import AnalysisAxis, Metric, TeamAnalysis
    cache = MemCache()
    ops = [opinion(DATA, ["E001"])]
    base = make_match([ev(1)])
    moderator.run_moderator(panel.build_panel_payload(base), ops,
                            settings=S, cache=cache, client=FakeClient())

    other = make_match([ev(1)])
    ta = TeamAnalysis(team="H", is_home=True)
    axis = AnalysisAxis(name="chance_quality")
    axis.metrics["recent6.xg"] = Metric(name="xg", value=1.23, period="recent6")
    ta.chance_quality = axis
    other.analysis.home = ta                      # 근거로 이어지지 않는 축
    p2 = panel.build_panel_payload(other)
    assert p2.home != panel.build_panel_payload(base).home, "자료가 안 바뀌었다"
    c2 = FakeClient()
    moderator.run_moderator(p2, ops, settings=S, cache=cache, client=c2)
    assert c2.moderator_calls == [], "사회자가 못 본 변경으로 다시 물었다"


def test_40e_cache_tracks_the_moderator_input_not_the_panel_payload():
    """캐시 키의 대상이 무엇인지 코드로 고정한다."""
    src = inspect.getsource(moderator.run_moderator)
    assert "input_hash(payload_in)" in src
    assert "payload_hash" not in src, "패널 자료 해시를 키로 쓰고 있다"


def test_41_model_change_invalidates():
    cache, p = MemCache(), payload_of()
    ops = [opinion(DATA)]
    moderator.run_moderator(p, ops, settings=S, cache=cache,
                            client=FakeClient())
    c2 = FakeClient()
    moderator.run_moderator(p, ops, settings=Settings(panel={"model": "x"}),
                            cache=cache, client=c2)
    assert len(c2.moderator_calls) == 1


def test_42_corrupt_cache_is_a_miss():
    cache, p = MemCache(), payload_of()
    ops = [opinion(DATA)]
    moderator.run_moderator(p, ops, settings=S, cache=cache,
                            client=FakeClient())
    for key in list(cache.data):
        cache.data[key] = {"쓰레기": 1}
    c2 = FakeClient()
    moderator.run_moderator(p, ops, settings=S, cache=cache, client=c2)
    assert len(c2.moderator_calls) == 1


def test_43_cache_versions_are_independent():
    assert moderator.MODERATOR_CACHE_VERSION == 1
    assert moderator.CACHE_SOURCE != panel.CACHE_SOURCE
    from toto.sources import fotmob
    assert fotmob._CACHE_VERSION == 9, "소스 캐시 버전을 건드렸다"


def test_44_cache_never_stores_the_api_key():
    cache = MemCache()
    moderator.run_moderator(payload_of(), [opinion(DATA)], settings=S,
                            cache=cache, client=FakeClient())
    assert "sk-" not in json.dumps(list(cache.data.values()),
                                   ensure_ascii=False)


# --------------------------------------------------------------------------
# 직렬화
# --------------------------------------------------------------------------
def test_45_roundtrip():
    run = panel.run_match(make_match(), settings=S, client=FakeClient())
    back = revive_panel_run(json.loads(json.dumps(asdict(run),
                                                  ensure_ascii=False)))
    assert back.moderator == run.moderator


def test_46_report_to_dict_includes_the_moderator():
    m = make_match()
    m.panel = panel.run_match(m, settings=S, client=FakeClient())
    d = Report(round_id="260048", matches=[m]).to_dict()
    assert d["matches"][0]["panel"]["moderator"]["status"] == "ok"
    assert json.dumps(d, ensure_ascii=False, default=str)


def test_47_old_payload_without_the_moderator_revives():
    assert revive_moderator(None) is None
    assert revive_moderator({}) == ModeratorResult()
    old = {"status": "ok (2/2 분석가)", "opinions": [], "role_status": {},
           "market_reference": None, "evidence_ids": [], "payload_hash": "x"}
    assert revive_panel_run(old).moderator is None


# --------------------------------------------------------------------------
# 경계
# --------------------------------------------------------------------------
def test_48_llm_client_is_reused_not_reimplemented():
    src = inspect.getsource(moderator)
    assert "anthropic" not in src, "새 클라이언트를 만들고 있다"
    assert "llm.complete" in src


def test_49_renderer_reads_the_moderator_without_deciding():
    """3-D 가 사회자를 화면에 내지만 **판정을 만들지 않는다.**

    예전에는 '렌더러가 사회자를 모른다' 로 확인했는데 3-D 에서 연결됐다.
    지키려는 것은 '렌더러가 종합에서 승무패를 뽑지 않는다' 이므로 그쪽을
    본다.
    """
    import ast as _ast

    from toto import render
    src = "\n".join(inspect.getsource(fn) for fn in
                    (render._moderator_block, render._adopted_block))
    tree = _ast.parse(src)
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Compare):
            dump = _ast.dump(node)
            assert "predicted_" not in dump
            # 채택한 스코어를 견주어 승패를 만들지 않는다. `is None` 검사는
            # 값의 유무를 보는 것이라 크기 비교와 다르다.
            for op in node.ops:
                if isinstance(op, (_ast.Lt, _ast.Gt, _ast.LtE, _ast.GtE)):
                    assert "adopted" not in dump, "채택 스코어를 비교하고 있다"
        if isinstance(node, _ast.BinOp) and isinstance(
                node.op, (_ast.Div, _ast.FloorDiv)):
            raise AssertionError("사회자 렌더링에 나눗셈이 있다")
    for banned in ("winner", "wdl", "pick", "recommendation", "confidence"):
        assert banned not in src, banned


def test_50_run_all_does_not_reach_the_moderator():
    from toto.analyze import run_all
    assert "moderator" not in ast.dump(ast.parse(inspect.getsource(run_all)))


# --------------------------------------------------------------------------
def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as exc:
            bad += 1
            print(f"  FAIL {name}: {exc}")
        except Exception as exc:                            # noqa: BLE001
            bad += 1
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - bad}/{len(tests)} 통과")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
