"""Claude 기반 분석기.

1) select_relevant : (제목만) 6개 신문 전체 제목을 보고 관심 주제와 관련된 기사를 선별
2) build_briefing  : 선별된 기사(본문 포함)로 카테고리별 브리핑 JSON 생성

anthropic SDK 는 함수 내부에서 지연 import.
"""
from __future__ import annotations

import json
import logging
import re

from .scraper import Article
from .settings import Settings

log = logging.getLogger(__name__)

# 카테고리 키와 화면 표기 (렌더러와 공유)
CATEGORY_ORDER = ["KT", "HRD", "HRM", "ESG", "CULTURE", "LABOR", "COMPETITOR"]
CATEGORY_TITLES = {
    "KT": "KT 관련 (꼭 알아야 할)",
    "HRD": "HRD (상세)",
    "HRM": "HRM",
    "ESG": "ESG",
    "CULTURE": "기업문화",
    "LABOR": "노사상생",
    "COMPETITOR": "타사 동향",
}


def _client(settings: Settings):
    import anthropic
    return anthropic.Anthropic(api_key=settings.anthropic_api_key or None)


def _extract_text(msg) -> str:
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _parse_json(text: str):
    """코드펜스/잡텍스트가 섞여도 JSON 부분만 안전하게 파싱."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        # 본문에서 첫 { 또는 [ 부터 마지막 } 또는 ] 까지 추출 시도
        for opener, closer in (("{", "}"), ("[", "]")):
            i, j = text.find(opener), text.rfind(closer)
            if i != -1 and j != -1 and j > i:
                try:
                    return json.loads(text[i:j + 1])
                except Exception:
                    continue
        raise


# --------------------------------------------------------------------------
# 1단계: 제목 선별
# --------------------------------------------------------------------------
SELECT_SYSTEM = """\
너는 대기업 HRD(인재개발) 부서의 분석 담당자다. 부서장은 매일 아침 6개 종이신문
(조선일보·중앙일보·동아일보·매일경제·한국경제·전자신문)을 읽는다.
아래에 오늘 지면 기사 '제목' 목록이 주어진다. 이 중 부서장에게 보고할 가치가 있는
기사의 번호만 골라라.

선별 기준(하나라도 해당하면 선택):
1. KT 및 그 계열사/경영진 관련 (KT, KT클라우드, BC카드, 케이뱅크, 스카이라이프 등)
2. HRD(인재개발/교육/리스킬링/리더십), HRM(채용·인사·평가보상·임금·정년 등)
3. ESG(지속가능경영·지배구조·사회공헌·탄소중립)
4. 기업문화/조직문화/일하는 방식
5. 노사관계/노사상생/노조/임단협
6. 위 2~5번 관점에서 의미 있는 '타사(경쟁사·주요 대기업) 동향'
   (단순 실적·주가·제품 기사는 제외, 인사/조직/노사/ESG/문화 움직임만)

제목만으로 애매하면 일단 포함시켜라(본문은 다음 단계에서 확인한다).
반드시 아래 JSON 형식의 정수 배열만 출력하라. 설명/문장 금지.
출력 예: [0, 5, 12, 33]
"""

SELECT_USER = "오늘 지면 기사 제목 목록:\n{listing}\n\n관련 기사 번호 배열(JSON)만 출력:"


def select_relevant(articles: list[Article], settings: Settings) -> set[int]:
    """제목만 보고 관련 기사 인덱스 집합을 반환."""
    if not articles:
        return set()
    subset = articles[: settings.max_titles_for_select]
    listing = "\n".join(f"{i}\t[{a.press}]\t{a.title}" for i, a in enumerate(subset))

    client = _client(settings)
    msg = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=3000,
        system=SELECT_SYSTEM,
        messages=[{"role": "user", "content": SELECT_USER.format(listing=listing)}],
    )
    try:
        idxs = _parse_json(_extract_text(msg))
        result = {int(i) for i in idxs if isinstance(i, (int, float)) and 0 <= int(i) < len(subset)}
        log.info("Claude 제목 선별: %d건", len(result))
        return result
    except Exception as e:
        log.error("제목 선별 결과 파싱 실패: %s", e)
        return set()


# --------------------------------------------------------------------------
# 2단계: 브리핑 생성
# --------------------------------------------------------------------------
BRIEF_SYSTEM = """\
너는 대기업 HRD(인재개발) 부서의 분석 담당자다. 부서장은 매일 아침 6개 종이신문
(조선일보·중앙일보·동아일보·매일경제·한국경제·전자신문)을 읽으며, 부서원이 그
내용 중 '알아야 할 것'과 '회의/대화에서 언급할 만한 것'을 아침 브리핑으로 받기를 원한다.

아래 기사들(제목+본문)을 분석해 카테고리별 브리핑을 만들어라.

[카테고리 키]
- "KT": KT 및 계열사/경영진 관련 — 부서장이 반드시 알아야 할 것
- "HRD": 인재개발/교육/리스킬링/리더십개발/사내대학 등 — **가장 중요**, 가장 상세히
- "HRM": 채용/인사/평가보상/임금/정년/근로시간/유연근무 등
- "ESG": 지속가능경영/지배구조/사회공헌/탄소중립
- "CULTURE": 기업문화/조직문화/일하는 방식
- "LABOR": 노사관계/노사상생/노조/임단협
- "COMPETITOR": 위 관점에서 의미 있는 타사(경쟁사·주요 대기업) 동향

[작성 규칙]
- 주어진 기사 내용에만 근거하라. 사실을 지어내지 말 것. url 은 기사에 주어진 값만 사용.
- 관련 없는 기사는 버려라. 카테고리에 해당 기사가 없으면 items 를 빈 배열로 둬라.
- 한 기사는 가장 적합한 한 카테고리에만 넣어라.
- HRD 카테고리의 각 항목은 "detail"(3~5문장, 배경·시사점 포함)을 반드시 채워라.
  다른 카테고리는 detail 을 비워도 된다(간결한 summary 위주).
- "talking_point" 에는 부서장이 회의/대화에서 언급하거나 질문할 만한 핵심 한 줄을 담아라.
- importance 는 "high"/"med"/"low" 중 하나(부서장 입장 중요도).
- headline_summary 에는 오늘 브리핑의 핵심을 3~5개 불릿(문자열 배열)로 요약하라.

반드시 아래 JSON '객체' 하나만 출력하라. 코드펜스/설명 금지.
{
  "headline_summary": ["...", "..."],
  "categories": {
    "KT":   [{"headline":"", "press":"", "summary":"", "talking_point":"", "importance":"high|med|low", "url":"", "detail":""}],
    "HRD":  [...],
    "HRM":  [...],
    "ESG":  [...],
    "CULTURE": [...],
    "LABOR": [...],
    "COMPETITOR": [...]
  }
}
"""

BRIEF_USER = "날짜: {date}\n\n분석 대상 기사:\n{articles}\n\n위 형식의 JSON 객체만 출력:"


def build_briefing(articles: list[Article], settings: Settings, date_str: str) -> dict:
    """선별·본문수집된 기사로 브리핑 JSON(dict)을 생성."""
    blocks = []
    for i, a in enumerate(articles):
        body = (a.body or "")[: settings.body_char_limit]
        blocks.append(
            f"### 기사 {i}\n신문: {a.press}\n제목: {a.title}\nURL: {a.url}\n본문:\n{body}\n"
        )
    content = "\n".join(blocks) if blocks else "(분석 대상 기사 없음)"

    client = _client(settings)
    msg = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=8000,
        system=BRIEF_SYSTEM,
        messages=[{"role": "user",
                   "content": BRIEF_USER.format(date=date_str, articles=content)}],
    )
    data = _parse_json(_extract_text(msg))
    if not isinstance(data, dict):
        data = {"headline_summary": [], "categories": {}}
    data.setdefault("headline_summary", [])
    data.setdefault("categories", {})
    data["date"] = date_str
    return data
