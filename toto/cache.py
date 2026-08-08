"""날짜별 JSON 파일 캐시.

후스코어드 수집은 팀당 페이지를 하나씩 여느라 느리고(요청 간 4초 대기),
차단 위험도 있다. 같은 날 재실행할 때 재크롤링하지 않도록 소스별 응답을
`cache/<날짜>/<소스>/<키>.json` 에 저장한다.

수집 실패 시 원본 HTML 을 함께 남길 수 있게 `save_debug()` 도 제공한다 —
셀렉터가 어긋났을 때 이 파일이 있어야 파서를 고칠 수 있다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .settings import ROOT

log = logging.getLogger(__name__)

CACHE_ROOT = ROOT / "cache"


def _safe(name: str) -> str:
    """파일명으로 쓸 수 있게 정리. 너무 길거나 특수문자가 많으면 해시로 대체."""
    slug = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", name).strip("_")
    if not slug or len(slug) > 80:
        slug = hashlib.sha1(name.encode("utf-8")).hexdigest()[:16]
    return slug


class Cache:
    def __init__(self, enabled: bool = True, day: str | None = None,
                 root: Path | None = None) -> None:
        self.enabled = enabled
        self.day = day or datetime.now().strftime("%Y-%m-%d")
        self.root = (root or CACHE_ROOT) / self.day

    def _path(self, source: str, key: str, ext: str = "json") -> Path:
        return self.root / source / f"{_safe(key)}.{ext}"

    def get(self, source: str, key: str) -> Any | None:
        if not self.enabled:
            return None
        path = self._path(source, key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            log.debug("캐시 적중 %s/%s", source, key)
            return data
        except Exception as exc:
            log.warning("캐시 읽기 실패 %s: %s", path, exc)
            return None

    def set(self, source: str, key: str, value: Any) -> None:
        if not self.enabled:
            return
        path = self._path(source, key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        except Exception as exc:
            log.warning("캐시 저장 실패 %s: %s", path, exc)

    def save_debug(self, source: str, key: str, html: str) -> Path | None:
        """파싱 실패 시 원본 HTML 을 남긴다 (셀렉터 수정용)."""
        path = self._path(source, f"FAILED_{key}", ext="html")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
            log.warning("파싱 실패 원본 저장 → %s", path)
            return path
        except Exception:
            return None

    # 브라우저 프로필 (후스코어드 통과 쿠키 재사용)
    @property
    def browser_profile(self) -> Path:
        path = (self.root.parent / "browser")
        path.mkdir(parents=True, exist_ok=True)
        return path
