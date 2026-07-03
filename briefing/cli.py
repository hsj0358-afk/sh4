"""CLI 오케스트레이션.

흐름:
  1) 6개 신문 지면 기사 목록 수집(Playwright)         [--sample 이면 샘플 사용]
  2) 키워드 프리필터로 후보 추출
  3) Claude 로 제목 선별(의미 기반) → 후보와 합집합     [--no-llm 이면 생략]
  4) 후보 기사 본문 수집
  5) Claude 로 카테고리별 브리핑 생성                   [--no-llm 이면 샘플 브리핑]
  6) 마크다운/HTML 렌더링 → reports/ 저장
  7) Gmail 발송                                        [--no-email 이면 생략]

사용 예:
  python -m briefing                         # 오늘자, 분석 후 메일 발송(유료 API 경로)
  python -m briefing --date 20260630         # 특정 날짜
  python -m briefing --no-email --save-dir reports   # 메일 없이 파일만
  python -m briefing --sample --no-llm --no-email     # 완전 오프라인 미리보기

수집 전용(Routine/구독 경로 — LLM/메일 없이 다이제스트만 생성):
  python -m briefing --collect-only --out digest.json
  python -m briefing --fetch-body https://n.news.naver.com/article/009/1001  # 단일 본문 출력
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

from . import prefilter, renderer
from .settings import ROOT, load_settings

log = logging.getLogger("briefing")


def _parse_args(argv=None):
    p = argparse.ArgumentParser(prog="briefing", description="부서장 아침 신문 브리핑 자동화")
    p.add_argument("--date", help="대상 날짜 YYYYMMDD (기본: 오늘)")
    p.add_argument("--presses", help="언론사 oid 부분집합(쉼표구분, 예: 009,030). 기본: 전체")
    p.add_argument("--no-email", action="store_true", help="메일 발송 생략(파일만 생성)")
    p.add_argument("--no-llm", action="store_true", help="Claude 분석 생략(샘플 브리핑 사용)")
    p.add_argument("--sample", action="store_true", help="네이버 스크래핑 대신 샘플 기사 사용(오프라인)")
    p.add_argument("--save-dir", default="reports", help="리포트 저장 폴더(기본: reports)")
    p.add_argument("--collect-only", action="store_true",
                   help="수집+키워드필터+본문까지만 하고 다이제스트 JSON 저장(LLM/메일 없음)")
    p.add_argument("--out", help="--collect-only 다이제스트 출력 경로(기본: digest_YYYYMMDD.json)")
    p.add_argument("--fetch-body", metavar="URL",
                   help="단일 기사 본문을 정제해 stdout 출력 후 종료")
    p.add_argument("-v", "--verbose", action="store_true", help="상세 로그")
    return p.parse_args(argv)


def _selected_presses(settings, presses_arg):
    presses = settings.presses
    if presses_arg:
        wanted = {x.strip() for x in presses_arg.split(",")}
        presses = {k: v for k, v in presses.items() if k in wanted}
    return presses


def run(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = load_settings()
    date_str = args.date or dt.date.today().strftime("%Y%m%d")
    date_human = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

    # 단일 본문 조회 (세션 Claude 가 추가 본문이 필요할 때 사용) -----------------
    if args.fetch_body:
        from . import scraper
        m = scraper.ARTICLE_HREF_RE.search(args.fetch_body)
        if not m:
            log.error("기사 URL 형식이 아닙니다: %s", args.fetch_body)
            return 2
        art = scraper.Article(oid=m.group(1), aid=m.group(2), press="", title="",
                              url=args.fetch_body)
        scraper.fetch_article_body(art)
        print(art.title)
        print(art.url)
        print()
        print(art.body or "(본문을 가져오지 못했습니다)")
        return 0

    # 수집 전용(Routine/구독 경로): 다이제스트 JSON 생성 후 종료 --------------------
    if args.collect_only:
        from . import collector
        presses = _selected_presses(settings, args.presses)
        digest = collector.collect(settings, date_str, presses, sample=args.sample)
        out_path = Path(args.out) if args.out else (ROOT / f"digest_{date_str}.json")
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        collector.write_digest(out_path, digest)
        n_all = len(digest["all_articles"])
        n_cand = len(digest["candidates"])
        if n_all == 0:
            log.error("수집된 기사가 없습니다. (네이버 접근 차단/구조 변경 가능성)")
        log.info("다이제스트 저장: %s (전체 %d건 / 후보 %d건)", out_path, n_all, n_cand)
        print(f"완료: 전체 {n_all}건, 후보 {n_cand}건 → {out_path}")
        return 0 if n_all else 3

    # 필수값 점검 (조기 실패)
    missing = settings.validate_for_run(
        need_llm=not args.no_llm,
        need_email=not args.no_email,
    )
    if missing:
        log.error("필수 설정 누락: %s  (.env / GitHub Secrets 확인)", ", ".join(missing))
        # 완전 오프라인 미리보기(--sample --no-llm)는 키 없이도 진행
        if not (args.sample and args.no_llm):
            return 2

    # 1) 기사 목록 ---------------------------------------------------------
    if args.sample:
        from .sample_data import SAMPLE_ARTICLES
        articles = list(SAMPLE_ARTICLES)
        log.info("샘플 모드: 기사 %d건", len(articles))
    else:
        presses = _selected_presses(settings, args.presses)
        from . import scraper
        log.info("네이버 지면 수집 시작: %s (%s)", ", ".join(presses.values()), date_human)
        articles = scraper.scrape_all(presses, date=date_str)
        log.info("총 %d건 수집", len(articles))
        if not articles:
            log.error("수집된 기사가 없습니다. (네이버 접근 차단/구조 변경 가능성)")
            return 3

    # 2~3) 후보 선별 -------------------------------------------------------
    cand_keys = prefilter.candidate_keys(articles, settings.keywords, settings.excludes)
    log.info("키워드 후보: %d건", len(cand_keys))

    if not (args.no_llm or args.sample):
        from . import analyzer
        sel_idx = analyzer.select_relevant(articles, settings)
        for i in sel_idx:
            cand_keys.add(articles[i].key)
        log.info("키워드+Claude 합집합 후보: %d건", len(cand_keys))

    candidates = [a for a in articles if a.key in cand_keys] or articles

    # 4) 본문 수집 ---------------------------------------------------------
    if not args.sample:
        from . import scraper
        log.info("후보 %d건 본문 수집", len(candidates))
        scraper.fetch_bodies(candidates)

    # 5) 브리핑 생성 -------------------------------------------------------
    if args.no_llm:
        from .sample_data import stub_briefing
        briefing = stub_briefing(date_human)
        log.info("--no-llm: 샘플 브리핑 사용")
    else:
        from . import analyzer
        log.info("Claude 브리핑 생성 (%s)", settings.anthropic_model)
        briefing = analyzer.build_briefing(candidates, settings, date_human)

    n_items = renderer.count_items(briefing)
    log.info("브리핑 항목 %d개 생성", n_items)

    # 6) 렌더링/저장 -------------------------------------------------------
    md = renderer.to_markdown(briefing)
    html = renderer.to_html(briefing)
    save_dir = Path(args.save_dir)
    if not save_dir.is_absolute():
        save_dir = ROOT / save_dir
    save_dir.mkdir(parents=True, exist_ok=True)
    md_path = save_dir / f"briefing_{date_str}.md"
    html_path = save_dir / f"briefing_{date_str}.html"
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    log.info("저장: %s , %s", md_path, html_path)

    # 7) 메일 발송 ---------------------------------------------------------
    if args.no_email:
        log.info("--no-email: 메일 발송 생략")
    else:
        from . import mailer
        subject = f"[아침 신문 브리핑] {date_human} · 항목 {n_items}건"
        mailer.send_briefing(settings, subject, md, html)

    print(f"완료: {n_items}개 항목, 리포트 → {md_path}")
    return 0


def main():
    sys.exit(run())


if __name__ == "__main__":
    main()
