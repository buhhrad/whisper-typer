# Whisper Typer

A lightweight, always-on-top voice typing widget for Windows. Transcribes speech in real-time using [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and routes text to your active terminal, clipboard, or any window.

![Windows](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)

## Features

- **Push-to-Talk** — Hold `Ctrl+Shift+Space` to record, release to transcribe
- **Always-on VAD** — Silero VAD detects speech automatically, hands-free
- **Snap to Terminal** — Attaches to Windows Terminal as a transparent overlay, follows the window
- **Multiple output routes** — Paste+Enter, Paste only, Clipboard, Type keys, or Auto Terminal (background)
- **Queued transcription** — Captures overlapping speech segments so pauses don't cut you off
- **System tray** — Minimizes to tray, stays out of the way
- **Configurable** — Model size, device, hotkeys, mic selection, output routing

## Requirements

- **Windows 10/11** (uses Win32 APIs for transparency and window management)
- **Python 3.10+**
- **CUDA GPU** (recommended) or CPU (slower transcription)

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/whisper-typer.git
cd whisper-typer
pip install -r requirements.txt
```

Or double-click `setup.bat` to install dependencies automatically.

### 2. Run

```bash
python whisper_typer.py
```

Or double-click `WhisperTyper.bat` for a windowless launch.

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

Edit `config.py` to change the default model:

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
| Paste + Enter | Clipboard → Ctrl+V → Enter (ideal for terminals) |
| Paste Only | Clipboard → Ctrl+V |
| Clipboard Only | Copies to clipboard, no paste |
| Type Keys | Types character by character (slow, universal) |
| Auto Terminal | Finds a terminal window and sends text there in the background |

### Hotkeys

Edit `config.py` or configure via the settings JSON:

- **Push-to-talk**: `Ctrl+Shift+Space` (default)
- **VAD toggle**: Not bound by default (configurable in settings)

## Files

| File | Purpose |
|------|---------|
| `whisper_typer.py` | Main application — GUI, state machine, event loop |
| `widgets.py` | Custom tkinter widgets — mic icon, VAD bars, duration badge, loading bar |
| `audio.py` | Mic capture, VAD processing, recording controller |
| `transcriber.py` | faster-whisper transcription wrapper |
| `typer.py` | Text output routing (clipboard, paste, type, auto-terminal) |
| `hotkeys.py` | Global hotkey listener (push-to-talk, VAD toggle) |
| `config.py` | All constants and configuration |
| `settings.py` | User settings persistence (JSON) |

## How It Works

1. **Audio capture**: `sounddevice` streams mic input at 16kHz
2. **VAD**: Silero VAD runs on a dedicated thread, detecting speech start/end
3. **Transcription**: `faster-whisper` transcribes audio segments (GPU-accelerated)
4. **Output**: Text is routed to the selected target (clipboard, paste, terminal)
5. **GUI**: Transparent tkinter overlay with PIL-rendered anti-aliased icons

The app uses a state machine: `IDLE → RECORDING → TRANSCRIBING → TYPING → IDLE`. Audio captured during transcription/typing is queued and processed sequentially.

## License

MIT
