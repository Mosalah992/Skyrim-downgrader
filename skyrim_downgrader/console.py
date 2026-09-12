"""Feed commands into the Steam console: auto-type via pywinauto, clipboard fallback."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time

from skyrim_downgrader.steam import open_console
from skyrim_downgrader.ui import console, get_logger

log = get_logger("console")

user32 = ctypes.windll.user32


def _window_title(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _window_pid(hwnd: int) -> int:
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def find_steam_window() -> int | None:
    """HWND of the visible top-level window titled 'Steam' (new CEF client)."""
    matches: list[tuple[int, str, int]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def enum_cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            title = _window_title(hwnd)
            if title == "Steam":
                matches.append((hwnd, _window_class(hwnd), _window_pid(hwnd)))
        return True

    user32.EnumWindows(enum_cb, 0)
    log.debug("candidate Steam windows (hwnd, class, pid): %s", matches)
    if not matches:
        return None
    # Prefer the SDL/CEF main window if present.
    for hwnd, cls, _pid in matches:
        if cls.lower().startswith("sdl"):
            return hwnd
    return matches[0][0]


def type_into_steam_console(command: str, settle: float = 2.5) -> bool:
    """Open the console page, focus Steam, type command + Enter. Returns False if it could not."""
    try:
        from pywinauto import Application, keyboard  # imported lazily: slow + windows-only
    except ImportError as exc:  # pragma: no cover
        log.error("pywinauto not installed: %s", exc)
        return False

    open_console()
    time.sleep(settle)

    hwnd = find_steam_window()
    if hwnd is None:
        log.warning("no visible window titled 'Steam' found")
        return False
    log.debug("using Steam hwnd=%s class=%s pid=%s", hwnd, _window_class(hwnd), _window_pid(hwnd))

    try:
        app = Application(backend="win32").connect(handle=hwnd)
        win = app.window(handle=hwnd)
        win.set_focus()
        time.sleep(0.5)
        if user32.GetForegroundWindow() != hwnd:
            log.warning("Steam window did not come to the foreground (fg hwnd=%s)", user32.GetForegroundWindow())
            return False
        # Steam's current console is a CEF page.  Giving its top-level window
        # focus is not enough: keystrokes are otherwise dropped until the
        # command field near the bottom of the page has been clicked.
        rect = win.rectangle()
        input_x = (rect.right - rect.left) // 2
        input_y = max(60, min(100, (rect.bottom - rect.top) // 10))
        log.debug("focusing Steam console input at relative (%d, %d) in %s", input_x, input_y, rect)
        win.click_input(coords=(input_x, (rect.bottom - rect.top) - input_y))
        time.sleep(0.3)
        log.info("Typing into Steam console: [bold]%s[/]", command)
        keyboard.send_keys(command, with_spaces=True, pause=0.01)
        time.sleep(0.2)
        keyboard.send_keys("{ENTER}")
        return True
    except Exception:  # noqa: BLE001 - anything from pywinauto means "fall back to manual"
        log.exception("auto-typing into Steam failed")
        return False


def copy_to_clipboard(text: str) -> bool:
    try:
        import win32clipboard  # part of pywin32, pulled in by pywinauto

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
        log.debug("clipboard <- %r", text)
        return True
    except Exception:  # noqa: BLE001
        log.exception("could not write to clipboard")
        return False


def prompt_manual(command: str) -> None:
    copied = copy_to_clipboard(command)
    hint = "It is on your clipboard - press Ctrl+V in the console." if copied else "Type it exactly as shown."
    console.print(
        f"\n[bold yellow]Manual step:[/] open the Steam console ([italic]Win+R -> steam://open/console[/]) "
        f"and run:\n\n    [bold]{command}[/]\n\n{hint}\nThis tool keeps watching console_log.txt and continues automatically."
    )
    log.info("waiting for user to paste command manually: %s", command)
    open_console()
