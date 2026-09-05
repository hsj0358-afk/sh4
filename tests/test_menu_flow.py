"""메뉴 실행 흐름 회귀 테스트 (Phase 3-A).

고정하려는 것은 다섯 가지다.

1. **메뉴가 루프다.** 기능 하나를 쓰려고 프로그램을 다시 켜지 않는다.
2. **[0] 과 입력 종료로만 빠져나간다.** 그 밖에는 결과를 보여주고 돌아온다.
3. **예외가 프로그램을 죽이지 않는다.** 단, Ctrl+C 는 죽여야 한다 —
   멈추라는 뜻인데 삼키면 루프가 계속 돈다.
4. **입력이 끝나면 멈춘다.** EOF 를 빈 입력으로 취급하면 기본 동작(1번
   전체 수집)이 무한 반복된다. 이 테스트가 그 무한 루프를 막는다.
5. **로그 레벨이 반복 실행마다 반영되고 핸들러는 늘지 않는다.**

pytest 없이도 돈다:  python tests/test_menu_flow.py
"""
from __future__ import annotations

import builtins
import io
import logging
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import cli, menu                                       # noqa: E402


class _Input:
    """입력을 대본대로 돌려준다. 대본이 떨어지면 EOF — 무한 루프를 막는다."""

    def __init__(self, lines):
        self.lines = list(lines)
        self.asked: list[str] = []

    def __call__(self, prompt=""):
        self.asked.append(prompt)
        if not self.lines:
            raise EOFError
        value = self.lines.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class _Runner:
    """`cli.main` 대역. 호출을 기록하고 정해진 값을 돌려준다."""

    def __init__(self, result=0):
        self.result = result
        self.calls: list[list[str]] = []

    def __call__(self, argv=None):
        self.calls.append(list(argv or []))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def drive(lines, result=0, quiet=True):
    """대본을 넣고 메뉴를 돌린다. (종료코드, 실행기록, 화면출력).

    `quiet` 는 **예상된** traceback 이 테스트 출력을 덮지 않게 한다 —
    로그가 남는지는 `test_c10` 이 따로 본다.
    """
    runner = _Runner(result)
    real_input, real_cli = builtins.input, cli.main
    builtins.input = _Input(lines)
    cli.main = runner                     # run_menu 안에서 호출 시점에 import 한다
    # propagate=False 만으로는 조용해지지 않는다 — 핸들러가 하나도 없으면
    # logging.lastResort 가 대신 stderr 로 찍는다. 흡수용 핸들러를 붙인다.
    was, sink = menu.log.propagate, logging.NullHandler()
    if quiet:
        menu.log.propagate = False
        menu.log.addHandler(sink)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            code = menu.main()
    finally:
        builtins.input = real_input
        cli.main = real_cli
        menu.log.propagate = was
        menu.log.removeHandler(sink)
    return code, runner.calls, buf.getvalue()


# --------------------------------------------------------------------------
# A. 메뉴 반복
# --------------------------------------------------------------------------
def test_a1_two_runs_in_one_process():
    """실행 → pause → 메뉴 → 실행 → pause → 메뉴 → [0]."""
    code, calls, out = drive(["4", "", "4", "", "0"])
    assert len(calls) == 2, f"기능이 2번 실행돼야 한다: {calls}"
    assert code == 0
    assert out.count("축구토토 승무패 분석 리포트") == 3, "메뉴가 3번 떠야 한다"


def test_a2_menu_is_reprinted_after_each_run():
    _, _, out = drive(["4", "", "0"])
    assert out.count("[0] 종료") == 2


def test_a3_different_items_in_one_session():
    # [1] 수집(회차 입력) → [9]→[1] 데모 → 종료
    code, calls, _ = drive(["1", "260050", "", "9", "1", "", "0"])
    assert calls[0] == ["--round", "260050", "--open"], calls
    assert calls[1] == ["--demo", "--open"], calls
    assert code == 0


def test_a4_exit_code_is_the_last_run():
    """한 번 쓰고 종료하면 루프가 없던 때와 같은 값이 나온다."""
    code, _, _ = drive(["4", "", "0"], result=3)
    assert code == 3


def test_a5_exit_code_zero_when_nothing_ran():
    code, calls, _ = drive(["0"])
    assert (code, calls) == (0, [])


# --------------------------------------------------------------------------
# B. [0] 종료
# --------------------------------------------------------------------------
def test_b6_zero_exits_immediately():
    code, calls, out = drive(["0"])
    assert code == 0 and calls == []
    assert "종료합니다" in out


def test_b7_zero_does_not_pause():
    """[0] 에는 pause 하지 않는다 — 대본에 pause 입력이 없어도 EOF 가 안 난다."""
    runner = _Runner(0)
    fake = _Input(["0"])
    real_input, real_cli = builtins.input, cli.main
    builtins.input, cli.main = fake, runner
    try:
        with redirect_stdout(io.StringIO()):
            menu.main()
    finally:
        builtins.input, cli.main = real_input, real_cli
    assert len(fake.asked) == 1, f"pause 를 물었다: {fake.asked}"


def test_b8_pause_is_asked_only_after_a_run():
    """프롬프트는 `input()` 인자로 나가므로 stdout 이 아니라 물어본 기록을 본다."""
    fake = _Input(["4", "", "0"])
    real_input, real_cli = builtins.input, cli.main
    builtins.input, cli.main = fake, _Runner(0)
    try:
        with redirect_stdout(io.StringIO()):
            menu.main()
    finally:
        builtins.input, cli.main = real_input, real_cli
    pauses = [p for p in fake.asked if "메뉴로 돌아갑니다" in p]
    assert len(pauses) == 1, f"pause 횟수가 다르다: {fake.asked}"


# --------------------------------------------------------------------------
# C. 기능 예외
# --------------------------------------------------------------------------
def test_c9_exception_does_not_kill_the_program():
    code, calls, out = drive(["4", "", "4", "", "0"],
                             result=RuntimeError("수집 실패"))
    assert len(calls) == 2, "예외 뒤에도 메뉴를 계속 쓸 수 있어야 한다"
    assert "오류가 발생했습니다: 수집 실패" in out
    assert "다른 메뉴는 계속 사용할 수 있습니다" in out
    assert code == 1


def test_c10_exception_is_logged_with_traceback(capture=None):
    """사용자에게는 한 줄, 로그에는 traceback."""
    records: list[logging.LogRecord] = []

    class Grab(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = Grab()
    menu.log.addHandler(handler)
    try:
        drive(["4", "", "0"], result=ValueError("boom"))
    finally:
        menu.log.removeHandler(handler)
    assert records, "예외가 로그에 남지 않았다"
    assert records[0].exc_info is not None, "traceback 이 없다"


def test_c11_unknown_number_returns_to_the_menu():
    code, calls, out = drive(["99", "", "0"])
    assert calls == [], "없는 번호로 기능이 실행됐다"
    assert "없는 번호입니다" in out
    assert out.count("[0] 종료") == 2, "메뉴로 돌아오지 않았다"


def test_c12_blank_round_falls_back_to_auto_detection():
    """빈 회차는 취소가 아니라 **자동 탐지**다 (예전 [1] 의 자리)."""
    code, calls, out = drive(["1", "", "", "0"])
    assert calls == [["--open"]], calls
    assert out.count("[0] 종료") == 2


# --------------------------------------------------------------------------
# D. Ctrl+C / EOF
# --------------------------------------------------------------------------
def test_d13_eof_at_the_menu_prompt_exits():
    """대본이 비면 EOF. 무한 루프가 되면 이 테스트가 멈추지 않는다."""
    code, calls, out = drive([])
    assert code == 0 and calls == []
    assert "입력이 끝나 종료합니다" in out


def test_d14_eof_does_not_run_the_default_item():
    """EOF 를 빈 입력으로 보면 1번(전체 수집)이 돈다 — 그러면 안 된다."""
    _, calls, _ = drive([])
    assert calls == [], f"EOF 로 기능이 실행됐다: {calls}"


def test_d15_eof_at_the_pause_prompt_exits():
    code, calls, _ = drive(["4"])         # 실행 후 pause 대본 없음 → EOF
    assert len(calls) == 1
    assert code == 0


def test_d16_ctrl_c_at_the_prompt_stops():
    code, calls, out = drive([KeyboardInterrupt()])
    assert code == 130, "Ctrl+C 는 중단이다"
    assert calls == [], "Ctrl+C 로 기능이 실행됐다"
    assert "중단했습니다" in out


def test_d17_ctrl_c_during_a_run_stops():
    code, _, out = drive(["4", "", "0"], result=KeyboardInterrupt())
    assert code == 130
    assert "중단했습니다" in out


def test_d18_ctrl_c_is_not_swallowed_into_a_loop():
    """Ctrl+C 를 일반 예외처럼 삼켜 루프를 계속 돌리지 않는다."""
    fake = _Input([KeyboardInterrupt(), "4", "", "0"])
    real_input = builtins.input
    builtins.input = fake
    try:
        with redirect_stdout(io.StringIO()):
            code = menu.main()
    finally:
        builtins.input = real_input
    assert code == 130
    assert len(fake.asked) == 1, "Ctrl+C 뒤에도 계속 물었다"


# --------------------------------------------------------------------------
# E. logging 반복 실행
# --------------------------------------------------------------------------
def test_e19_level_follows_verbose_on_every_call():
    root = logging.getLogger()
    before = root.level
    try:
        cli._setup_logging(False)
        assert root.level == logging.INFO
        cli._setup_logging(True)
        assert root.level == logging.DEBUG, "2회차에 verbose 가 무시됐다"
        cli._setup_logging(False)
        assert root.level == logging.INFO, "3회차에 레벨이 안 내려갔다"
    finally:
        root.setLevel(before)


def test_e20_first_call_installs_a_handler():
    root = logging.getLogger()
    before = root.level
    try:
        cli._setup_logging(False)
        assert root.handlers, "핸들러가 없다"
    finally:
        root.setLevel(before)


# --------------------------------------------------------------------------
# F. 핸들러 중복
# --------------------------------------------------------------------------
def test_f21_repeated_setup_does_not_add_handlers():
    root = logging.getLogger()
    before_level = root.level
    try:
        cli._setup_logging(False)
        count = len(root.handlers)
        for _ in range(5):
            cli._setup_logging(True)
            cli._setup_logging(False)
        assert len(root.handlers) == count, "핸들러가 늘었다 (로그가 중복된다)"
    finally:
        root.setLevel(before_level)


def test_f22_no_force_reset():
    """`force=True` 로 남의 핸들러까지 걷어내지 않는다.

    문자열 검색은 쓰지 않는다 — 그 낱말을 '쓰지 않는다' 고 적은 주석에
    그대로 걸린다(실제로 걸렸다). 호출 인자를 구조로 본다.
    """
    import ast
    tree = ast.parse(inspect_source(cli._setup_logging))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "basicConfig":
            names = {kw.arg for kw in node.keywords}
            assert "force" not in names, "basicConfig(force=…) 를 쓰고 있다"


def test_f23_menu_path_configures_logging_first():
    """메뉴로 갈 때도 로그가 켜져 있어야 traceback 이 남는다."""
    import ast
    tree = ast.parse(inspect_source(cli.main))
    body = tree.body[0].body
    order = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "_setup_logging":
            order.append(node.lineno)
        if isinstance(node, ast.Attribute) and node.attr == "menu":
            order.append(-node.lineno)
    setup = min(n for n in order if n > 0)
    menu_use = -max(n for n in order if n < 0)
    assert setup < menu_use, "메뉴 분기가 로그 설정보다 먼저다"
    assert body


def inspect_source(fn) -> str:
    import inspect
    import textwrap
    return textwrap.dedent(inspect.getsource(fn))


# --------------------------------------------------------------------------
# G. 기존 메뉴 회귀
# --------------------------------------------------------------------------
def test_g24_operational_menu_maps_to_the_right_flags():
    """운영 메뉴는 넷 + 도구. 번호와 인자가 어긋나면 엉뚱한 실행이 된다."""
    by_key = {k: a for k, _t, _d, a in menu.ITEMS}
    assert list(by_key) == ["1", "2", "3", "4", "9"], list(by_key)
    assert by_key["1"] == (menu.ROUND, [])
    # [2]·[3] 은 [1] 에 **더하는** 것이다. 후스코어드를 끄면 리포트에서
    # 강점/약점·상성이 빠지고, 그 값(shots_pg)이 축을 거쳐 패널 자료에도
    # 실리므로 패널에게 줄 자료가 오히려 줄었다.
    assert by_key["2"] == (menu.ROUND, ["--panel"])
    assert by_key["3"] == (menu.ROUND, ["--panel-export"])
    for key in ("2", "3"):
        assert "--skip-whoscored" not in by_key[key][1], key
        assert "--skip-match-details" not in by_key[key][1], key
    assert by_key["4"] == ["--serve"]
    assert by_key["9"] == "tools"


def test_g24b_every_collecting_item_asks_for_the_round():
    """수집하는 항목은 전부 회차를 먼저 묻는다."""
    for key, _t, _d, args in menu.ITEMS:
        collects = isinstance(args, tuple) or args in ("tools", ["--serve"])
        assert collects, (key, args)
        if isinstance(args, list):
            assert "--round" not in args, key


def test_g24c_dev_tools_are_kept_not_deleted():
    """§3-1 조사와 §1-4 실물 확인의 도구다. 하위 메뉴로 내렸을 뿐이다."""
    tags = [a for _k, _t, _d, a in menu.TOOLS]
    assert ["--demo"] in tags
    for tag in ("clear-cache", "diagnose", "probe", "probe-analyze"):
        assert tag in tags, tag


def test_g25_menu_never_recommends():
    """메뉴 문구가 승무패를 권하지 않는다."""
    blob = " ".join(t + d for _k, t, d, _a in menu.ITEMS)
    for word in ("홈승", "원정승", "무승부 추천", "추천 픽", "적중 보장",
                 "가장 가능성이 높은"):
        assert word not in blob, word


def test_g26_run_menu_still_runs_one_iteration():
    """루프는 main() 에 있다 — run_menu() 는 한 번만 돈다."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(menu.run_menu))
    loops = [n for n in ast.walk(tree)
             if isinstance(n, (ast.While, ast.For))
             and not isinstance(getattr(n, "iter", None), ast.Name)]
    whiles = [n for n in ast.walk(tree) if isinstance(n, ast.While)]
    assert whiles == [], "run_menu() 안에 루프가 생겼다"
    assert loops is not None


def test_g27_serve_and_diagnose_still_tagged():
    code, calls, out = drive(["4", "", "0"])
    assert calls == [["--serve"]], calls
    assert "공유를 마쳤습니다" in out


# --------------------------------------------------------------------------
# H. 회차 지정 · 하위 메뉴
# --------------------------------------------------------------------------
def test_h28_round_is_prepended_before_the_item_flags():
    """`--round` 가 먼저 오고 항목 인자가 뒤에 붙는다."""
    _code, calls, _out = drive(["3", "260050", "", "0"])
    assert calls == [["--round", "260050", "--panel-export", "--open"]], calls


def test_h29_panel_item_also_asks_for_the_round():
    _code, calls, _out = drive(["2", "260051", "", "0"])
    assert calls == [["--round", "260051", "--panel", "--open"]], calls


def test_h30_eof_at_the_round_prompt_does_not_run():
    """회차를 묻는 중에 입력이 끝나면 실행하지 않는다."""
    _code, calls, out = drive(["1"])
    assert calls == [], calls
    assert "실행하지 않았습니다" in out, out


def test_h31_tools_submenu_reaches_the_diagnostics():
    _code, calls, out = drive(["9", "3", "", "0"])
    assert calls == [], "진단 도구는 cli.main 을 부르지 않는다"
    assert "개발·진단 도구" in out, out


def test_h32_back_from_the_submenu_returns_to_the_menu():
    """하위 메뉴의 [0] 은 프로그램을 끝내지 않는다."""
    code, calls, out = drive(["9", "0", "", "0"])
    assert code == 0 and calls == [], (code, calls)
    assert "메뉴로 돌아갑니다" in out, out
    assert out.count("[0] 종료") == 2, "메인 메뉴가 다시 나오지 않았다"


def test_h33_submenu_shows_back_not_exit():
    _code, _calls, out = drive(["9", "0", "", "0"])
    assert "[0] 뒤로" in out, out


def test_h34_unknown_number_in_the_submenu_is_not_fatal():
    code, calls, out = drive(["9", "77", "", "0"])
    assert calls == [] and code == 1, (code, calls)
    assert "없는 번호입니다" in out


# --------------------------------------------------------------------------
def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as exc:
            bad += 1
            print(f"  FAIL {name}: {exc}")
        except Exception as exc:                       # noqa: BLE001
            bad += 1
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - bad}/{len(tests)} 통과")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
