"""리포트 정보 구조 + 1·2단계 최초 스코어 보존 회귀 테스트 (Phase 4-G).

고정하려는 것은 다섯 가지다.

1. **시장 중심 최상단이 리포트에서 빠졌다.** 회차 승산·단통표·직관 적용
   후보 세 블록이 맨 위를 차지하고 있으면 이 리포트의 출발점이 시장이
   된다. **계산은 지우지 않았다** — 표현 계층에서만 내렸다.
2. **14경기 한눈에 보기의 중심이 Panel 종합 예상 스코어다.** 시장 확률
   막대는 카드에서 빠지고 경기 상세의 `Pinnacle 시장 기준선` 에 남는다.
3. **1·2단계의 최초 예상 스코어만 보존한다.** `initial_scores` 는 스코어
   두 개짜리 스냅샷이고 **분석가 원문이 아니다** — 있어도 `MODERATOR_ONLY`
   이고 패널 제목도 그대로다.
4. **역추론하지 않는다.** `distribution.origin`·`adopted_from`·`conclusion`
   에서 최초 스코어를 만들지 않고, 사회자 채택 스코어를 복사하지도 않는다.
5. **경기 상세는 리그 위치 → 최근 폼 → 직접 비교 → 패널 순이고, 폼은
   접힘 밖이다.** 접힘 안의 값은 하나도 줄지 않았다.

pytest 없이도 돈다:  python tests/test_report_ia.py
"""
from __future__ import annotations

import copy
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import panelaudit, panelexport, panelimport, panelpaste, render  # noqa: E402
from toto.models import InitialScore, Report                               # noqa: E402
from toto.settings import Settings                                         # noqa: E402

import test_panel_paste as P                                               # noqa: E402
from test_panel_render import full_run                                     # noqa: E402

DA, MU = panelimport.DATA_ROLE, panelimport.MATCHUP_ROLE
INI = panelimport.INITIAL_SCORES
SKIP = P.SKIP

# Fixture A — 실물 260052 모양 (initial_scores 없음).
FIXTURE_A = P.FIXTURE
# Fixture B — 같은 모양에 최초 스코어를 실은 것. **구조 검증용이고 실제
# 분석 결과라고 주장하지 않는다** (§30).
FIXTURE_B = Path(__file__).with_name("fixtures").joinpath(
    "260052_moderator_result_initial.json")


# --------------------------------------------------------------------------
# 공통 도구
# --------------------------------------------------------------------------
def _text(html: str) -> str:
    """화면에 실제로 보이는 글자만 (태그 속성값을 검사에서 뺀다)."""
    return re.sub(r"<[^>]+>", " ", html)


def _imported(fixture: Path):
    """붙여넣기 → 검증 → 부착. (report, ImportResult)."""
    report = P._report()
    base = Path(tempfile.mkdtemp())
    path, res = panelpaste.apply(fixture.read_text(encoding="utf-8"),
                                 report, P.S, base=base)
    assert path is not None, [str(i) for i in res.issues]
    panelimport.attach(res, report)
    return report, res


def _html(report) -> str:
    return render.render_report(report, Settings())


def _card(html: str, no: int) -> str:
    mark = f'<h3><span class="no">{no}</span>'
    assert mark in html, no
    return html.split(mark)[1].split("<h3>")[0]


def _sumcard(html: str, no: int) -> str:
    """요약 그리드의 카드 하나."""
    parts = html.split('<a class="sumcard" href="#m')
    for chunk in parts[1:]:
        if chunk.startswith(f"{no}\""):
            return chunk.split("</a>")[0]
    raise AssertionError(f"{no}번 요약 카드가 없다")


def _demo_report(with_panel: bool = True) -> Report:
    from toto import fixtures as demo
    from toto.analyze import run_all

    matches = demo.build_demo_matches()
    s = Settings()
    run_all(matches, s, season_matches=[])
    if with_panel:
        for m in matches:
            m.panel = full_run()
    return Report(round_id="DEMO", generated_at="fixed", matches=matches)


# ==========================================================================
# A. 최초 스코어 보존
# ==========================================================================
def test_a1_stage_three_message_asks_for_initial_scores():
    """§29-1·2 — 3단계 자료가 두 분석가의 최초 스코어를 요구한다."""
    msg = panelexport._moderator_message("260052", 14, warned=False)
    assert INI in msg
    assert DA in msg and MU in msg
    assert "처음" in msg


def test_a2_instructions_document_the_field_without_new_prompt_version():
    """지침에 절이 생겼지만 **프롬프트 버전은 그대로**다 — 1·2·3단계의
    출력 형식 자체가 바뀐 것이 아니라 3단계가 한 칸을 더 적을 뿐이다."""
    from toto import moderator, panel

    body = panelexport.project_instructions()
    assert INI in body
    assert "거꾸로 만들지" in body
    assert panel.PANEL_PROMPT_VERSION == "2"
    assert moderator.MODERATOR_PROMPT_VERSION == "5"


def test_a3_json_step_carries_the_field_into_the_result_file():
    step = panelexport._json_step("260052", 14)
    assert INI in step
    assert "만들지 마십시오" in step


def test_a4_three_different_scores_all_survive():
    """§29-4 — 두 최초 스코어와 사회자 채택이 전부 달라도 모두 남는다."""
    report, _res = _imported(FIXTURE_B)
    run = report.matches[0].panel                 # 1번: DA 2-1 · MU 1-1
    assert run.initial_score(DA).label == "2-1"
    assert run.initial_score(MU).label == "1-1"
    assert (run.moderator.adopted_home, run.moderator.adopted_away) == (0, 1)


def test_a5_origin_is_not_used_to_invent_initial_scores():
    """§29-5 — `distribution.origin` 으로 만들지 않는다.

    Fixture A 의 분포에는 `data_analyst` origin 이 20회 있는데도 최초
    스코어는 **하나도 생기지 않는다**.
    """
    report, _res = _imported(FIXTURE_A)
    run = report.matches[0].panel
    assert run.moderator.distribution
    assert any(t.origin == DA for t in run.moderator.distribution)
    assert run.initial_scores == ()


def test_a6_adopted_from_is_not_used_to_invent_initial_scores():
    """§29-6 — `adopted_from` 에 두 역할이 다 있어도 만들지 않는다."""
    report, _res = _imported(FIXTURE_A)
    run = report.matches[0].panel
    assert set(run.moderator.adopted_from) == {DA, MU}
    assert run.initial_scores == ()


def test_a7_moderator_score_is_never_copied_into_an_initial_score():
    """§29-7 — 사회자 채택 스코어를 분석가 자리에 복사하지 않는다."""
    src = json.loads(FIXTURE_B.read_text(encoding="utf-8"))
    report, _res = _imported(FIXTURE_B)
    for item in src:
        no = item["match_no"]
        run = report.matches[no - 1].panel
        if no in SKIP:
            continue
        adopted = (run.moderator.adopted_home, run.moderator.adopted_away)
        for role in (DA, MU):
            given = (item[INI][role]["home"], item[INI][role]["away"])
            got = run.initial_score(role)
            assert (got.home, got.away) == given, (no, role)
            if given != adopted:
                assert (got.home, got.away) != adopted, (no, role)


def test_a8_old_results_without_the_field_still_import():
    """§29-8 — 260052 처럼 `initial_scores` 가 없는 결과가 그대로 읽힌다."""
    report, res = _imported(FIXTURE_A)
    assert res.success
    assert res.imported_matches == 14
    assert all((m.panel.initial_scores == ()) for m in report.matches)


def test_a9_bad_shapes_are_refused_not_repaired():
    """§29-9 — 고쳐 주지 않는다. `"2"`·`1.5`·`true`·음수·모르는 역할."""
    bad = [
        ({"home": "2", "away": 1}, "INITIAL_SCORE_INVALID"),
        ({"home": 1.5, "away": 1}, "INITIAL_SCORE_INVALID"),
        ({"home": True, "away": 1}, "INITIAL_SCORE_INVALID"),
        ({"home": -1, "away": 1}, "INITIAL_SCORE_INVALID"),
        ("2-1", "INITIAL_SCORE_INVALID"),
    ]
    for value, code in bad:
        data = json.loads(FIXTURE_B.read_text(encoding="utf-8"))
        data[0][INI][DA] = value
        report = P._report()
        _path, res = panelpaste.apply(json.dumps(data), report, P.S,
                                      base=Path(tempfile.mkdtemp()))
        codes = {i.code for i in res.issues}
        assert code in codes, (value, codes)
        assert not res.success

    # 최상위가 객체가 아닐 때 / 모르는 역할 이름일 때
    for mutate, code in (
            (lambda d: d[0].__setitem__(INI, [1, 2]),
             "INITIAL_SCORES_INVALID"),
            (lambda d: d[0][INI].__setitem__("market_reference",
                                             {"home": 1, "away": 0}),
             "INITIAL_SCORES_ROLE_UNKNOWN")):
        data = json.loads(FIXTURE_B.read_text(encoding="utf-8"))
        mutate(data)
        report = P._report()
        _path, res = panelpaste.apply(json.dumps(data), report, P.S,
                                      base=Path(tempfile.mkdtemp()))
        assert code in {i.code for i in res.issues}, code


def test_a10_null_stays_null():
    """§29-10 — 스코어를 내지 않은 분석가를 0-0 으로 채우지 않는다."""
    report, _res = _imported(FIXTURE_B)
    run = report.matches[1].panel                 # 2번: MU 가 null·null
    got = run.initial_score(MU)
    assert got is not None
    assert got.home is None and got.away is None
    assert got.label == ""
    # 화면에도 `0 - 0` 을 만들지 않는다.
    assert "0 - 0" not in _sumcard(_html(report), 2)


def test_a11_the_field_rides_the_artifact_round_trip():
    """저장본으로 되살려도 최초 스코어가 그대로다 (4-C)."""
    from toto import artifact

    report, _res = _imported(FIXTURE_B)
    out = Path(tempfile.mkdtemp())
    artifact.save(report, outdir=out)
    back, err = artifact.load(report.round_id, outdir=out)
    assert back is not None, err
    for before, after in zip(report.matches, back.matches):
        assert before.panel.initial_scores == after.panel.initial_scores
    assert all(isinstance(s, InitialScore)
               for s in back.matches[0].panel.initial_scores)


# ==========================================================================
# B. 회차 요약 카드
# ==========================================================================
def test_b12_summary_has_no_market_probability_bars():
    """§29-11 — 시장 확률 막대·백분율이 카드에서 빠졌다."""
    report, _res = _imported(FIXTURE_A)
    grid = render._summary_grid(report.matches)
    assert "<svg" not in grid
    assert "%" not in grid
    for banned in ("승 ", "무 ", "패 "):
        assert banned not in _text(grid), banned


def test_b13_adopted_score_is_the_largest_thing_on_the_card():
    """§29-12·13 — 종합 스코어가 가장 크고, 그 값은 사회자 채택값이다."""
    report, _res = _imported(FIXTURE_A)
    grid = render._summary_grid(report.matches)
    assert 'class="sumscore"' in grid
    sizes = {k: float(v) for k, v in re.findall(
        r"\.sumcard \.(\w+)\{font-size:([\d.]+)px", render.CSS)}
    assert sizes["sumscore"] > sizes["init"]
    assert sizes["sumscore"] > sizes["sumlab"]
    assert sizes["sumscore"] > sizes["pstate"]

    run = report.matches[0].panel
    home, away = run.moderator.adopted_home, run.moderator.adopted_away
    assert f'<p class="sumscore">{home} - {away}</p>' in _sumcard(grid, 1)


def test_b14_da_initial_score_shows_when_present():
    report, _res = _imported(FIXTURE_B)
    card = _text(_sumcard(_html(report), 1))
    assert "데이터 분석가" in card and "2-1" in card


def test_b15_matchup_initial_score_shows_when_present():
    report, _res = _imported(FIXTURE_B)
    card = _text(_sumcard(_html(report), 1))
    assert "맞대결" in card and "1-1" in card


def test_b16_moderator_only_without_initials_shows_only_the_score():
    """§14 — `데이터 분석가 —` 같은 빈 줄을 늘어놓지 않는다."""
    report, _res = _imported(FIXTURE_A)
    card = _sumcard(_html(report), 1)
    assert "0 - 1" in card
    assert "Moderator 결과만 반영" in card
    assert "데이터 분석가" not in _text(card)
    assert "—" not in card


def test_b17_skipped_match_has_no_score():
    report, _res = _imported(FIXTURE_A)
    card = _sumcard(_html(report), SKIP[0])
    assert "—" in card and "예상 스코어 없음" in card
    assert not re.search(r"\d+ - \d+", _text(card))


def test_b18_skipped_match_says_it_was_skipped():
    report, _res = _imported(FIXTURE_A)
    assert "Panel 생략" in _text(_sumcard(_html(report), SKIP[0]))


def test_b19_no_wdl_label_is_ever_derived():
    """§17·§29-19 — 스코어만 적고 승/무/패로 바꾸지 않는다."""
    for fixture in (FIXTURE_A, FIXTURE_B):
        report, _res = _imported(fixture)
        text = _text(render._summary_grid(report.matches))
        for banned in ("홈승", "원정승", "무승부 예상", "추천", "유력",
                       "승리 예상", "패 예상"):
            assert banned not in text, (fixture.name, banned)


def test_b20_fourteen_cards_and_working_anchors():
    """§29-20·21 — 카드 수와 이동 링크가 그대로다."""
    report, _res = _imported(FIXTURE_A)
    html = _html(report)
    assert html.count('class="sumcard"') == 14
    for no in range(1, 15):
        assert f'href="#m{no}"' in html, no
        assert f'id="m{no}"' in html, no


def test_b21_report_without_any_panel_does_not_promise_a_score():
    """패널이 없는 실행에서 없는 단계를 고장처럼 보이게 하지 않는다 (§1-6)."""
    html = _html(_demo_report(with_panel=False))
    assert "Panel 분석이" in html and "종합 예상 스코어가 없습니다" in html
    assert 'class="sumscore"' not in html


# ==========================================================================
# C. Moderator-only 의 뜻이 바뀌지 않는다
# ==========================================================================
def test_c22_initial_scores_do_not_promote_to_full_opinions():
    """§29-22 — 스코어가 있다는 것과 의견이 있다는 것은 다른 사실이다."""
    report, _res = _imported(FIXTURE_B)
    for no, match in enumerate(report.matches, start=1):
        run = match.panel
        assert run.opinions == (), no
        if no not in SKIP:
            assert run.initial_scores, no
            assert panelimport.is_moderator_only(run), no


def test_c23_state_is_still_moderator_only():
    """§29-23 — 감사의 결정 유형도 그대로다."""
    report, _res = _imported(FIXTURE_B)
    for no, match in enumerate(report.matches, start=1):
        audit = panelaudit.match_audit(match, match.panel)
        want = (panelaudit.PANEL_SKIPPED if no in SKIP
                else panelaudit.MODERATOR_ONLY)
        assert audit.decision_type == want, (no, audit.decision_type)


def test_c24_panel_heading_stays_moderator_only():
    """§23-2·§29-24 — `두 전문가의 해석` 으로 승격하지 않는다."""
    report, _res = _imported(FIXTURE_B)
    card = _card(_html(report), 1)
    assert "패널 분석 (사회자 결과만 반영)" in card
    assert "패널 분석 (두 전문가의 해석)" not in card


def test_c25_moderator_heading_stays_plain():
    """§29-25 — `사회자 (두 의견의 종합)` 로 올라가지 않는다."""
    report, _res = _imported(FIXTURE_B)
    card = _card(_html(report), 1)
    assert "사회자 종합" in card
    assert "두 의견의 종합" not in card


def test_c26_no_analyst_summary_or_rationale_is_fabricated():
    """§3·§29-26 — 요약·근거를 만들어 내지 않는다."""
    report, _res = _imported(FIXTURE_B)
    card = _card(_html(report), 1)
    # 분석가 의견 카드(`_opinion_card`)가 만들어지지 않았다. `.traits` 는
    # 정성 블록도 쓰므로 의견 카드만의 표시로 확인한다.
    assert "인용한 근거" not in card
    assert 'class="pscore"' not in card
    assert "실행하지 못한 분석가" not in card
    for run in (m.panel for m in report.matches):
        for item in run.initial_scores:
            assert set(vars(item)) == {"role", "home", "away"}


def test_c27_no_phantom_single_analyst_sentence():
    """본 의견이 **하나도 없을 때** '한 명의 의견만으로' 라고 적지 않는다.

    3단계 결과만 들어온 경기는 `panels_seen` 이 비어 있는데, 그때 빈 괄호가
    들어간 `분석가 한 명()의 의견만으로` 문장이 나오면 바로 위 줄("원문이
    없습니다")과 정면으로 어긋난다.
    """
    for fixture in (FIXTURE_A, FIXTURE_B):
        report, _res = _imported(fixture)
        html = _html(report)
        assert report.matches[0].panel.moderator.panels_seen == ()
        assert "분석가 한 명" not in html, fixture.name
        assert "명()" not in html, fixture.name


def test_c28_detail_block_marks_the_snapshot_as_scores_only():
    report, _res = _imported(FIXTURE_B)
    card = _text(_card(_html(report), 1))
    assert "1·2단계 최초 예상 스코어" in card
    assert "분석가 원문은 이번 입력에 포함되지 않았습니다" in card


# ==========================================================================
# D. 최상단에서 내린 세 블록
# ==========================================================================
def test_d28_round_verdict_section_is_gone():
    """§29-27 — 회차 승산이 리포트에 없다 (CSS 주석까지)."""
    for report in (_demo_report(True), _imported(FIXTURE_A)[0]):
        html = _html(report)
        assert "회차 승산" not in html
        assert 'class="verdict' not in html
        assert "P(≥11)" not in html


def test_d29_ticket_section_is_gone():
    """§29-28 — 단통표가 리포트에 없다."""
    html = _html(_demo_report(True))
    assert "단통표" not in html
    assert 'class="tk"' not in html and "<script" not in html


def test_d30_tossup_section_is_gone():
    """§29-29 — 직관 적용 후보 절이 최상단에 없다."""
    html = _html(_demo_report(True))
    assert "직관 적용 후보" not in html


def test_d31_the_calculations_are_untouched():
    """§27·§29-30 — 표현만 내렸다. 계산과 그 렌더러는 그대로 있다."""
    import inspect

    from toto import predict, ticket

    report = _demo_report(True)
    assert report.matches[0].probs is not None
    assert hasattr(predict, "round_winnability")
    # 되돌릴 수 있도록 렌더러와 스타일을 남겨 두었다.
    for name in ("_verdict_box", "_tossup_list", "VERDICT_CSS"):
        assert hasattr(render, name), name
    assert callable(ticket.render_ticket)
    assert "def render_ticket" in inspect.getsource(ticket)


def test_d32_market_moves_down_not_away():
    """§11·§26·§29-36 — Pinnacle 시장 기준선은 경기 상세에 그대로 있다."""
    report = _demo_report(True)
    html = _html(report)
    card = _card(html, 1)
    assert "Pinnacle 시장 기준선" in card
    assert "외부 참고값" in _text(card)
    # 요약 그리드보다 뒤에 있다 — 출발점이 아니라 참고값이다.
    assert html.index("14경기 한눈에 보기") < html.index("Pinnacle 시장 기준선")


def test_d33_market_probability_values_are_unchanged():
    """§29-37 — 확률 값 자체는 한 칸도 바뀌지 않았다."""
    report = _demo_report(True)
    html = _html(report)
    for m in report.matches:
        if m.probs is None:
            continue
        ph, pd, pa = m.probs.pct()
        card = _card(html, m.no)
        for value in (ph, pd, pa):
            assert f"{value:.1f}%" in card, (m.no, value)


# ==========================================================================
# E. 경기 상세 순서
# ==========================================================================
def _order(card: str, *marks: str) -> list[int]:
    out = []
    for mark in marks:
        idx = card.find(mark)
        assert idx >= 0, mark
        out.append(idx)
    return out


def test_e34_league_position_comes_before_form():
    """§19·§29-31."""
    card = _card(_html(_demo_report(True)), 1)
    pos, form = _order(card, "리그 내 위치", "최근 5경기")
    assert pos < form


def test_e35_form_comes_before_direct_comparison():
    """§29-32."""
    card = _card(_html(_demo_report(True)), 1)
    form, direct = _order(card, "최근 5경기", "홈 ↔ 원정")
    assert form < direct


def test_e36_form_is_not_inside_a_collapsed_block():
    """§20·§29-33 — 폼은 분위기를 빠르게 읽는 정보라 접지 않는다."""
    card = _card(_html(_demo_report(True)), 1)
    form = card.index("최근 5경기")
    first_details = card.find("<details")
    assert first_details == -1 or form < first_details


def test_e37_detail_metrics_and_evidence_stay_collapsed():
    """§22·§29-34·35 — 4-F 의 접힘 둘은 그대로다."""
    card = _card(_html(_demo_report(True)), 1)
    assert card.count("<details") == 2
    assert re.search(r"<details[^>]*\bopen\b", card) is None
    assert "상세 경기력 지표" in card and "근거 · 상대전적" in card


def test_e38_panel_sits_between_comparison_and_the_collapses():
    card = _card(_html(_demo_report(True)), 1)
    direct, panel_at, details = _order(
        card, "홈 ↔ 원정", "패널 분석", "<details")
    assert direct < panel_at < details


# ==========================================================================
# F. 값이 사라지지 않았다
# ==========================================================================
def test_f39_axis_values_and_samples_survive():
    """§29-38 — 접힘 안의 지표·표본 수가 그대로다."""
    report, _res = _imported(FIXTURE_A)
    card = _card(_html(report), 1)
    assert "n=" in card
    assert "measurement_basis" in card or "source" in card or "n=" in card


def test_f40_evidence_ids_are_unchanged():
    """§29-39 — 근거 ID 와 개수가 그대로다."""
    report, _res = _imported(FIXTURE_A)
    run = report.matches[0].panel
    # 이 경기에서 쓸 수 있던 ID 가 그대로 실려 있고, 없는 ID 가 생기지 않았다.
    assert run.evidence_ids == ("E001", "E002")
    for cited in (run.moderator.shared_evidence_ids
                  + run.moderator.data_only_evidence_ids
                  + run.moderator.matchup_only_evidence_ids):
        assert cited in run.evidence_ids, cited
    assert "E999" not in _html(report)


def test_f41_moderator_text_and_distribution_are_verbatim():
    """§29-41·42 — conclusion·distribution·origin 이 원문 그대로다."""
    src = {item["match_no"]: item
           for item in json.loads(FIXTURE_B.read_text(encoding="utf-8"))}
    report, _res = _imported(FIXTURE_B)
    for no, match in enumerate(report.matches, start=1):
        if no in SKIP:
            continue
        want, mod_out = src[no], match.panel.moderator
        assert mod_out.conclusion == want["conclusion"], no
        assert [(t.home, t.away, t.count, t.origin)
                for t in mod_out.distribution] == \
               [(d["home"], d["away"], d["count"], d["origin"])
                for d in want["distribution"]], no


def test_f42_fixture_a_still_produces_eleven_and_three():
    """§29-45 — 260052 회귀: Moderator-only 11경기 · 생략 3경기."""
    report, res = _imported(FIXTURE_A)
    audit = panelaudit.audit(res, report)
    assert len(audit.coverage["moderator_only"]) == 11
    assert len(audit.coverage["skipped_matches"]) == 3
    assert audit.status == panelaudit.PASS


def test_f43_fixture_b_keeps_the_same_shape():
    """최초 스코어를 실어도 회차 상태가 달라지지 않는다."""
    report, res = _imported(FIXTURE_B)
    audit = panelaudit.audit(res, report)
    assert res.success and res.imported_matches == 14
    assert len(audit.coverage["moderator_only"]) == 11
    assert len(audit.coverage["skipped_matches"]) == 3


def test_f44_canonical_file_round_trips_through_the_file_path():
    """붙여넣기가 만든 파일을 기존 importer 에 다시 넣어도 같다."""
    report, _first = _imported(FIXTURE_B)
    base = Path(tempfile.mkdtemp())
    path = panelpaste.canonical_path(report.round_id, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(panelpaste.convert(
        FIXTURE_B.read_text(encoding="utf-8"), P._report())[0],
        ensure_ascii=False), encoding="utf-8")
    data, err = panelimport.load(path)
    assert not err, err
    again = P._report()
    res2 = panelimport.validate(data, again, P.S)
    assert res2.success
    panelimport.attach(res2, again)
    for a, b in zip(report.matches, again.matches):
        assert a.panel.initial_scores == b.panel.initial_scores


def test_f45_the_field_lives_outside_the_moderator_block():
    """사회자가 만든 값이 아니므로 사회자 블록 안에 넣지 않는다."""
    report = P._report()
    data, issues = panelpaste.convert(
        FIXTURE_B.read_text(encoding="utf-8"), report)
    assert data is not None, [str(i) for i in issues]
    block = data["matches"][0]
    assert INI in block
    assert INI not in block[panelimport.MODERATOR_ROLE]


# ==========================================================================
# G. 리포트가 자체 완결이고 추천을 만들지 않는다
# ==========================================================================
def test_g46_report_stays_self_contained():
    html = _html(_imported(FIXTURE_B)[0])
    assert len(re.findall(r'(?:src|href)="https?://', html)) == 0
    assert "<script" not in html


def test_g47_render_layer_does_no_arithmetic_on_scores():
    """§29-19 — 새 함수들이 스코어를 계산하거나 견주지 않는다."""
    import ast
    import inspect

    for fn in (render._summary_panel, render._summary_grid,
               render._initial_pairs, render._initial_line,
               render._summary_intro):
        tree = ast.parse(inspect.getsource(fn).lstrip())
        for node in ast.walk(tree):
            assert not isinstance(node, ast.BinOp) or \
                isinstance(node.op, ast.Mod), (fn.__name__, ast.dump(node))
            if isinstance(node, ast.Compare):
                for op in node.ops:
                    assert not isinstance(op, (ast.Lt, ast.Gt, ast.LtE,
                                               ast.GtE)), fn.__name__
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ("sum", "round", "max", "min"), \
                    fn.__name__


def test_g48_footer_still_says_no_recommendation():
    html = _html(_imported(FIXTURE_B)[0])
    assert "승/무/패를 추천하지 않습니다" in html


def test_g49_schema_guide_documents_the_new_codes():
    guide = panelexport.schema_guide()
    for code in ("INITIAL_SCORES_INVALID", "INITIAL_SCORES_ROLE_UNKNOWN",
                 "INITIAL_SCORE_INVALID"):
        assert code in guide, code
    assert INI in guide
    assert "선택" in guide


def test_g50_schema_version_did_not_move():
    """§7 — 있어도 되고 없어도 되는 칸이라 버전을 올리지 않았다."""
    assert panelimport.SCHEMA_VERSION == "1.1"
    assert "1.0" in panelimport.SUPPORTED_VERSIONS
    data = json.loads(FIXTURE_B.read_text(encoding="utf-8"))
    report = P._report()
    block, _issues = panelpaste.convert(json.dumps(data), report)
    block["schema_version"] = "1.0"
    res = panelimport.validate(copy.deepcopy(block), P._report(), P.S)
    assert res.success, [str(i) for i in res.issues]


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
