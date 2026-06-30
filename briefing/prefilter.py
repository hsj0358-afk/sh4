"""키워드 기반 프리필터.

Claude 가 의미 기반으로 선별하기 전, 핵심 키워드(KT/HRD 등)가 들어간 기사는
반드시 후보에 포함시켜 누락을 방지한다.

오탐 방지: 'KT' 가 'KT&G'(담배)·'KTX'(철도) 등에 부분일치하지 않도록,
매칭 전에 excludes 목록을 텍스트에서 제거한다.
"""
from __future__ import annotations

import re

from .scraper import Article


def _strip_excludes(text: str, excludes: list[str]) -> str:
    if not text or not excludes:
        return text or ""
    for ex in excludes:
        if ex:
            text = re.sub(re.escape(ex), " ", text, flags=re.IGNORECASE)
    return text


def _hit(text: str, keywords: list[str]) -> bool:
    if not text:
        return False
    low = text.lower()
    for kw in keywords:
        if kw and kw.lower() in low:
            return True
    return False


def keyword_candidates(articles: list[Article], keywords: dict,
                       excludes: list[str] | None = None) -> dict[str, list[str]]:
    """제목 기준으로 키워드 그룹별 매칭된 기사 key 목록을 반환.

    반환 예: {"kt": ["009/123", ...], "hrd": [...], ...}
    """
    excludes = excludes or []
    result: dict[str, list[str]] = {g: [] for g in keywords}
    for a in articles:
        text = _strip_excludes(a.title, excludes)  # 목록 단계에선 제목만
        for g, kws in keywords.items():
            if _hit(text, kws):
                result[g].append(a.key)
    return result


def candidate_keys(articles: list[Article], keywords: dict,
                   excludes: list[str] | None = None) -> set[str]:
    """키워드에 하나라도 걸린 기사 key 집합."""
    keys: set[str] = set()
    for group in keyword_candidates(articles, keywords, excludes).values():
        keys.update(group)
    return keys
