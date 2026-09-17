"""정성 특성 관계 엔진 (Phase 6-E-3).

두 팀의 WhoScored 특성(`Characteristic`, §1-36)을 마주 놓고 **어떤 특성이
어떤 특성과 맞물리는가**를 낸다. 규칙 기반이고 같은 입력이면 같은 결과가
나온다 — ML 도 LLM 도 쓰지 않는다.

**의미 단위는 라벨 하나당 하나다.** 실측 260052 의 24개 고유 라벨이 각각
자기 단위를 갖는다. 예전 `analyze._TOPICS` 는 키워드 부분일치로 라벨을 14개
주제에 욱여넣었고, 그래서 두 가지가 동시에 일어났다.

```
set_piece  ← "Attacking set pieces" · "Defending set pieces"
              · "Shooting from direct free kicks"      ← 공격·수비가 한 축
finishing  ← "Creating scoring chances" · "Finishing scoring chances"
                                                       ← 창출·마무리가 한 축
```

그 결과 실물에서 **수비↔수비**(`Defending set pieces` × `Defending set
pieces`)와 **창출↔마무리**가 관계로 나왔다 — 둘 다 공이 흐르지 않는 자리다.
동시에 `Creating chances through individual skill` 의 자명한 짝인
`Defending against skillful players` 는 어떤 주제에도 매핑되지 않아 놓쳤다.

라벨 하나당 단위 하나면 그 병합이 **구조적으로 불가능**하다.

**짝은 라벨 문구가 스스로 말하는 것만 등록한다.**

```
"Attacking down the wings"  →  "Defending against attacks down the wings"
                                          └ 수비 라벨이 공격 개념을 문자 그대로 품는다
```

"축구적으로 비슷해 보인다" 로 늘리지 않는다 — §1-1-9 의 `COMPARABLE_SOURCES`
가 등록된 쌍만 허용하는 것과 같은 태도다. 등록하지 않고 미룬 후보는 아래
`DEFERRED_PAIRS` 에 사유와 함께 적어 두었다.

**강도를 숫자로 바꾸지 않는다** (§9). `Characteristic` 을 통째로 들고 다녀
원문과 강도가 그대로 보존되고, 이 모듈은 강도끼리 크기를 비교하지 않는다.

**승무패를 만들지 않는다.** 관계는 사실 진술이고 유리/불리를 매기지 않는다
(§1-3). 관계 개수를 세어 우열로 쓰지 않는다 (§1-1-14).
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Characteristic, characteristics

# --------------------------------------------------------------------------
# 단위의 역할 — 라벨이 **누구의 무엇**을 말하나
# --------------------------------------------------------------------------
#   ATTACKING   상대를 향해 하는 행동          "Attacking down the wings"
#   DEFENDING   상대의 행동을 막는 행동        "Defending against attacks down the wings"
#   CONTESTED   양 팀이 **같은 라벨**로 맞붙는다  "Aerial duels"
#   OWN         상대와의 관계를 라벨이 말하지 않는다  "Finishing scoring chances"
ATTACKING, DEFENDING, CONTESTED, OWN = "attacking", "defending", "contested", "own"

# --------------------------------------------------------------------------
# 관계의 종류 — **폴라리티**로 정한다
# --------------------------------------------------------------------------
#   ADVANTAGE  강점 → 약점    A의 강점이 B의 약점을 향한다 (방향 있음)
#   COUNTER    강점 → 강점    A의 강점이 B의 강점을 마주한다
#   DIRECT     약점 → 약점    같은 단위에서 양쪽 다 약하다 (방향 주장 없음)
#   NONE       짝이 없다      **만들지 않는다** (§1-5 — 없는 것을 지어내지 않는다)
ADVANTAGE, COUNTER, DIRECT, NONE = "ADVANTAGE", "COUNTER", "DIRECT", "NONE"

# 관계의 **구조** — 종류와 따로 기록한다.
#   MIRROR     서로 다른 두 라벨의 공격↔수비 짝
#   CONTEST    같은 라벨의 대칭 경합
MIRROR, CONTEST = "MIRROR", "CONTEST"


@dataclass(frozen=True)
class SemanticUnit:
    """의미 단위 하나. **라벨 하나당 하나다.**

    `label` 은 WhoScored 원문이고 여기서 고치거나 번역해 덮어쓰지 않는다.
    `ko` 는 화면 표시용 이름일 뿐 판정에 쓰이지 않는다.
    """
    key: str
    label: str
    role: str
    ko: str


def _u(key: str, label: str, role: str, ko: str) -> SemanticUnit:
    return SemanticUnit(key=key, label=label, role=role, ko=ko)


# --------------------------------------------------------------------------
# 단위 표 — 실측 260052 의 24개 고유 라벨
# --------------------------------------------------------------------------
# **관측하지 않은 라벨을 넣지 않는다** (§1-22 가 팀 별칭에 정한 것과 같은
# 규칙). 새 라벨이 나오면 여기 없으므로 `OWN` 으로 떨어지고, 그 사실이
# `unknown_labels()` 로 드러난다 — 조용히 빠지지 않는다 (§1-6-1).
_UNITS: tuple[SemanticUnit, ...] = (
    # --- 공격 측 (상대를 향한 행동) ---
    _u("wing_attack", "Attacking down the wings", ATTACKING, "측면 공격"),
    _u("through_ball_attack", "Creating chances using through balls",
       ATTACKING, "스루패스 기회 창출"),
    _u("long_shot_attack", "Creating long shot opportunities",
       ATTACKING, "중거리 기회 창출"),
    _u("individual_skill_attack", "Creating chances through individual skill",
       ATTACKING, "개인기 기회 창출"),
    _u("counter_attack", "Counter attacks", ATTACKING, "역습"),
    _u("set_piece_attack", "Attacking set pieces", ATTACKING, "세트피스 공격"),
    _u("chance_creation", "Creating scoring chances", ATTACKING, "기회 창출"),
    _u("ball_recovery", "Stealing the ball from the opposition",
       ATTACKING, "볼 탈취"),
    # --- 수비 측 (상대의 행동을 막는 행동) ---
    _u("wing_defence", "Defending against attacks down the wings",
       DEFENDING, "측면 수비"),
    _u("through_ball_defence", "Defending against through ball attacks",
       DEFENDING, "스루패스 수비"),
    _u("long_shot_defence", "Defending against long shots",
       DEFENDING, "중거리 수비"),
    _u("individual_skill_defence", "Defending against skillful players",
       DEFENDING, "개인기 수비"),
    _u("counter_defence", "Defending counter attacks", DEFENDING, "역습 수비"),
    _u("set_piece_defence", "Defending set pieces", DEFENDING, "세트피스 수비"),
    _u("chance_prevention", "Stopping opponents from creating chances",
       DEFENDING, "기회 억제"),
    _u("ball_retention", "Keeping possession of the ball", DEFENDING, "볼 간수"),
    # --- 대칭 경합 (양 팀이 같은 라벨로 맞붙는다) ---
    _u("aerial_duel", "Aerial duels", CONTESTED, "공중볼 경합"),
    # --- 짝 없음 (상대와의 관계를 라벨이 말하지 않는다) ---
    # `Finishing scoring chances` 가 여기 있는 것이 이 Phase 의 핵심이다 —
    # 자기 기회의 마무리는 상대의 어떤 라벨과도 맞물리지 않는다. 옛 코드는
    # 이것을 `Creating scoring chances` 와 한 주제로 묶어 관계로 만들었다.
    _u("finishing", "Finishing scoring chances", OWN, "마무리"),
    _u("lead_protection", "Protecting the lead", OWN, "리드 지키기"),
    _u("comeback", "Coming back from losing positions", OWN, "열세 반전"),
    _u("individual_errors", "Avoiding individual errors", OWN, "개인 실수 회피"),
    _u("offside_discipline", "Avoiding offside", OWN, "오프사이드 회피"),
    _u("foul_discipline", "Avoiding fouling in dangerous areas",
       OWN, "위험지역 파울 회피"),
    _u("direct_free_kick", "Shooting from direct free kicks", OWN, "직접 프리킥"),
)

UNITS: dict[str, SemanticUnit] = {u.label: u for u in _UNITS}

# --------------------------------------------------------------------------
# 짝 표 — **라벨 문구가 스스로 말하는 것만**
# --------------------------------------------------------------------------
# 각 줄의 셋째 칸이 등록 근거다. 늘리려면 그 자리에 적을 수 있어야 한다.
PAIRS: tuple[tuple[str, str, str], ...] = (
    ("wing_attack", "wing_defence",
     "수비 라벨이 'attacks down the wings' 를 문자 그대로 품는다"),
    ("through_ball_attack", "through_ball_defence",
     "수비 라벨이 'through ball' 을 문자 그대로 품는다"),
    ("long_shot_attack", "long_shot_defence",
     "수비 라벨이 'long shot' 을 문자 그대로 품는다"),
    ("individual_skill_attack", "individual_skill_defence",
     "공격은 'individual skill', 수비는 'skillful players' 로 같은 개념을 가리킨다"),
    ("counter_attack", "counter_defence",
     "수비 라벨이 'counter attacks' 를 문자 그대로 품는다"),
    ("set_piece_attack", "set_piece_defence",
     "공격은 'Attacking set pieces', 수비는 'Defending set pieces'"),
    ("chance_creation", "chance_prevention",
     "수비 라벨이 'opponents' 와 'creating chances' 를 함께 명시한다"),
    ("ball_recovery", "ball_retention",
     "공격 라벨이 대상('from the opposition')을, 수비 라벨이 그 반대 동작을 명시한다"),
)

# 등록하지 **않은** 후보. 지우지 않고 사유와 함께 남긴다 — 다음 사람이 같은
# 질문을 다시 하게 되고, 그때 '왜 안 넣었나' 가 없으면 그냥 넣게 된다.
DEFERRED_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("comeback", "lead_protection",
     "공유 토큰이 없다. 'losing position = 상대의 lead' 는 축구 도메인 추론이지 "
     "라벨이 말하는 것이 아니다"),
    ("direct_free_kick", "foul_discipline",
     "2단계 추론(파울 → 프리킥 허용 → 상대 프리킥 슈팅). 라벨이 직접 잇지 않는다"),
)


# --------------------------------------------------------------------------
# 관계
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Relationship:
    """두 특성이 맞물린다는 **사실** 하나.

    `source_*` 와 `target_*` 를 나눠 두는 이유는 §10 이다 — "A의 강점이 B의
    약점을 향한다" 와 "B의 약점이 A의 강점에 노출된다" 는 같은 사실을 다른
    관점에서 말한 것이지만, 결과 모델에서는 **주체와 대상**이 분명해야 한다.

    `CONTEST` 구조에서 양쪽 폴라리티가 같으면(둘 다 강점·둘 다 약점) 방향을
    주장할 근거가 없다. 그때 `source` 는 **홈 우선**이고 이는 표시 순서이지
    방향 주장이 아니다 — `kind` 가 `COUNTER`/`DIRECT` 라는 것이 그 표시다.
    """
    source_team: str
    source_characteristic: Characteristic
    source_unit: SemanticUnit
    target_team: str
    target_characteristic: Characteristic
    target_unit: SemanticUnit
    kind: str
    basis: str
    evidence: str

    @property
    def directional(self) -> bool:
        """주체와 대상이 갈리나. `ADVANTAGE` 만 참이다."""
        return self.kind == ADVANTAGE


def unit_of(label: str) -> SemanticUnit | None:
    """라벨 → 의미 단위. 표에 없으면 `None`.

    **추측하지 않는다** — 비슷해 보이는 단위에 붙이지 않는다 (§1-1-1 이
    부분일치를 걷어낸 것과 같은 이유).
    """
    return UNITS.get(label)


def unknown_labels(profile) -> list[str]:
    """이 프로필에서 단위 표에 **없는** 라벨. 조용히 빠지지 않게 한다.

    새 어휘가 소스에 나타나면 관계가 조용히 0건이 되는데, 그때 이 목록이
    무엇이 빠졌는지 말해 준다 (§1-6-1).
    """
    if profile is None:
        return []
    out = []
    for slot in ("strengths", "weaknesses"):
        for char in characteristics(getattr(profile, slot, None)):
            if char.label not in UNITS and char.label not in out:
                out.append(char.label)
    return out


# --------------------------------------------------------------------------
# 엔진
# --------------------------------------------------------------------------
def _slots(profile) -> tuple[dict[str, Characteristic], dict[str, Characteristic]]:
    """(강점 {라벨: 특성}, 약점 {라벨: 특성}). 원문을 그대로 안고 있다."""
    if profile is None:
        return {}, {}
    strong = {c.label: c for c in characteristics(getattr(profile, "strengths", None))}
    weak = {c.label: c for c in characteristics(getattr(profile, "weaknesses", None))}
    return strong, weak


def _kind(source_is_strength: bool, target_is_strength: bool) -> str:
    if source_is_strength and not target_is_strength:
        return ADVANTAGE
    if source_is_strength and target_is_strength:
        return COUNTER
    if not source_is_strength and not target_is_strength:
        return DIRECT
    # 강점을 향하는 약점 — 그 관계는 반대 방향에서 `ADVANTAGE` 로 이미 나온다.
    return NONE


def _evidence(kind: str, source_team: str, target_team: str,
              source: SemanticUnit, target: SemanticUnit, why: str) -> str:
    """관계가 성립한 **근거 문장**. 유리·불리를 적지 않는다 (§1-3)."""
    if kind == ADVANTAGE:
        head = (f"{source_team}의 강점({source.ko})이 "
                f"{target_team}의 약점({target.ko})과 맞물립니다")
    elif kind == COUNTER:
        head = (f"{source_team}의 강점({source.ko})이 "
                f"{target_team}의 강점({target.ko})과 마주섭니다")
    else:
        head = (f"{source_team}과 {target_team} 모두 이 단위가 약합니다 "
                f"({source.ko} ↔ {target.ko})")
    return f"{head} — {why}"


def _pair_rows() -> list[tuple[SemanticUnit, SemanticUnit, str]]:
    """등록 순서 그대로의 (공격 단위, 수비 단위, 근거). 집합을 쓰지 않는다."""
    by_key = {u.key: u for u in _UNITS}
    return [(by_key[a], by_key[d], why) for a, d, why in PAIRS]


def build_relationships(home_team: str, home_profile,
                        away_team: str, away_profile) -> list[Relationship]:
    """두 팀의 특성에서 관계를 만든다. **같은 입력이면 같은 출력이다.**

    순회 순서가 결과 순서다 — `PAIRS` 등록 순서로 (홈이 공격 → 원정이 공격),
    그다음 대칭 경합. 집합·사전 순서에 기대지 않는다 (§1-1-14 와 같은 이유로
    실행마다 줄이 달라지면 안 된다).

    관계가 성립하지 않으면 **만들지 않는다** — `NONE` 을 목록에 넣지 않는다.
    """
    hs, hw = _slots(home_profile)
    aws, aww = _slots(away_profile)
    out: list[Relationship] = []

    # --- MIRROR: 공격 라벨 → 상대의 대응 수비 라벨 ---
    for attack, defence, why in _pair_rows():
        for src_team, (s_strong, s_weak), dst_team, (t_strong, t_weak) in (
                (home_team, (hs, hw), away_team, (aws, aww)),
                (away_team, (aws, aww), home_team, (hs, hw))):
            source = s_strong.get(attack.label) or s_weak.get(attack.label)
            target = t_strong.get(defence.label) or t_weak.get(defence.label)
            if source is None or target is None:
                continue
            kind = _kind(attack.label in s_strong, defence.label in t_strong)
            if kind == NONE:
                continue
            out.append(Relationship(
                source_team=src_team, source_characteristic=source,
                source_unit=attack,
                target_team=dst_team, target_characteristic=target,
                target_unit=defence,
                kind=kind, basis=MIRROR,
                evidence=_evidence(kind, src_team, dst_team, attack, defence, why)))

    # --- CONTEST: 같은 라벨이 양 팀에 있다 ---
    for unit in _UNITS:
        if unit.role != CONTESTED:
            continue
        home_char = hs.get(unit.label) or hw.get(unit.label)
        away_char = aws.get(unit.label) or aww.get(unit.label)
        if home_char is None or away_char is None:
            continue
        home_strong = unit.label in hs
        away_strong = unit.label in aws
        why = "양 팀에 같은 라벨로 나와 직접 맞붙는다"
        if home_strong != away_strong:
            # 폴라리티가 갈리면 주체가 분명하다 — 강점 쪽이 source 다.
            if home_strong:
                src_team, src, dst_team, dst = home_team, home_char, away_team, away_char
            else:
                src_team, src, dst_team, dst = away_team, away_char, home_team, home_char
            kind = ADVANTAGE
        else:
            # 둘 다 강점이거나 둘 다 약점 — 방향을 주장할 근거가 없다.
            # 홈을 먼저 적는 것은 표시 순서이지 방향이 아니다.
            src_team, src, dst_team, dst = home_team, home_char, away_team, away_char
            kind = COUNTER if home_strong else DIRECT
        out.append(Relationship(
            source_team=src_team, source_characteristic=src, source_unit=unit,
            target_team=dst_team, target_characteristic=dst, target_unit=unit,
            kind=kind, basis=CONTEST,
            evidence=_evidence(kind, src_team, dst_team, unit, unit, why)))
    return out
