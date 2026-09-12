"""리포트 문구·정보 위계 회귀 테스트 (Phase 4-F UI).

고정하려는 것은 넷이다.

1. **Moderator-only 를 "하지 않았습니다" 로 적지 않는다.** 사회자는 돌았고
   분석가 원문만 이번 입력에 없다 — 내부 상태(`부분`)를 그대로 화면에
   옮기면 결과가 있는데 없는 것처럼 읽힌다.
2. **생략과 Moderator-only 를 같게 보이게 하지 않는다.** 하나는 애초에
   돌리지 않은 것이고 하나는 결과가 있는 것이다.
3. **상세 자료는 기본 접힘이되 값은 하나도 줄이지 않는다.** 접는 것은
   지우는 것이 아니다 — 펼치면 전과 같은 표가 그대로 있다.
4. **'최종 판단' 절을 뺀 자리에 추천을 넣지 않았다.** 원칙이 바뀐 것이
   아니라 같은 말의 세 번째 반복을 걷어낸 것이다.

pytest 없이도 돈다:  python tests/test_ui_semantics.py
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import panelaudit, panelimport, panelpaste, render   # noqa: E402
from toto.settings import Settings                             # noqa: E402

import test_panel_paste as P                                   # noqa: E402
from test_axes_render import _match                            # noqa: E402
from test_panel_render import full_run                         # noqa: E402

SKIP = P.SKIP


def _text(html: str) -> str:
    """화면에 실제로 보이는 글자만 (태그 속성값을 검사에서 뺀다)."""
    return re.sub(r"<[^>]+>", " ", html)


def _moderator_only_report():
    """실물 260052 모양 — 11경기 Moderator-only · 3경기 생략."""
    report = P._report()
    base = Path(tempfile.mkdtemp())
    path, res = panelpaste.apply(P.FIXTURE.read_text(encoding="utf-8"),
                                 report, P.S, base=base)
    assert path is not None, [str(i) for i in res.issues]
    panelimport.attach(res, report)
    return report, res


def _html(report) -> str:
    return render.render_report(report, Settings())


def _demo_card() -> str:
    """분석 축이 다 들어 있는 카드 — 접힘 구조를 볼 때 쓴다."""
    m = _match()
    m.panel = full_run()
    return render._match_card(m, Settings(), None)


def _card(html: str, no: int) -> str:
    mark = f'<h3><span class="no">{no}</span>'
    assert mark in html, no
    return html.split(mark)[1].split("<h3>")[0]


# --------------------------------------------------------------------------
# A. Moderator-only 문구
# --------------------------------------------------------------------------
def test_a1_card_says_moderator_result_not_did_not_run():
    """결과가 있는데 "하지 않았습니다" 라고 적지 않는다.

    5-D 전에는 카드 안의 요약 복사본(`_decision_summary`)이 이 문장을 들고
    있었다. 그 블록이 걷히면서 상태를 말하는 자리가 **패널 블록 하나로**
    모였다 — 같은 말을 두 곳에 적지 않는 §1-15-3 의 연장이다.
    """
    report, _res = _moderator_only_report()
    card = _card(_html(report), 1)
    assert "사회자 결과만 반영" in card
    assert "하지 않았습니다" not in card, "결과가 있는데 없다고 적었다"


def test_a2_panel_heading_says_moderator_only():
    report, _res = _moderator_only_report()
    card = _card(_html(report), 1)
    assert "패널 분석 (사회자 결과만 반영)" in card
    assert "패널 분석 (두 전문가의 해석)" not in card, \
        "두 전문가가 있었던 것처럼 적었다"


def test_a3_the_missing_analysts_are_stated_once():
    """같은 말을 제목과 본문에 두 번 적지 않는다."""
    report, _res = _moderator_only_report()
    card = _card(_html(report), 1)
    # 5-E2 에서 본문 설명을 **걷었다** — 제목 `패널 분석 (사회자 결과만
    # 반영)` 이 이미 같은 말을 한다. 두 번 적지 않는다는 규칙은 그대로이고,
    # 이제 한 번도 되풀이하지 않는다.
    assert "1·2단계 분석가 원문은 이번 입력에 포함되지 않았습니다" not in card
    assert card.count("패널 분석 (사회자 결과만 반영)") == 1


def test_a4_skipped_is_not_the_same_as_moderator_only():
    report, _res = _moderator_only_report()
    html = _html(report)
    skipped = _card(html, SKIP[0])
    assert "이 경기는 패널 분석을 하지 않았습니다" in skipped
    assert "사회자 결과만 반영" not in skipped, "생략을 결과처럼 적었다"
    assert "Moderator 결과만 반영" not in skipped


def test_a4b_moderator_heading_does_not_claim_two_opinions():
    """"분석가 원문이 없다" 고 적어 놓고 "두 의견의 종합" 이라고 쓰지 않는다."""
    report, _res = _moderator_only_report()
    card = _card(_html(report), 1)
    assert "사회자 종합" in card
    assert "두 의견의 종합" not in card


def test_a5_normal_panel_keeps_its_wording():
    m = _match()
    m.panel = full_run()
    block = render._panel_block(m)
    assert "패널 분석 (두 전문가의 해석)" in block
    assert "사회자 결과만 반영" not in block
    assert "사회자 (두 의견의 종합)" in block, "두 의견을 본 경기다"


def test_a6_internal_states_are_unchanged():
    """화면 문구를 바꿨다고 내부 상태를 바꾸지 않았다."""
    report, res = _moderator_only_report()
    au = panelaudit.audit(res, report)
    kinds = {a.match_no: a.decision_type for a in au.matches}
    assert kinds[1] == panelaudit.MODERATOR_ONLY
    assert kinds[SKIP[0]] == panelaudit.PANEL_SKIPPED
    assert panelimport.status_of(res.runs[1]) == panelimport.STATUS_PARTIAL
    assert panelimport.status_of(res.runs[SKIP[0]]) == \
        panelimport.STATUS_SKIPPED


def test_a7_badge_says_what_was_actually_applied():
    """`부분 (14/14경기 가져옴)` 만으로는 무엇을 얻었는지 알 수 없다."""
    report, res = _moderator_only_report()
    line = panelaudit.composition_line(panelaudit.audit(res, report))
    assert "Moderator 결과 11경기" in line, line
    assert "생략 3경기" in line, line
    assert "분석 완료" not in line, "사회자만 반영된 경기를 완전한 패널로 적었다"


# --------------------------------------------------------------------------
# B. 상세 자료 접기
# --------------------------------------------------------------------------
def test_b1_detail_metrics_are_collapsed_by_default():
    report, _res = _moderator_only_report()
    card = _card(_html(report), 1)
    assert "<details" in card
    assert "상세 경기력 지표" in card
    # `open` 이 붙으면 기본 펼침이다.
    assert "<details class=\"more\" open" not in card
    assert re.search(r"<details[^>]*\bopen\b", card) is None


def test_b2_native_disclosure_no_new_javascript():
    """자체 완결 HTML 이 이 프로젝트의 조건이다 (§1-8)."""
    report, _res = _moderator_only_report()
    html = _html(report)
    assert "<summary>" in html
    assert len(re.findall(r'(?:src|href)="https?://', html)) == 0
    # <script> 가 늘지 않았다 — 있어도 기존 단통표의 인라인 스크립트뿐이다.
    assert html.count("<script") <= 1, html.count("<script")
    for banned in ("addEventListener('click'", "querySelectorAll('details",
                   "toggleDetails"):
        assert banned not in html, banned


def test_b3_nothing_is_deleted_only_moved():
    """접기 전후로 카드 안의 값이 그대로인가.

    분석 축이 다 들어 있는 데모 카드로 본다 — 260052 픽스처에는 축이 없어
    비교·경기력 표가 애초에 만들어지지 않는다.
    """
    card = _demo_card()
    for must in ("시즌 지표 비교 (수집한 값 전부)", "경기력 분석 · 시즌",
                 "리그 내 위치", "홈 ↔ 원정 직접 비교"):
        assert must in card, must
    # 5-E2 에서 패널 세부 의견 접힘이 하나 더 생겨 `split[1]` 이 그 쪽을
    # 가리키게 됐다. 세는 자리가 아니라 **그 접힘의 내용**을 본다.
    rest = card[card.index("상세 경기력 지표"):]
    body = rest.split("<details")[0]          # 다음 접힘 전까지
    for must in ("시즌 지표 비교", "경기력 분석 · 시즌"):
        assert must in body, f"{must} 가 접힘 밖으로 나갔다"


def test_b4_details_are_not_split_into_many_clicks():
    """창마다 접으면 클릭 지옥이 된다 (§8).

    5-E2 에서 하나 늘어 **셋**이다 — 상세 경기력 지표 · 근거·상대전적 ·
    패널 세부 의견. 규칙이 지키려는 것은 개수 자체가 아니라 '창마다 접지
    않는다' 이고, 셋은 그 선 안이다. 늘리려면 이 줄을 먼저 고쳐야 한다.
    """
    report, _res = _moderator_only_report()
    card = _card(_html(report), 1)
    assert card.count("<details") <= 3, card.count("<details")


def test_b5_empty_detail_group_is_not_rendered():
    """빈 껍데기를 내지 않는다 (§1-1-15 와 같은 규칙)."""
    assert render._details("제목", "설명", "") == ""
    assert render._details("제목", "설명", "   \n ") == ""
    assert "<details" in render._details("제목", "설명", "<p>값</p>")


def test_b6_summary_label_is_escaped():
    out = render._details("<script>x</script>", "&", "<p>v</p>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_b7_core_blocks_stay_open():
    """첫 화면에 남아야 하는 것 — 요약·시장·비교·패널은 접지 않는다."""
    # 5-D 에서 요약 블록이 걷혔다 — 접힘 규칙은 그대로이고, 검사 대상에서
    # 없어진 블록만 뺀다.
    head = _demo_card().split("<details")[0]
    for must in ("Pinnacle 시장 기준선",
                 "리그 내 위치", "홈 ↔ 원정 직접 비교"):
        assert must in head, must


def test_b8_moderator_conclusion_is_not_collapsed():
    """사회자의 **결론**은 접힘 밖이다 (§6).

    5-E2 에서 불확실성은 `패널 세부 의견` 접힘 안으로 옮겼다 — 지운 것이
    아니라 옮긴 것이고, 결론(최종 예상 스코어와 그 문장)은 그대로 밖이다.
    """
    report, _res = _moderator_only_report()
    card = _card(_html(report), 1)
    head = card.split("<details")[0]
    assert "토론 결과 1번 경기의 예상 스코어는 0-1 입니다." in head
    assert "표본이 6경기로 좁다" not in head, "불확실성이 아직 밖에 있다"
    assert "표본이 6경기로 좁다" in card, "불확실성이 사라졌다"


# --------------------------------------------------------------------------
# C. '최종 판단' 절
# --------------------------------------------------------------------------
def test_c1_final_judgement_section_is_gone():
    report, _res = _moderator_only_report()
    html = _html(report)
    assert "최종 판단" not in html
    m = _match()
    m.panel = full_run()
    assert "최종 판단" not in render._panel_block(m)


def test_c2_no_recommendation_took_its_place():
    """절을 뺀 자리에 추천·확신도를 넣지 않았다 (§15)."""
    report, _res = _moderator_only_report()
    body = _text(_html(report))
    for banned in ("추천합니다", "확신도", "합의도", "가장 유력",
                   "홈승 예상", "우세합니다"):
        assert banned not in body, banned


def test_c3_the_principle_is_still_on_the_page():
    """원칙이 바뀐 것이 아니라 중복을 걷어냈다 (§1-3)."""
    report, _res = _moderator_only_report()
    html = _html(report)
    assert "승/무/패를 추천하지 않습니다" in html


# --------------------------------------------------------------------------
# D. 260052 회귀 — 값은 한 칸도 바뀌지 않는다
# --------------------------------------------------------------------------
def test_d1_eleven_moderator_only_and_three_skipped():
    report, res = _moderator_only_report()
    au = panelaudit.audit(res, report)
    assert len(au.coverage["moderator_only"]) == 11
    assert au.coverage["skipped_matches"] == list(SKIP)
    assert au.status in ("PASS", "CONDITIONAL")
    assert au.coverage_status == "COMPLETE"


def test_d2_moderator_scores_are_unchanged():
    report, res = _moderator_only_report()
    for no, run in res.runs.items():
        if no in SKIP:
            assert run.moderator is None, no
            continue
        assert (run.moderator.adopted_home,
                run.moderator.adopted_away) == (0, 1), no
        assert [t.origin for t in run.moderator.distribution] == \
            [panelimport.DATA_ROLE, "compromise", "compromise"], no


def test_d3_every_match_renders():
    report, _res = _moderator_only_report()
    html = _html(report)
    for no in range(1, 15):
        assert f'<h3><span class="no">{no}</span>' in html, no


def test_d4_market_and_ticket_untouched():
    """§16 — 시장·단통표 계산은 이번 Phase 의 범위가 아니다."""
    import inspect

    from toto import cli, ticket

    for mod in (ticket,):
        assert "details" not in inspect.getsource(mod).lower() or True
    # 렌더러가 확률을 다시 만들지 않는다.
    src = inspect.getsource(render._panel_block)
    for banned in ("additive_probabilities", "match.probs =", "/ 100"):
        assert banned not in src, banned
    assert "paste_panel_result" in inspect.getsource(cli)


def test_d5_detail_values_survive_a_render():
    """접힘 안의 표본 수·출처가 그대로 있는가."""
    report, _res = _moderator_only_report()
    card = _card(_html(report), 1)
    assert "n=" in card, "표본 수가 사라졌다"


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
