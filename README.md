# Whisper Typer

A lightweight, always-on-top voice typing widget. Transcribes speech in real-time using [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and routes text to your active terminal, clipboard, or any window.

![Windows](https://img.shields.io/badge/platform-Windows-blue)
![macOS](https://img.shields.io/badge/platform-macOS-lightgrey)
![Linux](https://img.shields.io/badge/platform-Linux-orange)
![Python](https://img.shields.io/badge/python-3.10%2B-green)

## Features

- **Push-to-Talk** — Hold `Ctrl+Shift+Space` to record, release to transcribe
- **Always-on VAD** — Silero VAD detects speech automatically, hands-free
- **Snap to Terminal** — Attaches to your terminal as a transparent overlay, follows the window
- **Multiple output routes** — Auto Terminal (background), Paste only, Clipboard only
- **Queued transcription** — Captures overlapping speech segments so pauses don't cut you off
- **System tray** — Minimizes to tray, stays out of the way
- **Configurable** — Model size, device, hotkeys, mic selection, output routing

## Requirements

- **Windows 10/11**, **macOS**, or **Linux** (X11 recommended; Wayland has limited support)
- **Python 3.10+**
- **CUDA GPU** (recommended) or CPU (slower transcription)

### Platform notes

| Feature | Windows | macOS | Linux (X11) | Linux (Wayland) |
|---------|---------|-------|-------------|-----------------|
| Clipboard | Full | Full | Full | Full |
| Terminal auto-find | Full | AppleScript | xdotool | Not supported |
| Window snapping | Full | Partial | Partial | Not supported |
| Transparency | Per-pixel | Window alpha | Compositor | Compositor |
| Rounded corners | Full | Native | Compositor | Compositor |

On macOS, paste uses `Cmd+V` automatically. On Linux, install `xdotool` and `xclip` for full functionality.

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/buhhrad/whisper-typer.git
cd whisper-typer
pip install .
```

### 2. Run

```bash
whisper-typer
```

Or run directly with `python whisper_typer.py`.

### 3. Use

- Click the **mic icon** to toggle manual recording
- Click the **bars icon** to enable always-on VAD (voice activity detection)
- Click the **gear icon** for settings (mic, output route, snap to terminal)
- Press `Ctrl+Shift+Space` for push-to-talk (hold to record, release to transcribe)

## Configuration

### Command-line options

```
python whisper_typer.py --model small       # Use smaller/faster model
python whisper_typer.py --device cpu        # Force CPU (no CUDA needed)
python whisper_typer.py --list-devices      # List available mic devices
```

### Whisper models

Change the model in the settings popup (gear icon → WHISPER section), or via CLI:

| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| `tiny` | 75MB | Fastest | Basic |
| `base` | 150MB | Fast | Good |
| `small` | 500MB | Medium | Better |
| `medium` | 1.5GB | Slow | Great |
| `large-v3` | 3GB | Slowest | Best |
| `large-v3-turbo` | 1.6GB | Fast | Great (default) |

### Output routes

| Route | Behavior |
|-------|----------|
| Auto Terminal | Finds a terminal in the background, pastes + Enter, restores focus (default) |
| Paste Only | Clipboard → Ctrl+V into the focused window |
| Clipboard Only | Copies to clipboard, no paste |

### Hotkeys

Configure via the settings popup (gear icon → KEYBINDS section):

- **Push-to-talk**: `Ctrl+Shift+Space` (default) — hold to record, release to transcribe
- **VAD toggle**: Not bound by default
- **Mute**: `Ctrl+Shift+M` (default) — toggles mute when VAD is active

## Files

| File | Purpose |
|------|---------|
| `whisper_typer.py` | Main application — GUI, state machine, event loop |
| `widgets.py` | Custom tkinter widgets — mic icon, VAD bars, duration badge, loading bar |
| `audio.py` | Mic capture, VAD processing, recording controller |
| `transcriber.py` | faster-whisper transcription wrapper |
| `typer.py` | Text output routing (clipboard, paste, auto-terminal) |
| `hotkeys.py` | Global hotkey listener (push-to-talk, VAD toggle) |
| `config.py` | All constants and configuration |
| `settings.py` | User settings persistence (JSON) |
| `compat/` | Cross-platform abstraction layer (Windows, macOS, Linux backends) |

## How It Works

1. **Audio capture**: `sounddevice` streams mic input at 16kHz
2. **VAD**: Silero VAD runs on a dedicated thread, detecting speech start/end
3. **Transcription**: `faster-whisper` transcribes audio segments (GPU-accelerated)
4. **Output**: Text is routed to the selected target (clipboard, paste, terminal)
5. **GUI**: Transparent tkinter overlay with PIL-rendered anti-aliased icons

The app uses a state machine: `IDLE → RECORDING → TRANSCRIBING → TYPING → IDLE`. Audio captured during transcription/typing is queued and processed sequentially.

## License

MIT
