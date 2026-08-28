# CLAUDE.md

이 저장소에서 작업할 때 지켜야 할 규칙. 아래 "확인된 프로젝트 규칙"은
**실제 파일과 코드를 읽어 확인한 사실**만 적었고, 근거 파일·줄을 함께 남겼다.
확인하지 못한 것은 맨 아래 "추가 확인이 필요한 규칙"으로 분리했다.

---

## 0. 저장소에 두 프로젝트가 함께 있다

| 디렉터리 | 프로젝트 | 이번 작업에서 |
|---|---|---|
| `toto/` | **축구토토 승무패 분석** (6,005줄, 21파일) | **작업 대상** |
| `briefing/` | 신문 브리핑 자동화 (1,091줄) | **수정하지 않는다** |

두 프로젝트는 설정·의존성·실행 경로가 완전히 분리돼 있다.

- 설정: `config_toto.yaml` (toto) / `config.yaml` (briefing)
- 의존성: `requirements-toto.txt` / `requirements.txt`
- 실행: `run_toto.sh`·`run_toto.bat`·`toto_menu.bat` / `run.sh`
- 자동화: `.github/workflows/briefing.yml` 은 **briefing 전용**이다

`briefing/` 및 `config.yaml`, `requirements.txt`, `run.sh`,
`docs/ROUTINE_SETUP.md`, `docs/briefing_spec.md`, `crontab.example`,
`.github/workflows/briefing.yml` 은 건드리지 않는다.

`toto/` 의 기존 기능과 구조는 최대한 보존한다. 리팩터링이 필요하면 동작을
바꾸지 않는 범위로 한정하고, 무엇이 왜 바뀌는지 먼저 말한다.

---

## 1. 확인된 프로젝트 규칙

### 1-1. 데이터 소스와 우선순위 — 임의로 바꾸지 않는다

`toto/cli.py` 의 수집 순서가 곧 우선순위다.

```
toto/cli.py:171   # ---- 2. FotMob (순위·홈원정 승점·폼·맞대결)
toto/cli.py:187   # ---- 3. 배당률 (Pinnacle)
toto/cli.py:199   # ---- 4. 후스코어드 (강점/약점·스타일·팀 통계)
```

**FotMob → Pinnacle → WhoScored.** 이 순서에는 이유가 있다.

- FotMob 이 순위표를 읽으면서 **승강으로 바뀐 소속 리그를 정정**한다
  (`toto/sources/fotmob.py` `enrich()`, `toto/normalize.py` `set_league()`).
  그게 끝난 뒤라야 Pinnacle 이 옳은 리그 피드를 조회한다.
- WhoScored 는 봇 차단이 잦아 마지막에 둔다. 실패해도 앞 두 소스의 결과가
  남는다.

**뒤에 오는 소스는 앞 소스가 비워 둔 칸만 채운다.** 덮어쓰지 않는다.

```python
# toto/models.py:243  fill_stats(dst, src, overwrite=False)
#   "나중에 붙는 소스가 앞서 채운 값을 None 으로 덮어쓰면 안 되므로,
#    기본은 '비어 있을 때만' 채운다."
```

호출부: `toto/sources/fotmob.py` `enrich()`, `toto/sources/whoscored.py`
`enrich()`. `overwrite=True` 는 현재 어디에서도 쓰지 않는다.

소스별 담당:

| 소스 | 담당 |
|---|---|
| 베트맨 | 회차 14경기 목록 (`toto/sources/betman.py`) |
| **FotMob** | 순위표(홈/원정 분리)·xG·시즌 팀통계 23종·최근 폼·맞대결 |
| **FotMob 경기 상세** | npxG·xGOT·오픈플레이/세트피스 xG·슈팅/피슈팅·박스 안팎 |
| **Pinnacle** | 승/무/패 배당률 (Arcadia guest API) |
| WhoScored | 강점/약점·플레이 스타일 (정성 데이터) |

### 1-1-2. 시즌 통계와 경기 상세는 표본이 다르다 — 섞지 않는다

FotMob 안에 **경로가 두 개** 있고, 각각 주는 것이 다르다. Phase 0 에서
저장본을 뜯어 확인한 사실이다.

| 경로 | 요청 | 주는 것 | 표본 |
|---|---|---|---|
| `api/data/leagues?id=` + `stats.teams[]` 피드 | 리그당 1 + 지표당 1 | 결정적 기회·점유율·세트피스 득점·PK·카드·크로스·롱볼 … | **시즌 전체** |
| `api/data/matchDetails?matchId=` | 최근 경기당 1 | **npxG·xGOT·오픈플레이/세트피스 xG·총슈팅·피슈팅·유효슈팅·박스 안팎** | **최근 N경기** |

아래 지표들은 **시즌 통계 29종 카탈로그에 없다.** 경기 상세에만 있다.
시즌 피드에서 찾으려다 시간을 버리지 않도록 적어 둔다.

  · npxG / npxGA          · xGOT / 피xGOT
  · 오픈플레이 xG · 세트피스 xG
  · 총슈팅 / 피슈팅        · 박스 안 슈팅 / 박스 밖 슈팅

**두 표본을 한 표에 섞지 않는다.** 이름 규칙과 리포트 블록으로 분리한다.

- 필드 이름 끝의 `_recent` = 최근 N경기 **합계**. `_recent_pg` 속성이
  경기당 값이다 (`toto/models.py` `_per_recent()`).
- **지표마다 표본이 다를 수 있다.** 어떤 경기에는 npxG 가 없고 슈팅만 있다.
  그래서 `recent_counts` 가 `{필드: 그 지표가 실제로 있던 경기 수}` 를 들고
  다니고, `_per_recent()` 는 그 수로 나눈다. `recent_matches`(받아 온 경기
  수)로 일괄해서 나누면 **빠진 경기를 0 으로 친 것과 같아져 값이 조용히
  낮아진다** — Phase 1-B 검증에서 실제로 이 상태였다(3경기치 합계를 6으로
  나눠 절반이 됐다). 표본이 모자란 지표는 실행 로그에 이름과 경기 수를 적는다.
- 이름 끝의 `_pg` = 그 소스가 이미 경기당으로 주는 값. 접미사가 없으면 누계다.
  누계를 비교표에 그대로 넣지 않는다 — 팀마다 소화 경기수가 달라 왜곡된다
  (`_per_played()` 로 나눈다).
- 리포트도 블록을 나눈다. 시즌 지표는 `compare_metrics`, 최근 N경기는
  `recent_metrics` → `toto/render.py` `_recent_block()`. 이 블록은 표본
  크기를 함께 적고, 두 팀의 표본이 다르면 그렇다고 밝힌다.

수집량 조절: `config_toto.yaml` 의 `fotmob.match_detail_matches` (기본 6).
`0` 이거나 `--skip-match-details` 면 이 단계를 통째로 건너뛰고, 값이 없으니
블록도 통째로 빠진다. 같은 경기를 두 팀이 공유하므로 캐시로 요청을 반씩 줄인다.

**경기 스탯은 '전체(All)' 표만 읽는다.** 경로가
`content.stats.Periods.All` 인데 **Periods 는 복수형**이라 전·후반 표가 함께
온다. `_walk` 는 스택(LIFO)이라 순회 순서가 문서 순서와 다르고 `setdefault`
가 먼저 만난 것을 채택하므로, 전체를 훑으면 하프 값이 이겨 지표가 조용히
절반이 된다. 260048 실행의 `npxG 대조 최대 차이 3.03` 이 이 증상이었다.
`_all_period()` 가 'All' 을 먼저 골라내고 그 안에서만 지표를 찾는다.
기간 구분이 없는 응답에서는 전체를 훑는 기존 동작으로 돌아간다.

**npxG 는 PK 를 상수로 빼서 만들지 않는다.** 슛맵의 `situation ==
"Penalty"` 분류를 쓴다 (`_shot_totals()`). 다만 값 자체는 경기 스탯의
`expected_goals_non_penalty` 를 그대로 쓰고, 슛맵 합산은 **대조용**으로만
남겨 차이를 로그에 적는다 — 둘을 억지로 맞추지 않는다.

회귀 테스트: `python tests/test_match_details.py` (36개).

### 1-1-1. 리그 ID 를 이름만으로 정하지 않는다

이름 매칭은 두 소스 모두에서 엉뚱한 리그를 골랐다. 실측 기록이다.

| 소스 | 사고 | 원인 |
|---|---|---|
| FotMob | EPL 요청에 `id=441` 채택, 순위표 해석 전체 실패 | `allLeagues` 에 **`Premier League` 라는 이름의 리그가 16개**. 첫 후보에서 `break` |
| Pinnacle | EPL 요청이 `England - Premier League 2 U21` 에 매칭, 배당 0/14 | 정답이 오답의 **접두사**인데 부분일치를 씀 |

지금 규칙 (`toto/sources/fotmob.py` `resolve_league_id()`,
`toto/sources/pinnacle.py` `league_id()`):

- **설정의 `fotmob_id` 가 최우선.** 실행으로 확인된 값만 적는다
  (`epl: 47`, `seriea: 55`, `kleague1: 9080`, `kleague2: 9116`).
- 탐색할 때는 **동명 후보를 전부 모은다.** 하나만 보고 멈추지 않는다.
- 후보가 여럿이면 `country` 로 좁히고, 그래도 남으면 **순위표의 팀 구성**
  으로 가린다 — `data/teams.yaml` 이 그 리그 소속으로 아는 팀이 몇 개
  들어 있는지 센다. `allLeagues` 내부 구조는 아직 실물로 확인하지 못해서
  경로를 단정하지 않고, 상위 dict 의 문자열 필드를 힌트로 쓴다.
- **가리지 못하면 임의로 고르지 않고 실패한다.** 엉뚱한 리그의 데이터를
  쓰는 것보다 비어 있는 편이 낫다.
- Pinnacle 은 **정규화 완전일치 → `pinnacle_aliases` → 실패** 뿐이다.
  부분일치를 다시 넣지 않는다.

회귀 테스트: `python tests/test_league_matching.py` (15개).

### 1-2. 배당률 로직 — 지침 v3.2, 등가(가산) 마진 제거

`toto/predict.py:1` — *"보정 확률 · argmax 픽 · 회차 승산
(Calibrated Single-Pick Engine v3.2)"*

```python
# toto/predict.py:91  additive_probabilities()  — 지침 §3-(b), 필수 방법
q_i = 1 / 배당_i
R   = Σ q_i
m   = (R − 1) / 3          # 옵션당 균등 절대 마진
p_i = q_i − m              # 자동으로 Σ p_i = 1
```

**비례식 `q_i / R` 로 바꾸지 않는다.** 코드 주석에 이유가 적혀 있다 —
피나클은 모든 옵션에 거의 동일한 *절대* 마진을 부과하므로 비례식은 정배를
과소·역배를 과대 추정한 채로 남긴다(Favorite-Longshot 편향).

고정 상수 (`toto/predict.py:20-26`):

| 상수 | 값 | 근거 |
|---|---|---|
| `GATE_THRESHOLD` | 0.15 | 지침 §5-(e) — 미만이면 회차를 건너뛴다 |
| `TOSS_UP_GAP` | 0.04 | 지침 §7 — 상위 두 픽이 이 안이면 [백중세] |
| `CLAMP_FLOOR` | 0.005 | |
| `VETO_MAX` | 0.05 | ±5%p 상한 |

지침 조항을 참조하는 곳: `toto/analyze.py:22`(§3-b), `:34`(§5),
`toto/cli.py:232`(§5), `:269`·`:281`(§8), `toto/models.py:379`(§5).

### 1-3. 추천 픽을 표시하지 않는다

리포트 하단에 명시돼 있다.

```
toto/render.py:536
  "이 리포트는 판단에 필요한 데이터를 모아 보여줄 뿐,
   승/무/패를 추천하지 않습니다."
```

확률과 근거 데이터만 제공하고 **최종 승무패 선택은 사용자가 한다.**
`toto/ticket.py` 의 단통표는 사용자가 픽을 직접 눌러 바꾸면 회차 승산
(E·σ·z·P(≥11))을 다시 계산해 보여주는 도구이지, 픽을 제안하는 기능이 아니다.

### 1-4. 구조를 추측하지 말고 실물을 먼저 확인한다

이 규칙은 실패 경험에서 나왔다. 응답 구조를 추측해 파서를 쓰다가 여러 번
왕복했고, 점검 도구를 만들어 실물을 본 뒤에야 한 번에 맞았다.

**새 데이터 소스를 추가하거나 기존 소스의 구조를 다룰 때는 실제 응답을
먼저 본다.**

| 도구 | 용도 |
|---|---|
| `tools/probe_sources.py` | 소스에 접속해 **구조만** 관찰. 파싱하지 않는다 |
| `tools/probe_sources.py --analyze` | 접속 없이 저장된 응답을 다시 분석 |
| `tools/diagnose_whoscored.py` | 저장된 실패 원본(`FAILED_*.html`)에서 원인을 짚는다 |

메뉴에서도 부를 수 있다 (`toto/menu.py`): `[6]` 진단 · `[7]` 점검 ·
`[8]` 저장본 재분석. 원본 응답은 `cache/probe/` 와
`cache/<날짜>/<소스>/FAILED_*.html` 에 남는다.

파서를 쓸 때는 **경로를 박지 말고 모양으로 찾는다.** FotMob 순위표가
`table[0].data.table.all` 이지만 스플릿 리그에서는 `tables[i].table.all`
이라, 경로를 고정하면 스플릿이 시작되는 날 조용히 빈 값이 된다
(`toto/sources/fotmob.py` `_standings_blocks()`).

파싱 로직을 고쳤으면 **캐시 버전을 올린다.** 안 그러면 같은 날 재실행이
옛 캐시를 읽어 수정이 반영되지 않는다 — 실제로 이것 때문에 두 번 헛돌았다.

```
toto/sources/fotmob.py:56     _CACHE_VERSION = 5   (Phase 1-B 에서 2 → 3 → 4 → 5)
toto/sources/whoscored.py:415 _LEAGUE_CACHE_VERSION = 2
```

### 1-5. 없는 데이터를 지어내지 않는다

**추정값을 실제 데이터처럼 표시하지 않는다.**

- 값이 없으면 `데이터 없음` 으로 표시한다 (`toto/render.py:330`).
- 레이더 축은 재료가 하나라도 없으면 `None` 을 돌려주고 축에서 빠진다.
  반쪽 값으로 채우면 리그 백분위가 왜곡되므로 차라리 축을 뺀다
  (`toto/models.py` 의 `home_goal_diff_pg`·`conversion_rate`·
  `defensive_solidity`·`finishing_delta` 등).
- `--demo` 는 난수 샘플이다. 리포트에 반드시 표시한다 —
  `toto/cli.py:142`: `"ok (샘플 · 실제 배당/성적 아님)"`.

### 1-6. 수집 실패와 데이터 부재를 구분한다

소스 상태 문자열이 셋을 구분한다 (`report.source_status`).

| 상태 | 뜻 |
|---|---|
| `생략` | 사용자가 건너뛰라고 했거나 조회 조건이 없다 (예: `"생략 (리그 미상)"`) |
| `실패 (사유)` | **수집 자체가 안 됐다** — `"실패 (브라우저 기동 불가)"`, `"실패 (bs4 미설치)"`, `"실패 (수집 0팀)"` |
| `부분 (n/m …)` | 일부만 받았다 — `"부분 (21/28팀 지표, 강점/약점 없음)"` |
| `ok (n/m …)` | 정상. 몇 건인지 함께 적는다 |

새 소스를 붙일 때도 이 형식을 따른다. **"데이터가 없다"와 "가져오지
못했다"를 같은 표현으로 뭉뚱그리지 않는다.** 실패 사유를 괄호에 적어야
다음 실행에서 무엇을 고칠지 알 수 있다.

한 소스가 실패해도 나머지는 계속 진행한다 (`toto/cli.py` 의 소스별
`try/except`). 실패가 실행 전체를 죽이지 않는다.

### 1-7. Windows 운영 규칙 — 보존한다

`.gitattributes` 에 이유와 함께 고정돼 있다. 세 가지 모두 실제로 사용자
환경에서 터졌던 문제다.

```
*.bat text eol=crlf     cmd.exe 는 바이트 오프셋으로 탐색해서, LF 만 있으면
*.cmd text eol=crlf     명령 중간부터 이어 읽어 이름이 잘린 채 실패한다
*.ps1 text eol=crlf     PowerShell 5.1 은 BOM 없는 .ps1 을 ANSI(한국어
                        윈도우는 cp949)로 읽어 비ASCII 문자열이 깨진다
*.sh  text eol=lf       윈도우에서 체크아웃해도 LF 유지
*.ico binary            줄바꿈 변환 금지
*.png binary
```

- `tools/create_shortcut.ps1` 은 **UTF-8 BOM** 으로 저장돼 있다
  (첫 3바이트 `ef bb bf`). 이 BOM 을 제거하면 바로가기 이름이 깨진다.
- `requirements*.txt` 는 **ASCII 전용**으로 유지한다. 한글 주석이 들어가면
  한국어 윈도우에서 pip 가 cp949 로 읽다 `UnicodeDecodeError` 로 죽는다.
- 메뉴 문구는 배치 파일이 아니라 파이썬(`toto/menu.py`)에서 출력한다.
  이유는 그 파일 상단 주석에 적혀 있다.

### 1-8. 새 기능은 기존 모듈을 먼저 재사용한다

중복 코드를 새로 만들지 않는다. 실제로 그렇게 정리한 사례가 있다.

- `toto/sources/browser.py` `StealthBrowser` — Playwright 세션.
  WhoScored 와 FotMob 이 **함께 쓴다**. 차단 판정만 `_is_blocked()` 훅으로
  소스별로 덮어쓴다 (`WhoScoredBrowser`, `FotMobBrowser`).
- `toto/models.py` `fill_stats()` — 소스 간 병합.
- `toto/cache.py` `Cache` — 날짜별 JSON 캐시 + `save_debug()`.
- `toto/normalize.py` `TeamResolver` — 팀명 해석. 트리를 훑으며 "이 문자열이
  팀명인가"를 시험 삼아 물을 때는 `quiet=True` 를 쓴다 (실패가 정상이라
  경고를 남기면 로그가 수천 줄이 된다).
- `toto/charts.py` — 인라인 SVG. 외부 라이브러리를 새로 들이지 않는다.

리포트는 **외부 참조가 0건인 자체 완결 HTML** 이어야 한다. CDN·외부
이미지·`<script src>` 를 추가하지 않는다. 폰에서 열기와 오프라인 열람이
여기에 달려 있다.

---

## 2. 작업 방식

### 2-1. 검증

이 저장소의 원격 세션에서는 대상 사이트가 **전부 차단**돼 있다
(betman·pinnacle·whoscored·fotmob). 그래서:

- 실물 수집 검증은 **사용자 PC 에서만** 가능하다. 로그를 받아 판단한다.
- 여기서는 `python -m toto --demo` 와 픽스처 기반 단위 검증까지 한다.
- 정책 우회는 하지 않는다.

### 2-2. 브랜치

작업 브랜치: `claude/soccer-toto-analysis-tool-xumkxg`.
`git push -u origin <branch>` 로 올린다. PR 은 요청받기 전까지 만들지 않는다.

### 2-3. 커밋 메시지

무엇을 왜 바꿨는지 적는다. 특히 **원인**을 남긴다 — 이 프로젝트는 같은
증상을 다른 원인으로 여러 번 만났다.

---

## 3. 추가 확인이 필요한 규칙

아래는 이번 점검에서 **확인하지 못했거나 아직 미해결**인 항목이다.
사실로 단정하지 말고, 다룰 때 실물을 먼저 확인한다.

### 3-1. WhoScored 정성 데이터 — 아직 한 번도 수집된 적 없다

`toto/sources/whoscored.py` 에 `_extract_characteristics()`,
`_extract_form()`, `_extract_missing()` 가 있으나 **실제 팀 페이지에서
성공한 기록이 없다.** 직전 원인(팀 링크 경로가 `/Teams/` → `/teams/` 소문자로
바뀜)은 고쳤지만, 수정 후 실행 결과를 아직 못 받았다.

→ 팀 페이지 HTML 을 실제로 받아 `Strengths`/`Weaknesses`/`Style of play`
구조를 확인한 뒤에만 파서를 손댄다. 실패하면 `FAILED_team_*.html` 이
남으므로 `[6]` 진단으로 본다.

### 3-2. FotMob 시즌 통계 피드 스키마

`toto/sources/fotmob.py` `_parse_stat_feed()` 는 `data.fotmob.com` 피드의
**정확한 스키마를 본 적이 없다.** "팀 이름으로 해석되는 문자열 + 지표로
보이는 숫자"를 찾는 구조 기반 파서로 짰고 실측에서 15종 × 27팀이 통과했지만,
스키마 자체는 미확인이다.

→ 필드를 추가하려면 `[7]` 점검의 `②-3 FotMob 팀 통계 피드` 로 실물을
먼저 본다.

### 3-2-1. Phase 1-B 에서 새로 붙인 것들 — 실물 실행 결과가 아직 없다

원격 세션은 fotmob.com 이 차단돼 있어 **픽스처로만 검증했다.** 아래 둘은
사용자 PC 실행 로그를 받기 전까지 "된다"고 단정하지 않는다.

- **시즌 피드 8종 추가** (15 → 23): `_set_piece_goals_team`,
  `_set_piece_goals_conceded_team`, `penalty_won_team`,
  `penalty_conceded_team`, `total_yel_card_team`, `total_red_card_team`,
  `accurate_cross_team`, `accurate_long_balls_team`.
  피드 **이름**은 Phase 0 [8] 의 29종 카탈로그에서 그대로 옮겼지만, 각
  피드의 응답을 실제로 받아 본 적은 없다. 구조 기반 파서라 이름이 맞으면
  통과할 것으로 보지만 확인 전이다. 실패해도 그 지표만 비고 나머지는 돈다.
- **경기 상세 파서**: 8개 스탯 키와 슛맵 필드는 Phase 0 저장본에서 실물로
  확인했다. 확인하지 못한 것은 **리그·경기마다 스탯 그룹 구성이 같은지**다
  (관찰 표본이 EPL 경기 몇 건뿐이었다). 특정 지표가 빠진 경기가 있으면 그
  칸만 비고 합산은 계속된다.

→ 실행 로그에서 `[리그] 경기 상세 N경기 수집` 과 `npxG 대조: … 최대 차이`
줄을 먼저 본다. 대조 차이가 크면 슛맵과 경기 스탯 중 무엇이 어긋나는지부터
확인한다 (값을 맞추지 말고 원인을 찾는다).

### 3-3. FotMob 결장자(injury) 값의 모양

`squad[].members[].injury` 필드와 `rating` 이 존재하는 것은 확인했으나,
관찰한 응답에서는 **전부 `None`** 이었다. 값이 들어올 때의 구조를 모른다.

→ 결장자 기능을 구현할 때 `[8]` 저장본 재분석으로 값이 든 사례를 먼저 찾는다.

### 3-4. 지침 원문의 소재

`predict.py` 가 "Calibrated Single-Pick Engine v3.2" 의 §0·§3·§5·§7·§8 을
구현한다고 밝히고 있으나, **지침 원문 파일은 저장소에 없다**
(`docs/` 에도 없다). 현재는 코드 주석이 유일한 사본이다.

→ §3-(b) 가산 마진 제거, §5 15% 게이트, §7 백중세 ±4%p, §8 회차로그 스키마는
코드에 구현돼 있으므로 그것을 근거로 삼는다. 지침 해석이 필요한 변경은
사용자에게 원문을 확인한다.

### 3-5. 리그 구성 (승강)

`data/teams.yaml` 의 `league:` 값은 사람이 적은 것이라 시즌이 바뀌면 썩는다
(2026 시즌에 대구·수원FC ↔ 인천·부천이 뒤바뀐 채로 있었다).

→ 실제 순위표가 권위다. `toto/normalize.py` `set_league()` 가 FotMob
순위표 기준으로 정정하고 `data/teams.league.yaml`(gitignore)에 남기며,
이 파일이 `teams.yaml` 보다 우선한다. **팀의 소속 리그를 손으로 단정하지
말고 순위표 결과를 따른다.**

### 3-6. 검증되지 않은 소스

- **FBref** — 실제 브라우저로도 Cloudflare 403. 다섯 차례 모두 실패. 제외.
- **Understat** — 아시아 리그 미수록(K리그 404). 제외.
- **Sofascore** — 접속은 되나 사용하지 않는다. 팀 시즌 통계 엔드포인트
  경로는 **미확인**(시도한 경로는 선수 랭킹이 나왔다).

→ 이 셋을 다시 쓰려면 `[7]` 점검부터 다시 한다.

---

## 4. 빠른 참조

```bash
python -m toto --demo              # 네트워크 없이 렌더링 확인
python -m toto --round 260044      # 회차 지정 수집
python -m toto --skip-whoscored    # 배당 + 순위·폼만 (빠름)
python -m toto --skip-match-details        # 경기 상세(npxG·xGOT…) 생략
python tests/test_league_matching.py       # 리그·팀 매칭 회귀 (15개)
python tests/test_match_details.py         # 경기 상세 파싱 회귀 (30개)
python -m toto --serve             # 리포트를 같은 와이파이에 공개
python tools/probe_sources.py --browser    # 소스 구조 점검
python tools/probe_sources.py --analyze    # 저장본 재분석 (접속 없음)
python tools/diagnose_whoscored.py         # 실패 원본 진단
```

메뉴(바탕화면 바로가기 / `toto_menu.bat`)에 같은 기능이 `[1]`~`[9]` 로 있다.
