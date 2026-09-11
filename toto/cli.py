"""축구토토 승무패 분석 리포트 CLI.

    python -m toto                      # 이번 회차 자동 탐지 → 풀 수집 → 리포트
    python -m toto --round 260032       # 회차 지정
    python -m toto --matches-file examples/matches.yaml
    python -m toto --demo               # 네트워크 없이 샘플 리포트
    python -m toto --skip-whoscored     # 배당률 위주 빠른 실행

소스 하나가 실패해도 나머지는 계속 진행하고, 빠진 항목은 리포트에
'데이터 없음' 으로 표시된다.
"""
from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from . import __version__
from .analyze import evaluate_round, run_all
from .cache import Cache
from .models import Report, TeamProfile
from .normalize import TeamResolver
from .render import render_report
from .settings import load_settings

log = logging.getLogger("toto")


def _setup_logging(verbose: bool) -> None:
    """로그 설정. **여러 번 불려도 레벨이 반영돼야 한다.**

    메뉴가 같은 프로세스 안에서 기능을 반복 실행하므로 이 함수도 반복해서
    불린다. `basicConfig` 는 루트에 핸들러가 이미 있으면 **아무것도 하지
    않아서**, 2회차부터 `verbose` 가 무시된다(실측: 2회차 verbose=True 인데
    레벨이 INFO 그대로). 핸들러 구성은 그대로 두고 레벨만 다시 맞춘다 —
    `force=True` 는 쓰지 않는다. 그러면 남의 핸들러까지 걷어내기 때문이다.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(          # 첫 호출에만 핸들러를 붙인다 (중복 없음)
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger().setLevel(level)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="toto",
        description="축구토토 승무패 14경기 상세 분석 리포트를 생성합니다.")
    p.add_argument("--round", dest="round_id", default=None,
                   help="회차 코드 (미지정 시 판매중 회차 자동 탐지)")
    p.add_argument("--matches-file", type=Path, default=None,
                   help="경기 목록 YAML (베트맨 크롤링 대신 사용)")
    p.add_argument("-o", "--output", type=Path, default=None,
                   help="출력 HTML 경로 (기본: reports/toto_<회차>.html)")
    p.add_argument("--demo", action="store_true",
                   help="네트워크 없이 샘플 데이터로 리포트 생성")
    p.add_argument("--skip-whoscored", action="store_true",
                   help="후스코어드 수집 생략 (배당률·순위 위주, 빠름)")
    p.add_argument("--skip-fotmob", action="store_true",
                   help="FotMob 수집 생략 (순위·홈원정 승점·폼·맞대결)")
    p.add_argument("--skip-match-details", action="store_true",
                   help="경기 상세 생략 (npxG·xGOT·총슈팅·피슈팅). 몇 분 빨라진다")
    p.add_argument("--skip-odds", action="store_true",
                   help="피나클 배당률 수집 생략")
    p.add_argument("--panel", action="store_true",
                   help="두 전문가 패널의 해석을 붙입니다 (Anthropic API 필요·"
                        "유료). 지정하지 않으면 호출하지 않습니다.")
    p.add_argument("--panel-export", action="store_true",
                   help="패널·사회자를 클로드 채팅에서 손으로 돌릴 자료를 "
                        "파일로 냅니다 (API 를 부르지 않습니다).")
    p.add_argument("--export-match-material", action="store_true",
                   help="회차 분석 결과를 클로드 채팅용 경기자료 MD 한 장으로 "
                        "냅니다 (reports/<회차>_경기자료.md). API 를 부르지 "
                        "않습니다.")
    p.add_argument("--import-panel-result", type=Path, default=None,
                   metavar="FILE",
                   help="클로드 채팅에서 만든 Panel Result JSON 을 가져와 "
                        "검증합니다. 오류가 있으면 붙이지 않습니다.")
    p.add_argument("--validate-panel-result", type=Path, default=None,
                   metavar="FILE",
                   help="--import-panel-result 와 같은 검증을 하되 "
                        "리포트에 붙이지 않습니다 (검사만).")
    p.add_argument("--audit-panel-result", type=Path, default=None,
                   metavar="FILE",
                   help="가져온 Panel Result 의 회차 전체 구조를 감사합니다 "
                        "(커버리지·채택·분포·근거). 판정하지 않습니다.")
    p.add_argument("--paste-panel-result", type=Path, default=None,
                   metavar="FILE",
                   help="클로드 3단계 Moderator 결과(JSON 배열) 원문을 읽어 "
                        "Panel Result 로 옮긴 뒤 가져오기·감사까지 합니다. "
                        "검증을 통과할 때만 panel_results/ 에 저장합니다.")
    p.add_argument("--panel-export-all", action="store_true",
                   help="--panel-export 를 켜고, 근거 0건 경기도 축 지표만으로 "
                        "냅니다 (시즌 초). 시트에 경고가 붙고 --panel 실행과 "
                        "같은 결과가 아닙니다.")
    p.add_argument("--rerender-artifact", type=Path, default=None,
                   metavar="FILE",
                   help="저장된 회차 분석 결과(data/artifacts/<회차>.json)를 "
                        "지금 코드로 다시 렌더한다. 수집하지 않는다")
    p.add_argument("--no-cache", action="store_true",
                   help="캐시를 무시하고 새로 수집")
    p.add_argument("--open", action="store_true",
                   help="생성 후 기본 브라우저로 열기")
    p.add_argument("--serve", action="store_true",
                   help="리포트를 같은 와이파이에 공개해 폰에서 열기 (Ctrl+C 종료)")
    p.add_argument("--serve-port", type=int, default=8899,
                   help="--serve 가 쓸 포트 (기본 8899)")
    p.add_argument("-v", "--verbose", action="store_true", help="디버그 로그")
    p.add_argument("--menu", action="store_true",
                   help="대화형 메뉴 (바탕화면 바로가기용)")
    p.add_argument("--version", action="version", version=f"toto {__version__}")
    return p


def _resolve_teams(matches, resolver: TeamResolver, report: Report,
                   settings) -> None:
    """베트맨 한글 팀명을 영문 정규명으로 해석하고, 리그를 채운다."""
    for match in matches:
        for side in ("home", "away"):
            ref = getattr(match, side)
            canon = resolver.resolve(ref.name_ko)
            if canon:
                ref.canonical = canon
                ref.matched = True
                if not ref.display:
                    ref.display = ref.name_ko or canon
            else:
                ref.matched = False
                ref.display = ref.name_ko or "(팀명 없음)"
                report.warnings.append(
                    f"{match.no}번 경기: '{ref.name_ko}' 팀명을 매칭하지 못했습니다. "
                    f"data/teams.yaml 에 별칭을 추가하면 다음 실행부터 해결됩니다.")

        # 베트맨 경기표에는 리그명 컬럼이 없다. 리그를 모르면 배당률 조회가
        # 통째로 불가능하므로 팀 소속 리그로 역추론한다(홈팀 우선).
        if not match.league:
            for ref in (match.home, match.away):
                league = resolver.league_of(ref.canonical) if ref.canonical else None
                if league:
                    match.league = league
                    match.league_ko = settings.league_ko(league)
                    break
            else:
                report.warnings.append(
                    f"{match.no}번 경기({match.title}): 리그를 알 수 없어 "
                    f"배당률을 조회하지 못합니다.")

        # 컵대회 등으로 두 팀의 리그가 다르면 표시에 남긴다
        lh = resolver.league_of(match.home.canonical) if match.home.canonical else None
        la = resolver.league_of(match.away.canonical) if match.away.canonical else None
        if lh and la and lh != la:
            match.notes.append(
                f"두 팀의 소속 리그가 다릅니다 ({settings.league_ko(lh)} vs "
                f"{settings.league_ko(la)}) — 컵대회 경기로 보이며, "
                f"배당률·순위 데이터가 없을 수 있습니다.")


# 없으면 아무것도 제대로 할 수 없는 의존성. 선택 의존성(playwright·bs4)은
# 소스별로 확인해 '실패 (사유)' 로 남기지만(§1-6), 아래 둘은 다르다 —
# PyYAML 이 없으면 config_toto.yaml 과 data/teams.yaml 이 통째로 안 읽혀
# **모든 팀명이 매칭에 실패하고**, 그런데도 10초를 돌려 빈 리포트를 만들어
# 낸다(실측: 260050, 52.3KB, 확인 필요 43건). 그건 결과가 아니라 소음이다.
#
# **PyYAML 하나뿐이다.** requests 가 없으면 피나클만 실패하고 나머지는
# 그대로 간다 — 그건 §1-6 의 '한 소스 실패, 나머지 진행' 이지 중단 사유가
# 아니다. 여기 목록을 늘려 정상 실행을 막지 않는다.
_REQUIRED_MODULES = (("yaml", "PyYAML"),)


def _missing_required_deps() -> bool:
    """필수 의존성이 빠졌으면 그 자리에서 알리고 True 를 돌려준다."""
    import importlib.util

    missing = [name for mod, name in _REQUIRED_MODULES
               if importlib.util.find_spec(mod) is None]
    if not missing:
        return False
    log.error("필수 패키지가 없습니다: %s", ", ".join(missing))
    log.error("  가상환경을 켜지 않았을 수 있습니다:")
    log.error("    PowerShell   .\\.venv\\Scripts\\Activate.ps1")
    log.error("    cmd          .venv\\Scripts\\activate.bat")
    log.error("    bash         source .venv/bin/activate")
    log.error("  그래도 없으면:  pip install -r requirements-toto.txt")
    log.error("  (%s 로 실행 중)", sys.executable)
    return True


def _paste_to_canonical(report: Report, args, settings, paste_file):
    """3단계 결과 원문 → Panel Result 파일 (Phase 4-F). 실패하면 `None`.

    **검증을 통과한 경우에만 파일을 만든다.** 깨진 붙여넣기가
    `panel_results/` 에 남으면 다음 실행이 그것을 집어 든다.
    """
    from . import panelpaste
    try:
        text = Path(paste_file).read_text(encoding="utf-8")
    except OSError as exc:
        log.error("붙여넣기 파일을 읽지 못했습니다: %s", exc)
        report.source_status["패널 가져오기"] = f"실패 ({exc})"
        return None

    path, outcome = panelpaste.apply(text, report, settings)
    if path is None:
        report.source_status["패널 가져오기"] = outcome.status_line()
        for line in panelpaste.report_lines(outcome):
            log.error("붙여넣기: %s", line)
        return None

    log.info("붙여넣기 → %s (%d경기)", path, outcome.imported_matches)
    # 아래 경로가 가져오기·감사를 하도록 같은 파일을 가리켜 준다.
    args.import_panel_result = path
    args.audit_panel_result = path
    return path


def _handle_panel_file(report: Report, args, settings, panel_file) -> None:
    """Panel Result 를 검증·부착하고(4-B) 회차 구조를 감사한다(4-C).

    수집 경로와 저장본 경로가 **이 함수 하나**를 쓴다 — 두 곳에 두면
    한쪽만 고쳐져 결과가 달라진다.
    """
    if args.paste_panel_result is not None:
        # 3단계 결과 붙여넣기 (Phase 4-F). **여기서 파이프라인을 새로 만들지
        # 않는다** — Panel Result 로 옮겨 저장한 뒤 아래 같은 경로를 탄다.
        panel_file = _paste_to_canonical(report, args, settings, panel_file)
        if panel_file is None:
            return

    from . import panelimport
    outcome = panelimport.run(
        panel_file, report, settings,
        attach_result=args.import_panel_result is not None)
    report.source_status["패널 가져오기"] = outcome.status_line()
    for line in panelimport.report_lines(outcome):
        (log.warning if outcome.errors else log.info)("패널 가져오기: %s", line)

    if args.audit_panel_result is None:
        return
    from . import panelaudit
    result = panelaudit.audit(outcome, report)
    # 배지에 **무엇이 실제로 반영됐는지**를 함께 적는다 (Phase 4-F UI §4).
    # `부분 (14/14경기 가져옴)` 만 보면 사용자는 무엇을 얻었는지 모른다.
    # 가져오기 상태(§1-6 어휘)는 그대로 두고 구성만 덧붙인다.
    composition = panelaudit.composition_line(result)
    if composition:
        report.source_status["패널 가져오기"] = (
            f"{outcome.status_line()} · {composition}")
    report.source_status["패널 감사"] = (
        f"{result.status} (커버리지 {result.coverage_status})")
    for line in panelaudit.report_lines(result):
        log.info("감사 | %s", line)


def _write_report(report: Report, args, settings, verb: str) -> Path:
    """렌더해서 파일로 쓰고 경로를 돌려준다.

    수집 경로·패널 전용 경로·저장본 재렌더 경로가 **같은 renderer 와 같은
    출력 규칙**을 쓰게 하려고 한 곳에 뒀다 (§1-8). 예전에는 이 열 줄이 두
    곳에 복사돼 있었고, 세 번째 사본을 만들면 어느 하나만 고쳐져 세 경로가
    조용히 갈라진다. **동작은 그대로다** — 경로 규칙도 로그도 전과 같고
    `verb` 만 호출부가 정한다.
    """
    html = render_report(report, settings)
    out = args.output
    if out is None:
        name = settings.output.get("filename", "toto_{round}.html").format(
            round=report.round_id or "latest")
        out = settings.output_dir / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    log.info("리포트 %s → %s (%.1f KB)", verb, out,
             len(html.encode("utf-8")) / 1024)
    return out


def _rerender(args, settings) -> int:
    """저장된 회차 분석 결과(4-C)를 **현재 renderer 로** 다시 그린다.

    이 경로는 **수집하지 않는다.** `toto.sources` 를 import 하지도 않으므로
    베트맨·FotMob·피나클·후스코어드 어느 것도 호출될 수 없다 — 네 모듈은
    전부 수집 구간 안에서 지연 import 되고 여기는 그 구간에 닿지 않는다.

    **왜 따로 필요한가.** 저장본을 읽는 입구가 `_panel_only` 하나뿐이었고
    그건 패널 파일 인자에 묶여 있었다. 그래서 "자료는 그대로 두고 화면만
    지금 코드로 다시 그린다" 를 할 방법이 없었다 — 리포트 표현이 바뀔 때마다
    (4-G·5-D) 그것을 실물 회차에 확인하려면 재수집밖에 없었는데, 재수집은
    순위표·배당이 움직여(§1-1-7) **다른 자료가 된다.**

    분석값을 다시 만들지 않는다. `revive_report()` 가 되감은 그대로 렌더에
    넘긴다.
    """
    from . import artifact

    path = Path(args.rerender_artifact)
    report, why = artifact.load_path(path)
    if report is None:
        log.error("저장본을 읽지 못했습니다 — %s", why)
        return 1

    log.info("저장본으로 다시 렌더합니다 (수집하지 않습니다) — %s", path)
    log.info("  회차 %s · %d경기 · 생성 %s",
             report.round_id or "미상", len(report.matches),
             report.generated_at or "미상")
    out = _write_report(report, args, settings, "갱신")
    for key, value in report.source_status.items():
        log.info("  · %s: %s", key, value)
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def _panel_only(report: Report, args, settings, panel_file) -> int:
    """저장된 회차 분석 결과에 패널 파일만 얹는다. **수집하지 않는다.**"""
    try:
        _handle_panel_file(report, args, settings, panel_file)
    except Exception as exc:                            # noqa: BLE001
        log.error("패널 처리 실패: %s", exc)
        log.debug("패널 처리 traceback", exc_info=True)
        return 1

    if args.import_panel_result is None:
        # 붙여넣기는 통과하면 위에서 `import_panel_result` 를 채운다. 아직
        # 비어 있다면 변환·검증에서 막힌 것이다 (§12 — 파일도 만들지 않았다).
        if args.paste_panel_result is not None:
            return 1
        return 0                        # 검사·감사만 — 리포트를 다시 쓰지 않는다

    out = _write_report(report, args, settings, "갱신")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # 메뉴로 가기 전에 로그를 켠다 — 메뉴 루프가 예외를 잡아 traceback 을
    # 로그로 남기는데, 그때 핸들러가 없으면 아무 데도 남지 않는다.
    _setup_logging(args.verbose)

    if args.menu:
        from .menu import main as menu_main
        return menu_main()

    if _missing_required_deps():
        return 2

    settings = load_settings()

    # --serve 만 주면 이미 만들어 둔 리포트를 그대로 공유한다.
    # 폰에서 보려고 매번 다시 수집할 이유가 없다.
    if args.serve and not any((args.demo, args.round_id, args.matches_file)):
        from .publish import serve
        return serve(settings, port=args.serve_port)

    # ---- 0-a. 저장본만 다시 렌더 (Phase 5-E3a) ---------------------------
    # **수집 경로에 닿기 전에** 갈라진다. 아래 한 줄 밑부터가 수집이고,
    # 여기서 돌려주면 `sources` 는 import 조차 되지 않는다.
    if args.rerender_artifact is not None:
        return _rerender(args, settings)

    # ---- 0. 저장된 회차 분석 결과로 되돌아가기 (Phase 4-C) ---------------
    # 패널 파일만 주고 그 회차의 artifact 가 있으면 **수집을 다시 하지
    # 않는다.** 클로드 채팅 작업이 며칠 걸려도 ① 을 다시 돌릴 필요가 없다.
    # 다시 돌리면 순위표·배당이 그때와 달라져(§1-1-7) 경기자료 MD 를 만든
    # 분석과 패널 결과를 붙이는 분석이 서로 다른 것이 된다.
    panel_file = (args.import_panel_result or args.validate_panel_result
                  or args.audit_panel_result or args.paste_panel_result)
    if panel_file is not None and args.round_id and not args.demo:
        from . import artifact
        saved, why = artifact.load(args.round_id)
        if saved is not None:
            log.info("저장된 회차 분석 결과를 씁니다 (수집하지 않습니다) — "
                     "%s", artifact.path_for(args.round_id))
            return _panel_only(saved, args, settings, panel_file)
        log.info("%s — 회차를 수집해서 진행합니다.", why)

    resolver = TeamResolver()
    cache = Cache(enabled=not args.no_cache)
    report = Report(generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"))

    # ---- 1. 경기 목록 -----------------------------------------------------
    if args.demo:
        from .fixtures import build_demo_matches
        matches = build_demo_matches()
        report.round_id = "DEMO"
        report.source_status["데이터"] = "ok (샘플 · 실제 배당/성적 아님)"
        log.info("데모 모드 — 샘플 14경기로 리포트를 만듭니다.")
    else:
        from .sources import betman
        if args.matches_file:
            matches = betman.load_matches_file(args.matches_file, settings)
            report.round_id = args.round_id or "manual"
            report.source_status["경기목록"] = (
                f"ok (수동 {len(matches)}경기)" if matches else "실패 (파일 읽기)")
        else:
            matches, detected = betman.fetch_matches(
                settings, round_id=args.round_id, cache=cache)
            report.round_id = detected or (args.round_id or "")
            report.source_status["경기목록"] = (
                f"ok (베트맨 {len(matches)}경기)" if matches else "실패")

        if not matches:
            log.error("경기 목록이 비었습니다. --matches-file 로 직접 입력하거나 "
                      "--demo 로 동작을 확인해 보세요.")
            return 1

        expected = int(settings.betman.get("expected_matches", 14))
        if len(matches) != expected:
            report.warnings.append(
                f"경기 수가 {len(matches)}개입니다 (승무패는 {expected}경기). "
                f"목록을 확인하세요.")

        _resolve_teams(matches, resolver, report, settings)

        # ---- 2. FotMob (순위·홈원정 승점·폼·맞대결) -------------------------
        # 배당보다 먼저 돌린다. 순위표를 읽으면서 승강으로 바뀐 소속 리그를
        # 정정하는데, 그게 끝난 뒤라야 피나클이 옳은 리그 피드를 조회한다.
        # (2026 시즌에 대구·수원FC 가 K2 로, 인천·부천이 K1 로 옮겼는데 표가
        #  2025 상태여서 배당 조회가 전부 헛돌고 폴백으로 겨우 건졌다.)
        if args.skip_fotmob:
            report.source_status["순위·폼"] = "생략"
        else:
            from .sources import fotmob
            if args.skip_match_details:
                # 설정을 직접 바꾸지 않고 이번 실행에만 끈다
                settings.fotmob = dict(settings.fotmob, match_detail_matches=0)
            try:
                report.source_status["순위·폼"] = fotmob.enrich(
                    matches, settings, resolver, cache=cache,
                    # Phase 2 가 쓸 시즌 경기 색인. 새로 수집하지 않고
                    # 이미 받은 리그 응답을 옮겨 담는다.
                    season_out=report.season_matches)
            except Exception as exc:
                log.error("FotMob 수집 중 오류: %s", exc)
                report.source_status["순위·폼"] = "실패"

        # ---- 3. 배당률 ----------------------------------------------------
        if args.skip_odds:
            report.source_status["배당률"] = "생략"
        else:
            from .sources import pinnacle
            try:
                report.source_status["배당률"] = pinnacle.fetch_odds(
                    matches, settings, resolver, cache=cache)
            except Exception as exc:
                log.error("배당률 수집 중 오류: %s", exc)
                report.source_status["배당률"] = "실패"

        # ---- 4. 후스코어드 (강점/약점·스타일·팀 통계) ------------------------
        if args.skip_whoscored:
            report.source_status["상세데이터"] = "생략"
            for match in matches:
                if match.home_profile is None:
                    match.home_profile = TeamProfile(team=match.home,
                                                     league=match.league)
                if match.away_profile is None:
                    match.away_profile = TeamProfile(team=match.away,
                                                     league=match.league)
        else:
            from .sources import whoscored
            try:
                report.source_status["상세데이터"] = whoscored.enrich(
                    matches, settings, resolver, cache=cache)
            except Exception as exc:
                log.error("후스코어드 수집 중 오류: %s", exc)
                report.source_status["상세데이터"] = "실패"
                for match in matches:
                    if match.home_profile is None:
                        match.home_profile = TeamProfile(team=match.home,
                                                         league=match.league)
                    if match.away_profile is None:
                        match.away_profile = TeamProfile(team=match.away,
                                                         league=match.league)

        resolver.save_learned()
        resolver.save_leagues()

    # ---- 5. 분석 ----------------------------------------------------------
    report.matches = matches
    run_all(matches, settings, season_matches=report.season_matches)

    # ---- 5-B. 패널 (Phase 3-B) — **--panel 없이는 호출하지 않는다** --------
    # 유료 API 라 기본은 꺼져 있다. 분석 결과를 읽기만 하고 되먹이지 않는다.
    if args.panel:
        from . import panel
        report.source_status["패널"] = panel.attach_panels(
            matches, settings, cache=cache)

    # ---- 5-C. Panel Result JSON 가져오기 (Phase 4-B) ----------------------
    # 클로드 채팅에서 손으로 만든 결과를 되받는 자리다. **API 를 부르지
    # 않는다.** 오류가 하나라도 있으면 붙이지 않는다(부분 import 금지).
    if panel_file is not None:
        try:
            _handle_panel_file(report, args, settings, panel_file)
        except Exception as exc:                        # noqa: BLE001
            report.source_status["패널 가져오기"] = f"실패 ({exc})"
            log.warning("패널 가져오기 실패: %s", exc)
            log.debug("패널 가져오기 traceback", exc_info=True)

    # 회차 승산 (지침 §5)
    expected = int(settings.betman.get("expected_matches", 14))
    report.verdict = evaluate_round(matches, expected_total=expected)

    missing_odds = [m.no for m in matches if not m.probs]
    if missing_odds:
        report.warnings.append(
            "배당률을 가져오지 못한 경기: " + ", ".join(f"{n}번" for n in missing_odds))

    # ---- 6. 렌더링 --------------------------------------------------------
    out = _write_report(report, args, settings, "생성 완료")

    # 폰에서 보기 — 동기화 폴더에도 복사한다 (실패해도 실행은 성공으로 끝난다)
    from .publish import publish
    for dest in publish(out, settings):
        log.info("폰에서 보기용 사본 → %s", dest)
    for key, value in report.source_status.items():
        log.info("  · %s: %s", key, value)
    if report.warnings:
        log.warning("확인 필요 %d건 — 리포트 상단에 표시했습니다.", len(report.warnings))

    v = report.verdict
    if v is not None and v.n:
        log.info("회차 승산: E=%.2f σ=%.2f z=%+.2f P(>=11)=%.0f%% → %s",
                 v.expected, v.sigma, v.z, v.p_ge11 * 100, v.verdict_ko)
        if v.incomplete:
            log.warning("  배당 미수집 경기가 있어 %d경기만으로 계산했습니다.", v.n)
        log.info("회차로그 1줄 (지침 §8):")
        log.info("  %s", _log_line(report))

    # 경기자료 MD (Phase 4-A). 프로그램과 클로드 채팅 사이의 인터페이스라
    # 리포트가 나온 뒤 그대로 직렬화만 한다.
    if args.export_match_material:
        try:
            from . import match_material
            log.info("경기자료 MD: %s",
                     match_material.export(report, settings))
        except Exception as exc:                        # noqa: BLE001
            log.warning("경기자료 MD 실패: %s", exc)
            log.debug("경기자료 MD traceback", exc_info=True)

    # 패널 자료 내보내기. API 를 부르지 않으므로 리포트가 나온 뒤에 한다.
    # `--panel-export-all` 은 `--panel-export` 를 켠다 — 둘을 함께 적게
    # 하면 하나만 적고 아무것도 안 나오는 일이 생긴다.
    if args.panel_export or args.panel_export_all:
        try:
            from . import panelexport
            log.info("패널 자료 내보내기: %s", panelexport.export(
                report, include_without_evidence=args.panel_export_all,
                settings=settings))
        except Exception as exc:                        # noqa: BLE001
            log.warning("패널 자료 내보내기 실패: %s", exc)
            log.debug("패널 자료 내보내기 traceback", exc_info=True)

    # 회차 분석 결과 저장 (Phase 4-C). 나중에 패널 결과만 가져올 때 수집을
    # 다시 하지 않기 위해서다 — 다시 돌리면 순위표·배당이 그때와 달라진다.
    # 실패해도 리포트는 이미 나왔으므로 실행을 죽이지 않는다 (§1-6).
    try:
        from . import artifact
        log.info("회차 분석 저장: %s", artifact.save(report))
    except Exception as exc:                            # noqa: BLE001
        log.warning("회차 분석 저장 실패: %s", exc)
        log.debug("회차 분석 저장 traceback", exc_info=True)

    # 회차 기록 축적. 지나간 회차는 되돌릴 수 없으므로 매 실행이 남긴다.
    # 실패해도 리포트는 이미 나왔으므로 실행을 죽이지 않는다 (§1-6).
    try:
        from . import roundlog
        log.info("회차 기록: %s", roundlog.record(report))
    except Exception as exc:                            # noqa: BLE001
        log.warning("회차 기록 실패: %s", exc)
        log.debug("회차 기록 traceback", exc_info=True)

    if args.open:
        webbrowser.open(out.resolve().as_uri())
    if args.serve:
        from .publish import serve
        return serve(settings, port=args.serve_port, open_path=out.name)
    return 0


def _log_line(report: Report) -> str:
    """지침 §8 스키마의 회차로그 한 줄 (정산 전이라 결과 칸은 비운다)."""
    v = report.verdict
    sum_draw = sum(m.probs.draw for m in report.matches if m.probs is not None)
    return " | ".join([
        report.round_id or "", report.generated_at[:10],
        str(v.n), f"{v.expected:.2f}", f"{v.sigma:.2f}", f"{v.z:+.2f}",
        f"{v.p_ge11 * 100:.0f}%", v.verdict_ko,
        "", "", f"{sum_draw:.2f}", "", "", "", "",
        "정산 전",
    ])


if __name__ == "__main__":
    sys.exit(main())
