"""Whisper Typer — settings persistence.

Saves and loads user preferences (mic device, output route, VAD state,
window position) to a JSON file alongside the script.
"""

from __future__ import annotations

import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).parent / "whisper_typer_settings.json"

_DEFAULTS = {
    "mic_device": None,       # device name string, or None for system default
    "output_route": None,     # route string, or None for default
    "vad_enabled": False,
    "window_x": None,
    "window_y": None,
    "ptt_hotkey": ["ctrl", "shift", "space"],  # push-to-talk key combo
    "vad_hotkey": None,       # VAD toggle key combo, or None for no binding
    "mute_hotkey": ["ctrl", "shift", "m"],    # mute toggle key combo
    "terminal_hotkey": ["ctrl", "tab"],  # cycle target terminal
    "whisper_model": None,    # model size, or None for config.py default
    "whisper_device": None,   # "cuda" or "cpu", or None for config.py default
    "whisper_language": None, # language code, or None for config.py default
}


def load() -> dict:
    """Load settings from disk, returning defaults for missing keys."""
    settings = dict(_DEFAULTS)
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            settings.update({k: v for k, v in saved.items() if k in _DEFAULTS})
    except Exception:
        pass
    return settings


def save(settings: dict) -> None:
    """Save settings to disk."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass
