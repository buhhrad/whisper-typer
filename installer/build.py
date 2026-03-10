#!/usr/bin/env python3
"""Whisper Typer — installer build script.

Bundles the app with PyInstaller, then creates a Windows installer with Inno Setup.

Usage:
    python installer/build.py              # Build everything
    python installer/build.py --no-inno    # PyInstaller only (skip Inno Setup)
    python installer/build.py --cpu-only   # Exclude CUDA (smaller ~300MB vs ~2GB)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "installer" / "dist"
BUILD_DIR = ROOT / "installer" / "build"
SPEC_NAME = "WhisperTyper"

# Common Inno Setup install locations
INNO_PATHS = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    r"D:\Inno Setup 6\ISCC.exe",
]


def find_inno() -> str | None:
    for p in INNO_PATHS:
        if os.path.isfile(p):
            return p
    # Check PATH
    found = shutil.which("ISCC")
    return found


def get_version() -> str:
    """Read version from pyproject.toml."""
    toml = ROOT / "pyproject.toml"
    for line in toml.read_text().splitlines():
        if line.strip().startswith("version"):
            return line.split('"')[1]
    return "1.0.0"


def get_torch_excludes(cpu_only: bool) -> list[str]:
    """Return PyInstaller excludes to shrink the bundle."""
    excludes = [
        "matplotlib", "scipy", "pandas", "IPython", "notebook",
        "tensorboard", "sympy", "jinja2",
        "trends",  # trends.py is a dev utility, not part of the app
    ]
    if cpu_only:
        excludes += [
            "torch.cuda",
            "triton",
        ]
    return excludes


def get_hidden_imports() -> list[str]:
    """Hidden imports that PyInstaller misses."""
    return [
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "pystray._win32",
        "PIL._tkinter_finder",
        "sounddevice",
        "_sounddevice_data",
        "ctranslate2",
        "faster_whisper",
        "huggingface_hub",
        "tokenizers",
    ]


def build_pyinstaller(cpu_only: bool = False) -> Path:
    """Run PyInstaller and return the output directory."""
    print(f"\n{'='*60}")
    print(f"  Building {SPEC_NAME} with PyInstaller")
    print(f"  Mode: {'CPU-only' if cpu_only else 'Full (CUDA + CPU)'}")
    print(f"{'='*60}\n")

    # Clean previous build
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", SPEC_NAME,
        "--noconfirm",
        "--windowed",                    # No console window (pythonw equivalent)
        "--icon", str(ROOT / "icons" / "whisper-typer.ico"),
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        "--specpath", str(ROOT / "installer"),
    ]

    # Add data files
    data_files = [
        (str(ROOT / "icons"), "icons"),
        (str(ROOT / "compat"), "compat"),
    ]
    # Include sounddevice portaudio DLL
    try:
        import _sounddevice_data
        sd_path = os.path.dirname(_sounddevice_data.__file__)
        data_files.append((sd_path, "_sounddevice_data"))
    except ImportError:
        print("  WARNING: _sounddevice_data not found — audio may not work")

    for src, dst in data_files:
        cmd += ["--add-data", f"{src}{os.pathsep}{dst}"]

    # Hidden imports
    for imp in get_hidden_imports():
        cmd += ["--hidden-import", imp]

    # Excludes
    for exc in get_torch_excludes(cpu_only):
        cmd += ["--exclude-module", exc]

    # Collect all from packages that have data files
    cmd += ["--collect-all", "faster_whisper"]
    cmd += ["--collect-all", "ctranslate2"]
    cmd += ["--collect-all", "torch"]

    # Entry point
    cmd.append(str(ROOT / "whisper_typer.py"))

    print(f"  Running: pyinstaller ...")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("\n  ERROR: PyInstaller failed!")
        sys.exit(1)

    output = DIST_DIR / SPEC_NAME
    size_mb = sum(f.stat().st_size for f in output.rglob("*") if f.is_file()) / (1024 * 1024)
    print(f"\n  SUCCESS: Bundle at {output}")
    print(f"  Size: {size_mb:.0f} MB")
    return output


def build_inno(version: str) -> Path:
    """Compile the Inno Setup script into a Windows installer."""
    iscc = find_inno()
    if not iscc:
        print("\n  Inno Setup not found!")
        print("  Download free from: https://jrsoftware.org/isdl.php")
        print("  Install it, then re-run this script.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Building installer with Inno Setup")
    print(f"{'='*60}\n")

    iss_file = ROOT / "installer" / "setup.iss"
    output_dir = ROOT / "installer" / "output"
    output_dir.mkdir(exist_ok=True)

    cmd = [
        iscc,
        f"/DAppVersion={version}",
        f"/DSourceDir={DIST_DIR / SPEC_NAME}",
        f"/DOutputDir={output_dir}",
        str(iss_file),
    ]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\n  ERROR: Inno Setup compilation failed!")
        sys.exit(1)

    # Find the output exe
    for f in output_dir.iterdir():
        if f.suffix == ".exe":
            print(f"\n  SUCCESS: Installer at {f}")
            print(f"  Size: {f.stat().st_size / (1024*1024):.0f} MB")
            return f

    print("  ERROR: No installer .exe found in output!")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Build Whisper Typer installer")
    parser.add_argument("--no-inno", action="store_true", help="Skip Inno Setup (PyInstaller only)")
    parser.add_argument("--cpu-only", action="store_true", help="Exclude CUDA for smaller bundle")
    args = parser.parse_args()

    version = get_version()
    print(f"  Whisper Typer v{version}")

    # Step 1: PyInstaller
    bundle_dir = build_pyinstaller(cpu_only=args.cpu_only)

    # Step 2: Inno Setup
    if not args.no_inno:
        installer = build_inno(version)
        suffix = "-cpu" if args.cpu_only else ""
        final_name = f"WhisperTyperSetup-v{version}{suffix}.exe"
        final_path = installer.parent / final_name
        if installer.name != final_name:
            installer.rename(final_path)
        print(f"\n  Final installer: {final_path}")
    else:
        print(f"\n  Skipped Inno Setup. Standalone bundle at: {bundle_dir}")
        print(f"  Run: {bundle_dir / 'WhisperTyper.exe'}")


if __name__ == "__main__":
    main()
