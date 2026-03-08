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

# Theme colors (Cairn dark theme — refined)
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
COLOR_TERMINAL_BG = "#0c0c0c"  # terminal black (NOT transparent key)
COLOR_GRIP = "#383838"         # subtle grip dots on drag handle
COLOR_DROPDOWN_BG = "#0e0e1a"
COLOR_DROPDOWN_FG = "#b0b0c8"

# ── Output routing ────────────────────────────────────────────────────
ROUTE_PASTE_ENTER = "Paste + Enter (terminal)"
ROUTE_PASTE = "Paste Only (Ctrl+V)"
ROUTE_CLIPBOARD = "Clipboard Only"
ROUTE_TYPE_KEYS = "Type Keys (slow, universal)"
ROUTE_SEND_CAIRN = "Send to Cairn"
ROUTE_AUTO_TERMINAL = "Auto Terminal (background)"

ROUTE_OPTIONS = [ROUTE_PASTE_ENTER, ROUTE_PASTE, ROUTE_CLIPBOARD, ROUTE_TYPE_KEYS, ROUTE_SEND_CAIRN, ROUTE_AUTO_TERMINAL]
ROUTE_DEFAULT = ROUTE_PASTE_ENTER

# Window class names for terminal auto-detection (tried in order)
TERMINAL_WINDOW_CLASSES = [
    "CASCADIA_HOSTING_WINDOW_CLASS",  # Windows Terminal
    "ConsoleWindowClass",              # CMD / PowerShell classic
]
# Title substrings to prefer when multiple terminals exist (case-insensitive)
TERMINAL_TITLE_HINTS = ["powershell", "cmd"]
# Title substrings to SKIP — avoids sending to the wrong terminal
TERMINAL_TITLE_EXCLUDE = ["cairn-backend", "cairn-desktop", "whisper-typer"]

# ── Cairn integration ────────────────────────────────────────────────
CAIRN_API_URL = "http://127.0.0.1:5187"
CAIRN_HEALTH_INTERVAL = 30
CAIRN_LAUNCH_BAT = r"D:\Coding\cairn-desktop\cairn-launch.bat"

# ── State machine ─────────────────────────────────────────────────────
STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_TRANSCRIBING = "transcribing"
STATE_TYPING = "typing"
