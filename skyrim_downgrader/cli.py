"""Command-line entry point: skyrim-downgrade <run|download|install|lock-updates|unlock-updates|status|fix-crash>."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TimeElapsedColumn, TransferSpeedColumn
from rich.table import Table

from skyrim_downgrader import __version__, config, console as steam_console, installer, logwatch, manifest, steam
from skyrim_downgrader.config import Depot
from skyrim_downgrader.ui import confirm, console, get_logger, panel, setup_logging, step

log = get_logger("cli")

DOWNLOAD_START_TIMEOUT = 15.0   # seconds to see "Downloading depot N" after typing the command
MAX_AUTO_RETRIES = 3
RETRY_BACKOFF = 10.0

LOG_PATH: Path | None = None


class Abort(RuntimeError):
    """Fatal, user-facing error; message printed without traceback."""


@dataclass
class Context:
    steam_dir: Path
    game_dir: Path
    appmanifest: Path | None
    console_log: Path
    depots: list[Depot]
    manual: bool
    assume_yes: bool
    force: bool
    dry_run: bool


# --------------------------------------------------------------------------- setup

def build_context(args: argparse.Namespace) -> Context:
    steam_dir = steam.find_steam_dir(args.steam_dir)
    game_dir = steam.find_game_dir(steam_dir, args.game_dir)
    acf = steam.find_appmanifest(steam_dir)
    depots = list(config.DEPOTS)

    ck_installed = (game_dir / "CreationKit.exe").is_file()
    if args.ck:
        depots += config.CK_DEPOTS
        log.info("Creation Kit depots included (--ck)")
    elif args.no_ck:
        log.info("Creation Kit depots skipped (--no-ck)")
    elif ck_installed:
        depots += config.CK_DEPOTS
        log.info("Creation Kit detected at %s - including its depots", game_dir)
    else:
        log.info("Creation Kit not installed - skipping its depots (use --ck to force)")

    if args.only:
        wanted = {int(x) for x in args.only.split(",") if x.strip()}
        depots = [d for d in depots if d.depot_id in wanted]
        log.info("--only: restricting to depots %s", sorted(wanted))
        if not depots:
            raise Abort(f"--only matched no known depot ids: {sorted(wanted)}")

    ctx = Context(
        steam_dir=steam_dir,
        game_dir=game_dir,
        appmanifest=acf,
        console_log=steam.console_log_path(steam_dir),
        depots=depots,
        manual=args.manual,
        assume_yes=args.yes,
        force=getattr(args, "force", False),
        dry_run=getattr(args, "dry_run", False),
    )
    log.debug("context: %s", ctx)
    return ctx


# --------------------------------------------------------------------------- download

def depot_is_done(ctx: Context, depot: Depot) -> bool:
    """True when the last log event for this depot is 'complete' with our manifest and the folder exists."""
    ev = logwatch.last_event_for_depot(ctx.console_log, depot.depot_id)
    folder = depot.content_dir(ctx.steam_dir)
    done = (
        ev is not None
        and ev.kind == "complete"
        and ev.manifest_id == depot.manifest_id
        and folder.is_dir()
        and any(folder.iterdir())
    )
    log.debug("depot %s done=%s (event=%s, folder_exists=%s)", depot.depot_id, done, ev and ev.kind, folder.is_dir())
    return done


def _is_start(depot: Depot):
    return lambda ev: ev.kind == "downloading" and ev.depot_id == depot.depot_id


def issue_command(ctx: Context, tail: logwatch.LogTail, depot: Depot) -> logwatch.Event:
    """Send the download_depot command and block until Steam reports 'Downloading depot'."""
    tail.seek_to_end()
    started = None
    if not ctx.manual:
        if steam_console.type_into_steam_console(depot.command):
            started = tail.wait_for(_is_start(depot), timeout=DOWNLOAD_START_TIMEOUT)
            if started is None:
                log.warning("Steam did not acknowledge the typed command within %.0fs", DOWNLOAD_START_TIMEOUT)
    if started is None:
        steam_console.prompt_manual(depot.command)
        with console.status("[yellow]Waiting for the command to be entered in the Steam console..."):
            started = tail.wait_for(_is_start(depot), timeout=None)
    assert started is not None
    log.info("Steam started depot %s: %s files, %s MB", started.depot_id, started.files, started.size_mb)
    return started


def wait_for_result(tail: logwatch.LogTail, depot: Depot) -> logwatch.Event:
    def is_result(ev: logwatch.Event) -> bool:
        if ev.kind == "complete":
            return ev.depot_id == depot.depot_id or ev.manifest_id == depot.manifest_id
        if ev.kind == "failed":
            return ev.depot_id in (None, depot.depot_id)
        return False

    label = f"[cyan]Downloading {depot.label} (depot {depot.depot_id})..."
    with console.status(f"{label} 0:00") as status:
        def tick(elapsed: float) -> None:
            status.update(f"{label} {int(elapsed) // 60}:{int(elapsed) % 60:02d}")
        result = tail.wait_for(is_result, timeout=None, on_tick=tick)
    assert result is not None
    return result


def download_depot(ctx: Context, depot: Depot) -> None:
    step(f"Depot {depot.depot_id} - {depot.label}")
    if not ctx.force and depot_is_done(ctx, depot):
        log.info("[green]already downloaded[/] (manifest %s) - skipping; use --force to redo", depot.manifest_id)
        return

    tail = logwatch.LogTail(ctx.console_log)
    attempt = 0
    while True:
        attempt += 1
        log.info("attempt %d: %s", attempt, depot.command)
        issue_command(ctx, tail, depot)
        result = wait_for_result(tail, depot)
        if result.kind == "complete":
            log.info("[green]Depot download complete[/] -> %s", result.path)
            return
        log.error("Depot download failed: %s", result.reason)
        if attempt <= MAX_AUTO_RETRIES:
            log.info("retrying in %.0fs (%d/%d)...", RETRY_BACKOFF, attempt, MAX_AUTO_RETRIES)
            time.sleep(RETRY_BACKOFF)
            continue
        if not confirm("Retry this depot?", ctx.assume_yes):
            raise Abort(f"Depot {depot.depot_id} failed: {result.reason}")


def cmd_download(ctx: Context) -> None:
    step("Preflight")
    if not ctx.console_log.parent.is_dir():
        raise Abort(f"Steam logs folder missing: {ctx.console_log.parent}")
    steam.ensure_steam_running(ctx.steam_dir)
    needed = config.SE_DEPOTS_BYTES + (config.CK_DEPOTS_BYTES if len(ctx.depots) > 3 else 0)
    free = steam.free_bytes(ctx.steam_dir)
    log.info("free space on Steam drive: %.1f GB (need roughly %.1f GB)", free / 1024**3, needed / 1024**3)
    if free < needed and not confirm("Low disk space - continue anyway?", ctx.assume_yes):
        raise Abort("Not enough free space")

    table = Table(title="Depots to download")
    table.add_column("Depot")
    table.add_column("Label")
    table.add_column("Command")
    table.add_column("State")
    for d in ctx.depots:
        table.add_row(str(d.depot_id), d.label, d.command, "done" if depot_is_done(ctx, d) else "pending")
    console.print(table)
    if not confirm("Start downloading through the Steam console?", ctx.assume_yes):
        raise Abort("Cancelled")

    for depot in ctx.depots:
        download_depot(ctx, depot)
    log.info("[bold green]All depots downloaded.[/]")


# --------------------------------------------------------------------------- install

def cmd_install(ctx: Context) -> None:
    step("Install (copy depot contents into the game folder)")
    if procs := steam.game_processes_running():
        raise Abort(f"Close the game first (running: {', '.join(procs)})")
    if not ctx.game_dir.is_dir():
        raise Abort(f"Game folder not found: {ctx.game_dir}")

    items: list[installer.CopyItem] = []
    for depot in ctx.depots:
        folder = depot.content_dir(ctx.steam_dir)
        if not folder.is_dir():
            raise Abort(f"Depot folder missing - run 'download' first: {folder}")
        items += installer.plan_copy(folder, ctx.game_dir)
    total = sum(i.size for i in items)
    log.info("%d files / %.2f GB -> %s", len(items), total / 1024**3, ctx.game_dir)
    if not ctx.dry_run and not confirm("Overwrite the game files now?", ctx.assume_yes):
        raise Abort("Cancelled")

    with Progress(
        TextColumn("[cyan]{task.description}"), BarColumn(), DownloadColumn(),
        TransferSpeedColumn(), TimeElapsedColumn(), console=console,
    ) as progress:
        task = progress.add_task("copying", total=total)
        for item in installer.copy_items(items, dry_run=ctx.dry_run):
            progress.update(task, advance=item.size, description=item.dst.name[:40])
    log.info("[bold green]%s copied.[/]", "Dry run - nothing" if ctx.dry_run else "All files")
    report_version(ctx)


def report_version(ctx: Context) -> bool:
    ver = installer.file_version(ctx.game_dir / config.GAME_EXE)
    ok = ver == config.TARGET_EXE_VERSION
    colour = "green" if ok else "red"
    log.info("%s version: [%s]%s[/] (target %s)", config.GAME_EXE, colour, installer.version_str(ver), config.TARGET_LABEL)
    return ok


# --------------------------------------------------------------------------- updates lock

def cmd_lock_updates(ctx: Context, lock: bool = True) -> None:
    step("Lock auto-updates" if lock else "Unlock auto-updates")
    acf = ctx.appmanifest
    if not acf:
        raise Abort("appmanifest_489830.acf not found - is the game installed through Steam?")
    value = manifest.ONLY_UPDATE_ON_LAUNCH if lock else manifest.ALWAYS_UPDATE
    manifest.set_auto_update_behavior(acf, value)
    manifest.set_read_only(acf, lock)
    if lock:
        panel(
            "Steam keeps app state in memory and may rewrite this file, so also set it in the client:\n"
            "Library -> Skyrim Special Edition -> Properties -> Updates -> "
            "[bold]Only update this game when I launch it[/].\n"
            "Launch the game through SKSE / a mod manager rather than Steam's Play button to avoid update checks.",
            title="Belt and braces", style="yellow",
        )


# --------------------------------------------------------------------------- status / misc

def cmd_status(ctx: Context) -> None:
    step("Status")
    table = Table(show_header=False)
    table.add_row("Steam dir", str(ctx.steam_dir))
    table.add_row("Game dir", str(ctx.game_dir))
    table.add_row("Steam running", str(steam.is_steam_running()))
    table.add_row("Game running", ", ".join(steam.game_processes_running()) or "no")
    if ctx.appmanifest:
        table.add_row("appmanifest", str(ctx.appmanifest))
        table.add_row("buildid", manifest.read_buildid(ctx.appmanifest) or "?")
        aub = manifest.read_auto_update_behavior(ctx.appmanifest)
        meaning = {0: "always", 1: "only on launch", 2: "high priority"}.get(aub, "?")
        table.add_row("AutoUpdateBehavior", f"{aub} ({meaning})")
        table.add_row("appmanifest read-only", str(manifest.is_read_only(ctx.appmanifest)))
    ver = installer.file_version(ctx.game_dir / config.GAME_EXE)
    table.add_row(config.GAME_EXE, f"{installer.version_str(ver)}  (target {config.TARGET_LABEL})")
    table.add_row("console log", str(ctx.console_log))
    table.add_row("tool log", str(LOG_PATH))
    console.print(table)

    dt = Table(title="Depots")
    dt.add_column("Depot")
    dt.add_column("Label")
    dt.add_column("Folder")
    dt.add_column("Last log event")
    for d in ctx.depots:
        ev = logwatch.last_event_for_depot(ctx.console_log, d.depot_id)
        folder = d.content_dir(ctx.steam_dir)
        if ev is None:
            state = "-"
        else:
            state = f"{ev.kind} @ {ev.timestamp}"
            if ev.kind == "complete":
                state += " (this manifest)" if ev.manifest_id == d.manifest_id else f" (other manifest {ev.manifest_id})"
        dt.add_row(str(d.depot_id), d.label, "present" if folder.is_dir() else "missing", state)
    console.print(dt)


def cmd_fix_crash(ctx: Context) -> None:
    step("Fix crash-after-launch (ContentCatalog.txt)")
    path = steam.content_catalog_path()
    if not path.exists():
        log.info("%s does not exist - nothing to do", path)
        return
    target = path.with_suffix(".txt.bak")
    if target.exists():
        target.unlink()
        log.debug("removed stale %s", target)
    path.rename(target)
    log.info("renamed %s -> %s", path, target.name)


def cmd_run(ctx: Context) -> None:
    panel(
        f"Rolling Skyrim Special Edition back to [bold]{config.TARGET_LABEL}[/]\n"
        f"Game: {ctx.game_dir}\nSteam: {ctx.steam_dir}\nDepots: {', '.join(str(d.depot_id) for d in ctx.depots)}",
        title="skyrim-downgrade",
    )
    cmd_download(ctx)
    cmd_install(ctx)
    cmd_lock_updates(ctx, lock=True)
    step("Done")
    if report_version(ctx):
        log.info("[bold green]Downgrade complete.[/] If the game crashes on launch, run: skyrim-downgrade fix-crash")
    else:
        log.warning("The exe version does not match the target - check the log for copy errors.")


# --------------------------------------------------------------------------- argparse

def add_common_options(p: argparse.ArgumentParser, *, for_subcommand: bool) -> None:
    """Global flags. Added to the main parser and to every subparser so they work in either position.

    On subparsers the defaults are SUPPRESS so a subparser never overwrites a value given before it.
    """
    kw = {"default": argparse.SUPPRESS} if for_subcommand else {}
    p.add_argument("--steam-dir", help="Steam install folder (default: from registry)", **kw)
    p.add_argument("--game-dir", help="Skyrim SE folder (default: from appmanifest)", **kw)
    ck = p.add_mutually_exclusive_group()
    ck.add_argument("--ck", action="store_true", help="also handle the Creation Kit depots", **kw)
    ck.add_argument("--no-ck", action="store_true", help="never handle the Creation Kit depots", **kw)
    p.add_argument("--only", metavar="IDS", help="comma-separated depot ids to restrict to, e.g. 489833", **kw)
    p.add_argument("--manual", action="store_true", help="never auto-type; always paste commands yourself", **kw)
    p.add_argument("-y", "--yes", action="store_true", help="answer yes to every confirmation", **kw)
    p.add_argument("-v", "--verbose", action="store_true", help="debug output on the console", **kw)
    p.add_argument("--log-file", help="where to write the debug log", **kw)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="skyrim-downgrade",
        description=f"Roll Skyrim Special Edition back to {config.TARGET_LABEL} using the Steam console.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    add_common_options(p, for_subcommand=False)

    sub = p.add_subparsers(dest="command")

    def add(name: str, help_: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_)
        add_common_options(sp, for_subcommand=True)
        return sp

    add("run", "download + install + lock updates (default)").add_argument(
        "--force", action="store_true", help="re-download depots even if already complete")
    add("download", "only run the Steam console downloads").add_argument(
        "--force", action="store_true", help="re-download depots even if already complete")
    add("install", "copy downloaded depot contents into the game folder").add_argument(
        "--dry-run", action="store_true", help="list what would be copied")
    add("lock-updates", "set 'only update when I launch' + read-only appmanifest")
    add("unlock-updates", "revert lock-updates")
    add("status", "show paths, depot states and exe version")
    add("fix-crash", "rename %%LOCALAPPDATA%%/Skyrim Special Edition/ContentCatalog.txt")
    return p


COMMANDS = {
    "run": cmd_run,
    "download": cmd_download,
    "install": cmd_install,
    "lock-updates": lambda c: cmd_lock_updates(c, True),
    "unlock-updates": lambda c: cmd_lock_updates(c, False),
    "status": cmd_status,
    "fix-crash": cmd_fix_crash,
}


def main(argv: list[str] | None = None) -> int:
    global LOG_PATH
    args = build_parser().parse_args(argv)
    LOG_PATH = setup_logging(args.verbose, Path(args.log_file) if args.log_file else None)
    log.debug("args: %s", vars(args))
    command = args.command or "run"
    try:
        ctx = build_context(args)
        COMMANDS[command](ctx)
        return 0
    except Abort as exc:
        log.error("[bold red]%s[/]", exc)
        return 2
    except KeyboardInterrupt:
        log.warning("Interrupted. Steam keeps downloading in the background; re-run to resume.")
        return 130
    except Exception:  # noqa: BLE001
        log.exception("Unexpected error")
        console.print(f"[red]See the log for details: {LOG_PATH}[/]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
