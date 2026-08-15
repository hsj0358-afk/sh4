"""완성된 리포트를 클라우드 동기화 폴더에도 복사한다 (폰에서 보기용).

리포트는 외부 참조가 하나도 없는 자체 완결 HTML 이라, 파일 하나만 폰으로
넘어가면 그대로 열린다. 표는 가로 스크롤이 걸려 있고 픽을 눌러 바꾸는
단통표도 순수 JS 라 폰에서 동작한다. 그래서 '동기화 폴더에 복사'만으로
모바일 활용이 끝난다.

회차별 파일과 함께 **이름이 고정된 사본**을 하나 더 둔다. 폰에서는 즐겨찾기를
한 번만 걸어두면 되므로, 매번 새 파일을 찾아 들어가는 것보다 편하다.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

# 흔한 동기화 폴더. 실제로 존재하는 것만 쓴다.
_HOME_CANDIDATES = (
    "OneDrive", "OneDrive - Personal",
    "Google Drive", "GoogleDrive", "My Drive",
    "Dropbox", "iCloudDrive", "Nextcloud",
)
_ENV_CANDIDATES = ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")


def find_cloud_roots() -> list[Path]:
    """설치돼 있는 클라우드 동기화 폴더를 찾는다 (없으면 빈 목록).

    윈도우는 OneDrive 를 설정하면 %OneDrive% 환경변수를 잡아준다. 그게 가장
    확실하고, 없으면 홈 폴더에서 흔한 이름을 찾는다.
    """
    roots: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        try:
            if not path.is_dir():
                return
            key = str(path.resolve()).lower()
        except OSError:
            return
        if key not in seen:
            seen.add(key)
            roots.append(path)

    for var in _ENV_CANDIDATES:
        value = os.environ.get(var)
        if value:
            add(Path(value))
    home = Path.home()
    for name in _HOME_CANDIDATES:
        add(home / name)
    return roots


def _targets(settings) -> list[Path]:
    """복사할 폴더 목록. 설정에 적힌 경로가 있으면 그것만 쓴다."""
    cfg = settings.output or {}
    explicit = [Path(os.path.expandvars(str(p))).expanduser()
                for p in (cfg.get("copy_to") or []) if str(p).strip()]
    if explicit:
        return explicit

    folder = str(cfg.get("cloud_folder") or "축구토토")
    return [root / folder for root in find_cloud_roots()]


def publish(report_path: Path, settings) -> list[Path]:
    """리포트를 동기화 폴더로 복사한다. 복사된 경로 목록을 돌려준다.

    복사가 실패해도 예외를 올리지 않는다 — 리포트 생성 자체는 이미 끝났고,
    동기화 폴더 문제로 실행 전체가 실패로 보이면 안 된다.
    """
    if not report_path.exists():
        return []
    latest = str((settings.output or {}).get("latest_name") or "최신리포트.html")
    done: list[Path] = []

    for target in _targets(settings):
        try:
            target.mkdir(parents=True, exist_ok=True)
            dest = target / report_path.name
            shutil.copy2(report_path, dest)
            done.append(dest)
            if latest:
                # 폰에서 즐겨찾기 하나로 항상 최신 리포트를 열 수 있게
                shutil.copy2(report_path, target / latest)
        except Exception as exc:
            log.warning("동기화 폴더 복사 실패 %s: %s", target, exc)
    return done
