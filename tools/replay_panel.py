"""패널 오프라인 재생 — 얼려 둔 사전 스냅샷에 프롬프트 안을 다시 돌린다.

실제 결과가 쌓이기를 기다리지 않고, **이미 정산된 회차**를 같은 자료로 다시
돌려 프롬프트 안을 견준다. 지금 목표 지표는 **정확 스코어 적중**이다.

    python tools/replay_panel.py show --variant <안>              # 무엇이 바뀌나 · $0
    python tools/replay_panel.py run --rounds 260054 --variant baseline --dry-run   # 준비만 · $0
    python tools/replay_panel.py run --rounds 260054 260059 260061 --variant baseline
    python tools/replay_panel.py run --rounds 260054 260059 260061 --variant <안>
    python tools/replay_panel.py score --rounds 260054 260059 260061 --variants baseline <안>

지키는 것.

  · **운영 자리를 건드리지 않는다.** `panel_work/`·`panel_results/`·`reports/`·
    `data/` 에 쓰지 않는다. 저장·조립·검증은 운영 함수를 그대로 부르되
    `base=` 로 재생 폴더를 넘긴다 (§1-8) — 검증 규칙이 두 벌이 되지 않는다.
  · **재생 폴더는 저장소 밖이다.** 저장소 안에서 `claude -p` 를 띄우면
    `CLAUDE.md` 가 호출마다 실린다 (§1-45). 안이면 시작하지 않는다.
  · **사후 스냅샷으로 돌리지 않는다.** 저장본의 `saved_at` 이 그 회차의 첫
    킥오프보다 뒤면(다시 수집한 저장본) 순위표·색인에 결과가 섞여 있다
    (§1-13·§1-27). 시작하지 않는다.
  · **안전장치는 운영과 같다.** `panelauto.preflight()` 를 그대로 부른다 —
    API 키 차단 · 구독 인증 확인 · 공통 packet 을 한 번 만들어 A·B 가 같은
    문자열을 받는다 (§1-9 불변조건 2).
  · **운영 프롬프트를 바꾸지 않는다.** 안(variant)은 운영 프롬프트 글자 위의
    **치환 목록**이다. 치환할 글자가 운영 프롬프트에 정확히 한 번 있어야
    하고, 없으면 시작하지 않는다 — 운영 프롬프트가 바뀌면 안이 조용히 다른
    것이 되지 않게 한다.
  · 한도·실패면 **거기서 멈춘다.** 다시 돌리면 끝난 단계는 건너뛴다.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from toto import (artifact, marketeval, moderator, panel,  # noqa: E402
                  panelauto, panelpacket, panelwork, roundlog, xpts)
from toto.settings import load_settings                    # noqa: E402

REPLAY_ENV = "TOTO_PANEL_REPLAY_DIR"      # 재생 폴더를 직접 정할 때
REPLAY_SCRATCH = "toto_panel_replay"
AGENT_DIR = "agent"
SHEET_DIR = "sheet"
RESULT_FILE = "replay.json"
SCORE_FILE = "score.json"

A, B, C = panel.DATA_ANALYST, panel.MATCHUP_ANALYST, panelauto.MODERATOR_DIR
STAGES = (A, B, C)
STAGE_KEY = {A: "a", B: "b", C: "c"}

# 종료코드 — 0 정상 · 1 실패 · 2 시작 불가 · 3 사용량 한도
EXIT_OK, EXIT_FAIL, EXIT_REFUSED, EXIT_LIMIT = 0, 1, 2, 3


# ==========================================================================
# 안(variant) — 운영 프롬프트 위의 치환 목록
# ==========================================================================
@dataclass(frozen=True)
class Edit:
    """`stages` 의 `part` 글자에서 `old` 를 `new` 로 한 번 바꾼다.

    `part` 는 `common`(공통 규칙 — A·B 에만 실린다) 또는 `role`(역할 규칙,
    사회자는 사회자 지침 전체)이다. `old` 는 그 글자에 **정확히 한 번** 있어야
    한다.
    """
    stages: tuple
    part: str
    old: str
    new: str
    why: str = ""


class VariantError(ValueError):
    pass


# --- 지난 안 ---------------------------------------------------------------
# v1(정확 스코어 목표)은 운영에 들어갔다 — PANEL 6 · MODERATOR 7 (§1-63).
# 운영 프롬프트가 곧 그 글자이므로 지금 `baseline` 이 v1 과 같다. 새 안을
# 시험할 때는 여기에 이름을 더한다.
VARIANTS: dict = {
    "baseline": (),
}

# 재생 폴더에 남기는 "이 폴더는 어떤 프롬프트로 만들었나" 기록.
PROMPTS_FILE = "prompts.json"


def _replace_once(text: str, edit: Edit, stage: str) -> str:
    n = text.count(edit.old)
    if n != 1:
        raise VariantError(
            f"{STAGE_KEY[stage]} 단계 {edit.part} 글자에서 치환할 문구가 "
            f"{n}번 나옵니다 (정확히 1번이어야 합니다): {edit.old[:40]!r} — "
            f"운영 프롬프트가 바뀌었으면 안을 다시 맞추십시오")
    return text.replace(edit.old, edit.new, 1)


def prompt_parts(stage: str, variant: str, settings=None) -> tuple:
    """그 단계의 (공통, 역할) 글자에 안을 적용한 것.

    출발점은 운영 함수 `panelauto.prompt_texts()` 다 — 재생이 프롬프트를
    따로 조립하지 않는다.
    """
    if variant not in VARIANTS:
        raise VariantError(f"모르는 안: {variant} (있는 것: "
                           f"{', '.join(VARIANTS)})")
    common, role = panelauto.prompt_texts(stage, settings)
    for edit in VARIANTS[variant]:
        if stage not in edit.stages:
            continue
        if edit.part == "common":
            if stage == C:
                raise VariantError("사회자 지침에는 공통 규칙이 따로 실리지 "
                                   "않습니다 — part=role 로 적으십시오")
            common = _replace_once(common, edit, stage)
        elif edit.part == "role":
            role = _replace_once(role, edit, stage)
        else:
            raise VariantError(f"모르는 part: {edit.part}")
    return common, role


def system_for(stage: str, variant: str, settings=None) -> str:
    common, role = prompt_parts(stage, variant, settings)
    return panelauto.join_system(stage, common, role)


def check_variant(variant: str, settings=None) -> list:
    """안이 운영 프롬프트에 맞는지 본다. 문제 목록 (비면 통과)."""
    try:
        for stage in STAGES:
            system_for(stage, variant, settings)
    except VariantError as exc:
        return [str(exc)]
    return []


def variant_diff(variant: str, settings=None) -> list:
    """운영(baseline) 대비 안의 차이 — 단계별 unified diff 줄."""
    lines = []
    for stage in STAGES:
        old = system_for(stage, "baseline", settings).splitlines()
        new = system_for(stage, variant, settings).splitlines()
        diff = list(difflib.unified_diff(
            old, new, f"{STAGE_KEY[stage]}/baseline",
            f"{STAGE_KEY[stage]}/{variant}", lineterm="", n=1))
        lines.extend(diff or [f"--- {STAGE_KEY[stage]}: 바뀐 것 없음"])
    return lines


# ==========================================================================
# 자리
# ==========================================================================
def replay_root() -> Path:
    env = os.environ.get(REPLAY_ENV, "").strip()
    return Path(env) if env else \
        Path(tempfile.gettempdir()).joinpath(REPLAY_SCRATCH)


def inside_repo(path: Path) -> bool:
    try:
        Path(path).resolve().relative_to(ROOT.resolve())
    except ValueError:
        return False
    return True


def round_base(root: Path, variant: str, round_id: str) -> Path:
    return Path(root).joinpath(variant, str(round_id))


# ==========================================================================
# 저장본 — 사전 스냅샷만
# ==========================================================================
def load_round(round_id: str, artifacts_dir: Path | None = None) -> tuple:
    """(Report | None, 사유). 사후 스냅샷이면 사유를 담아 None 이다."""
    path = artifact.path_for(round_id, artifacts_dir)
    report, why = artifact.load_path(path)
    if report is None:
        return None, why
    try:
        saved = json.loads(path.read_text(encoding="utf-8")).get("saved_at")
        saved_at = datetime.strptime(str(saved), "%Y-%m-%d %H:%M")
    except (OSError, ValueError, TypeError):
        return None, (f"저장 시각(saved_at)을 읽지 못해 사전 스냅샷인지 "
                      f"확인할 수 없습니다 ({path})")
    if not artifact.is_prematch(report, now=saved_at):
        return None, (f"킥오프 뒤에 저장된 스냅샷입니다 (saved_at {saved}) — "
                      f"결과가 섞였을 수 있어 재생에 쓰지 않습니다 ({path})")
    return report, ""


# ==========================================================================
# 실행
# ==========================================================================
class StopReplay(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _run_one(stage: str, system: str, prompt: str, stdin_text: str,
             workspace: Path, *, model: str, cli: str, timeout: int) -> tuple:
    """`claude -p` 한 번. (글자, 실행 정보). 실패면 StopReplay."""
    workspace.mkdir(parents=True, exist_ok=True)
    run = panelauto.run_agent(prompt, system, workspace, timeout=timeout,
                              model=model, cli=cli, stdin_text=stdin_text)
    info = {"status": run.status, "session_id": run.session_id,
            "cost_usd": run.cost_usd, "turns": run.turns,
            "usage": run.usage or {}, "reused": False}
    if not run.ok:
        code = EXIT_LIMIT if run.status == panelauto.AGENT_USAGE_LIMIT \
            else EXIT_FAIL
        raise StopReplay(code, f"{STAGE_KEY[stage]} 단계 실패 "
                               f"({run.status}): {run.message}")
    text, why = panelauto.agent_text(run, workspace)
    if not text:
        raise StopReplay(EXIT_FAIL, f"{STAGE_KEY[stage]} 단계: 빈 응답 ({why})")
    return text, info


def _issues(result) -> str:
    return " · ".join(panelwork.report_lines(result))[:600]


def _system_shas(systems: dict) -> dict:
    return {STAGE_KEY[s]: panelpacket.packet_digest(t)
            for s, t in systems.items()}


def _check_prompts(base: Path, systems: dict) -> None:
    """이 폴더의 끝난 단계가 **지금과 같은 프롬프트**로 만들어졌는지 본다.

    끝난 단계를 건너뛰는 규칙은 보관본이 검증을 지나는지만 본다. 운영
    프롬프트가 바뀐 뒤(안을 채택했을 때처럼) 같은 안 이름으로 다시 돌리면
    옛 프롬프트의 결과가 새 이름표를 달고 재사용된다. 기록이 다르면 시작하지
    않는다 — 다른 `--out` 을 쓰면 된다.
    """
    want = _system_shas(systems)
    recorded = None
    for name, key in ((PROMPTS_FILE, None), (RESULT_FILE, "system_sha256")):
        path = base / name
        if not path.is_file():
            continue
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        recorded = body.get(key) if key else body
        if recorded:
            break
    if recorded and recorded != want:
        raise StopReplay(EXIT_REFUSED, (
            f"이 재생 폴더({base})는 다른 프롬프트로 만든 결과입니다 — "
            f"운영 프롬프트가 바뀐 뒤라면 다른 --out 을 쓰십시오"))
    (base / PROMPTS_FILE).write_text(json.dumps(want), encoding="utf-8")


def run_round(report, variant: str, settings, *, root: Path, model: str,
              cli: str, echo=print) -> dict:
    """회차 하나를 A → B → C 로 재생한다. 요약 dict 를 돌려주고 파일로 남긴다.

    끝난 단계(검증을 지난 보관본)가 있으면 건너뛴다 — 한도에서 멈춘 뒤
    다시 돌려도 돈을 두 번 쓰지 않는다.
    """
    rid = str(report.round_id or "")
    base = round_base(root, variant, rid)
    base.mkdir(parents=True, exist_ok=True)
    agents = base / AGENT_DIR
    sheet_dir = base / SHEET_DIR
    count = len(report.matches)

    pre = panelauto.preflight(report, rid, base=base)
    if not pre.ok:
        raise StopReplay(EXIT_REFUSED, " / ".join(pre.problems))
    packet = pre.packet_text
    stages: dict = {}
    systems = {stage: system_for(stage, variant, settings) for stage in STAGES}
    _check_prompts(base, systems)

    for role in (A, B):
        key = STAGE_KEY[role]
        _ops, done = panelwork.load_stage(rid, role, report, base)
        if not done.errors:
            stages[key] = {"status": "reused", "reused": True}
            echo(f"  {rid} {key}: 끝난 결과를 씁니다")
            continue
        echo(f"  {rid} {key}: claude -p …")
        text, info = _run_one(role, systems[role],
                              panelauto.analyst_prompt(count), packet,
                              agents / key, model=model, cli=cli,
                              timeout=panelauto.ANALYST_AGENT_TIMEOUT)
        saved = panelwork.save_stage(text, role, report, base)
        if not saved.success:
            raise StopReplay(EXIT_FAIL, f"{key} 검증 실패: {_issues(saved)}")
        stages[key] = info
        echo(f"  {rid} {key}: 검증 통과 {saved.saved_matches}/{count}")

    key = STAGE_KEY[C]
    mod_path = panelwork.moderator_result_path(rid, base)
    reused = False
    if mod_path.is_file():
        try:
            _d, _a, res = panelwork.parse_moderator_result(
                mod_path.read_text(encoding="utf-8-sig"), report, settings)
            reused = res.success
        except (OSError, UnicodeDecodeError, ValueError):
            reused = False
    if reused:
        stages[key] = {"status": "reused", "reused": True}
        echo(f"  {rid} c: 끝난 결과를 씁니다")
    else:
        built = panelwork.build_completed_sheet(report, settings, base,
                                                outdir=sheet_dir)
        if not built.success:
            raise StopReplay(EXIT_FAIL, f"사회자 자료 조립 실패: "
                                        f"{_issues(built)}")
        stdin_text, why = panelauto.pack_moderator_data(report, base,
                                                        sheet_dir=sheet_dir)
        if not stdin_text:
            raise StopReplay(EXIT_FAIL, f"사회자 입력을 만들지 못했습니다: {why}")
        echo(f"  {rid} c: claude -p …")
        text, info = _run_one(C, systems[C],
                              panelauto.moderator_prompt(count), stdin_text,
                              agents / key, model=model, cli=cli,
                              timeout=panelauto.MODERATOR_AGENT_TIMEOUT)
        path, res = panelwork.save_moderator_result(text, report, settings,
                                                    base)
        if path is None:
            raise StopReplay(EXIT_FAIL, "사회자 결과 검증 실패: "
                             + " · ".join(i.message for i in res.issues)[:600])
        stages[key] = info
        echo(f"  {rid} c: 검증 통과")

    # 운영의 최종 반영과 **같은 조립·검증**(ok 경로)을 지난다 — 사회자가
    # 고른 스코어의 출처가 실제 A·B 원안과 맞는지까지 본다 (§1-49).
    data, assembled = panelwork.assemble_panel_result(report, settings, base)
    summary = {
        "variant": variant, "round": rid, "model": model or "cli",
        "panel_prompt_version": panel.PANEL_PROMPT_VERSION,
        "moderator_prompt_version": moderator.MODERATOR_PROMPT_VERSION,
        "packet_sha256": panelpacket.packet_digest(packet),
        "system_sha256": _system_shas(systems),
        "edits": [e.why for e in VARIANTS[variant]],
        "stages": stages,
        "assembled_ok": data is not None,
        "assemble_issues": [i.message for i in assembled.issues][:20],
        "scores": read_scores(rid, base),
    }
    (base / RESULT_FILE).write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


# ==========================================================================
# 점수
# ==========================================================================
def _score(row: dict, home_key: str, away_key: str):
    h, a = row.get(home_key), row.get(away_key)
    ok = all(isinstance(v, int) and not isinstance(v, bool) for v in (h, a))
    return [h, a] if ok else None


def _rows(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def read_scores(round_id: str, base: Path | None = None) -> dict:
    """보관본 셋 → {경기번호: {"a": [h,a]|None, "b": …, "c": …}}. **읽기만.**

    `base=None` 이면 운영 보관본(`panel_work/<회차>/`)이다.
    """
    out: dict = {}
    for role, key in ((A, "a"), (B, "b")):
        for row in _rows(panelwork.path_for(round_id, role, base)):
            no = row.get(panelwork.STAGE_NO)
            if isinstance(no, int):
                out.setdefault(str(no), {})[key] = _score(
                    row, "predicted_home", "predicted_away")
    for row in _rows(panelwork.moderator_result_path(round_id, base)):
        no = row.get(panelwork.STAGE_NO)
        if isinstance(no, int):
            out.setdefault(str(no), {})["c"] = _score(
                row, "adopted_home", "adopted_away")
    return out


def actual_scores(round_id: str, path: Path | None = None) -> dict:
    """정산된 실제 스코어. {경기번호: [h, a]}. `data/round_matches.csv` 를 읽기만."""
    rows = roundlog._read(path or roundlog.MATCH_FILE, roundlog.MATCH_FIELDS)
    out = {}
    for r in rows:
        if str(r.get("round")) != str(round_id):
            continue
        try:
            out[str(int(r["no"]))] = [int(r["home_goals"]),
                                      int(r["away_goals"])]
        except (KeyError, TypeError, ValueError):
            continue
    return out


# --------------------------------------------------------------------------
# 기대 적중 — 실제 결과 하나 대신 시장이 매긴 스코어 확률로 잰다
# --------------------------------------------------------------------------
# 정확 스코어는 잘 맞혀도 경기당 12% 안팎이라, 42경기의 실제 적중 수는 운에
# 크게 흔들린다. 그래서 같은 고른 스코어를 **시장이 매긴 그 스코어의 확률**로
# 다시 잰다 — 경기마다 킥오프 전 피나클 승/무/패 확률에 맞춘 독립 포아송
# 두 개(양 팀 기대 득점)로 스코어 확률을 만들고, 고른 스코어의 확률을 더한다.
#
#   · **시장을 정답에 가까운 기준으로 쓴다.** 높게 나오면 "시장보다 나쁘지
#     않다" 이지 "시장을 넘었다" 가 아니다. 시장 최빈 스코어가 언제나 위다.
#   · 재생 도구의 **채점에만** 쓴다. 운영 분석·리포트·패널 자료에 이 값이
#     들어가지 않는다 (§1-27 — 이 시스템에 독립 모델 확률은 없다).
#   · 시장 확률은 `marketeval.select()` 를 그대로 거친다 — 킥오프 전에 기록됐고
#     합이 1 근처이고 실제 결과가 있는 경기만 들어온다. 빠진 경기는 0 으로
#     세지 않고 따로 센다.
#   · 무승부 보정(Dixon-Coles)이 없다. 맞춤 오차를 함께 적는다.
FIT_LAMBDA_MAX = 5.0
FIT_COARSE_STEP = 0.1
FIT_REFINE_ROUNDS = 6


def _outcome_probs(lh: float, la: float) -> tuple:
    r = xpts.match_xpts(lh, la)
    return (r.home_win_probability, r.draw_probability,
            r.away_win_probability)


def _fit_error(lh: float, la: float, target: tuple) -> float:
    got = _outcome_probs(lh, la)
    return sum((g - t) ** 2 for g, t in zip(got, target))


def fit_market(p_home: float, p_draw: float, p_away: float) -> tuple:
    """시장 승/무/패 확률 → (홈 기대 득점, 원정 기대 득점, 최대 절대 오차).

    격자에서 시작해 간격을 줄여 가며 오차 제곱합이 가장 작은 점을 찾는다.
    같은 입력이면 같은 답이다(난수 없음).
    """
    target = (p_home, p_draw, p_away)
    step = FIT_COARSE_STEP
    grid = [step * i for i in range(1, int(FIT_LAMBDA_MAX / step) + 1)]
    best = min(((_fit_error(h, a, target), h, a) for h in grid for a in grid))
    _, lh, la = best
    for _ in range(FIT_REFINE_ROUNDS):
        step /= 4
        cands = [(lh + dh * step, la + da * step)
                 for dh in range(-4, 5) for da in range(-4, 5)]
        best = min((_fit_error(h, a, target), h, a) for h, a in cands
                   if 0 < h <= FIT_LAMBDA_MAX and 0 < a <= FIT_LAMBDA_MAX)
        _, lh, la = best
    got = _outcome_probs(lh, la)
    err = max(abs(g - t) for g, t in zip(got, target))
    return lh, la, err


def score_probability(lh: float, la: float, home: int, away: int) -> float:
    """독립 포아송에서 정확히 `home`-`away` 가 나올 확률 (0~9 절단)."""
    ph, pa = xpts.poisson_pmf(lh), xpts.poisson_pmf(la)
    if not (0 <= home < len(ph) and 0 <= away < len(pa)):
        return 0.0
    return ph[home] * pa[away]


def market_mode(lh: float, la: float) -> tuple:
    """시장 확률에서 가장 그럴듯한 스코어. 동률이면 득점 합이 적은 쪽, 그다음 홈 득점이 적은 쪽."""
    ph, pa = xpts.poisson_pmf(lh), xpts.poisson_pmf(la)
    p, neg_total, neg_home = max(
        (ph[i] * pa[j], -(i + j), -i)
        for i in range(len(ph)) for j in range(len(pa)))
    return (-neg_home, -neg_total + neg_home), p


def market_fits(rounds, path: Path | None = None) -> tuple:
    """{(회차, 경기번호): (λh, λa, 오차)}, [(회차, 번호, 뺀 사유)]. 읽기만."""
    rows = marketeval.load_rows(path)
    wanted = {str(r) for r in rounds}
    picked, dropped = marketeval.select(
        [r for r in rows if str(r.get("round")) in wanted])
    fits = {}
    for row in picked:
        m = row.market
        fits[(row.round_id, str(row.no))] = fit_market(m["H"], m["D"], m["A"])
    skipped = [(d.round_id, d.no, d.reason) for d in dropped
               if d.reason != "실제 결과가 없습니다"]
    return fits, skipped


def score(rounds, variants, root: Path, *, actual_path: Path | None = None,
          stored_base: Path | None = None) -> dict:
    """운영 보관본 · 재생 안들을 실제 스코어와 견준다.

    세는 것은 **정확 스코어 적중**과, 운영 보관본 대비 사회자 스코어가 바뀐
    경기 수다. baseline 의 바뀐 수가 곧 같은 프롬프트로 다시 돌렸을 때의
    흔들림(잡음 바닥)이다.
    """
    sources = {"stored": {rid: read_scores(rid, stored_base) for rid in rounds}}
    meta = {}
    for v in variants:
        sources[v] = {}
        for rid in rounds:
            path = round_base(root, v, rid) / RESULT_FILE
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                body = {}
            sources[v][rid] = body.get("scores") or {}
            meta[(v, rid)] = body

    actual = {rid: actual_scores(rid, actual_path) for rid in rounds}
    fits, skipped = market_fits(rounds, actual_path)
    table = {}
    for name, per_round in sources.items():
        row = {"n": 0, "hits": {"a": 0, "b": 0, "c": 0},
               "missing": {"a": 0, "b": 0, "c": 0},
               "changed_c_vs_stored": 0, "compared_c": 0,
               "c_scores": Counter(),
               "expected": {"a": 0.0, "b": 0.0, "c": 0.0},
               "expected_n": {"a": 0, "b": 0, "c": 0}}
        for rid in rounds:
            got = per_round.get(rid) or {}
            stored = sources["stored"].get(rid) or {}
            for no, real in actual[rid].items():
                row["n"] += 1
                pick = got.get(no) or {}
                fit = fits.get((str(rid), no))
                for k in ("a", "b", "c"):
                    s = pick.get(k)
                    if s is None:
                        row["missing"][k] += 1
                        continue
                    if s == real:
                        row["hits"][k] += 1
                    if fit is not None:
                        row["expected"][k] += score_probability(
                            fit[0], fit[1], s[0], s[1])
                        row["expected_n"][k] += 1
                c = pick.get("c")
                if c is not None:
                    row["c_scores"][f"{c[0]}-{c[1]}"] += 1
                s0 = (stored.get(no) or {}).get("c")
                if name != "stored" and c is not None and s0 is not None:
                    row["compared_c"] += 1
                    row["changed_c_vs_stored"] += int(c != s0)
        table[name] = row
    mode = {"expected": 0.0, "hits": 0, "n": 0, "scores": Counter()}
    errs = []
    for rid in rounds:
        for no, real in actual[rid].items():
            fit = fits.get((str(rid), no))
            if fit is None:
                continue
            (h, a), p = market_mode(fit[0], fit[1])
            mode["expected"] += p
            mode["hits"] += int([h, a] == real)
            mode["n"] += 1
            mode["scores"][f"{h}-{a}"] += 1
            errs.append(fit[2])
    market = {"mode": mode, "fitted": len(errs),
              "fit_error_mean": (sum(errs) / len(errs)) if errs else None,
              "fit_error_max": max(errs) if errs else None,
              "skipped": skipped}
    stored_packets = {}
    for rid in rounds:
        rec = panelwork.read_manifest(rid, stored_base).get("stages", {}) \
            .get(panelwork.STAGE_A, {})
        stored_packets[rid] = rec.get("packet_sha256", "")
    return {"rounds": list(rounds), "table": table, "market": market,
            "actual_matches": {rid: len(v) for rid, v in actual.items()},
            "stored_packet_sha256": stored_packets,
            "replay_packet_sha256": {f"{v}/{rid}": (m or {}).get(
                "packet_sha256", "") for (v, rid), m in meta.items()}}


def score_lines(result: dict) -> list:
    lines = [f"회차 {', '.join(result['rounds'])} · 정산된 경기 "
             f"{sum(result['actual_matches'].values())}"]
    lines.append(f"{'출처':<10}{'A 적중':>8}{'B 적중':>8}{'C 적중':>8}"
                 f"{'C 바뀜(vs 운영)':>18}   C 스코어 상위")
    for name, row in result["table"].items():
        n = row["n"]
        hit = "".join(f"{row['hits'][k]:>4}/{n:<3}" for k in ("a", "b", "c"))
        changed = ("—" if name == "stored"
                   else f"{row['changed_c_vs_stored']}/{row['compared_c']}")
        top = " ".join(f"{s}×{c}" for s, c in row["c_scores"].most_common(6))
        lines.append(f"{name:<10}{hit}{changed:>14}   {top}")
        miss = {k: v for k, v in row["missing"].items() if v}
        if miss:
            lines.append(f"{'':<10}스코어 없음: " + " · ".join(
                f"{k} {v}" for k, v in miss.items()))
    lines += expected_lines(result)
    lines.append("같은 입력인가 (packet sha 앞 12자):")
    for rid in result["rounds"]:
        stored = (result["stored_packet_sha256"].get(rid) or "")[:12] or "기록 없음"
        reps = " · ".join(f"{k.split('/')[0]} {v[:12] or '없음'}"
                          for k, v in result["replay_packet_sha256"].items()
                          if k.endswith(f"/{rid}"))
        lines.append(f"  {rid}: 운영 {stored} · {reps}")
    return lines


def expected_lines(result: dict) -> list:
    market = result.get("market") or {}
    mode = market.get("mode") or {}
    if not market.get("fitted"):
        return ["기대 적중: 시장 확률이 있는 정산 경기가 없습니다"]
    lines = ["기대 적중 (킥오프 전 피나클 승/무/패에 맞춘 독립 포아송 · 시장 기준 — "
             "시장보다 나은지가 아니라 시장 쪽에 얼마나 가까운지를 잰다)",
             f"{'출처':<10}{'A':>16}{'B':>16}{'C':>16}"]

    def cell(total: float, n: int) -> str:
        return f"{total:.2f}/{n} ({100 * total / n:.1f}%)" if n else "없음"

    for name, row in result["table"].items():
        exp, n = row.get("expected") or {}, row.get("expected_n") or {}
        lines.append(f"{name:<10}" + "".join(
            f"{cell(exp.get(k, 0.0), n.get(k, 0)):>16}" for k in ("a", "b", "c")))
    top = " ".join(f"{s}×{c}" for s, c in mode["scores"].most_common(6))
    lines.append(f"{'시장 최빈':<10}{cell(mode['expected'], mode['n']):>16}"
                 f"   실제 적중 {mode['hits']}/{mode['n']} · {top}")
    lines.append(f"맞춤 경기 {market['fitted']} · 승/무/패 맞춤 오차 평균 "
                 f"{market['fit_error_mean']:.4f} · 최대 {market['fit_error_max']:.4f}")
    for rid, no, why in market.get("skipped") or []:
        lines.append(f"  기대 적중에서 뺌: {rid} {no}번 — {why}")
    return lines


# ==========================================================================
# 명령
# ==========================================================================
def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="패널 오프라인 재생")
    sub = p.add_subparsers(dest="cmd", required=True)
    show = sub.add_parser("show", help="안이 운영 프롬프트에서 무엇을 바꾸나 ($0)")
    show.add_argument("--variant", required=True)
    run = sub.add_parser("run", help="회차를 재생한다 (claude -p · 구독)")
    run.add_argument("--rounds", nargs="+", required=True)
    run.add_argument("--variant", required=True)
    run.add_argument("--model", default=None,
                     help="기본 sonnet (운영과 같다) · cli 면 CLI 기본 모델")
    run.add_argument("--out", default=None, help="재생 폴더 (저장소 밖)")
    run.add_argument("--dry-run", action="store_true",
                     help="준비 점검만 · 모델을 부르지 않는다")
    sc = sub.add_parser("score", help="정확 스코어 적중을 센다 ($0)")
    sc.add_argument("--rounds", nargs="+", required=True)
    sc.add_argument("--variants", nargs="+", required=True)
    sc.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    from toto.cli import safe_console
    safe_console()
    args = _parser().parse_args(argv)
    settings = load_settings()

    if args.cmd == "show":
        problems = check_variant(args.variant, settings)
        if problems:
            print("\n".join(problems))
            return EXIT_REFUSED
        for edit in VARIANTS[args.variant]:
            print(f"· {edit.why}")
        print("\n".join(variant_diff(args.variant, settings)))
        return EXIT_OK

    root = Path(args.out) if args.out else replay_root()
    if inside_repo(root):
        print(f"재생 폴더가 저장소 안입니다 ({root}) — 저장소 밖을 쓰십시오. "
              f"안이면 claude -p 가 CLAUDE.md 를 호출마다 싣습니다")
        return EXIT_REFUSED

    if args.cmd == "score":
        result = score(args.rounds, args.variants, root)
        lines = score_lines(result)
        print("\n".join(lines))
        try:
            root.mkdir(parents=True, exist_ok=True)
            body = dict(result, table={
                k: dict(v, c_scores=dict(v["c_scores"]))
                for k, v in result["table"].items()})
            if "market" in body:
                body["market"] = dict(body["market"], mode=dict(
                    body["market"]["mode"],
                    scores=dict(body["market"]["mode"]["scores"])))
            (root / SCORE_FILE).write_text(
                json.dumps(body, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except OSError:
            pass
        return EXIT_OK

    problems = check_variant(args.variant, settings)
    if problems:
        print("\n".join(problems))
        return EXIT_REFUSED
    model = panelauto.resolve_model(args.model)
    reports = []
    for rid in args.rounds:
        report, why = load_round(rid)
        if report is None:
            print(f"{rid}: 시작하지 않습니다 — {why}")
            return EXIT_REFUSED
        reports.append(report)

    print(f"안 {args.variant} · 모델 {model or 'cli 기본'} · 재생 폴더 {root}")
    if args.dry_run:
        for report in reports:
            pre = panelauto.preflight(report, report.round_id,
                                      base=round_base(root, args.variant,
                                                      report.round_id))
            print(f"[{report.round_id}] {'준비됨' if pre.ok else '막힘'}")
            for line in pre.problems + pre.warnings + pre.notes:
                print(f"  · {line}")
        return EXIT_OK

    for report in reports:
        print(f"[{report.round_id}]")
        try:
            summary = run_round(report, args.variant, settings, root=root,
                                model=model, cli="")
        except StopReplay as stop:
            print(f"  멈춤 — {stop}")
            if stop.code == EXIT_LIMIT:
                print("  사용량 한도입니다. 과금으로 넘기지 않습니다 — 한도가 "
                      "풀린 뒤 같은 명령을 다시 돌리면 끝난 단계는 건너뜁니다")
            return stop.code
        cost = sum((s.get("cost_usd") or 0) for s in summary["stages"].values())
        print(f"  조립 {'ok' if summary['assembled_ok'] else '실패'} · "
              f"이번 실행 비용(추정) ${cost:.2f}")
        for issue in summary["assemble_issues"][:5]:
            print(f"    · {issue}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
