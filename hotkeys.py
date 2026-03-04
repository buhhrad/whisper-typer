"""Whisper Typer — global hotkey listener with press/release tracking.

Uses pynput.keyboard.Listener (raw listener) because GlobalHotKeys
doesn't support release events, which we need for push-to-talk.
"""

from __future__ import annotations

import queue
import threading
import time
from pynput import keyboard

from config import HOTKEY_COMBO

_COMBO_TIMEOUT = 5.0  # seconds — auto-reset stuck _combo_active state

# Key name normalization map
_KEY_NAMES = {
    keyboard.Key.ctrl_l: "ctrl_l",
    keyboard.Key.ctrl_r: "ctrl_l",   # treat both Ctrl keys the same
    keyboard.Key.shift: "shift",
    keyboard.Key.shift_l: "shift",
    keyboard.Key.shift_r: "shift",
    keyboard.Key.space: "space",
}


class HotkeyListener:
    """Tracks a key combo and posts press/release events to a queue.

    Events are tuples: ("hotkey_press",) or ("hotkey_release",).
    """

    def __init__(self, event_queue: queue.Queue):
        self._queue = event_queue
        self._pressed: set[str] = set()
        self._combo_active = False
        self._combo_active_time: float = 0.0
        self._listener: keyboard.Listener | None = None

    def start(self) -> None:
        """Start the hotkey listener in a daemon thread."""
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        """Stop the listener."""
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _normalize(self, key) -> str | None:
        """Convert a pynput key to a normalized string name."""
        if key in _KEY_NAMES:
            return _KEY_NAMES[key]
        # Character keys
        if hasattr(key, "char") and key.char:
            return key.char.lower()
        return None

    def _on_press(self, key) -> None:
        name = self._normalize(key)
        if name is None:
            return
        self._pressed.add(name)

        # Auto-reset combo if it's been stuck active too long
        if self._combo_active and (time.monotonic() - self._combo_active_time) >= _COMBO_TIMEOUT:
            self._combo_active = False
            self._queue.put(("hotkey_release",))

        # Check if full combo is held
        if not self._combo_active and HOTKEY_COMBO.issubset(self._pressed):
            self._combo_active = True
            self._combo_active_time = time.monotonic()
            self._queue.put(("hotkey_press",))

    def _on_release(self, key) -> None:
        name = self._normalize(key)
        if name is None:
            return

        # If combo was active and any combo key is released, fire release
        if self._combo_active and name in HOTKEY_COMBO:
            self._combo_active = False
            self._queue.put(("hotkey_release",))

        self._pressed.discard(name)
