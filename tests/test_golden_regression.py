"""골든 회귀 — 산출물이 **한 바이트라도** 바뀌면 알린다 (리팩터링 Phase 1).

Phase 2 이후(죽은 코드 제거 · 중복 통합 · 책임 분리)의 전제는 "동작을 바꾸지
않는다" 다. 지금까지 그것을 사람이 바이트 수를 재서(데모 675,280 · 재렌더
949,635 …) 확인했는데, 이 파일이 그 대조를 자동으로 한다.

**네트워크 없이 · 모델 호출 없이 · 저장소 파일을 쓰지 않고** 돈다. 산출물은
깨끗한 자식 프로세스에서 만든다 — 같은 pytest 세션의 다른 테스트가 모듈
전역을 바꿔 두었어도 결과가 흔들리지 않게 하려는 것이다.

고정하는 것 (tests/golden/expected.json — 이름 · sha256 · 바이트 수)

  demo/     데모 14경기. 난수 시드·경기 날짜가 고정돼 있고 생성 시각만 고정한다
            report.html          `python -m toto --demo` 가 쓰는 바로 그 파일
            match_material.md    경기자료 MD (4-A)
            artifact.json        회차 저장본 (4-C, saved_at 제외)
            panel_payloads.jsonl 경기별 PanelPayload 직렬화 (API 경로의 캐시 키)
            round_data.txt       회차 원본 자료 (6-F-9 기준선)
            common_packet.txt    A·B 가 stdin 으로 받는 공통 packet (6-F-10)
            chat_export_all/…    `--panel-export-all` 이 쓰는 파일 전부
  panel/    test_panel_apply 의 14경기 · 근거 셋 · A/B/C 보관본
            chat_export/…        `--panel-export` 가 쓰는 파일 전부
            common_packet.txt
            moderator_sheet_completed.md · moderator_stdin.txt   (6-F-3 · 6-F-9)
            moderator_inputs.jsonl  API 경로의 사회자 입력 (3-C)
            panel_result.json    1·2·3단계 보관본 반영 (6-F-14)
            import_lines.txt · audit_lines.txt   가져오기 · 감사 (4-B · 4-C)
            report.html          패널이 붙은 리포트
  prompt/   시스템 프롬프트 · 지침 · JSON 규격 · 판 번호 · 에이전트 지시문
  pages/    GitHub Pages 회차 목록 (§1-52)

그리고 셋을 함께 확인한다 (`problems`).

  · 테스트가 조립한 데모 리포트가 CLI `--demo` 출력과 **같다**
  · 저장본을 되살려 다시 그려도 **같다** (재렌더 경로 · §1-25)
  · 산출물에 오늘 날짜·임시 폴더 경로가 **새어 들어가지 않는다**

일부러 바꿨을 때
    TOTO_GOLDEN_UPDATE=1 python tests/test_golden_regression.py
  expected.json 이 새로 쓰이고, 무엇이 바뀌었는지 이름 단위로 출력된다.
  git diff 로 확인한 뒤 커밋한다.

무엇이 달라졌는지 내용을 보려면
    TOTO_GOLDEN_DUMP=<폴더> python tests/test_golden_regression.py
  산출물을 그 폴더에 파일로 쓴다. 바꾸기 전 커밋에서 한 번 더 돌려 두 폴더를
  diff 한다. (파일을 쓰는 것은 자식 프로세스이고 저장소 밖 폴더만 쓴다.)
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

EXPECTED_FILE = HERE / "golden" / "expected.json"
ENV_UPDATE = "TOTO_GOLDEN_UPDATE"
ENV_DUMP = "TOTO_GOLDEN_DUMP"
EMIT_FLAG = "--emit"

# 생성 시각. 산출물 가운데 시계를 읽는 것은 이것 하나다 (cli 의 datetime.now).
FIXED_NOW = datetime(2026, 1, 1, 0, 0)
GENERATED = FIXED_NOW.strftime("%Y-%m-%d %H:%M")
PAGES_ROUNDS = ["260054", "260052"]

_PASSED = _FAILED = 0


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


def digest(text: str) -> dict:
    data = text.encode("utf-8")
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


# ==========================================================================
# 산출물 만들기 — **자식 프로세스에서만** 돈다 (`--emit`)
# ==========================================================================
class _FixedDatetime(datetime):
    """cli 가 `datetime.now()` 로 적는 생성 시각만 고정한다."""

    @classmethod
    def now(cls, tz=None):                                  # noqa: ARG003
        return cls(FIXED_NOW.year, FIXED_NOW.month, FIXED_NOW.day,
                   FIXED_NOW.hour, FIXED_NOW.minute)


def _read_tree(root: Path, prefix: str, out: dict) -> None:
    """폴더 아래 파일 전부. 줄바꿈은 읽을 때 `\\n` 으로 모인다 — 윈도우에서
    `write_text` 가 CRLF 로 써도 같은 값이 나온다."""
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        out[f"{prefix}/{rel}"] = path.read_text(encoding="utf-8")


def _run_cli(argv: list, out: Path) -> str:
    """`python -m toto …` 를 그대로 부르고 쓴 리포트를 읽는다. 생성 시각을
    고정하고 클라우드 폴더 복사만 막는다 (사용자 PC 의 동기화 폴더에 데모가
    복사되면 안 된다)."""
    from toto import cli, publish
    saved = (cli.datetime, publish.publish)
    cli.datetime = _FixedDatetime
    publish.publish = lambda *a, **k: []
    try:
        code = cli.main([*argv, "-o", str(out)])
    finally:
        cli.datetime, publish.publish = saved
    if code != 0:
        raise RuntimeError(f"{argv} 종료코드 {code}")
    return out.read_text(encoding="utf-8")


def _demo_report(settings):
    """cli 의 --demo 갈래를 그대로 옮긴 것. CLI 출력과 같은지 `problems` 가 본다."""
    from toto.analyze import evaluate_round, run_all
    from toto.fixtures import build_demo_matches
    from toto.models import Report
    report = Report(generated_at=GENERATED)
    report.matches = build_demo_matches()
    report.round_id = "DEMO"
    report.source_status["데이터"] = "ok (샘플 · 실제 배당/성적 아님)"
    run_all(report.matches, settings, season_matches=report.season_matches)
    expected = int(settings.betman.get("expected_matches", 14))
    report.verdict = evaluate_round(report.matches, expected_total=expected)
    missing = [m.no for m in report.matches if not m.probs]
    if missing:
        report.warnings.append(
            "배당률을 가져오지 못한 경기: " + ", ".join(f"{n}번" for n in missing))
    return report


def _artifact_text(report, keep_saved_at: bool = False) -> str:
    """저장본(4-C)이 쓰는 모양 — `artifact.save()` 와 같은 직렬화 인자다.
    골든에서는 저장 시각만 뺀다."""
    from toto import artifact
    data = artifact.to_dict(report)
    if not keep_saved_at:
        data.pop("saved_at", None)
    return json.dumps(data, ensure_ascii=False, indent=1)


def _demo_outputs(settings, tmp: Path, out: dict, problems: list) -> None:
    from toto import match_material, panel, panelauto, panelexport
    from toto.render import render_report

    cli_html = _run_cli(["--demo"], tmp / "demo_cli.html")
    out["demo/report.html"] = cli_html

    report = _demo_report(settings)
    if render_report(report, settings) != cli_html:
        problems.append("테스트가 조립한 데모 리포트가 CLI --demo 출력과 "
                        "다릅니다 — _demo_report() 를 cli 의 --demo 갈래에 "
                        "맞추십시오")

    out["demo/match_material.md"] = match_material.build(report)
    out["demo/artifact.json"] = _artifact_text(report)

    # 저장본을 **실제 재렌더 입구**로 다시 그린다 (§1-25). 데모는 저장하지
    # 않으므로(§1-16) 같은 직렬화로 임시 파일에만 쓴다.
    saved = tmp / "DEMO.json"
    saved.write_text(_artifact_text(report, keep_saved_at=True),
                     encoding="utf-8")
    if _run_cli(["--rerender-artifact", str(saved)],
                tmp / "demo_rerender.html") != cli_html:
        problems.append("저장본을 --rerender-artifact 로 다시 그린 데모 "
                        "리포트가 원본과 다릅니다")

    out["demo/panel_payloads.jsonl"] = "\n".join(
        panel.serialize_payload(panel.build_panel_payload(m))
        for m in report.matches) + "\n"
    out["demo/round_data.txt"] = panelauto.pack_round_data(report, settings)
    out["demo/common_packet.txt"] = panelauto.common_packet_text(report,
                                                                 settings)

    export_dir = tmp / "demo_export"
    panelexport.export(report, outdir=export_dir,
                       include_without_evidence=True, settings=settings)
    _read_tree(export_dir, "demo/chat_export_all", out)


def _panel_outputs(settings, tmp: Path, out: dict) -> None:
    """test_panel_apply 의 픽스처(14경기 · 근거 셋 · A/B/C)를 그대로 쓴다 (§1-8)."""
    import test_panel_apply as TA
    from toto import (moderator, panel, panelaudit, panelauto, panelexport,
                      panelimport, panelpaste, panelwork)
    from toto.render import render_report

    report = TA.make_report("APPLY")
    base = tmp / "panel_work"

    export_dir = tmp / "panel_export"
    panelexport.export(copy.deepcopy(report), outdir=export_dir,
                       settings=settings)
    _read_tree(export_dir, "panel/chat_export", out)
    out["panel/common_packet.txt"] = panelauto.common_packet_text(report,
                                                                  settings)

    TA.seed(report, base)
    # 사회자 시트와 C 의 stdin 은 `reports/panel_<회차>/` 를 쓴다 — 자식
    # 프로세스 안에서만 그 뿌리를 임시 폴더로 옮긴다.
    panelexport.ROOT = tmp
    sheet = panelwork.build_completed_sheet(report, settings, base)
    if sheet.errors:
        raise RuntimeError(f"사회자 시트: {sheet.issues}")
    out["panel/moderator_sheet_completed.md"] = Path(sheet.path).read_text(
        encoding="utf-8")
    stdin, why = panelauto.pack_moderator_data(report, base)
    if not stdin:
        raise RuntimeError(f"사회자 stdin: {why}")
    out["panel/moderator_stdin.txt"] = stdin

    data, result = panelwork.assemble_panel_result(report, settings, base)
    if data is None:
        raise RuntimeError(f"조립 실패: {result.issues}")
    path = panelpaste.write_canonical(data, report.round_id, base)
    out["panel/panel_result.json"] = path.read_text(encoding="utf-8")

    outcome = panelimport.run(path, report, settings)
    audit = panelaudit.audit(outcome, report)
    out["panel/import_lines.txt"] = "\n".join(
        panelimport.report_lines(outcome)) + "\n"
    out["panel/audit_lines.txt"] = "\n".join(
        panelaudit.report_lines(audit)) + "\n"
    out["panel/moderator_inputs.jsonl"] = "\n".join(
        moderator.serialize_input(moderator.build_input(
            panel.build_panel_payload(m), m.panel.opinions))
        for m in report.matches) + "\n"
    out["panel/report.html"] = render_report(report, settings)


def _prompt_outputs(settings, tmp: Path, out: dict) -> None:
    from toto import (moderator, panel, panelauto, panelexport, panelimport,
                      panelpacket)
    sims = moderator.simulations_of(settings)
    out["prompt/system_common.md"] = panel.SYSTEM_COMMON
    for role in panel.ROLES:
        out[f"prompt/{role}.md"] = panel.ROLE_PROMPTS[role]
    out["prompt/moderator.md"] = moderator.system_prompt(sims)
    out["prompt/project_instructions.md"] = panelexport.project_instructions(
        sims)
    out["prompt/schema_guide.md"] = panelexport.schema_guide()
    for stage in (*panel.ROLES, panelauto.MODERATOR_DIR):
        out[f"prompt/stage_system/{stage}.md"] = panelauto.stage_system(
            tmp / "ws" / stage, stage, settings)
    out["prompt/analyst_task.txt"] = panelauto.one_line(
        panelauto.analyst_prompt(14))
    out["prompt/moderator_task.txt"] = panelauto.one_line(
        panelauto.moderator_prompt(14))
    out["prompt/versions.json"] = json.dumps({
        "panel_prompt_version": panel.PANEL_PROMPT_VERSION,
        "moderator_prompt_version": moderator.MODERATOR_PROMPT_VERSION,
        "instructions_fingerprint": panelexport.instructions_fingerprint(sims),
        "panel_result_schema": panelimport.SCHEMA_VERSION,
        "packet_version": panelpacket.PACKET_VERSION,
        "debate_simulations": sims,
    }, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def _pages_outputs(out: dict) -> None:
    from toto import pagespublish
    out["pages/index.html"] = pagespublish.render_index(PAGES_ROUNDS)
    out["pages/index_empty.html"] = pagespublish.render_index([])


def _fourteen(out: dict, problems: list) -> None:
    """14경기가 전부 실렸는지. 한 경기가 빠져도 sha 는 바뀌지만, 이 줄이
    **무엇이** 빠졌는지 먼저 말해 준다."""
    counts = {
        "demo/panel_payloads.jsonl":
            len(out["demo/panel_payloads.jsonl"].splitlines()),
        "panel/moderator_inputs.jsonl":
            len(out["panel/moderator_inputs.jsonl"].splitlines()),
        "panel/panel_result.json":
            len(json.loads(out["panel/panel_result.json"])["matches"]),
    }
    for name, n in counts.items():
        if n != 14:
            problems.append(f"{name} 에 경기가 {n}개입니다 (14개여야 합니다)")


def _leaks(out: dict, tmp: Path, problems: list) -> None:
    """시계·임시 폴더가 산출물에 새면 골든이 날마다·실행마다 달라진다."""
    today = datetime.now().strftime("%Y-%m-%d")
    markers = {"오늘 날짜": today, "임시 폴더 경로": str(tmp),
               "임시 폴더 경로(/)": tmp.as_posix()}
    for name, text in out.items():
        for what, marker in markers.items():
            if marker and marker in text:
                problems.append(f"{name} 에 {what}({marker})가 들어 있습니다")


def emit() -> dict:
    """모든 산출물을 만들어 {이름: 본문} 과 문제 목록을 돌려준다."""
    os.environ["TOTO_PAGES_DEPLOY"] = "0"           # 자동 배포를 부르지 않는다
    from toto import settings as settings_mod
    settings = settings_mod.load_settings()
    out: dict = {}
    problems: list = []
    with tempfile.TemporaryDirectory(prefix="toto_golden_") as name:
        tmp = Path(name)
        _demo_outputs(settings, tmp, out, problems)
        _panel_outputs(settings, tmp, out)
        _prompt_outputs(settings, tmp, out)
        _pages_outputs(out)
        _fourteen(out, problems)
        _leaks(out, tmp, problems)
    return {"texts": dict(sorted(out.items())), "problems": problems}


def _emit_main(target: Path) -> int:
    import logging
    logging.disable(logging.CRITICAL)
    result = emit()
    dump = os.environ.get(ENV_DUMP)
    if dump:
        root = Path(dump)
        for name, text in result["texts"].items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    payload = {"entries": {k: digest(v) for k, v in result["texts"].items()},
               "problems": result["problems"]}
    # 표준출력이 아니라 파일로 넘긴다 — CLI 가 무엇을 출력하든 섞이지 않는다.
    target.write_text(json.dumps(payload, ensure_ascii=False),
                      encoding="utf-8")
    return 0


# ==========================================================================
# 부모 쪽 — 자식을 띄워 결과를 받는다
# ==========================================================================
_ACTUAL: dict = {}


def actual(seed: str = "0") -> dict:
    if seed not in _ACTUAL:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        if seed != "0":
            env.pop(ENV_DUMP, None)          # 덤프는 기준 실행 한 번만
        with tempfile.TemporaryDirectory(prefix="toto_golden_out_") as d:
            target = Path(d) / "entries.json"
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), EMIT_FLAG,
                 str(target)],
                cwd=str(REPO), env=env, capture_output=True, timeout=600)
            if proc.returncode != 0 or not target.is_file():
                tail = proc.stderr.decode("utf-8", "replace")[-3000:]
                raise AssertionError(f"산출물 생성 실패 (종료코드 "
                                     f"{proc.returncode}):\n{tail}")
            _ACTUAL[seed] = json.loads(target.read_text(encoding="utf-8"))
    return _ACTUAL[seed]


def load_expected() -> dict:
    if not EXPECTED_FILE.is_file():
        return {}
    return json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))["entries"]


def write_expected(entries: dict) -> list:
    old = load_expected()
    changed = sorted(k for k in set(old) | set(entries)
                     if old.get(k) != entries.get(k))
    EXPECTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    body = {"_about": ("tests/test_golden_regression.py 의 기대값. "
                       "손으로 고치지 말고 TOTO_GOLDEN_UPDATE=1 로 다시 쓴다."),
            "entries": dict(sorted(entries.items()))}
    EXPECTED_FILE.write_text(
        json.dumps(body, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    return changed


def expected() -> dict:
    if os.environ.get(ENV_UPDATE) == "1" and not _ACTUAL.get("_updated"):
        changed = write_expected(actual()["entries"])
        _ACTUAL["_updated"] = True
        print(f"  골든 갱신: {len(changed)}개 바뀜")
        for name in changed:
            print(f"    · {name}")
    exp = load_expected()
    assert exp, (f"{EXPECTED_FILE} 이 없습니다 — "
                 f"{ENV_UPDATE}=1 로 한 번 만드십시오")
    return exp


def _compare(prefix: str) -> None:
    exp = {k: v for k, v in expected().items() if k.startswith(prefix)}
    got = {k: v for k, v in actual()["entries"].items()
           if k.startswith(prefix)}
    assert exp, f"{prefix} 로 시작하는 기대값이 없습니다"
    lines = []
    for name in sorted(set(exp) | set(got)):
        e, g = exp.get(name), got.get(name)
        if e == g:
            continue
        if e is None:
            lines.append(f"{name}: 새로 생겼습니다 ({g['bytes']:,} bytes)")
        elif g is None:
            lines.append(f"{name}: 사라졌습니다")
        else:
            lines.append(f"{name}: {e['bytes']:,} → {g['bytes']:,} bytes "
                         f"(sha {e['sha256'][:12]} → {g['sha256'][:12]})")
    assert not lines, (
        "산출물이 바뀌었습니다 — 의도한 변경이면 "
        f"{ENV_UPDATE}=1 로 갱신하고, 내용은 {ENV_DUMP}=<폴더> 로 보십시오\n  "
        + "\n  ".join(lines))


# ==========================================================================
# A. 기대값과 같다
# ==========================================================================
def test_a1_demo_outputs_unchanged():
    _compare("demo/")


def test_a2_panel_outputs_unchanged():
    _compare("panel/")


def test_a3_prompts_unchanged():
    _compare("prompt/")


def test_a4_pages_outputs_unchanged():
    _compare("pages/")


def test_a5_no_other_outputs():
    """골든의 네 갈래 밖으로 이름이 생기면 어느 비교에도 걸리지 않는다."""
    groups = ("demo/", "panel/", "prompt/", "pages/")
    stray = [k for k in {**expected(), **actual()["entries"]}
             if not k.startswith(groups)]
    assert not stray, stray


# ==========================================================================
# B. 산출물을 만드는 방법 자체가 믿을 만하다
# ==========================================================================
def test_b1_no_problems():
    """CLI 와 같고 · 재렌더해도 같고 · 14경기가 다 있고 · 시계·임시 경로가
    새지 않는다."""
    problems = actual()["problems"]
    assert not problems, "\n  ".join(problems)


def test_b2_independent_of_hash_seed():
    """파이썬 문자열 해시는 실행마다 달라진다(§3-8). 집합·사전 순서에 기대는
    출력이 생기면 여기서 걸린다."""
    a, b = actual("0")["entries"], actual("1")["entries"]
    diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    assert not diff, f"PYTHONHASHSEED 0 과 1 에서 다른 산출물: {diff}"


def test_b3_expected_file_is_sorted_and_complete():
    """손으로 고친 흔적이 없어야 한다 — 갱신 도구가 쓴 모양 그대로."""
    raw = json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))
    names = list(raw["entries"])
    assert names == sorted(names)
    for name, entry in raw["entries"].items():
        assert set(entry) == {"sha256", "bytes"}, name
        assert len(entry["sha256"]) == 64, name


def test_b4_emit_writes_nothing_in_repo():
    """골든을 만드는 일이 저장소를 건드리면 그 자체가 회귀다."""
    try:
        before = subprocess.run(
            ["git", "status", "--porcelain", "--ignored", "-uall"],
            cwd=str(REPO), capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  SKIP git 을 쓸 수 없습니다 ({exc})")
        return
    if before.returncode != 0:
        print("  SKIP git 저장소가 아닙니다")
        return
    _ACTUAL.pop("0", None)
    actual("0")
    after = subprocess.run(
        ["git", "status", "--porcelain", "--ignored", "-uall"],
        cwd=str(REPO), capture_output=True, text=True, timeout=120)
    new = sorted(set(after.stdout.splitlines())
                 - set(before.stdout.splitlines()))
    new = [line for line in new if "__pycache__" not in line]
    assert not new, f"저장소에 생긴 것: {new}"


def main() -> int:
    if sys.argv[1:2] == [EMIT_FLAG]:
        return _emit_main(Path(sys.argv[2]))
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과")
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
