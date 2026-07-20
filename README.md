# HR·HRD 주간 브리핑 에이전트

매주 **월요일 아침 8시(KST)**, HR(People)과 HRD의 최신 **트렌드와 사례**를
자동으로 조사해 **강의자료 슬라이드 + 이메일**로 전달하는 에이전트입니다.

## 무엇을 하나

매주 월요일, 영구 스케줄 트리거가 **새 세션을 자동 생성**하고 다음을 수행합니다.

1. 이 저장소를 클론하고 `briefing/PROMPT.md`(지시서)를 읽는다
2. `WebSearch`/`WebFetch`로 국내·글로벌 **4개 주제**를 **최근 1주일 소식 위주**로 리서치한다
   - HR(피플) 트렌드 / HRD·L&D / HR 테크 & AI / 기업 사례 & 정책
   - 근거자료(통계·리서치)는 기간·범위 제한 없이 활용
3. **HR전문가를 화자로**, 각 항목을 경영진의 날카로운 반론과의 **디베이트를 거친
   인사이트·기대효과**로 정제한 상세 리포트를 작성한다 (HR 조직 내부 강의용)
4. **바로 발표 가능한 강의자료(슬라이드) 형식**의 HTML 아티팩트를 발행한다
5. `hsj0358@gmail.com`으로 TL;DR + 아티팩트 링크 **이메일을 자동 발송**한다
   (발송 수단이 없으면 초안 생성으로 폴백 — 아래 '이메일 자동 발송' 참고)
6. 상세 원문을 `briefing/archive/YYYY-MM-DD.md`로 **커밋·푸시**한다

## 구성

| 파일 | 역할 |
|------|------|
| `briefing/PROMPT.md` | 에이전트의 두뇌 — 리서치 절차·작성 규칙·산출물 정의 |
| `briefing/TEMPLATE.md` | 상세 리포트 출력 형식 |
| `briefing/SOURCES.md` | 국내/글로벌 참고 소스 및 검색 키워드 |
| `briefing/archive/` | 매주 생성된 브리핑이 쌓이는 곳 |

## 브리핑 내용을 바꾸려면

`briefing/PROMPT.md`(무엇을·어떻게 조사할지)와 `briefing/TEMPLATE.md`(출력 형식)를
수정하면 됩니다. 새 세션이 매주 저장소를 다시 클론하므로 변경이 자동 반영됩니다.

## 스케줄 관리

스케줄은 Claude Code Remote의 **Routine(트리거)** 으로 운영됩니다.

- 트리거 이름: **HR·HRD 주간 브리핑**
- 트리거 ID: `trig_015aKG2p2jgiwSsp7xgaL3bM`
- 일정: 매주 월요일 08:00 (KST) — cron `0 23 * * 0` (UTC 기준 일요일 23:00)
- 방식: 매주 새 세션 자동 생성(`create_new_session_on_fire`) + 완료 시 푸시 알림

변경/중지 방법 (Claude에게 요청):
- 시간 변경: "브리핑 트리거 시간을 바꿔줘" → `update_trigger`
- 잠시 중지: "브리핑 트리거를 꺼줘" → `update_trigger(enabled=false)`
- 완전 삭제: "브리핑 트리거를 삭제해줘" → `delete_trigger`
- 지금 한 번 실행: "이번 주 브리핑을 지금 만들어줘" → `fire_trigger`

## 이메일 자동 발송

목표는 **완전 자동 발송**입니다. 매주 실행 시 아래 순서로 시도합니다.

1. **SMTP 자동 발송(기본 경로)**: 환경변수 `GMAIL_SMTP_USER` / `GMAIL_SMTP_APP_PASSWORD`가
   있으면 `smtp.gmail.com:465`(SSL)로 발송 — [Gmail 앱 비밀번호](https://myaccount.google.com/apppasswords) 방식
2. Gmail 도구가 세션에 있으면 활용 (트리거로 뜬 새 세션에는 Gmail 커넥터가
   전달되지 않으므로 보통 이 경로는 없음)
3. 둘 다 없으면 이메일 본문을 `briefing/outbox/`에 저장·커밋하고 알림에 명시

> **완전 자동 발송을 켜려면 (1회 설정 필요)**: Google 계정에서
> [앱 비밀번호](https://myaccount.google.com/apppasswords)를 발급받아,
> Claude Code 환경(env_019nQgJyBEGhYrQnmjtmJNpH) 설정의 환경변수에
> `GMAIL_SMTP_USER=hsj0358@gmail.com`, `GMAIL_SMTP_APP_PASSWORD=<앱 비밀번호>`를
> 추가하세요. 다음 실행부터 자동 발송됩니다. 설정 전까지는 3번 폴백으로 동작합니다.

## 참고

- 트리거는 이 계정/환경에 종속됩니다. 환경이 삭제되면 트리거를 다시 생성해야 합니다.
- 브리핑 콘텐츠는 이 브랜치(`claude/hr-weekly-briefing-agent-bqrmm8`)에서 운영됩니다.
