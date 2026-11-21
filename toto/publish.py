"""리포트 폴더를 같은 와이파이에 공개한다 — 폰에서 보기 (`--serve` · 메뉴 [5]).

리포트는 외부 참조가 하나도 없는 자체 완결 HTML 이라 폰 브라우저에서 그대로
열린다. 집 밖에서 볼 때는 GitHub Pages 게시(§1-54)를 쓴다.

예전에는 이 모듈이 리포트를 클라우드 동기화 폴더(OneDrive·구글드라이브 …)
에도 복사했다. 수집 직후에 불려 **패널 반영 전 판**을 복사할 수 있었고, 폰에서
보는 용도는 Pages 가 대신하게 되어 리팩터링 Phase 4 후속에서 지웠다 (§1-56).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


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
