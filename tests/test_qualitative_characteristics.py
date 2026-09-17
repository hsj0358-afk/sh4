"""정성 특성 데이터/모델 계층 (Phase 6-E-2).

후스코어드 강점/약점의 원문 `"<라벨> · <강도>"` 를 **손실 없이** 구조화하고,
`strengths=[]` 하나가 겸하고 있던 여러 뜻을 실물 근거가 있는 만큼만 가른다.

**이 Phase 가 하지 않는 것**을 먼저 적는다 — 테스트의 절반이 그것을 지킨다.

  · 관계 판정을 하지 않는다. `build_matchup()`·`_TOPICS`·`_TOPIC_KO` 무변경.
  · 강도를 숫자로 바꾸지 않는다. `Very Strong` 은 끝까지 `Very Strong` 이다.
  · 전달 경로를 바꾸지 않는다. `render`·`match_material`·`panel`·`menu` 무변경.
  · `source_ok` 의 뜻을 바꾸지 않는다. 특성 확보 여부는 **별개의 칸**이다.
  · 실물이 가려 주지 않는 상태를 만들지 않는다 — '슬롯 미검출' 은 없다.

**지키는 것 하나.** 원문이 곧 저장 형식이다. `TeamProfile.strengths` 는
`list[str]` 그대로이고 구조화는 **읽을 때 파생**된다 — 그래서 되돌릴 때
재조립할 것이 없고, 이 필드를 읽는 기존 코드가 한 줄도 바뀌지 않는다.

pytest 없이도 돈다:  python tests/test_qualitative_characteristics.py
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import sys
from dataclasses import asdict, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from toto import analyze, artifact                              # noqa: E402
from toto.models import (CHAR_OBSERVED_EMPTY, CHAR_OK,          # noqa: E402
                         CHAR_PAGE_FAILED, CHAR_UNRECORDED,
                         Characteristic, TeamProfile, TeamRef,
                         characteristic_status, characteristics,
                         parse_characteristic)
from toto.sources import whoscored                              # noqa: E402

ARTIFACT = ROOT / "data" / "artifacts" / "260052.json"

# 실물 260052 에서 관측된 강도 넷. **코드가 아니라 테스트에만 적는다** —
# 프로덕션이 이 목록을 갖게 되면 리그·언어가 바뀔 때 조용히 빗나간다.
OBSERVED_INTENSITIES = ("Strong", "Very Strong", "Weak", "Very Weak")


def _artifact():
    """실물 저장본. 없으면 `None` — 그 테스트는 조용히 지나간다."""
    if not ARTIFACT.exists():
        return None
    report, _why = artifact.load_path(ARTIFACT)
    return report


def _profiles(report):
    for match in report.matches:
        for side in ("home", "away"):
            profile = getattr(match, f"{side}_profile")
            if profile is not None:
                yield match, side, profile


def _src(obj) -> str:
    return inspect.getsource(obj)


def _code_only(obj) -> str:
    """docstring 을 걷어낸 소스.

    설명에 낱말이 나왔다고 '코드에 박혔다' 고 판정하면, 규칙을 적어 둔
    주석 때문에 테스트가 깨진다 — `test_strict_resolution.test_j2` 가
    같은 이유로 고쳐진 적이 있다. 지키려는 것은 **분기에 쓰이는가** 다.
    """
    tree = ast.parse(_src(obj))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
                and body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            body.pop(0)
    return ast.unparse(tree)


# ==========================================================================
# A. 파싱 — 실물에서 확인한 갈래만
# ==========================================================================
def test_a1_normal_item_splits_into_label_and_intensity():
    """Test A — 정상 항목."""
    char = parse_characteristic("Attacking down the wings · Very Strong")
    assert char is not None
    assert char.label == "Attacking down the wings", char.label
    assert char.intensity == "Very Strong", char.intensity
    assert char.parsed is True


def test_a2_all_four_observed_intensities_parse():
    for intensity in OBSERVED_INTENSITIES:
        char = parse_characteristic(f"Aerial duels · {intensity}")
        assert char is not None and char.parsed, intensity
        assert char.label == "Aerial duels", char.label
        assert char.intensity == intensity, char.intensity


def test_a3_missing_separator_keeps_the_label():
    """Test C — 구분자 없는 항목.

    가상의 사례가 아니다. `_extract_characteristics` 의 추출 갈래 넷 중
    셋(`li` · `span/td/p` · 임베드 JSON)이 구분자 없이 문자열을 만든다 —
    260052 는 `div.character` 갈래로 와서 전부 구분자가 있었을 뿐이다.
    그때도 **라벨은 버리지 않는다.**
    """
    char = parse_characteristic("Attacking down the wings")
    assert char is not None, "라벨만 있는 항목을 버렸다"
    assert char.label == "Attacking down the wings"
    assert char.intensity == ""
    assert char.parsed is False, "강도가 없는데 parsed 가 True 다"


def test_a4_multiple_separators_take_the_last_field():
    """열이 셋 이상이면 마지막이 강도다 — 추출 갈래가 열을 이어 붙인다."""
    char = parse_characteristic("A · B · Very Strong")
    assert char is not None
    assert char.label == "A · B", char.label
    assert char.intensity == "Very Strong", char.intensity
    assert char.raw == "A · B · Very Strong", "원문이 바뀌었다"


def test_a5_empty_input_is_not_a_characteristic():
    for bad in (None, "", "   ", "\n"):
        assert parse_characteristic(bad) is None, repr(bad)


def test_a6_non_string_input_is_not_a_characteristic():
    for bad in (0, 1, True, [], {}, 3.5):
        assert parse_characteristic(bad) is None, repr(bad)


def test_a7_half_empty_separator_is_not_split():
    """`" · Strong"` 처럼 한쪽이 비면 쪼개지 않는다 — 원문을 라벨로 둔다."""
    for raw in (" · Strong", "Aerial duels · ", " · "):
        char = parse_characteristic(raw)
        if char is None:            # " · " 는 strip 뒤에도 내용이 있다
            continue
        assert char.raw == raw, char.raw
        assert char.parsed is False, f"{raw!r} 가 정상 파싱으로 통과했다"


def test_a8_intensity_vocabulary_is_not_hardcoded():
    """강도 어휘를 코드에 두지 않는다 (§3-1 이 추출기에 정한 것과 같은 이유).

    자리로만 가르므로 모르는 낱말도 그대로 실린다.
    """
    from toto import models
    src = _code_only(models.parse_characteristic) + _code_only(models.Characteristic)
    for word in OBSERVED_INTENSITIES:
        assert word not in src, f"강도 어휘 {word!r} 가 코드에 박혔다"
    char = parse_characteristic("Pressing intensity · Extremely Strong")
    assert char is not None and char.parsed
    assert char.intensity == "Extremely Strong", char.intensity


def test_a9_intensity_is_never_turned_into_a_number():
    """`Very Strong=2` 류의 수치화가 없다."""
    for intensity in OBSERVED_INTENSITIES:
        char = parse_characteristic(f"Aerial duels · {intensity}")
        assert isinstance(char.intensity, str), type(char.intensity)
    from toto import models
    for fn in (models.parse_characteristic, models.characteristics,
               models.characteristic_status):
        # `rsplit(sep, 1)` 의 `1` 은 자릿수이지 강도 값이 아니므로 숫자
        # 상수 자체는 막지 않는다. 막는 것은 **산술**이다.
        for node in ast.walk(ast.parse(_src(fn))):
            assert not isinstance(node, (ast.Mult, ast.Div, ast.Add,
                                         ast.Sub, ast.Pow)), (
                f"{fn.__name__}: 강도를 값으로 다루는 산술이 들어왔다")


def test_a10_characteristic_is_frozen_and_has_no_score_field():
    char = parse_characteristic("Aerial duels · Strong")
    try:
        char.label = "바꿔치기"            # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("Characteristic 이 frozen 이 아니다")
    names = {f.name for f in fields(Characteristic)}
    assert names == {"raw", "label", "intensity"}, names
    for bad in ("score", "weight", "value", "rank", "level"):
        assert bad not in names, bad


def test_a11_parsing_lives_in_one_place():
    """구분자를 쪼개는 책임이 한 곳이다 (§1-8).

    소비 모듈이 각자 `split(" · ")` 하기 시작하면 규칙이 갈라진다.
    구분자를 **잇는**(`join`) 것은 다른 일이라 막지 않는다 — 막는 것은
    **쪼개는** 쪽이다.
    """
    literal, holder = [], []
    for path in sorted((ROOT / "toto").rglob("*.py")):
        rel = str(path.relative_to(ROOT))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            # `x.split(" · ")` / `x.rsplit(" · ", 1)` 처럼 리터럴로 쪼개는 곳
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("split", "rsplit")
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == " · "):
                literal.append(rel)
            # 상수를 거쳐 쪼개는 곳
            if isinstance(node, ast.Name) and node.id == "_CHAR_SEP":
                holder.append(rel)
    assert literal == [], f"구분자를 직접 쪼개는 곳이 생겼다: {literal}"
    assert set(holder) == {"toto/models.py"}, sorted(set(holder))


# ==========================================================================
# B. 원문 보존 — 이 Phase 의 핵심 불변조건
# ==========================================================================
def test_b1_roundtrip_returns_the_original_strings():
    """Test B — 구조화 → 복원 == 원문."""
    items = ["Attacking down the wings · Very Strong",
             "Aerial duels · Strong",
             "Creating chances using through balls · Strong"]
    assert [c.raw for c in characteristics(items)] == items


def test_b2_roundtrip_keeps_order():
    items = ["C · Weak", "A · Strong", "B · Very Weak"]
    assert [c.raw for c in characteristics(items)] == items


def test_b3_only_empty_entries_drop_out():
    items = ["Aerial duels · Strong", "", None, "   ", "Counter attacks · Weak"]
    out = characteristics(items)
    assert [c.raw for c in out] == ["Aerial duels · Strong",
                                    "Counter attacks · Weak"]


def test_b4_roundtrip_is_exact_on_the_real_round():
    """Test B (실물) — 260052 의 모든 항목이 글자까지 보존된다."""
    report = _artifact()
    if report is None:
        return
    total = 0
    for _match, _side, profile in _profiles(report):
        for slot in ("strengths", "weaknesses", "style_of_play"):
            items = getattr(profile, slot)
            back = [c.raw for c in characteristics(items)]
            assert back == items, f"{profile.team.canonical}/{slot}: {back}"
            total += len(items)
    assert total == 212, f"실물 항목 수가 달라졌다: {total}"


def test_b5_real_round_parses_completely():
    """실물 212건이 전부 라벨 + 강도로 갈린다 (파싱 실패 0건)."""
    report = _artifact()
    if report is None:
        return
    seen_intensity = set()
    unparsed = []
    for _match, _side, profile in _profiles(report):
        for slot in ("strengths", "weaknesses"):
            for char in characteristics(getattr(profile, slot)):
                if not char.parsed:
                    unparsed.append(char.raw)
                else:
                    seen_intensity.add(char.intensity)
                assert char.label, char.raw
    assert unparsed == [], unparsed
    assert seen_intensity == set(OBSERVED_INTENSITIES), sorted(seen_intensity)


def test_b6_real_round_label_counts_are_unchanged():
    """6-E-1 이 실측한 어휘 규모가 그대로다 (강점 14종 · 약점 14종)."""
    report = _artifact()
    if report is None:
        return
    labels = {"strengths": set(), "weaknesses": set()}
    counts = {"strengths": 0, "weaknesses": 0}
    for _match, _side, profile in _profiles(report):
        for slot in labels:
            for char in characteristics(getattr(profile, slot)):
                labels[slot].add(char.label)
                counts[slot] += 1
    assert counts == {"strengths": 103, "weaknesses": 109}, counts
    assert len(labels["strengths"]) == 14, sorted(labels["strengths"])
    assert len(labels["weaknesses"]) == 14, sorted(labels["weaknesses"])


# ==========================================================================
# C. 상태 — 실물 raw 가 가려 주는 만큼만
# ==========================================================================
def test_c1_three_states_plus_unrecorded():
    assert characteristic_status(["Aerial duels · Strong"], True) == CHAR_OK
    assert characteristic_status([], True) == CHAR_OBSERVED_EMPTY
    assert characteristic_status([], False) == CHAR_PAGE_FAILED
    assert characteristic_status([], None) == CHAR_UNRECORDED


def test_c2_values_are_items_first():
    """항목이 있으면 페이지 상태와 무관하게 `ok` 다 — 값이 우선이다."""
    for page_ok in (True, False, None):
        assert characteristic_status(["x · Strong"], page_ok) == CHAR_OK


def test_c3_status_does_not_read_source_ok():
    """§12 — `source_ok` 와 특성 확보 여부는 별개다.

    실물 입스위치가 `source_ok=True` 인 채로 강점 0개였다. 둘을 한 값으로
    묶으면 그 상태를 적을 자리가 없어진다.
    """
    from toto import models
    src = _src(models.characteristic_status)
    assert "source_ok" not in src.split('"""')[2], src
    profile = TeamProfile(team=TeamRef(canonical="Ipswich"))
    profile.source_ok = True
    profile.team_page_ok = True
    profile.weaknesses = ["Aerial duels · Very Weak"]
    assert characteristic_status(profile.strengths,
                                 profile.team_page_ok) == CHAR_OBSERVED_EMPTY
    assert characteristic_status(profile.weaknesses,
                                 profile.team_page_ok) == CHAR_OK


def test_c4_no_slot_undetected_state_was_invented():
    """'슬롯 미검출' 을 만들지 않았다.

    `_extract_characteristics` 가 제목을 못 찾은 경우와 제목은 찾았는데
    항목이 없는 경우를 **똑같이 `[]`** 로 돌려주므로, 지금 저장돼 있는
    자료로는 그 둘을 가를 수 없다. 없는 근거로 상태를 만들지 않는다 (§1-5).
    """
    from toto import models
    states = {v for k, v in vars(models).items()
              if k.startswith("CHAR_") and isinstance(v, str)}
    assert states == {CHAR_OK, CHAR_OBSERVED_EMPTY,
                      CHAR_PAGE_FAILED, CHAR_UNRECORDED}, states
    for bad in ("slot_missing", "heading_missing", "slot_undetected",
                "partial", "unknown"):
        assert bad not in states, bad


def test_c5_real_round_zero_strength_teams_are_observed_empty():
    """Test F (실물) — 입스위치·셀타비고·헤타페.

    셋 다 팀 페이지를 읽었고 약점·폼이 왔다. 저장본에는 `team_page_ok` 가
    없으므로(6-E-2 이전) 상태는 `unrecorded` 이고, **`page_failed` 가
    아니다** — 기록이 없는 것과 실패는 다르다.
    """
    report = _artifact()
    if report is None:
        return
    empty = []
    for _match, _side, profile in _profiles(report):
        if not profile.strengths:
            empty.append(profile)
            assert profile.team_page_ok is None, profile.team_page_ok
            assert characteristic_status(profile.strengths,
                                         profile.team_page_ok) == CHAR_UNRECORDED
            # 같은 팀의 약점은 왔다 — 페이지를 읽었다는 방증이다.
            assert profile.weaknesses, profile.team.canonical
    assert {p.team.canonical for p in empty} == {
        "Ipswich", "Celta Vigo", "Getafe"}, [p.team.canonical for p in empty]
    # 그 셋이 읽혔다고 표시되면 `observed_empty` 로 갈린다.
    for profile in empty:
        assert characteristic_status(profile.strengths, True) == CHAR_OBSERVED_EMPTY


def test_c6_real_round_coverage_is_unchanged():
    """6-E-1 실측 확보율이 그대로다 — 강점 25/28 · 약점 28/28 · 스타일 0/28."""
    report = _artifact()
    if report is None:
        return
    have = {"strengths": 0, "weaknesses": 0, "style_of_play": 0}
    total = 0
    for _match, _side, profile in _profiles(report):
        total += 1
        for slot in have:
            if getattr(profile, slot):
                have[slot] += 1
    assert total == 28, total
    assert have == {"strengths": 25, "weaknesses": 28,
                    "style_of_play": 0}, have


def test_c7_collector_records_the_page_result_in_both_branches():
    """수집기가 두 갈래 모두에서 `team_page_ok` 를 적는다.

    한쪽만 적으면 '표에 팀이 없었다' 가 `--skip-whoscored` 와 같은
    `None` 으로 남아 구분이 사라진다.
    """
    src = _src(whoscored.enrich)
    assert src.count("profile.team_page_ok") == 2, src.count("profile.team_page_ok")
    assert "profile.team_page_ok = bool(payload)" in src
    assert "profile.team_page_ok = False" in src


def test_c8_collector_marks_the_four_real_situations():
    """수집기를 **실제로 돌려** 네 상황이 갈리는지 본다.

    후스코어드는 이 세션에서 차단돼 있으므로(§2-1) 브라우저·`read_league`·
    `read_team` 만 가짜로 바꾸고 `enrich()` 본문은 그대로 태운다 — 소스
    문자열 검사만으로는 배선이 실제로 도는지 알 수 없다.
    """
    from toto.models import Match, TeamStats
    from toto.normalize import TeamResolver
    from toto.settings import load_settings

    class FakeBrowser:
        available = True

        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    payloads = {
        # 정상 — 강점이 왔다
        "Arsenal": {"strengths": ["Aerial duels · Strong"],
                    "weaknesses": [], "style": [], "form": [], "missing": []},
        # 관측된 0 — 페이지는 읽었는데 강점이 없다 (실물 입스위치 모양)
        "Ipswich": {"strengths": [],
                    "weaknesses": ["Aerial duels · Very Weak"],
                    "style": [], "form": [], "missing": []},
        # 페이지 실패 — `read_team` 이 `{}` 를 준다
        "Fulham": {},
    }
    table = {name: {"stats": TeamStats(), "url": f"/teams/1/show/{name}"}
             for name in ("Arsenal", "Ipswich", "Fulham")}    # Levante 는 없다

    def fake_read_league(*a, **kw):
        return table

    def fake_read_team(browser, settings, url, canonical, resolver, cache=None):
        return payloads.get(canonical, {})

    def mk(no, home, away):
        match = Match(no=no, league="epl")
        match.home = TeamRef(canonical=home, display=home)
        match.away = TeamRef(canonical=away, display=away)
        return match

    matches = [mk(1, "Arsenal", "Ipswich"), mk(2, "Fulham", "Levante")]
    saved = (whoscored.WhoScoredBrowser, whoscored.read_league,
             whoscored.read_team)
    whoscored.WhoScoredBrowser = FakeBrowser          # type: ignore[assignment]
    whoscored.read_league = fake_read_league          # type: ignore[assignment]
    whoscored.read_team = fake_read_team              # type: ignore[assignment]
    try:
        whoscored.enrich(matches, load_settings(), TeamResolver())
    finally:
        (whoscored.WhoScoredBrowser, whoscored.read_league,
         whoscored.read_team) = saved

    got = {}
    for match in matches:
        for side in ("home", "away"):
            profile = getattr(match, f"{side}_profile")
            got[profile.team.canonical] = (
                profile.team_page_ok,
                characteristic_status(profile.strengths, profile.team_page_ok))
    assert got == {
        "Arsenal": (True, CHAR_OK),                 # 정상
        "Ipswich": (True, CHAR_OBSERVED_EMPTY),     # 읽었는데 강점이 없다
        "Fulham": (False, CHAR_PAGE_FAILED),        # 페이지를 못 읽었다
        "Levante": (False, CHAR_PAGE_FAILED),       # 표에 팀이 없다
    }, got


# ==========================================================================
# D·E. 호환성
# ==========================================================================
def test_d1_existing_profile_construction_still_works():
    """Test D — 기존 방식으로 만든 TeamProfile 이 그대로 돈다."""
    profile = TeamProfile(team=TeamRef(canonical="Arsenal"), league="epl")
    assert profile.strengths == [] and profile.weaknesses == []
    assert profile.style_of_play == []
    assert profile.source_ok is False
    assert profile.team_page_ok is None, "새 칸의 기본값이 None 이 아니다"
    profile.strengths = ["Aerial duels · Strong"]
    assert isinstance(profile.strengths, list)
    assert isinstance(profile.strengths[0], str), "타입이 바뀌었다"


def test_d2_public_fields_keep_their_type():
    """`strengths` 를 구조체 목록으로 바꾸지 않았다 (§9).

    바꿨으면 `analyze`·`render`·`match_material` 이 전부 깨진다.
    """
    hints = {f.name: f.type for f in fields(TeamProfile)}
    for slot in ("strengths", "weaknesses", "style_of_play"):
        assert "list[str]" in str(hints[slot]), f"{slot}: {hints[slot]}"


def test_d3_field_order_is_not_shuffled():
    """앞쪽 필드 자리가 밀리지 않았다 — 위치 인자로 만드는 코드가 없더라도
    저장본의 키 순서가 바뀌면 대조가 흔들린다."""
    names = [f.name for f in fields(TeamProfile)]
    head = ["team", "league", "stats", "strengths", "weaknesses",
            "style_of_play", "form", "missing_players"]
    assert names[:len(head)] == head, names[:len(head)]
    assert "team_page_ok" in names
    assert names.index("team_page_ok") == names.index("source_ok") + 1


def test_e1_old_artifact_revives_without_the_new_field():
    """Test E — 새 칸이 없는 저장본도 읽힌다."""
    from toto.models import _revive_profile
    old = {"team": {"canonical": "Arsenal"}, "league": "epl",
           "strengths": ["Aerial duels · Strong"], "weaknesses": [],
           "source_ok": True}
    profile = _revive_profile(old)
    assert profile is not None
    assert profile.team_page_ok is None, profile.team_page_ok
    assert profile.source_ok is True
    assert profile.strengths == ["Aerial duels · Strong"]


def test_e2_missing_is_not_turned_into_false():
    """`None` 을 `False` 로 바꾸지 않는다 — 기록 없음과 실패는 다르다 (§1-5)."""
    from toto.models import _revive_profile
    for value, want in ((None, None), (True, True), (False, False)):
        payload = {"team": {"canonical": "A"}}
        if value is not None:
            payload["team_page_ok"] = value
        profile = _revive_profile(payload)
        assert profile.team_page_ok is want, (value, profile.team_page_ok)


def test_e3_asdict_roundtrip_preserves_everything():
    profile = TeamProfile(team=TeamRef(canonical="Arsenal"), league="epl")
    profile.strengths = ["Attacking down the wings · Very Strong"]
    profile.weaknesses = ["Aerial duels · Weak"]
    profile.team_page_ok = True
    from toto.models import _revive_profile
    back = _revive_profile(json.loads(json.dumps(asdict(profile), default=str)))
    assert back.strengths == profile.strengths
    assert back.weaknesses == profile.weaknesses
    assert back.team_page_ok is True


def test_e4_real_artifact_still_loads():
    """Test E (실물) — 260052 저장본이 그대로 읽힌다."""
    report = _artifact()
    if report is None:
        return
    assert len(report.matches) == 14, len(report.matches)
    assert report.round_id == "260052", report.round_id
    profiles = list(_profiles(report))
    assert len(profiles) == 28, len(profiles)


def test_e5_versions_were_not_bumped():
    """직렬화 출력이 바뀐 것이 없으므로 판을 올리지 않았다 (§19).

    `read_team` 의 payload 도 리그 캐시도 한 칸도 바뀌지 않았다.
    저장본은 선택 칸 하나가 늘었을 뿐이라 옛 파일이 그대로 읽힌다 —
    6-D-9B 가 `previous_*` 셋을 더할 때와 같은 경우다.
    """
    assert whoscored._TEAM_CACHE_VERSION == 1, whoscored._TEAM_CACHE_VERSION
    assert whoscored._LEAGUE_CACHE_VERSION == 3, whoscored._LEAGUE_CACHE_VERSION
    assert artifact.ARTIFACT_VERSION == 1, artifact.ARTIFACT_VERSION


def test_e6_read_team_payload_shape_is_unchanged():
    """캐시에 저장되는 모양이 그대로다."""
    src = _src(whoscored.read_team)
    for key in ('"_v"', '"strengths"', '"weaknesses"', '"style"',
                '"form"', '"missing"'):
        assert key in src, key
    tree = ast.parse(src)
    payload_keys = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)
                and any(getattr(t, "id", "") == "payload" for t in node.targets)):
            payload_keys = [k.value for k in node.value.keys]
    assert payload_keys == ["_v", "strengths", "weaknesses", "style",
                            "form", "missing"], payload_keys


# ==========================================================================
# F. 불변 — 이 Phase 가 건드리지 않기로 한 것
# ==========================================================================
def test_f1_matchup_reads_the_layer_but_does_not_reimplement_it():
    """6-E-2 때 이 테스트는 **범위 선언**이었다 — "관계 판정은 6-E-3 소관".

    6-E-3 이 바로 그것을 하는 Phase 라 범위를 옮긴다 (§1-29·§1-31 의 선례).
    지키려던 것은 '6-E-2 계층을 베끼지 않는다' 이므로 그것만 남긴다 —
    상성 경로는 이제 `relationships` 를 **부르되** 파싱·상태 판정을 다시
    구현하지 않는다.
    """
    src = _src(analyze.build_matchup)
    assert "relationships." in src, "상성이 관계 엔진을 부르지 않는다"
    for word in ("parse_characteristic", "characteristic_status",
                 "team_page_ok", 'split(" · "', 'rsplit(" · "'):
        assert word not in src, f"6-E-2 계층을 베꼈다: {word}"


def test_f2_topic_tables_are_pinned():
    """`_TOPICS`·`_TOPIC_KO` 가 한 글자도 바뀌지 않았다."""
    blob = json.dumps([analyze._TOPICS, analyze._TOPIC_KO],
                      ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    assert digest == "e4e6ea5e47c647ef", digest
    assert len(analyze._TOPICS) == 14, len(analyze._TOPICS)


def test_f3_stored_artifact_keeps_the_notes_it_was_saved_with():
    """**저장본은 다시 계산되지 않는다** (§1-25).

    6-E-2 때 이 테스트는 상성 18건의 해시를 고정해 '관계 판정을 건드리지
    않았다' 를 말했다. 6-E-3 이 판정을 고쳐 **재계산하면 17건**이 되지만,
    저장본을 읽는 경로는 그때 적힌 값을 그대로 되살린다 — 그 사실이 이제
    이 테스트가 지키는 것이다. 재계산 결과는
    `tests/test_relationship_engine.py` 의 G절이 대조한다.
    """
    report = _artifact()
    if report is None:
        return
    notes = [n for m in report.matches for n in (m.matchup_notes or [])]
    assert len(notes) == 18, len(notes)
    blob = json.dumps(notes, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    assert digest == "14cb515b42825f2d", digest


def test_f4_real_round_h2h_is_unchanged():
    """Test — H2H 는 6-E-2 범위 밖이다."""
    report = _artifact()
    if report is None:
        return
    total = sum(len(m.h2h.entries) for m in report.matches)
    assert total == 0, total
    assert all(m.h2h.home_wins == m.h2h.draws == m.h2h.away_wins == 0
               for m in report.matches)


def test_f5_real_round_market_probabilities_are_unchanged():
    """시장 확률·배당이 그대로다 (`predict.py` 무변경)."""
    report = _artifact()
    if report is None:
        return
    rows = [[m.no,
             m.odds.home, m.odds.draw, m.odds.away,
             None if m.probs is None else m.probs.home,
             None if m.probs is None else m.probs.draw,
             None if m.probs is None else m.probs.away]
            for m in report.matches]
    blob = json.dumps(rows, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    assert digest == "e9134ccb133ab5ef", digest


def test_f6_real_round_six_axes_are_unchanged():
    """Test H — 저장본의 여섯 축이 한 칸도 바뀌지 않았다."""
    report = _artifact()
    if report is None:
        return
    from toto.models import TeamAnalysis
    dump = []
    for match in report.matches:
        analysis = match.analysis
        if analysis is None:
            continue
        for side in ("home", "away"):
            team = getattr(analysis, side)
            if team is None:
                continue
            for axis_name in TeamAnalysis.AXES:
                axis = getattr(team, axis_name)
                dump.append([match.no, side, axis_name,
                             None if axis is None
                             else json.loads(json.dumps(asdict(axis),
                                                        default=str))])
    blob = json.dumps(dump, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    assert digest == "b8f7faba96cbd3ff", digest


# ==========================================================================
# G. 범위 — 전달 경로는 6-E-4 소관이다
# ==========================================================================
def test_g1_delivery_path_modules_do_not_use_the_new_layer():
    """`render`·`match_material`·`panel`·`menu`·`moderator` 무변경.

    이 Phase 는 데이터/모델 계층이다. 화면과 경기자료에 새 정보를 흘려보내는
    것은 6-E-4 이고, 그때 회귀 기준(바이트)이 함께 움직인다.
    """
    for mod in ("render.py", "match_material.py", "panel.py", "menu.py",
                "moderator.py", "panelexport.py"):
        text = (ROOT / "toto" / mod).read_text(encoding="utf-8")
        for word in ("parse_characteristic", "characteristic_status",
                     "Characteristic", "team_page_ok", "CHAR_OK"):
            assert word not in text, f"{mod}: {word}"


def test_g2_probability_and_axis_modules_are_untouched():
    for mod in ("predict.py", "analysis.py", "evidence.py", "xpts.py"):
        text = (ROOT / "toto" / mod).read_text(encoding="utf-8")
        for word in ("parse_characteristic", "characteristic_status",
                     "Characteristic", "team_page_ok"):
            assert word not in text, f"{mod}: {word}"


def test_g3_no_style_of_play_analysis_was_added():
    """스타일은 실물 0/28 이라 이 Phase 에서 분석에 쓰지 않는다 (§8)."""
    from toto import models
    for fn in (models.parse_characteristic, models.characteristics,
               models.characteristic_status):
        src = _src(fn)
        for word in ("style_of_play", "style"):
            assert word not in src, f"{fn.__name__}: {word}"


def test_g4_the_new_layer_has_no_relation_logic():
    """관계 판정·개수 세기·우열 비교가 없다 (6-E-3 소관)."""
    from toto import models
    src = "".join(_src(x) for x in (models.Characteristic,
                                    models.parse_characteristic,
                                    models.characteristics,
                                    models.characteristic_status))
    for word in ("opponent", "matchup", "relation", "pair", "advantage",
                 "stronger", "score(", "count("):
        assert word not in src, word


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
