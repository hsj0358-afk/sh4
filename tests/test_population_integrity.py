"""모집단 무결성 — 대륙대회 자료가 국내리그 분석에 섞이지 않는다 (Phase 6-D-9A).

6-D-9 조사가 찾은 **두 경로**를 막았는지 본다. 둘 다 오늘은 도달 불가지만
(대륙대회 수집이 아직 발화하지 않는다), 6-D-7 이 등록을 끝냈으므로 실제로
수집하는 순간 열린다.

  A. **`unknown` 슛 집계가 값을 냈다.** 창의 경기 ID 가 이 분석의 대회 모집단
     (좁혀진 시즌 색인)에 없으면 시점도 소속도 확인할 수 없는데, 예전에는
     값을 그대로 내고 메모 한 줄만 붙였다 (`analysis.py` 의 네 축).

  B. **대표 팀 항목을 알파벳 순서가 정했다.** `index.setdefault` 라서
     `sorted(['conference','epl'])` 에서 컨퍼런스리그 표가 이기고, 그 항목의
     `stats`·`form`·슛 계층이 통째로 그 팀의 시즌 자료가 됐다.

**`unknown` 은 '값이 None 인 경기' 가 아니다.** 값이 없는 경기는 `_mean` 이
이미 표본에서 빼고 있고(§1-1-2), 여기서 막는 것은 **값이 있는데 어느 모집단
것인지 모르는 경기**다. 두 상태를 같은 말로 다루지 않는다.

pytest 없이도 돈다:  python tests/test_population_integrity.py
"""
from __future__ import annotations

import inspect
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from toto import analysis                                      # noqa: E402
from toto.models import (SeasonMatch, TeamProfile, TeamRef,    # noqa: E402
                         TeamStats)
from toto.shots import MatchShotAggregate, RecentShotAggregate  # noqa: E402
from toto.settings import Settings, load_settings              # noqa: E402
from toto.sources import fotmob                                # noqa: E402

UTC = timezone.utc
TEAM = "Arsenal"
TEAM_ID = 9825
OPP_ID = 8650
WINDOWS = [6]
AS_OF = datetime(2026, 5, 1, tzinfo=UTC)
SETTINGS = Settings(fotmob={"shot_recent_windows": WINDOWS,
                            "match_detail_matches": 6})

VALID = ["v0", "v1", "v2"]          # 시즌 색인에 있는 경기
STRAY = "x9"                        # 색인에 없는 경기 (다른 대회에서 왔다고 보자)


def kick(day: int) -> datetime:
    return datetime(2026, 4, day, tzinfo=UTC)


def own(mid: str, *, xg=1.0) -> MatchShotAggregate:
    return MatchShotAggregate(
        match_id=mid, team_id=TEAM_ID, opponent_id=OPP_ID, is_home=True,
        shots=10, shots_on_target=4, shots_inside_box=6, shots_outside_box=4,
        xg=xg, npxg=xg, xgot=0.8)


def opp(mid: str, *, xg=1.0) -> MatchShotAggregate:
    return MatchShotAggregate(
        match_id=mid, team_id=OPP_ID, opponent_id=TEAM_ID, is_home=False,
        shots=8, shots_on_target=3, shots_inside_box=5, shots_outside_box=3,
        xg=xg, npxg=xg, xgot=0.6)


def window(mids) -> RecentShotAggregate:
    return RecentShotAggregate(
        team_id=TEAM_ID, window=6, venue="all", requested_matches=6,
        available_matches=len(mids), match_ids=list(mids),
        sums={"xg": float(len(mids)), "npxg": float(len(mids)),
              "shots": 10.0 * len(mids)},
        counts={"xg": len(mids), "npxg": len(mids), "shots": len(mids)})


def profile(mids, *, stray_xg=9.0) -> TeamProfile:
    """창에 `mids` 가 든 프로필. `STRAY` 는 눈에 띄게 큰 xG 를 준다."""
    p = TeamProfile(team=TeamRef(canonical=TEAM, fotmob_id=str(TEAM_ID)),
                    league="epl")
    p.stats = TeamStats(played=len(VALID))
    p.shot_matches = [own(m, xg=(stray_xg if m == STRAY else 1.0))
                      for m in mids]
    p.opponent_matches = [opp(m, xg=(stray_xg if m == STRAY else 1.0))
                          for m in mids]
    p.shot_aggregates = {"all6": window(mids)}
    return p


def season(mids, *, as_of_days=1) -> list[SeasonMatch]:
    return [SeasonMatch(
        match_id=m, competition="epl", kickoff=kick(as_of_days + i),
        kickoff_aware=True, home_team=TEAM, away_team=f"Opp{i}",
        home_goals=2, away_goals=1, finished=True)
        for i, m in enumerate(mids)]


def axes(prof, sm):
    """네 축을 한 번에 만든다 — 같은 규칙이 네 곳에 적용됐는지 보려고."""
    return {
        "time_context": analysis.build_time_context(
            prof, TEAM, sm, AS_OF, WINDOWS,
            analysis.thresholds_from(SETTINGS)),
        "chance_quality": analysis.build_chance_quality(
            prof, TEAM, sm, AS_OF, WINDOWS,
            analysis.chance_quality_config(SETTINGS)),
        "defensive_quality": analysis.build_defensive_quality(
            prof, TEAM, sm, AS_OF, WINDOWS,
            analysis.defensive_quality_config(SETTINGS),
            thresholds=analysis.thresholds_from(SETTINGS)),
        "sustainability": analysis.build_sustainability(
            prof, TEAM, sm, AS_OF, WINDOWS),
    }


# ==========================================================================
# A. unknown 슛 집계 — 값으로 들어가지 않는다
# ==========================================================================
def test_a1_valid_window_still_produces_values():
    """Case 1 — 전부 색인에 있으면 예전과 같이 값이 나온다."""
    ax = axes(profile(VALID), season(VALID))
    assert ax["time_context"].value("recent6.xg") is not None
    assert ax["chance_quality"].value("recent6.xg") is not None
    assert ax["defensive_quality"].value("recent6.shots_against") is not None
    assert ax["sustainability"].value("recent6.xg") is not None


def test_a2_future_window_is_still_blocked():
    """Case 2 — 기준시각 이후 경기가 섞인 창은 **예전 그대로** 막힌다."""
    later = season(VALID, as_of_days=1)
    later.append(SeasonMatch(
        match_id="future1", competition="epl", kickoff=datetime(
            2026, 6, 1, tzinfo=UTC), kickoff_aware=True,
        home_team=TEAM, away_team="Later", home_goals=1, away_goals=0,
        finished=True))
    ax = axes(profile(VALID + ["future1"]), later)
    for name, axis in ax.items():
        assert axis.get("recent6.xg") is None or name == "defensive_quality", \
            f"{name}: 미래 경기가 든 창에서 값이 나왔다"
        assert any("기준시각 이후" in n for n in axis.notes), name


def test_a3_unknown_window_is_blocked():
    """Case 3 — **NEW.** 모집단을 확인하지 못한 창은 값을 내지 않는다.

    창의 경기가 전부 색인 밖이면 남는 표본이 없다.
    """
    ax = axes(profile([STRAY]), season(VALID))
    assert ax["time_context"].get("recent6.xg") is None
    assert ax["chance_quality"].get("recent6.xg") is None
    assert ax["defensive_quality"].get("recent6.shots_against") is None
    assert ax["sustainability"].get("recent6.xg") is None


def test_a4_unknown_numbers_never_enter_the_aggregate():
    """Case 4 — valid 와 unknown 이 섞이면 unknown 의 숫자가 빠진다.

    `STRAY` 는 xG 9.0 이고 나머지는 1.0 이다. 섞인 채로 평균을 내면 3.0 이
    되는데, 빼면 1.0 이다 — **숫자가 실제로 달라지는 것**을 본다.
    """
    mixed = VALID + [STRAY]
    ax = axes(profile(mixed), season(VALID))

    cq = ax["chance_quality"].get("recent6.xg")
    assert cq is not None, "확인된 경기 3건이 남았으므로 값이 있어야 한다"
    assert abs(cq.value - 1.0) < 1e-9, f"섞인 값이 새어 나왔다: {cq.value}"
    assert cq.sample_count == 3, cq.sample_count

    sus = ax["sustainability"].get("recent6.xg")
    assert sus is not None and abs(sus.value - 1.0) < 1e-9, sus
    assert sus.sample_count == 3, sus.sample_count

    dq = ax["defensive_quality"].get("recent6.npxga")
    assert dq is not None and abs(dq.value - 1.0) < 1e-9, dq
    assert dq.sample_count == 3, dq.sample_count


def test_a4b_time_context_blocks_instead_of_filtering():
    """2-A 는 창의 **합계**를 쓰므로 한 경기만 빼낼 수 없다 — 통째로 뺀다.

    거르지 않는 것이 아니라 **거를 수 없는 자료 모양**이다. 섞인 합계를
    그대로 내면 unknown 의 숫자가 평균에 남으므로, 값을 내지 않는 쪽을 고른다.
    """
    axis = axes(profile(VALID + [STRAY]), season(VALID))["time_context"]
    assert axis.get("recent6.xg") is None
    assert any("확인하지 못한" in n for n in axis.notes), axis.notes
    # 결과 지표는 색인에서 오므로 그대로 남는다 — 조용히 비지 않는다.
    assert axis.value("recent6.goals") is not None


def test_a5_reason_is_never_silent():
    """뺐다는 사실이 축 notes 에 남는다 (§1-6-1)."""
    for name, axis in axes(profile(VALID + [STRAY]), season(VALID)).items():
        assert any("확인하지 못한" in n for n in axis.notes), \
            f"{name}: 사유 없이 조용히 뺐다"


def test_a6_none_is_not_zero():
    """값이 없으면 `None` 이고 0 이 아니다 (§1-5)."""
    ax = axes(profile([STRAY]), season(VALID))
    for name, axis in ax.items():
        for key, metric in axis.metrics.items():
            if not key.startswith("recent"):
                continue
            assert metric.value != 0.0 or metric.sample_count > 0, \
                f"{name}.{key}: 표본 0 인데 값이 0 으로 들어갔다"


def test_a7_empty_population_makes_no_judgment():
    """견줄 모집단이 없으면 모집단 판정을 하지 않는다.

    색인을 통째로 못 받은 실행(`--demo` · 색인 수집 실패)에서 전부 unknown 으로
    보면 슛 지표가 통째로 사라진다. 그것은 오염 차단이 아니라 **자료 부재**다.
    """
    future, unknown = analysis._window_time_check(window(VALID), set(), set())
    assert unknown == [], "모집단이 없는데 미확인 판정을 했다"
    assert future == []
    ax = axes(profile(VALID), [])
    assert ax["chance_quality"].value("recent6.xg") is not None
    assert ax["sustainability"].value("recent6.xg") is not None


def test_a8_unlabelled_index_is_still_a_population():
    """대회 표시가 없는 옛 색인은 여전히 모집단이다 (§1-30).

    `scope_to_competition` 이 그때 색인을 통째로 넘겨주므로 `known_ids` 가
    차 있고, 그 안에 든 경기는 unknown 이 아니다.
    """
    old = season(VALID)
    for m in old:
        m.competition = ""
    ta = analysis.build_team_analysis(
        profile(VALID), TEAM, old, AS_OF, SETTINGS, competition="epl")
    assert ta.chance_quality.value("recent6.xg") is not None


def test_a9_drop_unknown_keeps_rows_untouched_when_nothing_to_drop():
    rows = [own(m) for m in VALID]
    assert analysis.drop_unknown(rows, []) is rows


def test_a10_drop_unknown_removes_only_named_ids():
    rows = [own(m) for m in VALID + [STRAY]]
    kept = analysis.drop_unknown(rows, [STRAY])
    assert [r.match_id for r in kept] == VALID


def test_a11_all_four_axes_use_the_same_helper():
    """같은 규칙이 네 축에 **같은 함수**로 적용된다 (§1-8)."""
    users = [fn for fn in (analysis.build_chance_quality,
                           analysis.build_defensive_quality,
                           analysis.build_sustainability)
             if "drop_unknown" in inspect.getsource(fn)]
    assert len(users) == 3, "경기별 줄을 쓰는 세 축이 헬퍼를 써야 한다"
    # 2-A 는 창의 합계를 쓰므로 거르지 못하고 막는다 — 같은 `unknown` 을 본다.
    src = inspect.getsource(analysis.build_time_context)
    assert "unknown" in src and "_shot_values" in src


def test_a12_aggregate_fallback_cannot_reintroduce_unknown():
    """창 합계 폴백이 뒷문이 되지 않는다.

    2-B 는 경기별 원재료가 없으면 창의 합계로 폴백하는데, 그 합계에는 뺀
    경기의 숫자가 **이미 더해져 있다.** unknown 이 있으면 폴백하지 않는다.
    """
    p = profile(VALID + [STRAY])
    p.shot_matches = []                    # 경기별 원재료가 없다
    axis = analysis.build_chance_quality(
        p, TEAM, season(VALID), AS_OF, WINDOWS,
        analysis.chance_quality_config(SETTINGS))
    assert axis.get("recent6.xg") is None, "폴백으로 섞인 합계가 새어 나왔다"
    assert any("확인한 경기가 남지 않아" in n for n in axis.notes), axis.notes


# ==========================================================================
# B. 대표 팀 항목 — 알파벳 순서가 아니라 국내리그가 이긴다
# ==========================================================================
REAL = load_settings()


def entries(**by_league) -> dict:
    return {k: {"teams": {t: {"src": k} for t in v}}
            for k, v in by_league.items()}


def test_b1_domestic_beats_continental():
    """Arsenal 이 epl 과 ucl 에 다 있으면 **epl** 항목이 대표다."""
    data = entries(epl=[TEAM], ucl=[TEAM])
    idx = fotmob.team_index(data, sorted(data), REAL)
    assert idx[TEAM]["src"] == "epl", idx


def test_b2_alphabetical_order_is_not_the_rule():
    """`conference` 는 `epl` 보다 알파벳이 앞선다 — 그래도 epl 이 이긴다.

    예전 `setdefault` 가 정확히 여기서 뒤집혔다.
    """
    data = entries(conference=[TEAM], epl=[TEAM])
    assert sorted(data)[0] == "conference", "전제가 깨졌다"
    idx = fotmob.team_index(data, sorted(data), REAL)
    assert idx[TEAM]["src"] == "epl", idx


def test_b3_three_competitions_still_pick_domestic():
    data = entries(conference=[TEAM], epl=[TEAM], ucl=[TEAM])
    idx = fotmob.team_index(data, sorted(data), REAL)
    assert idx[TEAM]["src"] == "epl", idx


def test_b4_continental_only_team_keeps_its_entry():
    """국내 항목이 없는 팀은 그 대회 항목이 그대로 대표다 (§1-5)."""
    data = entries(conference=["Rijeka"], epl=[TEAM])
    idx = fotmob.team_index(data, sorted(data), REAL)
    assert idx["Rijeka"]["src"] == "conference", idx
    assert idx[TEAM]["src"] == "epl", idx


def test_b5_single_competition_is_unchanged():
    """대회가 하나면 예전과 같다."""
    data = entries(epl=[TEAM, "Chelsea"])
    idx = fotmob.team_index(data, sorted(data), REAL)
    assert {k: v["src"] for k, v in idx.items()} == {
        TEAM: "epl", "Chelsea": "epl"}


def test_b6_domestic_only_run_matches_setdefault_exactly():
    """국내리그만 모은 실행은 `setdefault` 와 **결과가 같다**.

    같은 순위끼리는 바꾸지 않으므로 먼저 온 것이 그대로 남는다 — 기존 8개
    리그 동작이 한 칸도 바뀌지 않는다는 근거다.
    """
    data = entries(epl=[TEAM, "Chelsea"], laliga=["Chelsea", "Madrid"],
                   seriea=["Madrid"])
    keys = sorted(data)
    old: dict = {}
    for k in keys:
        for t, e in data[k]["teams"].items():
            old.setdefault(t, e)
    assert fotmob.team_index(data, keys, REAL) == old


def test_b7_rank_comes_from_owns_team_league():
    """판정은 6-D-3 의 함수 하나다 — 키 이름으로 분기하지 않는다."""
    src = inspect.getsource(fotmob.entry_rank)
    assert "owns_team_league" in src
    for banned in ("ucl", "uel", "conference", "epl", "continental", "cup"):
        assert f'"{banned}"' not in src and f"'{banned}'" not in src, banned


def test_b8_domestic_leagues_are_not_ranked_against_each_other():
    """국내리그끼리 순위를 가르지 않는다.

    `league_of(canon) == league_key` 까지 보면 `teams.yaml` 의 소속이 낡았을 때
    대표가 바뀌어 기존 실행 결과가 달라진다 — 그 정정은 `set_league()` 소관이다.
    """
    ranks = {k: fotmob.entry_rank(REAL, k) for k in
             ("epl", "laliga", "seriea", "bundesliga", "ligue1",
              "kleague1", "kleague2", "jleague")}
    assert set(ranks.values()) == {0}, ranks
    assert inspect.signature(fotmob.entry_rank).parameters.keys() == {
        "settings", "league_key"}, "팀 이름을 보지 않는다"


def test_b9_continental_keys_rank_below_domestic():
    for k in ("ucl", "uel", "conference"):
        assert fotmob.entry_rank(REAL, k) == 1, k
    for k in ("epl", "laliga"):
        assert fotmob.entry_rank(REAL, k) == 0, k


def test_b10_enrich_uses_the_shared_helper():
    """`enrich` 가 규칙을 다시 적지 않는다 (§1-8)."""
    src = inspect.getsource(fotmob.enrich)
    assert "team_index(" in src
    assert "setdefault" not in src.split("team_index(")[0][-800:], \
        "옛 setdefault 가 남아 있다"


# ==========================================================================
# C. 범위 — 이번 Phase 가 건드리지 않은 것
# ==========================================================================
def test_c1_predict_is_untouched():
    from toto import predict
    src = inspect.getsource(predict)
    for word in ("competition", "drop_unknown", "team_index", "owns_team_league"):
        assert word not in src, word


def test_c2_rest_is_context_not_a_performance_axis():
    """휴식·경기 밀도는 **경기력 축이 아니다.**

    6-D-9A 때 이 테스트는 "`analysis` 에 `rest_*` 라는 낱말이 없다" 였다 —
    그 Phase 가 일정 문맥을 다루지 않는다는 **범위 선언**이었고, 6-D-9B 가
    바로 그것을 잇는 Phase다. 범위는 옮기고 **지키려던 것은 더 단단히**
    고정한다: 일정 문맥이 기회의 질·수비의 질과 같은 차원이 되지 않는 것.
    """
    from toto.models import TeamAnalysis

    # ① 경기력 축 레지스트리 밖이다. 이 목록을 `panel.py`·`match_material`·
    #    `revive` 가 '축 지표' 로 돈다.
    assert "schedule_context" not in TeamAnalysis.AXES
    assert len(TeamAnalysis.AXES) == 6, TeamAnalysis.AXES

    # ② 방향을 정하지 않았다 — 길수록 좋다/나쁘다를 코드가 말하지 않는다.
    for name in analysis.SCHEDULE_CONTEXT_SPECS:
        assert analysis.SPECS[name][2] == "", name
        assert name in analysis.UNDIRECTED, name

    # ③ 공격·수비·결과 어느 갈래에도 들어가지 않는다.
    for group in (analysis.ATTACK, analysis.DEFENSE, analysis.RESULT):
        for name in analysis.SCHEDULE_CONTEXT_SPECS:
            assert name not in group, name

    # ④ 직접 비교(덤벨)·레이더에 자동으로 올라가지 않는다 (§14).
    from toto import render
    from toto.settings import load_settings
    flat = {n for _axis, n in render._DIRECT_ROWS}
    radar = {str(m.get("key", "")) for m in load_settings().radar_metrics}
    radar |= {str(m.get("home_key", "")) for m in load_settings().radar_metrics}
    for name in analysis.SCHEDULE_CONTEXT_SPECS:
        assert name not in flat, name
        assert name not in radar, name

    # ⑤ 여섯 축에 수학적으로 합산되지 않는다 — 빌더가 축 값을 만들지 않는다.
    src = inspect.getsource(analysis.build_schedule_context)
    for word in ("time_context", "chance_quality", "defensive_quality",
                 "sustainability", "venue_context", "schedule_strength"):
        assert word not in src, word


def test_c2b_schedule_context_does_not_recompute_the_timeline():
    """시간축·휴식을 다시 계산하지 않는다 (§2) — 프로필 값을 읽을 뿐이다."""
    src = inspect.getsource(analysis.build_schedule_context)
    for word in ("team_timeline", "rest_context", "matches_before",
                 "REST_WINDOW_DAYS"):
        assert word not in src, word
    # 창 이름을 코드에 박지 않는다 — 프로필이 들고 온 창을 그대로 읽는다.
    for hard in ("7", "10", "14"):
        assert f"matches_last_{hard}d" not in src, hard


def test_c3_h2h_population_unchanged():
    """H2H 모집단은 건드리지 않는다 (금지 항목)."""
    src = inspect.getsource(fotmob.build_h2h)
    assert "competition" not in src and "owns_team_league" not in src


def test_c4_no_new_recent_population_names():
    for mod in (analysis, fotmob):
        src = inspect.getsource(mod)
        for word in ("overall_recent", "competition_recent",
                     "domestic_league_recent"):
            assert word not in src, f"{mod.__name__}: {word}"


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
