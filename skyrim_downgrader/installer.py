"""Copy depot contents over the game install and read the exe's file version."""

from __future__ import annotations

import ctypes
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from skyrim_downgrader.ui import get_logger

log = get_logger("installer")


@dataclass(frozen=True)
class CopyItem:
    src: Path
    dst: Path
    size: int


def plan_copy(depot_dir: Path, game_dir: Path) -> list[CopyItem]:
    """Every file under depot_dir mapped to the same relative path under game_dir."""
    items: list[CopyItem] = []
    if not depot_dir.is_dir():
        log.warning("depot dir missing, nothing to copy: %s", depot_dir)
        return items
    for root, _dirs, files in os.walk(depot_dir):
        for name in files:
            src = Path(root) / name
            rel = src.relative_to(depot_dir)
            items.append(CopyItem(src, game_dir / rel, src.stat().st_size))
    total = sum(i.size for i in items)
    log.info("%s: %d files, %.1f MB to copy", depot_dir.name, len(items), total / 1024**2)
    return items


def copy_items(items: list[CopyItem], dry_run: bool = False) -> Iterator[CopyItem]:
    """Copy each item (overwrite), yielding after each so the caller can drive a progress bar."""
    for item in items:
        existed = item.dst.exists()
        if dry_run:
            log.info("[dry-run] %-11s %s  (%.1f MB)", "overwrite" if existed else "new", item.dst.name, item.size / 1024**2)
            yield item
            continue
        item.dst.parent.mkdir(parents=True, exist_ok=True)
        if existed and not os.access(item.dst, os.W_OK):
            log.debug("clearing read-only on %s", item.dst)
            os.chmod(item.dst, 0o666)
        shutil.copy2(item.src, item.dst)
        log.debug("copied %s -> %s (%d bytes, %s)", item.src, item.dst, item.size, "overwrote" if existed else "new")
        yield item


def file_version(path: Path) -> tuple[int, int, int, int] | None:
    """Read the Win32 VERSIONINFO of an exe/dll; None if absent."""
    if not path.is_file():
        log.debug("file_version: %s does not exist", path)
        return None
    version = ctypes.windll.version
    size = version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        log.debug("file_version: no version resource in %s", path)
        return None
    buf = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(path), 0, size, buf):
        log.debug("file_version: GetFileVersionInfoW failed for %s", path)
        return None
    ptr = ctypes.c_void_p()
    length = ctypes.c_uint()
    if not version.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)):
        return None

    class VS_FIXEDFILEINFO(ctypes.Structure):
        _fields_ = [
            ("dwSignature", ctypes.c_uint32), ("dwStrucVersion", ctypes.c_uint32),
            ("dwFileVersionMS", ctypes.c_uint32), ("dwFileVersionLS", ctypes.c_uint32),
            ("dwProductVersionMS", ctypes.c_uint32), ("dwProductVersionLS", ctypes.c_uint32),
            ("dwFileFlagsMask", ctypes.c_uint32), ("dwFileFlags", ctypes.c_uint32),
            ("dwFileOS", ctypes.c_uint32), ("dwFileType", ctypes.c_uint32),
            ("dwFileSubtype", ctypes.c_uint32), ("dwFileDateMS", ctypes.c_uint32),
            ("dwFileDateLS", ctypes.c_uint32),
        ]

    info = ctypes.cast(ptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
    ver = (info.dwFileVersionMS >> 16, info.dwFileVersionMS & 0xFFFF,
           info.dwFileVersionLS >> 16, info.dwFileVersionLS & 0xFFFF)
    log.debug("file_version(%s) = %s", path, ver)
    return ver


def version_str(ver: tuple[int, int, int, int] | None) -> str:
    return ".".join(map(str, ver)) if ver else "unknown"
