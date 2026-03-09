"""Whisper Typer — configuration and constants."""

from __future__ import annotations

# ── Audio ─────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = 512          # samples per sounddevice callback (~32ms at 16kHz)
MAX_RECORD_SEC = 120      # hard cap on recording duration
SILENCE_TIMEOUT = 1.5     # seconds of silence before auto-stop (manual/PTT)

# ── VAD ───────────────────────────────────────────────────────────────
VAD_THRESHOLD = 0.5       # Silero VAD speech probability threshold
VAD_SILENCE_SEC = 1.2     # seconds of silence to end VAD segment
VAD_PRE_PAD_SEC = 0.3     # ring buffer pre-speech padding
VAD_WINDOW_MS = 32        # Silero expects 16/32ms chunks at 16kHz
VAD_WINDOW_SAMPLES = int(SAMPLE_RATE * VAD_WINDOW_MS / 1000)  # 512 samples

# ── Transcription ─────────────────────────────────────────────────────
WHISPER_MODEL = "large-v3-turbo"  # tiny/base/small/medium/large-v3/large-v3-turbo
WHISPER_DEVICE = "cuda"   # cpu or cuda
WHISPER_COMPUTE = "float16"  # int8 (fast CPU), float16 (GPU), float32 (fallback)
WHISPER_BEAM_SIZE = 1     # 1 = greedy (fastest), 5 = beam search (better quality)
WHISPER_LANGUAGE = "en"   # None for auto-detect

# ── Hotkey ────────────────────────────────────────────────────────────
HOTKEY_COMBO = {"ctrl_l", "shift", "space"}  # Ctrl+Shift+Space for PTT

# ── GUI ───────────────────────────────────────────────────────────────
WINDOW_WIDTH = 300
WINDOW_HEIGHT = 50
POLL_INTERVAL_MS = 50     # main loop polling interval

# Theme colors (dark theme)
COLOR_BG = "#080810"
COLOR_SURFACE = "#0c0c1a"
COLOR_BORDER = "#1a1a30"
COLOR_TEXT = "#d0d0e0"
COLOR_TEXT_DIM = "#505068"
COLOR_AMBER = "#e0a820"     # idle accent
COLOR_AMBER_DIM = "#8a6a10" # subtle amber
COLOR_RED = "#e84040"       # recording
COLOR_BLUE = "#5090f0"      # transcribing
COLOR_GREEN = "#40d060"     # done flash
COLOR_TRANSPARENT = "#010101"  # window transparency key color
COLOR_TERMINAL_BG = "#0c0c0c"  # terminal black — also used for button bg in transparent mode
COLOR_GRIP = "#383838"         # subtle grip dots on drag handle
COLOR_DROPDOWN_BG = "#0e0e1a"
COLOR_DROPDOWN_FG = "#b0b0c8"

# ── Output routing ────────────────────────────────────────────────────
ROUTE_AUTO_TERMINAL = "Send to Terminal (paste + enter)"
ROUTE_PASTE = "Auto Paste (focused window)"
ROUTE_CLIPBOARD = "Clipboard"

ROUTE_OPTIONS = [ROUTE_AUTO_TERMINAL, ROUTE_PASTE, ROUTE_CLIPBOARD]
ROUTE_DEFAULT = ROUTE_AUTO_TERMINAL

# Window class names for terminal auto-detection (platform-aware)
def _get_terminal_classes():
    from compat import backend
    return backend.get_terminal_window_classes()

def _get_terminal_hints():
    from compat import backend
    return backend.get_terminal_title_hints()

TERMINAL_WINDOW_CLASSES = _get_terminal_classes()
# Title substrings to prefer when multiple terminals exist (case-insensitive)
TERMINAL_TITLE_HINTS = _get_terminal_hints()
# Title substrings to SKIP — avoids sending to the wrong terminal (platform-neutral)
TERMINAL_TITLE_EXCLUDE = ["whisper-typer"]

# ── State machine ─────────────────────────────────────────────────────
STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_TRANSCRIBING = "transcribing"
STATE_TYPING = "typing"
