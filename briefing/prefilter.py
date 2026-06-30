"""키워드 기반 프리필터.

Claude 가 의미 기반으로 선별하기 전, 핵심 키워드(KT/HRD 등)가 들어간 기사는
반드시 후보에 포함시켜 누락을 방지한다.
"""
from __future__ import annotations

from .scraper import Article


def _hit(text: str, keywords: list[str]) -> bool:
    if not text:
        return False
    low = text.lower()
    for kw in keywords:
        if kw.lower() in low:
            return True
    return False


def keyword_candidates(articles: list[Article], keywords: dict) -> dict[str, list[str]]:
    """제목 기준으로 키워드 그룹별 매칭된 기사 key 목록을 반환.

    반환 예: {"kt": ["009/123", ...], "hrd": [...], ...}
    """
    flat = {g: kws for g, kws in keywords.items()}
    result: dict[str, list[str]] = {g: [] for g in flat}
    for a in articles:
        text = a.title  # 목록 단계에서는 제목만 (본문은 선별 후 수집)
        for g, kws in flat.items():
            if _hit(text, kws):
                result[g].append(a.key)
    return result


def candidate_keys(articles: list[Article], keywords: dict) -> set[str]:
    """키워드에 하나라도 걸린 기사 key 집합."""
    keys: set[str] = set()
    for group in keyword_candidates(articles, keywords).values():
        keys.update(group)
    return keys
