"""패널 회귀 테스트 (Phase 3-B · 두 전문가 패널).

고정하려는 것은 네 가지 불변조건이다.

1. **Market Reference 는 분석가가 아니다.** 역할 목록에 없고, `PanelOpinion`
   이 아니며, 선택값 계열(pick·favorite·toss_up)을 싣지 않는다.
2. **두 분석가는 같은 `PanelPayload` 객체와 같은 문자열을 받는다.**
3. **근거 ID 는 전역 공유다.** 패널이 자기 ID 를 만들면 떨어뜨린다.
4. **예상 스코어에서 승무패를 파생하지 않는다.** 그런 필드도 property 도
   존재하지 않는다.

그리고 돈이 드는 계층이므로: `--panel` 없이는 호출 0회, 근거 0건이면 호출
0회, 키·SDK 가 없어도 기존 프로그램은 그대로 돈다.

pytest 없이도 돈다:  python tests/test_panel.py
"""
from __future__ import annotations

import ast
import inspect
import json
import os
import sys
from dataclasses import asdict, fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import llm, panel                                      # noqa: E402
from toto.models import (Match, MarketReference, MatchAnalysis,  # noqa: E402
                         Odds, PanelOpinion, PanelRun, Report, TeamRef,
                         EvidenceItem, revive_panel_run)
from toto.predict import additive_probabilities                  # noqa: E402
from toto.settings import Settings                               # noqa: E402

S = Settings(panel={"model": "test-model", "max_tokens": 100,
                    "timeout_sec": 5})

GOOD = json.dumps({"predicted_home": 2, "predicted_away": 1,
                   "summary": "홈이 더 많은 기회를 만들었습니다.",
                   "rationale": ["E001 은 최근 xG 우위를 보여준다"],
                   "evidence_ids": ["E001"]}, ensure_ascii=False)


# 채택 스코어는 `GOOD`(2-1)과 같아야 한다 — 두 의견이 낸 조합만 통과한다.
MODERATOR_OK = json.dumps(
    {"common_points": ["두 의견 모두 표본이 작다고 본다"],
     "differences": ["예상 스코어가 다르다"],
     "counterpoints": [], "score_comparison": "홈 득점 예상이 1골 다르다",
     "adopted_home": 2, "adopted_away": 1,
     "score_rationale": "두 의견의 스코어가 같아 그대로 채택했습니다",
     "market_relation": "", "uncertainty": ["표본 1경기"],
     "evidence_ids": []}, ensure_ascii=False)


class FakeClient:
    """`complete(system, user)` 하나만 있으면 된다. 실제 API 를 부르지 않는다.

    **분석가 호출과 사회자 호출을 나눠 센다.** 3-C 에서 `run_match` 가 세
    번째 호출(사회자)을 하게 됐는데, 그것까지 같은 대본에서 꺼내면 3-B 의
    호출 수 단언이 전부 어긋난다. 사회자 호출은 대본을 소비하지 않고
    `moderator_calls` 에만 쌓이므로 3-B 단언은 **한 글자도 바뀌지 않는다.**
    """

    def __init__(self, replies=None, moderator_reply=None):
        self.replies = list(replies) if replies is not None else None
        self.moderator_reply = moderator_reply
        self.calls: list[tuple[str, str]] = []            # 분석가
        self.moderator_calls: list[tuple[str, str]] = []  # 사회자

    def complete(self, system, user):
        if "사회자" in system:
            self.moderator_calls.append((system, user))
            reply = (self.moderator_reply if self.moderator_reply is not None
                     else MODERATOR_OK)
            if isinstance(reply, BaseException):
                raise reply
            return reply
        self.calls.append((system, user))
        if self.replies is None:
            return GOOD
        if not self.replies:
            raise AssertionError("응답 대본이 떨어졌다 (호출이 예상보다 많다)")
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


class MemCache:
    """`Cache` 와 같은 모양의 메모리 캐시."""

    def __init__(self):
        self.data: dict[tuple[str, str], object] = {}
        self.reads = 0

    def get(self, source, key):
        self.reads += 1
        return self.data.get((source, key))

    def set(self, source, key, value):
        self.data[(source, key)] = json.loads(json.dumps(value,
                                                         ensure_ascii=False))


def ev(idx, team="H", metric="xg", value=1.7, n=6):
    return EvidenceItem(claim=f"근거 {idx}", metric=metric, value=value,
                        period="recent6", sample_count=n, axis="chance_quality",
                        team=team, category="attack", context="recent",
                        finding_kind="chance_and_execution",
                        supporting_metrics=[metric], supporting_axes=[],
                        source="shotmap", measurement_basis="shot_events")


def make_match(evidence_items=None, with_odds=True) -> Match:
    m = Match(no=1, league="epl", league_ko="프리미어리그",
              kickoff_kst="2026-08-29 20:00",
              home=TeamRef(canonical="H", display="홈팀"),
              away=TeamRef(canonical="A", display="원정팀"),
              odds=(Odds(home=2.90, draw=3.40, away=2.45,
                         source="arcadia-api", fetched_at="2026-08-29 18:00")
                    if with_odds else Odds()))
    if with_odds:
        m.probs = additive_probabilities(2.90, 3.40, 2.45)
    m.analysis = MatchAnalysis()
    m.analysis.evidence = list(evidence_items if evidence_items is not None
                               else [ev(1), ev(2, team="A")])
    return m


# --------------------------------------------------------------------------
# 1~4. PanelPayload · 직렬화 · 결정성 · 해시
# --------------------------------------------------------------------------
def test_01_payload_is_built_from_existing_facts():
    p = panel.build_panel_payload(make_match())
    assert p.match_no == 1 and p.home_team == "홈팀" and p.away_team == "원정팀"
    assert len(p.evidence) == 2
    assert p.market_reference is not None


def test_02_payload_serializes_to_json():
    js = panel.serialize_payload(panel.build_panel_payload(make_match()))
    back = json.loads(js)
    assert back["match_no"] == 1
    assert back["evidence"][0]["id"] == "E001"


def test_03_serialization_is_deterministic():
    m = make_match()
    a = panel.serialize_payload(panel.build_panel_payload(m))
    b = panel.serialize_payload(panel.build_panel_payload(m))
    assert a == b
    assert a.index('"away_team"') < a.index('"home_team"'), "키 정렬이 안 됐다"


def test_04_hash_is_deterministic_and_content_sensitive():
    m = make_match()
    h1 = panel.payload_hash(panel.build_panel_payload(m))
    assert h1 == panel.payload_hash(panel.build_panel_payload(m))
    m2 = make_match([ev(1), ev(2, team="A"), ev(3)])
    assert panel.payload_hash(panel.build_panel_payload(m2)) != h1


def test_04b_hash_does_not_contain_the_role():
    """역할은 캐시 키에서 따로 붙는다 (§82)."""
    src = inspect.getsource(panel.payload_hash)
    assert "role" not in src


# --------------------------------------------------------------------------
# 5~6. Market Reference
# --------------------------------------------------------------------------
def test_05_market_reference_reads_existing_probabilities():
    m = make_match()
    ref = panel.market_reference(m)
    assert (ref.home_probability, ref.draw_probability, ref.away_probability) \
        == (m.probs.home, m.probs.draw, m.probs.away)
    assert ref.overround == m.probs.overround
    assert ref.source == "arcadia-api" and ref.as_of == "2026-08-29 18:00"


def test_06_market_reference_has_no_pick_like_field():
    names = {f.name for f in fields(MarketReference)}
    for banned in ("pick", "p_pick", "favorite", "toss_up", "winner", "wdl",
                   "lean", "recommendation", "confidence"):
        assert banned not in names, banned
    js = panel.serialize_payload(panel.build_panel_payload(make_match()))
    for banned in ("p_pick", "favorite", "toss_up"):
        assert banned not in js, banned


def test_06b_market_reference_is_not_a_role():
    """불변조건 1 — 역할 목록에 시장이 없다."""
    assert panel.ROLES == (panel.DATA_ANALYST, panel.MATCHUP_ANALYST)
    assert len(panel.ROLES) == 2
    blob = " ".join(panel.ROLE_PROMPTS.values()) + " ".join(panel.ROLES)
    for banned in ("market_analyst", "Market Analyst", "시장 분석가",
                   "odds_analyst"):
        assert banned not in blob, banned
    assert not isinstance(MarketReference(), PanelOpinion)


def test_06c_missing_market_reference_is_not_a_failure():
    m = make_match(with_odds=False)
    p = panel.build_panel_payload(m)
    assert p.market_reference is None
    client = FakeClient()
    run = panel.run_match(m, settings=S, client=client)
    assert len(run.opinions) == 2, "시장이 없다고 패널이 실패했다"


# --------------------------------------------------------------------------
# 7~8. 같은 payload (불변조건 2)
# --------------------------------------------------------------------------
def test_07_both_roles_get_the_same_payload_object():
    seen = []
    real = panel.run_panel_role

    def spy(role, payload, payload_json, **kw):
        seen.append((role, payload, payload_json))
        return real(role, payload, payload_json, **kw)

    panel.run_panel_role = spy
    try:
        panel.run_match(make_match(), settings=S, client=FakeClient())
    finally:
        panel.run_panel_role = real
    assert len(seen) == 2
    assert seen[0][1] is seen[1][1], "두 역할이 서로 다른 payload 객체를 받았다"


def test_08_both_roles_get_the_same_serialized_payload():
    client = FakeClient()
    panel.run_match(make_match(), settings=S, client=client)
    assert len(client.calls) == 2
    users = [u for _s, u in client.calls]
    assert users[0] == users[1], "직렬화된 자료가 역할마다 다르다"
    systems = [s for s, _u in client.calls]
    assert systems[0] != systems[1], "역할 지시가 같다 (관점이 안 갈린다)"


def test_08b_role_prompt_does_not_filter_the_payload():
    """역할 프롬프트는 관점만 바꾼다 — 자료를 골라 주지 않는다 (§85)."""
    for text in panel.ROLE_PROMPTS.values():
        for banned in ("너에게는", "다음 지표만", "일부만"):
            assert banned not in text, banned


# --------------------------------------------------------------------------
# 9~10. 두 역할 파싱
# --------------------------------------------------------------------------
def test_09_data_analyst_parses():
    op = panel.parse_opinion(GOOD, panel.DATA_ANALYST, ["E001"])
    assert op.role == panel.DATA_ANALYST
    assert (op.predicted_home, op.predicted_away) == (2, 1)
    assert op.evidence_ids == ("E001",)


def test_10_matchup_analyst_parses():
    op = panel.parse_opinion(GOOD, panel.MATCHUP_ANALYST, ["E001"])
    assert op.role == panel.MATCHUP_ANALYST


def test_10b_role_is_injected_not_taken_from_the_model():
    text = json.dumps({"role": "market_analyst", "predicted_home": 1,
                       "predicted_away": 1, "summary": "s",
                       "rationale": [], "evidence_ids": []})
    op = panel.parse_opinion(text, panel.DATA_ANALYST, [])
    assert op.role == panel.DATA_ANALYST, "모델이 역할을 정했다"


def test_10c_fenced_json_is_accepted():
    op = panel.parse_opinion("```json\n" + GOOD + "\n```",
                             panel.DATA_ANALYST, ["E001"])
    assert op.predicted_home == 2


def test_10d_null_score_is_allowed():
    text = json.dumps({"predicted_home": None, "predicted_away": None,
                       "summary": "표본이 부족합니다", "rationale": [],
                       "evidence_ids": []})
    op = panel.parse_opinion(text, panel.DATA_ANALYST, [])
    assert op.predicted_home is None and op.predicted_away is None


# --------------------------------------------------------------------------
# 11. 근거 ID (불변조건 3)
# --------------------------------------------------------------------------
def test_11_unknown_evidence_id_is_rejected():
    text = json.dumps({"predicted_home": 1, "predicted_away": 0,
                       "summary": "s", "rationale": [],
                       "evidence_ids": ["E999"]})
    try:
        panel.parse_opinion(text, panel.DATA_ANALYST, ["E001"])
    except panel.ValidationError as exc:
        assert "E999" in str(exc)
    else:
        raise AssertionError("없는 근거 ID 가 통과했다")


def test_11b_evidence_ids_are_shared_between_roles():
    """같은 E01 을 두 역할이 인용해도 같은 문자열이다 (3-C 가 dedup 한다)."""
    reply = json.dumps({"predicted_home": 1, "predicted_away": 1,
                        "summary": "s", "rationale": [],
                        "evidence_ids": ["E001"]})
    run = panel.run_match(make_match(), settings=S,
                          client=FakeClient([reply, reply]))
    ids = [op.evidence_ids for op in run.opinions]
    assert ids == [("E001",), ("E001",)]
    assert run.evidence_ids == ("E001", "E002")


def test_11c_ids_follow_the_stored_evidence_order():
    rows = panel.evidence_rows(make_match([ev(1), ev(2), ev(3)]))
    assert [r["id"] for r in rows] == ["E001", "E002", "E003"]


def test_11d_panel_does_not_rebuild_evidence():
    """근거를 다시 만들지 않는다 — evidence·analysis 를 import 하지 않는다."""
    tree = ast.parse(inspect.getsource(panel))
    mods = [n.module for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom) and n.module]
    mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
             for a in n.names]
    for banned in ("evidence", "analysis", "predict", "xpts", "shots",
                   "sources", "requests"):
        assert not any(banned in (m or "") for m in mods), banned


# --------------------------------------------------------------------------
# 12. 스코어 검증
# --------------------------------------------------------------------------
def test_12_negative_score_is_rejected():
    text = json.dumps({"predicted_home": -1, "predicted_away": 2,
                       "summary": "s", "rationale": [], "evidence_ids": []})
    try:
        panel.parse_opinion(text, panel.DATA_ANALYST, [])
    except panel.ValidationError:
        return
    raise AssertionError("음수 스코어가 통과했다")


def test_12b_float_score_is_rejected():
    text = json.dumps({"predicted_home": 1.5, "predicted_away": 1,
                       "summary": "s", "rationale": [], "evidence_ids": []})
    try:
        panel.parse_opinion(text, panel.DATA_ANALYST, [])
    except panel.ValidationError:
        return
    raise AssertionError("실수 스코어가 통과했다")


def test_12c_string_score_is_not_repaired():
    """`\"2-1\"` 을 2 와 1 로 해석해 주지 않는다 (§105)."""
    text = json.dumps({"predicted_home": "2-1", "predicted_away": None,
                       "summary": "s", "rationale": [], "evidence_ids": []})
    try:
        panel.parse_opinion(text, panel.DATA_ANALYST, [])
    except panel.ValidationError:
        return
    raise AssertionError("문자열 스코어가 보정돼 통과했다")


def test_12d_bool_is_not_an_integer_here():
    text = json.dumps({"predicted_home": True, "predicted_away": 0,
                       "summary": "s", "rationale": [], "evidence_ids": []})
    try:
        panel.parse_opinion(text, panel.DATA_ANALYST, [])
    except panel.ValidationError:
        return
    raise AssertionError("불리언이 정수로 통과했다")


def test_12e_empty_summary_is_rejected():
    text = json.dumps({"predicted_home": 1, "predicted_away": 0,
                       "summary": "  ", "rationale": [], "evidence_ids": []})
    try:
        panel.parse_opinion(text, panel.DATA_ANALYST, [])
    except panel.ValidationError:
        return
    raise AssertionError("빈 summary 가 통과했다")


def test_12f_non_json_is_rejected():
    for junk in ("<html>안녕</html>", "그냥 문장입니다", "[1, 2, 3]"):
        try:
            panel.parse_opinion(junk, panel.DATA_ANALYST, [])
        except panel.ValidationError:
            continue
        raise AssertionError(f"JSON 이 아닌 응답이 통과했다: {junk}")


# --------------------------------------------------------------------------
# 13. 근거 0건이면 호출 없음
# --------------------------------------------------------------------------
def test_13_no_evidence_means_no_api_call():
    client = FakeClient()
    run = panel.run_match(make_match([]), settings=S, client=client)
    assert client.calls == [], "근거 0건인데 API 를 불렀다"
    assert run.status.startswith("생략")
    assert run.opinions == ()


def test_13b_skipped_match_still_records_the_market_reference():
    run = panel.run_match(make_match([]), settings=S, client=FakeClient())
    assert run.market_reference is not None


# --------------------------------------------------------------------------
# 14~15. 키·SDK 없음
# --------------------------------------------------------------------------
def test_14_missing_api_key_is_reported_not_crashed():
    had = os.environ.pop(llm.API_KEY_ENV, None)
    try:
        status = panel.attach_panels([make_match()], S)
    finally:
        if had is not None:
            os.environ[llm.API_KEY_ENV] = had
    assert status.startswith("실패"), status
    assert "anthropic" in status or "API_KEY" in status


def test_14b_no_fake_opinion_when_unavailable():
    m = make_match()
    had = os.environ.pop(llm.API_KEY_ENV, None)
    try:
        panel.attach_panels([m], S)
    finally:
        if had is not None:
            os.environ[llm.API_KEY_ENV] = had
    assert m.panel is None or not m.panel.opinions, "가짜 의견을 만들었다"


class _FakeSDK:
    """`anthropic` 자리에 끼워 넣는 최소 모듈 — 키 판정 경로를 실제로 밟는다.

    이 환경에는 anthropic 이 설치돼 있지 않아서, 흉내내지 않으면 언제나
    `sdk_unavailable` 에서 멈춰 '키 없음' 분기가 한 번도 실행되지 않는다.
    """

    class Anthropic:
        def __init__(self, api_key=None, timeout=None):
            self.api_key = api_key


def _with_fake_sdk(fn):
    real = sys.modules.get("anthropic")
    sys.modules["anthropic"] = _FakeSDK
    try:
        return fn()
    finally:
        if real is None:
            sys.modules.pop("anthropic", None)
        else:
            sys.modules["anthropic"] = real


def test_14c_sdk_present_but_no_key():
    had = os.environ.pop(llm.API_KEY_ENV, None)
    try:
        assert _with_fake_sdk(llm.unavailable_reason) == llm.NO_API_KEY
    finally:
        if had is not None:
            os.environ[llm.API_KEY_ENV] = had


def test_14d_sdk_and_key_present_is_available():
    had = os.environ.get(llm.API_KEY_ENV)
    os.environ[llm.API_KEY_ENV] = "sk-테스트"
    try:
        assert _with_fake_sdk(llm.unavailable_reason) == ""
    finally:
        if had is None:
            os.environ.pop(llm.API_KEY_ENV, None)
        else:
            os.environ[llm.API_KEY_ENV] = had


def test_14e_no_key_reaches_the_panel_status():
    had = os.environ.pop(llm.API_KEY_ENV, None)
    m = make_match()
    try:
        status = _with_fake_sdk(lambda: panel.attach_panels([m], S))
    finally:
        if had is not None:
            os.environ[llm.API_KEY_ENV] = had
    assert "ANTHROPIC_API_KEY 없음" in status, status
    assert m.panel is None, "실패했는데 패널이 붙었다"


def test_14f_client_never_returns_the_key():
    """`unavailable_reason()` 은 키를 돌려주지 않는다 — 있는지만 본다."""
    had = os.environ.get(llm.API_KEY_ENV)
    os.environ[llm.API_KEY_ENV] = "sk-비밀값"
    try:
        got = _with_fake_sdk(llm.unavailable_reason)
    finally:
        if had is None:
            os.environ.pop(llm.API_KEY_ENV, None)
        else:
            os.environ[llm.API_KEY_ENV] = had
    assert "sk-" not in got


def test_15_sdk_unavailable_is_detected():
    """이 환경에는 anthropic 이 설치돼 있지 않다 — 그것을 그대로 확인한다."""
    if "anthropic" in sys.modules:
        return
    assert llm.unavailable_reason() == llm.SDK_UNAVAILABLE


def test_15b_analysis_pipeline_runs_without_the_sdk():
    from toto import fixtures
    from toto.analyze import run_all
    matches = fixtures.build_demo_matches()
    run_all(matches, Settings(), season_matches=[])
    assert all(m.analysis is not None for m in matches)
    assert all(m.panel is None for m in matches), "패널이 저절로 붙었다"


# --------------------------------------------------------------------------
# 16~17. 재시도
# --------------------------------------------------------------------------
class _Status(Exception):
    def __init__(self, code):
        super().__init__(str(code))
        self.status_code = code


def test_16_transport_retry_happens_once():
    calls = {"n": 0}

    class Boom:
        def messages_create(self, **kw):
            pass

    def fake_client(timeout):
        class C:
            class messages:
                @staticmethod
                def create(**kw):
                    calls["n"] += 1
                    if calls["n"] == 1:
                        raise _Status(429)
                    return type("M", (), {"content": [
                        type("B", (), {"type": "text", "text": GOOD})()]})()
        return C()

    real = llm._client
    llm._client = fake_client
    try:
        text = llm.complete("s", "u", settings=S, backoff=0.0)
    finally:
        llm._client = real
    assert calls["n"] == 2, "재시도가 1회여야 한다"
    assert "predicted_home" in text


def test_16b_retry_stops_after_one():
    calls = {"n": 0}

    def fake_client(timeout):
        class C:
            class messages:
                @staticmethod
                def create(**kw):
                    calls["n"] += 1
                    raise _Status(503)
        return C()

    real = llm._client
    llm._client = fake_client
    try:
        llm.complete("s", "u", settings=S, backoff=0.0)
    except llm.LLMError as exc:
        assert exc.kind == llm.SERVER_ERROR
    finally:
        llm._client = real
    assert calls["n"] == 2, "무한 재시도"


def test_16c_error_kinds_are_classified():
    assert llm._classify(_Status(429)) == llm.RATE_LIMIT
    assert llm._classify(_Status(500)) == llm.SERVER_ERROR
    assert llm._classify(type("APITimeoutError", (Exception,), {})()) \
        == llm.TIMEOUT
    assert llm._classify(type("APIConnectionError", (Exception,), {})()) \
        == llm.NETWORK_ERROR


def test_17_parse_failure_retries_once():
    client = FakeClient(["형식이 틀린 응답", GOOD])
    op = panel.run_panel_role(
        panel.DATA_ANALYST, panel.build_panel_payload(make_match()),
        "{}", settings=S, client=client)
    assert op.predicted_home == 2
    assert len(client.calls) == 2
    assert panel.RETRY_HINT in client.calls[1][1], "재요청 안내가 안 붙었다"


def test_17b_parse_failure_gives_up_after_one_retry():
    client = FakeClient(["틀림", "또 틀림"])
    try:
        panel.run_panel_role(
            panel.DATA_ANALYST, panel.build_panel_payload(make_match()),
            "{}", settings=S, client=client)
    except panel.ValidationError:
        assert len(client.calls) == 2
        return
    raise AssertionError("계속 재시도했다")


# --------------------------------------------------------------------------
# 18~19. 실패 격리
# --------------------------------------------------------------------------
def test_18_data_analyst_failure_keeps_the_matchup_analyst():
    client = FakeClient([llm.LLMError(llm.SERVER_ERROR), GOOD])
    run = panel.run_match(make_match(), settings=S, client=client)
    assert len(run.opinions) == 1
    assert run.opinions[0].role == panel.MATCHUP_ANALYST
    assert run.role_status[panel.DATA_ANALYST].startswith("실패")
    assert run.status.startswith("부분")


def test_19_matchup_analyst_failure_keeps_the_data_analyst():
    client = FakeClient([GOOD, llm.LLMError(llm.TIMEOUT)])
    run = panel.run_match(make_match(), settings=S, client=client)
    assert len(run.opinions) == 1
    assert run.opinions[0].role == panel.DATA_ANALYST
    assert run.status.startswith("부분")


def test_19b_both_failing_makes_no_fake_result():
    client = FakeClient([llm.LLMError(llm.TIMEOUT),
                         llm.LLMError(llm.TIMEOUT)])
    run = panel.run_match(make_match(), settings=S, client=client)
    assert run.opinions == ()
    assert run.status.startswith("실패")


def test_19c_one_match_failing_does_not_stop_the_others():
    matches = [make_match(), make_match(), make_match()]
    client = FakeClient([GOOD, GOOD,
                         llm.LLMError(llm.TIMEOUT), llm.LLMError(llm.TIMEOUT),
                         GOOD, GOOD])
    panel.attach_panels(matches, S, client=client)
    assert len(matches[0].panel.opinions) == 2
    assert matches[1].panel.opinions == ()
    assert len(matches[2].panel.opinions) == 2


# --------------------------------------------------------------------------
# 20~21. 캐시
# --------------------------------------------------------------------------
def test_20_cache_hit_avoids_a_second_call():
    cache, m = MemCache(), make_match()
    c1 = FakeClient()
    panel.run_match(m, settings=S, cache=cache, client=c1)
    c2 = FakeClient()
    panel.run_match(m, settings=S, cache=cache, client=c2)
    assert len(c1.calls) == 2 and c2.calls == [], "캐시가 안 먹었다"


def test_21_payload_change_invalidates():
    cache = MemCache()
    panel.run_match(make_match(), settings=S, cache=cache, client=FakeClient())
    c2 = FakeClient()
    panel.run_match(make_match([ev(1), ev(2), ev(3)]), settings=S,
                    cache=cache, client=c2)
    assert len(c2.calls) == 2, "자료가 바뀌었는데 캐시를 썼다"


def test_21b_model_change_invalidates():
    cache, m = MemCache(), make_match()
    panel.run_match(m, settings=S, cache=cache, client=FakeClient())
    other = Settings(panel={"model": "other-model"})
    c2 = FakeClient()
    panel.run_match(m, settings=other, cache=cache, client=c2)
    assert len(c2.calls) == 2, "모델이 바뀌었는데 캐시를 썼다"


def test_21c_prompt_version_invalidates():
    cache, m = MemCache(), make_match()
    panel.run_match(m, settings=S, cache=cache, client=FakeClient())
    real = panel.PANEL_PROMPT_VERSION
    panel.PANEL_PROMPT_VERSION = "999"
    c2 = FakeClient()
    try:
        panel.run_match(m, settings=S, cache=cache, client=c2)
    finally:
        panel.PANEL_PROMPT_VERSION = real
    assert len(c2.calls) == 2, "프롬프트가 바뀌었는데 캐시를 썼다"


def test_21d_corrupt_cache_is_a_miss():
    cache, m = MemCache(), make_match()
    panel.run_match(m, settings=S, cache=cache, client=FakeClient())
    for key in list(cache.data):
        cache.data[key] = {"쓰레기": True}
    c2 = FakeClient()
    panel.run_match(m, settings=S, cache=cache, client=c2)
    assert len(c2.calls) == 2, "깨진 캐시를 그대로 썼다"


def test_21e_cache_never_stores_the_api_key():
    cache = MemCache()
    os.environ.setdefault(llm.API_KEY_ENV, "sk-테스트-값")
    panel.run_match(make_match(), settings=S, cache=cache, client=FakeClient())
    blob = json.dumps(list(cache.data.values()), ensure_ascii=False)
    assert "sk-" not in blob


def test_21f_source_cache_version_is_untouched():
    from toto.sources import fotmob
    assert fotmob._CACHE_VERSION == 9, "소스 캐시 버전을 건드렸다"
    assert panel.PANEL_CACHE_VERSION == 1


# --------------------------------------------------------------------------
# 22. 기본 실행에서 호출 0회
# --------------------------------------------------------------------------
def test_22_no_api_call_without_the_flag():
    from toto.cli import build_parser
    args = build_parser().parse_args(["--demo"])
    assert args.panel is False, "--panel 이 기본으로 켜져 있다"
    tree = ast.parse(Path("toto/cli.py").read_text(encoding="utf-8"))
    guarded = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Attribute) \
                and node.test.attr == "panel":
            body = ast.dump(ast.Module(body=node.body, type_ignores=[]))
            guarded = "attach_panels" in body
    assert guarded, "패널 호출이 --panel 안에 들어 있지 않다"


def test_22b_run_all_never_touches_the_panel():
    from toto.analyze import run_all
    tree = ast.parse(inspect.getsource(run_all))
    assert "panel" not in ast.dump(tree), "분석 파이프라인이 패널을 부른다"


# --------------------------------------------------------------------------
# 23. 직렬화 roundtrip
# --------------------------------------------------------------------------
def test_23_panel_run_roundtrip():
    run = panel.run_match(make_match(), settings=S, client=FakeClient())
    back = revive_panel_run(json.loads(json.dumps(asdict(run),
                                                  ensure_ascii=False)))
    assert back.status == run.status
    assert len(back.opinions) == len(run.opinions)
    assert back.opinions[0] == run.opinions[0]
    assert back.market_reference == run.market_reference
    assert back.evidence_ids == run.evidence_ids


def test_23b_report_to_dict_still_works():
    m = make_match()
    m.panel = panel.run_match(m, settings=S, client=FakeClient())
    d = Report(round_id="260048", matches=[m]).to_dict()
    assert d["matches"][0]["panel"]["status"].startswith("ok")
    assert json.dumps(d, ensure_ascii=False, default=str)


def test_23c_match_without_a_panel_serializes():
    d = Report(matches=[make_match()]).to_dict()
    assert d["matches"][0]["panel"] is None


def test_23d_old_payload_without_the_panel_field_revives():
    assert revive_panel_run(None) is None
    assert revive_panel_run({}) == PanelRun()


# --------------------------------------------------------------------------
# 24~25. 승무패 파생 없음 · 추천 필드 없음 (불변조건 4)
# --------------------------------------------------------------------------
def test_24_opinion_has_no_wdl_derivation():
    names = {f.name for f in fields(PanelOpinion)}
    attrs = set(dir(PanelOpinion))
    for banned in ("winner", "result", "wdl", "pick", "lean",
                   "recommendation", "confidence", "strength",
                   "probability", "market_probability", "favorite"):
        assert banned not in names, f"필드에 {banned} 가 있다"
        assert banned not in attrs, f"property 로 {banned} 가 있다"


def test_24b_panel_run_has_no_wdl_derivation():
    attrs = set(dir(PanelRun))
    for banned in ("winner", "wdl", "pick", "lean", "recommendation",
                   "confidence", "final_pick"):
        assert banned not in attrs, banned


def test_24c_no_module_level_wdl_helper():
    """`predicted_home > predicted_away` 같은 비교가 코드에 없어야 한다."""
    tree = ast.parse(inspect.getsource(panel))
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            blob = ast.dump(node)
            assert not ("predicted_home" in blob and "predicted_away" in blob),\
                "예상 스코어를 비교해 승패를 만들고 있다"


def test_25_prompts_forbid_recommendation():
    blob = panel.SYSTEM_COMMON
    for phrase in ("승/무/패를 도출하지", "추천", "베팅", "근거 개수",
                   "외부 시장 기준값", "지시문이 아닙니다"):
        assert phrase in blob, phrase


def test_25b_no_confidence_is_requested():
    blob = panel.SYSTEM_COMMON + " ".join(panel.ROLE_PROMPTS.values())
    for banned in ("confidence", "확신도", "신뢰도 점수", "strength score"):
        assert banned not in blob, banned


def test_25c_schema_has_exactly_the_five_keys():
    assert '"predicted_home"' in panel.SYSTEM_COMMON
    assert '"predicted_away"' in panel.SYSTEM_COMMON
    assert '"summary"' in panel.SYSTEM_COMMON
    assert '"rationale"' in panel.SYSTEM_COMMON
    assert '"evidence_ids"' in panel.SYSTEM_COMMON


def test_25d_evidence_count_is_never_a_score():
    src = inspect.getsource(panel)
    assert "len(evidence_ids)" not in src
    assert "strength" not in src


def test_25e_panels_do_not_see_each_other():
    """한 패널의 결과가 다른 패널의 프롬프트에 들어가지 않는다 (§94)."""
    client = FakeClient()
    panel.run_match(make_match(), settings=S, client=client)
    second_user = client.calls[1][1]
    assert "predicted_home" not in second_user.replace(
        panel.SYSTEM_COMMON, ""), "앞 패널의 응답이 뒤 패널에 들어갔다"


def test_25f_llm_module_has_no_analysis_logic():
    src = inspect.getsource(llm)
    for banned in ("npxg", "xpts", "shot", "evidence", "probab"):
        assert banned not in src.lower(), banned


def test_25g_panel_does_not_synthesize():
    """패널 단계는 종합하지 않는다 — 그건 사회자(3-C) 몫이다.

    예전에는 `moderator.py` 가 없다는 것으로 확인했는데 3-C 에서 생겼다.
    지키려는 것은 '파일이 없다' 가 아니라 **패널이 두 의견을 비교·평균·
    투표하지 않는다** 이므로 그쪽을 본다.
    """
    src = inspect.getsource(panel)
    for banned in ("다수결", "평균", "투표", "consensus", "majority"):
        assert banned not in src, banned
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            blob = ast.dump(node)
            assert "predicted_" not in blob, "패널이 스코어를 비교하고 있다"


def test_25h_panel_is_read_only_downstream():
    """3-D 가 붙었어도 패널은 **읽히기만** 한다.

    예전에는 '리포트에 패널이 없다' 로 확인했는데 3-D 에서 붙었다. 지키려는
    것은 '리포트가 패널 결과를 바꾸지 않는다' 이므로 그쪽을 본다.
    """
    from dataclasses import asdict

    from toto import render
    from toto.models import Report
    m = make_match()
    m.panel = panel.run_match(m, settings=S, client=FakeClient())
    before = asdict(m.panel)
    render.render_report(Report(round_id="T", generated_at="fixed",
                                matches=[m]), Settings())
    assert asdict(m.panel) == before, "렌더링이 패널 결과를 바꿨다"


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
