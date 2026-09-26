"""요약 카드의 1·2단계 최초 스코어 — 분석가 의견에서 읽는다 (§1-50).

6-F-14 로 반영한 결과(`panel-work`)는 두 분석가의 `PanelOpinion` 을 통째로
싣지만 `initial_scores` 칸은 없다. 요약 카드의 작은 줄은 그 칸만 읽고
있었기 때문에, 데이터가 멀쩡한데도 화면에 한 줄도 나오지 않았다
(실측 260054: `<p class="init">` 0건).

이 스위트가 지키는 것.

  A. `initial_scores` 가 비어 있으면 **의견의 스코어를 그대로** 보여 준다
  B. 역할로 찾는다 — 의견 순서에 기대지 않는다
  C. `initial_scores` 가 있으면 **기존 동작 그대로**다
  D. 사회자 채택 스코어를 최초 스코어로 복제하지 않는다
  E. `None` 은 줄에서 빠진다 — 0 으로 채우지 않는다
  F. 바뀌는 것은 요약 카드의 그 줄뿐이고 **데이터는 한 칸도 바뀌지 않는다**

**실제 모델을 부르지 않는다.** 데이터는 6-F-14 스위트의 픽스처를 그대로
쓴다 (§1-8) — 두 분석가의 스코어가 경기마다 다르고 13번은 B 가 `null` 이다.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import panel, panelimport, panelpaste, render  # noqa: E402
from toto.models import InitialScore                     # noqa: E402

from test_panel_apply import (                           # noqa: E402
    PLAN, c_rows, dump, imported, make_report, scratch, settings)

_PASSED = _FAILED = 0
DA, MU = panel.DATA_ANALYST, panel.MATCHUP_ANALYST
KO = {DA: "데이터 분석가", MU: "맞대결·전술 분석가"}


def check(name, fn):
    global _PASSED, _FAILED
    try:
        fn()
    except AssertionError as exc:
        _FAILED += 1
        print(f"  FAIL {name}: {exc}")
    except Exception as exc:                                # noqa: BLE001
        _FAILED += 1
        print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    else:
        _PASSED += 1
        print(f"  ok   {name}")


def label(pair):
    return "" if pair is None else f"{pair[0]}-{pair[1]}"


def expected_pairs(no):
    a, b, _kind = PLAN[no]
    out = [(KO[DA], label(a))]
    if b is not None:
        out.append((KO[MU], label(b)))
    return out


def old_initial_pairs(run):
    """수정 전 구현 그대로 — `initial_scores` 만 읽는다 (대조용)."""
    out = []
    for item in getattr(run, "initial_scores", ()) or ():
        if item.label:
            out.append((render._ROLE_KO.get(item.role, item.role), item.label))
    return out


_READY = None


def ok_report():
    """6-F-14 경로(`panel-work`)로 반영한 회차. 한 번 만들어 나눠 쓴다."""
    global _READY
    if _READY is None:
        _READY = imported()[0]
    return _READY


# ==========================================================================
# A. 의견에서 읽는다
# ==========================================================================
def test_a1_every_match_shows_the_analyst_scores():
    report = ok_report()
    for m in report.matches:
        assert m.panel.initial_scores == (), "픽스처 전제가 틀렸다"
        assert render._initial_pairs(m.panel) == expected_pairs(m.no), m.no


def test_a2_values_are_the_opinions_own_values():
    """새 값이 아니라 `PanelOpinion` 의 그 수다."""
    report = ok_report()
    for m in report.matches:
        ops = {o.role: o for o in m.panel.opinions}
        want = [(KO[r], f"{ops[r].predicted_home}-{ops[r].predicted_away}")
                for r in (DA, MU)
                if ops[r].predicted_home is not None
                and ops[r].predicted_away is not None]
        assert render._initial_pairs(m.panel) == want, m.no


def test_a3_summary_card_now_has_the_line():
    report = ok_report()
    html = render.render_report(report, settings())
    assert html.count('<p class="init">') == 14
    assert "1·2단계 최초 스코어 정보 없음" not in html
    assert "Moderator 결과만 반영" not in html
    assert "데이터 분석가 <b>2-1</b> · 맞대결·전술 분석가 <b>0-0</b>" in html


# ==========================================================================
# B. 역할로 찾는다
# ==========================================================================
def test_b1_opinion_order_does_not_matter():
    report = ok_report()
    for m in report.matches:
        flipped = dataclasses.replace(
            m.panel, opinions=tuple(reversed(m.panel.opinions)))
        assert render._initial_pairs(flipped) == \
            render._initial_pairs(m.panel), m.no


def test_b2_order_is_data_then_matchup():
    run = ok_report().matches[0].panel
    assert [p[0] for p in render._initial_pairs(run)] == [KO[DA], KO[MU]]


# ==========================================================================
# C. `initial_scores` 가 있으면 기존 동작 그대로
# ==========================================================================
def test_c1_initial_scores_win_over_opinions():
    run = ok_report().matches[0].panel
    snap = dataclasses.replace(
        run, initial_scores=(InitialScore(role=MU, home=5, away=4),))
    assert render._initial_pairs(snap) == [(KO[MU], "5-4")]
    assert render._initial_pairs(snap) == old_initial_pairs(snap)


def test_c2_moderator_only_runs_are_unchanged():
    """사회자 결과만 들어온 경기 — 의견이 없으니 여전히 빈 줄이다."""
    report = make_report()
    base = scratch()
    path, _res = panelpaste.apply(dump(c_rows(report)), report, None, base)
    panelimport.run(path, report, None)
    for m in report.matches:
        assert render._initial_pairs(m.panel) == []
    html = render.render_report(report, settings())
    assert html.count("1·2단계 최초 스코어 정보 없음") == 14
    assert html.count('<p class="init">') == 0


def test_c3_nothing_at_all_stays_empty():
    run = dataclasses.replace(ok_report().matches[0].panel,
                              opinions=(), initial_scores=())
    assert render._initial_pairs(run) == []
    assert render._initial_line(run) == ""


# ==========================================================================
# D. 사회자 스코어를 복제하지 않는다 · E. None 은 빠진다
# ==========================================================================
def test_d1_moderator_score_is_not_an_initial_score():
    """4번은 절충(1-1)을 채택했다 — 최초 스코어 줄에 1-1 이 없어야 한다."""
    m = next(x for x in ok_report().matches if x.no == 4)
    assert (m.panel.moderator.adopted_home,
            m.panel.moderator.adopted_away) == (1, 1)
    assert render._initial_pairs(m.panel) == [(KO[DA], "2-0"), (KO[MU], "0-2")]


def test_d2_only_analyst_roles_appear():
    roles = {p[0] for m in ok_report().matches
             for p in render._initial_pairs(m.panel)}
    assert roles <= {KO[DA], KO[MU]}, roles


def test_e1_null_score_is_left_out_not_zero():
    m = next(x for x in ok_report().matches if x.no == 13)
    assert render._initial_pairs(m.panel) == [(KO[DA], "3-2")]


# ==========================================================================
# F. 바뀌는 것은 그 줄뿐이다
# ==========================================================================
def test_f1_only_the_summary_line_is_added():
    """새 HTML 에서 `<p class="init">…</p>` 만 걷으면 옛 HTML 과 같다."""
    import re

    report = ok_report()
    new = render.render_report(report, settings())
    saved = render._initial_pairs
    render._initial_pairs = old_initial_pairs
    try:
        old = render.render_report(report, settings())
    finally:
        render._initial_pairs = saved
    stripped = re.sub(r'<p class="init">.*?</p>', "", new)
    # 생성 시각 줄은 렌더마다 달라질 수 있어 같은 자리에서 걷는다.
    clean = lambda h: re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?", "",
                             h)
    assert clean(stripped) == clean(old)


def test_f2_render_does_not_touch_the_data():
    report = ok_report()
    before = [copy.deepcopy(m.panel) for m in report.matches]
    render.render_report(report, settings())
    for m, snap in zip(report.matches, before):
        assert m.panel == snap, m.no
        assert m.panel.initial_scores == ()


def test_f3_panel_result_file_is_not_touched():
    report, base, path, _out, _audit = imported(make_report())
    raw = path.read_bytes()
    render.render_report(report, settings())
    assert path.read_bytes() == raw
    assert "initial_scores" not in json.loads(raw)["matches"][0]


def test_f4_no_arithmetic_in_the_fallback():
    """새 수치를 만들지 않는다 — 더하기·비교·평균이 없다."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(render._initial_pairs).lstrip())
    for node in ast.walk(tree):
        assert not isinstance(node, ast.BinOp), ast.dump(node)
        if isinstance(node, ast.Compare):
            for op in node.ops:
                assert isinstance(op, (ast.In, ast.NotIn, ast.Is,
                                       ast.IsNot)), ast.dump(node)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("sum", "round", "max", "min")
    src = inspect.getsource(render._initial_pairs)
    for bad in ("adopted_home", "adopted_away", "distribution",
                "adopted_from", "analyst_a", "analyst_b", "panel_work"):
        assert bad not in src, bad


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
