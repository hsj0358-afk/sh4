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
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timedelta
from pathlib import Path

from .models import Report, find_season_match
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
    "home", "away", "home_canon", "away_canon",
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
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding=_ENCODING, newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(fields))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fields})
        return True
    except OSError as exc:
        log.warning("회차 기록을 쓰지 못했습니다 (%s): %s", path.name, exc)
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


def _settle(rows: list[dict], report: Report) -> int:
    """이미 기록된 과거 경기의 결과를 시즌 색인으로 채운다.

    **새로 수집하지 않는다** — 이번 실행이 받아 온 색인만 쓴다. 이번 회차의
    경기는 아직 안 끝났으므로 대개 지난 회차가 채워진다.
    """
    # 스코어가 있는 종료 경기만 후보다. 짝 고르기 자체는
    # `models.find_season_match()` 가 한다 — `match_material` 과 **같은
    # 규칙**을 써야 해서 한 곳에 뒀다(두 벌이면 한쪽만 고쳐져 어긋난다).
    season = [sm for sm in (report.season_matches or [])
              if sm.finished and sm.home_goals is not None
              and sm.away_goals is not None]
    if not season:
        return 0

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    filled = 0
    for row in rows:
        if row.get("result"):
            continue
        sm = find_season_match(
            season, row.get("home_canon", ""), row.get("away_canon", ""),
            _kickoff_date(row.get("kickoff_kst", "")), _SETTLE_WINDOW,
            finished_only=True)
        if sm is None:
            # 같은 팀 짝이 둘 이상(홈/원정 두 경기)이고 날짜로 못 가리면
            # 비워 둔다. 틀린 결과를 채우는 것이 비어 있는 것보다 나쁘다.
            continue
        row["home_goals"] = str(sm.home_goals)
        row["away_goals"] = str(sm.away_goals)
        row["result"] = sm.result or ""
        pick = row.get("pick", "")
        if pick and row["result"]:
            row["pick_hit"] = "1" if pick == row["result"] else "0"
        row["settled_at"] = stamp
        filled += 1
    return filled


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

    filled = _settle(match_rows, report)
    _roll_up(round_rows, match_rows)

    match_rows.sort(key=lambda r: (r.get("round", ""), _no(r)))
    round_rows.sort(key=lambda r: r.get("round", ""))

    ok = _write(MATCH_FILE, MATCH_FIELDS, match_rows)
    ok = _write(ROUND_FILE, ROUND_FIELDS, round_rows) and ok
    if not ok:
        return "실패 (파일 쓰기)"

    rounds = len({r.get("round", "") for r in match_rows})
    settled = sum(1 for r in match_rows if r.get("result"))
    extra = f", 이번에 {filled}경기 정산" if filled else ""
    if frozen:
        extra += f", 사전 스냅샷 보존 {frozen}경기"
    return (f"ok ({len(report.matches)}경기 기록 · 누적 {rounds}회차 "
            f"{len(match_rows)}경기 · 결과 확보 {settled}경기{extra})")


def _no(row: dict) -> int:
    try:
        return int(row.get("no") or 0)
    except (TypeError, ValueError):
        return 0
