"""Linux platform backend for Whisper Typer.

Supports both X11 and Wayland display servers.  X11 gets full
functionality via xdotool/xprop/xclip; Wayland gracefully degrades
to no-ops for features the protocol doesn't expose (window enumeration,
focus stealing, snapping).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Any

from .base import PlatformBackend

log = logging.getLogger(__name__)

# ── display-server detection ────────────────────────────────────────
_SESSION_TYPE = os.environ.get("XDG_SESSION_TYPE", "x11")
_IS_WAYLAND = _SESSION_TYPE == "wayland"
_HAS_XDOTOOL = shutil.which("xdotool") is not None


def _run(cmd: list[str], *, input_: bytes | None = None) -> str | None:
    """Run *cmd* and return stripped stdout, or None on any failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            input=input_,
            timeout=3,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8", errors="replace").strip()
        return None
    except Exception:
        return None


class LinuxBackend(PlatformBackend):
    """Linux implementation — X11 first, Wayland fallback."""

    # ── identity ────────────────────────────────────────────────────
    @property
    def name(self) -> str:
        return "linux"

    # ── capability flags ────────────────────────────────────────────
    @property
    def supports_window_snapping(self) -> bool:
        return not _IS_WAYLAND and _HAS_XDOTOOL

    @property
    def supports_rounded_corners(self) -> bool:
        return False

    @property
    def supports_transparency(self) -> bool:
        return True

    @property
    def supports_terminal_finding(self) -> bool:
        return not _IS_WAYLAND and _HAS_XDOTOOL

    @property
    def snap_poll_interval_ms(self) -> int:
        return 50

    # ── clipboard ───────────────────────────────────────────────────
    def set_clipboard(self, text: str) -> bool:
        data = text.encode("utf-8")

        # Try xclip (most common on X11)
        if shutil.which("xclip"):
            if _run(["xclip", "-selection", "clipboard"], input_=data) is not None:
                return True

        # Try xsel (alternative X11)
        if shutil.which("xsel"):
            if _run(["xsel", "--clipboard", "--input"], input_=data) is not None:
                return True

        # Try wl-copy (Wayland)
        if shutil.which("wl-copy"):
            if _run(["wl-copy"], input_=data) is not None:
                return True

        log.warning("No clipboard tool found (tried xclip, xsel, wl-copy)")
        return False

    # ── terminal discovery ──────────────────────────────────────────
    def get_terminal_window_classes(self) -> list[str]:
        return [
            "gnome-terminal-server",
            "konsole",
            "xfce4-terminal",
            "xterm",
            "alacritty",
            "kitty",
            "foot",
            "tilix",
            "terminator",
        ]

    def get_terminal_title_hints(self) -> list[str]:
        return ["terminal", "konsole", "shell", "bash", "zsh"]

    def find_terminal_window(
        self,
        title_hints: list[str] | None = None,
        title_exclude: list[str] | None = None,
    ) -> int | None:
        if _IS_WAYLAND or not _HAS_XDOTOOL:
            return None

        hints = title_hints or self.get_terminal_title_hints()
        exclude = [e.lower() for e in (title_exclude or [])]

        for wm_class in self.get_terminal_window_classes():
            output = _run(["xdotool", "search", "--class", wm_class])
            if not output:
                continue

            for line in output.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    wid = int(line)
                except ValueError:
                    continue

                # Check title for exclude patterns
                title_out = _run(["xdotool", "getwindowname", str(wid)])
                title = (title_out or "").lower()

                if exclude and any(ex in title for ex in exclude):
                    continue

                # Prefer windows whose title matches a hint
                if hints:
                    if any(h.lower() in title for h in hints):
                        return wid

            # No hint-matched window — return first valid one for this class
            for line in output.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    wid = int(line)
                except ValueError:
                    continue
                title_out = _run(["xdotool", "getwindowname", str(wid)])
                title = (title_out or "").lower()
                if exclude and any(ex in title for ex in exclude):
                    continue
                return wid

        return None

    # ── focus management ────────────────────────────────────────────
    def get_foreground_window(self) -> int | None:
        if _IS_WAYLAND or not _HAS_XDOTOOL:
            return None
        output = _run(["xdotool", "getactivewindow"])
        if output is None:
            return None
        try:
            return int(output)
        except ValueError:
            return None

    def set_foreground_window(self, handle: Any) -> bool:
        if _IS_WAYLAND or not _HAS_XDOTOOL:
            return False
        return _run(["xdotool", "windowactivate", str(handle)]) is not None

    # ── paste key ───────────────────────────────────────────────────
    def get_paste_modifier(self):
        from pynput.keyboard import Key
        return Key.ctrl

    # ── window styles ───────────────────────────────────────────────
    def apply_tool_window_style(self, tk_root) -> None:
        try:
            tk_root.attributes("-topmost", True)
        except Exception:
            pass

        # Try to set skip-taskbar hint via xprop (X11)
        try:
            hwnd = self.get_tk_hwnd(tk_root)
            if hwnd is not None and shutil.which("xprop"):
                subprocess.run(
                    [
                        "xprop",
                        "-id", hex(hwnd),
                        "-f", "_NET_WM_STATE", "32a",
                        "-set", "_NET_WM_STATE",
                        "_NET_WM_STATE_SKIP_TASKBAR",
                    ],
                    capture_output=True,
                    timeout=3,
                )
        except Exception:
            pass

    def set_rounded_corners(self, tk_root, radius: int, enable: bool) -> None:
        # No-op — compositor-dependent, no portable API to control this.
        pass

    def setup_transparency(self, tk_root, transparent: bool) -> None:
        try:
            tk_root.attributes("-alpha", 0.9 if transparent else 1.0)
        except Exception:
            pass

    # ── screen geometry ─────────────────────────────────────────────
    def get_virtual_screen_bounds(self) -> tuple[int, int, int, int]:
        if _HAS_XDOTOOL:
            output = _run(["xdotool", "getdisplaygeometry"])
            if output:
                parts = output.split()
                if len(parts) >= 2:
                    try:
                        w, h = int(parts[0]), int(parts[1])
                        return (0, 0, w, h)
                    except ValueError:
                        pass
        # Sensible fallback
        return (0, 0, 1920, 1080)

    # ── window snapping ─────────────────────────────────────────────
    def get_tk_hwnd(self, tk_root) -> int | None:
        try:
            # wm_frame() returns a hex string like "0x1234567" on X11
            return int(tk_root.wm_frame(), 16)
        except Exception:
            return None

    def get_window_rect(self, handle: Any) -> tuple[int, int, int, int] | None:
        if _IS_WAYLAND or not _HAS_XDOTOOL:
            return None

        output = _run(["xdotool", "getwindowgeometry", "--shell", str(handle)])
        if output is None:
            return None

        vals: dict[str, int] = {}
        for line in output.splitlines():
            if "=" in line:
                key, _, val = line.partition("=")
                try:
                    vals[key.strip()] = int(val.strip())
                except ValueError:
                    pass

        x = vals.get("X")
        y = vals.get("Y")
        w = vals.get("WIDTH")
        h = vals.get("HEIGHT")
        if x is None or y is None or w is None or h is None:
            return None

        return (x, y, x + w, y + h)

    def is_window_valid(self, handle: Any) -> bool:
        if _IS_WAYLAND or not _HAS_XDOTOOL:
            return False
        return _run(["xdotool", "getwindowname", str(handle)]) is not None

    def is_window_minimized(self, handle: Any) -> bool:
        if _IS_WAYLAND:
            return False
        if not shutil.which("xprop"):
            return False
        try:
            output = _run(["xprop", "-id", str(handle), "_NET_WM_STATE"])
            if output is None:
                return False
            return "_NET_WM_STATE_HIDDEN" in output
        except Exception:
            return False

    def set_window_position(self, tk_hwnd: Any, x: int, y: int) -> None:
        if _IS_WAYLAND or not _HAS_XDOTOOL:
            return
        _run(["xdotool", "windowmove", str(tk_hwnd), str(x), str(y)])

    # ── subprocess helpers ──────────────────────────────────────────
    @property
    def subprocess_no_window_flags(self) -> int:
        return 0

    # ── console / ANSI ──────────────────────────────────────────────
    def enable_ansi_console(self) -> None:
        # Linux terminals support ANSI natively — nothing to do.
        pass

    # ── fonts ───────────────────────────────────────────────────────
    def get_ui_font(self) -> str:
        candidates = ["Ubuntu", "DejaVu Sans", "Noto Sans", "Liberation Sans"]
        return self._first_available_font(candidates) or "sans-serif"

    def get_mono_font(self) -> str:
        candidates = [
            "Ubuntu Mono",
            "DejaVu Sans Mono",
            "JetBrains Mono",
            "Noto Sans Mono",
        ]
        return self._first_available_font(candidates) or "monospace"

    @staticmethod
    def _first_available_font(candidates: list[str]) -> str | None:
        """Return the first font from *candidates* that tkinter knows about."""
        try:
            import tkinter
            import tkinter.font

            # Need a temporary Tk instance if one isn't already running
            try:
                root = tkinter._default_root  # type: ignore[attr-defined]
                if root is None:
                    raise AttributeError
                families = {f.lower() for f in tkinter.font.families()}
            except (AttributeError, tkinter.TclError):
                # No Tk root yet — can't query fonts; fall through to None
                return None

            for name in candidates:
                if name.lower() in families:
                    return name
        except Exception:
            pass
        return None
