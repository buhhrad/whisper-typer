"""Whisper Typer — global hotkey listener with press/release tracking.

Uses pynput.keyboard.Listener (raw listener) because GlobalHotKeys
doesn't support release events, which we need for push-to-talk.

Supports two configurable combos:
  - PTT (push-to-talk): hold-to-record, fires press/release events
  - VAD toggle: tap to toggle, fires a single toggle event
"""

from __future__ import annotations

import queue
import time
from pynput import keyboard

_COMBO_TIMEOUT = 5.0  # seconds — auto-reset stuck _combo_active state

# Key name normalization map — pynput special keys → internal names
_KEY_NAMES = {
    keyboard.Key.ctrl_l: "ctrl",
    keyboard.Key.ctrl_r: "ctrl",
    keyboard.Key.shift: "shift",
    keyboard.Key.shift_l: "shift",
    keyboard.Key.shift_r: "shift",
    keyboard.Key.alt_l: "alt",
    keyboard.Key.alt_r: "alt",
    keyboard.Key.space: "space",
    keyboard.Key.tab: "tab",
    keyboard.Key.enter: "enter",
    keyboard.Key.esc: "esc",
    keyboard.Key.f1: "f1",
    keyboard.Key.f2: "f2",
    keyboard.Key.f3: "f3",
    keyboard.Key.f4: "f4",
    keyboard.Key.f5: "f5",
    keyboard.Key.f6: "f6",
    keyboard.Key.f7: "f7",
    keyboard.Key.f8: "f8",
    keyboard.Key.f9: "f9",
    keyboard.Key.f10: "f10",
    keyboard.Key.f11: "f11",
    keyboard.Key.f12: "f12",
}

# Legacy name mapping (old config format → new)
_LEGACY_MAP = {"ctrl_l": "ctrl"}


def _normalize_combo(combo) -> set[str] | None:
    """Convert a combo list/set to normalized set, or None if empty/invalid."""
    if not combo:
        return None
    return {_LEGACY_MAP.get(k, k) for k in combo}


class HotkeyListener:
    """Tracks key combos and posts events to a queue.

    PTT events: ("hotkey_press",) / ("hotkey_release",)
    VAD events: ("vad_toggle",)
    """

    def __init__(
        self,
        event_queue: queue.Queue,
        ptt_combo: list[str] | set[str] | None = None,
        vad_combo: list[str] | set[str] | None = None,
    ):
        self._queue = event_queue
        self._pressed: set[str] = set()
        self._listener: keyboard.Listener | None = None

        # PTT combo state
        self._ptt_combo = _normalize_combo(ptt_combo)
        self._ptt_active = False
        self._ptt_active_time: float = 0.0

        # VAD toggle combo state
        self._vad_combo = _normalize_combo(vad_combo)
        self._vad_fired = False  # prevent repeat-fire while held

    def set_combos(
        self,
        ptt_combo: list[str] | set[str] | None = None,
        vad_combo: list[str] | set[str] | None = None,
    ) -> None:
        """Update combos at runtime (no restart needed)."""
        self._ptt_combo = _normalize_combo(ptt_combo)
        self._vad_combo = _normalize_combo(vad_combo)
        # Reset state
        self._ptt_active = False
        self._vad_fired = False

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
        if hasattr(key, "char") and key.char:
            return key.char.lower()
        return None

    def _on_press(self, key) -> None:
        name = self._normalize(key)
        if name is None:
            return
        self._pressed.add(name)

        # ── PTT combo (hold-to-talk) ──
        if self._ptt_combo:
            # Auto-reset if stuck
            if self._ptt_active and (time.monotonic() - self._ptt_active_time) >= _COMBO_TIMEOUT:
                self._ptt_active = False
                self._queue.put(("hotkey_release",))

            if not self._ptt_active and self._ptt_combo.issubset(self._pressed):
                self._ptt_active = True
                self._ptt_active_time = time.monotonic()
                self._queue.put(("hotkey_press",))

        # ── VAD combo (toggle) ──
        if self._vad_combo and not self._vad_fired:
            if self._vad_combo.issubset(self._pressed):
                self._vad_fired = True
                self._queue.put(("vad_toggle",))

    def _on_release(self, key) -> None:
        name = self._normalize(key)
        if name is None:
            return

        # PTT release
        if self._ptt_combo and self._ptt_active and name in self._ptt_combo:
            self._ptt_active = False
            self._queue.put(("hotkey_release",))

        # VAD — allow re-fire after any combo key is released
        if self._vad_combo and self._vad_fired and name in self._vad_combo:
            self._vad_fired = False

        self._pressed.discard(name)
