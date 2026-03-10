
<div align="center">

<pre>
░█░█░█░█░▀█▀░█▀▀░█▀█░█▀▀░█▀▄░░░▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀░░░
░█▄█░█▀█░░█░░▀▀█░█▀▀░█▀▀░█▀▄░░░ speak ░░▒▒▓▓██▓▓▒▒░░ type ░░░
░▀░▀░▀░▀░▀▀▀░▀▀▀░▀░░░▀▀▀░▀░▀░░░▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄░░░
                T Y P E R
</pre>

<img src="demo.gif" width="172" />

**Local, offline voice typing for your entire computer.**

[![Windows](https://img.shields.io/badge/Windows-0078D4?logo=windows&logoColor=white)](#windows)
[![macOS](https://img.shields.io/badge/macOS-000000?logo=apple&logoColor=white)](#macos)
[![Linux](https://img.shields.io/badge/Linux-FCC624?logo=linux&logoColor=black)](#linux)
[![Python](https://img.shields.io/badge/Python_3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/buhhrad/whisper-typer?style=flat)](https://github.com/buhhrad/whisper-typer/stargazers)
[![VirusTotal](https://img.shields.io/badge/VirusTotal-0%2F63_clean-brightgreen?logo=virustotal)](https://www.virustotal.com/gui/file/1d28cee2fdd1e9f4781ef54d45a7e8b12d5f69dad12333239097e6a0d7bbe7dc)

</div>

---

## Quick Start

### Windows

```bash
git clone https://github.com/buhhrad/whisper-typer.git
cd whisper-typer
python install.py
```

### macOS

```bash
git clone https://github.com/buhhrad/whisper-typer.git
cd whisper-typer
python3 install.py
```

### Linux

```bash
sudo apt install xclip xdotool
git clone https://github.com/buhhrad/whisper-typer.git
cd whisper-typer
python3 install.py
```

The installer handles dependencies, downloads a model, and offers a desktop shortcut.

> **Note:** Built and tested on Windows. macOS/Linux support is in progress via the `compat/` abstraction layer. [Open an issue](https://github.com/buhhrad/whisper-typer/issues) if something breaks.

<details>
<summary><b>CLI options</b></summary>

```
python whisper_typer.py --model small       # Use a smaller/faster model
python whisper_typer.py --device cpu        # Force CPU (no CUDA needed)
python whisper_typer.py --list-devices      # List available microphones
```

</details>

---

## Features

A floating widget that transcribes speech using [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and types it wherever you need. No cloud, no accounts, no internet.

- **Voice-type anywhere** — Speak and your words appear in any text field
- **Send to Terminal** — Pastes transcription + Enter into a background terminal. Talk to Claude Code hands-free.
- **Snap to Terminal** — Transparent overlay that follows your terminal window
- **Hands-free VAD** — [Silero VAD](https://github.com/snakers4/silero-vad) detects speech automatically
- **Queued transcription** — Keeps recording while transcribing. No speech is ever lost.
- **Lightweight** — Pure Python, no Electron. Starts in seconds.

| Action | How |
|--------|-----|
| **Record** | Click the mic icon |
| **Push-to-talk** | Hold `Ctrl+Shift+Space`, release to transcribe |
| **Always-on VAD** | Click the bars icon |
| **Mute** | `Ctrl+Shift+M` |
| **Switch terminal** | `Ctrl+Tab` |
| **Settings** | Click the gear icon |

---

## Models

All models run locally. Pick your tradeoff:

| Model | Size | Speed | Quality | |
|-------|------|-------|---------|-|
| `tiny` | 75 MB | Fastest | Basic | |
| `base` | 150 MB | Fast | Good | |
| `small` | 500 MB | Medium | Better | |
| `medium` | 1.5 GB | Slow | Great | |
| `large-v3-turbo` | 1.6 GB | Fast | Great | **recommended** |
| `large-v3` | 3 GB | Slowest | Best | |

Change in settings or via `--model`. Models download automatically on first use.

---

## Privacy

Everything runs locally after the initial model download. No audio leaves your machine, no telemetry, no accounts.

---

## FAQ

<details>
<summary><b>Do I need a GPU?</b></summary>
No. CPU works fine with smaller models. A CUDA GPU makes larger models much faster.
</details>

<details>
<summary><b>What languages are supported?</b></summary>
99+ languages. Larger models handle more languages better.
</details>

<details>
<summary><b>Can I use it without a terminal?</b></summary>
Yes. Route output to clipboard or auto-paste instead.
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
| `hotkeys.py` | Global hotkey listener (push-to-talk, VAD, mute, terminal cycle) |
| `config.py` | Constants and configuration |
| `settings.py` | User settings persistence (JSON) |
| `compat/` | Platform abstraction layer (Windows, macOS, Linux) |

</details>

## Contributing

PRs welcome. [Open an issue](https://github.com/buhhrad/whisper-typer/issues) for bugs or feature requests.

<details>
<summary><b>Acknowledgments</b></summary>

Built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Silero VAD](https://github.com/snakers4/silero-vad), [OpenAI Whisper](https://github.com/openai/whisper), [sounddevice](https://github.com/spatialaudio/python-sounddevice), [pynput](https://github.com/moses-palmer/pynput), [pystray](https://github.com/moses-palmer/pystray), [Pillow](https://github.com/python-pillow/Pillow), and [PyTorch](https://github.com/pytorch/pytorch).

</details>

## License

[MIT](LICENSE)
