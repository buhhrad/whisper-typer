
<div align="center">

```
░█░█░█░█░▀█▀░█▀▀░█▀█░█▀▀░█▀▄
░█▄█░█▀█░░█░░▀▀█░█▀▀░█▀▀░█▀▄
░▀░▀░▀░▀░▀▀▀░▀▀▀░▀░░░▀▀▀░▀░▀
          T Y P E R
```

**Local voice typing that lives in your terminal.**

Talk. Transcribe. Type. No cloud. No latency. No subscription.

<img src="demo.gif" width="344" />

[![Windows](https://img.shields.io/badge/Windows_10%2F11-0078D4?logo=windows&logoColor=white)](https://github.com/buhhrad/whisper-typer)
[![Python](https://img.shields.io/badge/Python_3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![faster-whisper](https://img.shields.io/badge/powered_by-faster--whisper-orange)](https://github.com/SYSTRAN/faster-whisper)

</div>

## What is this?

A tiny, always-on-top floating widget that transcribes your speech in real-time using [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and routes the text wherever you need it — your terminal, clipboard, or any focused window.

It snaps to your terminal as a transparent overlay and stays out of the way until you need it.

## Features

- **Push-to-Talk** — Hold `Ctrl+Shift+Space` to record, release to transcribe
- **Always-on VAD** — Silero VAD detects speech automatically, completely hands-free
- **Snap to Terminal** — Attaches to Windows Terminal as a transparent overlay, follows the window
- **Auto Terminal** — Finds a terminal in the background, pastes your text + Enter, restores focus
- **Queued transcription** — Overlapping speech segments are captured so pauses don't cut you off
- **System tray** — Minimizes to tray, stays out of the way
- **Fully configurable** — Model, device, hotkeys, mic, output routing — all from the settings popup

## Quick Start

```bash
git clone https://github.com/buhhrad/whisper-typer.git
cd whisper-typer
python install.py
```

The installer checks your environment, installs dependencies, and optionally pre-downloads a whisper model.

Or install manually:

```bash
pip install .
whisper-typer
```

<details>
<summary><b>CLI options</b></summary>

```
whisper-typer --model small       # Use a smaller/faster model
whisper-typer --device cpu        # Force CPU (no CUDA needed)
whisper-typer --list-devices      # List available microphones
```

</details>

## How to Use

| Action | How |
|--------|-----|
| **Manual record** | Click the mic icon |
| **Push-to-talk** | Hold `Ctrl+Shift+Space`, release to transcribe |
| **Always-on VAD** | Click the bars icon — speaks are detected automatically |
| **Mute (VAD)** | `Ctrl+Shift+M` while VAD is active |
| **Settings** | Click the gear icon |
| **Snap to terminal** | Settings → Snap to Terminal |

## Models

All models run locally via [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Pick your tradeoff:

| Model | Size | Speed | Quality | |
|-------|------|-------|---------|-|
| `tiny` | 75 MB | Fastest | Basic | |
| `base` | 150 MB | Fast | Good | |
| `small` | 500 MB | Medium | Better | |
| `medium` | 1.5 GB | Slow | Great | |
| `large-v3-turbo` | 1.6 GB | Fast | Great | **← recommended** |
| `large-v3` | 3 GB | Slowest | Best | |

Change the model in settings (gear icon → Whisper section) or via `--model`.

Models download automatically on first use from HuggingFace, or pre-download via `python install.py`.

## Output Routes

| Route | What it does |
|-------|-------------|
| **Auto Terminal** | Finds a background terminal, pastes + Enter, restores your focus *(default)* |
| **Paste Only** | Copies to clipboard → sends Ctrl+V to the focused window |
| **Clipboard Only** | Copies to clipboard, nothing else |

## Requirements

- **Windows 10 or 11**
- **Python 3.10+**
- **CUDA GPU** recommended — CPU works but transcription is slower

> macOS and Linux support is in development. The abstraction layer exists (`compat/`) but the backends are untested and not yet included in releases.

<details>
<summary><b>Architecture</b></summary>

```
Microphone → sounddevice (16kHz)
         → Silero VAD (speech detection)
         → faster-whisper (transcription)
         → Output routing (clipboard / paste / terminal)
         → Transparent tkinter overlay (GUI)
```

**State machine:** `IDLE → RECORDING → TRANSCRIBING → TYPING → IDLE`

Audio captured during transcription/typing is queued and processed sequentially — no speech is lost.

| File | Purpose |
|------|---------|
| `whisper_typer.py` | Main app — GUI, state machine, event loop |
| `widgets.py` | Custom tkinter widgets — mic icon, VAD bars, duration badge, loading bar |
| `audio.py` | Mic capture, VAD processing, recording controller |
| `transcriber.py` | faster-whisper transcription wrapper |
| `typer.py` | Text output routing (clipboard, paste, auto-terminal) |
| `hotkeys.py` | Global hotkey listener (push-to-talk, VAD toggle, mute) |
| `config.py` | Constants and configuration |
| `settings.py` | User settings persistence (JSON) |
| `compat/` | Platform abstraction layer |

</details>

## License

[MIT](LICENSE) — do whatever you want with it.
