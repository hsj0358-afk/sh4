# 축구토토 승무패 분석기 사용법

베트맨 축구토토 **승무패** 14경기를 자동으로 가져와, 경기별 상세 분석 데이터를
**HTML 리포트 한 파일**로 만들어 준다. 승/무/패 추천은 하지 않는다 —
판단에 필요한 데이터만 정리해서 보여주고, 선택은 사용자가 한다.

---

## 1. 설치

```bash
pip install -r requirements-toto.txt
playwright install chromium          # 베트맨·후스코어드는 실제 브라우저가 필요
```

### Windows

가상환경을 만들었다면 **활성화하지 말고 그 안의 파이썬을 직접 부르는 편이 안전하다**
(PowerShell 실행 정책 때문에 `Activate.ps1` 이 막히는 경우가 잦다).

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-toto.txt
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m toto --demo
```

`run_toto.bat` 은 `.venv` 가 있으면 알아서 그 파이썬을 쓴다.

## 2. 실행

### 바탕화면 아이콘으로 (Windows, 권장)

한 번만:

```
create_shortcut.bat  더블클릭
```

바탕화면에 **"축구토토 분석"** 바로가기가 생긴다. 이후로는 그 아이콘을
더블클릭하면 메뉴가 뜬다.

```
  [1] 전체 수집 (배당률 + 후스코어드 상세)
  [2] 빠른 수집 (배당률·순위 위주)
  [3] 회차 지정해서 수집
  [4] 데모 보기 (네트워크 불필요)
  [5] 캐시 비우고 새로 수집
  [6] 후스코어드 수집 실패 진단
  [0] 종료
```

번호를 고르면 실행되고, 끝나면 리포트가 브라우저로 열린다.
창은 결과를 읽을 수 있도록 바로 닫히지 않는다.

> 메뉴 문구는 배치 파일이 아니라 파이썬(`toto/menu.py`)이 출력한다.
> cmd 는 콘솔 코드페이지(한국어 윈도우는 cp949)로 배치 파일을 읽어서
> 한글을 넣으면 깨지거나 명령이 잘린다. `*.bat` 은 전부 ASCII + CRLF 로
> 유지하고(`.gitattributes` 로 고정), 한글은 파이썬 쪽에서만 출력한다.

### 명령줄로

```bash
python -m toto                       # 이번 회차 자동 탐지 → 풀 수집 → 리포트
python -m toto --menu                # 위 메뉴를 터미널에서 띄우기
./run_toto.sh                        # macOS/Linux (TZ=Asia/Seoul 고정)
run_toto.bat                         # Windows (시스템 시각 사용)
```

리포트는 `reports/toto_<회차>.html` 로 생성된다. 브라우저로 열면 끝 —
외부 CDN·폰트·스크립트를 전혀 쓰지 않아서 파일 하나만 전달해도 그대로 열린다.

### 주요 옵션

| 옵션 | 설명 |
|---|---|
| `--demo` | **네트워크 없이** 샘플 데이터로 리포트 생성. 설치 확인용 |
| `--round 260032` | 회차 직접 지정 |
| `--matches-file examples/matches.yaml` | 베트맨 크롤링 대신 경기 목록을 직접 입력 |
| `--skip-whoscored` | 후스코어드 생략 (배당률·순위 위주, 1~2분) |
| `--skip-odds` | 피나클 배당률 생략 |
| `--no-cache` | 캐시 무시하고 새로 수집 |
| `--open` | 생성 후 브라우저로 바로 열기 |
| `-o 경로.html` | 출력 파일 지정 |
| `-v` | 디버그 로그 |

**처음 쓴다면 이 순서를 권한다.**

```bash
python -m toto --demo --open          # 1) 렌더링이 정상인지 먼저 확인
python -m toto --skip-whoscored       # 2) 배당률 수집까지 확인 (빠름)
python -m toto                        # 3) 풀 수집 (10~20분)
```

---

## 3. 리포트에 담기는 것

**상단 — 14경기 한눈에 보기**
경기별 내재확률 미니 바 + 승/무/패 %. 카드를 누르면 상세로 이동한다.

**경기별 상세 카드**

| 블록 | 내용 | 시각화 |
|---|---|---|
| 순위 요약 | 순위·승점·전적·골득실·휴식일 | 텍스트 |
| 배당률 | 승/무/패 배당, **마진 제거 내재확률**, 아시안 핸디캡, O/U 2.5 | 100% 스택 바 + 표 |
| 리그 내 위치 | 득점·실점·xG·점유율·패스성공률·수비액션·공중볼·홈/원정 승점 등 **리그 백분위** | 레이더 (두 팀 겹침, 50% = 리그 중간) |
| 지표 직접 비교 | 경기당 승점/득점/실점/점유율/슈팅/패스/수비/평점 | 다이버징(마주보기) 바 |
| 최근 5경기 폼 | 결과·스코어·상대·홈원정, 획득 승점 | W/D/L 칩 + 누적 승점 스파크라인 |
| 상대전적 | 최근 최대 10경기, 승/무/패 카운트 | 스택 바 + 표 |
| 전략적 상성 | 두 팀 **Strengths / Weaknesses / Style of Play**, 그리고 **홈 강점 ↔ 원정 약점 교차 매칭** | 대조 카드 |
| 결장 예상 | 부상·징계 | 목록 |

### 색 규칙

리포트 전체에서 **홈 = 파랑, 원정 = 주황**으로 고정된다(어느 차트를 봐도 같은 팀은 같은 색).
무승부는 중립 회색 — 승↔무↔패는 "홈 우세 ← 중립 → 원정 우세" 극성 축이기 때문이다.
두 색 조합은 색각이상 시뮬레이션에서 분리도 검증을 통과했고, 라이트/다크 모드 모두 대응한다.

### 내재확률이란

북메이커 배당의 역수 합은 항상 1보다 크고, 그 초과분이 마진(vig)이다.
리포트의 확률은 **마진을 제거해 합이 정확히 100%가 되도록 정규화한 값**이라
그대로 "시장이 보는 확률"로 읽으면 된다. 마진 값도 함께 표시한다.
피나클은 마진이 얇아(보통 2~4%) 이 값의 신뢰도가 높은 편이다.

---

## 4. 데이터 출처

| 항목 | 출처 | 방식 |
|---|---|---|
| 14경기 목록 | 베트맨 (`gmId=G011`) | Playwright |
| 승/무/패 배당, 핸디캡, O/U | Pinnacle Arcadia **guest API** | REST (웹앱 내장 공개 키) |
| 순위표·팀 통계 | WhoScored 리그 페이지 | Playwright (리그당 1회) |
| 강점/약점/스타일·폼·결장자 | WhoScored 팀 페이지 | Playwright (팀당 1회) |
| 상대전적 | WhoScored 경기 프리뷰 | Playwright |

수집 부하를 줄이려고 **리그 페이지 1회 로드로 그 리그 모든 팀의 통계**를 한꺼번에 읽는다.
모든 응답은 `cache/<날짜>/` 에 저장되므로 같은 날 재실행은 훨씬 빠르다.

---

## 5. 문제 해결

### 후스코어드가 계속 차단당할 때

후스코어드는 Incapsula 봇 차단을 쓴다. 다음 순서로 해결한다.

1. `config_toto.yaml` 에서 `whoscored.headless: false` 로 바꾸고 **한 번 실행**한다.
   창이 뜬 상태로 통과하면 그 쿠키가 `cache/browser/` 에 저장되고,
   이후에는 `headless: true` 로 되돌려도 대체로 통과한다.
2. `whoscored.delay_sec` 를 6~8초로 늘린다 (기본 4초).
3. 그래도 안 되면 `--skip-whoscored` 로 배당률·순위 중심 리포트를 만든다.

### 베트맨 경기 목록을 못 가져올 때

베트맨은 페이지 구조가 바뀔 수 있다. 목록 수집이 실패하면
`cache/<날짜>/betman/FAILED_round_*.html` 에 원본이 저장된다.

당장 리포트가 필요하면 **수동 입력**을 쓰면 된다 — 이후 분석은 완전히 동일하게 돈다.

```bash
cp examples/matches.yaml my_round.yaml
# my_round.yaml 에 이번 회차 14경기를 적는다
python -m toto --matches-file my_round.yaml
```

### 팀명이 매칭되지 않을 때

리포트 상단에 `'○○○' 팀명을 매칭하지 못했습니다` 경고가 뜬다.
`data/teams.yaml` 에 한 줄만 추가하면 된다.

```yaml
Brighton:
  ko: [브라이튼, 브라이턴]        # ← 여기에 베트맨 표기를 추가
  en: [Brighton & Hove Albion]
```

자동으로 알아낸 별칭은 `data/teams.learned.yaml` 에 쌓이므로,
같은 팀 때문에 두 번 고생할 일은 없다.

### 승격/강등으로 팀이 바뀌었을 때

`data/teams.yaml` 에 새 팀을 추가하고, 필요하면 `config_toto.yaml` 의
`leagues.<리그>.whoscored` 경로(시즌이 바뀌면 토너먼트 ID가 바뀔 수 있다)를 확인한다.

### 승무패에 다른 리그가 나왔을 때

`config_toto.yaml` 의 `leagues:` 에 항목 하나만 추가하면 된다.

```yaml
  eredivisie:
    ko: "에레디비시"
    aliases: ["에레디비시", "네덜란드"]
    pinnacle_url: "https://www.pinnacle.com/en/soccer/netherlands-eredivisie/matchups/#all"
    pinnacle_name: "Netherlands - Eredivisie"
    whoscored: "/Regions/155/Tournaments/13/Netherlands-Eredivisie"
```

---

## 6. 구조

```
toto/
  cli.py          실행 흐름 (목록 → 배당 → 상세 → 분석 → 렌더)
  models.py       Match / TeamProfile / Odds / H2H 등 데이터 구조
  settings.py     config_toto.yaml + .env 로더
  normalize.py    팀명 한글↔영문 매칭
  analyze.py      마진 제거, 리그 백분위, 상성 교차 매칭
  charts.py       인라인 SVG (레이더 / 스택바 / 폼칩 / 다이버징바)
  render.py       자체 완결 HTML 조립
  cache.py        날짜별 JSON 캐시
  fixtures.py     --demo 샘플 데이터
  sources/        betman.py · pinnacle.py · whoscored.py
data/teams.yaml   팀명 별칭 테이블
config_toto.yaml  리그 URL, 레이더 항목, 수집 옵션
```

소스 하나가 실패해도 프로그램은 멈추지 않는다. 실패한 항목만
리포트에 `데이터 없음` 으로 표시되고 나머지는 정상 출력된다.

> 이 도구는 참고용 데이터 정리 도구다. 베팅 결과를 보장하지 않으며,
> 승/무/패 선택은 전적으로 사용자 판단에 달려 있다.
