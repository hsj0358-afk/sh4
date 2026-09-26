"""대회 피드가 팀 소속을 덮어쓰지 못하게 막는다 (Phase 6-D-3).

## 무엇을 막는가

`fotmob.enrich()` 는 받아 온 순위표의 팀에 `resolver.set_league()` 를 불러
소속을 정정한다 — 국내리그에서는 옳다(§3-5: 승강이 매 시즌 일어난다).

그런데 **대륙대회·컵대회의 참가팀 표에는 같은 권위가 없다.** 챔피언스리그
표에 아스널이 있다고 해서 아스널의 소속이 챔피언스리그인 것이 아니다.
막지 않으면 `data/teams.league.yaml` 에 `Arsenal: ucl` 이 **영구 저장**되고
(그 파일이 `data/teams.yaml` 보다 우선한다) 다음 회차부터 배당 조회·레이더
모집단·피드 선택이 전부 어긋난다.

Phase 6-D-2 에서 production 함수로 재현해 확인했다.

    [전] Arsenal=epl  Real Madrid=laliga   _league_dirty=False
    [후] 5/5 팀이 'ucl' 로 바뀜            _league_dirty=True

## 이 테스트가 고정하는 것

  · 판정 기준은 **대회 종류(`type`)** 이지 특정 키 이름이 아니다.
    `ucl`·`uel`·`fa_cup` 이 전부 같은 보호를 받아야 하므로 키를 하드코딩한
    테스트를 쓰지 않는다.
  · **미지정 = `league`** — 기존 여덟 리그가 그대로 돌아야 한다.
  · 막는 자리는 `set_league()` 가 아니라 **부르는 쪽**이다. 그래서
    `set_league()` 를 직접 부르는 검사로 끝내지 않고 **실제 `enrich()`
    경로**로 확인한다 (J절).

pytest 없이도 돈다:  python tests/test_competition_guard.py
"""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import settings as settings_mod                     # noqa: E402
from toto.models import Match, TeamProfile, TeamRef, TeamStats  # noqa: E402
from toto.normalize import TeamResolver                        # noqa: E402
from toto.settings import (COMPETITION_TYPES, CONTINENTAL, CUP,  # noqa: E402
                           LEAGUE, Settings)
from toto.settings import load_settings                        # noqa: E402
from toto.sources import fotmob                                # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 실측(6-D-2)에서 오염됐던 그 팀들. **키가 아니라 종류로 막는다**는 것을
# 보이려고 대회 키는 일부러 `ucl` 이 아닌 이름을 쓴다.
DOMESTIC = {"Arsenal": "epl", "Liverpool": "epl",
            "Real Madrid": "laliga", "Barcelona": "laliga",
            "Atletico Madrid": "laliga"}
# `data/teams.yaml` 에 소속이 적혀 있지 않은 팀. 리그 피드가 소속을 **실제로
# 채우는** 것을 보일 때 쓴다 (없는 값을 채우는 것이 §3-5 의 정상 동작이다).
UNASSIGNED = "Ipswich"


# --------------------------------------------------------------------------
# 도구 — production 파일을 절대 건드리지 않는다
# --------------------------------------------------------------------------
def _resolver(tmp: Path) -> TeamResolver:
    """실제 `data/teams.yaml` 은 읽되 **쓰기는 임시 폴더로 돌린다.**"""
    return TeamResolver(learned_file=tmp / "teams.learned.yaml",
                        league_file=tmp / "teams.league.yaml")


def _settings(**types: str) -> Settings:
    """`{키: type}` 으로 대회 표를 만든다. `type=None` 이면 칸 자체가 없다."""
    leagues: dict[str, dict] = {}
    for key, kind in types.items():
        cfg = {"ko": key, "fotmob_id": 1}
        if kind is not None:
            cfg["type"] = kind
        leagues[key] = cfg
    return Settings(leagues=leagues, whoscored={}, fotmob={})


class _FakeBrowser:
    """`FotMobBrowser` 자리. 네트워크를 쓰지 않는다."""
    available = True

    def __init__(self, *a, **k) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a) -> bool:
        return False


def _feed(teams: list[str]) -> dict:
    """`read_league()` 가 돌려주는 모양."""
    return {"teams": {t: {"stats": TeamStats(), "form": [], "fotmob_id": "",
                          "page_url": ""} for t in teams},
            "matches": []}


def _run_enrich(tmp: Path, settings: Settings, feeds: dict[str, list[str]],
                match_league: str) -> TeamResolver:
    """**실제 `enrich()`** 를 태운다. 브라우저와 리그 읽기만 가짜다."""
    resolver = _resolver(tmp)
    match = Match(no=1,
                  home=TeamRef(display="H", canonical="Arsenal"),
                  away=TeamRef(display="A", canonical="Real Madrid"))
    match.league = match_league
    match.home_profile = TeamProfile(team=match.home)
    match.away_profile = TeamProfile(team=match.away)

    real_browser, real_read = fotmob.FotMobBrowser, fotmob.read_league
    fotmob.FotMobBrowser = _FakeBrowser
    fotmob.read_league = (
        lambda browser, st, key, res, cache=None: _feed(feeds.get(key, [])))
    try:
        fotmob.enrich([match], settings, resolver, cache=None)
    finally:
        fotmob.FotMobBrowser, fotmob.read_league = real_browser, real_read
    return resolver


# ==========================================================================
# A~D. 종류별 판정 (설정 계층)
# ==========================================================================
def test_a1_missing_type_is_read_as_league():
    """**미지정 = league.** 기존 여덟 리그가 그대로 돌아야 한다."""
    s = _settings(epl=None)
    assert s.league_type("epl") == LEAGUE
    assert s.owns_team_league("epl") is True


def test_a2_real_config_has_no_type_and_still_owns():
    """**국내리그 항목**은 `type` 없이도 예전과 같이 동작한다.

    6-D-7 이 `type: continental` 인 대회를 같은 표에 등록하면서, '설정의 모든
    항목에 type 이 없다' 는 형태로는 더 못 적는다. 이 테스트가 지키려던 것은
    처음부터 **기존 여덟 리그가 칸 하나 없이도 소속 권위를 유지한다**는 것
    이므로(§3-5), 그 여덟을 직접 가려 확인한다 — 범위가 옮겨진 것이지
    불변조건이 약해진 것이 아니다.
    """
    s = load_settings()
    assert s.leagues, "설정을 읽지 못했다"
    domestic = [k for k, cfg in s.leagues.items() if "type" not in cfg]
    assert len(domestic) >= 8, f"국내리그 항목이 사라졌다: {domestic}"
    for key in domestic:
        assert s.owns_team_league(key) is True, key
        assert s.strict_team_match(key) is False, key
    # type 이 적힌 항목은 전부 아는 값이어야 한다 — 오타면 소속 정정이
    # 조용히 꺼진다.
    for key, cfg in s.leagues.items():
        if "type" in cfg:
            assert s.league_type(key) in COMPETITION_TYPES, (key, cfg["type"])


def test_b1_league_type_owns():
    s = _settings(epl=LEAGUE)
    assert s.league_type("epl") == LEAGUE
    assert s.owns_team_league("epl") is True


def test_c1_continental_does_not_own():
    s = _settings(anything=CONTINENTAL)
    assert s.league_type("anything") == CONTINENTAL
    assert s.owns_team_league("anything") is False


def test_d1_cup_does_not_own():
    s = _settings(anything=CUP)
    assert s.owns_team_league("anything") is False


def test_d2_unknown_type_is_blocked_not_guessed():
    """모르는 값을 조용히 `league` 로 바꾸지 않는다.

    엉뚱한 소속을 영구 저장하는 것보다 정정하지 않는 편이 낫다 — §1-1-1 이
    리그 ID 를 "가리지 못하면 임의로 고르지 않고 실패한다" 로 둔 것과 같다.
    """
    s = _settings(weird="leauge")            # 오타
    assert s.league_type("weird") == "leauge"   # 값을 고쳐 주지 않는다
    assert s.owns_team_league("weird") is False


def test_d3_type_is_case_and_space_insensitive():
    for raw in (" Continental ", "CONTINENTAL", "Cup"):
        s = _settings(x=raw)
        assert s.owns_team_league("x") is False, raw
    for raw in ("  League  ", "LEAGUE", ""):
        s = _settings(x=raw)
        assert s.owns_team_league("x") is True, raw


def test_d4_unknown_key_is_treated_as_league():
    """설정에 아예 없는 키는 기존과 같이 취급한다 (동작 변화 없음)."""
    s = _settings(epl=LEAGUE)
    assert s.owns_team_league("없는키") is True


# ==========================================================================
# E~H. 오염 차단 — 실제 소속 표로 확인
# ==========================================================================
def test_e1_continental_feed_keeps_every_domestic_league():
    """6-D-2 재현 시나리오. 다섯 팀 전부 국내 소속을 유지해야 한다."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        s = _settings(cl=CONTINENTAL, epl=None, laliga=None)
        r = _run_enrich(tmp, s, {"cl": list(DOMESTIC)}, "cl")
        for team, league in DOMESTIC.items():
            assert r.league_of(team) == league, (
                f"{team}: {league} → {r.league_of(team)} 로 오염됐다")


def test_e2_cup_feed_is_blocked_the_same_way():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        s = _settings(kcup=CUP, epl=None, laliga=None)
        r = _run_enrich(tmp, s, {"kcup": list(DOMESTIC)}, "kcup")
        assert [r.league_of(t) for t in DOMESTIC] == list(DOMESTIC.values())


def test_f1_continental_feed_does_not_dirty_the_resolver():
    """메모리만이 아니라 **저장까지** 막혔는지 본다."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        s = _settings(cl=CONTINENTAL, epl=None, laliga=None)
        r = _run_enrich(tmp, s, {"cl": list(DOMESTIC)}, "cl")
        assert r._league_dirty is False, "대회 피드가 저장 대상을 만들었다"
        r.save_leagues()
        assert not (tmp / "teams.league.yaml").exists(), \
            "대회 피드만으로 소속 파일이 생겼다"


def test_g1_league_feed_still_corrects_and_dirties():
    """반대 방향 — 국내리그 피드의 기존 동작은 그대로다 (§3-5)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        r = _resolver(tmp)
        assert r.league_of(UNASSIGNED) is None, "전제가 바뀌었다"

        s = _settings(epl=None, laliga=None)
        real_browser, real_read = fotmob.FotMobBrowser, fotmob.read_league
        fotmob.FotMobBrowser = _FakeBrowser
        fotmob.read_league = (
            lambda b, st, key, res, cache=None:
            _feed([UNASSIGNED] if key == "epl" else []))
        match = Match(no=1,
                      home=TeamRef(display="H", canonical="Arsenal"),
                      away=TeamRef(display="A", canonical="Liverpool"))
        match.league = "epl"
        try:
            fotmob.enrich([match], s, r, cache=None)
        finally:
            fotmob.FotMobBrowser, fotmob.read_league = real_browser, real_read

        assert r.league_of(UNASSIGNED) == "epl", "리그 피드의 정정이 막혔다"
        assert r._league_dirty is True
        r.save_leagues()
        assert (tmp / "teams.league.yaml").exists(), "저장 동작이 사라졌다"


def test_h1_downstream_league_of_is_unchanged():
    """소속을 읽어 쓰는 하류(배당 리그 선택·레이더 버킷)가 그대로여야 한다."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        before = {t: _resolver(tmp).league_of(t) for t in DOMESTIC}
        s = _settings(cl=CONTINENTAL, epl=None, laliga=None)
        r = _run_enrich(tmp, s, {"cl": list(DOMESTIC)}, "cl")
        after = {t: r.league_of(t) for t in DOMESTIC}
        assert before == after == DOMESTIC


def test_h2_match_league_is_not_rewritten_by_a_blocked_feed():
    """`enrich` 의 소속 정정 블록은 `match.league` 도 고친다 — 막히면 그대로."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        s = _settings(cl=CONTINENTAL, epl=None, laliga=None)
        resolver = _resolver(tmp)
        match = Match(no=1,
                      home=TeamRef(display="H", canonical="Arsenal"),
                      away=TeamRef(display="A", canonical="Real Madrid"))
        match.league = "cl"
        real_browser, real_read = fotmob.FotMobBrowser, fotmob.read_league
        fotmob.FotMobBrowser = _FakeBrowser
        fotmob.read_league = (
            lambda b, st, key, res, cache=None:
            _feed(list(DOMESTIC) if key == "cl" else []))
        try:
            fotmob.enrich([match], s, resolver, cache=None)
        finally:
            fotmob.FotMobBrowser, fotmob.read_league = real_browser, real_read
        assert match.league == "cl", "막힌 피드가 경기의 대회를 바꿨다"


# ==========================================================================
# I~J. 구조 — 어디서 막는가
# ==========================================================================
def test_i1_set_league_semantics_are_untouched():
    """`set_league()` 자체는 그대로다. 막는 자리는 부르는 쪽이다 (§11)."""
    src = (ROOT / "toto" / "normalize.py").read_text(encoding="utf-8")
    body = src[src.index("def set_league("):]
    body = body[:body.index("\n    def ")]
    for word in ("type", "continental", "cup", "owns_team_league", "settings"):
        assert word not in body, f"set_league 안에 '{word}' 가 들어갔다"


def test_j1_the_guard_sits_in_enrich_not_in_the_resolver():
    """실제 `enrich()` 경로에 가드가 있는지 소스로 확인한다."""
    src = (ROOT / "toto" / "sources" / "fotmob.py").read_text(encoding="utf-8")
    body = src[src.index("def enrich("):]
    assert "owns_team_league" in body, "enrich 에 가드가 없다"
    assert body.index("owns_team_league") < body.index("resolver.set_league"), \
        "가드가 set_league 호출보다 뒤에 있다"


def test_j2_no_hardcoded_competition_keys_or_names():
    """`ucl`·`champions` 같은 이름으로 분기하지 않는다 (§5·§16).

    문자열 상수만 본다 — 주석·docstring 은 설명이라 제외한다.

    **docstring 을 실제로 빼도록 고쳤다.** `ast.Constant` 에는 docstring 도
    들어와서, 설명에 적어 둔 제외 규칙이 지켜지지 않고 있었다 — 실측을 적은
    docstring 때문에 두 번 걸렸다(6-D-4 는 문장을 바꿔 피했다). docstring 은
    분기를 만들 수 없으므로 빼도 이 테스트가 지키는 것은 그대로다.
    """
    for rel in ("toto/sources/fotmob.py", "toto/settings.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
                first = node.body[0] if node.body else None
                if (isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    docstrings.add(id(first.value))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docstrings):
                low = node.value.lower()
                for banned in ("ucl", "uel", "champions", "europa", "fa_cup"):
                    assert banned not in low, f"{rel}: 상수 {node.value!r}"


def test_j3_the_decision_lives_in_one_place():
    """`== "league"` 를 부르는 쪽에서 다시 적지 않는다 (§1-8)."""
    src = (ROOT / "toto" / "sources" / "fotmob.py").read_text(encoding="utf-8")
    assert 'league_type(' not in src, \
        "enrich 가 종류를 직접 해석하고 있다 — owns_team_league 를 쓴다"
    assert settings_mod.COMPETITION_TYPES == (LEAGUE, CONTINENTAL, CUP)


def test_j4_only_one_ownership_write_path_exists():
    """`set_league` 를 **부르는** production 코드가 한 곳뿐이어야 한다.

    두 곳이 되면 한쪽만 막혀 조용히 오염된다. 주석·설명은 세지 않으려고
    실제 호출(AST `Call`)만 본다.
    """
    hits = []
    for path in sorted((ROOT / "toto").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "attr", "") == "set_league"):
                hits.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert len(hits) == 1, hits
    assert hits[0].startswith("toto/sources/fotmob.py:"), hits


def test_j5_source_modules_never_learn_aliases():
    """별칭 학습으로도 오염되지 않는다 — 소스는 전부 `learn=False` 다.

    §7 의 '또 다른 오염 경로가 있나' 에 대한 답을 고정한다.
    """
    for rel in ("toto/sources/fotmob.py", "toto/sources/whoscored.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        for i, line in enumerate(src.splitlines(), 1):
            if ".resolve(" in line and "def resolve" not in line:
                assert "learn=False" in line, f"{rel}:{i} — {line.strip()}"


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
