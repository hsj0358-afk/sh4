"""패널 호출은 사용자 설정을 읽지 않는다 — 중계 설정 유지 (§1-69).

    python tests/test_panel_setting_sources.py

사용자 수준 `~/.claude/settings.json` 의 `env` 에 요청 경로를 바꾸는 칸
(`ANTHROPIC_BASE_URL`·`ANTHROPIC_AUTH_TOKEN` …)이 있으면, 그 설정을 읽는
`claude -p` 는 구독이 아닌 그 경로로 나간다. 패널은 `--setting-sources
project,local` 로 그 파일만 비켜 가고 **파일은 건드리지 않는다.** 모델 호출 0회.
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_panel_auto import FakeReport, fake_cli, scratch  # noqa: E402

from toto import panelauto  # noqa: E402

ROUTED = {
    "env": {
        "ANTHROPIC_BASE_URL": "http://user:secret@localhost:31415",
        "ANTHROPIC_AUTH_TOKEN": "tok-should-never-show",
        "ANTHROPIC_MODEL": "auto",
    },
    "apiKeyHelper": "helper.sh",
}


@contextmanager
def env(**values):
    old = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _config(data=None, name="settings.json", raw=None) -> Path:
    folder = scratch()
    if raw is not None:
        (folder / name).write_bytes(raw)
    elif data is not None:
        (folder / name).write_text(json.dumps(data), encoding="utf-8")
    return folder


def _check(config_dir: Path, help_text: str | None = "  --setting-sources <s>\n"):
    """준비 점검을 돌린다. 경로 환경변수는 비운다 — 이 컨테이너 자신의 것이 섞이지 않게."""
    tmp = scratch()
    cli = fake_cli(tmp, version="9.9.9\n",
                   out='{"loggedIn":true,"authMethod":"oauth_token"}')
    saved = panelauto.cli_supports_setting_sources
    if help_text is None:
        panelauto.cli_supports_setting_sources = lambda exe, timeout=60: None
    elif "--setting-sources" not in help_text:
        panelauto.cli_supports_setting_sources = lambda exe, timeout=60: False
    clear = {k: None for k in panelauto.ROUTE_ENV_KEYS}
    try:
        with env(CLAUDE_CONFIG_DIR=str(config_dir),
                 **{panelauto.CLI_ENV: str(cli)}, **clear):
            return panelauto.preflight(FakeReport(), "TEST", base=scratch())
    finally:
        panelauto.cli_supports_setting_sources = saved


# ---------------------------------------------------------------- A 호출 인자
def test_a1_every_agent_call_skips_user_settings():
    argv = panelauto.agent_argv("claude", "지시", Path("s.md"), Path("w"),
                                session_id="sid", model="sonnet")
    i = argv.index("--setting-sources")
    assert argv[i + 1] == "project,local"
    assert "user" not in argv[i + 1].split(",")


def test_a2_bare_is_still_not_used():
    """`--bare` 는 구독 로그인을 읽지 않는다 (§1-42) — 대신 쓰는 것이 아니다."""
    argv = panelauto.agent_argv("claude", "지시", Path("s.md"), Path("w"),
                                session_id="sid", model="sonnet")
    assert "--bare" not in argv


# ---------------------------------------------------------------- B 설정 읽기
def test_b1_no_files_is_normal():
    assert panelauto.user_settings_routes(scratch()) == ([], "")


def test_b2_routes_found_and_secrets_hidden():
    found, why = panelauto.user_settings_routes(_config(ROUTED))
    assert why == ""
    keys = {k: shown for _n, k, shown in found}
    assert keys["ANTHROPIC_BASE_URL"] == "http://***@localhost:31415"
    assert keys["ANTHROPIC_AUTH_TOKEN"] == "값 있음"
    assert keys["apiKeyHelper"] == "값 있음"
    assert "ANTHROPIC_MODEL" not in keys          # 경로가 아니다
    text = repr(found)
    assert "secret" not in text and "tok-should-never-show" not in text


def test_b3_local_settings_file_is_read_too():
    folder = _config({"env": {"ANTHROPIC_BASE_URL": "http://x"}},
                     name="settings.local.json")
    found, _ = panelauto.user_settings_routes(folder)
    assert found == [("settings.local.json", "ANTHROPIC_BASE_URL", "http://x")]


def test_b4_broken_file_gives_reason_not_crash():
    found, why = panelauto.user_settings_routes(_config(raw=b"{not json"))
    assert found == [] and "settings.json" in why
    found, why = panelauto.user_settings_routes(_config(raw=b"\xff\xfe\x00{"))
    assert found == [] and why


def test_b5_settings_file_is_not_modified():
    folder = _config(ROUTED)
    path = folder / "settings.json"
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    panelauto.user_settings_routes(folder)
    _check(folder)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert sorted(p.name for p in folder.iterdir()) == ["settings.json"]


def test_b6_claude_config_dir_is_honoured():
    folder = _config(ROUTED)
    with env(CLAUDE_CONFIG_DIR=str(folder)):
        assert panelauto.claude_config_dir() == folder
        found, _ = panelauto.user_settings_routes()
    assert found
    with env(CLAUDE_CONFIG_DIR=None):
        assert panelauto.claude_config_dir() == Path.home() / ".claude"


# ---------------------------------------------------------------- C 준비 점검
def test_c1_routes_warn_but_do_not_block():
    pre = _check(_config(ROUTED))
    assert not pre.problems, pre.problems
    text = " ".join(pre.warnings)
    assert "ANTHROPIC_BASE_URL http://***@localhost:31415" in text, text
    assert "--setting-sources project,local" in text
    assert "바꾸지 않습니다" in text
    assert "tok-should-never-show" not in text and "secret" not in text


def test_c2_clean_settings_say_nothing():
    pre = _check(scratch())
    assert not pre.problems
    assert not any("사용자 설정" in w for w in pre.warnings), pre.warnings


def test_c3_cli_without_the_option_stops_before_the_round():
    pre = _check(_config(ROUTED), help_text="Usage: claude\n")
    assert any("--setting-sources 를 모릅니다" in p for p in pre.problems), pre.problems


def test_c4_unknown_support_is_a_note_not_a_block():
    pre = _check(_config(ROUTED), help_text=None)
    assert not pre.problems, pre.problems
    assert any("지원 여부를 확인하지 못했습니다" in n for n in pre.notes), pre.notes


def test_c5_process_env_route_is_warned():
    """환경변수는 --setting-sources 로 비켜 가지 않는다 — 그렇다고 말한다."""
    tmp = scratch()
    cli = fake_cli(tmp, version="9.9.9\n",
                   out='{"loggedIn":true,"authMethod":"oauth_token"}')
    clear = {k: None for k in panelauto.ROUTE_ENV_KEYS}
    clear["ANTHROPIC_BASE_URL"] = "http://localhost:31415"
    with env(CLAUDE_CONFIG_DIR=str(scratch()),
             **{panelauto.CLI_ENV: str(cli)}, **clear):
        pre = panelauto.preflight(FakeReport(), "TEST", base=scratch())
    assert any("환경변수 ANTHROPIC_BASE_URL" in w for w in pre.warnings), pre.warnings


def test_c6_help_probe_reads_the_real_cli_output():
    tmp = scratch()
    cli = fake_cli(tmp, version="9.9.9\n")       # 도움말에 옵션을 적는다
    assert panelauto.cli_supports_setting_sources(str(cli)) is True


def main() -> int:
    from _runner import run_tests
    return run_tests(globals())


if __name__ == "__main__":
    sys.exit(main())
