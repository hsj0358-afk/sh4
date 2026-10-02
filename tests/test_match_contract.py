"""경기 파싱·대회 식별·수집 준비 상태 계약 (Phase 6-C).

  A. 경기 행 계약 — 번호 셀 + vs 셀이 있는 행만 경기다. 번호 1~14 가 정확히
     한 번씩 있어야 회차로 통과한다. 13·15·번호 겹침은 실패이고, 앞 14개만
     잘라 쓰지 않는다. UI 행(전체조합수·전체선택…)은 가짜 경기가 되지 않는다.

픽스처는 PC 실측(260054·260055 betman cells)의 **구조**를 옮겨 적었다.
원본 JSON 은 저장소에 넣지 않았다 — 이 세션에 없고, 경기 행의 모양은
명세 §3 에 적힌 그대로다. UI 행의 실제 셀 내용은 확인하지 못했으므로,
식별 규칙은 UI 행의 내용에 기대지 않는다 (번호 셀이 없으면 경기가 아니다).

pytest 없이도 돈다:  python tests/test_match_contract.py
"""
from __future__ import annotations

import ast
import inspect
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import competition                                     # noqa: E402
from toto.sources import betman                                  # noqa: E402

EXPECTED = 14

# 260054 의 경기 행 모양 (§3-1). 팀명은 한 셀 안에 `홈\t\nvs\n원정`.
DOMESTIC = [("브라이턴", "아스널"), ("첼시", "리버풀"), ("에버턴", "토트넘"),
            ("풀럼", "번리"), ("본머스", "울버햄프"), ("리즈U", "선덜랜드"),
            ("맨체스C", "노팅엄F"), ("브렌트퍼", "A빌라"), ("뉴캐슬", "웨스트햄"),
            ("레알마드", "AT마드"), ("바르셀로", "세비야"), ("비야레알", "발렌시아"),
            ("헤타페", "셀타비고"), ("오사수나", "마요르카")]

# 260055 국가대표 회차에서 실측으로 확인된 세 경기 (§3-3) + 채움.
NATIONAL = [("이탈리아", "벨기에"), ("튀르키예", "프랑스"), ("잉글랜드", "스페인"),
            ("독일", "네덜란드"), ("포르투갈", "크로아티아"), ("일본", "호주"),
            ("덴마크", "스위스"), ("노르웨이", "오스트리아"), ("폴란드", "체코"),
            ("스코틀랜드", "웨일스"), ("세르비아", "헝가리"), ("그리스", "루마니아"),
            ("우크라이나", "슬로바키아"), ("스웨덴", "아일랜드")]


def real_row(no: int, home: str, away: str,
             when: str = "26.09.19 (토) 23:00") -> dict:
    """실측 경기 행의 셀 구성. 대회 칸이 **없다**."""
    return {"cells": [f"{no}경기", f"{when}\n경기장", f"{home}\t\nvs\n{away}",
                      "투표율\n41.2%\n27.5%\n31.3%", "",
                      f"{no}경기 {home} : {away} 상세정보 열기"]}


# 경기 목록 뒤에 붙는 UI 행. 실제 셀 내용은 확인하지 못했다 — 예전 대체
# 경로('팀처럼 보이는 셀 2개')가 가짜 경기로 만들던 모양을 일부러 넣었다.
UI_ROWS = [{"cells": ["전체조합수", "1", "전체선택", "최소 1경기 이상 선택"]},
           {"cells": ["전체선택", "선택해제", "조합 보기"]},
           {"cells": ["최소", "구매금액", "1,000원"]},
           {"cells": []}]

HEADER = {"cells": ["경기", "개최시간", "홈팀 vs 원정팀", "투표율", "상세"]}


def rows_for(pairs, start: int = 1, ui: bool = True) -> list[dict]:
    rows = [HEADER] + [real_row(i, h, a)
                       for i, (h, a) in enumerate(pairs, start=start)]
    return rows + (UI_ROWS if ui else [])


# ==========================================================================
# A. 경기 행 계약
# ==========================================================================
def test_a1_fourteen_real_rows_pass():
    got = betman.match_list(rows_for(DOMESTIC), EXPECTED, "260054")
    assert [m.no for m in got] == list(range(1, 15))
    assert [(m.home.name_ko, m.away.name_ko) for m in got] == DOMESTIC
    assert all(m.kickoff_kst == "2026-09-19 23:00" for m in got)


def test_a2_ui_rows_are_not_matches():
    parsed = betman.read_match_rows(UI_ROWS + [HEADER])
    assert parsed.matches == [] and parsed.unreadable == []
    assert parsed.ignored == len(UI_ROWS) + 1
    full = betman.read_match_rows(rows_for(DOMESTIC))
    assert len(full.matches) == 14
    assert full.ignored == len(UI_ROWS) + 1


def test_a3_thirteen_fails():
    try:
        betman.match_list(rows_for(DOMESTIC[:13]), EXPECTED, "260054")
    except betman.MatchListError as exc:
        assert exc.round_id == "260054"
        assert any("없는 번호: 14번" in p for p in exc.problems), exc.problems
    else:
        raise AssertionError("13경기가 통과했다")


def test_a4_fifteen_fails_instead_of_truncating():
    pairs = DOMESTIC + [("레버쿠젠", "도르트문")]
    try:
        betman.match_list(rows_for(pairs), EXPECTED, "260054")
    except betman.MatchListError as exc:
        assert any("14경기를 넘는 번호: 15번" in p for p in exc.problems), \
            exc.problems
    else:
        raise AssertionError("15경기에서 앞 14개를 조용히 썼다")


def test_a5_missing_number_is_named():
    rows = rows_for(DOMESTIC)
    del rows[7]                                   # 7번 경기 행 (머리글이 0번)
    rows.append(real_row(15, "레버쿠젠", "도르트문"))
    probs = betman.round_problems(betman.read_match_rows(rows), EXPECTED)
    assert any("없는 번호: 7번" in p for p in probs), probs
    assert any("넘는 번호: 15번" in p for p in probs), probs


def test_a6_same_number_different_match_fails():
    rows = rows_for(DOMESTIC) + [real_row(3, "레버쿠젠", "도르트문")]
    probs = betman.round_problems(betman.read_match_rows(rows), EXPECTED)
    assert probs == ["같은 번호에 다른 경기가 있습니다: 3번"], probs


def test_a7_identical_rows_from_two_frames_count_once():
    """프레임 두 곳에 같은 표가 실리면 **내용까지 같은 행**만 하나로 센다."""
    rows = rows_for(DOMESTIC) + [real_row(i, h, a)
                                 for i, (h, a) in enumerate(DOMESTIC, start=1)]
    parsed = betman.read_match_rows(rows)
    assert parsed.repeated == 14
    assert betman.round_problems(parsed, EXPECTED) == []


def test_a8_match_row_without_vs_cell_fails_loudly():
    rows = rows_for(DOMESTIC)
    rows[5] = {"cells": ["5경기", "26.09.19 (토) 23:00", "투표율", "상세정보"]}
    probs = betman.round_problems(betman.read_match_rows(rows), EXPECTED)
    assert probs == ["번호는 있지만 팀명(vs 셀)을 읽지 못한 행: 5번"], probs


def test_a9_number_comes_from_the_row_not_the_order():
    rows = rows_for(DOMESTIC)
    body = rows[1:15]
    rows[1:15] = list(reversed(body))
    got = betman.match_list(rows, EXPECTED)
    assert [m.no for m in got] == list(range(1, 15))
    assert (got[0].home.name_ko, got[0].away.name_ko) == DOMESTIC[0]


def test_a10_no_rows_at_all():
    assert betman.round_problems(betman.read_match_rows([]), EXPECTED) == \
        ["경기 행을 하나도 찾지 못했습니다"]


def test_a11_parser_does_not_decide_the_competition():
    """파서는 대회를 정하지 않는다 — 국가명이 별칭에 걸려도 `league` 는 빈칸."""
    for m in betman.match_list(rows_for(NATIONAL), EXPECTED):
        assert m.league == "" and m.league_ko == "", (m.no, m.league)


def test_a12_parser_source_has_no_league_lookup_or_truncation():
    tree = ast.parse(inspect.getsource(betman))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in (
                "read_match_rows", "_parse_rows", "match_list", "fetch_matches",
                "round_problems", "_teams", "_match_no"):
            body = ast.unparse(node)
            assert "league_of" not in body, node.name
            assert "[:expected]" not in body, node.name


def test_a13_match_list_error_message_lists_every_problem():
    exc = betman.MatchListError("260055", ["없는 번호: 3번", "넘는 번호: 15번"])
    assert str(exc) == "없는 번호: 3번; 넘는 번호: 15번"


# ==========================================================================
# B. 대회 식별 — 파서와 분리 · 근거를 남긴다
# ==========================================================================
def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="toto_6c_"))


def _resolver():
    """실제 `data/teams.yaml` 은 읽되 학습·승강 파일은 임시 폴더다.

    PC 의 `data/teams.learned.yaml`·`teams.league.yaml` 을 읽지도 쓰지도
    않는다 — 그 파일은 보호 대상이고, 거기 든 학습 별칭에 결과가 흔들리면
    안 된다.
    """
    from toto.normalize import TeamResolver
    tmp = _tmp()
    return TeamResolver(learned_file=tmp / "teams.learned.yaml",
                        league_file=tmp / "teams.league.yaml")


def _settings():
    from toto.settings import load_settings
    return load_settings()


def _resolved(pairs):
    """파서 → 팀명 해석 → 대회 식별 (cli 의 순서 그대로)."""
    from toto import cli
    from toto.models import Report
    matches = betman.match_list(rows_for(pairs), EXPECTED)
    report = Report(round_id="T", matches=matches)
    cli._resolve_teams(matches, _resolver(), report, _settings())
    return matches, report


def test_b1_national_teams_are_not_domestic_leagues():
    """260055 실측 세 경기가 국내리그로 오인되지 않는다."""
    matches, report = _resolved(NATIONAL)
    by_title = {(m.home.name_ko, m.away.name_ko): m for m in matches}
    for pair, wrong in ((("이탈리아", "벨기에"), "seriea"),
                        (("튀르키예", "프랑스"), "ligue1"),
                        (("잉글랜드", "스페인"), "epl")):
        m = by_title[pair]
        assert m.league != wrong, (pair, m.league)
        assert m.league == "" and m.league_basis == competition.NONE, \
            (pair, m.league, m.league_basis)
        assert competition.state(m.league, _settings()) == competition.UNKNOWN
    assert all(m.league == "" for m in matches), \
        [(m.no, m.league) for m in matches]
    unknown = [w for w in report.warnings if "리그를 알 수 없어" in w]
    assert len(unknown) == 14, report.warnings


def test_b2_domestic_rows_still_resolve_by_team_league():
    matches, report = _resolved(DOMESTIC)
    leagues = [m.league for m in matches]
    assert leagues == ["epl"] * 9 + ["laliga"] * 5, leagues
    assert all(m.league_basis == competition.TEAM_LEAGUE for m in matches)
    assert all(m.league_ko for m in matches)
    assert not [w for w in report.warnings if "리그" in w], report.warnings


def test_b3_real_260052_names_keep_the_saved_competitions():
    """실물 저장본(EPL·라리가 14경기)의 팀명으로 행을 만들어 새 경로에
    태우면, 저장본에 적힌 대회가 그대로 나온다. 없으면 SKIP."""
    import realdata
    saved = realdata.load_artifact()
    pairs = [(m.home.name_ko, m.away.name_ko) for m in saved.matches]
    matches, _ = _resolved(pairs)
    assert [m.league for m in matches] == [m.league for m in saved.matches]
    assert {m.league for m in matches} <= {"epl", "laliga"}


def test_b4_matches_file_league_is_confirmed():
    from toto.normalize import TeamResolver  # noqa: F401
    path = Path(__file__).resolve().parent.parent / "examples" / "matches.yaml"
    matches = betman.load_matches_file(path, _settings())
    assert len(matches) == 14
    assert all(m.league_basis == competition.MATCHES_FILE for m in matches)
    assert all(competition.is_confirmed(m) for m in matches)
    before = [m.league for m in matches]
    from toto import cli
    from toto.models import Report
    cli._resolve_teams(matches, _resolver(), Report(matches=matches),
                       _settings())
    assert [m.league for m in matches] == before


def test_b5_matches_file_unregistered_league_is_identified_not_supported():
    tmp = _tmp()
    path = tmp / "m.yaml"
    path.write_text("matches:\n"
                    "  - {no: 1, league: 월드컵예선, home: 이탈리아, away: 벨기에}\n"
                    "  - {no: 2, league: 챔피언스리그, home: 아스널, away: 첼시}\n",
                    encoding="utf-8")
    from toto import cli
    from toto.models import Report
    matches = betman.load_matches_file(path, _settings())
    report = Report(matches=matches)
    cli._resolve_teams(matches, _resolver(), report, _settings())
    a, b = matches
    assert (a.league, a.league_basis) == ("월드컵예선", competition.MATCHES_FILE)
    assert competition.state(a.league, _settings()) == competition.UNREGISTERED
    assert (b.league, b.league_basis) == ("ucl", competition.MATCHES_FILE)
    assert competition.state(b.league, _settings()) == competition.UNSUPPORTED
    notes = [w for w in report.warnings if "지원하는 국내리그가 아닙니다" in w]
    assert len(notes) == 2, report.warnings


def test_b6_preset_league_without_basis_is_left_alone():
    """근거 기록 없이 대회가 들어온 경기(예전 호출부)는 예전처럼 그대로다."""
    from toto.models import Match, TeamRef
    m = Match(no=1, league="kleague1", home=TeamRef(canonical="Arsenal"))
    assert competition.resolve(m, _resolver(), _settings()) == ""
    assert m.league == "kleague1" and m.league_basis == ""


def test_b7_basis_is_not_saved_in_the_artifact():
    """저장 형식은 그대로다 — 근거 칸은 저장본에 싣지 않는다."""
    import json
    from toto import artifact
    from toto.models import Report
    matches = betman.match_list(rows_for(DOMESTIC), EXPECTED)
    for m in matches:
        m.league_basis = competition.TEAM_LEAGUE
    text = json.dumps(artifact.to_dict(Report(round_id="1", matches=matches)),
                      ensure_ascii=False)
    assert "league_basis" not in text
    back, why = artifact.load_path(_write(text))
    assert back is not None, why
    assert all(m.league_basis == competition.UNRECORDED for m in back.matches)


def _write(text: str) -> Path:
    path = _tmp() / "a.json"
    path.write_text(text, encoding="utf-8")
    return path


def test_b8_competition_module_does_not_read_row_text():
    """대회 식별이 문자열에서 대회를 찾지 않는다 — 행 전체 추정 금지."""
    calls = []
    for node in ast.walk(ast.parse(inspect.getsource(competition))):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "league_of"):
            calls.append(ast.unparse(node.func.value))
    # 팀 정규명 → 소속 리그(`TeamResolver.league_of`) 만 쓴다.
    assert calls and set(calls) == {"resolver"}, calls


# ==========================================================================
# C. FotMob 소속 정정이 확정된 대회를 덮지 않는다
# ==========================================================================
class _FakeBrowser:
    """`FotMobBrowser` 자리. 네트워크를 쓰지 않는다."""
    available = True

    def __init__(self, *a, **k) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a) -> bool:
        return False


def _enrich(matches, feeds: dict[str, list[str]]):
    """**실제 `fotmob.enrich()`** 를 태운다. 브라우저와 리그 읽기만 가짜다."""
    from toto.models import TeamStats
    from toto.sources import fotmob

    def feed(browser, st, key, res, cache=None):
        return {"teams": {t: {"stats": TeamStats(), "form": [], "fotmob_id": "",
                              "page_url": ""} for t in feeds.get(key, [])},
                "matches": []}

    real = fotmob.FotMobBrowser, fotmob.read_league
    fotmob.FotMobBrowser, fotmob.read_league = _FakeBrowser, feed
    try:
        fotmob.enrich(matches, _settings(), _resolver(), cache=None)
    finally:
        fotmob.FotMobBrowser, fotmob.read_league = real


def _m(no: int, league: str, basis: str, home: str = "Arsenal"):
    from toto.models import Match, TeamRef
    return Match(no=no, league=league, league_ko=league, league_basis=basis,
                 home=TeamRef(name_ko=home, canonical=home),
                 away=TeamRef(name_ko="첼시", canonical="Chelsea"))


def test_c1_confirmed_competition_survives_team_relabel():
    """아스널의 소속이 순위표로 정정돼도 사람이 적은 대회는 그대로다."""
    confirmed = _m(1, "kleague1", competition.MATCHES_FILE)
    inferred = _m(2, "epl", competition.TEAM_LEAGUE)
    unrecorded = _m(3, "epl", competition.UNRECORDED)
    # 라리가 경기가 있어야 라리가 피드를 받는다. 그 피드에 아스널이 있으면
    # 소속 정정(moved>0)이 일어난다.
    laliga = _m(4, "laliga", competition.TEAM_LEAGUE, home="Real Madrid")
    _enrich([confirmed, inferred, unrecorded, laliga],
            {"laliga": ["Arsenal", "Real Madrid"]})
    assert (confirmed.league, confirmed.league_basis) == \
        ("kleague1", competition.MATCHES_FILE)
    assert (inferred.league, inferred.league_basis) == \
        ("laliga", competition.TEAM_LEAGUE)
    # 근거 기록이 없던 경기는 예전처럼 고치되 근거를 지어내지 않는다
    assert (unrecorded.league, unrecorded.league_basis) == ("laliga", "")
    assert inferred.league_ko == "라리가"


def test_c2_no_relabel_when_nothing_moved():
    inferred = _m(1, "epl", competition.TEAM_LEAGUE)
    _enrich([inferred], {"epl": ["Arsenal", "Chelsea"]})
    assert (inferred.league, inferred.league_basis) == \
        ("epl", competition.TEAM_LEAGUE)


def test_c3_adopt_team_league_rules():
    s = _settings()
    m = _m(1, "", competition.NONE)
    assert competition.adopt_team_league(m, "epl", s) is True
    assert (m.league, m.league_basis) == ("epl", competition.TEAM_LEAGUE)
    m = _m(1, "kleague1", competition.MATCHES_FILE)
    assert competition.adopt_team_league(m, "epl", s) is False
    assert m.league == "kleague1"
    assert competition.adopt_team_league(_m(1, "epl", "x"), None, s) is False
    assert competition.adopt_team_league(_m(1, "epl", "x"), "epl", s) is False


def test_c4_enrich_relabels_only_through_the_competition_module():
    from toto.sources import fotmob
    body = ast.unparse(next(
        n for n in ast.walk(ast.parse(inspect.getsource(fotmob)))
        if isinstance(n, ast.FunctionDef) and n.name == "enrich"))
    assert "competition.adopt_team_league(" in body
    assert "match.league =" not in body


# ==========================================================================
# D. 등록·종류 정합성 — 빈 키·미등록 키는 국내리그가 아니다
# ==========================================================================
def test_d1_league_type_distinguishes_registration():
    from toto.settings import CONTINENTAL, LEAGUE
    s = _settings()
    assert s.league_type("epl") == LEAGUE            # 등록 · type 미지정
    assert s.league_type("ucl") == CONTINENTAL       # 등록 · type 지정
    assert s.league_type("월드컵예선") == ""          # 미등록
    assert s.league_type("") == ""                   # 대회 모름


def test_d2_competition_states():
    s = _settings()
    assert competition.state("epl", s) == competition.SUPPORTED
    assert competition.state("laliga", s) == competition.SUPPORTED
    assert competition.state("ucl", s) == competition.UNSUPPORTED
    assert competition.state("월드컵예선", s) == competition.UNREGISTERED
    assert competition.state("", s) == competition.UNKNOWN


def test_d3_unregistered_key_gets_no_league_authority():
    s = _settings()
    assert s.owns_team_league("월드컵예선") is False
    assert s.owns_team_league("") is False
    assert s.strict_team_match("월드컵예선") is True
    # 국내리그는 그대로다
    for key in ("epl", "laliga", "seriea", "kleague1"):
        assert s.owns_team_league(key) is True, key
        assert s.strict_team_match(key) is False, key


def test_d4_fotmob_never_asks_about_unregistered_keys():
    """미등록 대회는 `enrich` 가 받기 전에 걸러진다 — 판정 변경이 실행에
    닿지 않는다."""
    from toto.settings import Settings
    asked: list[str] = []
    real = Settings.owns_team_league

    def spy(self, key):
        asked.append(key)
        return real(self, key)

    Settings.owns_team_league = spy
    try:
        m = _m(1, "월드컵예선", competition.MATCHES_FILE, home="")
        m.home.canonical = m.away.canonical = ""
        from toto.sources import fotmob
        status = fotmob.enrich([m], _settings(), _resolver(), cache=None)
    finally:
        Settings.owns_team_league = real
    assert status == "생략 (리그 미상)", status
    assert asked == []


def test_d5_whoscored_returns_before_strict_for_unregistered_keys():
    from toto.settings import Settings
    from toto.sources import whoscored
    asked: list[str] = []
    real = Settings.strict_team_match

    def spy(self, key):
        asked.append(key)
        return real(self, key)

    Settings.strict_team_match = spy
    try:
        got = whoscored.read_league(None, _settings(), "월드컵예선",
                                    _resolver(), cache=None)
    finally:
        Settings.strict_team_match = real
    assert got == {} and asked == []


# ==========================================================================
# E. 준비 상태 — 단계별로 적고, 막는 정책은 바꾸지 않는다
# ==========================================================================
def _ready_round(pairs=DOMESTIC, odds: int = 14, profiles: bool = True):
    from toto.models import Odds, TeamProfile
    matches, _ = _resolved(pairs)
    for i, m in enumerate(matches):
        if i < odds:
            m.odds = Odds(home=2.0, draw=3.2, away=3.8)
        for side in ("home", "away"):
            ref = getattr(m, side)
            setattr(m, f"{side}_profile",
                    TeamProfile(team=ref, league=m.league, source_ok=profiles))
    status = {"경기목록": "ok (베트맨 14경기)",
              "순위·폼": "ok (28/28팀 지표, 28팀 폼, 0경기 상대전적)",
              "배당률": f"ok ({odds}/14경기)" if odds else "실패",
              "상세데이터": "ok (28/28팀, 강점/약점 28팀)"}
    return matches, status


def test_e1_word_state_reads_the_four_words_and_nothing_else():
    from toto import readiness as R
    assert R.word_state("ok (베트맨 14경기)") == R.PASS
    assert R.word_state("부분 (21/28팀 지표)") == R.PARTIAL
    assert R.word_state("실패 (브라우저 기동 불가)") == R.FAIL
    assert R.word_state("실패") == R.FAIL
    assert R.word_state("생략 (리그 미상)") == R.SKIP
    assert R.word_state("연결됨 · 경기 매칭 실패") == R.FAIL   # 피나클의 다섯째 형식
    assert R.word_state("") == R.UNKNOWN
    assert R.word_state(None) == R.UNKNOWN
    assert R.word_state("무언가 이상한 문자열") == R.UNKNOWN


def test_e2_complete_domestic_round_is_ready():
    from toto import readiness as R
    matches, status = _ready_round()
    got = R.assess(matches, status, _settings())
    assert [c.name for c in got.checks] == [
        "Betman", "경기 파싱", "대회 식별", "FotMob", "Pinnacle", "WhoScored"]
    assert all(c.state == R.PASS for c in got.checks), got.lines()
    assert (got.analysis, got.artifact) == (R.READY, R.READY)
    assert got.reasons == []


def test_e3_one_failed_source_degrades_but_does_not_block():
    from toto import readiness as R
    matches, status = _ready_round(odds=0)
    got = R.assess(matches, status, _settings())
    assert got.get("Pinnacle").state == R.FAIL
    assert got.get("FotMob").state == R.PASS
    assert got.analysis == R.DEGRADED and got.artifact == R.DEGRADED
    assert "Pinnacle FAIL" in got.reasons
    assert got.artifact_policy == "record_only"


def test_e4_ok_word_with_missing_rows_is_partial():
    """소스가 `ok (13/14경기)` 라고 적어도 실제로 빈 경기가 있으면 PARTIAL."""
    from toto import readiness as R
    matches, status = _ready_round(odds=13)
    got = R.assess(matches, status, _settings())
    assert got.get("Pinnacle").state == R.PARTIAL
    assert "[채움 13/14]" in got.get("Pinnacle").detail


def test_e5_unidentified_competitions_are_not_ready():
    from toto import readiness as R
    matches, status = _ready_round(NATIONAL, odds=0, profiles=False)
    status["순위·폼"] = "생략 (리그 미상)"
    got = R.assess(matches, status, _settings())
    comp = got.get("대회 식별")
    assert comp.state == R.FAIL
    assert "supported 0/14" in comp.detail and "unknown 14" in comp.detail
    assert "근거 none 14" in comp.detail
    assert got.analysis == R.NOT_READY


def test_e6_wrong_match_count_is_not_ready():
    from toto import readiness as R
    matches, status = _ready_round()
    got = R.assess(matches[:13], status, _settings())
    assert got.get("경기 파싱").state == R.FAIL
    assert got.analysis == R.NOT_READY


def test_e7_assess_changes_nothing():
    import copy
    from toto import readiness as R
    matches, status = _ready_round(odds=10)
    before = (copy.deepcopy(matches), dict(status))
    R.assess(matches, status, _settings())
    assert (matches, status) == before


def test_e8_lines_name_every_stage():
    from toto import readiness as R
    matches, status = _ready_round(odds=0)
    text = "\n".join(R.assess(matches, status, _settings()).lines())
    for word in ("Betman", "경기 파싱", "대회 식별", "FotMob", "Pinnacle",
                 "WhoScored", "분석", "저장본", "record_only"):
        assert word in text, word


def test_e9_cli_records_readiness_but_does_not_gate_the_artifact():
    """준비 상태는 수집 갈래 끝에서 적고, 저장본 저장 앞에 문을 두지 않는다."""
    from toto import cli
    body = ast.unparse(next(
        n for n in ast.walk(ast.parse(inspect.getsource(cli)))
        if isinstance(n, ast.FunctionDef) and n.name == "main"))
    i_assess = body.index("readiness.assess(")
    assert body.index("resolver.save_leagues()") < i_assess
    assert i_assess < body.index("run_all(matches")
    assert body.index("build_demo_matches()") < i_assess   # 데모 갈래 밖
    save_at = body.index("artifact.save(report)")
    window = body[body.rfind("\n", 0, save_at - 200):save_at]
    assert "ready." not in window and "readiness." not in window


def main() -> int:
    # 직접 실행 러너는 `tests/_runner.py` 한 곳에 있다 (Phase 3 M13).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    sys.exit(main())
