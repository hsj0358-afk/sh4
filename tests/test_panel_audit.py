"""Panel Audit + 회차 분석 저장 회귀 테스트 (Phase 4-C).

고정하려는 것은 여섯 가지다.

1. **감사는 패널 위에 있지 않다.** "누가 옳은지" 를 만들지 않는다 —
   확신도·합의도·승무패·패널 확률이 없다.
2. **participation 과 origin 을 나눈다.** 맞대결 origin 0회는 그 분석가가
   참여하지 않았다는 뜻이 아니다 (260050 에서 실제로 나온 상태).
3. **DA → 맞대결 → 사회자 흐름을 언제나 재현할 수 있다.**
4. **4-B 를 다시 검증하지 않는다.** `PanelImportResult` 를 읽어 집계할 뿐.
5. **저장본으로 되돌아갈 수 있다.** 회차를 다시 수집하지 않고 패널 결과를
   붙일 수 있어야 한다 — 분석값이 한 칸도 달라지지 않은 채로.
6. **없는 것을 추론하지 않는다.** 라운드별 토론 내용은 `UNOBSERVED` 다.

pytest 없이도 돈다:  python tests/test_panel_audit.py
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from toto import artifact, panelaudit, panelimport, render           # noqa: E402
from toto.analyze import evaluate_round, run_all                     # noqa: E402
from toto.fixtures import build_demo_matches                         # noqa: E402
from toto.models import Report                                       # noqa: E402
from toto.settings import Settings, load_settings                    # noqa: E402
from test_panel_import import (DA, MU, S, _block, _like_260050,      # noqa: E402
                               _mod, _opinion, _payload, _report)


def _audit(data, report=None):
    report = report if report is not None else _report()
    imp = panelimport.validate(data, report, S)
    return panelaudit.audit(imp, report), imp, report


def _codes(result) -> set[str]:
    return {i.code for i in result.issues}


# --------------------------------------------------------------------------
# A. 커버리지 (§5·§6)
# --------------------------------------------------------------------------
def test_a1_full_coverage_is_complete():
    res, _imp, _r = _audit(_payload(_report(n=3)), _report(n=3))
    cov = res.coverage
    assert cov["matches_total"] == 3
    assert cov["panel_results"] == 3
    assert cov["data_analyst"] == 3
    assert cov["matchup_analyst"] == 3
    assert cov["moderator"] == 3
    assert res.coverage_status == panelaudit.COMPLETE
    assert res.status in (panelaudit.PASS, panelaudit.CONDITIONAL)


def test_a2_missing_analyst_is_named_not_just_counted():
    report = _report(n=3)
    data = _payload(report)
    del data["matches"][1][MU]
    res, _imp, _r = _audit(data, report)
    assert res.coverage["matchup_analyst"] == 2
    assert res.coverage["matchup_analyst_missing"] == [2], res.coverage
    assert res.coverage_status != panelaudit.COMPLETE
    assert res.status == panelaudit.FAIL


def test_a3_missing_moderator_is_named():
    report = _report(n=2)
    data = _payload(report)
    del data["matches"][0]["moderator"]
    res, _imp, _r = _audit(data, report)
    assert res.coverage["moderator"] == 1
    assert res.coverage["moderator_missing"] == [1]


def test_a4_import_errors_block_complete():
    """4-B 오류가 있으면 COMPLETE 로 적지 않는다 (§6)."""
    report = _report(n=2)
    data = _payload(report)
    data["round"] = "999999"
    res, imp, _r = _audit(data, report)
    assert imp.errors
    assert res.coverage_status != panelaudit.COMPLETE
    assert res.status == panelaudit.FAIL


def test_a5_empty_round_fails():
    res, _imp, _r = _audit({"schema_version": "1.0", "round": "260050",
                            "matches": []}, _report(n=2))
    assert res.status == panelaudit.FAIL
    assert res.coverage["panel_results"] == 0
    assert res.coverage["panel_missing"] == [1, 2]


# --------------------------------------------------------------------------
# B. 신원 / 연결 (§7·§8)
# --------------------------------------------------------------------------
def test_b1_match_id_comes_from_the_analysis_side():
    """감사의 match_id 는 **회차 분석 쪽** authoritative id 다."""
    report = _report(n=2)
    res, _imp, _r = _audit(_payload(report), report)
    assert [a.match_id for a in res.matches] == ["400001", "400002"]


def test_b2_teams_are_carried_from_the_analysis_not_the_file():
    report = _report(n=1)
    res, _imp, _r = _audit(_payload(report), report)
    a = res.matches[0]
    assert a.home_team == report.matches[0].home.display
    assert a.away_team == report.matches[0].away.display


def test_b3_attachment_errors_show_up_in_the_audit():
    report = _report(n=2)
    data = _payload(report)
    # 번호까지 없애야 정말로 못 찾는다 — 번호·팀이 맞으면 그쪽으로 잇고
    # `MATCH_ID_MISMATCH` 경고만 남긴다 (4-B 식별자 계약).
    data["matches"][0]["match_id"] = "9999999"
    data["matches"][0].pop("match_number")
    res, _imp, _r = _audit(data, report)
    assert "UNKNOWN_MATCH_ID" in _codes(res)
    assert res.status == panelaudit.FAIL


# --------------------------------------------------------------------------
# C. 두 분석가의 처음 의견 (§9·§10)
# --------------------------------------------------------------------------
def test_c1_score_flow_table_is_reproducible():
    """`Match | DA | Matchup | Moderator` 표 (§9)."""
    report = _report(n=2)
    data = _payload(report)
    data["matches"][1][DA] = _opinion(DA, 3, 0)
    data["matches"][1][MU] = _opinion(MU, 3, 0)
    data["matches"][1]["moderator"] = _mod(
        adopted=(3, 0), adopted_from=[DA, MU],
        dist=[{"home": 3, "away": 0, "count": 30, "origin": DA}])
    res, _imp, _r = _audit(data, report)
    assert [a.row for a in res.matches] == [
        ("01", "2-1", "1-1", "1-1"), ("02", "3-0", "3-0", "3-0")]


def test_c2_relation_is_a_label_not_a_score():
    assert panelaudit.initial_relation((2, 1), (2, 1)) == panelaudit.SAME_INITIAL
    assert panelaudit.initial_relation((2, 1), (1, 1)) == \
        panelaudit.DIFFERENT_INITIAL
    assert panelaudit.initial_relation(None, (1, 1)) == \
        panelaudit.UNKNOWN_INITIAL


def test_c3_relation_counts_are_in_the_summary():
    report = _report(n=2)
    data = _payload(report)
    data["matches"][1][MU] = _opinion(MU, 2, 1)      # 같은 원안
    data["matches"][1]["moderator"] = _mod(
        adopted=(2, 1), adopted_from=[DA, MU],
        dist=[{"home": 2, "away": 1, "count": 30, "origin": DA}])
    res, _imp, _r = _audit(data, report)
    assert res.adoption["same_initial"] == 1
    assert res.adoption["different_initial"] == 1


# --------------------------------------------------------------------------
# D. 사회자 결정 추적 (§11~§14)
# --------------------------------------------------------------------------
def test_d1_decision_type_is_derived_from_the_scores():
    """`adopted_from` 을 되읽지 않고 실제 스코어끼리 견준다."""
    f = panelaudit.decision_type
    assert f((2, 1), (2, 1), (1, 1)) == panelaudit.ADOPTED_DATA
    assert f((1, 1), (2, 1), (1, 1)) == panelaudit.ADOPTED_MATCHUP
    assert f((1, 1), (1, 1), (1, 1)) == panelaudit.ADOPTED_BOTH
    assert f((2, 0), (2, 1), (1, 1)) == panelaudit.MODIFIED
    assert f(None, (2, 1), (1, 1)) == panelaudit.NOT_ADOPTED


def test_d2_case_a_data_analyst_adopted():
    res, _i, _r = _audit(*_scored((2, 1), (1, 1), (2, 1), [DA]))
    a = res.matches[0]
    assert a.decision_type == panelaudit.ADOPTED_DATA
    assert a.adopted_from == (DA,)
    assert res.adoption["adopted_data_analyst"] == 1


def test_d3_case_b_both_analysts_same():
    res, _i, _r = _audit(*_scored((1, 1), (1, 1), (1, 1), [DA, MU],
                                  dist=[{"home": 1, "away": 1, "count": 30,
                                         "origin": DA}]))
    assert res.matches[0].decision_type == panelaudit.ADOPTED_BOTH
    assert res.adoption["adopted_both"] == 1


def test_d4_case_c_compromise():
    res, _i, _r = _audit(*_scored(
        (2, 1), (1, 1), (2, 0), [],
        dist=[{"home": 2, "away": 1, "count": 12, "origin": DA},
              {"home": 1, "away": 1, "count": 8, "origin": MU},
              {"home": 2, "away": 0, "count": 10, "origin": "compromise"}]))
    a = res.matches[0]
    assert a.decision_type == panelaudit.MODIFIED
    assert a.adopted_from == ()
    assert res.adoption["modified_or_compromise"] == 1


def test_d5_case_d_inconsistent_adopted_from_is_visible():
    """DA 2-1 · 맞대결 1-1 · 채택 1-1 인데 DA 것이라고 했다."""
    data, report = _scored((2, 1), (1, 1), (1, 1), [DA])
    res, imp, _r = _audit(data, report)
    assert imp.errors
    assert "ADOPTED_FROM_MISMATCH" in _codes(res)
    assert res.status == panelaudit.FAIL


def _scored(da, mu, adopted, adopted_from, dist=None):
    report = _report(n=1)
    data = _payload(report, da=_opinion(DA, *da), mu=_opinion(MU, *mu),
                    mod=_mod(adopted=adopted, adopted_from=adopted_from,
                             dist=dist))
    return data, report


# --------------------------------------------------------------------------
# E. 분포 (§15~§20)
# --------------------------------------------------------------------------
def test_e1_distribution_totals_and_origins_are_counted():
    res, _i, _r = _audit(*_scored(
        (2, 1), (1, 1), (2, 1), [DA],
        dist=[{"home": 2, "away": 1, "count": 19, "origin": DA},
              {"home": 1, "away": 1, "count": 7, "origin": MU},
              {"home": 2, "away": 0, "count": 4, "origin": "compromise"}]))
    a = res.matches[0]
    assert a.distribution_total == 30
    assert a.simulations == 30
    assert a.distribution_origins == {DA: 19, MU: 7, "compromise": 4}
    assert res.distribution["origin_counts"] == {"compromise": 4, DA: 19, MU: 7}


def test_e2_distribution_is_never_a_probability():
    """`count / simulations` 를 계산하지 않는다 (§16·§20)."""
    tree = ast.parse(inspect.getsource(panelaudit))
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(
                node.op, (ast.Div, ast.FloorDiv)):
            raise AssertionError("나눗셈이 있다 (분포를 확률로 바꾸고 있나)")
        if isinstance(node, ast.Call):
            fn = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
            assert fn not in ("mean", "fmean", "median", "average"), fn


def test_e3_most_frequent_score_is_not_called_best():
    res, _i, _r = _audit(_payload(_report(n=2)), _report(n=2))
    text = "\n".join(panelaudit.report_lines(res))
    # "확률" 은 **부정문**으로만 나온다 — 그 문장 자체를 금지하면 자기
    # 부정문에 걸린다 (이 프로젝트가 여러 번 겪은 함정).
    assert "확률이 아니다" in text
    for banned in ("최빈", "가장 유력", "%", "신뢰도", "합의도",
                   "우세", "추천", "홈승", "원정승"):
        assert banned not in text, banned


# --------------------------------------------------------------------------
# F. 맞대결 origin 0 — 참여 실패와 구분 (§2·§18)
# --------------------------------------------------------------------------
def test_f1_zero_origin_is_not_a_participation_failure():
    """**260050 회귀.** origin 0회인데 커버리지는 14/14 여야 한다."""
    data, report = _like_260050(evidence=1)
    res, imp, _r = _audit(data, report)
    assert not imp.errors, [str(i) for i in imp.errors][:3]
    assert res.coverage["matchup_analyst"] == 14, "참여를 0으로 셌다"
    assert res.coverage["matchup_analyst_missing"] == []
    assert res.distribution["origin_counts"].get(MU) is None
    assert "MATCHUP_ORIGIN_ZERO" in _codes(res)
    assert res.status == panelaudit.CONDITIONAL, res.status


def test_f2_the_warning_says_the_two_are_different():
    data, report = _like_260050(evidence=1)
    res, _i, _r = _audit(data, report)
    warn = next(i for i in res.issues if i.code == "MATCHUP_ORIGIN_ZERO")
    assert "참여하지 않은 것과는 다른" in warn.message


def test_f3_summary_shows_coverage_and_origin_side_by_side():
    data, report = _like_260050(evidence=1)
    res, _i, _r = _audit(data, report)
    text = "\n".join(panelaudit.report_lines(res))
    assert "맞대결·전술 분석가: 14/14" in text, text[:400]
    assert f"- {DA}: 420" in text, "origin 집계가 없다"
    assert MU not in text.split("origin")[1].split("근거")[0].replace(
        "맞대결", ""), "origin 0 인데 줄이 생겼다"


# --------------------------------------------------------------------------
# G. 근거 (§21·§22)
# --------------------------------------------------------------------------
def test_g1_evidence_summary_counts_the_round():
    data, report = _like_260050(evidence=1)
    res, _i, _r = _audit(data, report)
    ev = res.evidence
    assert ev["matches_with_evidence"] == 14
    assert ev["matches_without_evidence"] == 0
    assert ev["citations"] == 14        # 경기당 E001 하나 (중복 제거)
    assert ev["invalid_citation_issues"] == 0


def test_g2_260050_regression_evidence_absent_but_cited():
    """근거 0건인데 E001 을 썼다 — 감사에도 그대로 드러난다."""
    data, report = _like_260050(evidence=0)
    res, imp, _r = _audit(data, report)
    assert res.status == panelaudit.FAIL
    # 근거 0건 인용(14×3) + 없는 ID 인용(분석가 14×2)이 함께 잡힌다.
    assert res.evidence["invalid_citation_issues"] >= 14 * 3, res.evidence
    assert "EVIDENCE_ABSENT_BUT_CITED" in _codes(res)
    assert "UNKNOWN_EVIDENCE_ID" in _codes(res)
    assert res.coverage["panel_results"] == 0, "깨진 결과를 읽은 척했다"


def test_g3_no_evidence_and_empty_ids_is_clean():
    report = _report(n=2, evidence=0)
    data = _payload(report, da=_opinion(DA, 2, 1, ids=[]),
                    mu=_opinion(MU, 1, 1, ids=[]))
    res, _i, _r = _audit(data, report)
    assert res.evidence["matches_without_evidence"] == 2
    assert res.evidence["invalid_citation_issues"] == 0


# --------------------------------------------------------------------------
# H. 일관성 · 없는 것 (§43·§44)
# --------------------------------------------------------------------------
def test_h1_simulation_count_variance_is_flagged():
    report = _report(n=2)
    data = _payload(report)
    data["matches"][1]["moderator"] = _mod(
        sims=10, dist=[{"home": 1, "away": 1, "count": 10, "origin": MU}])
    res, _i, _r = _audit(data, report)
    assert res.consistency["simulation_counts"] == [10, 30]
    assert "SIMULATION_COUNT_VARIES" in _codes(res)


def test_h2_unobserved_things_are_named_not_inferred():
    res, _i, _r = _audit(_payload(_report()), _report())
    text = "\n".join(panelaudit.report_lines(res))
    assert "자료에 없는 것" in text
    assert panelaudit.UNOBSERVED in text
    assert "라운드별 토론 내용" in text


# --------------------------------------------------------------------------
# I. 감사는 판정하지 않는다 (§24·§32·§42)
# --------------------------------------------------------------------------
def test_i1_no_verdict_fields_exist():
    names = {f for f in dir(panelaudit.PanelMatchAudit)} | {
        f for f in dir(panelaudit.PanelAuditResult)}
    for banned in ("winner", "wdl", "pick", "lean", "recommendation",
                   "confidence", "strength", "consensus", "probability"):
        assert banned not in names, banned


def test_i2_no_verdict_helper_in_the_code():
    src = inspect.getsource(panelaudit)
    for banned in ("def _winner", "def _pick", "def _confidence",
                   "def _consensus", "def _strength"):
        assert banned not in src, banned


def test_i3_scores_are_never_compared_for_a_result():
    """스코어 두 값을 견줘 승무패를 만드는 코드가 없어야 한다."""
    tree = ast.parse(inspect.getsource(panelaudit))
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(
                isinstance(o, (ast.Lt, ast.Gt, ast.LtE, ast.GtE))
                for o in node.ops):
            blob = ast.dump(node)
            for banned in ("adopted", "predicted", "moderator_score"):
                assert banned not in blob, blob[:80]


def test_i4_audit_does_not_revalidate_or_recompute():
    """4-B 를 다시 검증하지 않고, 소스·분석 모듈을 부르지 않는다."""
    tree = ast.parse(inspect.getsource(panelaudit))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.lstrip("."))
        elif isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
    for banned in ("sources", "analysis", "analyze", "evidence", "xpts",
                   "shots", "predict", "cache", "llm", "requests"):
        assert not any(m == banned or m.startswith(banned + ".")
                       for m in mods), banned
    src = inspect.getsource(panelaudit)
    assert "parse_opinion" not in src and "parse_result" not in src


def test_i5_audit_does_not_mutate_the_report_or_the_import():
    report = _report(n=2)
    imp = panelimport.validate(_payload(report), report, S)
    before_report = [asdict(m.analysis) for m in report.matches]
    before_imp = [str(i) for i in imp.issues]
    panelaudit.audit(imp, report)
    assert [asdict(m.analysis) for m in report.matches] == before_report
    assert [str(i) for i in imp.issues] == before_imp


# --------------------------------------------------------------------------
# J. 회차 분석 저장 (§25~§28·§46)
# --------------------------------------------------------------------------
def _analyzed(round_id="260050") -> Report:
    r = Report(generated_at="2026-09-06 12:00", round_id=round_id)
    r.matches = build_demo_matches()
    r.source_status = {"경기목록": "ok (14경기)"}
    run_all(r.matches, load_settings(), r.season_matches)
    r.verdict = evaluate_round(r.matches)
    return r


def _norm(node):
    """저장이 뺀 칸과 datetime 표기를 맞춰 비교용으로 정규화한다."""
    if isinstance(node, dict):
        return {k: _norm(v) for k, v in node.items()
                if k not in artifact.DROPPED}
    if isinstance(node, list):
        return [_norm(v) for v in node]
    if isinstance(node, datetime):
        return node.isoformat()
    return node


def test_j1_save_and_reload_keeps_the_analysis_identical():
    """§46 — 다시 읽어도 분석값·Evidence·DataQuality 가 같아야 한다."""
    out = Path(tempfile.mkdtemp())
    src = _analyzed()
    status = artifact.save(src, outdir=out)
    assert status.startswith("ok"), status
    back, why = artifact.load("260050", outdir=out)
    assert back is not None, why
    assert _norm(asdict(src)) == _norm(asdict(back))


def test_j2_report_regenerates_byte_identically():
    """저장본으로 리포트를 다시 그려도 바이트가 같아야 한다."""
    out = Path(tempfile.mkdtemp())
    src = _analyzed()
    artifact.save(src, outdir=out)
    back, _why = artifact.load("260050", outdir=out)
    s = load_settings()
    assert hashlib.sha256(render.render_report(src, s).encode()).hexdigest() \
        == hashlib.sha256(render.render_report(back, s).encode()).hexdigest()


def test_j3_match_id_and_order_survive():
    out = Path(tempfile.mkdtemp())
    src = _report(n=3)
    artifact.save(src, outdir=out)
    back, _why = artifact.load(src.round_id, outdir=out)
    assert [m.no for m in back.matches] == [1, 2, 3]
    assert [panelimport._match_key(m, back) for m in back.matches] == \
        [panelimport._match_key(m, src) for m in src.matches]


def test_j4_panel_attaches_to_the_reloaded_report():
    """§26 — 수집을 다시 하지 않고 패널 결과를 붙일 수 있어야 한다."""
    out = Path(tempfile.mkdtemp())
    src = _report(n=2)
    artifact.save(src, outdir=out)
    back, _why = artifact.load(src.round_id, outdir=out)
    imp = panelimport.validate(_payload(src), back, S)
    assert imp.success, [str(i) for i in imp.issues]
    assert panelimport.attach(imp, back) == 2
    assert all(m.panel is not None for m in back.matches)


def test_j5_demo_is_not_saved():
    out = Path(tempfile.mkdtemp())
    r = _analyzed(round_id="DEMO")
    assert artifact.save(r, outdir=out).startswith("생략")
    assert not list(out.iterdir())


def test_j6_missing_or_old_artifact_is_reported_not_guessed():
    out = Path(tempfile.mkdtemp())
    back, why = artifact.load("999999", outdir=out)
    assert back is None and "없습니다" in why
    path = artifact.path_for("260050", outdir=out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"artifact_version": 999, "report": {}}),
                    encoding="utf-8")
    back, why = artifact.load("260050", outdir=out)
    assert back is None and "저장 형식이 다릅니다" in why


def test_j7_shot_layers_are_dropped_on_purpose():
    """분석의 **입력**은 저장하지 않는다 — 분석은 이미 끝났다."""
    out = Path(tempfile.mkdtemp())
    artifact.save(_analyzed(), outdir=out)
    raw = artifact.path_for("260050", outdir=out).read_text(encoding="utf-8")
    for key in artifact.DROPPED:
        assert f'"{key}"' not in raw, key
    src = inspect.getsource(artifact)
    assert "렌더링도 쓰지 않는다" in src, "왜 뺐는지 안 적었다"


def test_j8_artifact_does_not_recompute_anything():
    tree = ast.parse(inspect.getsource(artifact))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.lstrip("."))
    for banned in ("analyze", "analysis", "evidence", "sources", "render"):
        assert banned not in mods, banned


# --------------------------------------------------------------------------
# K. CLI
# --------------------------------------------------------------------------
def test_k1_three_panel_flags_are_wired_and_distinct():
    src = (Path(__file__).resolve().parent.parent / "toto"
           / "cli.py").read_text(encoding="utf-8")
    for flag in ("--validate-panel-result", "--import-panel-result",
                 "--audit-panel-result"):
        assert flag in src, flag
    # 저장본 경로와 수집 경로가 **같은 헬퍼**를 쓴다.
    assert src.count("_handle_panel_file(report, args, settings, panel_file)") \
        == 2, "두 경로가 다른 코드를 쓴다"
    assert "artifact.load(args.round_id)" in src, "저장본을 쓰지 않는다"
    assert "artifact.save(report)" in src, "저장하지 않는다"


def test_k2_audit_only_does_not_rewrite_the_report():
    src = inspect.getsource(
        __import__("toto.cli", fromlist=["_panel_only"])._panel_only)
    assert "args.import_panel_result is None" in src
    assert "return 0" in src


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
