"""팀명 정규화 및 별칭 매칭.

베트맨은 한글("맨체스터시티"), 피나클/후스코어드는 영문("Manchester City")을 쓴다.
세 소스를 한 팀으로 묶으려면 정규명(canonical, 영문)으로 수렴시켜야 한다.

매칭 우선순위:
  1. data/teams.yaml 의 ko/en 별칭 정확 일치 (정규화 후)
  2. data/teams.learned.yaml 에 누적된 학습 별칭
  3. 토큰 유사도 (접미어 제거 후 부분/토큰 일치)

끝내 못 찾으면 None 을 돌려준다. 호출부는 이때 조용히 다른 팀 데이터를 붙이지 말고
`matched=False` 로 표시해 리포트에 경고를 남긴다.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

from .settings import ROOT, load_yaml

log = logging.getLogger(__name__)

TEAMS_FILE = ROOT / "data" / "teams.yaml"
LEARNED_FILE = ROOT / "data" / "teams.learned.yaml"

# 팀명에서 떼어내도 의미가 유지되는 접미/접두어
_NOISE_TOKENS = {
    "fc", "afc", "cf", "sc", "ac", "as", "ss", "us", "rc", "rcd", "cd", "ud", "ca",
    "sv", "vfb", "vfl", "tsg", "fsv", "bsc", "sk", "hk", "club", "calcio", "futbol",
    "football", "de", "the", "1", "04", "05", "1907", "1899", "1995",
}


def _strip_accents(text: str) -> str:
    """라틴 문자의 악센트만 제거한다.

    NFD 는 한글 음절도 자모로 분해하므로, 결합 문자(Mn)를 걷어낸 뒤 반드시
    NFC 로 되돌려 한글을 음절로 재조합한다. (이 재조합을 빠뜨리면 한글 팀명이
    아래 정규식에서 통째로 지워져 빈 문자열이 된다.)
    """
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", stripped)


def normalize_name(name: str) -> str:
    """비교용 정규화 키. 대소문자/악센트/구두점/공백/노이즈 토큰을 제거한다.

    >>> normalize_name("Manchester Utd.")
    'manchesterutd'
    >>> normalize_name("맨체스터 시티")
    '맨체스터시티'
    """
    if not name:
        return ""
    text = _strip_accents(name.strip().lower())
    text = text.replace("&", " and ")
    text = re.sub(r"[^0-9a-z가-힣\s]", " ", text)
    tokens = [t for t in text.split() if t and t not in _NOISE_TOKENS]
    if not tokens:                      # 전부 노이즈였다면 원문 유지
        tokens = text.split()
    return "".join(tokens)


def _tokens(name: str) -> set[str]:
    text = _strip_accents(name.strip().lower())
    text = re.sub(r"[^0-9a-z가-힣\s]", " ", text)
    return {t for t in text.split() if t and t not in _NOISE_TOKENS}


class TeamResolver:
    """별칭 테이블을 들고 팀명을 정규명으로 해석한다."""

    def __init__(self, teams_file: Path | None = None,
                 learned_file: Path | None = None) -> None:
        self.teams_file = teams_file or TEAMS_FILE
        self.learned_file = learned_file or LEARNED_FILE
        self._index: dict[str, str] = {}     # 정규화 별칭 → 정규명
        self._canonicals: list[str] = []
        self._league: dict[str, str] = {}    # 정규명 → 리그 키
        # 조회 결과 기억. 같은 이름을 여러 번 묻는 일이 잦은데(리그 피드를
        # 경기마다 훑는다), 매번 유사도 계산을 돌리고 경고까지 찍으면
        # 느리고 로그가 도배된다. 실패도 기억해서 한 번만 경고한다.
        self._memo: dict[str, str | None] = {}
        self._learned: dict[str, str] = {}   # 원본 표기 → 정규명 (신규 학습분)
        self._dirty = False
        self._load()

    # ---- 로딩 -----------------------------------------------------------
    def _register(self, alias: str, canonical: str) -> None:
        key = normalize_name(alias)
        if key:
            self._index.setdefault(key, canonical)

    def _load(self) -> None:
        table = load_yaml(self.teams_file)
        for canonical, entry in (table or {}).items():
            canonical = str(canonical)
            self._canonicals.append(canonical)
            self._register(canonical, canonical)
            entry = entry or {}
            for alias in (entry.get("ko") or []):
                self._register(str(alias), canonical)
            for alias in (entry.get("en") or []):
                self._register(str(alias), canonical)
            if entry.get("league"):
                self._league[canonical] = str(entry["league"])

        for alias, canonical in (load_yaml(self.learned_file) or {}).items():
            self._register(str(alias), str(canonical))
            if str(canonical) not in self._canonicals:
                self._canonicals.append(str(canonical))

        log.debug("팀 별칭 %d개 / 정규명 %d개 로드", len(self._index), len(self._canonicals))

    # ---- 해석 -----------------------------------------------------------
    def resolve(self, name: str, learn: bool = True) -> str | None:
        """팀명 → 정규명. 못 찾으면 None."""
        if not name or not name.strip():
            return None

        memo_key = (name.strip(), learn)
        if memo_key in self._memo:
            return self._memo[memo_key]

        result = self._resolve_uncached(name, learn)
        self._memo[memo_key] = result
        return result

    def _resolve_uncached(self, name: str, learn: bool) -> str | None:
        key = normalize_name(name)
        if not key:
            log.warning("팀명 정규화 결과가 비었음: %r", name)
            return None
        if key in self._index:
            return self._index[key]

        # 부분 문자열 매칭: "맨체스터시티(홈)" 같은 군더더기 표기 대응.
        # 양쪽 모두 최소 길이를 요구한다 — 짧은 키는 엉뚱한 팀에 들러붙는다.
        if len(key) >= 3:
            for alias_key, canonical in self._index.items():
                if len(alias_key) < 3:
                    continue
                if alias_key in key or key in alias_key:
                    if learn:
                        self._learn(name, canonical)
                    return canonical

        # 토큰 유사도: 영문 표기 차이 대응 ("Wolverhampton Wanderers" ↔ "Wolverhampton")
        best, best_score = None, 0.0
        want = _tokens(name)
        if want:
            for canonical in self._canonicals:
                have = _tokens(canonical)
                if not have:
                    continue
                score = len(want & have) / len(want | have)
                if score > best_score:
                    best, best_score = canonical, score
        if best and best_score >= 0.5:
            if learn:
                self._learn(name, best)
            return best

        log.warning("팀명 매칭 실패: %r", name)
        return None

    def _learn(self, alias: str, canonical: str) -> None:
        key = normalize_name(alias)
        if key in self._index:
            return
        self._index[key] = canonical
        self._learned[alias.strip()] = canonical
        self._dirty = True
        self._memo.clear()          # 인덱스가 바뀌었으니 기억한 결과를 버린다

    def save_learned(self) -> None:
        """이번 실행에서 새로 알아낸 별칭을 파일에 누적 저장한다."""
        if not self._dirty or not self._learned:
            return
        try:
            import yaml  # type: ignore
        except Exception:
            return
        existing = load_yaml(self.learned_file) or {}
        existing.update(self._learned)
        try:
            self.learned_file.parent.mkdir(parents=True, exist_ok=True)
            self.learned_file.write_text(
                "# 자동 학습된 팀명 별칭 (프로그램이 갱신한다)\n"
                + yaml.safe_dump(existing, allow_unicode=True, sort_keys=True),
                encoding="utf-8")
            log.info("학습 별칭 %d건 저장 → %s", len(self._learned), self.learned_file)
        except Exception as exc:
            log.warning("학습 별칭 저장 실패: %s", exc)

    def league_of(self, canonical: str) -> str | None:
        """정규명 → 소속 리그 키. 베트맨 경기표에는 리그명이 없어서
        팀명으로 리그를 역추론해야 배당률 조회가 가능하다."""
        return self._league.get(canonical)

    def match_pair(self, name_a: str, name_b: str) -> bool:
        """두 표기가 같은 팀인지."""
        ra, rb = self.resolve(name_a, learn=False), self.resolve(name_b, learn=False)
        if ra and rb:
            return ra == rb
        return normalize_name(name_a) == normalize_name(name_b)
