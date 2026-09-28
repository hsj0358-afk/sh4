"""실물 골든 — 실제 회차 저장본으로 산출물이 바뀌지 않았는지 본다 (리팩터링 Phase 1).

데모 골든(test_golden_regression.py)은 어디서나 돌지만 데모에는 근거·정성
자료·대륙대회 색인이 없다. 실물 저장본이 그 빈칸을 채운다. 다만 저장본과
패널 보관본은 gitignore 대상이라(§1-16 · §1-40) **있는 환경에서만** 확인한다.

기대값(tests/golden/real.json)은 **입력 파일의 sha256 으로 묶여 있다.**

  · 같은 입력이 있으면 → 산출물을 비교한다 (다르면 FAIL)
  · 입력이 없거나 내용이 다르면 → SKIP 이다. 다른 자료로 만든 산출물은
    달라야 정상이라 실패로 세지 않는다. 사유는 SKIP 줄에 적힌다.

회차마다 두 묶음이다.

  artifact  저장본 하나로 만드는 것
            report.html            `--rerender-artifact` 가 쓰는 파일 그대로
            match_material.md      경기자료 MD
            panel_payloads.jsonl   경기별 PanelPayload
            round_data.txt         A·B 회차 원본 (6-F-9 기준선)
            common_packet.txt      A·B 가 받는 공통 packet (6-F-10)
            moderator_sheet.md     사회자 자료 (의견 없는 판)
  panel     저장본 + panel_work/<회차>/ 의 A·B·C 보관본
            panel_result.json      `--apply-panel-work` 가 쓰는 Panel Result
            audit_lines.txt        감사
            report.html            패널이 반영된 최종 리포트

**저장소를 한 글자도 쓰지 않는다.** 반영 결과는 임시 폴더에만 쓰고
(`panel_results/`·manifest 를 건드리지 않는다), 자동 배포는 끈다.

새 회차의 기준을 남기려면 (사용자 PC 에서)
    TOTO_GOLDEN_UPDATE=1 python tests/test_golden_real.py
  이 PC 에 있는 회차만 다시 쓰고, 없는 회차의 기준은 그대로 둔다.
내용을 보려면 TOTO_GOLDEN_DUMP=<폴더> (데모 골든과 같다).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import realdata                                                   # noqa: E402
import test_golden_regression as G                                # noqa: E402

EXPECTED_FILE = HERE / "golden" / "real.json"
ARTIFACT_DIR = REPO / "data" / "artifacts"
PANEL_WORK = REPO / "panel_work"
EMIT_FLAG = "--emit-real"
GROUPS = ("artifact", "panel")

_PASSED = _FAILED = _SKIPPED = 0


def check(name, fn):
    global _PASSED, _FAILED, _SKIPPED
    try:
        fn()
    except realdata.SkipTest as exc:
        _SKIPPED += 1
        print(f"  SKIP {name}: {exc}")
    except AssertionError as exc:
        _FAILED += 1
        print(f"  FAIL {name}: {exc}")
    except Exception as exc:                                # noqa: BLE001
        _FAILED += 1
        print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    else:
        _PASSED += 1
        print(f"  ok   {name}")


def file_sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return Path(path).resolve().relative_to(REPO).as_posix()


def local_rounds() -> list:
    if not ARTIFACT_DIR.is_dir():
        return []
    return sorted(p.stem for p in ARTIFACT_DIR.glob("*.json")
                  if p.stem.isdigit())


# ==========================================================================
# 산출물 만들기 — **자식 프로세스에서만** 돈다 (`--emit-real <회차> <파일>`)
# ==========================================================================
def emit_real(round_id: str) -> dict:
    os.environ["TOTO_PAGES_DEPLOY"] = "0"           # 자동 배포를 부르지 않는다
    from toto import (match_material, panel, panelaudit, panelauto,
                      panelexport, panelimport, panelpaste, panelwork)
    from toto import settings as settings_mod
    from toto.render import render_report

    settings = settings_mod.load_settings()
    source = ARTIFACT_DIR / f"{round_id}.json"
    groups: dict = {}
    problems: list = []
    with tempfile.TemporaryDirectory(prefix="toto_golden_real_") as name:
        tmp = Path(name)

        # ---- artifact ----------------------------------------------------
        out: dict = {}
        cli_html = G._run_cli(["--rerender-artifact", str(source)],
                              tmp / "rerender.html")
        out["report.html"] = cli_html
        report = realdata.load_artifact(source)
        if render_report(report, settings) != cli_html:
            problems.append("저장본을 직접 렌더한 결과가 --rerender-artifact "
                            "출력과 다릅니다")
        payloads = [panel.build_panel_payload(m) for m in report.matches]
        out["match_material.md"] = match_material.build(report)
        out["panel_payloads.jsonl"] = "\n".join(
            panel.serialize_payload(p) for p in payloads) + "\n"
        out["round_data.txt"] = panelauto.pack_round_data(report, settings)
        out["common_packet.txt"] = panelauto.common_packet_text(report,
                                                                settings)
        out["moderator_sheet.md"] = panelexport.moderator_data_sheet(
            round_id, payloads)
        if len(payloads) != len(report.matches) or not payloads:
            problems.append(f"PanelPayload {len(payloads)}개 / 경기 "
                            f"{len(report.matches)}개")
        groups["artifact"] = {"inputs": {rel(source): file_sha(source)},
                              "texts": out}

        # ---- panel (보관본 셋이 다 있을 때만) ------------------------------
        inputs = [panelwork.path_for(round_id, role) for role in panel.ROLES]
        inputs.append(panelwork.moderator_result_path(round_id))
        if all(p.is_file() for p in inputs):
            out = {}
            data, result = panelwork.assemble_panel_result(report, settings)
            if data is None:
                problems.append(f"보관본 조립 실패: {result.issues}")
            else:
                path = panelpaste.write_canonical(data, round_id, tmp)
                out["panel_result.json"] = path.read_text(encoding="utf-8")
                outcome = panelimport.run(path, report, settings)
                audit = panelaudit.audit(outcome, report)
                out["audit_lines.txt"] = "\n".join(
                    panelaudit.report_lines(audit)) + "\n"
                out["report.html"] = render_report(report, settings)
                sources = {rel(source): file_sha(source)}
                sources.update({rel(p): file_sha(p) for p in inputs})
                groups["panel"] = {"inputs": sources, "texts": out}

        for group in groups.values():
            for key, text in group["texts"].items():
                if str(tmp) in text or tmp.as_posix() in text:
                    problems.append(f"{key} 에 임시 폴더 경로가 들어 있습니다")
    return {"groups": groups, "problems": problems}


def _emit_main(round_id: str, target: Path) -> int:
    import logging
    logging.disable(logging.CRITICAL)
    result = emit_real(round_id)
    dump = os.environ.get(G.ENV_DUMP)
    if dump:
        for gname, group in result["groups"].items():
            for key, text in group["texts"].items():
                path = Path(dump) / "real" / round_id / gname / key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
    payload = {
        "groups": {g: {"inputs": v["inputs"],
                       "entries": {k: G.digest(t)
                                   for k, t in sorted(v["texts"].items())}}
                   for g, v in result["groups"].items()},
        "problems": result["problems"]}
    target.write_text(json.dumps(payload, ensure_ascii=False),
                      encoding="utf-8")
    return 0


# ==========================================================================
# 부모 쪽
# ==========================================================================
_ACTUAL: dict = {}


def actual(round_id: str, seed: str = "0") -> dict:
    key = (round_id, seed)
    if key not in _ACTUAL:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        if seed != "0":
            env.pop(G.ENV_DUMP, None)
        with tempfile.TemporaryDirectory(prefix="toto_golden_out_") as d:
            target = Path(d) / "real.json"
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), EMIT_FLAG,
                 round_id, str(target)],
                cwd=str(REPO), env=env, capture_output=True, timeout=900)
            if proc.returncode != 0 or not target.is_file():
                tail = proc.stderr.decode("utf-8", "replace")[-3000:]
                raise AssertionError(f"{round_id} 산출물 생성 실패 (종료코드 "
                                     f"{proc.returncode}):\n{tail}")
            _ACTUAL[key] = json.loads(target.read_text(encoding="utf-8"))
    return _ACTUAL[key]


def load_expected() -> dict:
    if not EXPECTED_FILE.is_file():
        return {}
    return json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))["rounds"]


def write_expected(rounds: dict) -> None:
    body = {"_about": ("tests/test_golden_real.py 의 기대값. 입력 파일 sha 로 "
                       "묶여 있다. 손으로 고치지 말고 TOTO_GOLDEN_UPDATE=1 "
                       "로 다시 쓴다."),
            "rounds": {r: {g: {"inputs": dict(sorted(v["inputs"].items())),
                               "entries": dict(sorted(v["entries"].items()))}
                           for g, v in sorted(block.items())}
                       for r, block in sorted(rounds.items())}}
    EXPECTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXPECTED_FILE.write_text(
        json.dumps(body, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")


def expected() -> dict:
    if os.environ.get(G.ENV_UPDATE) == "1" and not _ACTUAL.get("_updated"):
        rounds = load_expected()
        for round_id in local_rounds():
            got = actual(round_id)["groups"]
            # 이 PC 에서 만들지 못한 묶음(보관본 없음)은 옛 기준을 남긴다.
            rounds[round_id] = {**rounds.get(round_id, {}), **got}
            print(f"  실물 골든 갱신: {round_id} ({', '.join(sorted(got))})")
        write_expected(rounds)
        _ACTUAL["_updated"] = True
    return load_expected()


def comparable() -> tuple:
    """(비교할 [(회차, 묶음)], 건너뛴 사유). 입력 sha 가 같은 것만 견준다."""
    exp = expected()
    pairs, why = [], []
    local = local_rounds()
    if not local:
        why.append(f"실물 저장본 없음 — {rel(ARTIFACT_DIR)} 가 비었다")
    for round_id in local:
        base = exp.get(round_id)
        if base is None:
            why.append(f"{round_id}: 기준 없음 — {G.ENV_UPDATE}=1 로 남길 수 "
                       f"있다")
            continue
        for gname in GROUPS:
            group = base.get(gname)
            if group is None:
                continue
            missing = [p for p in group["inputs"] if not (REPO / p).is_file()]
            if missing:
                why.append(f"{round_id}/{gname}: 입력 없음 {missing}")
                continue
            changed = [p for p, s in group["inputs"].items()
                       if file_sha(REPO / p) != s]
            if changed:
                why.append(f"{round_id}/{gname}: 입력 내용이 기준과 다르다 "
                           f"{changed}")
                continue
            pairs.append((round_id, gname))
    return pairs, why


def _require_pairs() -> list:
    pairs, why = comparable()
    for line in why:
        print(f"    · {line}")
    if not pairs:
        raise realdata.SkipTest("; ".join(why) or "견줄 실물 기준이 없다")
    return pairs


def _diff_lines(exp: dict, got: dict, prefix: str) -> list:
    lines = []
    for name in sorted(set(exp) | set(got)):
        e, g = exp.get(name), got.get(name)
        if e == g:
            continue
        if e is None:
            lines.append(f"{prefix}{name}: 새로 생겼습니다")
        elif g is None:
            lines.append(f"{prefix}{name}: 사라졌습니다")
        else:
            lines.append(f"{prefix}{name}: {e['bytes']:,} → {g['bytes']:,} "
                         f"bytes (sha {e['sha256'][:12]} → "
                         f"{g['sha256'][:12]})")
    return lines


# ==========================================================================
# 테스트
# ==========================================================================
def test_r1_real_outputs_unchanged():
    lines = []
    for round_id, gname in _require_pairs():
        got = actual(round_id)["groups"].get(gname)
        exp = load_expected()[round_id][gname]["entries"]
        if got is None:
            lines.append(f"{round_id}/{gname}: 만들지 못했습니다")
            continue
        lines += _diff_lines(exp, got["entries"], f"{round_id}/{gname}/")
    assert not lines, (
        "실물 산출물이 바뀌었습니다 — 의도한 변경이면 "
        f"{G.ENV_UPDATE}=1 로 갱신하고, 내용은 {G.ENV_DUMP}=<폴더> 로 "
        "보십시오\n  " + "\n  ".join(lines))


def test_r2_no_problems():
    problems = []
    for round_id in sorted({r for r, _g in _require_pairs()}):
        problems += [f"{round_id}: {p}"
                     for p in actual(round_id)["problems"]]
    assert not problems, "\n  ".join(problems)


def test_r3_independent_of_hash_seed():
    diff = []
    for round_id, gname in _require_pairs():
        a = actual(round_id, "0")["groups"].get(gname, {}).get("entries")
        b = actual(round_id, "1")["groups"].get(gname, {}).get("entries")
        a, b = a or {}, b or {}
        names = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        if names:
            diff.append(f"{round_id}/{gname}: {names}")
    assert not diff, f"PYTHONHASHSEED 0 과 1 에서 다른 산출물: {diff}"


def test_r4_emit_writes_nothing_in_repo():
    """실물 보관본을 **읽기만** 한다 — panel_results/·manifest 가 생기면 안 된다."""
    pairs = _require_pairs()
    try:
        before = subprocess.run(
            ["git", "status", "--porcelain", "--ignored", "-uall"],
            cwd=str(REPO), capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise realdata.SkipTest(f"git 을 쓸 수 없습니다 ({exc})")
    if before.returncode != 0:
        raise realdata.SkipTest("git 저장소가 아닙니다")
    stamps = {p: p.stat().st_mtime_ns
              for p in [*ARTIFACT_DIR.glob("*.json"), *PANEL_WORK.rglob("*")]
              if p.is_file()}
    for round_id in sorted({r for r, _g in pairs}):
        _ACTUAL.pop((round_id, "0"), None)
        actual(round_id)
    after = subprocess.run(
        ["git", "status", "--porcelain", "--ignored", "-uall"],
        cwd=str(REPO), capture_output=True, text=True, timeout=120)
    new = sorted(set(after.stdout.splitlines())
                 - set(before.stdout.splitlines()))
    new = [line for line in new if "__pycache__" not in line]
    assert not new, f"저장소에 생긴 것: {new}"
    touched = [rel(p) for p, t in stamps.items()
               if not p.is_file() or p.stat().st_mtime_ns != t]
    assert not touched, f"손댄 입력 파일: {touched}"


def main() -> int:
    if sys.argv[1:2] == [EMIT_FLAG]:
        return _emit_main(sys.argv[2], Path(sys.argv[3]))
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        check(name, fn)
    print(f"\n{_PASSED}/{_PASSED + _FAILED} 통과"
          + (f" · 건너뜀 {_SKIPPED}" if _SKIPPED else ""))
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
