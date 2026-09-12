"""Console output (rich) and logging setup.

Two sinks:
  * console  - rich-formatted, INFO by default, DEBUG with --verbose
  * log file - always DEBUG, rotating, at %LOCALAPPDATA%/skyrim-downgrader/skyrim-downgrade.log
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.prompt import Confirm

console = Console(highlight=False)

LOG_NAME = "skyrim_downgrader"
LOG_FMT_FILE = "%(asctime)s %(levelname)-8s %(name)s:%(funcName)s:%(lineno)d  %(message)s"


def default_log_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "skyrim-downgrader"
    return base / "skyrim-downgrade.log"


def setup_logging(verbose: bool = False, log_file: Path | None = None) -> Path:
    """Configure root logger. Returns the resolved log file path."""
    log_file = log_file or default_log_path()
    log_file.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        root.removeHandler(h)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FMT_FILE))
    root.addHandler(file_handler)

    console_handler = RichHandler(
        console=console,
        level=logging.DEBUG if verbose else logging.INFO,
        show_path=verbose,
        rich_tracebacks=True,
        markup=True,
    )
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(console_handler)

    # pywinauto / comtypes are chatty at DEBUG; keep them at INFO in the file.
    for noisy in ("comtypes", "pywinauto"):
        logging.getLogger(noisy).setLevel(logging.INFO)

    log = logging.getLogger(LOG_NAME)
    log.debug("=" * 72)
    log.debug("session start  argv=%s", sys.argv)
    log.debug("python=%s  platform=%s  cwd=%s", sys.version.split()[0], platform.platform(), os.getcwd())
    log.debug("log file: %s", log_file)
    return log_file


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOG_NAME}.{name}")


def step(title: str) -> None:
    console.rule(f"[bold cyan]{title}")
    logging.getLogger(LOG_NAME).debug("STEP: %s", title)


def panel(text: str, title: str = "", style: str = "cyan") -> None:
    console.print(Panel(text, title=title, border_style=style))


def confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        logging.getLogger(LOG_NAME).debug("auto-confirmed (--yes): %s", question)
        return True
    answer = Confirm.ask(question, default=True)
    logging.getLogger(LOG_NAME).debug("user answered %s to: %s", answer, question)
    return answer
