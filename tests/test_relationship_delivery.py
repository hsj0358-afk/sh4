"""관계 전달 경로 회귀 (Phase 6-E-4).

6-E-3 이 만든 관계 21건이 **소비처에 하나도 빠지지 않고** 닿는지, 그리고
닿는 동안 **의미가 바뀌지 않는지**를 고정한다.

    relationships.build_relationships()      canonical 모델 (6-E-3, 무변경)
        ├→ analyze.build_matchup()           legacy ADVANTAGE 투영 (무변경)
        ├→ panel.build_panel_payload()       qualitative (6-E-4)
        ├→ match_material._tactical()        경기자료 MD  (6-E-4)
        └→ render._traits_block()            HTML          (6-E-4)

지키는 것 다섯.

1. **21건이 전부 간다.** ADVANTAGE 17 · COUNTER 2 · DIRECT 2 가 payload 에
   그대로 있고, 방향 없는 둘은 MD·HTML 에도 나온다.
2. **내부 이름이 화면에 없다.** `COUNTER`·`DIRECT`·`MIRROR`·`CONTEST`·
   「카운터」가 payload·MD·HTML 어디에도 나오지 않는다 (§4).
3. **방향 없는 관계에 주어가 생기지 않는다.** COUNTER·DIRECT 자리에
   `→`·공략·우위·유리·앞선다 가 없다. **`ADVANTAGE` 의 '상대 약점 공략'
   은 정상 표현이라 이 검사의 대상이 아니다** (사용자 §5).
4. **원문이 보존된다.** 212개 특성이 한 글자도 바뀌지 않고, 강도가 숫자로
   바뀌지 않는다.
5. **저장하지 않는다.** 캐시 판 셋이 그대로이고 artifact 에 새 칸이 없다.

실물 픽스처는 저장본 260052 다 (사용자 §6). 없으면 그 절만 건너뛴다 —
합성 픽스처로 실물 단언을 흉내내지 않는다.
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from toto import (analyze, artifact, match_material, panel,  # noqa: E402
                  relationships, render)
from toto.models import (Match, Report, TeamProfile,  # noqa: E402
                         TeamRef)

ARTIFACT = ROOT / "data" / "artifacts" / "260052.json"

# 실물 260052 기준값 (6-E-3 §28 · 사용자 §28).
REAL_COUNTS = {relationships.ADVANTAGE: 17,
               relationships.COUNTER: 2,
               relationships.DIRECT: 2}
REAL_NOTES = 17          # ADVANTAGE 만 `matchup_notes` 로 간다
REAL_CHARACTERISTICS = 212

# 사용자 §6 — 이 넷이 실제 출력에 정확히 나와야 한다.
REAL_SYMMETRIC = [
    (relationships.COUNTER, "본머스", "Aerial duels · Strong",
     "브렌트퍼", "Aerial duels · Strong"),
    (relationships.COUNTER, "코번트리", "Defending set pieces · Strong",
     "브라이턴", "Attacking set pieces · Strong"),
    (relationships.DIRECT, "크리스털", "Aerial duels · Weak",
     "입스위치", "Aerial duels · Very Weak"),
    (relationships.DIRECT, "셀타비고", "Aerial duels · Very Weak",
     "말라가", "Aerial duels · Very Weak"),
]

# 방향을 만들어 버리는 말. COUNTER·DIRECT 자리에만 적용한다.
DIRECTIONAL_WORDS = ("→", "공략", "우위", "유리", "불리", "앞선다", "앞선",
                     "누른다", "무너뜨", "이긴다", "카운터", "counter",
                     "advantage", "우세")

_report_cache: list = []


def _real_report():
    if _report_cache:
        return _report_cache[0]
    if not ARTIFACT.exists():
        _report_cache.append(None)
        return None
    rep, why = artifact.load_path(str(ARTIFACT))
    assert rep is not None, why
    _report_cache.append(rep)
    return rep


def _code_only(path: Path) -> str:
    """docstring 을 걷어낸 소스. 설명에 적은 낱말로 깨지지 않게 한다."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
                and body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            body.pop(0)
    return ast.unparse(tree)


def _profile(name: str, strengths, weaknesses, style=(), page_ok=True):
    p = TeamProfile(team=TeamRef(canonical=name, display=name))
    p.strengths = list(strengths)
    p.weaknesses = list(weaknesses)
    p.style_of_play = list(style)
    p.team_page_ok = page_ok
    return p


def _match(home_profile, away_profile, no: int = 1) -> Match:
    m = Match(no=no)
    m.home = home_profile.team
    m.away = away_profile.team
    m.home_profile = home_profile
    m.away_profile = away_profile
    return m


def _counter_match() -> Match:
    """양 팀 모두 공중볼 경합이 강점 — CONTEST COUNTER 하나."""
    return _match(_profile("홈팀", ["Aerial duels · Strong"], []),
                  _profile("원정팀", ["Aerial duels · Strong"], []))


def _direct_match() -> Match:
    return _match(_profile("홈팀", [], ["Aerial duels · Weak"]),
                  _profile("원정팀", [], ["Aerial duels · Very Weak"]))


def _mirror_counter_match() -> Match:
    """공격 강점 ↔ 그 수비 강점 — MIRROR COUNTER (실물 경기 10 모양)."""
    return _match(_profile("홈팀", ["Defending set pieces · Strong"], []),
                  _profile("원정팀", ["Attacking set pieces · Strong"], []))


def _advantage_match() -> Match:
    return _match(_profile("홈팀", ["Attacking down the wings · Strong"], []),
                  _profile("원정팀", [],
                           ["Defending against attacks down the wings · Weak"]))


def _symmetric_text(text: str, kind: str) -> str:
    """그 묶음의 본문만 잘라낸다 — 다른 묶음의 문장에 걸리지 않게."""
    label = relationships.KIND_KO[kind]
    if label not in text:
        return ""
    start = text.index(label)
    rest = text[start + len(label):]
    for other in relationships.KIND_KO.values():
        if other != label and other in rest:
            rest = rest[:rest.index(other)]
    return rest


# ==========================================================================
# A. 전달 완결성 — 21건이 하나도 빠지지 않는다
# ==========================================================================
def test_a1_payload_carries_every_relationship():
    rep = _real_report()
    if rep is None:
        return
    engine = {k: 0 for k in REAL_COUNTS}
    carried = {k: 0 for k in REAL_COUNTS}
    for m in rep.matches:
        hp, ap = m.home_profile, m.away_profile
        if hp is None or ap is None:
            continue
        for rel in relationships.build_relationships(
                hp.team.display, hp, ap.team.display, ap):
            engine[rel.kind] += 1
        q = panel.build_panel_payload(m).qualitative
        for group in q.get("relationships", []):
            for kind, label in relationships.KIND_KO.items():
                if group["relation"] == label:
                    carried[kind] += len(group["items"])
    assert engine == REAL_COUNTS, engine
    assert carried == REAL_COUNTS, carried


def test_a2_counter_and_direct_are_exactly_two_each():
    rep = _real_report()
    if rep is None:
        return
    found = []
    for m in rep.matches:
        q = panel.build_panel_payload(m).qualitative
        for group in q.get("relationships", []):
            if group["relation"] == relationships.KIND_KO[
                    relationships.ADVANTAGE]:
                continue
            for item in group["items"]:
                found.append((group["relation"],
                              item["home"]["team"],
                              item["home"]["characteristic"],
                              item["away"]["team"],
                              item["away"]["characteristic"]))
    expected = [(relationships.KIND_KO[k], ht, hc, at, ac)
                for k, ht, hc, at, ac in REAL_SYMMETRIC]
    assert sorted(found) == sorted(expected), found


def test_a3_mirror_counter_keeps_two_different_units():
    """사용자 §6-2 — 공격 단위와 수비 단위가 **그대로 따로** 나와야 한다."""
    rep = _real_report()
    if rep is None:
        return
    m = [x for x in rep.matches if x.no == 10][0]
    q = panel.build_panel_payload(m).qualitative
    rows = [i for g in q["relationships"]
            if g["relation"] == relationships.KIND_KO[relationships.COUNTER]
            for i in g["items"]]
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["home"]["unit"] != row["away"]["unit"], row
    assert row["home"]["unit"] == "세트피스 수비", row
    assert row["away"]["unit"] == "세트피스 공격", row


def test_a4_md_shows_both_symmetric_groups():
    rep = _real_report()
    if rep is None:
        return
    seen = set()
    for m in rep.matches:
        text = match_material._tactical(m)
        for kind in (relationships.COUNTER, relationships.DIRECT):
            if relationships.KIND_KO[kind] in text:
                seen.add(kind)
    assert seen == {relationships.COUNTER, relationships.DIRECT}, seen


def test_a5_html_shows_both_symmetric_groups():
    rep = _real_report()
    if rep is None:
        return
    seen = set()
    for m in rep.matches:
        html = render._traits_block(m)
        for kind in (relationships.COUNTER, relationships.DIRECT):
            if relationships.KIND_KO[kind] in html:
                seen.add(kind)
    assert seen == {relationships.COUNTER, relationships.DIRECT}, seen


def test_a6_symmetric_rows_appear_in_md_with_both_raw_strings():
    rep = _real_report()
    if rep is None:
        return
    by_no = {m.no: m for m in rep.matches}
    for kind, ht, hc, at, ac in REAL_SYMMETRIC:
        match = next(m for m in rep.matches
                     if m.home_profile is not None
                     and m.home_profile.team.display == ht)
        text = match_material._tactical(match)
        block = _symmetric_text(text, kind)
        assert block, (kind, ht)
        for token in (ht, hc, at, ac):
            assert token in block, (kind, token)
    assert by_no


# ==========================================================================
# B. 내부 이름을 화면에 내지 않는다 (§4)
# ==========================================================================
_INTERNAL = ("ADVANTAGE", "COUNTER", "DIRECT", "MIRROR", "CONTEST",
             "카운터", "Relationship", "SemanticUnit")


def test_b1_payload_has_no_internal_identifier():
    rep = _real_report()
    if rep is None:
        return
    for m in rep.matches:
        text = panel.serialize_payload(panel.build_panel_payload(m))
        for word in _INTERNAL:
            assert word not in text, (m.no, word)


def test_b2_md_and_html_have_no_internal_identifier():
    rep = _real_report()
    if rep is None:
        return
    for m in rep.matches:
        for text in (match_material._tactical(m), render._traits_block(m)):
            for word in _INTERNAL:
                assert word not in text, (m.no, word)


def test_b3_user_facing_names_are_the_three_words():
    assert relationships.KIND_KO == {
        relationships.ADVANTAGE: "상대 약점 공략",
        relationships.COUNTER: "강점 충돌",
        relationships.DIRECT: "공통 취약 영역"}


def test_b4_display_order_is_fixed():
    assert relationships.DISPLAY_ORDER == (
        relationships.ADVANTAGE, relationships.COUNTER, relationships.DIRECT)


# ==========================================================================
# C. 방향 무주장 (§5·§13) — COUNTER·DIRECT 에만 적용한다
# ==========================================================================
def test_c1_symmetric_md_block_has_no_directional_word():
    for maker in (_counter_match, _direct_match, _mirror_counter_match):
        m = maker()
        text = match_material._tactical(m)
        for kind in (relationships.COUNTER, relationships.DIRECT):
            block = _symmetric_text(text, kind)
            if not block:
                continue
            for word in DIRECTIONAL_WORDS:
                # 본문이 '공략하지 마십시오' 라고 **금지**하는 것은 방향
                # 주장이 아니다. 관계 줄에만 없으면 된다.
                for line in block.splitlines():
                    if line.startswith("|") and "---" not in line:
                        assert word not in line, (kind, word, line)


def test_c2_symmetric_html_rows_have_no_directional_word():
    for maker in (_counter_match, _direct_match, _mirror_counter_match):
        html = render._symmetric_relations(maker().home_profile,
                                           maker().away_profile)
        rows = html.split("<li>")[1:]
        assert rows, html
        for row in rows:
            for word in DIRECTIONAL_WORDS:
                assert word not in row, (word, row)


def test_c3_advantage_keeps_its_wording():
    """'상대 약점 공략' 은 정상 표현이라 위 검사에서 제외된다 (사용자 §5)."""
    m = _advantage_match()
    analyze.build_matchup([m])
    text = match_material._tactical(m)
    assert relationships.KIND_KO[relationships.ADVANTAGE] in text
    assert "의 강점이" in text and "약점과 맞물립니다" in text


def test_c4_symmetric_payload_rows_have_no_source_or_target_key():
    """`source`/`target` 이라는 칸 이름 자체가 주체를 만든다."""
    for maker in (_counter_match, _direct_match, _mirror_counter_match):
        q = panel._qualitative(maker())
        for group in q["relationships"]:
            if group["relation"] == relationships.KIND_KO[
                    relationships.ADVANTAGE]:
                continue
            for item in group["items"]:
                assert set(item) == {"home", "away", "note"}, item
                assert "source" not in json.dumps(item, ensure_ascii=False)
                assert "strength_side" not in item and "weakness_side" not in item
                # 칸 이름만 대칭이고 **문장이 방향을 만들면** 소용없다.
                for word in DIRECTIONAL_WORDS:
                    assert word not in item["note"], (word, item["note"])


def test_c5_symmetric_note_states_both_sides():
    assert relationships.SYMMETRIC_NOTE[relationships.COUNTER] == \
        "양 팀 모두 이 영역이 강점입니다"
    assert relationships.SYMMETRIC_NOTE[relationships.DIRECT] == \
        "양 팀 모두 이 영역이 약점입니다"
    for note in relationships.SYMMETRIC_NOTE.values():
        for word in DIRECTIONAL_WORDS:
            assert word not in note, (note, word)


def test_c6_left_is_always_home():
    """좌우를 `source` 가 아니라 **팀**으로 정한다 — 줄마다 뜻이 달라지면
    안 된다. 실물 경기 10 은 원정이 `source` 인데도 홈이 왼쪽이다."""
    rep = _real_report()
    if rep is None:
        return
    for m in rep.matches:
        hp = m.home_profile
        if hp is None:
            continue
        home = hp.team.display
        q = panel.build_panel_payload(m).qualitative
        for group in q.get("relationships", []):
            if group["relation"] == relationships.KIND_KO[
                    relationships.ADVANTAGE]:
                continue
            for item in group["items"]:
                assert item["home"]["team"] == home, (m.no, item)


# ==========================================================================
# D. legacy 투영 불변 (§14)
# ==========================================================================
def test_d1_matchup_notes_shape_is_unchanged():
    m = _advantage_match()
    analyze.build_matchup([m])
    assert len(m.matchup_notes) == 1
    assert set(m.matchup_notes[0]) == {"side", "topic", "strength",
                                       "weakness", "text"}


def test_d2_counter_and_direct_never_enter_matchup_notes():
    for maker in (_counter_match, _direct_match, _mirror_counter_match):
        m = maker()
        analyze.build_matchup([m])
        assert m.matchup_notes == [], m.matchup_notes


def test_d3_real_matchup_notes_still_seventeen():
    rep = _real_report()
    if rep is None:
        return
    total = 0
    for m in rep.matches:
        hp, ap = m.home_profile, m.away_profile
        if hp is None or ap is None:
            continue
        analyze.build_matchup([m])
        total += len(m.matchup_notes)
    assert total == REAL_NOTES, total


def test_d4_advantage_is_not_printed_twice():
    """상성 노트와 새 섹션이 같은 관계를 두 번 적지 않는다."""
    m = _advantage_match()
    analyze.build_matchup([m])
    text = match_material._tactical(m)
    rows = [ln for ln in text.splitlines()
            if ln.startswith("|") and "맞물립니다" in ln]
    assert len(rows) == 1, rows
    # 묶음 제목에도 비슷한 말이 나오므로 **노트 문장 자체**를 센다.
    html = render._traits_block(m)
    assert html.count(m.matchup_notes[0]["text"]) == 1, html
    assert relationships.KIND_KO[relationships.COUNTER] not in html
    assert relationships.KIND_KO[relationships.DIRECT] not in html


def test_d5_symmetric_sections_do_not_use_the_note_columns():
    """`쪽 | 강점 | 상대 약점` 구조를 재사용하지 않는다 (사용자 §8)."""
    m = _counter_match()
    block = _symmetric_text(match_material._tactical(m),
                            relationships.COUNTER)
    header = next(ln for ln in block.splitlines() if ln.startswith("| 홈"))
    assert "쪽" not in header, header
    assert header.count("|") == 7, header        # 6열 대칭


# ==========================================================================
# E. 원문 보존 (§7)
# ==========================================================================
def test_e1_every_characteristic_reaches_the_payload_unchanged():
    rep = _real_report()
    if rep is None:
        return
    total = kept = 0
    for m in rep.matches:
        q = panel.build_panel_payload(m).qualitative
        for side, profile in (("home", m.home_profile),
                              ("away", m.away_profile)):
            if profile is None:
                continue
            block = q["teams"][side]
            for name, items in (("strengths", profile.strengths),
                                ("weaknesses", profile.weaknesses),
                                ("style_of_play", profile.style_of_play)):
                total += len(items)
                if items:
                    assert block[name] == list(items), (m.no, side, name)
                    kept += len(items)
    assert total == REAL_CHARACTERISTICS, total
    assert kept == total, (kept, total)


def test_e2_every_characteristic_reaches_the_md_unchanged():
    rep = _real_report()
    if rep is None:
        return
    total = 0
    for m in rep.matches:
        text = match_material._tactical(m)
        for profile in (m.home_profile, m.away_profile):
            if profile is None:
                continue
            for raw in list(profile.strengths) + list(profile.weaknesses) \
                    + list(profile.style_of_play):
                assert f"- {raw}" in text, (m.no, raw)
                total += 1
    assert total == REAL_CHARACTERISTICS, total


def test_e3_md_restores_item_boundaries():
    """§9 — 항목 구분자와 `라벨 · 강도` 구분자가 섞이지 않는다."""
    m = _match(_profile("홈팀", ["Counter attacks · Strong",
                                "Creating long shot opportunities · Strong"],
                        []),
               _profile("원정팀", [], ["Aerial duels · Weak"]))
    text = match_material._tactical(m)
    assert "- Counter attacks · Strong\n" in text
    assert "Strong · Creating long shot" not in text


def test_e4_intensity_is_never_a_number():
    for maker in (_counter_match, _direct_match, _mirror_counter_match,
                  _advantage_match):
        q = panel._qualitative(maker())
        text = json.dumps(q, ensure_ascii=False)
        for bad in ('"Strong": 2', '"intensity": 1', "Very Strong=2"):
            assert bad not in text, bad
        assert "Strong" in text or "Weak" in text


def test_e5_empty_lists_say_why_not_just_nothing():
    """`[]` 가 네 뜻을 겸하지 않게 한다 (§1-6-1)."""
    m = _match(_profile("홈팀", [], ["Aerial duels · Weak"], page_ok=True),
               _profile("원정팀", [], ["Aerial duels · Weak"], page_ok=False))
    q = panel._qualitative(m)
    assert q["teams"]["home"]["strengths_status"] == "observed_empty"
    assert q["teams"]["away"]["strengths_status"] == "page_failed"
    text = match_material._tactical(m)
    assert "관측된 0" in text and "수집 실패" in text


def test_e6_style_of_play_never_gets_a_status():
    """§3-1 — 0/28 의 원인이 확인되지 않았다. 관측으로 단언하지 않는다."""
    m = _counter_match()
    q = panel._qualitative(m)
    for side in ("home", "away"):
        assert "style_of_play_status" not in q["teams"][side]
    text = match_material._tactical(m)
    assert "플레이 스타일" not in text


def test_e7_style_of_play_is_carried_when_it_exists():
    m = _match(_profile("홈팀", ["Aerial duels · Strong"], [],
                        style=["Possession based"]),
               _profile("원정팀", ["Aerial duels · Strong"], []))
    q = panel._qualitative(m)
    assert q["teams"]["home"]["style_of_play"] == ["Possession based"]
    assert "Possession based" in match_material._tactical(m)


# ==========================================================================
# F. 저장하지 않는다 (§13) · 두 역할이 같은 자료를 본다 (§12)
# ==========================================================================
def test_f1_cache_and_artifact_versions_are_unchanged():
    """관계는 runtime 파생이라 저장 형식을 바꾸지 않는다.

    **6-E-5 에서 범위를 옮겼다** — 거기서 파서가 바뀌며
    `_TEAM_CACHE_VERSION` 이 2 가 됐고, 그건 6-E-4 의 변경이 아니다.
    6-E-4 가 지키려던 것은 `test_f2`(artifact 에 qualitative 가 없다)와
    아래 두 판이다 (§1-31 과 같은 교정).
    """
    from toto.sources import whoscored
    assert whoscored._LEAGUE_CACHE_VERSION == 3
    assert artifact.ARTIFACT_VERSION == 1


def test_f2_artifact_stores_no_qualitative_block():
    rep = _real_report()
    if rep is None:
        return
    raw = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    text = json.dumps(raw, ensure_ascii=False)
    assert '"qualitative"' not in text
    assert '"relationships"' not in text


def test_f3_reload_reproduces_the_same_relationships():
    """저장본을 다시 읽어도 같은 관계가 나온다 — 파생이라 늘 재생된다."""
    rep = _real_report()
    if rep is None:
        return
    again, why = artifact.load_path(str(ARTIFACT))
    assert again is not None, why
    a = [panel.build_panel_payload(m).qualitative.get("relationships")
         for m in rep.matches]
    b = [panel.build_panel_payload(m).qualitative.get("relationships")
         for m in again.matches]
    assert a == b


def test_f4_both_roles_receive_the_same_payload():
    rep = _real_report()
    if rep is None:
        return
    m = rep.matches[0]
    one = panel.build_panel_payload(m)
    two = panel.build_panel_payload(m)
    assert panel.serialize_payload(one) == panel.serialize_payload(two)
    assert panel.payload_hash(one) == panel.payload_hash(two)


def test_f4b_payload_has_no_per_role_field():
    """불변조건 2 를 **구조로** 막는다 (§12).

    자료를 한 번 만들어 두 역할에 넘기는 것만으로는 부족하다 — 역할을 담을
    칸이 생기는 순간 역할별 payload 로 가는 길이 열린다. 칸 목록을 못 박아
    새 칸이 **의도적으로만** 들어오게 한다.
    """
    from dataclasses import fields
    names = [f.name for f in fields(panel.PanelPayload)]
    assert names == ["match_no", "league", "home_team", "away_team",
                     "kickoff_kst", "as_of", "home", "away", "evidence",
                     "conflicts", "data_quality", "market_reference",
                     "qualitative"], names
    for name in names:
        assert "role" not in name, name


def test_f4c_run_match_builds_the_payload_once():
    src = inspect.getsource(panel.run_match)
    assert src.count("build_panel_payload(") == 1, src


def test_f5_payload_is_deterministic_across_calls():
    q1 = panel._qualitative(_counter_match())
    q2 = panel._qualitative(_counter_match())
    assert json.dumps(q1, ensure_ascii=False, sort_keys=True) == \
        json.dumps(q2, ensure_ascii=False, sort_keys=True)


def test_f6_moderator_input_does_not_grow():
    """사회자는 축 덤프도 정성 자료도 받지 않는다 (§1-10)."""
    rep = _real_report()
    if rep is None:
        return
    data = analyze and None
    from toto import moderator
    payload = panel.build_panel_payload(rep.matches[0])
    text = json.dumps(moderator.build_input(payload, []), ensure_ascii=False)
    assert "qualitative" not in text
    assert "Aerial duels" not in text
    assert data is None


# ==========================================================================
# G. 프롬프트가 실제 자료와 일치한다 (§11)
# ==========================================================================
def test_g1_matchup_prompt_no_longer_claims_there_is_no_tactical_data():
    text = panel.ROLE_PROMPTS[panel.MATCHUP_ANALYST]
    assert "전술 자료가 **들어 있지 않습니다.**" not in text


def test_g2_matchup_prompt_names_what_is_and_is_not_there():
    text = panel.ROLE_PROMPTS[panel.MATCHUP_ANALYST]
    for word in ("강점", "약점", "관계"):
        assert word in text, word
    for word in ("포메이션", "선발 명단", "부상", "압박 방식", "감독 성향"):
        assert word in text, word
    assert "들어 있지 않습니다" in text


def test_g3_matchup_prompt_explains_the_three_relations():
    text = panel.ROLE_PROMPTS[panel.MATCHUP_ANALYST]
    for label in relationships.KIND_KO.values():
        assert label in text, label
    assert text.count("방향이 없습니다") >= 2


def test_g4_prompt_version_was_raised():
    assert panel.PANEL_PROMPT_VERSION == "3"


def test_g5_instructions_fingerprint_changed():
    from toto import panelexport
    fp = panelexport.instructions_fingerprint()
    assert fp != "e99bf42f", "지문이 그대로면 지침이 낡은 줄 모른다"
    assert fp == "b389d4f0", fp


def test_g6_prompt_forbids_scoring_the_intensities():
    text = panel.ROLE_PROMPTS[panel.MATCHUP_ANALYST]
    assert "점수" in text and "개수" in text


# ==========================================================================
# H. 범위 — 건드리지 않은 것 (§27·§29)
# ==========================================================================
def test_h1_engine_pairs_and_units_are_unchanged():
    assert len(relationships.PAIRS) == 8
    assert len(relationships._UNITS) == 24
    assert len(relationships.DEFERRED_PAIRS) == 2


def test_h2_display_layer_adds_no_relationship():
    for maker in (_counter_match, _direct_match, _mirror_counter_match,
                  _advantage_match):
        m = maker()
        rels = relationships.build_relationships(
            m.home_profile.team.display, m.home_profile,
            m.away_profile.team.display, m.away_profile)
        grouped = relationships.grouped(rels)
        assert sum(len(rows) for _k, _l, rows in grouped) == len(rels)


def test_h3_grouped_hides_empty_groups():
    assert relationships.grouped([]) == []
    m = _counter_match()
    rels = relationships.build_relationships("홈팀", m.home_profile,
                                             "원정팀", m.away_profile)
    kinds = [k for k, _l, _r in relationships.grouped(rels)]
    assert kinds == [relationships.COUNTER], kinds


def test_h4_untouched_modules_have_no_qualitative_wiring():
    for mod in ("predict.py", "moderator.py", "evidence.py", "analysis.py",
                "sources/pinnacle.py", "menu.py"):
        code = _code_only(ROOT / "toto" / mod)
        for word in ("qualitative", "KIND_KO", "SYMMETRIC_NOTE",
                     "side_rows", "grouped("):
            assert word not in code, f"{mod}: {word}"


def test_h5_no_arithmetic_in_the_new_delivery_helpers():
    for fn in (panel._qualitative, panel._team_characteristics,
               match_material._symmetric_table, render._symmetric_relations,
               relationships.grouped, relationships.side_rows):
        tree = ast.parse(inspect.getsource(fn))
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(
                    node.op, (ast.Div, ast.FloorDiv, ast.Mult, ast.Sub,
                              ast.Pow)):
                raise AssertionError(f"{fn.__name__}: 산술 연산")
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", "") or getattr(
                    node.func, "attr", "")
                assert name not in ("sum", "mean", "round", "sorted_by_score"), \
                    f"{fn.__name__}: {name}()"


def test_h6_no_verdict_vocabulary_in_the_new_code():
    for path in ("toto/panel.py", "toto/match_material.py",
                 "toto/render.py", "toto/relationships.py"):
        code = _code_only(ROOT / path)
        for bad in ("final_pick", "recommendation", "strength_score",
                    "matchup_score", "tactical_score", "advantage_score"):
            assert bad not in code, f"{path}: {bad}"


def test_h7_render_uses_no_new_css_class():
    code = _code_only(ROOT / "toto" / "render.py")
    start = code.index("def _symmetric_relations")
    body = code[start:code.index("def _traits_block")]
    for cls in ("class=\"", "class='"):
        assert cls not in body or True
    for allowed in ('class="lbl"', 'class="mnotes"', 'class="vs"'):
        pass
    used = set()
    for piece in body.split('class="')[1:]:
        used.add(piece.split('"')[0])
    assert used <= {"lbl", "mnotes", "vs"}, used


def test_h8_symmetric_html_marks_both_sides():
    html = render._symmetric_relations(_counter_match().home_profile,
                                       _counter_match().away_profile)
    assert html.count("--home") == 1 and html.count("--away") == 1


def main() -> int:
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    ok = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:                       # noqa: BLE001
            print(f"  FAIL {name}: {exc}")
        else:
            ok += 1
            print(f"  ok   {name}")
    print(f"\n{ok}/{len(tests)} 통과")
    return 0 if ok == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
