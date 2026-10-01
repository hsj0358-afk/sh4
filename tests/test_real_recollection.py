"""실측 재수집 회귀 (Phase 6-E-5).

260054 회차를 사용자 PC 에서 실제로 돌린 로그와 리포트에서 **관측된 것만**
고정한다. 여기 실린 문자열은 전부 그 실행에서 나온 실물이고, 지어낸 축구
용어가 없다 (§1-4).

이 Phase 가 실물로 답한 것 셋.

1. **스타일 제목은 팀 이름을 앞에 단다.** 28팀 전부 `"<팀>'s Style of Play"`
   였고, `len>20` 상한과 정확일치 **둘 다**에 막혀 `style` 이 0/28 이었다.
   데이터가 없는 것이 아니라 파서가 놓친 것이다.
2. **소스가 "없다" 를 문장 한 줄로 내려보낸다.** AT마드의 약점 칸이
   `(Team has no significant weaknesses)` 하나였고, 그대로 담겨 리포트에
   **가짜 약점**으로 나갔다 (§1-5).
3. **어휘는 회차를 건너도 같다.** 260052 와 260054 가 고유 label 24종 ·
   intensity 4종으로 **완전히 일치**한다 (신규 0 · 사라짐 0).

마크업은 로그가 찍어 준 **경로 그대로** 재구성했다 — 원본 HTML 은 사용자
PC 에만 있다. 그래서 테스트는 클래스 경로가 아니라 **읽어낸 결과**를
단언한다 (§3-1 이 같은 상황에서 쓴 방식).
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bs4 import BeautifulSoup                                   # noqa: E402

from toto.normalize import TeamResolver                         # noqa: E402
from toto.settings import load_yaml                             # noqa: E402
from toto.sources import whoscored as W                         # noqa: E402
from toto.models import (CHAR_OBSERVED_EMPTY, CHAR_OK,          # noqa: E402
                         characteristic_status, parse_characteristic)

# 260054 실행 로그가 찍은 제목 문자열 (28팀 전부 같은 모양).
REAL_STYLE_HEADINGS = [
    "Brighton's Style of Play",
    "Arsenal's Style of Play",
    "Everton's Style of Play",
    "Athletic Club's Style of Play",
    "Nottingham Forest's Style of Play",
    "Deportivo de A Coruna's Style of Play",
    "Crystal Palace's Style of Play",
    "Real Sociedad's Style of Play",
]
# 강점/약점 제목은 팀 이름이 없다 — 예전부터 지나가던 모양이다.
REAL_PLAIN_HEADINGS = {"Strengths": "strengths", "+ Strengths": "strengths",
                       "Weaknesses": "weaknesses", "Style of play": "style"}

# 실측된 "없다" 문장 둘. 약점은 260054 로그·리포트에서, 강점은 §3-10 에서
# 사용자가 페이지를 직접 열어 확인한 것이다.
REAL_PLACEHOLDERS = ["(Team has no significant weaknesses)",
                     "(Team has no significant strengths)"]

# 260052 · 260054 양쪽에서 똑같이 나온 24종.
REAL_LABELS = {
    "Attacking down the wings", "Creating chances using through balls",
    "Creating long shot opportunities",
    "Creating chances through individual skill", "Counter attacks",
    "Attacking set pieces", "Creating scoring chances",
    "Stealing the ball from the opposition",
    "Defending against attacks down the wings",
    "Defending against through ball attacks", "Defending against long shots",
    "Defending against skillful players", "Defending counter attacks",
    "Defending set pieces", "Stopping opponents from creating chances",
    "Keeping possession of the ball", "Aerial duels",
    "Finishing scoring chances", "Protecting the lead",
    "Coming back from losing positions", "Avoiding individual errors",
    "Avoiding offside", "Avoiding fouling in dangerous areas",
    "Shooting from direct free kicks",
}
REAL_INTENSITIES = {"Strong", "Very Strong", "Weak", "Very Weak"}


def _card(strengths=(), weaknesses=(), style=(), style_heading=None) -> BeautifulSoup:
    """로그가 찍은 경로 그대로의 최소 카드.

        h3 < div.col12-lg-12.col12-m-12 < div.sws-content.character-card
    """
    def block(items):
        return "".join(
            f'<div class="character"><div>{lbl}</div>'
            + (f"<span>{inten}</span>" if inten else "") + "</div>"
            for lbl, inten in items)

    head = style_heading or "Brighton's Style of Play"
    html = (
        '<div class="sws-content character-card">'
        '<div class="col12-lg-12 col12-m-12">'
        f'<h3><span style="color:#35AB53;">+</span> Strengths</h3>'
        f"<div>{block(strengths)}</div>"
        f"<h3>Weaknesses</h3><div>{block(weaknesses)}</div>"
        f"<h3>{head}</h3><div>{block(style)}</div>"
        "</div></div>")
    return BeautifulSoup(html, "html.parser")


def _label(text: str) -> str:
    return W._heading_label(BeautifulSoup(f"<h3>{text}</h3>", "html.parser").h3)


# ==========================================================================
# A. 스타일 제목 — 팀 이름을 앞에 단다
# ==========================================================================
def test_a1_possessive_style_headings_resolve():
    for text in REAL_STYLE_HEADINGS:
        assert W._heading_slot(_label(text)) == "style", text


def test_a2_plain_headings_are_unchanged():
    """바레 제목의 동작이 한 글자도 달라지지 않아야 한다."""
    for text, slot in REAL_PLAIN_HEADINGS.items():
        assert W._heading_slot(_label(text)) == slot, text


def test_a3_length_guard_still_rejects_prose():
    """상한을 없앤 것이 아니라 올린 것이다 — 긴 문단은 여전히 제목이 아니다."""
    long_text = "Team Strengths Guide And Full Season Analysis Overview Page"
    assert W._heading_slot(_label(long_text)) == ""
    src = inspect.getsource(W._extract_characteristics)
    assert "len(label) > 60" in src, "길이 상한이 사라졌다"


def test_a4_possessive_is_stripped_only_once_and_needs_the_suffix():
    """소유격을 벗긴 **뒤에도 정확일치**여야 한다 — 접미사 부분일치가 아니다."""
    assert W._heading_slot(_label("Brighton's Match Preview")) == ""
    assert W._heading_slot(_label("Notes about the team strengths")) == ""


def test_a4b_suffix_matching_is_not_what_we_do():
    """**소유격일 때만** 벗긴다 (§1-1-1 이 부분일치를 걷어낸 것과 같은 태도).

    경계 확인용 문자열이다 — 실측된 제목이 아니라, 접미사 부분일치로
    넓혔을 때 통과해 버리는 모양을 일부러 고른 것이다. 소유격 규칙은
    이것을 거부해야 한다.
    """
    for text in ("Match Analysis Style of play",
                 "Compare Strengths",
                 "This weeks Style of play"):
        assert W._heading_slot(_label(text)) == "", text


def test_a5_style_is_actually_extracted_from_the_real_shape():
    out = W._extract_characteristics(
        _card(strengths=[("Attacking set pieces", "Strong")],
              style=[("Possession based", "Strong")]))
    assert out["style"] == ["Possession based · Strong"], out
    assert out["strengths"] == ["Attacking set pieces · Strong"], out


def test_a6_unicode_apostrophe_also_works():
    assert W._heading_slot(_label("Brighton’s Style of Play")) == "style"


# ==========================================================================
# B. "없다" 문장을 특성으로 담지 않는다
# ==========================================================================
def test_b1_placeholder_is_not_a_characteristic():
    out = W._extract_characteristics(
        _card(strengths=[("Attacking set pieces", "Strong")],
              weaknesses=[("(Team has no significant weaknesses)", "")]))
    assert out["weaknesses"] == [], out["weaknesses"]
    assert out["strengths"] == ["Attacking set pieces · Strong"]


def test_b2_both_observed_placeholders_are_dropped():
    for text in REAL_PLACEHOLDERS:
        out = W._extract_characteristics(_card(weaknesses=[(text, "")]))
        assert out["weaknesses"] == [], text


def test_b3_dropping_turns_the_slot_into_observed_empty():
    """빈 목록이 곧 관측된 0이다 — `page_failed` 가 아니다 (§1-36)."""
    out = W._extract_characteristics(
        _card(weaknesses=[("(Team has no significant weaknesses)", "")]))
    assert characteristic_status(out["weaknesses"], True) == CHAR_OBSERVED_EMPTY


def test_b4_real_characteristics_are_never_dropped():
    items = [(l, "Strong") for l in sorted(REAL_LABELS)[:5]]
    out = W._extract_characteristics(_card(strengths=items))
    assert len(out["strengths"]) == 5, out["strengths"]
    assert characteristic_status(out["strengths"], True) == CHAR_OK


def test_b5_placeholder_rule_is_structural_not_vocabulary():
    """영어 낱말을 코드에 박지 않는다 (§3-1 과 같은 규칙)."""
    src = inspect.getsource(W)
    tree = ast.parse(src)
    lits = [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    code = [x for x in lits if "no significant" in x.lower()]
    assert not code, f"placeholder 어휘를 코드에 박았다: {code}"


def test_b6_dropping_is_not_silent():
    """조용히 버리지 않는다 (§1-6-1).

    문자열 검색이 아니라 AST 로 본다 — `if dropped:` 가지 **안에** 로그가
    있어야 한다. (처음엔 `split("dropped")` 로 썼다가 같은 낱말이 두 번
    나와 엉뚱한 구간을 봤다.)
    """
    tree = ast.parse(inspect.getsource(W._extract_characteristics).strip())
    for node in ast.walk(tree):
        if (isinstance(node, ast.If)
                and isinstance(node.test, ast.Name)
                and node.test.id == "dropped"):
            logged = [n for n in ast.walk(node)
                      if isinstance(n, ast.Call)
                      and getattr(n.func, "attr", "") in ("info", "warning")]
            assert logged, "버린 사유를 남기지 않는다"
            return
    raise AssertionError("`if dropped:` 가지를 찾지 못했다")


# ==========================================================================
# C. 8개 상한 — 실측 세 팀이 정확히 8이다
# ==========================================================================
def test_c1_cap_is_still_eight():
    items = [(l, "Strong") for l in sorted(REAL_LABELS)]      # 24개
    out = W._extract_characteristics(_card(strengths=items))
    assert len(out["strengths"]) == 8, len(out["strengths"])


def test_c2_cap_keeps_document_order():
    items = [(l, "Strong") for l in sorted(REAL_LABELS)]
    out = W._extract_characteristics(_card(strengths=items))
    assert out["strengths"] == [f"{l} · Strong" for l in sorted(REAL_LABELS)[:8]]


# ==========================================================================
# D. 어휘 — 두 회차가 같다
# ==========================================================================
def test_d1_every_real_label_parses_into_label_and_intensity():
    for label in REAL_LABELS:
        for inten in REAL_INTENSITIES:
            c = parse_characteristic(f"{label} · {inten}")
            assert c is not None and c.parsed, (label, inten)
            assert c.label == label and c.intensity == inten
            assert c.raw == f"{label} · {inten}"


def test_d2_placeholder_does_not_parse_as_a_characteristic():
    for text in REAL_PLACEHOLDERS:
        c = parse_characteristic(text)
        assert c is not None and not c.parsed, text
        assert c.raw == text, "원문이 바뀌었다"


def test_d2b_last_separator_wins():
    """`rsplit` 이지 `split` 이 아니다 — **마지막 칸이 강도**다 (§1-36).

    `.character` 블록은 `get_text(" · ")` 로 자식을 전부 잇는다. 자식이
    셋이면 구분자가 둘이 되므로, 앞에서부터 자르면 라벨이 잘려 나간다.
    실제 그 모양을 카드로 만들어 확인한다.
    """
    soup = BeautifulSoup(
        '<div class="sws-content character-card"><div class="col12-lg-12">'
        "<h3>Strengths</h3><div>"
        '<div class="character"><span>1</span><div>Aerial duels</div>'
        "<span>Very Strong</span></div>"
        "</div></div></div>", "html.parser")
    raw = W._extract_characteristics(soup)["strengths"][0]
    assert raw.count(" · ") == 2, raw
    c = parse_characteristic(raw)
    assert c.intensity == "Very Strong", c.intensity
    assert c.label == "1 · Aerial duels", c.label
    assert c.raw == raw, "원문이 바뀌었다"


def test_d3_vocabulary_counts_are_pinned():
    assert len(REAL_LABELS) == 24
    assert len(REAL_INTENSITIES) == 4


# ==========================================================================
# E. 라싱산탄 — 관측된 표기만 넣는다
# ==========================================================================
def test_e1_betman_spelling_resolves():
    r = TeamResolver()
    assert r.resolve("라싱산탄", learn=False, quiet=True) == "Racing Santander"


def test_e2_previously_registered_spellings_still_resolve():
    r = TeamResolver()
    assert r.resolve("R. Santander", learn=False, quiet=True) == "Racing Santander"
    assert r.resolve("Racing Santander", learn=False, quiet=True) == "Racing Santander"


def test_e3_no_existing_spelling_changed_meaning():
    """§1-22 의 충돌 시뮬레이션을 테스트로 옮긴다 — 앞으로 어떤 이름을
    더해도 기존 해석을 가로채면 여기서 깨진다."""
    table = load_yaml(ROOT / "data" / "teams.yaml") or {}
    r = TeamResolver()
    for canon, entry in table.items():
        canon = str(canon)
        spellings = [canon]
        for key in ("ko", "en"):
            spellings += [str(x) for x in ((entry or {}).get(key) or [])]
        for name in spellings:
            got = r.resolve(name, learn=False, quiet=True)
            assert got == canon, f"{name!r} → {got!r} (기대 {canon!r})"


def test_e4_only_observed_spellings_were_added():
    """FotMob 표기는 아직 관측되지 않았다 — 지어내지 않는다."""
    table = load_yaml(ROOT / "data" / "teams.yaml") or {}
    entry = table["Racing Santander"]
    assert entry.get("ko") == ["라싱산탄"], entry.get("ko")
    assert entry.get("en") == ["R. Santander"], entry.get("en")


# ==========================================================================
# F. 범위 — 이번 Phase 가 건드리지 않은 것
# ==========================================================================
def test_f1_relationship_engine_untouched():
    from toto import relationships as R
    assert len(R.PAIRS) == 8
    assert len(R._UNITS) == 24
    assert len(R.DEFERRED_PAIRS) == 2


def test_f2_storage_versions():
    """**팀 페이지 캐시만** 올렸다 — 저장되는 payload 내용이 실제로 달라진다
    (`style` 이 차고 "없다" 문장이 빠진다). 리그 캐시와 artifact 는 형식도
    내용도 그대로라 올리지 않는다 (§1-4 의 조건).
    """
    from toto import artifact
    assert W._TEAM_CACHE_VERSION == 2
    assert W._LEAGUE_CACHE_VERSION == 3
    assert artifact.ARTIFACT_VERSION == 1


def test_f3_no_new_semantic_unit_for_the_placeholder():
    """실측 미등록 label 을 관계 엔진에 몰래 넣지 않았다 (DEFERRED)."""
    from toto import relationships as R
    for text in REAL_PLACEHOLDERS:
        assert R.unit_of(text) is None, text


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
