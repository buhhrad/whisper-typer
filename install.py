#!/usr/bin/env python3
"""Whisper Typer — stylized installer.

Run: python install.py
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import shutil
import time
import threading

# ── ANSI styling ──────────────────────────────────────────────────────

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_WHITE = "\033[97m"
_GRAY = "\033[90m"
_GREEN = "\033[92m"
_RED = "\033[91m"
_AMBER = "\033[93m"
_CYAN = "\033[96m"
_BG_DARK = "\033[48;2;12;12;26m"

def _enable_ansi():
    """Enable ANSI escape codes on Windows."""
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        k.SetConsoleMode(k.GetStdHandle(-11), 7)

def _styled(text: str, *codes: str) -> str:
    return "".join(codes) + text + _RESET

def _print_banner():
    banner = f"""
  {_styled("░█░█░█░█░▀█▀░█▀▀░█▀█░█▀▀░█▀▄", _AMBER, _BOLD)}
  {_styled("░█▄█░█▀█░░█░░▀▀█░█▀▀░█▀▀░█▀▄", _AMBER)}
  {_styled("░▀░▀░▀░▀░▀▀▀░▀▀▀░▀░░░▀▀▀░▀░▀", _DIM)}

  {_styled("T Y P E R", _WHITE, _BOLD)}
  {_styled("Local voice typing — any platform", _GRAY)}
"""
    print(banner)


# ── Spinner ───────────────────────────────────────────────────────────

class Spinner:
    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, text: str):
        self._text = text
        self._running = False
        self._thread = None
        self._frame = 0

    def __enter__(self):
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._running = False
        if self._thread:
            self._thread.join()
        # Clear the spinner line
        print(f"\r\033[K", end="")

    def _spin(self):
        while self._running:
            frame = self._FRAMES[self._frame % len(self._FRAMES)]
            print(f"\r  {_styled(frame, _AMBER)} {_styled(self._text, _GRAY)}", end="", flush=True)
            self._frame += 1
            time.sleep(0.08)


def _step_ok(text: str, detail: str = ""):
    d = f"  {_styled(detail, _DIM)}" if detail else ""
    print(f"  {_styled('✓', _GREEN)} {_styled(text, _WHITE)}{d}")

def _step_fail(text: str, detail: str = ""):
    d = f"  {_styled(detail, _DIM)}" if detail else ""
    print(f"  {_styled('✗', _RED)} {_styled(text, _WHITE)}{d}")

def _step_info(text: str):
    print(f"  {_styled('→', _CYAN)} {_styled(text, _GRAY)}")

def _section(title: str):
    print(f"\n  {_styled(title, _WHITE, _BOLD)}")
    print(f"  {_styled('─' * 40, _DIM)}")


# ── Checks ────────────────────────────────────────────────────────────

def _check_python() -> bool:
    v = sys.version_info
    ver_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 10):
        _step_ok("Python", ver_str)
        return True
    _step_fail("Python", f"{ver_str} — need 3.10+")
    return False

def _check_pip() -> bool:
    try:
        import pip
        _step_ok("pip", pip.__version__)
        return True
    except ImportError:
        _step_fail("pip", "not found")
        return False

def _check_cuda() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode == 0 and result.stdout.strip():
            gpu_info = result.stdout.strip().split("\n")[0].strip()
            _step_ok("CUDA GPU", gpu_info)
            return True, gpu_info
    except Exception:
        pass
    _step_info("No CUDA GPU detected — will use CPU (slower)")
    return False, ""

def _check_disk_space() -> bool:
    try:
        total, used, free = shutil.disk_usage(os.path.dirname(os.path.abspath(__file__)))
        free_gb = free / (1024 ** 3)
        if free_gb >= 4:
            _step_ok("Disk space", f"{free_gb:.1f} GB free")
            return True
        _step_fail("Disk space", f"{free_gb:.1f} GB free — need 4+ GB for models")
        return False
    except Exception:
        return True


def _check_platform_deps() -> None:
    """Check for platform-specific optional dependencies."""
    if sys.platform == "linux":
        missing = []
        for tool, purpose in [("xclip", "clipboard"), ("xdotool", "terminal finding")]:
            if not shutil.which(tool):
                missing.append(f"{tool} ({purpose})")
        if missing:
            _step_info(f"Optional: install {', '.join(missing)} for full functionality")
        else:
            _step_ok("Linux tools", "xclip, xdotool")
    elif sys.platform == "darwin":
        _step_ok("macOS tools", "pbcopy, osascript (built-in)")


# ── Install ───────────────────────────────────────────────────────────

def _install_package() -> bool:
    """Install whisper-typer via pip."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", ".", "--quiet"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True, timeout=300,
        )
        return proc.returncode == 0
    except Exception:
        return False


# ── Model download ────────────────────────────────────────────────────

_MODELS = {
    "tiny":             ("75 MB",  "Fastest, basic quality"),
    "base":             ("150 MB", "Fast, good quality"),
    "small":            ("500 MB", "Balanced speed & quality"),
    "medium":           ("1.5 GB", "Slow, great quality"),
    "large-v3-turbo":   ("1.6 GB", "Fast, great quality (recommended)"),
    "large-v3":         ("3 GB",   "Slowest, best quality"),
}

def _check_model_cached(model: str) -> bool:
    """Check if a faster-whisper model is already downloaded."""
    try:
        from faster_whisper import WhisperModel
        WhisperModel(model, local_files_only=True)
        return True
    except Exception:
        return False

def _download_model(model: str) -> bool:
    """Download a model by loading it (triggers HuggingFace download)."""
    try:
        from faster_whisper import WhisperModel
        WhisperModel(model, device="cpu", compute_type="int8")
        return True
    except Exception:
        return False

def _prompt_model(has_cuda: bool) -> str | None:
    """Ask user which model to pre-download."""
    print()
    _section("Model Selection")
    print()

    default = "large-v3-turbo" if has_cuda else "base"
    for i, (name, (size, desc)) in enumerate(_MODELS.items(), 1):
        cached = _check_model_cached(name)
        tag = _styled(" (installed)", _GREEN) if cached else ""
        marker = _styled("→", _AMBER) if name == default else " "
        n = _styled(name, _WHITE, _BOLD) if name == default else _styled(name, _WHITE)
        print(f"  {marker} {i}. {n}  {_styled(size, _DIM)}  {_styled(desc, _GRAY)}{tag}")

    print(f"\n  {_styled(f'Recommended: {default}', _DIM)}")
    print(f"  {_styled('Models download on first use if not pre-downloaded.', _DIM)}")

    try:
        choice = input(f"\n  {_styled('Download a model now? [1-6 / Enter for recommended / s to skip]:', _GRAY)} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None

    if choice == "s" or choice == "skip":
        return None

    if choice == "":
        return default

    try:
        idx = int(choice) - 1
        names = list(_MODELS.keys())
        if 0 <= idx < len(names):
            return names[idx]
    except ValueError:
        pass

    return default


# ── Main ──────────────────────────────────────────────────────────────

def main():
    _enable_ansi()
    _print_banner()

    # ── Environment checks
    _section("Environment")
    ok = _check_python()
    if not ok:
        print(f"\n  {_styled('Python 3.10+ is required. Install from python.org', _RED)}")
        sys.exit(1)
    _check_pip()
    has_cuda, _ = _check_cuda()
    _check_disk_space()
    _step_ok("Platform", f"{platform.system()} {platform.release()}")
    _check_platform_deps()

    # ── Install dependencies
    _section("Install")
    with Spinner("Installing dependencies..."):
        success = _install_package()

    if success:
        _step_ok("Dependencies installed")
    else:
        _step_fail("Install failed — try manually: pip install .")
        sys.exit(1)

    # ── Model selection
    model = _prompt_model(has_cuda)
    if model:
        if _check_model_cached(model):
            _step_ok(f"Model '{model}' already downloaded")
        else:
            size = _MODELS[model][0]
            print()
            with Spinner(f"Downloading {model} ({size})... this may take a while"):
                dl_ok = _download_model(model)
            if dl_ok:
                _step_ok(f"Model '{model}' downloaded")
            else:
                _step_info(f"Download failed — model will download on first launch")

    # ── Done
    print()
    _section("Ready")
    print()
    print(f"  {_styled('Run from anywhere:', _GRAY)}")
    print(f"  {_styled('python -m whisper_typer', _AMBER, _BOLD)}")
    print()
    if not has_cuda:
        print(f"  {_styled('Tip: For faster transcription, use a CUDA GPU', _DIM)}")
        print(f"  {_styled('     and select cuda in settings.', _DIM)}")
        print()
    print(f"  {_styled('─' * 40, _DIM)}")
    print(f"  {_styled('Docs:', _GRAY)} {_styled('https://github.com/buhhrad/whisper-typer', _CYAN)}")
    print()


if __name__ == "__main__":
    main()
