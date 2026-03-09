"""Whisper Typer — text output routing.

Cross-platform approach:
  - compat backend for clipboard, terminal discovery, and focus management
  - pynput keyboard Controller for paste and Enter keystrokes
  - Send to Terminal mode: finds a terminal window and sends text there
"""

from __future__ import annotations

import sys
import time

from pynput.keyboard import Controller, Key

from compat import backend as _platform

_kb = Controller()


# ── Clipboard ─────────────────────────────────────────────────────────

def _set_clipboard(text: str) -> bool:
    """Set clipboard text via the platform backend."""
    return _platform.set_clipboard(text)


# ── Keystroke helpers ─────────────────────────────────────────────────

def _press_paste() -> None:
    """Send the platform paste shortcut (Ctrl+V on Win/Linux, Cmd+V on macOS)."""
    mod = _platform.get_paste_modifier()
    _kb.press(mod)
    _kb.press("v")
    _kb.release("v")
    _kb.release(mod)


def _press_enter() -> None:
    """Send Enter via pynput."""
    _kb.press(Key.enter)
    _kb.release(Key.enter)


# ── Terminal auto-find ────────────────────────────────────────────────

def _find_terminal_hwnd():
    """Find a terminal window handle via the platform backend."""
    from config import TERMINAL_TITLE_HINTS, TERMINAL_TITLE_EXCLUDE

    return _platform.find_terminal_window(
        title_hints=TERMINAL_TITLE_HINTS,
        title_exclude=TERMINAL_TITLE_EXCLUDE,
    )


def send_to_terminal(text: str) -> bool:
    """Find a terminal, paste text + Enter, restore focus back.

    Focus management (including any OS-specific tricks) is handled
    by the platform backend.
    """
    target = _find_terminal_hwnd()
    if not target:
        _set_clipboard(text)
        return False

    prev_hwnd = _platform.get_foreground_window()

    if not _set_clipboard(text):
        return False

    _platform.set_foreground_window(target)
    time.sleep(0.2)

    _press_paste()
    time.sleep(0.15)
    _press_enter()

    # Restore previous window
    time.sleep(0.15)
    if prev_hwnd and prev_hwnd != target:
        _platform.set_foreground_window(prev_hwnd)

    return True


# ── Public API ────────────────────────────────────────────────────────

def type_text(text: str, route: str = "Send to Terminal (paste + enter)") -> bool:
    """Output text using the selected routing mode."""
    if not text:
        return False

    if route == "Send to Terminal (paste + enter)":
        return send_to_terminal(text)

    if route == "Clipboard":
        return _set_clipboard(text)

    # Auto Paste: clipboard → paste shortcut into focused window
    if not _set_clipboard(text):
        print("[typer] clipboard failed", file=sys.stderr)
        return False

    time.sleep(0.1)
    _press_paste()
    return True
