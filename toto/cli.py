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
from .analyze import run_all
from .cache import Cache
from .models import Report, TeamProfile
from .normalize import TeamResolver
from .render import render_report
from .settings import load_settings

log = logging.getLogger("toto")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


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
    p.add_argument("--skip-odds", action="store_true",
                   help="피나클 배당률 수집 생략")
    p.add_argument("--no-cache", action="store_true",
                   help="캐시를 무시하고 새로 수집")
    p.add_argument("--open", action="store_true",
                   help="생성 후 기본 브라우저로 열기")
    p.add_argument("-v", "--verbose", action="store_true", help="디버그 로그")
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)

    settings = load_settings()
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

        # ---- 2. 배당률 ----------------------------------------------------
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

        # ---- 3. 후스코어드 ------------------------------------------------
        if args.skip_whoscored:
            report.source_status["상세데이터"] = "생략"
            for match in matches:
                match.home_profile = TeamProfile(team=match.home, league=match.league)
                match.away_profile = TeamProfile(team=match.away, league=match.league)
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

    # ---- 4. 분석 ----------------------------------------------------------
    report.matches = matches
    run_all(matches, settings)

    missing_odds = [m.no for m in matches if not m.probs]
    if missing_odds:
        report.warnings.append(
            "배당률을 가져오지 못한 경기: " + ", ".join(f"{n}번" for n in missing_odds))

    # ---- 5. 렌더링 --------------------------------------------------------
    html = render_report(report, settings)

    out = args.output
    if out is None:
        name = settings.output.get("filename", "toto_{round}.html").format(
            round=report.round_id or "latest")
        out = settings.output_dir / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    log.info("리포트 생성 완료 → %s (%.1f KB)", out, len(html.encode("utf-8")) / 1024)
    for key, value in report.source_status.items():
        log.info("  · %s: %s", key, value)
    if report.warnings:
        log.warning("확인 필요 %d건 — 리포트 상단에 표시했습니다.", len(report.warnings))

    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
