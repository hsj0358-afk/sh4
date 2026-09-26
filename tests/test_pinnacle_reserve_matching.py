"""피나클 2군·리저브 오매칭 회귀 테스트.

Phase 0-B GitHub Actions 실측(260054)에서 10번 `AT마드 vs 레알마드` 가
`Spain - Segunda Federacion` 의 2군 경기 배당(2.26 / 3.48 / 2.76)을 받았다.
라리가 더비는 이미 끝나 리그 피드에 없었고, 2차 탐색(같은 나라의 다른
대회)이 2군 팀명을 1군으로 읽었다.

    피나클 참가팀명 "Atletico Madrid B"
      → normalize_name → "atleticomadridb"
      → 정확일치 없음 → _fuzzy_candidate 의 **부분일치**
        ("atleticomadrid" ⊂ "atleticomadridb") → "Atletico Madrid"
      → _find_matchup 이 1군 경기로 판정 → 배당 연결

고친 뒤의 규칙: **2차 탐색은 참가팀명을 정확일치로만 해석한다**
(`resolve(strict=True)`, §1-29 와 같은 장치). 후보가 둘 이상이면 고르지
않는다. 1차(리그 피드) 동작은 그대로다.

네트워크를 쓰지 않는다. 가격은 피나클 API 와 같은 **아메리칸 배당**이다.

    python tests/test_pinnacle_reserve_matching.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto.models import Match, TeamRef                        # noqa: E402
from toto.normalize import TeamResolver                       # noqa: E402
from toto.settings import load_settings                       # noqa: E402
from toto.sources import pinnacle                             # noqa: E402

# 260054 10번 — 이 저장소의 실측 회차에 있는 실제 경기다.
HOME, AWAY = "Atletico Madrid", "Real Madrid"
# 실측에서 붙었던 배당 (소수 2.26 / 3.48 / 2.76 ↔ 아메리칸 +126 / +248 / +176)
WRONG_PRICES = (126, 248, 176)
RESERVE_HOME, RESERVE_AWAY = "Atletico Madrid B", "Real Madrid Castilla"

SEGUNDA = {"id": 900001, "name": "Spain - Segunda Federacion"}
COPA = {"id": 900002, "name": "Spain - Copa del Rey"}


def _matchup(mid: int, home: str, away: str, start="2026-09-20T14:15:00Z"):
    return {"id": mid, "type": "matchup", "parentId": None, "startTime": start,
            "participants": [{"alignment": "home", "name": home},
                             {"alignment": "away", "name": away}]}


def _moneyline(mid: int, prices=WRONG_PRICES):
    h, d, a = prices
    return {"matchupId": mid, "type": "moneyline", "period": 0,
            "prices": [{"designation": "home", "price": h},
                       {"designation": "draw", "price": d},
                       {"designation": "away", "price": a}]}


def _match(no=10, home=HOME, away=AWAY, league="laliga"):
    return Match(no=no, league=league,
                 home=TeamRef(name_ko="AT마드", canonical=home, display="AT마드"),
                 away=TeamRef(name_ko="레알마드", canonical=away, display="레알마드"))


class _FakeClient:
    """`_search_country_wide` 가 쓰는 두 메서드만 흉내낸다 (네트워크 없음)."""

    def __init__(self, feeds: dict):
        self.feeds = feeds                   # league id → (matchups, markets)

    def _all_leagues(self):
        return [{"id": lid, "name": name} for lid, name in
                ((SEGUNDA["id"], SEGUNDA["name"]), (COPA["id"], COPA["name"]))
                if lid in self.feeds]

    def payload_by_id(self, lid):
        return self.feeds.get(lid, ([], []))


def _reserve_feed():
    return {SEGUNDA["id"]: ([_matchup(1, RESERVE_HOME, RESERVE_AWAY)],
                            [_moneyline(1)])}


# --------------------------------------------------------------------------
# 재현 — 고치기 전 경로가 실제로 2군을 1군으로 읽는다는 것을 고정한다
# --------------------------------------------------------------------------
def test_r1_resolver_substring_maps_reserves_to_first_team():
    """원인 단계: 비-strict 해석의 부분일치가 2군 표지를 흘린다."""
    r = TeamResolver()
    assert r.resolve(RESERVE_HOME, learn=False, quiet=True) == HOME
    assert r.resolve(RESERVE_AWAY, learn=False, quiet=True) == AWAY


def test_r2_non_strict_find_matchup_would_pick_the_reserve_fixture():
    """1차(리그 피드)가 쓰는 비-strict 경로는 그대로다 — 대조군."""
    mu = pinnacle._find_matchup([_matchup(1, RESERVE_HOME, RESERVE_AWAY)],
                                TeamResolver(), HOME, AWAY)
    assert mu is not None and mu["id"] == 1


# --------------------------------------------------------------------------
# Test 1 — 2군 → 1군 오매칭 차단 (260054 재현)
# --------------------------------------------------------------------------
def test_1_country_wide_search_does_not_attach_reserve_odds():
    match = _match()
    filled = pinnacle._search_country_wide(
        _FakeClient(_reserve_feed()), [match], load_settings(),
        TeamResolver(), "now")
    assert filled == 0
    assert not match.odds.available, match.odds
    assert match.odds.home is None


def test_1b_the_wrong_2_26_price_is_never_attached():
    match = _match()
    pinnacle._search_country_wide(_FakeClient(_reserve_feed()), [match],
                                  load_settings(), TeamResolver(), "now")
    assert match.odds.home != pinnacle.american_to_decimal(126)


# --------------------------------------------------------------------------
# Test 2 — 정상 1군 매칭 유지
# --------------------------------------------------------------------------
def test_2_first_team_fixture_in_league_feed_still_matches():
    """1차 경로(리그 피드) — 한 줄도 바뀌지 않았다."""
    match = _match()
    ok = pinnacle._apply_odds(match, [_matchup(7, HOME, AWAY)],
                              [_moneyline(7, (120, 240, 200))],
                              TeamResolver(), "now")
    assert ok and match.odds.available
    assert match.odds.home == pinnacle.american_to_decimal(120)


def test_2b_first_team_fixture_in_other_competition_still_matches():
    """2차 경로도 정확한 1군 이름이면 그대로 붙인다 (컵대회 경로 유지)."""
    match = _match()
    feeds = {COPA["id"]: ([_matchup(8, HOME, AWAY)],
                          [_moneyline(8, (130, 250, 190))])}
    filled = pinnacle._search_country_wide(_FakeClient(feeds), [match],
                                           load_settings(), TeamResolver(),
                                           "now")
    assert filled == 1 and match.odds.available
    assert match.odds.home == pinnacle.american_to_decimal(130)


def test_2c_first_team_found_even_when_reserve_feed_comes_first():
    """2군 대회가 먼저 훑여도 뒤의 정확한 1군 경기를 찾는다."""
    match = _match()
    feeds = dict(_reserve_feed())
    feeds[COPA["id"]] = ([_matchup(8, HOME, AWAY)],
                         [_moneyline(8, (130, 250, 190))])
    pinnacle._search_country_wide(_FakeClient(feeds), [match],
                                  load_settings(), TeamResolver(), "now")
    assert match.odds.home == pinnacle.american_to_decimal(130)


# --------------------------------------------------------------------------
# Test 3 · 4 — B 접미사 · Castilla 가 1군과 같은 팀이 되지 않는다
# --------------------------------------------------------------------------
def test_3_b_suffix_is_not_the_first_team_under_strict():
    r = TeamResolver()
    assert r.resolve(HOME, learn=False, quiet=True, strict=True) == HOME
    assert r.resolve(RESERVE_HOME, learn=False, quiet=True, strict=True) is None


def test_4_castilla_is_not_the_first_team_under_strict():
    r = TeamResolver()
    assert r.resolve(AWAY, learn=False, quiet=True, strict=True) == AWAY
    assert r.resolve(RESERVE_AWAY, learn=False, quiet=True, strict=True) is None


def test_4b_half_reserve_pair_is_not_matched():
    """한쪽만 1군이어도 경기로 인정하지 않는다."""
    r = TeamResolver()
    for home, away in ((HOME, RESERVE_AWAY), (RESERVE_HOME, AWAY)):
        mu = pinnacle._find_matchup([_matchup(1, home, away)], r, HOME, AWAY,
                                    strict=True)
        assert mu is None, (home, away)


# --------------------------------------------------------------------------
# Test 5 — 불확실하면 붙이지 않는다
# --------------------------------------------------------------------------
def test_5_two_candidates_in_strict_mode_are_not_guessed():
    matchups = [_matchup(21, HOME, AWAY, "2026-09-20T14:15:00Z"),
                _matchup(22, HOME, AWAY, "2027-01-15T20:00:00Z")]
    assert pinnacle._find_matchup(matchups, TeamResolver(), HOME, AWAY,
                                  strict=True) is None


def test_5b_ambiguous_feed_leaves_odds_empty():
    match = _match()
    feeds = {COPA["id"]: ([_matchup(21, HOME, AWAY), _matchup(22, HOME, AWAY)],
                          [_moneyline(21), _moneyline(22)])}
    filled = pinnacle._search_country_wide(_FakeClient(feeds), [match],
                                           load_settings(), TeamResolver(),
                                           "now")
    assert filled == 0 and not match.odds.available


def test_5c_duplicate_id_is_one_candidate_not_two():
    """같은 matchup 이 두 번 실려도 후보는 하나다 — 이름이 아니라 id 로 센다."""
    matchups = [_matchup(21, HOME, AWAY), _matchup(21, HOME, AWAY)]
    mu = pinnacle._find_matchup(matchups, TeamResolver(), HOME, AWAY,
                                strict=True)
    assert mu is not None and mu["id"] == 21


# --------------------------------------------------------------------------
# 진단 — 막았다는 사실이 로그에 남는다 (§1-6-1)
# --------------------------------------------------------------------------
def test_6_blocked_guesses_are_reported(caplog=None):
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger(pinnacle.__name__)
    logger.addHandler(handler)
    try:
        pinnacle._search_country_wide(_FakeClient(_reserve_feed()), [_match()],
                                      load_settings(), TeamResolver(), "now")
    finally:
        logger.removeHandler(handler)
    text = " ".join(r.getMessage() for r in records)
    assert "Atletico Madrid B" in text and "Real Madrid Castilla" in text, text


# --------------------------------------------------------------------------
# 전체 경로 — fetch_odds 가 1차 → 2차를 타도 2군 배당이 붙지 않는다
# --------------------------------------------------------------------------
def test_7_fetch_odds_end_to_end():
    laliga_feed = ([_matchup(5, "Villarreal", "Levante")],
                   [_moneyline(5, (-150, 300, 400))])

    class Client(_FakeClient):
        ok = True

        def __init__(self, settings, cache=None):
            super().__init__(_reserve_feed())

        def league_payload(self, league_key):
            return laliga_feed if league_key == "laliga" else ([], [])

    derby = _match(no=10)
    other = Match(no=13, league="laliga",
                  home=TeamRef(name_ko="비야레알", canonical="Villarreal",
                               display="비야레알"),
                  away=TeamRef(name_ko="레반테", canonical="Levante",
                               display="레반테"))
    original = pinnacle.PinnacleClient
    pinnacle.PinnacleClient = Client
    try:
        status = pinnacle.fetch_odds([derby, other], load_settings(),
                                     TeamResolver())
    finally:
        pinnacle.PinnacleClient = original
    assert other.odds.available                       # 1차: 정상 1군 매칭
    assert not derby.odds.available                   # 2차: 2군 배당 차단
    assert status == "ok (1/2경기)", status


def test_8_first_pass_signature_default_is_unchanged():
    """1차 경로의 기본값이 비-strict 그대로다 — 기존 매칭이 바뀌지 않는다."""
    import inspect
    for fn in (pinnacle._find_matchup, pinnacle._apply_odds):
        assert inspect.signature(fn).parameters["strict"].default is False


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
