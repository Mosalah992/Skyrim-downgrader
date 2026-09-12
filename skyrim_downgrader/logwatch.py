"""Tail Steam's logs/console_log.txt and parse depot download events.

Real lines observed on this machine:
  [2026-08-24 08:47:57] Downloading depot 489832 (26 files, 7260 MB) ...
  [2026-08-24 10:48:17] Depot download complete : "C:\...\app_489830\depot_489832" (manifest 8042843504692938467)
  [2026-08-24 20:36:15] Depot download failed : Failed updating depot 489831 while downloading chunk "..." (Failure) (Content unavailable)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from skyrim_downgrader.ui import get_logger

log = get_logger("logwatch")

TIMESTAMP_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*")
DOWNLOADING_RE = re.compile(r"Downloading depot (\d+) \((\d+) files, (\d+) MB\)")
COMPLETE_RE = re.compile(r'Depot download complete : "(.+?)" \(manifest (\d+)\)')
FAILED_RE = re.compile(r"Depot download failed : (.+?)\s*$")


@dataclass(frozen=True)
class Event:
    kind: str  # "downloading" | "complete" | "failed"
    timestamp: str
    raw: str
    depot_id: int | None = None
    manifest_id: int | None = None
    path: str | None = None
    files: int | None = None
    size_mb: int | None = None
    reason: str | None = None


def parse_line(line: str) -> Event | None:
    line = line.rstrip("\r\n")
    ts_match = TIMESTAMP_RE.match(line)
    ts = ts_match.group(1) if ts_match else ""
    body = line[ts_match.end():] if ts_match else line

    if m := DOWNLOADING_RE.search(body):
        return Event("downloading", ts, line, depot_id=int(m.group(1)), files=int(m.group(2)), size_mb=int(m.group(3)))
    if m := COMPLETE_RE.search(body):
        path = m.group(1)
        depot = None
        if dm := re.search(r"depot_(\d+)$", path):
            depot = int(dm.group(1))
        return Event("complete", ts, line, depot_id=depot, manifest_id=int(m.group(2)), path=path)
    if m := FAILED_RE.search(body):
        reason = m.group(1)
        depot = None
        if dm := re.search(r"depot (\d+)", reason):
            depot = int(dm.group(1))
        return Event("failed", ts, line, depot_id=depot, reason=reason)
    return None


class LogTail:
    """Incremental reader over console_log.txt. Steam appends; we remember our byte offset."""

    def __init__(self, path: Path):
        self.path = path
        self.offset = 0
        log.debug("LogTail on %s", path)

    def seek_to_end(self) -> None:
        self.offset = self.path.stat().st_size if self.path.exists() else 0
        log.debug("log offset set to end: %d", self.offset)

    def read_new_lines(self) -> list[str]:
        if not self.path.exists():
            return []
        size = self.path.stat().st_size
        if size < self.offset:  # rotated / truncated
            log.warning("console_log.txt shrank (%d -> %d); restarting from 0", self.offset, size)
            self.offset = 0
        if size == self.offset:
            return []
        with self.path.open("rb") as fh:
            fh.seek(self.offset)
            data = fh.read()
            self.offset = fh.tell()
        lines = data.decode("utf-8", errors="replace").splitlines()
        for ln in lines:
            log.debug("console_log: %s", ln)
        return lines

    def new_events(self) -> list[Event]:
        events = [ev for ev in (parse_line(ln) for ln in self.read_new_lines()) if ev]
        for ev in events:
            log.debug("event: %s", ev)
        return events

    def wait_for(
        self,
        predicate: Callable[[Event], bool],
        timeout: float | None,
        poll: float = 0.5,
        on_tick: Callable[[float], None] | None = None,
    ) -> Event | None:
        """Block until an event satisfying predicate arrives, or timeout (None = forever)."""
        start = time.monotonic()
        while True:
            for ev in self.new_events():
                if predicate(ev):
                    return ev
            elapsed = time.monotonic() - start
            if on_tick:
                on_tick(elapsed)
            if timeout is not None and elapsed >= timeout:
                log.debug("wait_for timed out after %.1fs", elapsed)
                return None
            time.sleep(poll)


def iter_events(path: Path) -> Iterator[Event]:
    if not path.exists():
        return
    with path.open("rb") as fh:
        for raw in fh:
            ev = parse_line(raw.decode("utf-8", errors="replace"))
            if ev:
                yield ev


def last_event_for_depot(path: Path, depot_id: int) -> Event | None:
    """Latest downloading/complete/failed event that concerns depot_id (whole-file scan)."""
    last: Event | None = None
    current_depot: int | None = None
    for ev in iter_events(path):
        # A 'failed' line usually names the depot; when it doesn't, attribute it to the
        # depot whose 'Downloading' line came last.
        if ev.kind == "downloading":
            current_depot = ev.depot_id
        depot = ev.depot_id if ev.depot_id is not None else current_depot
        if depot == depot_id:
            last = ev
    log.debug("last event for depot %s: %s", depot_id, last)
    return last
