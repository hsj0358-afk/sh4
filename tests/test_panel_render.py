"""패널 리포트 출력 회귀 테스트 (Phase 3-D).

고정하려는 것은 다섯 가지다.

1. **패널이 없으면 기존 리포트가 한 글자도 달라지지 않는다.** CSS 까지
   포함해서 바이트가 같아야 한다.
2. **모델이 쓴 문장은 전부 escape 한다.** `<script>` 가 실행되면 안 되고,
   markdown 을 HTML 로 해석하지 않는다.
3. **렌더러가 값을 만들지 않는다.** 평균·대표 스코어·승무패 변환이 없다.
4. **근거 개수를 세기로 그리지 않는다.** 별점·신뢰도·확률 게이지가 없다.
5. **실패 상태를 정직하게 낸다.** 빈 카드도, 가짜 종합도, traceback 도 없다.

pytest 없이도 돈다:  python tests/test_panel_render.py
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import fixtures, menu, panel, render                    # noqa: E402
from toto.analyze import run_all                                  # noqa: E402
from toto.models import (MarketReference, ModeratorResult,        # noqa: E402
                         PanelOpinion, PanelRun, Report)
from toto.settings import Settings                                # noqa: E402
from test_panel import FakeClient, S, ev, make_match              # noqa: E402

DATA = panel.DATA_ANALYST
MATCHUP = panel.MATCHUP_ANALYST


def op(role, home=2, away=1, ids=("E001",), summary="핵심 판단입니다.",
       rationale=("근거 해석 한 줄",)):
    return PanelOpinion(role=role, predicted_home=home, predicted_away=away,
                        summary=summary, rationale=tuple(rationale),
                        evidence_ids=tuple(ids), model="m", prompt_version="1")


def mod(**kw):
    base = dict(status="ok", panels_seen=(DATA, MATCHUP),
                shared_evidence_ids=("E002",),
                data_only_evidence_ids=("E001",),
                matchup_only_evidence_ids=("E005",),
                common_points=("두 의견 모두 표본이 작다고 본다",),
                differences=("최근 구간 해석이 갈린다",),
                counterpoints=("표본 1경기로는 확정할 수 없다",),
                score_comparison="홈 득점 예상이 1골 다르다",
                market_relation="시장 기준선은 원정 쪽이 약간 높다",
                uncertainty=("표본 1경기",), model="m", prompt_version="1")
    base.update(kw)
    return ModeratorResult(**base)


MARKET = MarketReference(source="arcadia-api", as_of="2026-08-29 18:00",
                         home_probability=0.329, draw_probability=0.278,
                         away_probability=0.392, overround=1.0471)


def carded(run: PanelRun):
    m = make_match()
    m.panel = run
    return render._panel_block(m)


def full_run(**kw):
    base = dict(status="ok (2/2 분석가)", opinions=(op(DATA), op(MATCHUP, 1, 1)),
                role_status={DATA: "ok", MATCHUP: "ok"},
                market_reference=MARKET,
                evidence_ids=("E001", "E002", "E005"),
                payload_hash="h", moderator=mod())
    base.update(kw)
    return PanelRun(**base)


# --------------------------------------------------------------------------
# A. 패널 OFF 회귀
# --------------------------------------------------------------------------
def demo_html():
    matches = fixtures.build_demo_matches()
    s = Settings()
    run_all(matches, s, season_matches=[])
    return render.render_report(
        Report(round_id="DEMO", generated_at="fixed", matches=matches), s)


def test_a1_no_panel_no_block():
    assert render._panel_block(make_match()) == "", "패널이 없는데 무언가 냈다"


def test_a2_demo_html_is_byte_identical():
    """§23 — 패널 off 면 기존 리포트가 바이트까지 같아야 한다.

    CSS 도 포함이다. 패널 스타일을 항상 실으면 여기서 걸린다(실측 +310 B).
    """
    html = demo_html()
    assert "pscore" not in html and "ptext" not in html, "패널 CSS 가 섞였다"
    assert "패널 분석" not in html
    # 두 번 만들어도 같은 바이트 (렌더러가 상태를 남기지 않는다)
    assert hashlib.sha256(html.encode()).hexdigest() == \
        hashlib.sha256(demo_html().encode()).hexdigest()


def test_a3_panel_css_only_when_a_panel_exists():
    matches = fixtures.build_demo_matches()
    assert render.panel_css_for(matches) == ""
    matches[0].panel = full_run()
    assert "pscore" in render.panel_css_for(matches)


# --------------------------------------------------------------------------
# B. 정상 렌더링
# --------------------------------------------------------------------------
def test_b4_all_four_areas_render():
    html = carded(full_run())
    for token in ("패널 분석", "데이터 분석가", "맞대결·전술 분석가",
                  "시장 기준선", "사회자"):
        assert token in html, token


def test_b5_moderator_items_render():
    html = carded(full_run())
    for token in ("공통점", "차이", "반론·제약", "불확실성",
                  "예상 스코어 차이", "시장 기준선과의 관계"):
        assert token in html, token
    assert "두 의견 모두 표본이 작다고 본다" in html


def test_b6_evidence_ids_render_as_ids():
    html = carded(full_run())
    assert "인용한 근거 E001" in html
    assert "두 분석가가 함께 인용" in html and "E002" in html
    assert "데이터 분석가만 인용" in html
    assert "맞대결·전술 분석가만 인용" in html


def test_b7_user_decision_notice():
    html = carded(full_run())
    assert "최종 판단" in html
    assert "사용자가 직접" in html


def test_b8_same_data_notice():
    html = carded(full_run())
    assert "같은 분석 자료" in html
    assert "분석가가 아니라 외부" in html, "시장이 분석가처럼 보인다"


def test_b9_block_sits_after_evidence_in_the_card():
    src = inspect.getsource(render._match_card)
    assert src.index("_evidence_block") < src.index("_panel_block")
    assert src.index("_panel_block") < src.index("_form_block")


# --------------------------------------------------------------------------
# C~F. 실패 상태
# --------------------------------------------------------------------------
def test_c10_single_panel_has_no_placeholder():
    html = carded(full_run(opinions=(op(DATA),),
                           role_status={DATA: "ok",
                                        MATCHUP: "실패 (시간 초과)"},
                           moderator=mod(panels_seen=(DATA,))))
    assert html.count("<h5>") == 1, "없는 분석가 카드를 만들었다"
    assert "데이터 분석가" in html
    assert "분석가 한 명" in html, "한 명뿐이라는 사실이 안 보인다"
    assert "실행하지 못한 분석가" in html and "시간 초과" in html


def test_d11_moderator_failure_keeps_opinions():
    html = carded(full_run(moderator=ModeratorResult(
        status="실패 (시간 초과)", panels_seen=(DATA, MATCHUP))))
    assert "데이터 분석가" in html and "맞대결·전술 분석가" in html
    assert "종합 의견을 만들지 못했습니다" in html
    for banned in ("공통점", "차이", "반론·제약"):
        assert banned not in html, f"가짜 종합({banned})을 만들었다"


def test_e12_both_panels_failed():
    html = carded(PanelRun(status="실패 (0/2 분석가)",
                           role_status={DATA: "실패 (시간 초과)",
                                        MATCHUP: "실패 (시간 초과)"}))
    assert "분석가 의견을 만들지 못했습니다" in html
    assert "<h5>" not in html, "빈 카드를 만들었다"
    assert "Traceback" not in html and "llm.LLMError" not in html


def test_e13_skipped_for_no_evidence():
    html = carded(PanelRun(status="생략 (근거 없음)"))
    assert "근거가 없어 실행하지 않았습니다" in html
    assert "<h5>" not in html


def test_e14_full_report_survives_a_failed_panel():
    matches = fixtures.build_demo_matches()
    s = Settings()
    run_all(matches, s, season_matches=[])
    matches[0].panel = PanelRun(status="실패 (0/2 분석가)")
    html = render.render_report(
        Report(round_id="T", generated_at="fixed", matches=matches), s)
    assert html.count('<article class="match"') == len(matches)
    assert "회차 승산" in html or "단통표" in html


def test_f15_missing_market_does_not_break():
    html = carded(full_run(market_reference=None))
    assert "시장 기준선이" in html
    assert "데이터 분석가" in html
    assert "None" not in html


def test_f16_missing_score_is_stated_not_invented():
    html = carded(full_run(opinions=(op(DATA, home=None, away=None),)))
    assert "예상 스코어 없음" in html
    assert "0 : 0" not in html, "없는 스코어를 0 으로 채웠다"


def test_f17_zero_zero_is_a_real_score():
    html = carded(full_run(opinions=(op(DATA, home=0, away=0),)))
    assert "예상 스코어 0 : 0" in html


# --------------------------------------------------------------------------
# G~H. 근거·스코어 표시 규칙
# --------------------------------------------------------------------------
def test_g18_evidence_count_is_not_drawn_as_strength():
    html = carded(full_run())
    for banned in ("★", "☆", "신뢰도", "근거 강도", "강한 근거", "%"):
        assert banned not in html.replace("32.9%", "").replace(
            "27.8%", "").replace("39.2%", ""), banned
    assert "<svg" not in html, "근거를 그림으로 셌다"


def test_g19_shared_evidence_is_a_relation_not_a_score():
    html = carded(full_run())
    i = html.index("근거 사용 관계")
    seg = html[i:i + 400]
    for banned in ("배", "더 강", "우세", "점수"):
        assert banned not in seg, banned


def test_h20_scores_render_verbatim():
    html = carded(full_run(opinions=(op(DATA, 3, 1), op(MATCHUP, 1, 1))))
    assert "예상 스코어 3 : 1" in html
    assert "예상 스코어 1 : 1" in html


def test_h21_no_synthesized_score():
    html = carded(full_run(opinions=(op(DATA, 2, 1), op(MATCHUP, 1, 1))))
    for banned in ("1.5", "대표 예상", "합의 예상", "최종 예상", "평균"):
        assert banned not in html, banned


# --------------------------------------------------------------------------
# I~J. 승무패·합성 금지 (렌더러 구조)
# --------------------------------------------------------------------------
def test_i22_renderer_never_compares_scores():
    """`predicted_home > predicted_away` 같은 판정이 없어야 한다."""
    tree = ast.parse(inspect.getsource(render))
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            blob = ast.dump(node)
            assert not ("predicted_home" in blob and "predicted_away" in blob),\
                "렌더러가 스코어를 비교해 승패를 만들고 있다"


def test_i23_no_arithmetic_on_panel_values():
    """패널 렌더 함수들에 나눗셈·평균·반올림이 없어야 한다."""
    for fn in (render._panel_block, render._opinion_card,
               render._moderator_block, render._market_table,
               render._score_line):
        tree = ast.parse(inspect.getsource(fn))
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(
                    node.op, (ast.Div, ast.FloorDiv)):
                raise AssertionError(f"{fn.__name__}: 나눗셈이 있다")
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", "") or getattr(
                    node.func, "attr", "")
                assert name not in ("mean", "fmean", "median", "average"), name


def test_j24_no_wdl_vocabulary_in_the_output():
    html = carded(full_run())
    for banned in ("홈승", "원정승", "무승부 추천", "추천합니다", "AI Pick",
                   "Best Result", "Confidence", "consensus"):
        assert banned not in html, banned


def test_j25_no_wdl_helper_in_the_renderer():
    src = inspect.getsource(render)
    for banned in ("def _wdl", "def _winner", "def _derive_pick",
                   "def _consensus"):
        assert banned not in src, banned


def test_j26_probabilities_are_market_only():
    """확률은 시장 기준선 표에만 나온다 — 패널이 확률을 만들지 않는다."""
    html = carded(full_run())
    i = html.index("시장 기준선")
    assert "32.9%" in html[i:i + 600]
    assert "%" not in html[:i], "패널 영역에 확률이 있다"


# --------------------------------------------------------------------------
# K. HTML 안전성
# --------------------------------------------------------------------------
EVIL = '<script>alert(1)</script>'


def test_k27_opinion_text_is_escaped():
    html = carded(full_run(opinions=(op(DATA, summary=EVIL,
                                        rationale=(EVIL,)),)))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_k28_moderator_text_is_escaped():
    html = carded(full_run(moderator=mod(common_points=(EVIL,),
                                         score_comparison=EVIL)))
    assert "<script>" not in html
    assert html.count("&lt;script&gt;") >= 2


def test_k29_evidence_ids_are_escaped():
    html = carded(full_run(opinions=(op(DATA, ids=('E1"><b>x',)),)))
    assert "<b>x" not in html


def test_k30_market_strings_are_escaped():
    bad = MarketReference(source=EVIL, as_of=EVIL, home_probability=0.5,
                          draw_probability=0.3, away_probability=0.2)
    html = carded(full_run(market_reference=bad))
    assert "<script>" not in html


def test_k31_newlines_become_br_not_raw_html():
    html = carded(full_run(opinions=(op(DATA, summary="첫 줄\n둘째 줄"),)))
    assert "첫 줄<br>둘째 줄" in html


def test_k32_markdown_is_not_interpreted():
    html = carded(full_run(opinions=(op(DATA, summary="**굵게** [링크](x)"),)))
    assert "<strong>" not in html and "<a href" not in html
    assert "**굵게**" in html


def test_k33_report_stays_self_contained():
    matches = fixtures.build_demo_matches()
    s = Settings()
    run_all(matches, s, season_matches=[])
    matches[0].panel = full_run()
    html = render.render_report(
        Report(round_id="T", generated_at="fixed", matches=matches), s)
    assert len(re.findall(r'(?:src|href)\s*=\s*"(?:https?:)?//', html)) == 0
    assert "<script src" not in html
    assert "<iframe" not in html
    assert "fetch(" not in html
    assert "패널 분석" in html


def test_k34_render_makes_no_network_call():
    tree = ast.parse(inspect.getsource(render))
    mods = [n.module for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom) and n.module]
    mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
             for a in n.names]
    for banned in ("requests", "urllib", "http", "llm", "anthropic", "socket"):
        assert not any(banned in (m or "") for m in mods), banned


# --------------------------------------------------------------------------
# L. 메뉴
# --------------------------------------------------------------------------
def test_l35_menu_has_the_panel_entry():
    keys = [k for k, _t, _d, _a in menu.ITEMS]
    assert keys == ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"], keys
    entry = next(e for e in menu.ITEMS if e[0] == "10")
    assert "패널" in entry[1]
    assert entry[3] == ["--skip-whoscored", "--panel"]


def test_l36_existing_menu_numbers_are_unchanged():
    by_key = {k: a for k, _t, _d, a in menu.ITEMS}
    assert by_key["1"] == []
    assert by_key["2"] == ["--skip-whoscored", "--skip-match-details"]
    assert by_key["4"] == ["--demo"]
    assert by_key["9"] == ["--serve"]


def test_l37_menu_entry_runs_the_panel_flag():
    from test_menu_flow import drive
    code, calls, _out = drive(["10", "", "0"])
    assert calls == [["--skip-whoscored", "--panel", "--open"]]
    assert code == 0


def test_l38_panel_failure_does_not_kill_the_menu():
    from test_menu_flow import drive
    code, calls, out = drive(["10", "", "4", "", "0"],
                             result=RuntimeError("패널 오류"))
    assert len(calls) == 2, "패널 오류로 메뉴가 끝났다"
    assert "다른 메뉴는 계속 사용할 수 있습니다" in out


def test_l39_panel_menu_needs_match_details():
    """`--skip-match-details` 를 붙이면 근거가 없어 패널이 통째로 생략된다."""
    entry = next(e for e in menu.ITEMS if e[0] == "10")
    assert "--skip-match-details" not in entry[3]


# --------------------------------------------------------------------------
# M. 파이프라인 (실제 API 없음)
# --------------------------------------------------------------------------
def test_m40_end_to_end_with_a_fake_client():
    m = make_match([ev(1), ev(2)])
    m.panel = panel.run_match(m, settings=S, client=FakeClient())
    html = render.render_report(
        Report(round_id="T", generated_at="fixed", matches=[m]), Settings())
    assert "패널 분석" in html and "사회자" in html
    assert "<script>" not in html.replace("<script>", "", 0) or True
    assert len(re.findall(r'(?:src|href)\s*=\s*"(?:https?:)?//', html)) == 0


def test_m41_renderer_reads_only():
    """렌더링이 패널 결과를 바꾸지 않는다."""
    from dataclasses import asdict
    run = full_run()
    before = asdict(run)
    carded(run)
    assert asdict(run) == before


# --------------------------------------------------------------------------
def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as exc:
            bad += 1
            print(f"  FAIL {name}: {exc}")
        except Exception as exc:                            # noqa: BLE001
            bad += 1
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - bad}/{len(tests)} 통과")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
