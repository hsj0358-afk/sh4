"""후스코어드 리그 팀 통계 표 회귀 테스트 (§3-9).

260052 에서 `season.shots`·`season.on_target_rate`·`season.xg_per_shot` 이
28/28 팀 비었다. 셋 다 `TeamStats.shots_pg` 하나에 매달려 있고, 그 칸을
채우는 곳은 저장소 전체에서 `read_league()` 의 3절 한 곳뿐이다.

2026-09-12 사용자 PC 저장본으로 원인이 확정됐다.

  · `shots pg`·`pass%`·`aerialswon` 세 머리글이 EPL 730KB · 라리가 1,225KB
    두 파일 모두에서 **0회**다 — DOM 에도 `<script>` 에도. 열 이름이 바뀐
    것이 아니라 **그 표가 그 페이지에 없다.**
  · 받은 페이지는 리그 요약(`…/stages/<id>/show/…`)이고, 팀별 표는 형제 탭
    `…/stages/<id>/teamstatistics/…` 에 있다 — **페이지 자신의 링크로
    확인된 사실**이지 기억으로 지어낸 주소가 아니다.
  · 덤으로 3절 게이트가 톱5 위젯 세 개를 통과시키고 있었다. 머리글이
    `['Possession']`·`['Ratings']`·`['Ratings','','Apps','Rt']` 한두 칸뿐이라
    `_header_index` 의 부분일치에 걸리고, 그 0번 칸은 지표가 아니라 **팀
    이름 칸**이다. 셋째 것은 아예 선수 표였다.

아래 픽스처의 머리글·데이터 행은 전부 그 진단 출력에 **찍힌 그대로**다.
팀 통계 표의 모양만은 실물을 보지 못했으므로(그 탭을 이 세션에서 열 수
없다 — §2-1), 테스트는 특정 마크업이 아니라 **파서가 읽어낸 결과**를
단언한다.

pytest 없이도 돈다:  python tests/test_league_stat_table.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto.normalize import TeamResolver                         # noqa: E402
from toto.settings import load_settings                         # noqa: E402
from toto.sources import whoscored                              # noqa: E402
from toto.sources.whoscored import (                            # noqa: E402
    _LEAGUE_CACHE_VERSION, _stat_page_path, read_league)

SRC = Path(__file__).resolve().parent.parent / "toto" / "sources" / "whoscored.py"

# --------------------------------------------------------------------------
# 실물 진단 출력에서 그대로 옮긴 조각들 (2026-09-12 · EPL)
# --------------------------------------------------------------------------
CANON = ("https://www.whoscored.com/regions/252/tournaments/2/seasons/11141"
         "/stages/25544/show/england-premier-league-2026-2027")

# 머리글 세 줄 · 데이터 열 줄 — 진단 출력의 r0~r4 그대로다.
# (데이터 행은 머리글 r2 가 아니라 **r0 의 10칸**과 맞는다.)
STANDINGS = """<table id="standings-25544-grid" class="grid">
<tr><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th>
<th>GD</th><th>Pts</th><th>Form</th></tr>
<tr><th></th><th>Overall</th><th>Home</th><th>Away</th></tr>
<tr><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th>
<th>Pts</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th></tr>
<tr><td>1 Manchester City</td><td>3</td><td>3</td><td>0</td><td>0</td><td>7</td>
<td>2</td><td>+5</td><td>9</td><td>w w w</td></tr>
<tr><td>2 Arsenal</td><td>3</td><td>3</td><td>0</td><td>0</td><td>6</td><td>1</td>
<td>+5</td><td>9</td><td>w w w</td></tr>
</table>"""

# 표 [6] — 머리글 한 칸, 0번이 팀 이름 칸
WIDGET_POSS = """<table class="ws-list grid list-type-2">
<tr><th>Possession</th></tr>
<tr><td>Man City</td><td>66.5%</td></tr>
<tr><td>Brighton</td><td>65%</td></tr>
<tr><td>Arsenal</td><td>58.6%</td></tr></table>"""

# 표 [11] — 〃
WIDGET_RATING = """<table class="ws-list grid">
<tr><th>Ratings</th></tr>
<tr><td>Man City</td><td>6.98</td></tr>
<tr><td>Leeds</td><td>6.83</td></tr>
<tr><td>Arsenal</td><td>6.80</td></tr></table>"""

# 표 [16] — **선수 표**다. 팀 이름이 1번 칸에 있어 `_row_team` 이 팀을 만든다
WIDGET_PLAYER = """<table class="ws-list grid">
<tr><th>Ratings</th><th></th><th>Apps</th><th>Rt</th></tr>
<tr><td>*Ordered by appearance weighted ratings</td></tr>
<tr><td>J. Hinshelwood</td><td>Brighton</td><td>1</td><td>8.92</td></tr>
<tr><td>E. Haaland</td><td>Man City</td><td>3</td><td>8.41</td></tr></table>"""

TABS = (
    '<a href="/regions/252/tournaments/2/seasons/11141/stages/25544/fixtures'
    '/england-premier-league-2026-2027">Fixtures</a>'
    '<a href="/regions/252/tournaments/2/seasons/11141/stages/25544'
    '/playerstatistics/england-premier-league-2026-2027">Player Statistics</a>'
    '<a href="/regions/252/tournaments/2/seasons/11141/stages/25544'
    '/teamstatistics/england-premier-league-2026-2027">Team Statistics</a>'
)

STAT_PATH = ("/regions/252/tournaments/2/seasons/11141/stages/25544"
             "/teamstatistics/england-premier-league-2026-2027")

# 팀 통계 표 — **모양은 실물로 보지 못했다.** 머리글 이름은 파서가 이미
# 찾던 것들이고, 테스트는 마크업이 아니라 읽어낸 값을 단언한다.
STAT_TABLE = """<table id="statistics-team-table-summary" class="grid">
<tr><th>R</th><th>Team</th><th>Apps</th><th>Goals</th><th>Shots pg</th>
<th>Discipline</th><th>Possession%</th><th>Pass%</th><th>AerialsWon</th>
<th>Rating</th></tr>
<tr><td>1</td><td>Manchester City</td><td>3</td><td>7</td><td>15.3</td>
<td>4</td><td>66.5</td><td>88.2</td><td>12.4</td><td>6.98</td></tr>
<tr><td>2</td><td>Arsenal</td><td>3</td><td>6</td><td>13.7</td>
<td>5</td><td>58.6</td><td>85.1</td><td>14.1</td><td>6.80</td></tr>
</table>"""


def _page(body: str, *, canonical: str = CANON) -> str:
    head = f'<link rel="canonical" href="{canonical}"/>' if canonical else ""
    return (f'<html><head><title>Premier League Scores</title>{head}</head>'
            f'<body>{body}</body></html>')


LEAGUE_PAGE = _page(STANDINGS + WIDGET_POSS + WIDGET_RATING
                    + WIDGET_PLAYER + TABS)


class Browser:
    """`read_league` 가 부르는 것만 흉내낸다. 어느 주소를 받았는지 기록한다."""

    available = True

    def __init__(self, league: str, stat: str = "") -> None:
        self.league, self.stat, self.asked = league, stat, []

    def abs_url(self, path: str) -> str:
        return path if path.startswith("http") else "https://www.whoscored.com" + path

    def get_html(self, url: str, wait_selector: str | None = None) -> str:
        self.asked.append(url)
        return self.stat if whoscored._STAT_SEGMENT in url.lower() else self.league


def _run(league: str, stat: str = "") -> tuple[dict, Browser]:
    browser = Browser(league, stat)
    out = read_league(browser, load_settings(), "epl", TeamResolver(), cache=None)
    return out, browser


def _stats(out: dict, canon: str):
    entry = out.get(canon)
    return entry["stats"] if entry else None


# ==========================================================================
# A. 팀 통계 탭 주소를 페이지 자신의 링크에서 찾는다
# ==========================================================================
def test_a1_finds_tab_from_page():
    assert _stat_page_path(LEAGUE_PAGE) == STAT_PATH


def test_a2_absent_when_no_tab():
    assert _stat_page_path(_page(STANDINGS)) == ""


def test_a3_empty_html():
    assert _stat_page_path("") == ""


def test_a4_other_stage_ignored():
    """다른 stage 의 teamstatistics 링크를 집어오지 않는다."""
    other = ('<a href="/regions/108/tournaments/5/seasons/9999/stages/99999'
             '/teamstatistics/italy-serie-a">Serie A</a>')
    got = _stat_page_path(_page(STANDINGS + other + TABS))
    assert got == STAT_PATH, got
    assert "99999" not in got


def test_a5_only_other_stage_gives_nothing():
    other = ('<a href="/regions/108/tournaments/5/seasons/9999/stages/99999'
             '/teamstatistics/italy-serie-a">Serie A</a>')
    assert _stat_page_path(_page(STANDINGS + other)) == ""


def test_a6_no_canonical_uses_commonest_stage():
    """canonical 이 없어도 링크가 많은 stage 로 정한다."""
    got = _stat_page_path(_page(STANDINGS + TABS, canonical=""))
    assert got == STAT_PATH, got


def test_a7_absolute_href():
    tab = ('<a href="https://www.whoscored.com/regions/252/tournaments/2'
           '/seasons/11141/stages/25544/teamstatistics/x">T</a>')
    got = _stat_page_path(_page(STANDINGS + tab))
    assert got.startswith("https://") and got.endswith("/teamstatistics/x")


def test_a8_case_insensitive_segment():
    tab = ('<a href="/Regions/252/Tournaments/2/Seasons/11141/Stages/25544'
           '/TeamStatistics/England-Premier-League">T</a>')
    assert _stat_page_path(_page(STANDINGS + tab)).endswith(
        "/TeamStatistics/England-Premier-League")


def test_a9_stage_number_not_hardcoded():
    """시즌마다 바뀌는 번호를 소스에 박지 않는다."""
    text = SRC.read_text(encoding="utf-8")
    for bad in ("25544", "25662", "11141", "11213"):
        assert bad not in text, f"stage/season 번호 {bad} 가 소스에 박혀 있다"


# ==========================================================================
# B. 톱5 위젯은 팀 통계 표가 아니다 — 실물에서 셋 다 통과하고 있었다
# ==========================================================================
def test_b1_possession_widget_rejected():
    out, _ = _run(_page(STANDINGS + WIDGET_POSS))
    st = _stats(out, "Manchester City")
    assert st is not None and st.possession is None, st.possession


def test_b2_rating_widget_rejected():
    out, _ = _run(_page(STANDINGS + WIDGET_RATING))
    st = _stats(out, "Manchester City")
    assert st is not None and st.rating is None, st.rating


def test_b3_player_table_rejected():
    """선수 표는 팀 표가 아니다 — 팀 이름이 한 칸에 들어 있어도."""
    out, _ = _run(_page(STANDINGS + WIDGET_PLAYER))
    st = _stats(out, "Brighton")
    assert st is None or st.rating is None


def test_b4_widget_does_not_invent_teams():
    """위젯만 있는 팀이 순위표에 없는데 생기지 않는다."""
    out, _ = _run(_page(STANDINGS + WIDGET_POSS))
    assert "Brighton" not in out, sorted(out)


def test_b5_standings_not_treated_as_stat_table():
    out, _ = _run(_page(STANDINGS))
    st = _stats(out, "Manchester City")
    assert st.played == 3 and st.points == 9      # 2절은 그대로 돈다
    assert st.shots_pg is None and st.rating is None


def test_b6_rank_prefixed_widget_row_cannot_leak():
    """순위 접두가 붙어도 순위 숫자가 지표로 새지 않는다."""
    ranked = WIDGET_RATING.replace("<td>Man City</td>", "<td>1 Man City</td>")
    out, _ = _run(_page(STANDINGS + ranked))
    st = _stats(out, "Manchester City")
    assert st.rating is None, st.rating


# ==========================================================================
# C. 형제 탭에서 실제로 읽어 온다
# ==========================================================================
def test_c1_fetches_stat_tab():
    _, browser = _run(LEAGUE_PAGE, _page(STAT_TABLE))
    assert any(u.endswith(STAT_PATH) for u in browser.asked), browser.asked


def test_c2_fills_shots_pg():
    out, _ = _run(LEAGUE_PAGE, _page(STAT_TABLE))
    st = _stats(out, "Manchester City")
    assert st.shots_pg == 15.3, st.shots_pg
    assert _stats(out, "Arsenal").shots_pg == 13.7


def test_c3_fills_the_other_four():
    out, _ = _run(LEAGUE_PAGE, _page(STAT_TABLE))
    st = _stats(out, "Manchester City")
    assert (st.possession, st.pass_success, st.aerials_won_pg, st.rating) == (
        66.5, 88.2, 12.4, 6.98)


def test_c4_standings_survive():
    """3절이 2절의 값을 덮어쓰지 않는다."""
    out, _ = _run(LEAGUE_PAGE, _page(STAT_TABLE))
    st = _stats(out, "Manchester City")
    assert (st.played, st.points, st.goals_for) == (3, 9, 7)


def test_c5_stat_tab_failure_is_not_fatal():
    """탭을 못 받아도 순위표는 남는다 — 한 소스 실패가 전부를 죽이지 않는다."""
    out, _ = _run(LEAGUE_PAGE)           # 탭 요청은 빈 문자열
    st = _stats(out, "Manchester City")
    assert st.played == 3 and st.shots_pg is None


def test_c6_no_tab_link_no_extra_request():
    _, browser = _run(_page(STANDINGS))
    assert len(browser.asked) == 1, browser.asked


def test_c7_widgets_on_league_page_do_not_reach_stat_values():
    """탭을 받아도 리그 페이지의 위젯은 읽지 않는다 (표를 stat 쪽에서 찾는다)."""
    out, _ = _run(LEAGUE_PAGE, _page(STAT_TABLE))
    assert "Leeds" not in out, sorted(out)


# ==========================================================================
# D. 구조 — 추측·하드코딩을 막는다
# ==========================================================================
def test_d1_cache_version_bumped():
    assert _LEAGUE_CACHE_VERSION >= 3, _LEAGUE_CACHE_VERSION


def test_d2_no_team_name_special_case():
    text = SRC.read_text(encoding="utf-8")
    for bad in ('"Man City"', "'Man City'", '"Brighton"', '"Barcelona"'):
        assert bad not in text, f"팀 이름 {bad} 이 소스에 박혀 있다"


def test_d3_segment_from_observation_only():
    """관측한 구간 이름 하나만 쓴다 — 후보를 상상해 늘리지 않는다."""
    assert whoscored._STAT_SEGMENT == "teamstatistics"


def test_d4_stat_path_has_no_network():
    """주소 찾기는 순수 함수다 — 안에서 무언가를 받아 오지 않는다."""
    fn = next(n for n in ast.walk(ast.parse(SRC.read_text(encoding="utf-8")))
              if isinstance(n, ast.FunctionDef) and n.name == "_stat_page_path")
    called = {n.func.attr for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not called & {"get_html", "get_json", "goto"}, called


def test_d5_reason_is_logged_when_empty():
    """조용히 비우지 않는다 (§1-6-1) — 사유 문구가 소스에 있다."""
    text = SRC.read_text(encoding="utf-8")
    assert "팀 통계를 한 팀도 읽지 못했습니다" in text
    assert "팀 통계 탭 링크가 리그 페이지에 없습니다" in text


def test_d6_metric_column_never_equals_team_column():
    """지표 열이 팀 열과 같은 칸이면 지표로 읽지 않는다 — 게이트의 핵심."""
    same = """<table class="grid">
<tr><th>Team Rating</th><th>x</th></tr>
<tr><td>Man City</td><td>1</td></tr>
<tr><td>Arsenal</td><td>2</td></tr></table>"""
    out, _ = _run(_page(STANDINGS + same))
    st = _stats(out, "Manchester City")
    assert st.rating is None, st.rating


# --------------------------------------------------------------------------
def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            print(f"  ERR  {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
