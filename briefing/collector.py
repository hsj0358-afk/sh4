"""수집 전용(collect-only) 로직.

Routine(구독 기반) 경로에서 사용한다:
  - 6개 신문 지면을 스크래핑하고 키워드로 후보를 추린 뒤, 후보 본문까지 담은
    '다이제스트 JSON'을 만든다. (LLM 호출/메일 발송 없음 — 비용 0)
  - 세션의 Claude 가 이 다이제스트를 읽어 요약·발송한다.

다이제스트 스키마:
  {
    "date": "2026-07-01",
    "all_articles": [{"press","title","url"}],                       # 전 기사 제목+링크(가벼움)
    "candidates":   [{"press","title","url","groups":[...],"body"}]  # 키워드 매칭 + 본문
  }
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from . import prefilter
from .scraper import Article
from .settings import Settings

log = logging.getLogger(__name__)


def _groups_by_key(articles: list[Article], settings: Settings) -> dict[str, list[str]]:
    """기사 key -> 매칭된 키워드 그룹 목록."""
    per_group = prefilter.keyword_candidates(articles, settings.keywords, settings.excludes)
    out: dict[str, list[str]] = {}
    for group, keys in per_group.items():
        for k in keys:
            out.setdefault(k, []).append(group)
    return out


def build_digest(date_human: str, articles: list[Article],
                 candidates: list[Article], groups: dict[str, list[str]],
                 settings: Settings) -> dict:
    limit = settings.body_char_limit
    return {
        "date": date_human,
        "all_articles": [
            {"press": a.press, "title": a.title, "url": a.url} for a in articles
        ],
        "candidates": [
            {
                "press": a.press,
                "title": a.title,
                "url": a.url,
                "groups": groups.get(a.key, []),
                "body": (a.body or "")[:limit],
            }
            for a in candidates
        ],
    }


def collect(settings: Settings, date_str: str, presses: dict,
            sample: bool = False) -> dict:
    """스크래핑 → 키워드 후보 → 후보 본문 수집 → 다이제스트 dict 반환."""
    date_human = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

    if sample:
        from .sample_data import SAMPLE_ARTICLES
        articles = list(SAMPLE_ARTICLES)
        log.info("샘플 모드: 기사 %d건", len(articles))
    else:
        from . import scraper
        log.info("네이버 지면 수집: %s (%s)", ", ".join(presses.values()), date_human)
        articles = scraper.scrape_all(presses, date=date_str)
        log.info("총 %d건 수집", len(articles))

    groups = _groups_by_key(articles, settings)
    cand_keys = set(prefilter.candidate_keys(articles, settings.keywords, settings.excludes))
    candidates = [a for a in articles if a.key in cand_keys]
    log.info("키워드 후보: %d건", len(candidates))

    if candidates and not sample:
        from . import scraper
        log.info("후보 %d건 본문 수집", len(candidates))
        scraper.fetch_bodies(candidates)

    return build_digest(date_human, articles, candidates, groups, settings)


def write_digest(path: Path, digest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8")
