"""슛 이벤트 계층 회귀 테스트 (Phase 1-C).

`content.shotmap.shots[]` → ShotEvent → 경기별 → 팀별 → 최근 N경기 집계까지의
경로를 픽스처로 고정한다. 네트워크를 쓰지 않는다.

픽스처의 **필드 이름과 situation 값**은 Phase 0·1-B 에서 실물로 확인한 것만
쓴다. 값 자체는 합성이며, 검증하는 것은 '어떤 모양이 어떤 집계로 가는가' 다.

pytest 없이도 돈다:  python tests/test_shot_events.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import shots                                        # noqa: E402
from toto.sources import fotmob                               # noqa: E402

HOME, AWAY = 8650, 8455


def shot(**kw):
    """실물 필드 이름 그대로. 지정하지 않은 것은 기본값."""
    base = {"id": kw.pop("id", 1), "teamId": HOME, "playerId": 100,
            "playerName": "A Player", "x": 90.0, "y": 50.0, "min": 10,
            "minAdded": None, "period": "FirstHalf",
            "expectedGoals": 0.10, "expectedGoalsOnTarget": None,
            "isOnTarget": False, "isBlocked": False, "isOwnGoal": False,
            "isFromInsideBox": True, "shotType": "RightFoot",
            "situation": "RegularPlay", "eventType": "Miss"}
    base.update(kw)
    return base


# 홈 5슛: 일반3 + 코너1 + PK1.  xG 합 1.90, PK 0.80 → npxG 1.10
# 유효 3개(그중 1골), 블록 1개, 박스 밖 1개
HOME_SHOTS = [
    shot(id=1, expectedGoals=0.30, expectedGoalsOnTarget=0.45, isOnTarget=True,
         eventType="AttemptSaved"),
    shot(id=2, expectedGoals=0.20, isOnTarget=False, isBlocked=True,
         eventType="Blocked"),
    shot(id=3, expectedGoals=0.15, isFromInsideBox=False, isOnTarget=False,
         situation="FastBreak", eventType="Miss"),
    shot(id=4, expectedGoals=0.45, expectedGoalsOnTarget=0.70, isOnTarget=True,
         situation="FromCorner", shotType="Header", eventType="Goal"),
    shot(id=5, expectedGoals=0.80, expectedGoalsOnTarget=0.85, isOnTarget=True,
         situation="Penalty", eventType="Goal", min=70, period="SecondHalf"),
]
# 원정 2슛: xG 0.35, PK 없음 → npxG 0.35
AWAY_SHOTS = [
    shot(id=6, teamId=AWAY, expectedGoals=0.25, expectedGoalsOnTarget=0.30,
         isOnTarget=True, eventType="AttemptSaved"),
    shot(id=7, teamId=AWAY, expectedGoals=0.10, isOnTarget=False,
         situation="FreeKick", isFromInsideBox=False, eventType="Miss"),
]


def match_details(mid="M1", home_id=HOME, away_id=AWAY, periods=True):
    """실물 구조를 흉내낸 matchDetails 하나."""
    rows = [{"key": "g", "stats": [
        {"key": "expected_goals", "stats": [1.90, 0.35]},
        {"key": "expected_goals_non_penalty", "stats": [1.10, 0.35]},
        {"key": "expected_goals_on_target", "stats": [2.00, 0.30]},
        {"key": "total_shots", "stats": [5, 2]},
        {"key": "ShotsOnTarget", "stats": [3, 1]},
    ]}]
    stats = ({"Periods": {"All": {"stats": rows}}} if periods
             else {"stats": rows})
    return {
        "general": {"matchId": mid, "homeTeam": {"id": home_id},
                    "awayTeam": {"id": away_id}},
        "content": {"stats": stats,
                    "shotmap": {"shots": HOME_SHOTS + AWAY_SHOTS}},
    }


def events(mid="M1"):
    return shots.parse_shot_events(HOME_SHOTS + AWAY_SHOTS, mid)


# --------------------------------------------------------------------------
# Test 1 — 슛 이벤트 파싱
# --------------------------------------------------------------------------
def test_shot_event_parsing():
    evs = events()
    assert len(evs) == 7
    e = evs[0]
    assert e.match_id == "M1" and e.team_id == HOME and e.event_id == "1"
    assert e.player_id == 100 and e.player_name == "A Player"
    assert e.x == 90.0 and e.y == 50.0 and e.minute == 10
    assert e.period == "FirstHalf" and e.shot_type == "RightFoot"
    assert e.expected_goals == 0.30 and e.expected_goals_on_target == 0.45
    assert e.is_on_target is True and e.is_inside_box is True
    assert e.situation == "RegularPlay" and e.event_type == "AttemptSaved"


def test_shot_event_keeps_three_states_for_booleans():
    """False 와 '모름' 을 구분한다 — None 을 False 로 접으면 안 된다."""
    e = shots.parse_shot_events([shot(id=9, isFromInsideBox=None,
                                      isOnTarget=None)], "M1")[0]
    assert e.is_inside_box is None and e.is_on_target is None
    assert shots.parse_shot_events([shot(id=9, isOnTarget=False)], "M1")[0] \
        .is_on_target is False


def test_shot_without_team_id_is_dropped():
    """팀을 특정할 수 없는 슛은 어느 쪽에도 넣지 않는다."""
    evs = shots.parse_shot_events([shot(id=1), shot(id=2, teamId=None)], "M1")
    assert len(evs) == 1


# --------------------------------------------------------------------------
# Test 2 — teamId 분리
# --------------------------------------------------------------------------
def test_team_split_by_team_id():
    aggs = shots.aggregate_match(events(), HOME, AWAY)
    assert set(aggs) == {HOME, AWAY}
    assert aggs[HOME].shots == 5 and aggs[AWAY].shots == 2
    assert aggs[HOME].is_home is True and aggs[AWAY].is_home is False


def test_home_away_uses_team_id_not_array_order():
    """홈/원정을 뒤바꿔 넘기면 판정도 따라 바뀐다 = 배열 순서가 아니라 ID 를 본다."""
    flipped = shots.aggregate_match(events(), AWAY, HOME)
    assert flipped[HOME].is_home is False and flipped[AWAY].is_home is True
    unknown = shots.aggregate_match(events(), None, None)
    assert unknown[HOME].is_home is None, "모르면 추측하지 않는다"


def test_home_away_ids_found_by_shape():
    assert fotmob._home_away_ids(match_details()) == (HOME, AWAY)
    assert fotmob._home_away_ids({"content": {}}) == (None, None)


# --------------------------------------------------------------------------
# Test 3 — All period 선택 (Phase 1-B 결함 재발 방지)
# --------------------------------------------------------------------------
def _periods_doc():
    def g(npxg, sh):
        return {"stats": [{"key": "g", "stats": [
            {"key": "expected_goals_non_penalty", "stats": [npxg, 0.5]},
            {"key": "total_shots", "stats": [sh, 4]}]}]}
    return {"content": {"stats": {"Periods": {
        "All": g(2.40, 18), "FirstHalf": g(0.35, 6), "SecondHalf": g(2.05, 12)}}}}


def test_all_period_selected_over_halves():
    p = fotmob._match_stat_pairs(_periods_doc())
    assert p["expected_goals_non_penalty"] == (2.40, 0.5), "하프 표를 읽었다"
    assert p["total_shots"] == (18.0, 4.0)


def test_all_period_stable_across_repeats():
    doc = _periods_doc()
    got = {fotmob._match_stat_pairs(doc)["total_shots"] for _ in range(20)}
    assert got == {(18.0, 4.0)}, f"실행마다 달라진다: {got}"


def test_period_fallback_when_absent():
    assert fotmob._all_period({"content": {"stats": {}}}) is None
    p = fotmob._match_stat_pairs(match_details(periods=False))
    assert p["total_shots"] == (5.0, 2.0), "기간 구분이 없어도 읽어야 한다"


# --------------------------------------------------------------------------
# Test 4 — npxG 는 PK 를 실제 분류로 제외
# --------------------------------------------------------------------------
def test_npxg_excludes_penalty_by_situation():
    a = shots.aggregate_match(events(), HOME, AWAY)[HOME]
    assert round(a.xg, 4) == 1.90
    assert round(a.npxg, 4) == 1.10          # 0.80 짜리 PK 제외
    assert round(a.xg - a.npxg, 4) == 0.80
    assert a.penalties == 1


def test_npxg_is_not_a_constant_subtraction():
    """PK xG 가 0.76 이 아니어도 그 슛의 실제 값만큼만 빠진다."""
    evs = shots.parse_shot_events(
        [shot(id=1, expectedGoals=1.00),
         shot(id=2, expectedGoals=0.33, situation="Penalty")], "M1")
    a = shots.aggregate_match(evs)[HOME]
    assert round(a.xg, 4) == 1.33 and round(a.npxg, 4) == 1.00


def test_penalty_only_team_gets_zero_npxg_not_none():
    """PK 만 찬 팀의 npxG 는 '모름'이 아니라 실제 0 이다."""
    evs = shots.parse_shot_events(
        [shot(id=1, expectedGoals=0.80, situation="Penalty")], "M1")
    a = shots.aggregate_match(evs)[HOME]
    assert a.xg == 0.80 and a.npxg == 0.0


# --------------------------------------------------------------------------
# Test 5 — xGOT 집계
# --------------------------------------------------------------------------
def test_xgot_aggregation():
    a = shots.aggregate_match(events(), HOME, AWAY)
    # 홈: 0.45 + 0.70 + 0.85 = 2.00 (None 인 슛은 더하지 않는다)
    assert round(a[HOME].xgot, 4) == 2.00
    assert round(a[AWAY].xgot, 4) == 0.30


def test_xgot_none_when_no_shot_has_it():
    """한 슛도 xGOT 이 없으면 0.0 이 아니라 None 이다."""
    evs = shots.parse_shot_events(
        [shot(id=1, expectedGoalsOnTarget=None)], "M1")
    assert shots.aggregate_match(evs)[HOME].xgot is None


# --------------------------------------------------------------------------
# Test 6 — 경기 스탯과 교차검증
# --------------------------------------------------------------------------
def test_reconciliation_against_match_statistics():
    a = shots.aggregate_match(events(), HOME, AWAY)[HOME]
    stat = {"xg": 1.90, "npxg": 1.10, "xgot": 2.00,
            "shots": 5, "shots_on_target": 3}
    diffs = shots.reconcile(a, stat)
    assert all(abs(v) < 1e-9 for v in diffs.values()), diffs
    assert set(diffs) == {"xg", "npxg", "xgot", "shots", "shots_on_target"}


def test_reconciliation_reports_difference_without_fixing():
    a = shots.aggregate_match(events(), HOME, AWAY)[HOME]
    diffs = shots.reconcile(a, {"npxg": 0.55})   # 하프 표를 읽은 상황
    assert round(diffs["npxg"], 4) == 0.55       # 슛맵 1.10 − 스탯 0.55
    assert a.npxg == 1.10, "대조 때문에 값이 바뀌면 안 된다"


def test_reconciliation_skips_missing_sides():
    a = shots.aggregate_match(events(), HOME, AWAY)[HOME]
    assert shots.reconcile(a, {}) == {}


# --------------------------------------------------------------------------
# Test 7 — 중복 검출
# --------------------------------------------------------------------------
def test_duplicate_detection_by_event_id():
    evs = shots.parse_shot_events(HOME_SHOTS + HOME_SHOTS, "M1")
    kept, dropped = shots.dedupe(evs)
    assert len(kept) == 5 and dropped == 5


def test_duplicate_detection_without_event_id():
    """id 가 유일하다고 가정하지 않는다 — 없으면 내용으로 판정한다."""
    raw = [shot(id=None, expectedGoals=0.4), shot(id=None, expectedGoals=0.4)]
    kept, dropped = shots.dedupe(shots.parse_shot_events(raw, "M1"))
    assert len(kept) == 1 and dropped == 1
    # 서로 다른 슛은 남는다
    raw2 = [shot(id=None, min=10), shot(id=None, min=44)]
    kept2, _ = shots.dedupe(shots.parse_shot_events(raw2, "M1"))
    assert len(kept2) == 2


def test_same_match_not_aggregated_twice():
    a = shots.aggregate_match(events("M1"), HOME, AWAY)[HOME]
    r = shots.aggregate_recent([a, a, a], HOME, window=6)
    assert r.available_matches == 1 and r.match_ids == ["M1"]


# --------------------------------------------------------------------------
# Test 8 — 최근 N경기 집계
# --------------------------------------------------------------------------
def _series(n=4):
    """최신순 n경기. 홈/원정이 번갈아 나온다."""
    out = []
    for i in range(n):
        mid = f"M{i}"
        evs = events(mid)
        home_first = (i % 2 == 0)
        aggs = shots.aggregate_match(evs, HOME if home_first else AWAY,
                                     AWAY if home_first else HOME)
        out.append(aggs[HOME])
    return out


def test_recent_window_limits_and_counts():
    s = _series(4)
    r3 = shots.aggregate_recent(s, HOME, window=3)
    assert r3.requested_matches == 3 and r3.available_matches == 3
    assert r3.match_ids == ["M0", "M1", "M2"], "최신순 앞에서 N건"
    assert r3.total("shots") == 15 and r3.avg("shots") == 5.0
    assert round(r3.total("npxg"), 4) == 3.30
    assert round(r3.avg("npxg"), 4) == 1.10


def test_recent_window_larger_than_available():
    """창이 받아 온 경기보다 크면 감추지 않고 available 에 적는다."""
    r10 = shots.aggregate_recent(_series(4), HOME, window=10)
    assert r10.requested_matches == 10 and r10.available_matches == 4


def test_windows_are_configurable_not_hardcoded():
    got = shots.aggregate_windows(_series(4), HOME, [3, 5, 6, 10])
    assert set(got) == {f"{v}{w}" for w in (3, 5, 6, 10)
                        for v in ("all", "home", "away")}
    assert got["all3"].available_matches == 3
    assert got["all10"].available_matches == 4


# --------------------------------------------------------------------------
# Test 9 — 지표별 표본 수 (Phase 1-B 결함 재발 방지)
# --------------------------------------------------------------------------
def test_metric_specific_sample_count():
    """xGOT 이 일부 경기에만 있으면 그 경기 수로 나눈다."""
    full = shots.aggregate_match(events("M0"), HOME, AWAY)[HOME]
    # xGOT 이 하나도 없는 경기
    bare = shots.aggregate_match(shots.parse_shot_events(
        [shot(id=1, expectedGoals=0.5, expectedGoalsOnTarget=None)], "M1"))[HOME]
    r = shots.aggregate_recent([full, bare], HOME, window=6)

    assert r.available_matches == 2
    assert r.sample("shots") == 2 and r.sample("xgot") == 1
    assert round(r.total("xgot"), 4) == 2.00
    assert round(r.avg("xgot"), 4) == 2.00, "1경기치를 2로 나누면 안 된다"
    assert round(r.avg("xg"), 4) == round((1.90 + 0.50) / 2, 4)


def test_sum_count_average_are_separate():
    r = shots.aggregate_recent(_series(2), HOME, window=6)
    assert r.total("shots") == 10 and r.sample("shots") == 2
    assert r.avg("shots") == 5.0
    assert r.avg("nonexistent") is None and r.sample("nonexistent") == 0


# --------------------------------------------------------------------------
# Test 10 — 홈/원정 분리 집계
# --------------------------------------------------------------------------
def test_home_away_recent_aggregation():
    s = _series(4)          # M0·M2 는 홈, M1·M3 는 원정
    all6 = shots.aggregate_recent(s, HOME, 6, "all")
    home6 = shots.aggregate_recent(s, HOME, 6, "home")
    away6 = shots.aggregate_recent(s, HOME, 6, "away")
    assert all6.available_matches == 4
    assert home6.match_ids == ["M0", "M2"]
    assert away6.match_ids == ["M1", "M3"]
    assert home6.available_matches + away6.available_matches == 4
    assert home6.venue == "home" and away6.venue == "away"


def test_unknown_venue_excluded_from_split_but_kept_in_all():
    """홈/원정을 모르는 경기는 분리 집계에서만 빠진다."""
    unknown = shots.aggregate_match(events("MX"), None, None)[HOME]
    known = shots.aggregate_match(events("M0"), HOME, AWAY)[HOME]
    s = [unknown, known]
    assert shots.aggregate_recent(s, HOME, 6, "all").available_matches == 2
    assert shots.aggregate_recent(s, HOME, 6, "home").match_ids == ["M0"]
    assert shots.aggregate_recent(s, HOME, 6, "away").available_matches == 0


# --------------------------------------------------------------------------
# Test 11 — 없음 vs 0
# --------------------------------------------------------------------------
def test_missing_versus_zero():
    # xG 가 한 슛도 없으면 None. 슛은 셌으므로 개수는 실제 값.
    evs = shots.parse_shot_events(
        [shot(id=1, expectedGoals=None, expectedGoalsOnTarget=None)], "M1")
    a = shots.aggregate_match(evs)[HOME]
    assert a.xg is None and a.npxg is None and a.xgot is None
    assert a.shots == 1, "슛 개수는 실제로 1이다"
    assert a.goals == 0, "골이 없는 것은 실제 0"

    # 값이 없는 지표는 최근 집계에서 세지 않는다
    r = shots.aggregate_recent([a], HOME, 6)
    assert r.sample("xg") == 0 and r.avg("xg") is None
    assert r.sample("shots") == 1 and r.avg("shots") == 1.0


def test_inside_outside_unknown_counted_neither_way():
    evs = shots.parse_shot_events([shot(id=1, isFromInsideBox=None)], "M1")
    a = shots.aggregate_match(evs)[HOME]
    assert a.shots == 1
    assert a.shots_inside_box == 0 and a.shots_outside_box == 0
    assert shots.validate(a) == [], "안+밖 < 전체 는 정상이므로 위반이 아니다"


def test_own_goal_not_counted_as_goal():
    evs = shots.parse_shot_events(
        [shot(id=1, eventType="Goal", isOwnGoal=True)], "M1")
    a = shots.aggregate_match(evs)[HOME]
    assert a.goals == 0 and a.own_goals == 1


# --------------------------------------------------------------------------
# Test 12 — 캐시 동작
# --------------------------------------------------------------------------
class MemCache:
    def __init__(self): self.store = {}
    def get(self, s, k): return self.store.get((s, k))
    def set(self, s, k, v): self.store[(s, k)] = v


class FakeBrowser:
    base = "https://www.fotmob.com"
    available = True
    def __init__(self, payloads): self.payloads = payloads; self.calls = []
    def abs_url(self, p): return self.base + p
    def get_json(self, url):
        self.calls.append(url)
        for mid, d in self.payloads.items():
            if f"matchId={mid}" in url:
                return d
        return None


def test_cache_stores_shot_events_and_avoids_refetch():
    cache, br = MemCache(), FakeBrowser({"M1": match_details()})
    first = fotmob.read_match_details(br, {"id": "M1"}, cache=cache)
    assert len(first["shots"]) == 7
    assert first["team_ids"] == {"home": HOME, "away": AWAY}
    second = fotmob.read_match_details(br, {"id": "M1"}, cache=cache)
    assert len(br.calls) == 1, "캐시가 있는데 다시 요청했다"
    assert first == second


def test_cached_payload_survives_json_roundtrip():
    """캐시는 JSON 이다. 되살린 뒤에도 같은 집계가 나와야 한다."""
    br = FakeBrowser({"M1": match_details()})
    payload = fotmob.read_match_details(br, {"id": "M1"})
    back = json.loads(json.dumps(payload))
    evs = [shots.ShotEvent(**d) for d in back["shots"]]
    a = shots.aggregate_match(evs, back["team_ids"]["home"],
                              back["team_ids"]["away"])
    assert round(a[HOME].npxg, 4) == 1.10 and a[HOME].is_home is True


def test_cache_version_bumped_for_new_payload():
    assert fotmob._CACHE_VERSION >= 6
    assert fotmob._revive({"_v": 5, "teams": {}, "matches": []}) is None


def test_aggregates_survive_league_cache_roundtrip():
    """리그 캐시(_freeze/_revive)가 슛 집계를 잃지 않는가."""
    a = shots.aggregate_match(events("M0"), HOME, AWAY)[HOME]
    from toto.models import TeamStats
    result = {"matches": [], "teams": {"T": {
        "stats": TeamStats(), "form": [], "fotmob_id": str(HOME),
        "page_url": "", "shot_matches": [a],
        "shot_aggregates": shots.aggregate_windows([a], HOME, [6])}}}
    revived = fotmob._revive(json.loads(json.dumps(fotmob._freeze(result))))
    got = revived["teams"]["T"]["shot_aggregates"]["all6"]
    assert isinstance(got, shots.RecentShotAggregate)
    assert got.available_matches == 1 and round(got.avg("npxg"), 4) == 1.10
    assert isinstance(revived["teams"]["T"]["shot_matches"][0],
                      shots.MatchShotAggregate)


# --------------------------------------------------------------------------
# 검증 (§18) — 억지 단언은 넣지 않는다
# --------------------------------------------------------------------------
def test_validate_catches_real_violations():
    a = shots.aggregate_match(events(), HOME, AWAY)[HOME]
    assert shots.validate(a) == []
    a.shots_on_target = 99
    assert any("유효슈팅" in m for m in shots.validate(a))
    b = shots.aggregate_match(events(), HOME, AWAY)[HOME]
    b.npxg = b.xg + 1.0
    assert any("npxG" in m for m in shots.validate(b))
    c = shots.aggregate_match(events(), HOME, AWAY)[HOME]
    c.xg = -0.5
    assert any("음수" in m for m in shots.validate(c))


def test_situation_breakdown_kept_verbatim():
    a = shots.aggregate_match(events(), HOME, AWAY)[HOME]
    assert a.situations["RegularPlay"]["count"] == 2
    assert a.situations["Penalty"]["count"] == 1
    assert round(a.situations["FromCorner"]["xg"], 4) == 0.45
    # 목록에 없는 새 분류가 와도 버리지 않는다
    evs = shots.parse_shot_events([shot(id=1, situation="NewThing")], "M1")
    assert "NewThing" in shots.aggregate_match(evs)[HOME].situations


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
