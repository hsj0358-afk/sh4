"""후스코어드 차단 재시도와 정성 자료 공백 알림 (260059 후속).

260059(2026-10-10) 수집에서 라리가 리그 페이지가 차단돼 그 리그 12팀의 지표와
팀 페이지가 통째로 빠졌고, EPL 팀 페이지 셋도 받지 못했다. 세 가지를 고쳤다.

  A. 차단으로 판정된 페이지(리그·팀 통계 탭·팀 페이지)를 기다렸다 다시 받는다.
     차단이 아닌 실패는 다시 시도하지 않고, 한 번 끝까지 실패하면 그 실행에서는
     더 재시도하지 않는다 (사이트 전체가 막힌 경우 시간을 버리지 않게).
  B. 팀 페이지가 차단되면 그 사실과 원본을 남긴다 — 리그 페이지와 같은 방식.
  C. 패널 자동 분석이 시작 전에 정성 자료 공백을 알린다. 막지는 않는다.

외부 사이트에 접속하지 않고 실제로 기다리지 않는다.

    python tests/test_whoscored_block_retry.py
"""
from __future__ import annotations

import logging
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import panelauto                                      # noqa: E402
from toto.normalize import TeamResolver                         # noqa: E402
from toto.settings import load_settings                         # noqa: E402
from toto.sources import whoscored as W                         # noqa: E402

import tests.test_league_stat_table as LS                       # noqa: E402
import tests.test_whoscored_characteristics as WC               # noqa: E402

BLOCK_HTML = "<html><title>Attention Required! | Cloudflare</title></html>"
KST = timezone(timedelta(hours=9))


# --------------------------------------------------------------------------
# 흉내 — 주소 조각마다 응답을 차례로 돌려준다. 마지막 응답은 계속 되풀이된다.
# --------------------------------------------------------------------------
class Scripted:
    def __init__(self, script):
        self.script = [(key, list(seq)) for key, seq in script]
        self.calls: list[str] = []
        self.last_block, self.last_block_html = "", ""

    def abs_url(self, url):
        return "https://www.whoscored.com" + url if url.startswith("/") else url

    def get_html(self, url, wait_selector=None):
        self.calls.append(url)
        for key, seq in self.script:
            if key in url:
                html, block = seq.pop(0) if len(seq) > 1 else seq[0]
                self.last_block = block
                self.last_block_html = BLOCK_HTML if block else ""
                return html
        self.last_block, self.last_block_html = "", ""
        return ""


class Settings:
    def __init__(self, **cfg):
        self.whoscored = {"recent_form_count": 5, **cfg}


class Sleeps:
    """`W._sleep` 를 갈아 끼우고 몇 초를 기다리려 했는지 적는다."""

    def __enter__(self):
        self.saved, self.waits = W._sleep, []
        W._sleep = self.waits.append
        return self

    def __exit__(self, *exc):
        W._sleep = self.saved
        return False


class Logs(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(record.getMessage())

    def __enter__(self):
        logging.getLogger(W.__name__).addHandler(self)
        return self

    def __exit__(self, *exc):
        logging.getLogger(W.__name__).removeHandler(self)
        return False


class Cache:
    def __init__(self):
        self.debug: list[tuple] = []
        self.saved: dict = {}

    def get(self, ns, key):
        return None

    def set(self, ns, key, value):
        self.saved[(ns, key)] = value

    def save_debug(self, ns, key, body, failed=True):
        self.debug.append((ns, key, failed))


OK = ("<html>ok</html>", "")
BLOCKED = ("", "cloudflare")
FAILED = ("", "")                    # 차단이 아닌 실패 (예외·빈 응답)


# ==========================================================================
# A. 재시도 규칙
# ==========================================================================
def test_a1_success_needs_no_retry():
    b = Scripted([("x", [OK])])
    with Sleeps() as s:
        got = W._get_page(b, Settings(), "https://www.whoscored.com/x")
    assert got == OK[0] and len(b.calls) == 1 and s.waits == []


def test_a2_block_then_success_waits_and_retries():
    b = Scripted([("x", [BLOCKED, OK])])
    with Sleeps() as s:
        got = W._get_page(b, Settings(block_retry_wait_sec=12), "/x")
    assert got == OK[0]
    assert len(b.calls) == 2 and s.waits == [12.0]


def test_a3_always_blocked_tries_retry_count_and_keeps_block_state():
    b = Scripted([("x", [BLOCKED])])
    with Sleeps() as s, Logs() as h:
        got = W._get_page(b, Settings(block_retries=2), "/x", what="laliga 리그 페이지")
    assert got == ""
    assert len(b.calls) == 3 and len(s.waits) == 2
    # 부르는 쪽이 차단 사유와 원본을 그대로 남길 수 있어야 한다
    assert b.last_block == "cloudflare" and b.last_block_html == BLOCK_HTML
    assert any("laliga 리그 페이지" in ln and "1/2" in ln for ln in h.lines), h.lines
    assert any("더 재시도하지 않습니다" in ln for ln in h.lines), h.lines


def test_a4_after_one_exhausted_sequence_no_more_retries():
    """사이트 전체가 막히면 페이지마다 기다리지 않는다."""
    b = Scripted([("x", [BLOCKED]), ("y", [BLOCKED])])
    with Sleeps() as s:
        W._get_page(b, Settings(block_retries=2), "/x")
        W._get_page(b, Settings(block_retries=2), "/y")
    assert b.calls.count("/y") == 1, b.calls
    assert len(s.waits) == 2


def test_a5_success_after_retry_does_not_stop_later_retries():
    b = Scripted([("x", [BLOCKED, OK]), ("y", [BLOCKED, OK])])
    with Sleeps() as s:
        assert W._get_page(b, Settings(), "/x") == OK[0]
        assert W._get_page(b, Settings(), "/y") == OK[0]
    assert len(s.waits) == 2


def test_a6_non_block_failure_is_not_retried():
    b = Scripted([("x", [FAILED])])
    with Sleeps() as s:
        assert W._get_page(b, Settings(), "/x") == ""
    assert len(b.calls) == 1 and s.waits == []


def test_a7_zero_retries_turns_it_off():
    b = Scripted([("x", [BLOCKED])])
    with Sleeps() as s:
        assert W._get_page(b, Settings(block_retries=0), "/x") == ""
    assert len(b.calls) == 1 and s.waits == []


def test_a8_policy_parsing():
    assert W._retry_policy(Settings()) == (2, 30.0)
    assert W._retry_policy(Settings(block_retries="x",
                                    block_retry_wait_sec=None)) == (2, 30.0)
    assert W._retry_policy(Settings(block_retries=-3,
                                    block_retry_wait_sec=-1)) == (0, 0.0)
    assert W._retry_policy(SimpleNamespace()) == (2, 30.0)


def test_a9_config_values():
    assert W._retry_policy(load_settings()) == (2, 30.0)


def test_a10_stub_browser_without_block_attributes_still_works():
    """옛 흉내 브라우저(`last_block` 이 없는)도 그대로 돈다."""
    class Bare:
        def get_html(self, url, wait_selector=None):
            return ""
    with Sleeps() as s:
        assert W._get_page(Bare(), Settings(), "/x") == ""
    assert s.waits == []


# ==========================================================================
# B. 팀 페이지
# ==========================================================================
def _team(script, settings=None):
    b, cache = Scripted(script), Cache()
    with Sleeps() as s, Logs() as h:
        got = W.read_team(b, settings or Settings(), "/teams/62/show/spain-celta",
                          "Celta Vigo", TeamResolver(), cache)
    return got, b, cache, s, h


def test_b1_blocked_team_page_keeps_raw_and_says_so():
    got, b, cache, _s, h = _team([("/teams/", [BLOCKED])])
    assert got == {}
    assert ("whoscored", "blocked_team_Celta Vigo", False) in cache.debug, cache.debug
    assert any("Celta Vigo" in ln and "차단" in ln and "type=cloudflare" in ln
               for ln in h.lines), h.lines


def test_b2_blocked_team_page_is_not_cached():
    """빈 결과를 캐시하지 않는다 — 같은 날 다시 돌리면 다시 받는다."""
    _got, _b, cache, _s, _h = _team([("/teams/", [BLOCKED])])
    assert cache.saved == {}


def test_b3_non_block_failure_keeps_old_behaviour():
    got, b, cache, s, _h = _team([("/teams/", [FAILED])])
    assert got == {} and cache.debug == [] and s.waits == [] and len(b.calls) == 1


def test_b4_team_page_retried_then_parsed():
    got, b, cache, s, _h = _team([("/teams/", [BLOCKED, (WC.NO_STRENGTH, "")])])
    assert len(b.calls) == 2 and len(s.waits) == 1
    assert len(got["weaknesses"]) == 2, got
    assert ("whoscored", "team_Celta Vigo") in cache.saved


# ==========================================================================
# C. 리그 페이지 · 팀 통계 탭
# ==========================================================================
STAT_PAGE = LS._page(LS.STAT_TABLE)


def _league(script):
    b, cache = Scripted(script), Cache()
    with Sleeps() as s, Logs() as h:
        out = W.read_league(b, load_settings(), "epl", TeamResolver(), cache=cache)
    return out, b, cache, s, h


def test_c1_league_page_retried_then_collected():
    expected, _ = LS._run(LS.LEAGUE_PAGE, STAT_PAGE)
    out, b, _cache, s, _h = _league([
        ("/teamstatistics/", [(STAT_PAGE, "")]),
        ("England", [BLOCKED, (LS.LEAGUE_PAGE, "")]),
    ])
    assert out == expected
    assert len(s.waits) == 1


def test_c2_stat_tab_retried_then_collected():
    out, _b, _cache, s, _h = _league([
        ("/teamstatistics/", [BLOCKED, (STAT_PAGE, "")]),
        ("England", [(LS.LEAGUE_PAGE, "")]),
    ])
    assert LS._stats(out, "Arsenal").shots_pg == 13.7
    assert len(s.waits) == 1


def test_c3_league_still_blocked_keeps_existing_handling():
    out, _b, cache, _s, h = _league([("England", [BLOCKED])])
    assert out == {} and cache.saved == {}
    assert ("whoscored", "blocked_league_epl", False) in cache.debug
    assert any(ln.startswith("리그 페이지 수집 실패") for ln in h.lines), h.lines


# ==========================================================================
# D. 패널 자동 분석 — 정성 자료 공백 알림
# ==========================================================================
def _profile(page_ok):
    return SimpleNamespace(team_page_ok=page_ok)


def _report(states, kickoff="2026-10-11 20:00", status=""):
    """states: [(홈 team_page_ok, 원정 team_page_ok), …]"""
    matches = [SimpleNamespace(no=i, kickoff_kst=kickoff,
                               home_profile=_profile(h), away_profile=_profile(a))
               for i, (h, a) in enumerate(states, start=1)]
    return SimpleNamespace(matches=matches,
                           source_status={"상세데이터": status} if status else {})


BEFORE = datetime(2026, 10, 10, 16, 0, tzinfo=KST)
AFTER = datetime(2026, 10, 12, 0, 0, tzinfo=KST)


def test_d1_full_coverage_says_nothing():
    assert panelauto.qualitative_note(_report([(True, True)] * 3), BEFORE) == ""


def test_d2_counts_like_260059():
    states = [(True, True)] * 6 + [(False, False)] * 7 + [(True, False)]
    rep = _report(states, status="부분 (16/28팀 지표, 13팀 상세, 강점/약점 13팀, 맞대결 생략)")
    cov = panelauto.qualitative_coverage(rep)
    assert cov == {"total": 28, "ok": 13, "failed": 15, "unrecorded": 0}
    line = panelauto.qualitative_note(rep, BEFORE)
    assert "13/28팀" in line and "받지 못한 팀 15" in line
    assert "상세데이터: 부분 (16/28팀 지표" in line


def test_d3_before_kickoff_suggests_rerun():
    line = panelauto.qualitative_note(_report([(True, False)]), BEFORE)
    assert "[1] 회차 분석을 다시" in line and "저장본은 바뀌지" not in line


def test_d4_after_kickoff_says_it_cannot_be_fixed():
    line = panelauto.qualitative_note(_report([(True, False)]), AFTER)
    assert "저장본은 바뀌지 않습니다" in line and "다시 돌려" not in line


def test_d5_unrecorded_is_not_called_a_failure():
    """`None` 은 '받지 못함' 이 아니라 '기록 없음' 이다 (§1-36)."""
    rep = _report([(None, None), (True, True)])
    line = panelauto.qualitative_note(rep, BEFORE)
    assert "기록 없음 2" in line and "받지 못한" not in line
    assert "다시 돌려" not in line            # 다시 돌려도 생기지 않는다


def test_d6_missing_profile_counts_as_unrecorded():
    rep = _report([(True, True)])
    rep.matches[0].away_profile = None
    assert panelauto.qualitative_coverage(rep)["unrecorded"] == 1


def test_d7_preflight_puts_it_in_warnings_and_both_screens_show_it():
    import tests.test_panel_auto as PA
    report = PA.FakeReport(3)
    saved = [(m.home_profile.team_page_ok, m.away_profile.team_page_ok)
             for m in report.matches]
    report.matches[0].away_profile.team_page_ok = False
    base = Path(tempfile.mkdtemp(prefix="toto_qual_test_"))
    try:
        with PA.patched():
            pre = panelauto.preflight(report, "TEST", base)
            lines: list[str] = []
            panelauto.check("TEST", report, base=base, echo=lines.append)
    finally:
        for m, (h, a) in zip(report.matches, saved):
            m.home_profile.team_page_ok, m.away_profile.team_page_ok = h, a
    assert pre.warnings and "정성 자료" in pre.warnings[0], pre.warnings
    assert not any("정성 자료" in n for n in pre.notes), pre.notes
    assert any(ln.startswith("  ⚠") and "정성 자료" in ln for ln in lines), lines
    # 시작 전 문제가 아니다 — 막지 않는다
    assert not any("정성 자료" in p for p in pre.problems)


def test_d8_run_screen_echoes_warnings_on_the_normal_path():
    """정상 실행 화면에도 나와야 한다 — notes 는 점검·실패 화면에만 나간다."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(panelauto.run))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "warnings" in names


# --------------------------------------------------------------------------
def main() -> int:
    # 직접 실행 러너는 `tests/_runner.py` 한 곳에 있다 (Phase 3 M13).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    sys.exit(main())
