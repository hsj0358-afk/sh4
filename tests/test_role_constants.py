"""패널 역할 식별자·라벨 — 어디서 정하고 어디서 베끼나 (리팩터링 Phase 3-B M3).

역할에 관한 상수는 여러 벌 있지만 **계약이 모두 같은 것은 아니다.**

  식별자  `data_analyst` · `matchup_tactical_analyst`
          Panel Result 파일 · 분포 `origin` · `adopted_from` · `panels_seen` ·
          캐시 · 보관본에 **글자 그대로 저장되는 값**이다. `panel` 과
          `moderator` 가 순환 import 때문에 따로 들고 있었다 (§1-10). 이제
          `models` 한 곳에서 정하고 두 모듈은 기존 이름 그대로 가져다 쓴다.

  표시 라벨 (한국어) — **합치지 않는다.** 이름이 같아도 가리키는 것이 다르다.
    panel.ROLE_KO          메뉴·로그·보관 단계 화면
    render._ROLE_KO        HTML 리포트 (분포 출처 `_ORIGIN_KO` 의 바탕)
    panelexport._ROLE_KO   채팅 메시지가 **프로젝트 지침의 제목**을 가리킨다.
                           지침 원문은 지문(fingerprint)이 걸린 글이라, 이
                           라벨은 그 제목과 같아야 하지 다른 화면과 같아야
                           하는 것이 아니다.
    panelauto.STAGE_LABEL  자동 실행 로그의 영어 단계 이름

이 스위트가 지키는 것.

  A. 값이 그대로다 — 식별자·라벨·순서 (통합 전 코드에서도 통과한다)
  B. 따로 둔 사본은 **자기 계약**에 묶여 있다 — render 의 키는 역할
     식별자, panelexport 의 라벨은 지침 제목
  C. 식별자는 한 곳에서 정한다

pytest 없이도 돈다:  python tests/test_role_constants.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import (models, moderator, panel, panelauto,          # noqa: E402
                  panelexport, panelimport, render)

_PASSED = _FAILED = 0

DA, MU = "data_analyst", "matchup_tactical_analyst"
LABEL = {DA: "데이터 분석가", MU: "맞대결·전술 분석가"}


def check(name, fn):
    global _PASSED, _FAILED
    try:
        fn()
    except Exception as exc:                                 # noqa: BLE001
        _FAILED += 1
        print(f"  ✗ {name}: {type(exc).__name__}: {exc}")
    else:
        _PASSED += 1
        print(f"  ✓ {name}")


# --------------------------------------------------------------------------
# A. 값이 그대로다
# --------------------------------------------------------------------------
def test_a1_identifier_values_are_the_stored_contract():
    """파일에 저장되는 글자다 — 바꾸면 옛 Panel Result·보관본이 안 읽힌다."""
    assert (panel.DATA_ANALYST, panel.MATCHUP_ANALYST) == (DA, MU)
    assert (moderator.DATA_ROLE, moderator.MATCHUP_ROLE) == (DA, MU)
    assert (panelimport.DATA_ROLE, panelimport.MATCHUP_ROLE) == (DA, MU)
    assert panel.ROLES == (DA, MU), "역할 순서가 바뀌었다 (A → B)"
    assert panelimport.ANALYST_ROLES == panel.ROLES
    assert panelimport.MODERATOR_ROLE == "moderator"
    assert moderator.COMPROMISE == "compromise"


def test_a2_display_labels_are_unchanged():
    assert panel.ROLE_KO == LABEL
    assert render._ROLE_KO == LABEL
    assert render._ORIGIN_KO == dict(LABEL, compromise="양쪽 절충")
    assert panelexport._ROLE_KO == LABEL
    assert panelauto.STAGE_LABEL == {DA: "Data Analyst",
                                     MU: "Matchup Analyst",
                                     panelauto.MODERATOR_DIR: "Moderator"}


# --------------------------------------------------------------------------
# B. 따로 둔 사본은 자기 계약에 묶여 있다
# --------------------------------------------------------------------------
def test_b1_render_labels_are_keyed_by_the_role_identifiers():
    """HTML 은 `opinion.role` 로 라벨을 찾는다 — 키가 어긋나면 날 식별자가
    화면에 나온다 (`_ROLE_KO.get(r, r)`)."""
    assert set(render._ROLE_KO) == set(panel.ROLES)
    assert set(render._ORIGIN_KO) == set(panel.ROLES) | {moderator.COMPROMISE}


def test_b2_export_labels_point_at_the_instruction_headings():
    """채팅 메시지의 `"역할 A — …"` 는 프로젝트 지침의 제목을 가리킨다.
    라벨이 지침과 어긋나면 모델이 따를 제목이 사라진다."""
    text = panelexport.project_instructions()
    for letter, role in (("A", panel.DATA_ANALYST),
                         ("B", panel.MATCHUP_ANALYST)):
        heading = f"## 역할 {letter} — {panelexport._ROLE_KO[role]} "
        assert heading in text, heading
    assert set(panelexport._ROLE_KO) == set(panel.ROLES)


def test_b3_stage_labels_cover_the_three_stages():
    assert set(panelauto.STAGE_LABEL) == set(panel.ROLES) | {
        panelauto.MODERATOR_DIR}


# --------------------------------------------------------------------------
# C. 식별자는 한 곳에서 정한다
# --------------------------------------------------------------------------
def _assigned_literals(mod) -> list[str]:
    """모듈 맨 위에서 역할 식별자 글자를 이름에 직접 넣는 자리."""
    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    out = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and node.value.value in (DA, MU):
            out.append(ast.unparse(node))
    return out


def test_c1_identifiers_are_one_object():
    assert panel.DATA_ANALYST is models.DATA_ANALYST
    assert panel.MATCHUP_ANALYST is models.MATCHUP_ANALYST
    assert moderator.DATA_ROLE is models.DATA_ANALYST
    assert moderator.MATCHUP_ROLE is models.MATCHUP_ANALYST


def test_c2_panel_and_moderator_do_not_spell_them_again():
    for mod in (panel, moderator):
        assert not _assigned_literals(mod), (mod.__name__,
                                             _assigned_literals(mod))
    assert _assigned_literals(models) == [
        f"DATA_ANALYST = {DA!r}", f"MATCHUP_ANALYST = {MU!r}"]


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
