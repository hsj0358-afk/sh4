"""베트맨 축구토토 승무패 14경기 목록 수집.

베트맨 게임슬립은 JS 로 렌더링되므로 Playwright 가 필요하다
(briefing/scraper.py 의 sync_playwright 사용 패턴을 그대로 따른다).

사이트 구조는 예고 없이 바뀔 수 있으므로 파서를 여러 겹으로 둔다:
  1. 테이블 행(tr) 기반 파싱 — 가장 흔한 구조
  2. 실패 시 텍스트 정규식 기반 파싱 — 표 구조가 바뀌어도 팀명/시간은 잡힘
  3. 그래도 실패하면 원본 HTML 을 cache 에 남기고 빈 목록 반환

수집이 실패해도 `--matches-file` 로 직접 적어 넣으면 이후 분석은 동일하게 돈다.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from ..models import Match, TeamRef
from ..settings import Settings, load_yaml

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 축구토토 승무패 게임 ID. 게임슬립 URL 의 gmId 파라미터와 같다.
DEFAULT_GAME_ID = "G011"

# "2026-08-09 20:00" / "08.09 20:00" / "8/9 20:00" 등을 잡는다
_TIME_RE = re.compile(r"(\d{1,4}[./-]\d{1,2}(?:[./-]\d{1,2})?)?\s*(\d{1,2}:\d{2})")
# "맨체스터시티 vs 리버풀" / "맨체스터시티 - 리버풀"
_VS_RE = re.compile(r"(.+?)\s*(?:vs\.?|VS\.?|[-–:])\s*(.+)")

# 게임슬립 표의 머리글 행에 나타나는 문구. 이 중 하나라도 들어 있으면
# 경기 행이 아니다.
_HEADER_HINTS = ("홈팀", "원정팀", "대상경기", "개최시간", "경기결과", "적중")

# 팀명일 리 없는 셀: 순번("1경기"), 순수 숫자/기호, 구분자, 날짜, 요일
_NOT_TEAM_RE = re.compile(
    r"\d+\s*경기"                       # 1경기, 14경기
    r"|[\d.\s%:/()-]+"                  # 숫자·기호만
    r"|vs\.?|VS\.?"                     # 구분자
    r"|\d{2}\.\d{2}\.\d{2}.*"           # 26.08.08 (토) 19:00
    r"|\(.\)",                          # (토)
    re.IGNORECASE)


# --------------------------------------------------------------------------
# 수동 입력 파일
# --------------------------------------------------------------------------
def load_matches_file(path: Path, settings: Settings) -> list[Match]:
    """matches.yaml 에서 14경기를 읽는다 (크롤링 폴백/우회 경로).

    형식은 examples/matches.yaml 참고.
    """
    data = load_yaml(path)
    if not data:
        log.error("경기 목록 파일을 읽지 못했습니다: %s", path)
        return []

    rows = data.get("matches") or []
    matches: list[Match] = []
    for i, row in enumerate(rows, start=1):
        league_raw = str(row.get("league", ""))
        key = settings.league_of(league_raw) or league_raw
        matches.append(Match(
            no=int(row.get("no", i)),
            league=key,
            league_ko=settings.league_ko(key),
            home=TeamRef(name_ko=str(row.get("home", ""))),
            away=TeamRef(name_ko=str(row.get("away", ""))),
            kickoff_kst=str(row.get("kickoff", "")),
        ))
    log.info("수동 경기 목록 %d경기 로드 (%s)", len(matches), path)
    return matches


# --------------------------------------------------------------------------
# 베트맨 크롤링
# --------------------------------------------------------------------------
# 베트맨 표기 "26.08.08 (토) 19:00" 은 날짜와 시각 사이에 요일이 끼어 있어서
# 한 정규식으로 붙여 잡히지 않는다. 날짜와 시각을 따로 뽑아 합친다.
_YMD_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{2})\b")        # 26.08.08
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")          # 2026-08-08
_HM_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")                 # 19:00


def _parse_kickoff(blob: str) -> str:
    """행 텍스트에서 'YYYY-MM-DD HH:MM' 을 만든다. 날짜가 없으면 시각만."""
    date = ""
    m = _ISO_RE.search(blob)
    if m:
        date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    else:
        m = _YMD_RE.search(blob)
        if m:
            date = f"20{m.group(1)}-{m.group(2)}-{m.group(3)}"

    t = _HM_RE.search(blob)
    time_s = f"{int(t.group(1)):02d}:{t.group(2)}" if t else ""
    return " ".join(x for x in (date, time_s) if x)


def _parse_rows(rows: list[dict], settings: Settings) -> list[Match]:
    """행 텍스트 리스트 → Match 목록."""
    matches: list[Match] = []
    for row in rows:
        cells = [c.strip() for c in row.get("cells", []) if c and c.strip()]
        if len(cells) < 3:
            continue
        blob = " ".join(cells)

        # 표 머리글 행을 경기로 착각하면 실제 경기 하나가 밀려서 빠진다.
        if any(h in blob for h in _HEADER_HINTS):
            continue

        league_key = settings.league_of(blob)
        home = away = ""

        # 홈/원정이 별도 셀로 있는 경우를 먼저 시도
        for idx, cell in enumerate(cells):
            m = _VS_RE.match(cell)
            if m and not _TIME_RE.search(cell):
                home, away = m.group(1).strip(), m.group(2).strip()
                break
        if not home:
            # 팀명으로 보이는 셀 2개를 고른다.
            # 순번("1경기")·시간·날짜·구분자 셀을 걸러내지 않으면 그것들이
            # 팀명 자리로 올라온다.
            cands = [c for c in cells
                     if not _TIME_RE.search(c)
                     and not _NOT_TEAM_RE.fullmatch(c)
                     and settings.league_of(c) is None
                     and len(c) >= 2]
            if len(cands) >= 2:
                home, away = cands[0], cands[1]

        if not home or not away:
            continue

        kickoff = _parse_kickoff(blob)

        matches.append(Match(
            no=len(matches) + 1,
            league=league_key or "",
            league_ko=settings.league_ko(league_key) if league_key else "",
            home=TeamRef(name_ko=home),
            away=TeamRef(name_ko=away),
            kickoff_kst=kickoff,
        ))
    return matches


def fetch_matches(settings: Settings, round_id: str | None = None,
                  cache=None) -> tuple[list[Match], str]:
    """이번(또는 지정) 회차의 승무패 14경기를 수집한다.

    Returns: (경기 목록, 회차 ID)
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        log.error("playwright 가 설치되지 않았습니다. "
                  "`pip install -r requirements-toto.txt && playwright install chromium` "
                  "또는 --matches-file 을 사용하세요.")
        return [], round_id or ""

    cfg = settings.betman
    expected = int(cfg.get("expected_matches", 14))

    from playwright.sync_api import sync_playwright
    rows: list[dict] = []
    frames_html: list[tuple[str, str]] = []
    resolved_round = round_id or ""
    html = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = browser.new_page(user_agent=UA, locale="ko-KR")

            if not resolved_round:
                resolved_round = _detect_round(page, settings) or ""
                if not resolved_round:
                    log.error("판매중인 승무패 회차를 찾지 못했습니다. "
                              "--round 로 회차를 직접 지정하거나 --matches-file 을 쓰세요.")
                    return [], ""

            url = cfg["slip_url"].format(game_id=cfg.get("game_id", DEFAULT_GAME_ID),
                                         round=resolved_round)
            log.info("베트맨 게임슬립 로드: %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_selector("tr, .game-list, [class*=match]", timeout=20000)
            except Exception:
                log.warning("게임슬립 셀렉터 대기 실패 — 구조 확인 필요")
            page.wait_for_timeout(2500)

            # 게임슬립은 frameType 파라미터가 붙는 프레임 구성이라, 경기표가
            # 메인 문서가 아니라 하위 프레임 안에 있을 수 있다. 모든 프레임에서
            # 행을 긁어 합친다.
            for frame in page.frames:
                try:
                    found = frame.eval_on_selector_all(
                        "tr",
                        "els => els.map(el => ({cells: "
                        "Array.from(el.querySelectorAll('td,th')).map(c => c.innerText)}))"
                    ) or []
                except Exception:
                    continue
                if found:
                    log.debug("프레임 %s 에서 %d행 수집", frame.url or "(main)", len(found))
                    rows.extend(found)
                    frames_html.append((frame.name or "main", frame.content()))
            html = page.content()
        except Exception as exc:
            log.error("베트맨 수집 실패: %s", exc)
        finally:
            browser.close()

    log.info("베트맨 페이지에서 표 %d행 수집", len(rows))
    matches = _parse_rows(rows, settings)

    if len(matches) < expected:
        log.warning("베트맨에서 %d경기만 파싱됨 (기대 %d경기). "
                    "원본을 cache 에 저장합니다 — 이 파일로 파서를 맞출 수 있습니다.",
                    len(matches), expected)
        if cache is not None:
            if html:
                cache.save_debug("betman", f"round_{resolved_round}", html)
            for idx, (name, fhtml) in enumerate(frames_html):
                cache.save_debug("betman", f"round_{resolved_round}_frame{idx}_{name}",
                                 fhtml)
    if len(matches) > expected:
        matches = matches[:expected]

    for i, m in enumerate(matches, start=1):
        m.no = i
    log.info("베트맨 %s회차 — %d경기 수집", resolved_round, len(matches))
    return matches, resolved_round


def _detect_round(page, settings: Settings) -> str | None:
    """판매중인 승무패 회차 코드를 찾는다."""
    cfg = settings.betman
    game_id = cfg.get("game_id", DEFAULT_GAME_ID)
    try:
        page.goto(cfg["buy_url"], wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2000)
        # gmId=G011&gmTs=###### 형태의 링크에서 회차를 뽑는다
        hrefs = page.eval_on_selector_all(
            "a", "els => els.map(e => e.getAttribute('href') || '')") or []
        pattern = re.compile(rf"gmId={game_id}[^\"']*?gmTs=(\d+)")
        found = [pattern.search(h) for h in hrefs]
        rounds = sorted({m.group(1) for m in found if m})
        if rounds:
            log.info("승무패 회차 후보: %s → %s 사용", rounds, rounds[-1])
            return rounds[-1]
        # 링크에 없으면 페이지 전체 텍스트에서 탐색
        body = page.content()
        m = pattern.search(body)
        if m:
            return m.group(1)
    except Exception as exc:
        log.warning("회차 자동 탐지 실패: %s", exc)
    return None
