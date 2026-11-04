"""바탕화면 바로가기용 아이콘(assets/toto.ico) 생성.

외부 라이브러리 없이 표준 라이브러리만으로 PNG 를 만들고 ICO 컨테이너로
감싼다(Vista 이후 ICO 는 PNG 페이로드를 허용한다).

디자인: 리포트의 홈 팀 색(파랑) 둥근 사각형 위에 흰 공, 아래쪽에 주황
막대 하나 — 리포트의 승/무/패 스택바를 축소한 모양.

    python tools/make_icon.py
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "toto.ico"

SIZES = (16, 32, 48, 64, 128, 256)

BLUE = (42, 120, 214)       # --home
ORANGE = (235, 104, 52)     # --away
GRAY = (137, 135, 129)      # --draw
WHITE = (255, 255, 255)


def _rounded(x: float, y: float, n: int, radius: float) -> bool:
    """둥근 사각형 내부인지."""
    r = radius
    cx = min(max(x, r), n - r)
    cy = min(max(y, r), n - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _pixels(n: int) -> bytes:
    """n×n RGBA 픽셀 (PNG 스캔라인, 필터 0)."""
    rows = []
    pad = n * 0.08
    ball_cx, ball_cy = n * 0.5, n * 0.42
    ball_r = n * 0.22
    bar_top, bar_bot = n * 0.72, n * 0.84

    for py in range(n):
        row = bytearray([0])            # filter byte
        for px in range(n):
            x, y = px + 0.5, py + 0.5
            if not _rounded(x, y, n, n * 0.22):
                row += bytes((0, 0, 0, 0))
                continue

            # 하단 막대: 파랑 | 회색 | 주황 (승무패 스택바)
            if bar_top <= y <= bar_bot and pad <= x <= n - pad:
                span = (n - 2 * pad)
                t = (x - pad) / span
                if t < 0.52:
                    col = WHITE
                elif t < 0.72:
                    col = GRAY
                else:
                    col = ORANGE
                row += bytes(col + (255,))
                continue

            # 공
            d = ((x - ball_cx) ** 2 + (y - ball_cy) ** 2) ** 0.5
            if d <= ball_r:
                row += bytes(WHITE + (255,))
            else:
                row += bytes(BLUE + (255,))
        rows.append(bytes(row))
    return b"".join(rows)


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def _png(n: int) -> bytes:
    ihdr = struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)   # 8bit RGBA
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(_pixels(n), 9))
            + _chunk(b"IEND", b""))


def build() -> Path:
    images = [(n, _png(n)) for n in SIZES]

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for n, data in images:
        entries += struct.pack("<BBBBHHII",
                               0 if n >= 256 else n,   # 256 은 0 으로 표기
                               0 if n >= 256 else n,
                               0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(header + entries + blobs)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"생성: {path}  ({path.stat().st_size / 1024:.1f} KB, "
          f"{len(SIZES)}개 크기)")
