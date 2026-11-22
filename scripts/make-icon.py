"""Draws itor's icon (dark rounded square, white "i") and writes apps/desktop/icons/itor.ico.

Standard library only. Run: python scripts/make-icon.py
"""
import pathlib
import struct
import zlib

BG = (10, 10, 10, 255)        # #0A0A0A
BORDER = (64, 64, 64, 255)    # thin border so it stays visible on a dark taskbar
FG = (250, 250, 250, 255)     # #FAFAFA
CLEAR = (0, 0, 0, 0)


def inside_rounded(x: float, y: float, size: int, radius: float) -> bool:
    cx = min(max(x, radius), size - radius)
    cy = min(max(y, radius), size - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def pixel(x: int, y: int, size: int) -> tuple[int, int, int, int]:
    # 4x4 supersampling for smooth edges
    samples = []
    for sy in range(4):
        for sx in range(4):
            px, py = x + (sx + 0.5) / 4, y + (sy + 0.5) / 4
            radius = size * 0.2
            if not inside_rounded(px, py, size, radius):
                samples.append(CLEAR)
                continue
            border = max(1.0, size / 48)
            # thin border: points inside the shape but not inside the shape shrunk by `border`
            inner = inside_rounded(px - border, py - border, size - 2 * border, radius - border) \
                if border <= px <= size - border and border <= py <= size - border else False
            color = BG if inner else BORDER
            # the "i": a square dot and a stem, centred
            stem_w = size * 0.13
            left = (size - stem_w) / 2
            if left <= px <= left + stem_w and (size * 0.2 <= py <= size * 0.33 or size * 0.41 <= py <= size * 0.8):
                color = FG
            samples.append(color)
    return tuple(round(sum(s[i] for s in samples) / len(samples)) for i in range(4))  # type: ignore[return-value]


def png(size: int) -> bytes:
    rows = b"".join(b"\x00" + b"".join(bytes(pixel(x, y, size)) for x in range(size)) for y in range(size))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


def ico(sizes: list[int]) -> bytes:
    images = [png(size) for size in sizes]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for size, data in zip(sizes, images):
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return out + b"".join(images)


if __name__ == "__main__":
    root = pathlib.Path(__file__).resolve().parents[1]
    target = root / "apps/desktop/icons/itor.ico"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(ico([16, 24, 32, 48, 64, 128, 256]))
    (root / "apps/desktop/icons/itor-256.png").write_bytes(png(256))
    print(f"wrote {target}")
