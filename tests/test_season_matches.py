"""시즌 경기 색인 회귀 테스트 (Phase 2 P0-2).

`Report.season_matches` 는 Phase 2 의 **시점별 분석**(2-F 상대 강도)이
"그 경기 이전에 무슨 일이 있었나"를 묻기 위한 과거 경기 색인이다.

가장 중요한 것은 §14 의 **미래 경기 누수 테스트**다 — 시즌 목록 뒤에 미래
경기를 덧붙여도 과거 시점의 조회 결과가 한 건도 달라지면 안 된다.

pytest 없이도 돈다:  python tests/test_season_matches.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto.models import Report, SeasonMatch, matches_before   # noqa: E402
from toto.normalize import TeamResolver                       # noqa: E402
from toto.sources import fotmob                               # noqa: E402

UTC = timezone.utc
# 팀 ID 는 합성. 검증하는 것은 '정규명과 숫자 ID 가 따로 실리는가' 다.
ARS, CHE, EVE, FUL = 9001, 9002, 9003, 9004
NAME = {ARS: "Arsenal", CHE: "Chelsea", EVE: "Everton", FUL: "Fulham"}


def raw_match(mid, hid, aid, utc, score="2 - 1", finished=True):
    """FotMob 리그 응답의 경기 1건 (실물 구조)."""
    return {"id": mid,
            "home": {"id": hid, "name": NAME[hid]},
            "away": {"id": aid, "name": NAME[aid]},
            "status": {"finished": finished, "utcTime": utc,
                       **({"scoreStr": score} if finished else {})}}


def league_response(entries):
    return {"matches": {"allMatches": entries}}


def parsed(entries):
    return fotmob._parse_matches(league_response(entries), TeamResolver())


SEASON = [
    raw_match("M1", ARS, CHE, "2026-08-10T14:00:00Z"),
    raw_match("M2", EVE, FUL, "2026-08-20T18:00:00Z"),
    raw_match("M3", CHE, EVE, "2026-08-29T15:00:00Z"),
]
FUTURE = raw_match("M9", FUL, ARS, "2026-09-10T14:00:00Z",
                   finished=False)


# --------------------------------------------------------------------------
# 1. season_matches 생성
# --------------------------------------------------------------------------
def test_season_matches_field_exists_and_defaults_empty():
    r = Report()
    assert r.season_matches == []
    assert isinstance(r.season_matches, list)


def test_season_matches_built_from_league_response():
    got = fotmob.season_matches_from(parsed(SEASON), "epl")
    assert len(got) == 3
    assert all(isinstance(m, SeasonMatch) for m in got)
    assert {m.match_id for m in got} == {"M1", "M2", "M3"}
    assert all(m.competition == "epl" for m in got)


def test_match_without_id_is_dropped():
    """경기 ID 가 없으면 담지 않는다 — 팀명+날짜를 임의 키로 만들지 않는다."""
    entries = SEASON + [raw_match(None, ARS, FUL, "2026-08-25T14:00:00Z")]
    got = fotmob.season_matches_from(parsed(entries), "epl")
    assert len(got) == 3


# --------------------------------------------------------------------------
# 2·3. 개수 · match_id 유일성
# --------------------------------------------------------------------------
def test_match_ids_are_unique():
    got = fotmob.season_matches_from(parsed(SEASON + SEASON), "epl")
    ids = [m.match_id for m in got]
    assert len(ids) == len(set(ids)), f"중복: {ids}"


# --------------------------------------------------------------------------
# 4. 팀 식별자 — 정규명과 숫자 ID 를 **둘 다** 싣는다
# --------------------------------------------------------------------------
def test_both_identity_systems_are_carried():
    m = next(x for x in fotmob.season_matches_from(parsed(SEASON), "epl")
             if x.match_id == "M1")
    # 프로젝트 canonical = 팀명 문자열
    assert m.home_team == "Arsenal" and m.away_team == "Chelsea"
    # FotMob = 숫자 teamId (슛 계층·순위표와 잇는 열쇠)
    assert m.home_fotmob_id == ARS and m.away_fotmob_id == CHE
    assert isinstance(m.home_fotmob_id, int)


def test_numeric_ids_survive_when_name_resolution_differs():
    """정규명이 붙어도 숫자 ID 는 원본 그대로여야 한다."""
    for m in fotmob.season_matches_from(parsed(SEASON), "epl"):
        assert m.home_fotmob_id in NAME and m.away_fotmob_id in NAME
        assert m.home_fotmob_id != m.away_fotmob_id


# --------------------------------------------------------------------------
# 5. kickoff datetime
# --------------------------------------------------------------------------
def test_kickoff_parsed_as_aware_datetime():
    m = next(x for x in fotmob.season_matches_from(parsed(SEASON), "epl")
             if x.match_id == "M1")
    assert isinstance(m.kickoff, datetime)
    assert m.kickoff_aware is True
    assert m.kickoff.tzinfo is not None
    assert m.kickoff == datetime(2026, 8, 10, 14, 0, tzinfo=UTC)
    assert m.kickoff_raw == "2026-08-10T14:00:00Z"


def test_kickoff_without_timezone_stays_naive():
    """시간대 표시가 없으면 붙이지 않는다 — 임의로 UTC 라고 하지 않는다."""
    dt, aware = fotmob._parse_kickoff("2026-08-10T14:00:00")
    assert aware is False and dt.tzinfo is None


def test_kickoff_unparseable_keeps_raw():
    got = fotmob.season_matches_from(
        parsed([raw_match("MX", ARS, CHE, "언젠가")]), "epl")
    assert got[0].kickoff is None
    assert got[0].kickoff_raw == "언젠가", "근거를 남겨야 한다"
    assert got[0].kickoff_aware is False
    assert fotmob._parse_kickoff("") == (None, False)


# --------------------------------------------------------------------------
# 6. 스코어 · 결과
# --------------------------------------------------------------------------
def test_score_and_result():
    got = {m.match_id: m for m in fotmob.season_matches_from(parsed(SEASON), "epl")}
    m = got["M1"]
    assert m.home_goals == 2 and m.away_goals == 1
    assert m.finished is True and m.result == "H"

    draw = fotmob.season_matches_from(
        parsed([raw_match("MD", ARS, CHE, "2026-08-01T14:00:00Z", "1 - 1")]),
        "epl")[0]
    assert draw.result == "D"
    away = fotmob.season_matches_from(
        parsed([raw_match("MA", ARS, CHE, "2026-08-01T14:00:00Z", "0 - 2")]),
        "epl")[0]
    assert away.result == "A"


def test_unfinished_match_has_no_result():
    m = fotmob.season_matches_from(parsed([FUTURE]), "epl")[0]
    assert m.finished is False
    assert m.home_goals is None and m.result is None


# --------------------------------------------------------------------------
# 7. 정렬 — 반복 실행해도 같아야 한다
# --------------------------------------------------------------------------
def test_chronological_sorting_is_stable():
    got = fotmob.season_matches_from(parsed(SEASON + [FUTURE]), "epl")
    got.sort(key=lambda x: x.sort_key)
    assert [m.match_id for m in got] == ["M1", "M2", "M3", "M9"]
    # 여러 번 정렬해도 순서가 흔들리지 않는다
    for _ in range(5):
        again = fotmob.season_matches_from(parsed(SEASON + [FUTURE]), "epl")
        again.sort(key=lambda x: x.sort_key)
        assert [m.match_id for m in again] == ["M1", "M2", "M3", "M9"]


def test_same_kickoff_breaks_tie_by_match_id():
    same = [raw_match("MB", ARS, CHE, "2026-08-10T14:00:00Z"),
            raw_match("MA", EVE, FUL, "2026-08-10T14:00:00Z")]
    got = sorted(fotmob.season_matches_from(parsed(same), "epl"),
                 key=lambda x: x.sort_key)
    assert [m.match_id for m in got] == ["MA", "MB"], "동시각은 match_id 순"


def test_missing_kickoff_sorts_last():
    mixed = SEASON + [raw_match("MZ", ARS, FUL, "언젠가")]
    got = sorted(fotmob.season_matches_from(parsed(mixed), "epl"),
                 key=lambda x: x.sort_key)
    assert got[-1].match_id == "MZ", "시점을 모르는 경기는 뒤로"


# --------------------------------------------------------------------------
# 8·9. 직렬화 / 캐시 왕복
# --------------------------------------------------------------------------
def test_report_serialization_roundtrip():
    r = Report(round_id="260048")
    r.season_matches = fotmob.season_matches_from(parsed(SEASON), "epl")
    d = r.to_dict()
    assert len(d["season_matches"]) == 3
    assert d["season_matches"][0]["home_fotmob_id"] in NAME
    # datetime 은 JSON 이 직렬화하지 못한다 — default 로 문자열화해 확인
    text = json.dumps(d, default=str, ensure_ascii=False)
    assert "2026-08-10" in text


def test_season_match_dataclass_roundtrip():
    m = fotmob.season_matches_from(parsed(SEASON), "epl")[0]
    back = SeasonMatch(**asdict(m))
    assert back.match_id == m.match_id
    assert back.home_fotmob_id == m.home_fotmob_id
    assert back.kickoff == m.kickoff


def test_league_cache_roundtrip_keeps_team_ids():
    """리그 캐시(_freeze/_revive)가 경기 목록의 숫자 ID 를 잃지 않는가."""
    result = {"matches": parsed(SEASON), "teams": {}}
    revived = fotmob._revive(json.loads(json.dumps(fotmob._freeze(result))))
    got = fotmob.season_matches_from(revived["matches"], "epl")
    assert len(got) == 3
    assert all(m.home_fotmob_id is not None for m in got)
    assert fotmob._CACHE_VERSION >= 8
    assert fotmob._revive({"_v": 7, "teams": {}, "matches": []}) is None


# --------------------------------------------------------------------------
# 10·11·12. as_of cutoff · 미래 경기 제외 · 동시각 처리
# --------------------------------------------------------------------------
def _season():
    return fotmob.season_matches_from(parsed(SEASON + [FUTURE]), "epl")


def test_as_of_cutoff_excludes_future():
    got = matches_before(_season(), datetime(2026, 8, 25, tzinfo=UTC))
    assert [m.match_id for m in got] == ["M1", "M2"]


def test_unfinished_matches_excluded_by_default():
    """예정 경기는 과거처럼 쓰지 않는다."""
    late = datetime(2026, 12, 31, tzinfo=UTC)
    assert [m.match_id for m in matches_before(_season(), late)] == \
        ["M1", "M2", "M3"]
    with_future = matches_before(_season(), late, finished_only=False)
    assert "M9" in [m.match_id for m in with_future]


def test_same_timestamp_is_excluded():
    """같은 시각에 시작한 경기는 서로를 쓸 수 없다 (엄격한 <)."""
    kickoff = datetime(2026, 8, 20, 18, 0, tzinfo=UTC)     # M2 의 킥오프
    got = matches_before(_season(), kickoff)
    assert [m.match_id for m in got] == ["M1"], "동시각 경기를 포함했다"


def test_as_of_none_returns_empty():
    assert matches_before(_season(), None) == []


def test_match_without_kickoff_never_included():
    season = fotmob.season_matches_from(
        parsed(SEASON + [raw_match("MZ", ARS, FUL, "언젠가")]), "epl")
    got = matches_before(season, datetime(2026, 12, 31, tzinfo=UTC))
    assert "MZ" not in [m.match_id for m in got], "시점을 모르면 제외"


def test_naive_and_aware_mix_does_not_crash():
    """섞여 있으면 비교하지 않고 제외한다 — 시간대를 지어내지 않는다."""
    season = _season()
    season.append(SeasonMatch(match_id="MN", kickoff=datetime(2026, 8, 1),
                              kickoff_aware=False, finished=True))
    got = matches_before(season, datetime(2026, 8, 25, tzinfo=UTC))
    assert [m.match_id for m in got] == ["M1", "M2"]


# --------------------------------------------------------------------------
# 14. 미래 경기 누수 — Phase 2-F 의 기반 테스트
# --------------------------------------------------------------------------
def test_future_match_does_not_change_past_view():
    """시즌 목록 뒤에 미래 경기를 덧붙여도 과거 조회 결과가 바뀌면 FAIL.

    M1(8/10) · M2(8/20) · Target(8/29) 에 M_future(9/10) 를 추가한다.
    `matches_before(8/29)` 결과가 추가 전과 **완전히 동일**해야 한다.
    """
    as_of = datetime(2026, 8, 29, tzinfo=UTC)
    before = matches_before(fotmob.season_matches_from(parsed(SEASON), "epl"),
                            as_of)
    after = matches_before(fotmob.season_matches_from(parsed(SEASON + [FUTURE]),
                                                      "epl"), as_of)
    assert [m.match_id for m in before] == [m.match_id for m in after]
    assert [(m.home_goals, m.away_goals) for m in before] == \
           [(m.home_goals, m.away_goals) for m in after]
    assert [m.match_id for m in after] == ["M1", "M2"]

    # 미래 경기를 여러 개 붙여도 마찬가지
    more = [FUTURE,
            raw_match("MF2", CHE, ARS, "2026-10-01T14:00:00Z"),
            raw_match("MF3", EVE, ARS, "2026-11-01T14:00:00Z")]
    lots = matches_before(
        fotmob.season_matches_from(parsed(SEASON + more), "epl"), as_of)
    assert [m.match_id for m in lots] == ["M1", "M2"]


def test_report_helper_matches_module_function():
    r = Report()
    r.season_matches = _season()
    as_of = datetime(2026, 8, 25, tzinfo=UTC)
    assert [m.match_id for m in r.matches_before(as_of)] == \
           [m.match_id for m in matches_before(r.season_matches, as_of)]


# --------------------------------------------------------------------------
# 13. 기존 Report 필드 regression
# --------------------------------------------------------------------------
def test_existing_report_fields_unchanged():
    r = Report(round_id="260048", generated_at="2026-08-29 12:00")
    r.warnings.append("w")
    r.source_status["배당률"] = "ok"
    d = r.to_dict()
    for k in ("round_id", "generated_at", "matches", "warnings",
              "source_status", "verdict"):
        assert k in d, f"{k} 가 사라졌다"
    assert d["round_id"] == "260048" and d["warnings"] == ["w"]
    assert d["source_status"] == {"배당률": "ok"}


def test_parse_matches_keeps_existing_keys():
    """기존 소비자(_recent_finished·build_h2h)가 쓰는 키가 그대로 있는가."""
    m = parsed(SEASON)[0]
    for k in ("id", "date", "utc", "home", "away",
              "home_goals", "away_goals", "finished"):
        assert k in m, f"{k} 가 사라졌다"
    assert m["home_id"] is not None and m["away_id"] is not None


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
