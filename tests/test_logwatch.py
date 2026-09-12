from pathlib import Path

from skyrim_downgrader import logwatch

# Real lines from this machine's Steam/logs/console_log.txt.
LOG = """\
[2026-08-23 20:37:36] Depot download complete : "C:\\Program Files (x86)\\Steam\\steamapps\\content\\app_489830\\depot_489833" (manifest 1914580699073641964)
[2026-08-24 08:47:57] Downloading depot 489832 (26 files, 7260 MB) ...
[2026-08-24 10:48:17] Depot download complete : "C:\\Program Files (x86)\\Steam\\steamapps\\content\\app_489830\\depot_489832" (manifest 8042843504692938467)
[2026-08-24 17:59:25] Downloading depot 489831 (19 files, 4663 MB) ...
[2026-08-24 20:36:01] Depot download failed : Failed to write patch state file (File locked)
[2026-08-24 20:36:15] Depot download failed : Failed updating depot 489831 while downloading chunk "d75177b2f52f4a488795178fd0dd72f4a71a3b46" (Failure) (Content unavailable)
[2026-08-24 20:43:39] Depot download failed : Failed downloading 1 manifests (No connection)
[2026-08-24 20:45:18] GameAction [AppID 489830, ActionID 2] : LaunchApp changed task to CheckShaderDepotManifest with ""
"""


def test_parse_downloading():
    ev = logwatch.parse_line("[2026-08-24 08:47:57] Downloading depot 489832 (26 files, 7260 MB) ... ")
    assert ev and ev.kind == "downloading"
    assert (ev.depot_id, ev.files, ev.size_mb, ev.timestamp) == (489832, 26, 7260, "2026-08-24 08:47:57")


def test_parse_complete_extracts_depot_and_manifest():
    ev = logwatch.parse_line(LOG.splitlines()[0])
    assert ev and ev.kind == "complete"
    assert ev.depot_id == 489833
    assert ev.manifest_id == 1914580699073641964
    assert ev.path.endswith("depot_489833")


def test_parse_failed_with_and_without_depot():
    with_depot = logwatch.parse_line(LOG.splitlines()[5])
    assert with_depot and with_depot.kind == "failed" and with_depot.depot_id == 489831
    without = logwatch.parse_line(LOG.splitlines()[4])
    assert without and without.kind == "failed" and without.depot_id is None
    assert without.reason == "Failed to write patch state file (File locked)"


def test_non_event_lines_are_ignored():
    assert logwatch.parse_line(LOG.splitlines()[-1]) is None
    assert logwatch.parse_line("") is None


def test_last_event_for_depot(tmp_path: Path):
    log = tmp_path / "console_log.txt"
    log.write_text(LOG, encoding="utf-8")
    assert logwatch.last_event_for_depot(log, 489833).kind == "complete"
    assert logwatch.last_event_for_depot(log, 489832).kind == "complete"
    # 489831: last relevant event is the unattributed "No connection" failure after its Downloading line
    ev = logwatch.last_event_for_depot(log, 489831)
    assert ev.kind == "failed" and "No connection" in ev.reason
    assert logwatch.last_event_for_depot(log, 1946182) is None


def test_tail_reads_only_new_lines(tmp_path: Path):
    log = tmp_path / "console_log.txt"
    log.write_text(LOG, encoding="utf-8")
    tail = logwatch.LogTail(log)
    tail.seek_to_end()
    assert tail.new_events() == []
    with log.open("a", encoding="utf-8") as fh:
        fh.write("[2026-09-12 19:00:00] Downloading depot 489831 (19 files, 4663 MB) ... \n")
    events = tail.new_events()
    assert len(events) == 1 and events[0].depot_id == 489831
    assert tail.new_events() == []


def test_wait_for_times_out(tmp_path: Path):
    log = tmp_path / "console_log.txt"
    log.write_text("", encoding="utf-8")
    tail = logwatch.LogTail(log)
    assert tail.wait_for(lambda ev: True, timeout=0.2, poll=0.05) is None
