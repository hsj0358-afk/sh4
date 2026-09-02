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

### 1-1-3. 슛 이벤트 계층 (Phase 1-C) — `toto/shots.py`

`matchDetails` 의 `content.shotmap.shots[]` 를 슛 1개도 잃지 않는 계층으로
만들어 둔다. Phase 2 의 경기력 분석과 Phase 3 의 슈팅맵이 이 위에 올라간다.

```
Raw JSON → parse_shot_events() → ShotEvent
         → aggregate_match()   → MatchShotAggregate   (경기 × 팀)
         → aggregate_recent()  → RecentShotAggregate  (최근 N / 홈 / 원정)
```

- **홈/원정은 teamId 로만 정한다.** 경기 스탯의 `[0]/[1]` 배열 순서를 믿는
  구조를 여기에 만들지 않는다. `_home_away_ids()` 가 응답에서 모양으로 찾고,
  없으면 순위표의 팀ID 로 넘어가고, 그래도 없으면 `is_home=None` 이다.
  모르는 경기는 홈/원정 분리 집계에서 빠지고 전체 집계에는 남는다.
- **합계·표본 수·평균을 분리한다.** `sums` / `counts` / `avg()`. 평균은
  **그 지표의 표본 수**로 나눈다 (§1-1-2 와 같은 이유).
- **개수는 0 이 실제 0, xG 계열은 없으면 None.** 한 슛도 xG 를 갖지 않은
  경기의 xG 는 `0.0` 이 아니라 `None` 이다.
- **npxG 는 `situation == "Penalty"` 를 뺀 xG 다.** 상수 차감이 아니다.
  경기 스탯의 `expected_goals_non_penalty` 는 그대로 두고, 슛맵 합산은
  **대조용**으로만 쓴다 (`reconcile()`). 차이를 로그에 적고 맞추지 않는다.
- **`xGOT − npxG` 를 결정력이라고 부르지 않는다.** xGOT 은 PK 를 포함하고
  npxG 는 제외하므로 기준이 다르다. 두 원값을 따로 들고 있는다.
- 집계 창은 `config_toto.yaml` 의 `fotmob.shot_recent_windows` (기본
  `[3, 5, 6, 10]`). 6 을 코드에 박지 않는다. 창이 받아 온 경기 수보다 크면
  `available_matches` 에 실제 수가 남는다 — 모자란 것을 감추지 않는다.
- 결과는 `TeamProfile.shot_aggregates` 에 붙는다. **TeamStats 는 건드리지
  않는다** — 구조가 있는 값이라 `fill_stats` 의 스칼라 병합 규칙에 맞지
  않고, 기존 지표 계산에 끼어들면 안 된다.
- 중복은 `(경기, event id)` 로 거른다. **id 가 유일하다고 가정하지 않는다** —
  없으면 팀·선수·시간·좌표·xG 를 묶어 판정한다.
- **상대 팀은 `opponent_id`(숫자 teamId)로 잇는다.** 팀명 문자열로 찾지
  않는다. 해석 순서는 (1) 경기의 home/away 팀 ID 를 둘 다 알면 반대편 —
  상대가 **0슛이어도** 붙는다, (2) 슛맵에 팀이 정확히 2개면 나머지 하나,
  (3) 둘 다 아니면 None. 이게 있어야 상대의 같은 경기 집계에서 피슛·npxGA·
  피xGOT 을 만들 수 있다 (Phase 2 수비 분석).

**막힌 슛은 유효슈팅이 아니다.** FotMob 의 `isOnTarget` 은 **블록된 슛에도
true** 로 온다(골문으로 가던 슛이라는 뜻). 통상적인 유효슈팅과 FotMob 자신의
경기 스탯 `ShotsOnTarget` 은 블록을 제외한다. 그대로 세면 과다 집계된다 —
260048 실물에서 팀당 최대 +8, 리그 평균 +4.23 이 나왔다. 블록을 빼면 6개
팀-경기 전부에서 경기 스탯과 **정확히 일치**했다. 세 분류(유효/오프/블록)가
총슛을 정확히 나눈다.

실물 260048(3경기 82슛)로 확인된 것:

| 지표 | 슛맵 − 경기스탯 최대 차이 |
|---|---|
| 슛·유효슈팅·박스 안/밖 | **0.0000** (정확히 일치) |
| xGOT | 0.0038 (반올림) |
| xG · npxG | 0.0636 (반올림 누적) |

`situation` 은 6종이라고 단정하지 않는다 — 실물에서 `ThrowInSetPiece`·
`IndividualPlay` 가 추가로 나왔다. 목록은 참고용이고 필터가 아니다.

회귀 테스트: `python tests/test_shot_events.py` (46개).

### 1-1-4. 시즌 경기 색인 (Phase 2 P0-2) — `Report.season_matches`

Phase 2 의 시점별 분석(상대 강도)이 "그 경기 **이전에** 무슨 일이 있었나"를
물으려면 시즌 경기 목록이 필요하다. 예전에는 `read_league` 안에서만 쓰고
버렸다. 이제 `enrich(..., season_out=report.season_matches)` 로 넘긴다.

- **새로 수집하지 않는다.** 이미 받은 리그 응답을 `SeasonMatch` 로 옮길 뿐이다.
- **팀 식별자를 두 벌 싣는다.** 이 프로젝트의 정규 식별자는 **팀명 문자열**
  (`TeamResolver` 의 canonical name)이고 슛 계층은 **숫자 teamId** 로 돈다.
  서로 다른 체계라 하나로 합치면 한쪽이 끊긴다 —
  `home_team`/`away_team`(정규명)과 `home_fotmob_id`/`away_fotmob_id`(숫자)를
  함께 둔다. 팀명만으로 과거 경기를 잇지 않는다.
- **`kickoff` 는 시간대를 지어내지 않는다.** `...Z` 면 aware, 표시가 없으면
  naive 로 두고 `kickoff_aware=False` 로 남긴다. 파싱 실패면 `kickoff=None`
  이고 `kickoff_raw` 에 원본이 남는다.
- **경기 ID 가 없으면 담지 않는다.** 팀명+날짜를 임의의 키로 만들지 않는다.
- 정렬은 kickoff 오름차순, 동시각은 match_id. 시점을 모르는 경기는 뒤로.

**누수 방지는 `matches_before(as_of)` 하나로 모은다** (`toto/models.py`).

  · 기준은 **엄격한 `<`** — 같은 시각 경기는 포함하지 않는다. 그 경기 결과가
    아직 없기 때문이다(같은 날 15시 경기는 20시 경기에 쓸 수 있지만 그 반대는
    안 되고, 15시끼리도 서로 못 쓴다).
  · 기본은 **종료 경기만**. 예정 경기를 과거처럼 쓰지 않는다.
  · `as_of=None` 이면 빈 목록. "기준이 없으니 전부"로 두면 미래가 섞인다.
  · aware↔naive 가 섞이면 비교하지 않고 제외한다.

회귀 테스트: `python tests/test_season_matches.py` (27개). 그중 미래 경기를
덧붙여도 과거 조회가 한 건도 안 바뀌는지 보는 테스트가 Phase 2-F 누수
검사의 기반이다.

**시즌 경기별 xG 는 여기에 없다.** 경기 상세는 팀당 최근 N경기만 받으므로
시즌 전체 경기의 xG 는 확보돼 있지 않다. Phase 2-F(상대 강도)를 설계할 때
"모든 과거 경기의 당시 상대 xGD" 를 전제하면 안 된다.

### 1-1-5. Phase 2 분석 모델 (P0-3) — `Match.analysis`

Phase 2 결과를 담는 그릇. **계산은 P1 이후이고 여기서는 구조만 만든다.**

```
Match.analysis : MatchAnalysis | None
  ├ home / away : TeamAnalysis      팀별 6축 + data_quality
  │    time_context · chance_quality · defensive_quality
  │    sustainability · venue_context · schedule_strength
  ├ matchup   : [MatchupPair]   공격 지표 ↔ 상대 수비 지표 (곱하지 않는다)
  ├ conflicts : [Signal]        방향 라벨만. 합산하지 않는다
  ├ evidence  : [EvidenceItem]  side + counter 로 세 방향 × 반박
  └ data_quality : DataQuality  축별 available / degraded_reason
```

- **축이 None = 아직 계산 안 했거나 표본 부족.** 빈 축 객체를 넣어 분석이
  끝난 것처럼 보이게 하지 않는다.
- **축마다 전용 dataclass 를 만들지 않는다.** 축은 '이름 붙은 지표 묶음'이라
  `AnalysisAxis` 하나로 둔다 — 각 축의 최종 필드 구성이 확정되기 전에
  모양을 박으면 P2~P6 에서 매번 뜯어야 한다.
- **모든 숫자를 `Metric` 으로 감싸지 않는다.** 리포트에 근거로 나가거나
  출처·표본을 밝혀야 하는 값에만 쓰고, 중간 계산은 평범한 float 로 둔다.
- 출처는 모듈 상수 `OBSERVED / DERIVED / MODEL` (Enum 을 새로 들이지 않는다).
  xPTS 같은 모델 산출값은 반드시 `MODEL` 로 표시한다.
- 표본은 **세 수가 다른 개념**이다 — `requested_matches`(요청한 창),
  `available_matches`(실제 쓸 수 있었던 경기), `Metric.sample_count`(그
  지표에 값이 있던 경기). 하나로 뭉뚱그리지 않는다.
- **최종 승무패를 담는 필드를 두지 않는다.** `final_pick`·`recommendation`
  같은 이름이 어느 dataclass 에도 없어야 하고, 신호는 개수만 세고
  `winner`·`decide` 같은 메서드를 만들지 않는다 (§1-3).
- `MatchAnalysis` 는 `Match.probs` 와 **별개 객체**다. 확률을 다시 계산하거나
  배당 확률과 합치지 않는다.
- `generated_at` 을 두지 않는다 — `Report.generated_at` 이 이미 있다.
  `as_of`(시점 기준)만 둔다. 개념이 다르다.

**캐시에 넣지 않는다.** `Match`·`Report` 는 디스크에 캐시되지 않고
(캐시는 fotmob·pinnacle 응답뿐), 분석은 이미 캐시된 데이터로 매 실행
다시 만드는 편이 싸고 낡을 위험도 없다. 캐시 버전도 올리지 않았다.

회귀 테스트: `python tests/test_analysis_model.py` (22개).

### 1-1-6. 기대승점 xPTS (Phase 2 P1) — `toto/xpts.py`

경기별 xG 두 개로 승/무/패 확률과 기대승점을 만든다. **모델 산출값**이며
`provenance = MODEL` 로 표시한다.

**피나클 배당 확률과 다른 것이다.** 저쪽은 시장이 매긴 값(`predict.py`,
observed)이고 이쪽은 경기내용에서 만든 모델값이다. 두 확률을 합치거나 서로
보정하지 않는다. **두 모듈은 서로를 import 하지 않는다** — 소스 텍스트와
런타임 양쪽으로 테스트한다. `xpts.py` 는 `.probs`·`MatchProb`·`.odds` 를
아예 참조하지 않는다.

- **독립 포아송이다. Dixon-Coles 가 아니다.** 무승부 보정계수도 두 팀 득점의
  상관항도 없다. 실제 축구에서 저득점 스코어라인이 과소평가되는 것으로
  알려져 있는데, 그 보정을 넣지 않았다는 뜻이다.
- **두 팀 xPTS 의 합은 3 이 아니다.** 무승부 확률이 양쪽에 1점씩 들어가므로
  `3 − P(무)` 다 (λ 둘 다 1.0 이면 약 2.69). 3 이 나오면 공식이 틀린 것이다.
- 득점을 **0~9 로 절단**한다. 부족분을 `tail_mass` 로 남기고 **자동 정규화하지
  않는다** — 재분배하면 모델이 얼마나 어긋났는지 안 보인다. λ 가 커지면
  커진다(둘 다 4.0 이면 약 1.6%). 기대승점도 **절단된 확률 그대로** 쓴다.
- `poisson_pmf` 는 `λ^k/k!` 를 직접 계산하지 않고 점화식
  `p(k)=p(k-1)·λ/k` 를 쓴다 — 큰 λ 에서 넘치지 않는다.
- **xG 가 어느 한쪽이라도 None 이면 전부 None.** `0.0` 은 실제 값이라 계산한다
  (무득점 기대). 둘을 같게 취급하지 않는다.
- 팀 집계(`aggregate_team_xpts`)는 **시점을 다시 보지 않는다** — 호출부가
  `Report.matches_before(as_of)` 로 걸러서 넘긴다. 누수 방지를 한 곳에만 둔다.
- `requested_matches`(넘겨받은 경기)와 `available_matches`(xG 가 있어 실제
  계산된 경기)는 다르다. **시즌 전체 경기의 xG 가 없으므로 자주 다르다** —
  `coverage` 로 드러내고 없는 경기를 0점으로 치지 않는다.

결과는 `MatchAnalysis.model`(모델 산출 전용 축)에 담는다. observed/derived
축과 섞지 않으려고 자리를 따로 뒀다.

회귀 테스트: `python tests/test_xpts.py` (36개).

### 1-1-7. 시간축 분석 (Phase 2-A) — `toto/analysis.py`

시즌 전체 경기력과 최근 경기력을 **나란히** 보여 준다. 픽을 고르지 않고
전력 점수를 만들지 않는다.

결과는 `TeamAnalysis.time_context`(`AnalysisAxis`) 하나에 들어가고, 키는
**`기간.지표`** 다 — `season.xg` · `recent6.xg` · `trend6.xg`.
기간을 키에 넣어 두면 **시즌 값과 최근 값이 구조적으로 섞일 수 없다.**
하나의 평균으로 합치지 않는다.

기간 N 은 코드에 박지 않는다. `config_toto.yaml` 의 `analysis.periods`,
없으면 `fotmob.shot_recent_windows` 를 쓴다.

**지표가 기간마다 다르다. 빈칸을 추정으로 채우지 않는다.**

| 지표 | 시즌 | 최근 N |
|---|---|---|
| 득점·실점·승점·득실차·승무패 | 순위표 | 시즌 경기 색인(`SeasonMatch`)의 **실제 스코어** |
| xG | 시즌 xG 표 | 슛 계층 |
| 슈팅·유효슈팅 | 시즌 통계 피드 | 슛 계층 |
| npxG · xGOT · 박스 안 슈팅 | **없다** | 슛 계층 |
| 결정적 기회 | 시즌 통계 피드 | **없다** (경기별 값을 안 받는다) |
| 피npxG · 피xGOT · 피슈팅 · 피유효슈팅 | 없다 | **경기 상세 창 1개에서만** |

수비 지표가 창 하나뿐인 이유: 상대 팀의 **경기별** 슛 집계가 저장되지 않는다
(`opponent_id` 만 남는다). 지금 있는 것은 `TeamStats` 의 `*_against_recent`
합계뿐이고 그 표본은 `fotmob.match_detail_matches` 로 정한 창 하나다.
창별 수비 지표는 2-C 에서 상대 집계를 확보한 뒤에 만든다.

최근 득점은 **슛맵이 아니라 최종 스코어**에서 센다 — 슛맵은 상대 자책골을
우리 득점으로 세지 않으므로 승점·득실차의 기준이 될 수 없다.

- 평균은 언제나 **그 지표의 표본 수**로 나눈다. `requested_matches`(요청한
  창) · `available_matches`(확보한 경기) · `Metric.sample_count`(그 지표에
  값이 있던 경기) 셋을 구분해 전부 남긴다.
- 커버리지는 `DataQuality.axes["time_context.recent6"]` 에 남는다.
  **신뢰도 점수로 바꾸지 않는다.** 시즌 초 `1/6 경기` 는 오류가 아니다.
- **트렌드는 `최근 − 시즌` 이고 파생값(DERIVED)이다.** 시즌에 없는 지표
  (npxG·xGOT…)는 트렌드도 없다. 밴드(`higher`/`lower`/`similar`)는 라벨일
  뿐이고, 문턱은 `config_toto.yaml` 의 `analysis.trend_thresholds` 에 있다 —
  그 자리에 **"운영용 기준이며 통계적으로 검증된 기준이 아님"** 이라고
  적어 두었다. 밴드를 점수로 바꾸거나 여러 지표를 합산하지 않는다.
  **빼기 전에 뺄 수 있는지 먼저 본다 — §1-1-9.**
- **최근 값이 높다고 "상승세"·"전력 상승"·"강팀" 이라고 적지 않는다.**
  "최근 6경기 xG 가 시즌보다 +0.22" 까지가 전부다.
- `Metric.direction` 은 표시용 메타데이터다 (`higher_better`/`lower_better`,
  정하지 않았으면 빈 문자열). **슈팅 수와 무승부 수는 비워 둔다** — 많다고
  좋은 것이 아니다. 부호를 곱해 합산하는 데 쓰지 않는다.
- 승/무/패는 남기되 **폼 점수 같은 단일 숫자를 만들지 않는다.**
- xPTS 를 여기서 다시 계산하지 않는다 (P1 의 값, 연결은 2-D). `analysis.py`
  는 `xpts` 를 import 하지도 참조하지도 않는다 — AST 로 테스트한다.

**시점.** cutoff 는 `models.matches_before(as_of)` **하나뿐**이다. 이 모듈은
`kickoff` 을 직접 비교하지 않는다(테스트로 고정). `as_of` 는
`Match.kickoff_kst` 를 UTC+9 로 읽어 만든다 — 필드 이름이 KST 라고 밝히고
있어서지 시간대를 임의로 정하는 게 아니다. 파싱 실패면 `None` 이고, 그러면
과거 경기 구간이 비고 그 사실이 notes 에 남는다.

슛 계층의 창은 **수집 시점에 이미 만들어져 있어 다시 자를 수 없다.** 그래서
자르는 대신 창의 `match_ids` 를 시즌 색인과 대조한다.

  · `as_of` 이후 경기가 섞였으면 → 그 창의 **슛 지표를 만들지 않는다**
  · 색인에 없어 확인 불가면 → 값은 내되 notes 에 적는다

순위표·시즌 통계 피드는 **수집 시점 스냅샷**이라 `as_of` 로 잘리지 않는다.
과거 경기 수와 어긋나면 notes 에 그렇게 적는다 — 조용히 지나가면 과거
경기를 분석할 때 미래가 섞인 줄 모르게 된다.

회귀 테스트: `python tests/test_time_context.py` (43개).

### 1-1-8. 기회의 질 (Phase 2-B) — `toto/analysis.py` `build_chance_quality()`

흐름 하나를 구조로 만든다.

```
슈팅  →  xG · npxG  →  xGOT  →  득점
(양)     (기회의 질)    (실행)    (결과)
```

결과는 `TeamAnalysis.chance_quality` 에 들어가고 키는 2-A 와 같은
`기간.지표` 다. **기간 구조를 새로 만들지 않았다.**

**비율은 '평균의 평균' 이 아니다.** 경기별 xG/슛 을 구해 다시 평균 내면
슛이 적은 경기가 과대 대표된다. `Σ xG / Σ 슛` 으로 **합계끼리 나눈다.**

**분자와 분모의 표본이 같아야 한다.** 창의 합계(`RecentShotAggregate.sums`)
만으로는 이걸 보장할 수 없다 — 6경기 창에서 슛은 6경기에 있고 xG 는
4경기에만 있으면 `Σxg/Σshots` 는 4경기치를 6경기치로 나눈 값이 되어 조용히
낮아진다. 그래서 **경기별 원재료**(`TeamProfile.shot_matches`, 이번에
프로필까지 연결했다)에서 **둘 다 있는 경기만** 골라 합산한다.
원재료가 없으면(옛 캐시·데모) 창의 표본 수가 창의 확보 경기 수와 **완전히
일치할 때만** 계산하고, 아니면 만들지 않는다.

**`xGOT − npxG` 를 만들지 않는다.** xGOT 은 PK 를 포함하고 npxG 는
제외하므로 기준이 다르다. 이 차이를 "결정력"·"슈팅 효율" 로 부르면 PK 를
많이 얻은 팀이 자동으로 좋아 보인다. xG·npxG·xGOT 세 원값을 따로 둔다.
(리포트의 `recent_metrics` 에 Phase 1-B 때 넣은 `xgot_delta_recent` 행이
아직 남아 있다 — 2-B 는 UI 를 건드리지 않아 그대로 뒀다. §3-7 참고.)

**득점−xG 계열을 "결정력" 이라 부르지 않는다.** `goals_minus_xg` ·
`goals_minus_npxg` · `goals_minus_xgot` 세 개를 각각 따로 두고 **방향을
정하지 않는다**(`Metric.direction=""`) — 양수가 좋은 것도, 음수가 나쁜 것도
아니다. 셋을 합쳐 단일 점수로 만들지 않는다.

- 득점은 **슛맵이 아니라 최종 스코어**에서 온다(2-A 와 같은 이유). 스코어를
  모르는 경기는 차이 지표의 표본에서 빠진다 — 0 으로 치지 않는다.
- 박스 안 비율·유효슈팅 비율은 **%** 다 (`TeamStats.inside_box_shot_share`
  와 같은 관례). 분모 합이 0 이면 `None` 이다 — 0 이 답인 게 아니다.
- 시즌에는 npxG·xGOT·박스 안 슈팅이 없어 `npxg_per_shot`·`box_shot_share`·
  `goals_minus_npxg`·`goals_minus_xgot` 의 **시즌 값이 없다.** 결정적 기회는
  반대로 **시즌에만** 있다.
- 시즌 비율은 순위표 경기 수(`played`)와 xG 표 경기 수(`xg_played`)가
  **같을 때만** 만든다. 다르면 만들지 않고 notes 에 적는다.

**`Metric.group`** 을 붙인다 — `volume` · `chance_quality` · `execution` ·
`sustainability_gap` · `outcome`. **점수 계산용이 아니다.** 2-I 근거 요약에서
xG·npxG·슛당 xG 처럼 같은 이야기를 세 번 세지 않으려는 메타데이터다.

**패턴(A~D)은 추천이 아니라 상태 설명이다.** 문턱은
`config_toto.yaml` 의 `analysis.chance_quality.thresholds` 에 있고 그 자리에
**"운영용 기준이며 통계적으로 검증된 기준이 아님"** 이라고 적어 두었다.
표본이 `min_sample`(기본 3)에 못 미치면 **패턴을 아예 만들지 않는다** —
시즌 초 1경기로 "슈팅량 대비 기회 질이 낮다" 고 적으면 안 된다.
"반등한다"·"결정력이 좋다" 같은 예측 문구를 만들지 않는다.

시점은 2-A 와 **같은 장치**를 쓴다 — `matches_before(as_of)` 와
`_window_time_check`. 창에 기준시각 이후 경기가 섞였으면 그 기간을 통째로
만들지 않는다. 이 함수는 `kickoff` 을 직접 비교하지 않는다(테스트로 고정).

회귀 테스트: `python tests/test_chance_quality.py` (41개).

### 1-1-9. 트렌드를 만들기 전에 뺄 수 있는지 본다 (2-B 교정)

실물 260048 에서 풀럼의 값이 이랬다.

```
시즌 xG   1.33   ← 경기 스탯 값        (season_xg_table / match_stat)
최근 xG   1.39   ← 슛맵 이벤트 합산     (shotmap / shot_events)
트렌드    +0.06
```

**같은 한 경기다.** +0.06 은 경기력 변화가 아니라 두 측정 방식의 차이였다 —
슛맵은 슛마다 xG 를 반올림해 주므로 합치면 누적된다(§3-2-1 실측 최대 +0.09).
이런 숫자를 추세로 적으면 안 된다.

그래서 `Metric` 에 두 가지를 싣는다.

  · `source`            어느 피드에서 왔나 (`standings` · `shotmap` · …)
  · `measurement_basis` 어떻게 만들어졌나 (`final_score` · `match_stat` ·
                        `shot_events`)

표는 `_SEASON_ORIGIN` / `_RECENT_ORIGIN` 에 있다. **시즌과 최근이 다른
피드에서 온다는 사실 자체가 거기 적혀 있다.**

`trend_allowed()` 가 빼기 전에 여섯 가지를 본다.

| # | 조건 | 어긋나면 |
|---|---|---|
| 1 | 같은 지표 | `metric_mismatch` |
| 2 | 직접 비교 가능한 원천 | `source` |
| 3 | 같은 산출 방식 | `basis` |
| 4 | 경기당 값일 것 (누계가 아님) | `count_unit` |
| 5 | 서로 다른 경기 집합 | `same_match_set` |
| 6 | 표본이 최소 기준 이상·유효 | `sample` |

어긋나면 **값을 `None` 으로 두고 사유를 함께 남긴다** — 지우면 왜 없는지
알 수 없고, 숫자를 남기면 추세로 읽힌다. `Metric.note` 가
`not_meaningful <사유>` 로 시작하고 `parse_trend_band()` 가 되읽는다.

- **원천 비교는 명시적으로 등록한 쌍만 허용한다** (`COMPARABLE_SOURCES`).
  지금 등록된 것은 `{standings, season_match_index}` 하나뿐이다 — 순위표의
  득점·승점 누계는 정의상 최종 스코어의 합이고 260048 실물에서도 두 경로가
  정확히 같았다(첼시 3.00 = 3.00). **"아마 비슷할 것" 으로 늘리지 않는다.**
- 그 결과 **xG·슈팅·유효슈팅은 트렌드가 없다** (시즌은 피드, 최근은 슛맵).
  득점·실점·승점·득실차만 트렌드가 나온다.
- **승/무/패는 누계라 트렌드를 만들지 않는다.** "시즌 5승(10경기)" 과
  "최근 3승(3경기)" 을 빼면 −2 가 나오는데 이건 경기 수 차이일 뿐이다.
  경기당 승점(`points`)이 이미 같은 이야기를 한다.
- 시즌 초처럼 **최근 구간이 시즌 전체와 같은 경기**면 만들지 않는다
  (`available >= played`). 260048 이 정확히 이 경우다.
- 최소 표본은 `config_toto.yaml` 의 `analysis.trend_min_sample`(기본 3).
- notes 는 창과 무관한 사유(원천·방식·단위)를 **한 번만** 적는다
  (`STRUCTURAL_BLOCKS`). 창마다 반복하면 팀당 16줄이 된다.

**교정 범위는 트렌드뿐이다.** observed·derived 원값은 한 줄도 바뀌지 않았다 —
실물 두 팀의 `chance_quality` 136개, `time_context` 비-트렌드 138개가 교정
전후로 완전히 같다는 것을 대조로 확인했다.

회귀 테스트: `python tests/test_trend_validity.py` (25개).

### 1-1-10. 수비의 질 (Phase 2-C) — `build_defensive_quality()`

2-B 를 거울에 비춘 것이다.

```
피슈팅  →  npxGA  →  피xGOT  →  실점
(양)     (허용한 기회의 질) (실행)  (결과)
```

**값은 상대 팀의 같은 경기 슛 집계에서 온다.** 상대가 친 슛이 우리 피슛이고
상대의 npxG 가 우리 npxGA 다. 연결은 `opponent_id`(숫자 teamId, P0-1)로만
한다 — 팀명 문자열로 찾지 않는다.

**그 원재료를 이번에 저장하기 시작했다.** `_attach_shot_aggregates` 의
`per_match[mid]` 는 원래부터 양 팀을 다 갖고 있었는데 자기 팀 것만 꺼내
쓰고 버렸다. 이제 `entry["opponent_matches"]` → `TeamProfile.opponent_matches`
로 함께 싣는다. **캐시 버전 8 → 9** (형식이 바뀌어 옛 캐시를 읽으면 수비
지표가 통째로 빈다).

**상대가 0슛인 경기를 버리지 않는다.** `aggregate_match` 는 슛 이벤트에서
팀을 만들기 때문에 0슛 팀은 결과에 아예 없다. 그대로 두면 **가장 잘 막은
경기가 표본에서 사라져** 피슛 평균이 위로 치우친다. `shots.empty_aggregate()`
가 개수 0 · xG 계열 0.0 으로 채운다 — 상대 슛이 슛맵에 있어 응답이 실렸음이
확인된 경우에만 부르므로 이건 결측이 아니라 관측이다.

**`TeamStats.*_against_recent` 와 다른 값이다.** 이름이 비슷해 헷갈린다.

| | 원천 | 산출 방식 | 창 |
|---|---|---|---|
| `TeamStats.npxga_recent` (2-A) | `match_stats` | `match_stat` | `match_detail_matches` 하나 |
| `defensive_quality` 의 `npxga` (2-C) | `shotmap` | `opponent_shot_events` | 창마다 |

둘을 억지로 맞추지 않는다. 실물 260048 에서 슛맵 합산과 경기 스탯 피지표를
대조하니 **피슈팅·피유효슈팅은 정확히 일치**했고 npxGA 는 최대 0.0636,
피xGOT 은 0.0038 차이였다(슛별 반올림 누적, §1-1-9 와 같은 크기).

`measurement_basis` 에 `opponent_shot_events` 를 새로 넣은 이유가 이것이다 —
같은 슛맵이라도 **우리 슛을 센 것과 상대 슛을 센 것은 다른 양**이고,
`trend_allowed()` 가 자동으로 섞이지 않게 막는다. 같은 이름(`npxga`)이 축마다
다른 피드에서 오므로 이름만으로 원천을 정할 수 없어, 축이
`_metric(..., origin=...)` 로 직접 지정한다.

- **실점은 슛맵이 아니라 최종 스코어**에서 온다 (자책골 표기를 실물로
  확인하지 못했다 — §1-1-3). `provenance=OBSERVED`, 나머지 피지표는 전부
  **상대의 관측값을 우리 관점으로 옮긴 것**이라 `DERIVED` 다.
- **시즌에는 npxGA·피xGOT·피박스 안 슈팅이 없다.** 시즌 통계 피드에 없고
  상대 슛맵은 최근 N경기만 받는다. 시즌 수비 값은 실점과 **xGA** 뿐이다
  (xGA 는 PK 를 포함하므로 npxGA 와 다른 지표다 — 같은 칸에 넣지 않는다).
- 피슛당 npxGA 는 2-B 와 같은 규칙이다 — 분자·분모가 **둘 다 있는 경기만**,
  합계끼리 나눈다.
- **실점−npxGA · 실점−피xGOT 를 골키퍼 능력이라 부르지 않는다.** 방향을
  정하지 않고(`direction=""`), 둘을 합쳐 수비 점수로 만들지 않는다.
  `goalkeeper_score`·`defense_score` 같은 이름이 코드에 없어야 한다(테스트).
- `Metric.group` 은 공격과 따로 둔다 — `defense_volume` · `defense_quality` ·
  `defense_execution` · `defense_gap` · `defense_outcome`. 2-I 가 "우리 슈팅이
  많다" 와 "상대 슈팅을 많이 허용한다" 를 같은 근거로 세면 안 된다.
- 홈/원정은 **해석하지 않고 보존만** 한다 (2-E 소관). `build_defensive_quality`
  는 `is_home` 을 읽지 않는다(테스트로 고정).
- 시점·트렌드는 2-A/2-B 교정의 장치를 그대로 쓴다 — 자체 비교 로직을
  만들지 않는다(테스트로 고정).

회귀 테스트: `python tests/test_defensive_quality.py` (52개).

**값이 없으면 이유를 남긴다 (2-C 교정).** 예전에는 `_put()` 이 값이 `None`
일 때 `note` 까지 함께 버려서, 리포트에 "커버리지 6/6인데 실점이 없다" 는
상태만 남고 왜 없는지는 알 수 없었다. `_put(..., reasons=…)` 이 사유만
곁길로 빼내 `AnalysisAxis.notes` 와 `DataQuality.degraded_reason` 에 싣는다.

  · **값은 한 칸도 바뀌지 않는다** — `out` 에 들어가는 내용은 전과 같고,
    `None` 이 `0` 이 되지도 않는다.
  · 사유는 **창을 가로질러 한 줄로 모은다** (`_merge_missing` /
    `_missing_notes`). 창 4개에 같은 사유가 네 번 적히지 않는다 —
    2-B 교정의 `STRUCTURAL_BLOCKS` 와 같은 뜻이다. 그래서 `_gap()` 의
    "못 이었다" 사유는 경기 수를 빼고 `NO_SCORE` 상수를 쓴다.
  · 2-B·2-C 가 **같은 `_put()` 을 통해** 사유를 남긴다. 한 곳만 고쳤다.

회귀 테스트: `python tests/test_reason_preservation.py` (17개).

### 1-1-11. 지속성 (Phase 2-D) — `build_sustainability()`

세 층을 **나란히** 두고 차이만 적는다. 하나로 합치지 않는다.

```
ACTUAL      득점 · 승점            최종 스코어      observed
UNDERLYING  xG · npxG · xGOT       슛 이벤트        observed
MODEL       xPTS                   독립 포아송(P1)  model
```

결과는 `TeamAnalysis.sustainability` 에 들어가고 키는 2-A~2-C 와 같은
`기간.지표` 다.

**핵심 질문은 "값이 있나" 가 아니라 "같은 것을 비교하고 있나" 다.**
실제는 6경기, xG 는 4경기, xPTS 는 4경기인 일이 흔하다. 6경기 평균에서
4경기 평균을 빼면 그 차이의 절반은 **경기 구성이 다른 데서** 온다.

- **차이는 양쪽 값이 다 있는 경기에서만 만든다.** `_common_mean()` 이 그
  경기만 골라 합산하고, **실제값도 그 공통 경기에서 다시 계산한다** —
  6경기 승점 평균에서 4경기 xPTS 를 빼지 않는다.
- 그래서 **수가 넷**이다. `requested_matches`(요청한 창) ·
  `available_matches`(확보한 경기) · `Metric.sample_count`(그 지표에 값이
  있던 경기) · **`Metric.common_sample_count`(양쪽이 다 있던 경기)**.
  마지막 칸은 **차이 지표에만** 채운다 — 원값은 뺀 적이 없다.
- 빼기 전에 `comparison_allowed()` 를 지난다. 시즌 차이도 **같은 문**을
  지난다. 막히면 값은 `None` 이고 사유가 notes 와 `degraded_reason` 에
  남는다 (2-C 교정의 `_put(reasons=…)` 를 그대로 쓴다).

**`trend_allowed()` 와 반대 방향의 문이다.** 헷갈리기 쉬워 적어 둔다.

| | `trend_allowed()` (2-B 교정) | `comparison_allowed()` (2-D) |
|---|---|---|
| 묻는 것 | 최근 − 시즌 을 빼도 되나 | 실제 − 기대 를 빼도 되나 |
| 산출 방식 | **같아야** 한다 | **등록된 쌍**이어야 한다 |
| 경기 집합 | **달라야** 한다 (다른 기간) | **같아야** 한다 (공통 경기) |

등록된 쌍은 `COMPARABLE_GAPS` 넷뿐이다 — `final_score` ↔
`shot_events` · `opponent_shot_events` · `poisson_model` · `match_stat`.
"아마 비슷할 것" 으로 늘리지 않는다.

- 만드는 차이는 넷이고 전부 `DERIVED` 다 — `goals_minus_xg` ·
  `goals_minus_npxg` · `goals_minus_xgot` · `points_minus_xpts`.
- **xPTS 를 다시 구현하지 않는다.** P1 의 `xpts.aggregate_team_xpts()` 를
  부른다. `build_sustainability` 안에 거듭제곱도 `math.` 도 없다(AST 테스트).
- **시즌 xPTS 는 만들지 않는다.** 경기 상세를 팀당 최근 N경기만 받으므로
  시즌 전체의 경기별 xG 가 없다. 시즌에는 npxG·xGOT 도 없어 시즌에서
  견줄 수 있는 것은 **득점 ↔ xG 하나뿐**이고, 그것도 순위표 경기 수와 xG 표
  경기 수가 같을 때만 만든다.
- **평균회귀를 예언하지 않는다.** 상태 라벨 넷(`actual_below_underlying` ·
  `actual_above_underlying` · `aligned` · `not_comparable`)과 **부호**만
  둔다. "반등한다"·"곧 떨어진다" 를 만들지 않는다.
- **차이의 크기를 Small/Moderate/Large 로 나누지 않는다.** 이 프로젝트에
  검증된 기준이 없다 — 그래서 `config_toto.yaml` 에 2-D 문턱을 두지 않았다.
  패턴은 **부호**로만 갈리고, 표본이 `analysis.trend_min_sample` 에 못 미치면
  아예 만들지 않는다.
- 확률과 무관하다. `predict`·`Match.probs`·`odds` 를 참조하지 않는다(AST).

실물 260048 세 경기(팀-경기 6개)로 축의 값과 원자료 손계산이 전부 일치했다
(최대 차이 4.4e-16). 그 세 경기에는 PK 가 없어 **npxG 가 xG 와 같다** —
둘이 같다고 파서가 잘못된 것이 아니다.

회귀 테스트: `python tests/test_sustainability.py` (51개).

### 1-1-12. 장소 문맥 (Phase 2-E) — `build_venue_context()`

묻는 것은 하나다. **이 경기와 같은 장소에서 이 팀은 어땠고, 그것이 전체와
얼마나 다른가.** 홈팀에는 홈 표본을, 원정팀에는 원정 표본을 붙인다.

기간이 넷이고 키는 2-A~2-D 와 같은 `기간.지표` 다.

```
season          전체 시즌      (기준시각까지 끝난 모든 경기)
home_season     홈 시즌        ← away_season
recentN         전체 최근 N경기
homeN           최근 N경기 중 홈 ← awayN
```

**기간 정의를 새로 만들지 않았다.** 장소 최근 구간은 "최근 홈 N경기" 가
아니라 **최근 N경기 중 그 장소의 경기**다. 2-A 의 기간을 먼저 잡고 장소로
거른다 — 최근 5경기 중 홈이 1경기면 `home5` 는 1경기다.

이렇게 하는 이유가 둘이다.

  · 장소 표본이 **전체 표본의 부분집합**이라는 것이 경기 ID 로 확인된다.
    그래야 장소차를 만들 자격이 생긴다.
  · 한 블록 안에서 **승점과 xG 의 경기 집합이 같다.** 슛 계층의 `home6`
    창(최근 홈 6경기)을 그대로 쓰면 승점은 시즌 색인 기준, xG 는 다른 경기
    집합 기준이 되어 조용히 어긋난다.

**장소는 실제 경기의 home/away 로만 정한다** (`venue_of()`). 팀 이름이나
경기 수로 추정하지 않고, 이름이 정확히 맞지 않으면 `None` 이다.

값의 출처는 2-A~2-C 가 쓰는 **같은 함수**다. 집계를 새로 만들지 않았다.

| 지표 | 출처 | 함수 |
|---|---|---|
| 승점·득점·실점 | 시즌 경기 색인의 최종 스코어 | `_result_values` |
| xG·npxG·xGOT·슈팅 | 우리 슛맵의 경기별 집계 | `_match_rows` + `_mean` |
| 피슈팅·피유효슈팅·npxGA·피xGOT | 상대 슛맵의 경기별 집계 | `opponent_rows` + `_mean` |

**시즌 장소 블록은 최종 스코어 계열뿐이다.** 시즌 통계 피드에 홈/원정 분리가
없고 시즌 전체의 경기별 xG 도 없다 (2-D §17 과 같은 한계). 없는 것을
만들지 않는다.

**순위표의 홈/원정 표는 값으로 쓰지 않는다.** 수집 시점 스냅샷이라 기준시각
으로 잘리지 않는다. 경기 수가 시즌 색인과 어긋나면 notes 에만 적는다.

**장소차는 `comparison_allowed(relation=SUBSET)` 를 지나야 만들어진다.**
이 문은 2-D 와 **묻는 것이 다르다.**

| | `SAME_SET` (2-D 실제↔기대) | `SUBSET` (2-E 장소↔전체) |
|---|---|---|
| 지표 이름 | 달라도 된다 (득점 ↔ xG) | **같아야** 한다 |
| 산출 방식 | `COMPARABLE_GAPS` 등록 쌍 | **같아야** 한다 |
| 원천 | 묻지 않는다 | `sources_comparable()` |
| 경기 집합 | **같아야** 한다 | 한쪽이 **다른 쪽에 들어** 있어야 한다 |

`same_match_set` 은 두 경우 모두 "그 관계가 실제로 확인됐다"는 뜻이고,
호출부가 **경기 ID 로 확인해서** 넘긴다.

- 장소차 이름은 `<지표>_venue_gap` 이고 전부 `DERIVED` · **방향 없음**이다.
  홈 승점이 전체보다 높다는 것은 홈이 좋다는 뜻일 수도, 원정이 나쁘다는
  뜻일 수도 있다. 부호를 곱해 우위 점수로 만들지 않는다.
- 장소차의 `measurement_basis` 는 **`mixed` 가 아니라 원래 방식 그대로**다.
  같은 방식의 두 값을 뺐으므로 섞이지 않았다.
- `Metric.common_sample_count` 에 **장소 표본 수**를 싣는다 (좁은 쪽이
  한계 표본이다). note 에 `홈 3경기 ⊂ 전체 6경기` 로 적는다.
- 표본이 `analysis.venue_context.min_sample`(기본 3)에 못 미치면 장소차를
  만들지 않고 사유가 notes 와 `degraded_reason` 에 남는다.
- 패턴 A~D 는 상태 설명이다. 문턱은 `config_toto.yaml` 의
  `analysis.venue_context.thresholds` 에 있고 **"운영용 기준이며 통계적으로
  검증된 기준이 아님"** 이라고 적어 두었다. 갈래마다 **대표 지표 하나**만
  본다(공격은 npxG, 수비는 npxGA) — 같은 이야기를 세 번 세지 않는다.
  D 는 A~C 를 다시 세는 것이 아니라 **여러 갈래가 같은 방향인가**를 본다.
- **상대 강도(SoS)는 여기서 보지 않는다** — 2-F 소관이다.
- 확률과 무관하다. `predict`·`Match.probs`·`odds` 를 참조하지 않는다(AST).

**리포트에 처음으로 분석 축이 나간다.** `render._venue_block()` 이 전체 ·
장소 · 장소차를 한 표에 놓고 **지표마다 표본 수(n=…)를 함께 적는다** — 적은
표본이 충분해 보이면 안 되기 때문이다. 새 CSS 는 표본 수를 흐리게 하는
`table.mini small` 한 줄뿐이고 외부 참조는 그대로 0 이다.
`--demo` 에는 시즌 경기 색인이 없어 이 블록이 나오지 않는다 (2-A~2-D 와 같다).

캐시는 **올리지 않았다.** `MatchAnalysis` 는 캐시되지 않고 소스 응답의
저장 형식도 바뀌지 않았다.

회귀 테스트: `python tests/test_venue_context.py` (57개).

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
toto/sources/fotmob.py:59     _CACHE_VERSION = 9   (1-B 2→3→4→5, 1-C 6, Phase 2 P0-1 7 · P0-2 8 · 2-C 9)
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

### 3-2-1. Phase 1-B — 실물(260048)로 확인 완료

원격 세션은 fotmob.com 이 차단돼 픽스처로만 검증했었다. 2026-08-29 사용자 PC
실행(캐시 삭제 후 260048 재수집)으로 아래가 실물 확인됐다.

- **시즌 피드 8종** (15 → 23) — 전부 실제 응답을 반환했다. 이름이 맞다는 뜻이다.
  EPL 23종 전부, Serie A 는 20종(PK 2종·퇴장 1종은 그 리그 카탈로그에 없어
  시도조차 안 한다 — 정상 동작).
- **경기 상세 파서** — 리그당 11경기 수집, 팀 20개 전부 채워졌다.
- **npxG**: 슛맵 합산과의 차이가 EPL 평균 +0.01 / 중앙값 −0.00 / 최대 +0.06,
  Serie A 평균 +0.01 / 중앙값 +0.00 / 최대 +0.09 (각 표본 22).
  남은 차이는 슛맵이 슛마다 xG 를 반올림해 주기 때문에 누적되는 크기다.
- **xGOT**: 차이가 더 작다. EPL 평균 −0.00 / 최대 +0.00, Serie A 평균 +0.00 /
  최대 −0.01. 유효슈팅만 합산하므로 반올림 누적이 적다.
- **홈/원정 방향**: 대조는 순위표의 팀 ID 로 슛맵을 조회하므로 배열 순서와
  독립이다. 44개 팀-경기 쌍 전부 차이 ≈ 0 → `stats[0] = 홈` 이 맞고 배정도
  맞다는 실물 증거다(뒤집히면 합성 테스트에서 2.11 차이가 났다).

**아직 실물로 발현하지 않은 것**: 지표별 표본 수 차이(`recent_counts`).
시즌 초라 팀당 표본이 1경기뿐이어서 `0 < 개수 < 경기수` 조건이 성립할 수
없었다. 다만 한 경기 안에서 지표가 통째로 빠지는 사례는 실제로 나왔다
(세트피스 xG 2팀, 피xGOT·피유효슈팅 각 1팀 — 리포트에서 막대 없이 빠졌다).
표본이 여러 경기로 쌓이면 발현하므로, 그때 `일부 지표가 경기 수보다 적은
표본입니다` 로그를 확인한다.

→ 실행 로그에서 `[리그] 경기 상세 N경기 수집` 과 `npxG/xGOT 대조` 줄을 먼저
본다. 평균이 한쪽으로 0.30 넘게 쏠리면 계통 오차 경고가 함께 나온다.

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

### 3-7. 리포트에 남아 있는 `xGOT−npxG` 행

`config_toto.yaml` 의 `recent_metrics` 에 Phase 1-B 때 넣은
`xgot_delta_recent`("xGOT−npxG(합계)") 행이 있고,
`TeamStats.xgot_delta_recent` 가 그 값을 만든다.

Phase 2-B 에서 **이 지표를 분석에 쓰지 않기로 정했다** — xGOT 은 PK 를
포함하고 npxG 는 제외해 기준이 다르므로, 둘의 차이를 "결정력"·"슈팅 효율"
로 읽으면 PK 를 많이 얻은 팀이 자동으로 좋아 보인다(§1-1-3, §1-1-8).

리포트 UI 는 2-B 범위가 아니라 그대로 뒀다. **행을 지울지, 남기되 설명을
붙일지는 사용자 판단이 필요하다.** 분석 축(`chance_quality`)에는 들어가지
않는다는 것만 코드로 고정돼 있다.

---

## 4. 빠른 참조

```bash
python -m toto --demo              # 네트워크 없이 렌더링 확인
python -m toto --round 260044      # 회차 지정 수집
python -m toto --skip-whoscored    # 배당 + 순위·폼만 (빠름)
python -m toto --skip-match-details        # 경기 상세(npxG·xGOT…) 생략
python tests/test_league_matching.py       # 리그·팀 매칭 회귀 (15개)
python tests/test_match_details.py         # 경기 상세 파싱 회귀 (36개)
python tests/test_shot_events.py           # 슛 이벤트 계층 (46개)
python tests/test_season_matches.py        # 시즌 경기 색인·시점 (27개)
python tests/test_analysis_model.py        # Phase 2 분석 모델 (22개)
python tests/test_xpts.py                  # 독립 포아송 기대승점 (36개)
python tests/test_time_context.py          # 시간축 분석 2-A (43개)
python tests/test_chance_quality.py        # 기회의 질 2-B (41개)
python tests/test_trend_validity.py        # 트렌드 유효성 2-B 교정 (25개)
python tests/test_defensive_quality.py     # 수비의 질 2-C (52개)
python tests/test_reason_preservation.py   # 값 없음 사유 보존 2-C 교정 (17개)
python tests/test_sustainability.py        # 지속성 2-D (51개)
python tests/test_venue_context.py         # 장소 문맥 2-E (57개)
python -m toto --serve             # 리포트를 같은 와이파이에 공개
python tools/probe_season_index.py         # 시즌 색인이 시즌 전체를 담는가 (2-F 착수 조건)
python tools/probe_sources.py --browser    # 소스 구조 점검
python tools/probe_sources.py --analyze    # 저장본 재분석 (접속 없음)
python tools/diagnose_whoscored.py         # 실패 원본 진단
```

메뉴(바탕화면 바로가기 / `toto_menu.bat`)에 같은 기능이 `[1]`~`[9]` 로 있다.
