"""Whisper Typer — text output routing.

Simple approach:
  - clip.exe for clipboard (battle-tested, handles unicode)
  - pynput keyboard Controller for Ctrl+V and Enter
  - No ctypes SendInput complexity
"""

from __future__ import annotations

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


# ── Public API ────────────────────────────────────────────────────────

def type_text(text: str, route: str = "Paste + Enter (terminal)") -> bool:
    """Output text using the selected routing mode."""
    if not text:
        return False

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
