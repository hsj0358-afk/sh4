"""대회 팀명은 정확일치로만 해석한다 (Phase 6-D-4).

## 무엇을 막는가

국내리그는 참가팀이 20~28팀이고 전부 `data/teams.yaml` 에 있다. 그래서
부분일치·토큰 유사도가 표기 흔들림("맨체스터시티(홈)")을 흡수하는 쪽이
이득이었다. **대회는 반대다** — UEL 2025/26 36팀 중 우리가 아는 것은 11팀
뿐이고, 나머지 25팀은 *아무 데도 붙지 말아야 하는 이름*이다. 그 상태에서
부분일치를 켜 두면 모르는 이름이 아는 이름에 들러붙는다.

    Rangers  →  Angers      (별칭 'angers' ⊂ 'rangers')

실측(6-D-6C)에서 이것이 두 군데를 오염시켰다.

    _parse_matches    Rangers vs Roma  →  Angers vs Roma (match_id 4947788)
    _parse_standings  정규명 Angers 에 Rangers 의 fotmob_id 8548

경고는 한 줄도 나오지 않았다. **팀을 못 찾은 것과 다른 팀으로 잘못 찾은
것은 다른 상태**이고, 후자가 훨씬 나쁘다 (§1-5).

## 이 테스트가 고정하는 것

  · strict 는 **정확일치(정규명·별칭)만** 인정한다. 부분일치·토큰 유사도로
    다른 팀에 붙이지 않는다.
  · 막을 때 **무엇을 막았는지 남긴다** — 조용히 비지 않는다 (§1-6-1).
  · **국내리그 경로는 한 줄도 바뀌지 않는다.** 기본값이 `strict=False` 라
    부분일치가 그대로 살아 있다.
  · strict 는 **학습하지 않는다** — `_dirty` · `_league_dirty` 가 False 로
    남고 `teams.learned.yaml` · `teams.league.yaml` 이 생기지 않는다.
  · 판정 기준은 **대회 종류(`type`)** 이지 특정 키 이름이 아니다.

pytest 없이도 돈다:  python tests/test_strict_resolution.py
"""
from __future__ import annotations

import ast
import inspect
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto.normalize import TeamResolver, normalize_name      # noqa: E402
from toto.settings import CONTINENTAL, CUP, LEAGUE, Settings  # noqa: E402
from toto.settings import load_settings, load_yaml           # noqa: E402
from toto.sources import fotmob, whoscored                   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 6-D-2R·6-D-6B·6-D-6C 실측에서 실제로 다른 팀에 붙은 이름들.
# (원문, 붙을 뻔한 정규명)
OBSERVED_FALSE = [
    ("Rangers", "Angers"),                      # UEL 2025/26
    ("Lillestrøm", "Lille"),                    # UEL 2026/27
    ("Lillestroem", "Lille"),                   # 〃 (WhoScored 표기)
    ("Queens Park Rangers", "Angers"),          # FA Cup 2025/26
    ("Birmingham City", "Manchester City"),     # 〃
    ("Chester FC", "Manchester City"),          # 〃
    ("Charlton Athletic", "Athletic Club"),     # 〃
    ("Oldham Athletic", "Athletic Club"),       # 〃
    ("Wigan Athletic", "Athletic Club"),        # 〃
]


# --------------------------------------------------------------------------
# 도구 — production 파일을 절대 건드리지 않는다
# --------------------------------------------------------------------------
def _resolver(tmp: Path) -> TeamResolver:
    """실제 `data/teams.yaml` 은 읽되 **쓰기는 임시 폴더로 돌린다.**"""
    return TeamResolver(learned_file=tmp / "teams.learned.yaml",
                        league_file=tmp / "teams.league.yaml")


def _settings(**types) -> Settings:
    """`{키: type}` 으로 대회 표를 만든다. `type=None` 이면 칸 자체가 없다."""
    leagues: dict[str, dict] = {}
    for key, kind in types.items():
        cfg = {"ko": key, "fotmob_id": 1}
        if kind is not None:
            cfg["type"] = kind
        leagues[key] = cfg
    return Settings(leagues=leagues, whoscored={}, fotmob={})


def _row(name: str, tid: str, **extra) -> dict:
    row = {"name": name, "id": tid, "played": 8, "pts": 12,
           "wins": 4, "draws": 0, "losses": 4, "scoresStr": "10-9"}
    row.update(extra)
    return row


def _league_response(rows: list[dict], matches: list[dict]) -> dict:
    """FotMob 리그 응답의 최소 모양 (`_standings_blocks` + `_match_list` 용)."""
    return {"table": [{"data": {"table": {"all": rows}}}],
            "fixtures": {"allMatches": matches}}


def _match(mid: str, home: str, hid: str, away: str, aid: str,
           score: str = "0 - 2") -> dict:
    return {"id": mid, "round": "4", "roundName": 4,
            "home": {"name": home, "id": hid},
            "away": {"name": away, "id": aid},
            "status": {"utcTime": "2025-11-06T20:00:00Z", "finished": True,
                       "started": True, "cancelled": False,
                       "scoreStr": score}}


# ==========================================================================
# A. 설정 계층 — 어떤 대회가 strict 인가
# ==========================================================================
def test_a1_missing_type_is_not_strict():
    """**미지정 = league = 비-strict.** 기존 여덟 리그가 그대로 돌아야 한다."""
    s = _settings(epl=None)
    assert s.league_type("epl") == LEAGUE
    assert s.strict_team_match("epl") is False


def test_a2_league_is_not_strict():
    assert _settings(epl=LEAGUE).strict_team_match("epl") is False


def test_a3_continental_is_strict():
    assert _settings(any_key=CONTINENTAL).strict_team_match("any_key") is True


def test_a4_cup_is_strict():
    assert _settings(any_key=CUP).strict_team_match("any_key") is True


def test_a5_unknown_type_is_strict():
    """모르는 종류는 막는 쪽으로 판정한다 — 추측보다 미해석이 낫다."""
    assert _settings(x="knockout-ish").strict_team_match("x") is True


def test_a6_unknown_key_is_not_strict():
    """설정에 없는 키는 `league_type` 이 기본값을 주므로 비-strict 다.
    (없는 리그를 수집하는 경로가 애초에 없다 — 동작을 바꾸지 않는다.)"""
    assert _settings(epl=None).strict_team_match("없는키") is False


DOMESTIC_KEYS = {"epl", "laliga", "bundesliga", "seriea",
                 "ligue1", "kleague1", "kleague2", "jleague"}


def test_a7_real_config_has_no_strict_league():
    """**실제 config 의 국내 여덟 리그가 전부 비-strict 다.**

    6-D-7 이 대회 셋을 같은 표에 등록하면서 '설정의 모든 항목이 비-strict'
    로는 더 못 적는다. 지키려던 것은 처음부터 **국내리그 수집 동작이
    바뀌지 않는다**는 것이므로 그 여덟을 직접 가려 확인한다.
    """
    s = load_settings()
    assert DOMESTIC_KEYS <= set(s.leagues), "국내리그 항목이 사라졌다"
    strict = [k for k in DOMESTIC_KEYS if s.strict_team_match(k)]
    assert strict == [], f"strict 로 판정된 국내리그가 있다: {strict}"


def test_a8_decision_derives_from_league_type():
    """판정이 `league_type()` 한 곳에서 나온다 — 키 이름을 박지 않는다."""
    src = inspect.getsource(Settings.strict_team_match)
    assert "league_type(" in src
    for bad in ('"ucl"', "'ucl'", '"uel"', '"facup"', "champions", "europa"):
        assert bad not in src, f"키/대회명 하드코딩: {bad}"


# ==========================================================================
# B. strict 의미 — 정확일치만 인정한다
# ==========================================================================
def test_b1_exact_canonical_still_resolves():
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        assert r.resolve("Manchester City", learn=False, strict=True) == "Manchester City"


def test_b2_exact_alias_still_resolves():
    """정확한 별칭은 strict 에서도 그대로 작동한다 — 별칭을 지우는 Phase 가
    아니다 (§22 필수 5)."""
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        for alias, want in (("맨체스터시티", "Manchester City"),
                            ("M. City", "Manchester City"),
                            ("브렌트퍼", "Brentford"),
                            ("AT마드", "Atletico Madrid"),
                            ("R. Santander", "Racing Santander")):
            got = r.resolve(alias, learn=False, strict=True)
            assert got == want, f"{alias!r} → {got!r} (기대 {want!r})"


def test_b3_normalization_still_applies():
    """정규화(대소문자·구두점·노이즈 토큰)는 strict 에서도 그대로다.
    strict 가 막는 것은 **부분일치**이지 정규화가 아니다."""
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        assert normalize_name("MANCHESTER  CITY.") == normalize_name("Manchester City")
        assert r.resolve("MANCHESTER  CITY.", learn=False, strict=True) == "Manchester City"


def test_b4_unknown_stays_unresolved():
    """모르는 팀은 **아무 팀도 아니다.** 임의 정규명을 주지 않는다."""
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        assert r.resolve("Zalaegerszegi TE", learn=False, quiet=True, strict=True) is None


def test_b5_empty_input():
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        for bad in ("", "   ", "!!!"):
            assert r.resolve(bad, learn=False, quiet=True, strict=True) is None


# ==========================================================================
# C. 실측 오매칭 — 9건 전부 차단 (§11 · §12)
# ==========================================================================
def test_c1_observed_false_matches_are_blocked():
    """핵심. 실측에서 붙었던 9건이 **그 팀으로는 절대 붙지 않는다.**

    `teams.yaml` 에 정확한 별칭이 새로 생기면 원래 팀으로 해석돼도 된다.
    고정하는 것은 '틀린 팀으로 가지 않는다' 하나다 (§11).
    """
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        for raw, wrong in OBSERVED_FALSE:
            got = r.resolve(raw, learn=False, quiet=True, strict=True)
            assert got != wrong, f"{raw!r} 가 여전히 {wrong!r} 로 붙는다"


def test_c2_observed_false_matches_are_unresolved_today():
    """현재 `data/teams.yaml` 기준으로는 9건 모두 미해석이다.

    (이 팀들의 정확한 별칭이 등록되면 이 테스트는 깨지고, 그때는 c1 이
    남아 본질을 지킨다. 어떤 상태인지 기록해 두는 것이 목적이다.)
    """
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        table = load_yaml(ROOT / "data" / "teams.yaml") or {}
        known = set()
        for canon, entry in table.items():
            entry = entry or {}
            known.add(normalize_name(str(canon)))
            for alias in (entry.get("ko") or []) + (entry.get("en") or []):
                known.add(normalize_name(str(alias)))
        for raw, _ in OBSERVED_FALSE:
            if normalize_name(raw) in known:
                continue                      # 정확 별칭이 생겼다면 통과
            got = r.resolve(raw, learn=False, quiet=True, strict=True)
            assert got is None, f"{raw!r} → {got!r} (미해석이어야 한다)"


def test_c3_each_case_is_recorded_with_the_team_it_would_have_become():
    """막았다는 사실과 **무엇으로 붙을 뻔했는지**가 남는다 (§1-6-1)."""
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        for raw, _ in OBSERVED_FALSE:
            r.resolve(raw, learn=False, quiet=True, strict=True)
        recorded = {(a, b) for a, b, _ in r.strict_blocked}
        for pair in OBSERVED_FALSE:
            assert pair in recorded, f"{pair} 가 기록되지 않았다"
        for _, _, how in r.strict_blocked:
            assert how, "차단 경로가 비어 있다"


def test_c4_rangers_is_not_angers_and_angers_is_still_angers():
    """§12 의 개별 대조. 막는 것이 'Angers 를 못 쓰게 하는 것' 이 아니다."""
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        assert r.resolve("Rangers", learn=False, quiet=True, strict=True) != "Angers"
        assert r.resolve("Angers", learn=False, strict=True) == "Angers"
        assert r.resolve("Lillestrøm", learn=False, quiet=True, strict=True) != "Lille"
        assert r.resolve("Lille", learn=False, strict=True) == "Lille"
        assert r.resolve("Birmingham City", learn=False, quiet=True,
                         strict=True) != "Manchester City"
        assert r.resolve("Manchester City", learn=False, strict=True) == "Manchester City"
        for raw in ("Charlton Athletic", "Oldham Athletic", "Wigan Athletic"):
            assert r.resolve(raw, learn=False, quiet=True,
                             strict=True) != "Athletic Club"
        assert r.resolve("Athletic Club", learn=False, strict=True) == "Athletic Club"


def test_c5_no_fuzzy_fallback_survives():
    """토큰 유사도 경로도 막힌다 (부분일치만 막은 것이 아니다)."""
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        # 비-strict 에서는 토큰 유사도로 붙던 표기
        loose = r.resolve("Wolverhampton Rovers FC", learn=False, quiet=True)
        tight = r.resolve("Wolverhampton Rovers FC", learn=False, quiet=True,
                          strict=True)
        assert tight is None, f"strict 인데 {tight!r} 로 붙었다"
        if loose is not None:
            assert any(a == "Wolverhampton Rovers FC" for a, _, _ in r.strict_blocked)


# ==========================================================================
# D. 국내리그 회귀 — 기본 경로는 한 줄도 바뀌지 않는다 (§22 필수 3)
# ==========================================================================
def test_d1_partial_match_still_works_without_strict():
    """부분일치를 **삭제한 것이 아니다.** 기본 경로에서는 그대로 산다."""
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        assert r.resolve("맨체스터시티(홈)", learn=False) == "Manchester City"
        for raw, wrong in OBSERVED_FALSE:
            assert r.resolve(raw, learn=False, quiet=True) == wrong, \
                f"비-strict 동작이 바뀌었다: {raw!r}"


def test_d2_known_domestic_aliases_unchanged():
    """§1-6-1·§1-22·§1-26 이 고정한 표기들이 그대로 해석된다."""
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        for alias, want in (("브렌트퍼", "Brentford"), ("맨체스C", "Manchester City"),
                            ("노팅엄F", "Nottingham Forest"), ("A빌라", "Aston Villa"),
                            ("리즈U", "Leeds"), ("말라가", "Malaga"),
                            ("데포아코", "Deportivo La Coruna"),
                            ("AT마드", "Atletico Madrid"),
                            ("M. City", "Manchester City"),
                            ("A. Villa", "Aston Villa"),
                            ("N. Forest", "Nottingham Forest"),
                            ("R. Santander", "Racing Santander"),
                            ("Deportivo Alaves", "Alaves"),
                            ("알라베스", "Alaves")):
            got = r.resolve(alias, learn=False)
            assert got == want, f"{alias!r} → {got!r} (기대 {want!r})"


def test_d3_every_registered_spelling_still_resolves_to_itself():
    """표에 실린 **모든** 표기(정규명+ko+en)가 자기 정규명으로 해석된다.

    §1-22 · §1-26 이 파일을 고치기 전에 돌린 충돌 시뮬레이션을 테스트로
    옮긴 것이다. 이 Phase 는 alias 를 건드리지 않았다.
    """
    table = load_yaml(ROOT / "data" / "teams.yaml") or {}
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        checked = 0
        for canon, entry in table.items():
            entry = entry or {}
            for alias in [str(canon)] + [str(x) for x in (entry.get("ko") or [])] \
                    + [str(x) for x in (entry.get("en") or [])]:
                got = r.resolve(alias, learn=False, quiet=True)
                assert got == str(canon), f"{alias!r} → {got!r} (기대 {canon!r})"
                checked += 1
        assert checked > 600, f"검사한 표기가 너무 적다: {checked}"


def test_d4_strict_default_is_off_everywhere():
    """`strict` 의 기본값이 전부 False 다 — 호출부를 안 고친 곳은 예전 동작."""
    for fn in (TeamResolver.resolve, TeamResolver._resolve_uncached,
               fotmob._parse_standings, fotmob._parse_matches,
               fotmob._parse_stat_feed, fotmob._find_team_name,
               fotmob.read_team_stats, whoscored._row_team):
        sig = inspect.signature(fn)
        assert "strict" in sig.parameters, f"{fn.__qualname__} 에 strict 가 없다"
        assert sig.parameters["strict"].default is False, \
            f"{fn.__qualname__} 의 strict 기본값이 False 가 아니다"


# ==========================================================================
# E. 파서 경로 — 순위표·경기 목록 (§14)
# ==========================================================================
def test_e1_standings_does_not_attach_source_id_to_the_wrong_team():
    """실측 그대로. 정규명 `Angers` 에 Rangers 의 id 가 붙던 자리다."""
    data = _league_response([_row("Rangers", "8548"), _row("Roma", "8686")], [])
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        loose = fotmob._parse_standings(data, r, "uel")
        assert loose.get("Angers", {}).get("fotmob_id") == "8548"   # 문제 재현

        r2 = _resolver(Path(d))
        tight = fotmob._parse_standings(data, r2, "uel", strict=True)
        assert "Angers" not in tight
        assert "Rangers" not in tight          # 정확 별칭이 없으므로 미해석
        assert "Roma" in tight                 # 아는 팀은 그대로 들어온다
        assert ("Rangers", "Angers") in {(a, b) for a, b, _ in r2.strict_blocked}


def test_e2_matches_do_not_become_a_different_fixture():
    """`Rangers vs Roma` 가 `Angers vs Roma` 로 바뀌지 않는다."""
    data = _league_response([], [_match("4947788", "Rangers", "8548", "Roma", "8686")])
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        loose = fotmob._parse_matches(data, r)
        assert [(m["home"], m["away"]) for m in loose] == [("Angers", "Roma")]

        r2 = _resolver(Path(d))
        tight = fotmob._parse_matches(data, r2, strict=True)
        assert tight == [], f"strict 인데 경기가 남았다: {tight}"


def test_e3_merge_season_never_sees_the_fake_match():
    """§14. 색인까지 내려가지 않는다."""
    data = _league_response(
        [], [_match("4947788", "Rangers", "8548", "Roma", "8686"),
             _match("4947800", "Roma", "8686", "Napoli", "8564", "1 - 1")])
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        out: list = []
        fotmob.merge_season(out, fotmob._parse_matches(data, r, strict=True), "uel")
        pairs = {(s.home_team, s.away_team) for s in out}
        assert ("Angers", "Roma") not in pairs
        assert not any("Angers" in (s.home_team, s.away_team) for s in out)
        # 아는 팀끼리의 경기는 그대로 남는다 — 커버리지를 깎는 것이 목적이 아니다.
        assert ("Roma", "Napoli") in pairs


def test_e4_read_league_derives_strict_from_the_competition_type():
    """`read_league()` 가 리그 키에서 strict 를 유도한다 (AST)."""
    src = inspect.getsource(fotmob.read_league)
    assert "strict_team_match(league_key)" in src
    tree = ast.parse(src)                     # 최상위 함수라 들여쓰기가 없다
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id in ("_parse_standings", "_parse_matches")]
    assert len(calls) == 2, f"파서 호출이 {len(calls)}개다"
    for call in calls:
        assert any(k.arg == "strict" for k in call.keywords), \
            "파서에 strict 를 넘기지 않는다"


def test_e5_whoscored_league_derives_strict_too():
    src = inspect.getsource(whoscored.read_league)
    assert "strict_team_match(league_key)" in src
    assert "strict=strict" in src


def test_e6_season_index_path_is_strict_aware():
    """정산용 색인 경로(`_read_season`)도 같은 판정을 쓴다."""
    src = inspect.getsource(fotmob._read_season)
    assert "strict_team_match(league_key)" in src


# ==========================================================================
# F. 학습 금지 · 저장소 안전 (§22 필수 4)
# ==========================================================================
def test_f1_strict_never_learns():
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        for raw, _ in OBSERVED_FALSE:
            r.resolve(raw, learn=True, quiet=True, strict=True)   # learn=True 라도
        assert r._dirty is False
        assert r._learned == {}
        assert r._league_dirty is False


def test_f2_no_files_are_created():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        r = _resolver(tmp)
        for raw, _ in OBSERVED_FALSE:
            r.resolve(raw, learn=True, quiet=True, strict=True)
        r.save_learned()
        r.save_leagues()
        assert not (tmp / "teams.learned.yaml").exists()
        assert not (tmp / "teams.league.yaml").exists()


def test_f3_production_learned_files_absent():
    """저장소의 실제 자리에 학습 파일이 생기지 않았다."""
    for name in ("teams.learned.yaml", "teams.league.yaml"):
        assert not (ROOT / "data" / name).exists(), f"data/{name} 이 생겼다"


# ==========================================================================
# G. 기록과 로그 — 조용히 비지 않는다 (§1-6-1 · §9)
# ==========================================================================
def test_g1_strict_note_counts_and_names():
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        assert r.strict_note() == ""
        r.resolve("Rangers", learn=False, quiet=True, strict=True)
        note = r.strict_note()
        assert note.startswith("1건")
        assert "Rangers→Angers" in note


def test_g2_strict_note_window():
    """`since` 로 이번 대회 몫만 센다 — resolver 는 여러 리그에 공유된다."""
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        r.resolve("Rangers", learn=False, quiet=True, strict=True)
        mark = len(r.strict_blocked)
        r.resolve("Chester FC", learn=False, quiet=True, strict=True)
        note = r.strict_note(mark)
        assert note.startswith("1건") and "Chester FC" in note
        assert "Rangers" not in note


def test_g3_blocking_is_logged():
    """차단이 로그에 남는다 (quiet 여부로 수준만 달라진다)."""
    with tempfile.TemporaryDirectory() as d:
        r = _resolver(Path(d))
        logger = logging.getLogger("toto.normalize")
        seen: list[tuple[int, str]] = []

        class _Grab(logging.Handler):
            def emit(self, record):
                seen.append((record.levelno, record.getMessage()))

        h = _Grab()
        logger.addHandler(h)
        old = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            r.resolve("Rangers", learn=False, quiet=False, strict=True)
            r.resolve("Chester FC", learn=False, quiet=True, strict=True)
        finally:
            logger.removeHandler(h)
            logger.setLevel(old)
        loud = [m for lv, m in seen if lv >= logging.WARNING and "Rangers" in m]
        soft = [m for lv, m in seen if lv == logging.DEBUG and "Chester FC" in m]
        assert loud, "quiet=False 인데 경고가 없다"
        assert soft, "quiet=True 인데 debug 기록조차 없다"
        assert "Angers" in loud[0], "붙을 뻔한 팀 이름이 로그에 없다"


def test_g4_parse_standings_reports_only_when_strict_blocked():
    """국내리그 출력은 그대로다 — strict 가 막았을 때만 한 줄이 더 붙는다."""
    src = inspect.getsource(fotmob._parse_standings)
    assert "strict_note(" in src
    # 기존 debug 줄이 살아 있다
    assert "FotMob 팀명 미매칭" in src


# ==========================================================================
# H. 격리 — 이번 Phase 가 건드리지 않은 것
# ==========================================================================
def test_h1_analysis_layer_untouched():
    """분석 계층은 팀 식별을 모른다 — 이번 변경이 닿지 않는다."""
    for mod in ("analysis.py", "evidence.py", "xpts.py", "predict.py"):
        src = (ROOT / "toto" / mod).read_text(encoding="utf-8")
        assert "strict" not in src, f"{mod} 에 strict 가 들어갔다"


def test_h2_no_competition_added_to_config():
    """설정에 **대회를 더해도 국내 여덟은 그대로**다.

    6-D-4 에서는 "대회를 추가하지 않았다" 로 적었다 — 그 Phase 의 범위가
    그랬기 때문이다. 6-D-7 이 UCL·UEL·Conference 를 등록하는 Phase 이므로
    범위가 옮겨졌고, 남는 불변조건은 **국내 여덟이 빠지거나 성격이 바뀌지
    않는다**는 것이다. 새로 들어오는 항목은 전부 국내리그가 **아니어야**
    한다 — 국내리그를 조용히 더하면 회차 수집 대상이 달라진다.
    """
    s = load_settings()
    assert DOMESTIC_KEYS <= set(s.leagues), "국내 여덟이 빠졌다"
    for key in DOMESTIC_KEYS:
        assert s.league_type(key) == LEAGUE, key
    for key in set(s.leagues) - DOMESTIC_KEYS:
        assert s.league_type(key) != LEAGUE, f"{key}: 국내리그로 등록됐다"
        assert s.strict_team_match(key) is True, key
        assert s.owns_team_league(key) is False, key


def test_h3_season_param_not_added():
    """production fetcher 에 season 파라미터를 만들지 않았다 (§25-2)."""
    src = (ROOT / "toto" / "sources" / "fotmob.py").read_text(encoding="utf-8")
    assert "season=" not in src.replace("season=season", "")
    assert fotmob.LEAGUE_PATH == "/api/data/leagues?id={id}"


def test_h4_pinnacle_untouched():
    """Pinnacle 은 이번 Phase 범위가 아니다 (§15)."""
    src = (ROOT / "toto" / "sources" / "pinnacle.py").read_text(encoding="utf-8")
    assert "strict" not in src


# --------------------------------------------------------------------------
def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as exc:
            bad += 1
            print(f"  FAIL {fn.__name__}: {exc}")
        except Exception as exc:                        # noqa: BLE001
            bad += 1
            print(f"  ERR  {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - bad}/{len(tests)} 통과")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
