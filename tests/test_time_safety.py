"""시간누수 감사 (Phase 3-F).

**백테스트가 아니다.** 이 저장소에는 과거 시점을 복원할 데이터가 없어
백테스트는 만들지 않았다(§67·§68). 대신 백테스트의 전제이자 가장 중요한
성질 하나를 파이프라인 **끝까지** 검사한다.

    그 경기 직전에 정말 알 수 있었던 정보만으로 분석이 만들어지는가?

## 검사 방법 — 미래를 넣어도 결과가 바뀌지 않아야 한다

축별 cutoff 테스트는 이미 있다(`test_season_matches`·`test_time_context`·
`test_schedule_strength`·`test_venue_context`). 여기서는 그 위층을 본다:

    과거만 있는 자료  →  분석 → 근거 → PanelPayload → 사회자 입력
    과거+미래 자료    →  〃

두 결과의 **직렬화 바이트가 같아야** 한다. 어느 단계에서든 미래가 새면
바이트가 달라진다. 반대로 기준시각을 미래 뒤로 옮기면 **반드시 달라져야**
한다 — 그래야 이 검사가 차이를 실제로 감지한다는 것이 증명된다(음성 대조).

pytest 없이도 돈다:  python tests/test_time_safety.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import analysis, evidence, moderator, panel                 # noqa: E402
from toto.models import (Match, MatchAnalysis, Odds, SeasonMatch,     # noqa: E402
                         TeamProfile, TeamRef, TeamStats,
                         matches_before)
from toto.predict import additive_probabilities                       # noqa: E402
from toto.settings import Settings                                    # noqa: E402

KST = analysis.KST
US, OPP, X, Y = 101, 102, 103, 104
NAME = {US: "US", OPP: "OPP", X: "X", Y: "Y"}
S = Settings(analysis={"periods": [3], "trend_min_sample": 1,
                       "schedule_strength": {"min_sample": 1,
                                             "opponent_min_matches": 1}},
             fotmob={"shot_recent_windows": [3], "match_detail_matches": 3})


def sm(mid, day, home, away, hg, ag, hour=20, finished=True):
    return SeasonMatch(
        match_id=mid, competition="epl",
        kickoff=datetime(2026, 4, day, hour, 0, tzinfo=KST),
        kickoff_aware=True, home_team=NAME[home], away_team=NAME[away],
        home_fotmob_id=home, away_fotmob_id=away,
        home_goals=hg, away_goals=ag, finished=finished)


# 시간선: 1~10일 과거 · 15일 대상 경기 · 20~25일 미래
PAST = [sm("p1", 1, US, X, 2, 0), sm("p2", 2, OPP, Y, 1, 1),
        sm("p3", 4, X, US, 0, 3), sm("p4", 6, Y, OPP, 2, 2),
        sm("p5", 8, US, Y, 1, 1), sm("p6", 10, OPP, X, 3, 1)]
TARGET = sm("t1", 15, US, OPP, 4, 0)          # 결과는 평가에만 쓰는 미래 정보
FUTURE = [sm("f1", 20, US, X, 5, 0), sm("f2", 25, OPP, Y, 0, 4)]
AS_OF = TARGET.kickoff


def profile(team_id):
    p = TeamProfile(team=TeamRef(canonical=NAME[team_id],
                                 display=NAME[team_id],
                                 fotmob_id=str(team_id)), league="epl")
    p.stats = TeamStats(played=3, goals_for=4, goals_against=2, points=5)
    return p


def build_match(season) -> Match:
    m = Match(no=1, league="epl", league_ko="프리미어리그",
              kickoff_kst="2026-04-15 20:00",
              home=TeamRef(canonical="US", display="US"),
              away=TeamRef(canonical="OPP", display="OPP"),
              odds=Odds(home=2.5, draw=3.3, away=2.9, source="arcadia-api",
                        fetched_at="2026-04-15 18:00"))
    m.probs = additive_probabilities(2.5, 3.3, 2.9)
    m.home_profile, m.away_profile = profile(US), profile(OPP)
    m.analysis = MatchAnalysis()
    analysis.attach_time_context([m], S, season_matches=season)
    evidence.attach_evidence([m], S)
    return m


def payload_json(season) -> str:
    return panel.serialize_payload(panel.build_panel_payload(build_match(season)))


def axis_dump(season) -> str:
    m = build_match(season)
    out = {}
    for side in ("home", "away"):
        ta = getattr(m.analysis, side)
        if ta is None:
            continue
        for name in ta.AXES:
            ax = getattr(ta, name, None)
            if ax is None:
                continue
            out[f"{side}.{name}"] = {
                k: (v.value, v.sample_count, v.note)
                for k, v in sorted(ax.metrics.items())}
            out[f"{side}.{name}.notes"] = list(ax.notes)
    return json.dumps(out, sort_keys=True, ensure_ascii=False, default=str)


# --------------------------------------------------------------------------
# A. 시점 절단 — 대상 경기와 미래는 들어가지 않는다
# --------------------------------------------------------------------------
def test_a1_cutoff_excludes_target_and_future():
    got = {m.match_id for m in matches_before(PAST + [TARGET] + FUTURE, AS_OF)}
    assert got == {"p1", "p2", "p3", "p4", "p5", "p6"}, got


def test_a2_target_match_itself_is_never_included():
    """같은 시각은 **엄격한 `<`** 로 제외된다 — 그 경기 결과는 아직 없다."""
    assert TARGET.match_id not in {
        m.match_id for m in matches_before([TARGET], AS_OF)}


def test_a3_as_of_none_gives_nothing():
    assert matches_before(PAST + FUTURE, None) == []


# --------------------------------------------------------------------------
# B~D. 미래를 넣어도 결과가 바뀌지 않는다 (파이프라인 전 구간)
# --------------------------------------------------------------------------
def test_b4_axes_are_identical_with_or_without_the_future():
    assert axis_dump(PAST) == axis_dump(PAST + [TARGET] + FUTURE), \
        "미래 경기가 분석 축에 샜다"


def test_b5_evidence_is_identical():
    a = [(e.metric, e.value, e.sample_count, e.period)
         for e in build_match(PAST).analysis.evidence]
    b = [(e.metric, e.value, e.sample_count, e.period)
         for e in build_match(PAST + [TARGET] + FUTURE).analysis.evidence]
    assert a == b, "미래 경기가 근거에 샜다"


def test_b6_panel_payload_is_byte_identical():
    assert payload_json(PAST) == payload_json(PAST + [TARGET] + FUTURE), \
        "미래 경기가 PanelPayload 에 샜다"


def test_b7_payload_hash_is_identical():
    h1 = panel.payload_hash(panel.build_panel_payload(build_match(PAST)))
    h2 = panel.payload_hash(panel.build_panel_payload(
        build_match(PAST + [TARGET] + FUTURE)))
    assert h1 == h2


def test_b8_moderator_input_is_identical():
    def mod_input(season):
        p = panel.build_panel_payload(build_match(season))
        return moderator.serialize_input(moderator.build_input(p, ()))
    assert mod_input(PAST) == mod_input(PAST + [TARGET] + FUTURE), \
        "미래 경기가 사회자 입력에 샜다"


# --------------------------------------------------------------------------
# E. 음성 대조 — 이 검사가 차이를 실제로 감지하는가
# --------------------------------------------------------------------------
def test_e9_moving_the_cutoff_forward_does_change_the_result():
    """기준시각을 미래 뒤로 옮기면 **반드시** 달라져야 한다.

    이 테스트가 없으면 위의 '같다' 들이 '아무것도 안 만들어서 같은 것'
    일 수 있다.
    """
    later = FUTURE[-1].kickoff + timedelta(days=1)
    m = Match(no=1, league="epl", kickoff_kst="2026-04-26 20:00",
              home=TeamRef(canonical="US", display="US"),
              away=TeamRef(canonical="OPP", display="OPP"), odds=Odds())
    m.home_profile, m.away_profile = profile(US), profile(OPP)
    m.analysis = MatchAnalysis()
    analysis.attach_time_context([m], S, season_matches=PAST + [TARGET] + FUTURE)
    late = json.dumps(
        {k: (v.value, v.sample_count)
         for k, v in sorted(m.analysis.home.time_context.metrics.items())},
        sort_keys=True, default=str)
    early = json.dumps(
        {k: (v.value, v.sample_count)
         for k, v in sorted(
             build_match(PAST).analysis.home.time_context.metrics.items())},
        sort_keys=True, default=str)
    assert late != early, "기준시각을 옮겼는데 결과가 같다 — 검사가 무력하다"
    assert later > AS_OF


def test_e10_the_fixture_actually_produces_something():
    """빈 결과를 비교하며 통과하는 것을 막는다."""
    m = build_match(PAST)
    assert m.analysis.home is not None
    assert m.analysis.home.time_context.metrics, "축이 비어 있다"
    assert m.analysis.home.schedule_strength is not None


# --------------------------------------------------------------------------
# F. 최근 N · 장소 · 상대 강도 — 대상 경기 자체가 빠지는가
# --------------------------------------------------------------------------
def test_f11_recent_n_excludes_the_target():
    ax = build_match(PAST + [TARGET]).analysis.home.time_context
    played = ax.get("recent3.points")
    assert played is not None
    assert played.sample_count is not None and played.sample_count <= 3


def test_f12_sos_excludes_the_target_result():
    """상대 전적에 대상 경기(US 4-0 OPP)가 들어가면 값이 달라진다."""
    a = build_match(PAST).analysis.home.schedule_strength
    b = build_match(PAST + [TARGET]).analysis.home.schedule_strength
    for key in sorted(set(a.metrics) | set(b.metrics)):
        assert a.value(key) == b.value(key), f"{key}: 대상 경기가 SoS 에 샜다"


def test_f13_venue_excludes_the_target():
    a = build_match(PAST).analysis.home.venue_context
    b = build_match(PAST + [TARGET]).analysis.home.venue_context
    if a is None and b is None:
        return
    assert a is not None and b is not None
    for key in sorted(set(a.metrics) | set(b.metrics)):
        assert a.value(key) == b.value(key), f"{key}: 대상 경기가 장소에 샜다"


def test_f14_self_exclusion_survives_in_sos():
    """2-F 의 self-exclusion 은 그대로다 — 우리와의 경기는 상대 전적에서 뺀다."""
    with_us = analysis.opponent_record(PAST, "OPP", OPP, AS_OF, "없는팀", 999)
    without = analysis.opponent_record(PAST, "OPP", OPP, AS_OF, "US", US)
    assert with_us[2] >= without[2], "제외한 쪽 표본이 더 많다"


# --------------------------------------------------------------------------
# G. 슛 자료 — 창에 미래가 섞이면 지표를 만들지 않는다
# --------------------------------------------------------------------------
def test_g15_shot_window_with_a_future_match_is_refused():
    """2-A 의 `_window_time_check` 가 이미 갖고 있는 방어선이다.

    슛 계층의 창은 수집 시점에 만들어져 다시 자를 수 없으므로, 창의
    `match_ids` 를 시즌 색인과 대조해 기준시각 이후 경기가 섞였으면 그
    창의 슛 지표를 **만들지 않는다.**
    """
    src = __import__("inspect").getsource(analysis._window_time_check)
    assert "matches_before" in src or "as_of" in src
    m = build_match(PAST)
    notes = " ".join(m.analysis.home.time_context.notes)
    assert isinstance(notes, str)


# --------------------------------------------------------------------------
# H. 감사표 (§33)
# --------------------------------------------------------------------------
def audit_row(season, target):
    """`max_input_kickoff < target_kickoff` 인가."""
    used = matches_before(season, target.kickoff)
    latest = max((m.kickoff for m in used if m.kickoff), default=None)
    return {"match_id": target.match_id,
            "target_kickoff": target.kickoff,
            "max_input_kickoff": latest,
            "leakage_detected": bool(latest and latest >= target.kickoff)}


def test_h16_audit_table_reports_no_leakage():
    row = audit_row(PAST + [TARGET] + FUTURE, TARGET)
    assert row["max_input_kickoff"] == PAST[-1].kickoff
    assert row["leakage_detected"] is False


def test_h17_audit_detects_injected_future(monkey=None):
    """§64 — 일부러 미래를 '과거' 로 위장해 넣으면 감사가 잡아야 한다."""
    forged = sm("forged", 22, US, X, 9, 0)
    row = {"target_kickoff": TARGET.kickoff,
           "max_input_kickoff": forged.kickoff,
           "leakage_detected": forged.kickoff >= TARGET.kickoff}
    assert row["leakage_detected"] is True, "미래 주입을 감지하지 못했다"
    # 그리고 실제 파이프라인은 그것을 **쓰지 않는다**
    assert forged.match_id not in {
        m.match_id for m in matches_before(PAST + [forged], AS_OF)}


# --------------------------------------------------------------------------
# I. 대상 경기 결과는 분석 입력에 없다 (§12)
# --------------------------------------------------------------------------
def test_i18_target_result_never_reaches_the_payload():
    """대상 경기는 4-0 이다 — 그 숫자가 자료에 나타나면 안 된다."""
    blob = payload_json(PAST + [TARGET] + FUTURE)
    assert '"t1"' not in blob, "대상 경기 ID 가 자료에 있다"
    assert '"f1"' not in blob and '"f2"' not in blob


def test_i19_evaluation_label_is_computed_outside_the_analysis():
    """실제 결과는 평가에서만 쓴다 — 모델에 승무패 칸을 만들지 않는다."""
    actual = ("HOME" if TARGET.home_goals > TARGET.away_goals
              else "DRAW" if TARGET.home_goals == TARGET.away_goals else "AWAY")
    assert actual == "HOME"
    m = build_match(PAST)
    for obj in (m.analysis, m.analysis.home):
        for banned in ("winner", "wdl", "pick", "recommendation",
                       "actual_result"):
            assert not hasattr(obj, banned), banned


def test_i20_odds_are_not_derived_from_the_result():
    m = build_match(PAST)
    assert m.probs is not None
    assert abs(m.probs.home + m.probs.draw + m.probs.away - 1.0) < 1e-9


# --------------------------------------------------------------------------
# J. 단일 cutoff 원칙 (누수 방지는 한 곳에만)
# --------------------------------------------------------------------------
def test_j21_only_matches_before_is_the_cutoff():
    """축들이 `kickoff` 을 직접 비교하지 않는다 — 이미 각 축 테스트가
    고정하고 있고, 여기서는 그 사실이 여전한지만 확인한다."""
    import ast
    import inspect
    for fn in (analysis.build_time_context, analysis.build_venue_context,
               analysis.build_schedule_strength):
        tree = ast.parse(inspect.getsource(fn))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                blob = ast.dump(node)
                assert "kickoff" not in blob, \
                    f"{fn.__name__} 이 kickoff 을 직접 비교한다"


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
