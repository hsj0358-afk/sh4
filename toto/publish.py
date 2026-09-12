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

# 홈 폴더 아래에 생기는 동기화 폴더들. 실제로 존재하는 것만 쓴다.
_HOME_CANDIDATES = (
    "OneDrive", "OneDrive - Personal",
    "Google Drive", "GoogleDrive", "My Drive", "내 드라이브",
    "Dropbox", "iCloudDrive",
    "NAVER MYBOX", "네이버 MYBOX", "MYBOX", "NaverCloud", "네이버 클라우드",
    "Nextcloud", "MEGA", "pCloudDrive", "Sync",
)
_ENV_CANDIDATES = ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")
# 구글드라이브 데스크톱은 홈이 아니라 별도 드라이브로 붙는다 (보통 G:\내 드라이브)
_DRIVE_CANDIDATES = ("My Drive", "내 드라이브")


def find_cloud_roots() -> list[Path]:
    """설치돼 있는 클라우드 동기화 폴더를 찾는다 (없으면 빈 목록).

    윈도우는 OneDrive 를 설정하면 %OneDrive% 환경변수를 잡아준다. 구글드라이브
    데스크톱은 홈 폴더가 아니라 가상 드라이브(G: 등)로 붙으므로 드라이브
    문자도 훑는다.
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
    if os.name == "nt":
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            for name in _DRIVE_CANDIDATES:
                add(Path(f"{letter}:/") / name)
    return roots


def _excluded(path: Path, patterns: list[str]) -> bool:
    text = str(path).lower()
    return any(p.strip().lower() in text for p in patterns if str(p).strip())


def _targets(settings) -> list[Path]:
    """복사할 폴더 목록. 설정에 적힌 경로가 있으면 그것만 쓴다."""
    cfg = settings.output or {}
    explicit = [Path(os.path.expandvars(str(p))).expanduser()
                for p in (cfg.get("copy_to") or []) if str(p).strip()]
    if explicit:
        return explicit

    # 회사 계정 OneDrive 처럼 개인 파일을 두고 싶지 않은 폴더를 걸러낸다.
    skip = [str(s) for s in (cfg.get("copy_to_exclude") or [])]
    folder = str(cfg.get("cloud_folder") or "축구토토")
    return [root / folder for root in find_cloud_roots()
            if not _excluded(root, skip)]


def lan_addresses() -> list[str]:
    """이 PC 가 같은 와이파이에서 보이는 주소들."""
    import socket
    found: list[str] = []

    def add(ip: str) -> None:
        if ip and not ip.startswith("127.") and ip not in found:
            found.append(ip)

    # 바깥으로 나가는 경로에 붙은 주소가 보통 공유기가 준 주소다.
    # UDP 라 실제로 패킷을 보내지는 않는다.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        add(sock.getsockname()[0])
    except OSError:
        pass
    finally:
        sock.close()
    try:
        add_all = socket.gethostbyname_ex(socket.gethostname())[2]
        for ip in add_all:
            add(ip)
    except OSError:
        pass
    return found


def serve(settings, port: int = 8899, open_path: str | None = None) -> int:
    """리포트 폴더를 같은 와이파이에 공개한다 (Ctrl+C 로 종료).

    클라우드 계정을 전혀 쓰지 않는 방법이다. PC 가 켜져 있고 폰이 같은
    와이파이에 있을 때만 열리지만, 회사 계정 폴더에 개인 파일을 두지 않아도
    되고 설치할 것도 없다.
    """
    import functools
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    root = settings.output_dir
    root.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root))

    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    except OSError as exc:
        log.error("%d번 포트를 열지 못했습니다 (%s). --serve-port 로 다른 번호를 "
                  "쓰세요.", port, exc)
        return 1

    addresses = lan_addresses()
    print()
    print("=" * 60)
    print("  폰에서 아래 주소를 여세요 (같은 와이파이에 있어야 합니다)")
    print("=" * 60)
    if addresses:
        for ip in addresses:
            suffix = f"/{open_path}" if open_path else "/"
            print(f"    http://{ip}:{port}{suffix}")
    else:
        print("    이 PC 의 와이파이 주소를 찾지 못했습니다.")
        print("    명령 프롬프트에서 ipconfig 로 IPv4 주소를 확인하세요.")
    print()
    print(f"  공개 폴더: {root}")
    print("  ※ 처음 실행하면 윈도우 방화벽이 물어봅니다 — '개인 네트워크' 허용.")
    print("  ※ 끄려면 이 창에서 Ctrl+C.")
    print("=" * 60)
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n공유를 멈췄습니다.")
    finally:
        server.server_close()
    return 0


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
