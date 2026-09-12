"""회차 기록 축적 — 배당·확률·픽을 남기고, 나중에 결과를 채운다.

**왜 필요한가.** 이 프로그램은 회차마다 독립적으로 그 시점의 자료를 가져오고,
리포트는 실행이 끝나면 그 회차의 상태만 담는다. 그래서 지금까지는 "이 배당에
이 확률이었고 실제로는 이렇게 끝났다" 를 되짚을 방법이 없었다 — 지침 §8 의
회차로그 한 줄도 화면에 찍히기만 하고 저장되지 않았다.

지나간 회차는 되돌릴 수 없다. 그래서 **매 실행이 그 회차를 남긴다.**

    data/rounds.csv          회차 1줄  (지침 §8 스키마 + 승산)
    data/round_matches.csv   경기 14줄 (배당 · 내재확률 · argmax 픽 · 결과)

**결과는 새로 수집하지 않는다.** 다음 회차를 돌릴 때 이미 받아 온 시즌 경기
색인(`Report.season_matches`)에 지난 회차의 경기가 종료된 채로 들어 있다.
그것으로 채운다 — 새 소스를 붙이지 않는다.

규칙:

  · **재실행이 중복을 만들지 않는다.** 같은 회차 행은 교체한다.
  · **없는 값은 빈칸**이다. 0 으로 채우지 않는다 (§1-5).
  · **자동 정산은 확실할 때만.** 팀 짝이 맞고 종료됐고 날짜가 가까울 때만
    채운다. 애매하면 비워 둔다 — 틀린 결과를 채우는 것이 비어 있는 것보다
    나쁘다.
  · `--demo` 는 기록하지 않는다. 난수 표본이라 축적할 값이 아니다.
  · 파일은 **UTF-8 BOM** 으로 쓴다. 한국어 윈도우의 엑셀이 BOM 없는 UTF-8
    을 cp949 로 읽어 깨뜨린다 (§1-7 과 같은 계열의 함정).

## 정산은 두 경로에서 같은 함수를 쓴다 (Phase 6-C-2)

예전에는 결과를 채우려면 회차 하나를 **12분짜리 전체 수집으로 다시** 돌려야
했다 — `record()` 안에서만 정산이 일어났기 때문이다. 이제 결과만 채우는
입구가 따로 있고, 둘이 **같은 `settle_rows()`** 를 쓴다.

    [1] 수집        → record()      → settle_rows(모든 회차)
    --settle-round  → settle(회차)  → settle_rows(그 회차만)

짝을 고르는 순서도 바뀌었다. **① `match_id` 정확일치 → ② 팀·날짜 폴백.**
`SeasonMatch.match_id` 는 FotMob 이 준 권위 있는 값인데 예전에는 `_settle()`
이 그것을 손에 쥐고도 CSV 경계에서 버렸다. 이제 경기 전 스냅샷에 함께 싣고,
정산 때 그 값을 먼저 본다 — 팀 별칭이 바뀌어도(§1-22) 그 행은 계속 이어진다.
"""
from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .models import (Report, SeasonMatch, find_season_match,
                     find_season_match_by_id)
from .settings import ROOT

log = logging.getLogger("toto")

ROUND_FILE = ROOT / "data" / "rounds.csv"
MATCH_FILE = ROOT / "data" / "round_matches.csv"

# 엑셀이 cp949 로 오해하지 않도록 BOM 을 붙인다.
_ENCODING = "utf-8-sig"

ROUND_FIELDS = (
    "round", "recorded_at", "matches", "expected", "sigma", "z",
    "p_ge11", "verdict", "sum_draw", "incomplete", "settled_at",
    "hits", "settled_matches",
)

MATCH_FIELDS = (
    "round", "recorded_at", "no", "league", "kickoff_kst",
    "home", "away", "home_canon", "away_canon", "match_id",
    "odds_home", "odds_draw", "odds_away",
    "p_home", "p_draw", "p_away", "pick", "p_pick", "gap", "toss_up",
    "home_goals", "away_goals", "result", "pick_hit", "settled_at",
)

# 정산에 쓸 수 있는 날짜 오차. 회차의 경기는 며칠 안에 몰려 있고, 같은 팀
# 짝이 시즌에 두 번(홈/원정) 나오므로 날짜로 갈라야 한다.
_SETTLE_WINDOW = timedelta(days=4)

# 경기가 끝난 뒤 `_settle()` 이 채우는 칸. **나머지는 전부 사전 스냅샷**이고
# 경기가 시작한 뒤에는 바꾸지 않는다 (Phase 6-B).
#
# 배당·확률·픽은 **그 시점의 관측**이다. 같은 회차를 결과가 나온 뒤 다시
# 돌렸다는 이유로 새 값을 덮어쓰면, 그 회차는 시장 캘리브레이션 표본으로
# 쓸 수 없게 된다 — 사후 배당으로 사후 결과를 맞히는 셈이기 때문이다.
RESULT_FIELDS = ("home_goals", "away_goals", "result", "pick_hit",
                 "settled_at")

# `match_id` 는 결과 칸이 아니지만 **비어 있을 때 한 번은 채울 수 있다**
# (Phase 6-C-2). 옛 행에는 이 열이 아예 없었으므로, 정산하면서 권위 있는
# 값을 처음 확보하면 그때 싣는다. **이미 값이 있으면 바꾸지 않는다** —
# 고쳐 주는 것이 아니라 없던 것을 채우는 것이다.
ID_FIELD = "match_id"


def _fmt(value, spec: str = "") -> str:
    """숫자 → 문자열. **없으면 빈칸**이다 (0 이 아니다)."""
    if value is None:
        return ""
    if not spec:
        return str(value)
    try:
        return format(value, spec)
    except (TypeError, ValueError):
        return ""


def _read(path: Path, fields: tuple[str, ...]) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding=_ENCODING, newline="") as fh:
            rows = [dict(r) for r in csv.DictReader(fh)]
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("회차 기록을 읽지 못했습니다 (%s): %s", path.name, exc)
        return []
    # 열이 늘어난 뒤에도 옛 파일을 읽을 수 있어야 한다.
    return [{k: r.get(k, "") or "" for k in fields} for r in rows]


def _write(path: Path, fields: tuple[str, ...], rows: list[dict]) -> bool:
    """**옆에 다 쓴 뒤 한 번에 바꿔 끼운다.**

    예전에는 대상 파일을 곧바로 열어(`"w"`) 잘라내고 썼다. 도중에 예외가
    나면 축적해 온 기록이 **반쯤 잘린 채로 남는다** — 되돌릴 수 없는 자료라
    그건 실패가 아니라 손실이다. `os.replace` 는 같은 파일시스템 안에서
    원자적이라(윈도우 포함) 덮어쓰기가 끝나거나 아예 안 일어나거나 둘 중
    하나가 된다.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding=_ENCODING, newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(fields))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fields})
        os.replace(tmp, path)
        return True
    except OSError as exc:
        log.warning("회차 기록을 쓰지 못했습니다 (%s): %s", path.name, exc)
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def _kickoff_date(text: str) -> datetime | None:
    """'2026-08-09 18:00' → datetime. 못 읽으면 None (지어내지 않는다)."""
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:len(fmt) + 2].strip(), fmt)
        except ValueError:
            continue
    return None


def _started(kickoff_kst: str, now: datetime) -> bool:
    """이 경기가 이미 시작했나.

    **시각을 모르면 시작한 것으로 본다** — 모르는 채로 사전 값을 갈아
    끼우는 것보다 보존하는 편이 안전하다.
    """
    kickoff = _kickoff_date(kickoff_kst)
    return kickoff is None or now >= kickoff


def _merge_rows(old: list[dict], new: list[dict],
                now: datetime) -> tuple[list[dict], int]:
    """같은 회차의 기존 행과 이번 행을 합친다 → (행 목록, 보존한 수).

    예전에는 같은 회차 행을 **통째로 교체**해서, 결과가 나온 뒤 다시 돌리면
    `odds_*`·`p_*` 가 사후 값으로 바뀌었다 (Phase 6-A 에서 찾은 누수 지점).
    이제 경기가 시작한 뒤에는 **기존 행을 그대로 둔다** — 결과 칸은
    `_settle()` 이 나중에 채우므로 아무것도 잃지 않는다.

    이번 회차 목록에서 빠진 옛 행도 버리지 않는다. 기록은 축적이 목적이다.
    """
    kept = {r.get("no", ""): r for r in old}
    out, frozen = [], 0
    for row in new:
        prev = kept.pop(row.get("no", ""), None)
        if prev is not None and _started(row.get("kickoff_kst", ""), now):
            out.append(prev)
            frozen += 1
        else:
            out.append(row)
    out.extend(kept.values())
    return out, frozen


def _prematch_id(report: Report, match) -> str:
    """경기 전 스냅샷에 실을 소스 경기 ID (Phase 6-C-2).

    **새로 수집하지 않는다.** 이번 실행이 이미 받아 온 시즌 색인에 이 경기가
    예정 상태로 들어 있으므로(실측 260052 는 14/14) 그때 ID 를 함께 적어 둔다.
    나중에 정산할 때 팀명·날짜로 다시 가릴 이유가 없어진다.

    못 가리면 **빈 문자열**이다 — ID 를 지어내지 않는다 (§1-5).
    """
    return getattr(find_season_match(
        report.season_matches or [], match.home.canonical or "",
        match.away.canonical or "", _kickoff_date(match.kickoff_kst or ""),
        _SETTLE_WINDOW), "match_id", "") or ""


def _match_rows(report: Report) -> list[dict]:
    stamp = report.generated_at
    out = []
    for m in report.matches:
        odds, probs = m.odds, m.probs
        out.append({
            "round": report.round_id or "",
            "recorded_at": stamp,
            "no": str(m.no),
            "league": m.league_ko or m.league or "",
            "kickoff_kst": m.kickoff_kst or "",
            "home": m.home.display, "away": m.away.display,
            "home_canon": m.home.canonical or "",
            "away_canon": m.away.canonical or "",
            "match_id": _prematch_id(report, m),
            "odds_home": _fmt(getattr(odds, "home", None), ".2f"),
            "odds_draw": _fmt(getattr(odds, "draw", None), ".2f"),
            "odds_away": _fmt(getattr(odds, "away", None), ".2f"),
            "p_home": _fmt(getattr(probs, "home", None), ".4f"),
            "p_draw": _fmt(getattr(probs, "draw", None), ".4f"),
            "p_away": _fmt(getattr(probs, "away", None), ".4f"),
            "pick": probs.pick if probs else "",
            "p_pick": _fmt(getattr(probs, "p_pick", None), ".4f"),
            "gap": _fmt(getattr(probs, "gap", None), ".4f"),
            "toss_up": ("1" if probs.toss_up else "0") if probs else "",
            "home_goals": "", "away_goals": "", "result": "",
            "pick_hit": "", "settled_at": "",
        })
    return out


def _round_row(report: Report) -> dict | None:
    v = report.verdict
    if v is None or not v.n:
        return None
    sum_draw = sum(m.probs.draw for m in report.matches if m.probs is not None)
    return {
        "round": report.round_id or "",
        "recorded_at": report.generated_at,
        "matches": str(v.n),
        "expected": f"{v.expected:.2f}", "sigma": f"{v.sigma:.2f}",
        "z": f"{v.z:+.2f}", "p_ge11": f"{v.p_ge11:.4f}",
        "verdict": v.verdict_ko,
        "sum_draw": f"{sum_draw:.2f}",
        "incomplete": "1" if v.incomplete else "0",
        "settled_at": "", "hits": "", "settled_matches": "",
    }


# 미정산 사유. **창을 가로질러 같은 문구를 쓴다** — 사유별로 세어 보여
# 주려면 문자열이 하나여야 한다 (§1-1-10 의 `_merge_missing` 과 같은 뜻).
NO_CANON = "정규명이 비어 있습니다 (수집 때 팀명 매칭 실패)"
NO_FINISHED = "색인에 종료된 같은 경기가 없습니다"
NO_PICK = "팀·날짜로 가리지 못했습니다 (후보 0 또는 2개 이상)"


@dataclass
class SettleOutcome:
    """정산 한 번의 결과. **숫자의 뜻이 겹치지 않게 정의한다** (§14).

        rows      = already + settled_now + unsettled          (언제나 성립)
        matched   = 색인에서 종료 경기로 **확인된** 행 (이미 정산된 행 포함)

    `matched` 만 다른 셋과 겹친다. 겹친다는 사실을 여기 적어 둔다 — 로그에서
    네 수를 나란히 보여 주므로 읽는 사람이 합을 맞춰 볼 수 있어야 한다.
    """
    round_id: str = ""
    rows: int = 0
    matched: int = 0
    settled_now: int = 0
    already: int = 0
    unsettled: int = 0
    linked_ids: int = 0                       # 이번에 match_id 를 처음 채운 행
    by_id: int = 0                            # match_id 로 이은 행
    reasons: dict = field(default_factory=dict)
    conflicts: list = field(default_factory=list)

    def note(self, reason: str) -> None:
        self.reasons[reason] = self.reasons.get(reason, 0) + 1


def _ready(season) -> list:
    """스코어가 있는 종료 경기만. 정산 후보는 이것뿐이다."""
    return [sm for sm in (season or [])
            if sm.finished and sm.home_goals is not None
            and sm.away_goals is not None]


def _lookup(row: dict, ready: list) -> tuple[object, str, bool]:
    """이 행에 붙일 종료 경기. (경기|None, 사유, ID 로 이었나).

    **① match_id 정확일치 → ② 팀·날짜 폴백** 순이다 (§2). 두 조회 모두
    `models` 의 함수를 쓴다 — 중복 ID 를 거부하는 규칙 같은 것을 여기에
    다시 적으면 두 곳이 어긋난다 (§1-8).

    ID 가 맞으면 팀명·킥오프를 다시 보지 않는다 — 팀 별칭이 바뀌어도
    (§1-22 의 `Deportivo` 처럼) 그 행은 계속 이어진다. ID 가 없는 옛 행만
    폴백을 탄다.
    """
    mid = (row.get(ID_FIELD) or "").strip()
    if mid:
        sm = find_season_match_by_id(ready, mid, finished_only=True)
        if sm is not None:
            return sm, "", True
        # ID 가 있는데 색인에 종료 경기로 없다 = 아직 안 끝났거나 이번
        # 색인이 그 리그를 담지 않았다. **팀명으로 다시 찾지 않는다** —
        # 권위 있는 ID 가 아니라고 말하고 있는데 약한 단서로 뒤집지 않는다.
        return None, NO_FINISHED, False

    home, away = row.get("home_canon", ""), row.get("away_canon", "")
    if not home or not away:
        return None, NO_CANON, False
    sm = find_season_match(ready, home, away,
                           _kickoff_date(row.get("kickoff_kst", "")),
                           _SETTLE_WINDOW, finished_only=True)
    # 같은 팀 짝이 둘 이상(홈/원정 두 경기)이고 날짜로 못 가리면 비워 둔다.
    # 틀린 결과를 채우는 것이 비어 있는 것보다 나쁘다.
    return (sm, "", False) if sm is not None else (None, NO_PICK, False)


def _apply(row: dict, sm, stamp: str) -> None:
    """결과 5칸을 채운다. **그 밖의 칸은 손대지 않는다** (§4)."""
    row["home_goals"] = str(sm.home_goals)
    row["away_goals"] = str(sm.away_goals)
    row["result"] = sm.result or ""
    pick = row.get("pick", "")
    if pick and row["result"]:
        row["pick_hit"] = "1" if pick == row["result"] else "0"
    row["settled_at"] = stamp


def settle_rows(rows: list[dict], season, *, round_id: str | None = None,
                stamp: str | None = None) -> SettleOutcome:
    """**공유 정산 함수** — `[1]` 수집 경로와 `--settle-round` 가 같이 쓴다.

    정산 로직을 두 군데 두지 않는다 (§17). 다른 것은 `round_id` 로 범위를
    좁히느냐뿐이고, 채우는 칸·고르는 규칙·덮어쓰지 않는 규칙은 하나다.

    **새로 수집하지 않는다** — 넘겨받은 색인만 쓴다.
    """
    out = SettleOutcome(round_id=round_id or "")
    ready = _ready(season)
    stamp = stamp or datetime.now().strftime("%Y-%m-%d %H:%M")

    for row in rows:
        if round_id is not None and row.get("round") != round_id:
            continue
        out.rows += 1
        sm, reason, via_id = _lookup(row, ready)
        if sm is not None:
            out.matched += 1
            if via_id:
                out.by_id += 1

        if row.get("result"):
            # **이미 정산된 행은 다시 쓰지 않는다** (§6). 다만 소스가 다른
            # 결과를 말하면 그 사실은 남긴다 — 조용히 덮지도, 조용히
            # 지나치지도 않는다.
            out.already += 1
            if sm is not None and (sm.result or "") != row.get("result"):
                out.conflicts.append(
                    f"{row.get('round','')}회 {row.get('no','')}번 "
                    f"{row.get('home','')}–{row.get('away','')}: "
                    f"기록 {row.get('result')} / 소스 {sm.result}")
            continue

        if sm is None:
            out.unsettled += 1
            out.note(reason)
            continue

        _apply(row, sm, stamp)
        out.settled_now += 1
        if not (row.get(ID_FIELD) or "").strip() and (sm.match_id or ""):
            # 옛 행이 권위 있는 ID 를 **처음** 확보했다 (§4 의 예외).
            row[ID_FIELD] = str(sm.match_id)
            out.linked_ids += 1
    return out


def _roll_up(round_rows: list[dict], match_rows: list[dict]) -> None:
    """회차 행에 정산 결과(적중 수)를 반영한다."""
    by_round: dict[str, list[dict]] = {}
    for row in match_rows:
        by_round.setdefault(row.get("round", ""), []).append(row)
    for rnd in round_rows:
        rows = by_round.get(rnd.get("round", ""), [])
        settled = [r for r in rows if r.get("result")]
        if not settled:
            continue
        rnd["settled_matches"] = str(len(settled))
        rnd["hits"] = str(sum(1 for r in settled if r.get("pick_hit") == "1"))
        rnd["settled_at"] = max(r.get("settled_at", "") for r in settled)


def record(report: Report) -> str:
    """이번 회차를 기록하고 지난 회차를 정산한다. 상태 문자열을 돌려준다."""
    if not report.round_id:
        return "생략 (회차 번호 없음)"
    if report.round_id == "DEMO":
        return "생략 (데모는 기록하지 않습니다)"

    now = datetime.now()
    stored = _read(MATCH_FILE, MATCH_FIELDS)
    match_rows = [r for r in stored if r.get("round") != report.round_id]
    merged, frozen = _merge_rows(
        [r for r in stored if r.get("round") == report.round_id],
        _match_rows(report), now)
    match_rows.extend(merged)

    stored_rounds = _read(ROUND_FILE, ROUND_FIELDS)
    round_rows = [r for r in stored_rounds if r.get("round") != report.round_id]
    mine = [r for r in stored_rounds if r.get("round") == report.round_id]
    this_round = _round_row(report)
    if mine and frozen:
        # 경기 행을 얼렸으면 회차 행도 사전 스냅샷이다 — 승산·합계가 그때의
        # 배당에서 나온 값이라 같이 보존해야 짝이 맞는다. 정산 칸은 아래
        # `_roll_up()` 이 이 행에 그대로 채운다.
        round_rows.extend(mine)
    elif this_round is not None:
        round_rows.append(this_round)
    else:
        round_rows.extend(mine)

    res = settle_rows(match_rows, report.season_matches)
    _roll_up(round_rows, match_rows)

    match_rows.sort(key=lambda r: (r.get("round", ""), _no(r)))
    round_rows.sort(key=lambda r: r.get("round", ""))

    ok = _write(MATCH_FILE, MATCH_FIELDS, match_rows)
    ok = _write(ROUND_FILE, ROUND_FIELDS, round_rows) and ok
    if not ok:
        return "실패 (파일 쓰기)"

    rounds = len({r.get("round", "") for r in match_rows})
    settled = sum(1 for r in match_rows if r.get("result"))
    extra = f", 이번에 {res.settled_now}경기 정산" if res.settled_now else ""
    if frozen:
        extra += f", 사전 스냅샷 보존 {frozen}경기"
    if res.conflicts:
        extra += f", 결과 불일치 {len(res.conflicts)}경기"
    for line in res.conflicts:
        log.warning("이미 정산된 경기와 소스 결과가 다릅니다 — %s "
                    "(기록을 그대로 둡니다)", line)
    return (f"ok ({len(report.matches)}경기 기록 · 누적 {rounds}회차 "
            f"{len(match_rows)}경기 · 결과 확보 {settled}경기{extra})")


def rows_for(round_id: str) -> list[dict]:
    """그 회차의 기존 경기 전 기록. **읽기만 한다.**"""
    return [r for r in _read(MATCH_FILE, MATCH_FIELDS)
            if r.get("round") == round_id]


def settle(round_id: str, season: list[SeasonMatch]
           ) -> tuple[SettleOutcome | None, str]:
    """**지정 회차만** 정산하고 CSV 를 갱신한다 (Phase 6-C-2). (결과, 사유).

    `record()` 와 **같은 `settle_rows()`** 를 쓴다. 다른 것은 셋뿐이다.

      · 이 회차 행만 본다 (§5) — 다른 회차를 고치지도 만들지도 않는다.
      · **경기 전 스냅샷을 새로 만들지 않는다.** 행이 없으면 그렇게 말하고
        끝낸다. 조용히 만들면 `recorded_at` 이 사후 시각이 되어 그 회차가
        시장 캘리브레이션 표본에서 영구히 빠진다.
      · 리포트도 artifact 도 건드리지 않는다 (§9).
    """
    rows = _read(MATCH_FILE, MATCH_FIELDS)
    if not any(r.get("round") == round_id for r in rows):
        return None, (f"{round_id}회차의 경기 전 기록이 없습니다 — "
                      f"먼저 회차를 수집하십시오 (메뉴 [1] 또는 "
                      f"python -m toto --round {round_id}).")

    res = settle_rows(rows, season, round_id=round_id)
    for line in res.conflicts:
        log.warning("이미 정산된 경기와 소스 결과가 다릅니다 — %s "
                    "(기록을 그대로 둡니다)", line)
    if not res.settled_now and not res.linked_ids:
        # 바뀐 것이 없으면 쓰지 않는다 — 멀쩡한 파일을 다시 쓸 이유가 없다.
        return res, ""

    round_rows = _read(ROUND_FILE, ROUND_FIELDS)
    _roll_up(round_rows, rows)
    rows.sort(key=lambda r: (r.get("round", ""), _no(r)))
    round_rows.sort(key=lambda r: r.get("round", ""))
    if not _write(MATCH_FILE, MATCH_FIELDS, rows):
        return None, "경기 기록 파일을 쓰지 못했습니다."
    if round_rows and not _write(ROUND_FILE, ROUND_FIELDS, round_rows):
        return None, "회차 기록 파일을 쓰지 못했습니다."
    return res, ""


def _no(row: dict) -> int:
    try:
        return int(row.get("no") or 0)
    except (TypeError, ValueError):
        return 0
