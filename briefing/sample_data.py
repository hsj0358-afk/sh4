"""오프라인/미리보기용 샘플 데이터.

네이버 접속이나 Claude API 없이도 렌더링·메일 형식을 점검할 수 있도록
가짜 기사와 가짜 브리핑(JSON)을 제공한다. (--sample / --no-llm)
"""
from __future__ import annotations

from .scraper import Article

SAMPLE_ARTICLES = [
    Article("009", "1001", "매일경제", "KT, 그룹사 통합 AI 인재 1000명 양성 나선다",
            "https://n.news.naver.com/article/009/1001",
            body="KT가 그룹 차원의 AI 인재 양성 프로그램을 가동한다. ..."),
    Article("030", "2002", "전자신문", "SK텔레콤, 사내 리스킬링 플랫폼 전사 확대",
            "https://n.news.naver.com/article/030/2002",
            body="SK텔레콤이 임직원 재교육(리스킬링) 플랫폼을 전 직원으로 확대한다. ..."),
    Article("015", "3003", "한국경제", "주요 대기업 임단협 시즌…노사 상생 모델 주목",
            "https://n.news.naver.com/article/015/3003",
            body="올해 임단협에서 노사 상생 모델이 화두로 떠올랐다. ..."),
]

# Claude 없이 미리보기할 때 쓰는 가짜 브리핑 결과
STUB_BRIEFING = {
    "headline_summary": [
        "KT, 그룹 통합 AI 인재 1000명 양성 발표 — HRD 직접 관련, 최우선 보고 사안",
        "SK텔레콤·주요 대기업의 리스킬링/노사상생 움직임 등 타사 동향 포착",
        "(이 화면은 샘플입니다. 실제 실행 시 Claude 가 6개 신문 기사를 분석합니다.)",
    ],
    "categories": {
        "KT": [{
            "headline": "KT, 그룹사 통합 AI 인재 1000명 양성 나선다",
            "press": "매일경제", "importance": "high",
            "summary": "KT가 그룹 차원에서 AI 인재 1000명 양성 프로그램을 가동한다.",
            "talking_point": "우리 부서 AI 교육 로드맵과 연계 가능 — 부서장 보고 1순위",
            "url": "https://n.news.naver.com/article/009/1001", "detail": "",
        }],
        "HRD": [{
            "headline": "KT, 그룹사 통합 AI 인재 1000명 양성 나선다",
            "press": "매일경제", "importance": "high",
            "summary": "그룹 통합 AI 인재 양성 프로그램 가동.",
            "talking_point": "사내 AI 교육 과정 신설/확대 검토 필요",
            "url": "https://n.news.naver.com/article/009/1001",
            "detail": "KT는 계열사 공통의 AI 역량 체계를 도입해 직무별 맞춤 교육을 제공할 계획이다. "
                      "리스킬링·업스킬링을 동시에 추진하며 사내대학과 연계한다. "
                      "우리 부서의 연간 교육계획에 AI 기초/심화 트랙을 반영할지 검토가 필요하다. "
                      "타사 대비 진도와 예산 규모를 벤치마킹할 포인트다.",
        }],
        "HRM": [],
        "ESG": [],
        "CULTURE": [],
        "LABOR": [{
            "headline": "주요 대기업 임단협 시즌…노사 상생 모델 주목",
            "press": "한국경제", "importance": "med",
            "summary": "올해 임단협에서 노사 상생 모델이 화두.",
            "talking_point": "동종업계 임단협 타결 동향 모니터링 필요",
            "url": "https://n.news.naver.com/article/015/3003", "detail": "",
        }],
        "COMPETITOR": [{
            "headline": "SK텔레콤, 사내 리스킬링 플랫폼 전사 확대",
            "press": "전자신문", "importance": "med",
            "summary": "SKT가 임직원 재교육 플랫폼을 전 직원으로 확대.",
            "talking_point": "경쟁사 리스킬링 투자 확대 — 우리 수준과 비교 보고",
            "url": "https://n.news.naver.com/article/030/2002", "detail": "",
        }],
    },
}


def stub_briefing(date_str: str) -> dict:
    import copy
    data = copy.deepcopy(STUB_BRIEFING)
    data["date"] = date_str
    return data
