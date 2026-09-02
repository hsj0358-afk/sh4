"""Phase 2 분석 데이터 모델 회귀 테스트 (P0-3).

이 단계는 **그릇만** 만든다. 분석 계산은 P1 이후이므로, 여기서 검사하는 것은
'구조가 무엇을 표현할 수 있고 무엇을 표현할 수 없는가' 다.

가장 중요한 것은 §5 — `MatchAnalysis` 가 **구조적으로** 최종 승무패 추천을
담을 수 없어야 한다.

pytest 없이도 돈다:  python tests/test_analysis_model.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import models                                        # noqa: E402
from toto.models import (AWAY, DERIVED, DRAW, HOME, MODEL,     # noqa: E402
                         NEUTRAL, OBSERVED, UNKNOWN,
                         AnalysisAxis, DataQuality, EvidenceItem, Match,
                         MatchAnalysis, MatchupPair, Metric, Report, Signal,
                         TeamAnalysis, TeamRef, revive_match_analysis,
                         revive_team_analysis)

UTC = timezone.utc


def _sample_team(name="Arsenal", tid=9001, is_home=True) -> TeamAnalysis:
    """축 두 개만 채운 TeamAnalysis (나머지는 None 으로 남긴다)."""
    ta = TeamAnalysis(team=name, fotmob_id=tid, is_home=is_home)
    ta.chance_quality = AnalysisAxis(
        name="chance_quality", requested_matches=6, available_matches=4,
        metrics={
            "npxg_per_match": Metric(
                name="npxg_per_match", label="경기당 npxG", value=1.42,
                provenance=OBSERVED, period="recent6", sample_count=4,
                unit="per_match"),
            "npxg_per_shot": Metric(
                name="npxg_per_shot", label="슛당 npxG", value=0.109,
                provenance=DERIVED, period="recent6", sample_count=4),
        },
        notes=["표본 4/6경기"])
    ta.sustainability = AnalysisAxis(
        name="sustainability", requested_matches=6, available_matches=5,
        metrics={"xpts": Metric(name="xpts", label="기대 승점", value=8.4,
                                provenance=MODEL, period="recent6",
                                sample_count=5)})
    ta.data_quality = DataQuality()
    ta.data_quality.mark("chance_quality", True, 6, 4)
    ta.data_quality.mark("venue_context", False, 6, 1, "표본 부족 (1/6경기)")
    return ta


def _sample_match_analysis() -> MatchAnalysis:
    ma = MatchAnalysis(as_of=datetime(2026, 8, 29, 15, 0, tzinfo=UTC))
    ma.home = _sample_team("Arsenal", 9001, True)
    ma.away = _sample_team("Chelsea", 9002, False)
    ma.matchup = [MatchupPair(
        concept="chance_quality", label="기회의 질",
        direction="home_attack",
        attack=Metric(name="npxg_per_shot", value=0.109, provenance=DERIVED,
                      period="recent6", sample_count=4),
        defense=Metric(name="npxga_per_shot", value=0.131, provenance=DERIVED,
                       period="recent6", sample_count=3))]
    ma.conflicts = [
        Signal(name="market", lean=HOME, strength="high", basis="배당 46.9%",
               provenance=OBSERVED),
        Signal(name="recent_form", lean=AWAY, strength="low",
               basis="최근 6경기 승점", sample_count=2),
        Signal(name="venue", lean=UNKNOWN, basis="표본 부족"),
    ]
    ma.evidence = [
        EvidenceItem(claim="홈팀의 슛당 기대값이 높다", side=HOME,
                     metric="npxg_per_shot", value=0.109, comparison="상대 대비",
                     period="recent6", sample_count=4, provenance=DERIVED,
                     axis="chance_quality"),
        EvidenceItem(claim="최근 폼은 원정팀이 낫다", side=HOME, counter=True,
                     metric="points_per_match", value=1.0, period="recent6",
                     sample_count=2, axis="time_context"),
        EvidenceItem(claim="양 팀 기대 득점이 모두 낮다", side=DRAW,
                     metric="xg_total", value=1.9, period="recent6", axis="xpts"),
    ]
    ma.data_quality = DataQuality(source_status={"순위·폼": "ok"})
    ma.data_quality.mark("schedule_strength", False, 6, 0,
                         "시즌 경기별 xG 없음")
    return ma


# --------------------------------------------------------------------------
# 1·2·3. 기본값
# --------------------------------------------------------------------------
def test_team_analysis_defaults_are_none():
    ta = TeamAnalysis()
    for axis in TeamAnalysis.AXES:
        assert getattr(ta, axis) is None, f"{axis} 가 빈 객체로 채워졌다"
    assert ta.data_quality is None
    assert ta.computed_axes() == [], "계산 안 한 축이 계산된 것처럼 보인다"
    assert ta.team == "" and ta.fotmob_id is None and ta.is_home is None


def test_match_analysis_defaults():
    ma = MatchAnalysis()
    assert ma.home is None and ma.away is None
    assert ma.matchup == [] and ma.conflicts == [] and ma.evidence == []
    assert ma.data_quality is None and ma.as_of is None
    assert ma.signals_by_lean() == {} and ma.has_conflict is False


def test_mutable_defaults_are_not_shared():
    """dataclass 의 가변 기본값 사고 방지."""
    a, b = MatchAnalysis(), MatchAnalysis()
    a.evidence.append(EvidenceItem(claim="x"))
    assert b.evidence == [], "기본 리스트가 인스턴스 간에 공유된다"
    x, y = AnalysisAxis(), AnalysisAxis()
    x.metrics["k"] = Metric(name="k")
    assert y.metrics == {}
    p, q = DataQuality(), DataQuality()
    p.mark("axis", True)
    assert q.axes == {}


def test_match_analysis_is_none_by_default():
    m = Match(no=1)
    assert m.analysis is None, "기존 Match 생성부가 깨지면 안 된다"
    assert Match(no=2, league="epl").analysis is None


# --------------------------------------------------------------------------
# 4. 채워진 Match.analysis
# --------------------------------------------------------------------------
def test_populated_match_analysis():
    m = Match(no=1, home=TeamRef(canonical="Arsenal"),
              away=TeamRef(canonical="Chelsea"))
    m.analysis = _sample_match_analysis()
    assert m.analysis.home.team == "Arsenal"
    assert m.analysis.away.team == "Chelsea"
    assert m.analysis.home.computed_axes() == ["chance_quality", "sustainability"]
    assert m.analysis.home.chance_quality.value("npxg_per_shot") == 0.109
    # probs 는 손대지 않는다
    assert m.probs is None


def test_analysis_does_not_touch_probs():
    """MatchAnalysis 는 Match.probs 와 별개 객체다."""
    ma = _sample_match_analysis()
    names = {f.name for f in fields(MatchAnalysis)}
    assert "probs" not in names and "odds" not in names
    assert not hasattr(ma, "probability"), "확률을 다시 만들지 않는다"


# --------------------------------------------------------------------------
# 5·6·7. 직렬화 왕복
# --------------------------------------------------------------------------
def test_team_analysis_roundtrip():
    ta = _sample_team()
    back = revive_team_analysis(asdict(ta))
    assert back.team == ta.team and back.fotmob_id == ta.fotmob_id
    assert back.is_home is True
    assert isinstance(back.chance_quality, AnalysisAxis)
    assert isinstance(back.chance_quality.get("npxg_per_shot"), Metric)
    assert back.chance_quality.value("npxg_per_shot") == 0.109
    assert back.chance_quality.available_matches == 4
    assert back.chance_quality.notes == ["표본 4/6경기"]
    # 계산 안 한 축은 None 으로 되살아난다
    assert back.time_context is None and back.venue_context is None
    assert isinstance(back.data_quality, DataQuality)
    assert back.data_quality.unavailable() == ["venue_context"]


def test_match_analysis_roundtrip():
    ma = _sample_match_analysis()
    back = revive_match_analysis(asdict(ma))
    assert isinstance(back.home, TeamAnalysis) and back.home.team == "Arsenal"
    assert isinstance(back.away, TeamAnalysis)
    assert len(back.matchup) == 1 and isinstance(back.matchup[0], MatchupPair)
    assert isinstance(back.matchup[0].attack, Metric)
    assert back.matchup[0].attack.value == 0.109
    assert back.matchup[0].defense.provenance == DERIVED
    assert len(back.conflicts) == 3 and isinstance(back.conflicts[0], Signal)
    assert len(back.evidence) == 3 and isinstance(back.evidence[0], EvidenceItem)
    assert isinstance(back.data_quality, DataQuality)


def test_match_roundtrip_with_and_without_analysis():
    m = Match(no=1, home=TeamRef(canonical="Arsenal"))
    d = asdict(m)
    assert d["analysis"] is None
    assert revive_match_analysis(d["analysis"]) is None

    m.analysis = _sample_match_analysis()
    d2 = asdict(m)
    back = revive_match_analysis(d2["analysis"])
    assert back.home.team == "Arsenal"
    assert back.evidence[0].axis == "chance_quality"
    # JSON 으로도 나간다 (datetime 은 default=str 필요 — as_of 가 있으므로)
    text = json.dumps(d2, default=str, ensure_ascii=False)
    assert "npxg_per_shot" in text


def test_revive_handles_garbage_without_crashing():
    for junk in (None, "", 3, [], {"home": "nope", "matchup": ["x"]}):
        got = revive_match_analysis(junk)
        assert got is None or isinstance(got, MatchAnalysis)
    assert revive_team_analysis(None) is None


# --------------------------------------------------------------------------
# 8. provenance (observed / derived / model)
# --------------------------------------------------------------------------
def test_provenance_constants_and_usage():
    assert (OBSERVED, DERIVED, MODEL) == ("observed", "derived", "model")
    assert models.PROVENANCE == (OBSERVED, DERIVED, MODEL)
    ta = _sample_team()
    assert ta.chance_quality.get("npxg_per_match").provenance == OBSERVED
    assert ta.chance_quality.get("npxg_per_shot").provenance == DERIVED
    assert ta.sustainability.get("xpts").provenance == MODEL, "xPTS 는 모델값"


def test_provenance_survives_roundtrip():
    back = revive_team_analysis(asdict(_sample_team()))
    assert back.sustainability.get("xpts").provenance == MODEL
    assert back.chance_quality.get("npxg_per_shot").provenance == DERIVED


def test_not_every_number_is_wrapped():
    """모든 숫자를 Metric 으로 감싸지 않는다 — 축의 경기 수는 평범한 int."""
    axis = AnalysisAxis(requested_matches=6, available_matches=4)
    assert isinstance(axis.requested_matches, int)
    assert not is_dataclass(axis.available_matches)


# --------------------------------------------------------------------------
# 9. 표본 메타데이터
# --------------------------------------------------------------------------
def test_sample_metadata_is_expressible():
    ta = _sample_team()
    axis = ta.chance_quality
    assert axis.requested_matches == 6      # 요청한 창
    assert axis.available_matches == 4      # 실제로 쓸 수 있었던 경기
    assert axis.get("npxg_per_shot").sample_count == 4   # 그 지표의 표본
    # 세 수가 서로 다른 개념이라는 것을 구조가 표현할 수 있어야 한다
    axis.metrics["sparse"] = Metric(name="sparse", value=1.0, sample_count=2)
    assert axis.get("sparse").sample_count != axis.available_matches


def test_metric_none_is_not_zero():
    m = Metric(name="x")
    assert m.value is None and m.known is False
    assert Metric(name="y", value=0.0).known is True, "실제 0 은 값이 있는 것"
    assert AnalysisAxis().value("nothing") is None


def test_data_quality_records_reason_without_score():
    dq = DataQuality()
    dq.mark("venue_context", False, 6, 1, "표본 부족 (1/6경기)")
    dq.mark("chance_quality", True, 6, 4)
    assert dq.unavailable() == ["venue_context"]
    assert dq.axes["venue_context"]["degraded_reason"] == "표본 부족 (1/6경기)"
    # 종합 confidence 점수를 만들지 않는다
    names = {f.name for f in fields(DataQuality)}
    assert not (names & {"confidence", "score", "rating", "grade"})


# --------------------------------------------------------------------------
# 10. Final Pick 금지 — 구조적으로 표현 불가여야 한다
# --------------------------------------------------------------------------
FORBIDDEN = ("final_pick", "recommended_pick", "recommendation",
             "predicted_result", "pick", "prediction", "best_bet",
             "선택", "추천")


def test_no_final_pick_field_anywhere_in_analysis_model():
    for cls in (TeamAnalysis, MatchAnalysis, AnalysisAxis, Metric,
                MatchupPair, Signal, EvidenceItem, DataQuality):
        for f in fields(cls):
            low = f.name.lower()
            for bad in FORBIDDEN:
                assert bad not in low, f"{cls.__name__}.{f.name} 이 추천을 표현한다"


def test_signals_are_counted_not_summed():
    """신호를 합산해 최종 방향을 만들지 않는다."""
    ma = _sample_match_analysis()
    counts = ma.signals_by_lean()
    assert counts == {HOME: 1, AWAY: 1, UNKNOWN: 1}
    assert ma.has_conflict is True, "홈·원정이 갈리면 충돌로 남긴다"
    # 개수만 돌려줄 뿐 '승자'를 고르는 메서드가 없다
    api = {n for n in dir(ma) if not n.startswith("_")}
    assert not (api & {"winner", "verdict", "decide", "final", "pick"})


def test_evidence_has_three_directions_and_counter():
    ma = _sample_match_analysis()
    assert len(ma.evidence_for(HOME)) == 1
    assert len(ma.evidence_for(HOME, counter=True)) == 1
    assert len(ma.evidence_for(DRAW)) == 1
    assert len(ma.evidence_for(AWAY)) == 0
    assert models.LEANS == (HOME, DRAW, AWAY, NEUTRAL, UNKNOWN)


# --------------------------------------------------------------------------
# 11·12. 기존 필드 regression
# --------------------------------------------------------------------------
def test_existing_match_fields_unchanged():
    """기존 필드는 **자리까지** 그대로고, 새 필드는 그 뒤에만 붙는다.

    예전에는 `names[-1] == "analysis"` 로 확인했는데, 그러면 Phase 3-B 의
    `panel` 처럼 **규칙을 지켜 뒤에 붙인 필드**까지 실패로 잡힌다. 진짜
    지키려는 것은 '기존 필드의 순서가 밀리지 않는다' 이므로 접두사 전체를
    본다 — 원래보다 강한 검사다.
    """
    names = [f.name for f in fields(Match)]
    original = ["no", "league", "league_ko", "home", "away", "kickoff_kst",
                "odds", "probs", "home_profile", "away_profile", "h2h",
                "radar", "matchup_notes", "notes"]
    assert names[:len(original)] == original, "기존 필드의 자리가 바뀌었다"
    assert names[len(original)] == "analysis", "analysis 자리가 바뀌었다"
    for extra in names[len(original):]:
        assert extra in ("analysis", "panel"), f"모르는 필드: {extra}"
    m = Match(no=3, league="epl")
    assert m.no == 3 and m.league == "epl" and m.radar == {}
    assert m.title == " vs "


def test_existing_report_fields_unchanged():
    names = [f.name for f in fields(Report)]
    for k in ("round_id", "generated_at", "matches", "warnings",
              "source_status", "verdict", "season_matches"):
        assert k in names, f"{k} 가 사라졌다"
    r = Report(round_id="260048", generated_at="2026-08-29 12:00")
    assert r.to_dict()["round_id"] == "260048"


def test_match_analysis_has_no_duplicate_timestamp():
    """Report.generated_at 이 이미 있으므로 중복 필드를 만들지 않는다."""
    names = {f.name for f in fields(MatchAnalysis)}
    assert "generated_at" not in names
    assert "as_of" in names, "시점 기준은 별개 개념이라 필요하다"


# --------------------------------------------------------------------------
def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            print(f"  ERR  {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
