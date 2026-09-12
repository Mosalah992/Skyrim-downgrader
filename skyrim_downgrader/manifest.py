"""Edit appmanifest_<app>.acf so Steam stops auto-updating the game."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from skyrim_downgrader.ui import get_logger

log = get_logger("manifest")

_AUB_RE = re.compile(r'("AutoUpdateBehavior"\s+")(\d+)(")')
_BUILDID_RE = re.compile(r'"buildid"\s+"(\d+)"')

# Steam's meaning of AutoUpdateBehavior:
#   0 = always keep updated, 1 = only update when I launch it, 2 = high priority
ONLY_UPDATE_ON_LAUNCH = 1
ALWAYS_UPDATE = 0


def is_read_only(path: Path) -> bool:
    return not os.access(path, os.W_OK)


def set_read_only(path: Path, flag: bool) -> None:
    mode = path.stat().st_mode
    new_mode = (mode & ~stat.S_IWRITE) if flag else (mode | stat.S_IWRITE)
    os.chmod(path, new_mode)
    log.info("%s: read-only %s", path.name, "set" if flag else "cleared")


def read_auto_update_behavior(path: Path) -> int | None:
    m = _AUB_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    return int(m.group(2)) if m else None


def read_buildid(path: Path) -> str | None:
    m = _BUILDID_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    return m.group(1) if m else None


def set_auto_update_behavior(path: Path, value: int) -> bool:
    """Rewrite the AutoUpdateBehavior value. Returns True if the file changed."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _AUB_RE.search(text)
    if not m:
        log.warning("%s has no AutoUpdateBehavior entry; leaving untouched", path)
        return False
    current = int(m.group(2))
    if current == value:
        log.info("%s: AutoUpdateBehavior already %d", path.name, value)
        return False
    new_text = _AUB_RE.sub(rf"\g<1>{value}\g<3>", text, count=1)
    was_ro = is_read_only(path)
    if was_ro:
        set_read_only(path, False)
    path.write_text(new_text, encoding="utf-8")
    log.info("%s: AutoUpdateBehavior %d -> %d", path.name, current, value)
    if was_ro:
        set_read_only(path, True)
    return True
