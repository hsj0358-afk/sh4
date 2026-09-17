"""정성 특성 관계 엔진 (Phase 6-E-3).

6-E-2 가 원문을 손실 없이 구조화했고, 이 Phase 는 그 위에서 **어떤 특성이
어떤 특성과 맞물리는가**를 정한다.

**고치는 것은 의미 단위다.** 옛 `analyze._TOPICS` 는 키워드 부분일치라
`set piece` 가 공격·수비 라벨에 동시에 걸리고 `scoring` 이 창출·마무리에
동시에 걸렸다. 실물 260052 에서 18건 중 6건이 그래서 틀렸다.

```
Defending set pieces × Defending set pieces      ← 양쪽 다 수비. 공이 흐르지 않는다
Creating scoring chances × Finishing scoring chances  ← 창출 ≠ 마무리
Finishing scoring chances × Finishing scoring chances ← 자기 마무리끼리
```

동시에 자명한 짝을 놓쳤다 — `Creating chances through individual skill` 의
짝인 `Defending against skillful players` 가 어떤 주제에도 매핑되지 않았다.

**라벨 하나당 단위 하나**로 두면 그 병합이 구조적으로 불가능하다. 짝은
**라벨 문구가 스스로 말하는 것만** 등록한다.

pytest 없이도 돈다:  python tests/test_relationship_engine.py
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from toto import analyze, artifact, relationships                  # noqa: E402
from toto.models import (Characteristic, TeamProfile, TeamRef,     # noqa: E402
                         characteristics, parse_characteristic)

ARTIFACT = ROOT / "data" / "artifacts" / "260052.json"

# 실물 260052 의 고유 라벨 24종. **여기 없는 낱말로 fixture 를 만들지 않는다**
# (§15) — 가상 축구 용어를 지어내면 엔진이 실제 어휘와 맞는지 알 수 없다.
REAL_STRENGTH_LABELS = (
    "Aerial duels", "Attacking down the wings", "Attacking set pieces",
    "Coming back from losing positions", "Counter attacks",
    "Creating chances through individual skill",
    "Creating chances using through balls", "Creating long shot opportunities",
    "Creating scoring chances", "Defending set pieces",
    "Finishing scoring chances", "Protecting the lead",
    "Shooting from direct free kicks", "Stealing the ball from the opposition",
)
REAL_WEAKNESS_LABELS = (
    "Aerial duels", "Avoiding fouling in dangerous areas",
    "Avoiding individual errors", "Avoiding offside",
    "Defending against attacks down the wings", "Defending against long shots",
    "Defending against skillful players",
    "Defending against through ball attacks", "Defending counter attacks",
    "Defending set pieces", "Finishing scoring chances",
    "Keeping possession of the ball", "Protecting the lead",
    "Stopping opponents from creating chances",
)
REAL_INTENSITIES = ("Strong", "Very Strong", "Weak", "Very Weak")


def _artifact():
    if not ARTIFACT.exists():
        return None
    report, _why = artifact.load_path(ARTIFACT)
    return report


def prof(team: str, strengths=(), weaknesses=()) -> TeamProfile:
    """실측 라벨로만 프로필을 만든다."""
    for label in strengths:
        assert label.rsplit(" · ", 1)[0] in REAL_STRENGTH_LABELS, label
    for label in weaknesses:
        assert label.rsplit(" · ", 1)[0] in REAL_WEAKNESS_LABELS, label
    p = TeamProfile(team=TeamRef(canonical=team, display=team))
    p.strengths = list(strengths)
    p.weaknesses = list(weaknesses)
    return p


def rels(home_s=(), home_w=(), away_s=(), away_w=()):
    return relationships.build_relationships(
        "홈", prof("홈", home_s, home_w), "원정", prof("원정", away_s, away_w))


def _src(obj) -> str:
    return inspect.getsource(obj)


def _file_code_only(path: Path) -> str:
    """파일 하나에서 docstring 을 걷어낸 소스. `_code_only` 의 경로판."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
                and body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            body.pop(0)
    return ast.unparse(tree)


def _code_only(obj) -> str:
    """docstring 을 걷어낸 소스.

    설명에 낱말이 나왔다고 '코드가 그것을 쓴다' 고 판정하면, 규칙을 적어 둔
    문단 때문에 테스트가 깨진다 (6-E-2 의 같은 헬퍼와 같은 이유).
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
# A. 의미 단위 매핑
# ==========================================================================
def test_a1_every_real_label_has_a_unit():
    """실측 24개 라벨이 전부 단위 표에 있다."""
    missing = [l for l in set(REAL_STRENGTH_LABELS) | set(REAL_WEAKNESS_LABELS)
               if relationships.unit_of(l) is None]
    assert missing == [], missing


def test_a2_one_unit_per_label():
    """라벨 하나당 단위 하나 — 키도 라벨도 겹치지 않는다."""
    units = list(relationships.UNITS.values())
    assert len(units) == 24, len(units)
    keys = [u.key for u in units]
    labels = [u.label for u in units]
    assert len(set(keys)) == len(keys), "단위 키가 겹친다"
    assert len(set(labels)) == len(labels), "라벨이 겹친다"


def test_a3_unit_table_has_no_invented_label():
    """관측하지 않은 라벨을 표에 넣지 않았다 (§4)."""
    real = set(REAL_STRENGTH_LABELS) | set(REAL_WEAKNESS_LABELS)
    extra = sorted(set(relationships.UNITS) - real)
    assert extra == [], extra


def test_a4_set_piece_attack_and_defence_are_separate_units():
    """§5-1 — 세트피스 공격/수비가 **다른 단위**다."""
    atk = relationships.unit_of("Attacking set pieces")
    dfn = relationships.unit_of("Defending set pieces")
    assert atk.key != dfn.key, atk.key
    assert atk.role == relationships.ATTACKING, atk.role
    assert dfn.role == relationships.DEFENDING, dfn.role


def test_a5_chance_creation_and_finishing_are_separate_units():
    """§5-2 — 기회 창출과 마무리가 **다른 단위**다."""
    create = relationships.unit_of("Creating scoring chances")
    finish = relationships.unit_of("Finishing scoring chances")
    assert create.key != finish.key, create.key
    assert create.role == relationships.ATTACKING, create.role
    # 마무리는 상대와의 관계를 라벨이 말하지 않는다.
    assert finish.role == relationships.OWN, finish.role


def test_a6_own_units_have_no_pair():
    """짝 없음으로 분류한 단위는 짝 표 어디에도 없다."""
    paired = {k for a, d, _ in relationships.PAIRS for k in (a, d)}
    for unit in relationships.UNITS.values():
        if unit.role == relationships.OWN:
            assert unit.key not in paired, unit.key


def test_a7_every_pair_links_attacking_to_defending():
    by_key = {u.key: u for u in relationships.UNITS.values()}
    assert len(relationships.PAIRS) == 8, len(relationships.PAIRS)
    for atk, dfn, why in relationships.PAIRS:
        assert by_key[atk].role == relationships.ATTACKING, atk
        assert by_key[dfn].role == relationships.DEFENDING, dfn
        assert why.strip(), f"{atk}: 등록 근거가 비었다"


def test_a8_deferred_pairs_are_recorded_not_registered():
    """등록하지 않은 후보는 사유와 함께 남아 있고, 짝 표에는 없다."""
    registered = {(a, d) for a, d, _ in relationships.PAIRS}
    assert relationships.DEFERRED_PAIRS, "미룬 후보 기록이 사라졌다"
    for a, d, why in relationships.DEFERRED_PAIRS:
        assert (a, d) not in registered, (a, d)
        assert why.strip(), f"{a}→{d}: 사유가 비었다"


def test_a9_unknown_label_is_reported_not_swallowed():
    """표에 없는 라벨이 조용히 빠지지 않는다 (§1-6-1)."""
    p = TeamProfile(team=TeamRef(canonical="X"))
    p.strengths = ["Pressing intensity · Strong", "Aerial duels · Strong"]
    got = relationships.unknown_labels(p)
    assert got == ["Pressing intensity"], got
    assert relationships.unknown_labels(None) == []


# ==========================================================================
# B. 방향
# ==========================================================================
def test_b1_source_is_the_strength_holder():
    out = rels(home_s=["Attacking set pieces · Strong"],
               away_w=["Defending set pieces · Weak"])
    assert len(out) == 1, out
    r = out[0]
    assert r.source_team == "홈" and r.target_team == "원정"
    assert r.source_characteristic.label == "Attacking set pieces"
    assert r.target_characteristic.label == "Defending set pieces"
    assert r.kind == relationships.ADVANTAGE
    assert r.directional is True


def test_b2_reverse_side_is_reported_as_reverse():
    out = rels(home_w=["Defending set pieces · Weak"],
               away_s=["Attacking set pieces · Very Strong"])
    assert len(out) == 1, out
    r = out[0]
    assert r.source_team == "원정" and r.target_team == "홈"
    assert r.source_characteristic.intensity == "Very Strong"


def test_b3_mirror_never_runs_defence_to_attack():
    """수비 라벨이 source 가 되는 MIRROR 관계는 만들지 않는다."""
    out = rels(home_s=["Defending set pieces · Strong"],
               away_s=["Attacking set pieces · Strong"])
    for r in out:
        if r.basis == relationships.MIRROR:
            assert r.source_unit.role == relationships.ATTACKING, r.source_unit.key


def test_b4_direction_survives_both_teams_having_the_pair():
    """양 팀이 서로의 짝을 가지면 **두 방향이 각각** 나온다."""
    out = rels(home_s=["Attacking down the wings · Strong"],
               home_w=["Defending against attacks down the wings · Weak"],
               away_s=["Attacking down the wings · Very Strong"],
               away_w=["Defending against attacks down the wings · Very Weak"])
    adv = [r for r in out if r.kind == relationships.ADVANTAGE]
    assert len(adv) == 2, adv
    assert {r.source_team for r in adv} == {"홈", "원정"}


# ==========================================================================
# C. 관계 성립
# ==========================================================================
def test_c1_every_registered_pair_fires():
    """등록된 8쌍이 각각 실제로 관계를 만든다."""
    by_key = {u.key: u for u in relationships.UNITS.values()}
    for atk, dfn, _why in relationships.PAIRS:
        out = rels(home_s=[f"{by_key[atk].label} · Strong"],
                   away_w=[f"{by_key[dfn].label} · Weak"])
        assert len(out) == 1, (atk, dfn, out)
        assert out[0].kind == relationships.ADVANTAGE, (atk, dfn)
        assert out[0].basis == relationships.MIRROR, (atk, dfn)


def test_c2_contested_unit_fires_on_the_same_label():
    out = rels(home_s=["Aerial duels · Strong"], away_w=["Aerial duels · Very Weak"])
    assert len(out) == 1, out
    r = out[0]
    assert r.basis == relationships.CONTEST
    assert r.source_unit.key == r.target_unit.key == "aerial_duel"
    assert r.kind == relationships.ADVANTAGE
    assert r.source_team == "홈"


def test_c3_strength_meets_strength_is_counter():
    out = rels(home_s=["Attacking set pieces · Strong"],
               away_s=["Defending set pieces · Strong"])
    assert len(out) == 1 and out[0].kind == relationships.COUNTER, out
    assert out[0].directional is False


def test_c4_weakness_meets_weakness_is_direct():
    out = rels(home_w=["Aerial duels · Weak"], away_w=["Aerial duels · Very Weak"])
    assert len(out) == 1 and out[0].kind == relationships.DIRECT, out
    assert out[0].directional is False


def test_c5_evidence_names_both_characteristics():
    out = rels(home_s=["Attacking down the wings · Strong"],
               away_w=["Defending against attacks down the wings · Weak"])
    ev = out[0].evidence
    assert "홈" in ev and "원정" in ev, ev
    assert out[0].source_unit.ko in ev and out[0].target_unit.ko in ev, ev
    # 유리/불리를 매기지 않는다 (§1-3).
    for banned in ("유리", "불리", "우세", "열세", "추천", "승", "패"):
        assert banned not in ev, (banned, ev)


def test_c6_relationship_keeps_the_source_characteristic_object():
    out = rels(home_s=["Counter attacks · Very Strong"],
               away_w=["Defending counter attacks · Very Weak"])
    r = out[0]
    assert isinstance(r.source_characteristic, Characteristic)
    assert r.source_characteristic.raw == "Counter attacks · Very Strong"
    assert r.target_characteristic.raw == "Defending counter attacks · Very Weak"


# ==========================================================================
# D. 근거 없는 관계를 만들지 않는다  ← 이 Phase 가 고치는 6건
# ==========================================================================
def test_d1_defence_against_defence_is_not_a_relationship():
    """실물 5·10번 — 양쪽 다 수비다. 공이 흐르지 않는다."""
    out = rels(home_s=["Defending set pieces · Strong"],
               away_w=["Defending set pieces · Weak"])
    assert out == [], out


def test_d2_creating_is_not_finishing():
    """실물 6·7번 — 기회 창출과 마무리는 다른 단위다."""
    out = rels(home_s=["Creating scoring chances · Strong"],
               away_w=["Finishing scoring chances · Very Weak"])
    assert out == [], out


def test_d3_finishing_against_finishing_is_not_a_relationship():
    """실물 8·13번 — 자기 마무리끼리는 상호작용이 아니다."""
    out = rels(home_s=["Finishing scoring chances · Strong"],
               away_w=["Finishing scoring chances · Weak"])
    assert out == [], out


def test_d4_own_units_never_produce_relationships():
    """짝 없음으로 분류한 단위는 어떤 조합에서도 관계를 만들지 않는다."""
    own = [u for u in relationships.UNITS.values()
           if u.role == relationships.OWN]
    assert own, "OWN 단위가 사라졌다"
    for unit in own:
        s_ok = unit.label in REAL_STRENGTH_LABELS
        w_ok = unit.label in REAL_WEAKNESS_LABELS
        if s_ok and w_ok:
            assert rels(home_s=[f"{unit.label} · Strong"],
                        away_w=[f"{unit.label} · Weak"]) == [], unit.key
        if s_ok:
            assert rels(home_s=[f"{unit.label} · Strong"],
                        away_s=[f"{unit.label} · Strong"]
                        if s_ok else []) == [], unit.key


def test_d5_unrelated_labels_make_nothing():
    out = rels(home_s=["Protecting the lead · Strong"],
               away_w=["Avoiding offside · Weak"])
    assert out == [], out


def test_d6_empty_profiles_make_nothing():
    assert rels() == []
    assert relationships.build_relationships("A", None, "B", None) == []
    assert relationships.build_relationships(
        "A", prof("A", ["Aerial duels · Strong"]), "B", None) == []


def test_d7_deferred_candidates_do_not_fire():
    """미뤄 둔 두 후보는 관계를 만들지 않는다 (§4 — 추론으로 잇지 않는다)."""
    assert rels(home_s=["Coming back from losing positions · Strong"],
                away_w=["Protecting the lead · Weak"]) == []
    assert rels(home_s=["Shooting from direct free kicks · Strong"],
                away_w=["Avoiding fouling in dangerous areas · Very Weak"]) == []


# ==========================================================================
# E. 강도 — 원문 보존 · 숫자 변환 없음
# ==========================================================================
def test_e1_all_four_intensities_survive_verbatim():
    for intensity in ("Strong", "Very Strong"):
        for weak in ("Weak", "Very Weak"):
            out = rels(home_s=[f"Attacking set pieces · {intensity}"],
                       away_w=[f"Defending set pieces · {weak}"])
            assert out[0].source_characteristic.intensity == intensity
            assert out[0].target_characteristic.intensity == weak
            assert out[0].source_characteristic.raw.endswith(intensity)


def test_e2_no_numeric_conversion_of_intensity():
    """`Very Strong=2` 류의 환산이 없다 (§9)."""
    src = _src(relationships)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if (isinstance(k, ast.Constant) and isinstance(k.value, str)
                        and k.value in REAL_INTENSITIES):
                    raise AssertionError(f"강도를 값에 매핑했다: {k.value}")
    for word in ("intensity_score", "strength_score", "rank_intensity",
                 "INTENSITY_ORDER", "weight"):
        assert word not in src, word


def test_e3_intensity_vocabulary_is_not_hardcoded():
    """강도 낱말로 분기하지 않는다 — 엔진은 슬롯(강점/약점)으로만 가른다."""
    code = ast.unparse(ast.parse(_src(relationships.build_relationships)))
    for word in REAL_INTENSITIES:
        assert word not in code, word


def test_e4_engine_reuses_the_6e2_parser():
    """자체 파서를 만들지 않는다 (§1-8)."""
    src = _src(relationships)
    assert "characteristics(" in src, "6-E-2 파서를 쓰지 않는다"
    assert 'split(" · "' not in src and 'rsplit(" · "' not in src


# ==========================================================================
# F. 결정성
# ==========================================================================
def _many():
    return dict(
        home_s=["Attacking set pieces · Strong", "Aerial duels · Strong",
                "Attacking down the wings · Very Strong",
                "Creating scoring chances · Strong"],
        home_w=["Defending against through ball attacks · Weak",
                "Keeping possession of the ball · Very Weak"],
        away_s=["Creating chances using through balls · Strong",
                "Stealing the ball from the opposition · Strong"],
        away_w=["Defending set pieces · Weak", "Aerial duels · Very Weak",
                "Defending against attacks down the wings · Weak",
                "Stopping opponents from creating chances · Weak"])


def _key(out):
    return [(r.source_team, r.source_unit.key, r.target_team,
             r.target_unit.key, r.kind, r.basis) for r in out]


def test_f1_same_input_same_output():
    assert _key(rels(**_many())) == _key(rels(**_many()))


def test_f2_input_order_does_not_change_the_result():
    """목록 순서를 바꿔도 같은 관계 집합이 나온다."""
    base = _key(rels(**_many()))
    shuffled = {k: list(reversed(v)) for k, v in _many().items()}
    assert sorted(_key(rels(**shuffled))) == sorted(base)


def test_f3_output_order_follows_the_registry_not_a_set():
    """순서가 등록 표를 따른다 — 집합·사전 순서에 기대지 않는다."""
    out = rels(**_many())
    order = [a for a, _d, _w in relationships.PAIRS]
    mirror = [r.source_unit.key for r in out
              if r.basis == relationships.MIRROR]
    assert mirror == [k for k in order if k in mirror], mirror
    # 대칭 경합은 MIRROR 뒤에 온다.
    kinds = [r.basis for r in out]
    assert kinds == sorted(kinds, key=lambda b: 0 if b == relationships.MIRROR else 1)


def test_f4_multiple_characteristics_all_resolve():
    out = rels(**_many())
    assert len(out) >= 6, len(out)
    # 같은 (source_unit, target_unit, 방향) 이 두 번 나오지 않는다.
    seen = [(r.source_team, r.source_unit.key, r.target_unit.key) for r in out]
    assert len(set(seen)) == len(seen), seen


def test_f5_relationship_is_frozen():
    r = rels(home_s=["Aerial duels · Strong"], away_w=["Aerial duels · Weak"])[0]
    try:
        r.kind = "바꿔치기"                     # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("Relationship 이 frozen 이 아니다")


# ==========================================================================
# G. 기존 18건 — 실물 old/new
# ==========================================================================
OLD_18 = {
    (1, "away", "Aerial duels", "Aerial duels"),
    (2, "away", "Creating chances using through balls",
     "Defending against through ball attacks"),
    (2, "away", "Attacking set pieces", "Defending set pieces"),
    (5, "home", "Defending set pieces", "Defending set pieces"),
    (5, "away", "Attacking down the wings",
     "Defending against attacks down the wings"),
    (6, "away", "Creating scoring chances", "Finishing scoring chances"),
    (6, "away", "Attacking set pieces", "Defending set pieces"),
    (7, "home", "Aerial duels", "Aerial duels"),
    (7, "home", "Creating chances using through balls",
     "Defending against through ball attacks"),
    (7, "home", "Creating scoring chances", "Finishing scoring chances"),
    (7, "away", "Attacking down the wings",
     "Defending against attacks down the wings"),
    (8, "home", "Aerial duels", "Aerial duels"),
    (8, "away", "Finishing scoring chances", "Finishing scoring chances"),
    (10, "home", "Defending set pieces", "Defending set pieces"),
    (11, "away", "Attacking set pieces", "Defending set pieces"),
    (13, "away", "Finishing scoring chances", "Finishing scoring chances"),
    (14, "away", "Attacking down the wings",
     "Defending against attacks down the wings"),
    (14, "away", "Creating chances using through balls",
     "Defending against through ball attacks"),
}

# 의미상 틀려서 **사라지는** 6건.
REMOVED = {
    (5, "home", "Defending set pieces", "Defending set pieces"),
    (10, "home", "Defending set pieces", "Defending set pieces"),
    (6, "away", "Creating scoring chances", "Finishing scoring chances"),
    (7, "home", "Creating scoring chances", "Finishing scoring chances"),
    (8, "away", "Finishing scoring chances", "Finishing scoring chances"),
    (13, "away", "Finishing scoring chances", "Finishing scoring chances"),
}

# 옛 주제 표가 매핑하지 못하던 짝 — **새로** 생기는 5건.
ADDED = {
    (6, "away", "Creating scoring chances",
     "Stopping opponents from creating chances"),
    (7, "home", "Creating scoring chances",
     "Stopping opponents from creating chances"),
    (12, "home", "Creating scoring chances",
     "Stopping opponents from creating chances"),
    (12, "away", "Creating chances through individual skill",
     "Defending against skillful players"),
    (13, "away", "Stealing the ball from the opposition",
     "Keeping possession of the ball"),
}


def _new_notes(report):
    analyze.build_matchup(report.matches)
    return {(m.no, n["side"], parse_characteristic(n["strength"]).label,
             parse_characteristic(n["weakness"]).label)
            for m in report.matches for n in (m.matchup_notes or [])}


def test_g1_real_round_diff_is_exactly_as_recorded():
    report = _artifact()
    if report is None:
        return
    new = _new_notes(report)
    assert len(new) == 17, len(new)
    assert OLD_18 - new == REMOVED, sorted(OLD_18 - new)
    assert new - OLD_18 == ADDED, sorted(new - OLD_18)
    assert OLD_18 & new == OLD_18 - REMOVED, "유지되어야 할 12건이 달라졌다"
    assert len(OLD_18 & new) == 12, len(OLD_18 & new)


def test_g2_note_shape_is_unchanged():
    """다섯 칸과 그 뜻이 그대로다 — render·match_material 이 이 모양을 읽는다."""
    report = _artifact()
    if report is None:
        return
    analyze.build_matchup(report.matches)
    notes = [n for m in report.matches for n in (m.matchup_notes or [])]
    assert notes, "노트가 통째로 비었다"
    for n in notes:
        assert set(n) == {"side", "topic", "strength", "weakness", "text"}, set(n)
        assert n["side"] in ("home", "away"), n["side"]
        # `strength` 칸에는 강점만, `weakness` 칸에는 약점만 들어간다.
        assert parse_characteristic(n["strength"]).intensity in ("Strong", "Very Strong")
        assert parse_characteristic(n["weakness"]).intensity in ("Weak", "Very Weak")
        assert n["text"].endswith("약점과 맞물립니다.")


def test_g3_only_advantage_reaches_the_notes():
    """`COUNTER`·`DIRECT` 는 노트로 나가지 않는다 — 칸 이름이 거짓이 된다."""
    src = _src(analyze.build_matchup)
    assert "ADVANTAGE" in src, src
    out = rels(home_s=["Attacking set pieces · Strong"],
               away_s=["Defending set pieces · Strong"])
    assert out[0].kind == relationships.COUNTER
    from toto.models import Match
    m = Match(no=1, league="epl")
    m.home, m.away = TeamRef(canonical="홈", display="홈"), TeamRef(canonical="원정", display="원정")
    m.home_profile = prof("홈", ["Attacking set pieces · Strong"])
    m.away_profile = prof("원정", (), ())
    m.away_profile.strengths = ["Defending set pieces · Strong"]
    analyze.build_matchup([m])
    assert m.matchup_notes == [], m.matchup_notes


def test_g4_real_round_counter_and_direct_exist_in_the_engine():
    """노트에는 안 나가지만 엔진은 만들고 있다 (6-E-4 가 쓸 자리)."""
    report = _artifact()
    if report is None:
        return
    kinds = {relationships.ADVANTAGE: 0, relationships.COUNTER: 0,
             relationships.DIRECT: 0}
    for m in report.matches:
        if m.home_profile is None or m.away_profile is None:
            continue
        for r in relationships.build_relationships(
                m.home.display, m.home_profile, m.away.display, m.away_profile):
            kinds[r.kind] += 1
    assert kinds == {relationships.ADVANTAGE: 17, relationships.COUNTER: 2,
                     relationships.DIRECT: 2}, kinds


# ==========================================================================
# H. 범위 — 이 Phase 가 건드리지 않기로 한 것
# ==========================================================================
def test_h1_engine_does_not_use_the_old_topic_table():
    """`_TOPICS` 를 관계 엔진의 입력으로 쓰지 않는다 (§4)."""
    code_only = _code_only(relationships)
    for word in ("_TOPICS", "_TOPIC_KO", "_topics_of"):
        assert word not in code_only, word
    code = ast.unparse(ast.parse(_src(analyze.build_matchup)))
    for word in ("_TOPICS", "_TOPIC_KO", "_topics_of"):
        assert word not in code, f"build_matchup: {word}"


def test_h2_old_topic_tables_are_untouched():
    """표 자체는 한 글자도 바뀌지 않았다 — 제거는 별도 정리다."""
    blob = json.dumps([analyze._TOPICS, analyze._TOPIC_KO],
                      ensure_ascii=False, sort_keys=True)
    import hashlib
    assert hashlib.sha256(blob.encode()).hexdigest()[:16] == "e4e6ea5e47c647ef"


def test_h3_forbidden_modules_do_not_reference_the_engine():
    """엔진을 볼 이유가 없는 모듈은 엔진을 모른다.

    **6-E-4 에서 범위를 옮겼다.** 6-E-3 때 이 목록은 "전달 경로를 건드리지
    않았다" 는 범위 선언이었고, 6-E-4 가 정확히 그 전달을 하는 Phase 다
    (§1-29 의 `test_settlement.test_j3` · §1-31 의 `test_a2` 와 같은 교정).
    지키려던 것 — **엔진은 한 곳에서만 정의된다** — 은 아래 두 갈래로
    더 단단히 고정한다.
    """
    # 확률·축·수집·메뉴·사회자는 여전히 엔진을 몰라야 한다.
    for mod in ("menu.py", "moderator.py", "predict.py", "analysis.py",
                "evidence.py", "panelexport.py",
                "sources/pinnacle.py", "sources/whoscored.py"):
        path = ROOT / "toto" / mod
        assert path.exists(), path
        text = path.read_text(encoding="utf-8")
        for word in ("relationships", "Relationship", "SemanticUnit",
                     "build_relationships"):
            assert word not in text, f"{mod}: {word}"

    # 소비처 셋은 **읽기만** 한다. 의미 단위·짝을 자기 쪽에 다시 정의하면
    # 두 곳이 어긋나므로, canonical 모델의 이름을 만지지 못하게 막는다.
    for mod in ("render.py", "match_material.py", "panel.py"):
        # docstring 은 걷어낸다 — "`MIRROR` 를 내보내지 않는다" 라고 적어 둔
        # 설명 때문에 깨지면 안 된다 (`_code_only` 와 같은 이유).
        code = _file_code_only(ROOT / "toto" / mod)
        assert "relationships" in code, f"{mod}: 엔진을 쓰지 않는다"
        for word in ("SemanticUnit", "PAIRS", "_UNITS", "DEFERRED_PAIRS",
                     "unit_of", "_kind(", "MIRROR", "CONTEST"):
            assert word not in code, f"{mod}: {word}"


def test_h4_engine_is_pure_and_stores_nothing():
    """캐시·저장본에 손대지 않는다 (§16)."""
    src = _src(relationships)
    for word in ("cache", "Cache", "artifact", "CACHE_VERSION", "open(",
                 "requests", "browser"):
        assert word not in src, word
    from dataclasses import fields
    from toto.models import Match
    names = {f.name for f in fields(Match)}
    assert "relationships" not in names and "relationship" not in names, names


def test_h5_cache_and_artifact_versions_are_unchanged():
    from toto.sources import whoscored
    assert whoscored._TEAM_CACHE_VERSION == 1
    assert whoscored._LEAGUE_CACHE_VERSION == 3
    assert artifact.ARTIFACT_VERSION == 1


def test_h6_engine_makes_no_verdict():
    """승무패·추천·점수를 만들지 않는다 (§1-3)."""
    src = _src(relationships)
    for word in ("pick", "recommend", "confidence", "winner", "favorite",
                 "probability", "score(", "verdict", "lean"):
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
