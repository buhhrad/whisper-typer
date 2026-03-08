"""Whisper Typer — text output routing.

Simple approach:
  - clip.exe for clipboard (battle-tested, handles unicode)
  - pynput keyboard Controller for Ctrl+V and Enter
  - No ctypes SendInput complexity
  - Auto Terminal mode: finds a terminal window and sends text there
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import subprocess
import sys
import time

from pynput.keyboard import Controller, Key

_kb = Controller()


# ── Clipboard via clip.exe ────────────────────────────────────────────

def _set_clipboard(text: str) -> bool:
    """Set clipboard text via clip.exe (UTF-16LE for full unicode)."""
    try:
        proc = subprocess.Popen(
            ["clip"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        # BOM + UTF-16LE — clip.exe needs BOM to interpret encoding correctly
        proc.communicate(b"\xff\xfe" + text.encode("utf-16-le"))
        return proc.returncode == 0
    except Exception:
        return False


# ── Keystroke helpers ─────────────────────────────────────────────────

def _press_ctrl_v() -> None:
    """Send Ctrl+V via pynput."""
    _kb.press(Key.ctrl)
    _kb.press("v")
    _kb.release("v")
    _kb.release(Key.ctrl)


def _press_enter() -> None:
    """Send Enter via pynput."""
    _kb.press(Key.enter)
    _kb.release(Key.enter)


def _type_chars(text: str) -> None:
    """Type text character by character via pynput."""
    for char in text:
        _kb.type(char)
        time.sleep(0.008)


# ── Terminal auto-find ────────────────────────────────────────────────

# Win32 callback type for EnumWindows
_WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
_user32 = ctypes.windll.user32


def _find_terminal_hwnd() -> int | None:
    """Find a terminal window handle. Skips excluded titles, prefers hints."""
    from config import TERMINAL_WINDOW_CLASSES, TERMINAL_TITLE_HINTS, TERMINAL_TITLE_EXCLUDE

    candidates: list[tuple[int, str]] = []  # (hwnd, title)

    def _enum_cb(hwnd: int, _lparam: int) -> bool:
        if not _user32.IsWindowVisible(hwnd):
            return True
        # Get window class name
        cls_buf = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, cls_buf, 256)
        cls_name = cls_buf.value
        if cls_name not in TERMINAL_WINDOW_CLASSES:
            return True
        # Get window title
        title_len = _user32.GetWindowTextLengthW(hwnd) + 1
        title_buf = ctypes.create_unicode_buffer(title_len)
        _user32.GetWindowTextW(hwnd, title_buf, title_len)
        title = title_buf.value.lower()
        # Skip excluded windows (e.g. this Claude Code session)
        if any(excl in title for excl in TERMINAL_TITLE_EXCLUDE):
            return True
        candidates.append((hwnd, title))
        return True

    _user32.EnumWindows(_WNDENUMPROC(_enum_cb), 0)

    if not candidates:
        return None

    # Prefer windows whose title matches a hint
    for hint in TERMINAL_TITLE_HINTS:
        for hwnd, title in candidates:
            if hint in title:
                return hwnd

    # Fall back to first terminal found
    return candidates[0][0]


def send_to_terminal(text: str) -> bool:
    """Find a terminal, paste text + Enter, restore focus back.

    Uses the ALT-key trick to bypass Windows' foreground lock so
    SetForegroundWindow actually works from a background process.
    Quick flash to terminal and back — works while gaming.
    """
    target = _find_terminal_hwnd()
    if not target:
        _set_clipboard(text)
        return False

    prev_hwnd = _user32.GetForegroundWindow()

    # Set clipboard first while we still have time
    if not _set_clipboard(text):
        return False

    # ALT-key trick: Windows blocks SetForegroundWindow from background
    # processes unless the caller recently received input. A synthetic
    # ALT press/release satisfies this check.
    _user32.keybd_event(0x12, 0, 0, 0)    # ALT down
    _user32.keybd_event(0x12, 0, 2, 0)    # ALT up (KEYEVENTF_KEYUP=2)
    time.sleep(0.05)

    _user32.SetForegroundWindow(target)
    time.sleep(0.2)

    # Paste + Enter
    _press_ctrl_v()
    time.sleep(0.15)
    _press_enter()

    # Restore previous window
    time.sleep(0.15)
    if prev_hwnd and prev_hwnd != target:
        _user32.keybd_event(0x12, 0, 0, 0)
        _user32.keybd_event(0x12, 0, 2, 0)
        time.sleep(0.05)
        _user32.SetForegroundWindow(prev_hwnd)

    return True


# ── Cairn integration ─────────────────────────────────────────────────

def send_to_cairn(text: str) -> bool:
    """Send transcribed text to Cairn backend via /voice/input."""
    import json
    import urllib.request
    from config import CAIRN_API_URL
    try:
        data = json.dumps({"text": text, "source": "whisper_typer"}).encode()
        req = urllib.request.Request(
            f"{CAIRN_API_URL}/voice/input",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        # Fallback: copy to clipboard
        _set_clipboard(text)
        return False


# ── Public API ────────────────────────────────────────────────────────

def type_text(text: str, route: str = "Paste + Enter (terminal)") -> bool:
    """Output text using the selected routing mode."""
    if not text:
        return False

    if route == "Auto Terminal (background)":
        return send_to_terminal(text)

    if route == "Send to Cairn":
        ok = send_to_cairn(text)
        if not ok:
            # Already copied to clipboard by fallback
            pass
        return ok

    if route == "Clipboard Only":
        return _set_clipboard(text)

    if route == "Type Keys (slow, universal)":
        _type_chars(text)
        return True

    # Paste modes: clipboard → Ctrl+V → optional Enter
    if not _set_clipboard(text):
        print("[typer] clipboard failed", file=sys.stderr)
        return False

    time.sleep(0.1)
    _press_ctrl_v()

    if "Enter" in route:
        time.sleep(0.15)
        _press_enter()

    return True
