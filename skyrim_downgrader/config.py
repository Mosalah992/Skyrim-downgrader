"""Static facts about the rollback: app/depot/manifest ids and the target build."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

APP_ID = 489830
CK_APP_ID = 1946180
GAME_EXE = "SkyrimSE.exe"
GAME_PROCESSES = ("SkyrimSE.exe", "SkyrimSELauncher.exe", "skse64_loader.exe")
TARGET_EXE_VERSION = (1, 6, 1170, 0)
TARGET_LABEL = "1.6.1170"

# Rough on-disk size of the three SE depots, used only for the free-space preflight.
SE_DEPOTS_BYTES = 13 * 1024**3
CK_DEPOTS_BYTES = 1 * 1024**3


@dataclass(frozen=True)
class Depot:
    app_id: int
    depot_id: int
    manifest_id: int
    label: str

    @property
    def command(self) -> str:
        return f"download_depot {self.app_id} {self.depot_id} {self.manifest_id}"

    def content_dir(self, steam_dir: Path) -> Path:
        return steam_dir / "steamapps" / "content" / f"app_{self.app_id}" / f"depot_{self.depot_id}"


# Order matters: disk, core, exe (the guide's order).
DEPOTS: list[Depot] = [
    Depot(APP_ID, 489831, 8442952117333549665, "Skyrim SE disk"),
    Depot(APP_ID, 489832, 8042843504692938467, "Skyrim SE core"),
    Depot(APP_ID, 489833, 1914580699073641964, "Skyrim SE exe"),
]

CK_DEPOTS: list[Depot] = [
    Depot(CK_APP_ID, 1946182, 5099162879680505807, "Creation Kit (1/2)"),
    Depot(CK_APP_ID, 1946183, 1633303557398589581, "Creation Kit (2/2)"),
]
