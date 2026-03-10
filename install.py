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


# ── Launcher ─────────────────────────────────────────────────────────

def _create_launcher() -> None:
    """Create a platform-specific launcher script after install."""
    install_dir = os.path.dirname(os.path.abspath(__file__))
    python = sys.executable

    if sys.platform == "win32":
        # .bat file — uses pythonw to avoid console window
        pythonw = os.path.join(os.path.dirname(python), "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = "pythonw"
        bat_path = os.path.join(install_dir, "whisper-typer.bat")
        with open(bat_path, "w") as f:
            f.write(f'@echo off\n')
            f.write(f'start "" "{pythonw}" "%~dp0whisper_typer.py" %*\n')
        _step_ok("Created whisper-typer.bat")
    else:
        # Shell script for macOS/Linux
        sh_path = os.path.join(install_dir, "whisper-typer.sh")
        with open(sh_path, "w") as f:
            f.write("#!/usr/bin/env bash\n")
            f.write(f'cd "$(dirname "$0")"\n')
            f.write(f'python3 whisper_typer.py "$@" &\n')
            f.write("disown\n")
        os.chmod(sh_path, 0o755)
        _step_ok("Created whisper-typer.sh")


def _generate_icon() -> str | None:
    """Generate a whisper-typer.ico file using PIL. Returns path or None."""
    install_dir = os.path.dirname(os.path.abspath(__file__))
    ico_path = os.path.join(install_dir, "whisper-typer.ico")
    if os.path.exists(ico_path):
        return ico_path
    try:
        from PIL import Image, ImageDraw
        # Dark circle with amber mic — matches the app theme
        sizes = [16, 32, 48, 64, 128, 256]
        images = []
        for sz in sizes:
            img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            p = sz / 64  # scale factor
            # Background circle
            draw.ellipse([int(4*p), int(4*p), int(60*p), int(60*p)], fill="#1a1a2a")
            draw.ellipse([int(4*p), int(4*p), int(60*p), int(60*p)], outline="#3a3a50", width=max(1, int(2*p)))
            # Mic capsule
            lw = max(1, int(2*p))
            draw.rounded_rectangle([int(24*p), int(14*p), int(40*p), int(38*p)],
                                   radius=int(6*p), outline="#e0a820", width=lw)
            # Mic arc
            draw.arc([int(20*p), int(28*p), int(44*p), int(50*p)],
                     start=180, end=0, fill="#e0a820", width=lw)
            # Mic stem
            draw.line([int(32*p), int(50*p), int(32*p), int(56*p)], fill="#e0a820", width=lw)
            draw.line([int(24*p), int(56*p), int(40*p), int(56*p)], fill="#e0a820", width=lw)
            images.append(img)
        images[0].save(ico_path, format="ICO", sizes=[(s, s) for s in sizes],
                       append_images=images[1:])
        return ico_path
    except Exception:
        return None


def _prompt_shortcut() -> None:
    """Ask the user if they want a desktop shortcut."""
    try:
        choice = input(f"\n  {_styled('Create a desktop shortcut? [y/N]:', _GRAY)} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if choice not in ("y", "yes"):
        return

    install_dir = os.path.dirname(os.path.abspath(__file__))
    ico_path = _generate_icon()

    if sys.platform == "win32":
        # Use Shell API to find actual Desktop (handles OneDrive redirect)
        try:
            result = subprocess.run(
                ["powershell", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            desktop = result.stdout.strip()
        except Exception:
            desktop = ""
        if not desktop or not os.path.isdir(desktop):
            desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        if not os.path.isdir(desktop):
            _step_fail("Desktop folder not found")
            return
        # Point shortcut directly to pythonw.exe — no .bat, no console
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = sys.executable  # fallback to python.exe
        script_path = os.path.join(install_dir, "whisper_typer.py")
        shortcut_path = os.path.join(desktop, "Whisper Typer.lnk")
        icon_arg = f'$s.IconLocation = "{ico_path}"; ' if ico_path else ""
        ps_cmd = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$s = $ws.CreateShortcut("{shortcut_path}"); '
            f'$s.TargetPath = "{pythonw}"; '
            f'$s.Arguments = """{script_path}"""; '
            f'$s.WorkingDirectory = "{install_dir}"; '
            f'$s.Description = "Whisper Typer — local voice typing"; '
            f'{icon_arg}'
            f'$s.Save()'
        )
        try:
            subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            _step_ok("Desktop shortcut created", "Whisper Typer")
        except Exception:
            _step_fail("Could not create shortcut")
    elif sys.platform == "darwin":
        desktop = os.path.expanduser("~/Desktop")
        sh_path = os.path.join(install_dir, "whisper-typer.sh")
        try:
            subprocess.run(
                ["ln", "-sf", sh_path, os.path.join(desktop, "Whisper Typer")],
                timeout=5,
            )
            _step_ok("Desktop shortcut created")
        except Exception:
            _step_fail("Could not create shortcut")
    else:
        desktop = os.path.expanduser("~/Desktop")
        sh_path = os.path.join(install_dir, "whisper-typer.sh")
        desktop_file = os.path.join(desktop, "Whisper Typer.desktop")
        icon_line = f"Icon={ico_path}\n" if ico_path else ""
        try:
            with open(desktop_file, "w") as f:
                f.write("[Desktop Entry]\n")
                f.write("Type=Application\n")
                f.write("Name=Whisper Typer\n")
                f.write("Comment=Local voice typing\n")
                f.write(f"Exec={sh_path}\n")
                f.write(f"Path={install_dir}\n")
                f.write("Terminal=false\n")
                f.write(icon_line)
            os.chmod(desktop_file, 0o755)
            _step_ok("Desktop shortcut created")
        except Exception:
            _step_fail("Could not create shortcut")


# ── Install ───────────────────────────────────────────────────────────

def _install_package() -> bool:
    """Install dependencies via pip."""
    try:
        req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"],
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

    # ── Create launcher + shortcut
    _create_launcher()
    _prompt_shortcut()

    # ── Done
    print()
    _section("Ready")
    print()
    print(f"  {_styled('Launch Whisper Typer from:', _GRAY)}")
    print(f"  {_styled('• Desktop shortcut', _WHITE)}  {_styled('(if created above)', _DIM)}")
    print(f"  {_styled('• python whisper_typer.py', _WHITE)}  {_styled('(from this folder)', _DIM)}")
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
