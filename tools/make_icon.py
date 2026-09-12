"""Generate the Windows icon used by the packaged downgrader."""

from __future__ import annotations

import math
import struct
from pathlib import Path


SIZES = (16, 32, 48, 64, 128, 256)
NAVY = (21, 33, 46, 255)
GOLD = (224, 174, 67, 255)
GOLD_HIGHLIGHT = (255, 220, 128, 255)
INK = (9, 15, 23, 255)


def _set_pixel(pixels: bytearray, size: int, x: int, y: int, colour: tuple[int, int, int, int]) -> None:
    if 0 <= x < size and 0 <= y < size:
        # ICO DIB pixels are BGRA and stored bottom-up.
        offset = ((size - 1 - y) * size + x) * 4
        red, green, blue, alpha = colour
        pixels[offset : offset + 4] = bytes((blue, green, red, alpha))


def _icon_bitmap(size: int) -> bytes:
    red, green, blue, alpha = NAVY
    pixels = bytearray(bytes((blue, green, red, alpha)) * (size * size))
    centre = (size - 1) / 2
    outer = size * 0.43
    inner = size * 0.34

    for y in range(size):
        for x in range(size):
            distance = math.hypot(x - centre, y - centre)
            if inner <= distance <= outer:
                _set_pixel(pixels, size, x, y, GOLD)
            elif distance < inner:
                _set_pixel(pixels, size, x, y, INK)

    # A bright downward arrow makes the purpose recognizable even at 16 px.
    shaft_half = max(1, round(size * 0.075))
    shaft_top = round(size * 0.25)
    shaft_bottom = round(size * 0.55)
    head_top = round(size * 0.47)
    head_bottom = round(size * 0.73)
    head_half = round(size * 0.20)
    for y in range(shaft_top, head_bottom + 1):
        for x in range(size):
            dx = abs(x - centre)
            if y <= shaft_bottom:
                inside = dx <= shaft_half
            else:
                progress = (y - head_top) / max(1, head_bottom - head_top)
                inside = dx <= head_half * (1 - progress)
            if inside:
                _set_pixel(pixels, size, x, y, GOLD_HIGHLIGHT)

    dib_header = struct.pack(
        "<IIIHHIIIIII",
        40, size, size * 2, 1, 32, 0, size * size * 4, 0, 0, 0, 0,
    )
    and_mask = bytes(((size + 31) // 32 * 4) * size)
    return dib_header + pixels + and_mask


def build_icon(destination: Path) -> None:
    images = [_icon_bitmap(size) for size in SIZES]
    header_size = 6 + 16 * len(images)
    offset = header_size
    entries: list[bytes] = []
    for size, image in zip(SIZES, images, strict=True):
        entries.append(struct.pack("<BBBBHHII", size if size < 256 else 0, size if size < 256 else 0, 0, 0, 1, 32, len(image), offset))
        offset += len(image)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + b"".join(entries) + b"".join(images))


if __name__ == "__main__":
    build_icon(Path(__file__).resolve().parents[1] / "assets" / "skyrim-downgrader.ico")
