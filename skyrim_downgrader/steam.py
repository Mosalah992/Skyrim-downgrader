"""Locate Steam and the game, check processes, open the Steam console."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from skyrim_downgrader.config import APP_ID, GAME_PROCESSES
from skyrim_downgrader.ui import get_logger

log = get_logger("steam")

STEAM_CONSOLE_URL = "steam://open/console"


class SteamNotFound(RuntimeError):
    pass


# --------------------------------------------------------------------------- paths

def _read_registry(hive_name: str, subkey: str, value: str) -> str | None:
    try:
        import winreg  # noqa: WPS433 (windows only)
    except ImportError:  # pragma: no cover
        log.debug("winreg unavailable on this platform")
        return None
    hive = getattr(winreg, hive_name)
    try:
        with winreg.OpenKey(hive, subkey) as key:
            data, _ = winreg.QueryValueEx(key, value)
            log.debug("registry %s/%s/%s = %r", hive_name, subkey, value, data)
            return str(data)
    except OSError as exc:
        log.debug("registry %s/%s/%s not readable: %s", hive_name, subkey, value, exc)
        return None


def find_steam_dir(override: str | os.PathLike | None = None) -> Path:
    candidates: list[tuple[str, str | None]] = []
    if override:
        candidates.append(("--steam-dir", str(override)))
    candidates.append(("HKCU SteamPath", _read_registry("HKEY_CURRENT_USER", r"Software\Valve\Steam", "SteamPath")))
    candidates.append(("HKLM InstallPath", _read_registry("HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")))
    candidates.append(("default", r"C:\Program Files (x86)\Steam"))

    for source, raw in candidates:
        if not raw:
            continue
        path = Path(raw.replace("/", "\\")).resolve()
        if (path / "steam.exe").is_file():
            log.info("Steam dir: %s (from %s)", path, source)
            return path
        log.debug("candidate from %s rejected (no steam.exe): %s", source, path)
    raise SteamNotFound("Could not locate a Steam installation; pass --steam-dir")


_VDF_PATH_RE = re.compile(r'"path"\s+"([^"]+)"')


def library_folders(steam_dir: Path) -> list[Path]:
    """All Steam library roots (each has a steamapps/ folder), main install first."""
    libs: list[Path] = [steam_dir]
    vdf = steam_dir / "steamapps" / "libraryfolders.vdf"
    if vdf.is_file():
        text = vdf.read_text(encoding="utf-8", errors="replace")
        for raw in _VDF_PATH_RE.findall(text):
            p = Path(raw.replace("\\\\", "\\")).resolve()
            if p not in libs:
                libs.append(p)
        log.debug("libraryfolders.vdf -> %s", [str(p) for p in libs])
    else:
        log.debug("no libraryfolders.vdf at %s", vdf)
    return libs


def find_appmanifest(steam_dir: Path, app_id: int = APP_ID) -> Path | None:
    for lib in library_folders(steam_dir):
        acf = lib / "steamapps" / f"appmanifest_{app_id}.acf"
        if acf.is_file():
            log.debug("appmanifest for %s found: %s", app_id, acf)
            return acf
    log.debug("appmanifest_%s.acf not found in any library", app_id)
    return None


_INSTALLDIR_RE = re.compile(r'"installdir"\s+"([^"]+)"')


def find_game_dir(steam_dir: Path, override: str | os.PathLike | None = None) -> Path:
    if override:
        path = Path(override).resolve()
        log.info("Game dir: %s (from --game-dir)", path)
        return path
    acf = find_appmanifest(steam_dir)
    if acf:
        m = _INSTALLDIR_RE.search(acf.read_text(encoding="utf-8", errors="replace"))
        if m:
            path = acf.parent / "common" / m.group(1)
            log.info("Game dir: %s (from %s)", path, acf.name)
            return path
        log.warning("appmanifest %s has no installdir entry", acf)
    fallback = steam_dir / "steamapps" / "common" / "Skyrim Special Edition"
    log.info("Game dir: %s (fallback default)", fallback)
    return fallback


def console_log_path(steam_dir: Path) -> Path:
    return steam_dir / "logs" / "console_log.txt"


def content_catalog_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Skyrim Special Edition" / "ContentCatalog.txt"


# --------------------------------------------------------------------------- processes

def _running_images() -> set[str]:
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, check=False
        ).stdout
    except OSError as exc:  # pragma: no cover
        log.warning("tasklist failed: %s", exc)
        return set()
    names = set()
    for line in out.splitlines():
        if line.startswith('"'):
            names.add(line.split('","', 1)[0].strip('"').lower())
    return names


def is_steam_running() -> bool:
    running = "steam.exe" in _running_images()
    log.debug("steam.exe running: %s", running)
    return running


def game_processes_running() -> list[str]:
    images = _running_images()
    found = [p for p in GAME_PROCESSES if p.lower() in images]
    log.debug("game processes running: %s", found)
    return found


def ensure_steam_running(steam_dir: Path, timeout: float = 60.0) -> None:
    if is_steam_running():
        return
    exe = steam_dir / "steam.exe"
    log.info("Steam is not running - launching %s", exe)
    subprocess.Popen([str(exe)], cwd=str(steam_dir))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_steam_running():
            log.info("Steam started; waiting a few seconds for it to finish loading")
            time.sleep(8)
            return
        time.sleep(1)
    raise RuntimeError("Steam did not start within %.0fs" % timeout)


def open_console() -> None:
    log.info("Opening Steam console via %s", STEAM_CONSOLE_URL)
    os.startfile(STEAM_CONSOLE_URL)  # type: ignore[attr-defined]


def free_bytes(path: Path) -> int:
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    usage = shutil.disk_usage(probe)
    log.debug("disk usage at %s: free=%d total=%d", probe, usage.free, usage.total)
    return usage.free
