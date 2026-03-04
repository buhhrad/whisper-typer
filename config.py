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
WHISPER_MODEL = "medium"  # tiny/base/small/medium/large-v3
WHISPER_DEVICE = "cpu"    # cpu or cuda
WHISPER_COMPUTE = "int8"  # int8 (fast CPU), float16 (GPU), float32 (fallback)
WHISPER_BEAM_SIZE = 1     # 1 = greedy (fastest), 5 = beam search (better quality)
WHISPER_LANGUAGE = "en"   # None for auto-detect

# ── Hotkey ────────────────────────────────────────────────────────────
HOTKEY_COMBO = {"ctrl_l", "shift", "space"}  # Ctrl+Shift+Space for PTT

# ── GUI ───────────────────────────────────────────────────────────────
WINDOW_WIDTH = 380
WINDOW_HEIGHT = 120
POLL_INTERVAL_MS = 50     # main loop polling interval

# Theme colors (Cairn dark theme)
COLOR_BG = "#12121f"
COLOR_SURFACE = "#1a1a2e"
COLOR_TEXT = "#e0e0e0"
COLOR_TEXT_DIM = "#888888"
COLOR_AMBER = "#d4a030"     # idle accent
COLOR_RED = "#e04040"       # recording
COLOR_BLUE = "#4080e0"      # transcribing
COLOR_GREEN = "#40c040"     # done flash
COLOR_DROPDOWN_BG = "#22223a"
COLOR_DROPDOWN_FG = "#e0e0e0"

# ── Output routing ────────────────────────────────────────────────────
ROUTE_PASTE_ENTER = "Paste + Enter (terminal)"
ROUTE_PASTE = "Paste Only (Ctrl+V)"
ROUTE_CLIPBOARD = "Clipboard Only"
ROUTE_TYPE_KEYS = "Type Keys (slow, universal)"

ROUTE_OPTIONS = [ROUTE_PASTE_ENTER, ROUTE_PASTE, ROUTE_CLIPBOARD, ROUTE_TYPE_KEYS]
ROUTE_DEFAULT = ROUTE_PASTE_ENTER

# ── State machine ─────────────────────────────────────────────────────
STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_TRANSCRIBING = "transcribing"
STATE_TYPING = "typing"
