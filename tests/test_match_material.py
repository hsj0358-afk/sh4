"""경기자료 MD 회귀 테스트 (Phase 4-A, `toto/match_material.py`).

고정하려는 것은 다섯 가지다.

1. **직렬화 계층이다.** 새 분석값을 만들지 않는다 — 종합점수·백분위·
   confidence·승무패 어느 것도 여기서 계산되지 않는다.
2. **정보를 잃지 않는다.** 값·기간·표본·공통표본·source·measurement_basis·
   provenance 가 그대로 실린다.
3. **근거를 지어내지 않는다.** 근거 0건이면 `E001` 이 나오지 않는다.
4. **시장 상태를 구분한다.** '예정인데 배당 없음'(수집 실패)과 '종료돼서
   시장이 닫힘'을 같은 말로 뭉뚱그리지 않는다.
5. **없는 전술 자료를 만들지 않는다.** 포메이션·부상·선발이 나오지 않는다.

pytest 없이도 돈다:  python tests/test_match_material.py
"""
from __future__ import annotations

import ast
import inspect
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import match_material                                  # noqa: E402
from toto.analyze import run_all                                 # noqa: E402
from toto.fixtures import build_demo_matches                     # noqa: E402
from toto.models import (AnalysisAxis, EvidenceItem, H2H,        # noqa: E402
                         H2HEntry, Match, MatchAnalysis, Metric, Odds,
                         Report, SeasonMatch, TeamAnalysis, TeamProfile,
                         TeamRef)
from toto.settings import Settings, load_settings                # noqa: E402


# --------------------------------------------------------------------------
# 픽스처
# --------------------------------------------------------------------------
def demo_report(round_id="260050") -> Report:
    """데모 14경기 + Phase 2 분석. 네트워크를 쓰지 않는다."""
    r = Report(generated_at="2026-09-06 12:00", round_id=round_id)
    r.matches = build_demo_matches()
    r.source_status = {"경기목록": "ok (14경기)", "배당": "부분 (11/14)",
                       "상세데이터": "실패 (브라우저 기동 불가)"}
    run_all(r.matches, load_settings(), r.season_matches)
    return r


def _match(no=1, home="Arsenal", away="Chelsea", kickoff="2026-09-06 20:00"):
    m = Match(no=no, league="epl",
              home=TeamRef(display=home, canonical=home, name_ko=home),
              away=TeamRef(display=away, canonical=away, name_ko=away))
    m.league_ko, m.kickoff_kst = "프리미어리그", kickoff
    return m


def _axis(**metrics) -> AnalysisAxis:
    return AnalysisAxis(name="chance_quality", requested_matches=6,
                        available_matches=4, metrics=metrics,
                        notes=["최근 6경기: 4/6경기"])


def _metric(**kw) -> Metric:
    base = dict(name="npxg", label="npxG", value=1.84, period="recent6",
                sample_count=4, unit="per_match", source="shotmap",
                measurement_basis="shot_events", provenance="observed",
                direction="higher_better", group="chance_quality")
    base.update(kw)
    return Metric(**base)


def _season(home="Arsenal", away="Chelsea", when="2026-09-06 20:00",
            finished=False, hg=None, ag=None, mid="4123456") -> SeasonMatch:
    return SeasonMatch(match_id=mid, competition="epl",
                       kickoff=datetime.strptime(when, "%Y-%m-%d %H:%M"),
                       kickoff_raw=when + "Z", home_team=home, away_team=away,
                       home_goals=hg, away_goals=ag, finished=finished)


def _one(match, season=None) -> str:
    r = Report(generated_at="2026-09-06 12:00", round_id="260050")
    r.matches = [match]
    r.season_matches = list(season or [])
    return match_material.build(r)


# --------------------------------------------------------------------------
# A. 새 값을 만들지 않는다 (§2-2)
# --------------------------------------------------------------------------
_BUILDERS = ("_axis_rows", "_axis_block", "_basic", "_market", "_standings",
             "_evidence", "_quality", "_conflicts", "_h2h", "_tactical",
             "_match_section", "_round_head", "build")


def test_a1_no_new_numbers_are_computed():
    """본문을 만드는 함수에 나눗셈·평균·반올림이 없어야 한다.

    문자열 검색은 쓰지 않는다 — 모듈 설명에 "새 분석값을 만들지 않는다" 가
    적혀 있어 그 부정문에 걸린다. 실행되는 코드만 AST 로 본다.
    """
    for name in _BUILDERS:
        tree = ast.parse(inspect.getsource(getattr(match_material, name)))
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(
                    node.op, (ast.Div, ast.FloorDiv)):
                raise AssertionError(f"{name}: 나눗셈이 있다")
            if isinstance(node, ast.Call):
                fn = getattr(node.func, "id", "") or getattr(
                    node.func, "attr", "")
                assert fn not in ("mean", "fmean", "median", "average",
                                  "percentile", "round"), f"{name}: {fn}()"


def test_a2_no_verdict_vocabulary_in_the_code():
    """이름으로 검사한다 — 설명문에 "confidence 를 만들지 않는다" 가 적혀
    있어 단순 문자열 검색은 자기 부정문에 걸린다 (실제로 걸렸다)."""
    tree = ast.parse(inspect.getsource(match_material))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
    for banned in ("strength_score", "confidence", "_winner", "_pick",
                   "recommendation", "composite", "lean", "_percentile"):
        assert banned not in names, banned


def test_a3_no_score_comparison():
    """스코어·확률을 비교해 승패를 만드는 코드가 없어야 한다."""
    tree = ast.parse(inspect.getsource(match_material))
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            blob = ast.dump(node)
            for banned in ("home_probability", "away_probability",
                           "'home'", "predicted_"):
                if banned in blob and any(
                        isinstance(o, (ast.Lt, ast.Gt, ast.LtE, ast.GtE))
                        for o in node.ops):
                    raise AssertionError(f"확률을 비교하고 있다: {blob[:80]}")


def test_a4_percentile_is_read_not_recomputed():
    """백분위는 `analyze.build_radar()` 가 이미 만든 값을 읽기만 한다."""
    src = inspect.getsource(match_material)
    assert "build_radar" in src, "어디서 온 값인지 밝히지 않았다"
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "analyze" or {
                a.name for a in node.names} <= {"period_sort_key"}, (
                    "analysis/analyze 에서 계산 함수를 끌어왔다")


# --------------------------------------------------------------------------
# B. 260050 골든 케이스 (§15-1)
# --------------------------------------------------------------------------
def test_b1_all_matches_in_round_order():
    text = match_material.build(demo_report())
    heads = re.findall(r"^## 경기 (\d+)\. (.+)$", text, re.M)
    assert len(heads) == 14, len(heads)
    assert [h[0] for h in heads] == [f"{i:02d}" for i in range(1, 15)]


def test_b2_every_match_has_the_core_sections():
    text = match_material.build(demo_report())
    blocks = text.split("## 경기 ")[1:]
    assert len(blocks) == 14
    for i, block in enumerate(blocks, start=1):
        for section in ("경기 기본정보", "시장 기준선", "리그 내 위치",
                        "경기력 분석", "근거 (Evidence)", "데이터 품질",
                        "상대전적 (H2H)", "정성 자료"):
            assert section in block, (i, section)


def test_b3_section_numbers_have_no_gaps():
    """없는 절의 번호를 건너뛰면 읽는 쪽이 빠진 절을 찾게 된다."""
    text = match_material.build(demo_report())
    for block in text.split("## 경기 ")[1:]:
        nums = [int(n) for n in re.findall(r"^### \d+-(\d+)\. ", block, re.M)]
        assert nums == list(range(1, len(nums) + 1)), nums


def test_b4_round_header_states_what_is_missing():
    text = match_material.build(demo_report())
    head = text.split("## 경기 01")[0]
    assert "근거가 생성된 경기 | 0/14" in head, "근거 0건을 안 밝혔다"
    assert "실패 (브라우저 기동 불가)" in head, "수집 상태를 안 옮겼다"
    assert "`실패` 와 `생략` 은 다릅니다" in head


def test_b5_identifier_survives_for_reimport():
    """나중에 패널 결과를 되받을 때 경기를 다시 찾을 수 있어야 한다 (§10)."""
    m = _match(no=7)
    text = _one(m, [_season(mid="4999888")])
    block = text.split("## 경기 07")[1]
    assert "| 회차 | 260050 |" in block
    assert "| 경기 번호 | 07 |" in block
    assert "4999888" in block, "match_id 가 없다"
    assert "| home_team (정규명) | Arsenal |" in block
    assert "| away_team (정규명) | Chelsea |" in block


def test_b6_unresolved_match_says_so_instead_of_guessing():
    text = _one(_match(), season=[])       # 색인에 없는 경기
    assert "확인 불가" in text
    assert "match_id (FotMob) | 확인 불가" in text


# --------------------------------------------------------------------------
# C. 데이터 손실 (§15-2, §8)
# --------------------------------------------------------------------------
def test_c1_metric_metadata_survives_serialization():
    m = _match()
    m.analysis = MatchAnalysis(
        home=TeamAnalysis(team="Arsenal", is_home=True,
                          chance_quality=_axis(**{"recent6.npxg": _metric()})),
        away=TeamAnalysis(team="Chelsea", is_home=False))
    text = _one(m)
    row = next(l for l in text.splitlines() if "npxG" in l and "|" in l)
    for piece in ("recent6", "npxG", "1.84", "n=4", "per_match",
                  "shotmap", "shot_events", "OBSERVED", "chance_quality"):
        assert piece in row, (piece, row)


def test_c2_common_sample_count_is_kept_separate_from_n():
    """넷은 서로 다른 수다 — requested · available · n · 공통 (§1-1-11)."""
    m = _match()
    m.analysis = MatchAnalysis(
        home=TeamAnalysis(team="A", chance_quality=_axis(**{
            "recent6.goals_minus_xg": _metric(
                name="goals_minus_xg", label="득점 − xG", value=0.31,
                sample_count=6, common_sample_count=4,
                provenance="derived", direction="")})),
        away=TeamAnalysis(team="B"))
    text = _one(m)
    row = next(l for l in text.splitlines() if "득점 − xG" in l)
    assert "n=6" in row and "공통=4" in row, row
    assert "요청 창 6 / 확보 경기 4" in text


def test_c3_missing_value_is_not_zero():
    m = _match()
    m.analysis = MatchAnalysis(
        home=TeamAnalysis(team="A", chance_quality=_axis(**{
            "recent6.npxg": _metric(value=None, sample_count=None)})),
        away=TeamAnalysis(team="B"))
    text = _one(m)
    row = next(l for l in text.splitlines() if "npxG" in l and "|" in l)
    assert "0.00" not in row, "값 없음을 0 으로 적었다"
    assert "—" in row
    assert "`—` 인 것은 0 이 아닙니다" in text


def test_c4_axis_notes_are_carried_over():
    """값이 없는 이유가 사라지면 안 된다 (§1-1-10 교정)."""
    m = _match()
    m.analysis = MatchAnalysis(
        home=TeamAnalysis(team="A", chance_quality=_axis(
            **{"recent6.npxg": _metric()})),
        away=TeamAnalysis(team="B"))
    assert "최근 6경기: 4/6경기" in _one(m)


def test_c5_every_axis_metric_is_emitted_not_curated():
    """HTML 리포트와 달리 **고르지 않는다** — 축에 있는 것은 전부 낸다."""
    report = demo_report()
    text = match_material.build(report)
    first = report.matches[0]
    axis = first.analysis.home.time_context
    labels = {m.label for m in axis.metrics.values() if m.value is not None}
    block = text.split("## 경기 01")[1].split("## 경기 02")[0]
    missing = [l for l in labels if l not in block]
    assert not missing, missing


def test_c6_data_quality_reasons_survive():
    report = demo_report()
    text = match_material.build(report)
    assert "degraded_reason" in text
    assert "슛 계층 창 없음" in text or "표본 없음" in text


# --------------------------------------------------------------------------
# D. 근거 무결성 (§15-3)
# --------------------------------------------------------------------------
def test_d1_no_evidence_means_no_invented_ids():
    text = match_material.build(demo_report())      # 데모는 근거 0건
    assert "E001" not in text, "없는 근거 ID 를 만들었다"
    assert "E002" not in text
    assert "근거 없음" in text
    assert "지어내지 마십시오" in text


def test_d2_evidence_ids_are_positional_not_hardcoded():
    m = _match()
    m.analysis = MatchAnalysis(
        home=TeamAnalysis(team="A"), away=TeamAnalysis(team="B"),
        evidence=[EvidenceItem(claim="기회 창출이 많다", metric="npxg",
                               value=2.4, period="recent6", sample_count=6,
                               team="Arsenal", category="attack",
                               context="recent", finding_kind="chance",
                               source="shotmap",
                               measurement_basis="shot_events")])
    text = _one(m)
    assert "E001" in text and "E002" not in text
    assert "기회 창출이 많다" in text and "shot_events" in text
    src = inspect.getsource(match_material._evidence)
    assert '"E001"' not in src and "'E001'" not in src, "ID 를 박아 뒀다"


def test_d3_supporting_metrics_are_not_a_count():
    m = _match()
    m.analysis = MatchAnalysis(
        home=TeamAnalysis(team="A"), away=TeamAnalysis(team="B"),
        evidence=[EvidenceItem(claim="c", metric="npxg", team="A",
                               supporting_metrics=["a", "b"],
                               supporting_axes=["chance_quality"])])
    text = _one(m)
    assert "개수가 근거의 세기가 아닙니다" in text


# --------------------------------------------------------------------------
# E. 시장 상태 (§15-4)
# --------------------------------------------------------------------------
def _odds(available=True) -> Odds:
    if not available:
        return Odds()
    return Odds(home=2.1, draw=3.4, away=3.6, source="arcadia-api",
                fetched_at="2026-09-06 10:00")


def test_e1_scheduled_without_odds_is_a_collection_failure():
    m = _match()
    m.odds = _odds(False)
    text = _one(m, [_season(finished=False)])
    assert "예정 경기인데 배당을 가져오지 못했습니다" in text
    assert "수집 실패" in text


def test_e2_finished_without_odds_is_not_a_failure():
    """이미 끝난 경기에 배당이 없는 것은 정상이다 — 실패로 적지 않는다."""
    m = _match()
    m.odds = _odds(False)
    text = _one(m, [_season(finished=True, hg=2, ag=1)])
    assert "시장이 닫혔습니다" in text
    assert "수집 실패가 아닙니다" in text
    assert "예정 경기인데" not in text
    assert "| 실제 결과 | 2 : 1 |" in text


def test_e3_unknown_status_says_it_cannot_tell():
    m = _match()
    m.odds = _odds(False)
    text = _one(m, season=[])
    assert "판별할 수 없습니다" in text


def test_e4_market_is_a_baseline_not_a_pick():
    m = _match()
    m.odds = _odds()
    from toto.predict import additive_probabilities
    m.probs = additive_probabilities(2.1, 3.4, 3.6)
    text = _one(m)
    assert "오버라운드" in text and "내재확률" in text
    assert "외부 기준선" in text
    # 표 **칸**에 favorite·픽이 없어야 한다. 안내문의 "추천이나 favorite 를
    # 만들지 마십시오" 는 부정문이라 문자열 검색으로 재면 걸린다.
    market = text.split("시장 기준선")[1].split("리그 내 위치")[0]
    cells = [l for l in market.splitlines() if l.startswith("|")]
    for banned in ("favorite", "픽", "추천", "홈승", "원정승"):
        assert not any(banned in c for c in cells), banned


# --------------------------------------------------------------------------
# F. 전술 자료 부재 (§15-5)
# --------------------------------------------------------------------------
def test_f1_missing_tactical_data_is_stated_not_invented():
    """자료가 없으면 없다고만 적는다 (데모 픽스처에는 강점/약점이 있다)."""
    text = _one(_match())                # 프로필 자체가 없는 경기
    assert "Tactical qualitative data: unavailable" in text
    for banned in ("4-3-3", "4-4-2", "포메이션", "부상", "선발", "결장",
                   "압박 방식을 ", "감독 성향을 "):
        assert banned not in text.split("정성 자료")[1].split(
            "수집하지 않습니다")[0], banned


def test_f2_the_absence_is_told_to_the_model():
    text = match_material.build(demo_report())
    assert "수집하지 않습니다" in text
    assert "아는 것처럼" in text


def test_f3_present_tactical_data_is_carried_over():
    m = _match()
    m.home_profile = TeamProfile(team=m.home, strengths=["Set pieces"],
                                 weaknesses=["Defending counters"],
                                 style_of_play=["Possession"], rest_days=4)
    text = _one(m)
    assert "Set pieces" in text and "Defending counters" in text
    assert "Possession" in text and "휴식일" in text


# --------------------------------------------------------------------------
# G. H2H
# --------------------------------------------------------------------------
def test_g1_no_h2h_says_unavailable():
    assert "H2H: unavailable" in _one(_match())


def test_g2_h2h_entries_are_listed_verbatim():
    m = _match()
    m.h2h = H2H(entries=[H2HEntry(date="2026-03-01", home_team="Arsenal",
                                  away_team="Chelsea", home_goals=2,
                                  away_goals=1, competition="EPL")],
                home_wins=1, draws=0, away_wins=0, source_ok=True)
    text = _one(m)
    assert "2026-03-01" in text and "2-1" in text
    assert "H2H: unavailable" not in text


# --------------------------------------------------------------------------
# H. 파일 출력
# --------------------------------------------------------------------------
def test_h1_single_file_named_by_round():
    out = Path(tempfile.mkdtemp())
    status = match_material.export(demo_report(), outdir=out)
    files = sorted(p.name for p in out.iterdir())
    assert files == ["260050_경기자료.md"], files
    assert status.startswith("ok"), status
    assert "14경기" in status


def test_h2_written_as_utf8():
    out = Path(tempfile.mkdtemp())
    match_material.export(demo_report(), outdir=out)
    path = out / "260050_경기자료.md"
    text = path.read_text(encoding="utf-8")
    assert "경기자료" in text
    # BOM 을 붙이지 않는다 — 마크다운 파서가 첫 제목을 놓친다.
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_h3_empty_round_is_skipped_not_written():
    out = Path(tempfile.mkdtemp())
    status = match_material.export(Report(round_id="X"), outdir=out)
    assert status.startswith("생략"), status
    assert not list(out.iterdir())


def test_h4_output_goes_to_the_existing_reports_dir():
    """새 디렉터리를 만들지 않는다 — 기존 output 구조를 쓴다 (§11)."""
    s = load_settings()
    src = inspect.getsource(match_material.export)
    assert "output_dir" in src
    assert s.output_dir.name == "reports"


def test_h5_cli_flag_is_wired_without_touching_the_report():
    src = (Path(__file__).resolve().parent.parent / "toto"
           / "cli.py").read_text(encoding="utf-8")
    assert "--export-match-material" in src
    assert re.search(r"args\.export_match_material", src)
    assert "match_material.export(report, settings)" in src


# --------------------------------------------------------------------------
# I. 회귀 — 기존 분석을 건드리지 않는다 (§16)
# --------------------------------------------------------------------------
def test_i1_export_does_not_mutate_the_report():
    from dataclasses import asdict
    report = demo_report()
    before = asdict(report)
    match_material.build(report)
    assert asdict(report) == before, "직렬화가 원본을 바꿨다"


def test_i2_no_forbidden_module_is_imported():
    """수집·분석 모듈을 다시 부르지 않는다 (§14)."""
    tree = ast.parse(inspect.getsource(match_material))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.lstrip("."))
        elif isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
    for banned in ("sources", "evidence", "xpts", "shots", "predict",
                   "requests", "cache", "llm", "panel", "moderator"):
        assert not any(m == banned or m.startswith(banned + ".")
                       for m in mods), banned


def test_i3_the_season_lookup_rule_lives_in_one_place():
    """`roundlog` 와 같은 규칙을 써야 한다 — 두 벌이면 조용히 어긋난다."""
    from toto import models, roundlog
    assert hasattr(models, "find_season_match")
    assert "find_season_match" in inspect.getsource(roundlog)
    assert "find_season_match" in inspect.getsource(match_material)


def test_i4_lookup_refuses_ambiguous_pairs():
    """같은 팀 짝이 시즌에 두 번 나온다 — 못 가리면 붙이지 않는다."""
    from toto.models import find_season_match
    season = [_season(when="2026-03-01 20:00", mid="1"),
              _season(when="2026-09-06 20:00", mid="2")]
    when = datetime.strptime("2026-09-06 20:00", "%Y-%m-%d %H:%M")
    assert find_season_match(season, "Arsenal", "Chelsea", when,
                             timedelta(days=4)).match_id == "2"
    # 날짜를 모르면 둘 중 하나를 고르지 않는다.
    assert find_season_match(season, "Arsenal", "Chelsea", None,
                             timedelta(days=4)) is None


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
