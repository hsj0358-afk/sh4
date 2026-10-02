"""베트맨 축구토토 승무패 14경기 목록 수집.

베트맨 게임슬립은 JS 로 렌더링되므로 Playwright 가 필요하다
(briefing/scraper.py 의 sync_playwright 사용 패턴을 그대로 따른다).

## 경기 행 계약 (Phase 6-C)

실측(260054·260055 원본 cells)에서 경기 행은 이런 모양이다.

    "1경기" · "26.09.19 (토) 23:00 …" · "브라이턴\\t\\nvs\\n아스널" · 투표율 … ·
    "1경기 브라이턴 : 아스널 상세정보 열기"

**경기 행은 번호 셀(`N경기`)과 vs 셀이 함께 있는 행뿐이다.** 그 뒤에 오는
`전체조합수`·`전체선택` 같은 UI 행은 경기가 아니다. 예전에는 '팀처럼 보이는
셀 2개' 를 고르는 대체 경로가 그런 행을 가짜 경기로 만들었고, 그것을
`matches[:14]` 가 조용히 잘라 내고 있었다.

회차는 **번호 1~14 가 정확히 한 번씩** 있어야 통과한다 (`round_problems`).
모자라거나 넘치거나 번호가 겹치면 잘라 쓰지 않고 실패로 멈춘다 — 원본 HTML 은
cache 에 남는다. 그때는 `--matches-file` 로 직접 적어 넣으면 이후 분석이
동일하게 돈다.

**파서는 대회를 정하지 않는다.** 베트맨 경기 행에는 대회 칸이 없다. 행 전체
문자열에 `settings.league_of()` 를 걸면 국가대표 경기의 국가명이 국내리그
별칭에 걸린다(`이탈리아 vs 벨기에` → 세리에A — 260055 실측). 대회는
`toto.competition` 이 따로 정한다.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import competition
from ..models import Match, TeamRef
from ..settings import ROOT, Settings, load_yaml

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

# 경기 번호 셀: "1경기" ~ "14경기". **셀 전체가 이 모양**이어야 한다 —
# 마지막 셀 "1경기 브라이턴 : 아스널 상세정보 열기" 는 번호 셀이 아니다.
_MATCH_NO_RE = re.compile(r"(\d{1,2})\s*경기")


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
        # 여기의 `league_of` 는 사람이 적은 **리그 표기**를 읽는다 — 그 함수가
        # 원래 하는 일이다. 베트맨 행 전체에 걸던 것과 다르다 (Phase 6-C).
        league_raw = str(row.get("league", ""))
        key = settings.league_of(league_raw) or league_raw
        matches.append(Match(
            no=int(row.get("no", i)),
            league=key,
            league_ko=settings.league_ko(key),
            home=TeamRef(name_ko=str(row.get("home", ""))),
            away=TeamRef(name_ko=str(row.get("away", ""))),
            kickoff_kst=str(row.get("kickoff", "")),
            # 적혀 있으면 확정된 대회다 — 팀 추론·FotMob 정정이 덮지 않는다.
            league_basis=competition.MATCHES_FILE if key else "",
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


@dataclass
class MatchRows:
    """표 행을 경기 행 / 그 밖의 행으로 가른 결과 (Phase 6-C).

    `matches` 는 **행 순서 그대로**이고 번호는 행이 스스로 적은 번호다.
    회차로 통과하는지는 `round_problems()` 가 따로 판정한다.
    """
    matches: list[Match] = field(default_factory=list)
    unreadable: list[int] = field(default_factory=list)  # 번호는 있는데 vs 셀이 없다
    ignored: int = 0          # 경기 행이 아닌 행 (빈 행·머리글·UI 행)
    repeated: int = 0         # 번호·팀·시각까지 같은 행이 다시 나온 수 (프레임 중복)


def _match_no(cells: list[str]) -> int | None:
    for cell in cells:
        m = _MATCH_NO_RE.fullmatch(cell)
        if m:
            return int(m.group(1))
    return None


def _teams(cells: list[str]) -> tuple[str, str]:
    """`홈 vs 원정` 이 한 셀에 든 vs 셀에서 두 팀을 꺼낸다. 없으면 ("", "")."""
    for cell in cells:
        m = _VS_RE.match(cell)
        if m and not _TIME_RE.search(cell):
            home, away = m.group(1).strip(), m.group(2).strip()
            if home and away:
                return home, away
    return "", ""


def read_match_rows(rows: list[dict]) -> MatchRows:
    """표 행 → 경기 행. **대회는 정하지 않는다** (`league` 는 언제나 빈칸).

    경기 행은 번호 셀과 vs 셀이 함께 있는 행이다. 번호 셀이 없는 행은 세기만
    하고 버린다 — 그것이 UI 행을 가짜 경기로 만들지 않는 장치다.
    """
    out = MatchRows()
    seen: set[tuple] = set()
    for row in rows:
        cells = [c.strip() for c in row.get("cells", []) if c and c.strip()]
        blob = " ".join(cells)
        # 표 머리글 행을 경기로 착각하면 실제 경기 하나가 밀려서 빠진다.
        if len(cells) < 3 or any(h in blob for h in _HEADER_HINTS):
            out.ignored += 1
            continue
        no = _match_no(cells)
        if no is None:
            out.ignored += 1
            continue
        home, away = _teams(cells)
        if not home:
            out.unreadable.append(no)
            continue
        kickoff = _parse_kickoff(blob)
        key = (no, home, away, kickoff)
        if key in seen:
            out.repeated += 1
            continue
        seen.add(key)
        out.matches.append(Match(no=no, home=TeamRef(name_ko=home),
                                 away=TeamRef(name_ko=away),
                                 kickoff_kst=kickoff))
    return out


def round_problems(parsed: MatchRows, expected: int) -> list[str]:
    """회차가 **번호 1~expected 를 정확히 한 번씩** 갖는지. 문제가 없으면 [].

    잘라 쓰거나 번호를 다시 매겨 맞추지 않는다 — 모자라든 넘치든 실패다.
    """
    nos = [m.no for m in parsed.matches]
    if not nos and not parsed.unreadable:
        return ["경기 행을 하나도 찾지 못했습니다"]
    problems: list[str] = []
    if parsed.unreadable:
        problems.append("번호는 있지만 팀명(vs 셀)을 읽지 못한 행: "
                        + ", ".join(f"{n}번" for n in sorted(parsed.unreadable)))
    twice = sorted({n for n in nos if nos.count(n) > 1})
    if twice:
        problems.append("같은 번호에 다른 경기가 있습니다: "
                        + ", ".join(f"{n}번" for n in twice))
    have = set(nos) | set(parsed.unreadable)
    over = sorted(n for n in have if not 1 <= n <= expected)
    if over:
        problems.append(f"{expected}경기를 넘는 번호: "
                        + ", ".join(f"{n}번" for n in over))
    missing = [n for n in range(1, expected + 1) if n not in have]
    if missing:
        problems.append("없는 번호: " + ", ".join(f"{n}번" for n in missing))
    if len(nos) != expected and not problems:
        problems.append(f"경기 행 {len(nos)}개 (기대 {expected}개)")
    return problems


class MatchListError(RuntimeError):
    """베트맨 경기 목록이 회차 계약(번호 1~14 가 한 번씩)을 지키지 않는다."""

    def __init__(self, round_id: str, problems: list[str]) -> None:
        self.round_id = round_id
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def match_list(rows: list[dict], expected: int,
               round_id: str = "") -> list[Match]:
    """표 행 → 회차 14경기 (번호순). 계약을 어기면 `MatchListError`."""
    parsed = read_match_rows(rows)
    if parsed.repeated:
        log.info("내용까지 같은 경기 행 %d개를 한 번만 셉니다 (프레임 중복)",
                 parsed.repeated)
    problems = round_problems(parsed, expected)
    if problems:
        raise MatchListError(round_id, problems)
    return sorted(parsed.matches, key=lambda m: m.no)


def _parse_rows(rows: list[dict], settings: Settings | None = None) -> list[Match]:
    """행 텍스트 리스트 → 경기 행 목록 (회차 계약은 보지 않는다).

    회차 자동 탐지(`_detect_round`)가 "이 회차 페이지가 열리나" 를 물을 때
    쓴다. `settings` 는 예전 시그니처를 지키려고 남겨 둔 것이다 — 대회를
    정하지 않으므로 쓰지 않는다.
    """
    return read_match_rows(rows).matches


def fetch_matches(settings: Settings, round_id: str | None = None,
                  cache=None) -> tuple[list[Match], str]:
    """이번(또는 지정) 회차의 승무패 14경기를 수집한다.

    Returns: (경기 목록, 회차 ID). 브라우저를 못 띄우거나 회차를 못 찾으면
    빈 목록이다.

    Raises: `MatchListError` — 표를 받았는데 번호 1~14 가 한 번씩 있지 않을 때
    (모자람·넘침·번호 겹침·팀명을 읽지 못한 경기 행). 앞 14개만 잘라 쓰지
    않는다.
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
            rows = _scrape_rows(page, frames_html)
            html = page.content()
        except Exception as exc:
            log.error("베트맨 수집 실패: %s", exc)
        finally:
            browser.close()

    log.info("베트맨 페이지에서 표 %d행 수집", len(rows))
    try:
        matches = match_list(rows, expected, resolved_round)
    except MatchListError as exc:
        # 잘라 쓰지 않는다. 원본을 남기고 멈춘다 — 이 파일로 파서를 맞춘다.
        log.error("베트맨 %s회차 경기 목록이 %d경기 계약을 지키지 않습니다: %s",
                  resolved_round, expected, exc)
        if cache is not None:
            log.warning("원본을 cache 에 저장합니다 — 이 파일로 파서를 맞출 수 "
                        "있습니다.")
            if html:
                cache.save_debug("betman", f"round_{resolved_round}", html)
            for idx, (name, fhtml) in enumerate(frames_html):
                cache.save_debug("betman", f"round_{resolved_round}_frame{idx}_{name}",
                                 fhtml)
        raise

    log.info("베트맨 %s회차 — %d경기 수집", resolved_round, len(matches))
    # 다음 실행에서 회차를 자동 탐지할 때의 출발점으로 남긴다.
    _remember_round(resolved_round)
    return matches, resolved_round


def _scrape_rows(page, frames_html: list | None = None) -> list[dict]:
    """모든 프레임에서 표 행을 긁어 합친다.

    게임슬립은 frameType 파라미터가 붙는 프레임 구성이라, 경기표가 메인
    문서가 아니라 하위 프레임 안에 있을 수 있다.
    """
    rows: list[dict] = []
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
            if frames_html is not None:
                try:
                    frames_html.append((frame.name or "main", frame.content()))
                except Exception:
                    pass
    return rows


LAST_ROUND_FILE = ROOT / "data" / "last_round.txt"


def _remember_round(round_id: str) -> None:
    """마지막으로 성공한 회차를 남긴다 (다음 자동 탐지의 출발점)."""
    if not round_id or not round_id.isdigit():
        return
    try:
        LAST_ROUND_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_ROUND_FILE.write_text(round_id, encoding="utf-8")
    except Exception:
        pass


def _last_round() -> int | None:
    try:
        return int(LAST_ROUND_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _detect_round(page, settings: Settings) -> str | None:
    """판매중인 승무패 회차 코드를 찾는다.

    베트맨 구매 목록은 링크를 href 가 아니라 스크립트로 여는 경우가 있어서
    href 만 보면 한 건도 못 찾는다(실측에서 그랬다). 그래서
    href → 페이지 전체 HTML → 직전 회차에서 앞으로 세어보기 순으로 시도한다.
    """
    cfg = settings.betman
    game_id = cfg.get("game_id", DEFAULT_GAME_ID)
    # gmTs 가 gmId 앞에 오기도 하고, 따옴표·쉼표로 넘겨지기도 한다
    patterns = [
        re.compile(rf"gmId={game_id}[^\"'\s]*?gmTs=(\d{{5,8}})"),
        re.compile(rf"gmTs=(\d{{5,8}})[^\"'\s]*?gmId={game_id}"),
        re.compile(rf"['\"]{game_id}['\"]\s*,\s*['\"]?(\d{{5,8}})"),
    ]

    def _scan(text: str) -> list[str]:
        out: set[str] = set()
        for pattern in patterns:
            out.update(pattern.findall(text or ""))
        return sorted(out)

    try:
        page.goto(cfg["buy_url"], wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)

        hrefs = page.eval_on_selector_all(
            "a", "els => els.map(e => (e.getAttribute('href') || '') + '|' "
                 "+ (e.getAttribute('onclick') || ''))") or []
        rounds = _scan(" ".join(hrefs))
        if not rounds:
            # 프레임 안에 목록이 있을 수 있다
            for frame in page.frames:
                try:
                    rounds = _scan(frame.content())
                except Exception:
                    continue
                if rounds:
                    break
        if rounds:
            log.info("승무패 회차 후보: %s → %s 사용", rounds, rounds[-1])
            return rounds[-1]
    except Exception as exc:
        log.warning("회차 자동 탐지 실패: %s", exc)

    # 마지막 수단: 직전에 성공한 회차부터 앞으로 세어 실제로 열리는 회차를 찾는다.
    last = _last_round()
    if last is None:
        return None
    expected = int(cfg.get("expected_matches", 14))
    for step in range(1, 7):
        candidate = str(last + step)
        url = cfg["slip_url"].format(game_id=game_id, round=candidate)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2000)
            rows = _scrape_rows(page)
        except Exception:
            continue
        if len(_parse_rows(rows, settings)) >= expected:
            log.info("회차 %s 부터 세어 %s 회차를 찾았습니다.", last, candidate)
            return candidate
    log.warning("직전 회차 %s 이후로 열리는 회차를 찾지 못했습니다.", last)
    return None
