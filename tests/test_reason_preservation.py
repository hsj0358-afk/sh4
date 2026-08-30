"""값이 없을 때 그 이유가 남는가 (Phase 2-C 교정).

## 왜 이 파일이 생겼나

2-C 검증에서 이런 상태가 나왔다.

    커버리지        최근 6경기: 6/6경기
    recent6.goals_against   None
    사유            없음

값이 없는 것 자체는 옳다(시즌 경기 색인에서 스코어를 못 찾았다). 하지만
**왜 없는지가 남지 않아** 읽는 사람이 "6/6인데 왜 실점이 없지?" 의 답을
찾을 수 없었다.

사유가 사라지던 지점은 세 곳이었다.

    1. `_put()`         값이 None 이면 note 까지 함께 버렸다 (2-B·2-C 공통)
    2. 2-C `conceded_rows` 분기   `else` 가 없어 사유를 만들지도 않았다
    3. 2-B `team_goals` 분기      같은 모양

교정은 `_put()` 에 `reasons` 채널 하나를 더한 것뿐이다. **값은 한 칸도
바뀌지 않는다** — 그것을 6·7번 테스트가 지킨다.

pytest 없이도 돈다:  python tests/test_reason_preservation.py
"""
from __future__ import annotations

import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import analysis                                       # noqa: E402
from toto.models import (MatchAnalysis, SeasonMatch, TeamProfile,  # noqa: E402
                         TeamRef, TeamStats, revive_match_analysis)
from toto.settings import Settings                              # noqa: E402
from toto.shots import MatchShotAggregate, RecentShotAggregate   # noqa: E402

UTC = timezone.utc
TEAM = "우리팀"
US, THEM = 111, 222
WINDOWS = [10, 6, 5, 3]
MIDS = [f"m{i}" for i in range(4)]
AS_OF = datetime(2026, 5, 1, tzinfo=UTC)
SETTINGS = Settings(fotmob={"shot_recent_windows": WINDOWS,
                            "match_detail_matches": 6})


def own(mid: str) -> MatchShotAggregate:
    return MatchShotAggregate(
        match_id=mid, team_id=US, opponent_id=THEM, shots=10,
        shots_on_target=4, shots_inside_box=6, shots_outside_box=4,
        xg=1.0, npxg=1.0, xgot=0.8)


def opp(mid: str, **over) -> MatchShotAggregate:
    kw = dict(shots=12, shots_on_target=5, shots_inside_box=7,
              shots_outside_box=5, npxg=1.2, xgot=1.0)
    kw.update(over)
    return MatchShotAggregate(match_id=mid, team_id=THEM, opponent_id=US, **kw)


def profile(*, opponents=None, mine=None) -> TeamProfile:
    p = TeamProfile(team=TeamRef(canonical=TEAM, fotmob_id=str(US)),
                    league="epl")
    p.stats = TeamStats(played=4)
    p.shot_matches = list(mine if mine is not None else [own(m)
                                                        for m in MIDS])
    p.opponent_matches = list(opponents if opponents is not None
                              else [opp(m) for m in MIDS])
    p.shot_aggregates = {
        f"all{w}": RecentShotAggregate(
            team_id=US, window=w, requested_matches=w,
            available_matches=min(w, len(MIDS)), match_ids=MIDS[:w])
        for w in WINDOWS}
    return p


def season(home_team: str) -> list[SeasonMatch]:
    """`home_team` 을 바꾸면 팀명 조인이 실패한다."""
    return [SeasonMatch(
        match_id=m, competition="epl",
        kickoff=datetime(2026, 4, 1 + i, tzinfo=UTC), kickoff_aware=True,
        home_team=home_team, away_team="상대", home_goals=1, away_goals=2,
        finished=True) for i, m in enumerate(MIDS)]


MATCHED = season(TEAM)          # 색인이 맞는다
UNMATCHED = season("다른이름")   # 색인에서 이 팀을 못 찾는다


def defense(sm, prof=None, quality=None):
    return analysis.build_defensive_quality(
        prof or profile(), TEAM, sm, AS_OF, WINDOWS,
        analysis.defensive_quality_config(SETTINGS),
        thresholds=analysis.thresholds_from(SETTINGS), quality=quality)


def attack(sm, prof=None, quality=None):
    return analysis.build_chance_quality(
        prof or profile(), TEAM, sm, AS_OF, WINDOWS,
        analysis.chance_quality_config(SETTINGS), quality=quality)


def reason_lines(axis):
    return [n for n in axis.notes if n.startswith("값 없음")]


# --------------------------------------------------------------------------
# 1. 색인이 있으면 기존대로
# --------------------------------------------------------------------------
def test_1_season_index_present_keeps_metrics():
    ax = defense(MATCHED)
    assert ax.value("recent6.goals_against") == 2.0
    assert abs(ax.value("recent6.goals_against_minus_npxga") - 0.8) < 1e-9
    assert abs(
        ax.value("recent6.goals_against_minus_xgot_against") - 1.0) < 1e-9
    assert reason_lines(ax) == [], "정상인데 사유가 붙었다"

    cq = attack(MATCHED)
    assert cq.value("recent6.goals") == 1.0
    assert cq.value("recent6.goals_minus_xg") == 0.0
    assert reason_lines(cq) == []


def test_1b_normal_case_leaves_data_quality_clean():
    """정상 데이터의 **최근 창**에는 사유가 붙지 않는다.

    시즌 블록은 이 픽스처의 `TeamStats` 가 비어 있어 원래부터
    '시즌 지표 없음' 이다 — 이번 교정과 무관한 기존 동작이라 제외한다.
    """
    q = analysis.DataQuality()
    defense(MATCHED, quality=q)
    recent = {k: v for k, v in q.axes.items() if "recent" in k}
    assert recent, "최근 창이 하나도 없다"
    for key, entry in recent.items():
        assert entry["degraded_reason"] == "", f"{key}: {entry}"


# --------------------------------------------------------------------------
# 2. 색인이 없으면 값이 None
# --------------------------------------------------------------------------
def test_2_season_index_missing_gives_none():
    ax = defense(UNMATCHED)
    assert ax.get("recent6.goals_against") is None
    assert ax.get("recent6.goals_against_minus_npxga") is None
    assert ax.get("recent6.goals_against_minus_xgot_against") is None
    # 상대 집계에서 오는 값은 그대로 살아 있어야 한다.
    assert ax.value("recent6.shots_against") == 12.0
    assert ax.value("recent6.npxga") == 1.2


# --------------------------------------------------------------------------
# 3. 사유가 보존된다
# --------------------------------------------------------------------------
def test_3_reason_is_preserved_in_axis_notes():
    ax = defense(UNMATCHED)
    lines = reason_lines(ax)
    assert lines, "사유가 사라졌다"
    joined = " ".join(lines)
    assert analysis.NO_SCORE in joined, joined
    for label in ("실점", "실점 − npxGA", "실점 − 피xGOT"):
        assert label in joined, f"{label} 이 사유에 없다: {joined}"


def test_3b_reason_is_preserved_in_data_quality():
    q = analysis.DataQuality()
    defense(UNMATCHED, quality=q)
    entry = q.axes["defensive_quality.recent6"]
    assert entry["available"] is True, "다른 지표는 있으므로 available 이다"
    assert analysis.NO_SCORE in entry["degraded_reason"], entry


def test_3c_reason_survives_when_only_some_matches_join():
    """일부만 이어지면 값은 있고, 그 사실이 지표 note 에 남는다."""
    partial = [SeasonMatch(
        match_id="m0", competition="epl",
        kickoff=datetime(2026, 4, 1, tzinfo=UTC), kickoff_aware=True,
        home_team=TEAM, away_team="상대", home_goals=1, away_goals=3,
        finished=True)]
    ax = defense(partial)
    m = ax.get("recent6.goals_against_minus_npxga")
    assert m is not None and m.value is not None
    assert m.sample_count == 1, "이어진 경기만 세야 한다"
    assert "제외" in m.note, m.note


# --------------------------------------------------------------------------
# 4~5. 값은 바뀌지 않는다 / None 이 0 이 되지 않는다
# --------------------------------------------------------------------------
def test_4_numeric_values_are_unchanged():
    """교정 대상은 사유뿐 — 숫자는 손대지 않는다."""
    ax = defense(MATCHED)
    expect = {"recent6.shots_against": 12.0,
              "recent6.shots_on_target_against": 5.0,
              "recent6.shots_inside_box_against": 7.0,
              "recent6.npxga": 1.2, "recent6.xgot_against": 1.0,
              "recent6.goals_against": 2.0,
              "recent6.npxga_per_shot_against": 0.1,
              "recent3.shots_against": 12.0}
    for key, want in expect.items():
        got = ax.value(key)
        assert got is not None and abs(got - want) < 1e-9, f"{key}: {got}"


def test_5_none_never_becomes_zero():
    ax = defense(UNMATCHED)
    for key in ("recent6.goals_against", "recent6.goals_against_minus_npxga",
                "recent6.goals_against_minus_xgot_against"):
        m = ax.get(key)
        assert m is None or m.value is None, f"{key} 가 숫자가 됐다: {m}"
        assert ax.value(key) != 0.0

    # 0 은 여전히 실제 값이다.
    zero = [opp(m, shots=0, shots_on_target=0, shots_inside_box=0,
                shots_outside_box=0, npxg=0.0, xgot=0.0) for m in MIDS]
    ax2 = defense(MATCHED, prof=profile(opponents=zero))
    assert ax2.value("recent6.shots_against") == 0.0
    assert ax2.get("recent6.shots_against").known is True
    assert ax2.value("recent6.npxga") == 0.0


def test_5b_zero_denominator_reason_is_kept():
    """피슛 합계가 0 이면 비율은 None — 그 사유도 남아야 한다."""
    zero = [opp(m, shots=0, npxg=0.0) for m in MIDS]
    ax = defense(MATCHED, prof=profile(opponents=zero))
    assert ax.get("recent6.npxga_per_shot_against") is None
    joined = " ".join(reason_lines(ax))
    assert "분모" in joined, joined
    assert "피슛당 npxGA" in joined, joined


# --------------------------------------------------------------------------
# 6. 2-B 도 같은 경로로 고쳐졌다
# --------------------------------------------------------------------------
def test_6_chance_quality_reason_is_preserved_too():
    cq = attack(UNMATCHED)
    assert cq.get("recent6.goals") is None
    assert cq.get("recent6.goals_minus_xg") is None
    assert cq.get("recent6.goals_minus_npxg") is None
    assert cq.get("recent6.goals_minus_xgot") is None
    joined = " ".join(reason_lines(cq))
    assert analysis.NO_SCORE in joined, joined
    assert "득점" in joined
    # 슛 계열은 그대로 살아 있다.
    assert cq.value("recent6.shots") == 10.0
    assert cq.value("recent6.xg_per_shot") == 0.1


def test_6b_one_shared_fix_not_two():
    """두 축이 같은 함수(`_put`)를 통해 사유를 남긴다."""
    import inspect
    src = inspect.getsource(analysis._put)
    assert "reasons" in src and "setdefault" in src
    for fn in (analysis.build_chance_quality,
               analysis.build_defensive_quality):
        body = inspect.getsource(fn)
        assert "reasons=missing" in body, fn.__name__
        assert "_merge_missing" in body, fn.__name__


# --------------------------------------------------------------------------
# 7. notes 중복 방지
# --------------------------------------------------------------------------
def test_7_reason_is_not_repeated_per_window():
    """창 4개(10/6/5/3)에 같은 사유가 네 번 적히면 안 된다."""
    ax = defense(UNMATCHED)
    lines = reason_lines(ax)
    assert len(lines) == 1, f"{len(lines)}줄로 늘어났다: {lines}"
    line = lines[0]
    assert line.count(analysis.NO_SCORE) == 1
    # 한 줄 안에 영향받은 기간이 전부 적혀 있어야 한다.
    for w in WINDOWS:
        assert analysis.period_label(f"recent{w}") in line, (w, line)


def test_7b_window_specific_reasons_stay_separate():
    """사유가 실제로 다르면 합치지 않는다."""
    zero = [opp(m, shots=0, npxg=0.0) for m in MIDS]
    ax = defense(UNMATCHED, prof=profile(opponents=zero))
    lines = reason_lines(ax)
    assert len(lines) == 2, lines            # 스코어 없음 + 분모 0
    joined = " ".join(lines)
    assert analysis.NO_SCORE in joined and "분모" in joined


# --------------------------------------------------------------------------
# 8. 직렬화 왕복
# --------------------------------------------------------------------------
def test_8_reason_survives_serialization():
    ta = analysis.build_team_analysis(
        profile(), TEAM, UNMATCHED, AS_OF, SETTINGS, is_home=True)
    back = revive_match_analysis(asdict(MatchAnalysis(home=ta)))
    for axis in (back.home.defensive_quality, back.home.chance_quality):
        lines = [n for n in axis.notes if n.startswith("값 없음")]
        assert lines, f"{axis.name}: 왕복 후 사유가 사라졌다"
        assert analysis.NO_SCORE in " ".join(lines)
    dq = back.home.data_quality
    assert analysis.NO_SCORE in dq.axes["defensive_quality.recent6"][
        "degraded_reason"]


def test_8b_metric_level_note_survives_serialization():
    partial = [SeasonMatch(
        match_id="m0", competition="epl",
        kickoff=datetime(2026, 4, 1, tzinfo=UTC), kickoff_aware=True,
        home_team=TEAM, away_team="상대", home_goals=1, away_goals=3,
        finished=True)]
    ta = analysis.build_team_analysis(
        profile(), TEAM, partial, AS_OF, SETTINGS)
    back = revive_match_analysis(asdict(MatchAnalysis(home=ta)))
    m = back.home.defensive_quality.get("recent6.goals_against_minus_npxga")
    assert m is not None and "제외" in m.note, m


# --------------------------------------------------------------------------
# 상태 구분 (§2) — 서로 다른 사유가 서로 다른 문구로 남는가
# --------------------------------------------------------------------------
def test_states_stay_distinct():
    q = analysis.DataQuality()
    # 상대 집계가 아예 없음
    empty = profile(opponents=[])
    ax = defense(MATCHED, prof=empty, quality=q)
    assert q.axes["defensive_quality.recent6"]["degraded_reason"] == \
        "상대 집계 없음"
    assert not any(k.startswith("recent") for k in ax.metrics)

    # 조인 실패 — 다른 문구
    q2 = analysis.DataQuality()
    defense(UNMATCHED, quality=q2)
    assert q2.axes["defensive_quality.recent6"]["degraded_reason"] == \
        analysis.NO_SCORE

    # 트렌드 차단 사유는 기존 표현 그대로
    ax3 = defense(MATCHED)
    t = ax3.get("trend6.goals_against")
    if t is not None and t.value is None:
        assert analysis.parse_trend_band(t) == analysis.NOT_MEANINGFUL


def test_no_new_dataclass_or_enum():
    """교정은 기존 구조만 쓴다 (§4)."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(analysis))
    classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert classes == [], f"새 클래스가 생겼다: {classes}"
    assert isinstance(analysis.NO_SCORE, str)


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
