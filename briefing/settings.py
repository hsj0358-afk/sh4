"""설정 로딩: config.yaml(공개 설정) + .env(비밀값) + 기본값.

PyYAML 이나 config.yaml 이 없어도 내장 기본값으로 동작하도록 설계했다.
(오프라인/샘플 테스트 시 의존성 최소화)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# config.yaml 이 없을 때 사용할 내장 기본값 ----------------------------------
DEFAULT_PRESSES = {
    "023": "조선일보",
    "025": "중앙일보",
    "020": "동아일보",
    "009": "매일경제",
    "015": "한국경제",
    "030": "전자신문",
}

DEFAULT_KEYWORDS = {
    "kt": ["KT", "케이티", "kt", "KT클라우드", "BC카드", "케이뱅크", "스카이라이프",
           "KT엠모바일", "지니뮤직", "나스미디어", "현대HCN", "김영섭"],
    "hrd": ["HRD", "인재개발", "인재육성", "교육훈련", "사내교육", "직무교육",
            "역량개발", "리스킬링", "업스킬링", "리더십 개발", "사내대학", "온보딩"],
    "hrm": ["HRM", "인사", "채용", "인력", "성과급", "연봉", "임금", "승진",
            "희망퇴직", "정년연장", "주4일제", "근로시간", "유연근무", "임금피크"],
    "esg": ["ESG", "지속가능", "탄소중립", "사회공헌", "지배구조", "친환경", "넷제로"],
    "culture": ["기업문화", "조직문화", "워라밸", "수평문화", "DEI", "다양성"],
    "labor": ["노사", "노조", "노동조합", "파업", "임단협", "노사상생", "노사관계", "상생협력"],
}

DEFAULT_COMPETITORS = ["SK텔레콤", "SKT", "LG유플러스", "삼성전자", "삼성", "현대차",
                       "네이버", "카카오", "포스코", "LG전자", "SK하이닉스"]


def _load_dotenv(path: Path) -> None:
    """python-dotenv 가 있으면 사용, 없으면 간단 파서로 .env 를 환경변수에 주입."""
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(path, override=False)
        return
    except Exception:
        pass
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore
    except Exception:
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


@dataclass
class Settings:
    # 공개 설정
    presses: dict = field(default_factory=lambda: dict(DEFAULT_PRESSES))
    keywords: dict = field(default_factory=lambda: dict(DEFAULT_KEYWORDS))
    competitors: list = field(default_factory=lambda: list(DEFAULT_COMPETITORS))
    body_char_limit: int = 2500
    max_titles_for_select: int = 800

    # 비밀/실행 설정 (.env 또는 환경변수)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"
    gmail_user: str = ""
    gmail_app_password: str = ""
    briefing_to: list = field(default_factory=list)
    briefing_from_name: str = "신문 브리핑 봇"

    @property
    def all_keywords(self) -> list:
        out = []
        for group in self.keywords.values():
            out.extend(group)
        return out

    def validate_for_run(self, need_llm: bool, need_email: bool) -> list:
        """실제 실행 전 필수값 점검. 부족한 항목 목록 반환."""
        missing = []
        if need_llm and not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        if need_email:
            if not self.gmail_user:
                missing.append("GMAIL_USER")
            if not self.gmail_app_password:
                missing.append("GMAIL_APP_PASSWORD")
            if not self.briefing_to:
                missing.append("BRIEFING_TO")
        return missing


def load_settings(config_path: Path | None = None, env_path: Path | None = None) -> Settings:
    config_path = config_path or (ROOT / "config.yaml")
    env_path = env_path or (ROOT / ".env")
    _load_dotenv(env_path)

    cfg = _load_yaml(config_path)
    s = Settings()
    if cfg.get("presses"):
        # YAML 숫자 키 방지를 위해 문자열로 정규화
        s.presses = {str(k): v for k, v in cfg["presses"].items()}
    if cfg.get("keywords"):
        s.keywords = cfg["keywords"]
    if cfg.get("competitors"):
        s.competitors = cfg["competitors"]
    if cfg.get("body_char_limit"):
        s.body_char_limit = int(cfg["body_char_limit"])
    if cfg.get("max_titles_for_select"):
        s.max_titles_for_select = int(cfg["max_titles_for_select"])

    # 비밀값
    s.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    s.anthropic_model = os.environ.get("ANTHROPIC_MODEL", s.anthropic_model)
    s.gmail_user = os.environ.get("GMAIL_USER", "")
    s.gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    to = os.environ.get("BRIEFING_TO", "")
    s.briefing_to = [x.strip() for x in to.split(",") if x.strip()]
    s.briefing_from_name = os.environ.get("BRIEFING_FROM_NAME", s.briefing_from_name)
    return s
