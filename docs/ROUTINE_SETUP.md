# 무료·완전자동 브리핑 — Claude Code Routine 설정 가이드

PC를 켜지 않아도 **구독(Pro/Max) 한도 안에서 무료로** 매일 아침 브리핑을 받는 방법입니다.
별도 API 키(ANTHROPIC_API_KEY)나 Gmail 앱 비밀번호가 **필요 없습니다.**

## 동작 원리
1. 매일 예약된 시각에 **Claude Code Routine** 이 클라우드에서 실행됩니다(내 PC 불필요).
2. Routine 이 이 저장소를 클론해 **수집 스크립트**를 돌립니다
   → `python -m briefing --collect-only` 로 6개 신문 지면을 긁어 `digest.json` 생성.
3. **세션의 Claude 가** `digest.json` 을 읽고 [`docs/briefing_spec.md`](briefing_spec.md) 규격대로
   브리핑을 작성합니다. (요약 = 구독 사용량 차감, **추가 과금 없음**)
4. **Gmail 커넥터**로 브리핑 메일을 발송합니다.

> 과금: 문서상 "클라우드 VM 별도 요금 없음", 사용량은 구독 한도를 차감(+일일 Routine 실행 캡).
> 하루 1회 소규모라 부담이 거의 없습니다.

---

## 1) 사전 준비
- **Claude Pro / Max** 구독 + **Claude Code on the web** 사용 가능(리서치 프리뷰).
- **Gmail 커넥터** 연결: claude.ai → Settings → Connectors 에서 Gmail 연결.
- 이 저장소(`hsj0358-afk/sh4`)에 GitHub 접근 권한 연결.

## 2) 환경(네트워크) 설정 — 네이버 허용이 핵심
Routine 생성 화면에서 환경을 **Custom 네트워크**로 만듭니다(기본 Trusted 는 네이버를 막아 403).

- **Network access**: `Custom`
- **Allowed domains** (한 줄에 하나):
  ```
  media.naver.com
  n.news.naver.com
  ```
  (수집이 막히면 `*.naver.com` 을 추가)
- **"Also include default list of common package managers"** 체크
  (pip 로 의존성 설치가 되도록 — pypi 등 기본 허용 목록 유지)
- **Setup script**:
  ```bash
  pip install -r requirements.txt
  ```
  > Chromium 은 클라우드 이미지에 사전 설치되어 Playwright 가 자동으로 사용합니다.
  > 만약 첫 실행에서 브라우저를 못 찾으면 setup script 에
  > `python -m playwright install chromium` 을 추가하고, 필요 시 Playwright 다운로드 도메인을
  > Allowed domains 에 추가하세요.

## 3) Routine 생성
[claude.ai/code/routines](https://claude.ai/code/routines) → **New routine** (또는 CLI `/schedule`).

- **Repository**: `hsj0358-afk/sh4`
- **Environment**: 위에서 만든 Custom 환경
- **Connectors**: **Gmail 만 남기고** 나머지는 제거
- **Schedule**: `Daily`, 한국시간 **오전 7시** (로컬존 입력 → 자동 변환)
- **Permissions**: 브랜치 푸시 불필요(이 Routine 은 커밋하지 않음)
- **Model**: Opus 계열 권장(요약 품질)

## 4) 프롬프트 (아래 전문을 그대로 붙여넣기)
`<받는사람@example.com>` 만 실제 수신자로 바꾸세요(여러 명이면 쉼표로).

```
너는 KT HRD 부서의 '아침 신문 브리핑' 담당이다. 오늘자 브리핑을 만들어 이메일로 보내라.

절차:
1) 저장소 루트에서 실행: `python -m briefing --collect-only --out digest.json`
   - 6개 신문(조선·중앙·동아·매일경제·한국경제·전자신문) 네이버 지면을 수집한다.
   - 실행이 실패하거나 "전체 0건"이면, 원인(네이버 차단/구조 변경 등)을 담은 짧은 안내 메일을
     아래 6)의 방식으로 보내고 종료한다.
2) `digest.json` 을 읽는다.
   - `candidates`(본문 포함)를 1차 분석 대상으로 삼는다.
   - `all_articles`(제목+링크)도 훑어, 키워드가 놓쳤지만 관련 있는 기사를 추가로 고른다.
   - 그렇게 고른 기사의 본문이 필요하면 `python -m briefing --fetch-body <url>` 로 가져온다.
3) 저장소의 `docs/briefing_spec.md` 를 읽고, 그 규격을 **그대로** 따라 브리핑을 작성한다.
   (카테고리 순서: KT → 경쟁사·타사(SKT·LG U+ 폭넓게) → AI·AX → HRD(상세) → HRM → ESG →
    기업문화 → 노사상생. KT&G·KTX 는 KT 로 분류하지 말 것. 각 항목에 요약·부서장 언급 포인트·
    중요도·링크. HRD 는 3~5문장 상세. 맨 위에 '오늘의 핵심' 3~5불릿.)
4) 브리핑을 읽기 좋은 한국어 HTML 이메일로 정리한다.
5) Gmail 커넥터로 다음과 같이 발송한다:
   - 받는 사람: <받는사람@example.com>
   - 제목: [아침 신문 브리핑] {오늘 날짜 YYYY-MM-DD}
   - 본문: 위 HTML 브리핑
6) 저장소에는 아무것도 커밋/푸시하지 마라. 실행과 메일 발송만 한다.
```

## 5) 테스트 & 운영
- 생성 후 **Run now** 로 즉시 1회 실행 → 세션 트랜스크립트에서 확인:
  - (a) 네이버 수집 성공(로그에 `403 host_not_allowed` 없음, "전체 N건"),
  - (b) 브리핑 생성,
  - (c) Gmail 발송 완료.
- 문제 대처:
  - `403 host_not_allowed` → Allowed domains 에 네이버 도메인 보강(`*.naver.com`).
  - 브라우저 못 찾음 → setup script 에 `python -m playwright install chromium` 추가.
  - 수집은 되는데 0건 → 네이버 지면 DOM 변경 가능성. `briefing/scraper.py` 셀렉터 점검.
- 정상 확인 후에는 매일 예약에 맡기면 됩니다.

---

## 한계 / 참고
- **네이버가 클라우드 IP를 드물게 차단**할 수 있습니다. 그럴 경우 로컬 cron + 유료 API 경로
  (README 참고)로 대체하세요.
- Routine 은 **일일 실행 캡**과 구독 사용량 한도를 공유합니다(하루 1회는 문제 없음).
- 이 경로는 **API 키가 필요 없습니다.** 유료 API 경로(GitHub Actions)는 백업으로 남겨 둡니다.
