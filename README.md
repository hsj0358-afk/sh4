# 📰 부서장 아침 신문 브리핑 자동화

부서장이 매일 읽는 **6개 종이신문**(조선일보·중앙일보·동아일보·매일경제·한국경제·전자신문)을
네이버뉴스 **지면보기**로 수집하고, **Claude**가 아래 관점으로 분석해
**매일 아침 이메일로 브리핑**을 보냅니다.

- **KT 관련** 꼭 알아야 할 기사 (계열사·박윤영 대표 포함, `KT&G`·`KTX` 오탐 제외)
- **경쟁사·타사 동향** — 직접 경쟁사 **SKT·LG U+** 는 HR뿐 아니라 AI/AX·사업 전략까지 폭넓게,
  그 외 주요 대기업은 인사/조직/노사/ESG/문화 관점
- **AI·AX 트렌드** — KT 비전 *AX Platform Company* 와 연결한 AI 동향
- **HRD**(인재개발) — *가장 상세히*
- **HRM**(인사·채용·평가보상 등)
- **ESG** / **기업문화** / **노사상생**

각 항목에는 **요약**, 부서장이 회의·대화에서 꺼낼 만한 **💬 언급 포인트**,
**중요도**(🔴/🟡/⚪), **기사 링크**가 붙습니다.

---

## 실행 방식 두 가지

| 방식 | 비용 | PC | 요약 품질 | 설정 |
|---|---|---|---|---|
| **A. Routine (구독 포함, 권장)** | **추가 과금 없음** (Claude Pro/Max 구독 사용량) | 불필요 | ◎ (세션 Claude) | [`docs/ROUTINE_SETUP.md`](docs/ROUTINE_SETUP.md) |
| **B. GitHub Actions + Claude API** | 종량 과금(월 1~2만 원대) | 불필요 | ◎ | 아래 |

- **A(권장)**: 매일 클라우드 **Routine** 이 수집 스크립트를 돌리고, **세션의 Claude 가 요약**해
  **Gmail 커넥터**로 발송합니다. **API 키·앱 비밀번호 불필요**, 구독 한도 안에서 무료.
  → 설정은 [`docs/ROUTINE_SETUP.md`](docs/ROUTINE_SETUP.md) 참고.
- **B**: 아래 GitHub Actions 방식(유료 API). Routine 을 못 쓰는 경우의 대안입니다.

---

## 🚀 방식 B — GitHub Actions + Claude API (유료)

PC를 매일 켤 필요 없이 GitHub 서버에서 매일 아침 자동 실행됩니다.

1. **이 저장소를 GitHub에 둡니다.** (이미 있음)
2. **Secrets 등록** — 저장소 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`
   에서 아래 값들을 추가:

   | 이름 | 설명 |
   |---|---|
   | `ANTHROPIC_API_KEY` | Claude API 키 (https://console.anthropic.com) |
   | `GMAIL_USER` | 보내는 Gmail 주소 |
   | `GMAIL_APP_PASSWORD` | Gmail **앱 비밀번호** 16자리 (아래 참고) |
   | `BRIEFING_TO` | 받는 사람(쉼표로 여러 명) |
   | `ANTHROPIC_MODEL` | (선택) 기본 `claude-opus-4-8` |
   | `BRIEFING_FROM_NAME` | (선택) 보내는 사람 표시 이름 |

3. 끝입니다. 매일 **오전 7시(KST)** 에 자동 실행됩니다.
   - 워크플로: [`.github/workflows/briefing.yml`](.github/workflows/briefing.yml)
   - 시간 변경: 워크플로의 `cron` 값 수정 (UTC 기준, `KST - 9 = UTC`)
   - **지금 바로 테스트:** 저장소 `Actions` 탭 → `아침 신문 브리핑` → `Run workflow` 버튼

> ⚠️ **참고:** GitHub Actions는 클라우드 IP에서 실행되므로, 드물게 네이버가
> 접근을 제한할 수 있습니다. 그럴 경우 아래 **로컬/서버 cron** 방식을 사용하세요.

---

## 🖥️ 대안: 로컬 PC / 상시 서버에서 cron 실행

PC나 서버가 항상 켜져 있다면 이 방식이 네이버 차단 위험이 가장 적습니다.

```bash
# 1) 의존성 설치
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium      # 헤드리스 크롬 설치

# 2) 환경설정
cp .env.example .env        # .env 를 열어 키/메일 정보 입력

# 3) 한번 실행해보기 (메일 없이 파일만)
python -m briefing --no-email

# 4) cron 등록 (crontab.example 참고)
crontab -e
# 0 7 * * * /path/to/sh4/run.sh >> /path/to/sh4/reports/cron.log 2>&1
```

---

## 🔑 Gmail 앱 비밀번호 만들기

일반 Gmail 비밀번호로는 SMTP 발송이 안 됩니다. **앱 비밀번호**가 필요합니다.

1. 구글 계정 **2단계 인증** 켜기
2. https://myaccount.google.com/apppasswords 접속 → 앱 비밀번호 생성
3. 생성된 **16자리**를 `GMAIL_APP_PASSWORD` (또는 `.env`)에 입력 (띄어쓰기 제거)

---

## 🧪 오프라인 미리보기 (네이버/Claude 없이 형식만 확인)

```bash
# 샘플 기사 + 샘플 브리핑으로 reports/ 에 .md / .html 생성 (네트워크·API 불필요)
python -m briefing --sample --no-llm --no-email
open reports/briefing_*.html     # 메일에 들어갈 형태 미리보기
```

---

## ⚙️ 사용법 / 옵션

```bash
python -m briefing                       # 오늘자 → 분석 → 메일 발송
python -m briefing --date 20260630       # 특정 날짜 지면
python -m briefing --no-email            # 메일 없이 reports/ 에 파일만
python -m briefing --presses 009,030     # 일부 신문만 (매경, 전자신문)
python -m briefing --sample --no-llm --no-email   # 완전 오프라인 미리보기
python -m briefing -v                     # 상세 로그
```

| 옵션 | 설명 |
|---|---|
| `--date YYYYMMDD` | 대상 지면 날짜 (기본: 오늘, KST) |
| `--presses` | 언론사 oid 부분집합 (쉼표구분) |
| `--no-email` | 메일 발송 생략, `reports/` 에 파일만 |
| `--no-llm` | Claude 분석 생략(샘플 브리핑) — 형식 테스트용 |
| `--sample` | 네이버 스크래핑 대신 샘플 기사 사용(오프라인) |
| `--save-dir` | 리포트 저장 폴더 (기본 `reports/`) |
| `--collect-only` | (방식 A용) 수집+키워드필터+본문까지만 → 다이제스트 JSON 저장, LLM/메일 없음 |
| `--out PATH` | `--collect-only` 출력 경로 (기본 `digest_YYYYMMDD.json`) |
| `--fetch-body URL` | 단일 기사 본문을 정제해 출력 (세션 Claude 가 추가 본문 확보용) |

> **방식 A(Routine)** 는 `--collect-only` 로 만든 다이제스트를 세션 Claude 가 읽어 요약합니다.
> 분석 규격은 [`docs/briefing_spec.md`](docs/briefing_spec.md) 에 정리되어 있습니다.

---

## 🧩 동작 구조

**방식 A (Routine, 구독):**
```
Routine(매일, 클라우드)
   → python -m briefing --collect-only   (scraper + prefilter + collector → digest.json)
   → 세션 Claude 가 digest.json 읽고 docs/briefing_spec.md 규격대로 요약
   → Gmail 커넥터로 발송
```

**방식 B (GitHub Actions, 유료 API):**

```
6개 신문 지면 목록 수집      briefing/scraper.py   (Playwright)
   ↓
키워드 프리필터 (KT/HRD…)    briefing/prefilter.py
   ↓
Claude 제목 선별(의미기반)    briefing/analyzer.py  → 후보와 합집합
   ↓
후보 기사 본문 수집           briefing/scraper.py   (requests + BeautifulSoup)
   ↓
Claude 카테고리별 브리핑      briefing/analyzer.py  (HRD는 상세)
   ↓
마크다운/HTML 렌더링          briefing/renderer.py  → reports/ 저장
   ↓
Gmail 발송                    briefing/mailer.py
```

오케스트레이션: [`briefing/cli.py`](briefing/cli.py)

---

## 🛠️ 설정 커스터마이징

- **언론사 / 키워드 / 경쟁사 / 오탐 목록**: [`config.yaml`](config.yaml) 에서 자유롭게 수정
  - `keywords.kt` : KT 본사·계열사·대표(박윤영) — 걸리면 무조건 후보 포함
  - `keywords.competitor` : 직접 경쟁사(SKT·LG U+) — 하드 포함
  - `keywords.ai` : AI/AX 트렌드 키워드 (양이 많으면 줄이세요)
  - `competitors` : 넓은 비교군(삼성·네이버 등) — HR/조직 관점만, Claude 가 의미로 선별
  - `excludes` : `KT&G`·`KTX` 등 'KT' 부분일치 오탐 차단어
- **분석 관점(프롬프트)**: `briefing/analyzer.py` 의 `SELECT_SYSTEM` / `BRIEF_SYSTEM`
- **메일 디자인**: `briefing/renderer.py` 의 `to_html`
- **비용 절감**: `ANTHROPIC_MODEL` 을 `claude-sonnet-4-6` 등으로,
  `config.yaml` 의 `body_char_limit` 조정

---

## ❗ 트러블슈팅

| 증상 | 원인/해결 |
|---|---|
| `수집된 기사가 없습니다` | 네이버 접근 제한 또는 지면 구조 변경. 로컬 cron 방식으로 전환하거나 `-v` 로그 확인 |
| 메일 인증 실패 | 일반 비밀번호 대신 **앱 비밀번호** 사용했는지 확인 |
| `ANTHROPIC_API_KEY 누락` | `.env` 또는 GitHub Secrets 확인 |
| Playwright 오류 | `python -m playwright install chromium` 재실행 |

> 비밀값(`.env`)은 절대 커밋하지 마세요. `.gitignore` 로 제외되어 있습니다.
