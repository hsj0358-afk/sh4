"""패널 자료 내보내기 회귀 테스트 (`toto/panelexport.py`).

`--panel` 은 Anthropic API 를 부른다. 같은 분석을 클로드 채팅에서 손으로
돌리려면 지침과 자료가 파일로 있어야 한다.

**가장 중요한 것은 프롬프트가 두 벌이 아니라는 것이다.** 여기에 베껴 두면
API 판과 채팅 판이 조용히 갈라진다 — 그 뒤로는 "왜 결과가 다르지" 를
영원히 묻게 된다.

pytest 없이도 돈다:  python tests/test_panel_export.py
"""
from __future__ import annotations

import ast
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toto import moderator, panel, panelexport                  # noqa: E402
from toto.models import (                                       # noqa: E402
    EvidenceItem, Match, MatchAnalysis, MatchProb, Report, Signal,
    TeamAnalysis, TeamRef)


def _ev(team="Arsenal", metric="npxg", value=2.42, n=6,
        src="shotmap", basis="shot_events") -> EvidenceItem:
    return EvidenceItem(claim="기회 창출 수준이 높다", metric=metric,
                        value=value, period="recent6", sample_count=n,
                        provenance="observed", axis="chance_quality",
                        team=team, category="attack", context="recent",
                        finding_kind="chance_creation",
                        source=src, measurement_basis=basis)


def _match(no=1, evidence=True) -> Match:
    m = Match(no=no, home=TeamRef(display="아스널", canonical="Arsenal"),
              away=TeamRef(display="첼시", canonical="Chelsea"))
    m.league_ko, m.kickoff_kst = "프리미어리그", "2026-09-06 20:00"
    m.probs = MatchProb(home=0.52, draw=0.26, away=0.22,
                        overround=1.04, margin_per_option=0.013)
    m.analysis = MatchAnalysis(
        home=TeamAnalysis(team="Arsenal", is_home=True),
        away=TeamAnalysis(team="Chelsea", is_home=False),
        evidence=[_ev(), _ev(team="Chelsea", metric="npxga", value=1.61, n=5,
                             basis="opponent_shot_events")] if evidence else [],
        conflicts=[Signal(name="npxg", lean="UNKNOWN", strength="",
                          basis="표본에 따라 부호가 반대", sample_count=6,
                          provenance="derived", note="recent3 과 갈린다")])
    return m


def _report(matches=None) -> Report:
    r = Report(round_id="260051", generated_at="2026-09-06 12:00")
    r.matches = matches if matches is not None else [_match()]
    return r


def _run(matches=None):
    out = Path(tempfile.mkdtemp()) / "panel"
    status = panelexport.export(_report(matches), outdir=out)
    return status, out


def _sheet(out: Path) -> str:
    """경기별 시트 하나 (대체 경로). 회차 시트는 `_round()` 로 본다."""
    files = sorted((out / "경기별").glob("*.md"))
    assert files, list(out.rglob("*"))
    return files[0].read_text(encoding="utf-8")


def _round(out: Path, prefix: str) -> str:
    """회차 단위 시트를 이어 붙인 것 (여러 부로 나뉘었을 수 있다)."""
    files = sorted(f for f in out.glob(f"{prefix}*.md"))
    assert files, sorted(f.name for f in out.glob("*.md"))
    return "\n".join(f.read_text(encoding="utf-8") for f in files)


# ------------------------------------------------- 프롬프트가 두 벌이 아니다
def test_a1_no_prompt_text_is_copied_into_this_module():
    """프롬프트 문장을 여기에 베끼면 두 판이 갈라진다 (§1-8)."""
    src = Path(panelexport.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    for prompt in (panel.SYSTEM_COMMON, moderator.SYSTEM,
                   *panel.ROLE_PROMPTS.values()):
        for line in prompt.splitlines():
            line = line.strip()
            if len(line) < 25:            # 짧은 줄은 우연히 겹칠 수 있다
                continue
            for lit in literals:
                assert line not in lit, f"프롬프트를 베꼈다: {line[:40]}"


def test_a2_instructions_carry_the_real_prompts():
    text = panelexport.project_instructions()
    for prompt in (panel.SYSTEM_COMMON, moderator.SYSTEM,
                   *panel.ROLE_PROMPTS.values()):
        assert prompt in text, prompt.splitlines()[0]


def test_a3_payload_is_the_same_serialization_as_the_api():
    """채팅에 붙여넣는 문자열이 API 가 보내는 것과 같아야 한다."""
    m = _match()
    payload = panel.build_panel_payload(m)
    expected = panel.serialize_payload(payload)
    _st, out = _run([m])
    assert expected in _sheet(out), "직렬화가 API 판과 다르다"


def test_a4_moderator_input_uses_build_input():
    """사회자 입력을 여기서 다시 만들지 않는다 — 축소 규칙이 갈라진다."""
    m = _match()
    payload = panel.build_panel_payload(m)
    data = moderator.build_input(payload, [])
    sheet = _sheet(_run([m])[1])
    # opinions 를 뺀 나머지 칸이 그대로 들어 있어야 한다.
    for key in ("evidence", "conflicts", "market_reference", "match"):
        frag = json.dumps({key: data[key]}, sort_keys=True,
                          ensure_ascii=False, separators=(",", ":"))[1:-1]
        assert frag in sheet, key


# ---------------------------------------------------------------- 불변조건
def test_b1_both_analysts_get_the_same_payload_string():
    """불변조건 2 — 두 역할이 같은 자료를 본다 (§1-9)."""
    sheet = _sheet(_run()[1])
    blocks = re.findall(r"<panel_payload>\n(.*?)\n</panel_payload>",
                        sheet, re.S)
    assert len(blocks) == 2, len(blocks)
    assert blocks[0] == blocks[1], "두 역할이 다른 자료를 받는다"


def test_b2_moderator_does_not_get_the_axis_dump():
    """§1-10 — 사회자는 원지표를 다시 받지 않는다."""
    sheet = _sheet(_run()[1])
    mod = re.search(r"<moderator_input>\n(.*?)\n</moderator_input>",
                    sheet, re.S).group(1)
    for key in ('"home":{', '"away":{', '"data_quality"'):
        assert key not in mod, key


def test_b3_moderator_keeps_conflicts_and_basis():
    """빼면 사회자가 할 일을 못 하는 둘은 남는다 (§1-10)."""
    mod = re.search(r"<moderator_input>\n(.*?)\n</moderator_input>",
                    _sheet(_run()[1]), re.S).group(1)
    assert '"conflicts"' in mod
    assert '"measurement_basis"' in mod
    assert '"source"' in mod


def test_b4_three_separate_conversations_are_required():
    text = panelexport.project_instructions()
    assert "새 대화" in text, text[:200]
    for word in ("서로의 의견을 보지", "같은 자료"):
        assert word in text, word


def test_b5_limitation_is_stated_not_hidden():
    """채팅에는 구조적 강제가 없다 — 그 사실을 적어 둔다."""
    text = panelexport.project_instructions()
    assert "한계" in text and "강제하는 장치가 없습니다" in text, text[-800:]


# ---------------------------------------------------------------- 근거 게이트
def test_c1_no_evidence_means_no_sheet():
    """`run_match()` 와 같은 문. 근거 0건이면 지어낼 수밖에 없다."""
    status, out = _run([_match(evidence=False)])
    assert status.startswith("부분"), status
    names = sorted(f.name for f in out.iterdir())
    assert names == ["00_프로젝트_지침.md"], names


def test_c2_instructions_are_written_even_with_no_evidence():
    _st, out = _run([_match(evidence=False)])
    assert (out / "00_프로젝트_지침.md").read_text(encoding="utf-8")


def test_c3_mixed_round_skips_only_the_empty_ones():
    status, out = _run([_match(no=1), _match(no=2, evidence=False)])
    assert status.startswith("ok"), status
    assert "건너뜀 1경기" in status, status
    assert len(list((out / "경기별").glob("*.md"))) == 1


# ---------------------------------------------------------------- 시트 내용
def test_d1_sheet_names_the_evidence_ids():
    assert "E001" in _sheet(_run()[1])


def test_d2_sheet_carries_the_payload_hash():
    m = _match()
    digest = panel.payload_hash(panel.build_panel_payload(m))
    assert digest in _sheet(_run([m])[1])


def test_d3_opinion_slot_has_no_extra_brackets():
    """`"opinions":[...]` 안에 들어가므로 자리표시자에 대괄호를 넣지 않는다."""
    assert "[" not in panelexport.OPINIONS_SLOT
    assert "]" not in panelexport.OPINIONS_SLOT
    mod = re.search(r'"opinions":\[([^\]]*)\]', _sheet(_run()[1]))
    assert mod and panelexport.OPINIONS_SLOT in mod.group(1), mod


def test_d4_file_name_is_windows_safe():
    m = _match()
    m.home.display = 'A/B:C*D?E"F<G>H|I'
    _st, out = _run([m])
    for f in out.iterdir():
        for bad in '\\/:*?"<>|':
            assert bad not in f.name, f.name


def test_d5_no_api_key_or_client_is_touched():
    """이 경로는 API 를 부르지 않는다."""
    src = Path(panelexport.__file__).read_text(encoding="utf-8")
    for word in ("anthropic", "ANTHROPIC_API_KEY", "llm", "complete("):
        assert word not in src, word


def test_d6_no_pick_is_produced():
    """§1-3 — 승무패를 고르지 않는다."""
    text = panelexport.project_instructions() + _sheet(_run()[1])
    for word in ("추천합니다", "픽:", "베팅하십시오"):
        assert word not in text, word


# ------------------------------------------------- 회차 단위 (3개 대화)
def _round_matches(n=3, evidence=True):
    return [_match(no=i, evidence=evidence) for i in range(1, n + 1)]


def test_r1_one_file_per_step_covers_the_whole_round():
    """경기마다 대화를 열지 않는다 — 단계마다 회차 전체가 한 파일이다."""
    _st, out = _run(_round_matches(3))
    for prefix in ("01_", "02_", "03_"):
        assert list(out.glob(f"{prefix}*.md")), sorted(
            f.name for f in out.glob("*.md"))
    text = _round(out, "01_")
    for no in (1, 2, 3):
        assert f'<panel_payload no="{no}">' in text, no


def test_r2_both_analyst_steps_carry_identical_payloads():
    """불변조건 2 는 회차 단위에서도 지켜져야 한다."""
    _st, out = _run(_round_matches(3))
    a = re.findall(r"<panel_payload[^>]*>\n(.*?)\n</panel_payload>",
                   _round(out, "01_"), re.S)
    b = re.findall(r"<panel_payload[^>]*>\n(.*?)\n</panel_payload>",
                   _round(out, "02_"), re.S)
    assert a and a == b, "두 단계가 다른 자료를 받는다"


def test_r3_batch_output_schema_is_documented():
    """단일 객체 스키마를 배열로 감싸는 것이 유일한 차이다. 적어 둔다."""
    text = panelexport.project_instructions()
    assert "match_no" in text, text[-1200:]
    assert "배열" in text
    assert "유일한 점" in text, "API 판과의 차이를 밝히지 않았다"


def test_r4_moderator_round_sheet_takes_both_arrays():
    _st, out = _run(_round_matches(3))
    mod = (out / "03_3단계_사회자.md").read_text(encoding="utf-8")
    assert "[A]" in mod and "[B]" in mod, mod[:400]
    # 안내 문장에도 태그 이름이 나오므로 자료 절만 센다.
    body = mod.split("## 자료")[1]
    assert body.count('<moderator_input no="') == 3, body.count("moderator_input")
    assert '"home":{' not in mod, "사회자에게 축 지표가 갔다"


def test_r5_large_round_is_split_into_parts():
    """한 대화에 안 들어갈 크기면 나눈다 — 실패를 겪은 뒤 알게 하지 않는다."""
    out = Path(tempfile.mkdtemp()) / "panel"
    status = panelexport.export(_report(_round_matches(4)), outdir=out,
                                max_bytes=1_000)
    assert "나눔" in status, status
    parts = sorted(f.name for f in out.glob("01_*.md"))
    assert len(parts) > 1, parts
    assert all("of" in n for n in parts), parts


def test_r6_split_is_even_not_front_loaded():
    """앞에서부터 채우면 13+1 처럼 치우쳐 대화 하나가 거의 빈다."""
    payloads = [panel.build_panel_payload(m) for m in _round_matches(8)]
    one = len(panel.serialize_payload(payloads[0]).encode("utf-8"))
    groups = panelexport._chunks(payloads, one * 4)
    sizes = [len(g) for g in groups]
    assert len(groups) == 2, sizes
    assert max(sizes) - min(sizes) <= 1, sizes


def test_r7_small_round_is_not_split():
    _st, out = _run(_round_matches(2))
    assert sorted(f.name for f in out.glob("01_*.md")) == \
        ["01_1단계_데이터분석가.md"], sorted(f.name for f in out.glob("*.md"))


def test_r8_per_match_sheets_remain_as_the_fallback():
    """회차 파일이 너무 크면 경기별로 나눠 쓸 수 있어야 한다."""
    _st, out = _run(_round_matches(3))
    assert len(list((out / "경기별").glob("*.md"))) == 3
    assert "경기별" in panelexport.project_instructions()


# --------------------------------------------- 첨부할 때 채팅에 적을 말
def test_m1_every_step_file_carries_a_ready_message():
    """파일을 첨부하면 채팅에 뭘 적어야 하는지가 파일 안에 있어야 한다."""
    _st, out = _run(_round_matches(3))
    for f in sorted(out.glob("0*.md")):
        if f.name.startswith("00_"):
            continue
        text = f.read_text(encoding="utf-8")
        assert "채팅에 적을 말" in text, f.name
        assert "첨부한 파일은" in text, f.name


def test_m2_message_names_the_role_and_forbids_the_other():
    _st, out = _run(_round_matches(2))
    a = _round(out, "01_")
    b = _round(out, "02_")
    assert "역할 A — 데이터 분석가" in a and "다른 역할은 하지 마십시오" in a
    assert "역할 B — 맞대결·전술 분석가" in b and "다른 역할은 하지 마십시오" in b
    assert "역할 B" not in a.split("## 자료")[0], "1단계 메시지에 B 가 섞였다"


def test_m3_message_asks_for_the_batch_array():
    _st, out = _run(_round_matches(2))
    for prefix in ("01_", "02_"):
        head = _round(out, prefix).split("## 자료")[0]
        assert "match_no" in head and "배열 하나로" in head, prefix


def test_m4_moderator_message_has_two_slots_to_fill():
    _st, out = _run(_round_matches(2))
    head = (out / "03_3단계_사회자.md").read_text(
        encoding="utf-8").split("## 자료")[0]
    # 안내 문장에도 `◀ … ▶` 가 한 번 나오므로 채울 자리를 문구로 센다.
    for step in ("1단계 응답 배열을 통째로", "2단계 응답 배열을 통째로"):
        assert head.count(step) == 1, (step, head.count(step))
    assert "[A]" in head and "[B]" in head


def test_m5_instructions_point_at_the_ready_message():
    text = panelexport.project_instructions()
    assert "채팅에 적을 말" in text, text[:1500]


# ---------------------------------------------------------------- CLI 연결
def test_e1_cli_flag_exists_and_does_not_need_a_key():
    from toto.cli import build_parser
    args = build_parser().parse_args(["--panel-export"])
    assert args.panel_export is True
    assert args.panel is False, "패널 실행과 섞이면 API 를 부른다"


def test_e2_menu_item_does_not_call_the_api():
    from toto.menu import ITEMS
    entry = [i for i in ITEMS if i[0] == "11"]
    assert entry, [i[0] for i in ITEMS]
    flags = entry[0][3]
    assert "--panel-export" in flags, flags
    assert "--panel" not in flags, flags
    assert "--skip-match-details" not in flags, "슛맵이 없으면 근거가 없다"


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
