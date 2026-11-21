"""통계 모델 기준선 — 득점 기반 독립 포아송 (Phase 1 · 모델 패널의 첫 단계).

시즌 경기 색인의 **최종 스코어**만으로 팀마다 공격·수비 수준을 매기고,
이 경기의 양 팀 기대 득점(λ)과 승/무/패 확률을 만든다. **모델 산출값**이다
(`provenance = MODEL`).

    그 경기 이전 경기 (matches_before) → 리그 평균 득점(홈·원정)
      → 팀 공격·수비 (상대 수준으로 나눈다 · 리그 평균 쪽으로 당긴다)
      → λ_홈 = 리그 홈 평균 × 홈팀 공격 × 원정팀 수비
        λ_원정 = 리그 원정 평균 × 원정팀 공격 × 홈팀 수비
      → 독립 포아송 → 승/무/패 · 가장 그럴듯한 스코어

## 이것이 무엇이 아닌지부터

- **시장 확률과 합치지 않는다.** 저쪽(`Match.probs`)은 시장이 매긴 값이고
  이쪽은 득점 기록에서 만든 모델값이다. 서로 보정하지 않는다. 이 모듈은
  `predict` 를 import 하지 않는다(테스트).
- **패널에 주지 않는다** (이번 단계). 리포트의 참고값과 백테스트에만 쓴다.
  `panel`·`panelpacket`·`moderator` 등이 이 모듈을 import 하지 않는다.
- **추천이 아니다.** 확률을 낼 뿐 승/무/패를 고르지 않는다 (§1-3).
  `favorite` 은 **채점용**이다.
- Dixon-Coles 가 아니다. 무승부 보정이 없어 무승부 확률이 낮게 나오는 쪽으로
  치우칠 수 있다.

## 시점 — 미래를 섞지 않는다

입력은 `models.matches_before(season, as_of)` **하나**로 자른다 (§1-1-4).
그 경기와 같은 시각 이후의 경기는 들어오지 않는다. 모집단은
`models.scope_to_competition()` 으로 그 대회만 남긴다 (§1-30) — 휴식 계산용
유럽대회 경기(§1-65)가 국내리그 평균에 섞이지 않는다. 대회를 모르거나
색인에 대회 표시가 없으면 **만들지 않는다** — 두 리그가 한 평균으로 섞인다.

## 선택지 (백테스트로 고른다)

- `venue_split` — 홈팀은 **홈 경기**의 공격·수비, 원정팀은 **원정 경기**의
  공격·수비를 쓴다. 장소 표본이 작으므로 그 팀의 전체 수준 쪽으로 당긴다.
- `half_life_days` — 최근 경기에 가중치를 더 준다 (반감기 · 일). 없으면
  시즌 전체를 같은 무게로 본다.
- `shrink_matches` — 리그 평균 수준의 가상 경기 수. 표본이 작은 시즌 초에
  1~2경기로 극단값이 나오지 않게 한다. 가중치를 주면 유효 표본이 줄어들어
  같은 `shrink_matches` 라도 당김이 세진다 — 두 선택지를 함께 견준다.

이 값들은 **운영용 기준이며 통계적으로 검증된 기준이 아니다** — 기본값은
가장 단순한 형태이고, `tools/backtest_statmodel.py` 의 결과로 정한다.
같은 입력이면 같은 답이다 (난수 없음 · 반복 횟수 고정).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import marketscore, models
from .models import MODEL

OUTCOMES = ("H", "D", "A")

# 공격·수비를 서로의 상대 수준으로 나눠 맞추는 반복 횟수. 고정해 두어
# 결과가 결정적이다.
ITERATIONS = 12

REASON_NO_TARGET = "대상 대회 미상"
REASON_UNLABELED = "색인에 대회 표시 없음 — 리그를 가를 수 없습니다"
REASON_NO_ASOF = "기준 시각 없음"
REASON_LEAGUE_SMALL = "리그 표본 부족"
REASON_TEAM_SMALL = "팀 표본 부족"


@dataclass(frozen=True)
class ModelConfig:
    venue_split: bool = False
    half_life_days: float | None = None
    shrink_matches: float = 5.0
    min_team_matches: int = 3
    min_league_matches: int = 20

    @property
    def name(self) -> str:
        parts = ["venue" if self.venue_split else "overall"]
        if self.half_life_days:
            parts.append(f"hl{self.half_life_days:g}")
        parts.append(f"k{self.shrink_matches:g}")
        return "-".join(parts)


def config_from(settings) -> ModelConfig:
    """`config_toto.yaml` 의 `analysis.statmodel` → `ModelConfig`.

    읽을 수 없는 값은 기본값을 쓴다 — 설정이 깨졌다고 리포트가 죽지 않는다.
    """
    raw = ((getattr(settings, "analysis", None) or {}).get("statmodel")
           or {})
    base = ModelConfig()

    def num(key, default, cast):
        try:
            value = raw.get(key, default)
            return default if value is None else cast(value)
        except (TypeError, ValueError):
            return default

    hl = raw.get("half_life_days")
    try:
        hl = float(hl) if hl not in (None, "", 0) else None
    except (TypeError, ValueError):
        hl = None
    return ModelConfig(
        venue_split=bool(raw.get("venue_split", base.venue_split)),
        half_life_days=hl if hl and hl > 0 else None,
        shrink_matches=max(0.0, num("shrink_matches", base.shrink_matches, float)),
        min_team_matches=max(1, num("min_team_matches", base.min_team_matches, int)),
        min_league_matches=max(1, num("min_league_matches",
                                      base.min_league_matches, int)))


@dataclass(frozen=True)
class Forecast:
    home_goals: float              # 홈 기대 득점 (λ)
    away_goals: float
    p_home: float                  # 0~9골 절단 — 합이 1 보다 조금 작을 수 있다
    p_draw: float
    p_away: float
    score: tuple                   # 가장 그럴듯한 스코어 (홈, 원정)
    score_probability: float
    home_matches: int              # 그 팀의 이전 경기 수 (이 대회)
    away_matches: int
    home_venue_matches: int        # 홈팀의 이전 홈 경기 · 원정팀의 이전 원정 경기
    away_venue_matches: int
    league_matches: int
    league_home_avg: float
    league_away_avg: float
    config: str = ""
    provenance: str = MODEL

    @property
    def probs(self) -> dict:
        return {"H": self.p_home, "D": self.p_draw, "A": self.p_away}

    @property
    def favorite(self) -> str:
        """확률이 가장 높은 결과. **채점용이다 — 추천이 아니다** (§1-3)."""
        return max(OUTCOMES, key=lambda o: self.probs[o])

    @property
    def tail_mass(self) -> float:
        return max(0.0, 1.0 - self.p_home - self.p_draw - self.p_away)


# --------------------------------------------------------------------------
# 입력 고르기
# --------------------------------------------------------------------------
def _usable(m) -> bool:
    return (m.finished and m.home_goals is not None and m.away_goals is not None
            and bool(m.home_team) and bool(m.away_team))


def history(season, competition: str | None, as_of) -> tuple:
    """(그 경기 이전의 그 대회 종료 경기, 못 고른 사유). 사유가 있으면 목록은 비었다."""
    if as_of is None:
        return [], REASON_NO_ASOF
    if not competition:
        return [], REASON_NO_TARGET
    scoped, why = models.scope_to_competition(list(season or []), competition)
    if why:
        return [], REASON_UNLABELED
    return [m for m in models.matches_before(scoped, as_of) if _usable(m)], ""


def _weight(m, as_of, half_life: float | None) -> float:
    if not half_life:
        return 1.0
    try:
        age = (as_of - m.kickoff).total_seconds() / 86400.0
    except TypeError:               # matches_before 가 이미 걸렀지만 방어한다
        return 1.0
    return 0.5 ** (max(age, 0.0) / half_life)


# --------------------------------------------------------------------------
# 맞춤
# --------------------------------------------------------------------------
def _ratings(rows, mu_h: float, mu_a: float, k: float) -> tuple:
    """팀 공격·수비 수준. 1 = 리그 평균. 상대 수준으로 나누고 리그 평균 쪽으로 당긴다.

    rows = [(홈, 원정, 홈골, 원정골, 가중치)].
    """
    teams = sorted({t for r in rows for t in (r[0], r[1])})
    att = {t: 1.0 for t in teams}
    dfn = {t: 1.0 for t in teams}
    mu = (mu_h + mu_a) / 2.0
    for _ in range(ITERATIONS):
        num_a = {t: k * mu for t in teams}
        den_a = {t: k * mu for t in teams}
        for h, a, hg, ag, w in rows:
            num_a[h] += w * hg
            den_a[h] += w * mu_h * dfn[a]
            num_a[a] += w * ag
            den_a[a] += w * mu_a * dfn[h]
        att = {t: num_a[t] / den_a[t] for t in teams}
        num_d = {t: k * mu for t in teams}
        den_d = {t: k * mu for t in teams}
        for h, a, hg, ag, w in rows:
            num_d[h] += w * ag
            den_d[h] += w * mu_a * att[a]
            num_d[a] += w * hg
            den_d[a] += w * mu_h * att[h]
        dfn = {t: num_d[t] / den_d[t] for t in teams}
    return att, dfn


def _venue_rating(rows, team: str, home: bool, overall: float, opp: dict,
                  base: float, k: float, attack: bool) -> float:
    """그 장소 경기만의 수준. 표본이 작으면 그 팀 전체 수준(`overall`) 쪽으로 당긴다."""
    num = k * base * overall
    den = k * base
    for h, a, hg, ag, w in rows:
        if (h if home else a) != team:
            continue
        other = a if home else h
        scored, conceded = (hg, ag) if home else (ag, hg)
        num += w * (scored if attack else conceded)
        den += w * base * opp.get(other, 1.0)
    return num / den if den > 0 else overall


def forecast(season, competition: str | None, home: str, away: str, as_of,
             config: ModelConfig | None = None) -> tuple:
    """(Forecast | None, 못 만든 사유). 사유는 사람이 읽을 한 줄이다."""
    past, why = history(season, competition, as_of)
    if why:
        return None, why
    return forecast_from(past, home, away, as_of, config)


def forecast_from(past, home: str, away: str, as_of,
                  config: ModelConfig | None = None) -> tuple:
    """`history()` 가 고른 경기로 맞춘다. 백테스트가 안마다 다시 고르지 않게 나눴다.

    `past` 는 **이미 시점·모집단이 잘린** 목록이어야 한다 — 여기서 다시
    자르지 않는다.
    """
    cfg = config or ModelConfig()
    if len(past) < cfg.min_league_matches:
        return None, (f"{REASON_LEAGUE_SMALL} ({len(past)}경기, "
                      f"최소 {cfg.min_league_matches})")
    rows = [(m.home_team, m.away_team, m.home_goals, m.away_goals,
             _weight(m, as_of, cfg.half_life_days)) for m in past]
    n_home = sum(1 for r in rows if home in (r[0], r[1]))
    n_away = sum(1 for r in rows if away in (r[0], r[1]))
    if min(n_home, n_away) < cfg.min_team_matches:
        return None, (f"{REASON_TEAM_SMALL} (홈 {n_home} · 원정 {n_away}경기, "
                      f"최소 {cfg.min_team_matches})")
    total_w = sum(r[4] for r in rows)
    mu_h = sum(r[4] * r[2] for r in rows) / total_w
    mu_a = sum(r[4] * r[3] for r in rows) / total_w
    if mu_h <= 0 or mu_a <= 0:
        return None, "리그 평균 득점이 0 입니다"
    k = cfg.shrink_matches
    att, dfn = _ratings(rows, mu_h, mu_a, k)
    if cfg.venue_split:
        att_h = _venue_rating(rows, home, True, att[home], dfn, mu_h, k, True)
        def_h = _venue_rating(rows, home, True, dfn[home], att, mu_a, k, False)
        att_a = _venue_rating(rows, away, False, att[away], dfn, mu_a, k, True)
        def_a = _venue_rating(rows, away, False, dfn[away], att, mu_h, k, False)
    else:
        att_h, def_h, att_a, def_a = att[home], dfn[home], att[away], dfn[away]
    lam_h = mu_h * att_h * def_a
    lam_a = mu_a * att_a * def_h
    p_h, p_d, p_a = marketscore._outcome_probs(lam_h, lam_a)
    score, p_score = marketscore.market_mode(lam_h, lam_a)
    return Forecast(
        home_goals=lam_h, away_goals=lam_a, p_home=p_h, p_draw=p_d, p_away=p_a,
        score=tuple(score), score_probability=p_score,
        home_matches=n_home, away_matches=n_away,
        home_venue_matches=sum(1 for r in rows if r[0] == home),
        away_venue_matches=sum(1 for r in rows if r[1] == away),
        league_matches=len(rows), league_home_avg=mu_h, league_away_avg=mu_a,
        config=cfg.name), ""


def for_match(match, report, settings=None) -> tuple:
    """회차 경기 → (Forecast | None, 사유). 기준 시각은 `kickoff_kst` 다."""
    home = getattr(match.home, "canonical", "") or ""
    away = getattr(match.away, "canonical", "") or ""
    if not home or not away:
        return None, "팀 정규명 없음"
    season = getattr(report, "season_matches", None) or []
    if not season:
        return None, "시즌 경기 색인 없음"
    return forecast(season, getattr(match, "league", "") or "", home, away,
                    models.as_of_from_match(match),
                    config_from(settings) if settings is not None else None)
