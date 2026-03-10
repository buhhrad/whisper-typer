
<div align="center">

<pre>
░█░█░█░█░▀█▀░█▀▀░█▀█░█▀▀░█▀▄
░█▄█░█▀█░░█░░▀▀█░█▀▀░█▀▀░█▀▄
░▀░▀░▀░▀░▀▀▀░▀▀▀░▀░░░▀▀▀░▀░▀
          T Y P E R
</pre>

<img src="demo.gif" width="172" />

**Local, offline voice typing for your entire computer.**

[![Windows](https://img.shields.io/badge/Windows_10%2F11-0078D4?logo=windows&logoColor=white)](https://github.com/buhhrad/whisper-typer)
[![Python](https://img.shields.io/badge/Python_3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/buhhrad/whisper-typer?style=flat)](https://github.com/buhhrad/whisper-typer/stargazers)
[![VirusTotal](https://img.shields.io/badge/VirusTotal-0%2F63_clean-brightgreen?logo=virustotal)](https://www.virustotal.com/gui/file/134f259ba2b6411824fd07ad637f7e2956b275e0d365f592273ee762da926ee0/detection)

</div>

---

## Quick Start

Clone the repo wherever you want to keep it:

### Windows

```bash
cd %USERPROFILE%\Desktop
git clone https://github.com/buhhrad/whisper-typer.git
cd whisper-typer
python install.py
whisper-typer.bat
```

### macOS

```bash
cd ~/Desktop
git clone https://github.com/buhhrad/whisper-typer.git
cd whisper-typer
python3 install.py
./whisper-typer.sh
```

### Linux

```bash
cd ~/Desktop
git clone https://github.com/buhhrad/whisper-typer.git
cd whisper-typer
sudo apt install xclip xdotool   # required for clipboard & terminal features
python3 install.py
./whisper-typer.sh
```

The installer checks your environment, installs dependencies, downloads a model, and creates a launcher you can double-click or run from the terminal.

> **Note:** Whisper Typer is built and tested on Windows. macOS and Linux support is in development — the platform abstraction layer exists (`compat/`) but is not yet fully tested. If you run into issues, [open an issue](https://github.com/buhhrad/whisper-typer/issues).

<details>
<summary><b>CLI options</b></summary>

```
python whisper_typer.py --model small       # Use a smaller/faster model
python whisper_typer.py --device cpu        # Force CPU (no CUDA needed)
python whisper_typer.py --list-devices      # List available microphones
```

</details>

---

## What It Does

A small floating widget that transcribes your speech locally using [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and types it wherever you need it. No cloud, no accounts, no internet required.

- **Voice-type into any text field** — Click the field you want, speak, and your words appear. Works with any app.
- **Send to Terminal** — Finds a terminal in the background, pastes your text + Enter, and restores your focus. Talk to Claude Code without switching windows.
- **Snap to Terminal** — Attaches to your terminal as a transparent overlay and follows the window (Windows)
- **Hands-free VAD** — [Silero VAD](https://github.com/snakers4/silero-vad) detects speech automatically. Just talk and it types.
- **Queued transcription** — Keeps recording while transcribing. No speech is ever lost.
- **Lightweight** — Pure Python, no Electron. Starts in seconds.
- **Configurable** — 6 Whisper models, custom hotkeys, multiple output routes, mic selection, terminal targeting

---

## How to Use

| Action | How |
|--------|-----|
| **Manual record** | Click the mic icon |
| **Push-to-talk** | Hold `Ctrl+Shift+Space`, release to transcribe |
| **Always-on VAD** | Click the bars icon — speech is detected automatically |
| **Mute (VAD)** | `Ctrl+Shift+M` while VAD is active |
| **Switch terminal** | `Ctrl+Tab` to cycle target terminal |
| **Settings** | Click the gear icon |
| **Snap to terminal** | Settings → Snap to Terminal |
| **Select terminal** | Settings → Target terminal (when multiple are open) |

---

## Features

### Dictation
- **Push-to-Talk** — Hold `Ctrl+Shift+Space` to record, release to transcribe
- **Always-on VAD** — Silero VAD detects speech automatically, completely hands-free
- **Mute Toggle** — `Ctrl+Shift+M` to pause VAD without turning it off

### Output Routing
- **Send to Terminal** — Finds a terminal in the background, pastes your text + Enter, restores focus
- **Auto Paste** — Pastes into the currently focused text field
- **Clipboard** — Copies to clipboard for manual pasting

### Terminal
- **Terminal Selector** — Choose which terminal to target when multiple are open
- **Smart Labels** — Each terminal shows its screen position (top-left, center, right, etc.)
- **Cycle Hotkey** — `Ctrl+Tab` to switch target terminal without opening settings (configurable)
- **Auto-detect** — Automatically finds and targets a terminal on startup

### Interface
- **Always-on-Top** — Stays visible while you work in other apps
- **System Tray** — Minimizes to tray, stays out of the way
- **Duration Badge** — Shows recording time with a smooth animated pill
- **Amber Flash** — Widget flashes amber when no speech was detected
- **Close Animation** — Smooth collapse animation on exit
- **Fully Configurable** — Model, device, hotkeys, mic, output routing — all from the settings popup

---

## Models

All models run locally via [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Pick your tradeoff:

| Model | Size | Speed | Quality | |
|-------|------|-------|---------|-|
| `tiny` | 75 MB | Fastest | Basic | |
| `base` | 150 MB | Fast | Good | |
| `small` | 500 MB | Medium | Better | |
| `medium` | 1.5 GB | Slow | Great | |
| `large-v3-turbo` | 1.6 GB | Fast | Great | **recommended** |
| `large-v3` | 3 GB | Slowest | Best | |

Change the model in settings or via `--model`. Models download automatically on first use.

---

## Privacy

Whisper Typer processes everything locally. Your audio never leaves your machine and no telemetry is collected. There are no accounts, no cloud services, and no network requests.

---

## FAQ

<details>
<summary><b>Do I need a GPU?</b></summary>
No. CPU works fine, especially with smaller models like <code>tiny</code> or <code>base</code>. A CUDA-capable NVIDIA GPU makes transcription significantly faster, especially with <code>large-v3-turbo</code>.
</details>

<details>
<summary><b>Does it work with any microphone?</b></summary>
Yes. Any microphone your system recognizes will work. Select your preferred mic in the settings popup.
</details>

<details>
<summary><b>Can I use it without a terminal?</b></summary>
Yes. The terminal features are optional. Use it as a floating widget anywhere on your screen and route output to clipboard or paste.
</details>

<details>
<summary><b>What languages are supported?</b></summary>
Whisper supports 99+ languages. Accuracy depends on the model size — larger models handle more languages better.
</details>

<details>
<summary><b>How is this different from Windows Speech Recognition?</b></summary>
Whisper is dramatically more accurate, supports more languages, and works fully offline with no training. Windows Speech Recognition requires online connectivity for its best models and struggles with accents and technical vocabulary.
</details>

---

## Roadmap

- [ ] VAD sensitivity slider
- [ ] macOS and Linux testing
- [ ] Custom dictionary for names and technical terms
- [ ] AI text cleanup (remove filler words, fix grammar)
- [ ] Voice commands ("new line", "period", "select all")
- [ ] Per-app output profiles
- [ ] Standalone .exe installer (no Python required)

---

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

| File | Purpose |
|------|---------|
| `whisper_typer.py` | Main app — GUI, state machine, event loop |
| `widgets.py` | Custom tkinter widgets — mic icon, VAD bars, duration badge |
| `audio.py` | Mic capture, VAD processing, recording controller |
| `transcriber.py` | faster-whisper transcription wrapper |
| `typer.py` | Text output routing (clipboard, paste, auto-terminal) |
| `hotkeys.py` | Global hotkey listener (push-to-talk, VAD toggle, mute, terminal cycle) |
| `config.py` | Constants and configuration |
| `settings.py` | User settings persistence (JSON) |
| `compat/` | Platform abstraction layer (Windows, macOS, Linux) |

</details>

## Contributing

Contributions are welcome. Fork the repo, make your changes, and open a pull request.

If you find a bug or have a feature request, [open an issue](https://github.com/buhhrad/whisper-typer/issues).

## Acknowledgments

Built on these excellent open-source projects:

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — CTranslate2-powered Whisper inference
- [Silero VAD](https://github.com/snakers4/silero-vad) — Voice activity detection
- [OpenAI Whisper](https://github.com/openai/whisper) — The speech recognition model
- [sounddevice](https://github.com/spatialaudio/python-sounddevice) — PortAudio bindings
- [pynput](https://github.com/moses-palmer/pynput) — Input monitoring and simulation
- [pystray](https://github.com/moses-palmer/pystray) — System tray support
- [Pillow](https://github.com/python-pillow/Pillow) — Image processing
- [PyTorch](https://github.com/pytorch/pytorch) — ML framework for Silero VAD

## License

[MIT](LICENSE)
