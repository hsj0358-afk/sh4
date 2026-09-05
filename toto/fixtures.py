"""--demo 용 오프라인 샘플 데이터.

네트워크 없이도 정규화 → 분석 → 차트 → HTML 전 구간을 실제로 돌려볼 수 있게
14경기 분량의 그럴듯한 데이터를 생성한다. **실제 배당/성적이 아니다.**
"""
from __future__ import annotations

import random

from .models import (FormEntry, H2H, H2HEntry, Match, TeamProfile, TeamRef,
                     TeamStats)

# (리그키, 리그명, 홈, 원정) — 한글 팀명은 data/teams.yaml 에 있는 표기를 쓴다
_FIXTURES = [
    ("epl", "프리미어리그", "맨체스터시티", "번리"),
    ("epl", "프리미어리그", "아스날", "토트넘"),
    ("epl", "프리미어리그", "리버풀", "에버튼"),
    ("epl", "프리미어리그", "첼시", "브라이튼"),
    ("laliga", "라리가", "레알마드리드", "헤타페"),
    ("laliga", "라리가", "바르셀로나", "세비야"),
    ("laliga", "라리가", "아틀레티코마드리드", "발렌시아"),
    ("bundesliga", "분데스리가", "바이에른뮌헨", "마인츠"),
    ("bundesliga", "분데스리가", "도르트문트", "프라이부르크"),
    ("seriea", "세리에A", "인터밀란", "레체"),
    ("seriea", "세리에A", "유벤투스", "토리노"),
    ("ligue1", "리그앙", "파리생제르맹", "낭트"),
    ("kleague1", "K리그1", "울산HD", "대구FC"),
    ("jleague", "J리그", "비셀고베", "쇼난벨마레"),
]

_STRENGTHS = [
    "Scoring goals from set pieces", "Keeping possession", "Defending aerially",
    "Creating chances through the middle", "Counter attacking",
    "Finishing from long shots", "Pressing high up the pitch",
    "Attacking down the wings",
]
_WEAKNESSES = [
    "Defending set pieces", "Conceding on the counter attack",
    "Defending aerial balls", "Keeping the ball under pressure",
    "Defending the box", "Poor discipline - fouls conceded",
    "Struggles against long balls",
]
_STYLES = [
    "Plays short passes", "Attempts through balls often", "Plays direct football",
    "Builds patiently from the back", "Uses the wings frequently",
]


def _stats(rng: random.Random, strong: bool) -> TeamStats:
    played = rng.randint(20, 28)
    ppg = rng.uniform(1.8, 2.5) if strong else rng.uniform(0.6, 1.5)
    points = int(ppg * played)
    wins = int(points / 3.2)
    draws = max(0, min(played - wins, points - wins * 3))
    losses = max(0, played - wins - draws)
    gf_pg = rng.uniform(1.9, 2.7) if strong else rng.uniform(0.7, 1.4)
    ga_pg = rng.uniform(0.6, 1.1) if strong else rng.uniform(1.3, 2.1)
    home_played = played // 2
    away_played = played - home_played
    # 최근 N경기 표본 — 실제 수집에서는 경기 상세를 합산한 값이 들어온다.
    # 여기서는 렌더링 경로를 확인하려고 같은 모양의 난수를 만든다.
    recent = 6
    npxg_pg = gf_pg * rng.uniform(0.8, 1.1)
    npxga_pg = ga_pg * rng.uniform(0.8, 1.1)
    shots_pg = rng.uniform(14, 19) if strong else rng.uniform(8, 12.5)
    sot_pg = rng.uniform(5.5, 7.5) if strong else rng.uniform(2.6, 4.2)
    return TeamStats(
        rank=rng.randint(1, 6) if strong else rng.randint(10, 20),
        played=played, wins=wins, draws=draws, losses=losses,
        goals_for=int(gf_pg * played), goals_against=int(ga_pg * played),
        points=points,
        home_played=home_played,
        home_points=int(ppg * home_played * rng.uniform(1.05, 1.25)),
        away_played=away_played,
        away_points=int(ppg * away_played * rng.uniform(0.7, 0.95)),
        shots_pg=shots_pg,
        shots_on_target_pg=sot_pg,
        possession=rng.uniform(56, 66) if strong else rng.uniform(38, 50),
        pass_success=rng.uniform(84, 90) if strong else rng.uniform(72, 80),
        aerials_won_pg=rng.uniform(9, 16),
        tackles_pg=rng.uniform(13, 19),
        interceptions_pg=rng.uniform(7, 12),
        dribbles_pg=rng.uniform(6, 12),
        fouls_pg=rng.uniform(8, 13),
        rating=rng.uniform(6.9, 7.3) if strong else rng.uniform(6.4, 6.75),
        xg_pg_raw=gf_pg * rng.uniform(0.85, 1.15),
        xga_pg_raw=ga_pg * rng.uniform(0.85, 1.15),
        # 시즌 통계 피드 (누계)
        set_piece_goals=round(gf_pg * played * rng.uniform(0.15, 0.35)),
        set_piece_goals_conceded=round(ga_pg * played * rng.uniform(0.15, 0.35)),
        penalties_won=rng.randint(1, 7),
        penalties_conceded=rng.randint(1, 7),
        yellow_cards=rng.randint(30, 70),
        red_cards=rng.randint(0, 4),
        accurate_crosses_pg=rng.uniform(2.5, 6.5),
        accurate_long_balls_pg=rng.uniform(4.0, 9.0),
        # 경기 상세 집계 (최근 N경기 합계)
        recent_matches=recent,
        npxg_recent=npxg_pg * recent,
        npxga_recent=npxga_pg * recent,
        xgot_recent=npxg_pg * recent * rng.uniform(0.9, 1.25),
        xgot_against_recent=npxga_pg * recent * rng.uniform(0.9, 1.25),
        xg_open_play_recent=npxg_pg * recent * rng.uniform(0.6, 0.8),
        xg_set_play_recent=npxg_pg * recent * rng.uniform(0.15, 0.3),
        shots_recent=shots_pg * recent,
        shots_against_recent=rng.uniform(9, 16) * recent,
        shots_on_target_recent=sot_pg * recent,
        shots_on_target_against_recent=rng.uniform(3, 6) * recent,
        shots_inside_box_recent=shots_pg * recent * rng.uniform(0.55, 0.75),
        shots_outside_box_recent=shots_pg * recent * rng.uniform(0.25, 0.45),
    )


def _form(rng: random.Random, strong: bool, opponents: list[str]) -> list[FormEntry]:
    out = []
    weights = [0.62, 0.22, 0.16] if strong else [0.25, 0.25, 0.50]
    for i in range(5):
        result = rng.choices(["W", "D", "L"], weights=weights)[0]
        gf = rng.randint(1, 4) if result == "W" else (rng.randint(0, 2) if result == "D" else rng.randint(0, 1))
        ga = rng.randint(0, gf - 1) if result == "W" and gf > 0 else (
            gf if result == "D" else rng.randint(gf + 1, gf + 3))
        out.append(FormEntry(
            date=f"2026-0{7 if i > 2 else 8}-{28 - i * 6:02d}",
            opponent=rng.choice(opponents), home=(i % 2 == 0),
            goals_for=gf, goals_against=ga, result=result))
    return out


def build_demo_matches() -> list[Match]:
    """14경기 데모 데이터 생성 (시드 고정 — 실행할 때마다 동일)."""
    rng = random.Random(20260808)
    matches: list[Match] = []
    pool = [f[2] for f in _FIXTURES] + [f[3] for f in _FIXTURES]

    for i, (key, ko, home_ko, away_ko) in enumerate(_FIXTURES, start=1):
        home_strong = i % 3 != 0          # 대체로 홈이 강팀, 가끔 뒤집기
        away_strong = not home_strong and i % 4 == 0

        home_ref = TeamRef(name_ko=home_ko, canonical=home_ko, display=home_ko)
        away_ref = TeamRef(name_ko=away_ko, canonical=away_ko, display=away_ko)

        hp = TeamProfile(team=home_ref, league=key, stats=_stats(rng, home_strong),
                         source_ok=True)
        ap = TeamProfile(team=away_ref, league=key, stats=_stats(rng, away_strong),
                         source_ok=True)
        for profile, strong in ((hp, home_strong), (ap, away_strong)):
            profile.strengths = rng.sample(_STRENGTHS, 3)
            profile.weaknesses = rng.sample(_WEAKNESSES, 3)
            profile.style_of_play = rng.sample(_STYLES, 2)
            profile.form = _form(rng, strong, [p for p in pool if p != profile.team.display])
            if rng.random() < 0.6:
                profile.missing_players = [
                    {"player": f"선수 {rng.randint(1, 30)}", "reason": rng.choice(
                        ["부상 (햄스트링)", "출전 정지", "부상 (발목)"])}
                    for _ in range(rng.randint(1, 3))]

        match = Match(
            no=i, league=key, league_ko=ko,
            home=home_ref, away=away_ref,
            kickoff_kst=f"2026-08-{8 + (i % 3):02d} {(17 + i % 5)}:00",
        )
        match.home_profile, match.away_profile = hp, ap

        # 배당은 팀 전력에 대략 맞춘다
        base = 1.45 if home_strong else (3.6 if away_strong else 2.5)
        match.odds.home = round(base * rng.uniform(0.92, 1.12), 2)
        match.odds.draw = round(rng.uniform(3.3, 4.6), 2)
        match.odds.away = round((6.2 if home_strong else 2.3) * rng.uniform(0.9, 1.15), 2)
        match.odds.ah_line = round(rng.choice([-1.5, -1.0, -0.75, -0.5, 0.0, 0.5]), 2)
        match.odds.ah_home = round(rng.uniform(1.8, 2.05), 2)
        match.odds.ah_away = round(rng.uniform(1.8, 2.05), 2)
        match.odds.ou_line = 2.5
        match.odds.ou_over = round(rng.uniform(1.75, 2.1), 2)
        match.odds.ou_under = round(rng.uniform(1.75, 2.1), 2)
        match.odds.source = "demo"
        match.odds.fetched_at = "2026-08-08T09:00:00+00:00"

        # 상대전적
        entries = []
        for j in range(rng.randint(3, 8)):
            hg, ag = rng.randint(0, 4), rng.randint(0, 3)
            entries.append(H2HEntry(
                date=f"202{5 - j // 3}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                home_team=home_ko if j % 2 == 0 else away_ko,
                away_team=away_ko if j % 2 == 0 else home_ko,
                home_goals=hg, away_goals=ag, competition=ko))
        h2h = H2H(entries=entries, source_ok=True)
        for e in entries:
            if e.home_goals == e.away_goals:
                h2h.draws += 1
            else:
                winner = e.home_team if e.home_goals > e.away_goals else e.away_team
                if winner == home_ko:
                    h2h.home_wins += 1
                else:
                    h2h.away_wins += 1
        match.h2h = h2h

        # 한 경기는 일부러 데이터를 비워 '수집 실패' 표시를 검증한다
        if i == 7:
            match.away_profile.source_ok = False
            match.away_profile.strengths = []
            match.away_profile.weaknesses = []
            match.away_profile.style_of_play = []
            match.away_profile.form = []
            match.h2h = H2H()
            match.notes.append("데모: 원정팀 상세 데이터 수집 실패 상황을 재현한 경기입니다.")

        matches.append(match)
    return matches
