"""리그·팀 매칭 회귀 테스트 (Phase 1-A).

실측에서 드러난 두 가지 오선택을 재현하고, 고친 뒤에는 재현되지 않음을
확인한다. 네트워크를 쓰지 않으며 픽스처만으로 돈다.

  · FotMob  — 이름이 같은 리그가 여러 나라에 있어 엉뚱한 ID 가 뽑혔다
  · Pinnacle — "England - Premier League" 가 "... 2 U21" 에 부분일치했다

pytest 없이도 돈다:  python tests/test_league_matching.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto.normalize import TeamResolver                       # noqa: E402
from toto.settings import load_settings                       # noqa: E402
from toto.sources import fotmob                               # noqa: E402
from toto.sources.pinnacle import PinnacleClient, _norm_league  # noqa: E402

# 실제 FotMob ID 를 단언하지 않도록 합성 ID 를 쓴다. 검증하는 것은
# '어느 후보를 고르는가' 이지 특정 숫자가 아니다.
_ENGLAND, _RUSSIA, _EGYPT = 9001, 9002, 9003

# allLeagues 를 흉내낸다. 'Premier League' 라는 **같은 이름**이 세 나라에 있다.
ALL_LEAGUES = {"countries": [
    {"name": "England", "leagues": [{"id": _ENGLAND, "name": "Premier League"}]},
    {"name": "Russia", "leagues": [{"id": _RUSSIA, "name": "Premier League"}]},
    {"name": "Egypt", "leagues": [{"id": _EGYPT, "name": "Premier League"}]},
]}

# 실측 재현: 'Premier League' 동명 리그가 16개였고, 확인 상한(당시 4개) 안에
# 잉글랜드가 들어오지 않아 판별에 실패했다. 국가 힌트가 없으면 같은 일이 난다.
MANY = {"countries": (
    [{"name": f"Country{i}", "leagues": [{"id": 8000 + i, "name": "Premier League"}]}
     for i in range(15)]
    + [{"name": "England", "leagues": [{"id": _ENGLAND, "name": "Premier League"}]}]
)}

# 국가 정보가 없는 평평한 구조. 국가로 좁힐 수 없으므로 순위표 확인 단계까지
# 내려간다 — '가릴 수단이 없으면 임의로 고르지 않는다' 를 검사할 때 쓴다.
FLAT = {"leagues": [{"id": _ENGLAND, "name": "Premier League"},
                    {"id": _RUSSIA, "name": "Premier League"},
                    {"id": _EGYPT, "name": "Premier League"}]}


def _standings(names: list[str]) -> dict:
    """확인된 구조(table[].data.table.all)로 순위표를 만든다."""
    rows = [{"name": n, "id": i, "played": 3, "pts": 5, "idx": i + 1}
            for i, n in enumerate(names)]
    return {"table": [{"data": {"table": {"all": rows}}}]}


# 잉글랜드만 우리가 EPL 소속으로 아는 팀을 담고 있다.
STANDINGS = {
    _ENGLAND: _standings(["Arsenal", "Chelsea", "Liverpool", "Everton"]),
    _RUSSIA: _standings(["Zenit", "Spartak Moscow", "CSKA Moscow"]),
    _EGYPT: _standings(["Al Ahly", "Zamalek", "Pyramids"]),
}


class FakeBrowser:
    """요청 수를 세는 가짜 FotMob 세션."""

    base = "https://www.fotmob.com"
    available = True

    def __init__(self, standings=None):
        self.standings = STANDINGS if standings is None else standings
        self.calls: list[str] = []

    def abs_url(self, path):
        return self.base + path

    def get_json(self, url):
        self.calls.append(url)
        if "allLeagues" in url:
            return ALL_LEAGUES
        for lid, payload in self.standings.items():
            if f"id={lid}" in url:
                return payload
        return None


def _settings_without_epl_id():
    s = load_settings()
    s.leagues = {k: dict(v) for k, v in s.leagues.items()}
    s.leagues["epl"].pop("fotmob_id", None)      # 탐색 경로를 강제
    return s


# --------------------------------------------------------------------------
# 1. FotMob — 동명 리그가 여럿일 때 엉뚱한 리그를 고르지 않는다
# --------------------------------------------------------------------------
def test_fotmob_picks_right_league_among_same_names():
    s, r = _settings_without_epl_id(), TeamResolver()
    browser = FakeBrowser()
    got = fotmob.resolve_league_id(browser, s, "epl", cache=None, resolver=r)
    assert got == _ENGLAND, f"잉글랜드 대신 {got} 를 골랐다"
    assert got not in (_RUSSIA, _EGYPT)


def test_fotmob_lists_all_candidates_not_just_first():
    cands = fotmob._name_candidates(ALL_LEAGUES, "premier league")
    ids = {c[1] for c in cands}
    assert ids == {_ENGLAND, _RUSSIA, _EGYPT}, ids
    # 셋 다 이름 완전일치이므로 점수가 같아야 한다 (임의 우열이 없어야 함)
    assert len({c[0] for c in cands}) == 1


def test_fotmob_refuses_when_it_cannot_tell():
    """가릴 수단이 없거나 아는 팀이 없으면 임의로 고르지 않고 실패한다.

    국가 정보가 없는 응답(FLAT)을 써서 국가 단계로는 좁히지 못하게 한다.
    """
    s, r = _settings_without_epl_id(), TeamResolver()

    class FlatBrowser(FakeBrowser):
        def get_json(self, url):
            self.calls.append(url)
            if "allLeagues" in url:
                return FLAT
            for lid, payload in self.standings.items():
                if f"id={lid}" in url:
                    return payload
            return None

    # (a) resolver 없이 호출 → 판별 불가 → None
    assert fotmob.resolve_league_id(FlatBrowser(), s, "epl", resolver=None) is None

    # (b) 어느 후보에도 우리가 아는 EPL 팀이 없음 → None (엉뚱한 리그 채택 금지)
    blind = {lid: _standings(["Unknown A", "Unknown B"]) for lid in STANDINGS}
    got = fotmob.resolve_league_id(FlatBrowser(blind), s, "epl", resolver=r)
    assert got is None, f"가리지 못했는데 {got} 를 골랐다"

    # (c) 국가로는 못 가려도 순위표로는 가려낸다
    got = fotmob.resolve_league_id(FlatBrowser(), s, "epl", resolver=r)
    assert got == _ENGLAND, f"순위표로 가렸어야 하는데 {got}"


def test_fotmob_country_narrows_many_same_name_leagues():
    """동명 리그가 16개여도 국가 힌트로 좁혀 잉글랜드를 고른다 (실측 재현)."""
    s, r = _settings_without_epl_id(), TeamResolver()
    assert s.leagues["epl"].get("country"), "설정에 country 가 있어야 한다"

    # 잉글랜드 외에는 순위표를 받을 수 없게 둔다. 국가로 좁히지 못하면
    # 확인 상한에 걸려 실패했을 상황이다.
    browser = FakeBrowser({_ENGLAND: STANDINGS[_ENGLAND]})
    browser.get_json_all = ALL_LEAGUES

    class ManyBrowser(FakeBrowser):
        def get_json(self, url):
            self.calls.append(url)
            if "allLeagues" in url:
                return MANY
            return STANDINGS.get(_ENGLAND) if f"id={_ENGLAND}" in url else None

    mb = ManyBrowser()
    assert fotmob.resolve_league_id(mb, s, "epl", resolver=r) == _ENGLAND
    # 국가로 좁혔으니 순위표는 한 번만 받는다 (16번 받지 않는다)
    standings_calls = [c for c in mb.calls if "allLeagues" not in c]
    assert len(standings_calls) <= 2, f"순위표를 {len(standings_calls)}번 받았다"


def test_country_hints_are_structure_agnostic():
    """allLeagues 경로를 단정하지 않고 상위 dict 의 문자열을 힌트로 쓴다."""
    hints = fotmob._country_hints(ALL_LEAGUES)
    assert "england" in hints[_ENGLAND]
    assert "russia" in hints[_RUSSIA]
    assert "england" not in hints[_EGYPT]


def test_fotmob_config_id_wins_and_skips_network():
    """설정에 ID 가 있으면 그것을 쓰고 allLeagues 를 부르지 않는다."""
    s, browser = load_settings(), FakeBrowser()
    got = fotmob.resolve_league_id(browser, s, "kleague1", resolver=TeamResolver())
    assert got == s.leagues["kleague1"]["fotmob_id"]
    assert browser.calls == [], "설정값이 있는데도 네트워크를 탔다"


# --------------------------------------------------------------------------
# 2. Pinnacle — 비슷한 이름(U21 등)을 잘못 고르지 않는다
# --------------------------------------------------------------------------
def _client(payload):
    client = PinnacleClient(load_settings(), cache=None)
    client._leagues_payload = payload       # 네트워크 차단
    return client


def test_pinnacle_ignores_u21_prefix_match():
    # 실측 순서 재현: U21 이 목록에서 **먼저** 나온다
    payload = [
        {"id": 197646, "name": "England - Premier League 2 U21"},
        {"id": 1980, "name": "England - Premier League"},
    ]
    assert _client(payload).league_id("epl") == 1980


def test_pinnacle_fails_rather_than_pick_wrong_league():
    """정확히 일치하는 리그가 없으면 비슷한 것을 고르지 않고 실패한다."""
    payload = [
        {"id": 197646, "name": "England - Premier League 2 U21"},
        {"id": 197647, "name": "England - Premier League Cup"},
    ]
    assert _client(payload).league_id("epl") is None


def test_pinnacle_alias_allows_explicit_override():
    """이름이 달라졌을 때 설정 별칭으로 명시 지정할 수 있다."""
    s = load_settings()
    s.leagues = {k: dict(v) for k, v in s.leagues.items()}
    s.leagues["epl"]["pinnacle_aliases"] = ["England - Premier League (2026/27)"]
    client = PinnacleClient(s, cache=None)
    client._leagues_payload = [
        {"id": 197646, "name": "England - Premier League 2 U21"},
        {"id": 4242, "name": "England - Premier League (2026/27)"},
    ]
    assert client.league_id("epl") == 4242


def test_pinnacle_existing_leagues_still_match():
    """기존에 잘 되던 리그가 완전일치 규칙에서도 그대로 잡힌다."""
    payload = [
        {"id": 207551, "name": "Korea Republic - K League 1"},
        {"id": 207552, "name": "Korea Republic - K League 2"},
        {"id": 2436, "name": "Italy - Serie A"},
        {"id": 1234, "name": "Japan - J League"},
    ]
    client = _client(payload)
    assert client.league_id("kleague1") == 207551
    assert client.league_id("kleague2") == 207552
    assert client.league_id("seriea") == 2436
    assert client.league_id("jleague") == 1234


def test_norm_league_distinguishes_prefix():
    a = _norm_league("England - Premier League")
    b = _norm_league("England - Premier League 2 U21")
    assert a != b and b.startswith(a)      # 접두사이지만 같지는 않다


# --------------------------------------------------------------------------
# 3. 유럽 팀 별칭 → 정규명
# --------------------------------------------------------------------------
EUROPEAN = {
    "입스위치": "Ipswich",
    "리즈U": "Leeds",
    "브렌트퍼": "Brentford",
    "코모1907": "Como",
    "A빌라": "Aston Villa",
    "맨체스C": "Manchester City",
    "프로시노": "Frosinone",
    "베네치아": "Venezia",
    "US레체": "Lecce",
    # 260048 회차에서 새로 드러난 것들
    "코번트리": "Coventry City",
    "헐시티": "Hull City",
    "AC몬차": "Monza",
    "맨체스U": "Manchester United",
}


def test_european_betman_abbreviations():
    r = TeamResolver()
    for ko, want in EUROPEAN.items():
        got = r.resolve(ko, learn=False, quiet=True)
        assert got == want, f"{ko} → {got} (기대 {want})"


def test_new_aliases_do_not_hijack_other_teams():
    """새 별칭이 기존 팀을 가로채지 않는다."""
    r = TeamResolver()
    for ko, want in (("아스톤빌라", "Aston Villa"), ("맨체스터시티", "Manchester City"),
                     ("맨시티", "Manchester City"), ("레체", "Lecce"),
                     ("코모", "Como"), ("브렌트포드", "Brentford"),
                     ("비야레알", "Villarreal"), ("세비야", "Sevilla"),
                     ("맨유", "Manchester United"),
                     ("맨체스터유나이티드", "Manchester United")):
        got = r.resolve(ko, learn=False, quiet=True)
        assert got == want, f"{ko} → {got} (기대 {want})"


# --------------------------------------------------------------------------
# 4. K/J리그 회귀 — 기존 매핑이 그대로 살아 있는가
# --------------------------------------------------------------------------
DOMESTIC = {
    "서울": "FC Seoul", "울산": "Ulsan HD", "전북현대": "Jeonbuk Hyundai Motors",
    "인천유나": "Incheon United", "부천FC": "Bucheon FC 1995",
    "대구FC": "Daegu FC", "수원FC": "Suwon FC", "김해FC": "Gimhae FC",
    "포항": "Pohang Steelers", "제주SK": "Jeju SK",
}


def test_domestic_mapping_regression():
    r = TeamResolver()
    for ko, want in DOMESTIC.items():
        got = r.resolve(ko, learn=False, quiet=True)
        assert got == want, f"{ko} → {got} (기대 {want})"


def test_domestic_league_assignment_regression():
    """2026 승강 반영이 유지되는가 (대구·수원FC ↔ 인천·부천)."""
    r = TeamResolver()
    for team, league in (("Incheon United", "kleague1"), ("Bucheon FC 1995", "kleague1"),
                         ("Daegu FC", "kleague2"), ("Suwon FC", "kleague2"),
                         ("FC Seoul", "kleague1"), ("Gimhae FC", "kleague2")):
        assert r.league_of(team) == league, f"{team} → {r.league_of(team)}"


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
