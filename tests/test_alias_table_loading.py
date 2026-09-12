"""별칭 테이블 적재 진단 회귀 테스트.

260050 재실행에서 **28개 팀 전부** 매칭에 실패했다. 화면에 보인 것은
`팀명 매칭 실패: '첼시'` 같은 28줄뿐이었고, 그 이름들은 전부
`data/teams.yaml` 에 그대로 들어 있다(확인함). 즉 이름이 이상한 게 아니라
**테이블이 안 읽힌 것**인데, 그 사실을 말해 주는 줄이 한 줄도 없었다.

원인은 두 군데의 침묵이었다.

  · `settings.load_yaml()` 이 네 가지 실패(파일 없음·PyYAML 없음·인코딩·
    파싱)를 전부 조용히 삼키고 `{}` 를 돌려줬다.
  · `TeamResolver._load()` 가 적재 결과를 `log.debug` 로만 남겨, 테이블이
    통째로 비어도 보통 실행에서는 보이지 않았다.

**돌려주는 값은 바꾸지 않는다** — 실패해도 `{}` 이고 프로그램은 계속 돈다
(§1-6 의 '한 소스가 실패해도 나머지는 진행한다'). 바뀐 것은 사유가 보이는가
하나뿐이다.

pytest 없이도 돈다:  python tests/test_alias_table_loading.py
"""
from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import normalize as nz                                # noqa: E402
from toto.settings import ROOT, load_yaml                       # noqa: E402


class _Capture(logging.Handler):
    """레벨별로 메시지를 모은다."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def messages(self, level: int) -> list[str]:
        return [r.getMessage() for r in self.records if r.levelno == level]


def _capture(logger_name: str):
    logger = logging.getLogger(logger_name)
    cap = _Capture()
    logger.addHandler(cap)
    old_level, old_prop = logger.level, logger.propagate
    logger.setLevel(logging.DEBUG)
    logger.propagate = False           # 루트로 새어 화면을 더럽히지 않게
    return logger, cap, (old_level, old_prop)


def _restore(logger, cap, saved) -> None:
    logger.removeHandler(cap)
    logger.setLevel(saved[0])
    logger.propagate = saved[1]


def _tmp(name: str, data: bytes) -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / name
    p.write_bytes(data)
    return p


# ---------------------------------------------------------------- load_yaml
def test_a1_missing_file_is_quiet():
    """없는 파일은 정상일 수 있다(학습 별칭·승강 반영분). 경고하지 않는다."""
    logger, cap, saved = _capture("toto.settings")
    try:
        assert load_yaml(Path("/nope/absent.yaml")) == {}
        assert cap.messages(logging.WARNING) == [], cap.messages(logging.WARNING)
    finally:
        _restore(logger, cap, saved)


def test_a2_broken_yaml_warns_with_the_path():
    logger, cap, saved = _capture("toto.settings")
    try:
        path = _tmp("broken.yaml", b"a: [1, 2\n  b: {{{\n")
        assert load_yaml(path) == {}
        warned = " ".join(cap.messages(logging.WARNING))
        assert path.name in warned, warned
    finally:
        _restore(logger, cap, saved)


def test_a3_non_utf8_file_warns():
    """한국어 윈도우에서 cp949 로 저장되면 조용히 빈 dict 가 됐었다."""
    logger, cap, saved = _capture("toto.settings")
    try:
        path = _tmp("cp949.yaml", "첼시: {ko: [첼시]}\n".encode("cp949"))
        assert load_yaml(path) == {}
        warned = " ".join(cap.messages(logging.WARNING))
        assert "UTF-8" in warned, warned
    finally:
        _restore(logger, cap, saved)


def test_a4_valid_yaml_still_loads_and_is_quiet():
    logger, cap, saved = _capture("toto.settings")
    try:
        path = _tmp("ok.yaml", "Chelsea:\n  ko: [첼시]\n".encode("utf-8"))
        assert load_yaml(path) == {"Chelsea": {"ko": ["첼시"]}}
        assert cap.messages(logging.WARNING) == []
    finally:
        _restore(logger, cap, saved)


def test_a5_failures_still_return_empty_dict_not_raise():
    """동작은 바뀌지 않는다 — 실패해도 예외가 아니라 빈 dict 다."""
    logger, cap, saved = _capture("toto.settings")   # 경고를 화면에 흘리지 않는다
    try:
        for data in (b"a: [1, 2\n  b: {{{\n", "첼시: x\n".encode("cp949")):
            assert load_yaml(_tmp("x.yaml", data)) == {}
    finally:
        _restore(logger, cap, saved)


# ------------------------------------------------------------ TeamResolver
def test_b1_empty_table_is_reported_as_error():
    """테이블이 비면 모든 팀이 실패한다. 그 사실을 반드시 말한다."""
    logger, cap, saved = _capture("toto.normalize")
    try:
        empty = _tmp("teams.yaml", b"")
        nz.TeamResolver(teams_file=empty, learned_file=empty / "none",
                        league_file=empty / "none")
        errs = " ".join(cap.messages(logging.ERROR))
        assert "별칭" in errs, errs
        assert "teams.yaml" in errs, errs
    finally:
        _restore(logger, cap, saved)


def test_b2_error_says_whether_the_file_exists():
    logger, cap, saved = _capture("toto.normalize")
    try:
        missing = Path("/nope/teams.yaml")
        nz.TeamResolver(teams_file=missing, learned_file=missing,
                        league_file=missing)
        errs = " ".join(cap.messages(logging.ERROR))
        assert "아니오" in errs, errs
    finally:
        _restore(logger, cap, saved)


def test_b3_loaded_table_reports_counts_at_info():
    """정상일 때도 몇 개 읽었는지 보인다 — debug 면 보통 실행에서 안 보인다."""
    logger, cap, saved = _capture("toto.normalize")
    try:
        nz.TeamResolver()
        infos = " ".join(cap.messages(logging.INFO))
        assert "별칭" in infos, infos
        assert cap.messages(logging.ERROR) == [], cap.messages(logging.ERROR)
    finally:
        _restore(logger, cap, saved)


def test_b4_real_table_is_not_empty():
    r = nz.TeamResolver()
    assert len(r._index) > 100, len(r._index)


# ------------------------------------------------------- 실물 회차(260050)
# 베트맨 게임슬립이 팀명을 폭에 맞춰 자른다. 잘린 표기 그대로 매칭돼야 한다.
BETMAN_260050 = [
    "브렌트퍼", "선덜랜드", "브라이턴", "리즈U", "풀럼", "크리스털",
    "맨체스C", "코번트리", "노팅엄F", "토트넘", "인테르", "나폴리",
    "헐시티", "A빌라", "AS로마", "아탈란타", "에버턴", "맨체스U",
    "프로시노", "베네치아", "파르마", "AC몬차", "아스널", "첼시",
    "볼로냐", "사수올로", "유벤투스", "AC밀란",
]


def test_c1_all_betman_260050_names_resolve():
    r = nz.TeamResolver()
    missed = [n for n in BETMAN_260050
              if not r.resolve(n, learn=False, quiet=True)]
    assert not missed, f"매칭 실패: {missed}"


def test_c2_truncated_names_map_to_the_right_club():
    r = nz.TeamResolver()
    for name, want in (("맨체스C", "Manchester City"),
                       ("맨체스U", "Manchester United"),
                       ("노팅엄F", "Nottingham Forest"),
                       ("A빌라", "Aston Villa"),
                       ("리즈U", "Leeds")):
        got = r.resolve(name, learn=False, quiet=True)
        assert got == want, f"{name} → {got}"


def test_c3_teams_file_is_utf8_readable():
    """teams.yaml 이 UTF-8 로 읽히는지 직접 확인한다."""
    (ROOT / "data" / "teams.yaml").read_text(encoding="utf-8")


# ------------------------------------------------------- 필수 의존성 확인
# PyYAML 이 없으면 config 도 별칭 테이블도 통째로 안 읽혀 모든 팀명이
# 실패한다. 그런데도 예전에는 10초를 돌려 빈 리포트를 만들어 냈다
# (실측: 260050, 52.3KB, 확인 필요 43건). 그건 결과가 아니라 소음이다.
def test_d1_deps_ok_in_this_environment():
    from toto import cli
    assert cli._missing_required_deps() is False


def test_d2_missing_pyyaml_is_detected_and_explained():
    import importlib.util

    from toto import cli
    logger, cap, saved = _capture("toto")   # cli 는 getLogger("toto") 를 쓴다
    real = importlib.util.find_spec
    try:
        importlib.util.find_spec = (
            lambda name, *a, **k: None if name == "yaml" else real(name, *a, **k))
        assert cli._missing_required_deps() is True
        msg = " ".join(cap.messages(logging.ERROR))
    finally:
        importlib.util.find_spec = real
        _restore(logger, cap, saved)
    assert "PyYAML" in msg, msg
    assert "requirements-toto.txt" in msg, msg      # 무엇을 하면 되는지
    assert "Activate.ps1" in msg, msg               # 윈도우에서 가장 잦은 원인
    assert sys.executable in msg, msg               # 어느 파이썬으로 돌았나


def test_d3_run_stops_before_doing_any_work():
    """빈 리포트를 만들지 않고, 브라우저도 띄우지 않는다."""
    from toto import cli
    out = Path(tempfile.mkdtemp()) / "should_not_exist.html"
    logger, cap, saved = _capture("toto")   # cli 는 getLogger("toto") 를 쓴다
    real = cli._missing_required_deps
    try:
        cli._missing_required_deps = lambda: True
        rc = cli.main(["--demo", "-o", str(out)])
    finally:
        cli._missing_required_deps = real
        _restore(logger, cap, saved)
    assert rc == 2, rc
    assert not out.exists(), "필수 패키지가 없는데 리포트를 만들었다"


def test_d4_optional_deps_are_not_required():
    """requests·bs4·playwright 는 소스별 '실패 (사유)' 로 다룬다 (§1-6).

    여기 목록을 늘리면 멀쩡히 돌던 설정이 통째로 막힌다.
    """
    from toto import cli
    assert [mod for mod, _ in cli._REQUIRED_MODULES] == ["yaml"], \
        cli._REQUIRED_MODULES


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
