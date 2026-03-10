
<div align="center">

<pre>
░█░█░█░█░▀█▀░█▀▀░█▀█░█▀▀░█▀▄
░█▄█░█▀█░░█░░▀▀█░█▀▀░█▀▀░█▀▄
░▀░▀░▀░▀░▀▀▀░▀▀▀░▀░░░▀▀▀░▀░▀
          T Y P E R
</pre>

**Local voice typing for your entire computer.**

Offline voice-to-text that works anywhere — type into any app with your voice, or talk directly to CLI tools like Claude Code.
<br>
<img src="demo.gif" width="172" />
<br><br><br>
[![Windows](https://img.shields.io/badge/Windows_10%2F11-0078D4?logo=windows&logoColor=white)](https://github.com/buhhrad/whisper-typer)
[![Python](https://img.shields.io/badge/Python_3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/buhhrad/whisper-typer?style=flat)](https://github.com/buhhrad/whisper-typer/stargazers)
[![faster-whisper](https://img.shields.io/badge/powered_by-faster--whisper-orange)](https://github.com/SYSTRAN/faster-whisper)
[![VirusTotal](https://img.shields.io/badge/VirusTotal-0%2F63_clean-brightgreen?logo=virustotal)](https://www.virustotal.com/gui/file/134f259ba2b6411824fd07ad637f7e2956b275e0d365f592273ee762da926ee0/detection)

</div>

---

## Why Whisper Typer?

A small floating widget that transcribes your speech locally using [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and types it wherever you need it. Use it to voice-type into any application, or snap it to your terminal to talk directly to CLI tools like Claude Code.

- **Works everywhere** — Voice-type into any focused window on your computer
- **Send to Terminal** — Finds a terminal in the background, pastes your text + Enter, and restores your focus. Talk to CLI tools without switching windows.
- **Snap to Terminal** — Attaches to your terminal as a transparent overlay and follows the window (Windows)
- **Lightweight** — Pure Python, no Electron. Starts in seconds.
- **Queued transcription** — Keeps recording while transcribing so pauses in your speech don't lose words
- **Fully offline** — No accounts, no cloud, no internet required

## Features

### Dictation
- **Push-to-Talk** — Hold `Ctrl+Shift+Space` to record, release to transcribe
- **Always-on VAD** — [Silero VAD](https://github.com/snakers4/silero-vad) detects speech automatically, completely hands-free
- **Mute Toggle** — `Ctrl+Shift+M` to pause VAD without turning it off
- **Queued Transcription** — Overlapping speech segments are queued and processed sequentially — no speech is lost

### Output Routing
- **Send to Terminal** — Finds a terminal in the background, pastes your text + Enter, restores focus. Great for multitasking with CLI agents.
- **Auto Paste** — Pastes directly into whatever window is focused
- **Clipboard** — Copies to clipboard for manual pasting

### Interface
- **Always-on-Top** — Stays visible while you work in other apps
- **System Tray** — Minimizes to tray, stays out of the way
- **Duration Badge** — Shows recording time with a smooth animated pill
- **Amber Flash** — Widget flashes amber when no speech was detected in the recording
- **Fully Configurable** — Model, device, hotkeys, mic, output routing — all from the settings popup

## Quick Start

<table>
<tr>
<td align="center"><a href="#windows"><img src="https://img.shields.io/badge/Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" alt="Windows"></a></td>
<td align="center"><a href="#macos"><img src="https://img.shields.io/badge/macOS-000000?style=for-the-badge&logo=apple&logoColor=white" alt="macOS"></a></td>
<td align="center"><a href="#linux"><img src="https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black" alt="Linux"></a></td>
</tr>
</table>

<details open>
<summary><b id="windows">Windows</b></summary>

```bash
git clone https://github.com/buhhrad/whisper-typer.git
cd whisper-typer
python install.py
```

Or install manually:

```bash
pip install .
python -m whisper_typer
```

**Requirements:** Windows 10/11, Python 3.10+, CUDA GPU recommended (CPU works but slower)

</details>

<details>
<summary><b id="macos">macOS</b></summary>

```bash
git clone https://github.com/buhhrad/whisper-typer.git
cd whisper-typer
python3 install.py
```

Or install manually:

```bash
pip3 install .
python3 -m whisper_typer
```

**Requirements:** Python 3.10+, Apple Silicon recommended for best performance

> macOS support is in development. The platform abstraction layer exists (`compat/`) but is not yet fully tested.

</details>

<details>
<summary><b id="linux">Linux</b></summary>

```bash
git clone https://github.com/buhhrad/whisper-typer.git
cd whisper-typer
python3 install.py
```

Or install manually:

```bash
pip3 install .
python3 -m whisper_typer
```

**Requirements:** Python 3.10+, CUDA GPU recommended, PulseAudio or PipeWire for mic access, xclip and xdotool for clipboard and terminal features (X11)

> Linux support is in development. The platform abstraction layer exists (`compat/`) but is not yet fully tested.

</details>

> **Note:** Whisper Typer is built and tested on Windows. macOS and Linux have platform abstraction layers in place but have not been fully tested. If you run into issues on those platforms, [open an issue](https://github.com/buhhrad/whisper-typer/issues).

The installer checks your environment, installs dependencies, and optionally pre-downloads a Whisper model.

<details>
<summary><b>CLI options</b></summary>

```
python -m whisper_typer --model small       # Use a smaller/faster model
python -m whisper_typer --device cpu        # Force CPU (no CUDA needed)
python -m whisper_typer --list-devices      # List available microphones
```

</details>

## How to Use

| Action | How |
|--------|-----|
| **Manual record** | Click the mic icon |
| **Push-to-talk** | Hold `Ctrl+Shift+Space`, release to transcribe |
| **Always-on VAD** | Click the bars icon — speech is detected automatically |
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
| `large-v3-turbo` | 1.6 GB | Fast | Great | **recommended** |
| `large-v3` | 3 GB | Slowest | Best | |

Change the model in settings (gear icon → Whisper section) or via `--model`.

Models download automatically on first use from HuggingFace, or pre-download via `python install.py`.

## Highlights

- **Free and open source** — MIT licensed, no accounts, no subscriptions
- **Fully offline** — No cloud, no internet, no telemetry
- **Terminal integration** — Snap to terminal, auto-paste + Enter, background terminal detection
- **Hands-free VAD** — Silero voice activity detection, just talk and it types
- **Queued transcription** — Keeps recording while transcribing, no speech is lost
- **Configurable hotkeys** — Customize push-to-talk, VAD toggle, and mute keybindings
- **6 Whisper models** — From tiny (75 MB) to large-v3 (3 GB), pick your speed/quality tradeoff
- **Cross-platform** — Windows ready, macOS and Linux support in development

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

## Privacy

Whisper Typer processes everything locally. Your audio never leaves your machine and no telemetry is collected.

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
Yes. The terminal snap feature is optional. You can use it as a floating widget anywhere on your screen and route output to clipboard or paste.
</details>

<details>
<summary><b>What languages are supported?</b></summary>
Whisper supports 99+ languages. Accuracy depends on the model size — larger models handle more languages better.
</details>

<details>
<summary><b>How is this different from Windows Speech Recognition?</b></summary>
Whisper is dramatically more accurate, supports more languages, and works offline with no training. Windows Speech Recognition requires online connectivity for its best models and struggles with accents and technical vocabulary.
</details>

## Roadmap

**Phase 1 — Polish**
- [ ] VAD sensitivity slider
- [ ] macOS support (abstraction layer exists, needs testing)
- [ ] Linux support (same as above)
- [ ] Custom dictionary for frequently used words and names

**Phase 2 — Developer Features**
- [ ] AI text cleanup (remove filler words, fix grammar)
- [ ] Voice commands ("new line", "period", "select all", "undo")
- [ ] Per-app output profiles (different formatting for terminal vs Slack vs code editor)
- [ ] Multi-monitor snap (snap to any window, not just terminal)

**Phase 3 — Distribution**
- [ ] Auto-updates
- [ ] Standalone .exe installer (no Python required)
- [ ] Plugin system for custom output routes

## Contributing

Contributions are welcome. Fork the repo, make your changes, and open a pull request.

If you find a bug or have a feature request, [open an issue](https://github.com/buhhrad/whisper-typer/issues).

## Acknowledgments

Built on the shoulders of these excellent open-source projects:

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — CTranslate2-powered Whisper inference (up to 4x faster than OpenAI's implementation)
- [Silero VAD](https://github.com/snakers4/silero-vad) — Pre-trained voice activity detection model
- [OpenAI Whisper](https://github.com/openai/whisper) — The speech recognition model that started it all
- [sounddevice](https://github.com/spatialaudio/python-sounddevice) — PortAudio bindings for Python
- [pynput](https://github.com/moses-palmer/pynput) — Cross-platform input monitoring and simulation
- [pystray](https://github.com/moses-palmer/pystray) — System tray icon support
- [Pillow](https://github.com/python-pillow/Pillow) — Image processing for anti-aliased UI rendering
- [PyTorch](https://github.com/pytorch/pytorch) — ML framework powering Silero VAD

## License

[MIT](LICENSE)
